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
    STAGE_EXIT,
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


def build_schema(registry: ActionRegistry, *, action_list: bool = False) -> str:
    """生成该域给 LLM 的动作 schema（输入层裁剪）。

    action_list=True（MMT 域, 2026-09-02 消息流协议）: 输出"消息流"格式——
    聊天 = 消息序列, text 单元说话 + action 单元操作任意交错（话→图→话）。
    其他域（story/IDE）保持单动作输出。示例只给结构骨架——外壳字段以各
    动作声明为准。
    """
    names = registry.action_names()
    if not names:
        return "（该动作域尚未注册任何动作）"

    union: set[str] = set()
    for name in names:
        union |= set(registry.spec(name).prompt_fields)

    if action_list:
        lines = [
            "你以单个 JSON 对象输出本轮**消息流**（2026-09-02 协议, 聊天 = 消息序列）:",
            '    {"messages": [消息1, 消息2, ...]}',
            "单元类型:",
            '    {"text": "角色说的话"}              —— text 单元: 说话（任意条数）',
            '    {"action": "<动作名>", "payload": {...}}  —— action 单元: 需要程序',
            "        执行的操作（可任意夹在 text 之间——话→图→话 的节奏没问题）",
            "text 单元不是动作（程序直接渲染为消息气泡）; action 单元字段如下。",
            "",
        ]
    else:
        lines = ["你必须以单个 JSON 对象输出一个动作。", ""]
    lines.append("外壳字段:")
    for f in sorted(union):
        desc = _SHELL_FIELD_DESCRIPTIONS.get(f, "")
        lines.append(f"  - {f}: {desc}".rstrip())
    lines.append("")
    lines.append("可用动作:")
    for name in names:
        spec = registry.spec(name)
        note = _APPROVAL_NOTES.get(spec.approval, spec.approval)
        lines.append(f"  - {name}  [{note}]")
        lines.append(f"      外壳字段: {', '.join(sorted(spec.prompt_fields))}")
        if spec.payload_schema:
            lines.append(f"      payload: {spec.payload_schema}")
        else:
            lines.append("      payload: （未提供描述）")
    lines.append("")
    if action_list:
        lines.append(
            '消息流示例: {"messages": [{"text": "老师你看这个！"}, '
            '{"action": "mmt_send_media", "payload": {"image": "天台拍到的夕阳"}}, '
            '{"text": "是我特意拍的…好看吧？"}]}'
        )
        lines.append("action 单元按顺序执行并渲染（text 单元直接渲染为气泡）; "
                     "mmt_trigger_bond_story 独占操作（只能有它一个 action 单元, "
                     "text 邀约话可放它前面）;")
        lines.append("mmt_inspect_character 单独一轮（静默推理, 不与 text/其他动作混排）。")
    else:
        lines.append('格式示例: {"action": "<动作名>", "payload": {...}}'
                     '（外壳字段以各动作声明为准）')
    return "\n".join(lines)


def export_definitions(registry: ActionRegistry) -> dict[str, Any]:
    """导出该域的动作定义（纯数据，JSON 兼容）。

    A 方案的数据面：Python 端是唯一执行引擎，但定义本身与语言无关，
    未来 JS/WebLLM 端可消费同一份数据生成自己的渲染/校验。
    """
    actions = []
    for name in registry.action_names():
        spec = registry.spec(name)
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


def build_record_schema(*, with_examples: bool = True, char_id: str = "igusa_haruka",
                        char_display: str = "") -> str:
    """渲染 **VN 记录流契约**（LLM 可见）——`build_schema` 的第三种形态。

    与"单动作 JSON"（story 旧契约）和"messages 消息流"（MMT, `action_list=True`）并列。
    设计: `docs/DESIGN_VN_UPGRADE.md` §2（文法）/ §10.4（`art` 预告制）。
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
         f"本章纪念时刻的预告（本轮首条；一章至多一次）——**画面里必须有 {char_id} 本人**"
         "（写她的样子与动作; 只写风景/空镜/物件不合格）"),
        (STAGE_MEMORIAL, '"（触发句）"', "纪念触发；其后到本轮结束为纪念正文"),
        (STAGE_END, '"（收尾字段，可留空）"',
         "收尾——**这里不是老师的话**，是本轮最后的收束文字（旁白/余韵）；"
         "留空字符串 = 直接黑屏收尾（本轮最后一条）"),
        (STAGE_EXIT, '""', "仅纪念域（可留空）"),
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
        "1. 一行一条完整记录；字段只有那两个；text 除 stage=end / exit 外必填。",
        '2. text 里的半角双引号与反斜杠必须转义（写成 \\" 与 \\\\）——这是最常见的错误。',
        "3. 老师要说话就直接写 sensei 记录（连续 1~%d 条）——那几句就是玩家会看到、会挑的话。"
        % MAX_SENSEI_RUN,
        "4. 本章第一条必须是 stage=switch（交代开场景）；若本轮含纪念，"
        "则 stage=art 紧跟其后成为本轮首条。",
        "5. stage=end / exit 必须是本轮最后一条；stage=memorial 之后到本轮结束都属于纪念正文。",
        "6. 篇幅：一轮约 %d 行（写下你觉得完整的一段戏）。" % 40,
    ]
    if with_examples:
        lines += [
            "",
            "示例（第 3 行演示转义引号；连续两条 sensei = 一个群）:",
            '    {"stage": "switch", "text": "放学后的天台"}',
            f'    {{"character": "{char_id}", "text": "……老师，你、你来了。"}}',
            f'    {{"character": "{char_id}", "text": "他说 \\"别担心\\" 的时候，我、我却差点搞砸。"}}',
            '    {"character": "sensei", "text": "我想和你一起面对。"}',
            '    {"character": "sensei", "text": "你不想让我陪着吗？"}',
            f'    {{"character": "{char_id}", "text": "……！！"}}',
            '    {"character": "narrator", "text": "（她把手藏到身后，又慢慢拿出来。）"}',
            '    {"stage": "memorial", "text": "（她忽然抬起头，朝我笑了一下。）"}',
            f'    {{"character": "{char_id}", "text": "老师，谢谢你今天来。"}}',
        ]
    return "\n".join(lines)


def build_digest_schema() -> str:
    """digest 输出的 JSON 结构描述（数据 schema, 单源真值）。

    与动作契约不同: 这不是动作（无执行语义）, 是**数据产出** schema——
    Brain digest（core/brain/consolidation.py）的 LLM 输出格式。
    digest.md 的 `{{output_schema}}` 占位由此渲染——改字段只改这一处,
    prompt 描述与校验结构同步（DESIGN_BRAIN.md §4）。

    边界: 本函数管"结构/类型/边界"; 内容净化（significance clamp / tags 过滤 /
    空 content 丢弃）是清洗业务规则, 在 consolidation._clean_output 实现。
    """
    lines = [
        "输出 JSON（不要任何解释文字）:",
        '    {"summary": "...", "facts": [...], "beliefs": [...], "relations": [...], "affection_exp_delta": 0}',
        "字段说明:",
        "  - summary: 一句话主线（str, 整体视角, 不是只写新增）",
        "  - facts: 关键事实列表, 每项 {content: str, significance: 0~1 数字, tags: 可选 1~3 关键词}",
        "  - beliefs: 抽象信念列表, 每项 {content: str, significance: 0~1 数字}",
        "  - relations: 关系变化列表, 每项 {subject: str, object: str, relation: str, note: 可选 str}",
        "  - affection_exp_delta: 本段互动让角色对玩家好感增加的分数（int 0~100; 无变化 → 0）",
        "没有值得记的内容 → 对应字段输出空数组（合法）。",
    ]
    return "\n".join(lines)
