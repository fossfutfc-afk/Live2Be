# -*- coding: utf-8 -*-
"""设置路由 — GUI 配置存档（settings.toml）读写。

引擎已接入: llm/client.py 与 llm/image_gen.py 读配置时 settings.toml 非空
字段优先, .env 兜底——GUI 设置页改 key/base_url/model 立即生效。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from webgui import store

router = APIRouter()


class SettingsIn(BaseModel):
    llm: dict | None = None
    image: dict | None = None
    # 未来分组（characters.xxx）加字段即可——store.DEFAULTS 同步扩展


@router.get("/api/settings")
async def get_settings() -> dict:
    """返回当前配置（api_key 打码——'已设置 ****last4'）。"""
    data = store.load_settings()
    for section in data:
        key = data[section].get("api_key", "")
        if key:
            data[section]["api_key"] = store.mask_api_key(key)
    return data


@router.post("/api/settings")
async def post_settings(body: SettingsIn) -> dict:
    """合并保存（api_key 留空/打码标记 = 不改）; 只保留已知分组/字段。"""
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
    return {"ok": True}
