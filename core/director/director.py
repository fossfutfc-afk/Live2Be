# -*- coding: utf-8 -*-
"""视觉导演 — 纯算法映射器（无辅助 LLM）。

v2 决策链（DESIGN_VISUAL_PROTOCOL.md §2/§6/§11）:

    表情（per-beat）:  emotion 查表(词表白名单内=1:1 直接用) > 延续(词表外/缺失拍
        → 上一拍/上一场 sprite; 冷启动 → 默认) 。
        情感判断归主 LLM（beats[].emotion 直给 key）——导演**不猜情感、不调 LLM**。
    背景（per-scene）: place 合法(background_scenes) > 保持上一场 > 默认 neutral。
        place 非法/缺失 → 静默降级, 不回传主 LLM（协议 §5: 拦截在引擎边界）。
    beats 缺失（纯文本模式）→ 旧链兜底（正则 → 保持 → 默认）, VN 照跑。

辅助 LLM 定位（未来, 不在本组件）: 背景/音乐等非情感决策若需语义仲裁, 直接
用 llm/client.py 的 LLMClient（已含 json_object/重试/清洗）, 不再设 DirectorLLM
薄封装（2026-08-23 退役, 见 git 历史 core/director/llm.py）。
"""

from __future__ import annotations

import logging

from core.director.fallback import (
    DEFAULT_BACKGROUND,
    DEFAULT_SPRITE,
    infer_sprite,
)
from core.director.state import VisualState

logger = logging.getLogger(__name__)


class Director:
    """视觉导演复合体（意图查表驱动 + 正则/保持/默认降级链 + place 背景查表）。"""

    def __init__(
        self,
        catalog,
        char_id: str,
        *,
        default_sprite: str = DEFAULT_SPRITE,
        default_background: str = DEFAULT_BACKGROUND,
    ) -> None:
        self.catalog = catalog
        self.char_id = char_id
        self.default_sprite = default_sprite
        self.default_background = default_background
        self._state: VisualState | None = None      # 未开始 = None（冷启动）
        self._last_beat_sprites: list[str] = []     # 最近一次 visual_for 的 per-beat 映射

    # ------------------------------------------------------------------
    # 公共
    # ------------------------------------------------------------------

    def visual_for(
        self,
        beats: list[dict] | None = None,
        place: str | None = None,
        text: str = "",
        *,
        is_end: bool = False,
    ) -> VisualState:
        """对一场剧情定 sprite/background, 更新视觉记忆, 返回新 VisualState。

        Args:
            beats: 主 LLM 意图 [{text, emotion}]（可空 = 纯文本模式, 走旧降级链）
            place: 主 LLM 意图（场景级地点, 可空; 非法 → 静默保持/默认）
            text:  兜底段落文本（beats 缺失时正则推断用）
            is_end: 收尾标记（v2 不强制收尾表情, 保留参数兼容）

        Returns:
            新 VisualState{sprite, background}（场景级主视觉）。per-beat 映射
            经 last_beat_sprites 属性取（与 beats 对齐, 缺失拍 = 延续值）。
        """
        emotions = self.catalog.sprite_emotions(self.char_id)
        bg_scenes = set(self.catalog.background_scenes())

        prev = self._state
        base = prev or VisualState(
            sprite=self.default_sprite, background=self.default_background)

        background = self._decide_background(place, bg_scenes, base)
        if beats:
            beat_sprites = self._map_beats(beats, emotions, base)
            sprite = beat_sprites[-1] if beat_sprites else base.sprite
            self._last_beat_sprites = beat_sprites
        else:
            sprite = self._decide_sprite_legacy(text, emotions, base)
            self._last_beat_sprites = []

        new = VisualState(sprite=sprite, background=background)
        self._state = new
        return new

    def reset(self) -> None:
        """新会话清空视觉记忆（引擎 start_session 调用）。"""
        self._state = None
        self._last_beat_sprites = []

    @property
    def state(self) -> VisualState:
        """当前视觉记忆（未开始 → 冷启动默认）。"""
        return self._state or VisualState(
            sprite=self.default_sprite, background=self.default_background)

    @property
    def last_beat_sprites(self) -> list[str]:
        """最近一次 visual_for 的 per-beat sprite（与 beats 对齐; 纯文本 → []）。"""
        return list(self._last_beat_sprites)

    # ------------------------------------------------------------------
    # 决策链
    # ------------------------------------------------------------------

    def _map_beats(self, beats: list[dict], emotions: list[str], base: VisualState) -> list[str]:
        """逐拍查表: emotion 在白名单 → 直接用（1:1）; 词表外/缺失 → 延续。

        延续语义（协议 §11）: 拍内延续上一拍 sprite; 拍首用上一场 base.sprite;
        冷启动（无上一场）用默认。无辅助 LLM——1:N 的解法是拆词表（协议 §4:
        三种笑 = 三个词）, 作者拆细后全 1:1, 查表走天下。
        """
        sprites: list[str] = []
        current = base.sprite
        for b in beats:
            emo = b.get("emotion", "") if isinstance(b, dict) else ""
            if emo and emo in emotions:
                current = emo                     # 1:1 查表命中
            sprites.append(current)               # 词表外/缺失 → 延续 current
        return sprites

    def _decide_background(
        self, place: str | None, bg_scenes: set[str], base: VisualState,
    ) -> str:
        """背景: place 合法(background_scenes) > 保持上一场 > 默认 neutral。

        place 非法/缺失 → 静默降级（不回传主 LLM）。背景不参与正则。
        """
        if place and place in bg_scenes:
            return place
        if base.background in bg_scenes:
            return base.background
        return self.default_background

    def _decide_sprite_legacy(
        self, text: str, emotions: list[str], base: VisualState,
    ) -> str:
        """beats 缺失（纯文本模式）旧链兜底: 正则 > 保持 > 默认。"""
        inferred = infer_sprite(text, emotions)
        if inferred is not None:
            return inferred
        if base.sprite in emotions:
            return base.sprite
        if self.default_sprite in emotions:
            return self.default_sprite
        return emotions[0] if emotions else self.default_sprite
