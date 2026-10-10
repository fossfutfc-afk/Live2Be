# -*- coding: utf-8 -*-
"""`worldtime/when.py` + `worldtime/cal.py` —— 她写的时间 → 检索窗口。

守门口径（每条都经**变异验红**: `.testtmp/verify_when_red.py`）:

  ① ⭐ **两族各走各的路**: `last`（自然周期段）vs `back`（点 / 滚动）——
     混了就是"上周"与"7 天前那一天"分不清（静默错范围）
  ② ⭐ **`..` 是半开**: `back 0..7 day` ≡ `back 0..=6 day`（都 = 最近 7 天）;
     偏移空间的半开是**挪一天**, 周期序号空间的半开是**挪一个周期**（不许共用）
  ③ ⭐ **`last 0` 是唯一被 `now` 截断的周期**; 自然周从周一算
  ④ ⭐ **落在将来 ≠ 认不出**: 显式年份在将来 ⇒ `future=True`（合法但空）;
     语法/名字不认 ⇒ `None`
  ⑤ 日历夹取（3/31 往前一个月 = 2/28; 2/29 往前一年 = 2/28）**只有一处实现**
  ⑥ ⛔ 拒绝清单: `back 1..`（无下界）· `N > 99` · 表外具名日 · 端点反了 ·
     节日名写成区间 · 整句话里塞时间（**绝不从句抽取**）
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.worldtime.cal import (shift_days, shift_months,  # noqa: E402
                                shift_years, week_start)
from core.worldtime.when import WIDEN_DAYS, When, parse_when  # noqa: E402

#: 固定的"现在" —— **2026-10-08 是周四**（周五/周一/月末那几条单独造 `now`）
NOW = date(2026, 10, 8)


def _w(text: str, now: date = NOW) -> When | None:
    return parse_when(text, now=now)


def _win(text: str, now: date = NOW):
    got = _w(text, now)
    assert got is not None, f"{text!r} 应当认得出"
    return got.exact


def _days(text: str, now: date = NOW) -> int:
    start, end = _win(text, now)
    return (end - start).days + 1


# ---------------------------------------------------------------------------
# ⑤ 日历算术（一处实现）
# ---------------------------------------------------------------------------

def test_cal_shifts_clamp_at_month_end_and_leap_day():
    """夹取: 3/31 往前一个月 = 2/28（不是抛 `ValueError`）; 2/29 往前一年 = 2/28。"""
    assert shift_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert shift_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert shift_months(date(2028, 3, 31), -1) == date(2028, 2, 29)   # 闰年就到 29
    assert shift_months(date(2026, 8, 31), -1) == date(2026, 7, 31)   # 目标月有 31 号
    assert shift_years(date(2028, 2, 29), -1) == date(2027, 2, 28)
    assert shift_years(date(2026, 10, 8), -1) == date(2025, 10, 8)
    assert week_start(date(2026, 10, 8)) == date(2026, 10, 5)         # 周四 → 周一
    assert week_start(date(2026, 10, 5)) == date(2026, 10, 5)         # 周一 → 自己
    assert week_start(date(2026, 10, 11)) == date(2026, 10, 5)        # 周日 → 本周一
    print("    cal: 月末 / 闰日 / 周首日 夹取各一条")


# ---------------------------------------------------------------------------
# ① + ③ `last`（自然周期段）
# ---------------------------------------------------------------------------

def test_last_is_a_natural_period_and_zero_is_truncated():
    """⭐ `last N` = 倒数第 N 个**自然周期**; **只有 N=0 截到今天**。"""
    assert _win("last 1 week") == (date(2026, 9, 28), date(2026, 10, 4))   # 上周（整周）
    assert _win("last 2 week") == (date(2026, 9, 21), date(2026, 9, 27))
    assert _win("last 0 week") == (date(2026, 10, 5), NOW)                 # 本周**到今天**
    assert _win("上周") == _win("last 1 week")                             # 人话同义
    assert _win("last 1 month") == (date(2026, 9, 1), date(2026, 9, 30))
    assert _win("last 0 month") == (date(2026, 10, 1), NOW)
    assert _win("last 1 year") == (date(2025, 1, 1), date(2025, 12, 31))
    assert _win("last 0 year") == (date(2026, 1, 1), NOW)
    assert _days("last 0..=3 week") == 25       # 本周(4 天) + 前 3 整周 = 4 个自然周
    assert _win("last 0..=3 week")[0] == date(2026, 9, 14)


def test_week_boundary_days(monkeypatch=None):
    """⭐ 周首日 = 周一: 周一问"上周"给完整的上周一~周日; 周日问"本周"给整七天。"""
    monday = date(2026, 10, 5)
    sunday = date(2026, 10, 11)
    assert _win("last 1 week", monday) == (date(2026, 9, 28), date(2026, 10, 4))
    assert _win("last 0 week", monday) == (monday, monday)          # 本周一 = 今天一天
    assert _win("last 0 week", sunday) == (monday, sunday)          # 周日 = 整周
    assert _days("last 1 week", monday) == 7 and _days("last 1 week", sunday) == 7


# ---------------------------------------------------------------------------
# ② `back`（点 / 滚动）与半开
# ---------------------------------------------------------------------------

def test_back_is_a_point_and_half_open_moves_one_day():
    """⭐ `back N unit` = **N 个单位前的今天**（点）; `A..B` 半开 ⇒ **挪一天**。"""
    assert _win("back 1 week") == (date(2026, 10, 1), date(2026, 10, 1))
    assert _win("back 1 year") == (date(2025, 10, 8), date(2025, 10, 8))   # 一年前的今天
    assert _days("back 0..7 day") == 7 and _days("back 0..=6 day") == 7
    assert _win("back 0..7 day") == _win("back 0..=6 day")                 # 两种写法同窗口
    assert _win("back ..=6 day") == _win("back 0..=6 day")                 # 起点省 = 0
    assert _days("back 6..7 week") == 7                                    # ⚠️ 不许塌成一天
    assert _days("back 6..=7 week") == 8                                   # `..=` 两端都含
    assert _win("back 1 month") == (date(2026, 9, 8), date(2026, 9, 8))
    assert _win("一年前的今天") == _win("back 1 year")                      # 人话同义
    assert _win("6 周前") == _win("back 6 week")


def test_last_and_back_differ_where_it_matters():
    """⭐ 两族在 `week/month/year` 上**必须不同**（这正是分两个前缀的理由）。"""
    assert _win("last 1 year") != _win("back 1 year")
    assert _days("last 1 year") == 365 and _days("back 1 year") == 1
    assert _days("last 1 week") == 7 and _days("back 1 week") == 1
    # 周期长度 = 1 天的那些单位上**故意重合**（`day` 与节日名）
    assert _win("last 1 day") == _win("back 1 day")
    assert _win("last 1 christmas") == _win("back 1 christmas")


# ---------------------------------------------------------------------------
# ④ 将来 vs 认不出; 节日名两条路
# ---------------------------------------------------------------------------

def test_future_is_legal_but_empty_while_unparsable_is_none():
    """⭐ 规则⑥: **显式年份**落在将来 ⇒ `future=True`（不是错）; 认不出 ⇒ `None`。"""
    fut = _w("2027/01/01")
    assert fut is not None and fut.future and fut.exact == (date(2027, 1, 1),
                                                            date(2027, 1, 1))
    assert fut.wide is None                       # 将来 ⇒ 连放宽都没有（没什么可查）
    assert _w("2026/12/25").future is True
    assert _w("2026/09/25").future is False
    for bad in ("", "   ", "back 4 wek", "last 1..0", "10/1..=9/30", "9 月",
                "周日", "上周我们去咖啡厅那天", "last 1..", "back 1..",
                "back 100 day", "last 1..=2 christmas", "中秋", "明天"):
        assert _w(bad) is None, bad


def test_bare_festival_is_the_last_past_one_but_last_zero_is_not():
    """⭐⭐ 两条路**刻意不同**: 裸「圣诞节」= 最近一次**已过**; `last 0` = 今年那次
    （9 月问 ⇒ 落在将来 ⇒ 返空）。共用一条路就有一边静默错范围。"""
    assert _win("圣诞节") == (date(2025, 12, 25), date(2025, 12, 25))
    assert _win("去年圣诞") == _win("last 1 christmas")
    assert _win("上个圣诞") == _win("last 1 christmas")
    assert _win("前年圣诞") == _win("last 2 christmas")
    zero = _w("last 0 christmas")
    assert zero is not None and zero.future and zero.exact[0] == date(2026, 12, 25)
    # 12/26 那天问「圣诞节」⇒ 昨天的那个 ✓（同一年的已过）
    assert _win("圣诞节", date(2026, 12, 26)) == (date(2026, 12, 25),
                                                 date(2026, 12, 25))
    assert _win("last 0 christmas", date(2026, 12, 26))[0] == date(2026, 12, 25)


# ---------------------------------------------------------------------------
# 绝对形式（含"无年份 = 最近一次已过"）
# ---------------------------------------------------------------------------

def test_absolute_forms():
    assert _win("2026/09/25") == (date(2026, 9, 25), date(2026, 9, 25))
    assert _win("2026-09-25") == _win("2026/09/25")           # ISO 写法也收
    assert _win("9/25") == _win("2026/09/25")                 # 无年份 = 今年那个（已过）
    assert _win("12/31") == (date(2025, 12, 31), date(2025, 12, 31))   # 今年还没到 ⇒ 去年
    assert _win("2026/09") == (date(2026, 9, 1), date(2026, 9, 30))
    assert _win("2026") == (date(2026, 1, 1), date(2026, 12, 31))
    assert _win("2026/02") == (date(2026, 2, 1), date(2026, 2, 28))    # 平年 2 月
    assert _win("2028/02") == (date(2028, 2, 1), date(2028, 2, 29))    # 闰年 2 月
    assert _win("2026/09/20..=2026/09/28") == (date(2026, 9, 20), date(2026, 9, 28))
    assert _win("2026/09/20..2026/09/28")[1] == date(2026, 9, 27)      # 半开
    assert _win("12/28..=1/3") == (date(2025, 12, 28), date(2026, 1, 3))  # 跨年（各自最近）


# ---------------------------------------------------------------------------
# ⑤ 放宽（只对单日窗口, 末端夹到今天）
# ---------------------------------------------------------------------------

def test_widening_only_for_single_day_windows():
    got = _w("back 1 year")
    assert got.wide == (shift_days(got.exact[0], -WIDEN_DAYS),
                        shift_days(got.exact[1], WIDEN_DAYS))
    assert _w("last 1 week").wide is None          # 周期不放宽
    assert _w("back 0..=6 day").wide is None       # 区间不放宽
    assert _w("2026/09").wide is None
    today = _w("back 0 day")                       # ⚠️ 末端夹到今天（不许伸进将来）
    assert today.exact == (NOW, NOW)
    assert today.wide == (date(2026, 10, 6), NOW)


# ---------------------------------------------------------------------------
# ③ 人话（同义改写）与数字
# ---------------------------------------------------------------------------

def test_phrases_are_synonyms_not_approximations():
    assert _win("昨天") == _win("back 1 day")
    assert _win("前天") == _win("back 2 day")
    assert _win("大前天") == _win("back 3 day")
    assert _win("最近一周") == _win("back 0..=6 day")
    assert _win("最近三天") == _win("back 0..=2 day")
    assert _win("最近一个月") == _win("back 0..=1 month")
    assert _win("两天前") == _win("back 2 day")
    assert _win("三天前") == _win("back 3 day")
    assert _win("去年") == _win("last 1 year")
    assert _win("前年") == _win("last 2 year")
    assert _win("上个月") == _win("last 1 month")
    assert _w("十一 天前") is None              # 中文数量词只到十（「十一」拒）


def test_parse_when_never_raises_and_records_the_source():
    got = _w("上周")
    assert got.source == "上周"                 # `look` 的结果头回显她的原话
    assert _w(None) is None and _w(123) is None
    assert parse_when("last 1 week", now=None) is None      # 不给"现在" ⇒ 不猜
    assert parse_when("last 1 week",
                      now=datetime(2026, 10, 8, 21, 0,
                                   tzinfo=timezone.utc)) is not None
