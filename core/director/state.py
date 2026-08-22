# -*- coding: utf-8 -*-
"""视觉记忆 — 导演维护的当前视觉状态（每场喂回导演 context）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisualState:
    """当前视觉状态（表情 + 背景）。

    sprite    — 情绪白名单内值（如 nomal/smile/...），冷启动默认 DEFAULT_SPRITE
    background — 背景场景 id（如 class_room），冷启动默认 DEFAULT_BACKGROUND
    """

    sprite: str = "nomal"
    background: str = "neutral"

    def to_dict(self) -> dict:
        return {"sprite": self.sprite, "background": self.background}
