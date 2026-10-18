"""`setup_tool` —— **资源配置辅助工具**（独立小 exe，不进主程序的网页壳）。

它管的是"主程序管不好的那几件事"：素材/角色卡放在哪、缺什么、key 通不通、数据在哪。
主程序是"玩"的界面，它是"配"的界面 —— 所以是**另一个 exe**（`Live2BeSetup.exe`），
可以脱离主程序单独跑（装完先体检）。

| 模块 | 管什么 |
|---|---|
| `checks.py` | 体检逻辑（纯函数；不 import tkinter）—— 汇总成一条条 `Check` |
| `ui.py` | tkinter 界面：显示结果 + 选目录 + 写配置 |
| `main.py` | 入口（`python -m setup_tool` / 冻结后的 exe） |

## 三条纪律

1. **不手搓判据**：角色卡用 `CharacterLoader`、背景用 `MediaCatalog`、连通性用现役
   `LLMClient` / `LocalEmbedder`。工具只汇总和显示 —— 主程序改判据，工具自动跟上。
2. **真源只读**：`data/` 里是 append-only 事件流，工具**不写**；要备份只许复制（给路径）。
3. **写只走 `infra.settings.write`**（唯一写入口）。`[paths]` 是 import 期常量，
   保存后**必须重启主程序**才生效 —— 界面上要说出来。
"""
