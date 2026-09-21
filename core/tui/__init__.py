"""`core.tui` — 终端展示层（纯逻辑，零引擎依赖）。

（C11 从 `core/ui/` 搬来: `ui` 这个名字要和 web GUI 区分开, 后者在 `webgui/`。）

可复用展示组件:
    streaming        LineBuffer 断句 + TypingDelay 打字延迟
    text_processors  MomoTalk 文本处理（去括号/断句/前缀格式化）
    display          MomoTalkOutput / BondStoryOutput / IDEOutput 三种渲染策略

供 `core.momotalk` / `core.session.renderer` / `webgui.chat` 与 CLI/实验脚本复用。
⚠️ **不 import `renderer`**（那是 CLI 应用 `core/ui/vn_cli.py` 的事, 归 C12 搬 `apps/`）。
"""

from __future__ import annotations

from core.tui.display import BondStoryOutput, IDEDisplayItem, IDEOutput, MomoTalkOutput
from core.tui.streaming import (
    DisplayStep,
    LineBuffer,
    TypingDelay,
    chunk_typing_time,
    simulate_steps,
    simulate_typing,
)
from core.tui.text_processors import (
    _process_for_momotalk,
    _split_for_momotalk,
    _strip_action_brackets,
    format_momotalk_bubble,
    format_momotalk_reply,
    split_reply_chunks,
    strip_name_prefix,
)

__all__ = [
    "BondStoryOutput",
    "DisplayStep",
    "IDEDisplayItem",
    "IDEOutput",
    "LineBuffer",
    "MomoTalkOutput",
    "TypingDelay",
    "_process_for_momotalk",
    "_split_for_momotalk",
    "_strip_action_brackets",
    "chunk_typing_time",
    "format_momotalk_bubble",
    "format_momotalk_reply",
    "simulate_steps",
    "simulate_typing",
    "split_reply_chunks",
    "strip_name_prefix",
]
