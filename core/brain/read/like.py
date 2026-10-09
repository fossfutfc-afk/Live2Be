# -*- coding: utf-8 -*-
"""like — **相似召回**: 给一段情境（玩家这一句 / 本段经历）⇒ **最像的 k 条**。

「一个包、两个类」: `find` = 定向寻找（给锚, 要**全部**符合的; 分只是展示顺序）,
`like` = 本模块（给情境, 要最像的 k 条; **顺序就是答案**, 分是有意义的）。
两类共用形状 = `pack.Candidate`。

## 打分函数（`part_*`）—— 每个**独立**、每个**可单测**、每个返回 `(分, 一句话)`

| 函数 | 类 | 分 | 一句话（`why` 的一格） |
|---|---|---|---|
| `part_lexical` | **准入**（内容轴） | tags / 标题 / 正文覆盖 **取最大** | `tags[苔藓]` · `标题点名` · `覆盖 0.62` |
| `part_struct` | **准入**（⚠️ 窄门） | 种子的内容分 × 边权（≤ 种子） | `认过的相似 0.60` · `同类兄弟 0.48` |
| `part_temporal` | 加成 | `freshness(age)` ∈ **[floor, 1]** | `今天` · `12 天前` |
| `part_prior` | 加成 | `node.significance`（**就是它一个**，2026-10-08 从 `det` 拆干净） | `重要 0.85` |
| `part_name` | 加成 | 0 / 1（query 点到某个对象名） | `名字[杂草屋]` |

⚠️ **四个"角度"两两不同源**（`fuse.py` 那条纪律）: 像不像（字面）· 是不是同一件事的邻居（结构）·
多近（`ts` → 曲线）· 多重（L1 打的 `sig`）。⛔ **时间只算一次**、**重要性只算一次** ——
`det = SIG·TIME + emo_span·emo_int` 那格把两者各算了两遍，2026-10-08 已拆（见 `part_prior`）。

一句话由**函数自己**写（它算的时候就知道自己走的是哪一路）; `like()` 只按固定顺序拼。
⛔ **绝不事后重算** —— 重算就是第二个真源（`recall._keyword_candidates` 踩过）。

## 三张表 + 一个契约（照 `promptkit` 的形态: `BLOCKS` 注册表 + `DOMAIN_BOXES` 每域清单）

| 在哪 | 管什么 | 加东西时动哪 |
|---|---|---|
| `PARTS: dict[str, Part]` | **一条路是什么**: 函数 · `axis`（轴）· `scale`（尺度）· `needs`（要哪些输入） | 加一行 |
| `SPECS: dict[str, Spec]` | **一个场景怎么用它**: 问哪个面（`kinds`）· 调哪几路 · 权重 | 加一块 |
| `RecallCtx` | **输入契约**: 所有路共用同一份"现在几点 / 什么心情"（老 `RecallContext` 的字段与纪律） | 加一个输入字段 |

```
final = Σ wᵢ·sᵢ / Σ wᵢ        （只对**这次真调的那几路**求和; 分母 = 它们权重之和）
准入   = `axis=EVIDENCE` 的那几路里至少一路 > 0
```

* 分母是正常数 ⇒ **排序与"不带分母的加权和"完全一致**; 带分母只是把分压回 `[0,1]`、
  台账好看（用户 2026-10-08: *"最终调用各函数采用加权平均吧, 这样不费脑子"*）。
* ⚠️ **准入是唯一不是加权平均的规则**（**不是阈值** —— 边界就是"零"这个自然值）。
  零重合时若只看加权平均, `时间 + 先验 + 名字` 也能凑出一份分来: 真机 haruka 实测
  「老师，你今天有空吗」凑出 **10 条并列**、排序全交给先验 ⇒ 召回退化成"关于老师最重要的事",
  **每轮同样两条**（正是 `recall.recall_episodes` docstring 警告的"永远长不出新边"）。
  ⇒ **证据轴（内容 / 窄门结构）可以自己把人带进池; 先验轴（时间 / 重要 / 名字）只加成。**
* ⚠️ **`needs` 缺输入 ⇒ 那一路自动不参与** + 台账记 `skip=名字(无emo_now)` ——
  不靠人记得配 0, 也不会静默算错。
* ⚠️ **窄门**是 `struct` 那一路的定语, 不是形容词: 它只走两条边
  （`akin` = 她亲口认过的相似; `member_of` 的**同类兄弟**）—— ⛔ **`about`（归属）不在内**
  （太宽: 真机「老师」车道 10/21 条; 而且与 `name` 那一路重叠）。见 `_STRUCT_EDGES`。
* ⚠️ 权重是**代码常量**（在 `SPECS` 里; 覆盖只能改**本档已有**那几路的权重,
  **不能靠覆盖加一路**）—— 配置面只留"取几条"与"半衰期/下界"那类; 阈值旋钮
  2026-09-15 已全删, `test_no_threshold_knobs_left` 钉着。要按模型标定了再上配置面 ——
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
from dataclasses import dataclass, field, replace
from typing import Callable

from core.brain.address import normalize_title
from core.brain.graph import REL_AKIN, REL_MEMBER_OF, graph_of
from core.brain.read.pack import Candidate, ledger_line
from core.worldtime.age import (DEFAULT_FRESHNESS_FLOOR, DEFAULT_HALF_LIFE_DAYS,
                               age_days, freshness, render_relative)

logger = logging.getLogger(__name__)

#: `like` 取几条的**回落值**（真源 = `settings.toml [recall].like_k`）
LIKE_K = 3

#: 轴（`Part.axis`）—— 老 `channels.py` 的 `kind` 那一格: 决定合成层怎么用它
EVIDENCE = "evidence"     #: 证据轴: **可准入**（内容 / 窄门结构）
PRIOR = "prior"           #: 先验轴: 只加成（时间 / 重要 / 名字）
GATE = "gate"             #: 闸门: **不进加权平均**（将来 `place` 那类乘性闸门; 第一笔没有这一路）

#: 尺度（`Part.scale`）—— 老 `channels.py` 的 `scale` 那一格: 决定要不要池内归一
UNIT = "unit"             #: 自报 [0,1] 的绝对分, 原样用
COSINE = "cosine"         #: cos 那类**池内 min-max** 归一后才用（`part_lexical` 之外的路会是它）

# ⚠️ 下面这些是**代码常量, 不是旋钮**（理由见模块 docstring 的权重那条）
_TAG_BASE, _TAG_STEP = 0.60, 0.10      # tags 命中: 基分 + 每多命中一个 +0.10
_TITLE_HIT = 0.85                      # 标题（剥壳后）整体出现在 query
_COVER_MIN = 0.35                      # 正文覆盖率下限（`recall._keyword_candidates` 的 0.35 同款）
_NAME_HIT = 1.00                       # 名字/别名命中（只是加成的一份, 不作准入）

#: ⭐ **结构一跳的两条窄门**（`rel → (边权, 一句话)`）—— 用户 2026-10-08 裁"容许窄门准入"。
#: ⛔ **`about` 刻意不在内**: 它是"归属"不是"相似", 而且太宽 —— 真机 haruka 实测
#: 「老师」车道 **10/21 条**（48%）, 让它扩散等于每轮摆同一批; 况且 query 点到名时
#: 已经由 `part_name` 承担（重叠就该只算一次理由）。
_STRUCT_EDGES: dict[str, tuple[float, str]] = {
    REL_AKIN: (1.00, "认过的相似"),          # 她自己写过 `{"noticed": …}` 认下来的
    REL_MEMBER_OF: (0.80, "同类兄弟"),        # 同一个"经验"（类）下的其他经历
}


# ---------------------------------------------------------------------------
# 料（一次 `like` 的共享输入）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecallCtx:
    """一次召回的**输入契约** —— 所有路共用同一份"现在几点 / 什么心情"。

    ⚠️ **为什么集中**（老 `channels.RecallContext` 的原话, 2026-09-13）: 路各自去
    store / 事件流里捞上下文 ⇒ 同一次召回里"现在是几点、什么心情"会被**算出多份**,
    且台账里**无法复现**。所以输入只在这里声明一次, 路只读它。

    ## 字段分两半: **输入**（调用方填）· **派生**（`build_ctx` 现算, 调用方别填）

    输入那几个是**对称的**: 情绪 / 地点 / 好感各一对"键 + 原文"，因为它们服务的路不同
    （键做集合比较, 原文做语义比较）。🚫 **这些都不进 LLM 上下文**（用户 2026-09-15 裁决:
    召回侧信号, 参与筛选不参与写作）。
    """

    # ---- 输入（调用方填）----------------------------------------------------
    #: 当前**时刻**（`datetime` 或 `ts` 串）—— `TIME` 格用它算 `age`。
    #: **必填且无默认值**（故排第一位）: 逼调用方在调用处显式说明"现在是什么时候"，
    #: 不许模块偷偷读壁钟（同 `age_days` 的纪律）。
    now: object
    #: 情境文本（MMT 每轮 = 玩家这一句; digest = 本段新经历）
    query: str = ""
    #: 当前**情绪键序列**（B 链路的 query 侧）—— 如 `("tease", "smile")`。`()` = 未知（那一路降级）
    emo_now: tuple[str, ...] = ()
    #: 当前地点**键**（C 链路的素材轴）—— `""` = 未知
    place_now: str = ""
    #: 当前地点的 **writer 原文**（switch 短语原话, C 链路的叙事轴）—— 键不能当地名用
    #: （一键多义 / 一地多键）, 所以"是不是同一个地方"只能靠原文的语义相似。`""` = 未知
    place_raw_now: str = ""
    #: 当前**好感标量** ∈ [−1,1]（`Affection.to_scalar()`）—— 关系层信号
    aff_now: float | None = None
    #: 检索后端（`texts → 等长向量列表`）; None ⇒ 需要它的那几路自动降级
    embed_fn: object | None = None
    #: 本角色 id（词表 / 资产定位用）
    char_id: str = ""

    # ---- 派生（`build_ctx` 负责, 调用方别填）--------------------------------
    #: entity_id → 它**在 query 里被叫到的那个写法**（`why` 里要印这个名字）
    named: dict[str, str] = field(default_factory=dict)
    #: entity_id → 它车道上（`about` 边指向它）的节点 id 集合
    lanes: dict[str, frozenset[str]] = field(default_factory=dict)
    #: ⭐ **内容种子**: 节点 id → 内容分（只留 > 0 的）—— `part_struct` 的起点
    seeds: dict[str, float] = field(default_factory=dict)
    #: ⭐ **结构一跳能到达的节点**: 节点 id → `(分, 一句话)`; 分 **≤ 它的种子**
    reach: dict[str, tuple[float, str]] = field(default_factory=dict)


def build_ctx(store, ctx: RecallCtx, *, seed_parts: "tuple[str, ...] | list[str]" = (),
              ) -> RecallCtx:
    """把**派生料**算出来: 名字表（entity 的名字 + 别名）→ query 里命中的那几个 → 它们的车道
    → 内容种子 → 结构一跳。

    ⚠️ 节点表**在这里自己取全量**（不接调用方传进来的表）—— 名字表要从里面挑 entity;
    若让调用方传"选面过滤后"的那一份, 名字那一路会**恒空**而且**静默**
    （只是少一份加成, 不报错）。踩过一次, 所以这条做成结构性不可能。
    车道 / 结构取不到（图坏了）**不是错**: 只是少一份加成（宁缺勿错, 不阻断召回）。

    `seed_parts`: **这次真调的**、且 `Part.seeds` 为真的那几路（由 `like()` 按档位算好传进来）。
    一条都没有 ⇒ 没有种子 ⇒ 结构那一路自然为 0（消融 `lexical` 时正是这样, 见 `Part.seeds`）。
    """
    q = (ctx.query or "").strip()
    names: dict[str, tuple[str, str]] = {}          # 名字(casefold) → (entity_id, 原写法)
    universe = list(store.all())
    for n in universe:
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
    base = replace(ctx, query=q, named=named, lanes=lanes)
    # 结构一跳要"谁命中了内容"当种子 ⇒ 这里按**这次真调的内容路**跑一遍
    # （**同一个函数**, 不是第二份实现; 一条内容路都没参与 ⇒ 没有种子）
    seeds: dict[str, float] = {}
    for pname in seed_parts:
        fn = PARTS[pname].fn
        for n in universe:
            s = fn(n, base)[0]
            if s > seeds.get(n.id, 0.0):
                seeds[n.id] = s
    return replace(base, seeds=seeds, reach=_reach(store, seeds))


def _reach(store, seeds: dict[str, float]) -> dict[str, tuple[float, str]]:
    """**结构一跳**: 从内容种子出发, 沿窄门（`_STRUCT_EDGES`）到达的节点。

    分 = `种子的内容分 × 边权` ⇒ ⚠️ **永远不超过它的种子**（守门钉着这条不变量）。
    同一节点被多个种子够到时取最强的那个。

    ⚠️ **只一跳**: 走 `akin` 是一步; "同类兄弟"是"我 → 我的类 → 兄弟"两段边, 但**语义上
    仍是一跳**（同一个类, 一件事）。⛔ 不许传递闭包 —— 真机那个 6 条簇会滚成整张图。

    ⚠️ **种子自己不吃结构分**（它本来就是内容命中, 再给一份就是同一个理由算两次）。
    这条顺带把"类自己也是命中"的情形收干净了（它是种子 ⇒ 不进 `reach`）。

    ⚠️ **不再叠一层 kind 过滤**: 窄门本身就排除了跨面扩散（`about`（对象）/ `supports`
    （认知）都不在门里）; 唯一会跨的是"经历 → 它的类"那一步 —— 那正是同类兄弟要的
    （先前按"与种子同 kind"过滤, 会把兄弟全挡掉; 也说明**过滤该由窄门承担**）。
    """
    if not seeds:
        return {}
    g = graph_of(store)
    out: dict[str, tuple[float, str]] = {}
    for sid, s in seeds.items():
        for other, weight, why in _narrow_neighbors(g, sid):
            if other in seeds:
                continue                                 # 自己就是内容命中 ⇒ 不吃结构分
            score = s * weight
            if score > out.get(other, (0.0, ""))[0]:
                out[other] = (score, why)
    return out


def _narrow_neighbors(g, nid: str) -> list[tuple[str, float, str]]:
    """窄门邻居（`(对端, 边权, 一句话)`）—— 含"同类兄弟"那一步。"""
    out: list[tuple[str, float, str]] = []
    for e in list(g.edges_from(nid)) + list(g.edges_to(nid)):
        hit = _STRUCT_EDGES.get(e.rel)
        if hit:
            out.append((e.dst if e.src == nid else e.src, hit[0], hit[1]))
    for e in g.edges_from(nid, REL_MEMBER_OF):           # 我 → 我的类
        w, why = _STRUCT_EDGES[REL_MEMBER_OF]
        for sib in g.sources(e.dst, REL_MEMBER_OF):      # 类 → 兄弟们
            if sib != nid:
                out.append((sib, w, why))
    return out


# ---------------------------------------------------------------------------
# 打分函数（`part_*`）—— 每个独立、每个可单测
# ---------------------------------------------------------------------------

def part_lexical(node, ctx: RecallCtx) -> tuple[float, str]:
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


def part_struct(node, ctx: RecallCtx) -> tuple[float, str]:
    """**结构一跳**（⭐ **窄门准入**）: 从内容种子沿窄门到达的节点, 分 = `种子 × 边权`。

    窄门只有两条（`_STRUCT_EDGES`）: `akin`（**她自己认过的相似** —— 她写过
    `{"noticed": …}` 指认的那条）与 `member_of` 的**同类兄弟**。⛔ `about` 不在内。

    ⚠️ **为什么不作纯加成**: 结构一跳的全部意义就是"**带一条新的想起来**"; 若它不许准入,
    扩展出来的邻居内容分是 0 ⇒ 永远进不了池 ⇒ 这个函数就只剩"给已在池里的改排序"。
    用户 2026-10-08 裁: **容许窄门准入**（窄门的扩散有界 —— 真机 haruka 实测
    `akin` 5 条 + `member_of` 6 条指向**同一个 6 条簇**, 21 条里的 29%）。

    ⚠️ **与 `part_name` 去重**: 已经靠"名字"进来的节点不再吃结构加成（一条理由只算一次）。
    """
    if not ctx.reach:
        return 0.0, ""
    for eid in ctx.named:
        if node.id in ctx.lanes.get(eid, ()):
            return 0.0, ""
    score, why = ctx.reach.get(getattr(node, "id", ""), (0.0, ""))
    return (score, f"{why} {score:.2f}") if score > 0.0 else (0.0, "")


def part_temporal(node, ctx: RecallCtx) -> tuple[float, str]:
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


def part_prior(node, ctx: RecallCtx) -> tuple[float, str]:
    """**先验轴**: **这件事本身多重** —— 就一个参量: `node.significance`（0~1, 不用夹）。

    ## ⚠️ 2026-10-08: 从 `det` 退化成 `sig`（用户裁 + 实测）

    原形是 `compose` 的 A 链路那格 `det = SIG·TIME + emo_span·emo_int`; 这里**两处都拆掉**,
    理由是两条实测（真档 haruka 21 条）:

    1. **TIME 与 `part_temporal` 同源** ⇒ 时间在最终分里进两次（一次独立、一次乘在 `sig` 上）。
       那一句实测: 从"今天"到"11 天前"的 recency 优势共 0.091 分, 其中 **0.042（46%）
       来自这一格** —— 且它与权重那一路不同源 ⇒ "高 sig 的新事"被推两次。
    2. **`emo_span·emo_int` 与 `sig` 高度相关** ⇒ 留着等于**同一个 L1 判断数两次**:
       `pearson(sig, span·int) = **0.879**`; `span` 与 `int` 自身平均只差 0.063;
       按 `sig` 排 vs 按 `det` 排**前 8 名 8/8 重合**（只有内部次序不同）。
       而 `span·int` 的副作用是把 5/21 条顶到 >1 ⇒ 夹完**并列**（丢序）。

    拆完: 强度轴与时间轴**正交**（`fuse.py` 那条"两轴必须不同源"）, 老记忆的"不衰减"由
    `sig` 自己承担（它恒定不随时衰减）, recency 只由 `part_temporal` 一份表达。

    ## ⚠️ 连带后果（要记账）

    这一改之后 **`emo_span` / `emo_int` 没有活着的读者了** —— 全仓唯一读者是**待删的**
    `channel_impl.IntensityPrior`（`compose` 那一族, 零生产调用）, 而 digest 的 L1 每段照写。
    ⇒ 两条路: ①承认它是给将来的情绪通道留的料（⚠️ 但 B 链路 `EmotionRag` 用的是
    `emo_shape` 情绪**键序列**, 不是这两个数）; ②从契约里退掉（digest 那边的改动, 独立一笔）。
    **先记账, 不在这一笔里动。**
    """
    sig = float(getattr(node, "significance", 0.0) or 0.0)
    return sig, f"重要 {sig:.2f}"


def part_name(node, ctx: RecallCtx) -> tuple[float, str]:
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
    """**一条路是什么**（注册表的一行）: 函数 · 轴 · 尺度 · 需要哪些输入。

    ⚠️ 权重**不在这儿** —— 它是"这个场景怎么用这一路", 归 `Spec`（见 `_plan`）。
    """

    fn: Callable[[object, "RecallCtx"], tuple[float, str]]
    #: 轴: `EVIDENCE`（证据轴, **可准入**）· `PRIOR`（先验轴, 只加成）· `GATE`（闸门, **不进加权平均**）
    axis: str = EVIDENCE
    #: 尺度: `UNIT`（自报 [0,1] 绝对分, 原样用）· `COSINE`（池内 min-max 归一后再用）
    scale: str = UNIT
    #: 需要 `ctx` 里哪些字段 —— **缺 ⇒ 这一路自动不参与** + 台账记一笔 `skip=`（不靠人记得配 0）
    needs: tuple[str, ...] = ()
    #: 这一路**能当结构一跳的种子**吗（"内容命中"才配当种子）—— 目前只有 `lexical`。
    #: ⚠️ 它决定消融的正确性: 把 `lexical` 关掉时**种子也没了**（否则结构路还偷偷吃着字面证据,
    #: 那个消融就是假的）。
    seeds: bool = False


#: ⭐ **注册表 = 唯一注册点**（照 `promptkit/blocks.py::BLOCKS` 的形态）: 加一路只在这里加一行
PARTS: dict[str, Part] = {
    "lexical": Part(part_lexical, axis=EVIDENCE, scale=UNIT, needs=("query",), seeds=True),
    "struct": Part(part_struct, axis=EVIDENCE, scale=UNIT, needs=("query",)),
    "temporal": Part(part_temporal, axis=PRIOR, scale=UNIT, needs=("now",)),
    "prior": Part(part_prior, axis=PRIOR, scale=UNIT),
    "name": Part(part_name, axis=PRIOR, scale=UNIT, needs=("query",)),
}


@dataclass(frozen=True)
class Spec:
    """**一个场景怎么用它**（档位）: 问哪个面 + 调哪几路 + 权重。

    `parts` 的顺序 = `why` 的拼接顺序（只影响可读性, 不影响分数）。
    """

    #: 选面（节点 kind 白名单）—— "当下要连的是另一件**旧事**" ⇒ 缺省 episode
    kinds: tuple[str, ...] = ("episode",)
    #: `(路名, 权重)` —— **权重 0 = 这一路完全不参与（连准入也不算）**
    parts: tuple[tuple[str, float], ...] = ()


#: ⭐ **档位表**（照 `promptkit/box.py::DOMAIN_BOXES` 的形态）: 一个场景一块, 自包含、好审
SPECS: dict[str, Spec] = {
    # P19「你想起的事」: query = 玩家这一句, 只要 episode。
    # ⚠️ 没有 `name` 以外的差别, 是因为 turn 拿不到 query 侧的情绪/地点（见模块 docstring）。
    "turn": Spec(kinds=("episode",), parts=(
        ("lexical", 1.00), ("struct", 0.35), ("temporal", 0.15),
        ("prior", 0.15), ("name", 0.15),
    )),
    # digest（R2/L2 的候选）: query = **本段新经历**, 认知面也进池。
    # ⚠️ 故意**没有 `name`** —— 经历正文里出现"老师/遥香"是常态, "点名一个对象"在那里没有信息量。
    # ⚠️ `emotion` / `place` 两路要等真正的 part 落地（那两路**输入只在 digest 有**:
    #    本段节点自带 `emo_shape` / `place`, MMT 每轮没有）。
    "digest": Spec(kinds=("episode", "belief", "experience"), parts=(
        ("lexical", 1.00), ("struct", 0.35), ("temporal", 0.15), ("prior", 0.15),
    )),
}


def plan(spec: str = "turn", weights: dict[str, float] | None = None,
         ) -> list[tuple[str, Part, float]]:
    """档位 → **这次真调的清单** `[(路名, Part, 权重)]`（按档位声明顺序）。

    `weights` 是**一次性覆盖**（消融实验 / 对照台用）:
    * 只能改**本档已有**那几路的权重 —— 想给本档加一路请改 `SPECS`（档位决定调哪几路）;
    * `0` = 这一路完全不参与;
    * ⛔ 未知路名 → `KeyError`（防拼错静默失效, 同 `recall_config.get` 的纪律）。
    """
    sp = SPECS.get(spec)
    if sp is None:
        raise KeyError(f"未知召回档位: {spec!r}（可用: {sorted(SPECS)}）")
    names = [n for n, _ in sp.parts]
    unknown = sorted(set(weights or ()) - set(names))
    if unknown:
        raise KeyError(f"覆盖了本档没有的路: {unknown}（本档: {names}）")
    out: list[tuple[str, Part, float]] = []
    for name, w in sp.parts:
        part = PARTS.get(name)
        if part is None:                                 # 表写错了 ⇒ 当场炸, 不静默
            raise KeyError(f"档位 {spec!r} 里有未注册的路: {name!r}"
                           f"（注册表: {sorted(PARTS)}）")
        if weights and name in weights:
            w = weights[name]
        out.append((name, part, float(w)))
    return out


def like(store, ctx: "RecallCtx", *, spec: str = "turn",
         k: int | None = None, weights: dict[str, float] | None = None,
         ) -> list[Candidate]:
    """一段情境 → **最像的 k 条**（降序; 准入 = 证据轴至少一路 > 0）。

    Args:
        store: `WikiStoreV2`（**只读**）。
        ctx: **输入契约**（`RecallCtx`）—— 调用方只填输入字段, 派生料由 `build_ctx` 现算。
        spec: 档位名（`SPECS` 的键）—— 决定问哪个面、调哪几路、各自权重。
        k: None → `[recall].like_k`（默认 3）。
        weights: 一次性覆盖本档某几路的权重（`0` = 不参与）—— 消融实验用, 台账会印出来。

    Returns: 降序的 `Candidate`（≤ k 条）; 一条都不像 ⇒ **[]**（宁缺勿错:
    不拿"最近一条"或"最高 sig 那条"来凑 —— 摆一条无关的旧事 = 逼她强行联想,
    产生的还是一条**脏边**, 而边是要进图的）。
    """
    if k is None:
        k = int(_knob("like_k", LIKE_K))
    sp = SPECS[spec]
    pl = plan(spec, weights)
    active: list[tuple[str, Part, float]] = []
    skipped: list[str] = []
    for name, part, w in pl:
        if w <= 0.0:
            skipped.append(f"{name}(权重0)")
            continue
        miss = [f for f in part.needs if not _has(ctx, f)]
        if miss:                                         # 缺输入 ⇒ 自动不参与（不靠人记得配 0）
            skipped.append(f"{name}(无{'/'.join(miss)})")
            continue
        active.append((name, part, w))
    ctx = build_ctx(store, ctx, seed_parts=[n for n, p, _w in active if p.seeds])
    nodes = [n for n in store.all()
             if not sp.kinds or getattr(n, "kind", "") in sp.kinds]
    total_w = sum(w for _, _, w in active)
    out: list[Candidate] = []
    for node in nodes:
        scores: dict[str, float] = {}
        notes: list[str] = []
        admitted = False
        for name, part, _w in active:
            try:
                s, note = part.fn(node, ctx)
            except Exception as e:                       # noqa: BLE001 — 一路坏不阻断召回
                logger.info("recall_like part=%s 失败: %s", name, e)
                s, note = 0.0, ""
            scores[name] = float(s)
            if note:
                notes.append(note)
            if part.axis == EVIDENCE and s > 0.0:
                admitted = True
        if not admitted or total_w <= 0.0:
            continue
        final = sum(w * scores[name] for name, _p, w in active) / total_w
        out.append(Candidate(node=node, score=final, why=" · ".join(notes)))
    out.sort(key=lambda c: (-c.score, getattr(c.node, "id", "")))
    logger.info(ledger_line(out, query=ctx.query, pool=len(nodes), k=int(k),
                            spec=spec, skip=skipped, weights=weights))
    return out[:max(int(k), 0)]


def _has(ctx: "RecallCtx", name: str) -> bool:
    """`ctx` 的某个输入字段有没有值（`None` / 空串 / 空序列都算没有）。"""
    val = getattr(ctx, name, None)
    if val is None:
        return False
    if isinstance(val, (str, tuple, list, dict, set, frozenset)):
        return len(val) > 0
    return True


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _age(node, ctx: RecallCtx) -> int | None:
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


__all__ = ["COSINE", "EVIDENCE", "GATE", "LIKE_K", "PARTS", "PRIOR", "SPECS", "UNIT",
           "Part", "RecallCtx", "Spec", "build_ctx", "like", "part_lexical",
           "part_name", "part_prior", "part_struct", "part_temporal", "plan"]
