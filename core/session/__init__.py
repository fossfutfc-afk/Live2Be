# -*- coding: utf-8 -*-
"""会话存储 — 统一互动会话（MomoTalk + Bond Story）的持久化与恢复。

设计: core/DESIGN_SAVE.md（统一会话目录 + jsonl append-only + 状态机）。
分层: io（原语）→ models（dataclass）→ store（SessionStore 生命周期, 待实现）。

当前已落地: io 原子写/append/行级容错 + SessionMeta/VNState 模型。
"""

from core.session.io import (
    append_jsonl,
    append_jsonls,
    atomic_write_json,
    read_jsonl,
)
from core.session.models import (
    STATE_ACTIVE,
    STATE_ENDED,
    STATE_INTERRUPTED,
    STATE_PAUSED,
    TYPE_BOND,
    TYPE_MMT,
    SessionMeta,
    VNState,
    now_iso,
)

__all__ = [
    # io
    "atomic_write_json", "append_jsonl", "append_jsonls", "read_jsonl",
    # models
    "SessionMeta", "VNState", "now_iso",
    "TYPE_MMT", "TYPE_BOND",
    "STATE_ACTIVE", "STATE_PAUSED", "STATE_ENDED", "STATE_INTERRUPTED",
]
