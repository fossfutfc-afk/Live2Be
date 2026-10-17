"""启动外壳守门 —— 端口探测 / 已有实例 / 窗口模式退回 / 地址换算。

为什么值得钉: 这几条是"双击"那一下的全部体验。错了的表现是**双击没反应**
（或开出一个连接失败页），而用户不会去看控制台 —— 排查成本比写这组用例高得多。

跑法: python -m pytest tests/webgui/test_serve_launcher.py
"""
import socket
import sys

import pytest

from webgui import serve


def test_url_of_points_at_loopback_for_wildcard_hosts():
    assert serve.url_of("127.0.0.1", 8000) == "http://127.0.0.1:8000/"
    assert serve.url_of("0.0.0.0", 8001) == "http://127.0.0.1:8001/"
    assert serve.url_of("::", 8002) == "http://127.0.0.1:8002/"


def test_port_in_use_sees_a_listening_socket():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        assert serve.port_in_use("127.0.0.1", port) is True
    assert serve.port_in_use("127.0.0.1", port) is False


class _FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("没有 JSON")
        return self._body


def test_is_our_service_reads_the_status_shape(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse(200, {"busy": []}))
    assert serve.is_our_service("http://127.0.0.1:8000/") is True

    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse(200, {"hello": 1}))
    assert serve.is_our_service("http://127.0.0.1:8000/") is False, "形状不对就不是我们的"

    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse(404, {"busy": []}))
    assert serve.is_our_service("http://127.0.0.1:8000/") is False

    def boom(*_a, **_k):
        raise OSError("连不上")

    monkeypatch.setattr("httpx.get", boom)
    assert serve.is_our_service("http://127.0.0.1:8000/") is False


def test_existing_instance_is_opened_instead_of_failing(monkeypatch):
    """端口被占且上面是我们 ⇒ 打开它、返回 0（双击第二次 = 打开已有窗口）。"""
    opened: list[str] = []
    monkeypatch.setattr(serve, "port_in_use", lambda host, port: True)
    monkeypatch.setattr(serve, "is_our_service", lambda url, timeout=1.5: True)
    monkeypatch.setattr(serve, "open_browser", opened.append)

    assert serve.main(["--port", "8123", "--no-browser"]) == 0
    assert opened == ["http://127.0.0.1:8123/"]


def test_foreign_service_on_the_port_is_a_refusal(monkeypatch):
    monkeypatch.setattr(serve, "port_in_use", lambda host, port: True)
    monkeypatch.setattr(serve, "is_our_service", lambda url, timeout=1.5: False)
    monkeypatch.setattr(serve, "open_browser", lambda url: pytest.fail("不该打开浏览器"))

    assert serve.main(["--port", "8123", "--no-browser"]) == 2


def test_window_mode_falls_back_without_pywebview(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", None)     # `import webview` → ImportError
    ran: list[bool] = []
    opened: list[str] = []

    class _Srv:
        def run(self):
            ran.append(True)

    monkeypatch.setattr(serve, "_server", _Srv())
    monkeypatch.setattr(serve, "_open_when_ready", opened.append)

    assert serve._run_windowed("http://127.0.0.1:8123/") == 0
    assert ran == [True], "退回浏览器模式也要把服务跑起来"
    assert opened == ["http://127.0.0.1:8123/"]
