# -*- coding: utf-8 -*-
"""embedder.py — 本地 embedding 客户端（RAG 向量来源, core/rag/ 地基）。

对接本地 OpenAI 兼容 /v1/embeddings（LM Studio / Bionic, 默认 localhost:1234）,
跨语言 embedding 模型（如 bge-m3 / Qwen3-Embedding / multilingual-e5）由用户在
Bionic 里加载; 本模块只负责:
    - 自动发现: model 缺省时从 /v1/models 挑 id 含 "embed" 的模型（启发式）
    - 批式 embed(texts) → 等长向量（自动分批, 单次调用失败可重试）
    - 统一错误: RagError（继承 Live2BeError, [embedder.py][RagError][info]）

语义（宁缺勿错）: 服务未起 / 模型未加载 → 抛 RagError——调用方（place/brain）
自行降级（精确兜底 / tags 词面匹配）, 本层不吞错。

用法:
    from core.rag.embedder import LocalEmbedder
    emb = LocalEmbedder()                     # 自动发现 embedding 模型
    vecs = emb.embed(["school rooftop", "学校天台"])
"""
from __future__ import annotations

import time

import httpx

from core.common.errors import Live2BeError

DEFAULT_BASE_URL = "http://localhost:1234/v1"

#: 模型自动发现: id 含这些片段才当 embedding 模型（LLM 不带 embed）
_EMBED_HINTS = ("embed", "e5", "bge", "mxbai", "gte", "jina")

#: 批式上限（一次 /v1/embeddings 最多条数; 超过自动分批）
MAX_BATCH = 64

#: 单批重试次数（本地服务偶发抖动; 命中即返回）
_RETRIES = 2


class RagError(Live2BeError):
    """RAG 域错误（embedding 服务不可用/模型缺失/向量异常）。"""


class LocalEmbedder:
    """OpenAI 兼容 embedding 客户端（线程安全: 每调用独立 httpx 请求）。"""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str | None = None,
        *,
        timeout: float = 30.0,
        max_batch: int = MAX_BATCH,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_batch = max_batch
        # model 缺省 → 构造时自动发现（失败暂不抛——embed 时才需要真模型）
        self.model = model or self._auto_discover()

    # ------------------------------------------------------------------
    # 发现 / 健康
    # ------------------------------------------------------------------

    def _auto_discover(self) -> str:
        """从 /v1/models 挑 embedding 模型（id 启发式）; 找不到 → ""。"""
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
        return ids[0] if ids else ""       # 只有一个模型也认（宁可用不可断）

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
        """服务 + 模型就绪（embed 前探测; 不上抛, 调用方决定降级）。"""
        return bool(self.model)

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
