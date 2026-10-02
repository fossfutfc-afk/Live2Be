# -*- coding: utf-8 -*-
"""rounds.py — digest 的**轮次表**: 每段的步序 / 身份 / 料 / 产出 / 跳过 / 快照。

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
| 顺序（元组序） | `Cursor`：`digest_segment` 每进一轮先 `enter(key)`, **越序/回头当场炸** |
| `label` | `_round_call(..., label=spec.label)` → `task_labels.digest_label` |
| `prompt` / `phase` | `_system_for(spec)`：`load_prompt(spec.prompt)` + `build_schema(spec.phase)` |
| `parse` | `spec.parse(raw, **ctx)` —— 调用点只给这一轮的上下文 |
| `material` | `_sections_for(spec, …)`：**逐字校对"这一轮吃什么"**（对不上当场炸） |
| `writes` | 人读（"这一步往图上写什么"）+ 守门用例（字段名/边名/笔记槽必须真实存在） |
| `result_fields` | `reset_result()` —— ⭐ **`_rollback` 由此推导**, 不再手抄 |
| `skip` | 跳过时打的那句日志（文案单源）; 判据仍在调用点 |
| `budget` | ⭐ **这一轮自己的时间预算**（秒）—— `_round_call` 折算成 `min(整段硬顶, 现在 + 它)` |
| `own_snapshot` | 人读 + 守门: **只有**自带快照的那一步允许吞掉自己的失败 |

⚠️ **两个时间参数也住在本模块**（`ROUND_BUDGET_SECONDS` 每轮默认 / `SEGMENT_HARD_CAP_SECONDS`
整段硬顶）—— 判据: 每轮各自的预算防"前几轮慢 ⇒ 后面几轮被饿死", 硬顶防"每轮都刚好不超时
叠成半小时"。**硬顶必须 ≥ 各轮预算之和**（守门用例钉住, 否则等于没改）。

⚠️ 改这里就要看 `tests/core/test_digest_rounds.py` —— 它钉住: 结果字段分类齐全 ·
表里的字段名/边名/笔记槽真实存在 · prompt 文件在 · 标签在词表里 · 只有一步自带快照 ·
游标不许回头 · **预算之和 ≤ 硬顶**。
"""
from __future__ import annotations

from dataclasses import MISSING, dataclass, fields
from typing import Any, Callable

from contract.digest_registry import (
    PHASE_ATTRIBUTE,
    PHASE_CLOSE,
    PHASE_GROUP,
    PHASE_RECORD,
    PHASE_UNDERSTAND,
    digest_registry,
)

#: `writes` 的"面" —— 每个字段名归一个面, 守门用例按面去查真源:
#:   节点面 → `nodes.BrainNode` 的字段名 · `edge` → `graph.REL_*` 的取值 ·
#:   `note` → `notes.SLOT_*`（备忘录的槽 —— **不进图**, 只在工作记忆里）
NODE_FACES = ("episode", "experience", "belief", "entity", "group")
EDGE_FACE = "edge"
NOTE_FACE = "note"
FACES = (*NODE_FACES, EDGE_FACE, NOTE_FACE)

#: ⭐ **每轮的时间预算（秒）** —— 一轮（含它自己那次反馈重试）最多花多久。
#: 表里某轮写了 `budget` 就用它; 没写（0）用这个默认。
#: ⚠️ **为什么必须有它**（2026-09-29 刀 1）: 从前全段共享一个 300s 预算, 而
#: `llm_call` 只在**每次尝试前**看表 ⇒ 前几轮一慢, **后面几轮集体被"饿死"**
#: （报错还只说"撞上时间预算", 看不出是哪一轮）。5 次 high 档长考本来就贴着 300s。
#: 标定入口 = 真机日志 `llm chat task=digest.round_b ms=…`（已存在, 按 `task=` 分轮看）。
ROUND_BUDGET_SECONDS = 120.0

#: ⭐ **整段硬顶（秒）** —— 一轮轮下来总共不许超过它。
#: 判据: 每轮各自的预算防"互相饿死", 硬顶防"每轮都刚好不超时"叠成半小时
#: （2026-09-02 真发生过一次: 重试放大把 digest 拖到近半小时）。
#: ⚠️ **硬顶必须 ≥ 各轮预算之和** —— 否则后面的轮又会被前面的吃掉, 等于没改;
#: `tests/core/test_digest_rounds.py` 钉住这条。
SEGMENT_HARD_CAP_SECONDS = 600.0


@dataclass(frozen=True)
class RoundSpec:
    """一步（一次 LLM 调用, 或一次零成本补边）的完整声明。"""

    key: str
    """表内主键 —— 也是日志里的 `digest_<key>`（`akin` 是唯一不调 LLM 的一步）。"""

    step: str
    """人读的步号, 与 `core/digest/__init__.py` 的步序表同一份写法。"""

    label: str
    """LLM 调用身份（短名）—— `task_labels.digest_label` 拼成 `digest.<label>`。
    空串 = 这一步不调 LLM。"""

    prompt: str
    """`llm/prompts/<prompt>.md`。空串 = 不调 LLM。"""

    phase: str
    """契约相位（`build_schema` 与 parse 的键）。空串 = 不调 LLM。"""

    parse: Callable[..., Any] | None
    """`(raw, **ctx) -> (parsed, ValidationResult)` —— 结构校验的入口。"""

    material: tuple[str, ...]
    """这一轮吃哪几段料: **标题 + 顺序**。`_sections_for` 逐字校对（对不上当场炸）——
    "这一轮吃什么"的地图就这一行, 不可能与实际不符。"""

    writes: tuple[tuple[str, tuple[str, ...]], ...]
    """往哪写、写什么（**具体字段名**）: `((面, (字段, …)), …)`。"""

    result_fields: tuple[str, ...]
    """写进 `DigestResult` 的哪些字段 —— ⭐ `_rollback` 的清空清单由它推导。"""

    skip: str
    """跳过条件（跳过时打的那句日志; 判据在 `pipeline` 的调用点）。空串 = 从不跳过。"""

    budget: float = 0.0
    """⭐ 这一轮的时间预算（秒）。**0 = 用 `ROUND_BUDGET_SECONDS`**。

    ⚠️ 它的作用域 = **本轮自己**（含同轮那次反馈重试）, 由 `_round_call` 在开跑时
    折算成"`min(整段硬顶, 现在 + 本轮预算)`" —— 单轮慢**不连累后面的轮**。
    今天五轮都用默认; 要分轮调（R1 最贵、R4 最便宜）就在这一格写数。
    ⚠️ 它是**每次尝试前**的检查（`llm_call` 的既有语义）, 不掐断正在飞的那一次调用。
    """

    own_snapshot: bool = False
    """True = 这一步失败**只回滚它自己**（加法性的: 料留着, 下一段再来 —— 自愈）。"""


#: ⭐⭐ **每段的全部步序**（顺序就是这张表的顺序, 不是 `pipeline` 里语句的先后）。
ROUNDS: tuple[RoundSpec, ...] = (
    RoundSpec(
        key="round_a",
        step="① R1 记",
        label="round_a",
        prompt="digest_v2_round_a",
        phase=PHASE_RECORD,
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
            # ⭐ N4a: 她此刻那句心境 —— 与 R4 的约定共用 `notes_ops` 这条交付通道
            ("note", ("on_mind",)),
        ),
        result_fields=("notes_ops",),
        skip="",
    ),
    RoundSpec(
        key="akin",
        step="akin 补边（0 LLM）",
        label="",
        prompt="",
        phase="",
        parse=None,
        material=(),
        writes=(("edge", ("akin",)),),
        result_fields=(),
        skip="本段没有想起账（`noticed` 事件）",
    ),
    RoundSpec(
        key="close",
        step="② R4 记账",
        label="close",
        prompt="digest_v2_round_close",
        phase=PHASE_CLOSE,
        parse=digest_registry.parse_close,
        material=("还开着的约定", "本段新增的经历"),
        writes=(("note", ("promise",)),),
        result_fields=("notes_ops", "notes_warnings"),
        skip="没有开着的约定, 本段也没有新经历（那一轮必然空转）",
    ),
    RoundSpec(
        key="round_b",
        step="③ R2 接",
        label="round_b",
        prompt="digest_v2_round_b",
        phase=PHASE_UNDERSTAND,
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
        result_fields=(),
        skip="",
    ),
    RoundSpec(
        key="attr",
        step="④ R3 挂",
        label="attr",
        prompt="digest_v2_round_attr",
        phase=PHASE_ATTRIBUTE,
        parse=digest_registry.parse_attribution,
        material=("候选对象", "这几个对象的当前情况", "本轮新节点", "角色人设（锚点）"),
        writes=(
            ("entity", ("name", "aliases", "text", "state", "event_seq", "ts")),
            # 归属的**唯一落地形式**: 有边 = 归好了, 没边 = 没归（`about_state` 三态）。
            ("edge", ("about",)),
        ),
        result_fields=("created_entities",),
        skip="本段没有新节点可归属",
    ),
    RoundSpec(
        key="group",
        step="⑤ L2-a 分群",
        label="group",
        prompt="digest_v2_round_group",
        phase=PHASE_GROUP,
        parse=digest_registry.parse_group,
        material=("还没归类的块", "已有的类", "可能重复的类"),
        writes=(
            # `aliases` 是**并群**那条路的产物（输家的名字写进赢家, 名字是地址）。
            ("group", ("title", "aliases", "ts")),
            ("edge", ("member_of",)),
        ),
        result_fields=("created_groups", "grouped_episodes",
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
    return spec.budget if spec.budget > 0 else ROUND_BUDGET_SECONDS


def planned_seconds() -> float:
    """表里各轮预算之和（守门用: 它必须 ≤ `SEGMENT_HARD_CAP_SECONDS`）。"""
    return sum(budget_of(s) for s in ROUNDS if s.label)


#: ⭐ **失败时要清空的 `DigestResult` 字段** —— 由表推导（不再手抄）。
RESULT_FIELDS: tuple[str, ...] = tuple(dict.fromkeys(
    name for spec in ROUNDS for name in spec.result_fields))

#: `DigestResult` 上**不归任何一轮**的字段。它们不是"轮次的产出", 所以回滚不碰:
#:   · `ok` / `errors` / `llm_calls` —— **调用路径**的记录（失败报告本身, 抹掉就看不见了）
#:   · `created` / `affection_delta` —— **提交时**才赋值（成功路径; 任何一轮都不写）
COMMIT_ONLY: tuple[str, ...] = ("ok", "errors", "llm_calls", "created", "affection_delta")


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
                "顺序的真源是 core/digest/rounds.py 的 ROUNDS")
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
