"""Live2Be 启动壳 —— 真入口在 `cli/main.py`（C12b, `docs/EXEC_SPLIT.md`）。

用法不变:

    python main.py

为什么留这个壳: `python main.py` 是 README 与使用习惯里的命令, 且仓根在 `sys.path` 上
（`cli` 才 import 得到）; 真代码一律放 `cli/`——`core/` 是引擎层, 不该装 CLI 应用。
"""

from __future__ import annotations

import logging

from cli.main import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    main()
