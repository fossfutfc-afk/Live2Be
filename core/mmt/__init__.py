"""`core.mmt` —— MMT（MomoTalk）域: 引擎 + 动作契约 + 执行器 + 预设/玩家名 + 排名。

| 模块 | 管什么 |
|---|---|
| `engine.py` | **`MomoTalkEngine`**（消息流动作循环 / 上下文装配 / 存档回灌 / 记忆消化）—— C12a 从 `core/momotalk.py` 搬来 |
| `mmt_actions.py` | `build_mmt_registry()`：4 个动作的契约声明 |
| `mmt_executor.py` | `MmtExecutor`：按 approval 执行动作、reply 承载对白 |
| `mmt_preset.py` | 预设人设 + 玩家名系统（`/name` 命令、namegg 校验） |
| `ranking.py` | 角色排名（出场顺序/权重之类的展示层排序） |

⚠️ 本包**不再导出**名字（`__init__` 只有这份说明）——引擎入口是
`from core.mmt.engine import MomoTalkEngine`（旧路径 `core.momotalk` 已于 C12a 消失）。
"""
