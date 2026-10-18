"""OS 级小动作 —— 开目录 / 起进程 / 判断提权（**不依赖任何上层包**）。

为什么住在 `infra`: 两处都要用它 —— `webgui/serve.py`（开浏览器、开目录）与
「资源配置」辅助工具（`setup_tool`，**不能**为了开一个目录就把 fastapi/uvicorn 拖进来）。
放在 `infra` 之后两边都只是 `from infra.shell import …`。
"""

from __future__ import annotations

import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def is_elevated() -> bool:
    """本进程是管理员权限吗（Windows；别处一律 False）。"""
    if os.name != "nt":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (ImportError, AttributeError, OSError):
        return False


def launch(args: list[str]) -> bool:
    """启动外部程序。**提权时先降到普通权限再启动。**

    为什么必须降: 从管理员终端起的浏览器会继承管理员令牌并驻留后台；之后用户用普通权限
    双击时, 新进程没法把地址交给那个管理员实例（UIPI）—— 表现是灰色空窗口, 关窗时还会问
    "要不要用普通权限"。`runas /trustlevel:0x20000` 是 Windows 自带的"基本用户"令牌。
    """
    if os.name == "nt" and is_elevated():
        cmdline = " ".join(f'"{a}"' if " " in a else a for a in args)
        try:
            subprocess.Popen(["runas", "/trustlevel:0x20000", cmdline])
            return True
        except OSError:                              # runas 不在: 退回直接启动
            logger.warning("runas 降权失败, 直接启动（可能带管理员令牌）")
    try:
        subprocess.Popen(args)
        return True
    except OSError:
        return False


def open_folder(path: str) -> bool:
    """在资源管理器里打开一个目录（经 explorer 转交, 不继承管理员令牌）。"""
    if os.name != "nt":
        return False
    try:
        subprocess.Popen(["explorer.exe", path])
        return True
    except OSError:
        return False
