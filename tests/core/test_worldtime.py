# -*- coding: utf-8 -*-
"""core.worldtime 单测（T0）—— 时间模型 / 槽位算术 / 双出口 / 游标。

**最容易错的三处**（本文件重点钉的就是它们）:
  1. **凌晨归属**: 4/30 的「夜 → 凌晨」必须仍是 **4 月第 4 周**（用户点名的崩溃点）
  2. **`sim_day` 单位** = 一个时相格（不是"天"）—— 5 格 = 1 叙事日
  3. **两个时钟不互算**: story 的算术不读 realtime; realtime 不动 story 的游标
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.worldtime import (                        # noqa: E402
    PHASES,
    SPANS,
    WorldClock,
    advance,
    age_sim_days,
    freshness,
    parse_span,
    parse_story_time,
    render_relative,
)
from core.worldtime.age import DEFAULT_HALF_LIFE_DAYS   # noqa: E402
from core.worldtime.clock import world_clock_path       # noqa: E402
from core.worldtime.story import (                      # noqa: E402
    DAYS_TO_SIM,
    MAX_STEP,
    PHASES_PER_DAY,
    StoryTime,
)
from core.worldtime import realtime                     # noqa: E402


# ---------------------------------------------------------------------------
# 1. 时间点与日历派生
# ---------------------------------------------------------------------------

def test_phases_and_units():
    assert PHASES == ("晨", "昼", "夕", "夜", "凌晨")
    assert PHASES_PER_DAY == 5 == DAYS_TO_SIM
    st = StoryTime.from_sim_day(0)
    assert st.phase == "晨" and st.story_day == 0.0
    assert StoryTime.from_sim_day(5).story_day == 1.0
    print(f"    story: PHASES={PHASES} 5 格 = 1 叙事日")


def test_calendar_derives_from_sim_day():
    """日历是 sim_day 的**纯函数** —— 结构上不可能失同步。

    约定: 锚点当月第 1 周 = 起点; 7 叙事日进一周; 4 周进一月。
    （故"第 4 周"是 sim_day = 21 叙事日 = 105 格, 不是 4 天。）
    """
    a = {"year": 1, "month": 4}
    seq = [StoryTime.from_sim_day(n, anchor=a) for n in (0, 5, 35, 105)]
    for st in seq:
        print(f"      sim_day={st.sim_day:<4} {st}")
    assert seq[1].week == 1 and seq[1].phase == "晨"      # 第 1 日
    assert seq[2].week == 2, seq[2]                        # 第 7 日 → 第 2 周
    assert seq[3].week == 4 and seq[3].month == 4, seq[3]  # 第 21 日 → 第 4 周
    print(f"    story: 7 日/周 · 4 周/月 → 第 4 周 = {seq[3]}")


def test_month_rollover_at_four_weeks():
    a = {"year": 1, "month": 4}
    # 4 周 = 28 叙事日 = 140 格 → 翻到 5 月第 1 周
    st = StoryTime.from_sim_day(4 * 7 * DAYS_TO_SIM, anchor=a)
    assert (st.month, st.week) == (5, 1), st
    print(f"    story: 4 周/月 → sim_day={4 * 7 * DAYS_TO_SIM} 翻到 {st}")


def test_year_rollover():
    a = {"year": 1, "month": 4}
    # 从 4 月起满 12 个月 = 48 周 = 336 叙事日
    st = StoryTime.from_sim_day(48 * 7 * DAYS_TO_SIM, anchor=a)
    assert (st.year, st.month) == (2, 4), st
    print(f"    story: 跨年正确 → {st}")


def test_phase_cycles_within_a_day():
    a = {"year": 1, "month": 4}
    phases = [StoryTime.from_sim_day(n, anchor=a).phase for n in range(5)]
    assert phases == list(PHASES), phases
    assert StoryTime.from_sim_day(5, anchor=a).phase == "晨"
    print(f"    story: 日内时相循环 {phases} → 第 6 格回到 晨")


# ---------------------------------------------------------------------------
# 2. ★ 凌晨归属（用户点名的崩溃点）
# ---------------------------------------------------------------------------

def test_wee_hours_belong_to_previous_day():
    """★ 4 月第 4 周的「夜 → 凌晨」必须仍是 **4 月第 4 周**，不得提前翻到 5 月。

    （21 叙事日 = 105 格 起，是 4 月第 4 周的第 1 日。）
    """
    a = {"year": 1, "month": 4}
    w4d1 = 21 * DAYS_TO_SIM                     # 4 月第 4 周第 1 日（晨）
    d7 = w4d1 + 6 * DAYS_TO_SIM                 # 第 4 周第 7 日（晨）
    night = StoryTime.from_sim_day(d7 + 3, anchor=a)       # 夜
    wee = StoryTime.from_sim_day(d7 + 4, anchor=a)         # 凌晨
    assert night.phase == "夜" and wee.phase == "凌晨", (night, wee)
    assert night.month == 4 and night.week == 4, night
    assert wee.month == 4 and wee.week == 4, f"凌晨跑到下个月了: {wee}"
    # 再进「晨」才翻到 5 月
    nxt = StoryTime.from_sim_day(d7 + 5, anchor=a)
    assert nxt.phase == "晨" and nxt.month == 5 and nxt.week == 1, nxt
    print(f"    ★ 凌晨归属: {night} → {wee} → {nxt}")


# ---------------------------------------------------------------------------
# 3. advance 的单调性与夹取（I6）
# ---------------------------------------------------------------------------

def test_advance_is_monotone_for_every_span():
    st = StoryTime.from_sim_day(10)
    for sp in SPANS:
        nxt = advance(st, sp)
        assert nxt.sim_day >= st.sim_day, f"{sp} 让时间倒退了"
    print(f"    advance: {len(SPANS)} 个 span 全部单调不减（I6）")


def test_advance_span_semantics():
    st = StoryTime.from_sim_day(0)
    assert advance(st, "same").sim_day == 1                # 同一格
    assert advance(st, "halfday").sim_day == 1             # 时相级，不推到整天
    assert advance(st, "day").sim_day == DAYS_TO_SIM       # 1 叙事日
    assert advance(st, "days:3").sim_day == 3 * DAYS_TO_SIM
    assert advance(st, "week").sim_day == 7 * DAYS_TO_SIM
    assert advance(st, "month").sim_day == 4 * 7 * DAYS_TO_SIM
    print("    advance: same=1格 halfday=1格 day=5格 days:3=15格 week=35格 month=140格")


def test_advance_clamps_span_not_result():
    """★ 夹的是**增量**（≤ MAX_STEP），不是结果 —— 否则长世界线会被截断。"""
    far = StoryTime.from_sim_day(100000)
    nxt = advance(far, "days:99")
    assert nxt.sim_day - far.sim_day <= MAX_STEP, "增量没夹住"
    assert nxt.sim_day > far.sim_day
    print(f"    advance: 增量夹到 ≤{MAX_STEP} 格（结果不被截断）")


def test_advance_from_none_starts_at_anchor():
    st = advance(None, "day")
    assert st.sim_day == DAYS_TO_SIM and st.phase == "晨"
    print("    advance: st=None → 从锚点起算")


def test_advance_unknown_span_defaults():
    st = StoryTime.from_sim_day(0)
    for bad in ("", None, "十年后", "days:", "days:abc", 123):
        assert advance(st, bad).sim_day == 1, bad
    print("    advance: 未知/坏 span → 默认 +1 格（§4.3）")


# ---------------------------------------------------------------------------
# 4. span 契约
# ---------------------------------------------------------------------------

def test_parse_span_normalizes():
    assert parse_span(" DAYS:1 ") == "day"          # 归一化 + days:1 → day
    assert parse_span("weeks:1") == "week"
    assert parse_span("days:3") == "days:3"
    assert parse_span("weeks:4") == "weeks:4"
    print("    span: 归一化正确（大小写/空白/days:1→day）")


def test_parse_span_clamps_over_range():
    """★ 越界**夹取不丢弃** —— 叙事事实"跨了很久"比"精确多久"重要。"""
    assert parse_span("days:30") == "days:7", parse_span("days:30")
    assert parse_span("weeks:99") == "weeks:4"
    print("    span: days:30 → days:7（夹到上限, 不丢弃）")


def test_parse_span_never_raises_by_default():
    for bad in ("", None, 123, "乱写", "days:", "years:2"):
        got = parse_span(bad)
        assert got in SPANS, f"{bad!r} → {got!r} 不在合法集"
    print(f"    span: 任何输入都归一为合法枚举（共 {len(SPANS)} 种）")


# ---------------------------------------------------------------------------
# 5. 双出口
# ---------------------------------------------------------------------------

def test_age_needs_both_sides():
    """★ 任一侧缺值 → None（**不得折成 0** —— 否则旧记忆冒充刚发生）。"""
    st = StoryTime.from_sim_day(10)
    assert age_sim_days(None, st) is None
    assert age_sim_days(st, None) is None
    assert age_sim_days(None, None) is None
    assert age_sim_days(st, StoryTime.from_sim_day(13)) == 3
    # 未来节点（不该发生，但不得出负数）
    assert age_sim_days(StoryTime.from_sim_day(99), st) == 0
    print("    age: 缺值→None; 未来节点夹到 0")


def test_freshness_bounds_and_monotone():
    assert freshness(None) is None
    assert freshness(0) == 1.0
    hl = DEFAULT_HALF_LIFE_DAYS
    half = freshness(int(hl * DAYS_TO_SIM))
    assert abs(half - 0.5) < 1e-9, half                 # 半衰期处正好 0.5
    vals = [freshness(n * DAYS_TO_SIM) for n in range(0, 40, 5)]
    assert all(b < a for a, b in zip(vals, vals[1:])), vals
    assert all(0.0 < v <= 1.0 for v in vals)
    print(f"    freshness: age=0→1.0; 半衰期({hl}日)处→{half:.3f}; 单调递减且有界")


def test_render_relative_never_exposes_precise_values():
    """★ 硬约束: 短语里**不得出现精确日/周/月数以外的形态**, 更不得出现日期。"""
    samples = [0, 1, 3, 5, 9, 20, 40, 100, 200, 1000, 5000]
    out = []
    for a in samples:
        ph = render_relative(a)
        out.append((a, ph))
        assert ph, a
        # 不得出现完整日期或"小时/分"这种精确刻度
        for bad in ("年-", "-月-", "小时", "分钟", "天前 0", "."):
            assert bad not in ph, f"age={a} 的短语含精确形态: {ph!r}"
    for a, ph in out:
        print(f"      age={a:<5}格({a / DAYS_TO_SIM:>6.1f}日) → {ph!r}")


def test_render_relative_none_is_vague():
    assert render_relative(None) == "很久以前"
    print("    render_relative: 旧档(None) → '很久以前'（不暴露'未知'）")


# ---------------------------------------------------------------------------
# 6. 游标（clock）
# ---------------------------------------------------------------------------

def test_clock_roundtrip_and_monotone(tmp_path):
    p = world_clock_path(tmp_path, "w1")
    clk = WorldClock.load(p, anchor={"year": 1, "month": 4})
    assert clk.cursor.sim_day == 0
    clk.cursor = clk.advance("days:2")
    assert clk.save()
    back = WorldClock.load(p)
    assert back.cursor.sim_day == clk.cursor.sim_day
    assert back.cursor.phase == clk.cursor.phase
    assert back.anchor == clk.anchor
    print(f"    clock: 往返保真 {back.cursor}")


def test_clock_missing_file_starts_at_anchor(tmp_path):
    clk = WorldClock.load(tmp_path / "nope" / "world_clock.json")
    assert clk.cursor.sim_day == 0
    print("    clock: 文件缺失 → 从锚点起算（不抛）")


def test_clock_corrupt_file_does_not_raise(tmp_path):
    p = tmp_path / "world_clock.json"
    p.write_text("{ 坏 json", encoding="utf-8")
    clk = WorldClock.load(p)
    assert clk.cursor.sim_day == 0
    p.write_text('{"cursor": {"sim_day": -5}}', encoding="utf-8")
    assert WorldClock.load(p).cursor.sim_day == 0
    print("    clock: 损坏/非法 cursor → 回锚点 + WARNING（不抛）")


def test_clock_advance_is_monotone_assertion(tmp_path):
    clk = WorldClock.load(tmp_path / "wc.json")
    for sp in SPANS:
        before = clk.cursor.sim_day
        clk.cursor = clk.advance(sp)
        assert clk.cursor.sim_day > before, sp
    print(f"    clock: {len(SPANS)} 个 span 全部严格递增")


def test_clock_write_is_atomic(tmp_path):
    clk = WorldClock.load(tmp_path / "wc.json")
    clk.cursor = clk.advance("day")
    clk.save()
    leftovers = list(tmp_path.glob("*.tmp"))
    assert not leftovers, f"残留临时文件: {leftovers}"
    print("    clock: 原子写（无 .tmp 残留）")


# ---------------------------------------------------------------------------
# 7. ★ 两个时钟不互算（独立性）
# ---------------------------------------------------------------------------

def test_realtime_is_declared_not_implemented():
    assert realtime.IMPLEMENTED is False
    assert realtime.__all__ == []
    print("    realtime: 显式声明未实现（边界已写在 docstring）")


def test_worldtime_does_not_import_project_modules():
    """★ 独立性的**可验证定义**: 包内模块不 import 项目内其他模块。"""
    import ast
    pkg = Path(__file__).resolve().parents[2] / "core" / "worldtime"
    offenders: list[str] = []
    for py in sorted(pkg.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                if m.startswith("core.") and not m.startswith("core.worldtime"):
                    offenders.append(f"{py.name}: {m}")
    assert not offenders, f"worldtime 依赖了项目内模块: {offenders}"
    print("    ★ worldtime: 只依赖 stdlib（独立性的可验证定义成立）")


if __name__ == "__main__":
    import tempfile

    for fn in (test_phases_and_units, test_calendar_derives_from_sim_day,
               test_month_rollover_at_four_weeks, test_year_rollover,
               test_phase_cycles_within_a_day,
               test_wee_hours_belong_to_previous_day,
               test_advance_is_monotone_for_every_span,
               test_advance_span_semantics,
               test_advance_clamps_span_not_result,
               test_advance_from_none_starts_at_anchor,
               test_advance_unknown_span_defaults,
               test_parse_span_normalizes, test_parse_span_clamps_over_range,
               test_parse_span_never_raises_by_default,
               test_age_needs_both_sides, test_freshness_bounds_and_monotone,
               test_render_relative_never_exposes_precise_values,
               test_render_relative_none_is_vague,
               test_realtime_is_declared_not_implemented,
               test_worldtime_does_not_import_project_modules):
        fn()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        for fn in (test_clock_roundtrip_and_monotone,
                   test_clock_missing_file_starts_at_anchor,
                   test_clock_corrupt_file_does_not_raise,
                   test_clock_advance_is_monotone_assertion,
                   test_clock_write_is_atomic):
            fn(p)
    print("all worldtime tests passed")
