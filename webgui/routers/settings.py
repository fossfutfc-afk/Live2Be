# -*- coding: utf-8 -*-
"""设置路由 — GUI 配置存档（settings.toml）读写。

引擎已接入: llm/client.py 与 llm/image_gen.py 读配置时 settings.toml 非空
字段优先, .env 兜底——GUI 设置页改 key/base_url/model 立即生效。
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from webgui import chat, store

router = APIRouter()


class SettingsIn(BaseModel):
    llm: dict | None = None
    image: dict | None = None
    # 未来分组（characters.xxx）加字段即可——store.DEFAULTS 同步扩展


@router.get("/api/settings")
async def get_settings() -> JSONResponse:
    """返回当前配置（api_key 打码——'****last4', 前面打星尾部可辨认）。

    响应加 Cache-Control: no-store——无缓存头时浏览器可能启发式缓存旧响应
    （改 key 后刷新仍显示旧值——"假 key 又回来了"的错觉）。
    """
    data = store.load_settings()
    for section in data:
        key = data[section].get("api_key", "")
        if key:
            data[section]["api_key"] = store.mask_api_key(key)
    return JSONResponse(content=data, headers={"Cache-Control": "no-store"})


@router.post("/api/settings")
async def post_settings(body: SettingsIn) -> dict:
    """合并保存（api_key 留空/打码标记 = 不改）; 只保留已知分组/字段。

    保存后重建引擎实例（chat.reset_engines）——LLMClient 构造时 key 已写死,
    不重建则旧实例继续用旧 key（假 key 时期创建的实例改 key 不生效）。
    """
    current = store.load_settings()
    for section in ("llm", "image"):
        incoming = getattr(body, section, None)
        if not incoming:
            continue
        for key, val in incoming.items():
            if key == "api_key":
                if not val or store.is_masked(str(val)):
                    continue                  # 空/打码 → 不改 key
            current[section][key] = val
    store.save_settings(current)
    chat.reset_engines()                      # 配置变更 → 引擎按新配置重建
    return {"ok": True}
