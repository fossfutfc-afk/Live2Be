"""core/common — 核心公共基础设施。

当前只有一个模块:
    errors         统一错误格式（Live2BeError 基类 + err() 辅助）
                   用法: from core.common import Live2BeError, err
                   ⚠️ **C10 起只是薄再导出壳** —— 真家在 `contract/errors.py`
                   （契约层最底层, 免得 `contract/*` 反向依赖 `core`）。
                   路径保持不变, 全仓 20+ 处消费点零改动。
"""

from __future__ import annotations

from core.common.errors import Live2BeError, err

__all__ = ["Live2BeError", "err"]
