"""契约渲染与导出 — 输入层 + A 方案数据面。

build_schema():       把动作域渲染成 LLM 可见的动作 schema（输入层裁剪）。
                      AI 只看到它需要的字段——运行时动作域的输出中不会出现 sources/basis。
export_definitions(): 把动作域导出为纯数据（A 方案的数据面），供 JS/WebLLM 端消费。

依赖: constants（审批常量）、registry（遍历注册表公共方法）。
"""

from __future__ import annotations

from typing import Any

from contract.constants import APPROVAL_AUTO, APPROVAL_NEVER, APPROVAL_REQUIRED
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
