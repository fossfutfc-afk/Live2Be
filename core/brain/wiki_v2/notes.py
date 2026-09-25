# -*- coding: utf-8 -*-
"""notes.py — 随身笔记（note）: **操作事件 → 折叠状态 → 注入块**（DESIGN_GRAPH_V4 §3.2 / §6）。

note 是**三种组织形式**里的第二种（图 / **笔记** / 台账, §1.1）:
**图管"可查的细节", note 管"此刻"**。它不是记忆（不改写历史）、不是人设（不装设定）、
也不是图的镜像 —— 只装**她自己挑过的**。

    真源   `soul/events.jsonl`   append-only 的**操作**（`add` / `close` / `retire` / `rewrite`）
    缓存   `soul/notes.json`     `fold()` 的结果 + `up_to_seq` 水位（可随时重建）

⇒ **并发安全**（主 LLM 与 digest 同时写不丢更新）· **可回放** · **与水位同频**。

三槽（§3.2 的"按引擎要不要处理二分"）:

| 槽 | 类 | 装什么 | 更新模型 | 写者 |
|---|---|---|---|---|
| `promise` | **A 操作式** | 还没做的事（约定 / 承诺） | `add` / **`close` 结清** / **`retire` 退场** | 加 · 结清 = 当场（MMT 输出字段）或 digest 收口 · 退场 = 固化那一批 |
| `habits` | **B 快照式** | 我们之间的惯例 / 他的习惯 | 全景轮**整段替换** | 只全景轮 |
| `on_mind` | **B 快照式** | 我最近在意的（一段散文） | 全景轮**整段替换** | 只全景轮 |

**四条纪律**（写进形状里, 不靠自觉）:

0. ⭐ **`close` 是"结清", 不是"划掉"；划掉是 `retire`** —— 承诺是唯一"note 是它唯一落脚点"
   的东西（图里要等固化才有它, 而上下文窗口从来不是保证）。所以两段式:
   **结清 ⇒ 条目留在块里（尾巴换成理由）→ 图侧接住 ⇒ `retire` 才真删**。
   ⇒ **不变量: 一条承诺任何时刻至少在一个可见面上**（note 或图）, 永不在两者之外。
1. **`close` 必须给理由, `add` / `retire` 不用** —— "为什么这条不再开着了"既是**固化那一步**
   （§6: 判 `kept`/`broken`/`superseded`）的唯一原料, 也是她读到的那句话。读侧遇到没理由的
   close **照做但记响**（不认它反而会让本子停在过去）, 写侧直接拒。
   ⚠️ **已结清的不再覆盖**: 块里印着 id, 若二次 close 能改写 `reason`, 就是给"拿幻觉理由
   覆盖真实理由"开后门 ⇒ 第二次只告警（幂等 = 忽略）。
2. **`id` 只增不复用** —— `close`/`retire` 只带 `id`, 复用会让旧引用指错条目。故计数器 `next_n`
   必须随状态走, **不能从"活着的条目"推**（结清 n3 之后活着的是 n1/n2）。
3. **物品一个字都不进 note** —— 痕迹 → `episode.items`; 当前持有 → `inventory`（§3.3）;
   情感意义 → 就在那条 episode 的正文里。**没有 `gifts` 槽**。

本模块**纯函数、零 IO**（不碰文件 / 不碰 store / 不调 LLM）: 落盘归 `store.py`, 注入归引擎。
这样折叠能直接单测, 也保证"缓存可重建"这句话是真的。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from core.brain.wiki_v2.nodes import PROMISE_OUTCOMES   # 结局枚举的运行时真源（同包）
from core.common import err
from core.session.events import (
    N_ADD,
    N_CLOSE,
    N_RETIRE,
    N_REWRITE,
    TYPE_NOTE,
    make_event,
)

logger = logging.getLogger(__name__)

#: 三个槽（顺序 = 渲染顺序 = 清单顺序）
SLOT_PROMISE = "promise"
SLOT_HABITS = "habits"
SLOT_ON_MIND = "on_mind"
SLOTS: tuple[str, ...] = (SLOT_PROMISE, SLOT_HABITS, SLOT_ON_MIND)
#: **A 操作式**槽（增量 add/close）与 **B 快照式**槽（rewrite 整段替换）。
#: ⚠️ 这个二分就是"同一段只有一个写者"的实现: `close` 只作用于 A 类, `rewrite` 只碰 B 类。
OPSLOTS: tuple[str, ...] = (SLOT_PROMISE,)
SNAPSHOT_SLOTS: tuple[str, ...] = (SLOT_HABITS, SLOT_ON_MIND)

#: 上限（**超限只告警不截断** —— 丢哪条是她的判断, 交全景轮, 引擎不替她决定）
MAX_PROMISE = 5
MAX_HABITS = 5
MAX_ON_MIND = 1
#: 条目正文上限（§3.2: **名词短语 ≤20 字, 不写陈述句** —— 免得与 episode 的叙述竞争）
MAX_TEXT = 20
#: "结清未退场"的积压上限（**只告警**）—— 它是**正常态**（就是固化的待办队列）,
#: 所以不逐条报; 超过这个数才说明"收口没跑到 / 图侧一直没接住"。
MAX_CLOSED_PENDING = 3

#: 注入块标题 —— ⚠️ 必须**说清这是什么**（是她自己记的, 不是系统/别人派的任务; 编号是索引）,
#: 且**不含任何结构化痕迹**（无 JSON / 无键名 / 无波括号 —— **存 JSON, 看中文**, §3.2）。
TITLE = ("【你自己记的备忘录】（你自己随手记下的, 不是别人给你的任务; "
         "括号里是编号, 指回你记忆里的那件事）")
#: 槽 → 小节抬头（**自然语言**, 用设计稿自己的词: 约定 / 惯例 / 最近在想）。
#: ⚠️ **空槽不印抬头**（否则每个空槽都白占一行常驻预算）。
GROUP_LEADS: dict[str, str] = {SLOT_PROMISE: "· 你自己记下的约定",
                               SLOT_HABITS: "· 你们之间的惯例",
                               SLOT_ON_MIND: "· 最近在想"}
#: 抬头缩进 / 条目缩进（两级 —— 一瞥看得出手上开着几条）
_LEAD_INDENT = "  "
_ITEM_INDENT = "    "
#: 时间短语前缀（`§3.2` 渲染示例: `← 记于 3 天前`）
SINCE_LEAD = "  ← 记于 "
#: 结清行的状态词 —— ⚠️ **按 `state` 分三种说法**（2026-09-25）: `close` 也覆盖
#: **失约 / 不做了 / 被取代**, 所以光板一句"已完成"会撒谎。缺 `state`（旧事件）→ 中性兜底。
CLOSED_WORDS: dict[str, str] = {"kept": "已兑现", "broken": "没做到",
                                "superseded": "被新的取代了"}
#: 兜底状态词（没有 `state` 时）
CLOSED_LEAD = "  ← 已结清"

#: 槽 → 上限（`check` 用）
_CAPS: dict[str, int] = {SLOT_PROMISE: MAX_PROMISE,
                         SLOT_HABITS: MAX_HABITS,
                         SLOT_ON_MIND: MAX_ON_MIND}


# ---------------------------------------------------------------------------
# 形状
# ---------------------------------------------------------------------------

@dataclass
class NoteItem:
    """一条笔记（三槽共用形状: `{id, text, refs, since(, due)}` + 结清两字段）。

    `id`    —— 引擎在**折叠**时分配（`n1`/`n2`…, 全槽共享一个计数器, 只增不复用）。
               `on_mind` 是**单条散文**（不是索引条目, 没人会去 `close` 它）⇒ **无 id**。
    `text`  —— 名词短语 ≤ `MAX_TEXT` 字（"周六模型店" ≠ "我们约好周六去模型店"）。
    `refs`  —— ≥1, 指向**现存节点**（悬空 → `check()` 告警, 不阻断）。
    `since` —— 记于何时（引擎填 = 那条操作的 `ts`; 渲染成"记于 N 天前"）。
    `due`   —— `promise` 可选; ⚠️ **只存不渲染**（渲染成日期会诱使她"数日子",
               与 `worldtime.age` 那条"绝不输出精确值"直接冲突）。
    `closed_at` / `reason` / `state` —— **结清**（`closed_at` 非空 = 已结清）:
               她做完了 / 没成 / 被新的取代了（`state` = `kept`/`broken`/`superseded`）, 以及"为什么"。
               ⚠️ 字段名在这里是 **`state`**（节点侧叫 `outcome` —— entity 的 `state` 是 list, 撞类型;
               而 note 条目没有那个字段, 所以沿用它。两处同义不同名）。
    """

    id: str = ""
    text: str = ""
    refs: list[str] = field(default_factory=list)
    since: str = ""
    due: str = ""
    closed_at: str = ""
    reason: str = ""
    state: str = ""

    @property
    def closed(self) -> bool:
        """已结清（**还在 note 里**, 等图侧接住才退场）。"""
        return bool(self.closed_at)

    def copy(self) -> "NoteItem":
        return NoteItem(id=self.id, text=self.text, refs=list(self.refs),
                        since=self.since, due=self.due,
                        closed_at=self.closed_at, reason=self.reason,
                        state=self.state)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"text": self.text, "refs": list(self.refs),
                             "since": self.since}
        if self.id:
            d["id"] = self.id
        if self.due:
            d["due"] = self.due
        if self.closed_at:
            d["closed_at"] = self.closed_at
        if self.reason:
            d["reason"] = self.reason
        if self.state:
            d["state"] = self.state
        return d

    @classmethod
    def from_dict(cls, raw: Any) -> "NoteItem | None":
        """宽松读（坏值 → None）—— `on_mind` 也接受**裸字符串**（只有正文）。"""
        if isinstance(raw, str):
            raw = {"text": raw}
        if not isinstance(raw, dict):
            return None
        text = str(raw.get("text") or "").strip()
        if not text:
            return None
        return cls(id=str(raw.get("id") or "").strip(),
                   text=text,
                   refs=_str_list(raw.get("refs")),
                   since=str(raw.get("since") or "").strip(),
                   due=str(raw.get("due") or "").strip(),
                   closed_at=str(raw.get("closed_at") or "").strip(),
                   reason=str(raw.get("reason") or "").strip(),
                   state=str(raw.get("state") or "").strip())


@dataclass
class NotesState:
    """折叠结果 = `soul/notes.json` 的内容（**派生缓存**, 可随时从事件流重建）。

    `up_to_seq` —— 已折进的**最大事件 seq**（增量折叠的水位）。
    `next_n`    —— 下一个 `id` 号（纪律 2: 只增不复用 ⇒ 不能从活着的条目推）。
    """

    up_to_seq: int = 0
    next_n: int = 1
    promise: list[NoteItem] = field(default_factory=list)
    habits: list[NoteItem] = field(default_factory=list)
    on_mind: NoteItem | None = None

    def items(self, slot: str) -> list[NoteItem]:
        """槽 → 条目列表（`on_mind` 折成 0/1 条的列表, 便于统一校验/渲染）。"""
        if slot == SLOT_ON_MIND:
            return [self.on_mind] if self.on_mind is not None else []
        return list(getattr(self, slot, []) or [])

    def clone(self) -> "NotesState":
        return NotesState(up_to_seq=self.up_to_seq, next_n=self.next_n,
                          promise=[it.copy() for it in self.promise],
                          habits=[it.copy() for it in self.habits],
                          on_mind=self.on_mind.copy() if self.on_mind else None)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"up_to_seq": self.up_to_seq, "next_n": self.next_n,
                             SLOT_PROMISE: [it.to_dict() for it in self.promise],
                             SLOT_HABITS: [it.to_dict() for it in self.habits]}
        if self.on_mind is not None:
            d[SLOT_ON_MIND] = self.on_mind.to_dict()
        return d

    @classmethod
    def from_dict(cls, raw: Any) -> "NotesState":
        """宽松读（坏文件 → 空状态 = 现折一遍就回来了, 不会丢真源）。"""
        if not isinstance(raw, dict):
            return cls()
        promise = _items_of(raw.get(SLOT_PROMISE))
        habits = _items_of(raw.get(SLOT_HABITS))
        next_n = _int(raw.get("next_n"))
        if next_n < 1:                     # 旧档/坏档: 从活着的 id 推一个下界（防复用）
            next_n = _derive_next_n(promise + habits)
        return cls(up_to_seq=max(0, _int(raw.get("up_to_seq"))),
                   next_n=next_n,
                   promise=promise, habits=habits,
                   on_mind=NoteItem.from_dict(raw.get(SLOT_ON_MIND)))


# ---------------------------------------------------------------------------
# 折叠: 操作事件 → 状态（纯函数）
# ---------------------------------------------------------------------------

def fold(events: Iterable[Any], *, base: NotesState | None = None) -> NotesState:
    """事件流 → 笔记状态。

    增量: 给 `base` 就只折 `seq > base.up_to_seq` 的（省重复工作）; 不给就**全量重折**
    （`notes.json` 丢了 / 落后时的重建路径 —— 两条路的结果逐字节相同）。

    ⚠️ `base` 必须恰好是"折到 `up_to_seq` 为止"的状态 —— `id` 由**折叠次序**分配,
       喂一个半途的状态会让编号错位（与水位纪律同理）。

    读侧**宽松**: 坏操作只告警不抛。`notes.json` 是派生缓存, 折不出来 = 她凭空失忆,
    而一条坏事件不该有这个权力。
    """
    st = base.clone() if base is not None else NotesState()
    ops = [e for e in events
           if getattr(e, "type", None) == TYPE_NOTE
           and _int(getattr(e, "seq", 0)) > st.up_to_seq]
    ops.sort(key=lambda e: _int(getattr(e, "seq", 0)))       # 防御: 折叠次序 = seq 序
    for e in ops:
        seq = _int(getattr(e, "seq", 0))
        sub = str(getattr(e, "subtype", "") or "")
        payload = getattr(e, "payload", None) or {}
        ts = str(getattr(e, "ts", "") or "")
        if sub == N_ADD:
            _apply_add(st, payload, ts, seq)
        elif sub == N_CLOSE:
            _apply_close(st, payload, ts, seq)
        elif sub == N_RETIRE:
            _apply_retire(st, payload, seq)
        elif sub == N_REWRITE:
            _apply_rewrite(st, payload, ts, seq)
        else:
            logger.warning("note 未知操作（跳过）: subtype=%r seq=%s", sub, seq)
        st.up_to_seq = max(st.up_to_seq, seq)
    return st


def _apply_add(st: NotesState, payload: dict, ts: str, seq: int) -> None:
    """加一条（A 类）—— `id`/`since` 由引擎给（模型只写正文 + 引用）。"""
    text = str(payload.get("text") or "").strip()
    refs = _str_list(payload.get("refs"))
    if not text or not refs:
        logger.warning("note/add 残缺（跳过）: seq=%s text=%r refs=%r", seq, text, refs)
        return
    st.promise.append(NoteItem(id=_alloc_id(st), text=text, refs=refs, since=ts,
                               due=str(payload.get("due") or "").strip()))


def _apply_close(st: NotesState, payload: dict, ts: str, seq: int) -> None:
    """**结清**一条 —— ⚠️ **不是从 note 移除**。

    为什么不能立刻删（2026-09-23 用户裁决）: 承诺是**唯一"note 是它唯一落脚点"**的东西
    —— 图里要等固化才有它, 而上下文窗口（120 单元滚动）**从来不是保证**。close 一删,
    它就**三处全无**。所以两段式（与 promise 本身同构）:

        `close` = 结清（本子上还在, 注入块里照旧显示, 尾巴换成理由）
        `retire` = 退场（图侧接住了才划掉 —— 见 `_apply_retire`）

    ⇒ **不变量: 一条承诺任何时刻至少在一个可见面上** —— 开着 / 已结清 ⇒ 在 note;
      已固化 ⇒ 在图。永不在两者之外。

    ⚠️ **已结清的不再覆盖**: 块里印着 `id`, 若允许二次 close 改写 `reason`,
       就等于给"拿幻觉理由覆盖真实理由"开了个后门 ⇒ 第二次只告警（幂等 = 忽略）。
       还开着的那条**照旧覆盖**（当场结清 → digest 补判, 后写的更准）。
    ⚠️ 只作用于 **A 类槽**: B 类由 `rewrite` 整段替换, 让 `close` 也能改它就是两个写者
       抢同一份数据（§3.2"同一段只有一个写者"）。
    ⚠️ **理由缺失照做, 但把账记响**: 事件说的就是"这条不再开着了", 不认它会让本子停在过去;
       而"为什么"缺失只影响**固化进图**那一步（§6）, 那是另一处的账。
    """
    nid = str(payload.get("id") or "").strip()
    if not nid:
        logger.warning("note/close 缺 id（跳过）: seq=%s", seq)
        return
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        logger.warning("note/close 缺理由（照做; 固化那一步将无从判断为什么）: id=%s seq=%s",
                       nid, seq)
    for slot in OPSLOTS:
        for it in list(getattr(st, slot) or []):
            if it.id != nid:
                continue
            if it.closed:
                logger.warning("note/close 重复（忽略, 不覆盖已有理由）: id=%s seq=%s", nid, seq)
                return
            it.closed_at = ts or it.closed_at
            it.reason = reason
            it.state = str(payload.get("state") or "").strip()
            return
    logger.warning("note/close 指不到任何条目（跳过）: id=%s seq=%s", nid, seq)


def _apply_retire(st: NotesState, payload: dict, seq: int) -> None:
    """**退场** —— 真正从 note 划掉（图里已经有了）。

    写者 = **固化那一批**: digest 收口建好 `promise` 节点 + `from`/`to`/`formed_by` 边、
    事务 `ok` 之后, 由引擎补写这条事件（同好感事件那个模式: `digest` 只返回决定,
    事件由引擎在成功之后落 —— 事件流不随 `clone_state` 回滚）。

    ⚠️ **只对已结清的条目生效**: 退场一条"还开着"的承诺 = 把它从唯一的落脚点删掉
       （图里根本没有它）—— 那正是两段式要堵的洞。撞上就告警 + 跳过。
    """
    nid = str(payload.get("id") or "").strip()
    if not nid:
        logger.warning("note/retire 缺 id（跳过）: seq=%s", seq)
        return
    for slot in OPSLOTS:
        items = list(getattr(st, slot) or [])
        hit = [it for it in items if it.id == nid]
        if not hit:
            continue
        if not hit[0].closed:
            logger.warning("note/retire 指向一条还开着的条目（跳过 —— 先 close, 且图里要先接住）:"
                           " id=%s seq=%s", nid, seq)
            return
        setattr(st, slot, [it for it in items if it.id != nid])
        return
    logger.warning("note/retire 指不到任何条目（跳过）: id=%s seq=%s", nid, seq)


def _apply_rewrite(st: NotesState, payload: dict, ts: str, seq: int) -> None:
    """B 类两槽**整段替换**（全景轮）。

    ⚠️ **没提到的槽 = 保留**（同 `revise.apply_decisions` 的空值口径: 没提到 ≠ 要删）;
       想明确清空就送空值（`[]` / `null`）。
    ⚠️ `id`/`since` **按文本精确匹配**继承上一版（`_inherit`）—— 延续的惯例不该因为
       被重写一遍就变成"刚刚记下的"（那恰好把"惯例的厚度"抹平）。
    """
    if SLOT_HABITS in payload:
        raw = payload.get(SLOT_HABITS)
        if raw is None:
            st.habits = []
        else:
            st.habits = _inherit(st, st.habits, _items_of(raw), ts)
    if SLOT_ON_MIND in payload:
        raw = payload.get(SLOT_ON_MIND)
        new = NoteItem.from_dict(raw)
        st.on_mind = None if new is None else _inherit_since(st.on_mind, new, ts)


def _inherit(st: NotesState, old: list[NoteItem],
             new: list[NoteItem], ts: str) -> list[NoteItem]:
    """`rewrite` 的 `id`/`since` 延续 —— **按 `text` 精确匹配**上一版。

    匹配上 → 继承 `id`/`since`; 匹配不上 → 新条目（新号 + `since = 本次重写时刻`）。
    ⇒ 全景轮的 prompt 里必须写明"**延续的条目照抄上一版的原文措辞**": 改了措辞的那条
    会退化成"新条目"（无害 —— 只是 `记于` 重置 + 换一个号, 不会报错也不会丢内容）。
    """
    by_text = {it.text: it for it in old}
    used: set[str] = set()
    out: list[NoteItem] = []
    for it in new:
        prev = by_text.get(it.text)
        if prev is not None and prev.id and prev.id not in used:
            it.id = prev.id
            it.since = prev.since or ts
            it.due = it.due or prev.due
            used.add(prev.id)
        else:
            if prev is not None:
                logger.warning("note/rewrite 出现重复正文（%r）—— 只继承一条的编号", it.text)
            it.id = _alloc_id(st)
            it.since = it.since or ts
        out.append(it)
    return out


def _inherit_since(old: NoteItem | None, new: NoteItem, ts: str) -> NoteItem:
    """`on_mind` 的 `since` 延续 —— 正文没变就保留"第一次这么想"的时刻。

    ⚠️ **不发号**: `on_mind` 是单条散文, 不是索引条目（没人会去 `close` 它）。
    """
    if old is not None and old.text == new.text and old.since:
        new.since = old.since
    else:
        new.since = new.since or ts
    return new


def _alloc_id(st: NotesState) -> str:
    """发一个号（`n1`/`n2`…）—— **只增不复用**（纪律 2）。"""
    nid = f"n{st.next_n}"
    st.next_n += 1
    return nid


# ---------------------------------------------------------------------------
# 写侧: 构造 + 校验（唯一出口）
# ---------------------------------------------------------------------------

def add_op(text: str, refs: Iterable[str], *, due: str = "") -> dict:
    """`add` 操作（**不需要理由** —— 正文自己就是理由）。"""
    op: dict[str, Any] = {"action": N_ADD, "text": text, "refs": list(refs)}
    if str(due or "").strip():
        op["due"] = due                                   # 可选; 空则不落这个键
    return _checked(op)


def close_op(item_id: str, reason: str, state: str) -> dict:
    """`close` 操作 = **结清** —— **理由必填** + **结局必填**（`kept`/`broken`/`superseded`）。

    ⚠️ 结清**不等于**从本子上划掉（那是 `retire_op`）: 条目留在 note 里继续注入,
    直到图侧接住它。理由既是 §6 固化那一步的原料, 也是**注入块上那句话**
    （渲染按 `state` 分三种说法, 见 `CLOSED_WORDS`）。
    """
    return _checked({"action": N_CLOSE, "id": item_id, "reason": reason,
                     "state": state})


def retire_op(item_id: str) -> dict:
    """`retire` 操作 = **退场**（图里已经有了 ⇒ 本子上才划掉）。

    写者 = **固化那一批**（digest 事务 `ok` 之后由引擎补写）; 也允许全景轮
    核对"图里已经有这条承诺"之后顺手退场（那是**核对**, 不是判定）。
    **不加理由** —— 它是机械确认, 不是判断。
    """
    return _checked({"action": N_RETIRE, "id": item_id})


def rewrite_op(*, habits: list | None = None, on_mind: Any = None) -> dict:
    """`rewrite` 操作（B 类两槽整段替换; **不碰 `promise`**）。

    **没传的槽 = 本次不动它**（`None` 是"没提", 不是"清空"）——
    要清空就显式传空值: `habits=[]` / `on_mind=""`。
    """
    op: dict[str, Any] = {"action": N_REWRITE}
    if habits is not None:
        # ⚠️ 只对序列化友好的容器做 list() 归一（dict/str 等**原样留下**, 让写侧门槛拒它）
        op[SLOT_HABITS] = list(habits) if isinstance(habits, (list, tuple)) else habits
    if on_mind is not None:
        op[SLOT_ON_MIND] = on_mind
    return _checked(op)


def note_event(op: dict) -> Any:
    """操作 → **事件**（写侧唯一出口: 构造前必过校验, 残缺的写不进真源）。

    用法::

        store.append_event(char_id, "", notes.note_event(
            notes.add_op("周六模型店", ["m0009"], due="2026-09-26")))
    """
    validate_ops([op])
    payload = {k: v for k, v in op.items() if k != "action"}
    return make_event(TYPE_NOTE, str(op.get("action") or "").strip(), payload)


def validate_ops(ops: list[dict]) -> None:
    """写侧硬门槛（**抛 `ValueError`**）。

    查的是"**事件自身是否自足**"（一 append 就不可改, 残缺的写不进去）:
    动作名 · `add` 的 `text` + `refs` · **`close` 的 `id` + `reason`** · `retire` 的 `id` ·
    `rewrite` 的槽形状。
    **不查** `refs` 是否存在 —— "世上有没有那个节点"要看世界, 归 `check()` 告警。
    """
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise ValueError(err("BadNoteOp", f"note 操作[{i}] 必须是对象"))
        action = str(op.get("action") or "").strip()
        if action == N_ADD:
            if not str(op.get("text") or "").strip():
                raise ValueError(err("BadNoteOp", f"note 操作[{i}] add 缺 text"))
            if not _str_list(op.get("refs")):
                raise ValueError(err("BadNoteOp",
                                     f"note 操作[{i}] add 缺 refs（每条都要能指回一段经历）"))
        elif action == N_CLOSE:
            if not str(op.get("id") or "").strip():
                raise ValueError(err("BadNoteOp", f"note 操作[{i}] close 缺 id"))
            if not str(op.get("reason") or "").strip():
                raise ValueError(err("NoReason",
                                     f"note 操作[{i}] close 缺理由（闭合即固化进图, 没有理由就判不出"
                                     " kept/broken/superseded）"))
            state = str(op.get("state") or "").strip()
            if state not in PROMISE_OUTCOMES:
                raise ValueError(err("BadNoteOp",
                                     f"note 操作[{i}] close 的 state 非法: {state!r}"
                                     f"（可用: {', '.join(PROMISE_OUTCOMES)}）"))
        elif action == N_RETIRE:
            if not str(op.get("id") or "").strip():
                raise ValueError(err("BadNoteOp", f"note 操作[{i}] retire 缺 id"))
        elif action == N_REWRITE:
            for slot in SNAPSHOT_SLOTS:
                if slot not in op or op[slot] is None:
                    continue                          # 没提到的槽 = 本次不动它
                if slot == SLOT_HABITS and not isinstance(op[slot], (list, tuple)):
                    raise ValueError(err("BadNoteOp",
                                         f"note 操作[{i}] rewrite.{slot} 必须是数组"))
        else:
            raise ValueError(err("BadNoteAction", f"note 操作[{i}] 未知动作: {action!r}"))


def _checked(op: dict) -> dict:
    validate_ops([op])
    return op


# ---------------------------------------------------------------------------
# 读侧: 校验（告警, 不阻断）+ 渲染
# ---------------------------------------------------------------------------

def check(state: NotesState, known: Iterable[str] | None = None) -> list[str]:
    """读侧告警清单（**不阻断** —— 调用方打日志/记账, 照 `store.audit()` 的做法）。

    查四件:
    ① 每项至少一个 `refs`（§3.2 不变量①: 每条都要能指回一段经历）
    ② `refs` 指向**现存节点**（悬空 → 记一笔; **不删条目、不改写** —— 那条线索失效不是
       她的错, 而"删掉"是判定）
    ③ 上限 `5 / 5 / 1` —— **只算还开着的**（结清的是"等退场", 不该再占她的注意力预算）,
       且**超限只告警不截断**（丢哪条交全景轮）
    ④ 正文超 `MAX_TEXT` 字（该写名词短语, 不写陈述句）

    ⚠️ **`promise` 的"结清未退场"是正常态**（它就是固化的待办队列）⇒ 不逐条告警;
       只在**积压**时报一句（那才说明收口没跑到）。

    `known=None` → 跳过 ②（调用方没有图的时候, 比如单测折叠本身）。
    """
    known_set = set(known) if known is not None else None
    out: list[str] = []
    for slot in SLOTS:
        items = state.items(slot)
        live = [it for it in items if not it.closed]
        cap = _CAPS[slot]
        if len(live) > cap:
            out.append(f"{slot} 超上限（{len(live)} > {cap}, 只算还开着的）"
                       "—— 不截断, 取舍交全景轮")
        pending = [it for it in items if it.closed]
        if len(pending) > MAX_CLOSED_PENDING:
            out.append(f"{slot} 结清未退场积压（{len(pending)} > {MAX_CLOSED_PENDING}）"
                       "—— 图侧接住之后要补 retire")
        for it in items:
            tag = it.id or slot
            if not it.refs:
                out.append(f"{slot} {tag}: 没有 refs（每条都要能指回一段经历）")
            elif known_set is not None:
                for r in it.refs:
                    if r not in known_set:
                        out.append(f"{slot} {tag}: refs 指向不存在的节点 {r!r}")
            if len(it.text) > MAX_TEXT:
                out.append(f"{slot} {tag}: 正文 {len(it.text)} 字 > {MAX_TEXT}"
                           "（写名词短语, 不写陈述句 —— 免得与 episode 的叙述竞争）")
    return out


def render_note_block(state: NotesState, *, now: object | None = None) -> str:
    """笔记 → **注入块**（常驻层; 空状态 → `""` = 一个字的块都不出现）。

    **形态 = 自然语言小节, 不是数据**（2026-09-23 用户: *"注入的时候记得要剥离 json
    等结构, 更符合自然语言, 且告诉 LLM 这是什么"*）::

        【你自己记的备忘录】（你自己随手记下的, 不是别人给你的任务; 括号里是编号, 指回你记忆里的那件事）
          · 你自己记下的约定
            n3 周六模型店 (m0009)  ← 记于 3 天前
            n1 买花 (m0014)  ← 已结清（送出去了）
          · 你们之间的惯例
            n7 他买东西时总先问我想要哪个 (m0005, m0010)
          · 最近在想
            我不想再只是隔着玻璃看

    - **标题明说这是什么**（她自己的备忘 · 不是任务; 括号里是编号）—— 系统里同时住着
      规则书与 task 卡, 不说清就会被读成"引擎要她做的事"。
    - **小节抬头是自然语言**（约定 / 惯例 / 最近在想）, 且**空槽不印**。
    - **零结构化痕迹**: 无 JSON、无键名（`promise`/`habits`/`on_mind` 一个字都不出现）、
      无波括号 —— 字段名是引擎的词汇, 不是她的。
    - 槽内**按 `since` 降序**（新的在上面）; **开着的排在已结清前面**（这个块第一句要回答
      "我手上还开着什么", 混排会把第一眼读坏）。
    - **`id` 必须印出来**（否则她只能靠文本匹配去 `close` ⇒ 不可靠）。
    - **结清行的尾巴是理由不是时间**, 状态词**中性** —— 不能用"已完成": `close` 也覆盖
      **失约 / 不做了**（图里那个节点的 `state` 就是 kept/broken/superseded 三值）。
    - **频次绝不印**（既有纪律: 数值不直接喂 LLM, 防讨好/数值化）—— 要不要说
      "好多次/每次都"由 writer 决定。
    - **`on_mind` 不印编号也不印 refs**: 它是她自己的口吻, 一行散文（refs 照存,
      给 recall 与审计用）。**`due` 同理不印**（见 `NoteItem`）。

    `now=None` → 不加时间短语（同 `render._time_phrase` 的哨兵纪律: 未接线时保持原形态,
    不给一个假的"很久以前"）。
    """
    lines: list[str] = []
    for slot in (SLOT_PROMISE, SLOT_HABITS):
        items = state.items(slot)
        if not items:
            continue                                  # 空槽不印抬头（常驻预算是硬约束）
        lines.append(f"{_LEAD_INDENT}{GROUP_LEADS[slot]}")
        for it in _sorted_by([it for it in items if not it.closed], "since"):
            lines.append(f"{_ITEM_INDENT}{render_item(it, now=now)}")
        # 结清组按**结清时刻**排（刚做完的在上）—— 按 `since` 排会让"刚做完的老约定"沉底
        for it in _sorted_by([it for it in items if it.closed], "closed_at"):
            lines.append(f"{_ITEM_INDENT}{render_item(it)}")
    if state.on_mind is not None:
        lines.append(f"{_LEAD_INDENT}{GROUP_LEADS[SLOT_ON_MIND]}")
        lines.append(f"{_ITEM_INDENT}{state.on_mind.text}")
    if not lines:
        return ""
    return "\n".join([TITLE] + lines)


def render_item(item: NoteItem, *, now: object | None = None) -> str:
    """**一行条目**（不含缩进与抬头）—— 注入块与**全景轮的输入**共用这一份行格式。

    `n3 周六模型店 (m0009)  ← 记于 3 天前`; 已结清的尾巴换成 `← 已结清（理由）`。
    `id` 为空（`on_mind` 那条散文）→ 只有正文。
    """
    if not item.id:
        return item.text
    tail = _closed_suffix(item) if item.closed else _since_suffix(item, now)
    return f"{item.id} {item.text}{_refs_suffix(item)}{tail}"


def _closed_suffix(it: NoteItem) -> str:
    """`  ← 已兑现（理由）` —— 状态词按 `state` 分三种; 没有 `state` → 中性兜底。"""
    head = f"  ← {CLOSED_WORDS[it.state]}" if it.state in CLOSED_WORDS else CLOSED_LEAD
    return f"{head}（{it.reason}）" if it.reason else head


def _sorted_by(items: list[NoteItem], field: str) -> list[NoteItem]:
    """组内排序: `field`（`since` / `closed_at`）降序 —— 新的在上面;
    无该字段的排在最后（`id` 号大者在前）。"""
    return sorted(items, key=lambda it: (getattr(it, field) or "", _id_num(it.id)),
                  reverse=True)


def _refs_suffix(it: NoteItem) -> str:
    return f" ({', '.join(it.refs)})" if it.refs else ""


def _since_suffix(it: NoteItem, now: object | None) -> str:
    """`  ← 记于 3 天前`（算不出 → **整段不印**, 不编一个"很久以前"）。"""
    if now is None or not it.since:
        return ""
    try:
        from core.worldtime.age import age_days, render_relative
        age = age_days(it.since, now=now)
    except Exception:                              # noqa: BLE001 — 渲染绝不因时间炸
        return ""
    return f"{SINCE_LEAD}{render_relative(age)}" if age is not None else ""


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _items_of(raw: Any) -> list[NoteItem]:
    """宽松读一列条目（**丢坏条目要出声** —— 静默丢就是静默失忆）。"""
    if raw is None:
        return []
    if not isinstance(raw, list):
        logger.warning("note 槽不是数组（当空处理）: %r", type(raw).__name__)
        return []
    out: list[NoteItem] = []
    for r in raw:
        it = NoteItem.from_dict(r)
        if it is None:
            logger.warning("note 条目残缺（丢掉）: %r", r)
            continue
        out.append(it)
    return out


def _str_list(v: Any) -> list[str]:
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)):
        return []
    return [str(x).strip() for x in v if isinstance(x, (str, int)) and str(x).strip()]


def _int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _id_num(nid: str) -> int:
    """`n12` → 12（排序用; 坏值 → 0）。"""
    return _int(str(nid or "")[1:]) if str(nid or "").startswith("n") else 0


def _derive_next_n(items: list[NoteItem]) -> int:
    """旧档/坏档兜底: 从活着的 id 推一个**下界**（防复用; 真实计数器应随状态走）。"""
    return max([_id_num(it.id) for it in items] + [0]) + 1
