"""MMT 行流契约（盒A 的 schema 块）。

拼装顺序：外壳（md）→ 编号的硬规则（md 列表）→ "可用操作:" → 动作表（运行时）→ 示例（md）。

动作表必须由注册表渲染，新增动作才会自动进 prompt；文案里手写的动作名只是用法举例，
它们的名字与注册表是否一致由 test_schema_action_names_exist 钉住。

这段字进 system prompt，改一个字就跑 .testtmp/capture_1e.py。
"""
from __future__ import annotations

from contract.constants import APPROVAL_AUTO, APPROVAL_NEVER, APPROVAL_REQUIRED
from contract.registry import ActionRegistry
from contract.schema._parts import block, numbered, rules

#: 审批态 → 文案（记录流没有审批概念，只这里用）
_APPROVAL_NOTES = {
    APPROVAL_REQUIRED: "需用户批准",
    APPROVAL_AUTO: "自动执行",
    APPROVAL_NEVER: "直接执行",
}


def _action_table(registry: ActionRegistry) -> list[str]:
    """`可用操作:` 下面那张表 —— **运行时生成**（新增动作自动进 prompt）。"""
    out: list[str] = []
    for name, spec in registry.prompt_specs():          # in_prompt=False 的动作不进 prompt
        note = _APPROVAL_NOTES.get(spec.approval, spec.approval)
        out.append(f"  - {name}  [{note}]")
        if spec.payload_schema:
            out.append(f"      payload: {spec.payload_schema}")
        else:
            out.append("      payload: （未提供描述）")
    return out


def build_line_schema(registry: ActionRegistry, *, with_examples: bool = True) -> str:
    """渲染 MMT 行流契约（LLM 可见）。

    registry: 动作表来自 prompt_specs()；with_examples: A/B 对照与回归用。
    设计见 docs/DESIGN_STREAM_CONTRACT.md §1/§2/§10.2。
    """
    lines = block("line", {})
    lines += numbered(rules("line"))
    lines.append("")
    lines.append("可用操作:")
    lines += _action_table(registry)
    lines.append("")
    if with_examples:
        lines += block("line_examples", {})
    return "\n".join(lines)
