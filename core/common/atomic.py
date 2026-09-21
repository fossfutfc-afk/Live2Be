# -*- coding: utf-8 -*-
"""原子替换的 **Windows 健壮性包装** —— `os.replace` + 短暂占用重试。

## 为什么需要它

本项目的原子写一律是"temp 同目录 → `os.replace(tmp, path)`"（绝不半写）。
在 Windows 上 `os.replace` 会在**目标文件正被别的进程/线程短暂打开**时抛
`PermissionError`（WinError 5 / 32「另一个程序正在使用此文件」）——常见来源是杀软、
搜索索引器、以及另一端刚刚读取。**这不是"文件写坏了", 而是"这一刻不让换"**；
等几十毫秒通常就成功。实测过一次真实红（测试期 temp churn, `core/session/io.py`）。

## 语义

· 只对**瞬时**错误重试（`PermissionError` / WinError 5/32/33）;
  `FileNotFoundError`（temp 没了）等**不重试**, 立即抛;
· 重试用尽 → **原样抛出**（不吞异常: 上层照旧"静默降级 / 本轮不记", 但不假装成功）;
· 退避 = 30ms 起指数（30/60/120/240）, 默认 5 次尝试 ⇒ 最坏多等 ~0.45s;
· 测试可注入参数（`attempts` / `base_delay`）或 patch 下面的 `_replace`。
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

#: 默认尝试次数（含第一次）与退避基数
REPLACE_ATTEMPTS = 5
REPLACE_BASE_DELAY = 0.03

#: 间接层: 测试 patch 它（**叶子模块的全局**, 不是包属性——见 EXEC_SPLIT C1a 的教训）
_replace = os.replace

#: Windows 上"文件被占用"的 winerror（5=拒绝访问 / 32=共享冲突 / 33=区域锁定）
_TRANSIENT_WINERRORS = frozenset({5, 32, 33})


def _is_transient(exc: OSError) -> bool:
    """这个替换失败是"等一会儿就好"的那一类吗。"""
    if isinstance(exc, PermissionError):
        return True
    return getattr(exc, "winerror", None) in _TRANSIENT_WINERRORS


def replace_with_retry(
    src: str | Path,
    dst: str | Path,
    *,
    attempts: int | None = None,
    base_delay: float | None = None,
) -> None:
    """`os.replace(src, dst)` —— 被占用时短重试; 用尽后原样抛出。

    `attempts` / `base_delay` 缺省时**在调用时**读模块常量（测试可 patch, 无需传参）。
    """
    n = REPLACE_ATTEMPTS if attempts is None else attempts
    delay = REPLACE_BASE_DELAY if base_delay is None else base_delay
    last: OSError | None = None
    for i in range(max(1, n)):
        try:
            _replace(src, dst)
        except OSError as exc:                     # noqa: PERF203 — 只包一层
            if not _is_transient(exc):
                raise
            last = exc
            if i + 1 >= n:
                break
            time.sleep(delay * (2 ** i))
            logger.debug("atomic replace 被占用, 重试 %d/%d: %s (%s)",
                         i + 1, n, dst, exc)
        else:
            if i:
                logger.info("atomic replace 第 %d 次尝试成功: %s", i + 1, dst)
            return
    assert last is not None                        # n >= 1 时必然赋值
    raise last
