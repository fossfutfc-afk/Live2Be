"""core/common.errors — **薄再导出**（C10, `docs/EXEC_SPLIT.md`）。

真家已下沉到 `contract/errors.py`（`contract` 是最底层, 不再依赖 `core`）。
本文件只为**保住既有 import 路径**:
`from core.common import err` / `from core.common.errors import Live2BeError` 照旧可用——
全仓 20+ 处消费点一个字都不用改。

⚠️ 新代码（尤其 `contract/` 内）请直接 `from contract.errors import ...`;
`core/` 与 `llm/` 侧继续用这里也可以（`core.common` 是薄横切豁免项）。
"""

from __future__ import annotations

from contract.errors import Live2BeError, err

__all__ = ["Live2BeError", "err"]
