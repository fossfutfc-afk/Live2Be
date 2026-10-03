# -*- coding: utf-8 -*-
"""split.py — ⓪ R0「切分员」: 本段时间线 → **切片骨架**（区间 + `keep` + `abstract`）。

料（表里那两行, `ctx.sections_for` 逐字校对）: 本段新增互动 · 本章标题。
⚠️ **只有这两样** —— 画面记忆 / 人设 / 情绪标尺**不给它**: 切分是**结构判断**,
不需要人设; 给了反而诱使它写文学化的 `abstract`（那是 R1 的活）。

写: **段内中间产物** `ctx.result.segments`（`{span, keep, abstract}` 的列表）——
⛔ 不建节点、不碰图、不写 note。它交出去的是**骨架**, R1 照着它往里面填血肉。

⭐ **它是本段的第一步, 也是唯一能"叫停整段"的一步**: `{"segments": []}` = 这一段
没有值得记的 ⇒ 编排层**当场收工**（后面几轮一次都不发, 见 `pipeline` 的那条 break）。
⚠️ 那个判据**不在本文件的 `run()` 里** —— "跳过一整段"要同时决定水位推不推,
那是整段级的账, 归编排（表里这一轮的 `skip` 格也故意留空）。

⚠️ **它拿走了 R1 从前最重的那件事（划区间）** ⇒ 图的形状（几个节点、每个覆盖哪段）
从此由它一个人决定。所以它的产出必须**可校验**（区间在不在时间线里 —— 契约层的
`parse_split`）且**可观测**（几条 / 几条 keep / 覆盖多少 —— 下面的日志）。
"""
from __future__ import annotations

import logging

from core.digest.rounds.base import Ctx, RoundOut

logger = logging.getLogger(__name__)


def run(ctx: Ctx) -> RoundOut:
    """⓪ 切 —— 本段时间线 + 章标题 → 切片骨架（不建节点）。"""
    spec = ctx.enter("split")
    system = ctx.system_for(spec, domain=ctx.domain, chapter_count=len(ctx.chapters))
    user = ctx.sections_for(spec, [
        ("本段新增互动", ctx.timeline),
        ("本章标题", " / ".join(c["title"] for c in ctx.chapters if c["title"])),
    ])
    segments, _resp = ctx.call(
        spec, system, user,
        parse_fn=ctx.parse_for(spec, seq_set=ctx.seq_set))
    if segments is None:
        return RoundOut.failed()
    ctx.result.segments = segments
    logger.info("digest_split segments=%d keep=%d span=%s",
                len(segments),
                sum(1 for s in segments if s.get("keep") == "always"),
                " ".join(f"{s['span'][0]}-{s['span'][1]}" for s in segments[:8]) or "-")
    return RoundOut.done()
