"""core/common — 核心公共基础设施。

当前只有一个模块:
    errors         统一错误格式（Live2BeError 基类 + err() 辅助）
                   用法: from core.common import Live2BeError, err
"""

from __future__ import annotations

from core.common.errors import Live2BeError, err

__all__ = ["Live2BeError", "err"]
