# -*- coding: utf-8 -*-
"""Bond 路由 — 羁绊剧情驱动端点（webgui/bond.py 状态机）。

POST /api/bond/start   进入剧情（构造引擎 + 后台生成首场）→ {accepted, busy}
POST /api/bond/turn    玩家裁决（选项/自由输入）→ 补录 + 后台生成下一场 → {accepted, busy}
GET  /api/bond/status  轮询 → {busy, round, scene, error, completed}
POST /api/bond/finish  终结收尾（补录 + vn_exit + session_end + wrapup + digest）→ {completed}

前端流程:
    mmt events_after 收到 bond_story:True → POST start → 轮询 status 直到
    busy=False 且 scene 就绪 → 渲染场景（背景/立绘/打字机/选项）→ 玩家裁决
    POST turn → 轮询下一场 → is_end → POST finish → 回 MMT（轮询 events_after
    拉到 wrapup 收尾气泡）。

场景幂等: 前端按 status.round 去重（同一 round 只渲染一次）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from webgui import bond

router = APIRouter()


class BondStartIn(BaseModel):
    char_id: str
    session_id: str


class BondTurnIn(BaseModel):
    char_id: str
    session_id: str
    text: str


class BondFinishIn(BaseModel):
    char_id: str
    session_id: str


@router.post("/api/bond/start")
async def bond_start(body: BondStartIn) -> dict:
    """进入羁绊剧情（幂等: 已有进行中的剧情 → 返回现状）。"""
    try:
        return bond.bond_start(body.char_id, body.session_id)
    except Exception as e:                     # noqa: BLE001 — 驱动异常转 HTTP 错误
        raise HTTPException(status_code=500, detail=f"bond start 失败: {e}")


@router.post("/api/bond/turn")
async def bond_turn(body: BondTurnIn) -> dict:
    """玩家裁决 → 下一场（后台生成, 轮询 status 取场景）。"""
    try:
        return bond.bond_turn(body.char_id, body.session_id, body.text)
    except Exception as e:                     # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"bond turn 失败: {e}")


@router.get("/api/bond/status")
async def bond_status(char_id: str, session_id: str) -> dict:
    """轮询生成状态 + 最新场景。"""
    try:
        return bond.bond_status(char_id, session_id)
    except Exception as e:                     # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"bond status 失败: {e}")


@router.post("/api/bond/finish")
async def bond_finish(body: BondFinishIn) -> dict:
    """剧情终结收尾（wrapup + digest 后台执行）。"""
    try:
        return bond.bond_finish(body.char_id, body.session_id)
    except Exception as e:                     # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"bond finish 失败: {e}")
