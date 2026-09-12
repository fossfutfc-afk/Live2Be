# -*- coding: utf-8 -*-
"""回忆册路由（DESIGN_COLLECTION_BOOK.md）—— 书页 / 角色页 / 只读回放。

    GET /api/collection/book                    书页: 按白名单顺序的角色格（封面 collection.png）
    GET /api/collection/{cid}/chapters          角色页: 该角色**已确认结束**的章标题列表
    GET /api/collection/{cid}/{from_seq}        只读回放载荷（逐板 scene + 选项/当时的选择）

口径（作者 2026-09-12 拍板, 见设计稿 §1）:
    · 一格 = 一角色; 无 `portrait/collection.png` → **留白格**（仍占位, 顺序稳定）
    · 章 = 已结束的 bond story（`core.session.chapters` 派生）; 未完/中断/废弃的
      **连条目都不渲染**——后端也不返回（"渲染都不渲染"是数据口径, 不是前端过滤）
    · 只读回放 = 播完即停, 0 LLM, 不碰 BondState/不写事件流（`bond.chapter_replay`）

为什么全部从事件流派生、没有索引表: 见设计稿 §2（第二份真源必然漂移）。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.common.mmt_registry import load_mmt_registry
from core.parsing.dynamic_character_parser import CharacterLoader
from core.session.chapters import chapter_index
from webgui import bond
from webgui.routers.bond import _resolve_scene
from webgui.routers.mmt import collection_cover

router = APIRouter()

ROOT = Path(__file__).resolve().parent.parent.parent
CHAR_ROOT = ROOT / "config" / "characters"

#: 书页版式（设计稿 §1: 两半页 × 3 行 4 列 = 24 格一跨页）——前端也读这份, 单一真源
BOOK_ROWS = 3
BOOK_COLS = 4


def _events(cid: str) -> list:
    """该角色在当前世界线的事件流（读失败 → 空; 宁缺勿错: 册子少一格不报错）。"""
    store = bond._store()
    try:
        sid = store.meta(cid).session_id or ""
        return store.events(cid, sid)
    except Exception:                                    # noqa: BLE001 — 无该角色线
        return []


def _role(cid: str) -> dict:
    """角色显示信息（名字 + 社团）; 取不到 → 回落 id。"""
    try:
        info = bond._role_info(cid) or {}
    except Exception:                                    # noqa: BLE001
        info = {}
    return {"name": str(info.get("name") or cid), "club": str(info.get("club") or "")}


@router.get("/api/collection/book")
async def collection_book() -> dict:
    """书页数据: `{rows, cols, cells: [{char_id, name, cover, has_cover}]}`。

    顺序 = `mmt_registry.toml` 白名单顺序（作者维护, 与 MMT 列表同源）。
    **不含章的扫描**——格子上只要封面; 章列表点进去再取（开书零成本）。
    """
    registry = load_mmt_registry()
    try:
        names = CharacterLoader(CHAR_ROOT).list_characters()
    except Exception:                                    # noqa: BLE001 — 角色卡缺失降级
        names = {}
    cells = []
    for entry in registry:
        cid = str(entry.get("id") or "")
        if not cid:
            continue
        cover = ""
        try:
            cover = collection_cover(cid)
        except Exception:                                # noqa: BLE001 — 资产缺失留白
            cover = ""
        cells.append({
            "char_id": cid,
            "name": names.get(cid, cid),
            "cover": cover,
            "has_cover": bool(cover),
        })
    return {"rows": BOOK_ROWS, "cols": BOOK_COLS, "cells": cells,
            "registry_empty": not cells}


@router.get("/api/collection/{char_id}/chapters")
async def collection_chapters(char_id: str) -> dict:
    """角色页: 已结束的章（标题 + 板数 + 是否有纪念图）, 按事件流序。"""
    info = _role(char_id)
    chapters = chapter_index(_events(char_id))
    return {"char_id": char_id, "name": info["name"], "club": info["club"],
            "chapters": [{
                "from_seq": ch["from_seq"],
                "title": ch["title"],
                "boards": ch["boards"],
                "images": ch["images"],
                "memorial_url": (ch["images"][-1] if ch["images"] else ""),
            } for ch in chapters]}


@router.get("/api/collection/{char_id}/{from_seq}")
async def collection_replay(char_id: str, from_seq: int) -> dict:
    """只读回放载荷（0 LLM）: 该章逐板 scene（经 `_resolve_scene` 附渲染信息）。

    章不存在 / 未结束 / 属于废弃段 → 404（后端与"只渲染已结束章"同一判据）。
    """
    try:
        ch = bond.chapter_replay(char_id, from_seq)
    except Exception as e:                               # noqa: BLE001 — 派生异常转 404
        raise HTTPException(status_code=404, detail=f"回忆册读取失败: {e}")
    if not ch:
        raise HTTPException(status_code=404, detail="没有这一章（或它还没有结束）")
    for s in ch["scenes"]:
        s["scene"] = _resolve_scene(s.get("scene"), char_id)
    info = _role(char_id)
    return {"char_id": char_id, "name": info["name"], "club": info["club"], **ch}
