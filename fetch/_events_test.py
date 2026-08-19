# -*- coding: utf-8 -*-
"""Phase 2 事件模型同步测试 — stub LLM + stub emit/ask，不碰网络。

验证 agent_turn 注入 emit/ask 后产出确定的事件序列:
    approve:  THINKING → AI_MESSAGE → PENDING_APPROVAL → EXEC_RESULT(ok) → DONE
    reject:   ... → PENDING_APPROVAL → DECISION(reject) → ... → DONE
    abort:    ... → PENDING_APPROVAL → ABORTED（本轮中止, 不再调 LLM）
    invalid:  THINKING → INVALID_ACTION → ...（回灌给 LLM 修正）
同时验证 CLI 默认回调文本与历史输出逐字节一致、trace 结构不变。

用法: python fetch/_events_test.py
"""
import io
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fetch.agent import APPROVAL_PROMPT, IDEAgent
from fetch.events import AgentEvent, AgentEventKind


# ============================================================================
# Stub
# ============================================================================

class StubLLM:
    """按脚本返回动作 dict 的 stub——registry.parse 直接消费。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def chat(self, messages, **kw):
        self.calls += 1
        assert self._responses, f"stub LLM 响应用尽（已调用 {self.calls} 次）"
        return self._responses.pop(0)


class Recorder:
    """收集 emit 事件 + 回放 ask 决策。"""

    def __init__(self, decisions):
        self.events: list[AgentEvent] = []
        self.asks: list[tuple[str, str]] = []
        self.decisions = list(decisions)

    def emit(self, evt: AgentEvent):
        self.events.append(evt)

    def ask(self, approval_id: str, prompt: str):
        self.asks.append((approval_id, prompt))
        assert prompt == APPROVAL_PROMPT, f"ask 提示变了: {prompt!r}"
        assert self.decisions, "stub ask 决策用尽"
        return self.decisions.pop(0)

    def kinds(self) -> list[str]:
        return [e.kind.name for e in self.events]

    def find(self, kind: AgentEventKind) -> list[AgentEvent]:
        return [e for e in self.events if e.kind is kind]


def cc(summary: str = "创建测试角色") -> dict:
    """合法 create_character 动作 dict（过契约 + 真实 executor 可落盘）。"""
    return {
        "action": "create_character",
        "summary": summary,
        "reply": "好的，我来创建这个角色。",
        "payload": {
            "character_id": "stub_test",
            "files": {"profile.yml": "REQ~most_called_name: 测试酱\n"},
        },
    }


def done_msg(message: str = "角色已创建") -> dict:
    return {
        "action": "done",
        "summary": message,
        "reply": "全部完成了。",
        "payload": {"message": message},
    }


# ============================================================================
# 场景
# ============================================================================

def test_approve_flow() -> None:
    tmp = Path(tempfile.mkdtemp())
    rec = Recorder(["approve"])
    agent = IDEAgent(StubLLM([cc(), done_msg()]), root=tmp, emit=rec.emit, ask=rec.ask)
    agent.agent_turn("创建测试角色")

    assert rec.kinds() == [
        "THINKING", "AI_MESSAGE", "PENDING_APPROVAL", "EXEC_RESULT",
        "THINKING", "AI_MESSAGE", "DONE",
    ], rec.kinds()

    pa = rec.find(AgentEventKind.PENDING_APPROVAL)[0]
    assert pa.approval_id == "approval-1"
    assert pa.data["summary"] == "创建测试角色"
    assert "diff" in pa.data and "action" in pa.data

    assert rec.asks == [("approval-1", APPROVAL_PROMPT)]

    ex = rec.find(AgentEventKind.EXEC_RESULT)[0]
    assert ex.data["ok"] is True and ex.data["message"]

    dn = rec.find(AgentEventKind.DONE)[0]
    assert dn.data["message"] == "角色已创建"

    # trace 结构保持原样（_kayoko/_e2e 依赖）
    assert any(t.get("event") == "plan" and "diff" in t for t in agent.trace)
    assert any(t.get("event") == "decision" and t.get("choice") == "approved"
               and t.get("exec_ok") is True and t.get("message") for t in agent.trace)

    # 真实 executor 落盘（temp 隔离目录）
    assert (tmp / "config" / "characters" / "stub_test" / "profile.yml").exists()
    print("approve 路径 PASS")


def test_reject_flow() -> None:
    tmp = Path(tempfile.mkdtemp())
    rec = Recorder(["reject"])
    agent = IDEAgent(StubLLM([cc(), done_msg()]), root=tmp, emit=rec.emit, ask=rec.ask)
    agent.agent_turn("创建测试角色")

    assert rec.kinds() == [
        "THINKING", "AI_MESSAGE", "PENDING_APPROVAL", "DECISION",
        "THINKING", "AI_MESSAGE", "DONE",
    ], rec.kinds()

    de = rec.find(AgentEventKind.DECISION)[0]
    assert de.data == {"choice": "reject"}
    assert any(t.get("event") == "decision" and t.get("choice") == "rejected"
               for t in agent.trace)
    assert not (tmp / "config" / "characters" / "stub_test").exists()  # 未落盘
    print("reject 路径 PASS")


def test_abort_flow() -> None:
    tmp = Path(tempfile.mkdtemp())
    rec = Recorder(["abort"])
    agent = IDEAgent(StubLLM([cc()]), root=tmp, emit=rec.emit, ask=rec.ask)
    agent.agent_turn("创建测试角色")

    assert rec.kinds() == ["THINKING", "AI_MESSAGE", "PENDING_APPROVAL", "ABORTED"], rec.kinds()
    assert rec.find(AgentEventKind.ABORTED)[0].data == {}
    assert any(t.get("event") == "decision" and t.get("choice") == "abort"
               for t in agent.trace)
    print("abort 路径 PASS")


def test_invalid_flow() -> None:
    tmp = Path(tempfile.mkdtemp())
    rec = Recorder([])  # 无效动作不触发 ask
    agent = IDEAgent(StubLLM([{"action": "not_a_real_action"}, done_msg()]),
                     root=tmp, emit=rec.emit, ask=rec.ask)
    agent.agent_turn("随便")

    assert rec.kinds() == ["THINKING", "INVALID_ACTION", "THINKING", "AI_MESSAGE", "DONE"], rec.kinds()
    ia = rec.find(AgentEventKind.INVALID_ACTION)[0]
    assert ia.data["errors"], "INVALID_ACTION 应带错误信息"
    print("invalid 路径 PASS")


def test_cli_byte_compat() -> None:
    tmp = Path(tempfile.mkdtemp())
    agent = IDEAgent(StubLLM([]), root=tmp)
    buf = io.StringIO()
    with redirect_stdout(buf):
        agent._default_emit(AgentEvent(AgentEventKind.AI_MESSAGE, 0, {"message": "你好"}))
        agent._default_emit(AgentEvent(AgentEventKind.DONE, 0, {"message": "完成"}))
        agent._default_emit(AgentEvent(AgentEventKind.THINKING, 0, {}))
        agent._default_emit(AgentEvent(AgentEventKind.PENDING_APPROVAL, 0,
                                       {"summary": "s", "diff": "-a\n+b"}))
        agent._default_emit(AgentEvent(AgentEventKind.EXEC_RESULT, 0,
                                       {"ok": True, "message": "写入成功"}))
    expected = "\n[AI] 你好\n\n[AI] 完成\n\n[AI 提议] s\n-a\n+b\n[已执行] 写入成功\n"
    assert buf.getvalue() == expected, f"得 {buf.getvalue()!r}"
    print("CLI 默认 emit 逐字节 PASS")


def test_cli_ask() -> None:
    tmp = Path(tempfile.mkdtemp())
    agent = IDEAgent(StubLLM([]), root=tmp)
    for inp, expect in [("y", "approve"), ("n", "reject"), ("q", "abort"), ("quit", "abort")]:
        with patch("builtins.input", return_value=inp):
            got = agent._default_ask("x", APPROVAL_PROMPT)
        assert got == expect, f"input={inp!r} → {got!r}, 期望 {expect!r}"
    print("CLI 默认 ask 映射 PASS")


def main() -> None:
    tests = [
        test_approve_flow, test_reject_flow, test_abort_flow,
        test_invalid_flow, test_cli_byte_compat, test_cli_ask,
    ]
    for fn in tests:
        fn()
    print(f"\nPhase2 事件序列: {len(tests)}/{len(tests)} 全部通过")


if __name__ == "__main__":
    main()
