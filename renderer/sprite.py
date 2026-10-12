"""SpriteResolver — 差分意图解算（DESIGN_RENDERER.md §4.2）。

职责划分（§4.1 定稿）:
    renderer 只出【意图】——段落 emotion → emotion 序列（确定性延续）,
    **不查图**（播放由 core/media/sprite_player.py 负责: play_diff/play_spine）。
    平台/调用方决定用哪个 API（GUI 有 spine 资产用 spine, 没有用 diff）。

确定性延续规则:
    - 段落显式带 emotion → 使用（词表内）
    - 段落缺省 → 继承上一段
    - 首段缺省 → 角色默认 emotion（词表第一项; 词表空 → None = 不指定）
    - 词表外 → 保持上一段（静默降级, 不 raise——宁缺勿错）

输入 paragraphs 来自 RenderScene（[{text, emotion?}] 或 [str] 旧档兼容）。
"""
from __future__ import annotations

from core.media.catalog import MediaCatalog


class SpriteResolver:
    """意图层: 段落 emotion → emotion 序列（不查图——播放由 sprite_player 负责）。"""

    def __init__(self, char_id: str, catalog: MediaCatalog):
        self._char_id = char_id
        # 角色词表白名单（catalog.sprite_emotions 已 sorted——确定性）
        self._valid = set(catalog.sprite_emotions(char_id))
        # 默认 emotion = 词表惯例默认态 nomal; 无 nomal → 词表首项（sorted 确定性）
        self._default = ("nomal" if "nomal" in self._valid
                         else sorted(self._valid)[0] if self._valid else None)

    def emotions(self, paragraphs: list) -> list[str | None]:
        """段落 → emotion 序列（确定性延续; None = 不指定/保持）。

        元素类型 str | None——GUI 遇 None 保持上一张; CLI 遇 None 不标注。
        """
        seq: list[str | None] = []
        current: str | None = self._default
        for p in paragraphs:
            emotion = p.get("emotion") if isinstance(p, dict) else None
            if isinstance(emotion, str) and emotion.strip():
                key = emotion.strip()
                if key in self._valid:
                    current = key
                # 词表外 → 保持当前（静默降级）
            seq.append(current)
        return seq
