"""core/common.errors — **薄再导出**（C10, `docs/EXEC_SPLIT.md`）。

真家已下沉到 `contract/errors.py`（`contract` 是最底层, 不再依赖 `core`）。
本文件只为**保住既有 import 路径**:
`from core.common import err` / `from core.common.errors import Live2BeError` 照旧可用——
全仓 20+ 处消费点一个字都不用改。

⚠️ 新代码请直接 `from contract.errors import ...`。
⚠️ **`llm/` 已不再走这里**（三处改直连 `contract.errors`）—— `llm → core` 的豁免表
同步收窄成只剩 `core.paths`（`tests/core/test_import_direction.py`）。
`core/` 内部继续用本壳也可以, 但**别再往上/往外引**。
"""

from __future__ import annotations

from contract.errors import Live2BeError, err

__all__ = ["Live2BeError", "err"]
