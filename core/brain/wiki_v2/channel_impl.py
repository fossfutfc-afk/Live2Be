# -*- coding: utf-8 -*-
"""五条召回链路的实现（V3-3 前置）—— 接口见 `channels.py`。

## 本文件的现状：**大部分链路是"诚实的空"**

用户要的是"先写接口, 等有了接口统一构造公式"。所以这里实现的是**形态与降级路径**,
不是打分公式。如实记下每条链路**现在缺什么数据**——这才是本阶段的价值。

| 链路 | 现在能不能出分 | 缺什么 |
|---|---|---|
| **A** `A_intensity` | ✅ **能** | 只需要 `ctx.story_now`（游标）+ 节点 `story_time`。**旧档节点**（无 `story_time`）逐条跳过 |
| **B** `B_emotion_rag` | ✅ **能**（T15, 2026-09-15） | 需要 `ctx.emo_now` + 节点 `emo_shape`（digest 按板指针物化）+ `embed_fn` |
| **C** `C_place` | ❌ 不能 | `BrainNode` **无 `place` 字段**（§2.3.2: 设计已定、实现待补） |
| **D** `D_deja_vu` | ✅ **能** | 只需要 `narration` + `embed_fn`（两者都有） |
| **E** `E_unconscious` | ⏳ 未立项 | 认知碎片（§6.4 的 `percepts`） |

**A / B / D 是现在就能出分的三条**——都不是巧合：它们只需要**已存在的数据**
（A 是候选自身属性（`PRIOR`）; B/D 是 pairwise, 要 query + 向量后端）。

🚫 **召回侧字段不进 LLM 上下文**（用户 2026-09-15 裁决）: `emo_shape` /
`emo_now` / `place_now` 参与**排序与筛选**, 不参与**写作**——`render_*` 一律
不输出它们。与 `bond` 侧"place 不进 LLM 上下文"（§4 视觉键隔离）同一条纪律。

## 三条实现纪律

1. **缺数据 → `raw=None` + `degraded=True` + 单行 `note`**, 绝不编分
   （`raw=None` 与 `raw=0.0` 语义不同, 见 `ChannelHit`）
2. **不归一、不排序截断**（V3-3 的"无阈值取 top-k"由合成层做）
3. **只读 store**——链路不改任何状态（`last_recalled_at` 那种突变态属于物化层）
"""
from __future__ import annotations

import logging

from core.brain.wiki_v2.channels import (
    KIND_GATE,
    KIND_PRIOR,
    KIND_SIMILARITY,
    PLANNED,
    SCALE_COSINE,
    SCALE_UNIT,
    ChannelHit,
    ChannelResult,
    RecallContext,
)

logger = logging.getLogger(__name__)

#: 情绪键序列的 embedding 文本前缀（B 链路）——**只放键, 不放正文**。
#: 实测依据（§3.3）: 键序列单独向量化时两两 cos 有清晰层次
#: （haruka 板间 [0.590, 0.834]）; 而把情绪塞进 episode 正文会**塌陷空间**
#: （两两 cos 0.5595 → 0.6853）。
_EMO_PREFIX = "情绪序列: "


# ---------------------------------------------------------------------------
# A · 综合强度行列式
# ---------------------------------------------------------------------------

class IntensityPrior:
    """A 链路: `det = SIG·TIME + emo_span·emo_int`（§3.3 的 2×2 行列式）。

    **本链路是 `PRIOR`**——不依赖 query, 是候选**自己的属性**。所以它天然
    可以预物化（索引表里存一列）, 而 B/D/E 是 pairwise 的、不能。

    ## 四格

    | 格 | 来源 | 缺值时 |
    |---|---|---|
    | `SIG` | `node.significance`（0~1, 恒有） | — |
    | `emo_span` | `node.emo_span`（0~1） | 退化：第二行整行为 0 |
    | `emo_int` | `node.emo_int`（0~1） | 同上 |
    | `TIME` | `freshness(age, half_life)` | **降级不出分**（见下） |

    ## TIME 的判定（§4.11 ① —— 写路径与读路径分开）

    ```
    写路径（digest 时）:  stamp  →  node.story_time = 当前 cursor      ← 存下来
    读路径（召回时）:    age    =  ctx.story_now.sim_day − node.story_time.sim_day
                         TIME   =  0.5 ** ((age/5) / half_life_days)
    ```

    **`TIME` 不落库**——若写进节点, 节点就永远停在"写入那一刻的新鲜度", 指数白算。

    ## 降级（`raw=None`, 绝不编分）

    - `ctx.story_now is None` → 游标未就绪
    - `ctx.story_now` 不是 `StoryTime` → 调用方传错
    - `node.story_time is None` → 旧档未采集（**该节点**降级, 其余照常出分）

    **第三种的语义**: 一条旧档记忆的 `TIME` 无法判定, 但它的
    `emo_span·emo_int` 仍然有效 —— 所以**不是整条链路降级**, 而是该节点
    `raw=None`。`det` 的 `SIG·TIME` 项因此缺失, 由合成层决定怎么处理
    （当前口径: 不带 TIME 的候选进"待补"集合, 不参与排序）。
    """

    name = "A_intensity"
    kind = KIND_PRIOR
    scale = SCALE_UNIT
    unit = "det"

    def gather(self, store, ctx: RecallContext) -> ChannelResult:
        res = ChannelResult(channel=self.name, kind=self.kind)
        try:
            from core.worldtime.age import freshness
            from core.worldtime.story import parse_story_time
            from core.brain.wiki_v2.recall_config import get as _knob
        except Exception as e:                       # noqa: BLE001 — 链路失败不抛
            res.degraded = True
            res.note = f"依赖不可用: {e}"
            return res

        hl = _knob("time_half_life_days")
        now = ctx.story_now
        if now is None:
            res.degraded = True
            res.note = "TIME 缺 now（ctx.story_now=None）——游标未传"
            res.knobs = {"time_half_life_days": hl, "time_ready": False}
            return res
        now_st = parse_story_time(now.to_dict() if hasattr(now, "to_dict") else now)
        if now_st is None:
            res.degraded = True
            res.note = "TIME 缺 now（ctx.story_now 形态非法）"
            res.knobs = {"time_half_life_days": hl, "time_ready": False}
            return res

        hits: list[ChannelHit] = []
        no_time = 0
        for node in store.all():
            if node.kind != "episode":
                continue
            node_st = parse_story_time(node.story_time)
            age = None if node_st is None else max(0, now_st.sim_day - node_st.sim_day)
            t = freshness(age, hl) if age is not None else None
            if t is None:
                no_time += 1
                hits.append(ChannelHit(
                    node=node, raw=None, rank=0,
                    detail={"reason": "no story_time（旧档未采集）"}))
                continue
            span = float(node.emo_span or 0.0)
            emo_i = float(node.emo_int or 0.0)
            det = float(node.significance) * t + span * emo_i
            hits.append(ChannelHit(
                node=node, raw=det, rank=0,
                detail={"sig": node.significance, "time": round(t, 4),
                        "age": age, "span": span, "int": emo_i}))
        scored = [h for h in hits if h.raw is not None]
        scored.sort(key=lambda h: -h.raw)
        for i, h in enumerate(scored, 1):
            h.rank = i
        res.hits = scored + [h for h in hits if h.raw is None]
        res.knobs = {"time_half_life_days": hl, "time_ready": True,
                     "scored": len(scored), "no_story_time": no_time}
        if not scored:
            res.degraded = True
            res.note = f"无一条 episode 有 story_time（旧档 {no_time} 条）→ 不出分"
        return res


# ---------------------------------------------------------------------------
# B · 情绪数组 RAG 相似度
# ---------------------------------------------------------------------------

class EmotionRag:
    """B 链路: 情绪键序列的 embedding 相似度（唤醒度聚类, §3.3）。

    ★ 实测依据（两条, 都决定这个链路该存在）:
      1. **它按唤醒度聚类, 不按极性**——"高强度·正" vs "高强度·负" cos = 0.678,
         **高于** "同极性·不同强度" 的 0.498/0.557。即"情绪相反但都很猛"的记忆
         天然互相靠近, **不需要额外机制**（用户 2026-09-13 的直觉, 实测证实）
      2. **键序列单独向量化有层次**（haruka 板间 [0.590, 0.834], 跨度 0.244）,
         而塞进正文会塌陷

    ⚠️ **为什么键序列要物化到节点上**（T15, 2026-09-15 接通）:
    键序列在**板**上（`events.jsonl` 的 `payload.paragraphs[i].emotion`），
    而 `gather(store, ctx)` **只拿得到节点, 拿不到事件流**——链路无法去翻板。
    所以 `digest` 在写节点时按**板指针 `event_seq`** 把键序列物化成
    `node.emo_shape`（§3.3/§3.9 早就定了这一手: "板级 affect 物化缓存（一次算,
    索引表里存）…可从真源重建"）。有 `event_seq` 就能重算, 故它不是第二真源。

    🚫 **`emo_shape` / `emo_now` 绝不进 LLM 上下文**（用户 2026-09-15 裁决）:
    它们是**召回侧信号**, 与 `place` 同类——参与排序, 不参与写作。

    ⚠️ 另有一条**未验证**的依赖: 本链路需要"键 → 唤醒度"的映射才能排序,
    而那张表**已被用户否掉**（"怎么又回到机械打分的时代了"）。
    但**排序其实不需要数值**——cos 直接在键序列向量上算, 数值只在
    "解释为什么这两条近"时才需要。**所以本链路可以完全无数值表**。
    """

    name = "B_emotion_rag"
    kind = KIND_SIMILARITY
    scale = SCALE_COSINE
    unit = "cos"

    def gather(self, store, ctx: RecallContext) -> ChannelResult:
        res = ChannelResult(channel=self.name, kind=self.kind)
        q = [k.strip() for k in (ctx.emo_now or [])
             if isinstance(k, str) and k.strip()]
        if not q:
            res.degraded = True
            res.note = "无 emo_now（当前情绪键序列未知）"
            res.knobs = {"needs": "ctx.emo_now（当前这板的情绪键序列）"}
            return res
        nodes = [n for n in store.all() if n.kind == "episode" and n.emo_shape]
        no_shape = sum(1 for n in store.all()
                       if n.kind == "episode" and not n.emo_shape)
        res.knobs = {"n_nodes": len(nodes), "no_emo_shape": no_shape,
                     "query_keys": len(q)}
        if not nodes:
            res.degraded = True
            res.note = (f"无 episode 有 emo_shape（旧档 {no_shape} 条）"
                        "→ 不出分")
            return res
        if ctx.embed_fn is None:
            res.degraded = True
            res.note = "无 embed_fn（无向量后端）"
            return res
        try:
            from core.brain.wiki_v2.recall import _cosine
            texts = [f"{_EMO_PREFIX}{' '.join(n.emo_shape)}" for n in nodes]
            vecs = ctx.embed_fn(texts + [f"{_EMO_PREFIX}{' '.join(q)}"])
            qv = vecs[-1]
            scored = sorted(((_cosine(qv, v), n) for v, n in zip(vecs[:-1], nodes)),
                            key=lambda t: -t[0])
        except Exception as e:                       # noqa: BLE001 — 链路失败不抛
            logger.warning("B_emotion_rag 降级: %s", e)
            res.degraded = True
            res.note = f"embedding 失败: {e}"
            return res
        res.hits = [ChannelHit(node=n, raw=float(s), rank=i + 1,
                               detail={"keys": len(n.emo_shape)})
                    for i, (s, n) in enumerate(scored)]
        return res


# ---------------------------------------------------------------------------
# C · 地点字段查重（检测）
# ---------------------------------------------------------------------------

class PlaceGate:
    """C 链路: `place` 字段的**查重/检测**——`GATE`, 不是分数。

    用户 2026-09-13 的定位是"**检测**"（"地点字段查重"）, 与 A/B/D 不同:
    它不排序, 它**筛选/分组**——"同一地点的记忆"是一个集合, 集合内的成员
    再交给 A/D 排序。这也是它与"逻辑召回"的关系: 同地点/同时间/同在场者
    都是**键命中**（不是相似度）, 见 §3.3 的三通路拓扑。

    ⚠️ **`BrainNode` 没有 `place` 字段**（§2.3.2 已澄明: 设计已定、实现待补,
    链路未通因为背景系统没搞好）。所以现在必然降级。
    """

    name = "C_place"
    kind = KIND_GATE
    scale = SCALE_UNIT
    unit = "place_hit"

    def gather(self, store, ctx: RecallContext) -> ChannelResult:
        res = ChannelResult(channel=self.name, kind=self.kind)
        if not ctx.place_now:
            res.degraded = True
            res.note = "无 place_now（当前地点未知）"
            return res
        res.degraded = True
        res.note = "BrainNode 无 place 字段（§2.3.2 计划内）——地点查重无法执行"
        res.knobs = {"place_now": ctx.place_now,
                     "needs": "episode.place（narration 落库时取当时生效的 place）"}
        return res


# ---------------------------------------------------------------------------
# D · 既视感（narration 的 RAG 相似度）
# ---------------------------------------------------------------------------

class DejaVu:
    """D 链路: `narration` 的 RAG 相似度 —— "**这种感觉以前有过**"。

    与 B 的分工（**别混**）:
        B = 情绪的**形状**像（键序列向量）
        D = 事情的**内容**像（narration 向量）

    两者的重合是**有价值的信号**——用户 2026-09-13:
    *"双链路都召回的节点是最重要的"*。所以 `ChannelHit` 不合并同类,
    由合成层统计"一个节点被几条链路命中"（convergence）。

    **本链路是唯一现在就能出分的**——只需要 `narration`（已有）+ `embed_fn`。

    复用 `recall.py` 的 `_embed_text` 口径（`narration + verbatim + tags`）:
    **不另起一套文本构造**——否则同一条记忆在两个地方有不同的向量，
    排查"为什么这条没被召回"会变成考古。
    """

    name = "D_deja_vu"
    kind = KIND_SIMILARITY
    scale = SCALE_COSINE
    unit = "cos"

    def gather(self, store, ctx: RecallContext) -> ChannelResult:
        res = ChannelResult(channel=self.name, kind=self.kind)
        nodes = [n for n in store.all() if n.kind == "episode" and n.narration]
        if not nodes:
            res.degraded = True
            res.note = "无 episode 可检索"
            return res
        if not ctx.query:
            res.degraded = True
            res.note = "无 query"
            return res
        if ctx.embed_fn is None:
            res.degraded = True
            res.note = "无 embed_fn（无向量后端）"
            res.knobs = {"n_nodes": len(nodes)}
            return res
        try:
            from core.brain.wiki_v2.recall import _cosine, _embed_text
            texts = [_embed_text(n) for n in nodes]
            vecs = ctx.embed_fn(texts + [ctx.query])
            qv = vecs[-1]
            scored = sorted(
                ((_cosine(qv, v), n) for v, n in zip(vecs[:-1], nodes)),
                key=lambda t: -t[0])
        except Exception as e:                       # noqa: BLE001 — 链路失败不抛
            logger.warning("D_deja_vu 降级: %s", e)
            res.degraded = True
            res.note = f"embedding 失败: {e}"
            return res
        res.hits = [ChannelHit(node=n, raw=float(s), rank=i + 1,
                               detail={"embed_chars": len(texts[i])})
                    for i, (s, n) in enumerate(scored)]
        res.knobs = {"n_nodes": len(nodes)}
        return res


# ---------------------------------------------------------------------------
# E · 无意识（认知碎片 RAG）—— 未立项
# ---------------------------------------------------------------------------

class UnconsciousRag:
    """E 链路: **认知碎片**的 RAG（用户扩展项, 未立项）。

    素材 = §6.4 的 `percepts`（"午后的阳光斜着照进来" / "纸页的霉味"）。
    用户原话: *"无意识决定了很多东西…比如去杂草屋 llm 可以写一个看到了蓝天白云,
    这样 rag 检索时就能想起来那天也是这样的好天气。"*

    ⚠️ 本链路**未立项**, 且 `percepts` 字段也还没落地。列出来是为了
    **让"以后要加一条链路"这件事在接口里可见**——不是预留空壳实现。
    """

    name = "E_unconscious"
    kind = KIND_SIMILARITY
    scale = SCALE_COSINE
    unit = "cos"

    def gather(self, store, ctx: RecallContext) -> ChannelResult:
        res = ChannelResult(channel=self.name, kind=self.kind)
        res.degraded = True
        res.note = PLANNED[self.name]
        return res


def build_channels() -> list:
    """全部链路实例（顺序 = 台账打印顺序）。

    ⚠️ 新增链路: 在这里加一行 + 在 `channels.CHANNELS` 登记名。
    **合成层不感知具体链路**——它只按 `kind`/`scale` 分派。
    """
    return [IntensityPrior(), EmotionRag(), PlaceGate(), DejaVu(),
            UnconsciousRag()]
