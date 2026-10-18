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


__all__ = ["app_root", "default_path", "last_error", "raw", "section", "update"]

# ---------------------------------------------------------------------------
# 写（**唯一写入口**）—— 设置页与「资源配置」辅助工具都走这里
# ---------------------------------------------------------------------------
# 从前这套"清洗 + 手写 toml"只有一个读者（webgui 设置页），装在 `webgui/store.py`
# 里；辅助工具也要写 `[paths]` 之后就是**两处各写一份**（本仓已经因为"两处写"
# 出过一次事故）。下沉到这个唯一读写口之后：读 `raw()` / 写 `write()` 对称。

_SCALARS = (str, bool, int, float)      # 注意: bool 是 int 子类, 判值时要先判 bool


def _sane_value(v) -> bool:
    """叶子值能否安全写进 toml 并读回。

    只认真标量。`None` **必须拒收**: 非标量会被序列化成字符串 `"None"`, 读回就是垃圾值。
    dict/list 同理——它们会被降级成"看起来合法的字符串", 类型静默漂移。
    """
    return isinstance(v, _SCALARS)


def _sane_table(v) -> bool:
    """表（嵌套 dict）能否写: 键全 str, 值递归合法。"""
    if not isinstance(v, dict) or not v:
        return False
    for k, sub in v.items():
        if not isinstance(k, str):
            return False
        if isinstance(sub, dict):
            if not _sane_table(sub):
                return False
        elif not _sane_value(sub):
            return False
    return True


def _emit_table(data: dict, prefix: tuple[str, ...], lines: list[str]) -> None:
    """写一张表: 先标量、后子表（TOML 的表头顺序要求）。

    只含子表的中间表不写空表头（`[a.b]` 紧跟 `[a.b.c]` 是噪声, 语义等价）。
    """
    scalars, tables = [], []
    for k, v in data.items():
        (tables if isinstance(v, dict) else scalars).append((k, v))
    if prefix and (scalars or not tables):
        lines.append("[" + ".".join(prefix) + "]")
    for k, v in scalars:
        if isinstance(v, bool):
            lines.append(f'  {k} = {"true" if v else "false"}')
        elif isinstance(v, (int, float)):
            lines.append(f"  {k} = {v}")
        else:
            escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'  {k} = "{escaped}"')
    if prefix and (scalars or not tables):
        lines.append("")
    for k, v in tables:
        _emit_table(v, (*prefix, k), lines)


def to_toml(data: dict) -> str:
    """轻量 toml 序列化（分组 + k=v; 支持嵌套表 `[a.b]`）。"""
    lines: list[str] = []
    _emit_table(data, (), lines)
    return "\n".join(lines).rstrip() + "\n"


def write(data: dict) -> Path:
    """写 settings.toml —— **保真落盘**: 传进来有什么就写回什么, 只做类型防呆。

    已知取舍: 整文件重写、**注释不保留**（tomllib 解析后即丢; 想留注释得上 tomlkit）。
    "这次不改某个键"要在**调用方**滤掉 —— 本层对不可写的值只是跳过, 跳过 = 该键消失。
    """
    clean: dict = {}
    if isinstance(data, dict):
        for section, fields in data.items():
            if not isinstance(section, str) or not isinstance(fields, dict):
                continue
            out: dict = {}
            for key, val in fields.items():
                if not isinstance(key, str):
                    continue
                if isinstance(val, dict):
                    if _sane_table(val):
                        out[key] = val
                    continue
                if _sane_value(val):
                    out[key] = val
            clean[section] = out
    path = default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_toml(clean), encoding="utf-8")
    return path


def update(section: str, **values) -> Path:
    """改一段里的几个键（`""` = 删掉该键），其余原样写回。

    `write()` 是**整文件重写** —— 拿"只有这一段"的 dict 去写会把别的段抹掉。
    想"只改一个键"就走这里：先读磁盘、只动这一段、再写回。
    """
    data = raw()
    current = data.get(section)
    merged = dict(current) if isinstance(current, dict) else {}
    for key, value in values.items():
        if isinstance(value, str):
            value = value.strip()
        if isinstance(value, str) and not value:
            merged.pop(key, None)
        else:
            merged[key] = value
    if merged:
        data[section] = merged
    else:
        data.pop(section, None)
    return write(data)
