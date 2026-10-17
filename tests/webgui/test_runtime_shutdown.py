"""运行态与关停端点 —— 状态快照形状 · 口令与来源校验 · 没有启动器时如实拒绝。

为什么值得钉: `POST /api/shutdown` 是**能被任意网页调用**的端点。少了口令/来源校验,
你开着服务随便逛个网站就可能被关掉; 而"没有自持 server 时假装成功"会让前端显示
"正在关停"却永远不停（假绿灯比红灯更贵）。

跑法: python -m pytest tests/webgui/test_runtime_shutdown.py
"""
import asyncio

import pytest

from infra import runtime
from webgui import serve, shutdown
from webgui.app import app


def _request(method: str, path: str, *, client=("127.0.0.1", 50000), **kw):
    """一次 HTTP 往返（ASGI 传输——真实路由/校验, 无端口无网络）。"""
    from httpx import ASGITransport, AsyncClient

    async def go():
        transport = ASGITransport(app=app, client=client)
        async with AsyncClient(transport=transport,
                               base_url="http://127.0.0.1:8000") as c:
            return await c.request(method, path, **kw)

    return asyncio.run(go())


@pytest.fixture(autouse=True)
def _clean_runtime():
    runtime._reset_for_tests()
    yield
    runtime._reset_for_tests()


def test_status_reports_shutdown_flag_and_busy_stage():
    runtime.begin("digest", "relate")
    r = _request("GET", "/api/runtime/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["shutdown"] is False
    assert body["busy"][0]["name"] == "digest"
    assert body["busy"][0]["stage"] == "relate"


def test_menu_hands_out_the_shutdown_token():
    r = _request("GET", "/api/menu")
    assert r.status_code == 200, r.text
    assert r.json()["shutdown_token"] == shutdown.TOKEN


def test_shutdown_needs_the_token():
    for body in ({}, {"mode": "graceful"}, {"mode": "graceful", "token": "nope"}):
        r = _request("POST", "/api/shutdown", json=body)
        assert r.status_code == 403, (body, r.status_code)
    # 口令错也不许真去关
    assert runtime.shutdown_requested() is False


def test_shutdown_rejects_foreign_clients_and_origins():
    ok = {"mode": "graceful", "token": shutdown.TOKEN}
    far = _request("POST", "/api/shutdown", json=ok, client=("10.0.0.7", 50000))
    assert far.status_code == 403, "非本机来源必须拒"
    evil = _request("POST", "/api/shutdown", json=ok,
                    headers={"Origin": "http://evil.example"})
    assert evil.status_code == 403, "跨站 Origin 必须拒"
    assert runtime.shutdown_requested() is False


def test_bad_mode_is_a_400():
    r = _request("POST", "/api/shutdown",
                 json={"mode": "later", "token": shutdown.TOKEN})
    assert r.status_code == 400, r.text


def test_without_the_launcher_it_says_so(monkeypatch):
    """不是 `webgui.serve` 起的进程 ⇒ 409（前端据此提示"关不掉, 请关窗口"）。"""
    monkeypatch.setattr(serve, "_server", None)
    r = _request("POST", "/api/shutdown",
                 json={"mode": "graceful", "token": shutdown.TOKEN})
    assert r.status_code == 409, r.text


def test_shutdown_forwards_force_to_the_launcher(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(serve, "_server", object())     # 只要不是 None

    def _fake_stop(*, force: bool) -> dict:
        seen["force"] = force
        return {"ok": True, "mode": "force" if force else "graceful", "busy": []}

    monkeypatch.setattr(serve, "request_stop", _fake_stop)
    r = _request("POST", "/api/shutdown",
                 json={"mode": "force", "token": shutdown.TOKEN})
    assert r.status_code == 200, r.text
    assert seen == {"force": True}
    assert r.json()["mode"] == "force"


# ---------------------------------------------------------------------------
# 文件位置（"数据到底存哪儿"）
# ---------------------------------------------------------------------------

def test_paths_endpoint_tells_where_the_data_is():
    r = _request("GET", "/api/runtime/paths")
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("app", "resource", "config", "assets", "data", "settings"):
        assert isinstance(body.get(key), str) and body[key], body
    assert set(body["openable"]) == {"data", "assets", "config", "app"}


def test_open_folder_needs_token_and_local_origin(monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(serve, "open_folder", lambda p: called.append(p) or True)

    assert _request("POST", "/api/runtime/open",
                    json={"which": "data"}).status_code == 403
    assert _request("POST", "/api/runtime/open",
                    json={"which": "data", "token": "nope"}).status_code == 403
    far = _request("POST", "/api/runtime/open",
                   json={"which": "data", "token": shutdown.TOKEN},
                   client=("10.0.0.7", 50000))
    assert far.status_code == 403
    assert called == [], "没过校验就一个目录都不许开"


def test_open_folder_refuses_unknown_targets(monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(serve, "open_folder", lambda p: called.append(p) or True)
    r = _request("POST", "/api/runtime/open",
                 json={"which": "C:/Windows", "token": shutdown.TOKEN})
    assert r.status_code == 400, "只认那四个根, 不许传任意路径"
    assert called == []


def test_open_folder_opens_the_root(monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(serve, "open_folder", lambda p: called.append(p) or True)
    r = _request("POST", "/api/runtime/open",
                 json={"which": "data", "token": shutdown.TOKEN})
    assert r.status_code == 200, r.text
    assert called and called[0].replace("\\", "/").endswith("data")
