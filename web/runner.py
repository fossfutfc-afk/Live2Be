"""web/runner.py — AgentRunner: 单 IDEAgent + turn 串行化 + ask 桥 + auto-approve。

把 IDEAgent 的阻塞回调桥接到异步事件/决策通道:
    emit  → hub.publish(channel, evt.to_dict())   （线程安全, 直接发布）
    ask   → 轮询 decision_q: 用户决策 / auto-approve 取消窗口 / 超时 abort

关键护栏: ASK_TIMEOUT 超时 → abort——worker 不会永久占锁导致后续 turn 全部 409。
"""
from __future__ import annotations

import os
import queue
import threading
import time
from pathlib import Path
from typing import Any

from fetch.agent import IDEAgent
from fetch.events import ApprovalDecision
from web.hub import EventHub, HUBS

#: ask 桥默认超时（秒）——页面被关/无人响应时 worker 不永久占锁
ASK_TIMEOUT = float(os.getenv("IDE_ASK_TIMEOUT", "300"))
#: auto-approve 默认窗口（秒）
AUTO_APPROVE_DELAY = float(os.getenv("IDE_AUTO_DELAY", "2.0"))
#: ask 桥轮询间隔（秒）
_POLL = 1.0


class AgentRunner:
    """包装单个 IDEAgent。多标签页共享同一实例（同一对话流, 见 DESIGN §2.2）。"""

    def __init__(self, llm: Any, root: str | Path = ".",
                 *, hub: EventHub | None = None, channel: str = "ide",
                 ask_timeout: float = ASK_TIMEOUT,
                 auto_delay: float = AUTO_APPROVE_DELAY) -> None:
        self.hub = hub if hub is not None else HUBS.get(channel)
        self.channel = channel
        self.ask_timeout = ask_timeout
        self._auto_approve = False
        self.auto_delay = auto_delay
        self._decisions: queue.Queue[tuple[str, ApprovalDecision]] = queue.Queue()
        self._lock = threading.Lock()
        self._busy = False
        self.agent = IDEAgent(llm, root=root, emit=self._emit, ask=self._ask)

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._busy

    def status(self) -> dict:
        return {"busy": self._busy, "auto_approve": self._auto_approve,
                "auto_delay": self.auto_delay}

    def set_auto_approve(self, enabled: bool, delay_s: float | None = None) -> None:
        """开关 auto-approve; delay_s 可选更新窗口时长。"""
        self._auto_approve = bool(enabled)
        if delay_s is not None and delay_s > 0:
            self.auto_delay = float(delay_s)

    def close(self) -> None:
        """关服时关闭 LLM 客户端（若实现了 close）。"""
        closer = getattr(self.agent.llm, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:  # noqa: BLE001 — 关服清理, 不抛
                pass

    # ------------------------------------------------------------------
    # turn 串行化
    # ------------------------------------------------------------------

    def start_turn(self, message: str) -> bool:
        """非阻塞启动一轮。busy 时返回 False（HTTP 层映射为 409）。"""
        if not self._lock.acquire(blocking=False):
            return False
        self._busy = True
        threading.Thread(target=self._run_turn, args=(message,), daemon=True).start()
        return True

    def _run_turn(self, message: str) -> None:
        try:
            self.agent.agent_turn(message)
        except Exception as e:  # noqa: BLE001 — 兜底: 任何异常都不能挂死锁
            self.hub.publish({
                "kind": "LLM_ERROR", "step": -1,
                "data": {"error": f"turn 异常: {e}"}, "approval_id": None,
            })
        finally:
            self._busy = False
            self._lock.release()

    # ------------------------------------------------------------------
    # emit / ask 桥
    # ------------------------------------------------------------------

    def _emit(self, evt: Any) -> None:
        """IDEAgent emit 回调 → 发布到 hub（hub 已绑定本 runner 的 channel）。"""
        self.hub.publish(evt.to_dict())

    def submit_decision(self, approval_id: str, decision: ApprovalDecision) -> None:
        """HTTP 层把 /api/approve 决策投入 ask 队列（线程安全）。"""
        self._decisions.put((approval_id, decision))

    def _ask(self, approval_id: str, prompt: str) -> ApprovalDecision:
        """IDEAgent ask 回调 → 阻塞直到决策/auto-approve/超时。worker 线程调用。"""
        del prompt
        started = time.monotonic()
        while True:
            elapsed = time.monotonic() - started
            try:
                aid, decision = self._decisions.get(timeout=_POLL)
            except queue.Empty:
                if self._auto_approve and elapsed >= self.auto_delay:
                    return "approve"
                if elapsed >= self.ask_timeout:
                    return "abort"
                continue
            if aid == approval_id:
                return decision
            # 过期/其他审批实例的决策 → 忽略, 继续等
