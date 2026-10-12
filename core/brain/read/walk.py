# -*- coding: utf-8 -*-
"""walk — 记忆图上的**联想扩散**（BFS）。纯读、**零 LLM、零后端**。

> ⛔ **未接线**（2026-10-12 用户: *"near 就是 BFS 吧，可以留接口……先写一个接口，
> 不调用但需要有"*）—— 与 `channels.py` / `channel_impl.py` / `compose.py` 同一待遇:
> 接口与守门齐了, 但**没有调用方**。接线那一笔要另行审（见文末"接线还差什么"）。

## 它跟 `like._reach` 什么关系（⛔ 别合并）

| | `like._reach` | `walk.bfs` |
|---|---|---|
| 干什么 | **打分**用的一跳（`turn` 档的 `struct` 路） | **召回**用的遍历（`near` / `echo` 那种"顺着一件事想起来的一串"） |
| 口径 | 分 = 种子 × 边权, 一跳, 固定 | 分 = 父分 × 边权 × `decay`^跳, **跳数/关系/衰减都是参数** |
| 活在哪 | 热路径（每轮 `like` 都跑） | 现在谁也没跑 |

⚠️ 两边的**关系白名单必须是同一份**（`like._STRUCT_EDGES` —— 本文件直接 import 它,
⛔ 不抄第二份）。要拆开的话, 拆的人负责把那两条一句不改地搬走。

## 一句话逻辑

从**内容命中的那些旧事**（种子）出发, 沿**窄门**往外走 `hops` 步, 每远一步乘一次
`decay`; 谁先够到、谁够得强, 谁排在前面。

## 四条边界（每条都踩过或算过, 别默默改）

1. ⛔ **默认只走窄门**（`akin` = 她自己认过的相似 / `member_of` 的同类兄弟）——
   `about`（归属）太宽: 真机 haruka 「老师」车道 **10/21 条（48%）**, 走它等于每轮摆同一批。
2. ⛔ **默认一跳**: 真机那个 `akin` 簇（5 条 + 同类 6 条 = 同一个 6 条簇）**两跳就会串到别的簇**
   —— 2 跳是**实验位**, 不是默认。
3. ⛔ **同类兄弟算"语义一跳"**（我 → 我的类 → 兄弟）: 语义上那是"同一类事", 与 `like` 同口径。
4. ⛔ **`kinds` 过滤只在结果上做** —— 遍历中途会经过 `experience`（类）这类节点。
   ⚠️ **更正一句**（2026-10-12, 变异验红时发现的）: "同类兄弟"是**一跳内的原语**
   （`neighbors` 内部直接把兄弟取出来）, 所以早过滤**掐不断**它; 早过滤真正会掐断的是
   **两跳里经过非 episode 节点的路**（例: `m1 →(about) who →(about) m7`）。
   结论不变（过滤归结果）, 但**别拿"兄弟会被掐断"当理由 —— 那是错的**。

## 接线还差什么（留给接的人）

- `set` 形状今天是 `find` 一个人当执行器; `near`/`echo` 这一路要的是"按 id 集合取节点"
  或"执行器也表驱动"（`Mode.executor`）—— **两选一, 还没拍**;
- 两行形式: `near`（`rels=NARROW`）与 `echo`（`rels=(akin,)`, "这感觉以前有过"）——
  同一份料、白名单不同（用户 2026-10-12: *"echo 和 near 一起也行"*）;
- 排序: `near` 想要的是"近的在前"（本文件已经这么排）, 而 `set` 型今天的排序口径是
  `newest`（`Mode.order`）⇒ 要加**第二个取值** `"near"`。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.brain.graph import REL_AKIN, REL_MEMBER_OF, graph_of
from core.brain.read.find import _order as _newest_key
from core.brain.read.like import _STRUCT_EDGES

#: 关系白名单 —— 默认**只走窄门**（与 `like._STRUCT_EDGES` 同两条: 认过的相似 + 同类兄弟）。
#: ⚠️ 表本身住在 `like`（热路径先有的）, 这里只是"默认值取它" —— ⛔ 不抄一份。
NARROW: tuple[str, ...] = (REL_AKIN, REL_MEMBER_OF)

#: 每多一跳乘一次。**这是判断, 不是标定**（同 `when.WIDEN_DAYS` 那条纪律）:
#: "第二跳还算联想, 第三跳就只剩噪声了" —— 0.6 让两跳后的分量掉到 0.36 × 边权。
#: 有真机数据后再标定（或者干脆只留一跳）。
DECAY = 0.6


@dataclass(frozen=True)
class Hit:
    """一次扩散的结果: **谁 / 多少分 / 第几跳 / 凭什么**。

    `why` 是给她/台账看的一句话（"认过的相似"/"同类兄弟"）—— `like` 的 `why` 同款。
    """

    node_id: str
    score: float
    hop: int
    why: str


def neighbors(g, nid: str, *, rels: Iterable[str] | None = NARROW,
              ) -> list[tuple[str, float, str]]:
    """一个节点的**邻居**（BFS 的一步）: `[(对端 id, 边权, 为什么), …]`。

    · 有向图**两个方向都算**（`akin` 是双向语义; `member_of` 的方向由下面那一步专门处理）;
    · ⭐ **同类兄弟算一跳**: `我 →(member_of) 我的类 →(member_of) 兄弟` —— 与
      `like._narrow_neighbors` **同一个口径**（那是语义上的一步）;
    · ⚠️ `rels=None` ⇒ **全部边**（⛔ 只给对照台/实验: `about` 一跳就接近整条河;
      没在 `like._STRUCT_EDGES` 里登记的关系按 `(1.0, rel)` 算）;
    · `rels` 里没有 `member_of` ⇒ 兄弟那一步**不做**（这正是 `echo` 与 `near` 的唯一差别）。
    """
    want = None if rels is None else set(rels)
    out: list[tuple[str, float, str]] = []
    for e in list(g.edges_from(nid)) + list(g.edges_to(nid)):
        if want is not None and e.rel not in want:
            continue
        weight, why = _STRUCT_EDGES.get(e.rel, (1.0, e.rel))
        out.append((e.dst if e.src == nid else e.src, weight, why))
    if (want is None or REL_MEMBER_OF in want) and _STRUCT_EDGES.get(REL_MEMBER_OF):
        weight, why = _STRUCT_EDGES[REL_MEMBER_OF]
        for e in g.edges_from(nid, REL_MEMBER_OF):          # 我 → 我的类
            for sib in g.sources(e.dst, REL_MEMBER_OF):     # 类 → 兄弟们
                if sib != nid:
                    out.append((sib, weight, why))
    return out


def bfs(store, seeds: dict[str, float], *, rels: Iterable[str] | None = NARROW,
        hops: int = 1, decay: float = DECAY, kinds: Iterable[str] = ("episode",),
        skip: Iterable[str] = ()) -> list[Hit]:
    """从种子出发扩散（**语义跳** ≤ `hops`）—— 返回按"近 → 强 → 新"排好的 `Hit` 列表。

    Args:
        store: `WikiStoreV2`（**只读**）。
        seeds: `{节点 id: 分}` —— **调用方给**（内容命中的那些, 与 `like.build_ctx` 同一份料;
            ⚠️ 本模块**不自己找种子**: 找种子是"哪几路算内容命中"的事, 那是 `like.PARTS` 的活）。
        rels / hops / decay: 见模块 docstring 的四条边界（默认 = 窄门 / 一跳 / `DECAY`）。
        kinds: **结果**的 kind 白名单（⛔ 不在遍历中途过滤, 见边界 4）。
        skip: 已经在别的段摆过的 id（跨段去重 —— P19 三段共用一个 `seen`）。

    Returns:
        `[Hit, …]`; 排序 = **跳数升序 → 分降序 → 新→旧**（同分同跳才比新旧, 口径 = `find._order`）。
        ⚠️ **种子自己不在结果里**（它本来就是内容命中; 再给一份就是同一个理由算两次）。

    ⛔ **宁缺勿错**: 图/节点取不到 ⇒ 少几条, 不抛（同 `like.build_ctx` 的纪律）。
    """
    if not seeds or hops < 1:
        return []
    skip_set = set(skip)
    try:
        g = graph_of(store)
    except Exception:                                        # noqa: BLE001 — 图坏了不阻断
        return []
    want_kinds = set(kinds)
    #: `{id: (分, 跳, why)}` —— **只看第一次够到的那一跳**（最小跳 = 最近的那一环）:
    #: 同一个节点被更远的路以更高分够到时**不覆盖**（否则"第几跳"会与排序口径打架）。
    best: dict[str, tuple[float, int, str]] = {}
    frontier: dict[str, float] = dict(seeds)
    for hop in range(1, int(hops) + 1):
        reached: dict[str, tuple[float, str]] = {}
        for nid, parent in frontier.items():
            for other, weight, why in neighbors(g, nid, rels=rels):
                if other in seeds or other in skip_set or other in best:
                    continue                                 # 种子不吃分 / 已够到的不重算
                score = parent * weight * (decay ** (hop - 1))
                if score > reached.get(other, (0.0, ""))[0]:
                    reached[other] = (score, why)            # 同一跳多父 ⇒ 取最强那条
        if not reached:
            break
        for nid, (score, why) in reached.items():
            best[nid] = (score, hop, why)
        frontier = {nid: s for nid, (s, _why) in reached.items()}
    rows: list[tuple[tuple[int, float, object], Hit]] = []
    for nid, (score, hop, why) in best.items():
        node = store.get(nid)
        if node is None or getattr(node, "kind", "") not in want_kinds:
            continue
        rows.append(((hop, -score, _newest_key(node)),
                     Hit(node_id=nid, score=score, hop=hop, why=why)))
    rows.sort(key=lambda r: r[0])
    return [h for _key, h in rows]
