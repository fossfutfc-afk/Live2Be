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

    ⚠️ **runas 不可用时不许"退回直接启动"**（2026-10-19）: 那会起出一个**提权的浏览器**,
    把它的 profile 写成高权限状态 —— 之后同目录下普通权限的启动就打不开它（实测: 进程
    rc=0、零窗口, 真机表现为黑窗口 + "现有实例正在以提升权限运行"）。宁可不启动, 让调用方
    退回"经 explorer / 默认浏览器"那条正常权限的路。

    ⚠️ **实际命令行必须进日志**: "是谁在弹权限提示"从外面看不出来, 唯一能对账的是"这一秒
    我们 spawn 了什么"。日志里没有这一行 ⇒ 不是我们起的。
    """
    if os.name == "nt" and is_elevated():
        cmdline = " ".join(f'"{a}"' if " " in a else a for a in args)
        logger.info("启动（降权）: runas /trustlevel:0x20000 %s", cmdline)
        try:
            subprocess.Popen(["runas", "/trustlevel:0x20000", cmdline])
            return True
        except OSError as e:
            logger.warning("runas 不可用（%s）—— 不退回直接启动：提权起出来的浏览器会占住"
                           "profile, 让下次普通启动打不开它", e)
            return False
    try:
        logger.info("启动: %s", " ".join(args))
        subprocess.Popen(args)
        return True
    except OSError as e:
        logger.warning("启动失败: %r（%s）", args, e)
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
