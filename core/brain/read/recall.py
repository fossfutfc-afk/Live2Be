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
    合并: 去重(id) → 沿**边表**一跳扩展（G3 起; 旧版是节点上的 links ∪ contradictions）
          → significance 降序（暂定）→ 截断 cap

embedding 派生不落盘（修订改内容零漂移）——每次召回对当前内容冷算;
digest 是异步路径, 毫秒级重算可接受。
"""
from __future__ import annotations

import logging
import math
import random
from datetime import datetime
from typing import Callable

from core.brain.nodes import PRECIOUS_THRESHOLD, BrainNode
from core.brain.store import WikiStoreV2
from core.worldtime.age import REAL_TZ, parse_ts

logger = logging.getLogger(__name__)

#: 通道3 参数（per 角色可配——天然呆角色 σ 大, 呼应 CLAUDE.md 衰减系数设计）
PRECIOUS_RATIO = 0.3        # 珍贵分支概率
MU = 0.0                    # 对数正态位置（age 小时的对数）
SIGMA = 1.5                 # 对数正态尺度（衰减快慢）

#: 批式 embedding 后端（RAG 后路）: texts → 等长向量列表
EmbedFn = Callable[[list[str]], list[list[float]]]

#: 每 episode 最多带几个候选 —— **这是"给几条提示", 不是阈值**。
#: 2026-09-15（T17）: `CAND_HIGH` / `CAND_MED` **已删**（用户裁决"cand_high 相关全删掉"，
#: 落地 DESIGN_WIKI_V3 的 Q11/Q31/Q32）。三条理由，都不是口味问题:
#:
#: 1. **阈值从来不是标定出来的**。Q11 实测: nomic 下"无关经历"(0.868) 比"相关经历"
#:    (0.819) 得分还高——**单阈值原理上不可分**; 标定时 embedding 服务没通,
#:    `0.50` 是拍的。实测两个模型下候选 **6/6 全越线**。
#: 2. **它驱动的是一条硬闸门**。`>= CAND_HIGH` → 该 episode 出 `add` 就整包拒。
#:    分数带在**同一实体内部**天然压缩，于是"全部分侧面"被判成"同一件事" →
#:    新认知永远长不出来（v2 的真实失效模式）。
#: 3. **Q31 已定"召回不要阈值"**（用户: *"肯定不能要阈值"*）——改成
#:    排序取 top-k。Q32 随即裁掉写入侧的结构强制。
#:
#: 现在候选**只作提示**（`recommend_candidates` 排序取 top-k，`s > 0` 挡掉零/负相似），
#: 判断留给 LLM，而且**判 add 要在 note 里说明理由**（写进 Round B prompt）。
CAND_K = 3                  # 每 episode 最多候选数

#: ⭐ N5（2026-09-29）: **MMT 每轮"你想起的事"**摆几条（`[recall].turn_k`）。
#: 为什么是 2 而不是更多: 这一段进的是**主对话每轮**的动态尾, 与 `cand_k`（喂给
#: digest 的提示）不同 —— 摆多了她会"每轮都在回忆", 而这一段的全部价值是
#: "当下 ↔ 某一条旧事"的**具体关联**（`DESIGN_MMT_NEW_ACTION §3.7`）。
TURN_K = 2


def _thr(name: str, fallback: float) -> float:
    """取召回旋钮（配置优先; 配置层异常 → 回落模块常量, 绝不上抛）。"""
    try:
        from core.brain.read.recall_config import get
        return get(name)
    except Exception:                            # noqa: BLE001 — 配置层不阻断召回
        return fallback


def recall_subgraph(
    store: WikiStoreV2,
    *,
    query: str = "",
    k_sim: int = 5,
    n_precious: int = 2,
    n_random: int = 1,
    cap: int = 15,
    embed_fn: EmbedFn | None = None,
    rng: random.Random | None = None,
) -> list[BrainNode]:
    """三通道召回 + 一跳扩展 → significance 降序截断的子图。

    query: 通道1 的查询文本（digest 传时间线全文; 空 → 跳过通道1）。
    embed_fn: 批式 embedding 后端; None → tags 词面降级。
    rng: 通道3 的随机源（测试注入固定种子）。

    注（2026-09-21）: 旧签名有个 `hop: int = 1` 参数, 但函数体**从未读它**
    （下面的一跳扩展恒做）—— 一个"传了也没用"的旋钮（静默 no-op）。全仓无调用方传它,
    故删除; 要恢复可配深度, 请让下面的扩展读参数并在 `recall_config.DEFAULTS` 立台账。
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

    # 一跳扩展: **边表的 1-hop**（G3 起边在 edges.jsonl——任意 rel 都算一跳,
    # 不再只认旧字段 links ∪ contradictions）
    from core.brain.graph import graph_of
    g = graph_of(store)
    for n in list(picked.values()):
        for tgt in g.neighbors(n.id):
            other = store.get(tgt)
            if other is not None and other.id not in picked:
                picked[other.id] = other

    # 排序（D4 暂定: significance 降序）→ 截断
    return sorted(picked.values(), key=lambda n: n.significance,
                  reverse=True)[:cap]


# ---------------------------------------------------------------------------
# 通道1
# ---------------------------------------------------------------------------

def recommend_candidates(store: WikiStoreV2, query: str, *,
                         embed_fn: EmbedFn | None = None,
                         k: int | None = None,
                         kinds: tuple[str, ...] = ("belief", "experience"),
                         mode_out: list | None = None,
                         why_out: list | None = None) -> list[tuple[BrainNode, float]]:
    """按 query 打分取 top-k 的**通用**检索（两个调用者, 判据不同）。

    | 调用者 | `kinds` | 要什么 |
    |---|---|---|
    | digest Round B（本函数的原职） | `belief` / `experience` | "这条新经历该并入哪条已有认知" |
    | ⭐ **MMT 每轮想起**（N5, `recall_episodes`） | `episode` | "此刻这句话让她想起哪条旧事" |

    打分与降级**两边同一份**（这正是它值得收成一个函数的原因）: 语义（embed_fn）
    → 故障/缺省退**词面**（tags ∩ + subject 命中 + 正文 2-gram Dice, 保守——
    宁缺勿错: 不标注比标错好）。

    原职语义（**别丢**）: 服务 digest Round B——引擎先把每条新经历与现有稳定认知碰撞,
    把最像的几条**列出来给 LLM 参考**（A-MEM/AgentGal 同款"引擎先筛再让 LLM 逐条判定"）。
    那时只挑稳定认知（belief/experience）——episode 是流水不参与组织, fact 是
    出厂基座不可被 touch/update（守 revise._ensure_cognition 语义）。
    ⚠️ **候选只是提示, 没有阈值、也没有结构强制**（2026-09-15 T17 删 `CAND_HIGH`）:
    排序取 top-k, `s > 0` 挡掉零/负相似; 判 touch/update/add 全在 LLM。
    `add` 需在 note 里说明理由（写进 Round B prompt）。理由见 `CAND_K` 上方注释。
    ⚠️ **N5 起 `kinds` 可换**, 但上面那条"episode 不参与组织"**没有被推翻** ——
    变的只是**谁在问**: Round B 问的是"归到哪条认知", N5 问的是"想起哪条旧事"。

    **RAG 升级接口（2026-09-02 决策）**: embed_fn 即检索后端——未来上
    ChromaDB/FAISS/rerank 只换 embed_fn 实现（或其内部加向量库/重排）,
    调用方零改动。embedding 派生不落盘, 每次冷算（内容改动零漂移）。

    **降级可观测（2026-09-13 审计拆分点 A）**: 语义后端故障时打一行
    `recall_cand fallback=keyword reason=…`——此前的静默降级会让"引擎抬不出候选"
    表现为"wiki 只增不并", 排查时无从下手。

    Args:
        k: None → 读 `[recall].cand_k`（默认 3）
        kinds: 选面（节点 kind 白名单）——缺省 = Round B 的稳定认知
        mode_out: 可选传出参数——本函数会把实际走的通道 **append** 进去
            （`"semantic"` / `"keyword"`），供调用方汇总成召回台账（V3-0）。
            用列表而非返回值，是为了不改既有返回签名（测试与调用方零改动）。
        why_out: ⭐ **N2（2026-09-29）**: 可选传出参数——**为什么推荐它**
            （与返回值**等长同序**：`语义 0.72` / `tags[苔藓,杂草屋] 命中` /
             `subject 点名` / `2-gram 0.41`）。同样用列表传出而不改返回签名。
            为什么要它: Round B 的候选提示原来只有编号, LLM 判"要不要并"时
            **看不见理由**; 而理由正好是引擎手里现成的那点信息（少花 ≠ 少信息）。

    Returns: [(node, score), ...] 降序, score > 0; 空 query/空认知 → []。
    """
    if k is None:
        k = int(_thr("cand_k", CAND_K))
    nodes = [n for n in store.all() if n.kind in kinds]
    query = (query or "").strip()
    if not nodes or not query:
        return []
    if embed_fn is not None:
        try:
            vecs = embed_fn([_embed_text(n) for n in nodes])
            qv = embed_fn([query])[0]
            scored = sorted(
                ((_cosine(qv, v), n) for n, v in zip(nodes, vecs) if v),
                key=lambda t: t[0], reverse=True)
            if mode_out is not None:
                mode_out.append("semantic")
            hit = [(n, s) for s, n in scored[:k] if s > 0]
            if why_out is not None:              # 与返回值等长同序
                why_out.extend(f"语义 {s:.2f}" for _n, s in hit)
            return hit
        except Exception as e:                  # noqa: BLE001 — 后端故障降级
            logger.info("recall_cand fallback=keyword reason=embed_error err=%s "
                        "nodes=%d（Round B 抬不出候选 → 该段只能凭 LLM 自己判断）",
                        e, len(nodes))
    if mode_out is not None:
        mode_out.append("keyword")
    return _keyword_candidates(nodes, query, k, why_out=why_out)


def recall_episodes(store: WikiStoreV2, *, query: str = "", k: int | None = None,
                    embed_fn: EmbedFn | None = None,
                    mode_out: list | None = None) -> list[BrainNode]:
    """⭐ **N5** · MMT 每轮"她想起的旧事" —— **只出 episode, 按当下这句话取 1~2 条**。

    ⚠️ **与 `recall_subgraph` 的分工（别把两者合并成一个"召回"）**:
      · `recall_subgraph` = **digest 组织视图**的入口。三通道混合 + 沿边一跳,
        要的是"给我一块能拿去归纳的子图"——**所以它把 belief/entity 一起带进来是对的**,
        排序按 `significance`（D4 暂定, 组织视图的口径）;
      · 本函数 = **主对话每轮**的入口。要的是"此刻跟老师这句话有关的旧事",
        所以 ① **只要 episode**（当下要连的是"另一件旧事", 不是一条看法）
        ② 排序按**相关度**（"按当前对话"就是这句话的意思, 按 significance 排会变成
        "总是想起最重要的那件"——同一条每次都被想起 ⇒ 永远长不出新边）。
      ⇒ 检索原语**同一份**: 直接复用 `recommend_candidates` 的打分与降级
      （语义 → 故障退词面 tags/Dice）, 不新造第三条检索链。

    宁缺勿错: 没有 query / 空库 / 一条都不像 ⇒ **返 []（这一轮就不注）**,
    **不拿"最近一条"或随机一条来凑**——摆一条无关的旧事 = 逼她强行联想,
    产生的还是一条**脏边**（而边是要进图的, 比少说一句贵）。

    Returns: 相关度降序的 episode 节点（最多 `k` 条, 缺省 `[recall].turn_k`）。
    """
    if k is None:
        k = int(_thr("turn_k", TURN_K))
    picked = recommend_candidates(store, query, embed_fn=embed_fn, k=k,
                                  kinds=("episode",), mode_out=mode_out)
    return [n for n, _score in picked]


def _keyword_candidates(nodes: list[BrainNode], query: str, k: int, *,
                        why_out: list | None = None) -> list[tuple[BrainNode, float]]:
    """零依赖降级（保守, 宁缺勿错: 不标注比标错好——假阳性会逼 LLM 错 update）:

    - tags 命中（检索导向, 最强信号）→ 0.6 + 0.1 × (命中数-1)
    - subject 整体出现在 query（正文点名主题词）→ 0.85
    - 正文 2-gram Dice（verbatim/近句重现）→ 取原始 Dice（>0.35 才认）
    取各项最大值; score ≤ 0 → 不推荐。

    `why_out`（⭐ N2）: 传出**哪一路赢了**（`tags[...] 命中` / `subject 点名` /
    `2-gram 0.41`）—— 与返回值等长同序。⚠️ 用 `if s > best` 逐个比较来记录,
    **不能事后重算**（重算一份就是第二个真源, 迟早与这里的 max 语义漂开）。
    """
    q2 = _bigrams(query)
    out: list[tuple[BrainNode, float, str]] = []
    for n in nodes:
        s, why = 0.0, ""
        hits = [t for t in n.tags if t and t in query]
        if hits:
            s, why = 0.6 + 0.1 * (len(hits) - 1), f"tags[{','.join(hits)}] 命中"
        if n.subject and n.subject in query and 0.85 > s:
            s, why = 0.85, "subject 点名"
        body = n.text + (" " + n.growth if n.growth else "")
        d = _dice(q2, _bigrams(body))
        if d > 0.35 and d > s:
            s, why = d, f"2-gram {d:.2f}"
        if s > 0:
            out.append((n, s, why))
    out.sort(key=lambda t: (t[1], t[0].significance), reverse=True)
    kept = out[:k]
    if why_out is not None:
        why_out.extend(w for _n, _s, w in kept)
    return [(n, s) for n, s, _w in kept]


def _bigrams(text: str) -> set[str]:
    """中文无分词下的轻量词元: 去空白后全部相邻 2-gram。"""
    chars = [c for c in text if not c.isspace()]
    return {chars[i] + chars[i + 1] for i in range(len(chars) - 1)}


def _dice(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return 2.0 * len(a & b) / (len(a) + len(b))


def _similarity_hits(nodes: list[BrainNode], query: str,
                     embed_fn: EmbedFn | None, k: int) -> list[BrainNode]:
    if embed_fn is None:
        return _tags_hits(nodes, query, k)
    texts = [_embed_text(n) for n in nodes]
    try:
        vecs = embed_fn(texts)
        qv = embed_fn([query])[0]
    except Exception as e:                      # noqa: BLE001 — 后端故障降级, 宁缺勿错
        logger.info("recall_sim fallback=tags reason=embed_error err=%s nodes=%d "
                    "（通道1 语义召回不可用, 退词面标签命中）", e, len(nodes))
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
    """节点的可嵌入文本（主文本 + 附属 + 关键词; 与渲染口径一致）。"""
    body = node.text
    if node.kind == "episode" and node.verbatim:
        body += " " + node.verbatim
    elif node.kind == "experience" and node.examples:
        body += " " + " ".join(node.examples)
    elif node.kind == "belief" and node.growth:
        body += " " + node.growth
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
    # ★ 时区对齐（2026-09-27 修）——**必做**：`ts` 2026-09-17 收敛到带时区
    #   （`now_ts()` 写 `+08:00`），而这里原来是 `now = datetime.now()`（朴素）
    #   ⇒ `now - datetime.fromisoformat(n.ts)` 抛 **TypeError**（aware − naive），
    #   而下面的 `except ValueError` **抓不住它** ⇒ 直接冒泡出 `_random_segment`。
    #   ⚠️ 爆炸半径**不止随机那一支**：`recall_subgraph` 里这一句没有 try 包裹 ⇒
    #   通道 1/2 的结果全丢、**整个召回作废**（真机 haruka 实测 12 个 seed 崩 8 次）。
    #   真机后果: CLI 的 `memory_flash`（"剧情开始前突然想起一件事"）被外层
    #   `except Exception: 静默跳过` 吞掉 ⇒ 实际概率 25% → ≈7.5%（0.25 × 0.30），
    #   零日志（webgui 侧没接 random_events, 所以网页版没踩到）。
    #   同款 bug 在 `core/worldtime/prompt_time.py` 2026-09-17 已修过一次
    #   （症状: 时间注记整条静默消失）——**这里是那次收敛漏掉的第二处**。
    #   纪律: 统一走 `age.parse_ts`（朴素按 `REAL_TZ` 解释; 缺/坏 → None, 不抛），
    #   与 `age_days` / `render_relative` 同一个真源, 别在这里手写 fromisoformat。
    now = datetime.now(REAL_TZ)
    weights = []
    for n in daily:
        ts = parse_ts(n.ts)
        if ts is None:                           # ts 异常 → 视为远古, 权重趋零
            age = 1e9
        else:
            age = max((now - ts).total_seconds() / 3600, 0)
        x = math.log(age + 1)                    # 对数年龄（避免 log 0）
        w = math.exp(-((x - MU) ** 2) / (2 * SIGMA * SIGMA)) / (age + 1)
        weights.append(max(w, 1e-9))
    return rng.choices(daily, weights=weights, k=1)[0]


def random_flash_segment(store: WikiStoreV2,
                         rng: random.Random | None = None) -> BrainNode | None:
    """随机浮现段（memory_flash 用, 2026-09-02 切换 brain）: 从 episode
    （质感日常, 第一人称本就"我"）双通道随机摘 1 段——"想起一件事"的素材。

    原 legacy random_recall_segment 基于 events 文本摘段; v2 节点层同数学
    （30% 珍贵 sig 加权 / 70% lognormal ts 年龄）, 语义对齐: 浮现的是
    "记得的一段经历"（episode）, 不摘 belief/experience（模式不是事件）。
    空库/无 episode → None（无记忆可浮, 静默跳过）。
    """
    rng = rng or random.Random()
    # "只浮现她**亲历**的" —— 判据 = `observer` 空（2026-09-29 起; 原 `epistemic` 已退役）。
    episodes = [n for n in store.all()
                if n.kind == "episode" and not n.observer.strip()]
    return _random_segment(episodes, rng)
