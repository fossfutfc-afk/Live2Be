"""recall.py — 三通道召回 + 一跳扩展（AGENT_BRAIN.md §6 / M4）。

服务: 组织视图（digest/组织 LLM 的碰撞端）; API 通用——未来"回想注入"
（玩家问"你还记得那天吗"）用同一函数, 只是 query 换成用户问题。

通道（2026-09-02 决策）:
    1 相似度: embed_fn 批式注入（RAG 后路: v2 换 ChromaDB/FAISS 只换后端,
              调用方零改动）; 无 embed_fn → 降级 tags 词面匹配（零依赖）
    2 珍贵保底: significance ≥ 0.8 未命中通道1 → 补 n_precious
               （不排除 fact——预设经历 = 作者明示"角色必须记住的"）
    3 随机摘段: 30% 珍贵（sig 加权）/ 70% 对数正态(ts 年龄)加权抽 1 段
               （数学照搬 legacy random_recall_segment; age = ts 差, 小时）
    合并: 去重(id) → 沿 links ∪ contradictions 一跳扩展（否则 c: 标记悬空）
          → significance 降序（暂定）→ 截断 cap

embedding 派生不落盘（修订改内容零漂移）——每次召回对当前内容冷算;
digest 是异步路径, 毫秒级重算可接受。
"""
from __future__ import annotations

import math
import random
from datetime import datetime
from typing import Callable, Iterable

from core.brain.wiki_v2.nodes import PRECIOUS_THRESHOLD, BrainNode
from core.brain.wiki_v2.store import WikiStoreV2

#: 通道3 参数（per 角色可配——天然呆角色 σ 大, 呼应 CLAUDE.md 衰减系数设计）
PRECIOUS_RATIO = 0.3        # 珍贵分支概率
MU = 0.0                    # 对数正态位置（age 小时的对数）
SIGMA = 1.5                 # 对数正态尺度（衰减快慢）

#: 批式 embedding 后端（RAG 后路）: texts → 等长向量列表
EmbedFn = Callable[[list[str]], list[list[float]]]


def recall_subgraph(
    store: WikiStoreV2,
    *,
    query: str = "",
    k_sim: int = 5,
    n_precious: int = 2,
    n_random: int = 1,
    cap: int = 15,
    hop: int = 1,
    embed_fn: EmbedFn | None = None,
    rng: random.Random | None = None,
) -> list[BrainNode]:
    """三通道召回 + 一跳扩展 → significance 降序截断的子图。

    query: 通道1 的查询文本（digest 传时间线全文; 空 → 跳过通道1）。
    embed_fn: 批式 embedding 后端; None → tags 词面降级。
    rng: 通道3 的随机源（测试注入固定种子）。
    """
    rng = rng or random.Random()
    nodes = list(store.all())
    picked: dict[str, BrainNode] = {}

    # 通道1: 相似度（embed_fn 或 tags 降级）
    if query:
        for n in _similarity_hits(nodes, query, embed_fn, k_sim):
            picked.setdefault(n.id, n)

    # 通道2: 珍贵保底（含出厂 facts——D1）
    precious = sorted(
        (n for n in nodes
         if n.significance >= PRECIOUS_THRESHOLD and n.id not in picked),
        key=lambda n: n.significance, reverse=True)
    for n in precious[:n_precious]:
        picked.setdefault(n.id, n)

    # 通道3: 随机摘段（日常质感）
    for _ in range(max(n_random, 0)):
        seg = _random_segment(nodes, rng)
        if seg is not None:
            picked.setdefault(seg.id, seg)

    # 一跳扩展: links ∪ contradictions（D5）
    for n in list(picked.values()):
        for tgt in n.links + n.contradictions:
            other = store.get(tgt)
            if other is not None and other.id not in picked:
                picked[other.id] = other

    # 排序（D4 暂定: significance 降序）→ 截断
    return sorted(picked.values(), key=lambda n: n.significance,
                  reverse=True)[:cap]


# ---------------------------------------------------------------------------
# 通道1
# ---------------------------------------------------------------------------

def _similarity_hits(nodes: list[BrainNode], query: str,
                     embed_fn: EmbedFn | None, k: int) -> list[BrainNode]:
    if embed_fn is None:
        return _tags_hits(nodes, query, k)
    texts = [_embed_text(n) for n in nodes]
    try:
        vecs = embed_fn(texts)
        qv = embed_fn([query])[0]
    except Exception:                       # noqa: BLE001 — 后端故障降级, 宁缺勿错
        return _tags_hits(nodes, query, k)
    scored = sorted(
        ((_cosine(qv, v), n) for n, v in zip(nodes, vecs) if v),
        key=lambda t: t[0], reverse=True)
    return [n for s, n in scored[:k] if s > 0]


def _tags_hits(nodes: list[BrainNode], query: str, k: int) -> list[BrainNode]:
    """零依赖降级: 节点 tags 出现在 query 文本里 → 命中（按命中数, 再按 sig）。"""
    scored = [(len([t for t in n.tags if t and t in query]), n.significance, n)
              for n in nodes if n.tags]
    scored = [t for t in scored if t[0] > 0]
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [n for _, _, n in scored[:k]]


def _embed_text(node: BrainNode) -> str:
    """节点的可嵌入文本（内容 + 关键词; 与渲染口径一致）。"""
    if node.kind == "episode":
        body = node.narration + (" " + node.verbatim if node.verbatim else "")
    elif node.kind == "experience":
        body = node.pattern + (" " + " ".join(node.examples) if node.examples else "")
    elif node.kind == "relation":
        body = f"和{node.object}：{node.relation}" if node.object else node.relation
        if node.note:
            body += f"（{node.note}）"
    else:                                   # belief / fact
        body = node.content + (" " + node.growth if node.growth else "")
    tags = " ".join(node.tags)
    return f"{body} {tags}".strip()


def _cosine(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


# ---------------------------------------------------------------------------
# 通道3
# ---------------------------------------------------------------------------

def _random_segment(nodes: list[BrainNode],
                    rng: random.Random) -> BrainNode | None:
    """双通道随机摘段: 30% 珍贵（sig 加权, 永不衰减）/ 70% 遗忘曲线。"""
    if not nodes:
        return None
    if rng.random() < PRECIOUS_RATIO:
        precious = [n for n in nodes if n.significance >= PRECIOUS_THRESHOLD]
        if precious:
            weights = [max(n.significance, 0.1) for n in precious]
            return rng.choices(precious, weights=weights, k=1)[0]
    daily = [n for n in nodes if n.ts]
    if not daily:
        return None
    now = datetime.now()
    weights = []
    for n in daily:
        try:
            age = max((now - datetime.fromisoformat(n.ts)).total_seconds() / 3600, 0)
        except ValueError:
            age = 1e9                            # ts 异常 → 视为远古, 权重趋零
        x = math.log(age + 1)                    # 对数年龄（避免 log 0）
        w = math.exp(-((x - MU) ** 2) / (2 * SIGMA * SIGMA)) / (age + 1)
        weights.append(max(w, 1e-9))
    return rng.choices(daily, weights=weights, k=1)[0]
