# -*- coding: utf-8 -*-
"""web/ 服务端回归测试 — hub / runner / app（含 SSE 生成器）, 不依赖浏览器。

覆盖:
    hub             publish / snapshot / cursor 增量语义
    runner          busy → 409; auto-approve; 手动批准; 拒绝→重试→超时中止
    app             HTTP 端点状态码（400/409）+ SSE 生成器输出格式
    mock            MockLLM 全流程（mock 模式对前端无感知）

用法: python web/_server_test.py   （项目根环境, 推荐 live2be env）
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
    print("auto-approve 全流程 PASS")


def test_decision_approve():
    hub = HUBS.get("r3")
    runner = _mk_runner(MockLLM(), hub, "r3")
    assert runner.start_turn("创建")
    _wait(lambda: any(e["kind"] == "PENDING_APPROVAL" for e in hub.snapshot(0)[0]), timeout=5)
    pa = next(e for e in hub.snapshot(0)[0] if e["kind"] == "PENDING_APPROVAL")
    runner.submit_decision(pa["approval_id"], "approve")
    _wait(lambda: not runner.busy, timeout=10)
    assert "EXEC_RESULT" in _kinds(hub)
    assert "DONE" in _kinds(hub)
    print("手动批准 PASS")


def test_reject_then_timeout_abort():
    hub = HUBS.get("r4")
    # 拒绝 → LLM 重试 → 第二次 ask 无人决策 → 超时 abort
    runner = _mk_runner(MockLLM(), hub, "r4", ask_timeout=1.0)
    assert runner.start_turn("创建")
    _wait(lambda: any(e["kind"] == "PENDING_APPROVAL" for e in hub.snapshot(0)[0]), timeout=5)
    pa = next(e for e in hub.snapshot(0)[0] if e["kind"] == "PENDING_APPROVAL")
    runner.submit_decision(pa["approval_id"], "reject")
    _wait(lambda: not runner.busy, timeout=10)
    kinds = _kinds(hub)
    assert "DECISION" in kinds, f"应发出拒绝 DECISION, 得 {kinds}"
    assert "ABORTED" in kinds, f"第二次 ask 超时应 abort, 得 {kinds}"
    print("拒绝→重试→超时中止 PASS")


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
    assert '"kind": "PENDING_APPROVAL"' in joined
    assert '"kind": "EXEC_RESULT"' in joined
    assert '"kind": "DONE"' in joined
    _wait(lambda: not runner.busy, timeout=10)
    print("SSE 生成器输出 PASS")


def main() -> None:
    tests = [
        test_hub_cursor,
        test_runner_busy_409,
        test_auto_approve,
        test_decision_approve,
        test_reject_then_timeout_abort,
        test_app_endpoints,
        test_sse_stream,
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
