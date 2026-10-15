"""compose — **最终打分**（四条召回道路的合成层; V3-3 读路径的落点）。

## 用户原话（2026-09-20）

> *"你再看看现在有没有起，现在有**剧情语义 RAG，情绪相似度 RAG，正交矩阵，地点调和
> 平均**这四条道路，可以考虑最终打分了"*

四条道路 = 四条已实现的链路（`channel_impl.py`）:

| 用户叫法 | 链路 | `kind` | `raw` 是什么 |
|---|---|---|---|
| 剧情语义 RAG | `D_deja_vu` | `SIMILARITY` | `narration` 的 cos |
| 情绪相似度 RAG | `B_emotion_rag` | `SIMILARITY` | `emo_shape` 键序列的 cos |
| **正交矩阵** | `A_intensity` | `PRIOR` | `det = SIG·TIME + emo_span·emo_int` |
| 地点调和平均 | `C_place` | `GATE` | 两轴 `magic`（素材字面 × 叙事语义） |

链路只出 `raw`（`channels.py` 纪律 #2/#3: **不归一、不排序截断**）, 最终分在这里算。

## 为什么不是一个加权和（§3.3 已裁, 别回头）

1. `det` **上位替代**了线性和（用户 2026-09-13）: 乘积里一个因子为零则整项清零,
   表达的是"两组合取条件"。
2. `relevance` **装不进矩阵**（§3.3）: *"RAG 不是矩阵的一个格子, 是矩阵的前置闸门"*。
3. 用户 2026-09-20 选定形状 = **参数可选的调和平均**（`infra/fuse.py`）,
   与 C 链路的 `magic` **同一个函数**。

## 形状: `final = fuse(rel, prior, mode="harmonic")`

```
rel   = 1 − ∏(1 − sᵢ)     ← 相关轴: 各链路证据的 **noisy-OR**（收敛; 参数为零）
prior = A 的 det          ← 强度轴: **不归一**（用户 2026-09-20 裁决, 见下）
```

`rel` 用 noisy-OR 而不是平均, 是为了兑现用户 2026-09-13 那条判据:
*"双链路都召回的节点是最重要的"* —— 一条证据 → 它的分; 两条证据 → 比任一条都高;
都没命中 → 0。**没有权重旋钮**。

## 三根轴各自的处理（**按 `kind` 分派, 合成层不认具体链路**）

| `kind` | 链路 | 怎么用 | 为什么 |
|---|---|---|---|
| `PRIOR` | A | **原样**（上界不夹, `clamp=False`） | 用户: *"不必归一，这个矩阵携带的信息本身就比较重很合理"* |
| `SIMILARITY` | B / D | **池内 min-max** → [0,1] | 实测绝对值不可分（见下） |
| `GATE` | C | **原样**（构造上已是 [0,1] 的 `magic`） | 两轴融合已经把"一轴为零 ⇒ 0"吃进去了 |

⚠️ **A 的 `scale` 声明是 `unit`（`# [0, 1]`）但值域是 [0, 2]** ——
`IntensityPrior` 的注释已按用户裁决改成"[0,2]"。所以合成层**不按 `scale` 归一 A**
（归一就是压平它的上半段）; `clamp=False` 是这条裁决在形状函数里的落点。

### 为什么 `SIMILARITY` 必须池内 min-max（**实测, 不是偏好**）

真档 + `nomic-embed-text-v1.5` 实测（`experiments/recall_compose_probe.py`, 2026-09-20）:

```
同角色 narration 对   0.781 ~ 0.837
跨角色 narration 对   0.722 ~ 0.859
**域外 query**        0.336 ~ 0.798      ← "The quick brown fox…" 对真档 episode
```

**域外最大 0.798 > 同角色最小 0.781** ⇒ cos 的**绝对值在这套模型/数据上不可分**
（Q11 那条基线问题的真档复现）。若把 cos 直接当 [0,1] 的"相关度"喂进融合,
`prior`（真档 0.30~0.42）会**永远**是两轴里小的那个 → 融合退化成"只按 A 排序",
D/B 白召回。而**同一个 query 内部**它仍然可分（留一法: 自己 0.977 / 兄弟 0.80~0.83）。

⇒ 池内 min-max。这不是新发明: §10 Q31 引的 AgentGal 召回链就是
*"融合（vector 0.75 / BM25 0.25，**各自 min-max 归一化**）→ rerank → 加权排序 → 取 top 3,
**全程无阈值**"*。**无阈值**这条纪律由此继续成立。

⚠️ **池内 min-max 的三个必然后果**（是语义, 不是 bug —— 写在这里免得以后当故障查）:

1. **池内最差的那条 `rel = 0`** → `fuse(0, prior) = 0` → 该链路对它**等于没命中**,
   于是它落进 `dropped_no_rel`（有先验、无证据 → 不准入）。池越小越明显:
   **两条候选时必有一条 rel=0**（"较差的那条不构成证据"）。
2. **池内差距被拉满**: `0.86 vs 0.80` 与 `0.86 vs 0.10` 归一后**长得一样**。
   所以 `rel` 只是"**本次池内的相对相关度**", 不是绝对相似度。
3. **"这个 query 跟库里任何一条都不相关"测不出来**（域外 query 实测能到 0.798,
   与真·同角色对 0.781~0.837 重叠）。要测它得先给模型标定一条基线 —— 那是**阈值旋钮**,
   T17 不许。这是"无阈值"的代价, 记在这里而不是偷偷加一个数。

## ⚠️ "命中"必须先定义 —— 否则收敛判据是假的

`D_deja_vu` 会把池里**每一个** episode 都出分（含负 cos, 全量返回, 不筛）,
而 `C_place` 显式 `score <= 0 → skip`。所以按"出了分"数收敛, **每个节点都是满命中**
（收敛数恒等于链路条数, 判据退化成常数）。

本模块的定义: **命中 = 进了该链路的前 `hit_k` 名**（`[recall].sim_k`, 默认 5）。
这是**名次门槛, 不是分数阈值**（T17 只许"取几条"这类旋钮）。

## 两条不参与的纪律

1. **降级链路不参与**（`degraded=True` 或一条 raw 都没有）: 它缺席,
   绝不回退成 0 —— 0.0 是"算了, 就是 0 分", 会把"没数据"变成"反证据"。
2. **A 不能单独准入**: 只被 A 命中（没有任何相关证据）→ `rel = 0` → `fuse(0, prior) = 0`
   → 落选并计入 `dropped_no_rel`。*"珍贵保底"*是**独立旁路**（`channels.py`: 随机摘段/
   珍贵保底不是 query 驱动, 不进本协议）, 不靠 A 混进来。

## 先验缺席 → `pending`（不参与排序）

A 对**没有 `ts`** 的旧档节点给 `raw=None`（`IntensityPrior` 降级语义: *"不带 TIME 的
候选进'待补'集合, 不参与排序"*）。这类节点若有相关证据 → 进 `ComposeResult.pending`,
**不进 `items`**; 等 `ts` 补齐后自然回到排序里。

## 台账（观测层, 零行为影响）

本模块**纯函数、不写日志**。消费方一行接上:

    from core.brain.read import recall_ledger
    res = recall_now(store, ctx)
    recall_ledger.log_compose(char_id=store.path.parent.parent.name,
                              **res.ledger_fields())
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.brain.read.channels import (
    KIND_PRIOR,
    SCALE_COSINE,
    ChannelHit,
    ChannelResult,
    RecallContext,
)
from infra.fuse import DEFAULT_MODE, MODES, fuse

#: 命中门槛的缺省值（正常走 `[recall].sim_k`=`5`）——**名次, 不是分数阈值**
DEFAULT_HIT_K = 5


@dataclass
class Composed:
    """一个候选的最终分与它的来路（台账/排查用）。"""

    node: object
    final: float = 0.0
    #: 相关轴（各链路证据的 noisy-OR, ∈ [0,1]）; 没有任何相关证据 → 0.0
    rel: float = 0.0
    #: 强度轴（A 的行列式, **不归一**; 真档 0.30~0.42, 上界 2）; 缺席 → None
    prior: float | None = None
    #: 命中它的链路名（**top-k 内**才算; 台账号召回的收敛度）
    channels: list[str] = field(default_factory=list)
    #: 链路名 → 归一后的贡献（"这个分是谁给的"）
    per_channel: dict[str, float] = field(default_factory=dict)
    detail: dict = field(default_factory=dict)


@dataclass
class ComposeResult:
    """一次合成的全部产出（**已按 final 降序**）。"""

    items: list[Composed] = field(default_factory=list)
    #: 有相关证据、但先验缺席（A 的 `raw=None`: 旧档无 `ts`）→ **待补, 不参与排序**
    pending: list[Composed] = field(default_factory=list)
    #: 只被 A 命中（没有任何相关证据）→ 落选（A 不能单独准入）
    dropped_no_rel: int = 0
    #: 两轴有一轴是"真 0 分" → 融合为 0（`fuse(高, 0) == 0` 是形状语义）
    dropped_zero: int = 0
    #: 这次降级/无命中的链路（链路名 → 单行原因）——**它们缺席, 不是 0 分**
    degraded: dict[str, str] = field(default_factory=dict)
    mode: str = DEFAULT_MODE
    knobs: dict = field(default_factory=dict)

    def ledger_fields(self) -> dict:
        """→ `recall_ledger.log_compose(**…)` 的入参（不含 `char_id`）。"""
        rel = [c.rel for c in self.items + self.pending]
        pri = [c.prior for c in self.items if c.prior is not None]
        top = ",".join(f"{getattr(c.node, 'id', '?')}:{c.final:.3f}"
                       for c in self.items[:5]) or "-"
        return {
            "cands": len(self.items) + len(self.pending) + self.dropped_no_rel
                     + self.dropped_zero,
            "ranked": len(self.items),
            "pending": len(self.pending),
            "no_rel": self.dropped_no_rel,
            "mode": self.mode,
            "rel_band": (min(rel), max(rel)) if rel else (0.0, 0.0),
            "prior_band": (min(pri), max(pri)) if pri else (0.0, 0.0),
            "degraded": ",".join(sorted(self.degraded)) or "-",
            "top": top,
        }


# ---------------------------------------------------------------------------
# 归一（按 kind/scale 分派）
# ---------------------------------------------------------------------------

def _ranked(res: ChannelResult) -> list[ChannelHit]:
    """出分的命中, 按 `(-raw, id)` 降序 —— **不信任输入顺序, 自己排**（可复现）。"""
    hits = [h for h in res.hits if h.raw is not None]
    hits.sort(key=lambda h: (-float(h.raw), getattr(h.node, "id", "")))
    return hits


def normalize(hits: list[ChannelHit], *, scale: str) -> dict[str, float]:
    """一条链路的 `raw` → [0,1]（`node.id` → 分）。

    * `SCALE_COSINE`（B/D）→ **池内 min-max**（理由见模块 docstring 的实测块）。
      池内全同分: 有正值 → 都是 1.0（"都一样相关"）; 全非正 → 0.0（"都不相关"）。
    * 其它（`unit`: C 的 `magic`）→ **原样**, 负值夹到 0。**不做 min-max** ——
      它本来就是 [0,1] 的绝对分, 拉到池内相对会凭空制造"最差的一定是 0"。
    """
    raw = {getattr(h.node, "id", ""): float(h.raw) for h in hits}
    if scale != SCALE_COSINE:
        return {k: max(0.0, v) for k, v in raw.items()}
    if not raw:
        return {}
    lo, hi = min(raw.values()), max(raw.values())
    span = hi - lo
    if span <= 1e-9:
        v = 1.0 if hi > 0.0 else 0.0
        return {k: v for k in raw}
    return {k: (v - lo) / span for k, v in raw.items()}


def _noisy_or(vals) -> float:
    """证据累积 `1 − ∏(1 − sᵢ)`（参数为零; 单条 → 它自己; 空 → 0）。"""
    keep = 1.0
    for s in vals:
        keep *= 1.0 - min(1.0, max(0.0, float(s)))
    return 1.0 - keep


# ---------------------------------------------------------------------------
# 合成
# ---------------------------------------------------------------------------

def compose(results: list[ChannelResult], *,
            mode: str = DEFAULT_MODE,
            hit_k: int | None = None,
            top: int | None = None) -> ComposeResult:
    """四条道路 → 最终分（见模块 docstring）。

    Args:
        results: 各链路的产出（顺序无关）。
        mode: 融合形状（`infra/fuse.py` 的 `MODES`）——**代码选项, 不是配置项**。
        hit_k: "命中"的名次门槛（默认 `[recall].sim_k`）。⚠️ 是名次不是分数。
        top: 截断条数（None = 全给, 由调用方决定取几条）。

    Returns: `ComposeResult`（`items` 已按 `final` 降序）。
    """
    if mode not in MODES:
        raise ValueError(f"未知融合形状: {mode!r}（可选 {sorted(MODES)}）")
    if hit_k is None:
        hit_k = _hit_k()
    hit_k = max(int(hit_k), 1)

    out = ComposeResult(mode=mode, knobs={"hit_k": hit_k})
    by_id: dict[str, Composed] = {}
    no_prior: set[str] = set()          # A 说"这个节点 TIME 未定"（raw=None）
    prior_hit: set[str] = set()

    def slot(node) -> Composed:
        nid = getattr(node, "id", "")
        c = by_id.get(nid)
        if c is None:
            c = by_id[nid] = Composed(node=node)
        return c

    for res in results:
        hits = _ranked(res)
        if res.degraded or not hits:
            out.degraded[res.channel] = res.note or "无命中（raw 全为 None）"
            continue
        if res.kind == KIND_PRIOR:
            # 先验轴: **原样**（用户裁决"不归一"）; raw=None 的记成"待补"。
            # ⚠️ 这里按 **kind** 分派, 不认链路名 —— 新增一条 PRIOR 链路零改动。
            for h in res.hits:
                if h.raw is None:
                    no_prior.add(getattr(h.node, "id", ""))
            for h in hits:
                c = slot(h.node)
                c.prior = float(h.raw)
                prior_hit.add(getattr(h.node, "id", ""))
            continue
        # 证据轴: 归一 → **top-k 才算命中**（名次门槛, 不是分数阈值）
        norm = normalize(hits, scale=res.scale)
        for h in hits[:hit_k]:
            nid = getattr(h.node, "id", "")
            c = slot(h.node)
            c.per_channel[res.channel] = norm.get(nid, 0.0)
            c.channels.append(res.channel)

    for nid, c in by_id.items():
        c.rel = _noisy_or(c.per_channel.values())
        if c.prior is None:
            if c.rel > 0.0:
                out.pending.append(c)        # 有证据、无先验 → 待补, 不参与排序
            continue
        if c.rel <= 0.0:
            out.dropped_no_rel += 1          # A 不能单独准入（珍贵保底是独立旁路）
            continue
        c.final = fuse(c.rel, c.prior, mode=mode, clamp=False)
        if c.final <= 0.0:
            out.dropped_zero += 1            # 两轴里有一轴是真 0 分
            continue
        out.items.append(c)

    out.items.sort(key=lambda c: (-c.final, -c.rel, -(c.prior or 0.0),
                                  getattr(c.node, "id", "")))
    if top is not None:
        out.items = out.items[:max(int(top), 0)]
    out.knobs["cands"] = len(by_id)
    out.knobs["a_no_time"] = len(no_prior - prior_hit)
    out.knobs["prior_axis"] = "det 原样（不归一）"
    return out


def _hit_k() -> int:
    """读 `[recall].sim_k`（配置层异常 → 缺省, 绝不阻断）。"""
    try:
        from core.brain.read.recall_config import get
        return int(get("sim_k"))
    except Exception:                            # noqa: BLE001 — 配置层不阻断召回
        return DEFAULT_HIT_K


# ---------------------------------------------------------------------------
# 读路径入口（跑全部链路 → 合成）
# ---------------------------------------------------------------------------

def gather_all(store, ctx: RecallContext) -> list[ChannelResult]:
    """跑**全部**链路（顺序 = 登记顺序）。单条链路失败已在链路内降级, 这里不抛。"""
    from core.brain.read.channel_impl import build_channels
    return [ch.gather(store, ctx) for ch in build_channels()]


def recall_now(store, ctx: RecallContext, *, mode: str = DEFAULT_MODE,
               hit_k: int | None = None, top: int | None = None) -> ComposeResult:
    """读路径入口 = `gather_all` + `compose`（**只读 store, 不改任何状态**）。

    ⚠️ V3-3 的注入视图 / "回想注入"（玩家问"你还记得那天吗"）都从这里进;
    注入哪些条、按 kind 配额怎么分, 是**渲染层**的事（`render.py`）, 不在本模块。
    """
    return compose(gather_all(store, ctx), mode=mode, hit_k=hit_k, top=top)


__all__ = [
    "DEFAULT_HIT_K",
    "ComposeResult",
    "Composed",
    "compose",
    "gather_all",
    "normalize",
    "recall_now",
]
