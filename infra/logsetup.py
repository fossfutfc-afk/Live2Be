"""日志配置 —— 控制台短、文件全。外壳（`webgui` / `cli`）在这里一次配好。

两个 handler 各管一件事:

| 通道 | 给谁看 | 形态 |
|---|---|---|
| 控制台 | 人 | `20:06:47 digest …` · 轮询/静态请求静音 · 超长消息截断 |
| 文件 `data/diag/live2be.log` | 排障 | 全量 · 原名 · 不截断 |

分成两条的理由: **屏幕能看不等于可以少记**。校验发现的问题必须留在可 grep 的文本里,
而控制台只负责"现在在发生什么"。所以所有"变安静"的手段都只挂在控制台 handler 上
（唯一的例外是 uvicorn 的访问日志——那条同理走 logger 级 filter）。

环境变量:
- `LIVE2BE_LOG` — 控制台档位: `quiet`（WARNING+）· `normal`（默认）· `verbose`（DEBUG,
  且不静音轮询）。
- `LIVE2BE_DIAG_LOG` — 文件路径; `off`/`0`/`none` = 不落文件（测试与浏览器冒烟用,
  见 `tests/conftest.py`——否则测试噪音会混进真机诊断日志）。

诊断与错误**不进事件流**（`events.jsonl` 是 append-only 真源, 会被 digest 与回放消费）。
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

from infra import paths

#: 档位 → 级别
_LEVELS = {
    "quiet": logging.WARNING,
    "normal": logging.INFO,
    "verbose": logging.DEBUG,
}

#: 控制台**不再打印**的请求（2xx 才静音; 4xx/5xx 一律留）
_SILENT_PATH_PREFIXES = ("/static/", "/assets/", "/gallery/", "/favicon")
_SILENT_PATHS = frozenset({
    "/api/bond/status", "/api/mmt/events", "/api/runtime/status",
})

#: 控制台的 logger → 短域名（认不出的取头一段）
_DOMAINS = (
    ("core.digest", "digest"),
    ("core.bond", "bond"),
    ("core.brain", "mem"),
    ("core.session", "sess"),
    ("core.media", "media"),
    ("core.mmt", "mmt"),
    ("webgui.bond", "bond"),
    ("webgui", "web"),
    ("uvicorn", "http"),
    ("llm", "llm"),
    ("contract", "ctr"),
    ("infra", "infra"),
)

#: 控制台单行上限（超了截断; 文件里是全的）
_CONSOLE_LIMIT = 110

#: ── 控制台颜色（可关, 文件里永远不带转义码）────────────────────────────────
#: 关掉的三种方式: 不是终端（重定向/管道/IDE 抓取）· `NO_COLOR` 有值（社区约定）·
#: `LIVE2BE_COLOR=0`（本程序自己的开关）。
_DIM = "90"
_YELLOW = "33"
_RED = "91"
_DOMAIN_COLORS = {
    "web": "36",       # 青: 外壳（启动横幅、打开窗口、关停）
    "http": "34",      # 蓝: 访问日志
    "digest": "35",    # 紫: 记忆消化
    "bond": "94",      # 亮蓝: 剧情
    "mem": "96",       # 亮青: 记忆图
    "mmt": "95",       # 亮紫: 聊天
    "llm": "32",       # 绿: 模型请求
    "sess": "33",
    "media": "32",
    "ctr": "37",
    "infra": "90",
}
_STATUS_COLORS = {"2": "32", "3": "36", "4": "33", "5": "91"}

_configured = False
_handlers: list[logging.Handler] = []


def _paint(code: str, text: str) -> str:
    return f"\x1b[{code}m{text}\x1b[0m"


def _enable_vt() -> bool:
    """Windows 控制台要显式打开 VT 处理（否则转义码原样打出来）。"""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)          # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & 0x0004:                      # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, OSError):
        return False


def _color_enabled() -> bool:
    """控制台要不要上色（不是终端一律不上 —— 管道与文件里出现转义码是噪音）。"""
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("LIVE2BE_COLOR", "").strip().lower() in ("0", "off", "no", "none"):
        return False
    try:
        if not sys.stdout.isatty():
            return False
    except (AttributeError, ValueError):
        return False
    return _enable_vt()


def _paint_status(text: str) -> str:
    """只给访问日志最后一格（3 位状态码）上色: 2xx 绿 / 3xx 青 / 4xx 黄 / 5xx 红。"""
    match = re.search(r"(?<!\d)([1-5]\d\d)\s*$", text)
    if match is None:
        return text
    code = match.group(1)
    return (text[:match.start(1)] + _paint(_STATUS_COLORS[code[0]], code)
            + text[match.end(1):])


def _domain(name: str) -> str:
    """logger 名 → 短域名（认不出就取头一段）。"""
    for prefix, short in _DOMAINS:
        if name == prefix or name.startswith(prefix + "."):
            return short
    return (name.split(".")[0] or "?")[:6]


class AccessQuiet(logging.Filter):
    """uvicorn 访问日志: 轮询与静态资源的 2xx 不打印。

    `record.args` 是 uvicorn 的 `(client, method, path, http_version, status)`
    （见 `uvicorn.logging.AccessFormatter` 的 msg 模板）。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:
            return True
        path, status = str(args[2]), args[4]
        if not isinstance(status, int) or status >= 400:
            return True
        if path.startswith(_SILENT_PATH_PREFIXES):
            return False
        return path.split("?")[0] not in _SILENT_PATHS


class ConsoleFormatter(logging.Formatter):
    """`20:06:47 digest  …` —— 只给控制台用（短域名 + 截断 + 可选颜色）。

    时间**在这里自己拼**，不走 `%(asctime)s`：style 展开后再加前缀会把域名塞到时间前面。
    颜色只加在**列**上（时间 / 域名 / 状态码 / 级别），正文保持原样 —— 这样复制一行
    出去仍然可读, `\x1b` 也不会跟着宽度计算（域名的补位按**去掉转义码**后的长度算）。
    """

    def __init__(self, limit: int = _CONSOLE_LIMIT, color: bool | None = None) -> None:
        super().__init__("%(message)s", datefmt="%H:%M:%S")
        self._limit = limit
        self._color = _color_enabled() if color is None else bool(color)

    def formatMessage(self, record: logging.LogRecord) -> str:
        text = record.getMessage()
        if len(text) > self._limit:
            text = text[: self._limit].rstrip() + " …"
        stamp = self.formatTime(record, self.datefmt)
        domain = _domain(record.name)
        if not self._color:
            return f"{stamp} {domain:<6} {text}"
        pad = " " * max(0, 6 - len(domain))
        if record.levelno >= logging.ERROR:
            body = _paint(_RED, text)
        elif record.levelno >= logging.WARNING:
            body = _paint(_YELLOW, text)
        else:
            body = _paint_status(text)
        return (f"{_paint(_DIM, stamp)} "
                f"{_paint(_DOMAIN_COLORS.get(domain, '37'), domain)}{pad} {body}")


class _NoNoise(logging.Filter):
    """文件里不留每请求噪音（uvicorn access / httpx）——只留业务埋点。"""

    def filter(self, record: logging.LogRecord) -> bool:
        name = record.name
        return not (name.startswith(("httpx", "uvicorn", "werkzeug")))


def _level() -> int:
    mode = os.environ.get("LIVE2BE_LOG", "").strip().lower()
    return _LEVELS.get(mode, logging.INFO)


def _log_path() -> Path | None:
    target = os.environ.get("LIVE2BE_DIAG_LOG", "").strip()
    if target.lower() in ("off", "0", "none", "disable"):
        return None
    return Path(target) if target else paths.DIAG_LOG_PATH


def setup() -> None:
    """装好两个 handler（重复调用无副作用）。初始化期调用: 控制台 + 落盘。"""
    global _configured
    if _configured:
        return
    _configured = True

    level = _level()
    root = logging.getLogger()
    for old in _handlers:                      # 上一轮装过的（测试会重来）
        root.removeHandler(old)
    _handlers.clear()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(ConsoleFormatter())
    if level > logging.DEBUG:                  # verbose 时不静音轮询
        console.addFilter(AccessQuiet())
        logging.getLogger("uvicorn.access").addFilter(AccessQuiet())
    root.addHandler(console)
    _handlers.append(console)

    # httpx 每请求一行太吵（uvicorn 的访问日志由上头的 filter 管）
    if level > logging.DEBUG:
        logging.getLogger("httpx").setLevel(logging.WARNING)

    path = _log_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8", mode="a")
        file_handler.setLevel(level)
        file_handler.addFilter(_NoNoise())
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        root.addHandler(file_handler)
        _handlers.append(file_handler)
    except OSError as e:                       # 降级不阻断
        logging.warning("diag 日志文件不可用（降级控制台）: %s", e)


def _reset_for_tests() -> None:
    """只给测试: 拆掉 setup 装的 handler, 允许换环境变量重装。"""
    global _configured
    root = logging.getLogger()
    for handler in _handlers:
        root.removeHandler(handler)
        handler.close()
    _handlers.clear()
    logging.getLogger("uvicorn.access").filters.clear()
    _configured = False
