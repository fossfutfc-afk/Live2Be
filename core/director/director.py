"""视觉导演 — 纯算法映射器（只决定背景 + 音频占位, 无辅助 LLM）。

职责（DESIGN_VISUAL_PROTOCOL.md §2/§6/§11）:

    背景（per-scene）:  place 合法(background_scenes) > 保持上一场 > 默认 neutral。
        place 非法/缺失 → 静默降级, 不回传主 LLM（协议 §5: 拦截在引擎边界）。
    音频（占位）:       audio 恒 None——未来背景/音乐等非情感决策若需语义仲裁,
        直接用 llm/client.py 的 LLMClient（已含 json_object/重试/清洗）填此字段。
    表情（不在导演职责）: 主 LLM 意图 beats[].emotion 直接查 emotions.yml
        （catalog.sprite）, 渲染端消费; 导演**不猜情感、不查表情**。

历史: v1 导演曾做表情推断（正则 + 导演 LLM 大空间选择）, 2026-08-23 随视觉意图
协议退役（见 git 历史 core/director/fallback.py / llm.py / prompt.py）。
"""

from __future__ import annotations

import logging

from core.director.state import DEFAULT_BACKGROUND, VisualState

logger = logging.getLogger(__name__)


class Director:
    """视觉导演复合体（place 背景查表 + 音频占位）。"""

    def __init__(
        self,
        catalog,
        char_id: str,
        *,
        default_background: str = DEFAULT_BACKGROUND,
    ) -> None:
        self.catalog = catalog
        self.char_id = char_id
        self.default_background = default_background
        self._state: VisualState | None = None      # 未开始 = None（冷启动）

    # ------------------------------------------------------------------
    # 公共
    # ------------------------------------------------------------------

    def visual_for(
        self,
        place: str | None = None,
        *,
        is_end: bool = False,
    ) -> VisualState:
        """对一场剧情定 background（+ audio 占位）, 更新视觉记忆。

        Args:
            place: 主 LLM 意图（场景级地点, 可空; 非法 → 静默保持/默认）
            is_end: 收尾标记（保留参数兼容, 背景不因收尾变化）

        Returns:
            新 VisualState{background, audio}。audio 恒 None（占位, 未来填）。
        """
        bg_scenes = set(self.catalog.background_scenes())
        prev = self._state
        base = prev or VisualState(background=self.default_background)

        new = VisualState(
            background=self._decide_background(place, bg_scenes, base),
            audio=None,                                  # 占位: 未来音频仲裁填
        )
        self._state = new
        return new

    def reset(self) -> None:
        """新会话清空视觉记忆（引擎 start_session 调用）。"""
        self._state = None

    @property
    def state(self) -> VisualState:
        """当前视觉记忆（未开始 → 冷启动默认）。"""
        return self._state or VisualState(background=self.default_background)

    # ------------------------------------------------------------------
    # 决策链
    # ------------------------------------------------------------------

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
