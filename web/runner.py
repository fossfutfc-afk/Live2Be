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

from fetch import commands
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
            if self._dispatch_command(message):
                return
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
    # 本地命令路由（/view /edit）——与 CLI 共享 fetch.commands 纯逻辑
    # ------------------------------------------------------------------

    def _dispatch_command(self, message: str) -> bool:
        """返回 True = 已按本地命令处理（不再走 LLM）。"""
        try:
            cmd = commands.parse_cmd(message)
        except commands.CmdError as e:
            self._publish_command(f"[命令错误] {e}")
            return True
        if cmd is None:
            if message.lstrip().startswith("/"):
                # 未知命令/错别字（如 /veiw）→ 提示, 不回灌 LLM 烧 token
                self._publish_command(
                    "未知命令——可用: /view <角色>[/<文件>]  "
                    "/edit <角色>/<文件> 键: 值"
                )
                return True
            return False
        if cmd.verb == "view":
            try:
                text = commands.cmd_view(self.agent.executor.root, cmd)
            except commands.CmdError as e:
                text = f"[命令错误] {e}"
            self._publish_command(text)
            return True
        if cmd.verb == "edit":
            self._run_edit_command(cmd)
            return True
        return False

    def _publish_command(self, text: str) -> None:
        """命令的终态事件: 前端渲染 text 并复位 busy（terminal=True）。"""
        self.hub.publish({
            "kind": "COMMAND_RESULT", "step": 0,
            "data": {"text": text, "terminal": True}, "approval_id": None,
        })

    def _run_edit_command(self, cmd: commands.Cmd) -> None:
        """/edit 复用现有审批卡 + ask 桥（零并行 UI）: PENDING → 决策 → EXEC。"""
        if not cmd.snippet:
            self._publish_command(
                "补丁为空——请用行内 `键: 值` 或多行粘贴。\n"
                "例: /edit igusa_haruka/profile.yml SIG~age: 16"
            )
            return
        try:
            diff, action = commands.cmd_edit_plan(
                self.agent.executor.root, cmd, cmd.snippet
            )
        except commands.CmdError as e:
            self._publish_command(f"[命令错误] {e}")
            return
        if not diff.strip() or "[无变化]" in diff:
            self._publish_command("无变化（补丁与现有内容一致）。")
            return

        # 发起审批: approval_id 复用 agent 计数, 与 AI 写动作的提案不冲突
        self.agent._approval_seq += 1
        approval_id = f"approval-{self.agent._approval_seq}"
        self.hub.publish({
            "kind": "PENDING_APPROVAL", "step": 0,
            "data": {"summary": f"本地编辑 {cmd.char_id}/{cmd.file}",
                     "diff": diff, "action": action.to_dict()},
            "approval_id": approval_id,
        })

        decision = self._ask(approval_id, "本地编辑")
        if decision == "approve":
            try:
                message = commands.cmd_edit_execute(self.agent.executor.root, action)
            except commands.CmdError as e:
                self.hub.publish({
                    "kind": "EXEC_RESULT", "step": 0,
                    "data": {"ok": False, "message": str(e)}, "approval_id": None,
                })
                self._publish_command("")
                return
            self.hub.publish({
                "kind": "EXEC_RESULT", "step": 0,
                "data": {"ok": True, "message": message}, "approval_id": None,
            })
        elif decision == "reject":
            self.hub.publish({
                "kind": "DECISION", "step": 0,
                "data": {"choice": "reject"}, "approval_id": None,
            })
        else:  # abort
            self.hub.publish({
                "kind": "ABORTED", "step": 0, "data": {}, "approval_id": None,
            })
            return  # ABORTED 前端已复位 busy, 无需 terminal 事件
        self._publish_command("")

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
