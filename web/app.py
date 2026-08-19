"""web/app.py — FastAPI 应用: IDE agent Web GUI 服务。

端点契约见 web/DESIGN.md §5。mock 开关: IDE_MOCK=1 → StubLLM（临时目录落盘）。
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web.hub import HUBS
from web.runner import AgentRunner

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"

#: SSE 轮询间隔 / 心跳间隔（秒）
SSE_POLL = 0.05
SSE_HEARTBEAT = 15.0

_DECISIONS = {"approve", "reject", "abort"}


# ---------------------------------------------------------------------------
# 请求体
# ---------------------------------------------------------------------------

class TurnIn(BaseModel):
    message: str


class ApproveIn(BaseModel):
    approval_id: str
    decision: str


class AutoApproveIn(BaseModel):
    enabled: bool
    delay_s: float | None = None


# ---------------------------------------------------------------------------
# 依赖装配
# ---------------------------------------------------------------------------

def build_runner() -> AgentRunner:
    """构造 runner。IDE_MOCK=1 用 StubLLM（临时目录落盘）, 否则真实 LLMClient。"""
    if os.getenv("IDE_MOCK") == "1":
        from web.mock import MockLLM, mock_root
        return AgentRunner(MockLLM(), root=mock_root())
    from llm.client import LLMClient
    return AgentRunner(LLMClient(), root=ROOT)


#: 全局 runner（lifespan 装配; 测试可直接覆盖）
runner: AgentRunner | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global runner
    runner = build_runner()
    yield
    if runner is not None:
        runner.close()


app = FastAPI(title="Live2Be IDE", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/events")
async def api_events(channel: str = "ide"):
    """SSE 事件流。每个连接持有一个本地游标, 断开自动结束。"""
    hub = HUBS.get(channel)

    async def stream():
        cursor = hub.cursor
        last_beat = time.monotonic()
        while True:
            events, cursor = hub.snapshot(cursor)
            for evt in events:
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n".encode("utf-8")
                last_beat = time.monotonic()
            if time.monotonic() - last_beat >= SSE_HEARTBEAT:
                yield b": ping\n\n"
                last_beat = time.monotonic()
            await asyncio.sleep(SSE_POLL)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


@app.post("/api/turn")
async def api_turn(body: TurnIn):
    message = body.message.strip()
    if not message:
        return JSONResponse(status_code=400, content={"detail": "消息不能为空"})
    if runner is None:
        return JSONResponse(status_code=503, content={"detail": "服务未就绪"})
    if not runner.start_turn(message):
        return JSONResponse(status_code=409, content={"detail": "上一轮还没结束"})
    return {"ok": True}


@app.post("/api/approve")
async def api_approve(body: ApproveIn):
    if body.decision not in _DECISIONS:
        return JSONResponse(status_code=400,
                            content={"detail": f"decision 必须是 {sorted(_DECISIONS)} 之一"})
    if not body.approval_id:
        return JSONResponse(status_code=400, content={"detail": "approval_id 不能为空"})
    if runner is None:
        return JSONResponse(status_code=503, content={"detail": "服务未就绪"})
    runner.submit_decision(body.approval_id, body.decision)
    return {"ok": True}


@app.post("/api/auto_approve")
async def api_auto_approve(body: AutoApproveIn):
    if runner is None:
        return JSONResponse(status_code=503, content={"detail": "服务未就绪"})
    runner.set_auto_approve(body.enabled, body.delay_s)
    return runner.status()


@app.get("/api/status")
async def api_status():
    if runner is None:
        return JSONResponse(status_code=503, content={"detail": "服务未就绪"})
    return runner.status()
