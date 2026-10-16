"""差分播放层 — 差分/骨骼动画播放（DESIGN_RENDERER.md §4.3, 独立于 tui）。

tui 只出意图（emotion 序列）——播放由本模块负责:
    API 1: play_diff(char_id, emotion)   → diff/ 静态差分图（emotions.yml 查）
    API 2: play_spine(char_id, emotion)  → spine/ 骨骼动画包（spine 目录查）

平台/调用方决定用哪个 API（GUI 有 spine 资产用 spine, 没有用 diff）;
未来可扩展 play_l2d()（L2D 模型）——API 形态一致（char_id, emotion → 媒体/None）。

复用: MediaCatalog（懒加载缓存）——emotions.yml 键 → diff/ 静态路径 + 可选 spine 导出;
缺失 → None（调用方保持上一张, 静默降级——宁缺勿错）。
"""
from __future__ import annotations

from core.media.catalog import MediaCatalog
from core.media.sprites import SpinePack, SpriteMedia


class SpritePlayer:
    """差分播放层（薄封装 MediaCatalog——构造一次, 查询 O(1)）。"""

    def __init__(self, assets_root=None):
        self._catalog = MediaCatalog(assets_root) if assets_root else MediaCatalog()

    # ------------------------------------------------------------------
    # API 1: diff 静态差分播放（直接播放 diff/ 图）
    # ------------------------------------------------------------------

    def play_diff(self, char_id: str, emotion: str,
                  outfit: str = "default") -> SpriteMedia | None:
        """emotions.yml 查 emotion → 静态差分图（缺失 → None, 调用方保持上一张）。"""
        media = self._catalog.sprite(char_id, emotion, outfit)
        if media is None or media.static_path is None:
            return None
        return media

    # ------------------------------------------------------------------
    # API 2: spine 骨骼动画播放（未来——spine/ 目录资产）
    # ------------------------------------------------------------------

    def play_spine(self, char_id: str, emotion: str,
                   outfit: str = "default") -> SpinePack | None:
        """查该外观优先 spine 导出包（缺失 → None, 调用方降级到 play_diff）。"""
        media = self._catalog.sprite(char_id, emotion, outfit)
        if media is None or media.spine is None:
            return None
        return media.spine

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def sprite(self, char_id: str, emotion: str,
               outfit: str = "default") -> SpriteMedia | None:
        """原始查询（含 spine 的完整媒体; 调用方自取 static_path/spine）。"""
        return self._catalog.sprite(char_id, emotion, outfit)

    def emotions(self, char_id: str, outfit: str = "default") -> list[str]:
        """外观词表白名单（供 GUI 校验/降级决策）。"""
        return self._catalog.sprite_emotions(char_id, outfit)
