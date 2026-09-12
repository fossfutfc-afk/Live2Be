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
    M_MEMORIAL_IMAGE,
    M_VN_ABANDON,
    TYPE_BOND,
)
from core.session.maintenance import abandoned_ranges, attempt_spans

#: 章区间的"无上界"哨兵（未关段用——本模块只收已关闭的章, 保留给通用性）
_OPEN_END = 1 << 60


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
    """
    spans = attempt_spans(events)
    ranges = abandoned_ranges(events)
    chapters = [s for s in spans
                if s["completed"] and s["scenes"] > 0 and not _abandoned(s, ranges)]
    if not chapters:
        return []
    bonds = [e for e in events if getattr(e, "type", None) == TYPE_BOND]
    images = _memorial_urls(events, spans)
    out: list[dict] = []
    for s in chapters:
        lo, hi = s["enter_seq"], (s["close_seq"] or _OPEN_END)
        scenes = [_scene_of(e) for e in bonds if lo <= e.seq <= hi]
        out.append({
            "from_seq": lo,
            "to_seq": s["close_seq"],
            "title": s["title"],
            "boards": len(scenes),
            "images": images.get(lo, []),
            "scenes": scenes,
        })
    return out


def chapter_index(events: list) -> list[dict]:
    """角色页用的轻量索引（去掉 scenes 正文——列表不背正文）。"""
    return [{k: v for k, v in ch.items() if k != "scenes"}
            for ch in replayable_chapters(events)]
