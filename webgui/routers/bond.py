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

import logging
from pathlib import Path

logger = logging.getLogger("live2be.webgui")

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
    missing_asset  — **有明确地点但素材找不到**时的回执 `{key, scene_id?}`——
                     此时 background_url 给**黑屏 `black`**, 前端 `console.error`
                     + 一次 `alert`（用户 2026-09-19 裁决: 宁可黑屏让人看见）
    paragraphs[].fx — emotion → 特效符号列表（EffectResolver 单源: 角色表→全局表→空;
                      前端 VN 立绘头顶浮现——官方冒爱心/音符/惊叹等 UI 层特效）。
    paragraphs[].speaker_name — 记录流 v2 说话人显示名（最小形态: 只有名字行,
                      样式/气泡留给前端; 旁白为空串 → 不加名字行）。
    """
    if not scene:
        return None
    scene = dict(scene)
    # ① **有明确地点** → 先按地点键取图（这一条与导演的"保持上一场"无关,
    #    所以缺图不会被"上一场恰好有图"掩盖掉）
    place = scene.get("place")
    if isinstance(place, str) and place.strip():
        key = place.strip()
        url, st = _place_bg(key, _place_asset_of(scene))
        if st != "ok":
            # 缺素材 / 旧名 → 黑屏 + 回执（`_missing_info` 会带上改名解释）
            info = _missing_info(key)
            scene["missing_asset"] = info
            scene["background_url"] = _black_bg_url()
            logger.error("[place][MISSING_ASSET] key=%r 查不到背景素材 → 黑屏占位%s",
                         key, f"（{info.get('message')}）" if info.get("message") else "")
            return _finish_scene(scene, char_id)     # 已定背景, 段落特效照挂
    # ② 没有地点（或地点有图）→ 走老口径
    sid = scene.get("background")
    if sid:
        url = _catalog_url(sid)
        if url:
            scene["background_url"] = url
        elif not scene.get("is_end"):
            # 占位/缺资产（如 neutral 冷启动）→ 展示兜底真实场景（防纯黑; 锚点段仍会切）
            fb = _fallback_bg_url()
            if fb:
                scene["background_url"] = fb
    elif not scene.get("is_end"):
        fb = _fallback_bg_url()
        if fb:
            scene["background_url"] = fb
    return _finish_scene(scene, char_id)


def _finish_scene(scene: dict, char_id: str) -> dict:
    """段落级附带信息（名字行 / 特效 / 锚点背景）——`_resolve_scene` 的收尾半段。"""
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
                # 静态资源（表键 → **资产 scene_id** → catalog）
                pid = p.get("place")
                if isinstance(pid, str) and pid.strip():
                    pa = p.get("place_asset")
                    asset = pa.strip() if isinstance(pa, str) and pa.strip() else ""
                    url, st = _place_bg(pid.strip(), asset)
                    if st != "ok":
                        # 缺图（或旧名）→ **黑屏 + 报出**（不再静默保持上一背景）
                        p["place_bg"] = _black_bg_url()
                        p["missing_asset"] = _missing_info(pid.strip())
                        logger.error("[place][MISSING_ASSET] 锚点 key=%r → 黑屏%s",
                                     pid.strip(),
                                     f"（{p['missing_asset'].get('message')}）"
                                     if p["missing_asset"].get("message") else "")
                    elif url:
                        p["place_bg"] = url
    return scene


def _catalog_url(sid: str) -> str | None:
    """`scene_id` → `/assets/...` URL（查不到 → None）。"""
    try:
        cat = _catalog()
        media = cat.background(sid)
        if media is None:
            return None
        return f"/assets/{media.path.relative_to(cat.assets_root).as_posix()}"
    except Exception:                                # noqa: BLE001 — 资产缺失降级
        return None


#: 素材缺失时的占位背景（用户 2026-09-19 裁决: **黑屏 + 报出来**）
_MISSING_PLACEHOLDER = "black"


def _black_bg_url() -> str | None:
    """`black` 的 URL（素材缺失占位）; 连它都没有 → None（真没辙了）。"""
    return _catalog_url(_MISSING_PLACEHOLDER) or _fallback_bg_url()


def _missing_info(key: str) -> dict:
    """缺素材回执（板级与锚点共用）——**能解释就解释**。

    PL6（2026-09-19）: 先问改名台账（`data/worlds/*/place_renames.jsonl`）。
    命中 → `message` = *"key 'X' 已改名为 'Y'"*（前端 alert 直接用这句）;
    没命中 → 只给 `key`，前端回落成笼统的"素材未找到"。
    """
    info: dict = {"key": key}
    try:
        from core.media import place_renames
        why = place_renames.explain(key)
        if why:
            info["message"] = why
            info["renamed_to"] = place_renames.resolve(key)
    except Exception:                                # noqa: BLE001 — 没台账就笼统报
        pass
    return info


def _place_bg(key: str, asset: str = "") -> tuple[str | None, str]:
    """地点键（+ 第二遍选的图）→ `(URL, 状态)`。状态 = `"ok"` / `"missing"` / `"renamed"`。

    ## 素材缺失怎么办（用户 2026-09-19 裁决）

    > *"假如发现资源库里没有这张图，就用黑屏 black，且 alert/console.log
    > 素材未找到即可。"*

    此前是**静默换成别的图**（`_fallback_bg_url()` → `class_room`）—— 症状就是
    真机那 20/20 板"每次 VN 都在显示教室"：**看起来正常，其实错了**。
    现在改成**黑屏 + 明确报出**（`missing_asset` 随场景下发, 前端 `console.error`
    + 一次 `alert`）——**宁可黑屏让人看见, 不要拿一张错的图糊过去**。

    为什么会缺: `place` 键**不许改名**（用户 2026-09-19: *"key 是不可改的"*）,
    所以缺只可能来自**素材没进库/被移走**或**旧事件里的键在当前表里不存在**。
    ⇒ PL6（2026-09-19）补上第二种的解释: 查不到时**先问改名台账**
    （`core/media/place_renames.py`）, 命中就返回 `"renamed"` + 人话原因
    （*"key 'X' 已改名为 'Y'"*）—— 那条黑屏 alert 于是直接告诉人该去改什么。

    `asset` = 第二遍选中的**具体文件**（`place_asset`）; 非法/不属于这个键 → 回落默认图。
    """
    url = _table_bg_url(key, asset) or _catalog_url(_catalog_key(key))
    if url:
        return (url, "ok")
    try:
        from core.media import place_renames
        if place_renames.resolve(key):
            return (None, "renamed")
    except Exception:                                # noqa: BLE001 — 台账缺失不影响取图
        pass
    return (None, "missing")


def _place_asset_of(scene: dict) -> str:
    """场景里的 `place_asset`（第二遍选的图; 旧事件没有 → 空 = 默认图）。"""
    v = scene.get("place_asset")
    return v.strip() if isinstance(v, str) and v.strip() else ""


def _catalog_key(key: str) -> str:
    """地点键 → 资产 scene_id（先查表, 查不到原样交给 catalog 再试一次）。"""
    try:
        from core.media.place_table import load_table
        t = load_table()
        if t:
            return t.scene_id(key) or key
    except Exception:                                # noqa: BLE001 — 表缺失退回老口径
        pass
    return key


def _table_bg_url(key: str, asset: str = "") -> str | None:
    """走**表**取图（`place_asset` 优先, 否则该键的默认图）——查不到 → None。

    为什么优先走表而不是 catalog: 表的 `files` 路径是**逐字准确**的
    （实测 194/194 张时刻图都在盘上）, 而 `catalog.background(scene_id, variant)`
    会漏 6 张——`BG_ClassRoom2_Night.jpg` 派生成 `class_room_2` 这个**另一个
    scene_id**, 与键的 `class_room` 对不上（2026-09-19 探针）。
    """
    from core import paths
    try:
        from core.media.place_table import load_table
        t = load_table()
        if not t:
            return None
        rel = (asset or "").strip()
        if rel:
            # 第二遍选的图: 必须在**这个键自己的候选**里（防串键/防路径穿越）
            e = t.get(key)
            allowed = {r for r, _ in (e.image_candidates() if e else [])}
            rel = rel if rel in allowed else ""
        if not rel:
            rel = t.get(key).asset() if t.get(key) else None
        if not rel or rel.startswith(("/", "\\")) or ".." in rel:
            return None
        if not (paths.BACKGROUND_DIR / rel).is_file():
            return None
        return f"/assets/background/{rel}"
    except Exception:                                # noqa: BLE001 — 缺表/坏表退回 catalog
        return None


def _place_bg_url(key: str) -> str | None:
    """兼容包装: 只要 URL（缺失 → None）。新代码请用 `_place_bg()` 拿状态。"""
    return _place_bg(key)[0]


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
