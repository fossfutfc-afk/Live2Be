"""`cli` —— **应用层**（C12b, `docs/EXEC_SPLIT.md`）: 面向人的入口, 不是引擎。

| 模块 | 管什么 |
|---|---|
| `main.py` | MomoTalk CLI 主流程（玩家名引导 → 角色选择 → 对话循环 → VN 触发） |
| `vn_cli.py` | 羁绊剧情 VN 的**终端**驱动（逐段打字 + 选项交互 + 存档/回放）——**唯一依赖 `renderer` 的地方** |

启动: `python main.py`（仓根转调壳）或 `python -m cli.main`。

⚠️ **方向纪律**: 引擎层（`core/` · `contract/` · `llm/` · `renderer/`）与壳（`webgui/`）
**都不许 import `cli`**（C11 之前 `webgui → cli.vn_cli` 就是这么反过来的;
`tests/core/test_import_direction.py` 现在把这条钉住了）。
"""
