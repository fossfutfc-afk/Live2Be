"""素材包下载 —— 首次运行向导的后端（模型层在 `infra/packs.py`）。

`GET  /api/packs`          : 清单 + 每个包本地装到哪一步（素材源没配 → `configured=false`）
`POST /api/packs/source`   : 存 `[assets] manifest_url` 与 `[net] proxy`
`POST /api/packs/install`  : 挑若干包开始下载（同一时刻只跑一个任务，重复请求 → 409）
`POST /api/packs/cancel`   : 让在跑的下载停在当前包
`GET  /api/packs/progress` : 轮询进度（前端 500 ms 一次）

三个 POST 都要 `/api/menu` 下发的口令 + 本机来源（`webgui/shutdown.guard`）—— 否则任意网页
都能改你的素材源、往 `assets/` 里塞文件（清单和 zip 都由那个源决定）。

下载线程是守护线程：关掉服务它就没了，但**已落地的文件是完整的** —— 每个包先下到
`.part`、校验 sha256、才解压（`infra/packs.py` 的纪律）。
"""

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from infra import packs, paths, settings
from webgui import shutdown

logger = logging.getLogger(__name__)

router = APIRouter()

#: 工作目录（下下来的 zip 暂存，解压完就删）
WORK_DIR = paths.DATA_ROOT / "packs"


class _Job:
    """一次下载的进度。只在这里可变，读出去一律走 `snapshot()`。"""

    def __init__(self, ids: list[str]) -> None:
        self.ids = ids
        self.cancel = threading.Event()
        self.running = True
        self.pack_id = ids[0] if ids else ""
        self.stage = "starting"
        self.received = 0
        self.total = 0
        self.done: list[dict] = []
        self.error = ""
        self.thread: threading.Thread | None = None

    def snapshot(self) -> dict:
        return {
            "running": self.running,
            "ids": list(self.ids),
            "pack_id": self.pack_id,
            "stage": self.stage,
            "received": self.received,
            "total": self.total,
            "done": list(self.done),
            "error": self.error,
        }


_lock = threading.Lock()
_job: _Job | None = None


class SourceIn(BaseModel):
    manifest_url: str | None = None
    proxy: str | None = None
    token: str = ""


class InstallIn(BaseModel):
    ids: list[str]
    token: str = ""


class TokenIn(BaseModel):
    token: str = ""


def _pack_view(pack: packs.Pack) -> dict:
    state, present, total = packs.local_state(pack, paths.ASSETS_ROOT)
    return {
        "id": pack.id,
        "kind": pack.kind,
        "group": pack.group,
        "title": pack.title,
        "zip_bytes": pack.zip_bytes,
        "bytes": pack.bytes,
        "file_count": pack.file_count,
        "state": state,
        "present": present,
        "total": total,
    }


@router.get("/api/packs")
async def api_packs() -> dict:
    """清单 + 本地状态。**素材源没配不是错误**，只是一屏引导。"""
    url = packs.manifest_url()
    base = {
        "configured": bool(url),
        "manifest_url": url,
        "proxy": packs.proxy_url(),
        "assets": str(paths.ASSETS_ROOT),
        "packs": [],
        "error": "",
    }
    if not url:
        return base
    try:
        manifest = packs.read_manifest(url)
    except packs.PackError as e:
        base["error"] = str(e)
        return base
    base["generated"] = manifest.generated
    base["packs"] = [_pack_view(p) for p in manifest.packs]
    return base


@router.post("/api/packs/source")
async def api_packs_source(body: SourceIn, request: Request) -> dict:
    """存素材源与代理（空串 = 删掉该键，回到"没配"）。"""
    shutdown.guard(request, body.token)
    if body.manifest_url is not None:
        settings.update("assets", manifest_url=body.manifest_url)
    if body.proxy is not None:
        settings.update("net", proxy=body.proxy)
    logger.info("素材源已更新: manifest_url=%r proxy=%r",
                packs.manifest_url(), packs.proxy_url())
    return {"ok": True, "manifest_url": packs.manifest_url(), "proxy": packs.proxy_url()}


@router.post("/api/packs/install")
async def api_packs_install(body: InstallIn, request: Request) -> dict:
    """开始装。`ids` 只装挑中的包 —— 已装好的也允许重装（覆盖）。"""
    global _job
    shutdown.guard(request, body.token)
    ids = [i for i in (body.ids or []) if i]
    if not ids:
        raise HTTPException(status_code=400, detail="没挑任何包")
    with _lock:
        if _job is not None and _job.running:
            raise HTTPException(status_code=409, detail="已经有一个下载在跑了")
        try:
            manifest = packs.read_manifest()
        except packs.PackError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        missing = [i for i in ids if manifest.get(i) is None]
        if missing:
            raise HTTPException(status_code=400, detail=f"清单里没有这些包: {missing}")
        job = _Job(ids)
        _job = job

    def _run() -> None:
        def _progress(pack_id: str, stage: str, received: int, total: int) -> None:
            job.pack_id, job.stage = pack_id, stage
            job.received, job.total = received, total

        logger.info("开始下载素材: %s（工作目录 %s）", ", ".join(ids), WORK_DIR)
        try:
            outcomes = packs.install(manifest, ids, paths.ASSETS_ROOT, WORK_DIR,
                                     progress=_progress, cancel=job.cancel)
        except Exception as e:                 # noqa: BLE001 — 线程里炸了不能没人知道
            job.error = f"{type(e).__name__}: {e}"
            logger.warning("素材下载线程异常: %s", job.error)
            outcomes = []
        job.done = [
            {"pack_id": o.pack_id, "ok": o.ok, "files": o.files, "error": o.error}
            for o in outcomes
        ]
        failed = [o.pack_id for o in outcomes if not o.ok]
        job.stage = "cancelled" if job.cancel.is_set() else ("failed" if failed else "finished")
        job.running = False
        if failed:
            logger.warning("素材下载未全部成功: %s", ", ".join(failed))
        else:
            logger.info("素材下载完成: %d 个包", len(outcomes))

    job.thread = threading.Thread(target=_run, name="packs-install", daemon=True)
    job.thread.start()
    return {"ok": True, "ids": ids}


@router.post("/api/packs/cancel")
async def api_packs_cancel(body: TokenIn, request: Request) -> dict:
    shutdown.guard(request, body.token)
    job = _job
    if job is None or not job.running:
        return {"ok": False, "detail": "没有在跑的下载"}
    job.cancel.set()
    return {"ok": True}


@router.get("/api/packs/progress")
async def api_packs_progress() -> dict:
    job = _job
    if job is None:
        return {"running": False, "ids": [], "pack_id": "", "stage": "",
                "received": 0, "total": 0, "done": [], "error": ""}
    return job.snapshot()
