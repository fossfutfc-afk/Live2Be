# -*- coding: utf-8 -*-
"""segment.py — **这一段是什么**（2026-09-29 从 `pipeline.py` 拆出）。

回答问题"哪些事件算这一段 / 属于哪一章 / 一条条目覆盖哪些事件"，全部**纯函数**
（只读事件列表，不碰 store、不调 LLM）:

| 函数 | 干什么 |
|---|---|
| `_segment_domain` | 段类型（bond/mmt）+ **每一章的分组**（从 marker 派生，不落库） |
| `_in_seqs` | 某条条目/切片声明的 seq 是否落在给定章块里 |
| `_expand_spans` | `span` 区间 → 区间内**全部**内容 seq（写进 **`seqs`**; ⭐ 早于 `_collapse_bond_episodes`） |
| `_seqs_of` | 条目/切片 → 它**已经展开好的** seq 集合（两种键名都认） |
| `_span_range` | 条目/切片 → `span` 区间（两端）或 `None` |
| `_coverage` | 认领/未认领/章内未覆盖（覆盖率那本日志的唯一算法） |
| `_collapse_bond_episodes` | **一章一条**（提示词没压住时的确定性兜底 + 告警 + 区间并回） |

⭐ **2026-09-29（N4d / 3b-1）: 这一族从 R1 搬到了 R0** —— 切分权归切分员之后，
"区间 → 图"是**对着切片**做的（`rounds/split.py` 的产出点），R1 不再参与。
搬的是调用点，不是形状: 下面几个函数的判据一条都没改（水位那两条铁律住在
`pipeline._next_watermark`，它只读 `node.event_seq` ⇒ **对展开发生在哪一轮完全透明**）。

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
    """条目/切片声明的 seq 是否落在给的那组块里（两种键名都认, 见 `_seqs_of`）。"""
    return any(s in seqs for s in _seqs_of(e))


def _expand_spans(entries: list[dict], seq_set: set[int]) -> tuple[list[int], int]:
    """⭐ `span` → 区间内**全部**内容 seq，**写进 `seqs`** —— 就地改这批字典。

    ⚠️ **不 pop `span`**（2026-09-29 / 3b-1 改）: 从前展开完就把它弹掉（怕
    `from_dict` 静默忽略未知字段）; 现在 `span` 是这条切片的**身份** ——
    R1 要照着区间号找到自己在填哪一件, 收口要靠它并区间, 台账要印它。
    ⇒ 展开的结果另存一个键（`seqs`）, 两者并存: **`span` 给人看, `seqs` 给引擎用**。

    ⚠️ **必须早于 `_collapse_bond_episodes`**: 那一章的归属判据 `_in_seqs` 靠
    "条目的 seq 与章块**相交**" —— 展开前只有两个端点, 章块夹在中间
    （span `[80, 100]` / 章 `86..97`）时**两个端点全在章外** ⇒ 那条会被误判成"不属于本章"。

    Returns: `(未认领的 seq 升序, 被 ≥2 条切片共享的 seq 数)`

    ⭐ **重叠如实报告、不裁**: 同一段事件本来就可以同时是两件事（真机 `m0015`
    「约老师来看苔藓」`[208..235]` 与 `m0016`「老师说我很重要」`[214..223]` **整段嵌套**;
    裁掉"先到先得"会让 `m0016` 丢掉它**唯一的位置证据**）。
    而"未认领"才是真病 —— 真机 218 条内容事件里 **70 条（32%）没进任何记忆**。
    ⭐ 3b-2 起切分契约要求**覆盖全部** ⇒ 未认领恒为 0 才是健康; 非 0 = 契约没压住。
    """
    counts: dict[int, int] = {}
    for ent in entries:
        span = ent.get("span")
        if span is None:
            # 旧形状（`event_seq` 逐点）/ 没给位置 —— 原样计入, **不展开**
            for s in ent.get("event_seq") or []:
                counts[s] = counts.get(s, 0) + 1
            continue
        lo, hi = int(span[0]), int(span[1])
        seqs = sorted(s for s in seq_set if lo <= s <= hi)
        if seqs:
            ent["seqs"] = seqs
            for s in seqs:
                counts[s] = counts.get(s, 0) + 1
    unclaimed = sorted(seq_set - set(counts))
    shared = sum(1 for n in counts.values() if n > 1)
    return unclaimed, shared


def _seqs_of(item: dict) -> list[int]:
    """条目/切片 → 它**已经展开好的** seq 集合 —— 两种键名都认, **不现算**。

    `seqs`（R0 展开的结果）优先; 退到 `event_seq`（R1 时代 / 契约层给的点集）。
    ⚠️ 故意**不读 `span`**: 读的是"展开了没有", 而"该展开成什么"是 `_expand_spans`
    的事（同一个事实两个算法 = 迟早不一致）。
    """
    return _seq_ints(item.get("seqs") or item.get("event_seq"))


def _span_range(item: dict) -> tuple[int, int] | None:
    """条目/切片声明的 `span` 区间（`None` = 没声明 / 形状坏）。

    ⚠️ 没有它时**退到 `seqs`/`event_seq` 的首尾** —— 收口并区间时那段也要算进去,
    否则"没有 span 的条目"会从章覆盖里漏出去。
    """
    span = item.get("span")
    if isinstance(span, (list, tuple)) and len(span) >= 2:
        try:
            return int(span[0]), int(span[1])
        except (TypeError, ValueError):
            return None
    seqs = _seqs_of(item)
    return (seqs[0], seqs[-1]) if seqs else None


def _coverage(entries: list[dict], seq_set: set[int], chapters: list[dict]
              ) -> tuple[list[int], list[int]]:
    """覆盖率那本账: `(未认领, 章内未覆盖)` —— **唯一的算法**（日志与台账共用）。

    ⚠️ **要在收口之后算**: 章块的区间并回会让"章内那几条"从"未认领"变成"已认领"
    ⇒ 拿收口**前**算的那个数去记日志, 就会与节点上的覆盖**对不上**（两种口径）。
    ⚠️ 章内未覆盖是一条**异常信号**（章边界是引擎已知的 ⇒ 章内不该漏）; MMT 碎聊的
    未认领是常态, 章的不是。它**可重算**（节点 `event_seq` + 章 marker 都在盘上）
    ⇒ 进日志, 不进账。
    """
    covered = {s for e in entries for s in _seqs_of(e)}
    unclaimed = sorted(set(seq_set) - covered)
    chapter_seqs = (frozenset().union(*[c["seqs"] for c in chapters])
                    if chapters else frozenset())
    return unclaimed, sorted(s for s in unclaimed if s in chapter_seqs)


def _brief(e: dict) -> str:
    """条目/切片的一句话标识（优先 `title`, 否则 `abstract` 前 12 字）—— 只给台账用。"""
    t = str(e.get("title") or e.get("abstract") or "").strip()
    return t or str(e.get("text") or "")[:12]


def _collapse_bond_episodes(entries: list[dict], chapters: list[dict], *,
                            dropped_out: list[dict] | None = None) -> list[dict]:
    """**按章**收口: 每一章只留 1 条 —— "一章一件事"的引擎侧兜底（⛔ 丢的是**切片**）。

    契约在 `contract/digest_registry._DOMAIN_CONTRACT`（提示词侧）；这里是
    **确定性兜底**: 提示词没压住时留一条, 其余丢弃, 并留一行 `WARNING`（可 grep）
    —— 免得契约被违反是**静默**的。

    ⚠️ **2026-09-29（3b-1）: 它吃的是 R0 的切片**, 不再是 R1 的条目 ——
    切分权归切分员之后, "一章切成了几件"是**切分违约**, 该在产出点当场收口。
    判据也跟着换: 切片的 `keep` 优先（`always` 是"往后要带着的", 最不该丢）,
    否则**跨度最长**的那条（它最可能是那一章的总结）。
    ⛔ **不再看 `significance`** —— R0 不打分（打分是 R1 的活, 而 R1 这时还没跑）。

    ⚠️ **逐章收口**, 不是"整段收口"（见 `_segment_domain` 的两条警告）:
    * 窗口常同时含 MomoTalk 聊天（真档实测 13 / 26 条）—— 那些切片**不属于任何章**,
      照常留着（把整段压成 1 条会把聊天里的记忆一起丢掉）;
    * 窗口还可能有**多章**（水位清空后必然）—— **每章各留 1 条**。

    `kind == "experience"`（玩家画像）不算 —— 它是 R1 的产物, 到这一步还不存在;
    这条判据留着是为了 `_create_a_nodes` 的旧路径（老调用方直接喂条目的场合）。

    为什么丢弃而不是合并文本: 合并是创作（要 LLM）, 引擎只做判定。

    ⭐ **章块的覆盖由引擎兜到整章**（D0, 2026-09-29 用户裁决）—— 保留那条的 seq 取
    **并集**（它声称的 ∪ 章的整块 ∪ **被丢那几条的区间**）。
    判据: 章的边界是**引擎已知的**（marker 派生）, 没有理由让她划、也没理由让她划漏 ——
    划窄了有两个后果: ① 章尾留在水位之上 ⇒ 下一段**重喂** ⇒ 而重喂的窗口里没有 `vn_enter`
    ⇒ `_segment_domain` 会把它当**孤儿章** ⇒ 可能重复记一条; ② 召回侧的
    `emo_shape` / `place` / `node.ts` 全从 `event_seq` 推 ⇒ 少的正是那一截。
    ⭐ 3b-1 新增: **丢掉的那几条的区间也并回保留那条** —— 收口只该决定"合成几件事",
    不该让**位置**跟着消失（宽度是引擎能算的, 正文合并要 LLM ⇒ 只并区间不碰文本）。
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
        if not group:
            continue
        keep = max(group, key=_chapter_pick)
        # 章的整块 + 被丢那几条的区间, 一起并进保留那条（位置不丢）
        merged = {*_seq_ints(seqs)}
        for e in group:
            rng = _span_range(e)
            if rng is not None:
                merged.update(s for s in seqs if rng[0] <= int(s) <= rng[1])
        keep["seqs"] = sorted({*_seqs_of(keep), *merged})
        if len(group) <= 1:
            continue
        logger.warning(
            "digest_split contract=bond chapter=%r segments=%d keep=%r（一章一件; 其余已丢。"
            "这行常出现 = 提示词没压住, 看切分轮的【本段类型】产出契约）",
            ch["title"] or "-", len(group), _brief(keep))
        if dropped_out is not None:
            # ⭐ D1: 丢掉的那几条**只在这一刻存在**（它们的 `abstract` 之后世上没有第二份）
            # ⇒ 记进账（`digest_gap` 的 `items.dropped`）。
            dropped_out.append({"chapter": ch["title"] or "-", "keep": _brief(keep),
                                "lost": [_brief(e) for e in group if e is not keep]})
        dropped |= {id(e) for e in group if e is not keep}
    return [e for e in entries if id(e) not in dropped]


def _chapter_pick(e: dict) -> tuple[int, int]:
    """一章里留哪一条的判据（**降序**, 取第一个最大）: `keep=always` 优先, 再看跨度。

    ⚠️ 跨度 = `span` 的宽度（不是"覆盖了多少 seq"）—— 后者会被"这一章里她只标了几个点"
    这种稀疏声明放大, 而"她划了多宽"才是"这条是不是整章的总结"的判据。
    """
    rng = _span_range(e)
    width = (rng[1] - rng[0]) if rng is not None else len(_seqs_of(e))
    return (1 if e.get("keep") == "always" else 0, width)


def _seq_ints(raw) -> list[int]:
    """`event_seq` 里能当 seq 的那些（坏值丢, 同 `_in_seqs` 的宽容口径）。"""
    out: list[int] = []
    for s in raw or []:
        try:
            out.append(int(s))
        except (TypeError, ValueError):
            continue
    return out
