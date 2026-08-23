# -*- coding: utf-8 -*-
"""视觉导演 — 纯算法映射器（只决定背景 + 音频占位, 消费主 LLM 意图 place）。

v2（DESIGN_VISUAL_PROTOCOL.md）: 表情由主 LLM 意图 beats[].emotion 直查
emotions.yml（渲染端消费, 不经过导演）; 导演只做 place → background 查表 +
audio 占位。无辅助 LLM（未来背景/音乐等非情感决策若需语义仲裁, 直接用
llm/client.py 的 LLMClient 填 audio）。

用法:
    from core.director import Director, build_director
    director = build_director(char)
    vs = director.visual_for(place="class_room")
    # vs.background / vs.audio → 合并进 BondScene

架构见 core/DESIGN_VISUAL_PROTOCOL.md + core/DESIGN_VISUAL.md。
"""
from core.director.director import Director
from core.director.state import DEFAULT_BACKGROUND, VisualState

__all__ = [
    "Director", "build_director",
    "VisualState", "DEFAULT_BACKGROUND",
]


def build_director(char, *, catalog=None) -> Director:
    """从 DynamicCharacter 构建导演（纯背景查表模式, 无辅助 LLM）。

    catalog 缺省用 MediaCatalog()（背景全量扫描 ~百 ms, 每次 VN 会话一次）。
    """
    from core.media import MediaCatalog

    return Director(
        catalog=catalog if catalog is not None else MediaCatalog(),
        char_id=char.character_id,
    )
