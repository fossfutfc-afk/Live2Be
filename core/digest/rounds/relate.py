"""relate.py — ③ L1「判关系」: 本段经历 + 认知列表 → **关系表**（只落边）。

⭐ 这一趟**一个字正文都不写**（`docs/DESIGN_DIGEST_TWO_PASSES.md` §9）—— 它只回答
"谁和谁是什么关系"; 造看法 / 写正文是**另一趟**（L2）。两趟按**注意力**切
（`DESIGN_MEMORY_MODES.md` §0）: 一场调用里既判关系又写正文, 数据量一大,
"连接"的注意力就被写正文冲淡。

料（表里那五行）: 本次新经历（含引擎候选标注）· **现有经历（候选）** ·
本段时间线 · 现有认知 · 角色人设（锚点）。
⭐ **P2（2026-10-07）补齐了那两段候选** —— 在那之前 `akin` 连不到更早的经历
（料里根本没有它们）。

写: 边 `supports` / `akin` / `contradicts` / `evolved_from`（`apply_relations` —— 一个节点都不建）。
⛔ **`about` 不归它写**（E3, 2026-10-08）: 归属由**引擎**从节点 `tags` 里的 `#entity:` 派生。

## 三个 id 空间（⭐ 这一笔最容易写错的地方）

| 哪一端 | 空间 | 谁发的 |
|---|---|---|
| 经历 `m…`（本段新的 + 候选里的旧的）| **真实 id** | 料里印的就是真身（`_round_b_material` / `_episode_candidates`）|
| 认知 `u0001…` | **本地号** | `render_cognition_list`（它的判据: "parse 层只认本地 id, 防 LLM 猜真实 id"）|

⇒ 执行时用 `id_map` 把认知那一路翻回来; 而 `topics_of` / `kind_of`（轴与类型校验要它们）
**三个空间都要有键**（她写的那一端用哪个空间的 id, 就用哪一边去查）。

## 一处"关着"的东西（**有意**, ⛔ 别当成漏了）

**`r2_created` 不赋值** —— 它记的是"本轮新建的节点", 而这一趟**不建节点**
（R3 归属轮还在暂停; 将来由 L2 自己填）。

## 观测账（P6, 2026-10-08）—— 一行日志, 七个字段

```
digest_relate rows=2 rels=1 alone=1 lone=m0002 cands=0 pool=1 dropped=0
```

| 字段 | 是什么 |
|---|---|
| `rows` | parse **收下**的关系行数 |
| `rels` | ⭐ **边表真的长了几条**（`store.edges()` 的增量）—— ⛔ **不是 `rows`**: `add_edge` 幂等 |
| `alone` | 本段经历里**一行关系都没连上**的条数（分母 = `ctx.episode_ids`）|
| `lone` | 那些 id（最多 5 个, `·` 并列; 没有 ⇒ `-`）|
| `cands` | 「现有经历（候选）」摆出来几条 |
| `pool` | ⭐ **前提读数**: 库里 `kind=episode` 且**标了 `轴`** 的条数 |
| `dropped` | 这一轮被契约层丢掉的行数（取**调用前后** `contract_drops` 的差, 不猜中文）|

**为什么 `alone` 值得记**: 孤立经历**不进 L2**（`DESIGN_DIGEST_TWO_PASSES.md` §3 的
天然归纳门槛）⇒ 这一格 = 下一趟收料的实际范围。
**为什么 `pool` 必须一起记**: `cands=0` 有两种相反的解释 —— "这一段真没有同类旧经历"
（结论）vs "老经历压根没标轴"（数据缺陷, `topics` 是 P0 才加的字段）。缺了 `pool`,
那格数字读不出意思。⚠️ 用户 2026-10-08 裁: **只观测**, 不写补 `topics` 的维护脚本
（*"以后也要测试新的 digest, 之后就删掉数据重来了"*）。
"""
from __future__ import annotations

import logging

from core.brain.read.render import render_cognition_list
from core.brain.revise import apply_relations
from core.digest.material import _episode_candidates, _round_b_material
from core.digest.rounds.base import Ctx, RoundOut

logger = logging.getLogger(__name__)

#: 认知渲染上限（本地 id 数量; 排序: 珍贵档先）
DIGEST_COGNITION_CAP = 12


def run(ctx: Ctx) -> RoundOut:
    """③ 接 —— 把本段经历接到已有认知 / 已有经历 / 对象上。"""
    spec = ctx.enter("relate")
    cog_text, local_of = render_cognition_list(
        ctx.store, cap=DIGEST_COGNITION_CAP, exclude=set(ctx.player_ids))
    ep_text = _round_b_material(ctx.store, ctx.episode_ids, local_of,
                                embed_fn=ctx.embed_fn,
                                char_id=getattr(ctx.store, "char_id", ""))
    cand_text, cand_ids = _episode_candidates(ctx.store, ctx.episode_ids,
                                              now=ctx.now_ts)
    system = ctx.system_for(spec)
    user = ctx.sections_for(spec, [
        ("本次新经历（含引擎候选标注）", ep_text),
        ("现有经历（候选）", cand_text),
        ("本段时间线", ctx.timeline),
        ("现有认知", cog_text),
        ("角色人设（锚点）", ctx.character_prompt),
    ])
    drops_before = len(ctx.result.contract_drops)     # 观测账: 只算**这一轮**丢的
    rows, _resp = ctx.call(
        spec, system, user,
        parse_fn=ctx.parse_for(spec,
                               episode_ids=set(ctx.episode_ids),
                               # ⭐ **右边能引用的 = 渲染列表里的全部**: 认知用本地号
                               # （`u0001…`）、经历用真身（本段新的 + 候选里的旧经历）、
                               # 对象用真身（`x…`）。⛔ 少一类就会把合法行判成**编造 id**
                               # ⇒ 整包拒（P1b-2 的端到端用例逼出来的那一处）。
                               target_ids=(set(local_of.values())
                                           | set(ctx.episode_ids) | set(cand_ids)),
                               topics_of=_topics_of(ctx, local_of, cand_ids),
                               kind_of=_kind_of(ctx, local_of, cand_ids)))
    if rows is None:
        return RoundOut.failed()
    id_map = {v: k for k, v in local_of.items()}      # 本地号 → 真实 id
    edges_before = len(ctx.store.edges())             # 观测账: `rels` = 边表增量
    apply_relations(ctx.store, rows, ts=ctx.now_ts, id_map=id_map)
    _log_ledger(ctx, rows, cand_ids,
                edges_before=edges_before, drops_before=drops_before)
    return RoundOut.done()


def _log_ledger(ctx: Ctx, rows: list[dict], cand_ids: list[str], *,
                edges_before: int, drops_before: int) -> None:
    """这一段的观测账（字段表见模块 docstring）—— **只记, 不判**。"""
    lone = _lone_episodes(ctx, rows)
    logger.info("digest_relate rows=%d rels=%d alone=%d lone=%s cands=%d pool=%d dropped=%d",
                len(rows), len(ctx.store.edges()) - edges_before, len(lone),
                "·".join(lone[:5]) or "-", len(cand_ids), _episodes_with_axis(ctx),
                len(ctx.result.contract_drops) - drops_before)


def _lone_episodes(ctx: Ctx, rows: list[dict]) -> list[str]:
    """本段经历里**一行关系都没连上**的那几条（孤立经历 ⇒ 不进 L2）。

    ⚠️ **这里不需要 `id_map`** —— 我第一版翻了一遍（"两端都要过"）, 变异验红证明
    **那一行永远改不了结果**: 经历那一端永远是**真实 id**（料里印的就是真身,
    `_round_b_material` / `_episode_candidates`）; 本地号 `u…` 只发给**认知**那一端,
    而 `render_cognition_list` 只渲染 belief/experience（经历不在其中）。
    ⛔ 别为了"对称好看"再加回来。

    ⚠️ 反过来也要记住: **有行 ≠ 这条经历被连上** —— 两端都是认知的行
    （`{"belief": "u0001", "contradicts": "u0002"}`）照样算一行, 而本段的经历一条都没沾
    （用例 `test_row_between_two_cognitions_does_not_connect_the_episode`）。
    """
    touched: set[str] = set()
    for row in rows:
        touched.add(str(row["src"]))
        touched.add(str(row["dst"]))
    return [str(e) for e in ctx.episode_ids if str(e) not in touched]


def _episodes_with_axis(ctx: Ctx) -> int:
    """库里 `kind=episode` 且**标了 `轴`** 的条数 —— `cands=0` 的解释器。"""
    return sum(1 for n in ctx.store.all() if n.kind == "episode" and n.topics)


def _node_topics(ctx: Ctx, nid: str) -> list[str]:
    node = ctx.store.get(str(nid))
    return list(node.topics) if node is not None else []


def _topics_of(ctx: Ctx, local_of: dict[str, str],
               cand_ids: list[str]) -> dict[str, list[str]]:
    """`{她能写的 id: topics}` —— ⚠️ **三个空间都要有键**（见模块 docstring）。

    经历用真实 id（本段新的 + 候选里的旧的）· 认知用本地号（她看到的是 `u0001`）。
    取不到节点的落空表 —— 空表 ⇒ 交集为空 ⇒ 那一行丢, **不炸**。
    """
    out: dict[str, list[str]] = {}
    for nid in [*ctx.episode_ids, *cand_ids]:
        out[str(nid)] = _node_topics(ctx, nid)
    for real, local in local_of.items():
        node = ctx.store.get(real)
        if node is not None:
            out[local] = list(node.topics)
    return out


def _kind_of(ctx: Ctx, local_of: dict[str, str], cand_ids: list[str],
             ) -> dict[str, str]:
    """`{她能写的 id: kind}` —— 给 parse 判"两端类型"用（P2）。

    ⚠️ 键同样是**她看到的那一套**（经历/对象 = 真身 · 认知 = 本地号）。
    一个 id 可能出现在两边（经历同时是左端候选与右端候选）—— 值一样, 不冲突。
    """
    out: dict[str, str] = {}
    for nid in [*ctx.episode_ids, *cand_ids]:
        node = ctx.store.get(str(nid))
        if node is not None:
            out[str(nid)] = node.kind
    for real, local in local_of.items():
        node = ctx.store.get(real)
        if node is not None:
            out[local] = node.kind
    return out
