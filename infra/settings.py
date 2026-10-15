"""settings.toml 的唯一读入口。

每次调用都重新读盘（不缓存）——所以改完立刻生效，也不必重启或手动 reload。
缺文件 → {}（不是错误）；解析失败 → {} 并记住原因，由 last_error() 报出来。

只管"读文件"这一层。默认值留在各自的领域模块（"缺省开"这类是业务语义），类型校验与
环境变量优先级也留在那儿（LIVE2BE_IMAGE 那种是硬关开关）。

LIVE2BE_SETTINGS 可以把这份文件指到别处（测试与多份配置用）。
"""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

_ENV = "LIVE2BE_SETTINGS"

_last_error: str = ""


def app_root() -> Path:
    """settings.toml 该在哪儿。打包后是 exe 同级，源码树是仓库根。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def default_path() -> Path:
    """本进程读的那份 settings.toml（LIVE2BE_SETTINGS 可覆盖）。"""
    env = os.environ.get(_ENV, "").strip()
    return Path(env) if env else app_root() / "settings.toml"


def last_error() -> str:
    """上次读取失败的原因（"" = 没失败）。启动日志与设置页用它告诉用户配置没读进去。"""
    return _last_error


def raw() -> dict:
    """全量设置。文件不在或读坏 → {}（并记 last_error）。

    每次调用都重新读盘解析：一次 5 KB 的 TOML 解析是几十微秒，而"缓存住旧配置"是
    实打实的错（2026-10-15 踩过：同长度的改写落在同一个 mtime 刻度里，被挡在缓存外）。
    """
    global _last_error
    path = default_path()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _last_error = ""                       # 没配过不是错误
        return {}
    except (OSError, ValueError) as e:
        _last_error = f"{path.name}: {type(e).__name__}: {e}"
        return {}
    _last_error = ""
    return data if isinstance(data, dict) else {}


def section(name: str) -> dict:
    """取一个分组（不是表 → {}）。"""
    val = raw().get(name)
    return val if isinstance(val, dict) else {}


__all__ = ["app_root", "default_path", "last_error", "raw", "section"]
