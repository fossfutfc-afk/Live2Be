"""`contract/schema` 两个渲染器共用的三件小事（私有）。

    numbered()   硬规则 → 编号行（**编号由位置算, 不手写**）
    rules()      读 `<形态>_rules.md`（`- ` 列表）→ 一条一条的规则文本
    render()     读 md + 填槽 + 校验（薄壳, 见下）

## 为什么编号由位置算（别改回手写）

从前三个渲染器各自把 `"1." "2." …` 写死在字符串里 ⇒ 中间插一条就要把后面全部改一遍
（而且很容易漏一个数字, 让 prompt 里的编号跳号）。规则现在是**数据**（md 里一行一条）,
加一条只管往 md 里写。

## 为什么规则 md 用 `- ` 列表

它是"**一串**规则"而不是"一段话" —— 用列表写法, 代码才能既保住自动编号、又把文案
交给 md（人可读可改）。⛔ 因此 `<形态>_rules.md` 里**不许有别的 `- ` 开头的行**
（测试 `test_schema_rules_are_a_clean_list` 钉住条数）。
"""
from __future__ import annotations

from contract.schema.prompts import load
from contract.slots import render_template

#: 列表项前缀（md 的写法）
_BULLET = "- "


def numbered(items: list[str]) -> list[str]:
    """硬规则 → 编号行（`1. …` `2. …`）—— 编号按位置算。"""
    return [f"{i}. {t}" for i, t in enumerate(items, 1)]


def rules(name: str, *, slots: dict[str, str] | None = None) -> list[str]:
    """读 `<name>_rules.md` → 规则文本列表（槽先填, 再编号由调用方做）。

    ⚠️ 槽在**切列表之前**填（`render_template` 是全文替换）——槽值里不会有换行。
    """
    text = render(name + "_rules", slots or {})
    return [ln[len(_BULLET):].strip() for ln in text.split("\n") if ln.startswith(_BULLET)]


def render(name: str, slots: dict[str, str]) -> str:
    """读 `<name>.md` 并填槽 —— **两个方向都对不上就当场炸**（`render_template`）。

    ⚠️ 没有槽的 md 也要走这里（传 `{}`）: 那也校验了一次"这份 md 确实没有槽"。
    """
    return render_template(load(name), slots, where=f"contract/schema/prompts/{name}.md")


def block(name: str, slots: dict[str, str]) -> list[str]:
    """读 `<name>.md` 并**按行切开**（渲染器的返回是 `"\\n".join(lines)`, 所以按行拼）。"""
    return render(name, slots).split("\n")
