# -*- coding: utf-8 -*-
"""like — **相似召回**: 给一段情境（玩家这一句 / 本段经历）⇒ **最像的 k 条**。

「一个包、两个类」: `find` = 定向寻找（给锚, 要**全部**符合的; 分只是展示顺序）,
`like` = 本模块（给情境, 要最像的 k 条; **顺序就是答案**, 分是有意义的）。
两类共用形状 = `pack.Candidate`。

## 打分函数（`part_*`）—— 每个**独立**、每个**可单测**、每个返回 `(分, 一句话)`

| 函数 | 类 | 分 | 一句话（`why` 的一格） |
|---|---|---|---|
| `part_lexical` | **内容**（唯一能单独准入的） | tags / 标题 / 正文覆盖 **取最大** | `tags[苔藓]` · `标题点名` · `覆盖 0.62` |
| `part_temporal` | 加成 | `freshness(age)` ∈ **[floor, 1]** | `今天` · `12 天前` |
| `part_prior` | 加成 | `min(sig·TIME + emo_span·emo_int, 1)` | `sig .85·情绪 .16` |
| `part_name` | 加成 | 0 / 1（query 点到某个对象名） | `名字[杂草屋]` |

一句话由**函数自己**写（它算的时候就知道自己走的是哪一路）; `like()` 只按固定顺序拼。
⛔ **绝不事后重算** —— 重算就是第二个真源（`recall._keyword_candidates` 踩过）。

## 怎么合: **加权平均** + 一条单独的准入规则

```
final = Σ wᵢ·sᵢ / Σ wᵢ          w = {lexical 1.00, temporal .15, prior .15, name .15}
准入  = 内容类里至少一个 > 0
```

* 分母是正常数 ⇒ **排序与"不带分母的加权和"完全一致**; 带分母只是把分压回 `[0,1]`、
  台账好看（用户 2026-10-08: *"最终调用各函数采用加权平均吧, 这样不费脑子"*）。
* ⚠️ **准入是唯一一条不是加权平均的规则**（**不是阈值** —— 边界就是"零重合"这个自然 0）。
  零重合时若只看加权平均, `时间 + 先验 + 名字` 也能凑出一份分来: 真机 haruka 实测
  「老师，你今天有空吗」凑出 **10 条并列**、排序全交给先验 ⇒ 召回退化成"关于老师最重要的事",
  **每轮同样两条**（正是 `recall.recall_episodes` docstring 警告的"永远长不出新边"）。
  所以: **准入只认内容轴; 名字与先验只能在"已经像"的候选上加成**（用户同日裁"只加成, 不作准入"）。
* ⚠️ 权重是**代码常量, 先不进配置面**（配置面只留"取几条"与"半衰期/下界"那类; 阈值旋钮
  2026-09-15 已全删, `test_no_threshold_knobs_left` 钉着）。要按模型标定了再上配置面 ——
  免得又是一个"看着像旋钮、实际不做事"的值（`cand_med` 的教训）。

## 与旧件的关系（**不复用资源**）

`compose.recall_now` / `recall.recommend_candidates` 一个都不 import（守门⑤ 扫 AST）:
前者在 digest 场景**四链路降级三条**, 后者**无 embedder 时四个查询全空**（真档实测）。
`_bigrams` 这边**自己一份**（`recall.py` 也有, 但那边整族待删, 不许 import）。
✅ 照用的只有两样通用工具: `core.common.fuse`（真接语义轴时再用）与
`core.worldtime.age`（`age_days` / `freshness` / `render_relative` —— 时间真源, 不在 `read/` 里）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from core.brain.address import normalize_title
from core.brain.graph import graph_of
from core.brain.read.pack import Candidate, ledger_line
from core.worldtime.age import (DEFAULT_FRESHNESS_FLOOR, DEFAULT_HALF_LIFE_DAYS,
                               age_days, freshness, render_relative)

logger = logging.getLogger(__name__)

#: `like` 取几条的**回落值**（真源 = `settings.toml [recall].like_k`）
LIKE_K = 3

# ⚠️ 下面三个是**代码常量, 不是旋钮**（理由见模块 docstring 的权重那条）
_TAG_BASE, _TAG_STEP = 0.60, 0.10      # tags 命中: 基分 + 每多命中一个 +0.10
_TITLE_HIT = 0.85                      # 标题（剥壳后）整体出现在 query
_COVER_MIN = 0.35                      # 正文覆盖率下限（`recall._keyword_candidates` 的 0.35 同款）
_NAME_HIT = 1.00                       # 名字/别名命中（只是加成的一份, 不作准入）


# ---------------------------------------------------------------------------
# 料（一次 `like` 的共享输入）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LikeCtx:
    """一次召回的共享料: `query` · `now` · **query 点到的对象及其车道**。

    车道只为"query 里真的被叫到"的对象建 ⇒ 多数轮零成本。
    """

    query: str = ""
    now: object = None
    #: entity_id → 它**在 query 里被叫到的那个写法**（`why` 里要印这个名字）
    named: dict[str, str] = field(default_factory=dict)
    #: entity_id → 它车道上（`about` 边指向它）的节点 id 集合
    lanes: dict[str, frozenset[str]] = field(default_factory=dict)


def build_ctx(store, *, query: str, now) -> LikeCtx:
    """建料: 名字表（entity 的名字 + 别名）→ query 里命中的那几个 → 它们的车道。

    ⚠️ 节点表**在这里自己取全量**（不接调用方传进来的表）—— 名字表要从里面挑 entity;
    若让调用方传"`kinds` 过滤后"的那一份, 名字那一路会**恒空**而且**静默**
    （只是少一份加成, 不报错）。踩过一次, 所以这条做成结构性不可能。
    车道取不到（图坏了）**不是错**: 只是少一份加成（宁缺勿错, 不阻断召回）。
    """
    q = (query or "").strip()
    names: dict[str, tuple[str, str]] = {}          # 名字(casefold) → (entity_id, 原写法)
    for n in store.all():
        if getattr(n, "kind", "") != "entity":
            continue
        forms = [getattr(n, "name", "")] + list(getattr(n, "aliases", ()) or ())
        for form in forms:
            if form:
                names.setdefault(form.casefold(), (n.id, form))
    qf = q.casefold()
    named = {eid: raw for cf, (eid, raw) in names.items() if cf in qf}
    lanes: dict[str, frozenset[str]] = {}
    if named:
        try:
            g = graph_of(store)
            lanes = {eid: frozenset(g.lane(eid)) for eid in named}
        except Exception as e:                       # noqa: BLE001 — 少一份加成, 不阻断
            logger.info("recall_like lanes=skip reason=%s", e)
    return LikeCtx(query=q, now=now, named=named, lanes=lanes)


# ---------------------------------------------------------------------------
# 打分函数（`part_*`）—— 每个独立、每个可单测
# ---------------------------------------------------------------------------

def part_lexical(node, ctx: LikeCtx) -> tuple[float, str]:
    """**内容轴**（唯一能单独准入的一类）: tags / 标题 / 正文覆盖 —— 三路取最大。

    * **tags**: 检索词命中（`#` 开头的是**标记空间**, 不是检索词 —— 同 `render` 的口径）。
      最强的一般信号: 真机 haruka 的 tags 是 LLM 写的**具体名词**（苔藓 / 杂草屋 / 团子 / 中秋节）。
    * **标题**: 剥壳后**整体**出现在 query 里（"她还记得那件事的名字"）。
    * **正文覆盖**: query 的 2-gram 有多少**落在**节点的正文里。

    ⚠️ **不收对称 Dice**（`recall._keyword_candidates` 那条 2-gram 路）: 它对
    "短 query vs 长正文"天然低 —— 真档实测四个查询**全空**; 而覆盖率正是那个场景要的口径
    （实测「那盆苔藓长得怎么样了」⇒ tags 命中 3 条, 旧件只给 1 条）。
    """
    q = ctx.query
    if not q:
        return 0.0, ""
    best, why = 0.0, ""
    hits = [t for t in (getattr(node, "tags", ()) or ())
            if t and not t.startswith("#") and t in q]
    if hits:
        best, why = _TAG_BASE + _TAG_STEP * (len(hits) - 1), f"tags[{','.join(hits)}]"
    title = normalize_title(getattr(node, "title", ""))
    if title and title in q and _TITLE_HIT > best:
        best, why = _TITLE_HIT, "标题点名"
    q2 = _bigrams(q)
    b2 = _bigrams(_body(node))
    if q2 and b2:
        cov = len(q2 & b2) / len(q2)
        if cov > _COVER_MIN and cov > best:
            best, why = cov, f"覆盖 {cov:.2f}"
    return best, why


def part_temporal(node, ctx: LikeCtx) -> tuple[float, str]:
    """**时间轴**: `freshness(age)` ∈ **[floor, 1]**（`floor` 是渐近下界, **不归零**）。

    单位 = **现实日**（`ESSAY_TIME_MODEL §10` 时间轴换代后唯一日期轴）, 年龄 = 今天 − 节点那天。
    缺/坏 `ts` ⇒ **降级不出分**（0 分 + 一句话）, **绝不折成"刚发生"**
    （`age_days` 的纪律: 折成 0 会让旧记忆冒充新的）。
    """
    age = _age(node, ctx)
    if age is None:
        return 0.0, "无 ts"
    t = _freshness(age)
    return t, render_relative(age, float(getattr(node, "significance", 0.5) or 0.5))


def part_prior(node, ctx: LikeCtx) -> tuple[float, str]:
    """**先验轴**: **这件事本身重不重要** —— `min(sig·TIME + emo_span·emo_int, 1)`。

    * `sig` = `node.significance`; `emo_span`/`emo_int` = 那件事的情绪跨度与强度
      （缺一格 ⇒ 第二行整行为 0, 也就是退化成 `sig·TIME`）。
    * **夹到 1**: 真档实测 `det` 值域 **0.292 ~ 1.45**（5 条 >1）—— 不夹的话同一权重下
      先验的实际话语权会大到 1.45 倍。⚠️ 这不推翻用户 2026-09-20 那条「`det` 不归一」
      （*"这个矩阵携带的信息本身就比较重很合理"*）: 那条管的是 `compose` 的**乘性轴**,
      这里它是"最多算满一份"的**加成分**。

    ⚠️ **TIME 与 `part_temporal` 同源**（两处都取 `freshness`）⇒ 时间在最终分里进了两次:
    一次独立、一次乘在 `sig` 上。这是照 `compose` 的 A 链路 `det` 的形状（2026-10-08 批的
    就是这一版）; 若要让"老而重要"的记忆更抗老, 可把 TIME 格去掉（`prior = sig + emo`）
    —— 那正是 `time_freshness_floor` 当初加进来要保护的东西（见 `age.py::freshness`）。
    """
    age = _age(node, ctx)
    if age is None:
        return 0.0, "先验无 ts"
    sig = float(getattr(node, "significance", 0.0) or 0.0)
    span = float(getattr(node, "emo_span", 0.0) or 0.0)
    emo_i = float(getattr(node, "emo_int", 0.0) or 0.0)
    emo = span * emo_i
    det = sig * _freshness(age) + emo
    return min(det, 1.0), f"sig {sig:.2f}" + (f"+情绪 {emo:.2f}" if emo else "")


def part_name(node, ctx: LikeCtx) -> tuple[float, str]:
    """**对象名**: query 里点到某个对象（名 / 别名）⇒ 它**车道上**的节点得 1.0。

    车道 = `about` 边指向该 entity 的节点（方向是"节点 → entity", 走 `graph.lane`）。

    ⚠️ **只加成, 不作准入**（用户 2026-10-08 裁）: 真机 haruka 实测「老师」车道上
    **10/21 条** episode ⇒ 若让它作准入, 一句寒暄就能凑出 10 条并列、排序全交给先验。
    ⇒ **"按名字找全部"是 `find` 的活**（定向寻找那一类）, 不是 `like` 的。
    """
    for eid, form in ctx.named.items():
        if node.id in ctx.lanes.get(eid, ()):
            return _NAME_HIT, f"名字[{form}]"
    return 0.0, ""


# ---------------------------------------------------------------------------
# 注册表（**唯一注册点**）与合成
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Part:
    """一个打分函数的登记项: 名 / 函数 / 权重 / **是不是内容类**。"""

    name: str
    fn: Callable[[object, LikeCtx], tuple[float, str]]
    weight: float
    #: 内容类 = **准入**靠它（零重合时不许让加成类凑分）; 见模块 docstring
    content: bool = False


#: ⭐ **打分函数表 = 唯一注册点**（新增一路只在这里加一行, `like()` 零改动）
PARTS: tuple[Part, ...] = (
    Part("lexical", part_lexical, 1.00, content=True),
    Part("temporal", part_temporal, 0.15),
    Part("prior", part_prior, 0.15),
    Part("name", part_name, 0.15),
)

#: 权重之和（分母; `like()` 与台账都用它）
TOTAL_WEIGHT = sum(p.weight for p in PARTS)


def like(store, query: str, *, kinds: tuple[str, ...] = ("episode",),
         k: int | None = None, now) -> list[Candidate]:
    """一段情境 → **最像的 k 条**（降序; 准入 = 内容轴至少一路 > 0）。

    Args:
        store: `WikiStoreV2`（**只读**）。
        query: 情境文本（MMT 每轮 = 玩家这一句; digest = 本段新经历）。
        kinds: 选面（节点 kind 白名单）—— 缺省 episode（"当下要连的是另一件**旧事**"）。
        k: None → `[recall].like_k`（默认 3）。
        now: **必填**（与 `age_days` 同一条纪律: 逼调用方显式说明"现在是什么时候",
            不许模块偷偷读壁钟）。

    Returns: 降序的 `Candidate`（≤ k 条）; 一条都不像 ⇒ **[]**（宁缺勿错:
    不拿"最近一条"或"最高 sig 那条"来凑 —— 摆一条无关的旧事 = 逼她强行联想,
    产生的还是一条**脏边**, 而边是要进图的）。
    """
    if k is None:
        k = int(_knob("like_k", LIKE_K))
    nodes = [n for n in store.all() if not kinds or getattr(n, "kind", "") in kinds]
    ctx = build_ctx(store, query=query, now=now)     # ⚠️ 全量取料（名字表要从里面挑 entity）
    out: list[Candidate] = []
    for node in nodes:
        scores: dict[str, float] = {}
        notes: list[str] = []
        admitted = False
        for p in PARTS:
            try:
                s, note = p.fn(node, ctx)
            except Exception as e:                   # noqa: BLE001 — 一路坏不阻断召回
                logger.info("recall_like part=%s 失败: %s", p.name, e)
                s, note = 0.0, ""
            scores[p.name] = float(s)
            if note:
                notes.append(note)
            if p.content and s > 0.0:
                admitted = True
        if not admitted:
            continue
        final = sum(p.weight * scores[p.name] for p in PARTS) / TOTAL_WEIGHT
        out.append(Candidate(node=node, score=final, why=" · ".join(notes)))
    out.sort(key=lambda c: (-c.score, getattr(c.node, "id", "")))
    logger.info(ledger_line(out, query=ctx.query, pool=len(nodes), k=int(k)))
    return out[:max(int(k), 0)]


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _age(node, ctx: LikeCtx) -> int | None:
    """节点年龄（**现实日**）; 缺/坏 `ts` → None（调用方必须降级, 不得折成 0）。"""
    return age_days(getattr(node, "ts", ""), now=ctx.now)


def _freshness(age: int) -> float:
    """`freshness(age, half_life, floor)` —— 两个旋钮走 `[recall]`（读不到 → 缺省, 不抛）。"""
    hl = _knob("time_half_life_days", DEFAULT_HALF_LIFE_DAYS)
    fl = _knob("time_freshness_floor", DEFAULT_FRESHNESS_FLOOR)
    return float(freshness(age, hl, fl) or 0.0)


def _body(node) -> str:
    """参与覆盖率计算的正文（与 `recall._embed_text` 同口径: 主文本 + 各 kind 的附属 + 标题）。"""
    parts = [getattr(node, "text", "") or ""]
    kind = getattr(node, "kind", "")
    if kind == "episode":
        parts.append(getattr(node, "verbatim", "") or "")
    elif kind == "profile":
        parts.extend(getattr(node, "examples", ()) or ())
    elif kind == "belief":
        parts.append(getattr(node, "growth", "") or "")
    parts.append(getattr(node, "title", "") or "")
    return " ".join(p for p in parts if p)


def _bigrams(text: str) -> set[str]:
    """中文无分词下的轻量词元: 去空白后全部相邻 2-gram。

    ⚠️ `recall.py` 里也有一份（那边整族待删）——**不许 import 它**（守门⑤）:
    那会让"新召回"重新吊在旧件上, 而旧件正是要整体删掉的东西。
    """
    chars = [c for c in (text or "") if not c.isspace()]
    return {chars[i] + chars[i + 1] for i in range(len(chars) - 1)}


def _knob(name: str, fallback: float) -> float:
    """取旋钮（配置层异常 → 回落值, 绝不上抛 —— 召回不该被配置层绊倒）。"""
    try:
        from core.brain.read.recall_config import get
        return float(get(name))
    except Exception:                                # noqa: BLE001
        return float(fallback)


__all__ = ["LIKE_K", "PARTS", "TOTAL_WEIGHT", "LikeCtx", "Part", "build_ctx", "like",
           "part_lexical", "part_name", "part_prior", "part_temporal"]
