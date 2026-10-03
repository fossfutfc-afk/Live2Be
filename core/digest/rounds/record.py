# -*- coding: utf-8 -*-
"""record.py — ① R1「记录员」: 本段新增互动 → episode / 玩家画像（+ note 的 `on_mind`）。

料（表里那五行, `ctx.sections_for` 逐字校对）: 本段新增互动 · 本章标题 · 画面记忆 ·
角色人设（锚点）· 本段情绪标尺。

写: `episode` 节点 · `experience`（玩家画像）节点 · note 的 `on_mind` 槽。
⚠️ `writes` 的真源是 `rounds.ROUNDS` 那一格, 不在本文件里再写一遍。

引擎侧三个邻居（本文件只管"她说了什么", 判定全在引擎）:
    `core/digest/episodes.py`  → 条目落成节点（字段归属 / 去重 / 自己的时刻 / 板指针物化）
    `core/digest/segment.py`   → `span` 区间展开 · 一章一条收口 · 段类型
    `core/brain/notes.py`      → `on_mind` 那句心境的 note 操作（`rewrite_op`）

⚠️ **顺序有两条是正确性, 不是风格**:
  · `_resolve_verbatim` 在落节点**之前**（索引 → 原文, 引擎的活）
  · `_expand_spans` 在 `_collapse_bond_episodes` **之前**（章的归属靠 `event_seq` 与章块
    **相交**; 展开前只有两个端点, 章块夹在中间时会漏判）—— 守门用例钉住这条
"""
from __future__ import annotations

import logging

from core.brain.notes import rewrite_op
from core.digest.episodes import _create_a_nodes, _resolve_verbatim
from core.digest.rounds.base import Ctx, RoundOut
from core.digest.segment import _collapse_bond_episodes, _expand_spans

logger = logging.getLogger(__name__)


def run(ctx: Ctx) -> RoundOut:
    """① 记 —— 本段新增互动 + 人设 + 视觉记忆 → 条目（→ 节点）。"""
    spec = ctx.enter("record")
    system = ctx.system_for(spec, domain=ctx.domain, chapter_count=len(ctx.chapters))
    user = ctx.sections_for(spec, [
        ("本段新增互动", ctx.timeline),
        ("本章标题", " / ".join(c["title"] for c in ctx.chapters if c["title"])),  # 多章都列; 空 → 跳过
        ("画面记忆", "\n".join(f"- {v}" for v in ctx.visuals)),
        ("角色人设（锚点）", ctx.character_prompt),
        ("本段情绪标尺", ctx.emotion_scale),
    ])
    # ⭐ N4a: 她此刻那句心境（0/1 条）—— 装在这个**本轮自己的**盒子里,
    # 由 parse 回调填、由下面那句取用。它不是跨轮状态, 所以不进 `Ctx`。
    on_mind_box: list[str] = []
    entries, _resp = ctx.call(
        spec, system, user,
        parse_fn=ctx.parse_for(spec, seq_set=ctx.seq_set, on_mind_out=on_mind_box))
    if entries is None:
        return RoundOut.failed()
    # ⭐ N4a: 她此刻那句心境 —— L1 产出, 与 promise（R4）一样走 `notes_ops`
    # （调用方**整批 ok 之后**才 append）。⚠️ 只有**她真写了**才产操作:
    # 缺键 = 不变（`rewrite_op(on_mind=None)` 本来就不动它）。
    if on_mind_box:
        ctx.result.notes_ops.append(rewrite_op(on_mind=on_mind_box[0]))
    # 索引 → 原文（T14）: parse 层拿不到事件流, 回填在这里做
    for ent in entries:
        _resolve_verbatim(ent, ctx.by_seq)
    # ⭐ N3（2026-09-29）: `span` → 区间内全部内容 seq。
    # ⚠️ **必须在 `_collapse_bond_episodes` 之前** —— 那一章的归属靠 `event_seq`
    #    与章块**相交**, 展开前只有两个端点, 章块夹在中间时会漏判。
    _unclaimed, _shared = _expand_spans(entries, ctx.seq_set)
    # ⭐ D1: 章的覆盖缺口 —— 章边界是**引擎已知的**（marker 派生）, 所以"章内还有内容
    # 没被那条 episode 覆盖"是一条**异常信号**（MMT 碎聊的未认领是常态, 章的不是）。
    # ⚠️ 它**可重算**（节点 `event_seq` + 章 marker 都在盘上）⇒ **进日志, 不进账**。
    _chapter_seqs = (frozenset().union(*[c["seqs"] for c in ctx.chapters])
                     if ctx.chapters else frozenset())
    submitted = len(entries)
    # ⭐ **没有位置的条目**（`span` 被契约层丢了 / 她压根没给）—— 它们会被引擎**兜底到
    # 段级指针**（`_create_a_nodes` 的 `event_seq=[interact_max]`）。
    # ⚠️ 那个兜底是**有意的**（见 `test_emo_shape_absent_when_no_pointer`: 段级指针是**真的**,
    # 那条记忆确实产生于这一段; 而且它保住了 `_find_duplicate` 的幂等）——
    # 但会计上它会让那个 seq 看起来"已认领" ⇒ **按条目算的未认领 ≠ 按节点算的**。
    # 所以这里把条数**记下来**（进账 + 日志）, 而不是改行为。
    _no_pos = sum(1 for e in entries if not e.get("event_seq"))
    # 一章一个 episode（2026-09-20）—— 引擎确定性收口 + 可观测告警（+ ⭐ D1 的台账出口）
    # ⚠️ **它还会把章的覆盖兜到整章**（D0: `segment._collapse_bond_episodes` 的并集）
    collapsed: list[dict] = []
    entries = _collapse_bond_episodes(entries, ctx.chapters, dropped_out=collapsed)
    # ⚠️ **未认领要在收口之后重算**: 章块的并集让"章内那几条"从"未认领"变成"已认领"
    # ⇒ 拿收口**前**算的那个数去记日志, 就会与节点上的覆盖**对不上**（两种口径）。
    _covered = {s for e in entries for s in (e.get("event_seq") or [])}
    _unclaimed = sorted(set(ctx.seq_set) - _covered)
    _uncovered = sorted(s for s in _unclaimed if s in _chapter_seqs)
    logger.info("digest_record span=%d 认领=%d 未认领=%d 共享=%d 章内未覆盖=%d "
                "无位置=%d 未认领seq=%s",
                submitted, len(ctx.seq_set) - len(_unclaimed), len(_unclaimed), _shared,
                len(_uncovered), _no_pos, _unclaimed[:20] or "-")
    # ── 时间推进：**已退役**（2026-09-17, `ESSAY_TIME_MODEL §10`）──
    # 旧实现读 Round A 的 `time_span` 推进 `WorldClock` 的**剧情游标**,
    # 再把新游标 stamp 到节点上（`story_time`）。整条链已废:
    # **唯一日期轴是现实日期**（`node.ts` —— 由下面的 `ts=now_ts` 落下）,
    # 剧情内部的流逝自由但**不累积、不进账**。
    # 段的日期 = 段内最后一条内容事件的时刻（见 `digest_segment` 里 `now_ts` 的取法）。
    # ⚠️ 契约侧的 `time_span` 字段本身也已删（2026-09-17 用户裁决）—— 它当时
    #    "保留但不消费", 而**新衰减模型的输入是活跃日/会话, 不是它**;
    #    加上 parse 层从来没取过它（连落库都没有）, 留着就是白付 token。
    #    枚举定义仍留在 `core/worldtime/span.py`。详见 `contract/digest_registry.py`。
    reused: list[str] = []
    ctx.episode_ids, ctx.player_ids = _create_a_nodes(
        ctx.store, entries, ts=ctx.now_ts,
        event_seq=[ctx.interact_max], aff_at_encoding=ctx.aff_at_encoding,
        by_seq=ctx.by_seq, reused_out=reused)
    # ⭐ D1 的**条目面**台账（`items`）—— 只有它**不可重算**:
    # 一章一条丢掉的条目正文、判重复而复用的 id, 那一刻之后世上没有第二份记录。
    # ⚠️ 声明在表里 record 的 `result_fields` ⇒ 整段回滚时由 `reset_result` 一起清掉
    # （否则会出现"回滚了却留着一条缺口账"）。造行在 `pipeline` 的**提交块**（`_note_gap`）。
    ctx.result.record_gaps = {"items": {"in": submitted, "kept": len(entries),
                                       "no_pos": _no_pos,
                                       "dropped": collapsed, "reused": reused}}
    return RoundOut.done()
