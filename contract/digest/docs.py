"""digest 契约的**文档清单** —— 哪个相位有哪几份文档。

⛔ **文案不在这里**: 每个相位要说给 LLM 听的那段字住在 `prompts/*.md`（人可改、可 diff,
`build_schema` 读它 + 填槽）。本模块只剩**机器读的清单** —— 名称与相位, 供
`actions(phase)` / `RELATION_ACTIONS` / `parse` 的键域校验用。

⚠️ **每个字段只写一遍**的纪律没变, 只是落点换了: 示例与【逐字段】同源于
`prompts/parts/row_fields.md`, 域契约同源于 `prompts/parts/domain.*.md`。

⚠️ ~~`TOUCH` / `UPDATE` / `ADD`~~ 与 `parse_round_b` / `apply_decisions` 是**停放的旧一族**:
生产代码零调用者, 但用户裁"有些可能会留给 L2, 不用着急删"（`docs/TODO_TWO_PASSES.md` §94）
⇒ ⛔ **只改名, 不删**。
"""
from dataclasses import dataclass

from contract.digest.tables import (
    PHASE_COGNIZE,
    PHASE_RECORD,
    PHASE_RELATE,
    PHASE_UNDERSTAND,
)

#: ⭐ **输出纪律 = 契约层的独占句**（G1, 2026-10-05）—— 各相位共用,
#: **prompt 文件里一个字都不许再抄**（守门 `test_the_output_discipline_lives_only_in_the_contract`）。
#:
#: 合并前的样子是**同一句话两处各一份**: 契约层每个相位开头写"不要任何解释文字 /
#: 不要 ```json 代码块", 而每个 `digest_*.md` 结尾又各写一遍"必须输出完整 JSON（键名开头）"
#: —— 同一次调用的 system 里就重了两遍, 而模型只学会它看到的那一份。
#: **只有 prompt 有、契约没有**的那两点现在收进这里: **别在思考后停止**（reasoning
#: 截断那个坑）· **别交空输出**。
#: ⚠️ **修复轮不算重复**: 输出被整包拒之后 `core/digest/call.py` 的 feedback 与
#: `llm/client.py` 的 JSON 修复循环**故意各留一份** —— 那时模型才需要被提醒一次。
OUTPUT_RULES = (
    "不要任何解释文字",
    "不要 ```json 代码块",
    "不要在思考后停止",
    "不要空输出",
)
#: 渲染成给 LLM 的那一行（每个相位 md 的**第一行槽** `{{discipline}}`）: 元组 ⇒ 句子, 单源。
OUTPUT_DISCIPLINE = f"输出 JSON（{', '.join(OUTPUT_RULES)}）:"


@dataclass(frozen=True)
class DigestAction:
    """一份**文档**的名字与相位 —— 形状与字段约束的正文在 `prompts/*.md`。"""

    name: str
    phase: str


#: ⭐ **R1 记录员的条数契约**（3b-2, 2026-09-29）—— 与 R0 的"切成几件"**分开**:
#: 后者说的是"这一段该**切成**几件事"（切分权在 R0, 那句话跟着它）;
#: 而 R1 拿到的是**已经切好的骨架**, 它只需**按顺序填**。
#: ⚠️ 两处合一 = 模型会以为自己还有切分权（那正是 3b-1 刚拿走的东西）。
#: 正文: `prompts/parts/record.bond.md` / `record.mmt.md` + `prompts/record.md`。
RECORD_EPISODE = DigestAction("record_episode", PHASE_RECORD)

#: ⏸ `on_mind` 槽（连同它的字段常量）2026-09-29 退役 —— L1 的输出只有 `episodes` 一个键
#: （心境不是"经历", 不该跟 episodes 平级）。将来真要"她此刻在想什么"走 **belief**
#: （进图、有边、能被召回、会被新经历更新）。
#: ⚠️ 下面三个是**停放的旧一族**: 没有轮在用, 形状与解析留着。正文: `prompts/understand.md`。
TOUCH = DigestAction("touch", PHASE_UNDERSTAND)
UPDATE = DigestAction("update", PHASE_UNDERSTAND)
ADD = DigestAction("add", PHASE_UNDERSTAND)

#: ⭐⭐ **L1「判关系」的四个动作**（`DESIGN_DIGEST_TWO_PASSES.md` §9, 2026-10-07 用户定稿）
#:
#: 与 `TOUCH`/`UPDATE`/`ADD` 那一族的根本不同: **它们一个字的正文都不写** ——
#: **键本身就是动作**, 值恒是一个 **id**（凡是要"写点什么"的东西都在另一趟）。
#: ⚠️ `graph.RELS` 是边名的真源 ⇒ 守门钉住"这四个名字必须都在 `RELS` 里"。
#: 正文: `prompts/relate.md`。
RELATION_ACTIONS = (
    DigestAction("supports", PHASE_RELATE),
    DigestAction("akin", PHASE_RELATE),
    DigestAction("contradicts", PHASE_RELATE),
    DigestAction("evolved_from", PHASE_RELATE),
)

#: ⭐⭐ **L2「造认知 / 写正文」的两个动作**（`DESIGN_DIGEST_TWO_PASSES.md` §3/§5,
#: 2026-10-08 用户裁决 · P7 落契约）。
#:
#: ⚠️ **与 L1 那一族正好对偶**: L1 的键**全是边名**（⊆ `graph.RELS`）,
#: 这一族的键**全是节点 kind**（⊆ `nodes.KINDS`）—— 因为这一趟干的是"造节点 / 写正文"。
#: 两边合起来仍然只有 `RELS`(6) + `KINDS`(5) 两个真源, **零第三处维护**（§4 的纪律）。
#:
#: 两处**形状规则**（§4 的两条 + 这次的一处扩展, 用户 2026-10-08 点头）:
#:   ① 值是字符串 = 引用一个已有节点（`"evolved_from": "u0002"`）
#:   ② 值是对象 = 造一个新节点（`"belief": {…}`）
#:   ③ ⭐ **值是数组 = 引用多条**（`"supports": ["m0007", "m0011"]` —— 每条落一条边;
#:      写单个字符串也收, 见 `_ref_list`）
#:   ④ ⭐ **对象里带 `id` = 给那个已有节点写正文**（`"experience": {"id": "g0001", …}`）
#:      —— 与 ② 同一个键的两面（有 id = 改, 无 id = 造）。⛔ `id` 只在这一处合法。
#: ⚠️ **建类不归这一趟**（用户 2026-10-08: *"experience 本质是群 belief … 类是事件,
#: 事件归 L1"*）—— 起类名 / 圈成员是 `group` 那一环的结构活; 这里只**写它的正文**。
#: 正文: `prompts/cognize.md`。
COGNIZE_ACTIONS = (
    DigestAction("belief", PHASE_COGNIZE),
    DigestAction("experience", PHASE_COGNIZE),
)

DEFAULT_ACTIONS = (RECORD_EPISODE, TOUCH, UPDATE, ADD, *RELATION_ACTIONS,
                   *COGNIZE_ACTIONS)


# ============================================================================
# 下面两段是**切分那一轮**的设计注记 —— 正文在 md, 这里只留"为什么这么写"
# ============================================================================

#: 段类型 → **产出契约块**（进 `prompts/split.md` 的 `{{domain_contract}}`; 2026-09-20 用户裁决）
#:
#: 为什么按段类型给不同契约: `mmt` 是碎聊（**需要被切分**）, `bond` 是作者写的完整一章
#: （**本身就是一个 episode**, 再切就是把一个 episode 切断）。用户原话:
#: *"你细看这些 episode 像流水账一样，真正的 episode 一个就可以定下，需要被切分的是
#: 长篇 MMT 等；episode 应该 informative but single，belief 则是 brief but descriptive"*
#: ⭐ **2026-10-06 收窄（`docs/DESIGN_SPLIT_AND_AXES.md` §3）: 一件 = 一场戏。**
#: 真机那种"一个段切成 5 件"的切法直接违反 `DESIGN_SEGMENT.md` 的"段是最小单元、
#: 根本不产生截断" —— 肇事者原来是 bond 支末尾那三行（明写"聊天另行切件"）, 已改。
#: 正文: `prompts/parts/domain.bond.md` / `domain.mmt.md`（bond 那份里 `{{scope_line}}`
#: 就是"切几件"那一行, 由 `parts/scope.one.md` / `scope.multi.md` 填）。

#: ⭐ **R0 每行的字段与释义**（2026-10-05: 三键 → 五键, `keep` 换 `state`）。
#:
#: ⚠️ **2026-10-04 收窄过判据**（真机 13 段实测之后用户裁的）: 从"三种"（誓约 /
#: **被改了看法的时刻** / 她给自己定的规矩）收成"**一种**"（答应了谁一件还没了结的事）。
#: **为什么删那两条**: ① 它们是 **belief 的本职**（R2 的 `add` 就是"新经历形成了
#: 稳定结论"）—— 同一个东西两处收 = 第二个 belief 库; ② 它们的判据是"我明白了",
#: **忘了没有代价**, 而 `pinned` 的判据是"忘了会出事"。
#: ⭐ **实测症状**（13 段真机跑, `.testtmp/probe_r0_real.py`）: 6 章**每章恰好一条 ⭐**,
#: 全是章末的自我领悟（「原来不是只有被踩在脚下才算我的价值」）⇒ 走廊无限长、本子就无限长。
#: ⛔ **别再用"她会不会一直带着它"当判据** —— 那句话太宽, 任何一章的高潮都满足它。
#: 判据只能是"**忘了它, 就真会出问题**"。
#:
#: ⭐ **2026-10-05 换形状**（`DESIGN_DIGEST_LEDGER`）: 骨架与账目**合成一张表** ——
#: 一行 = 一件切片 + 它的账目状态（`state` / `id` / `due`）。约定从**出生切片**长出来、
#: 在**了结切片**上关掉; **没有那一刻的**（她等过、那天没人来）用 `span: null` 自成一行;
#: **后来才知道的日期**用 `state: open` + `id` 补。⇒ 收口轮整轮消失（它读的备忘录,
#: R0 手里就是原文）。
#:
#: ⚠️ **每个字段仍然只写一遍** —— 示例与【逐字段说明】都从 `parts/row_fields.md` 出
#: （左对齐、缩进按"逐字段说明"那一份; 进示例时整体缩 5 格, 由 `textwrap.indent` 做）。
#: 为什么非要这样: `contract/schema.py` 那条纪律 —— **"示例才是形状的来源"**; 而
#: "取值清单 / 说明 / 示例"三处强度不一的时候, 模型只学会示例那个形状
#: （2026-09-20 art 命中率 0/5 就是这么来的）。
#: ⚠️ 它渲染的是 `episodes[]` 里的**行形状**（不是某一份文档的字段块）, 所以它没有
#: `DigestAction` 可挂 —— 正文: `prompts/parts/row_fields.md`
#: （`{{abstract_max}}` 由 `tables.ABSTRACT_MAX` 填）+ `prompts/split.md` 的四个语义块。
