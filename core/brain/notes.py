# -*- coding: utf-8 -*-
"""notes.py — 随身笔记（note）: **操作事件 → 折叠状态 → 注入块**（DESIGN_GRAPH_V4 §3.2 / §6）。

note 是**三种组织形式**里的第二种（图 / **笔记** / 台账, §1.1）:
**图管"可查的细节", note 管"此刻"**。它不是记忆（不改写历史）、不是人设（不装设定）、
也不是图的镜像 —— 只装**她自己挑过的**。

    真源   `soul/events.jsonl`   append-only 的**操作**（`add` / `close` / `retire`）
    缓存   `soul/notes.json`     `fold()` 的结果 + `up_to_seq` 水位（可随时重建）

⇒ **并发安全**（主 LLM 与 digest 同时写不丢更新）· **可回放** · **与水位同频**。

**一槽**（§3.2 的"按引擎要不要处理二分"）:

| 槽 | 类 | 装什么 | 更新模型 | 写者 |
|---|---|---|---|---|
| `pinned` | **A 操作式** | ⭐ **她随身带着的事**（誓约 / 重大的约定; 2026-09-29 由 `promise` 改名并收紧判据） | `add` / **`close` 结清** / **`retire` 退场** | 加 · 结清 = digest 收口（R4）· 退场 = **今天零写者**（见下） |

> ⛔ **第二槽 `on_mind` 已退役（2026-09-29, N4e）** —— 用户裁决: *"它太煽情了,
> 煽情的剧情过去了, 就不必一直耿耿于怀了"*。判据不是"零读者"而是**时间尺度**:
> note 是**长期随身**的东西, 而"她此刻的心境"是**当下**的东西 —— 一旦写下来,
> 引擎就会在每一轮把它重新念给她听（常驻注入）,**情绪因此被冻在过去**。
> 归档判据 = 煽情性, 不是信息量。
>
> **退役 = 全链删, 不留形态**: 槽 · 上限 · `NotesState.on_mind` · `_apply_rewrite` ·
> `_inherit_since` · `rewrite_op` · 注入块的「最近在想」小节 · 契约的 `on_mind` 字段与
> 释义 · R1 的 `on_mind_box`。**旧档/旧事件里的那个键直接忽略**（同下面 `habits` 的口径:
> 不迁移、不报错 —— 真机那条也**不留档**, 留档就是给它立碑）。
> ⚠️ 将来若真需要"她此刻在想什么", 该走的是 **belief（有图、有边、能被召回、
> 会随新经历更新）**, 不是在 note 里再养一个形状特殊的槽。
>
> ⚠️ **第三槽 `habits` 已退役（2026-09-29, N4a）** —— 它是"规律"的**劣质替身**
> （`DESIGN_NOTE §4`：≤20 字标签 + `refs` 无走法 + 与 belief 重复 ⇒ 三条存在理由
> 一个都不满足）。内容归 **L2 的 belief（模式句）**、指针归将来的 `index`。
> **旧档里那个键读的时候直接忽略**（退役 = 不再读，不迁移）。别把它加回来。
>
> ⚠️ **`promise` 节点 2026-09-29 退图**（用户裁决: 承诺太轻, 不足以长期记录）——
> ⭐ **这一槽从此是约定的唯一落脚点**（从前还计划"固化进图"）。
> 连带: `retire` 的写者从前写的是"固化那一批", 那条路没了 ⇒ 退场时机改成
> **读路径能接住约定之后**（那条链路本来就欠着）; **今天仍然零写者, 行为零变化**。
> "这条经历涉及约定"改由 **`tags`** 承担（只做筛选, 不承担路由）。

**四条纪律**（写进形状里, 不靠自觉）:

0. ⭐ **`close` 是"结清", 不是"划掉"；划掉是 `retire`** —— 承诺太轻, 不值得在图里长期
   记录（2026-09-29 用户裁决 ⇒ promise 退图）, 所以 **note 是它唯一的落脚点**,
   而上下文窗口（120 单元滚动）从来不是保证 ⇒ 结清**不删条目**:
   **结清 ⇒ 条目留在块里（尾巴换成 `afterwards` 那句）→ 读路径能接住它了 ⇒ `retire` 才真删**。
   ⇒ **不变量: 一条约定只要还在 note 里, 她就看得见**。
1. **`close` 必须给 `afterwards`（"这件事后来怎么了"）, `add` / `retire` 不用** —— 它既是
   她读到的那句话, 也是"这件事后来怎么了"的唯一书面留存。读侧遇到没给它的
   close **照做但记响**（不认它反而会让本子停在过去）, 写侧直接拒。
   ⚠️ **已结清的不再覆盖**: 块里印着 id, 若二次 close 能改写 `afterwards`, 就是给"拿幻觉的一句话
   覆盖真实的那句话"开后门 ⇒ 第二次只告警（幂等 = 忽略）。
2. **`id` 只增不复用** —— `close`/`retire` 只带 `id`, 复用会让旧引用指错条目。故计数器 `next_n`
   必须随状态走, **不能从"活着的条目"推**（结清 n3 之后活着的是 n1/n2）。
3. **物品一个字都不进 note** —— "她此刻手边有什么"将来由 **`inventory` 旁路**（物品面:
   有身份、有增删）承担; 这条记忆里的实物痕迹写在 `text` 里就够。
   ⚠️ 原写的 `episode.items` 字段 **2026-09-29 已退役**（零活读者, 且"是不是同一个东西"
   写在 episode 里分不清）。**没有 `gifts` 槽**。

本模块**纯函数、零 IO**（不碰文件 / 不碰 store / 不调 LLM）: 落盘归 `store.py`, 注入归引擎。
这样折叠能直接单测, 也保证"缓存可重建"这句话是真的。
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Iterable

from core.brain import marks
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

#: 槽（顺序 = 渲染顺序 = 清单顺序）
#: ⚠️ **2026-09-29 改名 `promise` → `pinned`**（用户裁决: *"promise 混了两件事,
#: 而且誓约只是其中最重的一类"*）。判据同时收紧成 **"说定的将来 + 值得随身带着"**
#: （见 `llm/prompts/digest_record.md`）—— 名字与判据一起说"挡在门外的是什么":
#: **日常安排 / 事务待办不是"钉住的事"**。
#: ⚠️ **磁盘影响**: 事件流的 `add`/`close`/`retire` payload **不带槽名**（槽由 action
#: 隐含）⇒ **真源零影响**; 只有**派生缓存** `notes.json` 里有那个键 ⇒ `from_dict`
#: 兼容读一次旧名（见 `_LEGACY_SLOT`）。
SLOT_PINNED = "pinned"
#: 派生缓存里的**旧**槽名（改名前的 `promise`）—— 只读一次, 下次保存自动改写。
_LEGACY_SLOT = "promise"
#: ⚠️ ~~`SLOT_HABITS = "habits"`~~ **2026-09-29（N4a）已退役**：它是"规律"的劣质替身
#: （`DESIGN_NOTE §4` 三条存在理由都不满足）；内容归 L2 的 belief、指针归将来的 `index`。
#: 别把常量留着"以防万一" —— 退役就是退役，留着它就还有一条静默的写路。
#: ⛔ ~~`SLOT_ON_MIND = "on_mind"`~~ **2026-09-29（N4e）已退役** —— 判据见模块 docstring
#: （*"太煽情了"*: note 装的是**长期随身**的东西, 心境是**当下**的东西）。
#: **没有 `SNAPSHOT_SLOTS` 了** —— 它随这个槽一起消失（一个槽谈不上二分）。
SLOTS: tuple[str, ...] = (SLOT_PINNED,)
#: **A 操作式**槽（增量 add/close）。
#: ⚠️ 从前的二分（A 操作式 / B 快照式）是"同一段只有一个写者"的实现 ——
#: `on_mind` 退役后**只剩 A 类**, 那个二分连同 `rewrite` 动作一起没有读者了。
OPSLOTS: tuple[str, ...] = (SLOT_PINNED,)

#: ⭐ **备忘录的总量上限（字）**（2026-09-29 用户裁决）。
#: ## 为什么是"总量"而不是"每槽条数"
#: 从前的两条判据（`MAX_PROMISE=5` 条数上限 · `MAX_CLOSED_PENDING=3` 结清积压）**生产里
#: 零读者**（只有测试调 `check`）⇒ 真机永远不会响, 而真机会发生的事是**"结清不退场 +
#: 约定越记越多 ⇒ 注入块越来越长"**。而她每轮都在为这个块花 token ⇒ 该管的是**它多长**。
#: ⚠️ **数值未标定**: 先给一个数, 真机看 `note 体检` 那行里报的实际字数再调。
MAX_NOTE_CHARS = 500
#: ⛔ ~~`MAX_TEXT = 20`（条目正文上限）~~ **2026-10-05 删** —— 它是**只报不修**的体检判据,
#: 而 3b-3 起 note 正文 = 切片的 `abstract`（契约上限 `ABSTRACT_MAX = 60`）⇒ 它**必然恒响**,
#: 变成背景噪音（真问题也就跟着看不见了）。真机上它**已经误报过一次**
#: （`EXEC_DIGEST_SPLIT §12`: 那句 21 字的心境）。
#: ⚠️ **长度只有一个真源 = 契约层**（`ABSTRACT_MAX`）—— 别在体检里再管一次。
#: ⛔ ~~`MAX_ON_MIND_TEXT = 60`~~ **2026-09-29（N4e）随 `on_mind` 退役** ——
#: 它是"按槽分标尺"里的那一支（心境可以有口气、有破折号 ⇒ 与 A 槽不同限）。
#: ⭐ **`add` 操作上的去重键**（3b-3, 2026-09-29）—— "这条笔记指向哪条经历"。
#: `fold` 见到"本子上已经有一条 `refs` 含同一个值"就**跳过这条 add**:
#: digest 重跑（水位没推进 / 崩溃窗口）时, 节点面已经由 `_find_duplicate` 复用,
#: 而笔记面靠它。⚠️ **名字是字面量 `"src"`**（不是槽名）—— 它是 op 的元数据,
#: 不是条目字段; `NoteItem.from_dict` 不认它（它只在写侧与 `fold` 之间用）。
ALREADY_PINNED = "src"

#: ⭐ **约定的结局**（`close` 行的 `state`）—— **运行时真源**（改名 `PROMISE_OUTCOMES` →
#: `PINNED_OUTCOMES`, 2026-09-29 随槽名一起对齐）。
#: ⚠️ 节点上没有 `outcome` 字段（promise 退图）⇒ 这 3 个词只活在 note 面
#: （`contract/digest_registry.py` 有一份同源副本, 契约层不依赖 core）。
PINNED_OUTCOMES = ("kept", "broken", "superseded")

#: 注入块标题 —— ⚠️ 必须**说清这是什么**（是她自己记的, 不是系统/别人派的任务; 编号是索引）,
#: 且**不含任何结构化痕迹**（无 JSON / 无键名 / 无波括号 —— **存 JSON, 看中文**, §3.2）。
#: ⭐ 2026-09-29（N4a）: 括号里那截**从"编号"改成"名字"** —— 编号退回引擎内部
#: （`PROCEED §2 #10`），她读不懂 `m0021` 是哪件事; 照抄得到的**名字**才是她能用的地址。
TITLE = ("【你自己记的备忘录】（你自己随手记下的, 不是别人给你的任务; "
         "每条前面的编号指这一条本身, 括号里是它从哪件事来的）")
#: 槽 → 小节抬头（**自然语言**, 用设计稿自己的词: 约定）。
#: ⚠️ **空槽不印抬头**（否则每个空槽都白占一行常驻预算）。
#: ⚠️ ~~`SLOT_ON_MIND: "· 最近在想"`~~ **2026-09-29（N4e）随槽退役** ——
#: 那个小节是"她此刻的心境"的唯一显示面, 槽没了它就没了。
GROUP_LEADS: dict[str, str] = {SLOT_PINNED: "· 你自己记下的约定"}
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


# ---------------------------------------------------------------------------
# 形状
# ---------------------------------------------------------------------------

@dataclass
class NoteItem:
    """一条笔记（形状: `{id, text, refs, since(, due)}` + 结清两字段）。

    `id`    —— 引擎在**折叠**时分配（`n1`/`n2`…, 只增不复用）。
    `text`  —— **名词短语, 不写陈述句**（"周六模型店" ≠ "我们约好周六去模型店"）。
               ⚠️ 长度**不在这里管**（2026-10-05: 体检那条"≤20 字"已删 —— 它必然恒响）;
               真源 = 契约层 `ABSTRACT_MAX`（本条正文多来自切片 `abstract`）。
    `refs`  —— ≥1, 指向**现存节点**（悬空 → `check()` 告警, 不阻断）。
    `since` —— 记于何时（引擎填 = 那条操作的 `ts`; 渲染成"记于 N 天前"）。
    `due`   —— `pinned` 可选; ⚠️ **只存不渲染**（渲染成日期会诱使她"数日子",
               与 `worldtime.age` 那条"绝不输出精确值"直接冲突）。
    `closed_at` / `afterwards` / `state` —— **结清**（`closed_at` 非空 = 已结清）:
               她做完了 / 没成 / 被新的取代了（`state` = `kept`/`broken`/`superseded`）,
               以及 **`afterwards`** = "这件事后来怎么了"那句话（她自己的口吻;
               ⚠️ 早先叫 `reason` —— 用户 2026-09-25: *"reason 太理性了"*）。
               ⚠️ 字段名在这里是 **`state`**（节点侧叫 `outcome` —— entity 的 `state` 是 list, 撞类型;
               而 note 条目没有那个字段, 所以沿用它。两处同义不同名）。
    """

    id: str = ""
    text: str = ""
    refs: list[str] = field(default_factory=list)
    since: str = ""
    due: str = ""
    closed_at: str = ""
    afterwards: str = ""
    state: str = ""

    @property
    def closed(self) -> bool:
        """已结清（**还在 note 里**, 等图侧接住才退场）。"""
        return bool(self.closed_at)

    def copy(self) -> "NoteItem":
        return NoteItem(id=self.id, text=self.text, refs=list(self.refs),
                        since=self.since, due=self.due,
                        closed_at=self.closed_at, afterwards=self.afterwards,
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
        if self.afterwards:
            d["afterwards"] = self.afterwards
        if self.state:
            d["state"] = self.state
        return d

    @classmethod
    def from_dict(cls, raw: Any) -> "NoteItem | None":
        """宽松读（坏值 → None）。

        ⚠️ **裸字符串也收**（`{"text": raw}`）—— 那是 `on_mind` 时代的形状
        （N4e 之前 `rewrite` 收裸字符串）; 旧档读得进来但**没有槽接它**了。
        """
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
                   afterwards=str(raw.get("afterwards") or "").strip(),
                   state=str(raw.get("state") or "").strip())


@dataclass
class NotesState:
    """折叠结果 = `soul/notes.json` 的内容（**派生缓存**, 可随时从事件流重建）。

    `up_to_seq` —— 已折进的**最大事件 seq**（增量折叠的水位）。
    `next_n`    —— 下一个 `id` 号（纪律 2: 只增不复用 ⇒ 不能从活着的条目推）。
    """

    up_to_seq: int = 0
    next_n: int = 1
    pinned: list[NoteItem] = field(default_factory=list)
    # ⚠️ ~~`habits` 槽~~ **2026-09-29（N4a）已退役**：它是"规律"的劣质替身
    #    （`DESIGN_NOTE §4`：≤20 字标签 + refs 无走法 + 与 belief 重复 ⇒ 三条存在理由
    #    一个都不满足）。内容归 **L2 的 belief（模式句）**、指针归将来的 `index`。
    #    **旧档里那个键在读的时候直接忽略**（退役 = 不再读，不做迁移）。
    # ⛔ ~~`on_mind` 槽~~ **2026-09-29（N4e）已退役** —— 判据见模块 docstring
    #    （*"太煽情了"*）。**旧档/旧事件里那两个键同样直接忽略**（不迁移、不报错）。

    def __post_init__(self) -> None:
        """护栏: **发号器至少比现有 id 大**（纪律 2"只增不复用"的兜底）。

        正常路径（`fold`）不会踩到; 手工构造的状态 / 旧档推错的 `next_n` 会 —— 那会发出
        **重号**, 而 `close`/`retire` 只按号找人 ⇒ 旧引用指错条目（静默）。
        """
        self.next_n = max(self.next_n, _derive_next_n(self.pinned))

    def items(self, slot: str) -> list[NoteItem]:
        """槽 → 条目列表（今天只有 `pinned`; 一个槽也要走这一层, 口径统一）。"""
        return list(getattr(self, slot, []) or [])

    def clone(self) -> "NotesState":
        return NotesState(up_to_seq=self.up_to_seq, next_n=self.next_n,
                          pinned=[it.copy() for it in self.pinned])

    def to_dict(self) -> dict:
        return {"up_to_seq": self.up_to_seq, "next_n": self.next_n,
                SLOT_PINNED: [it.to_dict() for it in self.pinned]}

    @classmethod
    def from_dict(cls, raw: Any) -> "NotesState":
        """宽松读（坏文件 → 空状态 = 现折一遍就回来了, 不会丢真源）。

        ⚠️ 旧档里的 `habits` / `on_mind` 两个键**直接忽略**（N4a / N4e 退役；
        不迁移、不报错）。真机那份 `notes.json` 里那条 `on_mind` 也**不留档** ——
        用户的判据是"煽情的不必一直耿耿于怀", 留档就是给它立碑。
        """
        if not isinstance(raw, dict):
            return cls()
        # ⚠️ 兼容读旧槽名（改名 `promise` → `pinned`, 2026-09-29）—— 派生缓存里那
        # 个键是旧名; 不认它的话 `up_to_seq` 还在 ⇒ `fold` 不会重放 ⇒ **条目会没**。
        # 下次 `save_notes` 自动改写成新名。
        raw_pinned = (raw[SLOT_PINNED] if SLOT_PINNED in raw
                      else raw.get(_LEGACY_SLOT))
        pinned = _items_of(raw_pinned)
        next_n = _int(raw.get("next_n"))
        if next_n < 1:                     # 旧档/坏档: 从活着的 id 推一个下界（防复用）
            next_n = _derive_next_n(pinned)
        return cls(up_to_seq=max(0, _int(raw.get("up_to_seq"))),
                   next_n=next_n, pinned=pinned)


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
            # ⛔ `rewrite`（N4e 退役）: 它写的那个快照槽 `on_mind` 已经没有了 ⇒
            # 这里**什么都不做**（同 `habits` 的口径: 退役 = 不再读, 不报错不迁移）。
            # ⚠️ 但**动作名留着** —— 旧档（真机 seq 263 那条）里躺着它,
            # 落到 else 分支会打一条永远无法修掉的"未知操作"告警。
            pass
        else:
            logger.warning("note 未知操作（跳过）: subtype=%r seq=%s", sub, seq)
        st.up_to_seq = max(st.up_to_seq, seq)
    return st


def _apply_add(st: NotesState, payload: dict, ts: str, seq: int) -> None:
    """加一条（A 类）—— `id`/`since` 由引擎给（模型只写正文 + 引用）。

    ⭐ **重跑幂等的第二道**（3b-3）: `payload[ALREADY_PINNED]`（= 这条笔记由哪条经历
    长出来的）已经在某条活着的条目里 ⇒ **跳过**（同一条经历不重复钉）。
    ⚠️ 拿它比、**不拿正文比**: 她两次可能把同一句话写得不一样, 而来源是确定的。
    """
    text = str(payload.get("text") or "").strip()
    refs = _str_list(payload.get("refs"))
    if not text or not refs:
        logger.warning("note/add 残缺（跳过）: seq=%s text=%r refs=%r", seq, text, refs)
        return
    src = str(payload.get(ALREADY_PINNED) or "").strip()
    if src and any(src in it.refs for it in st.pinned):
        logger.info("note/add 跳过（同一条经历已经钉过）: src=%s seq=%s", src, seq)
        return
    st.pinned.append(NoteItem(id=_alloc_id(st), text=text, refs=refs, since=ts,
                               due=str(payload.get("due") or "").strip()))


def _apply_close(st: NotesState, payload: dict, ts: str, seq: int) -> None:
    """**结清**一条 —— ⚠️ **不是从 note 移除**。

    为什么不能立刻删（2026-09-23 用户裁决）: 承诺是**唯一"note 是它唯一落脚点"**的东西
    —— 而上下文窗口（120 单元滚动）**从来不是保证**。close 一删, 它就**三处全无**。
    所以两段式:

        `close` = 结清（本子上还在, 注入块里照旧显示, 尾巴换成 `afterwards` 那句话）
        `retire` = 退场（划掉）

    ⚠️ **2026-09-29 更正**: 两段式的第二段原写作"图侧接住了才划掉", 而**图侧那条路
    （固化 promise 节点）已经删掉**（承诺退图）⇒ 今天 `retire` 的时机改成
    "**读路径能接住约定之后**"（链路 ⑥ 欠着的那件事）, **写者仍然零**。
    ⇒ 不变量换成一句更简单的话: **一条约定只要还在 note 里, 她就看得见**;
      结清只改尾巴, 不改可见性。

    ⚠️ **已结清的不再覆盖**: 块里印着 `id`, 若允许二次 close 改写 `afterwards`,
       就等于给"拿幻觉的一句话覆盖真实的那句话"开了个后门 ⇒ 第二次只告警（幂等 = 忽略）。
       还开着的那条**照旧覆盖**（当场结清 → digest 补判, 后写的更准）。
    ⚠️ 只作用于 **A 类槽**: B 类由 `rewrite` 整段替换, 让 `close` 也能改它就是两个写者
       抢同一份数据（§3.2"同一段只有一个写者"）。
    ⚠️ **`afterwards` 缺失照做, 但把账记响**: 事件说的就是"这条不再开着了", 不认它会让本子停在过去;
       而那句话缺失只影响**她读到的那句尾巴**（注入块上那句"后来怎么了"）。
    """
    nid = str(payload.get("id") or "").strip()
    if not nid:
        logger.warning("note/close 缺 id（跳过）: seq=%s", seq)
        return
    afterwards = str(payload.get("afterwards") or "").strip()
    if not afterwards:
        logger.warning("note/close 缺 afterwards（照做; 注入块上那句尾巴会缺）:"
                       " id=%s seq=%s", nid, seq)
    for slot in OPSLOTS:
        for it in list(getattr(st, slot) or []):
            if it.id != nid:
                continue
            if it.closed:
                logger.warning("note/close 重复（忽略, 不覆盖已有的那句话）: id=%s seq=%s",
                               nid, seq)
                return
            it.closed_at = ts or it.closed_at
            it.afterwards = afterwards
            it.state = str(payload.get("state") or "").strip()
            return
    logger.warning("note/close 指不到任何条目（跳过）: id=%s seq=%s", nid, seq)


def _apply_retire(st: NotesState, payload: dict, seq: int) -> None:
    """**退场** —— 真正从 note 划掉。

    ⏸ **写者: 今天零**。从前的计划是"固化那一批"（R4 建好 promise 节点 + 三条边、
    事务 `ok` 之后由引擎补写这条事件）—— **2026-09-29 承诺退图, 那条路没了**;
    退场的时机改成"**读路径能接住约定之后**"（链路 ⑥）, 在那之前她需要它一直在本子上。
    ⚠️ 定义与读侧（`fold` 认它）都留着 —— 等那条链路接通, 它才有写者（同 `notes.retire_op`）。

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


# ⛔ ~~`_apply_rewrite` / `_inherit_since`~~ **2026-09-29（N4e）随 `on_mind` 一起删** ——
# 它们是那个快照槽的唯一实现（整段替换 + `since` 按正文延续）。`fold` 现在把
# `rewrite` 事件当**空操作**吞掉（旧档兼容, 见那里的注释）。


def _alloc_id(st: NotesState) -> str:
    """发一个号（`n1`/`n2`…）—— **只增不复用**（纪律 2）。"""
    nid = f"n{st.next_n}"
    st.next_n += 1
    return nid


# ---------------------------------------------------------------------------
# 写侧: 构造 + 校验（唯一出口）
# ---------------------------------------------------------------------------

def add_op(text: str, refs: Iterable[str], *, due: str = "", src: str = "") -> dict:
    """`add` 操作（**不需要理由** —— 正文自己就是理由）。

    `src`（⭐ 3b-3, 2026-09-29）: **这条笔记由哪条经历长出来的**（= 它唯一那条 ref）。
    它是**去重键**: `fold` 见到"本子上已经有一条指向同一条经历的"就跳过 ——
    重跑幂等的第二道（第一道是 `_find_duplicate` 复用节点, 那一道在节点面）。
    ⚠️ 去重**拿它、不拿正文**: 她两次可能把同一句话写得不一样, 而"指向哪条经历"是确定的。
    """
    op: dict[str, Any] = {"action": N_ADD, "text": text, "refs": list(refs)}
    if str(due or "").strip():
        op["due"] = due                                   # 可选; 空则不落这个键
    if str(src or "").strip():
        op[ALREADY_PINNED] = src
    return _checked(op)


def close_op(item_id: str, afterwards: str, state: str) -> dict:
    """`close` 操作 = **结清** —— **`afterwards` 必填**（"这件事后来怎么了", 她自己的口吻）
    + **结局必填**（`kept`/`broken`/`superseded`）。

    ⚠️ 结清**不等于**从本子上划掉（那是 `retire_op`）: 条目留在 note 里继续注入,
    直到**读路径能接住它**。`afterwards` 今天只有一个去处: 注入块上那句话
    （见 `CLOSED_WORDS`）—— ⏸ 从前还会"固化时并进 promise 节点的正文",
    那条路 2026-09-29 随承诺退图删掉了。
    """
    return _checked({"action": N_CLOSE, "id": item_id, "afterwards": afterwards,
                     "state": state})


def retire_op(item_id: str) -> dict:
    """`retire` 操作 = **退场**（本子上划掉 —— 读路径能接住它了才划）。

    ⏸ **写者: 今天零**（2026-09-29 起）。从前的计划是"固化那一批"（digest 事务 `ok`
    之后由引擎补写）, 而**固化那条路随承诺退图删掉了** ⇒ 时机改成"**读路径接住之后**"。
    定义与读侧都留着（`_apply_retire` / `fold` 认它）, 等那条链路接通才有写者。
    **不加理由** —— 它是机械确认, 不是判断。
    """
    return _checked({"action": N_RETIRE, "id": item_id})


# ⛔ ~~`rewrite_op`~~ **2026-09-29（N4e）随 `on_mind` 一起删** —— 它写的那个槽没了,
# 留着它就还有一条"往一个不存在的槽里写"的静默写路（同 `habits` 退役的判据）。
# ⚠️ **`rewrite` 这个动作名留在 `core/session/events.py`**（`N_REWRITE` / `NOTE_SUBTYPES`
# 都还在）—— 旧档里躺着那条事件, 名字没了 `fold` 就会把它当未知操作告警。


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
    动作名 · `add` 的 `text` + `refs` · **`close` 的 `id` + `afterwards` + `state`** ·
    `retire` 的 `id`。
    **不查** `refs` 是否存在 —— "世上有没有那个节点"要看世界, 归 `check()` 告警。
    ⚠️ `add` 上的 `ALREADY_PINNED`（`src`）也**不查**（3b-3）: 它是去重键,
    指向的节点存不存在同样归 `check()`。
    ⚠️ **`rewrite` 已不在写侧**（N4e 随 `on_mind` 退役）—— 走到这里 = 有人新造了一条
    往一个不存在的槽里写的操作 ⇒ 按**未知动作**拒（`fold` 那边仍吞旧档里的它）。
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
            if not str(op.get("afterwards") or "").strip():
                raise ValueError(err("NoAfterwards",
                                     f"note 操作[{i}] close 缺 afterwards（「这件事后来怎么了」）"
                                     " —— 它是她读到的那句尾巴"))
            state = str(op.get("state") or "").strip()
            if state not in PINNED_OUTCOMES:
                raise ValueError(err("BadNoteOp",
                                     f"note 操作[{i}] close 的 state 非法: {state!r}"
                                     f"（可用: {', '.join(PINNED_OUTCOMES)}）"))
        elif action == N_RETIRE:
            if not str(op.get("id") or "").strip():
                raise ValueError(err("BadNoteOp", f"note 操作[{i}] retire 缺 id"))
        else:
            raise ValueError(err("BadNoteAction", f"note 操作[{i}] 未知动作: {action!r}"))


def _checked(op: dict) -> dict:
    validate_ops([op])
    return op


# ---------------------------------------------------------------------------
# 读侧: 校验（告警, 不阻断）+ 渲染
# ---------------------------------------------------------------------------

def check(state: NotesState, known: Iterable[str] | None = None,
          *, block_chars: int | None = None) -> list[str]:
    """读侧告警清单（**不阻断** —— 调用方打日志/记账, 照 `store.audit()` 的做法）。

    查三件:
    ① 每项至少一个 `refs`（§3.2 不变量①: 每条都要能指回一段经历）
    ② `refs` 指向**现存节点**（悬空 → 记一笔; **不删条目、不改写** —— 那条线索失效不是
       她的错, 而"删掉"是判定）
    ③ ⭐ **备忘录的总量** > `MAX_NOTE_CHARS` 字（2026-09-29 改）—— 见下面那条历史
    ⛔ ~~④ 正文超 `MAX_TEXT` 字~~ **2026-10-05 删** —— 3b-3 起 note 正文 = 切片的
       `abstract`（契约上限 60）⇒ 它**必然恒响**, 只会制造噪音; 长度真源 = 契约层。
    ⚠️ ~~按槽分标尺~~ **2026-09-29（N4e）取消** —— 槽收成一个之后没有第二条标尺。

    ## ⚠️ ③ 的来历（改判据的理由）

    从前的两条是 **每槽条数上限**（`MAX_PROMISE=5`）与 **结清未退场积压**
    （`MAX_CLOSED_PENDING=3`）。2026-09-29 核出**它们在**生产**里零读者** —— 只有测试调
    `check`, 引擎从来没接过它们 ⇒ 真机永远不响。而真机会发生的事是另一件:
    **结清不退场（用户裁决）+ 约定越记越多 ⇒ 注入块越来越长**, 而她每轮都在为它花 token。
    ⇒ 判据换成**总量**（她真正付出的那个成本）。

    ⚠️ **`pinned` 的"结清未退场"现在是常态**（用户裁决: 不退场 —— 退场了就没人接住
       `afterwards`）⇒ 它**不再单独告警**, 由总量那一条统一管。
    ⚠️ `retire` 今天**零写者**（读路径没接上, §3.2）⇒ 总量涨到上限就是"该退役/该淘汰了"
       的信号 —— 而淘汰规则**还没定**, 所以这条告警今天只报不修（预期内的观察值）。

    `known=None` → 跳过 ②（调用方没有图的时候, 比如单测折叠本身）。
    `block_chars=None` → 自己算（`render_note_block` 的长度; 调用方已经渲过就传进来省一次）。
    """
    known_set = set(known) if known is not None else None
    out: list[str] = []
    chars = block_chars if block_chars is not None else len(render_note_block(state))
    if chars > MAX_NOTE_CHARS:
        out.append(f"备忘录太长（{chars} > {MAX_NOTE_CHARS} 字; 每轮都在花 token）"
                   "—— 该退役的退役 / 该淘汰的淘汰（⚠️ 淘汰规则未定, 见 `MAX_NOTE_CHARS`）")
    for slot in SLOTS:
        items = state.items(slot)
        for it in items:
            tag = it.id or slot
            if not it.refs:
                out.append(f"{slot} {tag}: 没有 refs（每条都要能指回一段经历）")
            elif known_set is not None:
                for r in it.refs:
                    if r not in known_set:
                        out.append(f"{slot} {tag}: refs 指向不存在的节点 {r!r}")
    return out


def render_note_block(state: NotesState, *, now: object | None = None,
                      titles: Mapping[str, str] | None = None) -> str:
    """笔记 → **注入块**（常驻层; 空状态 → `""` = 一个字的块都不出现）。

    **形态 = 自然语言小节, 不是数据**（2026-09-23 用户: *"注入的时候记得要剥离 json
    等结构, 更符合自然语言, 且告诉 LLM 这是什么"*）::

        【你自己记的备忘录】（你自己随手记下的, 不是别人给你的任务; 括号里是编号, 指回你记忆里的那件事）
          · 你自己记下的约定
            n3 周六模型店 (m0009)  ← 记于 3 天前
            n1 买花 (m0014)  ← 已结清（送出去了）

    - **标题明说这是什么**（她自己的备忘 · 不是任务; 括号里是编号）—— 系统里同时住着
      规则书与 task 卡, 不说清就会被读成"引擎要她做的事"。
    - **小节抬头是自然语言**（约定）, 且**空槽不印**。
    - **零结构化痕迹**: 无 JSON、无键名（`pinned` 一个字都不出现）、
      无波括号 —— 字段名是引擎的词汇, 不是她的。
    - 槽内**按 `since` 降序**（新的在上面）; **开着的排在已结清前面**（这个块第一句要回答
      "我手上还开着什么", 混排会把第一眼读坏）。
    - **`id` 必须印出来**（否则她只能靠文本匹配去 `close` ⇒ 不可靠）。
    - **结清行的尾巴是理由不是时间**, 状态词**中性** —— 不能用"已完成": `close` 也覆盖
      **失约 / 不做了**（`state` = kept/broken/superseded 三值）。
    - **频次绝不印**（既有纪律: 数值不直接喂 LLM, 防讨好/数值化）—— 要不要说
      "好多次/每次都"由 writer 决定。
    - **`due` 不印**（见 `NoteItem`）。
    - ⛔ ~~「最近在想」小节~~ **2026-09-29（N4e）随 `on_mind` 退役** —— 那个小节印的
      是她此刻的心境（一行散文、无编号）; 用户裁决 *"太煽情了, 煽情的剧情过去了,
      就不必一直耿耿于怀了"*。常驻块**从此只装约定**。

    `now=None` → 不加时间短语（同 `marks.relative` 的哨兵纪律: 未接线时保持原形态,
    不给一个假的"很久以前"）。
    """
    lines: list[str] = []
    for slot in (SLOT_PINNED,):
        items = state.items(slot)
        if not items:
            continue                                  # 空槽不印抬头（常驻预算是硬约束）
        lines.append(f"{_LEAD_INDENT}{GROUP_LEADS[slot]}")
        for it in _sorted_by([it for it in items if not it.closed], "since"):
            lines.append(f"{_ITEM_INDENT}{render_item(it, now=now, titles=titles)}")
        # 结清组按**结清时刻**排（刚做完的在上）—— 按 `since` 排会让"刚做完的老约定"沉底
        for it in _sorted_by([it for it in items if it.closed], "closed_at"):
            lines.append(f"{_ITEM_INDENT}{render_item(it, titles=titles)}")
    if not lines:
        return ""
    return "\n".join([TITLE] + lines)


def render_item(item: NoteItem, *, now: object | None = None,
                titles: Mapping[str, str] | None = None) -> str:
    """**一行条目**（不含缩进与抬头）—— 注入块与 **R4 的输入**共用这一份行格式。

    `n3 周六模型店 (《模型店的午后》)  ← 记于 3 天前`; 已结清的尾巴换成 `← 已结清（理由）`。
    ⚠️ `id` 为空 → 只有正文（旧档/手工构造的条目; N4e 之前 `on_mind` 那条散文走这条路）。

    ⭐ **`titles`: refs 的 id → 名字**（N4a, 2026-09-29）—— 由**调用方**从图上取好传进来
    （本模块**纯函数零 IO**，不碰 store）。渲染成 `(《名字》)`，多条用 `·` 连。

    ⚠️ **拿不到映射 ⇒ 整段不印**（`titles=None` / 那条没名字）——
    印一个她读不懂的编号（`m0021`）既违反"编号退回引擎内部"（`PROCEED §2 #10`），
    又白占常驻预算。**宁缺勿错**。
    """
    if not item.id:
        return item.text
    tail = _closed_suffix(item) if item.closed else _since_suffix(item, now)
    return f"{item.id} {item.text}{_refs_suffix(item, titles)}{tail}"


def _closed_suffix(it: NoteItem) -> str:
    """`  ← 已兑现（后来那句话）` —— 状态词按 `state` 分三种; 没有 `state` → 中性兜底。"""
    head = f"  ← {CLOSED_WORDS[it.state]}" if it.state in CLOSED_WORDS else CLOSED_LEAD
    return f"{head}（{it.afterwards}）" if it.afterwards else head


def _sorted_by(items: list[NoteItem], field: str) -> list[NoteItem]:
    """组内排序: `field`（`since` / `closed_at`）降序 —— 新的在上面;
    无该字段的排在最后（`id` 号大者在前）。"""
    return sorted(items, key=lambda it: (getattr(it, field) or "", _id_num(it.id)),
                  reverse=True)


def _refs_suffix(it: NoteItem, titles: Mapping[str, str] | None = None) -> str:
    """` (《那件事的名字》)` —— **印名字不印编号**（N4a）。

    ⚠️ 用**半角**括号: 全角 `（）` 在她的视图里是**正文的一部分**（旁白/补注），
    而这一截是**引擎的附注**。没有能印的名字 ⇒ 整段不出现（不是印一个空括号）。
    """
    if not it.refs or not titles:
        return ""
    names = [marks.name(titles[r]) for r in it.refs if titles.get(r)]
    names = [n for n in names if n]
    if not names:
        return ""
    return f" ({'·'.join(names)})"


def _since_suffix(it: NoteItem, now: object | None) -> str:
    """`  ← 记于 3 天前`（算不出 → **整段不印**, 不编一个"很久以前"）。

    ⚠️ 相对短语走 `marks.relative`（**唯一实现**）: 她视图里那句 `4 天前` 与这里
    `记于 3 天前` 从此是同一个算法（此前两处各算一遍, 只是恰好长得一样）。
    """
    span = marks.relative(it.since, now)
    return f"{SINCE_LEAD}{span}" if span else ""


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
