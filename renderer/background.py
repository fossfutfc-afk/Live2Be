# -*- coding: utf-8 -*-
"""BackgroundResolver — 背景解算（DESIGN_RENDERER.md §三）。

职责: scene_id → 背景媒体 + 过渡（复用 core/media/catalog 的 MediaCatalog 查库）;
状态: 记住当前背景——相同不切换（无闪烁）、缺失保持（宁缺勿错）。

切换策略:
    背景变化（新 scene_id ≠ 当前）  → 过渡切换（transition 秒; GUI 淡入淡出 / CLI 标签）
    背景相同                        → 不切换（transition=0, changed=False）
    背景缺失（None / catalog 查不到）→ 保持当前（宁缺勿错）

未来扩展（预留）: 动态背景（media_path 可指向视频/序列帧）、背景叠加层（overlay）。
"""
from __future__ import annotations

from dataclasses import dataclass

from core.media.catalog import MediaCatalog

#: 默认过渡时长（秒）——GUI 淡入淡出; CLI 忽略数值只打标签
DEFAULT_TRANSITION = 0.5


@dataclass(frozen=True)
class BackgroundResult:
    """一次背景解算结果（平台据此做动画/标签）。"""

    scene_id: str | None
    media_path: str | None       # 绝对路径（GUI 用）或 None
    transition: float            # 过渡秒数（0 = 无变化）
    changed: bool                # 是否发生了切换（平台据此做动画/标签）


class BackgroundResolver:
    """背景解算: scene_id → 背景媒体 + 过渡（纯查表 + 状态保持）。"""

    def __init__(self, catalog: MediaCatalog, *, transition: float = DEFAULT_TRANSITION):
        self._catalog = catalog
        self._transition = transition
        self._current: str | None = None     # 当前背景 scene_id（None = 尚未有）

    def resolve(self, scene_id: str | None) -> BackgroundResult:
        """解算一个场景的背景请求。

        scene_id=None（纯文本模式）→ 保持当前背景, 不切换;
        scene_id 与当前相同 → 不切换（无闪烁）;
        catalog 查不到该 scene_id → 保持当前（宁缺勿错, 不黑屏）。
        """
        if scene_id is None:
            return BackgroundResult(self._current, self._media_path(self._current),
                                    0.0, False)
        if scene_id == self._current:
            return BackgroundResult(scene_id, self._media_path(scene_id), 0.0, False)
        media = self._catalog.background(scene_id)
        if media is None:
            # 缺失 → 保持当前（宁缺勿错）
            return BackgroundResult(self._current, self._media_path(self._current),
                                    0.0, False)
        self._current = scene_id
        return BackgroundResult(scene_id, str(media.path), self._transition, True)

    def reset(self) -> None:
        """重置当前背景（新剧情/回放开始时调用）。"""
        self._current = None

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _media_path(self, scene_id: str | None) -> str | None:
        if scene_id is None:
            return None
        media = self._catalog.background(scene_id)
        return str(media.path) if media is not None else None
