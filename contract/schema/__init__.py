"""`contract/schema` — **LLM 可见的输出形态**（契约文本的渲染 + 文案仓库）。

    build_line_schema()    **MMT 行流**契约（盒A 的 `schema` 块）——`registry` 运行时
                           渲染"可用操作"表（新增动作自动进 prompt, ⛔ 不手写清单）。
    build_record_schema()  **VN 记录流**契约（盒B 的 `schema` 块）——**不依赖注册表**,
                           参数是角色 id 与显示名。

两个形态的**字**住在 `prompts/`（人可改、可 diff）; 代码只管"取哪份 / 槽填什么 / 怎么拼"
（`lines.py` / `records.py`, 共用件在 `_parts.py`）。

⚠️ **第三种形态（单动作 JSON / story·IDE 域）已在 2026-10-14 删除**：
`build_schema()` 生产零调用者（只有 `archive/ide_editor` 还在 import）、
`export_definitions()`（"A 方案数据面，给 JS/WebLLM 用"）**0 生产 0 测试**，
`_SHELL_FIELD_DESCRIPTIONS` 只有前者用 ⇒ 三件一起走。那些字段说明的正主是
`contract/spec.py` 的 `payload_schema` 与 `prompt_fields`。

⚠️ 本文案**进 system prompt**（盒的 `schema` 块）: 改一个字节 ⇒ 跑
`.testtmp/capture_1e.py`（这一族的逐字节判据, `EXPECTED_CHANGED` 要写"为什么"）。

⚠️ `contract.schema` 这个**名字没变**（原来是 `schema.py` 模块, 现在是包）⇒
`from contract import build_line_schema` 与 `from contract.schema import …` 两种写法
**都不用改**。
"""
from __future__ import annotations

from contract.schema.lines import build_line_schema
from contract.schema.records import build_record_schema

__all__ = ["build_line_schema", "build_record_schema"]
