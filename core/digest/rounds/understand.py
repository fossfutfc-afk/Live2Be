# -*- coding: utf-8 -*-
"""understand.py — ③ R2「理解者」: 本段经历 + 时间线 + 认知列表 → 决策表（+ `links`）。

料（表里那四行）: 本次新经历（含引擎候选标注）· 本段时间线 · 现有认知 · 角色人设（锚点）。

写: `belief` 节点 · 边 `supports` / `contradicts` / `evolved_from`。

⏸ **`affection_exp_delta` 2026-10-05（M1）搬去 R1** —— 它是"**这一段**她对老师的亲近感
净变化", 与 `significance` 同族（都是打分）, 而打分归 R1（手里还有情绪标尺）。
⇒ 本函数**不再碰 `resp`**（那条"最易漏的跨轮依赖"跟着搬到了 `record`）。

⏸ **本段时间线这一段料已经没有存在的理由**（2026-09-29）: 它当初就是为
`evidence.quote` 逐字引用时间线而喂的, 而 `evidence` 字段已删（零产品消费者）。
"这段要不要一起去掉"是**改行为**, 单独一次刀 —— 今天照旧喂着（表里仍写着它,
`ctx.sections_for` 逐字校对, 删表里那格才删得掉）。
"""
from __future__ import annotations

import logging

from core.brain.read.render import render_cognition_list
from core.brain.revise import apply_decisions
from core.digest.material import _round_b_material
from core.digest.rounds.base import Ctx, RoundOut

logger = logging.getLogger(__name__)

#: B 轮认知渲染上限（本地 id 数量; 排序: 珍贵档先）
DIGEST_COGNITION_CAP = 12


def run(ctx: Ctx) -> RoundOut:
    """③ 接 —— 把本段经历接到现有认知上（touch / update / add + `links`）。"""
    spec = ctx.enter("understand")
    cog_text, local_of = render_cognition_list(
        ctx.store, cap=DIGEST_COGNITION_CAP, exclude=set(ctx.player_ids))
    # ⚠️ `links` 认的 id 集今天 = 可 touch 的看法（承诺退图后不再有第二种端点）;
    # 那个"两个 id 空间故意不同"的口径见 `parse_round_b` 的 `link_ids`。
    target_ids = {local for real, local in local_of.items()
                  if getattr(ctx.store.get(real), "kind", "") in ("belief", "profile")}
    link_ids = set(local_of.values())
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
    rows, resp = ctx.call(
        spec, system, user,
        parse_fn=ctx.parse_for(spec, episode_ids=set(ctx.episode_ids),
                               target_ids=target_ids, link_ids=link_ids))
    if rows is None:
        return RoundOut.failed()
    ctx.r2_created = apply_decisions(ctx.store, rows,
                                     id_map={v: k for k, v in local_of.items()},  # local→real
                                     ts=ctx.now_ts,
                                     event_seq=[ctx.interact_max])
    return RoundOut.done()
