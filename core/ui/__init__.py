# -*- coding: utf-8 -*-
"""`core/ui` —— **空壳**: C11 起展示层已搬到 `core.tui`, 这里只剩 CLI **应用** `vn_cli.py`。

| 想要什么 | 去哪 |
|---|---|
| 展示组件（display / streaming / text_processors） | `core.tui.*` |
| `vn_cli`（CLI 应用: 跑一场 VN） | 还在原路径, **C12 会搬 `apps/`**（它依赖 `renderer`, 是 core→renderer 唯一来源） |
| webgui 要的 `_build_director` / `_trigger_title` | **C11 起在 `core.director.wiring`**（解掉 webgui→CLI 的反向耦合） |

⚠️ 本包**不再**再导出展示层名字（`from core.ui import MomoTalkOutput` 已作废,
请改 `from core.tui import MomoTalkOutput`）——只有一层名字, 免得两个入口漂移。
"""
