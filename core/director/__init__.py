# -*- coding: utf-8 -*-
"""视觉导演 — 每场定表情/背景（LLM 主驱动 + 正则/保持/默认降级 + 背景目录分层）。

用法:
    from core.director import Director, DirectorLLM, build_director
    director = build_director(char, trigger_reason="老师约我放学后见面")
    vs = director.visual_for("她脸红了", is_end=False)
    # vs.sprite / vs.background → 合并进 BondScene

导演 LLM 可注入（None = 纯正则模式）; 失败自动降级, VN 照跑。
架构见 core/DESIGN_VISUAL.md §2-4。
"""
from core.director.director import Director, load_common_whitelist
from core.director.fallback import DEFAULT_BACKGROUND, DEFAULT_SPRITE, infer_sprite
from core.director.llm import DirectorLLM, DirectorLLMError, DirectorSuggestion
from core.director.state import VisualState

__all__ = [
    "Director", "build_director", "load_common_whitelist",
    "VisualState", "DirectorLLM", "DirectorLLMError", "DirectorSuggestion",
    "DEFAULT_SPRITE", "DEFAULT_BACKGROUND", "infer_sprite",
]


def build_director(
    char,
    trigger_reason: str = "",
    *,
    catalog=None,
    llm=None,
    nudge_after: int = 3,
) -> Director:
    """从 DynamicCharacter 构建导演（人设注入 = char.build_prompt("trigger")）。

    catalog 缺省用 MediaCatalog()（背景全量扫描 ~百 ms, 每次 VN 会话一次）;
    llm 缺省 None（纯正则模式）——接入本地导演时传 DirectorLLM()。
    """
    from core.media import MediaCatalog

    return Director(
        catalog=catalog if catalog is not None else MediaCatalog(),
        char_id=char.character_id,
        persona=char.build_prompt("trigger"),
        trigger_reason=trigger_reason,
        llm=llm,
        nudge_after=nudge_after,
    )
