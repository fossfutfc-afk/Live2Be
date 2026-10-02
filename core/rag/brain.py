# -*- coding: utf-8 -*-
"""brain.py — RAG × Brain 适配（记忆召回的语义检索后端）。

brain/recall.py 已预留 EmbedFn 接口（"RAG 后路: 只换 embed_fn 实现, 调用方
零改动"）——本模块把 core/rag 的 LocalEmbedder 包成 EmbedFn, 并提供带 RAG 的
召回便利函数（recall_with / recommend_with）, digest 侧一行接线:
    embed_fn = make_embed_fn(LocalEmbedder())
    recall_subgraph(store, query=..., embed_fn=embed_fn)

降级哲学对齐 recall.py: embedding 服务故障 → EmbedFn 抛 RagError → recall 内部
try/except 自动落 tags 关键词匹配（宁缺勿错, 不阻断 digest）。
"""
from __future__ import annotations

from typing import Callable

from core.brain.nodes import BrainNode
from core.brain.recall import recall_subgraph, recommend_candidates
from core.brain.store import WikiStoreV2
from core.rag.embedder import LocalEmbedder, RagError

#: brain recall 的批式 embedding 后端签名（texts → 等长向量）
EmbedFn = Callable[[list[str]], list[list[float]]]


def make_embed_fn(embedder: LocalEmbedder) -> EmbedFn:
    """LocalEmbedder → brain EmbedFn（故障直接抛 RagError, 由 recall 降级）。"""
    def embed_fn(texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return embedder.embed(list(texts))
        except RagError:
            raise
        except Exception as e:                       # noqa: BLE001
            raise RagError(f"embedding 故障: {e}") from e
    return embed_fn


def recall_with(
    store: WikiStoreV2,
    query: str = "",
    embedder: LocalEmbedder | None = None,
    **kw,
) -> list[BrainNode]:
    """recall_subgraph + RAG（embedder 缺省自动发现; 故障自动降级 tags）。"""
    emb = embedder or LocalEmbedder()
    if emb.health():
        kw.setdefault("embed_fn", make_embed_fn(emb))
    return recall_subgraph(store, query=query, **kw)


def recommend_with(
    store: WikiStoreV2,
    query: str,
    embedder: LocalEmbedder | None = None,
    **kw,
) -> list[tuple[BrainNode, float]]:
    """recommend_candidates + RAG（Round B 候选推荐; 故障自动降级关键词）。"""
    emb = embedder or LocalEmbedder()
    if emb.health():
        kw.setdefault("embed_fn", make_embed_fn(emb))
    return recommend_candidates(store, query, **kw)
