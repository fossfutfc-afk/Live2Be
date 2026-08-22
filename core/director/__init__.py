# -*- coding: utf-8 -*-
"""视觉导演 — 纯算法映射器（消费主 LLM 意图 beats[].emotion + place → sprite/背景）。

v2（DESIGN_VISUAL_PROTOCOL.md）: 情感判断归主 LLM, 导演只查表（1:1）+ 词表外延续;
beats 缺失（纯文本模式）→ 旧链（正则 → 保持 → 默认）。无辅助 LLM（背景/音乐等
未来非情感决策若需语义仲裁, 直接用 llm/client.py 的 LLMClient）。

用法:
    from core.director import Director, build_director
    director = build_director(char)
    vs = director.visual_for(
        [{"text": "她脸红了", "emotion": "embarass"}], place="class_room")
    # vs.sprite / vs.background / director.last_beat_sprites → 合并进 BondScene

架构见 core/DESIGN_VISUAL_PROTOCOL.md + core/DESIGN_VISUAL.md。
"""
from core.director.director import Director
from core.director.fallback import DEFAULT_BACKGROUND, DEFAULT_SPRITE, infer_sprite
from core.director.state import VisualState

__all__ = [
    "Director", "build_director",
    "VisualState",
    "DEFAULT_SPRITE", "DEFAULT_BACKGROUND", "infer_sprite",
]


def build_director(char, *, catalog=None) -> Director:
    """从 DynamicCharacter 构建导演（纯查表模式, 无辅助 LLM）。

    catalog 缺省用 MediaCatalog()（背景全量扫描 ~百 ms, 每次 VN 会话一次）。
    """
    from core.media import MediaCatalog

    return Director(
        catalog=catalog if catalog is not None else MediaCatalog(),
        char_id=char.character_id,
    )
