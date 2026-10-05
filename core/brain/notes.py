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
> 约定从此住在 note 里; 而"这条经历涉及约定"由 **`tags`** 承担（只做筛选, 不承担路由）。

**四条纪律**（写进形状里, 不靠自觉）:

0. ⭐ **`close` = 划掉即移除**（2026-10-05 改）—— 从前是**两段式**（`close` 结清但留着条目,
   `retire` 才真删）, 那条设计的唯一理由是"承诺以 note 为唯一落脚点 ⇒ 删了就三处全无"。
   ⭐ 3b-3 起**约定长在它自己那条 episode 上**（`refs`）⇒ 那条理由没了, 两段式合并成一步。
   ⇒ **本子 = 当前抽屉, 不是账簿**（账簿 = 事件流 + 图）。结局（兑现 / 失约 / 被取代）
   不再是一个字段, 而是**图里那条经历的正文**（有那一刻 = 那条切片的 episode;
   没有那一刻 = 无区间经历）。⛔ `retire` 动作**删**（`fold` 仍认旧档里的它 —— 同义: 移除）。
1. **`update` 只改两样**: `due`（补/更正日期）· `text`（重写那句话）——
   ⚠️ 不许改 `refs`（出生地址）/ `since` / 槽。它存在的唯一理由: 日期**后来才知道**
   （"不知道 → 她问 → 知道了"）, 而 `due` 只能在建条目的那一刻给。
2. **`id` 只增不复用** —— `close`/`update` 只带 `id`, 复用会让旧引用指错条目。故计数器 `next_n`
   必须随状态走, **不能从"活着的条目"推**。
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
    N_UPDATE,
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
#: ⭐ **"这条经历是她随身带着过的一件事"** 的**节点 tag**（§4.5; L7 2026-10-05）。
#: 打给**出生那条** episode（`state=open` 那一行长出来的那条）, **建节点时**由引擎写,
#: ⛔ 不走 revise 通道、**也不让 R1 写**（提示词里那一句已删 —— 判据在 R0,
#: 两个写者 = 迟早一个标了 `close` 那一条）。
#: ⚠️ 它只是**筛选词**（同 `tags` 的既有定位）, 不承担路由。
PINNED_TAG = "#pinned"
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

#: ⛔ ~~`PINNED_OUTCOMES = ("kept", "broken", "superseded")`~~ **2026-10-05 删** ——
#: 三种结局**一律划掉**之后它再没有读者: 结局写在**图里那条经历**的正文里
#: （有那一刻 = 那条切片的 episode; 没有那一刻 = 无区间经历）。
#: ⚠️ 契约层 `contract/digest_registry.py` 还有一份同名副本 —— 那守的是**收口轮自己的
#: 输出契约**（它还活着）, 随那一轮一起死（见 `TODO_DIGEST_LEDGER` L8）。

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
#: ⛔ ~~`CLOSED_WORDS` / `CLOSED_LEAD`~~ **2026-10-05 删** —— 那是"结清行"的尾巴
#: （`← 已兑现（…）`）。条目**划掉即消失** ⇒ 没有结清行可渲染, 尾巴只剩 `SINCE_LEAD`。


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
    `due`   —— 可选; ⚠️ **只存不渲染**（渲染成日期会诱使她"数日子",
               与 `worldtime.age` 那条"绝不输出精确值"直接冲突）。

    ⛔ ~~`closed_at` / `afterwards` / `state`~~ **2026-10-05 删** —— `close` 改成
    **划掉即移除**（两段式合并, 见模块 docstring 纪律 0）⇒ 条目**再也不可能被结清**,
    那三个字段永远落不到条目上; 结局改由**图里那条经历的正文**承担。
    """

    id: str = ""
    text: str = ""
    refs: list[str] = field(default_factory=list)
    since: str = ""
    due: str = ""

    def copy(self) -> "NoteItem":
        return NoteItem(id=self.id, text=self.text, refs=list(self.refs),
                        since=self.since, due=self.due)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"text": self.text, "refs": list(self.refs),
                             "since": self.since}
        if self.id:
            d["id"] = self.id
        if self.due:
            d["due"] = self.due
        return d

    @classmethod
    def from_dict(cls, raw: Any) -> "NoteItem | None":
        """宽松读（坏值 / **已划掉的** → None）。

        ⚠️ **裸字符串也收**（`{"text": raw}`）—— 那是 `on_mind` 时代的形状
        （N4e 之前 `rewrite` 收裸字符串）; 旧档读得进来但**没有槽接它**了。
        ⚠️ **带 `closed_at` 的旧条目一律不进状态**（2026-10-05）: 那是一条**已经划掉的**
        条目（旧两段式的中间态）, 而新口径下本子上只留开着的 —— 放它进来它就会以
        "还开着"的样子重新出现。从事件流重折会得到同样的结果。
        """
        if isinstance(raw, str):
            raw = {"text": raw}
        if not isinstance(raw, dict):
            return None
        if str(raw.get("closed_at") or "").strip():
            return None
        text = str(raw.get("text") or "").strip()
        if not text:
            return None
        return cls(id=str(raw.get("id") or "").strip(),
                   text=text,
                   refs=_str_list(raw.get("refs")),
                   since=str(raw.get("since") or "").strip(),
                   due=str(raw.get("due") or "").strip())


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
        elif sub == N_UPDATE:
            _apply_update(st, payload, seq)
        elif sub == N_RETIRE:
            # 旧档: 与 `close` **同义**（2026-10-05 两段式合并）—— 走同一个函数
            _apply_close(st, payload, ts, seq)
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
    """**划掉**一条 —— 从 note **移除**（2026-10-05: 两段式合并成一步）。

    旧两段式的理由是"承诺以 note 为唯一落脚点 ⇒ close 一删就三处全无"。
    ⭐ 3b-3 起约定长在**它自己那条 episode** 上（`refs`）⇒ 那条理由没了,
    于是 `close`（结清）与 `retire`（退场）**合并**: 都是"移除"。
    ⛔ 旧档里的 `retire` 事件走同一个函数（`fold` 那侧分派）—— 语义相同, 不必区分。

    三种结局（兑现 / 失约 / 被取代）**一律移除**; 结局与"后来怎么了"由图里那条经历承担。
    op 里若还带着 `afterwards` / `state`（收口轮尚未退役）—— **只入账**（事件流 + evolution
    日志）, 不落到条目上（本子上已经没有"结清行"这种东西了）。
    """
    nid = str(payload.get("id") or "").strip()
    if not nid:
        logger.warning("note/close 缺 id（跳过）: seq=%s", seq)
        return
    for slot in OPSLOTS:
        items = list(getattr(st, slot) or [])
        if not any(it.id == nid for it in items):
            continue
        setattr(st, slot, [it for it in items if it.id != nid])
        logger.info("note/close 划掉一条: id=%s seq=%s", nid, seq)
        return
    logger.warning("note/close 指不到任何条目（跳过）: id=%s seq=%s", nid, seq)


def _apply_update(st: NotesState, payload: dict, seq: int) -> None:
    """**更正**一条还开着的 —— 只改 `due` 与 `text`（"日期后来才知道"的唯一出口）。

    ⚠️ 两样都没给 / 指不到条目 ⇒ 告警 + 跳过（读侧宽松, 同 `_apply_add` 的口径）;
    ⛔ 不许改 `refs`（出生地址）/ `since` / 槽 —— 写侧就构造不出来。
    """
    nid = str(payload.get("id") or "").strip()
    if not nid:
        logger.warning("note/update 缺 id（跳过）: seq=%s", seq)
        return
    due, text = payload.get("due"), payload.get("text")
    new_due = str(due).strip() if due is not None else ""
    new_text = str(text).strip() if text is not None else ""
    if not new_due and not new_text:
        logger.warning("note/update 一样都没改（跳过）: id=%s seq=%s", nid, seq)
        return
    for slot in OPSLOTS:
        for it in list(getattr(st, slot) or []):
            if it.id != nid:
                continue
            if new_due:
                it.due = new_due
            if new_text:
                it.text = new_text
            logger.info("note/update 更正一条: id=%s seq=%s", nid, seq)
            return
    logger.warning("note/update 指不到任何条目（跳过）: id=%s seq=%s", nid, seq)


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


def close_op(item_id: str) -> dict:
    """`close` 操作 = **划掉**（从本子移除）—— 只需要 `id`。

    ⚠️ **`afterwards` / `state` 不再进 op**（2026-10-05）: 三种结局一律移除 ⇒ note 面
    没有读者了; 那句"后来怎么了"与结局改由**图里那条经历**承担。
    ⏸ 从前它们还进 evolution 日志（`revise._close_one` 的审计账）—— 那个函数随收口轮
    一起删了（L8）, 于是这两样字段**今天一个读者都没有**（旧档里的事件读侧照认）。
    ⛔ 曾经的两段式（`close` 结清 / `retire` 退场）已合并 —— 见模块 docstring 纪律 0。
    """
    return _checked({"action": N_CLOSE, "id": item_id})


def update_op(item_id: str, *, due: str | None = None, text: str | None = None,
              before: dict | None = None, after: dict | None = None) -> dict:
    """`update` 操作 = **更正**一条还开着的 —— 只改 `due` 与 `text`, **至少一样**。

    ⭐ 它存在的唯一理由: `due`（期限）**只能在建条目的那一刻给**, 而日期常常是
    **后来才知道**的（"不知道 → 她问 → 知道了"）。没有它, 那条 note 永远拿不到期限
    ⇒ 永远不过期 ⇒ 烂在本子上（`DESIGN_DIGEST_LEDGER §3.5`）。
    ⛔ 不许改 `refs`（出生地址）/ `since` / 槽 —— 构造器根本不给这些口子。

    ⭐ `before` / `after`（L7, 2026-10-05）: **更正前后的那两句话与日期**（`{text, due}`）,
    由调用方从"本子上原来那句"与"这一行的产出"各取一份 —— 与 revise 的 `changed` 同形。
    ⚠️ 它们**只是审计账**（`fold` 不读; 事件流 append-only ⇒ 那一笔留得住）,
    所以缺省可以不传（手工记账 / 测试）。
    """
    op: dict[str, Any] = {"action": N_UPDATE, "id": item_id}
    if due is not None and str(due).strip():
        op["due"] = str(due).strip()
    if text is not None and str(text).strip():
        op["text"] = str(text).strip()
    if before:
        op["before"] = dict(before)
    if after:
        op["after"] = dict(after)
    # ⚠️ "至少要改一样"的判据**只有一处** = `validate_ops`（下面 `_checked` 会走它）——
    # 这里不重复判, 免得同一条规则两个实现、迟早漂。
    return _checked(op)


# ⛔ ~~`retire_op`~~ **2026-10-05 删** —— 它与 `close` 已合并（同一件事: 从本子划掉）。
# 留着它就是留一条"和 close 做同一件事、还多一层语义"的写路。


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
    动作名 · `add` 的 `text` + `refs` · `close` 的 `id` · **`update` 的 `id` + 至少一样**。
    **不查** `refs` 是否存在 —— "世上有没有那个节点"要看世界, 归 `check()` 告警。
    ⚠️ `add` 上的 `ALREADY_PINNED`（`src`）也**不查**（3b-3）: 它是去重键,
    指向的节点存不存在同样归 `check()`。
    ⚠️ **`close` 的 `afterwards` / `state` 不再查**（2026-10-05: 不再进 op）。
    ⚠️ **`retire` / `rewrite` 已不在写侧** —— 前者与 `close` 合并, 后者随 `on_mind` 退役
    （N4e）; 走到这里 = 有人新造了一条往旧形状里写的操作 ⇒ 按**未知动作**拒
    （`fold` 那边仍认旧档里的它们）。
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
            # ⚠️ 2026-10-05: `afterwards` / `state` **不在这里管了** —— 它们不再进 op
            # （三种结局一律移除, 结局由图里那条经历承担）。旧档里那两条事件带着它们,
            # 读侧（`_apply_close`）只当账, 不看也不校验。
        elif action == N_UPDATE:
            if not str(op.get("id") or "").strip():
                raise ValueError(err("BadNoteOp", f"note 操作[{i}] update 缺 id"))
            if not any(str(op.get(k) or "").strip() for k in ("due", "text")):
                raise ValueError(err("BadNoteOp",
                                     f"note 操作[{i}] update 至少要改一样（due 或 text）"
                                     " —— 白跑一行不许（同 revise 的'update 必须带非空 patch'）"))
        else:
            raise ValueError(err("BadNoteAction", f"note 操作[{i}] 未知动作: {action!r}"))


def _checked(op: dict) -> dict:
    validate_ops([op])
    return op


# ---------------------------------------------------------------------------
# 读侧: 校验（告警, 不阻断）+ 渲染
# ---------------------------------------------------------------------------

def stats(state: NotesState, *, block_chars: int | None = None) -> dict[str, int]:
    """⭐ **台账（数字, 不是告警）** —— L9（2026-10-05）。

    形态: `{"open": 开着的条数, "block_chars": 注入块多少字}`。

    ⚠️ **为什么另开一个函数, 不并进 `check()`**: `check()` 的语义是"**哪里不对**"
    （调用方按告警逐条打 WARNING）, 而这两个数**永远都有值** —— 混进去 = 每个正常段
    都多一条 WARNING, 告警就没人看了。数字归数字。

    设计 §9-5 的裁决: **先只记数、不拍上限** —— 开着的条数直接等于"每轮料里逐条现状"
    的成本, 上限要拿真机几段的数说话（`grep note 台账`）。"""
    chars = block_chars if block_chars is not None else len(render_note_block(state))
    return {"open": sum(len(state.items(slot)) for slot in SLOTS), "block_chars": chars}


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
        # ⚠️ 2026-10-05 起**只有还开着的**（`close` = 划掉即移除）⇒ 不再有结清组
        for it in _sorted_by(items, "since"):
            lines.append(f"{_ITEM_INDENT}{render_item(it, now=now, titles=titles)}")
    if not lines:
        return ""
    return "\n".join([TITLE] + lines)


def render_item(item: NoteItem, *, now: object | None = None,
                titles: Mapping[str, str] | None = None) -> str:
    """**一行条目**（不含缩进与抬头）—— 注入块与 **R4 的输入**共用这一份行格式。

    `n3 周六模型店 (《模型店的午后》)  ← 记于 3 天前`。
    ⚠️ `id` 为空 → 只有正文（旧档/手工构造的条目; N4e 之前 `on_mind` 那条散文走这条路）。

    ⭐ **`titles`: refs 的 id → 名字**（N4a, 2026-09-29）—— 由**调用方**从图上取好传进来
    （本模块**纯函数零 IO**，不碰 store）。渲染成 `(《名字》)`，多条用 `·` 连。

    ⚠️ **拿不到映射 ⇒ 整段不印**（`titles=None` / 那条没名字）——
    印一个她读不懂的编号（`m0021`）既违反"编号退回引擎内部"（`PROCEED §2 #10`），
    又白占常驻预算。**宁缺勿错**。
    """
    if not item.id:
        return item.text
    # ⚠️ 尾巴只剩时间一种（2026-10-05: 结清行的 `← 已兑现（…）` 随"划掉即移除"一起删）
    return f"{item.id} {item.text}{_refs_suffix(item, titles)}{_since_suffix(item, now)}"


def _sorted_by(items: list[NoteItem], field: str) -> list[NoteItem]:
    """组内排序: `field`（今天只有 `since`）降序 —— 新的在上面;
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
