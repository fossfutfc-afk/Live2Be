# -*- coding: utf-8 -*-
"""MMT 路由（成员列表 + 头像 + 好感 + 排序）。

角色来源 = mmt_registry.toml 白名单（作者维护）——只显示白名单内的角色, 按白名单
顺序; 头像 = **每个角色各取自己的** `{cid}/{outfit}/portrait/`（无则 diff 兜底,
见 `_find_avatar`）。
好感 = 事件流真源累计（load_affection_from_events）→ per-char 聚合（best_affection,
"你和她最好的那一次"）; 排序 = core/mmt/ranking.py（最新活跃 / 好感, ?sort= 切换）。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.affection import load_affection_from_events
from core.common.mmt_registry import load_mmt_registry
from core.mmt.ranking import SORT_MODES, best_affection, sort_characters
from core.parsing.dynamic_character_parser import CharacterLoader
from core.session import SessionStore
from webgui import chat

router = APIRouter()

ROOT = Path(__file__).resolve().parent.parent.parent
CHAR_ROOT = ROOT / "config" / "characters"
ILLUS_ROOT = ROOT / "assets" / "illustration"

#: MMT 列表头像来源（2026-09-12 定稿——`{cid}/{outfit}/` 标准外观格式）:
#:   1) `portrait/*.png` —— **该外观的 GUI 头像**（必有; 首选约定名 `collection.png`）
#:   2) `diff/*Idle*.png` —— 兜底（标准格式里 diff/ 可选, 没有 portrait/ 属资产缺件;
#:      宁可显一张裁圆的立绘也别让角色从列表里消失）
#: 历史: 曾有一层 `mmt/*.png`（BA 圆头像帧）与"全角色共用一张"的误改, 均已退役。
#: 标准外观格式 = emotions.yml + portrait/ + spine/（必有）; diff/ 可选（OC 无 spine 动画）。
_PORTRAIT_GLOB = "*.png"
_PORTRAIT_PREFERRED = "collection.png"      # 作者约定名（BA collection 半身像）
_IDLE_GLOB = "*[Ii]dle*.png"


def _asset_url(p: Path) -> str:
    """资产绝对路径 → 前端 URL（挂载点 = /assets/illustration/）。"""
    return f"/assets/illustration/{p.relative_to(ILLUS_ROOT).as_posix()}"


def _pick_portrait(d: Path) -> Path | None:
    """`portrait/` 里的头像图: 首选 `collection.png`（约定名）, 否则按名序第一张。"""
    if not d.is_dir():
        return None
    files = sorted(d.glob(_PORTRAIT_GLOB))
    if not files:
        return None
    return next((f for f in files if f.name == _PORTRAIT_PREFERRED), files[0])


def _find_avatar(cid: str) -> tuple[str, str]:
    """找角色头像 → (url, type); 无 → ("", "")。type: portrait(GUI 头像) | png(diff 兜底)。

    板块化（2026-08-28）: 资产在 {char}/{outfit}/（default 为首选外观）;
    旧平铺 {char}/ 兼容兜底。**每个角色各取自己的**——没有的层就往下落。
    """
    for base in (ILLUS_ROOT / cid / "default", ILLUS_ROOT / cid):
        f = _pick_portrait(base / "portrait")
        if f is not None:
            return _asset_url(f), "portrait"
        diff_dir = base / "diff"
        if diff_dir.is_dir():
            for f in sorted(diff_dir.glob(_IDLE_GLOB)):
                return _asset_url(f), "png"
    return "", ""


def collection_cover(cid: str, outfit: str = "default") -> str:
    """回忆册封面 = 该外观的 `portrait/collection.png`（DESIGN_COLLECTION_BOOK §1）。

    与 `_find_avatar` 的区别: **不做 diff 兜底**——册子的留白格是产品语义
    （"这一格的人我还没有素材"）, 拿整张立绘当封面反而像故障。缺 → 空串。
    """
    p = ILLUS_ROOT / cid / outfit / "portrait" / _PORTRAIT_PREFERRED
    return _asset_url(p) if p.is_file() else ""


def _session_ids(store: SessionStore, cid: str) -> list[str]:
    """该角色在【当前世界】的角色线 id（v2: 每角色一条线——读 meta.json）。

    旧版枚举 sessions/ 子目录; v2 世界内每角色一条线（characters/{cid}/）——
    返回线的 id（meta.session_id, 无则空列表）。
    """
    d = store.char_dir(cid)
    if not d.is_dir():
        return []
    meta = store.meta(cid)
    return [meta.session_id] if meta.session_id else []


@router.get("/api/mmt/characters")
async def mmt_characters(sort: str = "recent") -> dict:
    """白名单角色的列表（id + 显示名 + 头像 + state + bio + birthday + affection）。

    ?sort=recent（默认, 最新活跃）| affection（好感, per-char 最高 session 倒序）。
    白名单为空 → []; 白名单角色若无头像 → 跳过（头像缺失意味着 diff 未配置）。
    birthday: toml 是**显示真源**（作者维护）; toml 未填 → profile SIG~birthday 兜底。
    affection: 事件流真源累计（digest 写的好感事件）→ best_affection 聚合。
    """
    registry = load_mmt_registry()
    if not registry:
        return {"characters": [], "registry_empty": True, "sort": sort}
    loader = CharacterLoader(CHAR_ROOT)
    names = loader.list_characters()
    store = SessionStore(ROOT / "data")
    recent_map: dict[str, str] = {}
    affection_map: dict[str, dict] = {}
    chars: list[dict] = []
    for entry in registry:
        cid, state = entry["id"], entry["state"]
        bio, birthday = entry["bio"], entry["birthday"]
        avatar, avatar_type = _find_avatar(cid)
        if not avatar:
            continue                     # 无头像 → 跳过（diff 未配）
        if not birthday:                 # toml 未填显示生日 → profile 兜底（AI 用那份）
            try:
                char = loader.load(cid)
                bd = char.profile.get("SIG~birthday", "")
                if isinstance(bd, str) and bd.strip():
                    birthday = bd.strip()
            except Exception:             # noqa: BLE001 — 角色卡异常 → 生日空, 不挡列表
                pass
        # 好感 + 最近活跃: 枚举该角色 session, 事件流累计好感 + 取最新互动时间
        sess_affs: list[dict | None] = []
        recent_ts = ""
        for sid in _session_ids(store, cid):
            evs = store.events(cid, sid)
            if not evs:
                continue
            sess_affs.append(load_affection_from_events(evs))
            last_ts = evs[-1].ts or ""
            if last_ts > recent_ts:
                recent_ts = last_ts
        aff = best_affection(sess_affs)
        if aff:
            affection_map[cid] = aff
        if recent_ts:
            recent_map[cid] = recent_ts
        chars.append({
            "id": cid,
            "name": names.get(cid, cid),
            "avatar": avatar,
            "avatar_type": avatar_type,
            "state": state,
            "bio": bio,
            "birthday": birthday,
            "affection": aff,
        })
    mode = sort if sort in SORT_MODES else "recent"
    chars = sort_characters(chars, mode=mode, recent=recent_map, affection=affection_map)
    return {"characters": chars, "registry_empty": False, "sort": mode}


# ---------------------------------------------------------------------------
# 聊天（M3: 会话 + 后台任务 + 轮询——接 webgui/chat.py）
# ---------------------------------------------------------------------------

class ChatIn(BaseModel):
    char_id: str
    session_id: str
    text: str


def _display_name(cid: str) -> str:
    """角色显示名（入口横幅"进入 xx 的羁绊剧情"用）; 找不到 → 原 id。"""
    try:
        names = CharacterLoader(CHAR_ROOT).list_characters()
        return names.get(cid, cid)
    except Exception:                    # noqa: BLE001 — 角色卡异常 → id 兜底
        return cid


@router.get("/api/mmt/session")
async def mmt_session(char_id: str) -> dict:
    """打开某角色的会话（恢复进行中 or 新开世界线）+ 拉历史气泡。"""
    opened = chat.open_session(char_id)
    events = chat.events_after(char_id, opened["session_id"], 0, _display_name(char_id))
    return {**opened, "bubbles": events["bubbles"], "last_seq": events["last_seq"]}


@router.post("/api/mmt/chat")
async def mmt_chat(body: ChatIn) -> dict:
    """发起一轮对话（后台线程跑 agent_turn, 立即返回; 结果落事件流, 轮询拉取）。"""
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="消息不能为空")
    return chat.chat_async(body.char_id, body.session_id, text)


@router.get("/api/mmt/events")
async def mmt_events(char_id: str, session_id: str, since: int = 0) -> dict:
    """轮询: seq > since 的新气泡 + 最新 seq + 任务状态（回复中/出错/触发 bond）。"""
    return chat.events_after(char_id, session_id, since, _display_name(char_id))
