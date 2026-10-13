"""`{{名字}}` 槽的填充原语 —— **两个方向都对不上就当场炸**。

住在 `contract/`（最底层）: 契约层要用它渲染 digest 的契约文本, 而契约层不 import `llm`
⇒ 这个纯字符串件不能住在 `llm/prompts`（1c 从那儿搬来）。现在**一个实现, 两处用**。

替掉的是裸的 `text.replace("{{x}}", v)` —— 那种写法下两种错**都静默**:
  · 模板里**没有**这个槽 ⇒ replace 什么也没做, 调用方还以为填了;
  · 模板里**有**槽却没给值 ⇒ `{{x}}` 原样进 system prompt, 她会看见字面量。
"""
from __future__ import annotations

import re
from collections.abc import Mapping

#: 模板槽写法：`{{名字}}`。用双花括号是为了和正文里单个 `{` 不冲突。
_SLOT = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")


def render_template(text: str, slots: Mapping[str, str], *, where: str = "") -> str:
    """把 `{{名字}}` 槽填成给定值 —— **两个方向都对不上就当场炸**。

    Args:
        text: 模板全文。
        slots: 槽名 → 值（值里的 `{{...}}` 不参与二次替换）。
        where: 出错时印出来的位置（md 名 / 调用点）, 便于定位。

    Raises:
        ValueError: 模板的槽与给的值两个方向对不上（多一个或少一个都算）。
    """
    want = set(_SLOT.findall(text))
    got = set(slots)
    if want != got:
        at = f"（{where}）" if where else ""
        raise ValueError(
            f"模板槽对不上{at}: 模板里有 {sorted(want) or '无'} · 给了 {sorted(got) or '无'}")
    return _SLOT.sub(lambda m: str(slots[m.group(1)]), text)
