"""MMT **行流契约**（盒A 的 `schema` 块）—— 三个输出形态里**唯一要动作注册表**的那个。

拼装顺序 = 外壳（md）→ 编号的硬规则（md 列表 + `_parts.numbered`）→ `可用操作:`
→ **动作表**（运行时, 见下）→ 示例（md, `with_examples=False` 时整段不印）。

⭐ **动作表必须由注册表渲染**（`registry.prompt_specs()`）—— 新增一个动作它自动进 prompt,
⛔ 不许在文案里手写清单（`_MMT_RULES` 里那两处动作名讲的是**用法纪律**, 不是清单;
它们的"名字对不对得上注册表"由 `test_schema_action_names_exist` 钉住）。

⚠️ 这一段**进 system prompt**（盒A 的第 9 块）——改任何一个字都要跑
`.testtmp/capture_1e.py`（逐字节判据）。
"""
from __future__ import annotations

from contract.constants import APPROVAL_AUTO, APPROVAL_NEVER, APPROVAL_REQUIRED
from contract.registry import ActionRegistry
from contract.schema._parts import block, numbered, rules

#: 审批态 → 文案（与 `build_record_schema` 无关; 那边没有审批概念）
_APPROVAL_NOTES = {
    APPROVAL_REQUIRED: "需用户批准",
    APPROVAL_AUTO: "自动执行",
    APPROVAL_NEVER: "直接执行",
}


def _action_table(registry: ActionRegistry) -> list[str]:
    """`可用操作:` 下面那张表 —— **运行时生成**（新增动作自动进 prompt）。"""
    out: list[str] = []
    for name, spec in registry.prompt_specs():          # ⭐ 封印的动作不进 prompt（`in_prompt`）
        note = _APPROVAL_NOTES.get(spec.approval, spec.approval)
        out.append(f"  - {name}  [{note}]")
        if spec.payload_schema:
            out.append(f"      payload: {spec.payload_schema}")
        else:
            out.append("      payload: （未提供描述）")
    return out


def build_line_schema(registry: ActionRegistry, *, with_examples: bool = True) -> str:
    """渲染 **MMT 行流契约**（LLM 可见）。

    Args:
        registry: 动作注册表（`prompt_specs()` 供动作表; `in_prompt=False` 的动作被封印）。
        with_examples: 是否附 few-shot 示例（A/B 对照与回归用）。

    设计: `docs/DESIGN_STREAM_CONTRACT.md` §1（契约形式六条）/ §2（两域对照）/ §10.2 B1·B3。
    文案纪律（同用户裁决 #24）：不写"不要写 X 字段"式负面提醒；示范里戏词不包「」。
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
