# -*- coding: utf-8 -*-
"""页面/背景路由 — 静态页（登录/伪404）+ menu 背景列表。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
ROOT = Path(__file__).resolve().parent.parent.parent
MENU_DIR = ROOT / "assets" / "menu"


@router.get("/")
async def index() -> FileResponse:
    """登录页。"""
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/err404")
async def err404() -> FileResponse:
    """伪 404 故障页——FT~（致命）彩蛋触发: 假装系统宕机。"""
    return FileResponse(STATIC_DIR / "err404.html")


@router.get("/api/menu")
async def api_menu() -> dict:
    """menu 背景图列表（按文件名排序——BA 大版本 menu 图按序播放）。

    只取子目录（vol2.0/ 等版本目录）里的图片; logo/default 不列入
    （logo 是图标; default 是主界面专属背景）。
    """
    images: list[str] = []
    if MENU_DIR.is_dir():
        for sub in sorted(p for p in MENU_DIR.iterdir() if p.is_dir()):
            if sub.name in ("logo", "default"):
                continue
            for img in sorted(sub.glob("*.jpg")) + sorted(sub.glob("*.png")):
                rel = img.relative_to(MENU_DIR).as_posix()
                images.append(f"/assets/menu/{rel}")
    return {"images": images}
