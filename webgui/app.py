# -*- coding: utf-8 -*-
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
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

# 根日志配置（2026-09-08）: uvicorn 只配自己的 access/error logger——live2be.* 的
# INFO 埋点（bond_gen / bond_anno / llm chat …）此前从不输出, 排查全靠盲猜。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
# httpx 每请求一行太吵——压到 WARNING, 让 live2be.* 埋点可读
logging.getLogger("httpx").setLevel(logging.WARNING)

from webgui.routers import bond, menu, mmt, name, settings, spine

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
MENU_DIR = ROOT / "assets" / "menu"
ILLUS_DIR = ROOT / "assets" / "illustration"
BG_DIR = ROOT / "assets" / "background"
DATA_DIR = ROOT / "data"

#: 画廊 scene_id 形态: {YYYYMMDD_HHMMSS}_{hex4}
_SCENE_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{4}$")


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles + no-cache 头（每次重新验证——开发期避免旧 JS/CSS 缓存坑）。"""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response


app = FastAPI(title="Live2Be")
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
app.include_router(settings.router)
app.include_router(mmt.router)
app.include_router(bond.router)
app.include_router(spine.router)
