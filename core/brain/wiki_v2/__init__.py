"""wiki_v2 — 图式 wiki（AGENT_BRAIN.md 实施蓝图）。

⚠️ 2026-09-21: 原说明"不动 core/brain/{hippocampus,consolidation,recall}.py"已失效——
那三件（旧版记忆 digest v1）**已整族删除**, 本目录 = 唯一的记忆实现。
模块布局（多文件分工）:
    nodes.py   节点数据结构（BrainNode + 校验/归一/序列化）       ✅ M1a
    store.py   WikiStore v2（jsonl/原子整写/id/索引/快照/去重）    ✅ M1b
    render.py  组织视图 + 角色注入视图（分层 md 序列化）            ✅ M2
    revise.py  修订契约校验/执行 + evolution_log                  ✅ M2
    evolution.py 审计日志（append-only, R6 回滚依据）              ✅ M2
    recall.py  三通道召回 + 一跳扩展                               ✅ M4
    channels.py      召回链路**接口**（五条链路的形态声明）         ✅ V3-3 前置
    channel_impl.py  五条链路的实现（多数"诚实的空"——缺数据不出分） ✅ V3-3 前置
    compose.py        **最终打分**（四条道路合成 = 调和平均 rel×prior）✅ 2026-09-20
    recall_config.py  召回旋钮（settings.toml [recall]）           ✅ V3-0
    recall_ledger.py  召回台账（写路径候选碰撞 / 读路径注入视图）   ✅ V3-0
    digest.py  digest v2 管线（增量/召回/反馈重试/水位/幂等）       ✅ M3
    seed.py    （2026-09-05 出厂链归档——seed_from_config 不再导出,
               主进程解耦; 本体已移 archive/factory_memory/）
"""
from core.brain.wiki_v2.nodes import (
    EPISTEMICS,
    KINDS,
    PLAYER_SUBJECT,
    PRECIOUS_THRESHOLD,
    BrainNode,
    make_node,
)
from core.brain.wiki_v2.store import WikiStoreV2
from core.brain.wiki_v2.graph import Edge, Graph, graph_of
from core.brain.wiki_v2.evolution import EvolutionLog
from core.brain.wiki_v2.revise import RevisionResult, apply_revision_package
from core.brain.wiki_v2.render import render_background_experience, render_character_view, render_organize_view
from core.brain.wiki_v2.recall import recall_subgraph
from core.brain.wiki_v2 import recall_config, recall_ledger
from core.brain.wiki_v2.channels import (
    CHANNELS,
    KIND_GATE,
    KIND_PRIOR,
    KIND_SIMILARITY,
    PLANNED,
    Channel,
    ChannelHit,
    ChannelResult,
    RecallContext,
    describe as describe_channels,
    get as get_channel,
)
from core.brain.wiki_v2.digest import DigestResult, digest_segment
from core.brain.wiki_v2.compose import (
    ComposeResult,
    Composed,
    compose,
    gather_all,
    recall_now,
)

__all__ = [
    "EPISTEMICS",
    "KINDS",
    "PLAYER_SUBJECT",
    "PRECIOUS_THRESHOLD",
    "BrainNode",
    "make_node",
    "WikiStoreV2",
    "Edge",
    "Graph",
    "graph_of",
    "EvolutionLog",
    "RevisionResult",
    "apply_revision_package",
    "recall_subgraph",
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
    "DigestResult",
    "digest_segment",
    "ComposeResult",
    "Composed",
    "compose",
    "gather_all",
    "recall_now",
    "render_background_experience",
    "render_character_view",
    "render_organize_view",
]
