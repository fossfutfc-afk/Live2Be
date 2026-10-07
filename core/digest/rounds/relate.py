# -*- coding: utf-8 -*-
"""relate.py — ③ L1「判关系」: 本段经历 + 认知列表 → **关系表**（只落边）。

⭐ 这一趟**一个字正文都不写**（`docs/DESIGN_DIGEST_TWO_PASSES.md` §9）—— 它只回答
"谁和谁是什么关系"; 造看法 / 写正文是**另一趟**（L2）。两趟按**注意力**切
（`DESIGN_MEMORY_MODES.md` §0）: 一场调用里既判关系又写正文, 数据量一大,
"连接"的注意力就被写正文冲淡。

料（表里那四行）: 本次新经历（含引擎候选标注）· 本段时间线 · 现有认知 · 角色人设（锚点）。
⚠️ 「现有经历（候选）」**还没进料**（P2 那笔）⇒ 今天 `akin` / `contradicts` 只连得上
**本段之内**的两条经历, 连不到更早的那些。

写: 边 `supports` / `akin` / `contradicts` / `about`（`apply_relations` —— 一个节点都不建）。

## 两套 id 空间（⭐ 这一笔最容易写错的地方）

| 哪一端 | 空间 | 谁发的 |
|---|---|---|
| 经历 `m…` · 对象 `x…` | **真实 id** | 料里印的就是真身（`_round_b_material` / 候选表）|
| 认知 `u0001…` | **本地号** | `render_cognition_list`（它的判据: "parse 层只认本地 id, 防 LLM 猜真实 id"）|

⇒ 执行时用 `id_map` 翻回来; 而 `topics_of`（`akin` 的轴校验要它）**两个空间都要有键**
（她写的那一端用哪个空间的 id, 就用哪一边去查）。

## 三处"关着"的东西（**都有意**, ⛔ 别当成漏了）

1. **`about` 的候选 = 空集** —— 料里**还没印**那 ≤5 个人名（P2 那笔）⇒ `about` 一行都
   落不下来（丢行 + 记账）。⛔ **不传 `None`**: 那等于不校验, 编造的 `x9999` 会一路走到
   `add_edge`（它**拒悬空**）⇒ 抛错 ⇒ **整段回滚** —— 空集是"没有候选"的唯一安全写法。
2. **`akin` 的 `on` 交集校验 = 开着**（传真实 `topics_of`）—— 而 `topics` 今天**没有任何
   地方印给她看** ⇒ 那个词只能靠正文猜, 猜不中就丢行。这是**有意**的: 轴不成立的边一条都
   不许进图（宁缺勿错）; P2 把 `topics` 印进料之后它自然见效。
3. **`r2_created` 不赋值** —— 它记的是"本轮新建的节点", 而这一趟**不建节点**
   （R3 归属轮还在暂停; 将来由 L2 自己填）。
"""
from __future__ import annotations

import logging

from core.brain.read.render import render_cognition_list
from core.brain.revise import apply_relations
from core.digest.material import _round_b_material
from core.digest.rounds.base import Ctx, RoundOut

logger = logging.getLogger(__name__)

#: 认知渲染上限（本地 id 数量; 排序: 珍贵档先）
DIGEST_COGNITION_CAP = 12


def run(ctx: Ctx) -> RoundOut:
    """③ 接 —— 把本段经历接到已有认知 / 已有经历上。"""
    spec = ctx.enter("relate")
    cog_text, local_of = render_cognition_list(
        ctx.store, cap=DIGEST_COGNITION_CAP, exclude=set(ctx.player_ids))
    ep_text = _round_b_material(ctx.store, ctx.episode_ids, local_of,
                                embed_fn=ctx.embed_fn,
                                char_id=getattr(ctx.store, "char_id", ""))
    system = ctx.system_for(spec)
    user = ctx.sections_for(spec, [
        ("本次新经历（含引擎候选标注）", ep_text),
        ("本段时间线", ctx.timeline),
        ("现有认知", cog_text),
        ("角色人设（锚点）", ctx.character_prompt),
    ])
    rows, _resp = ctx.call(
        spec, system, user,
        parse_fn=ctx.parse_for(spec,
                               episode_ids=set(ctx.episode_ids),
                               # ⭐ **右边能引用的 = 渲染列表里的全部**: 认知用本地号
                               # （`u0001…`）, 本段新经历用真身（`m…` —— 它们在
                               # 「本次新经历」那一段里印着）。⛔ 不传"只有认知"那一份:
                               # 那会把"本段两条经历之间"的 `akin` 判成**编造 id**
                               # ⇒ 整包拒（端到端用例逼出来的这一处）。
                               target_ids=set(local_of.values()) | set(ctx.episode_ids),
                               entity_ids=set(),            # ← 模块 docstring 第 1 条
                               topics_of=_topics_of(ctx, local_of)))
    if rows is None:
        return RoundOut.failed()
    apply_relations(ctx.store, rows, ts=ctx.now_ts,
                    id_map={v: k for k, v in local_of.items()})   # 本地号 → 真实 id
    return RoundOut.done()


def _topics_of(ctx: Ctx, local_of: dict[str, str]) -> dict[str, list[str]]:
    """`{她能写的 id: topics}` —— ⚠️ **两个空间都要有键**（见模块 docstring）。

    经历用真实 id（她写的就是真身）· 认知用本地号（她看到的是 `u0001`）。
    取不到节点的落空表 —— 空表 ⇒ 交集为空 ⇒ 那一行丢, **不炸**。
    """
    out: dict[str, list[str]] = {}
    for nid in ctx.episode_ids:
        node = ctx.store.get(nid)
        if node is not None:
            out[str(nid)] = list(node.topics)
    for real, local in local_of.items():
        node = ctx.store.get(real)
        if node is not None:
            out[local] = list(node.topics)
    return out
