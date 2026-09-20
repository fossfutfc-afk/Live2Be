# -*- coding: utf-8 -*-
"""五条召回链路的实现（V3-3 前置）—— 接口见 `channels.py`。

## 本文件的现状：**大部分链路是"诚实的空"**

用户要的是"先写接口, 等有了接口统一构造公式"。所以这里实现的是**形态与降级路径**,
不是打分公式。如实记下每条链路**现在缺什么数据**——这才是本阶段的价值。

| 链路 | 现在能不能出分 | 缺什么 |
|---|---|---|
| **A** `A_intensity` | ✅ **能** | 只需要 `ctx.story_now`（游标）+ 节点 `story_time`。**旧档节点**（无 `story_time`）逐条跳过 |
| **B** `B_emotion_rag` | ✅ **能**（T15, 2026-09-15） | 需要 `ctx.emo_now` + 节点 `emo_shape`（digest 按板指针物化）+ `embed_fn` |
| **C** `C_place` | ✅ **能**（2026-09-20 两轴融合） | `ctx.place_now` + 节点 `place`（字面轴, 0 调用）; 叙事轴那一半还要 `ctx.place_raw_now` + 节点 `place_raw` + `embed_fn`（缺则 `axes=1`, 只用素材轴） |
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

    ⚠️ **值域是 [0, 2], 不是 [0, 1]**（2026-09-20 用户裁决时把这条注释更正过来）:
    `det` 是**两格之和**, 每格 ≤ 1×1 ⇒ 上界 2。`scale` 声明仍是 `SCALE_UNIT`
    ——枚举没错, 错的是"`unit` 就等于 ≤1"这个旧读法（`channels.py` 那里也标了）。

    **合成层因此不归一它**: 用户 2026-09-20 —— *"不必归一，这个矩阵携带的信息本身
    就比较重很合理"*。`compose.py` 把它当**强度轴**原样用（`fuse(..., clamp=False)`,
    **上界不夹**, 免得把 det>1 的上半段压平）。

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
    （**2026-09-20 已落地**: `compose.py` 把它放进 `ComposeResult.pending`
    = "待补" —— 有相关证据也**不参与排序**, 补上 `ts` 后自然回到排序里）。
    """

    name = "A_intensity"
    kind = KIND_PRIOR
    scale = SCALE_UNIT
    unit = "det"

    def gather(self, store, ctx: RecallContext) -> ChannelResult:
        res = ChannelResult(channel=self.name, kind=self.kind, scale=self.scale)
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
        res = ChannelResult(channel=self.name, kind=self.kind, scale=self.scale)
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
    """C 链路: 地点召回 —— **两轴融合**（`GATE` 的准入面 + 叙事轴的打分面）。

    用户 2026-09-13 的定位是"**检测**"（"地点字段查重"）。2026-09-20 用户又给了
    融合口径: *"最好是混合策略，一个特殊的 magic function，在 writer 词和 key
    相似度都高的时候值高，反之一般"* ⇒ 本链路现在**两根轴一起算分**
    （`core/media/place_fuse.py` 的 `magic` = 调和平均, 无阈值）。

    ## 两根轴（判据资格不同, 别混）

    | | 载体 | 判据 | 声称 |
    |---|---|---|---|
    | `sk`（素材轴） | `node.place` ↔ `ctx.place_now` | **字面**（同名 / 别名相交 / 键名 token） | 有多像**同一张图** |
    | `sw`（叙事轴） | `node.place_raw` ↔ `ctx.place_raw_now` | **语义**（embedding cos, 要 `embed_fn`） | 有多像**同一个地方的说法** |

    ⚠️ **更正（用户: *"真实地名和 key 大概率并不是一个双射"*）**: `place` 键相等只声称
    **"同一张图"** —— `ruinschoolcorridor` 的 note 自己写着*"也可以用做老屋子或者某种
    杂草秘密基地"*（一键多义）; 反过来别名 `天台` 指向 3 个键（一地多键）。
    两维**信息上正交**, 组合才是信号（同 `emo_span × emo_int`、同"双链路都召回 = 最重要"）。

    ## 融合出来的三条可读结论

    * **同键 + 同说法**（`sk=1, sw` 高）→ 最高: 确实同一个地方
    * **同键 + 说法不像**（`sk=1, sw` 低）→ 中: **素材复用**（一张图被两个叙事地点共用）
      —— 用户担心的假阳性**可见**（`detail.sem` 低）, 而不是被隐藏
    * **不同键 + 说法像**（`sk` 中, `sw` 高）→ 中高: **同地不同键** —— 这正是 2026-09-19
      记下的那条**反向假阴性**（`school_rooftop` vs `rooftop`: 键不等就不准入, 语义轴
      没机会）。现在靠 `sk` 的**字面**那一半（别名 / 键名 token）把它们连起来
    * **有键但不符 + 说法像**（`sk=0`, `sw` 高）→ **0**（融合形状自带的语义: 不是
      "弱关系"）—— "只有措辞像、键八竿子打不着"的候选**仍然进不来**, 语义轴
      **没有**偷偷放宽准入（这是用户担心的假阳性的防线, 别拆）
    * ⭐ **没有键**（`node.place` 为空 = 素材轴**不可算**）+ 说法像 → **走单轴**
      （`raw = sw`, `detail.by="narrative_only"`, `detail.axes=1`）。
      **用户 2026-09-20 裁决: *"还是走单轴"*** —— **键未知 ≠ 键不符**:
      前者是"没采集到"（旧档 / 标注层没跑）, 后者才是反证据; 与另一侧早就有的降级
      路径（无 `embed_fn`/无原话 → 只用素材轴）**对称**。
      ⚠️ **为什么必须修**: 真档实测 `place` 键 **0 条**、只有 `payload.place_hint`
      （2 条）—— 而 `magic(任意, 0) == 0` 会让这些记忆**永远进不来**（C 路恒空手）。
      有 `keys.no_key` 计数可观测（台账里能看到"这次有多少条是单轴进来的"）。

    ⚠️ **`key_sim` 满分有两种来源, 别混**: ① 键**字面相等**（`key_sim_by="same"`,
    `detail.same_image=True` —— 这才是"同一张图"）; ② 键名 **token 包含**
    （`rooftop` ⊆ `school_rooftop`, `key_sim_by="token"` —— "同一族图"）。
    要严格分组请认 `detail.same_image`, 不要用 `key_sim == 1` 去推。

    ## 两条纪律

    * **不给分定阈值**（T17: 配置面不许有阈值旋钮）——本链路只出 `raw`;
      **取前 k 条是合成层的事**（`channels.py` 纪律 #2/#3）
    * **无 `embed_fn` / 无 `place_raw` → 叙事轴缺席**: `raw` 退回**素材轴那一半**
      （`axes=1` 在 `detail` 里标出来）, 准入不受影响 —— 与"宁缺勿错"一致
    """

    name = "C_place"
    kind = KIND_GATE
    scale = SCALE_UNIT
    unit = "place_fuse"

    def gather(self, store, ctx: RecallContext) -> ChannelResult:
        res = ChannelResult(channel=self.name, kind=self.kind, scale=self.scale)
        now_place = (ctx.place_now or "").strip()
        now_raw = (ctx.place_raw_now or "").strip()
        if not now_place:
            res.degraded = True
            res.note = "无 place_now（当前地点未知）"
            return res
        nodes = [n for n in store.all()
                 if n.kind in ("episode", "belief", "experience")
                 and (n.place or n.place_raw)]
        if not nodes:
            res.degraded = True
            res.note = "无节点带 place/place_raw（旧档: M3 之前物化的没有这些字段）"
            res.knobs = {"place_now": now_place}
            return res
        # ── 素材轴（字面, 0 调用）: 每个候选与当前键的相似度 ──
        from core.media import place_fuse
        sk: dict[str, tuple[float, str, str]] = {}
        for n in nodes:
            sk[n.id] = place_fuse.key_similarity_to_set(n.place, now_place)
        # ── 叙事轴（语义, 要询问向量后端）: 只对**有原话可比**的候选算 ──
        sem: dict[str, float] = {}
        sem_note = ""
        cand = [n for n in nodes if n.place_raw]
        if not now_raw:
            sem_note = "无 place_raw_now"
        elif ctx.embed_fn is None:
            sem_note = "无 embed_fn（语义打分缺席 → 只用素材轴）"
        elif not cand:
            sem_note = "无节点带 place_raw（旧档）"
        else:
            try:
                from core.brain.wiki_v2.recall import _cosine
                texts = [" ".join(n.place_raw) for n in cand]
                vecs = ctx.embed_fn(texts + [now_raw])
                qv = vecs[-1]
                for n, v in zip(cand, vecs[:-1]):
                    sem[n.id] = max(0.0, _cosine(qv, v))   # 负相关不是"弱相关" → 夹到 0
            except Exception as e:                   # noqa: BLE001 — 打分失败不拖垮准入
                logger.warning("C_place 语义打分降级: %s", e)
                sem_note = f"语义打分失败: {e}"
        # ── 融合（调和平均; **缺的那根轴走单轴, 不当 0**）──
        # ⭐ 2026-09-20 用户裁决（*"还是走单轴"*）: **键未知 ≠ 键不符**。
        #   节点没有 `place` 键 = 素材轴**不可算**（旧档 / 标注层没跑）——与
        #   "有键但不符"（`k_sim == 0`）是两件事。前者缺席, 后者才是反证据。
        #   这与另一侧早就有降级路径对称（`s is None` → 只用素材轴）。
        #   为什么必须修: 真档实测 `place` 键 **0 条**、只有 `place_hint`,
        #   而 `magic(任意, 0) == 0` ⇒ 那些记忆**永远进不来**（C 路恒空手）。
        hits: list[ChannelHit] = []
        for n in nodes:
            k_sim, k_by, k_key = sk[n.id]
            s = sem.get(n.id)
            has_key = bool(n.place)                  # 素材轴**可算**吗（≠"值是不是 0"）
            # `detail.by` 标的是**键的来源**（不是轴的条数; 条数看 `axes`）:
            #   `same_image` = 键字面相等 | `similar_key` = 别名/token 同族
            #   `no_key` = 素材轴不可算（没有键）—— ⭐ 2026-09-20 新增
            key_by = "same_image" if k_by == "same" else "similar_key"
            if s is None:                            # 只有素材轴可算 → 用它的分
                score, axes, by = k_sim, 1, key_by
            elif not has_key:                        # 只有叙事轴可算 → 走单轴（用户裁决）
                score, axes, by = s, 1, "no_key"
            else:                                    # 两轴齐 → magic（一轴为零 ⇒ 0）
                score, axes, by = place_fuse.magic(s, k_sim), 2, key_by
            if score <= 0.0:
                continue                             # 能算的轴都给不出关系 → 不编命中
            # ⚠️ `same_image` **只认键字面相等**（`key_sim_by == "same"`）——
            # `key_sim` 满分还有一种来源: 键名 token 包含（`rooftop` ⊆ `school_rooftop`）。
            # 那种是"同一族图"，不是"同一张图"，别混。**没有键更不许声称**。
            same = has_key and k_by == "same"
            hits.append(ChannelHit(
                node=n, raw=float(score), rank=0,
                detail={"by": by,
                        "same_image": same,
                        "key_sim": round(k_sim, 3), "key_sim_by": k_by,
                        "key": k_key,
                        "sem": (round(s, 3) if s is not None else None),
                        "axes": axes}))
        hits.sort(key=lambda h: -h.raw)
        for i, h in enumerate(hits, 1):
            h.rank = i
        res.hits = hits
        if not hits:
            res.note = "无相关命中（能算的轴都为零: 素材不相干, 且没有可比的 writer 原话）"
        res.knobs = {"place_now": now_place, "n_nodes": len(nodes),
                     "hit": len(hits), "same_image": sum(1 for h in hits
                                                         if h.detail["same_image"]),
                     "no_key": sum(1 for n in nodes if not n.place),
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
        res = ChannelResult(channel=self.name, kind=self.kind, scale=self.scale)
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
        res = ChannelResult(channel=self.name, kind=self.kind, scale=self.scale)
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
