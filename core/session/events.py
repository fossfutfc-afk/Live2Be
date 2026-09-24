# -*- coding: utf-8 -*-
"""事件模型 — events.jsonl 的事件骨架 + 板块 payload（core/docs/archive/DESIGN_SAVE.md §4.2）。

Event 骨架: {seq, ts, type, subtype, payload}
    type    — 板块: mmt | bond | l2d | marker（预留 official_story）
              · **非叙事账目**（是"账目"不是"剧情", 不进上下文也不进 digest 时间线）:
                affection（好感结算）| note（她自己的备忘录操作）—— 见 `is_content_event`
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
from typing import Any

#: 板块类型（预留 official_story 官方剧情）
TYPE_MMT = "mmt"
TYPE_BOND = "bond"
TYPE_L2D = "l2d"
TYPE_MARKER = "marker"
TYPE_AFFECTION = "affection"   # 好感变化（digest 产出; 未来行为加好感同板块, subtype=行为名）
TYPE_NOTE = "note"             # ★ 她自己的备忘录操作（2026-09-23, DESIGN_GRAPH_V4 §3.2）:
                               # append-only 的**操作**事件, 折叠成 `soul/notes.json`
                               # （派生缓存）。**不是剧情** ⇒ 见 NON_CONTENT_TYPES
TYPE_OFFICIAL = "official_story"

EVENT_TYPES: tuple[str, ...] = (
    TYPE_MMT, TYPE_BOND, TYPE_L2D, TYPE_MARKER, TYPE_AFFECTION, TYPE_NOTE,
    TYPE_OFFICIAL,
)

#: **非叙事账目** —— 是"账目"不是"剧情"（好感结算 / 她的备忘录操作）。
#: 既不进 LLM 上下文（`renderer.render_events`）, 也不进 digest 的时间线
#: （`digest.new_events` · `mmt.engine._interact_max`）。
#: ⚠️ **新增此类类型只改这里** —— 三处消费点都读 `is_content_event`。
NON_CONTENT_TYPES: tuple[str, ...] = (TYPE_AFFECTION, TYPE_NOTE)

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

#: bond 板块的 subtype —— **板事件**（= 一次演出的单位）与**补录裁决**
S_STORY_SCENE = "story_scene"
S_STORY_END = "story_end"
S_STORY_PICK = "story_pick"    # ★ 补录裁决（2026-09-21）: payload {picked, board_seq}
                               # 为什么单开一条: 板事件是**演出**（append-only 不可改,
                               # 当时确实没裁决 → `picked=None`）, 而"玩家后来补上的
                               # 那次裁决"是**之后发生的事实**。写侧见
                               # `webgui/bond/stores.py::_log_pick`, 读侧唯一规则 =
                               # `pick_supplements()`（合并回"板 + 老师那句"）。
BOARD_SUBTYPES: tuple[str, ...] = (S_STORY_SCENE, S_STORY_END)

#: note 板块的 subtype —— 备忘录的**操作**（DESIGN_GRAPH_V4 §3.2: 真源 = 操作事件,
#: `soul/notes.json` = 折叠出来的派生缓存）:
#: `add` 加一条（**不需要理由**）· `close` 闭合一条（**必须给理由** —— 闭合即固化进图（§6）,
#: 没有理由就判不出 `kept`/`broken`/`superseded`; **close = 移除, 不留状态**）·
#: `rewrite` 整体重写（全景轮写 **B 类快照槽**, 不碰 `promise`）。
#: 条目的 `id` 由**引擎**在折叠时分配（`wiki_v2/notes.fold`）。
N_ADD = "add"
N_CLOSE = "close"
N_REWRITE = "rewrite"
NOTE_SUBTYPES: tuple[str, ...] = (N_ADD, N_CLOSE, N_REWRITE)

MARKER_SUBTYPES: tuple[str, ...] = (
    M_SESSION_START, M_VN_ENTER, M_VN_EXIT, M_VN_ABANDON, M_VN_STATE,
    M_MEMORIAL_ENTER, M_MEMORIAL_EXIT, M_MEMORIAL_IMAGE, M_SESSION_END,
)


def is_board_event(e: Any) -> bool:
    """是**板**事件吗（演出单位——`bond/story_pick` 不是板, 别当场景渲染/计数）。"""
    return (getattr(e, "type", None) == TYPE_BOND
            and getattr(e, "subtype", "") in BOARD_SUBTYPES)


def is_content_event(e: Any) -> bool:
    """是**叙事内容**事件吗 —— digest 时间线与"本段互动"的**唯一判据**。

    排除两类: `marker`（状态标记）· `NON_CONTENT_TYPES`（好感结算 / note 操作）。

    ⚠️ **2026-09-23 收敛**: 这条判据此前以 `e.type != "affection"` 的形式**抄在两处**
    （`digest.new_events` · `mmt.engine._interact_max`）。`note` 一落地就会从那儿漏进去
    —— 她的笔记操作会被**当成一段剧情消化掉**, 还会把"本段互动 max seq"（好感事件的
    幂等键）顶到一条没有内容的账目上。故收成一处: **新增非叙事类型只改
    `NON_CONTENT_TYPES`, 三处消费点自动生效。**
    """
    return (not getattr(e, "is_marker", False)
            and getattr(e, "type", None) not in NON_CONTENT_TYPES)


def pick_supplements(events: list) -> dict[int, str]:
    """补录裁决 → `{board_seq: picked}`（2026-09-21）——**读侧唯一规则**。

    场景: 玩家在**未裁决的选项板**上退出 → `bond_finish` 以 `picked=None` 把板补录
    （板 = 演出, 当时确实没裁决, 事实正确）; 重进后玩家补的那次裁决落成一条独立的
    `bond/story_pick`。渲染 / 认章 / 回放**一律把两者合并回"板 + 老师那句"**:
    合并后与"正常裁决过的板"逐字同形, 所以规则只有这一处（不再有"顺序相邻"这类隐式约定）。
    """
    out: dict[int, str] = {}
    for e in events:
        if getattr(e, "type", None) != TYPE_BOND \
                or getattr(e, "subtype", "") != S_STORY_PICK:
            continue
        p = getattr(e, "payload", None) or {}
        picked = p.get("picked")
        seq = p.get("board_seq")
        if isinstance(picked, str) and picked.strip() and isinstance(seq, int):
            out[seq] = picked.strip()
    return out


def now_iso() -> str:
    """事件时间戳 —— **转调 `age.now_ts()`**（带固定时区的**单一真源**）。

    2026-09-17（时间轴换代）收敛: 本函数是 `make_event` 的默认 `ts`,
    而 `make_event` 是**绝大多数 `ts` 的实际出口**（`store.append_event` 里那处
    只是 fallback）。保留函数名 —— 多处调用点认的是它。
    """
    from core.worldtime.age import now_ts
    return now_ts()


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
