"""read — **记忆的读路径**（从 `core/brain/` 分家出来）: 只读、不写图。

| 模块 | 干什么 |
|---|---|
| `pack.py` | 召回的候选包: `Candidate`（节点 + 分 + 凭什么）· `ledger_line` 台账 · `body_of`（"哪些字段算正文"的唯一一处, `find` 与 `like` 共用） |
| `like.py` | 相似召回: 情境 ⇒ 最像的 k 条。三张表 + 一个契约（`PARTS` / `SPECS` / `RecallCtx`）; 合成 = 原始分 → 按 scale 归一 → 准入 + 加权平均 |
| `find.py` | 定向寻找: 锚 → **全部**（不 top-k —— 漏一条即错）。五个锚全是确定判据; `Clue` = 她写的字面布尔式（零 `re`） |
| `render.py` | 把图渲染成字: 她的注入视图（一条河 · 旧→新）· 组织视图 · 认知列表 · 召回块 |
| `recall.py` | 三通道召回 + 一跳扩展（`recall_subgraph` / `recall_episodes` / 随机浮现） |
| `channels.py` · `channel_impl.py` | 五条召回链路的接口与实现（多数"诚实的空" —— 缺数据不出分） |
| `compose.py` | 最终打分（四条道路合成 = 调和平均 rel × prior） |
| `recall_config.py` · `recall_ledger.py` | 召回旋钮（`settings.toml [recall]`）与台账 |

边界: 这里**不许写图**（不 `store.add` / 不 `add_edge`）—— 要写就走写路径（`revise` /
`store`）。分家的价值就是把"读的不会顺手改数据"从口头纪律变成**包边界**。
门面照旧从 `core.brain` 再导出常用名字（`render_character_view` / `recall_subgraph` /
`compose` …）⇒ 旧调用点零改动; 只有深路径才写 `core.brain.read.*`。
"""
