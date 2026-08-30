# -*- coding: utf-8 -*-
"""MMT 路由（成员列表 + 头像 + 好感 + 排序）。

角色来源 = mmt_registry.toml 白名单（作者维护）——只显示白名单内的角色, 按白名单
顺序; 头像从 assets/illustration/{id}/diff/*Idle* 取（png <img> / webm <video>）。
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

# 头像优先级:
#   1) assets/illustration/{id}/mmt/*.png —— BA 圆形头像渲染图（作者放; 目前仅遥香）
#   2) diff/*Idle*.png —— 兜底（前端圆形裁剪）; 不用 webm（动图, 用户弃用）
_MMT_GLOB = "*.png"
_IDLE_GLOB = "*[Ii]dle*.png"


def _find_avatar(cid: str) -> tuple[str, str]:
    """找角色头像 → (url, type); 无 → ("", "")。type: mmt(BA圆头像) | png(diff兜底)。

    板块化（2026-08-28）: 资产在 {char}/{outfit}/（default 为默认外观）;
    旧平铺 {char}/mmt、{char}/diff 兼容兜底。
    """
    for base in (ILLUS_ROOT / cid / "default", ILLUS_ROOT / cid):
        mmt_dir = base / "mmt"
        if mmt_dir.is_dir():
            for f in sorted(mmt_dir.glob(_MMT_GLOB)):
                rel = f.relative_to(ILLUS_ROOT)
                return f"/assets/illustration/{rel.as_posix()}", "mmt"
        diff_dir = base / "diff"
        if diff_dir.is_dir():
            for f in sorted(diff_dir.glob(_IDLE_GLOB)):
                rel = f.relative_to(ILLUS_ROOT)
                return f"/assets/illustration/{rel.as_posix()}", "png"
    return "", ""


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
