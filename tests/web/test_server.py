# -*- coding: utf-8 -*-
"""web/ 服务端回归测试 — hub / runner / app（含 SSE 生成器）, 不依赖浏览器。

覆盖:
    hub             publish / snapshot / cursor 增量语义
    runner          busy → 409; auto-approve; 手动批准; 拒绝→重试→超时中止
    app             HTTP 端点状态码（400/409）+ SSE 生成器输出格式
    mock            MockLLM 全流程（mock 模式对前端无感知）

运行: python -m pytest tests/web/test_server.py
"""
import asyncio
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

import web.app as web_app
from web.hub import HUBS
from web.mock import MockLLM
from web.runner import AgentRunner


# ============================================================================
# Stub / 工具
# ============================================================================

class GateLLM:
    """chat 阻塞在 gate 上, 用于制造 busy（HTTP 409）。放行后返回 done。"""

    def __init__(self):
        self.gate = threading.Event()

    def chat(self, messages, **kw):
        self.gate.wait(timeout=10)
        return {"action": "done", "summary": "完成", "reply": "完毕",
                "payload": {"message": "done"}}

    def close(self):  # 模拟真实 LLMClient 的 close
        pass


def _wait(pred, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return
        time.sleep(0.02)
    raise AssertionError("wait 超时")


def _kinds(hub) -> list[str]:
    return [e["kind"] for e in hub.snapshot(0)[0]]


def _mk_runner(llm, hub, channel, **kw) -> AgentRunner:
    return AgentRunner(llm, root=Path(tempfile.mkdtemp()), hub=hub,
                       channel=channel, **kw)


# ============================================================================
# hub
# ============================================================================

def test_hub_cursor():
    hub = HUBS.get("ut")
    hub.publish({"kind": "A", "step": 0, "data": {}, "approval_id": None})
    hub.publish({"kind": "B", "step": 0, "data": {}, "approval_id": None})
    evts, cur = hub.snapshot(0)
    assert [e["kind"] for e in evts] == ["A", "B"] and cur == 2
    evts2, cur2 = hub.snapshot(1)
    assert [e["kind"] for e in evts2] == ["B"] and cur2 == 2
    evts3, cur3 = hub.snapshot(2)
    assert evts3 == [] and cur3 == 2
    print("hub 游标语义 PASS")


# ============================================================================
# runner
# ============================================================================

def test_runner_busy_409():
    hub = HUBS.get("r1")
    llm = GateLLM()
    runner = _mk_runner(llm, hub, "r1")
    assert runner.start_turn("测试")
    _wait(lambda: runner.busy, timeout=5)
    assert not runner.start_turn("再来"), "busy 时应拒绝第二轮"
    assert runner.status()["busy"] is True
    llm.gate.set()
    _wait(lambda: not runner.busy, timeout=5)
    assert runner.start_turn("恢复后可以再跑")
    _wait(lambda: not runner.busy, timeout=5)
    print("runner busy→409 语义 PASS")


def test_auto_approve():
    hub = HUBS.get("r2")
    runner = _mk_runner(MockLLM(), hub, "r2", auto_delay=0.1)
    runner.set_auto_approve(True, 0.1)
    assert runner.start_turn("创建")
    _wait(lambda: not runner.busy, timeout=10)
    kinds = _kinds(hub)
    assert "PENDING_APPROVAL" in kinds
    assert "EXEC_RESULT" in kinds, f"自动批准应执行, 得 {kinds}"
    assert "DONE" in kinds, f"应正常完成, 得 {kinds}"
    assert "ABORTED" not in kinds
    # 首次写动作的范例询问也被 auto-approve 自动放行
    assert "ASK_USER" in kinds, f"应出现范例询问, 得 {kinds}"
    assert "profile.yml" in runner.agent._example_loaded
    print("auto-approve 全流程 PASS")


def test_decision_approve():
    hub = HUBS.get("r3")
    runner = _mk_runner(MockLLM(), hub, "r3")
    assert runner.start_turn("创建")
    # 首次写动作 → 先出范例询问(ASK_USER), 批准后才进入写审批
    _wait(lambda: any(e["kind"] == "ASK_USER" for e in hub.snapshot(0)[0]), timeout=5)
    q = next(e for e in hub.snapshot(0)[0] if e["kind"] == "ASK_USER")
    assert q["approval_id"].startswith("example-")
    runner.submit_decision(q["approval_id"], "approve")
    _wait(lambda: any(e["kind"] == "PENDING_APPROVAL" for e in hub.snapshot(0)[0]), timeout=5)
    pa = next(e for e in hub.snapshot(0)[0] if e["kind"] == "PENDING_APPROVAL")
    runner.submit_decision(pa["approval_id"], "approve")
    _wait(lambda: not runner.busy, timeout=10)
    assert "EXEC_RESULT" in _kinds(hub)
    assert "DONE" in _kinds(hub)
    assert "profile.yml" in runner.agent._example_loaded
    print("手动批准 PASS")


def test_reject_then_timeout_abort():
    hub = HUBS.get("r4")
    # 范例询问超时(1s, 视为跳过) → 写审批拒绝 → LLM 重试 → 第二次 ask 无人决策 → 超时 abort
    runner = _mk_runner(MockLLM(), hub, "r4", ask_timeout=1.0)
    assert runner.start_turn("创建")
    _wait(lambda: any(e["kind"] == "PENDING_APPROVAL" for e in hub.snapshot(0)[0]), timeout=5)
    pa = next(e for e in hub.snapshot(0)[0] if e["kind"] == "PENDING_APPROVAL")
    runner.submit_decision(pa["approval_id"], "reject")
    _wait(lambda: not runner.busy, timeout=10)
    kinds = _kinds(hub)
    assert "ASK_USER" in kinds, f"应出范例询问, 得 {kinds}"
    assert "DECISION" in kinds, f"应发出拒绝 DECISION, 得 {kinds}"
    assert "ABORTED" in kinds, f"第二次 ask 超时应 abort, 得 {kinds}"
    assert not runner.agent._example_loaded          # 超时=跳过, 不加载
    assert "profile.yml" in runner.agent._example_asked_turn   # 但本轮只问一次
    print("拒绝→重试→超时中止 PASS")


def test_example_question():
    # 批准路径: 同意读取 → 范例启用, 重跑本轮后正常写
    hub = HUBS.get("ex1")
    runner = _mk_runner(MockLLM(), hub, "ex1")
    assert runner.start_turn("创建")
    _wait(lambda: any(e["kind"] == "ASK_USER" for e in hub.snapshot(0)[0]), timeout=5)
    q = next(e for e in hub.snapshot(0)[0] if e["kind"] == "ASK_USER")
    runner.submit_decision(q["approval_id"], "approve")
    _wait(lambda: "profile.yml" in runner.agent._example_loaded, timeout=5)
    _wait(lambda: any(e["kind"] == "PENDING_APPROVAL" for e in hub.snapshot(0)[0]), timeout=5)
    pa = next(e for e in hub.snapshot(0)[0] if e["kind"] == "PENDING_APPROVAL")
    runner.submit_decision(pa["approval_id"], "approve")
    _wait(lambda: not runner.busy, timeout=10)
    assert "profile.yml" in runner.agent._example_loaded
    assert "profile.yml" in runner.agent._example_asked_turn
    assert "DONE" in _kinds(hub)

    # 跳过路径: 拒绝 → 不加载, 但 _example_asked_turn 已记录（本轮不再问）
    hub2 = HUBS.get("ex2")
    runner2 = _mk_runner(MockLLM(), hub2, "ex2")
    assert runner2.start_turn("创建")
    _wait(lambda: any(e["kind"] == "ASK_USER" for e in hub2.snapshot(0)[0]), timeout=5)
    q2 = next(e for e in hub2.snapshot(0)[0] if e["kind"] == "ASK_USER")
    runner2.submit_decision(q2["approval_id"], "reject")
    _wait(lambda: any(e["kind"] == "PENDING_APPROVAL" for e in hub2.snapshot(0)[0]), timeout=5)
    pa2 = next(e for e in hub2.snapshot(0)[0] if e["kind"] == "PENDING_APPROVAL")
    runner2.submit_decision(pa2["approval_id"], "approve")
    _wait(lambda: not runner2.busy, timeout=10)
    assert not runner2.agent._example_loaded
    assert "profile.yml" in runner2.agent._example_asked_turn
    assert "DONE" in _kinds(hub2)
    print("范例询问(批准/跳过) PASS")


# ============================================================================
# app（HTTP 状态码 + SSE 生成器）
# ============================================================================

def test_app_endpoints():
    hub = HUBS.get("http")
    llm = GateLLM()
    runner = _mk_runner(llm, hub, "http")
    web_app.runner = runner
    client = TestClient(web_app.app)

    assert client.get("/").status_code == 200
    st = client.get("/api/status").json()
    assert st["busy"] is False and st["auto_approve"] is False

    assert client.post("/api/turn", json={"message": ""}).status_code == 400
    assert client.post("/api/turn", json={"message": "  "}).status_code == 400
    assert client.post("/api/turn", json={"message": "测试"}).status_code == 200
    _wait(lambda: runner.busy, timeout=5)
    assert client.post("/api/turn", json={"message": "再来"}).status_code == 409

    assert client.post("/api/approve",
                       json={"approval_id": "a1", "decision": "maybe"}).status_code == 400
    assert client.post("/api/approve",
                       json={"approval_id": "", "decision": "approve"}).status_code == 400
    assert client.post("/api/approve",
                       json={"approval_id": "a1", "decision": "approve"}).status_code == 200

    auto = client.post("/api/auto_approve", json={"enabled": True}).json()
    assert auto["auto_approve"] is True
    assert client.get("/api/status").json()["auto_approve"] is True

    llm.gate.set()
    _wait(lambda: not runner.busy, timeout=5)
    assert client.get("/api/status").json()["busy"] is False
    print("app 端点 PASS")


def test_sse_stream():
    hub = HUBS.get("sse")
    runner = _mk_runner(MockLLM(), hub, "sse", auto_delay=0.2)
    runner.set_auto_approve(True, 0.2)

    # 模拟浏览器: 先打开 SSE 流, 再发 turn（reconnect 语义: 开流前的事件不回放）
    result: dict = {}

    def _run():
        async def collect():
            resp = await web_app.api_events("sse")
            lines: list[str] = []
            agen = resp.body_iterator
            try:
                async for chunk in agen:
                    lines.append(chunk.decode("utf-8"))
                    if '"kind": "DONE"' in "\n".join(lines):
                        break
            finally:
                await agen.aclose()
            return lines
        result["lines"] = asyncio.run(collect())

    t = threading.Thread(target=_run)
    t.start()
    time.sleep(0.2)                       # 等 SSE 流进入轮询
    assert runner.start_turn("创建")
    t.join(timeout=10)
    assert not t.is_alive(), "SSE 收集应在 DONE 后退出"

    joined = "\n".join(result["lines"])
    assert "data: " in joined
    assert '"kind": "THINKING"' in joined
    assert '"kind": "ASK_USER"' in joined
    assert '"kind": "PENDING_APPROVAL"' in joined
    assert '"kind": "EXEC_RESULT"' in joined
    assert '"kind": "DONE"' in joined
    _wait(lambda: not runner.busy, timeout=10)
    print("SSE 生成器输出 PASS")


# ============================================================================
# 本地命令（/view /edit）走 runner 路由, 不碰 LLM
# ============================================================================

def _seed_char(root: Path, name: str) -> Path:
    """在 runner 的执行层 root 下种一个角色, 返回其 profile.yml 路径。"""
    char_dir = Path(root) / "config" / "characters" / name
    char_dir.mkdir(parents=True)
    profile = char_dir / "profile.yml"
    profile.write_text(
        "REQ~most_called_name: 伊草 遥香\nREQ~is_official_character: true\n"
        "SIG~age: 15\nSIG~club: 真相调查部\n",
        encoding="utf-8",
    )
    return profile


def test_command_view():
    hub = HUBS.get("cmd1")
    runner = _mk_runner(MockLLM(), hub, "cmd1")
    _seed_char(runner.agent.executor.root, "stub")

    assert runner.start_turn("/view stub")
    _wait(lambda: not runner.busy, timeout=5)
    cmd_events = [e for e in hub.snapshot(0)[0] if e["kind"] == "COMMAND_RESULT"]
    assert cmd_events, "应发出 COMMAND_RESULT"
    assert "五件套" in cmd_events[-1]["data"]["text"]
    assert cmd_events[-1]["data"]["terminal"] is True
    # 全程零 LLM 事件
    kinds = _kinds(hub)
    assert "THINKING" not in kinds and "DONE" not in kinds
    print("web /view 路由 PASS")


def test_command_edit():
    hub = HUBS.get("cmd2")
    runner = _mk_runner(MockLLM(), hub, "cmd2")
    profile = _seed_char(runner.agent.executor.root, "stub")

    assert runner.start_turn("/edit stub/profile.yml SIG~age: 16")
    # 走审批卡: 等 PENDING_APPROVAL → 批准
    _wait(lambda: any(e["kind"] == "PENDING_APPROVAL" for e in hub.snapshot(0)[0]), timeout=5)
    pa = next(e for e in hub.snapshot(0)[0] if e["kind"] == "PENDING_APPROVAL")
    assert "本地编辑 stub/profile.yml" in pa["data"]["summary"]
    runner.submit_decision(pa["approval_id"], "approve")

    _wait(lambda: not runner.busy, timeout=10)
    kinds = _kinds(hub)
    assert "EXEC_RESULT" in kinds, f"批准后应执行, 得 {kinds}"
    assert "COMMAND_RESULT" in kinds, f"命令终态应复位 busy, 得 {kinds}"
    assert "SIG~age: 16" in profile.read_text(encoding="utf-8")
    assert "伊草 遥香" in profile.read_text(encoding="utf-8")  # 未提及字段保留
    print("web /edit 路由 PASS")


def test_command_unknown():
    hub = HUBS.get("cmd3")
    runner = _mk_runner(MockLLM(), hub, "cmd3")
    _seed_char(runner.agent.executor.root, "stub")

    assert runner.start_turn("/veiw stub")
    _wait(lambda: not runner.busy, timeout=5)
    cmd_events = [e for e in hub.snapshot(0)[0] if e["kind"] == "COMMAND_RESULT"]
    assert cmd_events and "未知命令" in cmd_events[-1]["data"]["text"]
    # 不回灌 LLM: 零 THINKING/DONE
    assert "THINKING" not in _kinds(hub)
    print("web 未知命令提示 PASS")


def main() -> None:
    tests = [
        test_hub_cursor,
        test_runner_busy_409,
        test_auto_approve,
        test_decision_approve,
        test_reject_then_timeout_abort,
        test_example_question,
        test_app_endpoints,
        test_sse_stream,
        test_command_view,
        test_command_edit,
        test_command_unknown,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\nweb/ 服务端回归: {len(tests) - failed}/{len(tests)} 通过")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
