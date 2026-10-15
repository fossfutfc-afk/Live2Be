"""settings.toml 的唯一读入口。

按 mtime + size 失效：文件没动就复用上次解析结果，文件一动立刻重读（所以改完不必重启
就能生效）。缺文件 → {}（不是错误）；解析失败 → {} 并记住原因，由 last_error() 报出来。

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

_cache: dict | None = None
_cache_key: tuple[int, int, str] | None = None
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


def reset() -> None:
    """丢缓存。正常流程靠 mtime 自动失效，这个留给测试。"""
    global _cache, _cache_key
    _cache, _cache_key = None, None


def raw() -> dict:
    """全量设置（带缓存）。文件不在或读坏 → {}。"""
    global _cache, _cache_key, _last_error
    path = default_path()
    try:
        st = path.stat()
    except OSError:
        _cache, _cache_key, _last_error = {}, None, ""
        return _cache
    key = (st.st_mtime_ns, st.st_size, str(path))
    if _cache is not None and key == _cache_key:
        return _cache
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        # 记住 key：坏文件不必每次调用都重读一遍
        _cache, _cache_key = {}, key
        _last_error = f"{path.name}: {type(e).__name__}: {e}"
        return _cache
    _cache = data if isinstance(data, dict) else {}
    _cache_key, _last_error = key, ""
    return _cache


def section(name: str) -> dict:
    """取一个分组（不是表 → {}）。"""
    val = raw().get(name)
    return val if isinstance(val, dict) else {}


__all__ = ["app_root", "default_path", "last_error", "raw", "reset", "section"]
