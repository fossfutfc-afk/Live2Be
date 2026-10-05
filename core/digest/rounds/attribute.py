# -*- coding: utf-8 -*-
"""attribute.py — ④ R3「归属」: 候选对象 + 命中集载荷 + 本轮新节点 → `about` 边 + entity。

⏸ **2026-10-05 暂停**（`PAUSED`）—— entity 那条链路今天没有读侧消费者, 而它每段付一次
调用; 它的两件活并进 M3 的两趟（见模块常量上的注释）。**代码全留, 相位不摘**。

料（表里那四行）: 候选对象 · 这几个对象的当前情况 · 本轮新节点 · 角色人设（锚点）。

写: `entity` 节点（name / aliases / text / state）· 边 `about`。
⚠️ **归属的唯一落地形式是边**: 有边 = 归好了, 没边 = 没归（`about_state` 三态读它）。

**为什么它必须排在最后**: 它要挂的是**本轮全部新节点**（R1 的经历/画像 + R2 新建的
认知）⇒ 前面几轮都落地了它才看得全（批内顺序 R0→R1→R2→R3）。

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

#: ⏸ **暂停（2026-10-05）** —— entity 那条链路今天**没有读侧消费者**:
#: 注入的四个桶（episode / belief / player / reported）里**没有 entity**,
#: `core/brain/read/` 对它**零引用**, `graph.unattributed()` 也零生产调用者
#: ⇒ "R3 写 → R3 下一段读"是个闭环, 而它每段要付**一次 LLM 调用**。
#:
#: **它的两件活的去向**（用户裁: 并进 M3 的两趟, 边际成本≈0）:
#: `attach`（归属 → `about` 边）→ **M3 第一趟**（它已经在看"新的东西 × 已有的类"）;
#: entity 摘要 / `state`（"她现在的样子"）→ **M3 第二趟**（它本来就要读整组全文）。
#:
#: **重开判据**: ① wiki 大到全量注不进去（今天真机 1.6k~3.1k 字）② 要做"动态成长线"呈现。
#: ⚠️ **重开只对以后生效** —— digest 不回溯, 暂停期间那些段落的归属**永远缺着**;
#: 要补旧账得走一次性脚本（`core/session/maintenance.py` 那套工具面）。
#: ⚠️ 所以**代码一字不删、相位也不摘**: 恢复 = 把这个常量翻掉（`tests/core/test_round_attr.py`
#: 那个 autouse fixture 就是"临时翻开"的写法）。
PAUSED = True


def run(ctx: Ctx) -> RoundOut:
    """④ 挂 —— 本轮新节点归到候选对象上（没有可归属的新节点 ⇒ 按表跳过）。"""
    spec = ctx.enter("attribute")
    if PAUSED:                     # ⏸ 全局暂停 —— 理由与恢复判据见 `PAUSED` 的注释
        ctx.log_skip(spec)
        return RoundOut.skipped()
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
    logger.info("digest_attribute nodes=%d hit=%d", len(new_ids), len(hits))
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
    logger.info("digest_attribute table=%d hit=%d payload=%d rows=%d new=%d",
                len(ent_local), len(hits), len(payload.splitlines()),
                len(rows), len(ctx.result.created_entities))
    return RoundOut.done()
