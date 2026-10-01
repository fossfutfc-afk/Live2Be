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
包级字段（B 轮）: evidence（罗盘成长证据）/ affection_exp_delta（引擎消费）。

引擎执行层在 core/brain/wiki_v2/（digest.py 两轮编排 + revise.py 执行器, 板块 4）;
本文件只管"LLM 契约层": 结构/类型/边界/字段约束。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from contract.model import ValidationResult

PHASE_RECORD = "record"
PHASE_UNDERSTAND = "understand"
#: R4 收口（DESIGN_GRAPH_V4 §8: promise 记账）—— 每段的第 4 步，**窄调用**，
#: 只判"这条约定还开着吗"，不碰正文/认知。
PHASE_CLOSE = "close"
#: ⚠️ ~~`PHASE_PANORAMA`~~（全景轮/写卡）**2026-09-29（N4a）已退役** —— 它的两个槽
#: 一个被取消（`habits`）、一个换了写者（`on_mind` → L1）⇒ 它没有输出了。
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

#: promise 的结局（与 `core.brain.wiki_v2.nodes.PROMISE_OUTCOMES` 对齐 ——
#: 契约层**不依赖 core**, 所以这里独立声明一份, 由这条注释钉住"两处同源"）
PROMISE_OUTCOMES = ("kept", "broken", "superseded")

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
MAX_ITEMS = 3           # items（物品台账, §3.1）单条上限
#: 类名（group 的 `title`）上限 —— ⚠️ **与 episode 的 8~16 字不是同一条**: 类名可以很短
#: （"那片苔藓" 4 字就够）, 这里只挡"写成一整句话的那种"; 超了**只告警不截断**
#: （截断会把名字截坏, 而名字是**地址**）。
GROUP_TITLE_MAX = 16

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
_DOMAIN_CONTRACT = {
    "bond": (
        "【本段含一章羁绊剧情（**作者单位**: 有始有终的完整一段）】\n"
        "→ **这一章恰好 1 条** episode, 它就是**这一章的总结**:\n"
        "   · informative but single —— 把这一章讲透（起因/关键推进/落点都在里面）,\n"
        "     但**只讲这一件事**; 不按时间把每个回合罗列一遍。\n"
        "   · ⚠️ 时间线里的每一步**不是**要分别记的条目 —— 那会写成流水账, 是本轮的典型错误。\n"
        "   · title 用**本章标题**（用户消息的【本章标题】给了）;\n"
        "     span 给**本章的起止**块号（`[起, 止]`）——整章都算这一条覆盖;"
        " verbatim 仍只挑最关键的一句。\n"
        "⚠️ 本段**可能同时含 MomoTalk 聊天**（时间线里那些不是剧情画面的来回消息）:\n"
        "   那部分**不属于这一章** —— 按 `mmt` 规则 0~5 条**另行记录**（约定/玩家画像/\n"
        "   值得记的对话）, 与本章那一条分开; 既不要并进章总结, 也不要漏记。"
    ),
    "mmt": (
        "【本段类型 = MomoTalk 聊天（**无作者单位**: 一次覆盖多轮碎聊）】0~5 条\n"
        "→ 长聊天**需要切分**: 一条 = 一件可独立复述的事（informative but single）。\n"
        "   · 同一件事不拆两条; 两件事不并一条;\n"
        "   · 没有值得记的 → `\"episodes\": []`（合法）。"
    ),
}

RECORD_EPISODE = DigestAction(
    name="record_episode",
    phase=PHASE_RECORD,
    role="把本段新增互动浓缩为值得记住的经历条目（一条一对象）。",
    semantics=(
        "何时用: 时间线里形成了完整经历（有起有落/有情感细节/值得以后想起）;\n"
        "怎么改: 第一人称浓缩——起点→关键推进→落点, 保留角色当时的感受与反应;\n"
        "指位置（T14 → ⭐ **N3**, 2026-09-29）: 给出**区间**, 不打分——"
        " span 写 `[28, 30]` = 本条覆盖**从 28 到 30 这一整段**（起止两块的事件头编号）;"
        " verbatim 抄 `[28.3]`/`[28.p]` 这类记录行号（关键的几句）;\n"
        "禁什么: 不升华成人生感悟; 不记寒暄流水账; 不写旧记忆里已有的事;"
        " 情绪词堆砌但无情节支撑 → 舍弃。"
    ),
    field_schema=(
        '    {  // 一条记录; **条数见上方【本段类型】的产出契约**（bond=恰好 1 / mmt=0~5）//\n'
        '      "kind": "episode",    // "episode"=经历 | "experience"=玩家画像专用\n'
        '                            //（玩家口癖/偏好/一次性个人信息——text 写画像句,\n'
        '                            //  subject 不用填, 引擎固定为 player）//\n'
        '      "text": "…",        // 必填（两种 kind 同一个字段名）; 单行 ≤300 字;\n'
        '                          // kind=episode → 第一人称浓缩, 不流水账;\n'
        '                          // kind=experience → 玩家画像句, 如"玩家的生日是\n'
        '                          // 5 月 20 日""玩家总说摸鱼" //\n'
        '      "title": "…",      // kind=episode 必填; 8-16 字短标题; 拿不准也给朴素标题 //\n'
        '      "span": [28, 30],   // ⭐ **本条覆盖【哪一段】**——起止两块的事件头编号\n'
        '                          //（`[28] 【羁绊剧情】` 里的 28）。**这是指位置, 不是打分**;\n'
        '                          // 区间内的事件**全部**算你覆盖了, 不必逐块列;\n'
        '                          // 两端必须真实存在、且 起 ≤ 止。拿不准就把区间写宽一点 //\n'
        '      "verbatim": "…",   // 可选; **两条通道, 给一条即可**:\n'
        '                          //  ① 列表 = 抄时间线的记录行号（推荐）——\n'
        '                          //     ["28.3", "20.p"]; 引擎据此取回**逐字原文**\n'
        '                          //  ② 字符串 = 原话逐字复制（禁改写）;\n'
        '                          // 两条都给时**以②为准**（索引只留作溯源）——\n'
        '                          // 所以想用①就**别写字符串**, 别两条都给 //\n'
        '      "tags": ["…"],     // 必填 1-4 个; 检索导向——未来玩家输入/叙事可能出现的词\n'
        '                          //（人名/地点/物品/动作/话题）; 不含时间词; 从最重要排起 //\n'
        '      "about_hint": "老师",  // 可选; 这条记忆**是关于谁的**——写你心里那个自然名字\n'
        '                          //（"老师"/"睦月"/"杂草屋"）。\n'
        '                          // 判据: **三个月后再提到它, 需要它前后一致吗?** 需要才写。\n'
        '                          // ⚠️ 一次性道具**不写**（那顶帽子/只去过一次的饭馆）——\n'
        '                          // 它们留在 text 里就够, 写进来只会造出一堆没有下文的身份 //\n'
        '      "items": ["一盆杂草"],  // 可选; 这件事里她**得到/失去了什么实物**\n'
        '                          //（一盆杂草/一本笔记/一个挂件）。\n'
        '                          // 情绪、对话、"发生的事"都不算; 最多 3 件; 没有就不写 //\n'
        '      "significance": 0~1,  // 行为锚点: 0.9+ 改变认知/极深刻（初遇/告白）;\n'
        '                          // 0.7~0.9 重要约定/特别难忘的日常; <0.7 普通但角色在意的细节;\n'
        '                          // 拿不准往低给 //\n'
        '      "epistemic": "observed_fact",  // observed_fact 默认;\n'
        '                          // 若是"听别人说的"→ reported_fact 且必须填 observer=转述者 //\n'
        '      "observer": "…",    // reported_fact 时必填（转述者）; observed 不填 //\n'
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
        ' "span": [31, 33],'
        ' "verbatim": ["33.2", "33.p"],'
        ' "tags": ["公园", "流浪猫", "热茶"],'
        ' "about_hint": "老师",'
        ' "items": ["老师给的纸杯"],'
        ' "significance": 0.8,'
        ' "emo_int": 0.6, "emo_span": 0.7}'
    ),
)

#: ⭐ **L1 的第二个产物: 她此刻在想什么**（N4a, 2026-09-29）——
#: 从前由全景轮每 10 段整段替换; 现在归 **Round A**（"心境是此刻"，本段视野就够）。
#: ⚠️ 它是 `episodes` 的**同级键**（不是又一条 episode）⇒ 在这里当常量注入,
#:    不走"再加一个 DigestAction"（那个机制渲染的是 `episodes[]` 里的行形状）。
ON_MIND_FIELD = (
    '     "on_mind": "…"     // 可选; **她此刻心里悬着/想通的那一件事**（≤60 字, 一句散文,'
    ' 她自己的口吻）。\n'
    '                        // 例: "我给瓦片留了缝让它见光——也想给自己留一道"\n'
    '                        // ⚠️ 不复述刚发生的事（那归 episodes）; 不写计划/待办（那归约定）;\n'
    '                        //    没写这个键 = **保持上次那句不变**（不是清空）'
)
ON_MIND_SEMANTICS = (
    "【on_mind 怎么写】它不是这一段的总结, 是**她此刻的心境** —— 一句就够, 用她的口吻。\n"
    "写得出就写（那件事真的在她心里挂着）; 写不出**整个键都别出现**（缺键 = 不变）。\n"
    "要明确清空（那件事已经过去了）→ 写成空串 `\"on_mind\": \"\"`。"
)
#: `on_mind` 的软上限（超了**收下但告警** —— 它不是"形状错", 不该废整包）
ON_MIND_MAX = 60

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
        "禁什么: 不复制原文进 text; 不改 epistemic; 不碰出厂基座(canon 只读)。"
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
        '      "example": "…",       // 可选; 本次的具体例子一句 //\n'
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
        understand: {"decisions": [...], "evidence": [...], "affection_exp_delta": n}

        `domain`（2026-09-20, 用户裁决）—— **粒度跟着"作者单位"走**:

        | 段 | 边界 | Round A 产出 |
        |---|---|---|
        | `bond` | `vn_enter`…`vn_exit`（**引擎已知**, 一章 = 作者写的有始有终的一段） | **每章恰好 1 条** = 这一章的总结 |
        | `mmt` | 无作者单位（一次 digest 覆盖多轮碎聊） | 0~5 条原子 |

        用户原话: *"真正的 episode 一个就可以定下，需要被切分的是长篇 MMT 等；
        episode 应该 **informative but single**，belief 则是 **brief but descriptive**"*。
        段类型与**章分组**由 `digest._segment_domain` 从 marker **派生**（不落库）。

        `chapter_count` > 1 = 这一段的窗口里有**多章**（水位被清 / 重跑时必然如此）——
        契约要写成"**每章各 1 条**", 否则两章会被压成一条。
        """
        if phase == PHASE_RECORD:
            contract = _DOMAIN_CONTRACT.get(domain, _DOMAIN_CONTRACT["mmt"])
            if domain == "bond" and chapter_count > 1:
                contract = contract.replace(
                    "→ **这一章恰好 1 条** episode, 它就是**这一章的总结**:",
                    f"→ 本段含 **{chapter_count} 章** —— **每章各恰好 1 条** episode"
                    f"（共 {chapter_count} 条）, 每条就是**它那一章的总结**:")
            lines = [
                "输出 JSON（不要任何解释文字, 不要 ```json 代码块）:",
                contract,
                "",
                '    {"episodes": [',
            ]
            a = self.spec("record_episode")
            lines.append(a.field_schema)
            lines.extend(["    ],",
                          ON_MIND_FIELD,
                          "    }",
                          "",
                          f"【record_episode 释义】{a.role}",
                          "语义:", a.semantics,
                          "",
                          ON_MIND_SEMANTICS])
            if include_examples and a.example:
                lines.extend(["", "【范例】", a.example])
            return "\n".join(lines)

        if phase == PHASE_UNDERSTAND:
            actions = self.actions(PHASE_UNDERSTAND)
            lines = [
                "输出 JSON（不要任何解释文字, 不要 ```json 代码块）:",
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
                '     "evidence": [ // 可选; 成长证据——只输出有明确原文支撑的;',
                '                    // confidence < 0.7 会被引擎丢弃; quote 必须逐字来自时间线 //',
                '        {"function": "fe", "confidence": 0.8, "quote": "…原文…", "note": "…"}',
                "     ],",
                '     "affection_exp_delta": 0  // 本段好感净变化 -100~100（int）; 无变化 → 0;',
                '                                // **负值 = 关系恶化**（被伤到/失望/决裂）//',
                "    }",
                "",
                "decisions 规则: 每个 episode 恰好一行; 必须覆盖全部 episode;",
                "id 只能引用上方渲染列表里出现的 id（编造 id → 整包拒）;",
                "引擎候选标注'疑似印证/疑似重复'时必须遵守（印证→touch, 重复→update）。",
                "",
                "links 规则（**可选的补充边**, 别拿它当主力）:",
                "  supports      —— 「这条承诺/这件事, 长出了那个看法」（承诺 → 看法）;",
                "  contradicts   —— 「这两条互相打架」（无向: 写一次就够）;",
                "  evolved_from  —— 「这条是新的, 它把旧的盖过去了」（新 → 旧）;",
                "  ⚠️ 方向别写反（`from` 是新/被支撑的那一头）; 两端都不能是本轮新建的条目",
                "    （列表是这一轮**开始前**的样子 —— 新建的下一轮才连得上）;",
                "  ⚠️ 承诺（promise）**只**能用 links 连: 它不是看法, 不要 touch/update 它。",
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

        if phase == PHASE_CLOSE:
            return "\n".join([
                "输出 JSON（不要任何解释文字, 不要 ```json 代码块）:",
                "    {",
                '     "add": [ // 这一段新说定的约定（没有就写 []）;',
                '        {"text": "周六模型店", "refs": ["m0013"], "due": "2026-09-26"}',
                "     ],",
                '     "close": [ // 已经不再开着的约定（没有就写 []）;',
                '        {"id": "n1", "state": "kept", "refs": ["m0013"],',
                '         "afterwards": "周六我们真的去了"}',
                "     ]",
                "    }",
                "",
                "两个键**都要在**（没有就写空数组 []）。",
                "",
                "add 一行 = 一条新约定:",
                "  text  —— 一句短语（≤20 字）: 写「要做什么」+ 你此刻对它的那点意思（有人味, 但别复述事件）;",
                "  refs  —— 说定它的经历编号（≥1, 只能引用上面列出的编号）;",
                '  due   —— 可选, 说好的日子（没有就省略这个键）。',
                "",
                "close 一行 = 一条约定翻篇了:",
                "  id         —— 备忘录上的编号（上面「还开着」名单里的）;",
                "  state      —— kept（兑现了）/ broken（没成: 失约, 或你自己作罢）/",
                "                superseded（被新定的那条盖过去了）;",
                "  afterwards —— 一句话说「这件事后来怎么了」（**必填** —— 它会原样出现在她的备忘录上,"
                " 归档时还会并进那条记忆的正文）;",
                "  refs       —— 可选: **了结它的那条经历**（指得出就写, 指不出就不写 ——"
                " 别为了填字段硬拉一条无关的经历）。",
                "",
                "规则:",
                "  只引用上面出现过的编号; 编造的编号会被丢弃;",
                "  close 只针对「还开着」的那些; 名单里没有的不要写;",
                "  同一件事不要写两遍; 这条约定还开着就**不要**写进 close。",
            ])

        if phase == PHASE_ATTRIBUTE:
            return "\n".join([
                "输出 JSON（不要任何解释文字, 不要 ```json 代码块）:",
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
                "    hint   —— 【本轮新节点】里那句自然称呼（写了就顺手记进别名, 没有就省略）;",
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
                "输出 JSON（不要任何解释文字, 不要 ```json 代码块）:",
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

    def parse_round_a(self, raw: Any, *, seq_set: set[int] | None = None,
                      on_mind_out: list | None = None
                      ) -> tuple[list[dict], ValidationResult]:
        """Round A: `{"episodes": [...], "on_mind": "…"}` → 规范化条目列表。

        `seq_set`（T14）: 本段**事件 seq 全集**——`event_seq` / `verbatim` 索引
        的 ⊆ 校验基准（与 `parse_round_b` 的 `episode_ids` 同思路:
        引用纪律在 parse 层, 不在 prompt 层）。`None` = 不校验（老调用方/单测）。

        `on_mind_out`（⭐ N4a）: 可选传出参数 —— 收下她此刻那句心境（`None` = 本次
        **没提**，与"空串 = 清空"是两件事）。⚠️ 用列表传出而不改返回签名（同
        `recall.mode_out` / `why_out` 的手法: 现有调用方与单测零改动）。
        """
        errors: list[str] = []
        warnings: list[str] = []
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
            item, item_errs, item_warns = _clean_episode(e, i, seq_set)
            errors.extend(item_errs)
            warnings.extend(item_warns)
            if item is not None:
                out.append(item)
        if on_mind_out is not None and "on_mind" in raw:
            val = raw.get("on_mind")
            if val is None:
                warnings.append("on_mind 是 null（当**没提**处理, 保持上次那句）")
            elif not isinstance(val, str):
                warnings.append(f"on_mind 必须是字符串（丢弃）: {type(val).__name__}")
            elif len(val.strip()) > ON_MIND_MAX:
                warnings.append(f"on_mind 超过 {ON_MIND_MAX} 字（收下但请写短）")
                on_mind_out.append(val.strip())
            else:
                on_mind_out.append(val.strip())
        return out, ValidationResult(tuple(errors), tuple(warnings))

    def parse_close(self, raw: Any) -> tuple[list[dict], ValidationResult]:
        """R4 收口: `{"add": […], "close": […]}` → 归一化行。

        **只做形状校验**（键在不在 / 是不是数组 / 值域 / 必填字段）。
        "那个编号存不存在""这条还开着吗"是**世界校验** —— 归执行器
        （`revise.apply_closures`），那里**剔掉 + 记账、不拒整包**：
        形状错重试有用（模型没按契约说话），"看错了世界"重试大概率还是错。

        ⚠️ 与 `parse_round_b` 把引用错误当 `errors` 的口径**故意不同**（2026-09-25 定）；
        那里的引用是本轮渲染出来的闭集，这里的 `refs` 是"这一段的经历"，
        指错更像"它记错了"而不是"它没读契约"。

        Returns: `(rows, ValidationResult)` —— `errors` 非空 = **整包拒 + 带反馈重试**。
        行形状: `{"action": "add", "text", "refs", "due"?}`
                `{"action": "close", "id", "state", "afterwards", "refs"?}`
        """
        errors: list[str] = []
        warnings: list[str] = []
        if not isinstance(raw, dict):
            return [], ValidationResult(errors=("收口轮输出必须是 JSON 对象",))

        out: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for key in ("add", "close"):
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
                item = (_clean_add(row, i, errors) if key == "add"
                        else _clean_close(row, i, errors))
                if item is None:
                    continue
                mark = (key, item.get("id") or item.get("text") or "")
                if mark in seen:
                    warnings.append(f"{key}[{i}] 重复（只留第一条）: {mark[1]!r}")
                    continue
                seen.add(mark)
                out.append(item)
        return out, ValidationResult(tuple(errors), tuple(warnings))

    def parse_group(self, raw: Any, *, block_ids: set[str]
                    ) -> tuple[list[dict], ValidationResult]:
        """L2-a 分群（N7）: `{"attach": […], "new": […]}` → 归一化行。

        **只做形状 + 闭集校验**（键在不在 / 是不是数组 / 必填 / 块的把手来自本轮名单 /
        ⭐ **每个块恰好一次归属**）。"那个类名存不存在"是**世界校验** ⇒ 归执行器
        （`groups.apply_groups`）**剔掉 + 记账、不拒整包** —— 同 `parse_close` 的口径:
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
        """Round B: `{"decisions": [...], "links": [...], "evidence": [...],
        "affection_exp_delta": n}`。

        episode_ids: 本轮 Round A 产出的真实 episode id 集（引用检查）。
        target_ids: **可被 `touch`/`update` 的**本地 id 集（u0001..; 只有看法）。
        link_ids: **可出现在 `links` 两端的**本地 id 集（看法 ∪ **承诺**）。
            ⚠️ 两个集合**故意不同**（2026-09-25, §5.1/§9-13）: 承诺也是"稳定下来的东西"
            ⇒ R2 要看得见它（才能写出 `supports`/`evolved_from`），但它**不是看法**
            ⇒ 不能被 `touch`/`update`（那句"这条经历支撑这条承诺"是 `formed_by` 的活,
            而且承诺的正文在固化那一刻就写死了）。`None` → 退化成 `target_ids`
            （老调用方/单测不必改）。

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
                    # ⚠️ 措辞带上"承诺要用 links"—— 2026-09-25 起 `target_ids` 只含
                    # **看法**（belief/experience），而 promise 会出现在**渲染列表**里
                    # ⇒ 模型完全可能 touch 它。这条消息是给它的指路牌。
                    errors.append(f"decisions[{i}].target 不在可 touch/update 的列表内"
                                  f"（只有看法; 承诺不是看法 —— 用 links 连它）: {target!r}")
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
                    if "epistemic" in patch:
                        errors.append(f"decisions[{i}]: patch 不得含 epistemic")
                        continue
                    item["patch"] = patch
            else:  # add
                kind = str(row.get("kind", "belief")).strip()
                # ⚠️ **只有 belief**（2026-09-25, DESIGN_GRAPH_V4 §5.1）: `experience`
                # 已定名 **玩家画像专用**（"关于老师的事"），写者只有第 1 轮 ⇒ 这一轮
                # 想写"反复出现的模式"就写成 **belief 的模式句**（§9-10）。
                if kind != "belief":
                    errors.append(f"decisions[{i}].kind 非法: {kind!r}（只有 belief ——"
                                  " 模式也写成 belief 的模式句; experience 是玩家画像专用，"
                                  " 由第 1 轮产出）")
                    continue
                item["kind"] = kind
                for f in ("subject", "text", "example", "tags",
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
#: ⚠️ 别加 `about`（那是第 3 轮的活, 走候选表映射）· 别加 `formed_by`/`from`/`to`
#: （承诺固化时引擎自己写）· 别加 `source`（已删）。
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
                              "（承诺也得先在列表里出现过; 本轮新建的连不上）")
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


def _clean_add(row: dict, i: int, errors: list[str]) -> dict | None:
    """`add` 一行（R4）: 正文短语 + ≥1 个引用; `due` 可选。"""
    text = str(row.get("text") or "").strip()
    if not text:
        errors.append(f"add[{i}] 缺 text")
        return None
    refs = [str(r).strip() for r in row.get("refs") or []
            if isinstance(r, (str, int)) and str(r).strip()]
    if not refs:
        errors.append(f"add[{i}] 缺 refs（至少一个：这条约定是说在哪件事里的）")
        return None
    item: dict = {"action": "add", "text": text, "refs": refs}
    due = str(row.get("due") or "").strip()
    if due:
        item["due"] = due
    return item


def _clean_close(row: dict, i: int, errors: list[str]) -> dict | None:
    """`close` 一行（R4）: 编号 + 结局 + **`afterwards`**（"这件事后来怎么了"）· `refs` 可选。

    ⚠️ 早先那个字段叫 `reason` —— 用户 2026-09-25: *"reason 太理性了"*。
    """
    nid = str(row.get("id") or "").strip()
    if not nid:
        errors.append(f"close[{i}] 缺 id")
        return None
    state = str(row.get("state") or "").strip()
    if state not in PROMISE_OUTCOMES:
        errors.append(f"close[{i}].state 非法: {state!r}"
                      f"（可用: {', '.join(PROMISE_OUTCOMES)}）")
        return None
    afterwards = str(row.get("afterwards") or "").strip()
    if not afterwards:
        errors.append(f"close[{i}] 缺 afterwards —— 一句话说这件事后来怎么了（必填）")
        return None
    item: dict = {"action": "close", "id": nid, "state": state,
                  "afterwards": afterwards}
    #: `refs` = **finish episode**（了结它的那条经历）—— 可选（失约那种"没有那一刻"就不给）
    refs = [str(r).strip() for r in row.get("refs") or []
            if isinstance(r, (str, int)) and str(r).strip()]
    if refs:
        item["refs"] = refs
    return item


def _clean_episode(e: Any, i: int, seq_set: set[int] | None = None
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
    kind = str(e.get("kind", "episode")).strip()
    if kind == "episode":
        item, errors, warnings = _clean_episode_item(
            e, i, errors, warnings, seq_set)
        if item is not None:
            item["kind"] = "episode"
        return item, errors, warnings
    if kind == "experience":
        # 玩家画像条目（MMT 专则, 2026-09-02）: text 必填, subject 引擎固定 player
        text = _read_text(e, i, warnings)
        if not text:
            return None, [f"episodes[{i}]: kind=experience（玩家画像）必须填 text"], []
        item: dict = {"kind": "experience", "text": text,
                      "subject": PLAYER_SUBJECT}
        # 画像条目无 episode 载体——原话直接存（两条通道: 文本 / 索引）
        _fill_verbatim(item, e, i, warnings, seq_set)
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
    return None, [f"episodes[{i}].kind 非法: {kind!r}（episode|experience）"], []


def _norm_index(raw: Any) -> str | None:
    """索引项 → 规范串 `"28.3"` / `"28.p"` / `"28"`（坏项 → None）。"""
    from contract.timeline_index import parse_index
    got = parse_index(raw) if isinstance(raw, str) else (
        (raw, "") if isinstance(raw, int) and not isinstance(raw, bool) else None)
    if got is None:
        return None
    seq, rec = got
    return f"{seq}.{rec}" if rec != "" else str(seq)


def _clean_seq_list(raw: Any, seq_set: set[int] | None, *,
                    label: str, warnings: list[str],
                    record_level: bool) -> list[str]:
    """索引数组清洗 —— **坏项逐条丢弃**（不废整包, 与 `parse_index_list` 同纪律）。

    `record_level=False`（板指针 `event_seq`）: 只收事件级 `"28"`, 记录级
    `"28.3"` 视为写错（它的 seq 部分仍然认, 但会记一条 warning 提醒）。
    `record_level=True`（`verbatim` 索引通道）: 收 `"28.3"` / `"28.p"` / `"28"`。

    `seq_set` 非空时做 ⊆ 校验——**抄不存在的编号 → 丢弃**（与 `evidence.quote`
    的"逐字来自时间线"同一套防幻觉思路, 但这里是真的实现了的）。
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
            warnings.append(f"{label} 的 {norm!r} 不在本段时间线里——丢弃")
            continue
        if norm not in out:
            out.append(norm)
    if bad:
        warnings.append(f"{label}: {bad} 个索引不可用（已丢弃）")
    return out


def _clean_span(raw: Any, seq_set: set[int] | None, *, label: str,
                warnings: list[str]) -> list[int] | None:
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
        warnings.append(f"{label} 不是数组——丢弃")
        return None
    if not items:
        warnings.append(f"{label} 是空数组——丢弃")
        return None
    if len(items) > 2:
        warnings.append(f"{label} 给了 {len(items)} 个端点——只取首尾")
        items = [items[0], items[-1]]
    seqs: list[int] = []
    for it in items:
        norm = _norm_index(it)
        if norm is None:
            warnings.append(f"{label} 的 {it!r} 不是合法编号——丢弃整个区间")
            return None
        seq = parse_index(norm)[0]
        if "." in norm:
            warnings.append(f"{label} 收了记录级索引 {norm!r}——已按事件 {seq} 收下")
        seqs.append(seq)
    if len(seqs) == 1:
        seqs.append(seqs[0])                      # 单值 ⇒ 退化成一块
    lo, hi = seqs
    if lo > hi:
        warnings.append(f"{label} 起止反了（{lo} > {hi}）——丢弃（不自动交换）")
        return None
    missing = [s for s in (lo, hi) if seq_set is not None and s not in seq_set]
    if missing:
        warnings.append(f"{label} 的端点 {missing} 不在本段时间线里——丢弃")
        return None
    return [lo, hi]


def _fill_verbatim(item: dict, e: dict, i: int, warnings: list[str],
                   seq_set: set[int] | None) -> None:
    """`verbatim` 的**两条通道**（T14, 用户 2026-09-15 裁决: 保文本通道）。

    ① `"verbatim": ["28.3", "20.p"]` —— 索引通道: 引擎据此取回**逐字原文**
    ② `"verbatim": "…"`             —— 文本通道: 原话逐字复制（禁改写）
    ③ 另可显式给 `"verbatim_seq": [...]`（与①等价, 两条并存时合并去重）

    落库分工: `verbatim_seq` = 索引（可重解析 / 板归属）; `verbatim` = 文本。
    **文本由引擎在 `digest.py` 解析索引后回填**——parse 层拿不到事件流。

    两条并存时的顺序: `verbatim` 列表在先、显式 `verbatim_seq` 在后
    （schema 里 `verbatim` 是主字段, `verbatim_seq` 是它的显式别名）。
    """
    seqs: list[str] = []
    for key in ("verbatim", "verbatim_seq"):
        v = e.get(key)
        if isinstance(v, (list, tuple)):
            seqs.extend(_clean_seq_list(v, seq_set, label=f"episodes[{i}].{key}",
                                        warnings=warnings, record_level=True))
        elif key == "verbatim_seq" and v is not None:
            warnings.append(f"episodes[{i}].verbatim_seq 必须是数组——忽略")
    if seqs:
        item["verbatim_seq"] = list(dict.fromkeys(seqs))
    raw_text = e.get("verbatim")
    if isinstance(raw_text, str) and raw_text.strip():
        item["verbatim"] = raw_text.strip()


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
                        seq_set: set[int] | None = None
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
    # ⭐ 位置 = **区间**（N3, 2026-09-29）: `span: [28, 30]` = 本条覆盖从 28 到 30 **这一整段**。
    # 为什么不让 LLM 逐块列: 真机实测"挑点"必然漏 —— 覆盖率只有 **67.9%**
    # （218 条内容事件里 70 条没进任何记忆），缺口动辄 12~18 处；
    # 而人的"那次"本来就是**一段**，不是若干个点。展开在 `digest._expand_spans`。
    span = _clean_span(e.get("span"), seq_set, label=f"episodes[{i}].span",
                       warnings=warnings)
    if span is not None:
        item["span"] = span
    else:
        # 旧形状 `event_seq: ["28","30"]` **仍收**（防契约漂移时整条丢位置），
        # ⚠️ 但**不展开成区间** —— 那是她**自己挑的点**, 展开等于替她加上她没声称的事件
        # （宁缺勿错）。只告警, 让契约漂移**可见**。
        seqs = _clean_seq_list(e.get("event_seq"), seq_set,
                               label=f"episodes[{i}].event_seq",
                               warnings=warnings, record_level=False)
        if seqs:
            item["event_seq"] = [int(s) for s in seqs]
            warnings.append(f"episodes[{i}] 用的是旧形状 event_seq（逐点挑选）——"
                            f"契约已改成 span: [起, 止]（区间，引擎负责展开）")
    # verbatim 两条通道（索引 / 文本）
    _fill_verbatim(item, e, i, warnings, seq_set)
    tags = [t for t in e.get("tags", []) if isinstance(t, str) and t.strip()][:MAX_TAGS]
    if tags:
        item["tags"] = tags
    else:
        warnings.append(f"episodes[{i}] 缺 tags（检索导向 1-4 个）")
    # 归属线索（§8.2, D1）: `about_hint` = **自然名字**, 空/坏 → 不落字段。
    # ⚠️ 它**不落库**（引擎在 `digest._create_a_nodes` 里摘走, 传给第 3 轮做映射）——
    # 所以这里只负责清洗成一个干净字符串, 不是节点字段。
    hint = e.get("about_hint")
    if isinstance(hint, str) and hint.strip():
        item["about_hint"] = hint.strip()
    # 物品台账（§3.1, D1）: 裸字符串数组, 截断到 MAX_ITEMS; 空 → 不落字段。
    raw_items = e.get("items")
    if isinstance(raw_items, list):
        got = [x.strip() for x in raw_items if isinstance(x, str) and x.strip()]
        if len(got) > MAX_ITEMS:
            warnings.append(f"episodes[{i}].items 超过 {MAX_ITEMS} 件——截断")
        if got[:MAX_ITEMS]:
            item["items"] = got[:MAX_ITEMS]
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
    epi = str(e.get("epistemic", "observed_fact")).strip()
    if epi == "reported_fact":
        obs = e.get("observer")
        if not (isinstance(obs, str) and obs.strip()):
            return None, errors + [f"episodes[{i}]: reported_fact 必须带 observer（转述者）"], warnings
        item["epistemic"] = "reported_fact"
        item["observer"] = obs.strip()
    else:
        item["epistemic"] = "observed_fact"
    return item, errors, warnings


def _nonempty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


#: 默认注册表实例（板块 4 引擎编排消费）
digest_registry = DigestRegistry()
