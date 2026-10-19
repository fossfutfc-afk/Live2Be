"""进程级运行态 —— 关停信号 + 在途登记（引擎与外壳之间的最小接缝）。

两件事，都很小:

1. **关停信号**: 外壳收到"要关了"（前端点退出 / 控制台 Ctrl+C / 系统信号）时置一次,
   长任务在**提交前**查一眼就能自己收手。为什么必须查: `digest` 的提交是"先写图、
   后写水位", 中途被杀就会留下"图新、水位旧"（详见 `core/brain/store._heal_watermark`）。
2. **在途登记**: 谁在跑、跑到第几步、跑了多久 —— 前端"等它跑完再关"要读它,
   控制台的关停日志也要。

⚠️ **中止 ≠ 失败**: 被关停打断的 digest 必须**不写盘、不计失败次数**。计数的后果是
`DIGEST_MAX_ATTEMPTS=3` 之后水位被推过去、这一段**永久放弃** —— 三次 Ctrl+C 就该丢记忆
是荒唐的。所以 `digest_segment` 的中止路径走 `_abort()`, 不走 `_fail()`。
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

_SHUTDOWN = threading.Event()
_lock = threading.Lock()
#: 名字 → (阶段, 起始 monotonic)
_busy: dict[str, tuple[str, float]] = {}


def request_shutdown() -> bool:
    """置关停信号（幂等）。返回是否是**第一次**置位。"""
    first = not _SHUTDOWN.is_set()
    _SHUTDOWN.set()
    if first:
        logger.info("收到关停请求：长任务在下一个安全点收手（已提交的不回滚）")
    return first


def shutdown_requested() -> bool:
    return _SHUTDOWN.is_set()


def clear_shutdown() -> None:
    _SHUTDOWN.clear()


def begin(name: str, stage: str = "") -> None:
    """登记一个在途任务（同名重复登记 = 更新阶段）。"""
    with _lock:
        _busy[name] = (stage, time.monotonic())


def stage(name: str, phase: str) -> None:
    """更新**已登记的**任务阶段（没登记就什么都不做 —— 直接调 `digest_segment`
    的测试与探针不该因此变成"在途任务"）。"""
    with _lock:
        if name not in _busy:
            return
        _busy[name] = (phase, _busy[name][1])


def end(name: str) -> None:
    with _lock:
        _busy.pop(name, None)


def snapshot() -> dict:
    """给端点/日志看的快照: `{"shutdown": bool, "busy": [{"name","stage","elapsed_s"}]}`。"""
    now = time.monotonic()
    with _lock:
        busy = [{"name": n, "stage": s or "-", "elapsed_s": round(now - t, 1)}
                for n, (s, t) in _busy.items()]
    return {"shutdown": _SHUTDOWN.is_set(), "busy": busy}


def wait_idle(timeout: float) -> bool:
    """等所有在途任务收手，最多 `timeout` 秒。返回是否真的全空了。"""
    deadline = time.monotonic() + max(0.0, timeout)
    while time.monotonic() < deadline:
        with _lock:
            if not _busy:
                return True
        time.sleep(0.05)
    with _lock:
        return not _busy


# ---------------------------------------------------------------------------
# 页面加载计数 —— 外壳用它回答"我开的那个窗口到底连上没有"
# ---------------------------------------------------------------------------
# 为什么不下结论而是数请求: 起浏览器这一步**我们看不到结果**（`Popen` 成功只代表
# 进程起来了, 空白窗口也算成功）。唯一可靠的信号是"服务端收到过 `/`"。
# ⚠️ 只数 `/`（窗口的第一跳）, 不数 `/static/*` 与 `/api/*`。
_page_loads = 0


def note_page_load() -> None:
    """记一次页面加载（`GET /` 的处理器里调）。"""
    global _page_loads
    _page_loads += 1


def page_loads() -> int:
    """累计收到过几次 `/`（单调递增; 外壳拿"开窗前后有没有涨"当判据）。"""
    return _page_loads


def _reset_for_tests() -> None:
    """只给测试: 清信号与登记。"""
    global _page_loads
    _SHUTDOWN.clear()
    _page_loads = 0
    with _lock:
        _busy.clear()
