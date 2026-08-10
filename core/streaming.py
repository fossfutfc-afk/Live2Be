"""流式输出工具 — LineBuffer + 打字延迟。

LineBuffer:
    接收 SSE token 流 → 累积到断点（。！？…）→ 产生完整气泡。
    配合 LLM streaming API 实现"对方正在打字"的手机体验。

TypingDelay:
    基于文本长度计算延迟时间，模拟真人打字速度。
    第一句不延迟（TTFT 已充当自然延迟）。

用法:
    lb = LineBuffer()
    for token in llm_stream:
        for bubble in lb.feed(token):
            delay = TypingDelay.for_bubble(bubble, is_first)
            typing_animation(bubble, delay)
            is_first = False
    final = lb.flush()
"""

from __future__ import annotations

import random
import re
import time

# ---------------------------------------------------------------------------
# LineBuffer
# ---------------------------------------------------------------------------

# 断点标点 — 这些符号出现时认为一句话说完了
_BREAK_PUNCT = re.compile(r"[。！？\.!\?…\n]")


class LineBuffer:
    """累积 token 流，在断点处产生完整气泡。

    用法:
        lb = LineBuffer()
        for chunk in llm_stream:
            for bubble in lb.feed(chunk):
                yield bubble   # 完整的一句话
        remainder = lb.flush()  # 流结束，取出剩余片段
    """

    def __init__(self):
        self._buf: str = ""

    def feed(self, text: str) -> list[str]:
        """喂入一个 token 片段；返回已完成的句子列表。"""
        self._buf += text

        # 如果缓冲区还没有断点标点，不切
        if not _BREAK_PUNCT.search(self._buf):
            return []

        # 找到最后一个断点的位置
        parts = _BREAK_PUNCT.split(self._buf)
        # parts 最后一个元素是断点后的剩余（可能为空或不完整）
        # 把断点标点加回每个完整部分
        result: list[str] = []
        cursor = 0
        for m in _BREAK_PUNCT.finditer(self._buf):
            end = m.end()
            # 如果后面还有内容且已经又出现了断点 → 前面的就是完整的
            # 简化处理：遇到断点就切，但保留最后一个断点之后的作为 buf
            pass

        # 简化实现：找最后一个断点位置，之前的部分全切走
        last_break = 0
        for m in _BREAK_PUNCT.finditer(self._buf):
            last_break = m.end()

        if last_break > 0:
            complete = self._buf[:last_break]
            self._buf = self._buf[last_break:]
            # 按断点切分（每个断点后一段）
            segments = _BREAK_PUNCT.split(complete)
            # 重建：把断点贴回去
            puncts = _BREAK_PUNCT.findall(complete)
            for i, seg in enumerate(segments):
                seg = seg.strip()
                if not seg:
                    continue
                if i < len(puncts):
                    result.append(seg + puncts[i])
                else:
                    # 最后一个 segment 可能没有跟随的断点
                    if seg.strip():
                        result.append(seg)

        return result

    def flush(self) -> str | None:
        """流结束，取出剩余文本。"""
        leftover = self._buf.strip()
        self._buf = ""
        return leftover if leftover else None


# ---------------------------------------------------------------------------
# TypingDelay
# ---------------------------------------------------------------------------

# 打字速度配置（毫秒）
_CHAR_DELAY_MIN = 60    # 每字最短延迟
_CHAR_DELAY_MAX = 120   # 每字最长延迟（随机抖动用）
_BUBBLE_PAUSE = 400     # 气泡间的额外停歇


class TypingDelay:
    """计算气输出泡的延迟时间，模拟真人打字。

    第一句不延迟 — TTFT 已经提供了自然等待。
    """

    _first: bool = True

    @classmethod
    def for_bubble(cls, text: str) -> float:
        """返回该气泡应延迟的秒数。第一句返回 0。"""
        if cls._first:
            cls._first = False
            return 0.0
        char_count = len(text)
        # 每字延迟 + 气泡间停顿 + 随机抖动
        base = char_count * (_CHAR_DELAY_MIN + _CHAR_DELAY_MAX) / 2 / 1000.0
        jitter = random.uniform(-0.1, 0.1) * char_count / 1000.0
        return max(0, base + jitter + _BUBBLE_PAUSE / 1000.0)

    @classmethod
    def reset(cls) -> None:
        """重置首句标记（新对话时调用）。"""
        cls._first = True


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

def simulate_typing(text: str, delay: float) -> None:
    """逐字打印文本，模拟打字效果（CLI 用）。"""
    for ch in text:
        print(ch, end="", flush=True)
        char_delay = random.uniform(_CHAR_DELAY_MIN, _CHAR_DELAY_MAX) / 1000.0
        time.sleep(char_delay)
    time.sleep(delay)
