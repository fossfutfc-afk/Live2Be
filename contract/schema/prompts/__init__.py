"""`contract/schema` 的**文案仓库** —— 两个输出形态要说给 LLM 听的字。

    <形态>.md           外壳（+ 槽）—— 一段完整的话
    <形态>_rules.md     **只有** `- ` 列表（编号由代码按位置算, 见 `_parts.numbered`）
    <形态>_examples.md  示例块（`with_examples=False` 时整段不印）

⚠️ md 里**只有会给 LLM 看的话** —— 判据与说明住在 `.py` 的注释里
（md 没有"注释"这回事: 写进去就会被注入）。
⚠️ 加载 `.strip()` 首尾空白, 内部一字不动 ⇒ **文件末尾的空行不进 prompt**。
⚠️ 这几份是**逐字节判据**的对象（`.testtmp/capture_1e.py`）——改一个字节都要跑它。

⛔ 包内谁都不许 import 本包以外的东西替它填槽 —— 填槽只用 `contract.slots.render_template`。
"""
from __future__ import annotations

from pathlib import Path

from contract.prompt_files import load_md

#: 本包目录 = md 文件所在目录
_DIR = Path(__file__).resolve().parent


def load(name: str) -> str:
    """读 `<name>.md` 的全文（`.strip()` 后）。

    Raises:
        FileNotFoundError: 文件不存在（列出可用清单辅助定位）。
    """
    return load_md(_DIR, name, what="契约 schema")


__all__ = ["load"]
