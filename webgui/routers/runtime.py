"""运行态与关停 —— 前端「关闭服务」的后端（状态快照 + 两种关停）。

`GET /api/runtime/status`  : 在跑什么、跑到第几步、多久了（前端据此决定要不要劝等一下）
`POST /api/shutdown`      : `mode=graceful`（等它跑完, 最多 180s）或 `mode=force`（立刻）

关停端点必须带 `/api/menu` 下发的口令, 且只接受本机来源 —— 否则任意网页都能把服务关掉
（见 `webgui/shutdown.py` 的说明）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from infra import runtime
from webgui import serve, shutdown

logger = logging.getLogger(__name__)

router = APIRouter()

_MODES = ("graceful", "force")


@router.get("/api/runtime/status")
async def api_runtime_status() -> dict:
    """在途任务快照: `{"shutdown": bool, "busy": [{"name","stage","elapsed_s"}]}`。"""
    return runtime.snapshot()


@router.post("/api/shutdown")
async def api_shutdown(request: Request) -> dict:
    """关停服务。missing/错误口令或非本机来源一律 403（不解释细节）。"""
    if not shutdown.is_local_origin(request.headers.get("origin") or ""):
        raise HTTPException(status_code=403, detail="forbidden")
    client = request.client
    if client is None or not shutdown.is_local_client(client.host):
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        body = await request.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    if body.get("token") != shutdown.TOKEN:
        logger.warning("拒绝关停请求: 口令不对（来自 %s）",
                       client.host if client else "?")
        raise HTTPException(status_code=403, detail="forbidden")
    mode = str(body.get("mode") or "graceful")
    if mode not in _MODES:
        raise HTTPException(status_code=400, detail=f"mode 必须是 {_MODES}")

    result = serve.request_stop(force=(mode == "force"))
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail="本进程不是由 `webgui.serve` 起的, 关不掉")
    logger.info("前端请求关停: mode=%s 在途=%d", mode, len(result.get("busy") or []))
    return result
