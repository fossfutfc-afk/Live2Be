# -*- coding: utf-8 -*-
"""MMT 路由（M3: 成员列表 + 头像——纯 UI 数据, 聊天逻辑后写）。

角色来源 = mmt_registry.toml 白名单（作者维护）——只显示白名单内的角色,
按白名单顺序; 头像从 assets/illustration/{id}/diff/*Idle* 取（png <img> / webm <video>）。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from core.common.mmt_registry import load_mmt_registry
from core.parsing.dynamic_character_parser import CharacterLoader

router = APIRouter()

ROOT = Path(__file__).resolve().parent.parent.parent
CHAR_ROOT = ROOT / "config" / "characters"
ILLUS_ROOT = ROOT / "assets" / "illustration"

# 头像文件名规律: {char缩写}_spr_Idle_01.{png,webm}（glob 通配, 大小写宽容）
_IDLE_GLOB = "*[Ii]dle*"


def _find_avatar(cid: str) -> tuple[str, str]:
    """找角色 idle 头像 → (url, type); 无 → ("", "")。png 优先, webm 兜底。"""
    ill = ILLUS_ROOT / cid / "diff"
    if not ill.is_dir():
        return "", ""
    avatar, avatar_type = "", "png"
    for f in sorted(ill.glob(_IDLE_GLOB)):
        suffix = f.suffix.lower()
        if suffix == ".png" and not avatar:
            avatar, avatar_type = f"/assets/illustration/{cid}/diff/{f.name}", "png"
        elif suffix == ".webm" and not avatar:
            avatar, avatar_type = f"/assets/illustration/{cid}/diff/{f.name}", "webm"
        if avatar and avatar_type == "png":
            break
    return avatar, avatar_type


@router.get("/api/mmt/characters")
async def mmt_characters() -> dict:
    """白名单角色的列表（id + 显示名 + 头像 + state + bio + birthday）。

    白名单为空 → []; 白名单角色若无头像 → 跳过（头像缺失意味着 diff 未配置）。
    birthday: toml 是**显示真源**（作者维护）; toml 未填 → profile SIG~birthday 兜底。
    """
    registry = load_mmt_registry()
    if not registry:
        return {"characters": [], "registry_empty": True}
    loader = CharacterLoader(CHAR_ROOT)
    names = loader.list_characters()
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
        chars.append({
            "id": cid,
            "name": names.get(cid, cid),
            "avatar": avatar,
            "avatar_type": avatar_type,
            "state": state,
            "bio": bio,
            "birthday": birthday,
        })
    return {"characters": chars, "registry_empty": False}
