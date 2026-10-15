"""contract/schema 两个渲染器共用的三件小事（私有）。

    numbered()   规则列表 → 编号行
    rules()      读 <形态>_rules.md（每行一条 `- `）→ 规则列表
    render()     读 md + 填槽（槽对不上就抛）

编号由位置算，不手写：从前写死在字符串里，中间插一条就要改后面全部，还容易跳号。
规则 md 用 `- ` 列表，是因为它是"一串规则"而不是"一段话"，这样代码才能既拿到列表、
又把文案留在 md 里。注意 <形态>_rules.md 里不许有别的 `- ` 开头的行。
"""
from __future__ import annotations

from contract.schema.prompts import load
from contract.slots import render_template

#: 列表项前缀（md 的写法）
_BULLET = "- "


def numbered(items: list[str]) -> list[str]:
    """规则列表 → 编号行。"""
    return [f"{i}. {t}" for i, t in enumerate(items, 1)]


def rules(name: str, *, slots: dict[str, str] | None = None) -> list[str]:
    """读 <name>_rules.md → 规则文本列表（先填槽，编号由调用方做）。"""
    text = render(name + "_rules", slots or {})
    return [ln[len(_BULLET):].strip() for ln in text.split("\n") if ln.startswith(_BULLET)]


def render(name: str, slots: dict[str, str]) -> str:
    """读 <name>.md 并填槽；模板与给的值对不上会抛。"""
    return render_template(load(name), slots, where=f"contract/schema/prompts/{name}.md")


def block(name: str, slots: dict[str, str]) -> list[str]:
    """同 render()，但按行切开（渲染器最后是 "\\n".join(lines)）。"""
    return render(name, slots).split("\n")
