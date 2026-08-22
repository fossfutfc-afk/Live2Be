# -*- coding: utf-8 -*-
"""媒体查库 — assets/ 纯数据索引（差分/背景/spine → 路径）。

查询面（宁缺勿错, 查不到返回 None）:
    MediaCatalog.background(scene_id, variant=None)  → 背景（命名派生, 零 manifest）
    MediaCatalog.sprite(char_id, emotion)            → 差分（manifest 映射 + 可选 spine 导出）
    sprite_emotions / background_scenes              → 白名单（喂 ② 导演/播放协议）

架构见 core/DESIGN_VISUAL.md §5-①。
"""
from core.media.background import BackgroundMedia, derive_background
from core.media.catalog import MediaCatalog, MediaError
from core.media.sprites import SpinePack, SpriteMedia

__all__ = [
    "MediaCatalog", "MediaError",
    "BackgroundMedia", "derive_background",
    "SpinePack", "SpriteMedia",
]
