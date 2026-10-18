"""素材包端点 —— 口令闸 · 素材源没配时的形状 · 清单坏掉时如实报错。

为什么值得钉: 三个 POST 都能**改机器状态**（写 settings.toml、往 `assets/` 里塞文件），
而素材源是**用户填的 URL** —— 清单和 zip 都来自那个源。少了口令闸，任意网页都能改它。

跑法: python -m pytest tests/webgui/test_packs_api.py
"""
import asyncio

import pytest

from webgui import shutdown
from webgui.app import app
from webgui.routers import packs as packs_router


def _request(method: str, path: str, *, client=("127.0.0.1", 50000), **kw):
    """一次 HTTP 往返（ASGI 传输——真实路由/校验, 无端口无网络）。"""
    from httpx import ASGITransport, AsyncClient

    async def go():
        transport = ASGITransport(app=app, client=client)
        async with AsyncClient(transport=transport,
                               base_url="http://127.0.0.1:8000") as c:
            return await c.request(method, path, **kw)

    return asyncio.run(go())


@pytest.fixture
def no_manifest(tmp_path, monkeypatch):
    """一份空 settings（没有 `[assets] manifest_url`）。"""
    path = tmp_path / "settings.toml"
    monkeypatch.setenv("LIVE2BE_SETTINGS", str(path))
    return path


def test_source_without_token_is_rejected(no_manifest):
    r = _request("POST", "/api/packs/source", json={"manifest_url": "http://x/m.json"})
    assert r.status_code == 403, r.text


def test_source_from_foreign_origin_is_rejected(no_manifest):
    r = _request("POST", "/api/packs/source",
                 json={"manifest_url": "http://x/m.json", "token": shutdown.TOKEN},
                 headers={"Origin": "http://evil.example"})
    assert r.status_code == 403, r.text


def test_install_without_token_is_rejected(no_manifest):
    r = _request("POST", "/api/packs/install", json={"ids": ["char.igusa_haruka"]})
    assert r.status_code == 403, r.text


def test_install_with_empty_ids_is_rejected(no_manifest):
    r = _request("POST", "/api/packs/install", json={"ids": [], "token": shutdown.TOKEN})
    assert r.status_code == 400, r.text


def test_get_packs_is_honest_when_unconfigured(no_manifest):
    r = _request("GET", "/api/packs")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is False
    assert body["packs"] == []
    assert body["error"] == ""


def test_get_packs_reports_fetch_failure_instead_of_500(no_manifest, monkeypatch):
    """素材源指到不存在的地方 → 200 + error（页面要能渲染出"读不到", 不是白屏）。"""
    monkeypatch.setenv("LIVE2BE_PACKS_MANIFEST", "http://127.0.0.1:9/none.json")
    r = _request("GET", "/api/packs")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is True
    assert body["packs"] == []
    assert "清单取不到" in body["error"]


def test_source_saves_and_clears(no_manifest, tmp_path):
    r = _request("POST", "/api/packs/source",
                 json={"manifest_url": "http://127.0.0.1:8000/manifest.json",
                       "proxy": "http://127.0.0.1:7897", "token": shutdown.TOKEN})
    assert r.status_code == 200, r.text
    assert r.json()["manifest_url"] == "http://127.0.0.1:8000/manifest.json"
    assert no_manifest.read_text(encoding="utf-8").count("manifest_url") == 1

    # 空串 = 删掉那个键（回到"没配"），而不是留一个空字符串
    r = _request("POST", "/api/packs/source",
                 json={"manifest_url": "", "token": shutdown.TOKEN})
    assert r.status_code == 200, r.text
    assert r.json()["manifest_url"] == ""
    assert "manifest_url" not in no_manifest.read_text(encoding="utf-8")


def test_progress_is_idle_when_nothing_ran(monkeypatch):
    monkeypatch.setattr(packs_router, "_job", None)
    r = _request("GET", "/api/packs/progress")
    assert r.status_code == 200, r.text
    assert r.json()["running"] is False
