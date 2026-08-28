# -*- coding: utf-8 -*-
"""spine 路由 — SpinePlayer 前端元信息端点（side-request: spine-player 接口）。

GET /api/spine/{char_id} → 用现有 core/media/sprite_player.py（SpritePlayer）查库:
    - pack:     该角色首选 spine 包的三件套 URL（skel/atlas; png 由 atlas 页名同目录推导）
    - emotions:  情绪词表 → 动画名映射（默认推导: diff 文件名去 "<包名>_" 前缀）

映射推导规则（与 assets 命名红利对齐）:
    diff/haruka_spr_01.png + pack "haruka_spr" → 动画 "01"
    diff/haruka_spr_Eye_Close_01.png           → 动画 "Eye_Close_01"
    diff 前缀与包名不符 → 原样返回 stem（前端 load 后校验动画集合, 不在则 setEmotion 返回 false 保持现状）

动画名存在性由前端校验（后端不解析 skel 二进制——宁缺勿错, 前端 play() 已有静默降级）。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.media.sprite_player import SpritePlayer

router = APIRouter()

# 模块级懒单例（MediaCatalog 构造扫背景 ~百 ms, 避免每请求重建）
_PLAYER: SpritePlayer | None = None


def _player() -> SpritePlayer:
    global _PLAYER
    if _PLAYER is None:
        _PLAYER = SpritePlayer()
    return _PLAYER


def _derive_emotion_map(char_id: str) -> dict[str, str]:
    """情绪词表 → 动画名（机械推导, 不做存在性判断——前端校验）。"""
    player = _player()
    emotions = player.emotions(char_id)
    if not emotions:
        return {}
    pack = None
    for e in emotions:
        media = player.sprite(char_id, e)
        if media and media.spine:
            pack = media.spine
            break
    if pack is None:
        return {}
    prefix = f"{pack.name}_"
    mapping: dict[str, str] = {}
    for e in emotions:
        media = player.sprite(char_id, e)
        if media is None or media.static_path is None:
            continue
        stem = media.static_path.stem
        mapping[e] = stem[len(prefix):] if stem.startswith(prefix) else stem
    return mapping


@router.get("/api/spine/{char_id}")
async def api_spine(char_id: str) -> dict:
    """SpinePlayer 元信息: 首选 spine 包 URL + 情绪→动画映射。

    无 spine 资产 / 角色不存在 → 404（前端保持 diff 静态图降级, 不阻断）。
    """
    player = _player()
    emotions = player.emotions(char_id)
    if not emotions:
        raise HTTPException(status_code=404, detail=f"角色无资源: {char_id}")

    pack = None
    for e in emotions:
        media = player.sprite(char_id, e)
        if media and media.spine:
            pack = media.spine
            break
    if pack is None:
        raise HTTPException(status_code=404, detail=f"角色无 spine 包: {char_id}")

    def url(path: Path) -> str:
        return f"/assets/illustration/{char_id}/spine/{pack.name}/{path.name}"

    return {
        "char_id": char_id,
        "pack": {
            "name": pack.name,
            "skel": url(pack.skel),
            "atlas": url(pack.atlas),
        },
        "emotions": _derive_emotion_map(char_id),
    }
