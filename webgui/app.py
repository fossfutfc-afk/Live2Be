# -*- coding: utf-8 -*-
"""webgui/app.py — Live2Be 游戏 GUI 后端（薄壳装配）。

路由按功能域拆分在 routers/（name 登录彩蛋 / settings 设置 / menu 页面背景）,
配置存储独立 store.py——未来每个界面独立示范/修改, 不动壳。

与 web/（角色卡 IDE）分离的独立 FastAPI 应用。

启动: uvicorn webgui.app:app --reload --port 8080
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from webgui.routers import menu, name, settings

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
MENU_DIR = ROOT / "assets" / "menu"

app = FastAPI(title="Live2Be")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/assets/menu", StaticFiles(directory=MENU_DIR), name="menu")

# 路由注册（每域独立文件——铺路: 未来加域只加 import + include_router）
app.include_router(menu.router)
app.include_router(name.router)
app.include_router(settings.router)
