"""Prompt 仓库 — 长篇 prompt 的统一归处（llm/prompts/*.md）。

集中管理：长篇大段的 prompt 文本全部入 md 文件（可读、可改、可 git diff），
代码只保留加载逻辑与拼装顺序。`{{槽}}` 的填法在 `contract.slots`。
md 文件约定：
    - UTF-8 编码
    - 文件内容 = 注入 System Prompt 的完整块（含 `【标题】` 段头）
    - 加载时 .strip() 首尾空白，内部空白原样保留

用法:
    from llm.prompts import load_prompt

    system_prompt += "\\n\\n" + load_prompt("momotalk_rules")
    # 读的是 llm/prompts/momotalk_rules.md
"""

from __future__ import annotations

from pathlib import Path

from contract.prompt_files import load_md

#: 本包目录 = md 文件所在目录
_PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompt(name: str) -> str:
    """读取 llm/prompts/{name}.md 的全文（.strip() 后）。

    ⚠️ 读法本身（strip + 找不到时列清单）与 `contract/digest/prompts` **同一实现**:
    `contract.prompt_files.load_md` —— 这里只钉住"读哪个目录"。

    Args:
        name: md 文件名（不含 .md 扩展名）。

    Returns:
        提示词全文。

    Raises:
        FileNotFoundError: 文件不存在（列出可用 prompt 清单辅助定位）。
    """
    return load_md(_PROMPTS_DIR, name, what="prompt")
