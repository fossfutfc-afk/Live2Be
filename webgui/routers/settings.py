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


def _acceptable(cur: dict, key: str, val) -> bool:
    """POST 来的值是否可写（False = **不改这个键**）。

    为什么"入口校验"在这里: `store.save_settings` 已是**保真落盘**（文件里有什么就
    写回什么），它只做类型防呆——不认识的键不再被裁, 但"不可写的值"会被**跳过不写**,
    而跳过 = 该键从文件里消失 = 读回回落 `DEFAULTS`。那是"删掉"而不是"不改"。

    2026-09-13 复核补（审计 A1 的余波）:
      · `None`（JSON `null`）——语义是"这次没提供值", **不是"把键设成空"**。透传下去
        会删键: `[image].enabled=false` 被 null 一冲就翻回默认 `true`（生图开 =
        花钱方向）, `model` 被重置成内置默认。GUI 输入框给的是 `""` 不是 null,
        但 API 调用/未来的 UI 可能发 null。
      · 非标量塞进**本来存标量**的键（如 `{"model": {"x": 1}}`）——`save_settings`
        会把 dict 当嵌套表忠实写成 `[llm.model]`, 该键从此不是字符串（LLMClient
        会拿到 dict）。list 等其它类型同理。
      · 嵌套表本身是合法配置（`[llm.tasks.*]`）, 所以 dict 只在**该键当前也是表**
        或**该键还不存在**时放行——不误伤合法的表写入。
    """
    if val is None:
        return False
    if isinstance(val, dict):
        return key not in cur or isinstance(cur.get(key), dict)
    return isinstance(val, (str, bool, int, float))


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
    """合并保存（**只改 POST 里显式给出的标量**; api_key 空/打码 = 不改）。

    保存后重建引擎实例（chat.reset_engines）——LLMClient 构造时 key 已写死,
    不重建则旧实例继续用旧 key（假 key 时期创建的实例改 key 不生效）。
    """
    current = store.load_settings()
    for section in ("llm", "image"):
        incoming = getattr(body, section, None)
        if not incoming:
            continue
        for key, val in incoming.items():
            if not _acceptable(current[section], key, val):
                continue                  # null/非法类型 → 不改（见 `_acceptable`）
            if key == "api_key":
                if not val or store.is_masked(str(val)):
                    continue                  # 空/打码 → 不改 key
            current[section][key] = val
    store.save_settings(current)
    chat.reset_engines()                      # 配置变更 → 引擎按新配置重建
    return {"ok": True}
