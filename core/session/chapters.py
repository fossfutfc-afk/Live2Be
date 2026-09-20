# -*- coding: utf-8 -*-
"""回忆册（DESIGN_COLLECTION_BOOK.md）— 事件流 → 可回放章节列表（纯派生, 0 LLM）。

口径（2026-09-12 作者拍板）:
    · **章 = `vn_enter`…`vn_exit` 区间**——分段边界真源 = `maintenance.attempt_spans`
      （维护工具同一份实现: `vn_abandon` 关闭的段 close_kind='abandon' → 不是章）。
    · **只收"确认结束"的章**（`vn_exit.payload.completed == True`）: 未完 / 中断 /
      废弃的**连条目都不渲染**。理由: 未完章的正文还会继续长, 渲染它等于把**可变**
      内容放进册子; 回忆册承诺的是"已经结束、不会再变的记忆"——这也是 append-only
      语义下唯一能保证"回放内容 = 当时看到的内容"的判据。
    · 无正文（bond 场景数 == 0）的章不渲染（空壳重启段）。
    · **纪念图归属**: 先看**最近的前置 `memorial_enter`**（那才是"哪块板触发的图"）——
      它落在某章内 → 图归该章; 它落在章前的空档（预热板）→ 归紧随其后的那一章
      （预热先出图, 决策 #40）。没有前置 `memorial_enter` 时退回区间判据: 图落在章
      区间内 → 该章; 落在 `vn_enter` 之前 → 紧随其后的章; 无归属 = **孤儿**, 不显示。
      为什么不能只按区间判: 图生成要 ~26s, 纪念又多在本章末尾——**图常常在本章
      `vn_exit` 之后才落盘**; 只按区间判会把这张"晚到的图"错挂到下一章去。

为什么没有索引表: 本模块是**纯函数**, 开书时从事件流派生一次即可（真实规模下是
毫秒级）; 落盘索引会是第二份真相, 且必然漂移（章会被 vn_abandon 废弃、图异步后到、
写表与章结束不原子）。升级路线见设计稿 §2。

消费方: `webgui/routers/collection.py`（书页 / 角色页 / 只读回放）。
"""
from __future__ import annotations

from core.session.events import (
    M_MEMORIAL_ENTER,
    M_MEMORIAL_EXIT,
    M_MEMORIAL_IMAGE,
    M_SESSION_END,
    M_VN_ABANDON,
    M_VN_EXIT,
    TYPE_BOND,
)
from core.session.maintenance import abandoned_ranges, attempt_spans

#: 章区间的"无上界"哨兵（未关段用——本模块只收已关闭的章, 保留给通用性）
_OPEN_END = 1 << 60

#: 闭合一个纪念窗口的 marker（v2: 引擎在**下一块解析成功**时补 `memorial_exit`;
#: 章在窗口内结束 → 由 `vn_exit`/`session_end` 闭合, 与 `session_status` 同一规则）
_WINDOW_CLOSERS = (M_MEMORIAL_EXIT, M_VN_EXIT, M_SESSION_END)


def _scene_of(event) -> dict:
    """bond 事件 payload → 回放场景项（input/picked 摘出来单放, 其余即渲染字段）。"""
    payload = event.payload or {}
    return {
        "seq": event.seq,
        "input": str(payload.get("input") or ""),
        "picked": payload.get("picked"),
        "scene": {k: v for k, v in payload.items() if k not in ("input", "picked")},
    }


def _holding(spans: list[dict], seq: int) -> dict | None:
    """seq 落在哪个章区间内（不在任何区间 → None）。"""
    return next((s for s in spans
                 if s["enter_seq"] <= seq <= (s["close_seq"] or _OPEN_END)), None)


def _next_span(spans: list[dict], seq: int) -> dict | None:
    """seq 之后最近开的新章（无 → None）。"""
    return next((s for s in spans if s["enter_seq"] > seq), None)


def _memorial_urls(events: list, spans: list[dict]) -> dict[int, list[str]]:
    """纪念图 → 归属章的 `enter_seq`（见模块 docstring 的归属规则）。"""
    out: dict[int, list[str]] = {}
    anchors = [e.seq for e in events
               if e.is_marker and e.subtype == M_MEMORIAL_ENTER]
    abandons = [e.seq for e in events if e.is_marker and e.subtype == M_VN_ABANDON]
    for m in events:
        if not (m.is_marker and m.subtype == M_MEMORIAL_IMAGE):
            continue
        url = str((m.payload or {}).get("url") or "").strip()
        if not url:
            continue
        # ① 触发它的那块板（最近的前置 memorial_enter）决定归属
        anchor = next((a for a in reversed(anchors) if a < m.seq), None)
        owner = _holding(spans, anchor) if anchor is not None else None
        if owner is None and anchor is not None:
            owner = _next_span(spans, anchor)      # 预热板: 章前触发 → 归下一章
            if owner is not None and any(anchor < a < owner["enter_seq"]
                                         for a in abandons):
                continue                           # 中间夹废弃 → 那是废弃章的图
        # ② 没有板锚点（v1 档/图先于板落盘）→ 退回区间判据
        if owner is None and anchor is None:
            owner = _holding(spans, m.seq) or _next_span(spans, m.seq)
            if owner is not None and m.seq < owner["enter_seq"] and any(
                    m.seq < a < owner["enter_seq"] for a in abandons):
                continue
        if owner is None:
            continue                               # 孤儿（无章可挂）→ 不显示
        out.setdefault(owner["enter_seq"], []).append(url)
    return out


def _memorial_boards(events: list) -> dict[int, dict]:
    """**板级**纪念归属（P1①, 2026-09-20）: `{bond 事件 seq: {"img": url}}`。

    只读回放要和 live 看到的一样——live 的纪念态是"进窗口即隐藏立绘 + 清空普通背景
    + 图淡入, 窗口内每板都保持", 所以这里得算出**每一板在不在窗口里**以及**哪一板
    该亮哪张图**。

    三条判据都从事件流直接读得出, **不加新字段**:

    | 要什么 | 怎么算 |
    |---|---|
    | **窗口** | `memorial_enter` … 其后第一条 `memorial_exit`/`vn_exit`/`session_end`。v2 的区间 = "到本块块尾", 引擎在**下一块解析成功**时补 exit ⇒ 事件流里就是这一对（★ 所以"块尾"不需要额外信息） |
    | **触发板** | 见下面 `_trigger_board`——**不是**"marker 之前最后一条 bond 事件"（那句话曾写在这里, 是错的: `_log_scene_meta` 在板**落地**时写 marker, 而 `_log_scene` 在玩家**裁决/推进/收尾**时才写板正文 ⇒ 真机形状是 **marker 在前、板在后**（seq 21 marker → seq 23 板）, 按那句话判会挂到上一板）。实现认"**离 marker 最近且带纪念标记的板**", 并同时兼容预热/草稿的两种落地顺序 |
    | **图归哪板** | 图 marker 认**最近的前置 `memorial_enter`**（图晚到 26s, 常常晚于本章 `vn_exit`——按 seq 区间判会错挂到下一章, 与章级 `_memorial_urls` 同一条纪律） |

    **v1 档 / 图先于板落盘**（没有前置 `memorial_enter`）→ 这里不管, 由
    `replayable_chapters` 用章级判据挂到"带 `memorial`/`memorial_prompt` 的板"上。
    """
    bonds = [e for e in events if getattr(e, "type", None) == TYPE_BOND]

    def _memorial_flag(e) -> bool:
        p = e.payload or {}
        return bool(p.get("memorial") or p.get("memorial_prompt"))

    def _trigger_board(anchor: int) -> int | None:
        """哪一板触发了这个窗口（→ 图挂它）。

        **不能只看 marker 之前**: 两条落地顺序都真实存在——
        · 正常落地: 先写板、紧接着写 marker ⇒ 触发板在 marker **之前**;
        · **预热/草稿**路径（决策 #40）: marker 先写、板随后才落, 而且可能在
          `vn_enter` **之后**（B 层冒烟实测: `memorial_enter` seq4 → `vn_enter` seq7 →
          板 seq8）。
        ⇒ 认**离 marker 最近的、带纪念标记的那一板**（`memorial`/`memorial_prompt`）;
        都拿不到标记时, 退回"最近的一块板"（先看前、再看后）。
        """
        flagged = [b.seq for b in bonds if _memorial_flag(b)]
        if flagged:
            return min(flagged, key=lambda s: (abs(s - anchor), s > anchor))
        before = [b.seq for b in bonds if b.seq < anchor]
        after = [b.seq for b in bonds if b.seq > anchor]
        return (before[-1] if before else None) or (after[0] if after else None)

    anchors = [e.seq for e in events
               if e.is_marker and e.subtype == M_MEMORIAL_ENTER]
    windows: list[dict] = []
    for a in anchors:
        closer = next((e for e in events
                       if e.is_marker and e.subtype in _WINDOW_CLOSERS and e.seq > a),
                      None)
        end = closer.seq if closer is not None else _OPEN_END
        board = _trigger_board(a)
        members = [b.seq for b in bonds if a <= b.seq < end]
        # ⚠️ **收窗那一板不算在窗内**（2026-09-20 实测出来的 off-by-one）:
        # 引擎在"**新一块的第一板**落地"时才补 `memorial_exit`（`_log_scene_meta` 里
        # 先写板、紧接着写 marker）, 而 live 的复位发生在**新块解析成功**那一刻
        # ⇒ 那块板在 live 里已经是普通板。判据: 闭合 marker 是 `memorial_exit`
        # **且**它紧跟在最后一条 bond 事件之后（中间没有别的 marker）, 且那块板不是
        # 触发板 —— 三者同时成立才剔。`vn_exit`/`session_end` 收窗（章在窗口内结束）
        # 不动: 那时窗口内的板都是同块的, live 里全在纪念态。
        if (closer is not None and closer.subtype == M_MEMORIAL_EXIT and members):
            last = members[-1]
            between = [e.seq for e in events if last < e.seq < closer.seq]
            if last != board and not between:
                members.pop()
        windows.append({"enter": a, "board": board, "members": members})
    out: dict[int, dict] = {}
    for w in windows:                                   # 窗口内每板都算"在纪念里"
        for seq in w["members"]:
            out.setdefault(seq, {"img": ""})
    for m in events:                                    # 图 → 触发板
        if not (m.is_marker and m.subtype == M_MEMORIAL_IMAGE):
            continue
        url = str((m.payload or {}).get("url") or "").strip()
        anchor = next((a for a in reversed(anchors) if a < m.seq), None)
        if not (url and anchor):
            continue                                    # v1 档 → 留给章级回落
        w = next((x for x in windows if x["enter"] == anchor), None)
        if w is None or w["board"] is None:
            continue
        out.setdefault(w["board"], {"img": ""})["img"] = url
    return out


def _abandoned(span: dict, ranges: list[tuple[int, int]]) -> bool:
    """章区间与废弃区间是否相交（相交 = 该章视为未发生）。

    实战里 `vn_abandon` 只关**未收尾**的段（`abandon_open_attempts`/`supersede`）,
    所以收尾章一般不会命中; 这里是显式兜底——口径上"废弃 = 未发生", 册子不显示。
    """
    lo, hi = span["enter_seq"], (span["close_seq"] or _OPEN_END)
    return any(not (hi < a or lo > b) for a, b in ranges)


def replayable_chapters(events: list) -> list[dict]:
    """事件流 → **已确认结束**的章列表（事件流序; 纯读, 幂等）。

    返回 `[{from_seq, to_seq, title, boards, images, scenes}]`:
        from_seq  vn_enter 的 seq（**章的稳定 id**——前端按它进只读回放）
        to_seq    vn_exit 的 seq
        title     vn_enter.payload.chapter_title（空串 = 旧档/异常, 由消费方兜底文案）
        boards    章内 bond 板数（== len(scenes)）
        images    本章纪念图 URL（按出现序; 空 = 无图 → 前端降级纯 VN 回放）
        scenes    [{seq, input, picked, scene}]——与现网回放同构的逐板数据
                  ⚠️ 板在纪念窗口内时 `scene` 多带 `in_memorial: true`, 触发板另带
                  `memorial_img`（P1①: 只读回放据此隐藏立绘/清背景/淡入图,
                  与 live 的 `syncMemorial` 同一套键）
    """
    spans = attempt_spans(events)
    ranges = abandoned_ranges(events)
    chapters = [s for s in spans
                if s["completed"] and s["scenes"] > 0 and not _abandoned(s, ranges)]
    if not chapters:
        return []
    bonds = [e for e in events if getattr(e, "type", None) == TYPE_BOND]
    images = _memorial_urls(events, spans)
    per_board = _memorial_boards(events)
    out: list[dict] = []
    for s in chapters:
        lo, hi = s["enter_seq"], (s["close_seq"] or _OPEN_END)
        scenes = [_scene_of(e) for e in bonds if lo <= e.seq <= hi]
        _attach_memorial(scenes, per_board, images.get(lo, []))
        out.append({
            "from_seq": lo,
            "to_seq": s["close_seq"],
            "title": s["title"],
            "boards": len(scenes),
            "images": images.get(lo, []),
            "scenes": scenes,
        })
    return out


def _attach_memorial(scenes: list[dict], per_board: dict[int, dict],
                     chapter_images: list[str]) -> None:
    """把纪念态写进**板**（原地改 `scenes[i]["scene"]`）。

    * 窗口内的板 → `in_memorial: true`; 触发板 → 再带 `memorial_img`
    * **章级回落**: 这一章有图、但**没挂到任何板**上（图先于板落盘 / 旧契约 /
      **预热先出图**）→ 把图挂到"带 `memorial`/`memorial_prompt` 的板"上
      （宁缺勿错: 没有这种板就不挂, 章级缩略图照旧还在）

    ⚠️⚠️ **2026-09-20 修（真机报障"回放里也放不出来"）**: 回落的判据原先是
    `if scene.get("in_memorial"): continue` —— 只补"**不在**窗口里的板"。但真机
    这一局恰好是"**图在预热时就生成（早于 `vn_enter`）, 而板在窗口里**"：
    * 板级：`memorial_enter`(21) → 收尾板(23, `memorial=True`) 在窗口内 ⇒ 拿到
      `in_memorial: true`;
    * 图级：图 marker(12) **前面没有任何 `memorial_enter`** ⇒ 挂不到板
      （`_memorial_boards` 的纪律: 图认"最近的前置 `memorial_enter`"）,
      于是它只能走本章的章级回落 —— 而回落**正好跳过了这块板**。
    ⇒ 结果 `in_memorial=true` 但 `memorial_img` 为空 = 前端那一支"清背景 + 什么都不
      淡入" = **黑屏**（live 与回放同一个症状）。
    修法: 回落只看"**这块板还没有图**", 不管它是不是已经在窗口里。
    """
    attached = {url for info in per_board.values() if (url := info.get("img"))}
    for item in scenes:
        scene = item.get("scene")
        if not isinstance(scene, dict):
            continue
        info = per_board.get(item.get("seq"))
        if info is not None:
            scene["in_memorial"] = True
            if info.get("img"):
                scene["memorial_img"] = info["img"]
    spare = [u for u in chapter_images if u and u not in attached]
    if not spare:
        return
    for item in scenes:
        scene = item.get("scene")
        if not isinstance(scene, dict):
            continue
        if scene.get("memorial_img"):                # 已有图 → 不动（不再看 in_memorial）
            continue
        if not (scene.get("memorial") or scene.get("memorial_prompt")):
            continue
        scene["in_memorial"] = True
        scene["memorial_img"] = spare.pop(0)
        if not spare:
            return


def chapter_index(events: list) -> list[dict]:
    """角色页用的轻量索引（去掉 scenes 正文——列表不背正文）。"""
    return [{k: v for k, v in ch.items() if k != "scenes"}
            for ch in replayable_chapters(events)]
