"""wiki_v2 — 图式 wiki（AGENT_BRAIN.md 实施蓝图）。

独立模块, 不动现有 core/brain/{hippocampus,consolidation,recall}.py,
直到里程碑切换（AGENT_BRAIN.md §8）。当前文件: 节点数据结构。
"""
from core.brain.wiki_v2.nodes import (
    EPISTEMICS,
    KINDS,
    PLAYER_SUBJECT,
    PRECIOUS_THRESHOLD,
    BrainNode,
    make_node,
)

__all__ = [
    "EPISTEMICS",
    "KINDS",
    "PLAYER_SUBJECT",
    "PRECIOUS_THRESHOLD",
    "BrainNode",
    "make_node",
]
