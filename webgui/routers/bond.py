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


#: 无意图/占位背景的展示兜底优先级（语义 id; neutral 等无资产占位 → 选真实场景）。
#: 只作用于展示层（background_url）, 不改事件/导演状态——防"开场无锚点+占位无资产
#: = 纯黑"（2026-09-08 实机问题 2）; 锚点句到达后前端仍会在该段切真实意图。
_BG_FALLBACK_PRIORITY = [
    "class_room", "campus", "school_ground", "school_rooftop",
    "gehenna_street", "park", "beachside",
]


def _fallback_bg_url() -> str | None:
    """真实背景兜底 URL（None = 资产库全空, 前端保持原样）。"""
    try:
        cat = _catalog()
        scenes = set(cat.background_scenes())
    except Exception:                                # noqa: BLE001 — 资产缺失降级
        return None
    for sid in [*_BG_FALLBACK_PRIORITY, *sorted(scenes)]:
        if sid in scenes:
            media = cat.background(sid)
            if media is not None:
                try:
                    rel = media.path.relative_to(cat.assets_root)
                    return f"/assets/{rel.as_posix()}"
                except Exception:                    # noqa: BLE001
                    return None
    return None


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


def _speaker_name_map(char_id: str) -> dict[str, str]:
    """记录流 v2: 说话人取值 → 显示名（最小形态——前端只负责把名字行画出来）。

    角色 id → 人设 display_name; `sensei` → 老师; `narrator` → 空串
    （旁白不加名字行）。取不到人设 → 回落 id（宁缺勿错）。
    """
    from contract import CHARACTER_NARRATOR, SPEAKER_SENSEI_LABEL
    try:
        who = bond._role_info(char_id).get("name") or char_id
    except Exception:                                # noqa: BLE001 — 取不到用 id
        who = char_id
    return {char_id: who, "sensei": SPEAKER_SENSEI_LABEL,
            CHARACTER_NARRATOR: ""}


def _resolve_scene(scene: dict | None, char_id: str) -> dict | None:
    """场景 dict 附带前端渲染信息:
    background_url — scene_id → 静态文件 URL（无背景 → 保持 None, 黑屏余韵）
    paragraphs[].fx — emotion → 特效符号列表（EffectResolver 单源: 角色表→全局表→空;
                      前端 VN 立绘头顶浮现——官方冒爱心/音符/惊叹等 UI 层特效）。
    paragraphs[].speaker_name — 记录流 v2 说话人显示名（最小形态: 只有名字行,
                      样式/气泡留给前端; 旁白为空串 → 不加名字行）。
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
        elif not scene.get("is_end"):
            # 占位/缺资产（如 neutral）→ 展示兜底真实场景（防纯黑; 锚点段仍会切）
            fb = _fallback_bg_url()
            if fb:
                scene["background_url"] = fb
    elif not scene.get("is_end"):
        fb = _fallback_bg_url()
        if fb:
            scene["background_url"] = fb
    paras = scene.get("paragraphs")
    if isinstance(paras, list):
        _names = _speaker_name_map(char_id) if scene.get("records") else {}
        for p in paras:
            if isinstance(p, dict):
                sp = p.get("speaker")
                if _names and isinstance(sp, str) and sp.strip():
                    p["speaker_name"] = _names.get(sp.strip(), sp.strip())
                e = p.get("emotion")
                if isinstance(e, str) and e.strip():
                    fx = _fx_resolver(char_id).effects_for(e)
                    if fx:
                        p["fx"] = fx
                # place 锚点背景（DESIGN_BOND_CONTRACT_V2 P3b-2）: 换场句的背景
                # 静态资源（表键 → **资产 scene_id** → catalog; 查不到 → 保持上一背景）
                pid = p.get("place")
                if isinstance(pid, str) and pid.strip():
                    url = _place_bg_url(pid.strip())
                    if url:
                        p["place_bg"] = url
    return scene


def _place_bg_url(key: str) -> str | None:
    """地点键 → 背景 URL（C5, 2026-09-19）。

    表键（`classroom`/`moderncafe`/`view_sky`）**不是**资产 scene_id
    （`class_room`/`modern_cafe`/`view_sky`）——表里 `files` 的文件名才是。
    所以先经 `load_table().scene_id()` 翻一次，再走 catalog（老口径）。
    任一步失败 → None（调用方保持上一背景, 宁缺勿错）。
    """
    try:
        cat = _catalog()
    except Exception:                                # noqa: BLE001 — 资产缺失降级
        return None
    sid = key
    try:
        from core.media.place_table import load_table
        t = load_table()
        if t:
            sid = t.scene_id(key) or key
    except Exception:                                # noqa: BLE001 — 表缺失退回老口径
        sid = key
    for cand in (sid, key):
        media = cat.background(cand)
        if media is not None:
            try:
                return f"/assets/{media.path.relative_to(cat.assets_root).as_posix()}"
            except Exception:                        # noqa: BLE001
                return None
    return None


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
    """进入羁绊剧情（幂等: 已有进行中的剧情 → 返回现状）。

    场景已就绪的路径（回放 / 预热命中 / adopt 就绪 / 续玩）会带 `scene`——与
    `/api/bond/status` 同通道过 `_resolve_scene`（否则前端拿到的段落缺
    speaker_name/background_url/fx, 首屏无背景无名字行）。
    """
    try:
        r = bond.bond_start(body.char_id, body.session_id)
        if isinstance(r.get("scene"), dict):
            r["scene"] = _resolve_scene(r["scene"], body.char_id)
        return r
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
    """玩家裁决 → 下一场（后台生成, 轮询 status 取场景）。

    注: 裁决直返（branch=True, 记录流 v2 的"就地物化展示"）也带 scene——与 status
    同通道过 `_resolve_scene`（否则前端拿到的段落缺 speaker_name/fx/background_url,
    老师那句会没名字行）。
    """
    try:
        r = bond.bond_turn(body.char_id, body.session_id, body.text)
        if isinstance(r.get("scene"), dict):
            r["scene"] = _resolve_scene(r["scene"], body.char_id)
        return r
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


@router.get("/api/bond/replay")
async def bond_replay(char_id: str, session_id: str = "") -> dict:
    """回放接口（纯读, 2026-09-07）: 会话内已记录羁绊剧情——按 vn_enter 分段,
    每段逐场 scene（带 input/picked）; 场景经 _resolve_scene 附渲染信息
    （background_url/fx, 与 live status 同通道）。消费方: 回放 UI / 中断前缀回放。
    """
    try:
        attempts = bond.replay_attempts(char_id, session_id)
        for at in attempts:
            for s in at["scenes"]:
                s["scene"] = _resolve_scene(s.get("scene"), char_id)
        return {"attempts": attempts}
    except Exception as e:                     # noqa: BLE001 — 回放异常转 HTTP
        raise HTTPException(status_code=500, detail=f"bond replay 失败: {e}")


@router.post("/api/bond/finish")
async def bond_finish(body: BondFinishIn) -> dict:
    """剧情终结收尾（wrapup + digest 后台执行）。"""
    try:
        return bond.bond_finish(body.char_id, body.session_id)
    except Exception as e:                     # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"bond finish 失败: {e}")
