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

from core.brain.notes import PINNED_TAG, add_op, close_op, update_op
from core.digest.episodes import _create_a_nodes, _resolve_verbatim, _spanless_nodes
from core.digest.material import SKELETON_HINT, _skeleton_rows, _skeleton_text
from core.digest.material import existing_entities_line
from core.digest.rounds.base import Ctx, RoundOut

logger = logging.getLogger(__name__)


def run(ctx: Ctx) -> RoundOut:
    """① 记 —— 按**骨架**逐条填（切分不归它 —— 3b-2）。

    ⭐ **没有能填的行 ⇒ 只跳过那次 LLM 调用, 引擎照走**（L5+L7, 2026-10-05）:
    一段里可能只有 `span: null` 那种"没有那一刻"的行（正文是 R0 给的, R1 没活干）,
    但**引擎这一轮照样有事**: 落那条无区间经历 + 产 `close` / `update` 的 note 操作。
    ⇒ 早退的位置在**调用**那一层, 不在函数开头（否则账目整批不落地）。
    """
    spec = ctx.enter("record")
    rows = _skeleton_rows(ctx.result.segments)
    entries: list[dict] = []
    gaps: dict = {}
    reused: list[str] = []
    new_eps: list[str] = []
    if rows:
        system = ctx.system_for(spec, domain=ctx.domain, chapter_count=len(ctx.chapters))
        user = ctx.sections_for(spec, [
            ("本段新增互动", ctx.timeline),
            ("本段骨架", _skeleton_text(ctx.result.segments) + "\n" + SKELETON_HINT),
            ("本章标题", " / ".join(c["title"] for c in ctx.chapters if c["title"])),  # 多章都列; 空 → 跳过
            ("画面记忆", "\n".join(f"- {v}" for v in ctx.visuals)),
            # ⭐ E1b（2026-10-08）: 写 `#entity:` 之前先看**已有的对象**（名字 + 别名）——
            # 防她自己造新叫法（造了引擎就认不出 ⇒ 同一个人被重复建）
            ("已有的对象", existing_entities_line(ctx.store, texts=[ctx.timeline])),
            ("角色人设（锚点）", ctx.character_prompt),
            ("本段情绪标尺", ctx.emotion_scale),
        ])
        entries, resp = ctx.call(
            spec, system, user,
            parse_fn=ctx.parse_for(spec, seq_set=ctx.seq_set))
        if entries is None:
            return RoundOut.failed()
        # ⭐ **M1（2026-10-05）: 好感的原始 resp 存在这一轮** —— "这一段她对老师的亲近感
        # 净变化"与 `significance` 同族（都是打分）, 而打分归 R1。
        # ⚠️ 从这一格取它（不是在返回值里搬）: `RoundOut` 只说"成没成"。
        ctx.resp_a = resp
        # ⭐ **按顺序对齐骨架** —— 位置与条数都归 R0（判据见 `_align_to_skeleton`）
        entries, gaps = _align_to_skeleton(entries, ctx.result.segments)
        # 索引 → 原文（T14）: parse 层拿不到事件流, 回填在这里做（对齐**之后**才解析）
        for ent in entries:
            _resolve_verbatim(ent, ctx.by_seq)
        before = len(ctx.episode_ids)
        strangers: list[str] = []       # ⭐ E1: `#entity:` 里解析不到的名字（= 还没建的人）
        ctx.episode_ids, ctx.player_ids = _create_a_nodes(
            ctx.store, entries, ts=ctx.now_ts,
            event_seq=[ctx.interact_max], aff_at_encoding=ctx.aff_at_encoding,
            by_seq=ctx.by_seq, reused_out=reused, strangers_out=strangers)
        if strangers:
            # 观测账（可 grep）: 这些名字留在 tag 里, 等认人那一轮把人建出来再补边
            logger.info("digest_record strangers=%d（还没建的人）: %s",
                        len(strangers), strangers)
        # ⚠️ **判重复复用的那条不算"新的"** —— 它的 note 上一段已经写过了（重跑幂等的
        # 第一道; 节点面复用之后这道必须跟着生效, 否则 op 会再产一次、白写一条事件）
        new_eps = [e for e in ctx.episode_ids[before:] if e not in reused]
    else:
        ctx.log_skip(spec)              # 日志文案来自表里 `skip` 格（这一轮**不调 LLM**）
    # ⭐ **L7 ①: 无区间那一行 ⇒ 一条"没有那一刻"的经历**（正文 = R0 的 `abstract`,
    #    不过 R1; 它**也是**本段的经历 ⇒ 进 `episode_ids`, R2/R3 照常接得上）
    note_state = ctx.store.notes_state(ctx.events)
    spanless = _spanless_nodes(ctx.store, ctx.result.segments, note_state=note_state,
                               now_ts=ctx.now_ts, interact_max=ctx.interact_max,
                               reused_out=reused)
    # ⚠️ 它们接在 R1 那批后面（顺序 = 契约顺序）; ⛔ **别让它们进水位** ——
    # 那格 `event_seq=[interact_max]` 是**账的指针**, 不是"这一段被覆盖了"
    # （`pipeline._next_watermark` 的 `skip_ids`）。
    ctx.episode_ids = [*ctx.episode_ids, *spanless]
    ctx.result.spanless_ids = list(spanless)
    # ⭐ **L7 ②: 按 R0 那张表产 note 操作**（`add` / `update` / `close` 三种 + `#pinned`）
    keeper = _ledger_ops(ctx, gaps.get("orders") or [], new_eps, note_state)
    _note_items(ctx, entries, reused, gaps, keeper, spanless=spanless)
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

    ⭐ **L5（2026-10-05）: 对位走 `_skeleton_rows`** —— 骨架**只印有区间的行**
    （无区间那一行没有事件可写, 正文就是 R0 的 `abstract`）。⇒ 这里也必须照那份清单对位,
    ⚠️ 但 `orders` 里存的仍是**原始下标**（`_pinned_ops` 拿它去 `ctx.result.segments` 里
    数"第几条是 `open`"）—— 过滤只改"第 i 条条目 → 哪条切片", 不改切片的身份。
    """
    rows = _skeleton_rows(segments)
    row_count = len(rows)
    out: list[dict] = []
    orders: list[int] = []          # ⭐ 每条落节点的条目**对到第几条切片**（0 基, **原始**下标）—— note 要用
    dropped: list[str] = []
    unfilled: list[str] = []
    for i, ent in enumerate(entries):
        j, seg = rows[min(i, row_count - 1)] if row_count else (i, None)
        if ent.get("drop"):
            dropped.append(_brief(seg, j) if seg is not None else f"#{i + 1}")
            continue
        ent["seqs"] = list((seg or {}).get("seqs") or [])
        if not ent["seqs"]:
            # 切片自己没有位置（R0 的区间被契约层丢了）⇒ 落回段级指针, 并记账
            unfilled.append(_brief(seg or {}, j))
            ent.pop("seqs", None)
        orders.append(j)
        out.append(ent)
    if row_count and len(entries) > row_count:
        logger.warning("digest_record 多写了 %d 条（骨架只有 %d 条）—— 都挂在末条切片上: %s",
                       len(entries) - row_count, row_count,
                       [_brief(e, i) for i, e in enumerate(entries[row_count:], row_count)])
    # 她**漏填**的那几条（既没 drop、也没给行）
    for i, seg in rows[len(entries):]:
        unfilled.append(_brief(seg, i))
    if dropped or unfilled:
        logger.info("digest_record drop=%d 漏填=%d（漏填的几条没人记）: %s",
                    len(dropped), len(unfilled), unfilled[:6] or "-")
    return out, {"dropped": dropped, "unfilled": unfilled, "orders": orders}


def _brief(seg: dict, i: int) -> str:
    """切片的一句话标识（台账用）—— `#序号 摘要`。"""
    return f"#{i + 1} {seg.get('abstract') or '-'}"


def _ledger_ops(ctx: Ctx, orders: list[int], new_eps: list[str], note_state) -> dict:
    """⭐⭐ **按 R0 那张表产 note 操作**（L7, 2026-10-05）—— `add` / `update` / `close` 三种。

    这是"切片即账目"落到**本子**上的那一笔: 行的 `state` 说什么, 这里就写什么。

    | 那一行 | 产出 | 依据 |
    |---|---|---|
    | `state=open`（**无** `id`） | **`add`** —— `text` = 那一行 `abstract`（原样）· `refs` = **它自己那条 episode** · `due` 透传 | §2.1 |
    | `state=open`（**有** `id`） | **`update`** —— 只改 `due` / `text`, 带 `before`/`after`; ⛔ **一样都没变 ⇒ 不写** | §1.1b |
    | `state=close`（有区间 / `span: null`） | **`close`** —— 划掉即移除（三种结局一律） | §2.2 |

    三条纪律（每一条都有代价, 别顺手改）:

    1. **出生地址 = 那条切片自己的 episode**（`orders` 把"第 i 条条目"对到"第几条切片"）。
       ⚠️ 判重复而复用的那条**不在 `new_eps` 里** —— 它的 note 上一段已经写过了
       （重跑幂等的第二道: op 里那个 `src` = `ALREADY_PINNED` 去重键）。
    2. ⛔ **她 drop 掉 / 漏填一条 `open`** ⇒ **收下她的裁决 + 记账**（`lost_kept`）:
       "说过要带着的东西没被记住"不能是静默的（走 D1 台账, 不发明新机制）。
    3. **`update` 的 `before == after` ⇒ 不写 op**（§1.1b）: 崩溃窗口重跑时那一行是白跑的,
       **不能假装变了**。判据只比 `due`/`text` 两样（行契约只允许改这两样）。

    ⭐ 顺带把 **`#pinned`** 打在**出生那条** episode 上（§4.5: 语义 = "这是她随身带着过的
    一件事"）—— 建节点时就能写, **不走 revise 通道**; 了结那一条不打。

    ## 重跑幂等有**两道**, 都不在这个函数里

      · **节点面**: `_create_a_nodes` 的 `_find_duplicate` 会复用旧节点 ⇒ 复用出来的
        不进 `new_eps` ⇒ 这里根本不会产 op（上面纪律 1）;
      · **笔记面**: op 里带 **`src`**（= 它指向的那条 episode）, `fold` 见到
        "本子上已经有一条 `refs` 含同一个 `src`" 就跳过（`notes.ALREADY_PINNED`）——
        ⚠️ 拿 `refs` 而不是拿正文比: 她两次可能把同一句话写得不一样, 而**指向哪条经历**是确定的。
    """
    lost_kept: list[str] = []
    no_change: list[str] = []
    # 切片序号 → 它长出来的 episode（`orders[i]` = 第 i 条条目对到第几条切片）
    ep_of: dict[int, str] = {}
    for pos, j in enumerate(orders):
        if pos < len(new_eps):
            ep_of.setdefault(j, new_eps[pos])
    open_items = {str(it.id): it for it in getattr(note_state, "pinned", []) or []}
    for j, seg in enumerate(ctx.result.segments):
        state = seg.get("state")
        if state not in ("open", "close"):
            continue
        nid = str(seg.get("id") or "").strip()
        text = str(seg.get("abstract") or "").strip()
        if state == "close":
            # 了结: 只有 id 一件事 —— 账平与"有没有留下正文"无关（她 drop 掉那一条也照划）
            if nid:
                ctx.result.notes_ops.append(close_op(nid))
            continue
        if nid:
            # **更正**（§1.1b）: "后来才知道的日期"那条主路径 —— 只改 due / text
            item = open_items.get(nid)
            if item is None:                  # 闭集由契约层保证; 这里只是兜底
                continue
            before = {"text": item.text, "due": str(item.due or "")}
            after = {"text": text or item.text,
                     "due": str(seg.get("due") or "").strip() or str(item.due or "")}
            if before == after:
                no_change.append(f"{nid}（这一行什么都没改）")
                continue
            ctx.result.notes_ops.append(
                update_op(nid, due=after["due"] or None, text=after["text"] or None,
                          before=before, after=after))
            continue
        ep = ep_of.get(j)
        if not (text and ep):
            # 没人填 / 契约层丢了区间 / 正文空 —— 那条约定的**唯一书面留存**没了 ⇒ 进账
            lost_kept.append(f"#{j + 1} {text or seg.get('abstract') or '-'}")
            continue
        ctx.result.notes_ops.append(
            add_op(text, [ep], due=str(seg.get("due") or ""), src=ep))
        _mark_pinned(ctx, ep)
    if lost_kept:
        logger.warning("digest_record `state=open` 有 %d 条没长成 note（约定丢了）: %s",
                       len(lost_kept), lost_kept[:4])
    if no_change:
        logger.info("digest_record 更正行什么都没改（不写 op）: %s", no_change[:4])
    return {"lost_kept": lost_kept}


def _mark_pinned(ctx: Ctx, ep_id: str) -> None:
    """给**出生那条** episode 打 `#pinned`（§4.5）—— 幂等: 已经在就不重复加。"""
    node = ctx.store.get(ep_id)
    if node is None or PINNED_TAG in (node.tags or []):
        return
    ctx.store.update(ep_id, {"tags": [*(node.tags or []), PINNED_TAG]})


def _note_items(ctx: Ctx, entries: list[dict], reused: list[str],
                gaps: dict | None = None, keeper: dict | None = None,
                spanless: list[str] | None = None) -> None:
    """D1 的**条目面**台账（`items`）—— 只有它**不可重算**。

    四半合成一行账:
      · `dropped` = R0 章收口丢掉的（`segment_collapsed`）+ 她 `drop` 的 +
        切片没位置的 + ⭐ **她 drop 掉/没填的 `state=open`**（3b-3: 约定丢了要看得见）;
      · `no_pos`  = 落回段级指针的条数;
      · `reused`  = 判重复而复用的 id;
      · `spanless` = ⭐ **无区间那几条**（它们**不经 R1** —— 正文就是 R0 的 `abstract`,
        所以既不算 kept 也不算漏填; 记一格是为了让这本账加得起来）。
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
        "reused": reused, "spanless": len(spanless or [])}}
