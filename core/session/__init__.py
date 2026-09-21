# -*- coding: utf-8 -*-
"""会话存储 — 统一互动会话（MomoTalk + Bond Story）的持久化与恢复。

设计: core/docs/archive/DESIGN_SAVE.md（统一会话目录 + events.jsonl 事件流唯一真源 + marker 状态标记）。
分层: io（原语）→ models（meta 纯索引 + VN 恢复点）→ events/renderer → store（待实现）。

当前已落地: io 原子写/append/行级容错 + SessionMeta（纯索引）/VNState（marker payload）。
"""

from core.session.chapters import (
    chapter_index,
    replayable_chapters,
)
from core.session.events import (
    EVENT_TYPES,
    MARKER_SUBTYPES,
    M_MEMORIAL_IMAGE,
    M_SESSION_END,
    M_SESSION_START,
    M_VN_ENTER,
    M_VN_EXIT,
    M_VN_STATE,
    TYPE_BOND,
    TYPE_L2D,
    TYPE_MARKER,
    TYPE_MMT,
    TYPE_OFFICIAL,
    Event,
    make_event,
    marker,
    parse_events,
)
from core.session.io import (
    append_jsonl,
    append_jsonls,
    atomic_write_json,
    read_jsonl,
)
from core.session.models import (
    SessionMeta,
    VNState,
    now_iso,
)
from core.session.renderer import (
    filter_bond,
    render_events,
    render_timeline,
    session_status,
)
from core.session.store import DEFAULT_DATA_ROOT, SessionStore

__all__ = [
    # io
    "atomic_write_json", "append_jsonl", "append_jsonls", "read_jsonl",
    # models
    "SessionMeta", "VNState", "now_iso",
    # events
    "Event", "make_event", "marker", "parse_events",
    "EVENT_TYPES", "MARKER_SUBTYPES",
    "TYPE_MMT", "TYPE_BOND", "TYPE_L2D", "TYPE_MARKER", "TYPE_OFFICIAL",
    "M_SESSION_START", "M_VN_ENTER", "M_VN_EXIT", "M_VN_STATE", "M_SESSION_END",
    "M_MEMORIAL_IMAGE",
    # renderer
    "render_events", "filter_bond", "session_status", "render_timeline",
    # 回忆册（可回放章节派生）
    "replayable_chapters", "chapter_index",
    # store
    "SessionStore", "DEFAULT_DATA_ROOT",
]

