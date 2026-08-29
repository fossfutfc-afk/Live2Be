# -*- coding: utf-8 -*-
"""spine 路由 — SpinePlayer 前端元信息端点（side-request: spine-player 接口）。

GET /api/spine/{char_id}?outfit=default → 用现有 core/media/sprite_player.py（SpritePlayer）查库:
    - pack:     该外观首选 spine 包的三件套 URL（skel/atlas; png 由 atlas 页名同目录推导）
    - emotions:  外观词表 → 动画名映射（manifest 双投影: 资源 ID / 路径 stem 推导）

板块结构（2026-08-28）: 每外观一个自包含目录 {char}/{outfit}/, 有 emotions.yml 的目录 = 外观;
outfit 缺省 "default"; 不存在的外观 → 404（前端保持 diff 静态图降级, 不阻断）。

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


def _derive_emotion_map(char_id: str, outfit: str) -> dict[str, str]:
    """外观词表 → 动画名（manifest 双投影派生: 资源 ID / 路径 stem 推导——前端校验存在性）。"""
    player = _player()
    emotions = player.emotions(char_id, outfit)
    if not emotions:
        return {}
    mapping: dict[str, str] = {}
    for e in emotions:
        media = player.sprite(char_id, e, outfit)
        if media and media.anim:
            mapping[e] = media.anim
    return mapping


@router.get("/api/spine/{char_id}")
async def api_spine(char_id: str, outfit: str = "default") -> dict:
    """SpinePlayer 元信息: 该外观首选 spine 包 URL + 情绪→动画映射。

    无资源 / 外观不存在 → 404（前端保持 diff 静态图降级, 不阻断）。
    """
    player = _player()
    emotions = player.emotions(char_id, outfit)
    if not emotions:
        raise HTTPException(status_code=404,
                            detail=f"角色/外观无资源: {char_id}/{outfit}")

    pack = None
    for e in emotions:
        media = player.sprite(char_id, e, outfit)
        if media and media.spine:
            pack = media.spine
            break
    if pack is None:
        raise HTTPException(status_code=404,
                            detail=f"外观无 spine 包: {char_id}/{outfit}")

    def url(path: Path) -> str:
        return f"/assets/illustration/{char_id}/{outfit}/spine/{pack.name}/{path.name}"

    return {
        "char_id": char_id,
        "outfit": outfit,
        "pack": {
            "name": pack.name,
            "skel": url(pack.skel),
            "atlas": url(pack.atlas),
        },
        "emotions": _derive_emotion_map(char_id, outfit),
    }
