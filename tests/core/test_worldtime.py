"""core.worldtime 单测（T0）—— 时间模型 / 槽位算术 / 双出口 / 游标。

**最容易错的三处**（本文件重点钉的就是它们）:
  1. **凌晨归属**: 4/30 的「夜 → 凌晨」必须仍是 **4 月第 4 周**（用户点名的崩溃点）
  2. **`sim_day` 单位** = 一个时相格（不是"天"）—— 5 格 = 1 叙事日
  3. **两个时钟不互算**: story 的算术不读 realtime; realtime 不动 story 的游标
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.worldtime import (                        # noqa: E402
    SPANS,
    age_days,
    date_of,
    freshness,
    parse_span,
    render_date,
    render_relative,
)
from core.worldtime.age import DEFAULT_HALF_LIFE_DAYS   # noqa: E402
from core.worldtime import realtime                     # noqa: E402


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------











# ---------------------------------------------------------------------------
# 2. ★ 凌晨归属（用户点名的崩溃点）
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------











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

def test_age_days_is_real_calendar_days():
    """★ `age` = 今天 − date(node.ts)，**整数日历日**；缺/坏 → None（不折成 0）。

    2026-09-17（`ESSAY_TIME_MODEL §10`）: 年龄的唯一来源是**现实日期**。
    """
    now = datetime(2026, 9, 17, 14, 0)
    assert age_days("", now=now) is None
    assert age_days(None, now=now) is None
    assert age_days("坏值", now=now) is None
    assert age_days("2026-09-17T01:00:00", now=now) == 0
    assert age_days("2026-09-10T00:00:00", now=now) == 7
    assert age_days("2026-09-10T00:00:00", now="坏值") is None
    # 未来日（时钟回拨 / 时区误配）→ 夹到 0，不出负数
    assert age_days("2026-10-01T00:00:00", now=now) == 0
    print("    age_days: 缺/坏→None; 未来→夹到 0")


def test_age_days_is_calendar_not_hours():
    """★ 必须是**日历日**：跨午夜 2 小时算"昨天"，不是"今天"。

    玩家说的是"昨天/今天"，那是日历日。用小时差会给出与玩家相反的答案。
    """
    now = datetime(2026, 9, 17, 1, 0)
    assert age_days("2026-09-16T23:00:00", now=now) == 1        # 相差 2 小时，但是昨天
    assert render_relative(age_days("2026-09-16T23:00:00", now=now)) == "昨天"
    print("    跨午夜 2 小时 → age=1 → '昨天'（不是'今天'）")


def test_date_of_is_timezone_pinned():
    """★ 时区定死（约束 1）—— 朴素/带偏移的 `ts` 一律按 `REAL_TZ` 切日。"""
    assert date_of("2026-09-17T00:30:00+00:00") == date(2026, 9, 17)   # = UTC+8 08:30
    assert date_of("2026-09-17T20:00:00+00:00") == date(2026, 9, 18)   # = UTC+8 次日 04:00
    assert date_of("2026-09-17T00:30:00") == date(2026, 9, 17)         # 朴素 = REAL_TZ
    assert date_of("") is None and date_of(None) is None
    print("    date_of: 按 REAL_TZ 切日；朴素 ts 视为 REAL_TZ")


def test_freshness_bounds_and_monotone():
    """★ 2026-09-17 加了下界 `floor` —— 这条断言随之改写（**行为变更, 不是放宽**）。

    旧口径: `freshness(hl) == 0.5` **正好**（半衰期的字面定义）。
    新口径: `freshness(hl) == (1 + floor) / 2`; 只有 `floor=0` 时才回到 0.5。
    `age=0` 仍是 **1.0**（与 floor 无关）—— 这条没变, 是关键。
    """
    from core.worldtime.age import DEFAULT_FRESHNESS_FLOOR as FL

    assert freshness(None) is None
    assert freshness(0) == 1.0                       # 新记忆不受 floor 影响
    assert freshness(0, floor=0.9) == 1.0            # 极端 floor 也一样
    hl = DEFAULT_HALF_LIFE_DAYS
    half = freshness(int(hl))
    assert abs(half - (1 + FL) / 2) < 1e-9, half     # 半衰期处 = (1+floor)/2
    assert abs(freshness(int(hl), floor=0.0) - 0.5) < 1e-9, "floor=0 应回到旧行为"

    vals = [freshness(n) for n in range(0, 40, 5)]
    assert all(b < a for a, b in zip(vals, vals[1:])), vals
    assert all(FL <= v <= 1.0 for v in vals)         # 下界是 floor, 不是 0

    # ★ 下界真的兜住了尾巴（旧版这里是 1e-22 量级）
    assert freshness(365) >= FL
    assert freshness(3650) == FL or freshness(3650) > 0.9 * FL
    print(f"    freshness: age=0→1.0; 半衰期处→{half:.3f}; "
          f"下界 {FL}（floor=0 时回到 0.5 / 0.0）")


def test_render_relative_buckets():
    """桶边界（**"刚才"档已删** —— 整数日历日到不了它，留着会把 age=0 误判成"刚才"）。"""
    assert render_relative(0) == "今天"
    assert render_relative(1) == "昨天"
    assert render_relative(2) == "2 天前"
    assert render_relative(10) == "1 周前"
    assert render_relative(40) == "1 个月前"
    assert render_relative(400) == "1 年前"
    print("    render_relative 桶: 0→今天 1→昨天 2→2天前 10→1周前 40→1个月前 400→1年前")


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
        print(f"      age={a:<5}(现实日) → {ph!r}")


def test_render_relative_none_is_vague():
    assert render_relative(None) == "很久以前"
    print("    render_relative: 缺 ts(None) → '很久以前'（不暴露'未知'）")


# ---------------------------------------------------------------------------
# 5b. ⭐ N5: 绝对日期（引擎坐标）—— 与相对短语**两个都要**
# ---------------------------------------------------------------------------

def test_render_date_same_year_and_cross_year():
    """今年印 `9/27`（不印年份 = 省字）；**跨年才印全** `2025/9/26`。

    为什么要它（`PROCEED §2 #16` 已裁）: 相对短语是**她的口吻**（"3 周前"）,
    而它是**引擎的坐标** —— 相对短语每天都在变, 光靠它没法把一条记忆
    钉到"具体哪一天"（对齐、检索、写时间条件都要坐标）。
    """
    now = datetime(2026, 10, 1, 12, 0)
    assert render_date("2026-09-27T10:00:00", now=now) == "9/27"
    assert render_date("2026-01-05T10:00:00", now=now) == "1/5"      # 不补前导零
    assert render_date("2025-09-26T10:00:00", now=now) == "2025/9/26"
    assert render_date(datetime(2026, 1, 5), now="2026-10-01T00:00:00+08:00") == "1/5"
    print("    render_date: 今年 9/27 · 跨年 2025/9/26")


def test_render_date_never_invents():
    """**取不到就不印**（同 `render_relative` 的哨兵纪律）: 缺 `now` / 坏 ts → `""`。

    ⚠️ 缺 `now` 就不能猜年份 —— 这与 `age_days(*, now)` 不留默认值是同一条纪律。
    """
    now = datetime(2026, 10, 1, 12, 0)
    assert render_date("", now=now) == ""
    assert render_date("坏值", now=now) == ""
    assert render_date(None, now=now) == ""
    assert render_date("2026-09-27T10:00:00", now=None) == ""        # 不猜年份
    assert render_date({"nope": 1}, now=now) == ""
    print("    render_date: 缺 now / 坏 ts → 空串（不编日期、不猜年份）")


# ---------------------------------------------------------------------------
# 6. 游标（clock）
# ---------------------------------------------------------------------------











# ---------------------------------------------------------------------------
# 7. ★ 两个时钟不互算（独立性）
# ---------------------------------------------------------------------------

def test_realtime_declares_its_boundaries():
    """`realtime` 的边界仍然显式声明（2026-09-17: 已实现, 但边界没变）。

    旧断言是 `IMPLEMENTED is False` + `__all__ == []` —— 那是"只声明不实现"阶段的
    哨兵。现在它实现了, 但**"只做由头不做时钟"**这条要保住:
    它不该导出任何时钟/游标概念（`snap_to` / 游标推进已随换代取消）。
    """
    assert "due_notes" in realtime.__all__
    banned = {"snap_to", "advance", "cursor", "sim_day", "WorldClock"}
    assert not banned & set(realtime.__all__)
    print("    realtime: 已实现（表 + 台账）, 但无任何时钟出口")


#: worldtime 允许的**薄横切**依赖（只有这两个; 业务层一律不许）。
#: `core.paths` = 固定路径宏（`clock_path` 用）; `core.common` = 横切小件
#: （`atomic.replace_with_retry`, 纯 stdlib 的原子替换包装）。二者都不引入业务概念,
#: 不破坏"时间逻辑可独立测试"这条独立性。
WORLDTIME_ALLOWED_CORE = ("core.paths", "core.common")


def test_worldtime_does_not_import_project_modules():
    """★ 独立性的**可验证定义**: 包内模块只依赖 stdlib + 上面那两个薄横切件。

    2026-09-21 收紧: 旧写法只比对 `node.module`, 于是 `from core import paths`
    （module == "core", 不以 "core." 开头）**漏检**——`realtime.py` 一直这么写着却算"只依赖 stdlib"。
    现在把 `from core import X` 展开成 `core.X` 再判, 并把允许集**显式化**:
    漏检补上 + 业务依赖（`core.bond` / `core.session` …）仍然一律报红。
    """
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
                if node.module == "core":                     # from core import X → core.X
                    mods = [f"core.{a.name}" for a in node.names]
                else:
                    mods = [node.module]
            for m in mods:
                if not m.startswith("core") or m.startswith("core.worldtime"):
                    continue
                if any(m == a or m.startswith(a + ".") for a in WORLDTIME_ALLOWED_CORE):
                    continue
                offenders.append(f"{py.name}: {m}")
    assert not offenders, f"worldtime 依赖了项目内模块: {offenders}"
    print("    ★ worldtime: 只依赖 stdlib + core.paths/core.common（独立性的可验证定义成立）")


if __name__ == "__main__":

    for fn in (test_phases_and_units, test_calendar_derives_from_sim_day,
               test_month_rollover_at_four_weeks, test_year_rollover,
               test_parse_span_normalizes, test_parse_span_clamps_over_range,
               test_parse_span_never_raises_by_default,
               test_age_days_is_real_calendar_days,
               test_age_days_is_calendar_not_hours,
               test_date_of_is_timezone_pinned,
               test_freshness_bounds_and_monotone,
               test_render_relative_buckets,
               test_render_relative_never_exposes_precise_values,
               test_render_relative_none_is_vague,
               test_realtime_declares_its_boundaries,
               test_worldtime_does_not_import_project_modules):
        fn()
    print("all worldtime tests passed")
