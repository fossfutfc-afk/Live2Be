# -*- coding: utf-8 -*-
"""record.py — ① R1「记录员」: 本段新增互动 → episode / 玩家画像。

料（表里那五行, `ctx.sections_for` 逐字校对）: 本段新增互动 · 本章标题 · 画面记忆 ·
角色人设（锚点）· 本段情绪标尺。

写: `episode` 节点 · `experience`（玩家画像）节点。
⚠️ `writes` 的真源是 `rounds.ROUNDS` 那一格, 不在本文件里再写一遍。
⛔ ~~note 的 `on_mind` 槽~~ **2026-09-29（N4e）退役** —— L1 从此**只写图**, 不写 note
（约定归 R4 收口那一轮; 见 `notes.py` 的模块 docstring）。

引擎侧三个邻居（本文件只管"她说了什么", 判定全在引擎）:
    `core/digest/episodes.py`  → 条目落成节点（字段归属 / 去重 / 自己的时刻 / 板指针物化）
    `core/digest/segment.py`   → 段类型 · `span` 展开 · 章收口（⛔ **3b-1 起归 R0 调**）
    `core/brain/notes.py`      → 约定那条线（R4 收口; 本文件不碰）

⚠️ **顺序有一条是正确性, 不是风格**: `_resolve_verbatim` 在落节点**之前**
（索引 → 原文, 引擎的活）。
⛔ ~~`_expand_spans` 在 `_collapse_bond_episodes` 之前~~ **2026-09-29（3b-1）随它们一起
搬去了 `rounds/split.py`** —— 那条顺序仍然成立, 只是不再住在本文件里。

⏸ **3b-1 的过渡状态**: 切分权已经归 R0（切片带 `seqs`）, 但 R1 **还在自己划区间**
（它这轮还没看见骨架 —— 那是 3b-2）。所以这一步**行为零变化**, 只是"位置"的来源
从她的条目换成切片的 `seqs` 兜底。
"""
from __future__ import annotations

import logging

from core.digest.episodes import _create_a_nodes, _resolve_verbatim
from core.digest.rounds.base import Ctx, RoundOut
from core.digest.segment import _seqs_of, _span_range

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
    entries, _resp = ctx.call(
        spec, system, user,
        parse_fn=ctx.parse_for(spec, seq_set=ctx.seq_set))
    if entries is None:
        return RoundOut.failed()
    # 索引 → 原文（T14）: parse 层拿不到事件流, 回填在这里做
    for ent in entries:
        _resolve_verbatim(ent, ctx.by_seq)
    # ⭐ 3b-1 过渡: 位置由**切片的 `seqs`** 说了算（切分权已归 R0）, 而 R1 这一轮
    # 还在自己划区间 ⇒ 按声明的区间去切片里**取交集**, 取不到就让它没有位置
    # （落回段级指针 —— 那是"她的区间越界/没有对应切片"的既有处置, 见 D1 的 `no_pos`）。
    # ⚠️ 章块那条"覆盖兜到整章"的兜底也跟着搬了过来（见 `_apply_segment_seqs`）。
    _no_pos = _apply_segment_seqs(entries, ctx.result.segments, ctx.chapters)
    # ⛔ **`span` 展开 / 章收口 / 覆盖率那本账 2026-09-29（3b-1）搬去了 R0** ——
    # 切分权归切分员之后, "区间 → 图"是对着**切片**做的（`rounds/split.py` 的产出点）。
    # 这里剩下的只是"她说了什么" → 节点, 位置由切片带过来（`ent["seqs"]`）。
    submitted = len(entries)
    reused: list[str] = []
    ctx.episode_ids, ctx.player_ids = _create_a_nodes(
        ctx.store, entries, ts=ctx.now_ts,
        event_seq=[ctx.interact_max], aff_at_encoding=ctx.aff_at_encoding,
        by_seq=ctx.by_seq, reused_out=reused)
    # ⭐ D1 的**条目面**台账（`items`）—— 只有它**不可重算**:
    # 一章一件丢掉的那条骨架、判重复而复用的 id, 那一刻之后世上没有第二份记录。
    # ⚠️ 声明在表里 record 的 `result_fields` ⇒ 整段回滚时由 `reset_result` 一起清掉
    # （否则会出现"回滚了却留着一条缺口账"）。造行在 `pipeline` 的**提交块**（`_note_gap`）。
    # ⚠️ `dropped`（章收口丢掉的那几条）**归 R0 造**（`split` 那一轮, 切分权在它手里）
    # ⇒ 这里只把那一半接过来, 与"她多写/复用"的那几项并成一行账。
    dropped = list(getattr(ctx.result, "segment_collapsed", None) or [])
    ctx.result.record_gaps = {"items": {
        "in": len(entries) + len(dropped), "kept": len(entries),
        "no_pos": _no_pos, "dropped": dropped, "reused": reused}}
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
    return RoundOut.done()


def _apply_segment_seqs(entries: list[dict], segments: list[dict],
                        chapters: list[dict]) -> int:
    """把**切片的 seq** 落到她每条条目的 `seqs` 上（3b-1 的过渡对位）—— 返回"没落上"的条数。

    ## 为什么要对位（这是 3b-1 唯一新增的语义）

    切分权归 R0 之后, "一条记录覆盖哪些事件"由**切片**说了算（`segments[i]["seqs"]`）。
    但 R1 这一轮**还没看见骨架**（那是 3b-2）⇒ 它照样声明 `span`。
    对位规则: **她声明的区间 ∩ 切片的 seq**, 取交集; 落在**多条切片**里时取**最窄**的那条
    （"这条记录属于哪一件"—— 窄的那条更具体; 真机 `m0015[208..235]` 与 `m0016[214..223]`
    正是这种嵌套）。

    ⚠️ **落在章块里的, 位置一律兜到整章** —— 这条判据原来住在 `_collapse_bond_episodes`
    （它从前吃 R1 的条目）; 收口搬到切片层之后, 那半张判据跟着搬到这里,
    ⛔ **否则会丢**: "她只划了 11–12 而章是 11–14"那种情形, 章尾会留在水位之上
    ⇒ 下一段**重喂**（而重喂的窗口里没有 `vn_enter` ⇒ 被当孤儿章 ⇒ 可能重复记一条）。

    ⚠️ **取不到交集 ⇒ 不落 `seqs`**: 那让 `_create_a_nodes` 回落到**段级指针**
    （`[interact_max]`）—— 与"她没给位置/位置被契约层丢了"同一个既有处置, 并进 D1 的
    `no_pos` 账。⛔ **不要**退化成"用切片自己的区间" —— 那是引擎替她认领了**她没声称**的事件
    （她的区间越界了, 该看得见, 不该被顺手补好）。

    ⛔ **3b-2 一到就删这个函数**: 那时 R1 按骨架填、`segments[i]["seqs"]` 直接带过去,
    根本不需要对位（对位是"两套位置声明并存"的过渡产物）。
    """
    chapter_seqs: list[frozenset] = [c["seqs"] for c in chapters if c.get("seqs")]
    no_pos = 0
    for ent in entries:
        seqs = _pick_segment_seqs(ent, segments)
        if not seqs:
            no_pos += 1
            continue
        ent["seqs"] = seqs
        for ch in chapter_seqs:                      # 章块 ⇒ 覆盖兜到整章
            if any(s in ch for s in seqs):
                ent["seqs"] = sorted({*seqs, *(int(s) for s in ch)})
                break
    return no_pos


def _pick_segment_seqs(ent: dict, segments: list[dict]) -> list[int]:
    """条目声明的区间 ∩ 各切片的 seq —— 取最窄的那条切片（取不到 ⇒ 空）。"""
    seqs = {s for s in _seqs_of(ent)}          # 条目自带的优先（旧形状逐点声明）
    rng = _span_range(ent)
    if not seqs and rng is not None:
        hits = [sg for sg in segments if sg.get("seqs")
                and rng[0] <= max(sg["seqs"]) and min(sg["seqs"]) <= rng[1]]
        if not hits:
            return []
        pick = min(hits, key=lambda sg: max(sg["seqs"]) - min(sg["seqs"]))
        return [s for s in pick["seqs"] if rng[0] <= s <= rng[1]]
    if not seqs:
        return []
    # 逐点声明: 只要有任何一条切片覆盖到它, 就算落上了（并集）
    covered = {s for sg in segments for s in (sg.get("seqs") or [])}
    return sorted(seqs & covered) if covered else sorted(seqs)
