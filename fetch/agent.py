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
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from contract import (
    APPROVAL_REQUIRED,
    build_schema,
)
from fetch.actions import build_ide_registry
from fetch.executor import ExecError, Executor

MAX_STEPS = 12          # 单轮 agent 最大动作步数（防死循环）
HISTORY_MAX = 30        # 跨轮记忆条数上限（去掉 system 后）
TEMP = 0.4              # 动作决策用较低温度, 减少随机


class IDEAgent:
    """IDE 撰写 agent。llm: 兼容主项目 llm.client.LLMClient 的对象。"""

    def __init__(self, llm: Any, root: str | Path = "."):
        self.llm = llm
        self.registry = build_ide_registry()
        self.executor = Executor(root)
        self.history: list[dict[str, str]] = []
        # 调试/测试用的逐步记录（每次动作交换一条）
        self.trace: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # CLI 主循环
    # ------------------------------------------------------------------

    def run(self) -> None:
        """命令行交互入口。"""
        print("═" * 46)
        print("  Live2Be IDE — 角色资料撰写助手")
        print("  用自然语言描述需求; /exit 退出")
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
            self.agent_turn(user_input)

    # ------------------------------------------------------------------
    # 单轮 agent 循环
    # ------------------------------------------------------------------

    def agent_turn(self, user_input: str) -> None:
        """一轮 agent 对话：LLM 动作循环, 直到 done / 达到步数上限。"""
        messages = [{"role": "system", "content": self._system_prompt()}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_input})

        for step in range(MAX_STEPS):
            try:
                response = self.llm.chat(
                    messages, temperature=TEMP, max_tokens=1024,
                    response_format="json_object",
                )
            except Exception as e:
                # client.chat(json_object) 失败：网络错误 / JSON 修正重试耗尽
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
                "payload": action.payload if action else None,
            })
            if not result.is_valid:
                messages.append({
                    "role": "user",
                    "content": (
                        f"动作无效: {'; '.join(result.errors)}\n"
                        "请严格按 schema 重新输出单个动作 JSON。"
                    ),
                })
                continue

            # 写动作 → 审批
            if action.approval == APPROVAL_REQUIRED:
                if self._handle_write(action, messages):
                    break
                continue

            # 只读/收尾动作
            if action.action == "done":
                msg = action.summary or action.payload.get("message", "完成")
                print(f"\n[AI] {msg}")
                break
            if action.action == "fetch_url":
                self._handle_fetch(action, messages)
                continue

        # 跨轮记忆（去掉 system, 截断）
        self.history = messages[1:][-HISTORY_MAX:]

    # ------------------------------------------------------------------
    # 动作处理
    # ------------------------------------------------------------------

    def _handle_write(self, action, messages: list[dict]) -> bool:
        """写动作审批。返回 True = 中止本轮（用户主动退出）。"""
        try:
            plan = self.executor.plan(action)
        except ExecError as e:
            messages.append({
                "role": "user",
                "content": f"无法执行: {e}\n请调整后重新输出动作。",
            })
            self.trace.append({"event": "plan_error", "error": str(e)})
            return False

        print(f"\n[AI 提议] {action.summary}")
        print(plan.diff)
        self.trace.append({"event": "plan", "diff": plan.diff})

        choice = input("\n批准? [y=执行 / n=拒绝 / q=中止本轮] ").strip().lower()
        if choice in ("q", "quit"):
            print("[已中止本轮]")
            self.trace.append({"event": "decision", "choice": "abort"})
            return True

        if choice in ("y", "yes"):
            try:
                result = self.executor.execute(action)
                print(f"[已执行] {result.message}")
                self.trace.append({"event": "decision", "choice": "approved",
                                   "exec_ok": True, "message": result.message})
                messages.append({
                    "role": "user",
                    "content": f"动作已执行: {result.message}",
                })
            except ExecError as e:
                print(f"[执行失败] {e}")
                self.trace.append({"event": "decision", "choice": "approved",
                                   "exec_ok": False, "message": str(e)})
                messages.append({
                    "role": "user",
                    "content": f"执行失败: {e}",
                })
        else:
            print("[已拒绝]")
            self.trace.append({"event": "decision", "choice": "rejected"})
            messages.append({
                "role": "user",
                "content": "用户拒绝了该动作。请按用户反馈调整后再输出。",
            })
        return False

    def _handle_fetch(self, action, messages: list[dict]) -> None:
        """抓取网页 → 回灌给 LLM 继续推理。"""
        try:
            result = self.executor.execute(action)
            print(f"[抓取 {action.payload['url']}] 已获取 {len(result.message)} 字符")
            self.trace.append({"event": "fetch", "url": action.payload["url"],
                               "chars": len(result.message)})
            messages.append({
                "role": "user",
                "content": f"[网页资料 {action.payload['url']}]\n{result.message}",
            })
        except ExecError as e:
            print(f"[抓取失败] {e}")
            self.trace.append({"event": "fetch_error", "url": action.payload["url"],
                               "error": str(e)})
            messages.append({
                "role": "user",
                "content": f"抓取失败: {e}",
            })

    # ------------------------------------------------------------------
    # System Prompt
    # ------------------------------------------------------------------

    def _system_prompt(self) -> str:
        schema = build_schema(self.registry)
        return (
            "你是 Live2Be 的角色资料撰写助手。用户用自然语言描述需求"
            "（创建/修改角色、人际关系等），你必须以动作 JSON 形式执行，"
            "而不是自由回答。\n\n"
            "规则:\n"
            "1. 需要资料时先 fetch_url 查阅（默认萌娘百科 / kivowiki / "
            "BAfandomwiki），不要凭空编造。\n"
            "2. 写动作需要完整依据（sources 为网页 URL, basis 为用户明确需求），"
            "宁缺勿错。\n"
            "3. 一次只输出一个动作；全部完成后输出 done。\n\n"
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
