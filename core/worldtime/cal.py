"""cal.py — **日历算术**（纯 stdlib, 零项目内依赖; 2026-10-08）。

三个"往前/往后"的位移, 每个都有**一处**实现。它们单独成件是因为夹取规则
（月末 / 闰日）**写错不会报错, 只会静默落在另一天** —— 而"3/31 往前一个月是哪天"
这种地方, 第二份实现迟早与第一份漂开。

| 函数 | 不变量 |
|---|---|
| `shift_days(d, n)` | `d + n` 天 |
| `shift_months(d, n)` | **同月同日**; 目标月没有那一天 ⇒ 夹到**月末**（3/31 → 2/28） |
| `shift_years(d, n)` | **同年同月同日**; `2/29` ⇒ 夹到 `2/28`（与 `realtime._minus_one_year` 同源, 那份已改成调本函数） |
| `week_start(d)` | 所在**自然周的周一**（用户 2026-10-08 裁: 自然周从周一起） |

⚠️ **方向约定**: `n` **正数 = 往后（未来）**, 负数 = 往前（过去）—— 与 `timedelta` 同向。
调用方（`when.parse_when`）里的 "back N" 一律传 `-N`, 读起来就是"往前 N"。

⚠️ **越界一律抛 `ValueError`**（`date` 的范围, 如 `shift_years(d, -3000)`）——
本模块不做夹取猜测: 调用方要负责给合法的 `n`（`parse_when` 把 `N` 夹在 `[0, 99]`）。
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta


def shift_days(d: date, n: int) -> date:
    """`d` 往后 `n` 天（负数 = 往前）。"""
    return d + timedelta(days=int(n))


def shift_months(d: date, n: int) -> date:
    """`d` 往后 `n` 个月 —— **同月同日, 月末夹住**。

    3/31 往后一个月 ⇒ 4/30（4 月没有 31 号）; 8/31 往前一个月 ⇒ 7/31 ✓。
    ⛔ **不用 `date.replace(month=…)`**: 它在 3/31 → 2/31 上直接抛 `ValueError`。
    """
    total = d.year * 12 + (d.month - 1) + int(n)
    y, m = divmod(total, 12)
    m += 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def shift_years(d: date, n: int) -> date:
    """`d` 往后 `n` 年 —— **同年同月同日, `2/29` 夹到 `2/28`**。

    ⚠️ 与 `realtime._minus_one_year`（EXT, 原第一份）**同一语义**; 那份现在转调本函数,
    所以"闰日怎么处置"全库只有这一处。
    """
    try:
        return d.replace(year=d.year + int(n))
    except ValueError:                       # 2/29 → 目标年不是闰年
        return d.replace(year=d.year + int(n), day=28)


def week_start(d: date) -> date:
    """`d` 所在**自然周的周一**（`date.weekday()`: 0 = 周一 ⇒ 零换算）。

    ⛔ **不引入 `isocalendar()`**: 它把"本周"变成 ISO 周号, 年末会多出
    "第 53 周"那一族边界问题, 而周首日它定的也是周一 —— 收益为零。
    """
    return d - timedelta(days=d.weekday())


__all__ = ["shift_days", "shift_months", "shift_years", "week_start"]
