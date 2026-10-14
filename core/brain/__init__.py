"""brain — 角色记忆（**图式 wiki**；实现蓝图 = 同目录 `AGENT_BRAIN.md`）。

⭐ **2026-09-29 改名**: `core/brain/wiki_v2/` → **`core/brain/`**（用户裁决: 去版本号、
留 `brain` —— 这个名字有历史）。原来那层 27 行的再导出壳同时删掉（全仓零调用方）。

⚠️ **2026-09-21: 旧版记忆（digest v1）整族删除** —— `consolidation.py`（digest_session）/
`hippocampus.py`（WikiStore v1）/ `recall.py`（build_brain_injection）三件套连同
`llm/prompts/digest.md`、`contract/schema.build_digest_schema()`、`experiments/brain_real_run.py`
一并移除（文档早已声明"保留但无运行时消费方"）。历史设计（v1 时代）见根级 `DESIGN_BRAIN.md`（混合史，慎读）。

模块布局（多文件分工）:
    nodes.py   节点数据结构（BrainNode + 校验/归一/序列化）       ✅ M1a
    store.py   WikiStore（jsonl/原子整写/id/索引/快照/去重）       ✅ M1b
    graph.py   边表（类型化 + 有向 + 三索引 + 查询）               ✅ G1–G4
    marks.py   括号与信息头的**唯一实现**（那一行字长什么样）       ✅ N5d
    address.py 她写下的名字 → 节点（与 marks 共用字符集）           ✅ N5a
    revise.py  修订契约校验/执行 + evolution_log                  ✅ M2
    evolution.py 审计日志（append-only, R6 回滚依据）              ✅ M2
    notes.py   随身笔记（约定 / 心境）—— 纯函数 + 零 IO            ✅ M4′
    groups.py  群（L2 归纳）与并群                                 ✅ N7b
    entities.py  entity 初始化 + 第 3 轮（归属）的输入侧            ✅ D2/D3
    read/      ⭐ **读路径**（2026-09-29 分家; 只读、不写图）:
        render.py        组织视图 + 角色注入视图（分层 md 序列化）   ✅ M2
        recall.py        三通道召回 + 一跳扩展                       ✅ M4
        channels.py      召回链路**接口**（五条链路的形态声明）       ✅ V3-3 前置
        channel_impl.py  五条链路的实现（多数"诚实的空"——缺数据不出分）✅ V3-3 前置
        compose.py       **最终打分**（四条道路合成 = 调和平均 rel×prior）✅ 2026-09-20
        recall_config.py 召回旋钮（settings.toml [recall]）          ✅ V3-0
        recall_ledger.py 召回台账（写路径候选碰撞 / 读路径注入视图）  ✅ V3-0
        walk.py   记忆图上的两种走法（⛔ **未接线** —— 用户 2026-10-12 裁
                  "先写一个接口, 不调用但需要有"）: `bfs` = **找同类**
                  （akin/member_of 横向扩散, 有分/深度/广度闸）·
                  `chain` = **深挖**（evolved_from/contradicts 纵向 DFS,
                  来路+方向, 已访问集防环）                    ⏸ 接口
    seed.py    （2026-09-05 出厂链归档——seed_from_config 不再导出,
               主进程解耦; 本体已移 archive/factory_memory/）

⭐ **本包的三条边界**（2026-09-29 两次搬家之后）:
1. **写路径**（`store` / `graph` / `revise` / `groups` / `notes` / `entities`）与
   **读路径**（`read/`）分家 —— 读路径**只读不写图**, 谁要写就走写路径那几件。
2. **零 LLM**: 本包不 import `llm` / `core.digest` / `core.session` 的编排件
   ⇒ digest 管线（要那三样）搬去了 **`core/digest/`**; 她视图里的 `digest_segment`
   从 `core.digest` 取。⚠️ 契约层只许取**纯值常量**（`contract.digest` 的
   `ENTITY_TAG_PREFIX` 那种）, 不许取 schema 渲染与动作注册表。
3. `marks.py` 是**她眼前那一行字**的唯一实现 —— 别的模块只许调它, 不许手写括号
   （守门 `tests/core/test_marks_guard.py`）。
"""
from core.brain.evolution import EvolutionLog
from core.brain.graph import Edge, Graph, graph_of
from core.brain.nodes import (
    KINDS,
    PRECIOUS_THRESHOLD,
    BrainNode,
    make_node,
)
from core.brain.read import recall_config, recall_ledger
from core.brain.read.channels import (
    CHANNELS,
    KIND_GATE,
    KIND_PRIOR,
    KIND_SIMILARITY,
    PLANNED,
    Channel,
    ChannelHit,
    ChannelResult,
    RecallContext,
)
from core.brain.read.channels import (
    describe as describe_channels,
)
from core.brain.read.channels import (
    get as get_channel,
)
from core.brain.read.compose import (
    Composed,
    ComposeResult,
    compose,
    gather_all,
    recall_now,
)
from core.brain.read.recall import recall_episodes, recall_subgraph
from core.brain.read.render import (
    render_background_experience,
    render_character_view,
    render_organize_view,
    render_recall_block,
)
from core.brain.store import WikiStoreV2

__all__ = [
    "KINDS",
    "PRECIOUS_THRESHOLD",
    "BrainNode",
    "make_node",
    "WikiStoreV2",
    "Edge",
    "Graph",
    "graph_of",
    "EvolutionLog",
    "recall_subgraph",
    "recall_episodes",
    "recall_config",
    "recall_ledger",
    "CHANNELS",
    "PLANNED",
    "KIND_PRIOR",
    "KIND_SIMILARITY",
    "KIND_GATE",
    "Channel",
    "ChannelHit",
    "ChannelResult",
    "RecallContext",
    "describe_channels",
    "get_channel",
    "ComposeResult",
    "Composed",
    "compose",
    "gather_all",
    "recall_now",
    "render_background_experience",
    "render_character_view",
    "render_organize_view",
    "render_recall_block",
]
