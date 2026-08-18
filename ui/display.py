"""Stream display strategies — LLM token → 屏幕呈现的中间层。

MomoTalkOutput  — 手机聊天: LineBuffer 断句 + 去括号 + TypingDelay 自动延迟
BondStoryOutput — 视觉小说: 累积全文, 按段落分割, UI 层控制打字 & Enter 推进

职责边界:
    Engine 负责: 调 LLM + 管理会话历史
    Display 负责: 如何把 token 流变成可显示单元

用法:
    from ui.display import MomoTalkOutput, BondStoryOutput
"""

from __future__ import annotations

import re
from collections.abc import Callable

from ui.streaming import LineBuffer, TypingDelay
from ui.text_processors import format_momotalk_bubble


# ============================================================================
# MomoTalk 显示策略
# ============================================================================

class MomoTalkOutput:
    """手机聊天显示策略。

    封装 LineBuffer 断句、文本处理、名字前缀格式化、打字延迟计算。
    调用方只需 feed(token) → flush() 即可获得可直接显示的气泡。

    用法:
        display = MomoTalkOutput(_process_for_momotalk, "伊草 遥香")
        for token in llm_stream:
            for bubble, delay in display.feed(token):
                show_bubble(bubble, delay)
        for bubble, delay in display.flush():
            show_bubble(bubble, delay)
    """

    def __init__(self, text_processor: Callable[[str], list[str]], name: str):
        self._lb = LineBuffer()
        self._processor = text_processor
        self._name = name
        self._delay = TypingDelay()

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def _publish(self, text: str):
        """渲染一条文本 → (气泡, 延迟) 序列。feed/flush 共用。"""
        for processed in self._processor(text):
            formatted = format_momotalk_bubble(processed, self._name)
            if formatted:
                yield formatted, self._delay.for_bubble(formatted)

    def feed(self, token: str):
        """喂入 SSE token，yield (formatted_bubble, delay_seconds)。"""
        for bubble in self._lb.feed(token):
            yield from self._publish(bubble)

    def flush(self):
        """流结束，处理 LineBuffer 残留文本。yield (formatted_bubble, delay_seconds)。"""
        remaining = self._lb.flush()
        if remaining:
            yield from self._publish(remaining)


# ============================================================================
# 羁绊剧情显示策略
# ============================================================================

class BondStoryOutput:
    """视觉小说显示策略。

    token 流式来 → 内部累积 → flush 时按双换行（段落）分割。
    不去括号（羁绊剧情允许动作描写），不断句，不加名字前缀。

    UI 层在流式期间可通过 get_current_text() 轮询当前文本，
    实现逐字打字动画；按 Enter 时跳过动画直接显示完整文本。

    用法:
        display = BondStoryOutput()
        for token in llm_stream:
            display.feed(token)
            # 可选: UI 轮询 display.get_current_text() 做打字效果
        for i, para in enumerate(display.flush()):
            ui_show_paragraph(para, is_last=(i == len - 1))
    """

    def __init__(self):
        self._buf = ""

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def feed(self, token: str) -> list:
        """喂入 token 并累积。返回空列表（流中不 yield，由 UI 轮询）。"""
        self._buf += token
        return []

    def get_current_text(self) -> str:
        """返回当前累积的全部文本（供 UI 逐字渲染）。"""
        return self._buf

    def flush(self) -> list[str]:
        """流结束，按段落分割返回完整文本列表。"""
        text = self._buf.strip()
        self._buf = ""
        if not text:
            return []
        paragraphs = re.split(r"\n{2,}", text)
        return [p.strip() for p in paragraphs if p.strip()]
