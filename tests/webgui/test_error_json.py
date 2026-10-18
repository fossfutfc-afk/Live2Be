"""错误呈现的 HTTP 契约 —— 未捕获异常必须回 **JSON**（2026-10-18）。

病灶（真机，冻结版第一次装完）: 点角色 → 聊天窗显示
`打开会话失败（网络错误: Unexpected token 'I', "Internal S"... is not valid JSON）`。
真因是没配 API Key（`LLMClient` 构造抛 `ValueError`），而 FastAPI 对未捕获异常回的是
**纯文本** `Internal Server Error` ⇒ 前端 `.json()` 解析它以 `I` 开头的串就炸了。
用户看到的是"网络错误"，永远查不到"你还没填 key"。

判据两条:
    ① 没配 key ⇒ **412 + JSON**（`code=no_api_key`，`detail` 是能照着做的一句话）;
    ② 其它未捕获异常 ⇒ **500 + JSON**（`code=internal`），⛔ 不是纯文本。

运行: python -m pytest tests/webgui/test_error_json.py
"""
import asyncio
import json

import pytest

from webgui import chat
from webgui.app import app

CHARACTER = "igusa_haruka"
_NO_KEY = "ValueError: [client.py][ConfigError][LLM_API_KEY not set. 请在 .env 中设置]"


def _http(method: str, path: str):
    """一次 HTTP 往返（ASGI 直连，不开端口）。

    ⚠️ `raise_app_exceptions=False`: Starlette 发完我们的 JSON 之后**仍会把异常抛回**
    传输层（它要给 uvicorn 记日志用）——不放这个开关，测试拿到的是异常而不是响应。
    """
    from httpx import ASGITransport, AsyncClient

    async def go():
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.request(method, path)

    return asyncio.run(go())


def _raise_value_error(*_a, **_kw):
    raise ValueError("[client.py][ConfigError][LLM_API_KEY not set. 请在 .env 中设置]")


def test_missing_api_key_is_412_json(monkeypatch):
    """① 没配 key ⇒ 412 + JSON，`detail` 要能照着修。"""
    monkeypatch.setattr(chat, "LLMClient", _raise_value_error)
    chat._engines.pop(CHARACTER, None)
    r = _http("GET", f"/api/mmt/session?char_id={CHARACTER}")

    assert r.status_code == 412, (r.status_code, r.text[:200])
    assert r.headers["content-type"].startswith("application/json"), r.headers
    body = json.loads(r.text)                      # ⛔ 解析不了就是这次的病灶回来了
    assert body["code"] == "no_api_key", body
    assert "API Key" in body["detail"] and "设置" in body["detail"], body
    print(f"    缺 key: {r.status_code} {body['code']} — {body['detail'][:30]}…")


def test_uncaught_exception_is_500_json(monkeypatch):
    """② 其它未捕获异常 ⇒ 500 + JSON（不是纯文本 `Internal Server Error`）。"""
    def boom(*_a, **_kw):
        raise RuntimeError("引擎炸了（这条只该进日志）")

    monkeypatch.setattr(chat, "_engine", boom)
    r = _http("GET", f"/api/mmt/session?char_id={CHARACTER}")

    assert r.status_code == 500, (r.status_code, r.text[:200])
    body = json.loads(r.text)
    assert body["code"] == "internal", body
    assert body["detail"].startswith("服务器内部错误"), body
    print(f"    其它异常: {r.status_code} {body['code']} — {body['detail'][:30]}…")
