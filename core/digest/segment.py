# -*- coding: utf-8 -*-
"""segment.py — **这一段是什么**（2026-09-29 从 `pipeline.py` 拆出）。

回答问题"哪些事件算这一段 / 属于哪一章 / 一条条目覆盖哪些事件"，全部**纯函数**
（只读事件列表，不碰 store、不调 LLM）:

| 函数 | 干什么 |
|---|---|
| `_segment_domain` | 段类型（bond/mmt）+ **每一章的分组**（从 marker 派生，不落库） |
| `_in_seqs` | 某条条目声明的 `event_seq` 是否落在给定章块里 |
| `_expand_spans` | `span` 区间 → 区间内**全部**内容 seq（⭐ 必须早于 `_collapse_bond_episodes`） |
| `_collapse_bond_episodes` | **一章一条**（提示词没压住时的确定性兜底 + 告警） |

⚠️ 拆出来顺带把"L1 的那些洞"（未认领/被丢弃的台账出口）圈进了同一个文件。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _segment_domain(events: list) -> tuple[str, list[dict], frozenset]:
    """本段类型、**每一章的分组**、章块并集（从 marker 与事件类型派生, 不落库）。

    用户原话: *"离散的是 mmt，但 bond story 不应该连续吗"* ⇒ **粒度跟着"作者单位"走**:
    一章羁绊剧情 → **恰好 1 条**; MMT 碎聊 → 0~5 条（**需要切分的是它**）。

    ⚠️ **窗口是"混的"—— 实测真档**（2026-09-20）: haruka 的窗口里 **13 条 MMT 聊天 +
    5 块羁绊剧情**; mutsuki 是 **26 + 13**。所以不能"整段按一个契约"。

    ⚠️⚠️ **窗口里还可能有"多章"** —— 水位被清 / 重跑时**必然**如此。
    所以"一章一条"必须**按章分组**收口; 拿全窗口的 bond 块当一个章, 会把两章压成一条。

    Returns: `(domain, chapters, bond_seqs)`
        domain: `"bond"`（窗口里有 `vn_enter`）/ `"mmt"`
        chapters: `[{"title": str, "seqs": frozenset[int]}]` —— **一章一块**
            （`vn_enter` … `vn_exit` 之间的 bond 事件）; 不在任何章里的 bond 块
            自成一组（旧档/异常, 标题为空）
        bond_seqs: 全部章块的并集（"这条条目属不属于某一章"的粗判用）
    """
    from core.session.events import M_VN_ENTER, M_VN_EXIT
    chapters: list[dict] = []
    cur: dict | None = None
    orphan: set = set()
    for e in events:
        if getattr(e, "is_marker", False):
            if e.subtype == M_VN_ENTER:
                cur = {"title": str((getattr(e, "payload", None) or {})
                                    .get("chapter_title") or "").strip(),
                       "seqs": set()}
                chapters.append(cur)
            elif e.subtype == M_VN_EXIT:
                cur = None
            continue
        if getattr(e, "type", "") == "bond":
            (cur["seqs"] if cur is not None else orphan).add(e.seq)
    if orphan:
        chapters.append({"title": "", "seqs": orphan})
    chapters = [{"title": c["title"], "seqs": frozenset(c["seqs"])} for c in chapters]
    union = (frozenset().union(*[c["seqs"] for c in chapters]) if chapters
             else frozenset())
    return ("bond" if chapters else "mmt"), chapters, union


def _in_seqs(e: dict, seqs: frozenset) -> bool:
    """条目声明的 `event_seq` 是否落在给的那组块里。"""
    return any(int(s) in seqs for s in (e.get("event_seq") or [])
               if isinstance(s, (int, str)) and str(s).lstrip("-").isdigit())


def _expand_spans(entries: list[dict], seq_set: set[int]) -> tuple[list[int], int]:
    """⭐ `span` → 区间内**全部**内容 seq（**N3**, 2026-09-29）—— 就地改写成 `event_seq`。

    ⚠️ **必须 `pop` 掉 `span`**: `_create_a_nodes` 走
    `make_node("episode", **{k: v for k, v in ent.items() if k != "kind"})` ——
    留在条目里的 `span` 会被 `from_dict` **静默忽略**（这个项目最恨的静默 no-op;
    `about_hint` 当年也是为这个专门 `pop` 的 —— 它 2026-09-29 已退役）。

    ⚠️ **必须在 `_collapse_bond_episodes` 之前跑**: 那一章的归属判据 `_in_seqs` 靠
    "条目的 `event_seq` 与章块的**相交**" —— 展开前只有两个端点, 章块夹在中间
    （span `[80, 100]` / 章 `86..97`）时**两个端点全在章外** ⇒ 那条会被误判成"不属于本章"。

    Returns: `(未认领的 seq 升序, 被 ≥2 条 episode 共享的 seq 数)`

    ⭐ **重叠如实报告、不裁**: 同一段事件本来就可以同时是两件事（真机 `m0015`
    「约老师来看苔藓」`[208..235]` 与 `m0016`「老师说我很重要」`[214..223]` **整段嵌套**;
    裁掉"先到先得"会让 `m0016` 丢掉它**唯一的位置证据**）。
    而"未认领"才是真病 —— 真机 218 条内容事件里 **70 条（32%）没进任何记忆**。
    """
    counts: dict[int, int] = {}
    for ent in entries:
        span = ent.pop("span", None)
        if span is None:
            # 旧形状（`event_seq` 逐点）或没给位置 —— 原样计入, **不展开**
            for s in ent.get("event_seq") or []:
                counts[s] = counts.get(s, 0) + 1
            continue
        lo, hi = int(span[0]), int(span[1])
        seqs = sorted(s for s in seq_set if lo <= s <= hi)
        if seqs:
            ent["event_seq"] = seqs
            for s in seqs:
                counts[s] = counts.get(s, 0) + 1
    unclaimed = sorted(seq_set - set(counts))
    shared = sum(1 for n in counts.values() if n > 1)
    return unclaimed, shared


def _brief(e: dict) -> str:
    """条目的一句话标识（优先 `title`, 否则正文前 12 字）—— 只给台账用。"""
    t = str(e.get("title") or "").strip()
    return t or str(e.get("text") or "")[:12]


def _collapse_bond_episodes(entries: list[dict], chapters: list[dict], *,
                            dropped_out: list[dict] | None = None) -> list[dict]:
    """**按章**收口: 每一章的 episode 只留 1 条 —— "一章一个 episode"的引擎侧兜底。

    契约在 `contract/digest_registry._DOMAIN_CONTRACT`（提示词侧）；这里是
    **确定性兜底**: 提示词没压住时留 `significance` 最高的那条, 其余丢弃, 并留一行
    `WARNING`（可 grep）—— 免得契约被违反是**静默**的。

    ⚠️ **逐章收口**, 不是"整段收口"（见 `_segment_domain` 的两条警告）:
    * 窗口常同时含 MomoTalk 聊天（真档实测 13 / 26 条）—— 那些条目**不属于任何章**,
      照 0~5 条留着（把整段压成 1 条会把聊天里的记忆一起丢掉）;
    * 窗口还可能有**多章**（水位清空后必然）—— **每章各留 1 条**。

    `experience`（玩家画像）不算 episode。为什么丢弃而不是合并文本: 合并是创作（要 LLM）,
    引擎只做判定; 而"一章一条"的前提是那条总结**本来就该覆盖全章**。
    """
    if not chapters:
        return entries
    dropped: set[int] = set()
    for ch in chapters:
        seqs = ch["seqs"]
        if not seqs:
            continue
        group = [e for e in entries
                 if e.get("kind") != "experience" and _in_seqs(e, seqs)]
        if len(group) <= 1:
            continue
        keep = max(group, key=lambda e: float(e.get("significance") or 0.0))
        logger.warning(
            "digest_record contract=bond chapter=%r entries=%d keep=%r（一章一条; 其余已丢。"
            "这行常出现 = 提示词没压住, 看 Round A 的【本段类型】产出契约）",
            ch["title"] or "-", len(group), _brief(keep))
        if dropped_out is not None:
            # ⭐ D1: 丢掉的那几条**只在这一刻存在**（它们的正文之后世上没有第二份）
            # ⇒ 记进账（`digest_gap` 的 `items.dropped`）。
            dropped_out.append({"chapter": ch["title"] or "-", "keep": _brief(keep),
                                "lost": [_brief(e) for e in group if e is not keep]})
        dropped |= {id(e) for e in group if e is not keep}
    return [e for e in entries if id(e) not in dropped]
