# -*- coding: utf-8 -*-
"""record.py — ① R1「记录员」: **按骨架逐条填**（切分不归它）。

料（表里那六行, `ctx.sections_for` 逐字校对）: 本段新增互动 · **本段骨架** · 本章标题 ·
画面记忆 · 角色人设（锚点）· 本段情绪标尺。

写: `episode` 节点 · `experience`（玩家画像）节点。
⚠️ `writes` 的真源是 `rounds.ROUNDS` 那一格, 不在本文件里再写一遍。
⛔ ~~note 的 `on_mind` 槽~~ **2026-09-29（N4e）退役** —— L1 从此**只写图**, 不写 note
（约定归 R4 收口那一轮; 见 `notes.py` 的模块 docstring）。

引擎侧三个邻居（本文件只管"她说了什么", 判定全在引擎）:
    `core/digest/episodes.py`  → 条目落成节点（字段归属 / 去重 / 自己的时刻 / 板指针物化）
    `core/digest/segment.py`   → 段类型 · `span` 展开 · 章收口（⛔ **3b-1 起归 R0 调**）
    `core/brain/notes.py`      → 约定那条线（R4 收口; 本文件不碰）

⚠️ **顺序有两条是正确性, 不是风格**:
  · `_align_to_skeleton` 在 `_resolve_verbatim` **之前**（对齐要删条目 ⇒ 先删再解析,
    省掉对已被丢弃条目的白做）;
  · `_resolve_verbatim` 在落节点**之前**（索引 → 原文, 引擎的活）。
⛔ ~~`_expand_spans` 在 `_collapse_bond_episodes` 之前~~ **2026-09-29（3b-1）随它们一起
搬去了 `rounds/split.py`** —— 那条顺序仍然成立, 只是不再住在本文件里。

⭐ **3b-2（2026-09-29）: 切分权冻结给 R0**。R1 的输出**不再是"几条 episode"**,
而是"**按顺序填骨架**": 一条切片一行, 位置（`seqs`）与条数都由切片带过来;
她唯一的裁决权是 `drop`（"这一条不记"）。
"""
from __future__ import annotations

import logging

from core.brain.notes import ALREADY_PINNED, add_op
from core.digest.episodes import _create_a_nodes, _resolve_verbatim
from core.digest.material import SKELETON_HINT, _skeleton_text
from core.digest.rounds.base import Ctx, RoundOut

logger = logging.getLogger(__name__)


def run(ctx: Ctx) -> RoundOut:
    """① 记 —— 按**骨架**逐条填（切分不归它 —— 3b-2）。"""
    spec = ctx.enter("record")
    system = ctx.system_for(spec, domain=ctx.domain, chapter_count=len(ctx.chapters))
    user = ctx.sections_for(spec, [
        ("本段新增互动", ctx.timeline),
        ("本段骨架", _skeleton_text(ctx.result.segments) + "\n" + SKELETON_HINT),
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
    # ⭐ **按顺序对齐骨架** —— 位置与条数都归 R0（判据见 `_align_to_skeleton`）
    entries, gaps = _align_to_skeleton(entries, ctx.result.segments)
    # 索引 → 原文（T14）: parse 层拿不到事件流, 回填在这里做（对齐**之后**才解析）
    for ent in entries:
        _resolve_verbatim(ent, ctx.by_seq)
    reused: list[str] = []
    before = len(ctx.episode_ids)
    ctx.episode_ids, ctx.player_ids = _create_a_nodes(
        ctx.store, entries, ts=ctx.now_ts,
        event_seq=[ctx.interact_max], aff_at_encoding=ctx.aff_at_encoding,
        by_seq=ctx.by_seq, reused_out=reused)
    # ⭐ **`state=open` ⇒ 长成 note**（3b-3 / 2026-10-05 换判据）—— 用刚建出来的 id 当 `refs`
    # （切分权在 R0, 所以 note 的来源是**它自己那条切片**; 身份取"指向哪条 episode"⇒ 重跑不重复记）
    # ⚠️ **判重复复用的那条不算"新的"** —— 它的 note 上一段已经写过了（重跑幂等的第一道,
    # 节点面复用之后这道必须跟着生效, 否则 op 会再产一次、白写一条事件）
    new_eps = [e for e in ctx.episode_ids[before:] if e not in reused]
    keeper = _pinned_ops(ctx, gaps.get("orders") or [], new_eps)
    _note_items(ctx, entries, reused, gaps, keeper)
    return RoundOut.done()


def _align_to_skeleton(entries: list[dict], segments: list[dict]
                       ) -> tuple[list[dict], dict]:
    """把她的应答**按顺序**并到骨架上 —— 返回 `(要落节点的条目, 缺口账)`。

    ## 三条判据（都是"谁说了算"的问题）

    1. **位置不归她**: 条目自带 `span` / `event_seq` 的**一律不读**（契约层已经退役了
       那两个字段）。位置取 `segments[i]["seqs"]` —— 切分员算好的区间。
    2. **多了 ⇒ 截断 + 告警**: 骨架只有 N 条, 她给了 N+2 条 ⇒ 只收前 N 条。
       ⚠️ 多出来的那些**本来就没有位置**（没有第 N+1 条切片可挂）⇒ 收下也没法落节点。
       这条与 `episodes > MAX_EPISODES` 的老口径一致: 形状错**重试有用**, 所以先告警
       （下一段她会收敛）, 而不是拒整包把整段记忆丢掉。
    3. **少了 ⇒ 那几条切片没人填**: `drop` 掉的不算少（那是她的裁决）; **其余**算"漏填",
       记进 D1 台账（`items.no_pos` / `dropped`）—— 那一刻之后世上没有第二份记录。
       ⛔ 引擎**不替她补**（"没记"是她的裁决, 引擎补 = 把她没说的话写进她的记忆）;
       带 ⭐ 的那几条要不要兜底, 归 3b-3 的 note 那条线（`state=open` ⇒ 长成 note）。

    ⚠️ **"多写了" ⇒ 挂在最后一条切片上**（不丢!）: 一条切片不止能长一条记忆 ——
    她完全可能在一件事里同时写"发生了什么"和"这让我看清了什么"。硬截断会把那些
    **悄悄丢掉**, 而它们没有位置只是因为没有更多切片。⇒ 超出的**附在末条切片**上,
    并留一行 warning（可 grep: 多写了 = 契约没压住, 该在**切分**那头看）。
    ⛔ 反向（**少写**）没有兜底: 那几条切片就是没人填 —— 记进 D1 台账。
    """
    seg_count = len(segments)
    out: list[dict] = []
    orders: list[int] = []          # ⭐ 每条落节点的条目**对到第几条切片**（0 基）—— note 要用
    dropped: list[str] = []
    unfilled: list[str] = []
    for i, ent in enumerate(entries):
        j = min(i, seg_count - 1) if seg_count else i
        if ent.get("drop"):
            dropped.append(_brief(segments[j], j) if seg_count else f"#{i + 1}")
            continue
        seg = segments[j] if seg_count else None
        ent["seqs"] = list((seg or {}).get("seqs") or [])
        if not ent["seqs"]:
            # 切片自己没有位置（R0 的区间被契约层丢了）⇒ 落回段级指针, 并记账
            unfilled.append(_brief(seg or {}, j))
            ent.pop("seqs", None)
        orders.append(j)
        out.append(ent)
    if seg_count and len(entries) > seg_count:
        logger.warning("digest_record 多写了 %d 条（骨架只有 %d 条）—— 都挂在末条切片上: %s",
                       len(entries) - seg_count, seg_count,
                       [_brief(e, i) for i, e in enumerate(entries[seg_count:], seg_count)])
    # 她**漏填**的那几条（既没 drop、也没给行）
    for i, seg in enumerate(segments[len(entries):], len(entries)):
        unfilled.append(_brief(seg, i))
    if dropped or unfilled:
        logger.info("digest_record drop=%d 漏填=%d（漏填的几条没人记）: %s",
                    len(dropped), len(unfilled), unfilled[:6] or "-")
    return out, {"dropped": dropped, "unfilled": unfilled, "orders": orders}


def _brief(seg: dict, i: int) -> str:
    """切片的一句话标识（台账用）—— `#序号 摘要`。"""
    return f"#{i + 1} {seg.get('abstract') or '-'}"


def _pinned_ops(ctx: Ctx, orders: list[int], new_eps: list[str]) -> dict:
    """⭐ **`state=open` 的切片 ⇒ 一条 `note/add`**（3b-3）—— 返回缺口账。

    ## 三条判据

    1. **来源 = 那条切片自己的 episode**: `refs` 取**新**建出来的 episode id。
       切分权在 R0 ⇒ 约定挂在**它自己那件事**上, 不需要 LLM 指任何位置
       （这正是最初那个"实时记一笔拿不到地址"的问题的解法）。
    2. ⚠️ **`refs` 只收新节点**: 判重复而复用的那条不在 `new_eps` 里 —— 它的 note
       上一段已经写过了（重跑幂等的第二道）。
    3. ⛔ **她 drop 掉一条 `always`** ⇒ **收下她的裁决**, 但**记账**（返回 `lost_kept`）:
       "说过要一直带着的东西没被记住"不能是静默的。它走已有的 D1 台账那条通路
       （`digest_gap` 的 `items.dropped`）—— ⛔ 不发明新机制。
       ⛔ **也不替她补**: 引擎补 = 把她没说的话写进她的本子。

    ## 为什么不在这里做去重

    重跑幂等有**两道**, 都不在这个函数里:
      · **节点面**: `_create_a_nodes` 的 `_find_duplicate` 会复用旧节点 ⇒ 复用出来的
        不进 `new_eps` ⇒ 这里根本不会产 op（上面判据 2）;
      · **笔记面**: op 里带 **`src`**（= 它指向的那条 episode）, `fold` 见到
        "already 在本子上的条目里有一条 `refs` 含同一个 `src`" 就跳过
        （`notes.ALREADY_PINNED`）—— ⚠️ 拿 `refs` 而不是拿正文比:
        她两次可能把同一句话写得不一样, 而**指向哪条经历**是确定的。

    ## 形状

    `text` = 切片的 `abstract`（**原样**）: 契约要求 `always` 的那句就是
    "她带走的那句话"（"还欠着什么 + 她此刻对它的那点意思"）⇒ 不再二次加工。
    """
    if not orders:
        return {"lost_kept": []}
    lost_kept: list[str] = []
    # 切片序号 → 它长出来的 episode（`orders[i]` = 第 i 条条目对到第几条切片）
    ep_of: dict[int, str] = {}
    for pos, j in enumerate(orders):
        if pos < len(new_eps):
            ep_of.setdefault(j, new_eps[pos])
    for j, seg in enumerate(ctx.result.segments):
        # ⭐ 2026-10-05（L1 的过渡）: 判据从 `keep == "always"` 换成 **`state == "open"`
        # 且**没有 `id`**（那是"新建"; 带 `id` 的是"更正", 走 L7 的 `update` 那一路）。
        # ⚠️ 这两行是为了**不留窗口**: `keep` 已经从契约里拿掉, 不改这里就再没有 note 会被新建。
        if seg.get("state") != "open" or seg.get("id"):
            continue
        text = str(seg.get("abstract") or "").strip()
        ep = ep_of.get(j)
        if not (text and ep):
            # 没人填 / 契约层丢了区间 / 正文空 —— 那条约定的**唯一书面留存**没了 ⇒ 进账
            lost_kept.append(f"#{j + 1} {text or seg.get('abstract') or '-'}")
            continue
        ctx.result.notes_ops.append(
            add_op(text, [ep], due=str(seg.get("due") or ""), src=ep))
    if lost_kept:
        logger.warning("digest_record `state=open` 有 %d 条没长成 note（约定丢了）: %s",
                       len(lost_kept), lost_kept[:4])
    return {"lost_kept": lost_kept}


def _note_items(ctx: Ctx, entries: list[dict], reused: list[str],
                gaps: dict | None = None, keeper: dict | None = None) -> None:
    """D1 的**条目面**台账（`items`）—— 只有它**不可重算**。

    四半合成一行账:
      · `dropped` = R0 章收口丢掉的（`segment_collapsed`）+ 她 `drop` 的 +
        切片没位置的 + ⭐ **她 drop 掉/没填的 `state=open`**（3b-3: 约定丢了要看得见）;
      · `no_pos`  = 落回段级指针的条数;
      · `reused`  = 判重复而复用的 id。
    ⚠️ 声明在表里 record 的 `result_fields` ⇒ 整段回滚时由 `reset_result` 一起清掉
    （否则会出现"回滚了却留着一条缺口账"）。造行在 `pipeline` 的**提交块**（`_note_gap`）。
    """
    collapsed = list(getattr(ctx.result, "segment_collapsed", None) or [])
    gaps = gaps or {}
    unfilled = list(gaps.get("unfilled") or [])
    lost_kept = list((keeper or {}).get("lost_kept") or [])
    # `in` = 切分员**交了几件** = 活着的 + 被契约层当场丢的（丢的在 `segments` 里已不存在）
    n_in = (len(ctx.result.segments)
            + int(getattr(ctx.result, "segment_dropped", 0) or 0))
    ctx.result.record_gaps = {"items": {
        "in": n_in, "kept": len(entries),
        "no_pos": len(unfilled),
        "dropped": (collapsed + list(gaps.get("dropped") or []) + unfilled + lost_kept),
        "reused": reused}}
