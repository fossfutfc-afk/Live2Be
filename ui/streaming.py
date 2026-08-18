"""流式输出工具 — LineBuffer + 打字延迟。

LineBuffer:
    接收 SSE token 流 → 累积到断点（。！？…）→ 产生完整气泡。
    配合 LLM streaming API 实现"对方正在打字"的手机体验。

TypingDelay:
    基于文本长度计算延迟时间，模拟真人打字速度。
    第一句不延迟（TTFT 已充当自然延迟）。

用法:
    lb = LineBuffer()
    delay = TypingDelay()
    for token in llm_stream:
        for bubble in lb.feed(token):
            typing_animation(bubble, delay.for_bubble(bubble))
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
_BREAK_CHARS = "。！？.!?…\n"
_BREAK_PUNCT = re.compile(f"[{_BREAK_CHARS}]")


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
        # 孤立断点标点（chunk 边界遗留/连续标点无前文可贴）→ 攒着贴给下一个文本段
        self._pending_punct: str = ""

    def feed(self, text: str) -> list[str]:
        """喂入一个 token 片段；返回已完成的句子列表。"""
        self._buf += text

        # 还没有断点标点 → 继续累积, 不切
        if not _BREAK_PUNCT.search(self._buf):
            return []

        # 找最后一个断点位置, 之前的部分整体切走
        last_break = 0
        for m in _BREAK_PUNCT.finditer(self._buf):
            last_break = m.end()
        complete = self._buf[:last_break]
        self._buf = self._buf[last_break:]

        # 逐字符重建: 每个文本段带上紧跟它的所有断点标点。
        #   连续/尾部标点（如 "！！"）→ 贴到上一个已完成段, 不丢
        #   孤立标点（chunk 开头, 无前文可贴）→ 攒着, 留给下一个文本段
        # 保证任何 chunk 划分都不丢字符（flush 兜底）。
        result: list[str] = []
        pending = self._pending_punct  # 带入上次遗留
        self._pending_punct = ""
        buf = ""
        for ch in complete:
            if ch in _BREAK_CHARS:
                if buf:
                    result.append(buf + ch)
                    buf = ""
                elif result:
                    result[-1] += ch  # 连续/尾部标点 → 贴到上一个已完成段
                else:
                    pending += ch     # 孤立标点（无前文可贴）→ 留给下个文本段
            else:
                if pending:
                    buf = pending + ch
                    pending = ""
                else:
                    buf += ch
        if buf:
            result.append(buf)
        elif pending:
            self._pending_punct = pending  # 本 complete 全是标点 → 留给下个文本段
        return result

    def flush(self) -> str | None:
        """流结束，取出剩余文本（含遗留标点）。"""
        leftover = (self._pending_punct + self._buf).strip()
        self._pending_punct = ""
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
    """计算输出气泡的延迟时间，模拟真人打字。

    第一句不延迟 — TTFT 已经提供了自然等待。
    实例化使用: 每实例独立维护首句标记, 多个 display 并存互不影响。
    """

    def __init__(self):
        self._first = True

    def for_bubble(self, text: str) -> float:
        """返回该气泡应延迟的秒数。第一句返回 0。"""
        if self._first:
            self._first = False
            return 0.0
        char_count = len(text)
        # 每字延迟 + 气泡间停顿 + 随机抖动
        base = char_count * (_CHAR_DELAY_MIN + _CHAR_DELAY_MAX) / 2 / 1000.0
        jitter = random.uniform(-0.1, 0.1) * char_count / 1000.0
        return max(0, base + jitter + _BUBBLE_PAUSE / 1000.0)

    def reset(self) -> None:
        """重置首句标记（新对话时调用）。"""
        self._first = True


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
