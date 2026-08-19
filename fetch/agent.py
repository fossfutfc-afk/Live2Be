"""丐中丐 AGENT — IDE 角色撰写会话循环。

用户用自然语言说需求（创建/修改角色、人际关系等），LLM 返回动作 JSON，
契约解析 → 执行层落地。写动作展示 diff、用户批准后才落盘。

核心循环（agent_turn）:
    用户输入
      → 注入动作 schema + 跨轮历史
      → 调 LLM（response_format=json_object）
      → 契约解析（build_ide_registry().parse()）
          ├─ 校验失败 → 回灌错误给 LLM → 重试
          ├─ APPROVAL_REQUIRED（写动作）
          │     executor.plan → 展示 diff → 用户批准 → executor.execute
          │     拒绝/失败 → 回灌 → 继续
          ├─ fetch_url → executor 抓取 → 结果回灌 → 继续
          └─ done → 收尾, 控制权交回用户

输出经 emit 回调、审批经 ask 回调:
    CLI 默认实现复刻 print/input（输出逐字节不变），
    GUI 注入队列实现（见 fetch.events + ui.IDEOutput）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from contract import (
    APPROVAL_REQUIRED,
    build_schema,
)
from fetch import commands
from fetch.actions import build_ide_registry
from fetch.events import (
    AgentEvent,
    AgentEventKind,
    ApprovalDecision,
    AskFn,
    EmitFn,
)
from fetch.executor import ExecError, Executor
from ui.display import IDEOutput

MAX_STEPS = 12          # 单轮 agent 最大动作步数（防死循环）
HISTORY_MAX = 30        # 跨轮记忆条数上限（去掉 system 后）
TEMP = 0.4              # 动作决策用较低温度, 减少随机

# IDE agent 默认用推理模型（v4-flash），配合大 max_tokens 容纳 reasoning_content。
# 推理模型会把 max_tokens 分给"思考"与"内容"两部分——max_tokens 太小会导致
# reasoning 吃光预算、content 为空（实测复现）。非推理模型（如 deepseek-chat 别名）
# 可不依赖大 max_tokens，但依赖其不在官方模型列表、不保证长期可用。
# 可用环境变量 IDE_LLM_MODEL 覆盖。
IDE_MODEL = os.getenv("IDE_LLM_MODEL", "deepseek-v4-flash")

# CLI 审批提示（与历史 input 逐字节一致）
APPROVAL_PROMPT = "\n批准? [y=执行 / n=拒绝 / q=中止本轮] "

# 展示侧规范化器（无状态纯函数, 模块级单例即可）
_IDE_OUTPUT = IDEOutput()

# 角色写作系统提示词（参照 config/characters/igusa_haruka 的高质量结构）
_GUIDE_PATH = Path(__file__).resolve().parent / "prompts" / "character_writer.md"


def _load_guide() -> str:
    try:
        return _GUIDE_PATH.read_text(encoding="utf-8")
    except OSError:
        return (
            "你是 Live2Be 的角色资料撰写助手。创建角色时先 fetch_url 查资料, "
            "按 REQ~/SIG~/无前缀/null 约定产出五件套 YAML, 字段要具体充实。"
            "REQ~/SIG~ 是键前缀字面量（直接写进 YAML 键名）；"
            "profile.yml 必须含非空 REQ~most_called_name（界面显示名）。"
        )


_GUIDE = _load_guide()


class IDEAgent:
    """IDE 撰写 agent。llm: 兼容主项目 llm.client.LLMClient 的对象。"""

    def __init__(self, llm: Any, root: str | Path = ".",
                 *, emit: EmitFn | None = None, ask: AskFn | None = None):
        self.llm = llm
        self.registry = build_ide_registry()
        self.executor = Executor(root)
        self.history: list[dict[str, str]] = []
        # 调试/测试用的逐步记录（每次动作交换一条）
        self.trace: list[dict[str, Any]] = []
        # 输出/审批回调：默认 = CLI（逐字节复刻现有 print/input）
        self._emit = emit or self._default_emit
        self._ask = ask or self._default_ask
        self._approval_seq = 0  # 审批实例计数器（GUI 用 approval_id 关联决策）

    # ------------------------------------------------------------------
    # 默认回调（CLI）——注入 emit/ask 后, 输出与现状逐字节一致
    # ------------------------------------------------------------------

    def _default_emit(self, evt: AgentEvent) -> None:
        """CLI 默认输出：IDEOutput 渲染 → print。

        GUI-only 事件（THINKING 等）text 为空串, 直接跳过。
        """
        item = _IDE_OUTPUT.render(evt.to_dict())
        if item.text:
            print(item.text)

    def _default_ask(self, approval_id: str, prompt: str) -> ApprovalDecision:
        """CLI 默认审批：阻塞 input → approve/reject/abort。"""
        del approval_id  # CLI 单审批流, 无需区分实例
        choice = input(prompt).strip().lower()
        if choice in ("q", "quit"):
            return "abort"
        if choice in ("y", "yes"):
            return "approve"
        return "reject"

    # ------------------------------------------------------------------
    # CLI 主循环
    # ------------------------------------------------------------------

    def run(self) -> None:
        """命令行交互入口。"""
        print("═" * 46)
        print("  Live2Be IDE — 角色资料撰写助手")
        print("  用自然语言描述需求; /view /edit 本地命令; /exit 退出")
        print("═" * 46)
        while True:
            try:
                user_input = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_input:
                continue
            if user_input in ("/exit", "exit", "退出"):
                break
            if user_input.startswith("/"):
                self._run_command(user_input)
                continue
            self.agent_turn(user_input)

    # ------------------------------------------------------------------
    # 本地命令（/view /edit）——确定性操作, 不走 LLM
    # ------------------------------------------------------------------

    def _run_command(self, text: str) -> None:
        try:
            cmd = commands.parse_cmd(text)
        except commands.CmdError as e:
            print(f"[命令] {e}")
            return
        if cmd is None:
            print("[命令] 未知命令——可用: /view <角色>[/<文件>]  /edit <角色>/<文件> 键: 值  /exit")
            return
        try:
            if cmd.verb == "view":
                print(commands.cmd_view(self.executor.root, cmd))
            elif cmd.verb == "edit":
                self._run_edit(cmd)
        except commands.CmdError as e:
            print(f"[命令] {e}")

    def _run_edit(self, cmd: commands.Cmd) -> None:
        snippet = cmd.snippet or self._paste_yaml()
        diff, action = commands.cmd_edit_plan(self.executor.root, cmd, snippet)
        if not diff.strip() or "[无变化]" in diff:
            print("[命令] 无变化（补丁与现有内容一致）。")
            return
        print(diff)
        choice = input("\n应用上面的 diff? [y=应用 / n=放弃] ").strip().lower()
        if choice not in ("y", "yes"):
            print("[命令] 已放弃。")
            return
        print(f"[命令] {commands.cmd_edit_execute(self.executor.root, action)}")

    def _paste_yaml(self) -> str:
        """多行 YAML 补丁粘贴: 空行结束, Ctrl-D/Ctrl-C 取消。"""
        print("粘贴 YAML 补丁（空行结束, Ctrl-D 取消）:")
        lines = []
        try:
            while True:
                line = input()
                if not line.strip():
                    break
                lines.append(line)
        except (EOFError, KeyboardInterrupt):
            print()
            raise commands.CmdError("已取消")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 单轮 agent 循环
    # ------------------------------------------------------------------

    def agent_turn(self, user_input: str) -> None:
        """一轮 agent 对话：LLM 动作循环, 直到 done / 达到步数上限。"""
        messages = [{"role": "system", "content": self._system_prompt()}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_input})

        for step in range(MAX_STEPS):
            self._emit(AgentEvent(AgentEventKind.THINKING, step, {}))
            try:
                response = self.llm.chat(
                    messages, model=IDE_MODEL, temperature=TEMP, max_tokens=16384,
                    response_format="json_object",
                )
            except Exception as e:
                # client.chat(json_object) 失败：网络错误 / JSON 修正重试耗尽
                self._emit(AgentEvent(AgentEventKind.LLM_ERROR, step, {"error": str(e)}))
                messages.append({
                    "role": "user",
                    "content": f"LLM 调用失败: {e}\n请重试。",
                })
                continue
            # client.chat(json_object) 已内置 JSON 清洗与修正重试, 返回 dict。
            # 直接用 registry.parse 契约解析, 不走 parse_action_text（那是给原始文本的）。
            messages.append({"role": "assistant", "content": str(response)})

            action, result = self.registry.parse(response)
            self.trace.append({
                "step": step,
                "llm_response": response,
                "parse_valid": result.is_valid,
                "parse_errors": list(result.errors),
                "parse_warnings": list(result.warnings),
                "action": action.action if action else None,
                "approval": action.approval if action else None,
                "summary": action.summary if action else "",
                "reply": action.reply if action else "",
                "payload": action.payload if action else None,
            })
            if not result.is_valid:
                self._emit(AgentEvent(
                    AgentEventKind.INVALID_ACTION, step, {"errors": list(result.errors)},
                ))
                messages.append({
                    "role": "user",
                    "content": (
                        f"动作无效: {'; '.join(result.errors)}\n"
                        "请严格按 schema 重新输出单个动作 JSON。"
                        "若错误涉及 YAML 字段约定（REQ~/SIG~ 前缀、必填键），"
                        "按系统提示『字段约定』的示例，把前缀字面量写进键名。"
                    ),
                })
                continue

            # AI 对用户的话（任何动作的 reply 都展示）
            if action.reply:
                self._emit(AgentEvent(
                    AgentEventKind.AI_MESSAGE, step, {"message": action.reply},
                ))

            # 写动作 → 审批
            if action.approval == APPROVAL_REQUIRED:
                if self._handle_write(action, messages, step):
                    break
                continue

            # 只读/收尾动作
            if action.action == "done":
                msg = action.summary or action.payload.get("message", "完成")
                self._emit(AgentEvent(AgentEventKind.DONE, step, {"message": msg}))
                break
            if action.action in ("fetch_url", "search"):
                self._handle_tool(action, messages, step)
                continue

        # 跨轮记忆（去掉 system, 截断）
        self.history = messages[1:][-HISTORY_MAX:]

    # ------------------------------------------------------------------
    # 动作处理
    # ------------------------------------------------------------------

    def _handle_write(self, action, messages: list[dict], step: int) -> bool:
        """写动作审批。返回 True = 中止本轮（用户主动退出）。"""
        try:
            plan = self.executor.plan(action)
        except ExecError as e:
            self._emit(AgentEvent(AgentEventKind.PLAN_ERROR, step, {"error": str(e)}))
            messages.append({
                "role": "user",
                "content": f"无法执行: {e}\n请调整后重新输出动作。",
            })
            self.trace.append({"event": "plan_error", "error": str(e)})
            return False

        # 发起审批：approval_id 供 GUI 把 /api/approve 决策关联回本次提案
        self._approval_seq += 1
        approval_id = f"approval-{self._approval_seq}"
        self._emit(AgentEvent(
            AgentEventKind.PENDING_APPROVAL, step,
            {"summary": action.summary, "diff": plan.diff, "action": action.to_dict()},
            approval_id=approval_id,
        ))
        self.trace.append({"event": "plan", "diff": plan.diff})

        decision = self._ask(approval_id, APPROVAL_PROMPT)
        if decision == "abort":
            self._emit(AgentEvent(AgentEventKind.ABORTED, step, {}))
            self.trace.append({"event": "decision", "choice": "abort"})
            return True

        if decision == "approve":
            try:
                result = self.executor.execute(action)
                self._emit(AgentEvent(AgentEventKind.EXEC_RESULT, step,
                                      {"ok": True, "message": result.message}))
                self.trace.append({"event": "decision", "choice": "approved",
                                   "exec_ok": True, "message": result.message})
                messages.append({
                    "role": "user",
                    "content": f"动作已执行: {result.message}",
                })
            except ExecError as e:
                self._emit(AgentEvent(AgentEventKind.EXEC_RESULT, step,
                                      {"ok": False, "message": str(e)}))
                self.trace.append({"event": "decision", "choice": "approved",
                                   "exec_ok": False, "message": str(e)})
                messages.append({
                    "role": "user",
                    "content": f"执行失败: {e}",
                })
        else:
            self._emit(AgentEvent(AgentEventKind.DECISION, step, {"choice": "reject"}))
            self.trace.append({"event": "decision", "choice": "rejected"})
            messages.append({
                "role": "user",
                "content": "用户拒绝了该动作。请按用户反馈调整后再输出。",
            })
        return False

    def _handle_tool(self, action, messages: list[dict], step: int) -> None:
        """只读工具（search / fetch_url）→ 结果回灌给 LLM 继续推理。"""
        name = action.action
        label = action.payload.get("url") or action.payload.get("query") or name
        self._emit(AgentEvent(AgentEventKind.TOOL_START, step,
                              {"name": name, "label": label}))
        try:
            result = self.executor.execute(action)
            self._emit(AgentEvent(AgentEventKind.TOOL_RESULT, step,
                                  {"name": name, "label": label,
                                   "chars": len(result.message)}))
            self.trace.append({"event": name, "label": label,
                               "chars": len(result.message)})
            messages.append({
                "role": "user",
                "content": f"[{name} 结果 {label}]\n{result.message}",
            })
        except ExecError as e:
            self._emit(AgentEvent(AgentEventKind.TOOL_ERROR, step,
                                  {"name": name, "label": label, "error": str(e)}))
            self.trace.append({"event": f"{name}_error", "label": label,
                               "error": str(e)})
            messages.append({
                "role": "user",
                "content": f"{name} 失败: {e}",
            })

    # ------------------------------------------------------------------
    # System Prompt
    # ------------------------------------------------------------------

    def _system_prompt(self) -> str:
        schema = build_schema(self.registry)
        return (
            _GUIDE
            + "\n\n# 动作执行规则\n"
            "1. 一次只输出一个动作 JSON；动作之间按流程衔接（查资料 → 写动作 → done）。\n"
            "2. 写动作需要完整依据：sources 为网页 URL, basis 为用户明确需求, 宁缺勿错。\n"
            "3. 每次动作都用 reply 字段向用户简要说明你基于什么资料、准备怎么写。\n"
            "4. **范围由用户决定**: 只做用户明确要求的文件/关系, 不自行扩大范围。\n"
            "   用户说\"全部写入/完整建档\"才算 5件套+interperson(5+1) 全写;\n"
            "   只提了某几个文件就只写那几个。\n"
            "5. 范围不明确时, 先输出 done 并附 reply 询问用户想写哪些, 不要猜。\n"
            "6. 全部完成后输出 done。\n\n"
            "可用动作 schema:\n" + schema
        )


# ============================================================================
# 入口
# ============================================================================

def main() -> None:
    """CLI 入口: python -m fetch.agent"""
    from llm.client import LLMClient

    client = LLMClient()
    try:
        IDEAgent(client).run()
    finally:
        client.close()


if __name__ == "__main__":
    main()
