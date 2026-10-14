"""VN **记录流契约**（盒B 的 `schema` 块）—— 三个输出形态里**不吃动作注册表**的那个。

拼装顺序 = 外壳 + 取值表（md, 带 `{{char_id}}` / `{{char_note}}` / `{{max_sensei_run}}`）
→ 编号的硬规则（md 列表）→ 示例（md, `with_examples=False` 时整段不印）。

## 取值表为什么写在 md 里（而不是从 `contract.records` 渲染）

那 7 个取值（`narrator` / `sensei` / `switch` / `art` / `memorial` / `end` …）的**真源**
是 `contract.records` 的常量（这个模块 import 它们做别的事）。md 里写的是**给人读的
复述** —— 两个家靠 `test_schema_values_match_grammar` 对账（从真源 AST 取, 与
`test_digest_contract_refs.py` 同一手法）。⛔ 别把那 7 个值换成 7 个槽: 那会让这一段
从"契约"退化成"模板", 而她眼前该看到的是取值本身。

⚠️ 这一段**进 system prompt**（盒B 的第 8 块）——改任何一个字都要跑
`.testtmp/capture_1e.py`（逐字节判据）。
"""
from __future__ import annotations

from contract.records import MAX_SENSEI_RUN
from contract.schema._parts import block, numbered, rules

#: 一轮戏的篇幅目标（行）—— 只写进 prompt 当参考，引擎不校验。
_VN_TURN_LINES = 40


def _char_note(char_display: str) -> str:
    """取值表第一行右边那句里的"你自己（谁）"那一小截。

    ⚠️ 它留在代码里（不写进 md）: 它是**从会话参数拼出来的**, 两个变体共用一个槽
    （`{{char_note}}`）—— 与 `{{char_id}}` 同理。
    """
    name = char_display.strip()
    return f"你自己（{name}）——本场只有你一个角色" if name else "你自己——本场只有你一个角色"


def build_record_schema(*, with_examples: bool = True, char_id: str = "igusa_haruka",
                        char_display: str = "") -> str:
    """渲染 **VN 记录流契约**（LLM 可见）。

    与"行流"（MMT, `build_line_schema`）并列（第三个"单动作 JSON / story·IDE"
    2026-10-14 已随 `build_schema` 删除，见 `contract/schema/__init__.py`）。
    设计: `docs/DESIGN_STREAM_CONTRACT.md` §2（文法）/ §10.4（`art` 预告制）。
    文案单源: 取值与约束全部取自 `contract.records` 常量（md 里是它们的复述, 有对账用例）。

    独立入口（而不是并进一个吃注册表的函数）是因为记录文法**不依赖动作注册表**
    （参数是角色 id 与状态约束，不是 ActionSpec 集合）——语义更清楚（§8.2 已按此对齐）。

    文案纪律（2026-09-10 用户裁决 #24）:
    - **不写"不要写 X 字段"这类负面提醒**（白熊效应: 不说模型不知道, 一说反而幻觉 + 废 token）;
    - 台词**不包引号**（范例里也不出现「」，直接告诉模型写纯文本）;
    - 示例里的角色取值 = **真实 id**（引擎按会话传入, 默认值即本项目角色）。

    Args:
        with_examples: 是否附 few-shot 示例（含**转义引号**示范——实测唯一真实错误源）。
        char_id: 本场角色的记录取值（引擎传真实 id）。
        char_display: 角色显示名（非空则写进取值说明，便于模型对上号）。
    """
    # ⚠️ **槽按文件给**（`render_template` 两个方向都对账）: `record.md` 没有
    # `{{turn_lines}}`（那一格只在规则里）, 多给一个就当场炸 —— 这正是要的。
    head = {"char_id": char_id, "char_note": _char_note(char_display),
            "max_sensei_run": str(MAX_SENSEI_RUN)}
    lines = block("record", head)
    lines += numbered(rules("record", slots={"max_sensei_run": str(MAX_SENSEI_RUN),
                                            "turn_lines": str(_VN_TURN_LINES)}))
    if with_examples:
        lines.append("")
        lines += block("record_examples", {"char_id": char_id})
    return "\n".join(lines)
