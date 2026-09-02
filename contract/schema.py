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

    action_list=True（MMT 域, 2026-08-23 定稿）: 输出"动作列表"格式——
    AI 可一次返回多个动作实现"说话→发图→说话"的混合节奏（text_processor
    逐动作切分渲染）。其他域（story/IDE）保持单动作输出。
    """
    names = registry.action_names()
    if not names:
        return "（该动作域尚未注册任何动作）"

    union: set[str] = set()
    for name in names:
        union |= set(registry.spec(name).prompt_fields)

    if action_list:
        lines = [
            "你必须以单个 JSON 对象输出一个动作列表（按顺序执行并渲染）:",
            '    {"actions": [动作1, 动作2, ...]}',
            "每个动作的字段如下。",
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
            '格式示例: {"actions": [{"action": "<动作名>", "summary": "一句话说明", '
            '"payload": {...}}, ...]}'
        )
        lines.append("动作按列表顺序依次执行; mmt_trigger_bond_story 必须独占一轮（模式切换）;")
        lines.append("mmt_inspect_character 不能混入列表（静默推理轮, 单独输出一轮）。")
    else:
        lines.append('格式示例: {"action": "<动作名>", "summary": "一句话说明", "payload": {...}}')
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


def build_digest_schema_v2() -> str:
    """digest v2 输出的 JSON 结构描述（单源真值, AGENT_BRAIN.md §3 Step 1）。

    与 v1 的区别: **新经历统一走 revisions 的 create 动作**（与修订同包——
    引擎 apply_revision_package 一次原子执行; ref 机制让"新 episode 链接新
    belief"成为可能, entries[] 与 revisions[] 双数组做不到——2026-09-02 实现修订）;
    event_seq/ts/segment_id 由引擎分配（LLM 不猜, 防幻觉）; evidence 供罗盘成长。

    校验/执行在 core/brain/wiki_v2/（revise.py 修订契约 + digest.py 管线）;
    本函数只描述结构（prompt 的 {{output_schema}} 占位由此渲染）。
    """
    lines = [
        "输出 JSON（不要任何解释文字）:",
        '    {"revisions": [...], "evidence": [...], "affection_exp_delta": 0}',
        "",
        "revisions: 修订动作数组（新经历 = create, 与修订统一——引擎一次原子执行）:",
        "  - create: 新条目。{action, ref?: \"n1\"(包内引用名, 供后续动作/链接引用), entry: {...}}",
        "    entry 按 kind 填字段（epistemic/significance/tags/links 等; 不要输出 id/ts/event_seq/segment_id——引擎分配）:",
        "    * episode:   {kind, narration(必填), verbatim?(原文逐字), tags?, significance 0~1,",
        "                  epistemic(observed_fact|reported_fact), links?[子图 id], observer?(reported 时必填)}",
        "    * experience:{kind, pattern(必填), subject?(sensei/player/其他), examples?[≤3], tags?,",
        "                  significance 0~1, epistemic(observed_fact), links?}",
        "    * belief:    {kind, content(必填), subject?, growth?, observation?, tags?, significance 0~1,",
        "                  epistemic(inferred_belief), links(必填 ≥1——必须有支撑)}",
        "    （relation kind 已废弃——关系信息落 tags/subject, 2026-09-02）",
        "  - update: 修改已有条目。{action, id, patch: {字段: 新值}}——不得改 epistemic; 出厂基座(canon 只读)禁止",
        "  - merge: 深度整理（糅杂/归类）。{action, ids: [≥2 子图 id], into: {新条目字段(同 create.entry)}}",
        "  - link/unlink: 建/删关联边。{action, from, to}",
        "  - contradict/resolve: 标/解矛盾。{action, a, b}",
        "  - accrue: 同类事件并入已有 experience。{action, id: experience id,",
        "             occurrence: {episode_ref: 本包新建 episode 的 ref | episode_id: 子图 episode id,",
        "                          example?: 新例子}}",
        "",
        "evidence: 成长证据数组（罗盘函数触发判定用）:",
        "  - 每项 {function: 罗盘函数名(如 fe/ni), confidence: 0~1, quote: 事件流原文逐字, note?: 简短说明}",
        "  - 只输出有明确原文支撑的; 置信度 < 0.7 的会被引擎丢弃",
        "",
        "affection_exp_delta: 本段互动让角色对玩家好感增加的分数（int 0~100; 无变化 → 0）",
        "没有值得记的 → revisions 空数组（合法）。",
    ]
    return "\n".join(lines)
