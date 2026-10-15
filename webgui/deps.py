"""webgui 的**显式接缝**（可替换依赖）——拆分节点 C1a（`docs/EXEC_SPLIT.md`）。

## 为什么单列这个模块

测试要替换 store / 生图器 / 标注入队 / 看门狗阈值; 而 `webgui/bond.py` 要拆成包
（C1b 起）——**模块→包之后, 子模块读的是自己的全局**: `monkeypatch.setattr(bond, …)`
会**静默失效**（测试照旧绿, 覆盖全丢）。所以把这些"可替换的东西"集中到这里,
消费方一律写 `deps.xxx`（**调用时**属性查找 ⇒ patch 生效）, 测试 patch `deps.xxx`。
守门在 `tests/core/test_split_safety.py`（禁止再 patch 被拆包的属性）。

## 纪律

· 只放**叶子依赖**（store / 生图 / 阈值 / 开关 / 钩子）, 不放业务逻辑;
· **不要** `from webgui.deps import store` 再直接调用——那又把名字绑死了;
  写 `from webgui import deps` + `deps.store()`。
"""
from __future__ import annotations

import logging
from typing import Any

from core.session import SessionStore
from infra import paths
from llm.image_gen import ImageGenerator, image_enabled

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ① 会话存储（测试靠它把世界线指到 tmp_path; `webgui/chat.py` 与 bond 共用）
# ---------------------------------------------------------------------------

#: 运行时数据根（**固定路径的唯一来源**是 `infra/paths.py`，见那里的约定）
DATA_ROOT = paths.DATA_DIR

#: 当前世界线存储（`set_store()` / 测试 monkeypatch 替换; 读一律走 `store()`）
_store: SessionStore = SessionStore(DATA_ROOT)


def store() -> SessionStore:
    """当前会话存储（**每次调用都读模块全局** —— 替换后才能生效）。"""
    return _store


def set_store(st: SessionStore) -> None:
    """替换会话存储（测试 / 多世界线切换）。"""
    global _store
    _store = st


# ---------------------------------------------------------------------------
# ② 生图器（懒初始化缓存 + 总开关）
# ---------------------------------------------------------------------------

#: 生图器懒初始化缓存（首次纪念触发才构造——无 key 环境零开销）
_image_gen: ImageGenerator | None = None


def image_generator() -> ImageGenerator | None:
    """懒初始化生图器。总开关关 / 未配 IMAGE_API_KEY → None = 纪念降级纯文字。

    本地 diffusers 兜底已于 2026-09-10 移除（出图"不像人类"）——只有 APIYI 一条路。
    **总开关**（`image_enabled`: `LIVE2BE_IMAGE=off` / settings `[image].enabled=false`,
    2026-09-11）在此设卡: 关闭即**不构造、不开生图线程**——跑测试/离线调试的确定性
    关闭（key 配着时否则真会出图烧钱）。
    """
    global _image_gen
    if not image_enabled():
        if _image_gen is None or _image_gen.enabled:
            logger.info("生图总开关为关（LIVE2BE_IMAGE/settings [image].enabled）"
                        "——纪念场景降级纯文字")
        return None
    if _image_gen is None:
        try:
            _image_gen = ImageGenerator()
        except Exception as e:                   # noqa: BLE001 — 构造失败降级
            logger.warning("生图器初始化失败（纪念降级纯文字）: %s", e)
            return None
    else:
        _image_gen.enabled = True                # 开关回调（关过又开）——缓存实例跟手
    if not _image_gen.available:
        return None
    return _image_gen


# ---------------------------------------------------------------------------
# ③ 标注入队（**可替换钩子**）——测试常把它换成 no-op 以关掉 lane
# ---------------------------------------------------------------------------

def enqueue_annotate(state: Any, scene: Any) -> None:
    """场景入队异步标注（默认转发到 `webgui.bond.lanes` 的真实实现）。

    为什么绕一层: 测试需要"关掉标注 lane"（`setattr(deps, "enqueue_annotate", noop)`）,
    而真实实现依赖 bond 的内部状态。C4 把 lane 搬进 `webgui.bond.lanes` 后,
    转发目标已指向新家（C8 拆 `api.py` 时若再挪, 只改这一行）。
    """
    from webgui.bond.lanes import _enqueue_annotate as _impl
    _impl(state, scene)


# ---------------------------------------------------------------------------
# ④ 看门狗阈值（`bond_status` 顺手调用; 测试会把它们调小/调负以逼出兜底）
# ---------------------------------------------------------------------------

#: 忙态/视觉门卡住多久算异常 → 兜底放行（2026-09-11）
BUSY_WATCHDOG_MS = 300_000     # 5min（LLM client 超时 240s + 余量）: 超时且线程不在 → 复位
GATE_WATCHDOG_MS = 25_000      # 视觉门 25s 未就绪且 lane 空闲 → 强制兜底就绪
PREGEN_GATE_WATCHDOG_MS = 25_000   # 预生成消费门 25s 未通过 → 强制兜底就绪并消费


# ---------------------------------------------------------------------------
# ⑤ choice 候选预生成开关（settings.toml; 测试可替换成常量）
# ---------------------------------------------------------------------------

#: 运行时开关读取路径（`infra/paths.py` 的宏 —— settings.toml, gitignore, 本机 GUI 设置文件）
CAND_SETTINGS_PATH = paths.SETTINGS_PATH


def choice_pregen_enabled() -> bool:
    """choice_pregen 开关（DESIGN_CHOICE_PREGEN §4, N2d）:

    settings.toml [bond] choice_pregen = "off" | "sibling" | "tree"
    - sibling: 单层候选预生成（当前实现; tree 暂同 sibling——递归展开未做,
      预判收益趋零不做）; off: 关闭（走分支播放期单路 pregen 老路）。
    - 读取失败/缺省 → True（sibling——功能默认开, 不稳可一键关）。
    """
    try:
        import tomllib
        text = CAND_SETTINGS_PATH.read_text(encoding="utf-8")
        mode = str(((tomllib.loads(text).get("bond") or {})
                    .get("choice_pregen") or "sibling")).strip().lower()
        return mode in ("sibling", "tree")
    except Exception:                              # noqa: BLE001 — 缺省开
        return True


__all__ = [
    "BUSY_WATCHDOG_MS", "CAND_SETTINGS_PATH", "DATA_ROOT", "GATE_WATCHDOG_MS",
    "ImageGenerator", "PREGEN_GATE_WATCHDOG_MS", "choice_pregen_enabled",
    "enqueue_annotate", "image_enabled", "image_generator", "set_store", "store",
]
