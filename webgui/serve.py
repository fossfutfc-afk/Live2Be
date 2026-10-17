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

from infra import logsetup, runtime

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


def main(argv: list[str] | None = None) -> int:
    global _server
    parser = argparse.ArgumentParser(prog="python -m webgui.serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--allow-ctrl-c", action="store_true",
                        help="开发用: 恢复 Ctrl+C 立刻退")
    args = parser.parse_args(argv)

    logsetup.setup()
    config = uvicorn.Config(
        "webgui.app:app", host=args.host, port=args.port,
        log_level="info", timeout_graceful_shutdown=SHUTDOWN_TIMEOUT_S,
        # 不装 uvicorn 自己那套 handler: 启动/关停的叙述由本模块讲（附带的还有一条会误导的
        # "Press CTRL+C to quit" 横幅, 而我们的 Ctrl+C 是忽略的）。
        log_config=None,
    )
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    _server = Server(config)
    if not args.allow_ctrl_c:
        _ignore_sigint()
    logger.info("WebGUI → http://%s:%d  停服务: 前端菜单「关闭服务」", args.host, args.port)
    _server.run()
    logger.info("服务已退出")
    return 0


if __name__ == "__main__":
    # ⚠️ `python -m webgui.serve` 把本文件当 `__main__` 执行 —— 那份副本里的 `_server`
    # 与路由 `import webgui.serve` 拿到的那份**不是同一个模块**（表现: 端点回"关不掉"）。
    # 按真实模块名再导一次并在那份里跑 main(): 全进程只有一份状态。
    import webgui.serve as _mod

    raise SystemExit(_mod.main())
