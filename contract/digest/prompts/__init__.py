"""digest 契约的**文案仓库** —— 每个相位要说给 LLM 听的那段字。

    <相位>.md       一份 = 一个相位的**完整输出契约**（`build_schema` 直接返回它）
    parts/*.md      被上面几份共用的片段: 域/条数契约 · 逐字段块 · "切几件"那一行

⚠️ md 里**只有会给 LLM 看的话** —— 判据与说明住在 `docs.py` / `tables.py` 的注释里
（md 没有"注释"这回事: 写进去就会被注入）。
⚠️ 加载 `.strip()` 首尾空白, 内部一字不动 ⇒ **文件末尾的空行不进 prompt**。

⛔ 包内谁都不许 import 本包以外的东西替它填槽 —— 填槽只用 `contract.slots.render_template`。
"""
from __future__ import annotations

from pathlib import Path

from contract.prompt_files import load_md
from contract.slots import render_template as fill

#: 本包目录 = md 文件所在目录
_DIR = Path(__file__).resolve().parent


def load(name: str) -> str:
    """读 `<name>.md` 的全文（`.strip()` 后）。

    ⚠️ 读法本身与 `llm/prompts` **同一实现**: `contract.prompt_files.load_md`
    —— 这里只钉住"读哪个目录"。

    Raises:
        FileNotFoundError: 文件不存在（列出可用清单辅助定位）。
    """
    return load_md(_DIR, name, what="digest 契约")


def fragment(name: str) -> str:
    """读 `parts/<name>.md`（共用片段）。"""
    return load(f"parts/{name}")


__all__ = ["fill", "fragment", "load"]
