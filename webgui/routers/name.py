"""登录/名字路由 — 玩家名读写 + namegg 彩蛋（前缀两大类: 给取/不给取 + FT 伪 404）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.mmt.mmt_preset import (
    egg_allows,
    egg_kind,
    egg_reply_for,
    has_player_name,
    load_player_name,
    save_player_name,
)

router = APIRouter()

#: 名字长度上限（防滥用）
MAX_NAME_LEN = 32


class NameIn(BaseModel):
    name: str


@router.get("/api/name")
async def get_name() -> dict:
    """当前玩家名（是否已设置 + 名字）——前端决定显示输入框 or 欢迎回来。"""
    return {
        "has_name": has_player_name(),
        "name": load_player_name(),
    }


@router.post("/api/name")
async def set_name(body: NameIn) -> dict:
    """保存玩家名 + 返回 namegg 彩蛋（如有）。

    彩蛋前缀两大类（egg_allows）:
      给取   AC~ / SP~ / 无前缀 → 保存名字, 彩蛋照常展示
      不给取 RJ~ / ER~ → 不保存, 前端提示换名
      致命   FT~ → 不保存, 前端跳伪 404（假装系统宕机）
    """
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名字不能为空")
    if len(name) > MAX_NAME_LEN:
        raise HTTPException(status_code=400, detail=f"名字最长 {MAX_NAME_LEN} 字")
    egg = egg_reply_for(name)
    kind = egg_kind(egg)
    if not egg_allows(egg):
        # RJ~/ER~/FT~ 不给取: 不保存; 前端按 kind 分流（fatal → 伪 404）
        return {"ok": False, "rejected": True, "kind": kind, "egg": egg}
    save_player_name(name)
    return {
        "ok": True,
        "name": name,
        "egg": egg,          # 未命中彩蛋 → None
        "kind": kind,
    }
