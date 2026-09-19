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
    | `TIME` | `freshness(age, half_life, floor)` | **降级不出分**（见下） |

    ## TIME 的判定（2026-09-17, `ESSAY_TIME_MODEL §10` 时间轴换代）

    ```
    写路径:  什么都不写 —— `ts` 本来就在节点上（不再需要 stamp 剧情时间）
    读路径:  age  = 今天 − date(node.ts)          （**整数, 单位 = 现实日**）
             TIME = floor + (1-floor) * 0.5 ** (age / half_life_days)
    ```

    ⚠️ **`floor`（下界）是 2026-09-17 加的**, 两个旋钮都在
    `settings.toml [recall]`: `time_half_life_days` / `time_freshness_floor`。
    加它的理由是实测出来的 —— `SIG=0.9` 的旧记忆在 `floor=0` 时**四天**就被
    "今天的 `SIG=0.5`"盖过, 一年后差 22 个数量级。完整对照见
    `core/worldtime/age.py::freshness` 的 docstring（那里也写明它**不是万灵药**:
    想让"情绪平淡但重要"的记忆长期占优, 缺的是**重复提起**那条通道）。

    **`TIME` 不落库**——它是"读的时候算出来的新鲜度"; 写进节点就永远停在
    写入那一刻的新鲜度, 指数白算。而 `age` 的两个输入端（`node.ts` 与"今天"）
    都不需要额外存储。

    ## 降级（`raw=None`, 绝不编分）

    - `ctx.now is None` → 调用方未给"现在"
    - `ctx.now` 解析不出日期 → 调用方传错
    - `node.ts` 缺失/坏值 → **该节点**降级, 其余照常出分

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
            from core.worldtime.age import age_days, date_of, freshness
            from core.brain.wiki_v2.recall_config import get as _knob
        except Exception as e:                       # noqa: BLE001 — 链路失败不抛
            res.degraded = True
            res.note = f"依赖不可用: {e}"
            return res

        hl = _knob("time_half_life_days")
        fl = _knob("time_freshness_floor")
        now = ctx.now
        if now is None:
            res.degraded = True
            res.note = "TIME 缺 now（ctx.now=None）——调用方未给"
            res.knobs = {"time_half_life_days": hl, "time_ready": False}
            return res
        if date_of(now) is None:
            res.degraded = True
            res.note = "TIME 缺 now（ctx.now 形态非法）"
            res.knobs = {"time_half_life_days": hl, "time_ready": False}
            return res

        hits: list[ChannelHit] = []
        no_time = 0
        for node in store.all():
            if node.kind != "episode":
                continue
            # 2026-09-17（ESSAY §10 时间轴换代）: 年龄 = 今天 − date(node.ts)
            # （**现实日**）。缺 `ts`（空串/坏值）→ None → **该节点**降级,
            # 绝不折成 0（那会让旧记忆冒充"刚发生"，det 虚高）。
            age = age_days(node.ts, now=now)
            t = freshness(age, hl, fl) if age is not None else None
            if t is None:
                no_time += 1
                hits.append(ChannelHit(
                    node=node, raw=None, rank=0,
                    detail={"reason": "no ts（未采集）"}))
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
        res.knobs = {"time_half_life_days": hl, "time_freshness_floor": fl,
                     "time_ready": True, "scored": len(scored), "no_ts": no_time}
        if not scored:
            res.degraded = True
            res.note = f"无一条 episode 有 ts（未采集 {no_time} 条）→ 不出分"
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

    ## 判据（**三个坐标 = 检索的三个维度**, 2026-09-19）

    ⚠️ **更正（用户: *"真实地名和 key 大概率并不是一个双射"*）**: `place` 键相等
    只声称 **"同一张图"** —— 表里 `ruinschoolcorridor` 的 note 自己写着
    *"也可以用做老屋子或者某种杂草秘密基地"*（一键多义）; 反过来别名 `天台`
    指向 3 个键（一地多键）。

    用户进一步指出: *"key 需要用于回放，而 writer 名则需要用于检索，**二者缺一不可**。
    但是 writer 名不像键名可以直接 literal compare……会不会是用于检索的两个维度？"*
    —— 三个维度, 但**判据的资格不同**:

    | 信号（`by`） | 载体 | 判据 | 声称 | 准入? |
    |---|---|---|---|---|
    | `same_image` | `node.place` | **字面相等**（键） | **同一张图**（素材轴 / 回放） | ✅ 是 |
    | `same_area` | `node.region` | **字面相等** | 同一片地方（粗兜底） | ✅ 是 |
    | `sem`（打分, 非信号） | `node.place_raw` vs `ctx.place_raw_now` | **语义相似度** | 有多像"同一个地方" | ❌ **不参与准入** |

    **为什么语义轴暂时不参与准入**: 准入若要靠它, 就得有**相似度阈值**, 而
    `tests/core/test_wiki_recall_ledger.py::test_no_threshold_knobs_left` 钉着
    用户的 T17 裁决 —— *"三个阈值旋钮已删, 配置面不再有任何阈值"*（理由: 未标定的
    硬闸门曾把新认知永远掐死）。语义轴现在只对**已由等值准入的命中**打分, 于是:
    * `same_image` 高 `sem` → 确实同一个地方
    * `same_image` 低 `sem` → **素材复用**（一张图被两个叙事地点共用）——这正是
      用户担心的假阳性, 但下游能**看见**它, 而不是被隐藏
    * ⚠️ **反向假阴性仍未解**（同地不同键: `school_rooftop` vs `rooftop`）——
      键不等就不准入, 语义轴没机会。**这是一个未决项**（见 TODO）:
      要么为语义轴破例开阈值, 要么改"取前 N 条"口径, 要么走地点实体表。

    三维**信息上正交**, 组合才是信号（同 `emo_span × emo_int`、同"B/D 双链路都
    召回 = 最重要"那条判据）。

    无 `embed_fn` → 语义打分缺席（`raw` 退回 1.0）, 准入不受影响。
    """

    name = "C_place"
    kind = KIND_GATE
    scale = SCALE_UNIT
    unit = "place_hit"

    def gather(self, store, ctx: RecallContext) -> ChannelResult:
        res = ChannelResult(channel=self.name, kind=self.kind)
        now_place = (ctx.place_now or "").strip()
        now_region = (ctx.region_now or "").strip()
        now_raw = (ctx.place_raw_now or "").strip()
        if not (now_place or now_region):
            res.degraded = True
            res.note = "无 place_now / region_now（当前地点未知）"
            return res
        nodes = [n for n in store.all()
                 if n.kind in ("episode", "belief", "experience")
                 and (n.place or n.region or n.place_raw)]
        if not nodes:
            res.degraded = True
            res.note = "无节点带 place/place_raw/region（旧档: M3 之前物化的没有这些字段）"
            res.knobs = {"place_now": now_place, "region_now": now_region}
            return res
        # ── 准入（**等值, 无阈值**）──
        admitted: list[tuple[BrainNode, str]] = []
        for n in nodes:
            if now_place and now_place in (n.place or []):
                admitted.append((n, "same_image"))
            elif now_region and n.region == now_region:
                admitted.append((n, "same_area"))
        if not admitted:
            res.note = "无相关命中（这段记忆不在当前素材/地区）"
            res.knobs = {"place_now": now_place, "region_now": now_region,
                         "n_nodes": len(nodes), "sem": "n/a（无准入）"}
            return res
        # ── 叙事轴: 只给**已准入**的命中打分（不参与准入, 见 docstring）──
        sem: dict[str, float] = {}
        sem_note = ""
        cand = [n for n, _ in admitted if n.place_raw]
        if not now_raw:
            sem_note = "无 place_raw_now"
        elif ctx.embed_fn is None:
            sem_note = "无 embed_fn（语义打分缺席）"
        elif not cand:
            sem_note = "无节点带 place_raw（旧档）"
        else:
            try:
                from core.brain.wiki_v2.recall import _cosine
                texts = [" ".join(n.place_raw) for n in cand]
                vecs = ctx.embed_fn(texts + [now_raw])
                qv = vecs[-1]
                for n, v in zip(cand, vecs[:-1]):
                    sem[n.id] = _cosine(qv, v)
            except Exception as e:                   # noqa: BLE001 — 打分失败不拖垮准入
                logger.warning("C_place 语义打分降级: %s", e)
                sem_note = f"语义打分失败: {e}"
        # 语义高的排前面（**排序**, 不是准入——全量参与, 无闸门）
        admitted.sort(key=lambda t: -sem.get(t[0].id, 0.0))
        res.hits = [ChannelHit(node=n, raw=float(sem.get(n.id, 1.0)), rank=i + 1,
                               detail={"by": by,
                                       "place": list(n.place or []),
                                       "region": n.region,
                                       "place_raw": list(n.place_raw or []),
                                       "sem": (round(sem[n.id], 3)
                                               if n.id in sem else None)})
                    for i, (n, by) in enumerate(admitted)]
        res.knobs = {"place_now": now_place, "region_now": now_region,
                     "n_nodes": len(nodes), "hit": len(res.hits),
                     "sem": sem_note or "ok"}
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
