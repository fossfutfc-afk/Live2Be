"""VN 记录流契约（盒B 的 schema 块）。

拼装顺序：外壳 + 取值表（md）→ 编号的硬规则（md 列表）→ 示例（md，with_examples=False 时整段不印）。

取值表的真源是 contract/records 的常量，md 里写的是给人读的复述，靠
test_schema_values_match_grammar 两边对账。别把那几个取值换成槽——她该看到的是取值本身。

这段字进 system prompt，改一个字就跑 .testtmp/capture_1e.py。
"""
from __future__ import annotations

from contract.records import MAX_SENSEI_RUN
from contract.schema._parts import block, numbered, rules

#: 一轮戏的篇幅目标（行）。只写进 prompt 当参考，引擎不校验。
_VN_TURN_LINES = 40


def _char_note(char_display: str) -> str:
    """取值表第一行右边那截"你自己（谁）"。由会话参数拼出，所以留在代码里。"""
    name = char_display.strip()
    return f"你自己（{name}）——本场只有你一个角色" if name else "你自己——本场只有你一个角色"


def build_record_schema(*, with_examples: bool = True, char_id: str = "igusa_haruka",
                        char_display: str = "") -> str:
    """渲染 VN 记录流契约（LLM 可见）。

    with_examples: 是否附 few-shot 示例（含转义引号示范）。char_id / char_display:
    本场角色的记录取值与显示名，由引擎传入。

    独立入口（不并进吃注册表的那个函数）是因为记录文法不依赖动作注册表。
    设计见 docs/DESIGN_STREAM_CONTRACT.md §2 / §10.4。
    """
    # 槽按文件给：record.md 没有 {{turn_lines}}（那一格只在规则里），多给会抛。
    head = {"char_id": char_id, "char_note": _char_note(char_display),
            "max_sensei_run": str(MAX_SENSEI_RUN)}
    lines = block("record", head)
    lines += numbered(rules("record", slots={"max_sensei_run": str(MAX_SENSEI_RUN),
                                            "turn_lines": str(_VN_TURN_LINES)}))
    if with_examples:
        lines.append("")
        lines += block("record_examples", {"char_id": char_id})
    return "\n".join(lines)
