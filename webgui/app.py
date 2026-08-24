# -*- coding: utf-8 -*-
"""webgui/app.py — Live2Be 游戏 GUI 后端（M1: 登录起名）。

与 web/（IDE）分离的独立 FastAPI 应用。M1 最小闭环:
  登录页（LOGO + 名字输入）→ 名字校验/保存（data/basic/player.json）→
  namegg 彩蛋（config/eggs/namegg.json）→ 进入主界面占位。

复用: core/mmt/mmt_preset 的玩家名系统（load/save/has）+ egg_reply_for 彩蛋查询。
能跑优先: 无认证/美化; 单玩家单窗口。

启动: uvicorn webgui.app:app --reload --port 8080
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.mmt.mmt_preset import (
    egg_kind,
    egg_reply_for,
    has_player_name,
    load_player_name,
    save_player_name,
)

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
MENU_DIR = ROOT / "assets" / "menu"

app = FastAPI(title="Live2Be")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/assets/menu", StaticFiles(directory=MENU_DIR), name="menu")

#: 名字长度上限（防滥用）
MAX_NAME_LEN = 32


class NameIn(BaseModel):
    name: str


@app.get("/")
async def index() -> FileResponse:
    """登录页。"""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/menu")
async def api_menu() -> dict:
    """menu 背景图列表（按文件名排序——BA 大版本 menu 图按序播放）。

    只取子目录（vol2.0/ 等版本目录）里的图片; logo 不列入背景。
    """
    images: list[str] = []
    if MENU_DIR.is_dir():
        for sub in sorted(p for p in MENU_DIR.iterdir() if p.is_dir()):
            if sub.name in ("logo", "default"):
                continue                  # logo 是图标; default 是主界面专属背景——不轮播
            for img in sorted(sub.glob("*.jpg")) + sorted(sub.glob("*.png")):
                rel = img.relative_to(MENU_DIR).as_posix()
                images.append(f"/assets/menu/{rel}")
    return {"images": images}


@app.get("/api/name")
async def api_get_name() -> dict:
    """当前玩家名（是否已设置 + 名字）——前端决定显示输入框 or 欢迎回来。"""
    return {
        "has_name": has_player_name(),
        "name": load_player_name(),
    }


@app.post("/api/name")
async def api_set_name(body: NameIn) -> dict:
    """保存玩家名 + 返回 namegg 彩蛋（如有）。

    namegg 彩蛋回复带前缀: AC~ 接受 / RJ~ 玩笑拒绝 / 无前缀 普通。
    彩蛋是"惊喜展示"——RJ~ 也只是娱乐（GUI 不真的拒绝, 名字照样保存）。
    """
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名字不能为空")
    if len(name) > MAX_NAME_LEN:
        raise HTTPException(status_code=400, detail=f"名字最长 {MAX_NAME_LEN} 字")
    egg = egg_reply_for(name)
    kind = egg_kind(egg)
    if kind in ("reject", "system"):
        # RJ~/ER~ 阻止取名: 不保存, 前端提示换名（彩蛋照常展示）
        return {"ok": False, "rejected": True, "kind": kind, "egg": egg}
    save_player_name(name)
    return {
        "ok": True,
        "name": name,
        "egg": egg,          # 未命中彩蛋 → None
        "kind": kind,
    }
