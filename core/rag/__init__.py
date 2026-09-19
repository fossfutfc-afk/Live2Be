# -*- coding: utf-8 -*-
"""core/rag — 本地语义检索基础设施（RAG）。

双用例（同一 embedding 后端, 宁缺勿错统一降级）:
    place.py   地点检索: 自由话语/意图 → **地点表键**（PL4 起语料 = `place_entities.json`,
               与标注层同一张表; 跨语言靠 embedding 模型, 别名以中文为主）
    brain.py   记忆召回: WikiStoreV2 节点的 EmbedFn 后端（digest 必经之路）

embedder 对接本地 OpenAI 兼容 /v1/embeddings（LM Studio / Bionic, :1234）——
在 Bionic 里加载跨语言 embedding 模型（bge-m3 / Qwen3-Embedding 等）即可用;
服务不可用 → 上层自动降级（place 精确兜底 / brain tags 关键词）, 不阻断引擎。

用法:
    from core.rag.place import PlaceRetriever
    from core.rag.brain import recall_with, make_embed_fn

    PlaceRetriever().resolve_one("她们在天台上看星星")   # → "school_rooftop"（表键）
    recall_with(store, query="遥香第一次埋炸弹的经历")     # → [BrainNode, ...]
"""
from core.rag.embedder import LocalEmbedder, RagError
from core.rag.place import PlaceError, PlaceRetriever
from core.rag.brain import make_embed_fn, recall_with, recommend_with

__all__ = [
    "LocalEmbedder",
    "RagError",
    "PlaceRetriever",
    "PlaceError",
    "make_embed_fn",
    "recall_with",
    "recommend_with",
]
