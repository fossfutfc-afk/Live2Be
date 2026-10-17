"""WebGUI 启动器 —— **自持 `uvicorn.Server`**，退出由前端发起。

为什么需要它（`python -m uvicorn webgui.app:app` 不够）: 要让进程"自己优雅地关自己",
就得有人**持有** `Server` 对象（`server.should_exit = True`）。用 CLI 起的时候那个对象
是 `uvicorn.main` 里的局部变量, 路由们拿不到。

`Ctrl+C` 在这里被**忽略**（只打一行提示）: 常规出口是前端菜单里的「关闭服务」。
兜底仍在 —— 关掉控制台窗口 / 任务管理器 / `taskkill`：**强杀也是安全的**, 因为提交是
两阶段的（`core/brain/store.commit`）, 且 digest 在提交前会看关停信号。

用法::

    python -m webgui.serve --port 8000     # 正常启动（Ctrl+C 不退出）
    python -m webgui.serve --allow-ctrl-c  # 开发用: 恢复 Ctrl+C 立刻退
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import signal
import threading
import time

import uvicorn

from infra import logsetup, paths, runtime

logger = logging.getLogger(__name__)

#: graceful 关停最多等长任务多久（digest 一段常见 ~40s, 硬顶 600s）
GRACEFUL_WAIT_S = 180.0

#: 强关的兜底: 这么久还没退就硬退
FORCE_BACKSTOP_S = 5.0

#: 收到 `should_exit` 之后等 in-flight 请求的上限
SHUTDOWN_TIMEOUT_S = 10

_server: Server | None = None


class Server(uvicorn.Server):
    """不接管信号 —— `SIGINT` 归 `_ignore_sigint` 管（父类会把 Ctrl+C 变成关停）。"""

    def capture_signals(self):
        return contextlib.nullcontext()


def server() -> Server | None:
    """当前自持的 server（不是本启动器起的 ⇒ None）。"""
    return _server


def request_stop(*, force: bool = False) -> dict:
    """前端「关闭服务」的入口。**立刻返回**, 真正的等待/退出在后台线程里做。"""
    if _server is None:
        logger.warning("收到关停请求, 但没有自持的 server"
                       "（不是 `python -m webgui.serve` 起的, 关不掉）")
        return {"ok": False, "reason": "launcher_missing"}
    runtime.request_shutdown()
    snap = runtime.snapshot()
    if force:
        threading.Thread(target=_force_stop, daemon=True).start()
        return {"ok": True, "mode": "force", "busy": snap["busy"]}
    threading.Thread(target=_graceful_stop, daemon=True).start()
    return {"ok": True, "mode": "graceful", "busy": snap["busy"],
            "wait_s": GRACEFUL_WAIT_S}


def _graceful_stop() -> None:
    """等在途任务收手（最多 `GRACEFUL_WAIT_S`）, 然后正常关停。"""
    if runtime.wait_idle(GRACEFUL_WAIT_S):
        logger.info("关停: 没有在途任务了, 开始收尾")
    else:
        logger.warning("关停: 等满 %.0fs 仍有在途任务 ⇒ 直接关（它们不会写盘）",
                       GRACEFUL_WAIT_S)
    _ask_exit()


def _force_stop() -> None:
    logger.warning("强制关停: 不等在途任务（提交前有关停闸, 数据不会半截）")
    threading.Thread(target=_backstop, daemon=True).start()
    _ask_exit()


def _ask_exit() -> None:
    """让 uvicorn 走正常关停（lifespan shutdown 会跑）; 先让 HTTP 响应发出去。"""
    time.sleep(0.3)
    srv = _server
    if srv is not None:
        srv.should_exit = True


def _backstop() -> None:
    """强关兜底: `FORCE_BACKSTOP_S` 之后还在跑就硬退（两阶段提交保证数据安全）。"""
    time.sleep(FORCE_BACKSTOP_S)
    logger.error("关停超时 ⇒ 硬退（提交是两阶段的, 数据不会半截）")
    os._exit(1)


def _ignore_sigint() -> None:
    def _on_sigint(_signum, _frame) -> None:
        logger.warning("Ctrl+C 已忽略 —— 要停服务请在前端菜单点「关闭服务」; "
                       "急停可关掉控制台窗口或用任务管理器（强杀也安全）")

    with contextlib.suppress(ValueError, OSError):   # 非主线程 / 无控制台
        signal.signal(signal.SIGINT, _on_sigint)


# ── 启动外壳（打包后就是"双击"那一下）──────────────────────────────────────

def url_of(host: str, port: int) -> str:
    """给浏览器/窗口用的地址（0.0.0.0 这类监听地址换成回环，否则打不开）。"""
    shown = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    return f"http://{shown}:{port}/"


def port_in_use(host: str, port: int) -> bool:
    """端口上已经有人在听吗（不区分是不是我们自己的）。"""
    import socket

    probe = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((probe, port)) == 0


def is_our_service(url: str, timeout: float = 1.5) -> bool:
    """那个端口上的是不是 Live2Be（看 `/api/runtime/status` 的形状）。"""
    import httpx

    try:
        res = httpx.get(url.rstrip("/") + "/api/runtime/status", timeout=timeout)
        body = res.json()
    except (httpx.HTTPError, OSError, ValueError):
        return False
    return res.status_code == 200 and isinstance(body, dict) and "busy" in body


def is_elevated() -> bool:
    """本进程是管理员权限吗（Windows；别的地方一律 False）。"""
    if os.name != "nt":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (ImportError, AttributeError, OSError):
        return False


def open_browser(url: str) -> bool:
    """开浏览器。返回是否"交出去了"。

    ⚠️ **提权时必须经 `explorer.exe` 代开**: 直接 `os.startfile` 会让浏览器继承管理员
    令牌, Edge 于是弹"有实例以提升的权限运行, 要不要用普通权限"—— 选"是"它会**重启自己**,
    刚打开的那个标签页连窗口一起没了（实测: 用户以为"Edge 被关闭"）。explorer 跑在用户
    正常权限上, 由它转交 URL 就不会有这问题。
    """
    if os.name == "nt" and is_elevated():
        import subprocess

        try:
            subprocess.Popen(["explorer.exe", url])
            return True
        except OSError:                              # explorer 都不在: 退回普通方式
            pass
    import webbrowser

    try:
        return bool(webbrowser.open(url))
    except Exception:                                # noqa: BLE001 — 没有浏览器/无桌面
        return False


def open_folder(path: str) -> bool:
    """在资源管理器里打开一个目录（提权时同样经 explorer 代开）。"""
    if os.name != "nt":
        return False
    import subprocess

    try:
        subprocess.Popen(["explorer.exe", path])
        return True
    except OSError:
        return False


def _open_when_ready(url: str, timeout: float = 20.0) -> None:
    """等 server 真的在听再开浏览器（否则用户看到的是连接失败页）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        srv = _server
        if srv is not None and getattr(srv, "started", False):
            break
        time.sleep(0.1)
    if open_browser(url):
        logger.info("已交给浏览器: %s（没反应就手动打开它）", url)
    else:
        logger.warning("没能自动打开浏览器 —— 请手动打开: %s", url)


def _run_windowed(url: str) -> int:
    """原生窗口模式: 服务跑在后台线程, **关窗口 = 关服务**。"""
    try:
        import webview
    except ImportError:
        logger.warning("没有 pywebview ⇒ 退回浏览器模式（pip install pywebview 可开窗口）")
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
        if _server is not None:
            _server.run()
        return 0
    srv = _server
    assert srv is not None                           # main() 里先建好才进来
    worker = threading.Thread(target=srv.run, daemon=True)
    worker.start()
    webview.create_window("Live2Be", url, width=1360, height=860, min_size=(900, 600))
    webview.start()                                  # 阻塞到窗口关闭
    logger.info("窗口已关闭 ⇒ 关停服务")
    request_stop(force=True)
    worker.join(timeout=SHUTDOWN_TIMEOUT_S + 2)
    return 0


def _banner(url: str) -> None:
    """启动横幅: 地址 + **五个根**。用户在问"数据到底存哪儿", 答案就得在这儿。"""
    logger.info("WebGUI → %s", url)
    logger.info("   角色卡  %s", paths.CONFIG_ROOT)
    logger.info("   素材    %s", paths.ASSETS_ROOT)
    logger.info("   数据    %s   （事件流 / 记忆 / 诊断日志）", paths.DATA_ROOT)
    logger.info("   设置    %s", paths.SETTINGS_PATH)
    if is_elevated():
        logger.warning("本进程以**管理员权限**运行: 浏览器与资源管理器经 explorer 代开"
                       "（否则 Edge 会提示权限并重启自己）; 建议改用普通终端启动")


def main(argv: list[str] | None = None) -> int:
    global _server
    parser = argparse.ArgumentParser(prog="python -m webgui.serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--allow-ctrl-c", action="store_true",
                        help="开发用: 恢复 Ctrl+C 立刻退")
    parser.add_argument("--window", action="store_true",
                        help="开原生窗口（pywebview）而不是浏览器")
    parser.add_argument("--no-browser", action="store_true",
                        help="不自动打开浏览器（调试 / 无桌面环境用）")
    args = parser.parse_args(argv)

    logsetup.setup()
    url = url_of(args.host, args.port)

    # 双击第二次 = 打开已经开着的那个, 而不是报端口被占
    if port_in_use(args.host, args.port):
        if is_our_service(url):
            logger.info("已经有一个 Live2Be 在跑了 ⇒ 打开它: %s", url)
            if not open_browser(url):
                logger.warning("没能自动打开浏览器 —— 请手动打开: %s", url)
            return 0
        logger.error("端口 %d 被别的程序占用 —— 换一个端口: --port 8001", args.port)
        return 2

    # ⚠️ 这里必须是**真实 import**（不是 "webgui.app:app" 字符串）: 冻结后 PyInstaller
    # 只认识分析期能看见的 import, 字符串 import 的模块不会被打进包里。
    from webgui.app import app as app_obj

    config = uvicorn.Config(
        app_obj, host=args.host, port=args.port,
        log_level="info", timeout_graceful_shutdown=SHUTDOWN_TIMEOUT_S,
        # 不装 uvicorn 自己那套 handler: 启动/关停的叙述由本模块讲（附带的还有一条会误导的
        # "Press CTRL+C to quit" 横幅, 而我们的 Ctrl+C 是忽略的）。
        log_config=None,
    )
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    _server = Server(config)
    if not args.allow_ctrl_c:
        _ignore_sigint()
    _banner(url)
    if args.window:
        return _run_windowed(url)
    if not args.no_browser:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    _server.run()
    logger.info("服务已退出")
    return 0


if __name__ == "__main__":
    # ⚠️ `python -m webgui.serve` 把本文件当 `__main__` 执行 —— 那份副本里的 `_server`
    # 与路由 `import webgui.serve` 拿到的那份**不是同一个模块**（表现: 端点回"关不掉"）。
    # 按真实模块名再导一次并在那份里跑 main(): 全进程只有一份状态。
    import webgui.serve as _mod

    raise SystemExit(_mod.main())
