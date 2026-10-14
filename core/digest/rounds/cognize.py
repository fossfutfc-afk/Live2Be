"""cognize.py — ⑥ L2「造认知 / 写正文」: 造看法（这一趟唯一的动作）。

⭐ **它是第二趟**（`docs/DESIGN_DIGEST_TWO_PASSES.md` §3）:
    · L1（`relate`）只判关系, **一个字的正文都不写**;
    · 这一趟**只写正文** —— 造新的 `belief`（出生自带证据边 / 进化 / 打架）。

⏸ **2026-10-13**: 原先它还有第二件事 —— 给**已有的类**（`experience`）重写**沉淀**。
那是 `group`（分群, 同一趟的上一轮）的下游, 而 `group` 退役了 ⇒ 那一半**停产**
（契约不再要它, `COGNIZE_RETIRED` 认得出、丢行、⛔ 不判非法）。所以本节原来的
"它为什么排在最后"（顺序 = 结构先于正文）也**不再成立** —— 今天它没有需要等待的上游。

## 它的两条纪律

1. **不判已有成分之间的关系** —— 那是 L1 判过的（契约里明写"不用你判"）;
   这一趟只写"**新造的那条**跟谁相连"。
2. **一个节点面只造一种东西**: `belief`; ⛔ 不改已有的正文、不动 `ts` / `title`。

## 失败语义

`own_snapshot=True`: 失败**只回滚这一步** —— 拿真东西换装饰是亏的（同 `group` 的判据）。
`return RoundOut.swallowed("cognize_warnings")` 只**申报**, 回滚 / 挪 errors 由编排执行。
"""
from __future__ import annotations

import logging

from core.brain.read.render import render_cognition_list
from core.brain.revise import apply_cognitions
from core.digest.material import _l2_material, _node_texts, collided_beliefs_block, existing_entities_line
from core.digest.rounds.base import Ctx, RoundOut
from core.digest.rounds.relate import DIGEST_COGNITION_CAP

logger = logging.getLogger(__name__)


def run(ctx: Ctx) -> RoundOut:
    """⑥ 想 —— 造看法（失败只回滚自己）。"""
    spec = ctx.enter("cognize")
    linked_text, evidence_ids = _l2_material(ctx)
    if not evidence_ids:
        # 没有被 L1 连过的经历 ⇒ 归纳没有立足点（**跳过不是失败**）
        ctx.log_skip(spec)
        return RoundOut.skipped()
    cog_text, local_of = render_cognition_list(
        ctx.store, cap=DIGEST_COGNITION_CAP)
    # ⭐ **撞上那一格**: 跟本段证据**共享证据**的已有看法（共同证据优先）。
    # ⚠️ 它可能给"cap 之外"的看法发新本地号 ⇒ 必须赶在下面那份 `cognition_ids` 之前跑。
    collide_text = collided_beliefs_block(ctx.store, evidence_ids, local_of)
    system = ctx.system_for(spec)
    user = ctx.sections_for(spec, [
        ("被连过的经历", linked_text),
        ("现有认知", cog_text),
        ("跟这条撞上的现有看法", collide_text),
        # ⭐ E1b: 写 `#entity:` 之前先看**已有的对象**（防自造别名 ⇒ 重复建对象）
        ("已有的对象",
         existing_entities_line(ctx.store, texts=_node_texts(ctx.store, ctx.episode_ids))),
        ("角色人设（锚点）", ctx.character_prompt),
    ])
    drops_before = len(ctx.result.contract_drops)     # 观测账: 只算**这一轮**丢的
    rows, _resp = ctx.call(
        spec, system, user,
        parse_fn=ctx.parse_for(
            spec,
            # ⭐ 她能引用的 = **料里印出来过的全部**（`_l2_material` 的第二个返回值 ——
            # 从渲染里带出来的, 不另算一份）; 少一类就整包拒。
            evidence_ids=set(evidence_ids),
            # 认知那一端是**本地号**（`u0001…`）—— 与 L1 同一个口径。
            cognition_ids=set(local_of.values()),
            # ⏸ `group_ids` **不传**（缺省 None = 不校验）: 没有类可写了, 停产的那一行
            # 在契约层就被丢掉了（`COGNIZE_RETIRED`）。⛔ 传一个恒空的集合, 反而会把
            # 停产行判成"不在名单里" ⇒ **整包拒** —— 那正是这一刀要修的口子。
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
    logger.info("digest_cognize rows=%d beliefs=%d reused=%d patched=%d edges=%d akin=%d "
                "soaked=%d empty=%d watermark=%d dropped=%d strangers=%s",
                len(rows), len(res.created), len(res.reused), len(res.patched),
                len(res.edges), res.akin_joined, len(res.soaked),
                len(res.empty_skips), len(res.watermark_skips),
                len(ctx.result.contract_drops) - drops_before,
                res.strangers or "-")
    return RoundOut.done()


def _kind_of(ctx: Ctx, local_of: dict[str, str]) -> dict[str, str]:
    """`{她能写的认知本地号: kind}` —— 给 parse 判"另一端是不是看法"用。"""
    out: dict[str, str] = {}
    for real, local in local_of.items():
        node = ctx.store.get(real)
        if node is not None:
            out[local] = node.kind
    return out
