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

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.media.catalog import MediaCatalog
from renderer.effects import EffectResolver
from webgui import bond

router = APIRouter()

# 背景查库（懒单例——MediaCatalog 构造扫背景 ~百 ms）
_BG_CATALOG: MediaCatalog | None = None
# 特效解算器（per 角色懒缓存——角色表 assets/illustration/{char}/effects.yml + 全局表）
_FX_RESOLVERS: dict[str, EffectResolver] = {}


def _catalog() -> MediaCatalog:
    global _BG_CATALOG
    if _BG_CATALOG is None:
        _BG_CATALOG = MediaCatalog()
    return _BG_CATALOG


def _fx_resolver(char_id: str) -> EffectResolver:
    global _FX_RESOLVERS
    r = _FX_RESOLVERS.get(char_id)
    if r is None:
        r = EffectResolver(Path("assets/illustration") / char_id)
        _FX_RESOLVERS[char_id] = r
    return r


def warm_render(char_id: str) -> None:
    """预热渲染依赖（P2, EXEC_BOND_LATENCY §5#3）: MediaCatalog（构造一次
    ~百 ms）+ 角色特效表——移出首帧 status 轮询路径, 首个场景解析不再现构造。

    幂等（模块级单例）; 资产缺失/损坏 → 静默跳过（宁缺勿错——渲染链本就
    有各自降级）。由 webgui/bond.py 在进入剧情（含预热）时懒调用。
    """
    try:
        _catalog()
    except Exception:                                # noqa: BLE001 — 资产缺失降级
        return
    try:
        _fx_resolver(char_id)
    except Exception:                                # noqa: BLE001 — 角色无特效表降级
        pass


def _resolve_scene(scene: dict | None, char_id: str) -> dict | None:
    """场景 dict 附带前端渲染信息:
    background_url — scene_id → 静态文件 URL（无背景 → 保持 None, 黑屏余韵）
    paragraphs[].fx — emotion → 特效符号列表（EffectResolver 单源: 角色表→全局表→空;
                      前端 VN 立绘头顶浮现——官方冒爱心/音符/惊叹等 UI 层特效）。
    """
    if not scene:
        return None
    scene = dict(scene)
    sid = scene.get("background")
    if sid:
        media = _catalog().background(sid)
        if media is not None:
            rel = media.path.relative_to(_catalog().assets_root)
            scene["background_url"] = f"/assets/{rel.as_posix()}"
    paras = scene.get("paragraphs")
    if isinstance(paras, list):
        for p in paras:
            if isinstance(p, dict):
                e = p.get("emotion")
                if isinstance(e, str) and e.strip():
                    fx = _fx_resolver(char_id).effects_for(e)
                    if fx:
                        p["fx"] = fx
    return scene


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


@router.post("/api/bond/demo")
async def bond_demo(body: BondStartIn) -> dict:
    """演示模式: 预设剧本驱动（不调 LLM——前端 VN 体验/联调用）。"""
    try:
        return bond.bond_start_demo(body.char_id, body.session_id)
    except Exception as e:                     # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"bond demo 失败: {e}")


@router.post("/api/bond/turn")
async def bond_turn(body: BondTurnIn) -> dict:
    """玩家裁决 → 下一场（后台生成, 轮询 status 取场景）。"""
    try:
        return bond.bond_turn(body.char_id, body.session_id, body.text)
    except Exception as e:                     # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"bond turn 失败: {e}")


@router.get("/api/bond/status")
async def bond_status(char_id: str, session_id: str) -> dict:
    """轮询生成状态 + 最新场景（附带 background_url / 段落 fx 供前端渲染）。"""
    try:
        st = bond.bond_status(char_id, session_id)
        st["scene"] = _resolve_scene(st.get("scene"), char_id)
        return st
    except Exception as e:                     # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"bond status 失败: {e}")


@router.post("/api/bond/finish")
async def bond_finish(body: BondFinishIn) -> dict:
    """剧情终结收尾（wrapup + digest 后台执行）。"""
    try:
        return bond.bond_finish(body.char_id, body.session_id)
    except Exception as e:                     # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"bond finish 失败: {e}")
