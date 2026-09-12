# -*- coding: utf-8 -*-
"""事件模型 — events.jsonl 的事件骨架 + 板块 payload（core/DESIGN_SAVE.md §4.2）。

Event 骨架: {seq, ts, type, subtype, payload}
    type    — 板块: mmt | bond | l2d | marker（预留 official_story）
    subtype — 动作名（mmt_chat / story_scene / generate / vn_state …）; 新板块只加 subtype
    payload — 板块固定 schema（文档定档; 解析层宽松, 字段级校验留给消费方/渲染器）

marker subtype（状态标记, 替代状态机, §5.1）:
    session_start / vn_enter{reason} / vn_exit /
    vn_state{round, seed, visual} / session_end{ended}

解析策略（宁缺勿错 + 复现能力）:
    - 骨架字段坏（seq 非 int / ts 空 / type 不在白名单 / subtype 空）→ 该事件丢弃
    - payload 非 dict → 视为空 dict（宽容, 不拒绝）
    - to_dict/from_dict 往返无损（复现; l2d 引用式最小 {paragraphs, choices, images}, 定档后再收紧）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

#: 板块类型（预留 official_story 官方剧情）
TYPE_MMT = "mmt"
TYPE_BOND = "bond"
TYPE_L2D = "l2d"
TYPE_MARKER = "marker"
TYPE_AFFECTION = "affection"   # 好感变化（digest 产出; 未来行为加好感同板块, subtype=行为名）
TYPE_OFFICIAL = "official_story"

EVENT_TYPES: tuple[str, ...] = (
    TYPE_MMT, TYPE_BOND, TYPE_L2D, TYPE_MARKER, TYPE_AFFECTION, TYPE_OFFICIAL,
)

#: marker subtype（状态标记）
M_SESSION_START = "session_start"
M_VN_ENTER = "vn_enter"       # payload: {parent_session_id, chapter_title?}（2026-09-05 reason 退役）
M_VN_EXIT = "vn_exit"
M_VN_ABANDON = "vn_abandon"   # ★ 废弃宣告（2026-09-07, core/session/maintenance.py）:
                              # payload {start_seq, end_seq, note?}——中断段被新章节压掉
                              # （从未续写/走完）= 废弃"未发生": 从窗口/digest 排除;
                              # 关闭语义同 vn_exit（推导 in_vn 时视同收尾）
M_VN_STATE = "vn_state"       # payload: VNState.to_dict()（round/seed/visual…）
M_MEMORIAL_ENTER = "memorial_enter"  # ★ 进入纪念子模式（§4.7）payload: {chapter_title?}
M_MEMORIAL_EXIT = "memorial_exit"    # ★ 退出纪念, 回 bond
M_MEMORIAL_IMAGE = "memorial_image"  # ★ 纪念图**异步落盘**回执（2026-09-12）:
                                     # payload {url, prompt, width, height, scene_id}
                                     # ——图是生成完才有的, 不能补写进原 bond 事件
                                     # （append-only）, 故单开一条 marker; 回放/重启
                                     # 据此恢复纪念图（见 webgui `_ensure_memorial_img`）
M_SESSION_END = "session_end"  # payload: {ended: true}

MARKER_SUBTYPES: tuple[str, ...] = (
    M_SESSION_START, M_VN_ENTER, M_VN_EXIT, M_VN_ABANDON, M_VN_STATE,
    M_MEMORIAL_ENTER, M_MEMORIAL_EXIT, M_MEMORIAL_IMAGE, M_SESSION_END,
)


def now_iso() -> str:
    return datetime.now().isoformat()


@dataclass
class Event:
    """一个事件（events.jsonl 的一行）。"""

    seq: int = 0                  # 会话内递增（重放/rewind 定位; 由 store 分配）
    ts: str = ""                  # 时间戳
    type: str = TYPE_MMT          # 板块
    subtype: str = ""             # 动作名 / marker 名
    payload: dict = field(default_factory=dict)

    @property
    def is_marker(self) -> bool:
        return self.type == TYPE_MARKER

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "seq": self.seq,
            "ts": self.ts,
            "type": self.type,
            "subtype": self.subtype,
        }
        if self.payload:
            d["payload"] = dict(self.payload)
        return d

    @classmethod
    def from_dict(cls, raw: dict | None) -> "Event | None":
        """宽松解析: 骨架坏 → None（宁缺勿错, 丢坏事件）; payload 非 dict → 空。"""
        if not isinstance(raw, dict):
            return None
        seq = raw.get("seq")
        ts = raw.get("ts")
        typ = raw.get("type")
        sub = raw.get("subtype")
        if not isinstance(seq, int) or seq < 1:
            return None
        if not isinstance(ts, str) or not ts:
            return None
        if not isinstance(typ, str) or typ not in EVENT_TYPES:
            return None
        if not isinstance(sub, str) or not sub:
            return None
        payload = raw.get("payload")
        payload = dict(payload) if isinstance(payload, dict) else {}
        return cls(seq=seq, ts=ts, type=typ, subtype=sub, payload=payload)


def make_event(
    type: str,
    subtype: str,
    payload: dict | None = None,
    *,
    seq: int = 0,
    ts: str | None = None,
) -> Event:
    """构造事件（ts 默认当前时间; seq 由调用方/store 分配）。"""
    return Event(
        seq=seq,
        ts=ts or now_iso(),
        type=type,
        subtype=subtype,
        payload=dict(payload or {}),
    )


def marker(
    subtype: str,
    payload: dict | None = None,
    *,
    seq: int = 0,
    ts: str | None = None,
) -> Event:
    """构造 marker 事件（状态标记）。"""
    return make_event(TYPE_MARKER, subtype, payload, seq=seq, ts=ts)


def parse_events(rows: list[dict]) -> list[Event]:
    """批量解析事件流行（已过 io.read_jsonl 的行级容错）: 坏骨架事件丢弃。"""
    out: list[Event] = []
    for row in rows:
        ev = Event.from_dict(row)
        if ev is not None:
            out.append(ev)
    return out
