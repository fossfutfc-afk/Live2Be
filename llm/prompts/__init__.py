"""Prompt 仓库 — 长篇 prompt 的统一归处（llm/prompts/*.md）。

集中管理：长篇大段的 prompt 文本全部入 md 文件（可读、可改、可 git diff），
代码只保留加载逻辑与拼装顺序。md 文件约定：
    - UTF-8 编码
    - 文件内容 = 注入 System Prompt 的完整块（含 `【标题】` 段头）
    - 加载时 .strip() 首尾空白，内部空白原样保留

用法:
    from llm.prompts import load_prompt

    system_prompt += "\\n\\n" + load_prompt("momotalk_rules")
    # 读的是 llm/prompts/momotalk_rules.md
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from core.common import err

#: 本包目录 = md 文件所在目录
_PROMPTS_DIR = Path(__file__).resolve().parent

#: 模板槽写法：`{{名字}}`。用双花括号是为了和正文里单个 `{` 不冲突。
_SLOT = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")


def load_prompt(name: str) -> str:
    """读取 llm/prompts/{name}.md 的全文（.strip() 后）。

    Args:
        name: md 文件名（不含 .md 扩展名）。

    Returns:
        提示词全文。

    Raises:
        FileNotFoundError: 文件不存在（列出可用 prompt 清单辅助定位）。
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        available = sorted(p.stem for p in _PROMPTS_DIR.glob("*.md"))
        raise FileNotFoundError(err(
            "NotFound",
            f"prompt 文件不存在: {path.name}（llm/prompts/ 可用: {', '.join(available) or '无'}）",
        ))
    return path.read_text(encoding="utf-8").strip()


def render_template(text: str, slots: Mapping[str, str], *, where: str = "") -> str:
    """把 `{{名字}}` 槽填成给定值 —— **两个方向都对不上就当场炸**。

    从前是裸的 `text.replace("{{x}}", v)`，于是两种错**都静默**：
      · 模板里**没有**这个槽 ⇒ replace 什么也没做，调用方还以为填了；
      · 模板里**有**槽却没给值 ⇒ `{{x}}` 原样进 system prompt，她会看见字面量。
    第二类已经被 `core/brain/read/modes.py` 手写守卫抓过一次 —— 那个守卫收进这里。

    Args:
        text: 模板全文。
        slots: 槽名 → 值（值里的 `{{...}}` 不参与二次替换）。
        where: 出错时印出来的位置（prompt 名 / 调用点），便于定位。

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

