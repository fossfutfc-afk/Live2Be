"""`*.md` 文案文件的加载 —— **一个实现, 两处用**。

两处消费方（从前各写一份，形状逐行相同）:
    `llm/prompts`              任务/盒/标注的提示词（`llm/prompts/*.md`）
    `contract/digest/prompts`  digest 的输出契约（`contract/digest/prompts/*.md`）

⚠️ 它住在 `contract/`（最底层）: 契约层要读自己的契约 md, 而**契约层不 import `llm`**
⇒ 这个纯文件件不能住在 `llm/prompts`。

⚠️ 加载 `.strip()` 首尾空白, 内部一字不动 ⇒ **文件末尾的空行不进 prompt**
（非程序员用编辑器改 md, 编辑器会自己补最后一个换行 —— 那不该改变 prompt）。

⚠️ 出错时 `err()` 从**这里**取文件名 ⇒ 消息前缀是 `[prompt_files.py][NotFound]`。
这是有意的: "文件找不到"这件事就发生在本模块, 比从前印一个 `[__init__.py]` 好认。
"""
from __future__ import annotations

from pathlib import Path

from contract.errors import err


def load_md(base: Path, name: str, *, what: str) -> str:
    """读 `base/<name>.md`（`.strip()` 后）。

    Args:
        base: md 文件所在目录。
        name: 文件名（不含 `.md`; 可以带子目录, 如 `parts/row_fields`）。
        what: 报错时用的名字（`"prompt"` / `"digest 契约"`）—— 让看到错的人知道去哪找。

    Returns:
        文件全文（首尾空白已去）。

    Raises:
        FileNotFoundError: 文件不存在（列出**它所在那一层**的可用清单辅助定位）。
    """
    path = base / f"{name}.md"
    if not path.exists():
        folder = path.parent
        available = sorted(p.stem for p in folder.glob("*.md"))
        raise FileNotFoundError(err(
            "NotFound",
            f"{what} md 不存在: {name}.md"
            f"（{folder.name}/ 可用: {', '.join(available) or '无'}）",
        ))
    return path.read_text(encoding="utf-8").strip()
