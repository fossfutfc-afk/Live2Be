"""rounds/__init__.py — digest 的**轮次表**: 每段的步序 / 身份 / 料 / 产出 / 跳过 / 快照。

⚠️ **本模块是一个包的门面**（2026-09-29 拆包乙-1）: 从前它是 `core/digest/rounds.py`,
现在 `rounds/` 是包 —— **import 路径一个都没变**（`from core.digest.rounds import ROUNDS`）::

    rounds/__init__.py  ← 本文件: **只有表**（+ Cursor / 预算 / 回滚清单）
    rounds/base.py      Ctx（段级上下文）+ RoundOut（一轮跑完的交代）
    rounds/record.py    ① R1 记        rounds/akin.py       补边（0 LLM）
    rounds/relate.py     ③ L1 接       rounds/settle.py     ④ R3 沉淀
    ⏸ ⑤ L2-a 分群（`rounds/group.py` + `core/brain/groups.py`）**2026-10-13 退役**
      —— 整族搬 `archive/digest_group/`（理由与去向见那份 README）。
    ⏸ ② R4 收口（`rounds/close.py`）**2026-10-05（L8）删** —— 账目归 R0 的表。

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
   （R4 的世界校验记账在整批回滚后还留在结果对象里, 而它描述的正是那些已经作废的操作）
   —— 这就是"手抄"这件事的证词（那个字段 2026-10-05 随收口轮一起删了）。
3. **料跨 3~4 个文件** —— 想知道"R2 吃什么", 得把编排、`entities.py`、`render.py`
   和 prompt 一起读。

## 它是什么 / 不是什么

这是**声明**: 跑哪几步、每步是谁（LLM 身份）、吃哪几段料、往哪写、什么时候跳过。
**执行体仍在各家**（prompt 在 `llm/prompts/`、契约在 `contract/digest/`、落库在
`revise.py` / `groups.py`）—— 表只说"是什么", 不说"怎么写"。

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

from collections.abc import Callable
from dataclasses import MISSING, dataclass, fields
from typing import Any

from contract.digest import digest_registry

#: `writes` 的"面" —— 每个字段名归一个面, 守门用例按面去查真源:
#:   节点面 → `nodes.BrainNode` 的字段名 · `edge` → `graph.REL_*` 的取值 ·
#:   `note` → `notes.SLOT_*`（备忘录的槽 —— **不进图**, 只在工作记忆里）·
#:   ⭐ `segment` → ⛔ **不查真源**（它是**段内中间产物**: R0 产、同段的 R1 吃,
#:   不进图也不落库 ⇒ 没有"真源"可查）。为什么仍要写进表: `writes` 是"这一步往哪写"
#:   的地图, 中间产物也是它的产出; 而 `result_fields` 那格管的是回滚, 两者分工不同。
NODE_FACES = ("episode", "experience", "belief", "entity", "profile")
EDGE_FACE = "edge"
NOTE_FACE = "note"
SEGMENT_FACE = "segment"
#: 名字**不对任何真源**的面（守门用例跳过名字校验, 但要认得它）
FREE_FACES = (SEGMENT_FACE,)
FACES = (*NODE_FACES, EDGE_FACE, NOTE_FACE, *FREE_FACES)

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
#: `llm_chat` 只在**每次尝试前**看表 ⇒ 前几轮一慢, **后面几轮集体被"饿死"**
#: （报错还只说"撞上时间预算", 看不出是哪一轮）。5 次 high 档长考本来就贴着 300s。
#: 标定入口 = 真机日志 `llm chat task=digest.relate ms=…`（已存在, 按 `task=` 分轮看）。
DIGEST_ROUND_BUDGET_SECONDS = 120.0

#: ⭐ **整段硬顶（秒）** —— 一轮轮下来总共不许超过它。
#: 判据: 每轮各自的预算防"互相饿死", 硬顶防"每轮都刚好不超时"叠成半小时
#: （2026-09-02 真发生过一次: 重试放大把 digest 拖到近半小时）。
#: ⚠️ **硬顶必须 ≥ 各轮预算之和** —— 否则后面的轮又会被前面的吃掉, 等于没改;
#: `tests/core/test_digest_rounds.py` 钉住这条。
#:
#: ⭐ **2026-09-29: 600 → 840**（这是给 R0「切分」留的位子）。由来: 当时是
#: 5 个 LLM 轮 × 120s = **600, 正好顶满**硬顶（`akin` 不算 —— 它零 LLM,
#: `planned_seconds()` 只数 `llm=True` 的轮）⇒ 再多一轮守门当场红。
#: ⭐ **2026-10-05（L8）: 840 → 600** —— 收口轮删掉, 又回到 5 个 LLM 轮 × 120s。
#: ⭐ **2026-10-08（P10）: 600 → 720** —— 加上 L2（`cognize`）= 6 个 LLM 轮 × 120s。
#: ⭐ **2026-10-13: 720 → 600** —— **`group`（L2-a 分群）退役**（代码搬
#: `archive/digest_group/`）= 5 个 LLM 轮 × 120s。
#: ⚠️ **每轮 120s 依然没动**（理由同上一条, 别砍）; 真机最坏墙钟因此回到 10 分钟。
#: ⚠️ **每轮 120s 没动**（它是按 high 档长考标定的, 砍它会重新制造"前几轮把后几轮
#: 饿死"那个病; 标定入口 = 真机日志 `llm chat task=digest.… ms=`）。
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

    判据: key 取的**就是契约相位名**（`contract.digest.PHASE_*` 的取值）, 而
    LLM 调用身份的后缀与日志前缀本来就该跟它同名 —— 于是"三个派生"其实是**零个新名字**。
    """

    key: str
    """表内主键 —— 契约相位名（`record` / `akin` / `relate` /
    `settle` / `group`）。见类 docstring: 另外四个标识都从它来。"""

    step: str
    """人读的步号（与 `core/digest/__init__.py` 的步序表同一份写法）。
    ⏸ 旧文档与旧注释里的 `R1`/`R2`/`R3`/`R4` 按这里对: **R1=记 · R2=接（`relate`）· R3=挂**
    （`R4=收口` 2026-10-05 删）。"""

    parse: Callable[..., Any] | None
    """`(raw, **ctx) -> (parsed, ValidationResult)` —— 结构校验的入口（住在契约层,
    `contract/digest/parse.py`; ⚠️ 它的函数名仍叫 `parse_round_a` / `parse_round_b`
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
    今天五轮都用默认; 要分轮调（记最贵）就在这一格写数。
    ⚠️ 它是**每次尝试前**的检查（`llm_chat` 的既有语义）, 不掐断正在飞的那一次调用。
    """

    own_snapshot: bool = False
    """True = 这一步失败**只回滚它自己**（加法性的: 料留着, 下一段再来 —— 自愈）。"""

    needs_segments: bool = True
    """True = 这一步是**对着切片干活**的（没有切片就没活干）。

    ⭐ 判据来自 R0 那条"空骨架 ⇒ 收工"（2026-09-29, N4d）: 切分员说"这一段没有
    值得记的"时, 建节点 / 连边 / 归属 / 分群**全部空转**（`relate` 还会被契约
    判形状错）⇒ 一律不发。
    ⏸ **从前唯一写 False 的是 `close`**（收口吃备忘录而不是切片）—— 2026-10-05（L8）
    随轮一起删 ⇒ **今天五轮全是 True**（这一格留着, 是因为"有一轮不对着切片干活"
    这件事本身还会回来: 将来若有"只看备忘录/只看时间"的轮, 就在这一格写 False）。
    """

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
        key="split",
        step="⓪ 切",
        parse=digest_registry.parse_split,
        material=("本段新增互动", "本段的时间", "日子", "还开着的约定", "本章标题"),
        writes=((SEGMENT_FACE, ("span", "abstract", "state", "id", "due")),),
        result_fields=(*CONTRACT_FIELDS, "segments", "segment_collapsed", "segment_dropped"),
        # ⚠️ **不设跳过条件**: 它跑不跑由编排层说（`digest_segment` 入口已经挡过
        # "这一段没新事件"）, 而"跳过一整段"是整段级的判定 —— 那要同时决定水位推不推
        # （推了 = 那段内容永不入记忆）, 不该藏在某一轮的 `skip` 格里。
        skip="",
    ),
    RoundSpec(
        key="record",
        step="① 记",
        parse=digest_registry.parse_round_a,
        material=("本段新增互动", "本段骨架", "本章标题", "画面记忆", "已有的对象",
                  "角色人设（锚点）", "本段情绪标尺"),
        writes=(
            # 条目自带的位置是 `span` 区间, 由 `_expand_spans` 展开成 `event_seq`。
            ("episode", ("title", "text", "verbatim", "verbatim_seq", "tags", "entity",
                         "significance", "emo_int", "emo_span", "observer",
                         "event_seq", "ts",
                         # 引擎物化（🚫 只进召回侧, 绝不进 LLM 上下文）:
                         "emo_shape", "place", "place_raw", "aff_at_encoding")),
            # ⏸ **`topics` 2026-10-14 摘掉**（用户裁"退役"）—— 它唯一的读者是 `akin`
            # 那条链（挑候选 / 印 `轴` / 校验 `on`），而真机上**大半是空的**（6 个 akin
            # anchor 里 4 个 `topics=[]`）+ 有值的三条互相不共轴 ⇒ 候选**恒 0 条**。
            # ⚠️ 节点字段**留着**（停产不删格式, 同 `profile`）: 老档那几格还读得回来。
            # ⏸ **`("profile", …)` 2026-10-12 摘掉**（玩家画像停产, 用户裁:
            # *"`entity.text` 取代了它的定位"*）—— 契约不再要它、`parse_round_a`
            # 认得出但**丢行**, 所以这一步在真机上**不会再产 profile 节点**。
            # ⚠️ `episodes._create_a_nodes` 里那一支**仍在**（直接喂条目的调用方
            # 还能用它, 单测也还打着）—— 那是**停用**不是**删机器**, 见那边的注释。
            # ⭐ note 的写者 **2026-10-05（L7/L8）起只有这一轮**: 按 R0 的表产
            # `add` / `update` / `close`（收口轮已删）。
        ),
        result_fields=(*CONTRACT_FIELDS, "notes_ops", "record_gaps", "spanless_ids"),
        skip="没有能填的骨架行（无区间那一行没有事件可写 —— 正文就是 R0 给的 abstract）",
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
        key="relate",
        step="③ 接",
        parse=digest_registry.parse_relations,
        material=("本次新经历（含引擎候选标注）", "现有经历（候选）",
                  # ⭐ 2026-10-14（L2 碰撞这一刀）: 她认过的同类经历**印证过哪条看法**。
                  # 补的是 L1 唯一缺的那一刀 —— 看得见候选经历, 却看不见"它印证过谁"
                  # ⇒ `supports` 只能靠猜（详见 `material.akin_supported_beliefs_block`）。
                  "她认过的同类印证过的看法",
                  "本段时间线", "现有认知", "角色人设（锚点）"),
        writes=(
            # ⭐ **只落边**（`apply_relations`）—— 一个节点都不建、一个字正文都不写
            # （造看法 / 写正文是 L2 的活; 边归属表见 `DESIGN_DIGEST_TWO_PASSES` §3）。
            # ⚠️ **`evolved_from` 2026-10-08（E3）补进这一格** —— P7-2 加了那个动作却
            # 漏了它, 而守门把这个漏印固化成了判据（红账, 见 `DESIGN_ENTITY_TAGS §7`）。
            # ⛔ **`about` 移出**（E3）: 它不由 LLM 写 —— 引擎从 `tags` 的 `#entity:` 派生。
            ("edge", ("supports", "akin", "contradicts", "evolved_from")),
        ),
        result_fields=(*CONTRACT_FIELDS,),
        skip="",
    ),
    RoundSpec(
        key="cognize",
        step="⑥ 想",
        parse=digest_registry.parse_cognitions,
        material=("这次的事", "这一类事", "现有认知",
                  # ⭐ 2026-10-14（L2 碰撞这一刀）: 跟这一段的证据**共享证据**的已有看法 ——
                  # 治"同一个结论写第二条"（判据/印法见 `material.collided_beliefs_block`）。
                  "跟这条撞上的现有看法",
                  "已有的对象", "角色人设（锚点）"),
        writes=(
            # ⭐ **L2 的产出 = 正文 + 它出生自带的那几条边**（`apply_cognitions`）:
            # 造 `belief` + 三条边。
            # ⏸ **`("experience", ("text",))` 2026-10-13 摘掉** —— 给类写沉淀随 `group`
            # 退役停产（契约不再要它 ⇒ `parse_cognitions` 丢那一行 + 记账）。⛔ 不改
            # `title` / `ts` 那条纪律照旧（停产不是删机器: `revise._soak` 那一支还在）。
            ("belief", ("text", "subject", "significance", "tags", "entity",
                        "event_seq", "ts")),
            ("edge", ("supports", "evolved_from", "contradicts")),
        ),
        result_fields=(*CONTRACT_FIELDS, "created_beliefs", "reused_beliefs",
                       # ⏸ `soaked_groups` **留着但恒空**（没有类可写了）—— 它是
                       # `DigestResult` 上的字段, 删它要一起动回滚清空清单与守门;
                       # 与"停产不是删机器"同一条口径, 单独一刀再说。
                       "soaked_groups", "cognize_warnings"),
        # ⭐ **两个料名 = 两个区**（用户 2026-10-14 裁, 印法见 `material._l2_material`）:
        # 【这次的事】= 本段被 L1 连过的（**立足点**）·【这一类事】= 它们一跳 `akin`
        # 的邻居（她认过"是同一类事"的那些 —— **额外的证据**）。
        # ⏸ 从前那张**平表**（`被连过的经历` + 挂在每条 anchor 下面的 `↳ 她认过跟它像的`）
        # 已撤: 簇散在 anchor 底下 ⇒ 她数不出"这一类一共几条 / 跨多长时间"。
        # ⏸ **「本段归类的群」那一格 2026-10-13 摘掉** —— 它由 `member_of` 喂, 而那条边
        # 不再有人落 ⇒ 恒空（守门 `test_material_names_are_not_dead` 当场抓到这个不一致:
        # "料还在、没人提"）。
        skip="本段没有被 L1 连过的经历（孤立经历不进 L2 —— 归纳没有立足点）",
        # ⭐ **它也是加法的**: 失败只丢"新造的那几条看法", 经历与边照旧
        # （与 `group` 同一个理由 —— 拿真东西换装饰是亏的; 用户 2026-10-08 裁）。
        own_snapshot=True,
    ),
    RoundSpec(
        key="settle",
        step="⑦ 沉淀",
        parse=digest_registry.parse_attribution,
        material=("这一段认下的对象", "她写了、但库里还没有的名字",
                  "已有的对象", "角色人设（锚点）"),
        writes=(
            # ⭐ **两路**（2026-10-13 接线, `parse_attribution` 按 `id` 分好）:
            # 没有 `id` ⇒ 造 `entity` 节点（name / aliases / `event_seq` / ts, 行里带了
            # `text` 就顺手装第一句看法）; 有 `id` ⇒ 改已有的（`name` 改名 / `text` 写看法
            # + **水位 `text_seq`**）。
            ("entity", ("name", "aliases", "text", "text_seq", "event_seq", "ts")),
            # ⚠️ **`about` 不由 LLM 写**: 她只在写节点时留下引用, 引擎据此派生边;
            # 这一轮**建完新对象之后回头补边**（同段闭合, 零 LLM）。
            ("edge", ("about",)),
        ),
        result_fields=(*CONTRACT_FIELDS, "created_entities",
                       "renamed_entities", "rewritten_entities"),
        skip="本段没有被引用的对象, 也没有解析不到的名字（这一趟没有活干）",
        # ⭐ 加法的: 失败只丢"新对象 + 这一次补边" —— 经历/看法照旧（同 group / cognize 的判据）。
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
