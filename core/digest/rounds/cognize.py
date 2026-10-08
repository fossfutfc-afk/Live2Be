# -*- coding: utf-8 -*-
"""cognize.py — ⑥ L2「造认知 / 写正文」: 造看法 + 给本段归过类的群写沉淀。

⭐ **它是第二趟**（`docs/DESIGN_DIGEST_TWO_PASSES.md` §3）:
    · L1（`relate`）只判关系, **一个字的正文都不写**;
    · 这一趟**只写正文** —— 造新的 `belief`（出生自带证据边 / 进化 / 打架）,
      并给**已有的类**（`experience`）重写它的**沉淀**。

## 它为什么排在最后

⭐ **顺序 = 结构先于正文**: 沉淀要写给"**本段刚归好类的那些类**", 而类由 `group` 建/挂
（它是上一轮）⇒ 这一趟才看得见"这一段给它添了哪几条"。`group` 那一步失败会**自吞**
（`own_snapshot`）⇒ 那些经历这段没有成员 ⇒ 这一趟自然跳过它们的沉淀（下一段再来）——
**不用任何额外机制**。

## 它的两条纪律

1. **不判已有成分之间的关系** —— 那是 L1 判过的（契约里明写"不用你判"）;
   这一趟只写"**新造的那条**跟谁相连"。
2. **不建类、不改类名、不动 `ts`** —— 起类名 / 圈成员是 `group` 的活
   （用户 2026-10-08: *"experience 本质是群 belief … 类是事件, 事件归 L1"*）。

## 失败语义

`own_snapshot=True`: 失败**只回滚这一步** —— 拿真东西换装饰是亏的（同 `group` 的判据）。
`return RoundOut.swallowed("cognize_warnings")` 只**申报**, 回滚 / 挪 errors 由编排执行。
"""
from __future__ import annotations

import logging

from core.brain.read.render import render_cognition_list
from core.brain.revise import apply_cognitions
from core.digest.material import _groups_for_l2, _l2_material
from core.digest.rounds.base import Ctx, RoundOut
from core.digest.rounds.relate import DIGEST_COGNITION_CAP

logger = logging.getLogger(__name__)


def run(ctx: Ctx) -> RoundOut:
    """⑥ 想 —— 造看法 + 写沉淀（失败只回滚自己）。"""
    spec = ctx.enter("cognize")
    grp_text, linked_text, evidence_ids = _l2_material(ctx)
    groups = _groups_for_l2(ctx)
    if not groups and not evidence_ids:
        # 既没有可写的类、也没有被连过的经历 ⇒ 归纳没有立足点（**跳过不是失败**）
        ctx.log_skip(spec)
        return RoundOut.skipped()
    cog_text, local_of = render_cognition_list(
        ctx.store, cap=DIGEST_COGNITION_CAP, exclude=set(ctx.player_ids))
    system = ctx.system_for(spec)
    user = ctx.sections_for(spec, [
        ("本段归类的群", grp_text),
        ("被连过的经历", linked_text),
        ("现有认知", cog_text),
        ("角色人设（锚点）", ctx.character_prompt),
    ])
    drops_before = len(ctx.result.contract_drops)     # 观测账: 只算**这一轮**丢的
    rows, _resp = ctx.call(
        spec, system, user,
        parse_fn=ctx.parse_for(
            spec,
            # ⭐ 她能引用的 = **料里印出来过的全部**（`_l2_material` 的第三个返回值 ——
            # 从渲染里带出来的, 不另算一份）; 少一类就整包拒。
            evidence_ids=set(evidence_ids),
            # 认知那一端是**本地号**（`u0001…`）—— 与 L1 同一个口径。
            cognition_ids=set(local_of.values()),
            group_ids={g for g, _new in groups},
            # `evolved_from` / `contradicts` 的另一端必须是**看法**（挡画像: 画像没有
            # "进化"可言, 也不是"看法"）。
            kind_of=_kind_of(ctx, local_of)))
    if rows is None:
        # ⚠️ 只申报: 回滚 / 挪 errors 在编排里（表里 `own_snapshot=True`）
        return RoundOut.swallowed("cognize_warnings")
    res = apply_cognitions(ctx.store, rows, ts=ctx.now_ts,
                           id_map={v: k for k, v in local_of.items()},
                           event_seq=[ctx.interact_max])
    ctx.result.created_beliefs = list(res.created)
    ctx.result.reused_beliefs = list(res.reused)
    ctx.result.soaked_groups = list(res.soaked)
    # 观测账（可 grep）: 这一趟干了什么 —— 与 P6 的 `digest_relate` 同一个口径
    # （`dropped=` 取**调用前后** `contract_drops` 的差, ⛔ 不靠中文子串匹配）
    logger.info("digest_cognize rows=%d beliefs=%d reused=%d edges=%d soaked=%d dropped=%d",
                len(rows), len(res.created), len(res.reused),
                len(res.edges), len(res.soaked),
                len(ctx.result.contract_drops) - drops_before)
    return RoundOut.done()


def _kind_of(ctx: Ctx, local_of: dict[str, str]) -> dict[str, str]:
    """`{她能写的认知本地号: kind}` —— 给 parse 判"另一端是不是看法"用。"""
    out: dict[str, str] = {}
    for real, local in local_of.items():
        node = ctx.store.get(real)
        if node is not None:
            out[local] = node.kind
    return out
