# -*- coding: utf-8 -*-
"""时间注记单测（T13 / `§4.11` 的"进 prompt"）—— `core/worldtime/prompt_time.py`。

钉住四条:
  1. **季节/日夜**是 `month`/`phase` 的纯函数（无新状态）
  2. **手机上的日期 = 真实日期**（虚构年 `2100` 已于 2026-09-17 删除, 用户裁决）
  3. **归因与边界**: "手机上的日期"必须写明来源 + "问起才引用"
  4. **措辞虚化**: 间隔注记绝不出现小时/分钟/精确日期（与 I-c 同一条纪律）
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.worldtime import (                                   # noqa: E402
    phone_date_note,
    real_gap_note,
    time_notes,
)
from core.worldtime.prompt_time import WEEKDAYS, phone_date    # noqa: E402


# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# 2. 手机日期（真实日期 + 真实闰年）
# ---------------------------------------------------------------------------

def test_phone_date_is_the_real_date():
    """★ 2026-09-17 用户裁决: 虚构年 `2100` 已删 —— 手机上的日期**就是真实日期**。

    旧断言是 `y == FICTIONAL_YEAR`（2100）+ `wd == WEEKDAYS[datetime(2100, …)]`。
    现在 `wd` 必须等于**同一年**的星期几, 而不再是另一个年份的。
    """
    y, m, d, wi, wd = phone_date(datetime(2026, 9, 13, 20, 41))
    assert (y, m, d) == (2026, 9, 13)
    assert wi == datetime(2026, 9, 13).weekday()
    assert wd == WEEKDAYS[datetime(2026, 9, 13).weekday()]
    print(f"    手机日期: {y}年{m}月{d}日（{wd}）—— 与真实历一致")


def test_phone_date_keeps_feb29_when_it_exists():
    """★ 删掉虚构年之后 `2/29` **不再被平移** —— 真实年份闰就是闰。

    旧行为: 2100 不是闰年 → 真实 `2/29` 一律平移到 `3/1`。
    新行为: 2028 是闰年 → 原样保留。**这是一次真实的行为变更, 不是等价改写。**
    """
    assert phone_date(datetime(2028, 2, 29, 12, 0))[:3] == (2028, 2, 29)
    # 非闰年的 2/29 根本不可能是 datetime, 所以无需再防"构造非法日期"
    print("    闰年边界: 2028-02-29 → 2028年2月29日（原样保留）")


def test_phone_note_has_attribution_and_boundary():
    """★ 归因（"手机上的"）+ 使用边界（"问起才引用"）—— 少任一条都会破墙。

    ⚠️ 虚构年删掉之后**这两半更承重了**: 原先还有"年份不重合"当第二道保险,
    现在只剩归因 —— 她说的就是 2026, 靠"这是手机上显示的"把它框在手机里。
    """
    note = phone_date_note(datetime(2026, 9, 13, 20, 41))
    assert "手机上的日期" in note, f"缺归因: {note}"
    assert "问起" in note and "不要主动" in note, f"缺使用边界: {note}"
    assert "2026年9月13日" in note
    print("    phone_note: 归因+边界齐全")


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
    """★ 组装（2026-09-17 时间轴换代后）—— **不再有剧情时间注记**。

    MMT = 现实间隔 + 手机日期（2 行）; VN = 只有现实间隔（1 行）。
    `【现在是】1年4月·春·白天` **已删** —— 它读的是作废的剧情游标,
    留着会让两个时间事实并排在同一个 prompt 里（`ESSAY §5.2` 的坑）。
    """
    now = datetime(2026, 9, 13, 20, 41)
    mmt = time_notes(last_ts="2026-09-01T10:00:00", now=now, include_phone=True)
    assert len(mmt) == 2, mmt
    assert any("手机上的日期" in n for n in mmt)
    # ★ 核心断言: 剧情时间注记不再出现（两个事实并排 = 那个坑）
    assert not any("【现在是】" in n for n in mmt), mmt
    vn = time_notes(last_ts="2026-09-01T10:00:00", now=now, include_phone=False)
    assert len(vn) == 1 and not any("手机" in n for n in vn)
    assert time_notes(last_ts=None) == []                # 空 → 空列表（不注空行）
    print(f"    notes: MMT {len(mmt)} 行 / VN {len(vn)} 行（**无剧情时间注记**）")
    for n in mmt:
        print(f"      {n[:60]}")


if __name__ == "__main__":
    for fn in (test_phone_date_is_the_real_date,
               test_phone_date_keeps_feb29_when_it_exists,
               test_phone_note_has_attribution_and_boundary,
               test_real_gap_is_vague,
               test_real_gap_empty_on_bad_input,
               test_notes_bundle_and_phone_switch):
        fn()
    print("all prompt_time tests passed")
