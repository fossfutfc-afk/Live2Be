# -*- coding: utf-8 -*-
"""时间注记单测（T13 / `§4.11` 的"进 prompt"）—— `core/worldtime/prompt_time.py`。

钉住四条:
  1. **季节/日夜**是 `month`/`phase` 的纯函数（无新状态）
  2. **虚构年份 2100**, 月/日/星期几照真实; **闰年边界**（2/29 → 3/1）不构造非法日期
  3. **归因与边界**: "手机上的日期"必须写明来源 + "问起才引用"
  4. **措辞虚化**: 间隔注记绝不出现小时/分钟/精确日期（与 I-c 同一条纪律）
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.worldtime import (                                   # noqa: E402
    FICTIONAL_YEAR,
    SEASONS,
    StoryTime,
    phone_date_note,
    real_gap_note,
    story_time_note,
    time_notes,
)
from core.worldtime.prompt_time import WEEKDAYS, phone_date    # noqa: E402


# ---------------------------------------------------------------------------
# 1. 季节与日夜（纯派生）
# ---------------------------------------------------------------------------

def test_season_is_pure_function_of_month():
    """★ 季节无新状态 —— 由 `month` 算出, 边界 3/6/9/12。"""
    got = {}
    for m in range(1, 13):
        st = StoryTime.from_sim_day((m - 1) * 28 * 5)   # 每月第 1 天
        got[st.month] = st.season
    assert got[3] == got[4] == got[5] == "春"
    assert got[6] == got[7] == got[8] == "夏"
    assert got[9] == got[10] == got[11] == "秋"
    assert got[12] == got[1] == got[2] == "冬"
    assert set(SEASONS) == {"春", "夏", "秋", "冬"}
    print(f"    season: 3~5春/6~8夏/9~11秋/12~2冬（12 个月全覆盖）")


def test_day_part_maps_every_phase():
    parts = {StoryTime.from_sim_day(n).phase: StoryTime.from_sim_day(n).day_part
             for n in range(5)}
    assert set(parts) == {"晨", "昼", "夕", "夜", "凌晨"}, parts
    assert parts["晨"] == "清晨" and parts["夜"] == "夜里"
    print(f"    day_part: {parts}")


def test_date_label_is_coarse():
    """★ 粗日期 —— **不带周、不带精确日**（I-c 同一条纪律）。"""
    label = StoryTime.from_sim_day(65).date_label
    assert label == "1年4月·春·清晨", label
    for bad in ("周", "第", "日"):
        assert bad not in label, f"粗日期里出现了 {bad}: {label}"
    print(f"    date_label: {label}（无周/无精确日）")


# ---------------------------------------------------------------------------
# 2. 手机日期（虚构年 + 闰年边界）
# ---------------------------------------------------------------------------

def test_phone_date_uses_fictional_year():
    y, m, d, _, wd = phone_date(datetime(2026, 9, 13, 20, 41))
    assert y == FICTIONAL_YEAR
    assert (m, d) == (9, 13), "月/日必须照真实"
    assert wd in WEEKDAYS
    # 星期几必须**按虚构年那天**算, 不是照抄真实年
    real_wd = WEEKDAYS[datetime(2026, 9, 13).weekday()]
    assert wd == WEEKDAYS[datetime(FICTIONAL_YEAR, 9, 13).weekday()]
    print(f"    手机日期: {y}年{m}月{d}日（{wd}）; 真实 {2026} 那天是 {real_wd}")


def test_phone_date_handles_leap_boundary():
    """★ 2100 **不是闰年** → 真实 2/29 平移到 3/1, **绝不构造非法日期**。"""
    assert not (FICTIONAL_YEAR % 4 == 0 and
                (FICTIONAL_YEAR % 100 != 0 or FICTIONAL_YEAR % 400 == 0)), \
        "2100 被当成闰年了——测试前提错了"
    y, m, d, _, _ = phone_date(datetime(2028, 2, 29, 12, 0))
    assert (m, d) == (3, 1), (m, d)
    print(f"    闰年边界: 真实 2028-02-29 → {y}年{m}月{d}日（2100 非闰年）")


def test_phone_note_has_attribution_and_boundary():
    """★ 归因（"手机上的"）+ 使用边界（"问起才引用"）—— 少任一条都会破墙。"""
    note = phone_date_note(datetime(2026, 9, 13, 20, 41))
    assert "手机上的日期" in note, f"缺归因: {note}"
    assert "问起" in note and "不要主动" in note, f"缺使用边界: {note}"
    assert str(FICTIONAL_YEAR) in note
    print(f"    phone_note: 归因+边界齐全")


# ---------------------------------------------------------------------------
# 3. 现实间隔（虚化）
# ---------------------------------------------------------------------------

def test_real_gap_is_vague():
    """★ 绝不出现小时/分钟/精确日期 —— 只给人类口径的间隔。"""
    now = datetime(2026, 9, 13, 20, 41)
    cases = [
        ("2026-09-13T20:30:00", "刚刚"),
        ("2026-09-13T10:00:00", "今天"),
        ("2026-09-12T10:00:00", "昨天"),
        ("2026-09-10T10:00:00", "天前"),
        ("2026-08-20T10:00:00", "周前"),
        ("2026-01-01T10:00:00", "很久"),
    ]
    for ts, expect in cases:
        got = real_gap_note(ts, now=now)
        assert expect in got, f"{ts} → {got!r} 不含 {expect!r}"
        for bad in ("小时", "分钟", "：", "2026"):
            assert bad not in got, f"间隔注记出现精确形态 {bad}: {got}"
    print(f"    间隔: 刚刚/今天/昨天/N天前/N周前/很久 —— 无精确刻度")


def test_real_gap_empty_on_bad_input():
    now = datetime(2026, 9, 13, 20, 41)
    for bad in (None, "", "不是时间", 123):
        assert real_gap_note(bad, now=now) == "", bad
    # 未来时间 → 不编（负间隔）
    assert real_gap_note("2027-01-01T00:00:00", now=now) == ""
    print("    间隔: 坏值/未来 → 空（不编）")


# ---------------------------------------------------------------------------
# 4. 组装
# ---------------------------------------------------------------------------

def test_notes_bundle_and_phone_switch():
    st = StoryTime.from_sim_day(65)
    now = datetime(2026, 9, 13, 20, 41)
    mmt = time_notes(st, last_ts="2026-09-01T10:00:00", now=now, include_phone=True)
    assert len(mmt) == 3, mmt
    assert mmt[0].startswith("【现在是】")
    assert any("手机上的日期" in n for n in mmt)
    # VN: 不给手机日期
    vn = time_notes(st, last_ts="2026-09-01T10:00:00", now=now, include_phone=False)
    assert len(vn) == 2 and not any("手机" in n for n in vn)
    # 空输入 → 空列表（不注空行）
    assert time_notes(None, last_ts=None) == []
    print(f"    notes: MMT {len(mmt)} 行 / VN {len(vn)} 行（手机日期仅 MMT）")
    for n in mmt:
        print(f"      {n[:60]}")


if __name__ == "__main__":
    for fn in (test_season_is_pure_function_of_month,
               test_day_part_maps_every_phase,
               test_date_label_is_coarse,
               test_phone_date_uses_fictional_year,
               test_phone_date_handles_leap_boundary,
               test_phone_note_has_attribution_and_boundary,
               test_real_gap_is_vague,
               test_real_gap_empty_on_bad_input,
               test_notes_bundle_and_phone_switch):
        fn()
    print("all prompt_time tests passed")
