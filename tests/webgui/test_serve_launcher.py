"""启动外壳守门 —— 端口探测 / 已有实例 / 窗口模式退回 / 地址换算。

为什么值得钉: 这几条是"双击"那一下的全部体验。错了的表现是**双击没反应**
（或开出一个连接失败页），而用户不会去看控制台 —— 排查成本比写这组用例高得多。

跑法: python -m pytest tests/webgui/test_serve_launcher.py
"""
import socket
import sys

import pytest

from infra import shell as infra_shell
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


# ---------------------------------------------------------------------------
# 打开地址: 优先独立应用窗口 → 提权走 explorer → 默认浏览器
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _restore_browser_mode():
    """`main()` 会改模块级 `_PREFER_APP_WINDOW`，用例之间别串味。"""
    before = serve._PREFER_APP_WINDOW
    yield
    serve._PREFER_APP_WINDOW = before


def _record_popen(calls: list[list[str]]):
    class _Popen:
        def __init__(self, args, **_kw):
            calls.append(list(args))

    return _Popen


def test_app_window_gets_its_own_profile(monkeypatch, tmp_path):
    """独立 `--user-data-dir` + `--app=` —— 绕开日常那个（可能是管理员的）浏览器实例。"""
    monkeypatch.setattr(serve.paths, "DATA_ROOT", tmp_path / "data")
    # launch() 住在 infra.shell —— 降权判断也在那儿
    monkeypatch.setattr("infra.shell.is_elevated", lambda: False)
    calls: list[list[str]] = []
    monkeypatch.setattr("subprocess.Popen", _record_popen(calls))

    assert serve.open_app_window("http://127.0.0.1:8000/", "msedge.exe") is True
    args = calls[0]
    assert args[0] == "msedge.exe"
    assert "--app=http://127.0.0.1:8000/" in args
    assert any(a.startswith("--user-data-dir=") for a in args), args
    assert (tmp_path / "data" / "browser").is_dir(), "配置目录要建出来"


def test_elevated_launcher_drops_privileges(monkeypatch):
    """提权时必须用 `runas /trustlevel:0x20000` 起浏览器。

    否则开出来的 Edge 带管理员令牌并驻留后台 —— 之后用户用普通权限双击就撞 UIPI,
    表现是灰色空窗口, 关窗时还问"要不要用普通权限"（真机实测过）。
    """
    calls: list[list[str]] = []
    monkeypatch.setattr("infra.shell.is_elevated", lambda: True)
    monkeypatch.setattr("subprocess.Popen", _record_popen(calls))

    assert infra_shell.launch(["msedge.exe", "--app=http://127.0.0.1:8000/"]) is True
    assert calls[0][:2] == ["runas", "/trustlevel:0x20000"], calls
    assert "msedge.exe" in calls[0][2]


def test_browser_prefers_the_app_window(monkeypatch):
    monkeypatch.setattr(serve, "_PREFER_APP_WINDOW", True)
    monkeypatch.setattr(serve, "find_browser_exe", lambda: "msedge.exe")
    used: list[str] = []
    monkeypatch.setattr(serve, "open_app_window",
                        lambda url, exe: used.append(exe) or True)
    monkeypatch.setattr(serve, "is_elevated", lambda: pytest.fail("不该走到 explorer"))
    monkeypatch.setattr("webbrowser.open", lambda url: pytest.fail("不该动默认浏览器"))

    assert serve.open_browser("http://127.0.0.1:8000/") == "app-window"
    assert used == ["msedge.exe"]


def test_browser_falls_back_to_explorer_when_elevated(monkeypatch):
    """找不到 Chromium 系浏览器 + 提权 ⇒ explorer 代开（浏览器不继承管理员令牌）。"""
    monkeypatch.setattr(serve, "_PREFER_APP_WINDOW", True)
    monkeypatch.setattr(serve, "find_browser_exe", lambda: None)
    monkeypatch.setattr(serve, "is_elevated", lambda: True)
    calls: list[list[str]] = []
    monkeypatch.setattr("subprocess.Popen", _record_popen(calls))

    assert serve.open_browser("http://127.0.0.1:8000/") == "explorer"
    assert calls and calls[0][0].lower().endswith("explorer.exe"), calls
    assert calls[0][1] == "http://127.0.0.1:8000/"


def test_browser_falls_back_to_default_when_elevated_and_no_chromium(monkeypatch):
    monkeypatch.setattr(serve, "_PREFER_APP_WINDOW", True)
    monkeypatch.setattr(serve, "find_browser_exe", lambda: None)
    monkeypatch.setattr(serve, "is_elevated", lambda: False)
    seen: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: seen.append(url) or True)

    assert serve.open_browser("http://127.0.0.1:8000/") == "browser"
    assert seen == ["http://127.0.0.1:8000/"]


def test_browser_flag_skips_the_app_window(monkeypatch):
    """`--browser` = 用系统默认浏览器（独立应用窗口是默认行为）。"""
    monkeypatch.setattr(serve, "find_browser_exe",
                        lambda: pytest.fail("--browser 下不该去找应用窗口"))
    monkeypatch.setattr(serve, "is_elevated", lambda: False)
    seen: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: seen.append(url) or True)
    serve._PREFER_APP_WINDOW = False                 # `main(--browser)` 的效果

    assert serve.open_browser("http://127.0.0.1:8123/") == "browser"
    assert seen == ["http://127.0.0.1:8123/"]


def test_folder_opens_through_explorer(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr("subprocess.Popen", _record_popen(calls))
    if serve.os.name != "nt":
        pytest.skip("只有 Windows 走 explorer")
    assert infra_shell.open_folder("D:/x/data") is True
    assert calls and calls[0][0].lower().endswith("explorer.exe"), calls
