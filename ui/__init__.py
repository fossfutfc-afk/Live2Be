"""ui — 展示层（纯逻辑，零引擎依赖）。

从 core/ 移出的可复用展示组件:
    streaming        LineBuffer 断句 + TypingDelay 打字延迟
    text_processors  MomoTalk 文本处理（去括号/断句/前缀格式化）
    display          MomoTalkOutput / BondStoryOutput 两种流式渲染策略

供主项目（core.momotalk / core.bond_story）与 web/ GUI 复用。
"""

from __future__ import annotations

from ui.display import BondStoryOutput, MomoTalkOutput
from ui.streaming import LineBuffer, TypingDelay, simulate_typing
from ui.text_processors import (
    _process_for_momotalk,
    _split_for_momotalk,
    _strip_action_brackets,
    format_momotalk_bubble,
    format_momotalk_reply,
    strip_name_prefix,
)

__all__ = [
    "BondStoryOutput",
    "LineBuffer",
    "MomoTalkOutput",
    "TypingDelay",
    "_process_for_momotalk",
    "_split_for_momotalk",
    "_strip_action_brackets",
    "format_momotalk_bubble",
    "format_momotalk_reply",
    "simulate_typing",
    "strip_name_prefix",
]
