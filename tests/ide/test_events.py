# -*- coding: utf-8 -*-
"""Phase 2 事件模型同步测试 — stub LLM + stub emit/ask，不碰网络。

验证 agent_turn 注入 emit/ask 后产出确定的事件序列:
    approve:  THINKING → AI_MESSAGE → PENDING_APPROVAL → EXEC_RESULT(ok) → DONE
    reject:   ... → PENDING_APPROVAL → DECISION(reject) → ... → DONE
    abort:    ... → PENDING_APPROVAL → ABORTED（本轮中止, 不再调 LLM）
    invalid:  THINKING → INVALID_ACTION → ...（回灌给 LLM 修正）
同时验证 CLI 默认回调文本与历史输出逐字节一致、trace 结构不变。

运行: python -m pytest tests/ide/test_events.py
"""
import io
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ide.ide_agent import APPROVAL_PROMPT, IDEAgent, _example_ask_prompt
from ide.ide_events import AgentEvent, AgentEventKind


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
    """收集 emit 事件 + 回放 ask 决策。

    ask 有两种合法提示: 写动作审批(APPROVAL_PROMPT) 与 范例询问(以"是否读取 "开头,
    按文件粒度, 见 _example_ask_prompt)。decisions 按出现顺序消费。
    """

    def __init__(self, decisions):
        self.events: list[AgentEvent] = []
        self.asks: list[tuple[str, str]] = []
        self.decisions = list(decisions)

    def emit(self, evt: AgentEvent):
        self.events.append(evt)

    def ask(self, approval_id: str, prompt: str):
        self.asks.append((approval_id, prompt))
        assert prompt == APPROVAL_PROMPT or prompt.startswith("是否读取 "), \
            f"ask 提示变了: {prompt!r}"
        assert self.decisions, "stub ask 决策用尽"
        return self.decisions.pop(0)

    def kinds(self) -> list[str]:
        return [e.kind.name for e in self.events]

    def find(self, kind: AgentEventKind) -> list[AgentEvent]:
        return [e for e in self.events if e.kind is kind]


def cc(summary: str = "创建测试角色", files=None) -> dict:
    """合法 create_character 动作 dict（过契约 + 真实 executor 可落盘）。"""
    return {
        "action": "create_character",
        "summary": summary,
        "reply": "好的，我来创建这个角色。",
        "payload": {
            "character_id": "stub_test",
            "files": files or {"profile.yml": "REQ~most_called_name: 测试酱\n"},
        },
    }


def uc(summary: str = "更新测试角色", files=None) -> dict:
    """合法 update_character 动作 dict（目录需已存在）。"""
    return {
        "action": "update_character",
        "summary": summary,
        "reply": "好的，我来更新这个角色。",
        "payload": {
            "character_id": "stub_test",
            "mode": "overwrite",
            "files": files or {"profile.yml": "REQ~most_called_name: 测试酱\n"},
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
    # 决策[0]=范例询问(同意→重跑本轮), 决策[1]=写动作审批
    rec = Recorder(["approve", "approve"])
    agent = IDEAgent(StubLLM([cc(), cc(), done_msg()]), root=tmp,
                     emit=rec.emit, ask=rec.ask)
    agent.agent_turn("创建测试角色")

    # 首轮 reply 在范例询问前不展示（gate 在 emit reply 之前 continue 重跑）
    assert rec.kinds() == [
        "THINKING", "ASK_USER",
        "THINKING", "AI_MESSAGE", "PENDING_APPROVAL", "EXEC_RESULT",
        "THINKING", "AI_MESSAGE", "DONE",
    ], rec.kinds()
    assert agent._example_loaded == {"profile.yml"}   # 同意 → 该板块已加载
    ask0 = rec.find(AgentEventKind.ASK_USER)[0]
    assert ask0.data["prompt"] == _example_ask_prompt("profile.yml")
    assert ask0.data["file"] == "profile.yml"

    pa = rec.find(AgentEventKind.PENDING_APPROVAL)[0]
    assert pa.approval_id == "approval-2"        # example-1 用掉序号 1
    assert pa.data["summary"] == "创建测试角色"
    assert "diff" in pa.data and "action" in pa.data

    assert rec.asks == [
        ("example-1", _example_ask_prompt("profile.yml")),
        ("approval-2", APPROVAL_PROMPT),
    ]

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
    rec = Recorder(["approve", "reject"])       # 范例同意, 写动作拒绝
    agent = IDEAgent(StubLLM([cc(), cc(), done_msg()]), root=tmp,
                     emit=rec.emit, ask=rec.ask)
    agent.agent_turn("创建测试角色")

    assert rec.kinds() == [
        "THINKING", "ASK_USER",
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
    rec = Recorder(["approve", "abort"])        # 范例同意, 写动作中止
    agent = IDEAgent(StubLLM([cc(), cc()]), root=tmp,
                     emit=rec.emit, ask=rec.ask)
    agent.agent_turn("创建测试角色")

    assert rec.kinds() == [
        "THINKING", "ASK_USER",
        "THINKING", "AI_MESSAGE", "PENDING_APPROVAL", "ABORTED",
    ], rec.kinds()
    assert rec.find(AgentEventKind.ABORTED)[0].data == {}
    assert any(t.get("event") == "decision" and t.get("choice") == "abort"
               for t in agent.trace)
    print("abort 路径 PASS")


def test_example_question_skip() -> None:
    """范例询问拒绝/超时 → 跳过且不启用, 写动作照常进行（本轮只问一次）。"""
    tmp = Path(tempfile.mkdtemp())
    rec = Recorder(["reject", "approve"])       # 范例拒绝, 写动作批准
    agent = IDEAgent(StubLLM([cc(), done_msg()]), root=tmp,
                     emit=rec.emit, ask=rec.ask)
    agent.agent_turn("创建测试角色")

    # 跳过 → 不重跑: 首轮 reply 保留, 无第二次 THINKING
    assert rec.kinds() == [
        "THINKING", "ASK_USER", "AI_MESSAGE", "PENDING_APPROVAL", "EXEC_RESULT",
        "THINKING", "AI_MESSAGE", "DONE",
    ], rec.kinds()
    assert agent._example_loaded == set()            # 拒绝 → 未加载
    assert agent._example_suppressed == set()        # 拒绝 ≠ 不再询问
    assert agent._example_asked_turn == {"profile.yml"}
    assert (tmp / "config" / "characters" / "stub_test" / "profile.yml").exists()
    print("范例询问跳过路径 PASS")


def test_example_per_file() -> None:
    """按文件粒度: 一次写动作涉及多文件时逐个询问, 只注入读取的板块。"""
    tmp = Path(tempfile.mkdtemp())
    files = {
        "profile.yml": "REQ~most_called_name: 测试酱\n",
        "experience.yml": "SIG~self: null\n",
    }
    # 决策[0]=profile读, 决策[1]=experience跳, 决策[2]=写动作批准
    rec = Recorder(["approve", "reject", "approve"])
    agent = IDEAgent(StubLLM([cc(files=files), cc(files=files), done_msg()]),
                     root=tmp, emit=rec.emit, ask=rec.ask)
    agent.agent_turn("创建测试角色")

    # 两个板块各问一次（顺序 = files 键序）
    asks = rec.find(AgentEventKind.ASK_USER)
    assert len(asks) == 2, rec.kinds()
    assert asks[0].data["prompt"] == _example_ask_prompt("profile.yml")
    assert asks[0].data["file"] == "profile.yml"
    assert asks[1].data["prompt"] == _example_ask_prompt("experience.yml")
    assert asks[1].data["file"] == "experience.yml"

    # profile 已加载, experience 本次跳过（未不再询问）
    assert agent._example_loaded == {"profile.yml"}
    assert agent._example_suppressed == set()
    assert agent._example_asked_turn == {"profile.yml", "experience.yml"}

    # system prompt 只注入读取的板块
    sys_prompt = agent._system_prompt()
    assert "## profile.yml" in sys_prompt
    assert "## experience.yml" not in sys_prompt
    assert "## personality.yml" not in sys_prompt
    print("按文件粒度范例询问 PASS")


def test_example_reject_reasks_next_turn() -> None:
    """拒绝的板块下轮仍会问; 不再询问才静默（本会话）。"""
    tmp = Path(tempfile.mkdtemp())
    # 轮1: profile 拒绝; 轮2: profile 不再询问; 轮3: profile 已静默
    rec = Recorder(["reject", "approve", "skip", "approve", "approve"])
    agent = IDEAgent(
        StubLLM([cc(), done_msg(), uc(), done_msg(), uc(), done_msg()]),
        root=tmp, emit=rec.emit, ask=rec.ask,
    )

    agent.agent_turn("创建测试角色")           # 轮1: 问 profile(拒绝)
    assert agent._example_loaded == set()
    assert agent._example_suppressed == set()
    assert agent._example_asked_turn == {"profile.yml"}
    assert len(rec.find(AgentEventKind.ASK_USER)) == 1

    agent.agent_turn("补充 profile")           # 轮2: 又问 profile(不再询问)
    assert agent._example_suppressed == {"profile.yml"}
    assert len(rec.find(AgentEventKind.ASK_USER)) == 2

    agent.agent_turn("再改 profile")           # 轮3: 已静默, 不再问
    assert agent._example_suppressed == {"profile.yml"}
    assert agent._example_loaded == set()
    assert len(rec.find(AgentEventKind.ASK_USER)) == 2   # 没新增
    print("拒绝→下轮再问 / 不再询问→静默 PASS")


def test_example_dont_ask_again_cli() -> None:
    """不再询问(skip) → 不加载也不重跑, 直接进入审批。"""
    tmp = Path(tempfile.mkdtemp())
    rec = Recorder(["skip", "approve"])
    agent = IDEAgent(StubLLM([cc(), done_msg()]), root=tmp,
                     emit=rec.emit, ask=rec.ask)
    agent.agent_turn("创建测试角色")

    # skip 不是 approve → 无重跑: 首轮 reply 保留, 无第二次 THINKING
    assert rec.kinds() == [
        "THINKING", "ASK_USER", "AI_MESSAGE", "PENDING_APPROVAL", "EXEC_RESULT",
        "THINKING", "AI_MESSAGE", "DONE",
    ], rec.kinds()
    assert agent._example_loaded == set()
    assert agent._example_suppressed == {"profile.yml"}
    assert (tmp / "config" / "characters" / "stub_test" / "profile.yml").exists()
    print("CLI 不再询问路径 PASS")


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
    for inp, expect in [("y", "approve"), ("n", "reject"), ("q", "abort"),
                        ("quit", "abort"), ("d", "skip"), ("dont", "skip")]:
        with patch("builtins.input", return_value=inp):
            got = agent._default_ask("x", APPROVAL_PROMPT)
        assert got == expect, f"input={inp!r} → {got!r}, 期望 {expect!r}"
    print("CLI 默认 ask 映射 PASS")


def main() -> None:
    tests = [
        test_approve_flow, test_reject_flow, test_abort_flow,
        test_example_question_skip, test_example_per_file,
        test_example_reject_reasks_next_turn, test_example_dont_ask_again_cli,
        test_invalid_flow, test_cli_byte_compat, test_cli_ask,
    ]
    for fn in tests:
        fn()
    print(f"\nPhase2 事件序列: {len(tests)}/{len(tests)} 全部通过")


if __name__ == "__main__":
    main()
