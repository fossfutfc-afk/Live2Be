"""group.py — ⑤ L2-a 分群: 还没归类的块 + 已有的类 → **群节点 + `member_of` 边**。

料（表里那三行）: 还没归类的块 · 已有的类 · 可能重复的类。

⚠️ 它是每段的**最后一步**, 与 R1–R4 **不同层**:
    · 料 = 引擎切好的块（`akin` 连通块, ⭐ **边不进视野**）+ 已有的类
    · 产 = 群节点 + `member_of` 边; 它**只起名**, 不判"像不像"（那是她的活）

⚠️⚠️ **它失败不连累整段** —— 分群是**加法**的（块留到下段再来 ⇒ 自愈）, 所以这一步在
表里 `own_snapshot=True`。失败时它**只申报、不动手**:
    `return RoundOut.swallowed("group_warnings")`
⇒ **快照 / 回滚 / 把 errors 挪进 warnings 全由编排执行**
（`pipeline.digest_segment` 的循环）—— 这一步自己一行都不碰整段的事务。
判据: 把"命名没成"升级成"整段记忆全丢"是拿真东西换装饰。

⚠️ **顺序: 先归属, 后并群** —— 反过来那条 `attach` 会打在一个已经删掉的类上。
"""
from __future__ import annotations

import logging

from core.brain import groups
from core.digest.rounds.base import Ctx, RoundOut

logger = logging.getLogger(__name__)


def run(ctx: Ctx) -> RoundOut:
    """⑤ 分群 —— 给连出来的块起类名 / 并掉重复的类（失败只回滚自己）。"""
    spec = ctx.enter("group")
    blks = groups.build_blocks(ctx.store, groups.ungrouped(ctx.store))
    cands = groups.merge_candidates(ctx.store)
    if not blks and not cands:
        ctx.log_skip(spec)
        return RoundOut.skipped()
    system = ctx.system_for(spec)
    user = ctx.sections_for(spec, [
        ("还没归类的块",
         groups.render_blocks(ctx.store, blks) or "（这一段没有新连出来的块）"),
        ("已有的类", groups.render_groups(ctx.store) or "（还没有任何类 —— 全部走 new）"),
        ("可能重复的类", groups.render_merge_candidates(ctx.store, cands)),
    ])
    rows, _resp = ctx.call(
        spec, system, user,
        parse_fn=ctx.parse_for(spec, block_ids={b.bid for b in blks}))
    if rows is None:
        # ⚠️ 只申报: 回滚 / 挪 errors 在编排里（见模块 docstring）
        return RoundOut.swallowed("group_warnings")
    # ⚠️ 顺序: **先归属, 后并群** —— 反过来那条 attach 会打在一个已经删掉的类上
    gres = groups.apply_groups(
        ctx.store, [r for r in rows if r["action"] in ("attach", "new")],
        blks, ts=ctx.now_ts, event_seq=[ctx.interact_max])
    mres = groups.apply_merges(
        ctx.store, [r for r in rows if r["action"] == "merge"], cands, ts=ctx.now_ts)
    ctx.result.created_groups = list(gres.nodes)
    ctx.result.grouped_episodes = len(gres.grouped)
    ctx.result.merged_groups = list(mres.merged)
    ctx.result.group_warnings = list(gres.warnings) + list(mres.warnings)
    for w in ctx.result.group_warnings:
        logger.warning("digest_group: %s", w)
    logger.info("digest_group blocks=%d cand=%d rows=%d new=%d grouped=%d "
                "merged=%d moved=%d warn=%d",
                len(blks), len(cands), len(rows), len(gres.nodes),
                len(gres.grouped), len(mres.merged), mres.moved,
                len(ctx.result.group_warnings))
    return RoundOut.done()
