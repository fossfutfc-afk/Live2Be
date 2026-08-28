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

from pathlib import Path

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

from webgui.routers import menu, mmt, name, settings, spine

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
MENU_DIR = ROOT / "assets" / "menu"
ILLUS_DIR = ROOT / "assets" / "illustration"


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

# 路由注册（每域独立文件——铺路: 未来加域只加 import + include_router）
app.include_router(menu.router)
app.include_router(name.router)
app.include_router(settings.router)
app.include_router(mmt.router)
app.include_router(spine.router)
