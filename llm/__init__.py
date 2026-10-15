"""llm —— 传输层（与模型服务打交道的那一层）。

    client.py       客户端：配置优先级、超时/流式/usage、反馈重试、llm_chat
    retry.py        结构化调用的重试循环（三个引擎共用同一个）
    task_labels.py  「这次调用是谁」的唯一真源（label → task 标签）
    task_levels.py  档位真源：每个形态的 thinking 档与 max_tokens
    image_gen.py    生图（纪念立绘）
    prompts/        提示词文案仓库（人可改）

只依赖 `contract/` 与 `infra/`，不 import `core/`（tests/core/test_import_direction.py 钉着）。
"""
from __future__ import annotations

__all__: list[str] = []
