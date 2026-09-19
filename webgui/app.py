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

from core import paths

# 根日志配置（2026-09-08）: uvicorn 只配自己的 access/error logger——live2be.* 的
# INFO 埋点（bond_gen / bond_anno / llm chat …）此前从不输出, 排查全靠盲猜。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
# httpx 每请求一行太吵——压到 WARNING, 让 live2be.* 埋点可读
logging.getLogger("httpx").setLevel(logging.WARNING)


def _setup_file_logging() -> None:
    """诊断日志落盘（2026-09-09, 用户拍板: 排障留痕不进事件流）:

    events.jsonl 是 append-only 唯一真源——错误/诊断**不进事件流**（会被
    window_messages/digest/回放消费, 污染 LLM 上下文与记忆）;
    旁路文件 data/diag/live2be.log 挂 root logger（INFO+, 单行可 grep:
    bond_gen/bond_anno/bond_cand/bond_finish/羁绊剧情收尾回复失败/llm chat…
    自动积累, 历史问题从此有据可查）。目录 gitignore; 创建失败静默降级。

    **路径可覆盖（2026-09-11）**: 环境变量 `LIVE2BE_DIAG_LOG` 指定落盘文件,
    值为 `off`/`0` = 不落文件。测试与浏览器冒烟导入本模块时会把日志重定向到
    `.testtmp`——否则**测试的噪音会混进真机诊断日志**（2026-09-11 就因此把
    "settings reasoning_effort 非法: 'turbo'"（来自 tests/llm 的非法值用例）
    误读成用户配置问题; 同类的还有 ScriptedLLM 脚本耗尽）。
    """
    import os

    target = os.environ.get("LIVE2BE_DIAG_LOG", "").strip()
    if target.lower() in ("off", "0", "none", "disable"):
        return

    class _NoNoise(logging.Filter):
        """排除每请求高频噪音（uvicorn access / httpx）——只留业务埋点。"""

        def filter(self, record: logging.LogRecord) -> bool:
            name = record.name
            return not (name.startswith("httpx")
                        or name.startswith("uvicorn")
                        or name.startswith("werkzeug"))

    try:
        log_file = (Path(target) if target else paths.DIAG_LOG_PATH)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
        handler.setLevel(logging.INFO)
        handler.addFilter(_NoNoise())
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    except Exception as e:                           # noqa: BLE001 — 降级不阻断
        logging.warning("diag 日志文件不可用（降级控制台）: %s", e)


_setup_file_logging()

from webgui.routers import bond, collection, menu, mmt, name, settings, spine

ROOT = paths.ROOT
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
app.include_router(collection.router)
app.include_router(spine.router)
