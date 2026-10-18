"""运行态、文件位置与关停 —— 前端三个小功能的后端。

`GET  /api/runtime/status` : 在跑什么、跑到第几步、多久了（"要不要等它跑完"据此决定）
`GET  /api/runtime/paths`  : **五个根在哪**（"数据到底存在哪里"的答案就在这儿）
`POST /api/runtime/open`   : 在资源管理器里打开某个根（提权时经 explorer 代开）
`POST /api/shutdown`       : `mode=graceful`（等它跑完, ≤180s）或 `mode=force`（立刻）

后两个端点必须带 `/api/menu` 下发的口令, 且只接受本机来源 —— 否则任意网页都能关掉你的
服务、或在你机器上弹资源管理器（见 `webgui/shutdown.py`）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from infra import paths, runtime, shell
from webgui import serve, shutdown

logger = logging.getLogger(__name__)

router = APIRouter()

_MODES = ("graceful", "force")
#: 允许从界面打开的位置（不给任意路径: 这个端点只做"打开这几个目录"）
_OPENABLE = {
    "data": paths.DATA_ROOT,
    "assets": paths.ASSETS_ROOT,
    "config": paths.CONFIG_ROOT,
    "app": paths.APP_ROOT,
}


class OpenIn(BaseModel):
    which: str
    token: str = ""


def _guard(request: Request, token: str) -> None:
    """本机来源 + 口令双校验（判据在 `webgui/shutdown.py`，两个路由共用）。"""
    shutdown.guard(request, token)


@router.get("/api/runtime/status")
async def api_runtime_status() -> dict:
    """在途任务快照: `{"shutdown": bool, "busy": [{"name","stage","elapsed_s"}]}`。"""
    return runtime.snapshot()


@router.get("/api/runtime/paths")
async def api_runtime_paths() -> dict:
    """五个根 + settings.toml 的位置（只读；给设置页显示"东西都在哪"）。"""
    return {
        "app": str(paths.APP_ROOT),
        "resource": str(paths.RESOURCE_ROOT),
        "config": str(paths.CONFIG_ROOT),
        "assets": str(paths.ASSETS_ROOT),
        "data": str(paths.DATA_ROOT),
        "settings": str(paths.SETTINGS_PATH),
        "openable": sorted(_OPENABLE),
    }


@router.post("/api/runtime/open")
async def api_open_folder(body: OpenIn, request: Request) -> dict:
    """在资源管理器里打开某个根（`data` / `assets` / `config` / `app`）。"""
    _guard(request, body.token)
    target = _OPENABLE.get(body.which)
    if target is None:
        raise HTTPException(status_code=400, detail=f"which 必须是 {sorted(_OPENABLE)}")
    ok = shell.open_folder(str(target))
    if not ok:
        raise HTTPException(status_code=409, detail="打不开资源管理器")
    return {"ok": True, "path": str(target)}


@router.post("/api/shutdown")
async def api_shutdown(request: Request) -> dict:
    """关停服务。missing/错误口令或非本机来源一律 403。"""
    try:
        body = await request.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    _guard(request, str(body.get("token") or ""))
    mode = str(body.get("mode") or "graceful")
    if mode not in _MODES:
        raise HTTPException(status_code=400, detail=f"mode 必须是 {_MODES}")

    result = serve.request_stop(force=(mode == "force"))
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail="本进程不是由 `webgui.serve` 起的, 关不掉")
    logger.info("前端请求关停: mode=%s 在途=%d", mode, len(result.get("busy") or []))
    return result
