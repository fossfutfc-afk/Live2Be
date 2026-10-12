"""契约渲染与导出 — 输入层 + A 方案数据面。

build_schema():       把动作域渲染成 LLM 可见的动作 schema（输入层裁剪）。
                      AI 只看到它需要的字段——运行时动作域的输出中不会出现 sources/basis。
export_definitions(): 把动作域导出为纯数据（A 方案的数据面），供 JS/WebLLM 端消费。

依赖: constants（审批常量）、registry（遍历注册表公共方法）。
"""

from __future__ import annotations

from typing import Any

from contract.constants import APPROVAL_AUTO, APPROVAL_NEVER, APPROVAL_REQUIRED
from contract.records import (
    CHARACTER_NARRATOR,
    CHARACTER_SENSEI,
    KIND_CHARACTER,
    KIND_STAGE,
    MAX_SENSEI_RUN,
    STAGE_ART,
    STAGE_END,
    STAGE_MEMORIAL,
    STAGE_SWITCH,
)
from contract.registry import ActionRegistry

# 外壳字段的说明文本（build_schema 渲染用）
_SHELL_FIELD_DESCRIPTIONS = {
    "action": "动作名（从下方可用动作中精确选择）",
    "summary": "给用户看的一句话说明",
    "reply": "对用户的话：给用户看的完整回复/解释（可选, 区别于 summary 的一句话）",
    "payload": "动作参数（见各动作的 payload 说明）",
    "sources": "事实依据：来源 URL 列表。宁缺勿错——无可靠依据时留空，改在 basis 说明决策依据；请勿编造",
    "basis": "决策依据：字符串数组（列表），如 [\"用户要求整理资料\", \"宁缺勿错\"]，每项一句话；无依据则留空 []，不要写成单个字符串",
}

_APPROVAL_NOTES = {
    APPROVAL_REQUIRED: "需用户批准",
    APPROVAL_AUTO: "自动执行",
    APPROVAL_NEVER: "直接执行",
}


def _numbered(items: tuple[str, ...]) -> list[str]:
    """硬规则 → 编号行。**编号由位置算，不手写**。

    从前三个渲染器各自把 `"1." "2." …` 写死在字符串里 ⇒ 中间插一条就要把后面
    全部改一遍（而且很容易漏一个数字，让 prompt 里的编号跳号）。规则现在是
    数据（元组），加一条只管往元组里写。
    """
    return [f"{i}. {t}" for i, t in enumerate(items, 1)]


def build_schema(registry: ActionRegistry) -> str:
    """生成该域给 LLM 的动作 schema（输入层裁剪）—— **单动作形态**。

    用于 story / IDE 这类"一轮一个动作"的域。⚠️ **MMT 不用它**（⑥-2f 起）：
    手机聊天走 `build_line_schema`（一行一条 JSON 的行流），旧 `action_list=True`
    的"messages 消息流"分支已随 `{"messages":[…]}` 协议**整段删除**。
    示例只给结构骨架——外壳字段以各动作声明为准。
    """
    specs = registry.specs()
    if not specs:
        return "（该动作域尚未注册任何动作）"

    union: set[str] = set()
    for _name, spec in specs:
        union |= set(spec.prompt_fields)

    lines = ["你必须以单个 JSON 对象输出一个动作。", ""]
    lines.append("外壳字段:")
    for f in sorted(union):
        desc = _SHELL_FIELD_DESCRIPTIONS.get(f, "")
        lines.append(f"  - {f}: {desc}".rstrip())
    lines.append("")
    lines.append("可用动作:")
    for name, spec in specs:
        note = _APPROVAL_NOTES.get(spec.approval, spec.approval)
        lines.append(f"  - {name}  [{note}]")
        lines.append(f"      外壳字段: {', '.join(sorted(spec.prompt_fields))}")
        if spec.payload_schema:
            lines.append(f"      payload: {spec.payload_schema}")
        else:
            lines.append("      payload: （未提供描述）")
    lines.append("")
    lines.append('格式示例: {"action": "<动作名>", "payload": {...}}'
                 '（外壳字段以各动作声明为准）')
    return "\n".join(lines)


def export_definitions(registry: ActionRegistry) -> dict[str, Any]:
    """导出该域的动作定义（纯数据，JSON 兼容）。

    A 方案的数据面：Python 端是唯一执行引擎，但定义本身与语言无关，
    未来 JS/WebLLM 端可消费同一份数据生成自己的渲染/校验。
    """
    actions = []
    for name, spec in registry.specs():
        actions.append({
            "action": name,
            "approval": spec.approval,
            "prompt_fields": sorted(spec.prompt_fields),
            "payload_schema": spec.payload_schema,
        })
    return {
        "domain": registry.domain,
        "actions": actions,
    }


#: MMT 行流的硬规则。⚠️ **编号不在这里** —— 由 `_numbered()` 按位置算。
_MMT_RULES: tuple[str, ...] = (
    "一行一个完整 JSON 对象；三类行可以任意交错（一行接一行地说下去没问题）。",
    "**气泡粒度由你定**：想连发就写多条消息行（一条行 = 独立的一条手机消息）——"
    "**一条行可以只是半句话**（不必凑成完整句子，行末也不必加标点）。",
    '话里的半角双引号与反斜杠必须转义（写成 \\" 与 \\\\）——这是最常见的错误。',
    "`mmt_trigger_bond_story` 是模式切换：它必须是**唯一**的操作行，"
    "见面的话写在它**前面**的消息行里。",
    "`mmt_look` 是那一轮**唯一的操作行**，并且放在**最后一行**："
    "想说的话（\"唔……我找找看\"）写在它**前面**的消息行里——"
    "翻到的东西要等它跑完才回到你手上。",
    "本轮至少要有一条行（说话或做事）——**想起行只是记账，不代替说话**。",
)


def build_line_schema(registry: ActionRegistry, *, with_examples: bool = True) -> str:
    """渲染 **MMT 行流契约**（LLM 可见）——`build_schema` 的第四种形态（⑥-2a）。

    三个并列形态：单动作 JSON（story/IDE, `build_schema`）· 记录流（VN,
    `build_record_schema`）· **行流（MMT, 本函数）**。
    设计: `docs/DESIGN_STREAM_CONTRACT.md` §1（契约形式六条）/ §2（两域对照）/
    §10.2 B1·B3。

    与 `build_record_schema` 的结构差别：记录文法**不依赖动作注册表**（所以那个函数
    是独立入口），而行流的**操作行**要用注册表里的动作 ⇒ 本函数收 `registry`
    （新增动作**自动进 prompt**，不手写清单）。

    ⚠️ 旧的 `build_schema(action_list=True)`（`{"messages":[…]}` 消息流）**已整段删除**
    （⑥-2f："旧协议统统改掉"）——三个形态现在是: 单动作 JSON（story/IDE）· 行流
    （MMT, 本函数）· 记录流（VN, `build_record_schema`）。

    文案纪律（同用户裁决 #24）：不写"不要写 X 字段"式负面提醒；示范里戏词不包「」。
    """
    lines = [
        "你以**一行一条 JSON** 的形式输出本轮内容（一行一条，不要数组、不要围栏）:",
        "",
        "三类行（看行里的键就知道是哪一类）:",
        '    {"text": "角色说的话"}                     —— **消息行**: 一条行 = 一个气泡',
        '    {"action": "<动作名>", "payload": {...}}   —— **操作行**: 不上屏, 程序去执行',
        '    {"noticed": "事件名"}                      —— **想起行**: 不上屏; 发现"这件事'
        '和我记得的某一条是同一件事"时记一笔',
        "",
        "硬规则（形状不对的行会被丢掉; 操作行不对会被要求重发）:",
        *_numbered(_MMT_RULES),
        "",
        "可用操作:",
    ]
    for name, spec in registry.prompt_specs():          # ⭐ 封印的动作不进 prompt（`in_prompt`）
        note = _APPROVAL_NOTES.get(spec.approval, spec.approval)
        lines.append(f"  - {name}  [{note}]")
        if spec.payload_schema:
            lines.append(f"      payload: {spec.payload_schema}")
        else:
            lines.append("      payload: （未提供描述）")
    lines.append("")
    if with_examples:
        lines += [
            "示例（第 2 行演示转义引号）:",
            '    {"text": "老师你看这个！"}',
            '    {"text": "他说 \\"好看\\" 的时候，我才真的放心了。"}',
            "",
            "连发那一种（一次回复四行 = 四个气泡；每条不必是完整句子、行末不必加标点）:",
            '    {"text": "唔……"}',
            '    {"text": "今天阿露又搞了个奇怪的企划"}',
            '    {"text": "然后我们全都去收拾烂摊子了"}',
            '    {"text": "不过，其实还挺开心的！"}',
            "",
            "触发羁绊剧情那一轮（见面的话在前, trigger 是唯一操作行）:",
            '    {"text": "诶嘿～老师，我正好也在这一节车厢哦？"}',
            '    {"action": "mmt_trigger_bond_story",'
            ' "payload": {"chapter_title": "电车上的零食"}}',
            "",
            # ⭐ "先说话再翻"是**两块**（= 两跳）: look 独占它那一轮（最后一行）, 程序把
            # 结果还给她之后她才接着说 —— 写成一块里 look + **翻完之后的话** = 教了
            # 检查器会判 `mmt.exclusive-violation` 的形状（示例才是形状的来源 §8）。
            "先说话再翻那一轮（`mmt_look` 是**唯一的操作行**、放在**最后一行**）:",
            '    {"text": "唔……等一下，我找找看"}',
            '    {"action": "mmt_look",'
            ' "payload": {"clue": "苔藓 && 杂草", "when": "last 1 week"}}',
            "",
            "翻到之后（程序把翻到的东西还给你，你接着这一轮说）:",
            '    {"text": "唔……找到了"}',
            '    {"text": "原来就是那次啊"}',
            "",
            "想起了某条旧事那一轮（**可选**——想不起来就正常聊）:",
            '    {"noticed": "瓦片缝里的苔藓"}',
            '    {"text": "……等等"}',
            '    {"text": "这不就跟上次屋顶上那盆一样吗"}',
        ]
    return "\n".join(lines)


#: 一轮戏的篇幅目标（行）—— 只写进 prompt 当参考，引擎不校验。
_VN_TURN_LINES = 40

#: VN 记录流的硬规则。⚠️ 编号不在这里（`_numbered()` 按位置算）；
#: 两条嵌了常量: 老师连续条数上限、篇幅行数。
_VN_RULES: tuple[str, ...] = (
    "一行一条完整记录；字段只有那两个；text 除 stage=end 外必填。",
    'text 里的半角双引号与反斜杠必须转义（写成 \\" 与 \\\\）——这是最常见的错误。',
    f"老师要说话就直接写 sensei 记录（连续 1~{MAX_SENSEI_RUN} 条）"
    "——那几句就是玩家会看到、会挑的话。",
    "本章第一条必须是 stage=switch（交代开场地点）。**含纪念的那一轮："
    "art 放最前（switch 紧随其后）**——art 与 memorial **必须同轮成对**："
    "写了 art 就要写 memorial，写了 memorial 就要有 art。",
    "stage=end 必须是本轮最后一条；stage=memorial 之后到本轮结束都属于纪念正文。",
    f"篇幅：一轮约 {_VN_TURN_LINES} 行（写下你觉得完整的一段戏）。",
)


def build_record_schema(*, with_examples: bool = True, char_id: str = "igusa_haruka",
                        char_display: str = "") -> str:
    """渲染 **VN 记录流契约**（LLM 可见）——`build_schema` 的第三种形态。

    与"单动作 JSON"（story/IDE）和"行流"（MMT, `build_line_schema`）并列。
    设计: `docs/DESIGN_STREAM_CONTRACT.md` §2（文法）/ §10.4（`art` 预告制）。
    文案单源: 取值与约束全部取自 `contract.records` 常量。

    不进 `build_schema()` 是因为记录文法**不依赖动作注册表**（参数是角色 id 与状态约束，
    不是 ActionSpec 集合）——保留独立入口，语义更清楚（§8.2 已按此对齐）。

    文案纪律（2026-09-10 用户裁决 #24）:
    - **不写"不要写 X 字段"这类负面提醒**（白熊效应: 不说模型不知道, 一说反而幻觉 + 废 token）;
    - 台词**不包引号**（范例里也不出现「」，直接告诉模型写纯文本）;
    - 示例里的角色取值 = **真实 id**（引擎按会话传入, 默认值即本项目角色）。

    Args:
        with_examples: 是否附 few-shot 示例（含**转义引号**示范——实测唯一真实错误源）。
        char_id: 本场角色的记录取值（引擎传真实 id）。
        char_display: 角色显示名（非空则写进取值说明，便于模型对上号）。
    """
    char_note = (f"你自己（{char_display.strip()}）——本场只有你一个角色" if char_display.strip()
                 else "你自己——本场只有你一个角色")
    char_shapes = [
        (char_id, '"你说的台词，纯文本"', f"{char_note}；记录里写 `{char_id}`"),
        (CHARACTER_NARRATOR, '"（旁白 / 短动作）"', "叙述（稀有：一整段 0~3 条）"),
        (CHARACTER_SENSEI, '"老师此刻会说的一句话"',
         f"老师的话；连续 1~{MAX_SENSEI_RUN} 条 = 一个群（玩家挑一句说）"),
    ]
    stage_shapes = [
        (STAGE_SWITCH, '"目标地点"', "换场（用你自己的话，写具体名词短语）"),
        (STAGE_ART, '"画面意向（1~2 句）"',
         f"**给画师**的画面意向（本轮最前一条；一章至多一次）——**必须与 memorial 同轮成对"
         f"出现**；**画面里必须有 {char_id} 本人**（写她的样子与动作; 只写风景/空镜/物件不合格）"),
        (STAGE_MEMORIAL, '"（转场的那一句）"',
         "纪念进入；**这句会显示给玩家看**，之后到本轮结束都是纪念正文"),
        (STAGE_END, '"（收尾字段，可留空）"',
         "收尾——**这里不是老师的话**，是本轮最后的收束文字（旁白/余韵）；"
         "留空字符串 = 直接黑屏收尾（本轮最后一条）"),
    ]
    lines = [
        "你以**一行一条 JSON 记录**的形式输出本轮内容（一行一条，不要数组、不要围栏）:",
        "",
    ]
    for kind, shapes in ((KIND_CHARACTER, char_shapes), (KIND_STAGE, stage_shapes)):
        lines.append(f"{kind} 取值:")
        for value, text_shape, note in shapes:
            lines.append(f'    {{"{kind}": "{value}", "text": {text_shape}}}   {note}')
        lines.append("")
    lines += [
        "硬规则（违反即被丢弃）:",
        *_numbered(_VN_RULES),
    ]
    if with_examples:
        lines += [
            "",
            "示例（**含纪念的那一轮**；第 3 行演示转义引号；连续两条 sensei = 一个群）:",
            '    {"stage": "art", "text": "她在开满杂草的坡道上回头，夕阳打在脸上，眼里有一点水光"}',
            '    {"stage": "switch", "text": "放学后的天台"}',
            f'    {{"character": "{char_id}", "text": "……老师，你、你来了。"}}',
            f'    {{"character": "{char_id}", "text": "他说 \\"别担心\\" 的时候，我、我却差点搞砸。"}}',
            '    {"character": "sensei", "text": "我想和你一起面对。"}',
            '    {"character": "sensei", "text": "你不想让我陪着吗？"}',
            f'    {{"character": "{char_id}", "text": "……！！"}}',
            '    {"character": "narrator", "text": "（她把手藏到身后，又慢慢拿出来。）"}',
            '    {"stage": "memorial", "text": "（她抬起头，第一次直视我的眼睛。）"}',
            f'    {{"character": "{char_id}", "text": "老师，谢谢你今天来。"}}',
            f'    {{"character": "{char_id}", "text": "……所以，我也可以再撑一会儿。"}}',
        ]
    return "\n".join(lines)

