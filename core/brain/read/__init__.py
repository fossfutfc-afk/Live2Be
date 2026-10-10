# -*- coding: utf-8 -*-
"""read — **记忆的读路径**（2026-09-29 从 `core/brain/` 分家出来）。

一句话分工: **只读、不写图**。

| 模块 | 干什么 |
|---|---|
| `pack.py` | ⭐ 召回的**候选包**（2026-10-08）: `Candidate`（节点 + 分 + **凭什么**）· `ledger_line`（台账, `scores=False` / `k=None` 两个开关）· **`body_of`**（"哪些字段算正文"的唯一一处 —— `find` 与 `like` 共用） |
| `like.py` | ⭐ **相似召回**（同日）: 情境 ⇒ 最像的 k 条。**三张表 + 一个契约**（`PARTS` 注册表 / `SPECS` 档位 / `RecallCtx` 输入契约），照 promptkit 的 `BLOCKS`+`DOMAIN_BOXES` 形态。合成 = 三趟: 原始分 → **按 scale 归一**（`UNIT` 原样 / `COSINE` 池内 min-max + **名次门槛**）→ 准入 + 加权平均 |
| `find.py` | ⭐ **定向寻找**（同日）: **锚 → 全部**（⛔ 不 top-k: 漏一条即错）。五条锚（`title` / `entity` / `group` / `when` / `text`）全是**确定判据**; `Clue` = 她写的**字面**布尔式（`&& & \|\| \|` + 半角括号, ⛔ **零 `re`**） |
| `render.py` | 把图渲染成字: 她的注入视图（一条河 · 旧→新）· 组织视图 · 认知列表 · 召回块 |
| `recall.py` | 三通道召回 + 一跳扩展（`recall_subgraph` / `recall_episodes` / 随机浮现） |
| `channels.py` · `channel_impl.py` | 五条召回链路的**接口**与实现（多数"诚实的空"——缺数据不出分） |
| `compose.py` | **最终打分**（四条道路合成 = 调和平均 rel × prior） |
| `recall_config.py` · `recall_ledger.py` | 召回旋钮（`settings.toml [recall]`）与台账（写/读两路径各打一行） |

⚠️ **边界纪律**: 这里**不许写图**（不 `store.add` / 不 `add_edge`）——要写就走
`core/brain/` 的写路径（`revise` / `groups` / `store`）。分家的价值就是把这条
"读的不会顺手改数据"从口头纪律变成**包边界**（一眼看得出 `from core.brain import read`
之后拿到的东西只读）。

⚠️ **它不在 `core/brain/__init__.py` 的 `__all__` 之外被额外转发**: 门面照旧从
`core.brain` 再导出常用的那几个名字（`render_character_view` / `recall_subgraph` /
`compose` …）⇒ 旧调用点零改动; 只有**深路径** import 需要写 `core.brain.read.*`。
"""
