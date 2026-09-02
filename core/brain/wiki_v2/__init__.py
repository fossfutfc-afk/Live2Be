"""wiki_v2 — 图式 wiki（AGENT_BRAIN.md 实施蓝图）。

独立模块, 不动现有 core/brain/{hippocampus,consolidation,recall}.py,
直到里程碑切换（AGENT_BRAIN.md §8）。模块布局（多文件分工）:
    nodes.py   节点数据结构（BrainNode + 校验/归一/序列化）       ✅ M1a
    store.py   WikiStore v2（jsonl/原子整写/id/索引/快照/去重）    ✅ M1b
    seed.py    出厂 digest pass（experience/knowledge → fact）    ✅ M1c
    render.py  组织视图 + 角色注入视图（分层 md 序列化）            ✅ M2
    revise.py  修订契约校验/执行 + evolution_log                  ✅ M2
    evolution.py 审计日志（append-only, R6 回滚依据）              ✅ M2
    recall.py  三通道召回 + 一跳扩展                               ✅ M4
    digest.py  digest v2 管线（增量/召回/反馈重试/水位/幂等）       ✅ M3
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
from core.brain.wiki_v2.evolution import EvolutionLog
from core.brain.wiki_v2.revise import RevisionResult, apply_revision_package
from core.brain.wiki_v2.seed import SeedResult, seed_from_config
from core.brain.wiki_v2.render import render_character_view, render_organize_view
from core.brain.wiki_v2.recall import recall_subgraph
from core.brain.wiki_v2.digest import DigestResult, digest_segment

__all__ = [
    "EPISTEMICS",
    "KINDS",
    "PLAYER_SUBJECT",
    "PRECIOUS_THRESHOLD",
    "BrainNode",
    "make_node",
    "WikiStoreV2",
    "EvolutionLog",
    "RevisionResult",
    "apply_revision_package",
    "SeedResult",
    "seed_from_config",
    "recall_subgraph",
    "DigestResult",
    "digest_segment",
    "render_character_view",
    "render_organize_view",
]
