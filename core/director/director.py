# -*- coding: utf-8 -*-
"""视觉导演 — 每场定 sprite/background, 维护 VisualState（视觉记忆）。

决策链（宁缺勿错, 逐级降级, 失败**不进主 LLM retry 循环**; DESIGN_VISUAL §3-4）:

    表情:  导演 sprite(合法)  >  正则推断(段落)  >  状态保持(上一场)  >  默认 nomal
           正则在"无导演 LLM"(当驱动器, 每场) 或 "冷启动"(尚无已定状态) 才跑——
           有导演 LLM 且已有状态时不跑, 防止正则抖动盖过导演的细腻选择。
    背景:  导演 scene_id(合法)  >  目录分层(先选目录→拍板场景)  >  状态保持  >  默认 neutral
           背景**无正则**（文本→地点太模糊）; 不参与 nudge（教室戏待在教室是对的）。

人设注入: persona = char.build_prompt("trigger")（profile + brief_traits 极简）,
   喂给导演保证 sprite 贴合角色性格（7B 把握不好人设 → sprite 质量低, 这是主要缓解）。

LLM 降级: 连续 2 次 DirectorLLMError → 本轮禁用 LLM, 降级正则+默认（VN 照跑）。

算法辅助（nudge）: 同一表情保持 ≥ nudge_after 场 → 给导演系统注记换表情
（只进导演 context 不入历史, 镜像 remind_rounds）。收尾**不强制** nomal, 只给提示。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from core.director.fallback import (
    DEFAULT_BACKGROUND,
    DEFAULT_SPRITE,
    infer_sprite,
)
from core.director.llm import DirectorLLMError
from core.director.prompt import build_director_prompt, build_drill_prompt
from core.director.state import VisualState
from llm.prompts import load_prompt

logger = logging.getLogger(__name__)

#: 常用集合默认文件（可编辑; 缺失/损坏 → 空, 宁缺勿错）
_DEFAULT_COMMON = Path(__file__).resolve().parent.parent.parent / "assets" / "_director_whitelist.json"


def load_common_whitelist(path: str | Path | None = None) -> dict:
    """读常用集合 → {"scenes": [...], "dirs": [...]}（导演背景快速路径 + 目录分层）。"""
    p = Path(path) if path else _DEFAULT_COMMON
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"scenes": [], "dirs": []}
    return {
        "scenes": [s for s in data.get("common_scenes", []) if isinstance(s, str)],
        "dirs": [d for d in data.get("common_dirs", []) if isinstance(d, str)],
    }


class Director:
    """视觉导演复合体（LLM 主驱动 + 正则/保持/默认 fallback 链 + 背景目录分层）。"""

    def __init__(
        self,
        catalog,
        char_id: str,
        *,
        persona: str = "",
        trigger_reason: str = "",
        llm=None,
        nudge_after: int = 3,
        common: dict | None = None,
        default_sprite: str = DEFAULT_SPRITE,
        default_background: str = DEFAULT_BACKGROUND,
        rules: str | None = None,
    ) -> None:
        self.catalog = catalog
        self.char_id = char_id
        self.persona = persona
        self.trigger_reason = trigger_reason
        self.llm = llm                        # DirectorLLM | None（None = 纯正则模式）
        self.nudge_after = nudge_after
        self._common = common if common is not None else load_common_whitelist()
        self.default_sprite = default_sprite
        self.default_background = default_background
        self._rules = rules if rules is not None else load_prompt("director_rules")
        self._state: VisualState | None = None   # 未开始 = None（冷启动）
        self._unchanged = 0                      # 表情连续保持场数（nudge）
        self._llm_failures = 0
        self._llm_down = False

    # ------------------------------------------------------------------
    # 公共
    # ------------------------------------------------------------------

    def visual_for(self, text: str, *, is_end: bool = False) -> VisualState:
        """对一场剧情定 sprite/background, 更新视觉记忆, 返回新 VisualState。"""
        emotions = self.catalog.sprite_emotions(self.char_id)
        bg_scenes = set(self.catalog.background_scenes())
        dirs = set(self.catalog.background_dirs())

        prev = self._state
        base = prev or VisualState(
            sprite=self.default_sprite, background=self.default_background)

        llm_out = self._llm_suggest_call1(text, base, emotions, is_end)
        background = self._decide_background(llm_out, bg_scenes, dirs, base, text)
        sprite = self._decide_sprite(llm_out, text, emotions, base)

        new = VisualState(sprite=sprite, background=background)
        self._state = new
        if prev is None:
            self._unchanged = 0
        elif sprite == prev.sprite:
            self._unchanged += 1
        else:
            self._unchanged = 0
        return new

    def reset(self) -> None:
        """新会话清空视觉记忆与计数（引擎 start_session 调用）。"""
        self._state = None
        self._unchanged = 0
        self._llm_failures = 0
        self._llm_down = False

    @property
    def state(self) -> VisualState:
        """当前视觉记忆（未开始 → 冷启动默认）。"""
        return self._state or VisualState(
            sprite=self.default_sprite, background=self.default_background)

    @property
    def unchanged(self) -> int:
        """表情连续保持场数（nudge 用 / 测试断言）。"""
        return self._unchanged

    # ------------------------------------------------------------------
    # 决策链
    # ------------------------------------------------------------------

    def _decide_sprite(self, llm_out, text: str, emotions: list[str], base: VisualState) -> str:
        cand = llm_out.sprite if llm_out else None
        # 1) 导演合法（catalog 白名单）
        if cand and cand in emotions:
            return cand
        # 2) 正则: 导演不可用（无 LLM / 已禁用）当驱动器逐场推断;
        #    导演可用时仅冷启动（尚无已定状态）, 防正则抖动盖过导演选择
        if not self._llm_active() or self._state is None:
            inferred = infer_sprite(text, emotions)
            if inferred is not None:
                return inferred
        # 3) 状态保持（上一场仍合法）
        if base.sprite in emotions:
            return base.sprite
        # 4) 默认（白名单内首选, 否则硬默认）
        if self.default_sprite in emotions:
            return self.default_sprite
        return emotions[0] if emotions else self.default_sprite

    def _decide_background(
        self, llm_out, bg_scenes: set[str], dirs: set[str], base: VisualState, text: str,
    ) -> str:
        cand = llm_out.background if llm_out else None
        # 1) 导演直给合法 scene_id → 用
        if cand and cand in bg_scenes:
            return cand
        # 2) 导演给目录名 → 第二段: 目录内容拍板（拍板失败 → 走保持, 宁缺勿错）
        if cand and cand in dirs and self._llm_active():
            scenes = self.catalog.background_scenes_in_dir(cand)
            if scenes:
                out2 = self._llm_suggest_drill(cand, scenes, base, text)
                if out2 is not None and out2.background in set(scenes):
                    return out2.background
        # 3) 状态保持（上一场仍合法）
        if base.background in bg_scenes:
            return base.background
        # 4) 默认 neutral（冷启动; 渲染面映射"无背景/纯色"）
        return self.default_background

    # ------------------------------------------------------------------
    # 导演 LLM 调用（含降级）
    # ------------------------------------------------------------------

    def _llm_active(self) -> bool:
        """导演 LLM 是否可用（未注入 / 已禁用 → False, 走降级链）。"""
        return self.llm is not None and not self._llm_down

    def _llm_suggest_call1(self, text: str, base: VisualState, emotions: list[str], is_end: bool):
        if not self._llm_active():
            return None
        nudge = self._unchanged >= self.nudge_after
        prompt = build_director_prompt(
            rules=self._rules,
            persona=self.persona,
            state=base,
            emotions=emotions,
            common_scenes=self._common["scenes"],
            common_dirs=self._common["dirs"],
            trigger_reason=self.trigger_reason,
            nudge=nudge,
            unchanged=self._unchanged,
            is_end=is_end,
            text=text,
        )
        return self._call_llm(prompt)

    def _llm_suggest_drill(self, dir_name: str, scenes: list[str], base: VisualState, text: str):
        if not self._llm_active():
            return None
        prompt = build_drill_prompt(dir_name=dir_name, scenes=scenes, state=base, text=text)
        return self._call_llm(prompt)

    def _call_llm(self, prompt: str):
        """调导演 LLM; 失败计数 ≥2 → 本轮禁用（宁缺勿错, VN 不阻断）。"""
        try:
            out = self.llm.suggest(prompt)
        except DirectorLLMError as e:
            self._llm_failures += 1
            if self._llm_failures >= 2:
                self._llm_down = True
                logger.warning(
                    "导演 LLM 连续失败 %d 次, 本轮降级正则+默认: %s",
                    self._llm_failures, e,
                )
            return None
        self._llm_failures = 0
        return out
