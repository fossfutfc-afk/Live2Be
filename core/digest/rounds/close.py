# -*- coding: utf-8 -*-
"""close.py — ② R4「收口」: 还开着的约定 + 本段经历 → **note 操作**（不建节点）。

料（表里那两行）: 还开着的约定（带编号 —— 它要照着 `id` 写 `close`）· 本段新增的经历
（真 id —— `add` / `close` 的 `refs` 只能引它们）。

⚠️ **它是 note 的唯一收口处**（2026-09-29）: `promise` 槽归它, ⭐ 而 `on_mind` 归 R1
（`record.py`）—— 两者共用 `DigestResult.notes_ops` 这条交付通道, 所以 R1 先 append、
这里**必须是 `extend` 而不是覆盖**。

⚠️ 它产的 note 操作**不在这里 append 进事件流**: 挂在 `result.notes_ops` 上, 由调用方在
**整批 `ok` 之后**才写（失败 = 整批回滚 ⇒ 那条约定原样开着; 事件 append 不可撤销,
提前写就回不去了）。

⚠️ **跳过条件**（表里那格）: 没有开着的约定、本段也没有新经历 ⇒ 这一轮**必然空转**
（`add` 没有可引用的经历、`close` 没有可翻篇的条目）。

⏸ **位置的理由已消失, 顺序照旧**: 从前"R4 必须夹在 R1 与 R2 之间"是因为它会物化
promise 节点、而那个节点的边由后两轮写; **2026-09-29 承诺退图之后它只产 note 操作、
不碰图**。顺序今天仍照旧（改了它没有收益, 却要重验一遍编排）, 但不再是正确性要求。
"""
from __future__ import annotations

import logging

from core.brain.revise import apply_closures
from core.digest.material import _episode_lines, _open_promises_text
from core.digest.rounds.base import Ctx, RoundOut

logger = logging.getLogger(__name__)


def run(ctx: Ctx) -> RoundOut:
    """② 收口 —— 开着的约定 + 本段经历 → note 操作（`add` / `close`）。"""
    spec = ctx.enter("close")
    note_state = ctx.store.notes_state(ctx.events)     # 本段之前的备忘录（缓存优先）
    open_promises = [it for it in note_state.promise if not it.closed]
    if not (ctx.episode_ids or open_promises):
        ctx.log_skip(spec)
        return RoundOut.skipped()
    system = ctx.system_for(spec)
    user = ctx.sections_for(spec, [
        ("还开着的约定", _open_promises_text(open_promises)),
        ("本段新增的经历", _episode_lines(ctx.store, ctx.episode_ids)),
    ])
    rows, _resp = ctx.call(spec, system, user, parse_fn=ctx.parse_for(spec))
    if rows is None:
        return RoundOut.failed()
    closures = apply_closures(ctx.store, rows, note_state=note_state, ts=ctx.now_ts)
    # ⚠️ **extend 不覆盖** —— `notes_ops` 里已经有 L1 交来的那句 `on_mind`（N4a）
    ctx.result.notes_ops.extend(closures.ops)          # ⚠️ 调用方等 ok 之后才 append
    ctx.result.notes_warnings = list(closures.warnings)
    for w in closures.warnings:
        logger.warning("digest_close: %s", w)
    logger.info("digest_close open=%d add=%d close=%d warn=%d",
                len(open_promises),
                sum(1 for o in closures.ops if o.get("action") == "add"),
                sum(1 for o in closures.ops if o.get("action") == "close"),
                len(closures.warnings))
    return RoundOut.done()
