"""brain — 角色记忆（**图式 wiki**）: 节点 / 边 / 存储 / 笔记 / 地址 / 读路径。

模块布局:
    nodes.py     节点数据结构（BrainNode + 校验 / 归一 / 序列化）
    store.py     存储（jsonl / 原子整写 / id / 索引 / 快照 / 去重）
    graph.py     边表（类型化 · 有向 · 三索引 · 查询）
    marks.py     括号与信息头的唯一实现（她眼前那行字）
    address.py   她写下的名字 → 节点（与 marks 共用字符集）
    revise.py    修订契约校验 / 执行 + evolution_log
    evolution.py 审计日志（append-only, R6 回滚依据）
    notes.py     随身笔记（约定 / 心境）—— 纯函数、零 IO
    entities.py  entity 初始化 + 归属轮的输入侧
    read/        读路径（只读、不写图; 分工见 `read/__init__.py`）

本包的三条边界:
1. **写路径**（`store` `graph` `revise` `notes` `entities`）与
   **读路径**（`read/`）分家 —— 读路径**只读不写图**, 谁要写就走写路径那几件。
2. **零 LLM**: 本包不 import `llm` / `core.digest` / `core.session` 的编排件
   ⇒ digest 管线（要那三样）搬去了 **`core/digest/`**; 她视图里的 `digest_segment`
   从 `core.digest` 取。契约层只许取**纯值常量**（`contract.digest` 的
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
