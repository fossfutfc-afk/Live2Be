"""webgui/app.py — Live2Be 游戏 GUI 后端（薄壳装配）。

路由按功能域拆分在 routers/（name 登录彩蛋 / settings 设置 / menu 页面背景）,
配置存储独立 store.py——未来每个界面独立示范/修改, 不动壳。

与 web/（角色卡 IDE）分离的独立 FastAPI 应用。

启动: uvicorn webgui.app:app --reload --port 8080

静态缓存策略: 所有静态文件（html/js/css）带 Cache-Control: no-cache——
浏览器每次重新验证（ETag 条件请求: 文件没变 304 快, 变了拉新 200）——
保证前端逻辑永远最新（不依赖手动强刷; 旧 JS 不会因缓存不执行覆盖逻辑）。
"""
from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

from infra import logsetup, paths, runtime, settings

# 控制台短、文件全（形态与理由见 `infra/logsetup.py`）——必须在 routers import 之前配好,
# 否则那批模块的 logger 已按默认（无 handler）初始化。
logsetup.setup()
if settings.last_error():
    logging.getLogger(__name__).warning(
        "settings.toml 没用上（用默认值跑）: %s", settings.last_error())

from webgui.routers import (
    bond,
    collection,
    menu,
    mmt,
    name,
    spine,
)

# ⚠️ 别名: `settings` 这个名字属于 infra.settings（路由器那份遮蔽过它一次）
from webgui.routers import (
    settings as settings_router,
)

STATIC_DIR = paths.WEBGUI_STATIC_DIR
MENU_DIR = paths.MENU_DIR
ILLUS_DIR = paths.ILLUSTRATION_DIR
BG_DIR = paths.BACKGROUND_DIR
DATA_DIR = paths.DATA_DIR

#: 画廊 scene_id 形态: {YYYYMMDD_HHMMSS}_{hex4}
_SCENE_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{4}$")


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles + no-cache 头（每次重新验证——开发期避免旧 JS/CSS 缓存坑）。"""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """关停: 先让长任务（digest）在安全点收手，再等它们退出 —— 最多 3 秒。

    uvicorn 的优雅关停只等在途 **HTTP 请求**；digest 跑在守护线程里，不在它的账上。
    所以这里置关停信号（digest 在下一轮之间/提交前看到就回滚）并等一会儿 —— 等不到
    也**不会**写坏: 提交窗口自己有关停闸，被杀在最坏处只是这段下次重来。
    """
    yield
    runtime.request_shutdown()
    if not runtime.wait_idle(3.0):
        logging.getLogger(__name__).warning(
            "关停: 在途任务 3 秒内没收手（它们不会写盘 —— 提交前有关停闸）, 下次启动重来")


app = FastAPI(title="Live2Be", lifespan=_lifespan)
app.mount("/static", NoCacheStaticFiles(directory=STATIC_DIR), name="static")
app.mount("/assets/menu", NoCacheStaticFiles(directory=MENU_DIR), name="menu")
app.mount("/assets/illustration", NoCacheStaticFiles(directory=ILLUS_DIR), name="illus")
app.mount("/assets/background", NoCacheStaticFiles(directory=BG_DIR), name="bg")


@app.get("/gallery/{world_id}/{char_id}/{scene_id}.png")
def gallery_png(world_id: str, char_id: str, scene_id: str) -> Response:
    """纪念立绘取图（2026-09-02: 画廊收进世界线角色目录——
    worlds/{world}/characters/{char}/gallery/; 动态路由按需读, 不整树静态挂载
    （防 events.jsonl/wiki 等被静态目录暴露）; 路径严格校验防穿越）。"""
    if not _SCENE_RE.match(scene_id):
        raise HTTPException(status_code=404, detail="not found")
    if not re.match(r"^[a-z0-9_]+$", char_id) or not re.match(r"^[a-z0-9_]+$", world_id):
        raise HTTPException(status_code=404, detail="not found")
    png = (DATA_DIR / "worlds" / world_id / "characters" / char_id
           / "gallery" / f"{scene_id}.png")
    if not png.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(png, headers={"Cache-Control": "no-cache"})

# 路由注册（每域独立文件——铺路: 未来加域只加 import + include_router）
app.include_router(menu.router)
app.include_router(name.router)
app.include_router(settings_router.router)
app.include_router(mmt.router)
app.include_router(bond.router)
app.include_router(collection.router)
app.include_router(spine.router)
