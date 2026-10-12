"""embedder.py — 本地 embedding 客户端（RAG 向量来源, core/rag/ 地基）。

对接本地 OpenAI 兼容 `/v1/embeddings`（LM Studio / llama.cpp / Bionic 等），
跨语言 embedding 模型（如 bge-m3 / Qwen3-Embedding / multilingual-e5）由用户加载;
本模块只负责:
    - **配置发现**: `settings.toml [embed]` > `LIVE2BE_EMBED_*` > 默认（见下）
    - **模型发现**: `model` 一路都空时，从 `/v1/models` 挑 id 含 "embed" 的模型
    - 批式 embed(texts) → 等长向量（自动分批, 单次调用失败可重试）
    - 统一错误: RagError（继承 Live2BeError, [embedder.py][RagError][info]）

**地址默认 1234 只是"LM Studio 的常见端口"，不是约定**——2026-09-15（T18）之前
它是硬编码的、没有配置面, 于是"本机装好的模型对代码不可见"（Qwen3 在 1235,
代码只会去敲 1234）。配置面见 `_settings_embed_cfg` 的 docstring。

语义（宁缺勿错）: 服务未起 / 模型未加载 → 抛 RagError——调用方（place/brain）
自行降级（精确兜底 / tags 词面匹配）, 本层不吞错。

用法:
    from core.rag.embedder import LocalEmbedder
    emb = LocalEmbedder()                     # 走配置链 + 自动发现
    vecs = emb.embed(["school rooftop", "学校天台"])
"""
from __future__ import annotations

import logging
import os
import time

import httpx

from core import paths
from core.common.errors import Live2BeError

logger = logging.getLogger(__name__)

#: 默认服务地址（LM Studio 的常见端口; **可被 [embed].base_url 覆盖**）
DEFAULT_BASE_URL = "http://localhost:1234/v1"

#: 项目根 + settings.toml（`core/paths.py` 的宏）
_PROJECT_ROOT = paths.ROOT

#: settings.toml（与 `[llm]` / `[image]` / `[recall]` 同一份；缺失/损坏 → 默认）
_SETTINGS_PATH = paths.SETTINGS_PATH

#: 环境变量（进程级; `.env` 亦被加载——见 `_load_dotenv_once`）
ENV_BASE = "LIVE2BE_EMBED_BASE"
ENV_MODEL = "LIVE2BE_EMBED_MODEL"

_DOTENV_DONE = False


def _load_dotenv_once() -> None:
    """懒加载项目根 `.env`（**只一次**, 失败静默）。

    为什么不学 `llm/client.py` 在模块级 `load_dotenv`: 那样"有没有 .env"取决于
    **谁先被 import**。而 embedder 被 `core/mmt/engine.py` 与 `core/rag/*` 共用,
    调用序不固定（测试里尤其）→ 显式加载一次, **不靠 import 顺序**。
    """
    global _DOTENV_DONE
    if _DOTENV_DONE:
        return
    _DOTENV_DONE = True
    try:
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env")
    except Exception:                            # noqa: BLE001 — 无 dotenv/无 .env 都正常
        pass


def _settings_embed_cfg() -> dict:
    """读项目根 `settings.toml` 的 `[embed]` 分组（缺失/损坏 → `{}`, 不阻塞）。

    **2026-09-15（T18）新增**——此前 `LocalEmbedder` **没有任何配置面**:
    `DEFAULT_BASE_URL` 硬编码 1234, 模型靠 id 启发式自动发现。后果不是"少个旋钮"
    而是**本机装好的模型对代码不可见**: 实验里 Qwen3 监听的是 1235, 而代码只会
    去敲 1234。配置面缺位时, 唯一能"接入"的办法是**把服务挪到代码猜的那个端口**——
    那是让配置迁就代码。

    形态（与 `[llm]` / `[image]` 同构，可被 GUI 设置页安全共存——`webgui/store.py`
    的 `load_settings` 会合并未知分组、`save_settings` 保真落盘）::

        [embed]
          base_url = "http://localhost:1235/v1"
          model    = "Qwen3-Embedding-0.6B"
    """
    if not _SETTINGS_PATH.is_file():
        return {}
    try:
        import tomllib
        data = tomllib.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, ImportError):
        return {}
    section = data.get("embed") if isinstance(data, dict) else None
    return section if isinstance(section, dict) else {}


def _cfg_str(section: dict, key: str) -> str:
    v = section.get(key)
    return v.strip() if isinstance(v, str) and v.strip() else ""


#: 模型自动发现: id 含这些片段才当 embedding 模型（LLM 不带 embed）
_EMBED_HINTS = ("embed", "e5", "bge", "mxbai", "gte", "jina")

#: 批式上限（一次 /v1/embeddings 最多条数; 超过自动分批）
MAX_BATCH = 64

#: 单批重试次数（本地服务偶发抖动; 命中即返回）
_RETRIES = 2


class RagError(Live2BeError):
    """RAG 域错误（embedding 服务不可用/模型缺失/向量异常）。"""


class LocalEmbedder:
    """OpenAI 兼容 embedding 客户端（线程安全: 每调用独立 httpx 请求）。

    **配置优先级（与 `llm/client.py` / `llm/image_gen.py` 同一条链）**::

        构造参数  >  settings.toml [embed]  >  环境变量  >  默认

    环境变量 = `LIVE2BE_EMBED_BASE` / `LIVE2BE_EMBED_MODEL`（`.env` 亦被加载）。
    `model` 一路都空 → 退回**自动发现**（`/v1/models` 里 id 含 embed 的那个）。
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        *,
        timeout: float = 30.0,
        max_batch: int = MAX_BATCH,
    ) -> None:
        _load_dotenv_once()
        cfg = _settings_embed_cfg()
        self.base_url = (
            base_url or _cfg_str(cfg, "base_url")
            or os.getenv(ENV_BASE, DEFAULT_BASE_URL)
        ).rstrip("/")
        self.timeout = timeout
        self.max_batch = max_batch
        # 模型: 构造参数 > settings.toml > env > 自动发现。
        # ⚠️ 配了模型就**不做发现**（否则每次构造都要打一次 /v1/models）——
        # 但那样一来"名字打错"就没人发现了, 所以 health() 必须真探一次（见下）。
        cfg_model = (model or _cfg_str(cfg, "model")
                     or os.getenv(ENV_MODEL, "").strip())
        self._healthy: bool | None = None            # health() 的探测缓存
        if cfg_model:
            self.model = cfg_model
        else:
            self.model = self._auto_discover()
            self._healthy = bool(self.model)         # 刚列过模型表 = 服务已通

    # ------------------------------------------------------------------
    # 发现 / 健康
    # ------------------------------------------------------------------

    def _auto_discover(self) -> str:
        """从 `/v1/models` 挑 embedding 模型（id 启发式）; 找不到 → `""`。

        ⚠️ **刻意不盲选 `ids[0]`**（2026-09-15）: 旧实现末尾是
        `return ids[0] if ids else ""`（"只有一个模型也认——宁可用不可断"）。
        那在"这台机器只跑了一个 **LLM**"时是**有毒**的: 拿 LLM 的 id 当 embedding
        模型 → `health()` True → 每轮 embed 全失败, 而日志只说"调用失败",
        看不出是**端口指错了服务**。本机正是这种布局（embedding 在 1235,
        1234 另有用）→ 宁可返回 `""`: `health()` False, 上层走关键词兜底并打一行
        `digest_embed fn=none`。**宁可降级, 不可用错。**
        """
        try:
            with httpx.Client(timeout=min(self.timeout, 10)) as client:
                r = client.get(f"{self.base_url}/models")
                r.raise_for_status()
        except Exception:
            return ""
        ids = [m.get("id", "") for m in r.json().get("data", []) if isinstance(m, dict)]
        for hint in _EMBED_HINTS:
            hit = next((i for i in ids if hint.lower() in i.lower()), None)
            if hit:
                return hit
        logger.warning("[embed] %s 上没有可识别的 embedding 模型（列表: %s）"
                       "——不盲选; 请确认端口, 或显式配 settings.toml [embed].model",
                       self.base_url, ids or "（空）")
        return ""

    def available_models(self) -> list[str]:
        """当前服务已加载的全部模型 id（供上层挑选/排查）。"""
        try:
            with httpx.Client(timeout=min(self.timeout, 10)) as client:
                r = client.get(f"{self.base_url}/models")
                r.raise_for_status()
        except Exception as e:
            raise RagError(f"模型列表不可用: {e}") from e
        return [m.get("id", "") for m in r.json().get("data", []) if isinstance(m, dict)]

    def health(self) -> bool:
        """服务 + 模型就绪（embed 前探测; 不上抛, 调用方决定降级）。

        **2026-09-15（T18）改真**: 旧实现是 `bool(self.model)` —— 自动发现年代
        它等价于"刚敲通 `/v1/models`", 够用。但**配置面一上来它就不够了**:
        手写的 `model` 名字打错时 `bool(model)` 仍为 True, 于是 `_get_embed_fn()`
        报 `fn=ok`, 而每次 embed 都 404 → 降级日志只说"调用失败", 看不出根因。
        现在: 配来的模型**真探一次**（可达 **且** 在模型表里）, 结果缓存。
        """
        if not self.model:
            return False
        if self._healthy is None:
            self._healthy = self._probe_model()
        return self._healthy

    def _probe_model(self) -> bool:
        """服务可达 **且** 该模型在 `/v1/models` 里（打错名字在这里挡住）。"""
        try:
            return self.model in self.available_models()
        except RagError:
            return False

    # ------------------------------------------------------------------
    # 核心: embed
    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批式 embedding。空输入 → []。服务/模型故障 → RagError（调用方降级）。"""
        texts = [t for t in texts if isinstance(t, str)]
        if not texts:
            return []
        if not self.model:
            raise RagError("无 embedding 模型: 请在 Bionic/LM Studio 加载后重试")
        out: list[list[float]] = []
        for start in range(0, len(texts), self.max_batch):
            chunk = texts[start : start + self.max_batch]
            out.extend(self._embed_chunk(chunk))
        return out

    def embed_one(self, text: str) -> list[float]:
        """单条 embedding（query 侧常用）。"""
        vecs = self.embed([text])
        return vecs[0] if vecs else []

    def _embed_chunk(self, texts: list[str]) -> list[list[float]]:
        last_err: Exception | None = None
        for attempt in range(_RETRIES + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    r = client.post(
                        f"{self.base_url}/embeddings",
                        json={"model": self.model, "input": texts},
                    )
                    r.raise_for_status()
                    data = r.json().get("data", [])
                    data.sort(key=lambda d: d.get("index", 0))
                    vecs = [d["embedding"] for d in data]
                if len(vecs) != len(texts):
                    raise RagError(
                        f"向量数不匹配: {len(vecs)} != {len(texts)}"
                    )
                return vecs
            except RagError:
                raise
            except Exception as e:               # noqa: BLE001 — 传输层重试
                last_err = e
                time.sleep(0.5 * (attempt + 1))
        raise RagError(f"embedding 调用失败: {last_err}") from last_err

    # ------------------------------------------------------------------
    # 便捷: cosine（召回用同一实现——recall.py 已有内部版, 这里供新代码用）
    # ------------------------------------------------------------------

    @staticmethod
    def cosine(a: list[float], b: list[float]) -> float:
        """余弦相似度（空向量 → 0）。"""
        na = sum(x * x for x in a)
        nb = sum(x * x for x in b)
        if na == 0 or nb == 0:
            return 0.0
        return sum(x * y for x, y in zip(a, b)) / (na ** 0.5 * nb ** 0.5)
