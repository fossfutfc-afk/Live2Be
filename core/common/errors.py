"""core/common.errors — **薄再导出**（C10, `docs/EXEC_SPLIT.md`）。

真家已下沉到 `contract/errors.py`（`contract` 是最底层, 不再依赖 `core`）。
本文件只为**保住既有 import 路径**:
`from core.common import err` / `from core.common.errors import Live2BeError` 照旧可用——
全仓 20+ 处消费点一个字都不用改。

⚠️ 新代码请直接 `from contract.errors import ...`。
⚠️ **`llm/` 已不再走这里**（三处改直连 `contract.errors`）; 2026-10-15 `core/paths.py`
搬进 `infra/` 之后, `llm → core` 的豁免表**整个清空了**
（`test_import_direction.py` 的 `LLM_CORE_ALLOWED` 现在是空表 ⇒ 这条规则零例外）。
`core/` 内部继续用本壳也可以, 但**别再往上/往外引**。
⚠️ 本壳自己也在排队退役（`core/common/` 那个"抽屉"就地解散 ⇒ 全仓消费点改直连
`contract.errors`）。
"""

from __future__ import annotations

from contract.errors import Live2BeError, err

__all__ = ["Live2BeError", "err"]
