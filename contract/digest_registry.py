"""digest 域注册表 — 记忆整理 LLM 输出的动作 spec 单源（AGENT_BRAIN.md §3 重构 / 板块 2）。

背景: digest 曾是"数据产出"风格——build_digest_schema_v2 手写 schema（LLM 可见面）
与 revise.py 手写校验（runtime 接受面）双写, 漂移源。重构为动作注册表:
每个动作 spec 一份, 驱动两层——
    ① build_schema(phase)  → prompt 内嵌的输出格式文本（字段旁内联约束注释,
                              A-MEM Ps1 模板同款: 规则贴字段, 不散散文）
    ② parse_round_a/b      → 结构校验（宁缺勿错, 逐条报错; 内容质量用 warning
                              不阻断, 引擎执行层再叠加引用级/图语义校验）

分轮（两轮 digest, 2026-09-02 定稿 + 深度整理占位）:
    phase=record     Round A 记录员: record_episode——只产 episode, 不看旧记忆
    phase=understand Round B 理解者: touch / update / add——决策表（逐 episode 一行,
                     结构保证不漏不编 id; 输出对齐输入 = A-MEM 列表对齐的升级）
    phase=deep       深度整理（merge/contradict/…: 后续板块注册, 每 N=5 段触发）
包级字段（B 轮）: affection_exp_delta（引擎消费）。
⚠️ ~~`evidence`~~ **2026-09-29 删** —— 零产品消费者, 而契约每段要它 ≤5 条 + `quote`
逐字引用时间线 ⇒ 白付；详见 `core/brain/REDUNDANCY.md`。

引擎执行层 = `core/digest/pipeline.py`（**每段 5 轮**编排）+ `core/brain/revise.py` /
`core/brain/groups.py`（各轮的执行器）; 本文件只管"LLM 契约层": 结构/类型/边界/字段约束。
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass
from datetime import date
from typing import Any

from contract.model import ValidationResult

PHASE_RECORD = "record"
#: ⭐ **R0「切分」**（2026-09-29, N4d）—— 每段的**第一步**: 只划区间 + 写一句总括
#: + 挑出"要一直带着的"那几条。**不写正文、不填情绪、不打分、不建节点。**
#: ⚠️ 它拿走了 R1 从前最重的那件事（划区间）⇒ **图的形状由它一个人决定**
#: （几个节点、每个覆盖哪段）, 所以它的产出必须**可校验**（区间在不在时间线里）
#: 且**可观测**（覆盖了多少 / 丢了几条 —— 见 D1 那本缺口账）。
PHASE_SPLIT = "split"
PHASE_UNDERSTAND = "understand"
#: ⏸ ~~`PHASE_CLOSE`~~（R4 收口）**2026-10-05（L8）删** —— 账目归 R0 的表
#: （`state`/`id`/`due` 三个键）, 那一轮整轮消失。它的判据搬去了哪里:
#: 判"这条约定还开着吗 / 这一段里有没有新说定的"= `parse_split` + `STATE_SEMANTICS`
#: / `CLOSE_SEMANTICS`（R0 手里是本段**原文**, 比 R4 读的 120 字转述强）。
#: ⚠️ ~~`PHASE_PANORAMA`~~（全景轮/写卡）**2026-09-29（N4a / N4e）已退役** —— 它的两个槽
#: 都没了（`habits` 取消 · `on_mind` 自己也退役: *"太煽情了"*）⇒ 它没有输出了。
#: **R3 归属轮**（§8 第 3 行: 归属 + entity 维护）—— 每段的**最后一步**。
#: 它写 `about`（hint/正文 → 候选表里的对象）、`new_entity` 提案、entity 载荷改写；
#: ⚠️ **不碰正文**（改正文是 R2 的活）、**不合并节点**（§9-12 ④ 未裁）。
PHASE_ATTRIBUTE = "attribute"
#: ⭐ **L2-a 分群轮**（N7, 2026-09-29）—— 每段的**最后一步**, 与 R1–R4 **不同层**:
#: 它吃的是"**她连过的块**"（`akin` 连通块, 由引擎切好）, 产的是**群节点 + `member_of` 边**。
#: ⚠️ 它**不给块判像不像**（那是她的活, 也是为什么要分两步）—— 只做两件事:
#: **起名**（new）/ **认出它属于已有的类**（attach）。
PHASE_GROUP = "group"
# EXT: digest-deep — 三相位之 deep（设计已声明, 未实现）; 勿删（docs/EXTENSION_POINTS.md）
PHASE_DEEP = "deep"

#: B 轮决策类型
DECISIONS = ("touch", "update", "add")

#: ⏸ ~~`PINNED_OUTCOMES = ("kept", "broken", "superseded")`~~ **2026-10-05（L8）删** ——
#: 它守的是收口轮 `close` 行的 `state`（结局词）。三种结局如今**一律划掉**,
#: 结局写在**图里那条经历**的正文里; 而那条 note 操作只剩 `{"action": "close", "id": …}`
#: （见 `core.brain.notes.close_op`）⇒ 词表没有读者了。
#: ⚠️ 旧档里带着 `state` 的 `note` 事件读侧照认（`notes.fold` 只当账, 不校验）。

#: 玩家画像条目的 subject 固定值（与 nodes.PLAYER_SUBJECT 对齐, 契约层不依赖 core）
PLAYER_SUBJECT = "player"

#: 边界（parse 级）
#: ⚠️ 2026-09-21 删 `MAX_CONTENT` / `MAX_EXAMPLES` / `MAX_EVIDENCE`——全仓（含本文件）
#: 零引用: 注释写着"parse 级边界", 但没有任何校验器消费它们, prompt 侧也没硬编码对应
#: 数字 ⇒ 属"契约声明与执行脱钩"的残留。**要恢复边界必须同时落校验器**,
#: 只把常量加回来 = 又留一处看起来生效的假边界。
MAX_EPISODES = 5        # A 轮单包最多 episode 数
MAX_ALIASES = 8         # `new_entity` 的别名上限（超了截断 + warning —— 别名是效率优化）
MAX_TEXT = 300          # 正文（text）单行上限（汉字）——三槽合流后两种 kind 共用
MAX_TAGS = 4            # tags 检索词上限
#: ⏸ `MAX_ITEMS` / `items` 字段 **2026-09-29 删** —— 零活读者, 且"是不是同一个东西"
#: 写在 episode 里分不清（见 `nodes.py` 的字段区注释）⇒ 物品面将来走 `inventory` 旁路。
#: 类名（group 的 `title`）上限 —— ⚠️ **与 episode 的 8~16 字不是同一条**: 类名可以很短
#: （"那片苔藓" 4 字就够）, 这里只挡"写成一整句话的那种"; 超了**只告警不截断**
#: （截断会把名字截坏, 而名字是**地址**）。
GROUP_TITLE_MAX = 16

#: ⭐ **R0 行的账目状态**（2026-10-05 取代旧的 `keep`）。
#:
#: `open`  = 到**本段结束时还开着**的约定（进她的备忘录）
#: `close` = 这一行**了结**了名单里的某条（`id` 必填）
#: ⛔ **没有"与账无关"这个取值** —— 那就是**不写这个键**（缺键 = 无关, 是绝大多数）。
#: ⇒ 旧那套"缺键/非法值 ⇒ 按默认档 `temporary` 收下"的口径**随之取消**:
#:   缺键不是"取了个默认值", 而是"这件事跟账无关"。
#: ⚠️ 但**值写错（`"opne"` 这种）仍然按"缺键"收 + 告警** —— 理由是内容: 这一条切片
#:   的区间与 `abstract` 都是真的, 把它整条丢掉 = 那段事从此没有任何记录;
#:   而账目效果丢了会**自愈**（那条约定下一段还在名单里, 引擎会再摆一次）。
STATE_VALUES = ("open", "close")
#: `abstract`（一句总括）的字数上限 —— **软上限**: 超了**收下但告警**
#: （同 `ON_MIND_MAX` 当年的口径: 它不是"形状错", 不该废整包）。
#: ⭐ **note 正文的长度真源就是它**（2026-10-05）: `state=open` 的切片, 它的 `abstract`
#: 会被**原样**抄进常驻备忘录 —— 而 note 侧那条"≤20 字"的体检判据已删
#: （3b-3 起它必然恒响, 只会制造噪音）⇒ **长度只在这里管一次**。
#: 60 = 一句散文的上界, 再长就该怀疑她在写正文了。
ABSTRACT_MAX = 60
#: ⭐ **没有区间那一行的字数上限**（`state=close` + `span: null`）—— 那一行的 `abstract`
#: **就是那条回忆的正文**（"老师生日那天没有来"）, 所以它按 **episode 正文**的尺子量,
#: 不按上面那句"一句总括"的 60 量。数值与 `MAX_TEXT`（episode 正文）同源。
ABSTRACT_MAX_FREEFORM = 300
#: 一段最多切几件事。⭐ **这是防"切太碎"的唯一边界** —— R0 不写正文, 没有别的信号
#: 能拦住它把一场戏切成好几件（那是流水账, 不是记忆）。越界 ⇒ 截断 + 告警。
#: ⚠️ **12 → 20**（2026-09-29 / 3b-2）**是错的; 2026-10-06 收回 20 → 12**:
#: 那次改动同时做了三件推"过切"的事（加"必须覆盖全部" + "连闲聊自成一件" + 抬上限）——
#: 真机实测 **9 次调用切了 18 件**, 一个段（Trigger+Bond+Finish）被切成 5 件。
#: ⇒ **上限从来不只是上限, 它是标尺。** 一件 = 一场戏之后, 一段的件数应当 ≈ 1。
#: **数值标定**: 看 `digest_split segments=` 那行的分布。
MAX_SEGMENTS = 12

#: ⭐ **输出纪律 = 契约层的独占句**（G1, 2026-10-05）—— 六个相位共用下面那一行,
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
#: 渲染成给 LLM 的那一行（`build_schema` 每个相位的第一行）: 元组 ⇒ 句子, 单源。
OUTPUT_DISCIPLINE = f"输出 JSON（{', '.join(OUTPUT_RULES)}）:"

#: ⚠️ **`TASK_TIMESPAN` 已于 2026-09-17 删除**（用户裁决）—— 连同 schema 里那行
#: `"time_span": "halfday"`。
#:
#: 它曾是 A 轮要求 LLM 回答的"本段剧情跨了多久"（枚举 `same`/`halfday`/`day`/
#: `days:N`/`week`/`weeks:N`/`month`），唯一目的是喂**剧情游标**（`sim_day` 累加）。
#: 时间轴换代（`ESSAY_TIME_MODEL §10`）把剧情日历整族作废之后：
#:
#: 1. **推进链已删**（`digest.py` 的 `_clock.advance` 那一段）
#: 2. **parse 层从来没取过它** —— `parse_round_a` 只读 `raw["episodes"]`,
#:    所以它**连落库都没有**（真机 `data/` 里 grep 一条都没有）
#: 3. ⇒ 它成了**每轮 digest 都要付的 token 开销, 收益为零**
#:
#: ⚠️ 当时给它的免死理由（"为衰减新模型预留"）**不成立** —— 新模型的年龄单位是
#: **活跃日/会话**, 输入是 `node.ts` + 事件流, `time_span` 不是它的输入。
#: 详见 `TODO.md`「记忆衰减」。
#:
#: **枚举定义（`core/worldtime/span.py`）保留** —— 契约死了, 语法不必跟着死;
#: 将来真要有"她口述跨了多久"的需求, 那套枚举可以直接拿回来用。



@dataclass(frozen=True)
class DigestAction:
    """digest 动作 spec（单源真值）。

    渲染与校验共用: schema_text 的每个字段约束同时是 parse 的检查依据——
    改字段约束只改这一处。
    """

    name: str                       # record_episode / touch / update / add
    phase: str                      # PHASE_*
    role: str                       # 一句释义（LLM 可见）
    semantics: str                  # 何时用/怎么改/禁什么（三段式规则文案）
    field_schema: str               # 字段块（// 内联约束注释, A-MEM Ps1 式）
    example: str = ""               # 范例 JSON 片段（正例）


# ============================================================================
# 动作定义
# ============================================================================

#: 段类型 → **产出契约块**（进 Round A 的 `{{digest_schema}}`; 2026-09-20 用户裁决）
#:
#: 为什么按段类型给不同契约: `mmt` 是碎聊（**需要被切分**）, `bond` 是作者写的完整一章
#: （**本身就是一个 episode**, 再切就是把一个 episode 切断）。用户原话:
#: *"你细看这些 episode 像流水账一样，真正的 episode 一个就可以定下，需要被切分的是
#: 长篇 MMT 等；episode 应该 informative but single，belief 则是 brief but descriptive"*
#: ⭐ **2026-10-06 收窄（`docs/DESIGN_SPLIT_AND_AXES.md` §3）: 一件 = 一场戏。**
#: 真机那种"一个段切成 5 件"的切法直接违反 `DESIGN_SEGMENT.md` 的"段是最小单元、
#: 根本不产生截断" —— 肇事者是下面 bond 支末尾那三行（明写"聊天另行切件"）, 已改。
_DOMAIN_CONTRACT = {
    "bond": (
        "【本段含一章羁绊剧情（**作者单位**: 有始有终的完整一段）】\n"
        "→ **这一段恰好 1 件**（它就是**这一段经历过的事**）:\n"
        "   · informative but single —— 把这一段讲透（起因/关键推进/落点都在里面）,\n"
        "     但**只讲这一件事**; 不按时间把每个回合罗列一遍。\n"
        "   · ⚠️ 时间线里的每一步**不是**要分别切的件 —— 那会写成流水账, 是本轮的典型错误。\n"
        "   · title 用**本章标题**（上方【本章标题】给了）。\n"
        "⚠️ 本段**同时含 MomoTalk 聊天**（时间线里那些不是剧情画面的来回消息）时:\n"
        "   那些**是这一次见面的铺垫与余韵** —— **写进这一件里**, 不另起件。\n"
        "   （判据: 聊天里换了几次话题**不算**新的一件; 只有**另一次见面**开始才算。）"
    ),
    "mmt": (
        "【本段类型 = MomoTalk 聊天（**无作者单位**: 一次覆盖多轮碎聊）】\n"
        "→ **一件 = 一次见面 / 一段连续聊天**（informative but single）。\n"
        "   · ⚠️ **中间换了话题、换了人、换了地方, 都还是同一件事** —— 那只是它的过程;\n"
        "     只有**另一件事真的开始了**（人走了、事结了、隔到下一次）才新起一行。\n"
        "   · 同一件事不拆两件; 两件事不并一件;\n"
        "   · ⚠️ **不能留空档**: 落在所有件外面的记录 = 谁也没读到它。\n"
        "     （`abstract` 老实写就行 —— 记不记是**下一轮**的事, 不是你的。）\n"
        "   · ⚠️ 但**最后那一截如果明显还没结束**（话没落点、事还在推进）⇒ **不要写它**:\n"
        "     那一截会自动并进下一次, 跟后文连成一件。**只有\"明显\"才留** —— 拿不准就照写。"
    ),
}

#: ⭐ **R1 记录员的条数契约**（3b-2, 2026-09-29）—— 与 `_DOMAIN_CONTRACT` **分开**:
#: `_DOMAIN_CONTRACT` 说的是"这一段该**切成**几件事"（切分权在 R0, 那句话跟着它）;
#: 而 R1 拿到的是**已经切好的骨架**, 它只需**按顺序填**。
#: ⚠️ 两处合一 = 模型会以为自己还有切分权（那正是 3b-1 刚拿走的东西）。
_RECORD_CONTRACT = {
    "bond": (
        "【本段含羁绊剧情（作者单位: 有始有终的完整一段）】\n"
        "→ 骨架里**每一条切片给一行**（`drop` 的除外）—— 某一条是整章的总结时,\n"
        "   就把它写成那**一章**的总结（起因/关键推进/落点都在里面）;\n"
        "   不按时间把每个回合罗列一遍。title 优先用**本章标题**（上方给了）。"
    ),
    "mmt": (
        "【本段类型 = MomoTalk 聊天（无作者单位: 一次覆盖多轮碎聊）】\n"
        "→ 骨架里**每一条切片给一行**（`drop` 的除外; 顺序一一对应）。\n"
        "   · 一条 = 一件可独立复述的事（informative but single）;\n"
        "   · ⚠️ 骨架里那条**本来就是闲聊**的（`abstract` 写着「几轮寒暄」这种）\n"
        "     ⇒ 写 `{\"drop\": true}` 跳过它, 别硬编一条出来;\n"
        "   · 没有值得记的 → `\"episodes\": []` 只在骨架为空时才对（那时也不会问你）。"
    ),
}

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
#: ⚠️ **这里是唯一副本** —— `build_schema("split")` 的**示例**与它下面那段
#: **逐字段说明**都从这几个常量拼出来。为什么非要这样（而不是各写一遍）:
#: `contract/schema.py` 那条纪律 —— **"示例才是形状的来源"**; 而"取值清单 / 说明 /
#: 示例"三处强度不一的时候, 模型只学会示例那个形状（2026-09-20 art 命中率 0/5
#: 就是这么来的）。
#: ⇒ 每个字段**只写一遍**（左对齐、缩进按"逐字段说明"那一份）, 进示例时整体缩 5 格
#: （`textwrap.indent`）—— 两边的**注释列因此也对齐**, 不需要各写一份文案。
#:
#: ⚠️ 与那些 `DigestAction.field_schema`（渲染 `episodes[]` 里的**行形状**）不同:
#: 一行切片只有五个键, 不值得为它造一个 `DigestAction`。
_SPAN_FIELD = (
    '"span": [28, 30],       // ⭐ 这件事覆盖【哪一段】—— 起止**两块事件的编号**\n'
    '                        //（`[28] 【羁绊剧情】` 里的 28）; 这是指**位置**, 不是打分;\n'
    '                        // 区间内的事件**全部**算它覆盖了, 不必逐块列;\n'
    '                        // 两端必须真实存在、且 起 ≤ 止; 拿不准就写宽一点;\n'
    '                        // ⚠️ 两条切片**可以重叠**（同一段事可以同时是两件事）;\n'
    '                        // ⚠️ **只有「没有那一刻的了结」才写 null**（见 state）'
)
_ABSTRACT_FIELD = (
    '"abstract": "…",        // 必填; 一句 ≤%d 字 —— **那件事是什么**;\n'
    '                        // 写法随 state 变（见下面【abstract 怎么写】）' % ABSTRACT_MAX
)
_STATE_FIELD = (
    '"state": "open",        // **省略**（绝大多数, = 这件事跟账无关）/ "open" / "close";\n'
    '                        // open  = 到**这一段结束时还开着**的约定（进她的备忘录）;\n'
    '                        // close = 这一行**了结**了名单里的某条（那时必须写 id）'
)
_ID_FIELD = (
    '"id": "n1",             // 只在 state 有值时出现; 必须是**【还开着的约定】名单里\n'
    '                        // 出现过的编号**（编的会被丢掉）; "close" 时指被了结的那条,\n'
    '                        // "open" 时指**要更正**的那条（后来才知道日期的那种）'
)
_DUE_FIELD = (
    '"due": "2027-05-13",    // 只在 state="open" 时; **哪一天到期** —— 全日期（年-月-日）;\n'
    '                        // 没有明确的一天就别写（不写 = 它不会过期）'
)
#: 逐字段说明（接在示例后面）—— 与示例**同源**
ROW_FIELDS = "\n".join([_SPAN_FIELD, _ABSTRACT_FIELD, _STATE_FIELD,
                        _ID_FIELD, _DUE_FIELD])
STATE_SEMANTICS = (
    "【state 怎么判】只有这件事该写 `open`: **她与老师之间说定的一件事, 还没了结,\n"
    "而且失约会真的伤到谁**（或者只此一次、补不回来）。\n"
    "  ⭐ 跟一件**小事**的界线: **「今天带个东西」办完就没了;「每年都来」说的是\n"
    "     往后一直算数的事。**\n"
    "  ⭐ 再一条: **真重要的事, 人是不会等到翻备忘录才想起来的** ——\n"
    "     所以「答应了」本身不是理由, **分量**才是。\n"
    "  ⭐ **只标「这一段结束时还开着」的** —— 一段之内说了又办完的（出现和消失都在本段）,\n"
    "     **一行都不要标**: 它不需要被带到下一段去。\n"
    "  ⇒ 写成**还没完的那件事**（「答应老师：以后每年都一起过生日」）,\n"
    "     **不是**一句已经想通了的道理。\n"
    "  ⚠️ 反过来说: **当时想通了什么 / 看清了什么, 不写在这儿** —— 那句话说的是\n"
    "     「我已经明白了」, 没有欠着谁, 忘了也不会有代价（下一轮会把它写成一条**看法**收好）。\n"
    "  其余**一律省略 state**（这是绝大多数）。包括这些看似重要的:\n"
    "    · **日常安排 / 顺路的小事**: 「明天把团子带去夏莱」「周六下午两点集合」\n"
    "      「顺路帮我看一眼」「把复印件送过去」—— 那些**补得上、改期就行**;\n"
    "    · **随口一说**: 「下次一起去吧」「有空来玩」「想看你穿那件」;\n"
    "    · **夸奖与安慰**: 「你今天做得很好」「别紧张, 有我在」「你已经很努力了」;\n"
    "    · ⭐ **当时的领悟与触动**: 「原来不是只有被踩在脚下才算我的价值」\n"
    "      「重要的东西不用再埋起来」—— 这些是**那一刻的心情**, 不是欠着的事;\n"
    "      真走出来一条看法, 下一轮自然会把它写成一条「看法」收好。\n"
    "  ⇒ 判据的一句话: **`open` 记的是欠着的债, 不是想通的道理; 而且只有那种\n"
    "     欠着不还就真的伤了人的债。**\n"
    "  ⇒ **一整段里一条 `open` 都没有, 是正常结果**, 不是漏了。"
)
CLOSE_SEMANTICS = (
    "【close 什么时候写】两种情况:\n"
    "  · 这一段里**有一刻**那件事了了（兑现 / 说好了不做了 / 被新的约定盖过）\n"
    "    ⇒ `state`: \"close\" + `id`: 名单里那条的编号 + `span` 指**那一刻**（它就在本段原文里）;\n"
    "  · ⚠️ **没有那一刻**（她等过、那天没人来; 或者那条约定悄悄过期了）\n"
    "    ⇒ `state`: \"close\" + `span`: null + `id`, 而 **`abstract` 就是那条回忆的正文** ——\n"
    "      如实写「老师生日那天没有来」这种; ⛔ 不许编日期、也不许编当时的心情。\n"
    "      ⭐ **这一行还要多给两样**（`title` + `significance`）: 它没有事件、也不经过写正文\n"
    "      的那一轮 ⇒ **标题与「值不值」只能由你给**（缺了它, 这条记忆在回忆册里引不到）。"
)
LATE_DUE_SEMANTICS = (
    "【名单里那条的日期后来才知道】⇒ 再用一行: `state`: \"open\" + `id` + 新的 `due`\n"
    "  （`abstract` 也跟着改就是她本子上新的那句话）。\n"
    "  ⚠️ 这是唯一允许「重提旧条目」的写法; 其余情况**不许**给旧条目再写一行。"
)
ABSTRACT_SEMANTICS = (
    "【abstract 怎么写】这一个字段**有三个去处**:\n"
    "  · 普通的一行 —— 平实描述**发生了什么**（后面有人照着它写回忆的正文; 别写成文学片段,\n"
    "    也别在这儿抒情）;\n"
    "  · `state: \"open\"` —— **就是她带走的那句话**（会被原样抄进她的备忘录）:\n"
    "    写「答应/欠着什么 + 她此刻对它的那点意思」。\n"
    "  例: open →「答应老师：以后每年生日都一起过, 这次我不许自己忘」\n"
    "  · `state: \"close\"` + `span: null` —— **就是那条回忆的正文**（没有那一刻, 只有这句话）。"
)


RECORD_EPISODE = DigestAction(
    name="record_episode",
    phase=PHASE_RECORD,
    role="把本段新增互动浓缩为值得记住的经历条目（一条一对象）。",
    semantics=(
        "何时用: 骨架里**每一条切片**都要给一行（`drop: true` 的那些除外）;\n"
        "怎么改: 第一人称浓缩——起点→关键推进→落点, 保留角色当时的感受与反应;\n"
        "指位置（⭐ **3b-2, 2026-09-29**）: **位置不归你** —— 每条经历覆盖哪一段由 R0 的骨架\n"
        " 决定（`【本段骨架】` 里那一行的区间）, 引擎按**顺序**把你这行并到那条切片上。\n"
        " ⇒ 所以**没有 `span` 这个字段**了; `verbatim` 仍抄 `[28.3]`/`[28.p]` 这类记录行号;\n"
        "不记（`drop`）: **只有一种情况** —— 那一条切片压根没什么可记的（纯寒暄 / 无实质\n"
        " 进展）。⚠️ 骨架里带 ⭐ 的**不许 drop** —— 那是**账目行**（她答应了什么 /\n"
        " 哪一件把一笔账了结了）: 丢了它, 账就不平。\n"
        "禁什么: 不升华成人生感悟; 不记寒暄流水账; 不写旧记忆里已有的事;"
        " 情绪词堆砌但无情节支撑 → 舍弃。"
    ),
    field_schema=(
        '    {  // 一条记录; ⭐ **骨架里有几条切片就给几行, 按顺序对应**（`drop` 的除外;\n'
        '      // ⭐ **也不必都写** —— 不是硬性一一对应）//\n'
        '      // ⚠️ **默认就是"经历", 不用写 `kind`**（2026-09-29）—— 只有**例外**才写:\n'
        '      "kind": "profile",  // 可选; 只在"**玩家画像**"那一条上写\n'
        '                            //（玩家口癖/偏好/一次性个人信息——text 写画像句,\n'
        '                            //  subject 不用填, 引擎固定为 player）//\n'
        '      "drop": true,       // 可选; **这一条切片不记**（只有真的没什么可记时才用:\n'
        '                          // 纯寒暄 / 无实质进展）。⚠️ 骨架里带 ⭐ 的**不许 drop**\n'
        '                          //（账目行: 她答应了什么 / 哪一件把一笔账了结了）;\n'
        '                          // 写了 drop 的行**不用**再给 text/title //\n'
        '      "text": "…",        // 必填（`drop` 行除外）; 单行 ≤300 字;\n'
        '                          // 经历 → 第一人称浓缩, 不流水账;\n'
        '                          // 玩家画像 → 画像句, 如"玩家的生日是\n'
        '                          // 5 月 20 日""玩家总说摸鱼" //\n'
        '      "title": "…",      // 经历必填（画像条目不用）; 8-16 字短标题; 拿不准也给朴素标题 //\n'
        '                          // ⛔ **没有 `span`**（位置由 R0 的骨架定, 不归你）//\n'
        '      "verbatim": ["28.3", "20.p"],   // 可选; 抄**时间线的记录行号**（印象最深的\n'
        '                          // 1~2 句）—— 引擎据此取回**逐字原文**, 你不必抄文本。\n'
        '                          // ⚠️ **只给行号（数组）**; 写成字符串会被忽略 //\n'
        '      "tags": ["…"],     // 必填 1-4 个; 检索导向——未来玩家输入/叙事可能出现的词\n'
        '                          //（人名/地点/物品/动作/话题）; 不含时间词; 从最重要排起 //\n'
        '      "significance": 0~1,  // 行为锚点: 0.9+ 改变认知/极深刻（初遇/告白）;\n'
        '                          // 0.7~0.9 重要约定/特别难忘的日常; <0.7 普通但角色在意的细节;\n'
        '                          // 拿不准往低给 //\n'
        '      "observer": "…",    // 可选; **只有"听别人说的"才填**（写转述者是谁, 如\n'
        '                          // "阿露"）—— 不填 = 你亲历/亲眼所见。\n'
        '                          // 引擎按"有没有 observer"把这条放进「我记得的事」\n'
        '                          // 或「我听说的」，所以**别为了亲历也写一个占位值** //\n'
        '      "emo_int": 0~1,     // 峰值情绪强度: 这条经历里角色情绪最猛的那一下有多猛。\n'
        '                          // 判据 = 时间线里记录后的 (情绪键) + 【本段情绪标尺】\n'
        '                          // （作者为该角色手写的强度语义）。\n'
        '                          // **不是** significance（那个问"改不改变认知"）;\n'
        '                          // 0.9+ 失控/崩溃级; 0.6~0.9 明显起伏; 0.3~0.6 平常情绪;\n'
        '                          // <0.3 近乎无波澜（纯事务性寒暄）。拿不准往低给 //\n'
        '      "emo_span": 0~1,    // 情绪摆幅: 这条经历里情绪**从最低摆到最高跨了多远**。\n'
        '                          // 与 emo_int 分工: 一直很猛但没转折 → int 高 span 低;\n'
        '                          // 先炸后真心笑（爆发→释然）→ 两个都高;\n'
        '                          // 缓慢的起伏（不安→期待→不安）→ span 高 int 低;\n'
        '                          // 全程一个调子 → 0。**必须非负**（是幅度不是方向）//\n'
        '    }'
    ),
    example=(
        '{"text": "老师约我去公园散步, 我紧张但努力答应了; 在长椅上一起喝热茶时,'
        ' 一只流浪猫来蹭老师的裤脚, 我鼓起勇气摸了摸它。回家时老师把没喝完的纸杯'
        '塞给我说「拿着暖手」, 我一路捧着它, 嘴角一直藏着笑。",'
        ' "title": "和老师的公园散步",'
        ' "verbatim": ["33.2", "33.p"],'
        ' "tags": ["公园", "流浪猫", "热茶"],'
        ' "significance": 0.8,'
        ' "emo_int": 0.6, "emo_span": 0.7}'
    ),
)

# ⛔ ~~`ON_MIND_FIELD` / `ON_MIND_SEMANTICS` / `ON_MIND_MAX`~~ **2026-09-29（N4e）随
# `on_mind` 槽退役** —— 用户裁决: *"它太煽情了, 煽情的剧情过去了, 就不必一直耿耿于怀了"*。
# L1 的输出**从此只有 `episodes` 一个键**（心境不是"经历", 也就不该跟 episodes 平级）。
# ⚠️ 将来若真要"她此刻在想什么", 该走 belief（图里、有边、能被召回、会被新经历更新）。

TOUCH = DigestAction(
    name="touch",
    phase=PHASE_UNDERSTAND,
    role="episode 只是再次印证了某条已有认知——连一条边即可。",
    semantics=(
        "何时用: 引擎候选标注'疑似印证'或你判断新经历只是重复已知相处模式;\n"
        "怎么改: 什么都不改——引擎自动把 episode 链到 target 认知;\n"
        "禁什么: 禁止带 patch/content——印证不动原文（改动只发生在 update）。"
    ),
    field_schema=(
        '    {  // 每个 episode 恰好一行; decisions 覆盖全部 episode（引擎结构检查）//\n'
        '      "episode": "m0001",   // 本行处理的 episode id（Round A 产物, 真实 id）//\n'
        '      "decision": "touch",  // touch=印证, 只连边 //\n'
        '      "target": "u0002",    // 必填: 目标认知 id（只能来自下方渲染列表 u0001..）//\n'
        '      "note": "…"           // 可选: 一句印证理由（不进记忆, 仅供审计）//\n'
        '    }'
    ),
    example=(
        '{"episode": "m0001", "decision": "touch", "target": "u0002",'
        ' "note": "又是老师带猫粮来喂, 印证了猫粮约定"}'
    ),
)

UPDATE = DigestAction(
    name="update",
    phase=PHASE_UNDERSTAND,
    role="新经历带来新角度/修正/深化——改写既有认知并连接。",
    semantics=(
        "何时用: 找到同主题认知, 新经历改变/丰富了它;\n"
        "怎么改: patch 部分字段合并改写——只写要变的字段, 空=保留旧值;"
        " 新认知是已有认知的子/超集 → 改宽已有 subject, 不新建;\n"
        " 新 text 应覆盖新旧理解, 重新表述为连贯结论;\n"
        "禁什么: 不复制原文进 text; 不改来源（observer）; 不碰出厂基座(canon 只读)。"
    ),
    field_schema=(
        '    {  // 每个 episode 恰好一行 //\n'
        '      "episode": "m0001",   // 真实 id //\n'
        '      "decision": "update",\n'
        '      "target": "u0002",    // 必填: 目标认知 id //\n'
        '      "patch": {            // 部分字段, 空=保留; 至少一个非空 //\n'
        '        "subject": "…",     // 可选; 认知主体, 不按情境命名（太窄→并入更宽维度）//\n'
        '        "text": "…",        // 可选; 结论式 ≤200 字, 不描述事件 //\n'
        '        "significance": 0~1,// 可选; 行为锚点同 A 轮 //\n'
        '        "tags": ["…"],      // 可选; 检索导向 //\n'
        '        "growth": "…"       // 可选; 认知的成长方向（一句）//\n'
        '      }\n'
        '    }'
    ),
    example=(
        '{"episode": "m0002", "decision": "update", "target": "u0001",'
        ' "patch": {"text": "和老师在一起可以安静相处, 沉默也是自然的——现在连'
        ' 带猫粮喂猫这种小事, 我都敢主动约老师一起做了。"}}'
    ),
)

ADD = DigestAction(
    name="add",
    phase=PHASE_UNDERSTAND,
    role="无同主题认知——新建一条 belief 并连回 episode。",
    semantics=(
        "何时用: 候选里没有同主题认知, 且新经历形成了稳定结论或可复用模式;\n"
        "怎么改: subject 用稳定维度命名（人/关系/互动模式/性格特征）;"
        " text 写结论/模式不写事件 —— ⭐ **反复出现的模式也写成 belief 的模式句**"
        "（没有单独的 kind: 模式 = 她的看法, 见 DESIGN_GRAPH_V4 §5.1/§9-10）;\n"
        "禁什么: 与已有认知同抽象层或更窄 → 应 update 已有而非 add;"
        " 只印证不新增 → 应 touch; 引擎标注'疑似重复'仍 add → 整包拒。"
    ),
    field_schema=(
        '    {  // 每个 episode 恰好一行 //\n'
        '      "episode": "m0001",   // 真实 id //\n'
        '      "decision": "add",\n'
        '      "kind": "belief",     // 只有 belief（模式也写成 belief 的模式句）//\n'
        '      "subject": "…",       // 必填; 稳定维度命名, 不按情境 //\n'
        '      "text": "…",          // 必填; 结论式/模式句, ≤200 字, 不复述事件 //\n'
        '      "tags": ["…"],        // 可选; 检索导向 //\n'
        '      "significance": 0~1,  // 可选; 行为锚点 //\n'
        '      "growth": "…"         // 可选; 成长方向 //\n'
        '    }'
    ),
    example=(
        '{"episode": "m0003", "decision": "add", "kind": "belief",'
        ' "subject": "我对老师的信任",'
        ' "text": "老师是第一个不嫌弃我的人——把猫抱到我腿边这种小事, 都让我'
        ' 觉得自己也被放在心上。", "significance": 0.9}'
    ),
)

DEFAULT_ACTIONS = (RECORD_EPISODE, TOUCH, UPDATE, ADD)


# ============================================================================
# 注册表
# ============================================================================

class DigestRegistry:
    """digest 动作注册表: schema 渲染 + 结构解析（LLM 契约层）。"""

    domain = "digest"

    def __init__(self, actions=DEFAULT_ACTIONS):
        self._actions: dict[str, DigestAction] = {}
        for a in actions:
            self.register(a)

    def register(self, action: DigestAction) -> None:
        if action.name in self._actions:
            raise ValueError(f"digest 动作重复注册: {action.name}")
        self._actions[action.name] = action

    def spec(self, name: str) -> DigestAction | None:
        return self._actions.get(name)

    def actions(self, phase: str | None = None) -> list[DigestAction]:
        out = [a for a in self._actions.values()
               if phase is None or a.phase == phase]
        return sorted(out, key=lambda a: a.name)

    # ------------------------------------------------------------------
    # schema 渲染（prompt 的 {{digest_schema}} 占位; 含内联约束 + 语义 + 范例）
    # ------------------------------------------------------------------

    def build_schema(self, phase: str, *, include_examples: bool = True,
                     domain: str = "mmt", chapter_count: int = 1) -> str:
        """渲染某一轮的输出格式文本。

        record:     {"episodes": [...]}
        understand: {"decisions": [...], "affection_exp_delta": n}

        `domain`（2026-09-20, 用户裁决）—— **粒度跟着"作者单位"走**:

        | 段 | 边界 | 该切成几件事（**R0 的活**） |
        |---|---|---|
        | `bond` | `vn_enter`…`vn_exit`（**引擎已知**, 一章 = 作者写的有始有终的一段） | **每章恰好 1 件** = 这一章的总结 |
        | `mmt` | 无作者单位（一次 digest 覆盖多轮碎聊） | 一件一件切, **必须覆盖全部**（连闲聊自成一件） |

        ⚠️ **3b-2（2026-09-29）起 `record` 相位用的是另一份**（`_RECORD_CONTRACT`）:
        R1 只填骨架, 条数不归它。本表说的是**切分**（`split` 相位）。

        用户原话: *"真正的 episode 一个就可以定下，需要被切分的是长篇 MMT 等；
        episode 应该 **informative but single**，belief 则是 **brief but descriptive**"*。
        段类型与**章分组**由 `digest._segment_domain` 从 marker **派生**（不落库）。

        `chapter_count` > 1 = 这一段的窗口里有**多章**（水位被清 / 重跑时必然如此）——
        契约要写成"**每章各 1 条**", 否则两章会被压成一条。
        """
        if phase == PHASE_SPLIT:
            # ⭐ **本段类型那段契约与 R1 共用一份**（`_DOMAIN_CONTRACT`）—— 它是
            # "这一段该切成几件事"的唯一说明, 而**切分权在 R0** ⇒ 它必须在这儿出现。
            contract = _DOMAIN_CONTRACT.get(domain, _DOMAIN_CONTRACT["mmt"])
            if domain == "bond" and chapter_count > 1:
                contract = contract.replace(
                    "→ **这一段恰好 1 件**（它就是**这一段经历过的事**）:",
                    f"→ 本段含 **{chapter_count} 章** —— **每章各恰好 1 件**"
                    f"（共 {chapter_count} 条切片）, 每条就是**它那一章的总结**:")
            # 示例由字段常量拼（**不是另抄一份文案** —— 见 `_SPAN_FIELD` 那段注释）:
            # 整体缩 5 格就与"逐字段说明"那一份的注释列对齐
            example = "\n".join([
                "    {  // 一件事 = 一行; 顺序 = 时间顺序 //",
                textwrap.indent(ROW_FIELDS, " " * 5),
                "    }",
            ])
            return "\n".join([
                OUTPUT_DISCIPLINE,
                contract,
                "",
                '    {"segments": [',
                example,
                "    ]}",
                "",
                "  · **切成几件事**: 一件 = 一场戏（一次见面 / 一段连续聊天）——\n"
                "    换了话题 / 换了人 / 换了场景都**还是**同一件事（那只是它的过程）;\n"
                "    ⚠️ **别切太碎** —— 一场戏切成好几件, 那是流水账, 不是记忆;\n"
                "    ⚠️ 但也**别留空档** —— 没被任何一件覆盖的记录, 下一轮读不到它;\n"
                "    ⚠️ **最后那一截明显没结束 ⇒ 不要写它**（留给下一次, 它会跟后文连成一件）;\n"
                "  · `span` 只写**事件头编号**（`[28.0]` 那种记录行号不用管）;\n"
                "  · **一行一件事** —— 同一件事既了结旧的、又新说定一件 ⇒ 写**两行**\n"
                "    （同一个 span 出现两次, 那没关系）;\n"
                "  · 本段确实没有内容事件 → `\"segments\": []`（合法, 但很少见）。",
                "",
                "【逐字段】",
                ROW_FIELDS,
                "",
                STATE_SEMANTICS,
                "",
                CLOSE_SEMANTICS,
                "",
                LATE_DUE_SEMANTICS,
                "",
                ABSTRACT_SEMANTICS,
            ])

        if phase == PHASE_RECORD:
            # ⭐ **R1 的条数契约 = "骨架有几条就填几条"**（3b-2, 2026-09-29）——
            # 它**不再是**"一章恰好 1 条 / MMT 0~5 条": 那是**切分**的契约（归 R0）。
            # ⚠️ 这两句**故意不复用 `_DOMAIN_CONTRACT`**: 后者说的是"怎么切",
            # 而 R1 拿到的是**已经切好的骨架**, 它只需按顺序填 —— 两句话术不同。
            contract = _RECORD_CONTRACT.get(domain, _RECORD_CONTRACT["mmt"])
            lines = [
                OUTPUT_DISCIPLINE,
                contract,
                "",
                '    {"episodes": [',
            ]
            a = self.spec("record_episode")
            lines.append(a.field_schema)
            lines.extend(["    ],",
                          '     "affection_exp_delta": 0  // ⭐ **整段**的好感净变化 -100~100（int）;',
                          '                                // 平淡寒暄 0~10 · 有意义的共同经历 30~60 ·',
                          '                                // 重要羁绊时刻 80~100;',
                          '                                // **负值 = 关系恶化**（被伤到/失望/决裂）;',
                          '                                // 判据 = **她对你的亲近感这一段的净变化**,',
                          '                                // 不是"这段剧情好不好"; 拿不准给 0',
                          "    }",
                          "",
                          f"【record_episode 释义】{a.role}",
                          "语义:", a.semantics])
            if include_examples and a.example:
                lines.extend(["", "【范例】", a.example])
            return "\n".join(lines)

        if phase == PHASE_UNDERSTAND:
            actions = self.actions(PHASE_UNDERSTAND)
            lines = [
                OUTPUT_DISCIPLINE,
                '    {"decisions": [',
            ]
            for i, a in enumerate(actions):
                lines.append(a.field_schema)
                if i < len(actions) - 1:
                    lines.append("    , // ——或—— //")
            lines.extend([
                "    ],",
                '     "links": [ // 可选; 额外的边——把**上面列表里已有**的两条连起来;',
                '               // 只这三种 rel, 两端都必须是列表里出现过的本地 id;',
                '               // 没有就写 []（或省略这个键）//',
                '        {"from": "u0007", "rel": "supports", "to": "u0002"},',
                '        {"from": "u0009", "rel": "evolved_from", "to": "u0007"}',
                "     ],",
                "    }",
                "",
                "decisions 规则: 每个 episode 恰好一行; 必须覆盖全部 episode;",
                "id 只能引用上方渲染列表里出现的 id（编造 id → 整包拒）;",
                "引擎候选标注'疑似印证/疑似重复'时必须遵守（印证→touch, 重复→update）。",
                "",
                "links 规则（**可选的补充边**, 别拿它当主力）:",
                "  supports      —— 「**这条看法**支撑**那条看法**」（两端都是看法;",
                "                    「经历支撑看法」那种由决策表的 touch 写, 别在这里重复）;",
                "  contradicts   —— 「这两条互相打架」（无向: 写一次就够）;",
                "  evolved_from  —— 「这条是新的, 它把旧的盖过去了」（新 → 旧）;",
                "  ⚠️ 方向别写反（`from` 是新/被支撑的那一头）; 两端都不能是本轮新建的条目",
                "    （列表是这一轮**开始前**的样子 —— 新建的下一轮才连得上）。",
                "",
                "两层写法（别混, 2026-09-20 用户定）:",
                "  episode = **informative but single**（信息量足, 但只讲一件事）;",
                "  认知（belief/experience）= **brief but descriptive**（简短, 但描述性 ——",
                "  写的是模式/结论/看法, 不是事件; 不要复述剧情）;",
            ])
            if include_examples:
                lines.append("")
                for a in actions:
                    lines.extend([f"【{a.name} 释义】{a.role}", "语义:", a.semantics,
                                  "【范例】", a.example, ""])
            return "\n".join(lines)

        if phase == PHASE_ATTRIBUTE:
            return "\n".join([
                OUTPUT_DISCIPLINE,
                '    {"attributions": [ // 没有可归属的就写 [] //',
                '        {"action": "attach", "entity": "c0001", "hint": "老师",',
                '         "nodes": ["u0001", "u0003"]},',
                '        {"action": "new_entity", "name": "小玉", "aliases": ["tama"],',
                '         "reason": "她第一次出场, 之后还会来", "nodes": ["u0002"]},',
                '        {"action": "rewrite", "entity": "c0001",',
                '         "text": "他是第一个不嫌弃我的人。",',
                '         "state": ["今天戴了眼镜"]}',
                "    ]}",
                "",
                "三件事（一行一件）:",
                "  attach     —— 把【本轮新节点】挂到某个对象上（**有边 = 归好了**）:",
                "    entity —— 候选表里的编号（c0001…）;",
                "    hint   —— **你自己**从这条记忆里认出来的那个自然称呼（从它的正文 / 名字"
                "里认, 别去猜; 写了引擎会顺手记进别名, 认不出就省略）;",
                "    nodes  —— 要挂上去的节点编号（u0001…, 至少一个）。",
                "  new_entity —— 候选表里**确实没有**的人/地方/东西:",
                "    name   —— 它的名字（必填）; aliases 可选;",
                "    reason —— **为什么值得建**（必填, 一句话）;",
                "    nodes  —— 顺手把这批节点挂上去（可选）。",
                "  rewrite    —— 改写某个对象的【当前载荷】（立场 / 现状）:",
                "    entity —— 候选表里的编号;",
                "    text   —— 立场（她的看法, 慢变量; 空 = 保留原文）;",
                "    state  —— 现状（物理状况清单; 空 = 保留）。",
                "",
                "规则:",
                "  ⚠️ 候选表里**已经有**的别新建 —— 同一个人/地方/东西只能有一个对象;",
                "  ⚠️ 只挂**本轮新节点**（u 编号只在本轮有效, 别引用别处的）;",
                "  ⚠️ **判不出来就别挂**（宁缺勿错: 没边 ≠ 错, 挂错才要花成本修）;",
                "  ⚠️ `rewrite` 是**增量改写**: state 只给**变了的那几行**（原样照抄其余的）,"
                " 立场重写一次就够, 没变就别写这一行;",
                "  ⚠️ 立场（text）没变就别动 —— 它是慢变量。",
            ])

        if phase == PHASE_GROUP:
            return "\n".join([
                OUTPUT_DISCIPLINE,
                "    {",
                '     "attach": [ // 这些块属于**已有的类**（没有就写 []）;',
                '        {"block": "b1", "group": "那片苔藓"}',
                "     ],",
                '     "new": [ // 这些块是一个**新的类**（没有就写 []）;',
                '        {"block": "b2", "title": "模型店的那些事"}',
                "     ],",
                '     "merge": [ // 这两个名字**说的是同一个类**（没有就写 []）;',
                '        {"from": "苔藓的事", "into": "那片苔藓"}',
                "     ]",
                "    }",
                "",
                "三个键**都要在**（没有就写空数组 []）。",
                "⭐ **每个块恰好出现在 attach 或 new 里一个** —— 发下来的每个块都必须有归属;",
                "   漏一个块 = 整包被拒（引擎会带着「你漏了 b2」再问一次）。",
                "",
                "attach 一行 —— 这一块说的就是**已有的某个类**:",
                "  block —— 上面「还没归类的块」的把手（b1…）;",
                "  group —— 「已有的类」里那个类的名字（**照抄**它, 不要改写）;",
                "            名单里没有的名字不要写（写了会被丢掉, 那块留到下次）。",
                "",
                "new 一行 —— 这一块是一个**新的类**:",
                "  block —— 块的把手;",
                "  title —— 你给这个类起的名字（**2~16 字**, 短一点好）:",
                "            写「这类事的名字」, 不是某一件具体事的名字;",
                "            要**具体**（含一个具体的人 / 地方 / 东西）, 不要抽象类别词 ——",
                '            ✗「日常」「回忆」「和老师的相处」 ✓「那片苔藓」「模型店的那些事」。',
                "",
                "merge 一行 —— 库里**两个名字说的是同一个类**, 把它们并成一个:",
                "  from —— 被并掉的**那个名字**（以后不再用）;",
                "  into —— **留下来的**那个名字（成员都会挂到它下面）;",
                "  ⚠️ 只能并【可能重复的类】里出现过的那些名字;",
                "  ⚠️ **名字是地址**: 并掉一个名字 = 那个名字以后指不到东西了 ——",
                "     除非两个类确实是同一类, 否则别并（拿不准就不并, 空着最安全）。",
                "",
                "规则:",
                "  ⚠️ **能归已有的类就别新建** —— 同一个类裂成两个名字是这一步最贵的错"
                "（引擎会把同名的并回去, 但**名字不同、意思相同**的它认不出来）;",
                "  ⚠️ 块是**她自己觉得像**的几件事连起来的 —— 你**不用再判一次像不像**,",
                "     你的活是**给它们一个共同的名字**（或者认出它属于已有的哪个名字）;",
                "  ⚠️ 头里写着「**1 条**」的那种块 = **她把它连到了某个已有的类**（那一行里已经写出"
                "是哪个类）:",
                "     通常就是 attach 到那个类; **只有它明显不是那一类**时, 才给它起个新名字。",
                "  ⚠️ 其余块的类名下面至少要能站住**两件事**（引擎只把有同伴的块发给你, 所以每块都能起）;",
                "  ⚠️ 不要复述事件 —— 类的名字不是这次发生了什么。",
            ])

        raise ValueError(f"未知 digest phase: {phase!r}")

    # ------------------------------------------------------------------
    # 解析（结构校验; 引用级/图语义在引擎执行层）
    # ------------------------------------------------------------------

    def parse_round_a(self, raw: Any, *, seq_set: set[int] | None = None
                      ) -> tuple[list[dict], ValidationResult]:
        """Round A: `{"episodes": [...]}` → 规范化条目列表。

        `seq_set`（T14）: 本段**事件 seq 全集**——`event_seq` / `verbatim` 索引
        的 ⊆ 校验基准（与 `parse_round_b` 的 `episode_ids` 同思路:
        引用纪律在 parse 层, 不在 prompt 层）。`None` = 不校验（老调用方/单测）。

        ⛔ ~~`on_mind_out`~~ **2026-09-29（N4e）随 `on_mind` 槽退役** ——
        它从前是这个 parse 的第二个产物（用列表传出而不改返回签名的手法）。
        """
        errors: list[str] = []
        warnings: list[str] = []
        #: ⭐ D1（2026-09-29）: "真的丢了东西"的那几条 warning（见 `ValidationResult.drops`）
        drops: list[str] = []
        if not isinstance(raw, dict):
            return [], ValidationResult(errors=("Round A 输出必须是 JSON 对象",))
        raw_eps = raw.get("episodes")
        if not isinstance(raw_eps, list):
            return [], ValidationResult(errors=("episodes 必须是数组",))
        if len(raw_eps) > MAX_EPISODES:
            errors.append(f"episodes 超过 {MAX_EPISODES} 条（超出的丢弃）")
            raw_eps = raw_eps[:MAX_EPISODES]
        out: list[dict] = []
        for i, e in enumerate(raw_eps):
            # ⭐ **`drop`**（3b-2, 2026-09-29）: 她对**这一条切片**说"不记"。
            # 只有一种合法用途: 那条切片压根没什么可记的（纯寒暄 / 无实质进展）。
            # ⚠️ "骨架里带 ⭐ 的不许 drop" 是**提示词纪律**, 引擎侧不做硬拦 ——
            # 引擎不知道哪条带 ⭐（那是 `keep` 的语义, 属于 R0 的产出）;
            # 真丢了约定由 3b-3 的缺口账兜（走已有的 `digest_gap` 通路）。
            if isinstance(e, dict) and e.get("drop") is True:
                out.append({"drop": True})
                continue
            item, item_errs, item_warns = _clean_episode(e, i, seq_set, drops)
            errors.extend(item_errs)
            warnings.extend(item_warns)
            if item is not None:
                out.append(item)
        return out, ValidationResult(tuple(errors), tuple(warnings), tuple(drops))

    def parse_split(self, raw: Any, *, seq_set: set[int] | None = None,
                    note_ids: set[str] | None = None,
                    overdue_ids: set[str] | None = None,
                    ) -> tuple[list[dict], ValidationResult]:
        """R0 切分: `{"segments": [{"span", "abstract", "state"?, "id"?, "due"?}, …]}`。

        ⭐ **只做形状校验**（键在不在 / 区间合不合法 / 真值表配不配 / `id` 在不在名单里）——
        "这段区间里到底有什么"是**世界的事**, 归引擎（`seq_set` 只用来查端点存在性）。

        ## 一行的合法形状只有五种（`state` × `span` × `id`）

        | `state` | `span` | `id` | 含义 |
        |---|---|---|---|
        | 省略 | 必填 | 不许 | 与账无关的一件事（**绝大多数**） |
        | `open` | 必填 | 不许 | 新建: 到本段结束还开着的约定 |
        | `open` | 必填 | 必填 | 更正: 那条约定后来才知道日期（`due` / `abstract` 变） |
        | `close` | 必填 | 必填 | 这一行**了结**了名单里那条 |
        | `close` | **null** | 必填 | **没有那一刻**的了结（`abstract` 就是那条回忆的正文） |

        ## 坏行分两档（**别混**）

        · **收下但改写 + 告警**（内容不丢 ⇒ 不 `_drop`）:
          `state` 值不在词表（按"省略"收）· `close` 有 `span` 但 `id` 缺失/不在名单
          （降级成普通一行 —— 那一刻照样是记忆）· `open` 给了 `id` 但不在名单
          （同上; ⛔ **不新建**, 免得把同一条约定记两遍）· `due` 不是全日期（当没期限）。
        · **真的丢**（`_drop`, 进 D1 台账）: 沿用今天那些（端点不在时间线 / 起止反 /
          形状错 / `abstract` 缺或空 / 同 span + 同 abstract 的重复行）。
        · **没有区间那几行的坏形状**: 走 `warnings`（**不进 `drops`**）——
          `_drop` 的判据是"有没有内容离开过**库**", 而 `span: null` 的行本来就没有库内容
          （它是 R0 凭引擎的资格位写出来的一句）:
          `span: null` 却不是 `close` · `close` + `null` 但 `id` 缺失/不在名单 ·
          `close` + `null` 而**引擎没发资格位**（`overdue_ids` 里没有它）。

        Args:
            seq_set: 本段**可寻址事件 seq 全集**（端点 ⊆ 它）。`None` = 不校验。
            note_ids: 本轮料里印出来的**还开着的约定**编号（`id` 的闭集）。
                `None` = 不校验（老调用方 / 单测）。
            overdue_ids: 引擎判定的**超期**条目（= 允许 `span: null` 的资格位）。
                `None` = 不限制（老调用方 / 单测）。

        Returns: `(segments, ValidationResult)` —— 每条 = 引擎要的那一行:
        `{"span": [起, 止] | None, "abstract": "…", "state"?: …, "id"?: …, "due"?: …}`。
        ⚠️ 引擎随后把 `span` 展开成 `event_seq` 并**就地改写这批字典**（R1 在同一批
        字典上填正文）—— 所以这里**不 pop `span`**, 它是这一行的身份。
        """
        errors: list[str] = []
        warnings: list[str] = []
        #: ⭐ D1: "真的丢了东西"的那几条 warning（见 `ValidationResult.drops`）
        drops: list[str] = []
        if not isinstance(raw, dict):
            return [], ValidationResult(errors=("切分轮输出必须是 JSON 对象",))
        raw_segs = raw.get("segments")
        if not isinstance(raw_segs, list):
            return [], ValidationResult(errors=("segments 必须是数组",))
        if len(raw_segs) > MAX_SEGMENTS:
            warnings.append(f"segments 给了 {len(raw_segs)} 条（> {MAX_SEGMENTS}）——"
                            f"超出的丢弃; 一段里切成这么多件 = 流水账, 不是记忆")
            raw_segs = raw_segs[:MAX_SEGMENTS]

        out: list[dict] = []
        #: 同 span + 同 abstract 才算重复（⚠️ **同 span 不同行是合法的** —— 出+进两行,
        #: 或同一个时刻长出的两条记忆; 2026-10-05 起不再"完全一样就丢"）
        seen: set[tuple[int, int, str]] = set()
        for i, seg in enumerate(raw_segs):
            if not isinstance(seg, dict):
                errors.append(f"segments[{i}] 必须是对象")
                continue
            label = f"segments[{i}]"
            # ── 账目三键（后面的分档都靠它） ──
            state_raw = seg.get("state")
            if state_raw is None:
                state = ""
            elif isinstance(state_raw, str) and state_raw.strip() in STATE_VALUES:
                state = state_raw.strip()
            else:
                warnings.append(f"{label}.state 不是 {'/'.join(STATE_VALUES)} 之一"
                                f"（{state_raw!r}）——按「无账目」收下（这一行的内容不丢）")
                state = ""
            nid = str(seg.get("id") or "").strip()
            id_given = bool(nid)
            # ⚠️ 闭集：名单没给就不校验（老调用方 / 单测）; 给了就必须命中
            id_ok = id_given and (note_ids is None or nid in note_ids)

            # ── span：可以是 null —— **只对 close 合法** ──
            if seg.get("span") is None:
                if state != "close":
                    warnings.append(f"{label} 的 span 是 null, 但它不是 close"
                                    f"（没有那一刻、又没有账目 ⇒ 这一行什么都没留下）——丢弃")
                    continue
                if not id_ok:
                    warnings.append(f"{label} 是 close + span=null, 但 id {nid!r} "
                                    f"不在【还开着的约定】名单里 —— 丢弃")
                    continue
                if overdue_ids is not None and nid not in overdue_ids:
                    warnings.append(f"{label} 是 close + span=null, 但引擎**没有**判定 "
                                    f"{nid!r} 超期（资格位没发）—— 丢弃"
                                    f"（凭空造一条「没发生过」的记忆不行）")
                    continue
                span: list[int] | None = None
            else:
                # 区间 —— **复用 `_clean_span`**（端点存在性 / 起止反 / >2 端点 / 记录级编号
                # 那一整套规矩与 R1 逐字相同; 坏的那条它已经 `_drop` 过了）
                span = _clean_span(seg.get("span"), seq_set, label=f"{label}.span",
                                   warnings=warnings, drops=drops)
                if span is None:
                    continue

            abstract = seg.get("abstract")
            if not isinstance(abstract, str) or not abstract.strip():
                text = (f"{label} 缺 abstract —— 丢弃"
                        if span is not None else
                        f"{label}（close + span=null）缺 abstract —— 丢弃: "
                        f"那一行的 abstract **就是**那条回忆的正文, 没有它这一行什么都不剩")
                if span is not None:
                    _drop(warnings, drops, text)
                else:
                    warnings.append(text)
                continue
            abstract = abstract.strip()

            if span is not None:
                key = (span[0], span[1], abstract)
                if key in seen:
                    _drop(warnings, drops,
                          f"{label} 与前面那条**完全一样**（同 span 同 abstract）——丢弃")
                    continue
                seen.add(key)
                cap = ABSTRACT_MAX
            else:
                cap = ABSTRACT_MAX_FREEFORM          # 它就是那条回忆的正文
            if len(abstract) > cap:
                # 软上限: 收下但告警（它不是形状错 —— 超了只说明她写得长）
                warnings.append(f"{label}.abstract {len(abstract)} 字 > {cap}（收下但请写短）")

            # ── id 配不上: close / 更正都做不成 ⇒ 降级成普通一行（⛔ 不新建） ──
            # ⚠️ **`open` 且没给 id 是合法的**（新建）—— 只有"给了 id 却配不上"才降级。
            if (state == "close" and not id_ok) or \
                    (state == "open" and id_given and not id_ok):
                what = "close" if state == "close" else "更正"
                warnings.append(f"{label} 想做「{what}」, 但 id {nid!r} 不在"
                                f"【还开着的约定】名单里 —— 这一行按「无账目」收下"
                                f"（那一刻照样记; ⛔ 不新建, 免得同一条约定记两遍）")
                state = ""

            row: dict = {"span": list(span) if span is not None else None,
                         "abstract": abstract}
            if state:
                row["state"] = state
                if id_given:
                    # ⚠️ **新建的 `open` 不带 `id`**（缺键 = 新建; 只有"更正"才带）
                    row["id"] = nid
            # ⭐ **无区间那一行还带 `title` + `significance`**（L7, 2026-10-05）——
            # 它没有事件、也不经过写正文的那一轮（R1 看不到它）⇒ 那条记忆的**标题**与
            # "值不值"只能由 R0 给（§1.1 真值表的"另外必填"列）。
            # ⚠️ 缺了**不拒**: 一条"没有那一刻"的记忆比一个没标题重得多 ⇒ 收下 + 告警,
            # 标题退回 `abstract` 前 12 字（⛔ 不编一个漂亮名字）。
            if span is None:
                title = str(seg.get("title") or "").strip()
                if not title:
                    warnings.append(f"{label} 是无区间那一行, 但没给 `title` —— "
                                    f"退回用 abstract 前 12 字（那条记忆在视图里就引不到）")
                row["title"] = title or abstract[:12]
                sig = seg.get("significance")
                if isinstance(sig, bool) or not isinstance(sig, (int, float)):
                    if sig is not None:
                        warnings.append(f"{label}.significance 不是数字 —— 取 0.5")
                    row["significance"] = 0.5
                else:
                    row["significance"] = max(0.0, min(1.0, float(sig)))
            # `due` 只跟新建的 `open`: ⚠️ **判不了就退化成"没有期限"**（不告警 ——
            # 契约已经写明"全日期"; 引擎判不了 = 它永不过期, 宁缺勿错。
            # ⛔ 绝不替她滚到明年、也绝不替她猜）
            if state == "open" and seg.get("due") is not None:
                due = str(seg.get("due") or "").strip()
                if due and is_full_date(due):
                    row["due"] = due
            out.append(row)

        if not out and raw_segs:
            warnings.append("这一包**一条切片都没留下**（全部被剔除）——"
                            "本段不会有任何记忆, 看上面的 `drops`")
        return out, ValidationResult(tuple(errors), tuple(warnings), tuple(drops))

    def parse_group(self, raw: Any, *, block_ids: set[str]
                    ) -> tuple[list[dict], ValidationResult]:
        """L2-a 分群（N7）: `{"attach": […], "new": […]}` → 归一化行。

        **只做形状 + 闭集校验**（键在不在 / 是不是数组 / 必填 / 块的把手来自本轮名单 /
        ⭐ **每个块恰好一次归属**）。"那个类名存不存在"是**世界校验** ⇒ 归执行器
        （`groups.apply_groups`）**剔掉 + 记账、不拒整包** —— 同 `parse_attribution` 的口径:
        形状错重试有用, "看错了世界"重试大概率还是错。

        ⚠️ **覆盖是硬错**（同 `parse_round_b` 的"必须覆盖全部 episode"）: 漏一个块 =
        那几件事白连了一次, 而"漏"正是"没按契约说话" —— 带反馈重试一次通常就好。
        （调用方还有一道安全网: 这一步整体失败**只回滚它自己**, 不连累整段 —— 见 `digest_segment`。）

        Returns: `(rows, ValidationResult)`; 行形状

            `{"action": "attach", "block": "b1", "group": "那片苔藓"}`
            `{"action": "new", "block": "b2", "title": "模型店的那些事"}`
            `{"action": "merge", "from": "苔藓的事", "into": "那片苔藓"}`
        """
        errors: list[str] = []
        warnings: list[str] = []
        if not isinstance(raw, dict):
            return [], ValidationResult(errors=("分群轮输出必须是 JSON 对象",))

        out: list[dict] = []
        seen: set[str] = set()
        for key in ("attach", "new"):
            if key not in raw:
                errors.append(f"缺键 {key!r}（两个键都要在, 没有就写空数组）")
                continue
            rows = raw.get(key)
            if not isinstance(rows, list):
                errors.append(f"{key} 必须是数组")
                continue
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    errors.append(f"{key}[{i}] 必须是对象")
                    continue
                block = row.get("block")
                if not isinstance(block, str) or not block.strip():
                    errors.append(f"{key}[{i}] 缺 block（块的把手 b1…）")
                    continue
                block = block.strip()
                if block not in block_ids:
                    errors.append(f"{key}[{i}] 块 {block!r} 不在本轮名单里"
                                  f"（只有 {', '.join(sorted(block_ids))}）")
                    continue
                if block in seen:
                    warnings.append(f"{key}[{i}] 块 {block!r} 重复（只留第一条）")
                    continue
                if key == "attach":
                    name = row.get("group")
                    if not isinstance(name, str) or not name.strip():
                        errors.append(f"attach[{i}] 缺 group（已有类的名字）")
                        continue
                    seen.add(block)
                    out.append({"action": "attach", "block": block,
                                "group": name.strip()})
                    continue
                title = row.get("title")
                if not isinstance(title, str) or not title.strip():
                    errors.append(f"new[{i}] 缺 title（这个类叫什么）")
                    continue
                title = title.strip()
                if len(title) > GROUP_TITLE_MAX:
                    warnings.append(f"new[{i}] 类名偏长（{len(title)} 字）: {title!r}")
                seen.add(block)
                out.append({"action": "new", "block": block, "title": title})

        missing = sorted(b for b in block_ids if b not in seen)
        if missing:
            errors.append("这些块没有归属: " + ", ".join(missing)
                          + "（每个块都要出现在 attach 或 new 里, 一个都不能漏）")

        # —— `merge`（N7b）: 两个类名 —— ⚠️ "这对名字在不在候选里" 是**世界校验**,
        # 归执行器（`groups.apply_merges`）: 名字解析要归一, 而契约层不依赖 core。
        if "merge" not in raw:
            errors.append("缺键 'merge'（三个键都要在, 没有就写空数组）")
        else:
            rows = raw.get("merge")
            if not isinstance(rows, list):
                errors.append("merge 必须是数组")
            else:
                used: set[str] = set()
                for i, row in enumerate(rows):
                    if not isinstance(row, dict):
                        errors.append(f"merge[{i}] 必须是对象")
                        continue
                    src, dst = row.get("from"), row.get("into")
                    if not _nonempty_str(src) or not _nonempty_str(dst):
                        errors.append(f"merge[{i}] 需要 from 与 into（两个类名）")
                        continue
                    src, dst = str(src).strip(), str(dst).strip()
                    if src == dst:
                        errors.append(f"merge[{i}] from 与 into 是同一个类名: {src!r}")
                        continue
                    if src in used or dst in used:
                        errors.append(f"merge[{i}] 一个类一轮只能并一次: {src!r} / {dst!r}")
                        continue
                    used.add(src)
                    used.add(dst)
                    out.append({"action": "merge", "from": src, "into": dst})
        return out, ValidationResult(tuple(errors), tuple(warnings))

    def parse_attribution(self, raw: Any, *, entity_ids: set[str],
                          node_ids: set[str]) -> tuple[list[dict], ValidationResult]:
        """R3 归属轮: `{"attributions": […]}` → 归一化行（形状见 `apply_attribution`）。

        三种行::

            {"action": "attach",     "entity": "c0001", "hint": "老师", "nodes": ["u0001"]}
            {"action": "new_entity", "name": "小玉", "aliases": ["tama"],
                                     "reason": "…", "nodes": ["u0002"]}
            {"action": "rewrite",    "entity": "c0001", "text": "…", "state": ["…"]}

        **形状错与引用错都拒整包**（同 Round B 的口径 —— 这里的 id 是引擎**渲染出来的闭集**,
        指错就是"没读输入"）; 而"这个对象该不该存在""这条归得对不对"是**判断**, 引擎不管。

        Args:
            entity_ids: 候选表里的本地 id 集（`c0001..`）
            node_ids: 本轮新节点的本地 id 集（`u0001..`）

        ⚠️ `hint` / `aliases` / `reason` 的**空值口径**: `hint` 与 `aliases` 空 = 不写
        （可选）; `reason` 空 ⇒ **拒**（它是 `new_entity` 的准入门槛, §3.0）。
        `rewrite` 的 `text`/`state` 都空 ⇒ **拒**（那一行什么都没说 = 白跑一趟）。
        """
        errors: list[str] = []
        warnings: list[str] = []
        if not isinstance(raw, dict):
            return [], ValidationResult(errors=("归属轮输出必须是 JSON 对象",))
        rows = raw.get("attributions")
        if rows is None:
            # 空包是合法的（这一段没有可归属的）—— 但**缺键**与"写空数组"要分得开
            errors.append("缺键 'attributions'（没有可归属的就写 []）")
            return [], ValidationResult(tuple(errors))
        if not isinstance(rows, list):
            return [], ValidationResult(errors=("attributions 必须是数组",))

        out: list[dict] = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"attributions[{i}] 必须是对象")
                continue
            action = str(row.get("action", "")).strip()
            if action == "attach":
                item = _clean_attach(row, i, entity_ids, node_ids, errors)
            elif action == "new_entity":
                item = _clean_new_entity(row, i, node_ids, errors, warnings)
            elif action == "rewrite":
                item = _clean_rewrite(row, i, entity_ids, errors)
            else:
                errors.append(f"attributions[{i}].action 非法: {action!r}"
                              "（attach|new_entity|rewrite）")
                continue
            if item is not None:
                out.append(item)
        return out, ValidationResult(tuple(errors), tuple(warnings))

    def parse_round_b(self, raw: Any, *, episode_ids: set[str],
                      target_ids: set[str],
                      link_ids: set[str] | None = None,
                      ) -> tuple[list[dict], ValidationResult]:
        """Round B: `{"decisions": [...], "links": [...], "affection_exp_delta": n}`。

        episode_ids: 本轮 Round A 产出的真实 episode id 集（引用检查）。
        target_ids: **可被 `touch`/`update` 的**本地 id 集（u0001..; 只有看法）。
        link_ids: **可出现在 `links` 两端的**本地 id 集。⏸ 2026-09-29 承诺退图之后,
            它与 `target_ids` 实际同集（渲染列表里只剩看法）—— 参数**留着**: 它是
            "可连接的端点"这件通用事, 而调用方今天传的是渲染列表的全集。
            `None` → 退化成 `target_ids`（老调用方/单测不必改）。

        ⚠️ **`must_touch` 参数已删**（2026-09-15 T17）: 它曾是"引擎候选 ≥ 阈值 →
        该 episode 禁 `add`"的**结构强制**，而那个阈值从未标定过、实测两模型下
        候选皆 6/6 全越线 → **新认知永远长不出来**（DESIGN_WIKI_V3 Q11/Q31/Q32
        已裁"取消结构强制, 候选仅作提示"）。现在候选只是输入里的一行提示,
        判 add/touch/update 全归 LLM, **引擎不设闸门**。
        """
        if link_ids is None:
            link_ids = target_ids
        errors: list[str] = []
        warnings: list[str] = []
        if not isinstance(raw, dict):
            return [], ValidationResult(errors=("Round B 输出必须是 JSON 对象",))
        rows = raw.get("decisions")
        if not isinstance(rows, list):
            return [], ValidationResult(errors=("decisions 必须是数组",))
        seen: set[str] = set()
        out: list[dict] = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"decisions[{i}] 必须是对象")
                continue
            ep = str(row.get("episode", "")).strip()
            if ep not in episode_ids:
                errors.append(f"decisions[{i}].episode 不在本轮 episode 集内: {ep!r}")
                continue
            decision = str(row.get("decision", "")).strip()
            if decision not in DECISIONS:
                errors.append(f"decisions[{i}].decision 非法: {decision!r}（touch|update|add）")
                continue
            seen.add(ep)
            item: dict = {"episode": ep, "decision": decision}
            if decision in ("touch", "update"):
                target = str(row.get("target", "")).strip()
                if not target:
                    errors.append(f"decisions[{i}]: {decision} 必须填 target")
                    continue
                if target not in target_ids:
                    errors.append(f"decisions[{i}].target 不在可 touch/update 的列表内"
                                  f"（只有看法）: {target!r}")
                    continue
                item["target"] = target
                if decision == "touch":
                    note = row.get("note")
                    if isinstance(note, str) and note.strip():
                        item["note"] = note.strip()
                else:  # update
                    patch = row.get("patch")
                    if not isinstance(patch, dict) or not patch:
                        errors.append(f"decisions[{i}]: update 必须带非空 patch 对象")
                        continue
                    if not any(isinstance(v, (str, int, float, list))
                               and v not in (None, "", [], 0)
                               for v in patch.values()):
                        errors.append(f"decisions[{i}]: update.patch 至少一个非空字段")
                        continue
                    # ⏸ 原「patch 不得含 epistemic」2026-09-29 删 —— 字段退役后它是
                    # 白名单外的未知键, 执行器那边照样拒（`revise` 的可改字段表 + store 守卫）;
                    # 这里不再为它单开一条错误文案。
                    item["patch"] = patch
            else:  # add
                kind = str(row.get("kind", "belief")).strip()
                # ⚠️ **只有 belief**（2026-09-25, DESIGN_GRAPH_V4 §5.1）: `profile`
                # 已定名 **玩家画像专用**（"关于老师的事"），写者只有第 1 轮 ⇒ 这一轮
                # 想写"反复出现的模式"就写成 **belief 的模式句**（§9-10）。
                if kind != "belief":
                    errors.append(f"decisions[{i}].kind 非法: {kind!r}（只有 belief ——"
                                  " 模式也写成 belief 的模式句; profile 是玩家画像专用，"
                                  " 由第 1 轮产出）")
                    continue
                item["kind"] = kind
                for f in ("subject", "text", "tags",
                          "significance", "growth"):
                    v = row.get(f)
                    if v not in (None, "", []):
                        item[f] = v
                if not _nonempty_str(item.get("text")):
                    errors.append(f"decisions[{i}]: add({kind}) 必须填 text")
                    continue
                if not _nonempty_str(item.get("subject")):
                    warnings.append(f"decisions[{i}]: add 缺 subject（建议稳定维度命名）")
            out.append(item)
        # 包级: 覆盖检查（结构保证——漏 episode 直接报错, 引擎不补）
        missing = sorted(episode_ids - seen)
        if missing:
            errors.append(f"decisions 未覆盖全部 episode: 漏 {', '.join(missing)}")
        # 可选的补充边（`links`）—— 形状错同样**拒整包**（rel 是契约词汇的一部分）
        out.extend(_parse_links(raw.get("links"), link_ids, errors, warnings))
        return out, ValidationResult(tuple(errors), tuple(warnings))


# ============================================================================
# 内部清洗（宁缺勿错: 坏项丢弃 + 报错; 质量项 warning 不阻断）
# ============================================================================

#: `links` 允许的 rel（**只有这三种** —— 见 DESIGN_GRAPH_V4 §2 的边表）。
#: ⚠️ 别加 `about`（那是第 3 轮的活, 走候选表映射）· 别加 `source`（已删）·
#: 别加 `formed_by`/`from`/`to`（2026-09-29 随 promise 退图一起删）。
#: ⭐ `supports` 在 `links` 这里**只认"看法 → 看法"那一种形状** ——
#: `supports` 共两种形状（§2）: `episode → 认知` 由**决策表**的 touch/update/add 写,
#: `认知 → 认知` 才轮到 links（用户 2026-09-29 裁决两条都留, 所以这一档**不是冗余**）。
LINK_RELS: tuple[str, ...] = ("supports", "contradicts", "evolved_from")


def _parse_links(raw: Any, link_ids: set[str], errors: list[str],
                 warnings: list[str]) -> list[dict]:
    """R2 的可选补充边 `[{"from","rel","to"}]` → 执行器认的行（`action="link"`）。

    与决策行**同一个数组**交出去（`apply_decisions` 一个循环处理两类行）—— 但那两类行的
    校验口径不同: 决策行必须覆盖每个 episode, `link` 行**不参与覆盖统计**（它没有 episode）。

    形状错 = **拒整包**（rel 是契约词汇、两端是渲染列表里的编号 —— 都是"没读契约"）;
    重复的边只留一条（warning, 不算错: 模型多说了一遍同一件事）。
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append("links 必须是数组（没有就写 [] 或省略这个键）")
        return []
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            errors.append(f"links[{i}] 必须是对象")
            continue
        src = str(row.get("from", "")).strip()
        dst = str(row.get("to", "")).strip()
        rel = str(row.get("rel", "")).strip()
        if rel not in LINK_RELS:
            errors.append(f"links[{i}].rel 非法: {rel!r}（只有 "
                          f"{'|'.join(LINK_RELS)}）")
            continue
        bad = [lbl for lbl, val in (("from", src), ("to", dst))
               if val not in link_ids]
        for lbl, val in (("from", src), ("to", dst)):
            if lbl in bad:
                errors.append(f"links[{i}].{lbl} 不在渲染列表内: {val!r}"
                              "（端点也得先在列表里出现过; 本轮新建的连不上）")
        if bad:
            continue
        if src == dst:
            errors.append(f"links[{i}] 两端相同: {src!r}（边不能自环）")
            continue
        key = (rel, src, dst)
        if key in seen:
            warnings.append(f"links[{i}] 重复（只留一条）: {src} -{rel}-> {dst}")
            continue
        seen.add(key)
        out.append({"action": "link", "rel": rel, "from": src, "to": dst})
    return out


def _clean_attach(row: dict, i: int, entity_ids: set[str], node_ids: set[str],
                  errors: list[str]) -> dict | None:
    """`attach`: 把本轮新节点挂到某个对象上（`about` 边的唯一入口）。"""
    ent = str(row.get("entity", "")).strip()
    if ent not in entity_ids:
        errors.append(f"attributions[{i}].entity 不在候选表内: {ent!r}")
        return None
    nodes = _local_nodes(row.get("nodes"), i, node_ids, errors)
    if nodes is None:
        return None
    item: dict = {"action": "attach", "entity": ent, "nodes": nodes}
    hint = str(row.get("hint", "") or "").strip()
    if hint:
        item["hint"] = hint
    return item


def _clean_new_entity(row: dict, i: int, node_ids: set[str], errors: list[str],
                      warnings: list[str]) -> dict | None:
    """`new_entity`: 候选表里确实没有的对象（`name` + **`reason`** 必填）。"""
    name = str(row.get("name", "") or "").strip()
    if not name:
        errors.append(f"attributions[{i}]: new_entity 必须填 name")
        return None
    reason = str(row.get("reason", "") or "").strip()
    if not reason:
        # 准入门槛（§3.0）: 建对象是**永久成本**（此后每轮都在候选表里）, 得说清为什么
        errors.append(f"attributions[{i}]: new_entity 必须填 reason（为什么值得建）")
        return None
    item: dict = {"action": "new_entity", "name": name, "reason": reason}
    aliases = [a.strip() for a in (row.get("aliases") or [])
               if isinstance(a, str) and a.strip()]
    if aliases:
        item["aliases"] = aliases[:MAX_ALIASES]
        if len(aliases) > MAX_ALIASES:
            warnings.append(f"attributions[{i}].aliases 超过 {MAX_ALIASES} 条——截断")
    if row.get("nodes") is None:
        return item                                        # 顺手挂节点是可选的
    nodes = _local_nodes(row.get("nodes"), i, node_ids, errors, optional=True)
    if nodes is None:
        return None
    if nodes:
        item["nodes"] = nodes
    return item


def _clean_rewrite(row: dict, i: int, entity_ids: set[str],
                   errors: list[str]) -> dict | None:
    """`rewrite`: 改写对象的**当前载荷**（`text` 立场 / `state` 现状）—— 空值 = 保留。"""
    ent = str(row.get("entity", "")).strip()
    if ent not in entity_ids:
        errors.append(f"attributions[{i}].entity 不在候选表内: {ent!r}")
        return None
    text = str(row.get("text", "") or "").strip()
    raw_state = row.get("state")
    state: list[str] = []
    if isinstance(raw_state, list):
        state = [s.strip() for s in raw_state if isinstance(s, str) and s.strip()]
    elif raw_state not in (None, ""):
        errors.append(f"attributions[{i}].state 必须是字符串数组")
        return None
    if not text and not state:
        # 行级"什么都没说"= 白跑一趟（`apply_attribution` 那边也会当成空 patch 拒）
        errors.append(f"attributions[{i}]: rewrite 至少要给 text 或 state 之一")
        return None
    item: dict = {"action": "rewrite", "entity": ent}
    if text:
        item["text"] = text
    if state:
        item["state"] = state
    return item


def _local_nodes(raw: Any, i: int, node_ids: set[str], errors: list[str],
                 optional: bool = False) -> list[str] | None:
    """`nodes` 字段清洗: 本地 id 数组（`u0001..`）。

    Returns: 归一化后的 id 列表; `None` = 有错（调用方丢这一行）。
    ⚠️ `optional=True`（`new_entity` 的顺手挂）时**空数组合法** —— 建对象本身就有价值。
    """
    if not isinstance(raw, list):
        errors.append(f"attributions[{i}].nodes 必须是数组（本地 id, 如 [\"u0001\"]）")
        return None
    out: list[str] = []
    for nid in raw:
        s = str(nid).strip()
        if s not in node_ids:
            errors.append(f"attributions[{i}].nodes 里的 {s!r} 不在本轮新节点里")
            return None
        if s not in out:
            out.append(s)
    if not out and not optional:
        errors.append(f"attributions[{i}]: nodes 不能是空的（挂谁上去?）")
        return None
    return out


def _id_list(v: Any) -> list[str]:
    """宽松取 id 数组（非列表 → 空; 元素转字符串去空白）。"""
    if not isinstance(v, (list, tuple)):
        return []
    return [str(x).strip() for x in v if isinstance(x, (str, int)) and str(x).strip()]


def _clean_episode(e: Any, i: int, seq_set: set[int] | None = None,
                   drops: list[str] | None = None
                   ) -> tuple[dict | None, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(e, dict):
        return None, [f"episodes[{i}] 必须是对象"], []
    # 引擎字段一律不收（id/ts——LLM 塞了也丢弃）
    # ⚠️ `event_seq` **已从这份名单移出**（T14, 2026-09-15）: 它现在是**板指针**,
    #    是 §3.3.1 里 LLM 唯一的"指位置"输出之一。旧版把它当引擎字段丢弃,
    #    而 `digest.py` 又把它覆写成常量 → 两者相加 = 板指针从来没存在过。
    # ⚠️ `segment_id` 2026-09-21 移出: 那个字段本身已退役（引擎不再落它）,
    #    把它继续当"引擎字段"警告是历史残留。
    for f in ("id", "ts"):
        if f in e:
            warnings.append(f"episodes[{i}] 含引擎字段 {f}——已忽略")
    # ⭐ **2026-09-29: `kind` 只在"例外"时写**（用户裁决: 轮次决定的常量不该由 LLM 声明）——
    # 缺键 / 空串 ⇒ 默认 **episode**; 只有 `experience`（玩家画像）需要显式写;
    # 写坏值照旧拒（不静默降级 —— 静默改 kind 会让模型下次还这么写）。
    kind = str(e.get("kind", "") or "").strip() or "episode"
    if kind == "episode":
        item, errors, warnings = _clean_episode_item(
            e, i, errors, warnings, seq_set, drops)
        if item is not None:
            item["kind"] = "episode"
        return item, errors, warnings
    if kind == "profile":
        # 玩家画像条目（MMT 专则, 2026-09-02）: text 必填, subject 引擎固定 player
        text = _read_text(e, i, warnings)
        if not text:
            return None, [f"episodes[{i}]: kind=experience（玩家画像）必须填 text"], []
        item: dict = {"kind": "profile", "text": text,
                      "subject": PLAYER_SUBJECT}
        # 画像条目无 episode 载体——原话同样走**记录行号**（玩家那句 = `[N.0]`）
        _fill_verbatim(item, e, i, warnings, seq_set, drops=drops)
        tags = [t for t in e.get("tags", []) if isinstance(t, str) and t.strip()][:MAX_TAGS]
        if tags:
            item["tags"] = tags
        sig = e.get("significance")
        try:
            sig_f = float(sig) if sig is not None else 0.5
        except (TypeError, ValueError):
            sig_f = 0.5
        item["significance"] = max(0.0, min(1.0, sig_f))
        return item, errors, warnings
    return None, [f"episodes[{i}].kind 非法: {kind!r}（不写 = 经历; 只有"
                  f"「玩家画像」才写 'profile'）"], []


def _norm_index(raw: Any) -> str | None:
    """索引项 → 规范串 `"28.3"` / `"28.p"` / `"28"`（坏项 → None）。"""
    from contract.timeline_index import parse_index
    got = parse_index(raw) if isinstance(raw, str) else (
        (raw, "") if isinstance(raw, int) and not isinstance(raw, bool) else None)
    if got is None:
        return None
    seq, rec = got
    return f"{seq}.{rec}" if rec != "" else str(seq)


def is_full_date(v: str) -> bool:
    """`YYYY-MM-DD`（**全日期**）—— `due` 唯一的格式规矩。

    ⚠️ **公开**（2026-10-05, L3）: 料那一侧（`material._due_cell` / 资格位）**也要判同一件事**
    —— "什么算全日期"只许有这一个实现, 否则"料里印成日期、契约当没期限"就会漂。

    ⚠️ **只在这里校验格式**: 引擎判"过期没有"时用 `date` 自己比
    （`date.fromisoformat(due) < 今天`）—— **绝不把它喂给 `worldtime.age.age_days`**
    （那个函数吃的是节点 `ts` 那种 **aware** 时间戳, 裸日期会 `aware − naive` 当场 TypeError,
    `tests/core/test_wiki_recall.py:146` 踩过一次）。
    """
    try:
        date.fromisoformat(v)
    except ValueError:
        return False
    return True


def _drop(warnings: list[str], drops: list[str] | None, text: str) -> None:
    """记一条**真的丢了东西**的 warning（⭐ D1, 2026-09-29）。

    ⚠️ 这是"分类"的**唯一来源**: 一处 warning 是不是"丢"由**写它的这一行代码**说了算,
    绝不靠事后拿中文子串去猜（`ValidationResult.drops` 的 docstring 讲了为什么）。
    ⇒ **改这里的用法时只有一个判据**: 这条 warning 背后**有没有一个内容离开过库**?
    有（区间作废 / 原话丢了 / 心境丢了）⇒ 用 `_drop`; 只是形状建议 / 夹紧 / 兼容旧名 ⇒
    `warnings.append`。
    """
    warnings.append(text)
    if drops is not None:
        drops.append(text)


def _clean_seq_list(raw: Any, seq_set: set[int] | None, *,
                    label: str, warnings: list[str],
                    record_level: bool, drops: list[str] | None = None) -> list[str]:
    """索引数组清洗 —— **坏项逐条丢弃**（不废整包, 与 `parse_index_list` 同纪律）。

    `record_level=False`（板指针 `event_seq`）: 只收事件级 `"28"`, 记录级
    `"28.3"` 视为写错（它的 seq 部分仍然认, 但会记一条 warning 提醒）。
    `record_level=True`（`verbatim` 索引通道）: 收 `"28.3"` / `"28.p"` / `"28"`。

    `seq_set` 非空时做 ⊆ 校验——**抄不存在的编号 → 丢弃**（防幻觉: 序号由引擎发,
    抄不到就丢, 绝不猜）。
    """
    from contract.timeline_index import parse_index
    if raw is None:
        return []
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    out: list[str] = []
    bad = 0
    for it in items:
        norm = _norm_index(it)
        if norm is None:
            bad += 1
            continue
        seq = parse_index(norm)[0]
        if not record_level and "." in norm:
            warnings.append(f"{label} 收了记录级索引 {norm!r}——板指针只收事件级"
                            f"（已按事件 {seq} 收下）")
            norm = str(seq)
        if seq_set is not None and seq not in seq_set:
            bad += 1
            _drop(warnings, drops, f"{label} 的 {norm!r} 不在本段时间线里——丢弃")
            continue
        if norm not in out:
            out.append(norm)
    if bad:
        warnings.append(f"{label}: {bad} 个索引不可用（已丢弃）")
    return out


def _clean_span(raw: Any, seq_set: set[int] | None, *, label: str,
                warnings: list[str], drops: list[str] | None = None) -> list[int] | None:
    """⭐ 区间清洗（**N3**, 2026-09-29）—— `[28, 30]` → `[28, 30]`；坏形状 → `None`。

    规矩:
      · 收 **2 个端点**的数组；单值也收（退化成 `[n, n]`）；>2 个 ⇒ **只取首尾** + 告警
      · 端点必须是**事件级** seq（`"28"`）；记录级 `"28.3"` 取它的 seq 部分 + 告警
      · `起 ≤ 止`；**反了 ⇒ 丢弃**（⚠️ **不自动交换** —— 静默改她的意思比报错贵）
      · `seq_set` 非空时**两端都必须存在**（抄不存在的编号 → 丢弃）

    ⚠️ **只校验两端的存在性，不逐块校验** —— 区间是"这一段"，引擎按 `seq_set` 求交即可；
    逐块校验会把"区间里夹着 marker（marker 不在 `seq_set` 里）"误判成坏区间。

    ⚠️ **一律告警、不废整包**（与 `_clean_seq_list` 同纪律）: 一个坏区间不该让她重写整段,
    而"本条没有位置"是**可见的**（节点 `event_seq` 为空 ⇒ `_node_ts` 回落到段 ts）。
    """
    from contract.timeline_index import parse_index
    if raw is None:
        return None
    if isinstance(raw, (str, int)):
        items: list = [raw]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        _drop(warnings, drops, f"{label} 不是数组——丢弃")
        return None
    if not items:
        _drop(warnings, drops, f"{label} 是空数组——丢弃")
        return None
    if len(items) > 2:
        warnings.append(f"{label} 给了 {len(items)} 个端点——只取首尾")
        items = [items[0], items[-1]]
    seqs: list[int] = []
    for it in items:
        norm = _norm_index(it)
        if norm is None:
            _drop(warnings, drops, f"{label} 的 {it!r} 不是合法编号——丢弃整个区间")
            return None
        seq = parse_index(norm)[0]
        if "." in norm:
            warnings.append(f"{label} 收了记录级索引 {norm!r}——已按事件 {seq} 收下")
        seqs.append(seq)
    if len(seqs) == 1:
        seqs.append(seqs[0])                      # 单值 ⇒ 退化成一块
    lo, hi = seqs
    if lo > hi:
        _drop(warnings, drops, f"{label} 起止反了（{lo} > {hi}）——丢弃（不自动交换）")
        return None
    missing = [s for s in (lo, hi) if seq_set is not None and s not in seq_set]
    if missing:
        _drop(warnings, drops, f"{label} 的端点 {missing} 不在本段时间线里——丢弃")
        return None
    return [lo, hi]


def _fill_verbatim(item: dict, e: dict, i: int, warnings: list[str],
                   seq_set: set[int] | None, drops: list[str] | None = None) -> None:
    """`verbatim` = **记录行号**（唯一通道）。

    ① `"verbatim": ["28.3", "20.p"]` —— 抄时间线的记录行号
    ② 也可显式给 `"verbatim_seq": [...]`（等价; 两条并存时合并去重）

    落库: `verbatim_seq` = 索引（可重解析 / 板归属）; `verbatim` = 文本, **由引擎在
    `digest.py` 解析索引后回填**（parse 层拿不到事件流）。

    ⏸ **文本通道（`"verbatim": "…"` 字符串）2026-09-29 退役**：它和索引说的是同一件事,
    而并存时**文本优先** ⇒ 一个偏了一位的索引会被一句"看起来正常的"手抄文本静默盖掉。
    现在只认数组: 写字符串 → 逐条丢弃 + 告警（**不兜底**）。
    """
    seqs: list[str] = []
    for key in ("verbatim", "verbatim_seq"):
        v = e.get(key)
        if isinstance(v, (list, tuple)):
            seqs.extend(_clean_seq_list(v, seq_set, label=f"episodes[{i}].{key}",
                                        warnings=warnings, record_level=True,
                                        drops=drops))
        elif v is not None:
            _drop(warnings, drops,
                  f"episodes[{i}].{key} 必须是数组（记录行号）——忽略")
    if seqs:
        item["verbatim_seq"] = list(dict.fromkeys(seqs))


def _read_text(e: dict, i: int, warnings: list[str]) -> str:
    """条目正文 —— 主字段 `text`（2026-09-21 三槽合流）, 兼容旧名 `narration`/
    `pattern`/`content`。

    ## 为什么兼容旧名（这是一个**安全**决定, 不是留恋旧形状）

    契约文案改名的那个版本落地时, 模型有惯性（也可能命中**旧的 prompt 缓存**）——
    若只认 `text`, 一次惯性就**整条丢弃**（episode/experience 都是"缺正文即丢"）,
    代价是整包重发 + 反馈重试。兼容读 + **一行 warning** 把这件事变成可观测:
    长期还在出现旧名 → grep `用了旧字段名` 就能发现（同 §8"示例才是形状来源"那条纪律）。
    """
    for key in ("text", "narration", "pattern", "content"):
        v = e.get(key)
        if isinstance(v, str) and v.strip():
            if key != "text":
                warnings.append(
                    f"episodes[{i}] 用了旧字段名 {key}——已按 text 收下"
                    f"（schema 已改名, 若长期出现请查 prompt 缓存）")
            return v.strip()
    return ""


def _clean_episode_item(e: dict, i: int, errors: list[str], warnings: list[str],
                        seq_set: set[int] | None = None,
                        drops: list[str] | None = None
                        ) -> tuple[dict | None, list[str], list[str]]:
    """kind=episode 条目的字段清洗（缺 text 整条丢弃, 宁缺勿错）。"""
    text = _read_text(e, i, warnings)
    if not text:
        return None, errors + [f"episodes[{i}] 缺 text"], warnings
    if len(text) > MAX_TEXT:
        # 宁缺勿错: 整条丢弃（包已无效 → 反馈重试会让 LLM 重写整包, 截断反而静默改内容）
        return None, errors + [f"episodes[{i}].text 超过 {MAX_TEXT} 字——整条丢弃"], warnings
    item: dict = {"text": text}
    title = e.get("title")
    if isinstance(title, str) and title.strip():
        item["title"] = title.strip()
    else:
        warnings.append(f"episodes[{i}] 缺 title（建议 8-16 字短标题）")
    # ⛔ **位置不再从这里读**（3b-2, 2026-09-29）: 切分权归 R0 ⇒ 一条经历覆盖哪一段
    # 由**骨架**定（`split` 那一轮的 `seqs`）, 引擎按顺序把这一行并到那条切片上。
    # 所以:
    #  · `span` 字段**退役**（契约里不再渲染它; 她还写就只记一句 warning）;
    #  · 旧形状 `event_seq`（逐点挑选）**一并退役** —— 它是"她自己挑位置"的时代的产物。
    # 原先那两段"没位置 ⇒ 回落段级指针 ⇒ 进 `no_pos` 账"的逻辑因此整套消失:
    # **没有"她的位置"可错了**（位置是引擎算的区间）。
    for gone in ("span", "event_seq"):
        if gone in e:
            warnings.append(f"episodes[{i}] 写了 {gone}——位置由【本段骨架】定, 这个字段已退役"
                            f"（引擎忽略它）")
    # verbatim: 记录行号（唯一通道 —— 文本通道 2026-09-29 退役）
    _fill_verbatim(item, e, i, warnings, seq_set, drops=drops)
    tags = [t for t in e.get("tags", []) if isinstance(t, str) and t.strip()][:MAX_TAGS]
    if tags:
        item["tags"] = tags
    else:
        warnings.append(f"episodes[{i}] 缺 tags（检索导向 1-4 个）")
    # ⏸ `about_hint`（归属线索, §8.2/D1）清洗 **2026-09-29 删** —— 字段退役:
    # 它和 R3 的"挂谁"**判两次**（R1 猜一次、R3 再判一次, 还可能不一致）,
    # 而 R3 本来就拿得到候选表（全量）+ 新节点正文 ⇒ **引擎不必替它预判一个名字**。
    # 详见 `core/brain/REDUNDANCY.md` #2。
    # ⏸ `items`（物品台账）清洗 **2026-09-29 删** —— 字段退役, 旧档里的值一并清掉。
    sig = e.get("significance")
    try:
        sig_f = float(sig) if sig is not None else 0.5
    except (TypeError, ValueError):
        warnings.append(f"episodes[{i}].significance 非数字——取 0.5")
        sig_f = 0.5
    item["significance"] = max(0.0, min(1.0, sig_f))
    # 情绪两标量（§3.3.3）: **缺/坏 → 不落字段**（None 哨兵）, 不折成 0.0——
    # 「未采集」与「真的毫无波澜」是两件事, 合并会让旧档在召回里冒充后者。
    # （`emo_valence` 2026-09-21 删——有生产零消费, 极性由 `emo_shape` 逐键承担。）
    for fname, lo, hi in (("emo_int", 0.0, 1.0), ("emo_span", 0.0, 1.0)):
        raw_v = e.get(fname)
        if raw_v is None:
            continue
        if isinstance(raw_v, bool):
            warnings.append(f"episodes[{i}].{fname} 是布尔——忽略")
            continue
        try:
            v = float(raw_v)
        except (TypeError, ValueError):
            warnings.append(f"episodes[{i}].{fname} 非数字——忽略")
            continue
        if v != v:                              # NaN
            warnings.append(f"episodes[{i}].{fname} 是 NaN——忽略")
            continue
        item[fname] = max(lo, min(hi, v))       # 越界**夹紧**（不丢弃——值仍可用）
    # 来源（2026-09-29 起**只有 `observer` 一个字段**）: 非空 = 听说的 + 转述者是谁;
    # 空 = 亲历。⏸ 原 `epistemic` 字段退役（判据: 与 observer 互为函数 + 跨 kind 两个意思,
    # `REDUNDANCY.md` #3）—— 旧 prompt 缓存里若还带着它, 这里只**提一句**不落库
    # （不废整包: 值与 observer 重复, 信息没丢）。
    if e.get("epistemic") not in (None, ""):
        warnings.append(f"episodes[{i}].epistemic 字段已退役——只填 observer（忽略）")
    obs = e.get("observer")
    if isinstance(obs, str) and obs.strip():
        item["observer"] = obs.strip()
    return item, errors, warnings


def _nonempty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


#: 默认注册表实例（板块 4 引擎编排消费）
digest_registry = DigestRegistry()
