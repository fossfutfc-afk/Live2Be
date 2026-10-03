# -*- coding: utf-8 -*-
"""rounds/__init__.py — digest 的**轮次表**: 每段的步序 / 身份 / 料 / 产出 / 跳过 / 快照。

⚠️ **本模块是一个包的门面**（2026-09-29 拆包乙-1）: 从前它是 `core/digest/rounds.py`,
现在 `rounds/` 是包 —— **import 路径一个都没变**（`from core.digest.rounds import ROUNDS`）::

    rounds/__init__.py  ← 本文件: **只有表**（+ Cursor / 预算 / 回滚清单）
    rounds/base.py      Ctx（段级上下文）+ RoundOut（一轮跑完的交代）
    rounds/record.py    ① R1 记        rounds/akin.py       补边（0 LLM）
    rounds/close.py     ② R4 收口      rounds/understand.py ③ R2 接
    rounds/attribute.py ④ R3 挂        rounds/group.py      ⑤ L2-a 分群

⚠️ 表住在 `__init__` 里, 每轮的**正文**在各自文件里 —— 所以本文件**不 import 任何**
`rounds/<轮>.py`（那会让"读一张表"变成"拉起整条管线"）。key → 实现的那张映射在
`core/digest/pipeline.py` 的 `IMPL`, 守门用例钉住它与 `ROUNDS` 一一对应。

## 为什么有它

一句话: 从前"digest 跑哪几步、每步吃什么写什么"**没有一处说全** —— 要同时读六个地方
（契约 `PHASE_*` + 五个 prompt 文件 + `pipeline.digest_segment` 的语句先后 +
`revise.py`/`groups.py` 执行器 + `task_labels.py` + 测试）。三处具体的病:

1. **没有轮次表** —— 顺序只由 `digest_segment` 里的**语句先后 + 注释**表达,
   改一次调用位置就是一次无声的契约改动。
2. **`_rollback` 是手抄清单** —— 每轮往 `DigestResult` 写的新字段必须**手工**加进
   清空列表; 漏一个就是雷。⚠️ 这不是假想: `notes_warnings` **一直**没被清
   （R4 的世界校验记账在整批回滚后还留在结果对象里, 而它描述的正是那些已经作废的操作），
   这就是"手抄"这件事的证词。
3. **料跨 3~4 个文件** —— 想知道"R2 吃什么", 得把编排、`entities.py`、`render.py`
   和 prompt 一起读。

## 它是什么 / 不是什么

这是**声明**: 跑哪几步、每步是谁（LLM 身份）、吃哪几段料、往哪写、什么时候跳过。
**执行体仍在各家**（prompt 在 `llm/prompts/`、契约在 `contract/digest_registry.py`、
落库在 `revise.py` / `groups.py`）—— 表只说"是什么", 不说"怎么写"。

| 列 | 谁在读它 |
|---|---|
| 顺序（元组序） | ⭐ **编排的循环本体**：`for spec in ROUNDS: IMPL[spec.key](ctx)`; 每轮进门先 `ctx.enter(key)`（`Cursor`, **越序/回头当场炸**） |
| ⭐ `key` | **四个标识的唯一来源**: `name`（日志第一段）· `label`（LLM 身份后缀）· `prompt`（prompt 文件）· `phase`（契约相位）—— 后三个是 `RoundSpec` 上的 property, 表里**不再有这三格** |
| `llm` | 这一步调不调 LLM（False ⇒ 上面三个派生值是空串; 今天只有 `akin`） |
| `parse` | `spec.parse(raw, **ctx)` —— 调用点只给这一轮的上下文 |
| `material` | `_sections_for(spec, …)`：**逐字校对"这一轮吃什么"**（对不上当场炸） |
| `writes` | 人读（"这一步往图上写什么"）+ 守门用例（字段名/边名/笔记槽必须真实存在） |
| `result_fields` | `reset_result()` —— ⭐ **`_rollback` 由此推导**, 不再手抄 |
| `skip` | 跳过时打的那句日志（文案单源）; **判据写在那一步的 `run()` 里** |
| `budget` | ⭐ **这一轮自己的时间预算**（秒）—— `_round_call` 折算成 `min(整段硬顶, 现在 + 它)` |
| `own_snapshot` | ⭐ **编排真按它执行**: 为这一步取快照, 失败时只回滚它 + 把 errors 挪进 `RoundOut.warnings_field`（从前只是"人读的说明"） |

⚠️ **两个时间参数也住在本模块**（`DIGEST_ROUND_BUDGET_SECONDS` 每轮默认 /
`DIGEST_SEGMENT_HARD_CAP` 整段硬顶）—— 判据: 每轮各自的预算防"前几轮慢 ⇒ 后面几轮被饿死",
硬顶防"每轮都刚好不超时叠成半小时"。**硬顶必须 ≥ 各轮预算之和**（守门用例钉住, 否则等于没改）。

⚠️ 改这里就要看 `tests/core/test_digest_rounds.py` —— 它钉住: 结果字段分类齐全 ·
表里的字段名/边名/笔记槽真实存在 · prompt 文件在 · 标签在词表里 · 只有一步自带快照 ·
游标不许回头 · **预算之和 ≤ 硬顶** · ⭐ **`IMPL` 与表一一对应**（每一步都真有实现）·
⭐ **相位是契约真认识的**（`key` 必须能 `build_schema`）。
另有一条 `tests/core/test_digest_naming_guard.py` 钉住**命名**（前缀派生 + 日志第一段 = 轮名）。
"""
from __future__ import annotations

from dataclasses import MISSING, dataclass, fields
from typing import Any, Callable

from contract.digest_registry import digest_registry

#: `writes` 的"面" —— 每个字段名归一个面, 守门用例按面去查真源:
#:   节点面 → `nodes.BrainNode` 的字段名 · `edge` → `graph.REL_*` 的取值 ·
#:   `note` → `notes.SLOT_*`（备忘录的槽 —— **不进图**, 只在工作记忆里）
NODE_FACES = ("episode", "experience", "belief", "entity", "group")
EDGE_FACE = "edge"
NOTE_FACE = "note"
FACES = (*NODE_FACES, EDGE_FACE, NOTE_FACE)

#: ⭐ **轮次标识的公共前缀** —— 三种派生标识（日志第一段 / prompt 文件 / 任务标签）
#: 都从它拼出来。⚠️ 源码里**不许手写**这个前缀 + 轮名（守门用例扫 `core/digest/**`）。
DIGEST_LOG_PREFIX = "digest_"

#: ⭐ **任何一轮的契约层都可能说话**（`ValidationResult.warnings` / `.drops`）——
#: 所以**每个 LLM 轮**都声明这两个字段（`RESULT_FIELDS` 会去重, 回滚一起清）。
#: ⚠️ 它们必须**可回滚**: 一个没提交的段, 它的 warning 描述的是**没发生的事**。
CONTRACT_FIELDS: tuple[str, ...] = ("contract_warnings", "contract_drops")

#: ⭐ **每轮的时间预算（秒）** —— 一轮（含它自己那次反馈重试）最多花多久。
#: 表里某轮写了 `budget` 就用它; 没写（0）用这个默认。
#: ⚠️ **为什么必须有它**（2026-09-29 刀 1）: 从前全段共享一个 300s 预算, 而
#: `llm_call` 只在**每次尝试前**看表 ⇒ 前几轮一慢, **后面几轮集体被"饿死"**
#: （报错还只说"撞上时间预算", 看不出是哪一轮）。5 次 high 档长考本来就贴着 300s。
#: 标定入口 = 真机日志 `llm chat task=digest.understand ms=…`（已存在, 按 `task=` 分轮看）。
DIGEST_ROUND_BUDGET_SECONDS = 120.0

#: ⭐ **整段硬顶（秒）** —— 一轮轮下来总共不许超过它。
#: 判据: 每轮各自的预算防"互相饿死", 硬顶防"每轮都刚好不超时"叠成半小时
#: （2026-09-02 真发生过一次: 重试放大把 digest 拖到近半小时）。
#: ⚠️ **硬顶必须 ≥ 各轮预算之和** —— 否则后面的轮又会被前面的吃掉, 等于没改;
#: `tests/core/test_digest_rounds.py` 钉住这条。
DIGEST_SEGMENT_HARD_CAP = 600.0


@dataclass(frozen=True)
class RoundSpec:
    """一步（一次 LLM 调用, 或一次零成本补边）的完整声明。

    ⭐ **`key` 是四个标识的唯一来源**（2026-09-29 乙-2 起 —— 从前 `label` / `prompt` /
    `phase` 各写一份字面量, 改一次 key 要同时改四处, 漏一处就是静默不一致）::

        key  = "record"     →  name   = "digest_record"      （日志第一段）
                            →  label  = "record"              （`digest.record` 那个后缀）
                            →  prompt = "digest_record"       （`llm/prompts/digest_record.md`）
                            →  phase  = "record"              （`PHASE_RECORD` 的取值）

    判据: key 取的**就是契约相位名**（`contract/digest_registry.PHASE_*` 的取值）, 而
    LLM 调用身份的后缀与日志前缀本来就该跟它同名 —— 于是"三个派生"其实是**零个新名字**。
    """

    key: str
    """表内主键 —— 契约相位名（`record` / `akin` / `close` / `understand` /
    `attribute` / `group`）。见类 docstring: 另外四个标识都从它来。"""

    step: str
    """人读的步号（与 `core/digest/__init__.py` 的步序表同一份写法）。
    ⏸ 旧文档与旧注释里的 `R1`/`R2`/`R3`/`R4` 按这里对: **R1=记 · R4=收口 · R2=接 · R3=挂**。"""

    parse: Callable[..., Any] | None
    """`(raw, **ctx) -> (parsed, ValidationResult)` —— 结构校验的入口（住在契约层,
    `contract/digest_registry.py`; ⚠️ 它的函数名仍叫 `parse_round_a` / `parse_round_b`
    —— 契约层是独立面, 改名要动 60 多处引用, 留作单独一刀）。"""

    material: tuple[str, ...]
    """这一轮吃哪几段料: **标题 + 顺序**。`_sections_for` 逐字校对（对不上当场炸）——
    "这一轮吃什么"的地图就这一行, 不可能与实际不符。"""

    writes: tuple[tuple[str, tuple[str, ...]], ...]
    """往哪写、写什么（**具体字段名**）: `((面, (字段, …)), …)`。"""

    result_fields: tuple[str, ...]
    """写进 `DigestResult` 的哪些字段 —— ⭐ `_rollback` 的清空清单由它推导。"""

    skip: str
    """跳过条件（跳过时打的那句日志; 判据写在那一步的 `run()` 里）。空串 = 从不跳过。"""

    budget: float = 0.0
    """⭐ 这一轮的时间预算（秒）。**0 = 用 `ROUND_BUDGET_SECONDS`**。

    ⚠️ 它的作用域 = **本轮自己**（含同轮那次反馈重试）, 由 `_round_call` 在开跑时
    折算成"`min(整段硬顶, 现在 + 本轮预算)`" —— 单轮慢**不连累后面的轮**。
    今天五轮都用默认; 要分轮调（记最贵、收口最便宜）就在这一格写数。
    ⚠️ 它是**每次尝试前**的检查（`llm_call` 的既有语义）, 不掐断正在飞的那一次调用。
    """

    own_snapshot: bool = False
    """True = 这一步失败**只回滚它自己**（加法性的: 料留着, 下一段再来 —— 自愈）。"""

    llm: bool = True
    """这一步调不调 LLM。**False = 零成本的一步**（今天只有 `akin`）——
    `label` / `prompt` / `phase` 三个派生值在它上面都是空串。
    ⚠️ 与 `parse is None` **必须一致**（守门用例钉住）, 否则"LLM 四件套同生共死"就破了。"""

    # ── 三个派生标识（⭐ 不手写; 见类 docstring）──

    @property
    def name(self) -> str:
        """日志第一段 —— 恒 `digest_<key>`（**零 LLM 的 `akin` 也一样**, 它也有日志）。

        ⚠️ 轮文件里的日志**字面量必须等于它**（守门用例扫源码钉住）—— 这一处**没有**
        改成 `spec.name` 拼进每条日志: 那要把前缀穿进 `_link_akin` / `_collapse_bond_episodes`
        的签名, 为一个日志字段付的接口噪声比收益大; 而"字面量与 key 对不上"照样会被守门抓住。
        """
        return f"{DIGEST_LOG_PREFIX}{self.key}"

    @property
    def label(self) -> str:
        """LLM 调用身份（短名）—— `task_labels.digest_label` 拼成 `digest.<label>`。
        空串 = 这一步不调 LLM。"""
        return self.key if self.llm else ""

    @property
    def prompt(self) -> str:
        """`llm/prompts/<prompt>.md`。空串 = 不调 LLM。"""
        return f"{DIGEST_LOG_PREFIX}{self.key}" if self.llm else ""

    @property
    def phase(self) -> str:
        """契约相位（`build_schema` 与 parse 的键）。空串 = 不调 LLM。"""
        return self.key if self.llm else ""


#: ⭐⭐ **每段的全部步序**（顺序就是这张表的顺序, 不是 `pipeline` 里语句的先后）。
ROUNDS: tuple[RoundSpec, ...] = (
    RoundSpec(
        key="record",
        step="① 记",
        parse=digest_registry.parse_round_a,
        material=("本段新增互动", "本章标题", "画面记忆",
                  "角色人设（锚点）", "本段情绪标尺"),
        writes=(
            # 条目自带的位置是 `span` 区间, 由 `_expand_spans` 展开成 `event_seq`。
            ("episode", ("title", "text", "verbatim", "verbatim_seq", "tags",
                         "significance", "emo_int", "emo_span", "observer",
                         "event_seq", "ts",
                         # 引擎物化（🚫 只进召回侧, 绝不进 LLM 上下文）:
                         "emo_shape", "place", "place_raw", "aff_at_encoding")),
            ("experience", ("text", "subject", "verbatim", "verbatim_seq", "tags",
                            "significance", "event_seq", "ts")),
            # ⭐ N4a: 她此刻那句心境 —— 与收口的约定共用 `notes_ops` 这条交付通道
            ("note", ("on_mind",)),
        ),
        result_fields=(*CONTRACT_FIELDS, "notes_ops", "record_gaps"),
        skip="",
    ),
    RoundSpec(
        key="akin",
        step="补边（0 LLM）",
        parse=None,
        material=(),
        writes=(("edge", ("akin",)),),
        result_fields=(),
        skip="本段没有想起账（`noticed` 事件）",
        llm=False,
    ),
    RoundSpec(
        key="close",
        step="② 收口",
        parse=digest_registry.parse_close,
        material=("还开着的约定", "本段新增的经历"),
        writes=(("note", ("promise",)),),
        result_fields=(*CONTRACT_FIELDS, "notes_ops", "notes_warnings"),
        skip="没有开着的约定, 本段也没有新经历（那一轮必然空转）",
    ),
    RoundSpec(
        key="understand",
        step="③ 接",
        parse=digest_registry.parse_round_b,
        material=("本次新经历（含引擎候选标注）", "本段时间线",
                  "现有认知", "角色人设（锚点）"),
        writes=(
            ("belief", ("text", "subject", "tags", "significance", "growth",
                        "event_seq", "ts")),
            # `supports` 两种形状都在这条路上: `episode → 认知`（每条决策行都补）
            # 与 `认知 → 认知`（`links` 那几行）; 另两条边只由 `links` 写。
            ("edge", ("supports", "contradicts", "evolved_from")),
        ),
        result_fields=(*CONTRACT_FIELDS,),
        skip="",
    ),
    RoundSpec(
        key="attribute",
        step="④ 挂",
        parse=digest_registry.parse_attribution,
        material=("候选对象", "这几个对象的当前情况", "本轮新节点", "角色人设（锚点）"),
        writes=(
            ("entity", ("name", "aliases", "text", "state", "event_seq", "ts")),
            # 归属的**唯一落地形式**: 有边 = 归好了, 没边 = 没归（`about_state` 三态）。
            ("edge", ("about",)),
        ),
        result_fields=(*CONTRACT_FIELDS, "created_entities"),
        skip="本段没有新节点可归属",
    ),
    RoundSpec(
        key="group",
        step="⑤ 分群（L2-a）",
        parse=digest_registry.parse_group,
        material=("还没归类的块", "已有的类", "可能重复的类"),
        writes=(
            # `aliases` 是**并群**那条路的产物（输家的名字写进赢家, 名字是地址）。
            ("group", ("title", "aliases", "ts")),
            ("edge", ("member_of",)),
        ),
        result_fields=(*CONTRACT_FIELDS, "created_groups", "grouped_episodes",
                       "merged_groups", "group_warnings"),
        skip="没有未归群的块, 也没有可能重复的类",
        # ⭐ 它是**加法**的（块留到下段再来 ⇒ 自愈）: 失败只回滚这一步,
        # R1–R4 的活照常提交（把"命名没成"升级成"整段记忆全丢"是拿真东西换装饰）。
        own_snapshot=True,
    ),
)

#: 表内主键 → spec / 下标（游标与调用点用）
BY_KEY: dict[str, RoundSpec] = {s.key: s for s in ROUNDS}
ROUND_INDEX: dict[str, int] = {s.key: i for i, s in enumerate(ROUNDS)}


def budget_of(spec: RoundSpec) -> float:
    """这一轮实际用多少秒（表里没写 ⇒ 默认）—— 唯一取法, 别在调用点各写一份。"""
    return spec.budget if spec.budget > 0 else DIGEST_ROUND_BUDGET_SECONDS


def planned_seconds() -> float:
    """表里各轮预算之和（守门用: 它必须 ≤ `DIGEST_SEGMENT_HARD_CAP`）。"""
    return sum(budget_of(s) for s in ROUNDS if s.llm)


#: ⭐ **失败时要清空的 `DigestResult` 字段** —— 由表推导（不再手抄）。
RESULT_FIELDS: tuple[str, ...] = tuple(dict.fromkeys(
    name for spec in ROUNDS for name in spec.result_fields))

#: `DigestResult` 上**不归任何一轮**的字段。它们不是"轮次的产出", 所以回滚不碰:
#:   · `ok` / `errors` / `llm_calls` —— **调用路径**的记录（失败报告本身, 抹掉就看不见了）
#:   · `created` / `affection_delta` —— **提交时**才赋值（成功路径; 任何一轮都不写）
#:   · `creep_rows` —— ⭐ **失败也要留下的事实**（`kind=digest_skip` 的账）:
#:     账不是剧情, **不随事务回滚** —— 恰恰相反, 它记的就是"这批没成"
COMMIT_ONLY: tuple[str, ...] = ("ok", "errors", "llm_calls", "created",
                                "affection_delta", "creep_rows")


class Cursor:
    """按 `ROUNDS` 的顺序走一遍 —— **跳过的步留空, 但不许回头、不许越序**。

    `digest_segment` 每进一轮先 `enter(key)`: 从此"表说的顺序"就是"实际顺序",
    不再是两句可能对不上的东西（改错顺序 = 当场炸, 不是等到线上才发现）。
    """

    def __init__(self) -> None:
        self._at = 0

    @property
    def at(self) -> int:
        """已经走到的位置（下一个允许进入的下标）。"""
        return self._at

    def enter(self, key: str) -> RoundSpec:
        spec = BY_KEY[key]
        i = ROUND_INDEX[key]
        if i < self._at:
            raise AssertionError(
                f"digest 轮次越序: {key!r} 是第 {i + 1} 步, 而已经走到第 {self._at} 步 —— "
                "顺序的真源是 core/digest/rounds/__init__.py 的 ROUNDS")
        self._at = i + 1
        return spec


def reset_result(result: Any) -> list[str]:
    """把表里声明过的 `DigestResult` 字段恢复成**初值** —— `_rollback` 的唯一实现。

    ⚠️ 从前这是 `_rollback` 里手抄的一份清单（见模块 docstring 第 2 条）。
    现在清单由 `ROUNDS` 的 `result_fields` 推导: 某轮新写一个结果字段而**表里没写**,
    `tests/core/test_digest_rounds.py` 直接红。
    """
    by_name = {f.name: f for f in fields(type(result))}
    for name in RESULT_FIELDS:
        f = by_name[name]                # 表里写了而 dataclass 上没有 → KeyError（响亮）
        setattr(result, name,
                f.default_factory() if f.default_factory is not MISSING else f.default)
    return list(RESULT_FIELDS)
