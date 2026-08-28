# -*- coding: utf-8 -*-
"""Renderer — 羁绊剧情渲染管线（DESIGN_RENDERER.md §二/§九）。

输入 RenderScene（实时 from_live / 回放 from_event——同构, 渲染器不区分来源）;
输出 RenderOutput（平台无关状态——GUI/CLI 各自消费）。

管线:
    render(scene) → RenderOutput
      ├─ ① 背景解算:   scene.background → BackgroundResolver → 图 + 过渡
      ├─ ② 差分解算:   paragraphs → SpriteResolver → emotion 序列（确定性延续）
      ├─ ③ 特效解算:   emotion 序列 → EffectResolver → 逐段特效
      ├─ ④ 音频解算:   scene.audio → AudioRequest（占位, 当前恒 None）
      └─ ⑤ 文本+选项:  paragraphs / choices 透传（平台渲染）

确定性: ①②③ 全是纯查表/确定性算法——同输入必同输出（回放与实时一致）。

职责边界:
    - 渲染器不 import 引擎（core/bond_story）——只认 scene dict（防循环依赖 + 回放复用）
    - 渲染器不做剧情决策（生成/选择/收尾全在引擎）——只做"怎么显示"
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.media.catalog import MediaCatalog
from renderer.audio import AudioRequest
from renderer.background import BackgroundResolver, BackgroundResult
from renderer.effects import EffectResolver
from renderer.scene import RenderScene
from renderer.sprite import SpriteResolver


@dataclass
class RenderOutput:
    """一次 render 的平台无关输出（GUI/CLI 据此渲染）。"""

    background: BackgroundResult
    sprites: list[str | None]       # 每段 emotion 意图（播放层查图）
    effects: list[list[str]]        # 每段特效（emotion → 特效名列表）
    paragraphs: list[dict]          # 原文透传（[{text, emotion?}]）
    choices: list[str]              # 选项（空 = 无选项）
    audio: AudioRequest | None      # 音频指令（未来; 当前恒 None）
    is_end: bool
    place: str | None = None        # 场景级地点意图（只读透传, 平台可用作背景辅助）


class Renderer:
    """羁绊剧情渲染器——实时 + 回放双用途。"""

    def __init__(self, char_id: str, assets_root=None, *, mode: str = "live"):
        # mode: "live"（等玩家交互）| "replay"（自动推进）——影响状态机推进方式,
        # 渲染管线本身与 mode 无关（同输入同输出）
        self.mode = mode
        self._catalog = MediaCatalog(assets_root) if assets_root else MediaCatalog()
        self.background = BackgroundResolver(self._catalog)
        self.sprite = SpriteResolver(char_id, self._catalog)
        self.effects = EffectResolver(self._catalog.assets_root / "illustration" / char_id)

    # ------------------------------------------------------------------
    # 渲染管线
    # ------------------------------------------------------------------

    def render(self, scene: RenderScene) -> RenderOutput:
        """场景 → 渲染输出（背景/差分/特效/音频/文本/选项——平台无关）。"""
        bg = self.background.resolve(scene.background)
        emotions = self.sprite.emotions(scene.paragraphs)
        fx = self.effects.resolve(emotions)
        audio = self._audio_for(scene)
        return RenderOutput(
            background=bg,
            sprites=emotions,
            effects=fx,
            paragraphs=scene.paragraphs,
            choices=scene.choices,
            audio=audio,
            is_end=scene.is_end,
            place=scene.place,
        )

    def _audio_for(self, scene: RenderScene) -> AudioRequest | None:
        """音频解算（未来: catalog 查 asset; 当前 scene.audio 恒 None → None）。"""
        if scene.audio:
            return AudioRequest(kind="bgm", asset=scene.audio)
        return None

    def reset(self) -> None:
        """重置渲染状态（新剧情/回放开始时调用）。"""
        self.background.reset()
