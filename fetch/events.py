"""fetch/events.py — IDE agent 事件模型。

agent_turn 运行时产生的离散事件，统一经 emit 回调输出：
    CLI 默认 emit 直接 print（逐字节复刻历史输出）；
    GUI 注入队列实现（web/runner.py）。

显示侧契约: AgentEvent.to_dict() 的产物直接喂给 ui.IDEOutput.render()——
    {"kind": str, "step": int, "data": dict, "approval_id": str|None}
kind 取 AgentEventKind 的字符串值，与 IDEOutput 的 render 契约一一对应。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable, Literal


class AgentEventKind(StrEnum):
    """事件类别。to_dict() 里 kind 用枚举字符串值（与 ui.IDEOutput 契约一致）。"""

    THINKING = "THINKING"
    AI_MESSAGE = "AI_MESSAGE"
    INVALID_ACTION = "INVALID_ACTION"
    LLM_ERROR = "LLM_ERROR"
    PLAN_ERROR = "PLAN_ERROR"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    DECISION = "DECISION"
    TOOL_START = "TOOL_START"
    TOOL_RESULT = "TOOL_RESULT"
    TOOL_ERROR = "TOOL_ERROR"
    EXEC_RESULT = "EXEC_RESULT"
    DONE = "DONE"
    ABORTED = "ABORTED"


@dataclass(frozen=True)
class AgentEvent:
    """一条 agent 运行时事件。

    data — 事件载荷（见 AgentEventKind 各自约定）;
    approval_id — 仅 PENDING_APPROVAL 携带，供 GUI 把 /api/approve 决策
                  关联回本次提案。
    """

    kind: AgentEventKind
    step: int
    data: dict = field(default_factory=dict)
    approval_id: str | None = None

    def to_dict(self) -> dict:
        """→ ui.IDEOutput.render() 消费的结构。"""
        return {
            "kind": self.kind.value,
            "step": self.step,
            "data": dict(self.data),
            "approval_id": self.approval_id,
        }


# ---------------------------------------------------------------------------
# 回调类型
# ---------------------------------------------------------------------------

#: 审批决策（GUI / CLI 统一的归一化结果）
ApprovalDecision = Literal["approve", "reject", "abort"]

#: 事件输出回调: emit(event)
EmitFn = Callable[[AgentEvent], None]

#: 审批回调: ask(approval_id, prompt) → decision（阻塞直到用户决策）
AskFn = Callable[[str, str], ApprovalDecision]
