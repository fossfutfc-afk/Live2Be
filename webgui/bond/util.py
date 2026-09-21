# -*- coding: utf-8 -*-
"""`webgui.bond` 的**跨模块纯小工具**（C4 新开, `docs/EXEC_SPLIT.md`）。

## 为什么单开一个模块

只有 `_ms_since`（计时埋点, EXEC_BOND_LATENCY §6.1）: 它是**纯函数**（只依赖
`time.monotonic`）, 却被 `lanes` / `watchdog` / `pregen` / `api` **四处**要用。
放进 `state.py` 属"位置放错"（那里是状态模型）; 放进 `lanes.py` 更别扭
（别的模块凭什么从"双路 lane"借计时器）; 复制一份则会漂。⇒ 单开 3 行的叶子模块。

## 纪律

只放**无状态、跨模块**的纯小工具。一旦某个工具只有一方用（如 `_thread_alive` 只有
watchdog 用）, 就留在那个模块里, **别往这里堆**; 也不许放依赖注入与业务逻辑。
"""
from __future__ import annotations

import time


def _ms_since(t0: float) -> int:
    """自 t0（time.monotonic）起的毫秒（计时埋点, EXEC_BOND_LATENCY §6.1）。"""
    return int((time.monotonic() - t0) * 1000)
