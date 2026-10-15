"""LLM 可见的输出形态：两个渲染器 + 它们的文案仓库。

    build_line_schema()    MMT 行流契约（盒A 的 schema 块）；动作表由注册表运行时渲染。
    build_record_schema()  VN 记录流契约（盒B 的 schema 块）；不依赖注册表。

文案在 prompts/ 的 md 里，代码只管取哪份、填什么槽、怎么拼（lines.py / records.py，
共用件在 _parts.py）。第三个形态（单动作 JSON，story 域）2026-10-14 删除。

这段字进 system prompt，改一个字节就跑 .testtmp/capture_1e.py。

名字没变（原先的 schema.py 变成了包），所以 from contract import ... 与
from contract.schema import ... 两种写法都不用改。
"""
from __future__ import annotations

from contract.schema.lines import build_line_schema
from contract.schema.records import build_record_schema

__all__ = ["build_line_schema", "build_record_schema"]
