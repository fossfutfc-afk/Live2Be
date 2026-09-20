"""Stream display strategies — LLM token → 屏幕呈现的中间层。

MomoTalkOutput  — 手机聊天: LineBuffer 断句 + 去括号 + TypingDelay 自动延迟
BondStoryOutput — 视觉小说: 累积全文, 按段落分割, UI 层控制打字 & Enter 推进

职责边界:
    Engine 负责: 调 LLM + 管理会话历史
    Display 负责: 如何把 token 流变成可显示单元

用法:
    from core.ui.display import MomoTalkOutput, BondStoryOutput
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from core.ui.streaming import DisplayStep, LineBuffer, TypingDelay, chunk_typing_time
from core.ui.text_processors import (
    _strip_action_brackets,
    format_momotalk_bubble,
    split_reply_chunks,
)


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

    def publish_reply(self, reply: str) -> list[DisplayStep]:
        """非流式: 完整回复 → 显示步骤序列（全 JSON 动作 loop 用）。

        去括号 → 字数+随机数切块（split_reply_chunks）→ 每块前插"…"
        打字指示（delay = 该块打字时长）→ 气泡步骤。返回步骤列表, 由 UI
        依序渲染（CLI 用 simulate_steps; GUI 动画自取 typing 标志）。
        """
        text = _strip_action_brackets(reply).strip()
        if not text:
            return []
        steps: list[DisplayStep] = []
        for chunk in split_reply_chunks(text):
            formatted = format_momotalk_bubble(chunk, self._name)
            if not formatted:
                continue
            steps.append(DisplayStep("…", chunk_typing_time(chunk), typing=True))
            steps.append(DisplayStep(formatted, 0.0))
        return steps


# ============================================================================
# 羁绊剧情显示策略
# ============================================================================

class BondStoryOutput:
    """视觉小说显示策略。

    token 流式来 → 内部累积 → flush 时按双换行（段落）分割。
    不去括号（羁绊剧情允许动作描写），不断句，不加名字前缀。

    用法:
        display = BondStoryOutput()
        for token in llm_stream:
            display.feed(token)
        for i, para in enumerate(display.flush()):
            ui_show_paragraph(para, is_last=(i == len - 1))

    ⚠️ 2026-09-21: 原 `get_current_text()`（"UI 层可轮询它做打字动画"）已删——
    零消费者; webgui 的打字机自己维护缓冲, 不走这里。
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

    def flush(self) -> list[str]:
        """流结束，按段落分割返回完整文本列表。"""
        text = self._buf.strip()
        self._buf = ""
        if not text:
            return []
        paragraphs = re.split(r"\n{2,}", text)
        return [p.strip() for p in paragraphs if p.strip()]


# ============================================================================
# IDE agent 显示策略
# ============================================================================

@dataclass(frozen=True)
class IDEDisplayItem:
    """IDE agent 事件的显示单元。

    text — CLI 直接 print 的渲染文本（与现状逐字节一致；无 CLI 表示时为空串）
    data — GUI/SSE 的结构化载荷（前端按 kind 渲染）
    kind — 事件类别（与 AgentEventKind 同名，GUI 用它分发）
    """

    kind: str
    text: str
    data: dict = field(default_factory=dict)


class IDEOutput:
    """IDE agent 事件流 → 统一显示单元（第三种展示策略）。

    无状态纯函数：render(event) → IDEDisplayItem，恒有返回。
    event 是 AgentEvent.to_dict() 的产物（ide/ide_events.py 定义），本类只认
    kind / data / approval_id / step 四个键——不 import ide.ide_events，
    ui/ 保持零引擎依赖。

    CLI 无文本的事件（THINKING / TOOL_START / INVALID_ACTION / LLM_ERROR /
    PLAN_ERROR）text 为空串：CLI emit 侧跳过空文本，保证 python -m ide.ide_agent
    的输出与现状逐字节一致；GUI 侧按 kind 正常渲染这些状态。

    render 契约（event.data 的键）:
        AI_MESSAGE       {"message"}
        PENDING_APPROVAL {"summary", "diff", "action"}   + 顶层 approval_id
        DECISION         {"choice": "reject" | "abort"}
        EXEC_RESULT      {"ok": bool, "message"}
        COMMAND_RESULT   {"text", "terminal"}   # /view /edit 本地命令输出
        ASK_USER         {"prompt"}             # 轻量提问; 顶层 approval_id 关联答案
        TOOL_START       {"name", "label"}
        TOOL_RESULT      {"name", "label", "chars"}
        TOOL_ERROR       {"name", "label", "error"}
        DONE             {"message"}
        THINKING / INVALID_ACTION / LLM_ERROR / PLAN_ERROR / ABORTED  无载荷

    用法（Phase 2 emit 回调注入）:
        item = ide_output.render(event.to_dict())
        if item.text:
            print(item.text)          # CLI
        hub.publish(item.data)        # GUI → SSE
    """

    #: 无 CLI 文本的事件——GUI 才渲染（ASK_USER 的提问文本走 ask 回调的 input 提示）
    _GUI_ONLY = frozenset({
        "THINKING", "TOOL_START", "INVALID_ACTION", "LLM_ERROR", "PLAN_ERROR",
        "ASK_USER",
    })

    def render(self, event: dict) -> IDEDisplayItem:
        kind = event.get("kind", "")
        data = dict(event.get("data") or {})
        if kind == "PENDING_APPROVAL":
            data["approval_id"] = event.get("approval_id") or data.get("approval_id")
        return IDEDisplayItem(kind=kind, text=self._render_text(kind, data), data=data)

    # ------------------------------------------------------------------
    # 内部：CLI 文本渲染（逐字节复刻 ide/ide_agent.py 现有 print）
    # ------------------------------------------------------------------

    def _render_text(self, kind: str, data: dict) -> str:
        if kind == "AI_MESSAGE":
            return f"\n[AI] {data.get('message', '')}"
        if kind == "PENDING_APPROVAL":
            return (
                f"\n[AI 提议] {data.get('summary', '')}\n"
                f"{data.get('diff', '')}"
            )
        if kind == "DECISION":
            if data.get("choice") == "abort":
                return "[已中止本轮]"
            return "[已拒绝]"  # reject 及未知 choice
        if kind == "ABORTED":
            return "[已中止本轮]"
        if kind == "EXEC_RESULT":
            if data.get("ok"):
                return f"[已执行] {data.get('message', '')}"
            return f"[执行失败] {data.get('message', '')}"
        if kind == "COMMAND_RESULT":
            text = data.get("text", "")
            return f"\n[命令]\n{text}" if text else ""
        if kind == "TOOL_RESULT":
            return (
                f"[{data.get('name', '')} {data.get('label', '')}] "
                f"已获取 {data.get('chars', 0)} 字符"
            )
        if kind == "TOOL_ERROR":
            return f"[{data.get('name', '')}失败] {data.get('error', '')}"
        if kind == "DONE":
            return f"\n[AI] {data.get('message', '')}"
        return ""  # _GUI_ONLY 事件 / 未知 kind
