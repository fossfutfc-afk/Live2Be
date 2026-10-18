"""关停口令与本地来源校验 —— 「改机器状态」的端点共用这一道闸。

为什么要有口令: `POST /api/shutdown` / `/api/runtime/open` / `/api/packs/*` 都是**能被任意
网页调用**的端点（浏览器允许跨域发简单请求, 只是读不到响应）。没有校验的话, 你开着服务随便
逛个网站就可能被关掉、被弹资源管理器、或者被塞进一堆文件。口令由 `/api/menu` 发给**本页**,
其它源读不到响应体 ⇒ 拿不到口令。

来源校验是第二道: 只接受本机客户端的请求, 且 `Origin`（若有）必须是本机。
"""

from __future__ import annotations

import logging
import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

#: 本进程的口令（每次启动换一个; 页面从 `/api/menu` 拿）
TOKEN = secrets.token_hex(8)

#: 认可的本机主机名
LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

logger = logging.getLogger(__name__)


def host_of(url_or_origin: str) -> str:
    """`http://127.0.0.1:8000` → `127.0.0.1`（不是 URL 就给空串）。"""
    try:
        return urlsplit(url_or_origin).hostname or ""
    except ValueError:
        return ""


def is_local_origin(origin: str) -> bool:
    """`Origin` 头是本机吗（空串 = 同源 GET 之类没有 Origin, 放行交给口令判）。"""
    return not origin or host_of(origin) in LOCAL_HOSTS


def is_local_client(host: str) -> bool:
    return host in LOCAL_HOSTS


def guard(request: Request, token: str) -> None:
    """本机来源 + 口令双校验（不合规一律 403，不解释细节）。"""
    if not is_local_origin(request.headers.get("origin") or ""):
        raise HTTPException(status_code=403, detail="forbidden")
    client = request.client
    if client is None or not is_local_client(client.host):
        raise HTTPException(status_code=403, detail="forbidden")
    if token != TOKEN:
        logger.warning("拒绝请求: 口令不对（来自 %s）", client.host)
        raise HTTPException(status_code=403, detail="forbidden")
