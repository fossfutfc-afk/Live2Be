"""contract/schema 的文案仓库。

    <形态>.md           外壳（带槽）
    <形态>_rules.md     只有 `- ` 列表，编号由代码按位置算
    <形态>_examples.md  示例块；with_examples=False 时整段不印

md 里只放会给 LLM 看的话——判据与说明写在 .py 的注释里，因为 md 没有"注释"这回事。
加载会去掉首尾空白，所以文件末尾的空行不进 prompt。
这几份被 .testtmp/capture_1e.py 逐字节比对，改一个字节都要跑它。
"""
from __future__ import annotations

from pathlib import Path

from contract.prompt_files import load_md

#: 本包目录 = md 文件所在目录
_DIR = Path(__file__).resolve().parent


def load(name: str) -> str:
    """读 <name>.md（去掉首尾空白）。文件不存在会列出同目录可用清单。"""
    return load_md(_DIR, name, what="契约 schema")


__all__ = ["load"]
