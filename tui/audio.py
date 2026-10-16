"""AudioRequest — 渲染器输出的音频指令（DESIGN_RENDERER.md §六, 未来占位）。

渲染器只输出指令（不实现播放）——播放器（GUI WebAudio / CLI 无）未来接入。
来源: scene.audio（导演层占位, 当前恒 None）→ 未来导演填 bgm/sfx id;
特效音（星星音效）: EffectResolver 可附带 effect_audio（未来）。

平台消费: GUI 播放 / CLI 忽略（无音频输出）。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioRequest:
    """一条音频指令。kind: "bgm" | "sfx" | "voice" | "stop"。"""

    kind: str            # "bgm" | "sfx" | "voice" | "stop"
    asset: str           # 音频资源 id/路径（catalog 查）
    volume: float = 1.0
    fade_in: float = 0.0   # 淡入秒
    fade_out: float = 0.0  # 淡出秒
    loop: bool = False
