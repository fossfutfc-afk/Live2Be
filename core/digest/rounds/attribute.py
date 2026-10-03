# -*- coding: utf-8 -*-
"""attribute.py — ④ R3「归属」: 候选对象 + 命中集载荷 + 本轮新节点 → `about` 边 + entity。

料（表里那四行）: 候选对象 · 这几个对象的当前情况 · 本轮新节点 · 角色人设（锚点）。

写: `entity` 节点（name / aliases / text / state）· 边 `about`。
⚠️ **归属的唯一落地形式是边**: 有边 = 归好了, 没边 = 没归（`about_state` 三态读它）。

**为什么它必须排在最后**: 它要挂的是**本轮全部新节点**（R1 的经历/画像 + R2 新建的
认知）⇒ 前面几轮都落地了它才看得全（批内顺序 R1→R4→R2→R3）。

⚠️ **两套本地号必须分开**（`node_local` vs `ent_local` —— 混用会让"挂谁"与"挂在谁身上"
写反）: 前者是**本轮新节点**的 `u0001…`, 后者是**候选对象表**的 `c0001…`。
⚠️ **命中集只决定"给 R3 看哪些对象的当前载荷"** —— 候选表是全量的, 所以命中变窄
= 少看一点载荷, **不是判不了挂谁**（`REDUNDANCY.md` #2）。
⏸ `about_hint`（R1 预判的名字）**2026-09-29 字段退役** ⇒ 这里只喂**正文通道**
（引擎从新节点的 text/title/verbatim 里认称呼, 确定性）。
"""
from __future__ import annotations

import logging

from core.brain.entities import candidate_table, hit_set, new_nodes_block, payload_block
from core.brain.revise import apply_attribution
from core.digest.material import _node_texts
from core.digest.rounds.base import Ctx, RoundOut

logger = logging.getLogger(__name__)


def run(ctx: Ctx) -> RoundOut:
    """④ 挂 —— 本轮新节点归到候选对象上（没有可归属的新节点 ⇒ 按表跳过）。"""
    spec = ctx.enter("attr")
    new_ids = [*ctx.episode_ids, *ctx.player_ids, *ctx.r2_created]
    node_text, node_local = new_nodes_block(ctx.store, new_ids)
    if not node_text:
        ctx.log_skip(spec)
        return RoundOut.skipped()
    table_text, ent_local = candidate_table(ctx.store)
    # ⭐ 2026-09-29: `about_hint`（R1 预判的名字）退役 ⇒ 这里只喂**正文通道**
    # （引擎从新节点的 text/title/verbatim 里认称呼, 确定性）。
    # ⚠️ **命中集只决定"给 R3 看哪些对象的当前载荷"** —— 候选表是全量的,
    # 所以命中变窄 = 少看一点载荷, **不是判不了挂谁**（`REDUNDANCY.md` #2）。
    hits = hit_set(ctx.store, texts=_node_texts(ctx.store, new_ids))
    payload = payload_block(ctx.store, hits, ent_local)
    logger.info("digest_hit eps=%d hit=%d", len(new_ids), len(hits))
    system = ctx.system_for(spec)
    user = ctx.sections_for(spec, [
        ("候选对象", table_text or "（还没有任何对象）"),
        ("这几个对象的当前情况", payload),
        ("本轮新节点", node_text),
        ("角色人设（锚点）", ctx.character_prompt),
    ])
    rows, _resp = ctx.call(
        spec, system, user,
        parse_fn=ctx.parse_for(spec, entity_ids=set(ent_local.values()),
                               node_ids=set(node_local.values())))
    if rows is None:
        return RoundOut.failed()
    ctx.result.created_entities = apply_attribution(
        ctx.store, rows,
        id_map={v: k for k, v in node_local.items()},   # local→real
        local_of=ent_local, ts=ctx.now_ts, event_seq=[ctx.interact_max])
    logger.info("digest_attr table=%d hit=%d payload=%d rows=%d new=%d",
                len(ent_local), len(hits), len(payload.splitlines()),
                len(rows), len(ctx.result.created_entities))
    return RoundOut.done()
