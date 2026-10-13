"""digest 契约的**值表** —— 相位名 / 上限 / 取值域 / 日期格式。

这一层只有机器读: 校验器（`parse.py`）、渲染器（`registry.py`）、引擎（`core/digest`）。
⛔ 这里不放**一句给 LLM 看的话** —— 那些在 `contract/digest/docs.py`。

⚠️ 上限这类数字**不只是上限, 它还是标尺**（改一个数字 = 改模型的行为 —— 见 `MAX_SEGMENTS`
那段注释里 12 → 20 → 12 的教训）。动之前先看真机那一行的分布。

⚠️ 本模块**零项目内依赖**（只用 stdlib）, 所以谁都可以往上压。
"""
from datetime import date

PHASE_RECORD = "record"
#: ⭐ **R0「切分」**（2026-09-29, N4d）—— 每段的**第一步**: 只划区间 + 写一句总括
#: + 挑出"要一直带着的"那几条。**不写正文、不填情绪、不打分、不建节点。**
#: ⚠️ 它拿走了 R1 从前最重的那件事（划区间）⇒ **图的形状由它一个人决定**
#: （几个节点、每个覆盖哪段）, 所以它的产出必须**可校验**（区间在不在时间线里）
#: 且**可观测**（覆盖了多少 / 丢了几条 —— 见 D1 那本缺口账）。
PHASE_SPLIT = "split"
PHASE_UNDERSTAND = "understand"
#: ⭐ **L1「判关系」那一趟**（`docs/DESIGN_DIGEST_TWO_PASSES.md` §9）。
#: ⚠️ 今天**没有轮在用它** —— 这是 P1a 的"新增并立": 形状与解析先落, 接线在 P1b
#: （换骨头那笔把 `ROUNDS` 的 key 从 `understand` 改成 `relate`, 并删掉旧一族）。
PHASE_RELATE = "relate"
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
#: ⭐⭐ **L2「造认知 / 写正文」那一趟**（`DESIGN_DIGEST_TWO_PASSES.md` §3/§5,
#: 2026-10-08 用户定稿）—— 它是**第二趟**:
#:   · L1（`relate`）只判关系, **一个字的正文都不写**;
#:   · 这一趟**只写正文** —— 造新的 `belief`（⛔ 不判已有成分之间的关系: 那是 L1 判过的）,
#:     并给**已有的类**（`experience`）重写它的**沉淀**。
#: ⚠️ **顺序上它排在 `group` 之后** —— 沉淀要写给"本段刚归好类的那些类", 类得先存在。
#: ⚠️ 今天**没有轮在用它**: 形状与解析先落, 接线（`ROUNDS` 那一行 + prompt + 桩）在 P10
#: —— 与 P1a 的 `PHASE_RELATE` 当时同一个状态。
#: ⚠️ 建**新类**不归它（那是 `group` 的活）⇒ `experience` 那一行**必须带 `id`**。
PHASE_COGNIZE = "cognize"
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
#: ⭐ **L2（`cognize`）单包最多造几条看法**（用户 2026-10-08 裁决 = 5, 同 `MAX_EPISODES` 量级）。
#: ⚠️ 写沉淀的类**不算**在这条里（那是"更新正文", 不是"长出新节点"）—— 一段里造太多看法
#: 就变成流水账, 而"没话说就不写"本来就是它的纪律。超了**丢行 + 记账**（同 `MAX_SEGMENTS`
#: 的"超出的丢弃"口径）。
MAX_COGNITIONS = 5
MAX_ALIASES = 8         # `new_entity` 的别名上限（超了截断 + warning —— 别名是效率优化）
MAX_TEXT = 300          # 正文（text）单行上限（汉字）——三槽合流后两种 kind 共用
MAX_TAGS = 4            # tags 检索词上限（⭐ 只数**检索词** —— `#` 开头的标记不算, 见下）

#: ⭐ **结构 tag 的语法**（E1, 2026-10-08）: `#entity:<名字>` = 这条经历/看法**涉及谁**。
#: `#` 开头 = **标记, 不是检索词** —— 这条约定已经有第一个成员（`notes.PINNED_TAG =
#: "#pinned"`, 判据写在 `core/digest/material.py`: *"`#pinned` 那种标记不是词"*）⇒
#: 检索侧天然已经跳过它们（`startswith("#")`）, 本常量只是把第二个成员写下来。
#: ⚠️ 名字**不在这里解析**（契约层没有 store）—— 归一与落边见
#: `core/brain/entities.normalize_entity_tags` 与 `core/digest/episodes._link_about`。
ENTITY_TAG_PREFIX = "#entity:"
#: 一条经历最多带几个 `#entity:` —— ⚠️ 它**不占** `MAX_TAGS` 的额度（分开计数）。
#: 上限 2 = "这段涉及谁"必须挑（宽口径也要有边）; 超了截 + 告警。
ENTITY_TAGS_MAX = 2
#: ⭐ `topics` 上限（**≤3**, 用户 2026-10-07 裁决）—— "这条经历关于什么"的**具体东西**。
#: 它是"同类的事"认亲的把手（L1 的 `akin` 要求 `on` ∈ 两端 `topics` 的交集）。
TOPICS_MAX = 3
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


#: L1 的**锚点类型**（行首那个键能写哪几个 kind）。
#: ⚠️ 与 `nodes.KINDS` **同源**，但契约层不 import core ⇒ 手写一份 + 守门钉住两边相等。
#: ⚠️ **2026-10-08（E3）删掉 `"entity"`** —— 它是 `about` 那一行的锚点, 而 `about` 不再是
#: LLM 的动作（**归属由引擎从节点 `tags` 里的 `#entity:` 派生**, 见 `DESIGN_ENTITY_TAGS`）。
RELATION_ANCHORS = ("episode", "belief", "experience", "profile")


#: L2 的**锚点键**（= 她能动手的两种 kind: 造看法 / 给类写沉淀）。
COGNIZE_ANCHORS = ("belief", "experience")
#: L2 一行的**合法键域** = 两个锚点 + 三个关系名（⊆ `RELS`）。
#: ⚠️ 多值只发生在 `supports`（一条看法常被好几条经历支撑）与 `contradicts`（可能跟好几条打架）上;
#: ⛔ **没有 `evidence` 这个键** —— 它 2026-09-29 就退役了（零产品消费者）, 别让它长回来。
COGNIZE_KEYS = (*COGNIZE_ANCHORS, "supports", "evolved_from", "contradicts")


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
