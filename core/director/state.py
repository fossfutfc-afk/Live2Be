# -*- coding: utf-8 -*-
"""视觉记忆 — 导演维护的当前视觉状态（背景 + 音频占位）。

表情不在导演职责内（DESIGN_VISUAL_PROTOCOL.md §2）: 主 LLM 意图 beats[].emotion
直接经 emotions.yml 查表（catalog.sprite）, 渲染端消费, 不经过导演。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 冷启动默认背景（渲染面无资产时映射为"无背景/纯色"）
DEFAULT_BACKGROUND = "neutral"


@dataclass(frozen=True)
class VisualState:
    """当前视觉状态（背景 + 音频）。

    background — 背景场景 id（如 class_room），冷启动默认 DEFAULT_BACKGROUND
    audio      — 音频占位（str | None; 当前恒 None, 未来背景/音乐语义仲裁时填）
    """

    background: str = DEFAULT_BACKGROUND
    audio: str | None = None

    def to_dict(self) -> dict:
        d = {"background": self.background}
        if self.audio is not None:
            d["audio"] = self.audio
        return d
