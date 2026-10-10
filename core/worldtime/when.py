# -*- coding: utf-8 -*-
"""when.py — **她写的时间 → 检索窗口**（`DESIGN_MMT_NEW_ACTION §2` 的落地; 2026-10-08）。

## 为什么是**两个**前缀（用户 2026-10-08 裁）

因为语言本身就分两族, 一个 `back` 扛不了:

| 人话 | 规范 | 窗口 |
|---|---|---|
| **「上 X」**（上周 · 上个月 · 去年 · 上上周） | `last N unit` · `last A..B unit` | **自然周期段**（7 / 30 / 365 天） |
| **「N 个 X 前」**（一周前 · 一年前的今天 · 6 周前） | `back N unit` · `back A..B unit` | **同一天的点 / 滚动区间**（1 天 / 连续天） |

⭐ 一个前缀同时当两族的下场是**必有一族别扭**（"`back 1 year` 到底是一整年,
还是一年前的今天"）—— 两族各有各的写法之后, **一个乘法都不用做**
（`back 365 day` 那种逼她算数的写法不存在了）。

## 语法

```
last N unit              倒数第 N 个自然周期（0 = 本周期, **截到今天**）
last A..B unit           倒数第 A~B 个周期（`..` 不含 B 那一端）
last A..=B unit          同上（`..=` 含 B）
back N unit              N 个单位前的今天（**点**）
back A..B unit           从 A 个单位前 到 B 个单位前（滚动）
back ..=B unit           起点省 = 0（`..B` 同义）
back A..                 ⛔ 拒（无下界 = 吞整库）

unit := day | week | month | year | <festivals.json 里的节日名>
        （中文同义: 天/日 · 周/星期 · 个月/月 · 年 —— 用户自己就写过 `back 6..7周`）
绝对:   2026/09/25 · 09/25(无年) · 2026/09 · 2026 · 2026/09/25..=2026/09/28
```

⚠️ **`last` 与 `back` 在"周期长度 = 1 天"的那些单位上故意重合**（`day` 与节日名）:
"第 N 个自然日"就是"N 天前那一天","倒数第 N 个圣诞"就是"圣诞那天" ⇒ 两族在那里
走同一条路, 免得出现"`last 1 day` 与 `back 1 day` 不一样"这种没人能解释的差异。

## 五条口径（2026-10-08 与用户逐条定的）

1. **`A..B` 是半开**（Rust 语义）⇒ `back 0..7 day` ≡ `back 0..=6 day`（都 = 最近 7 天）。
2. ⛔ **`A..` 拒**（无下界会把整库吞进来）。
3. **自然周从周一起**; `last 0` 是**唯一被 `now` 截断**的周期（本周 = 周一到今天）。
4. **无年份的日期 = 最近一次已过的那一天** —— 她抄记忆头里的 `9/26` 正是这个形态;
   而**显式年份**落在将来 ⇒ 规则⑥: **合法但空**（`future=True`, 不是"她写错了"）。
5. **只有单日窗口才放宽**（`WIDEN_DAYS` 两侧各 ±2 天, **末端夹到今天**）——
   周期 / 区间本来就有宽度, 再放宽没有信息量。

## 三条边界

* ⛔ **不读壁钟**: `now` 必填（同 `age.age_days` 的纪律）—— 不给"现在"就不知道该算到哪天。
* ⛔ **不从整句话里抽时间**: `when` 只放时间。认不出 ⇒ 返回 `None`, 由调用方回她
  "认不出这个时间, 你给个日期"（`§2.5`）—— **绝不做从句抽取**（那是猜）。
* ⛔ **纯函数零台账**: "她写的串 → 算出的窗口"那一行由调用方（`look`）记, 本模块
  **不打 info 日志、不写盘**（唯一的读盘是 `load_occasions`, 同包先例）。
  但**内部出 bug 时打一条 warning** —— 那是我该知道的, 不是该吞的。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date

from core.worldtime.age import date_of
from core.worldtime.cal import shift_days, shift_months, shift_years, week_start
from core.worldtime.realtime import Occasion, load_occasions

logger = logging.getLogger(__name__)

#: ⭐ **放宽的幅度（天）** —— 只对**单日窗口**放宽（见 `When.wide`）。
#: ⚠️ 这是**判断, 不是标定**（同 `age.DEFAULT_FRESHNESS_FLOOR` 那条纪律）:
#: "那天前后两天"是人对"我记不准是哪天"的自然口径。有真机数据后再标定。
WIDEN_DAYS = 2

#: `N` 的上界（`DESIGN_MMT_NEW_ACTION §2.4` 规则③ —— 上界防荒唐）。
#: ⚠️ 正则**故意放宽到 3 位**, 好让上界由**这一条**说了算 —— 把"≤99"藏在
#: `\d{1,2}` 里, 谁哪天把正则改宽一格规则就静默消失了（第一版就是那样写的:
#: 变异验红时才发现下面那条检查**根本不可达**, 也就是说规则从没生效过）。
_N_MAX = 99

#: 单位名 —— **中英文都收**（规范写英文单数; 容错吃中文, 见用户自己写的 `6..7周`）。
_UNITS: dict[str, str] = {
    "day": "day", "days": "day", "天": "day", "日": "day",
    "week": "week", "weeks": "week", "周": "week", "星期": "week", "个星期": "week",
    "month": "month", "months": "month", "月": "month", "个月": "month",
    "year": "year", "years": "year", "年": "year",
}

_RANGE = re.compile(r"^(?P<a>\d{0,3})(?P<dots>\.\.=?)(?P<b>\d{1,3})$")
_BARE = re.compile(r"^\d{1,3}$")
_PREFIX = re.compile(r"^(last|back)\s*(?P<rest>.+)$", re.IGNORECASE)
#: 前缀之后 = `<数字与点> <单位名>`（单位名是**尾部的字母/汉字串**, 空格可有可无）
_UNIT_TAIL = re.compile(r"^(?P<rng>[0-9.=\s]*?)\s*(?P<unit>[A-Za-z_]+|[^\W\d_]+)$")

_ABS_MONTH = re.compile(r"^(?P<y>\d{4})[-/](?P<m>\d{1,2})$")
_ABS_YEAR = re.compile(r"^(?P<y>\d{4})$")
_ABS_DAY = re.compile(r"^(?:(?P<y>\d{4})[-/])?(?P<m>\d{1,2})[-/](?P<d>\d{1,2})$")

#: 固定人话（**同义改写, 绝不近似** —— `§2.6` 纪律）。
#: ⚠️ "最近 N 天/周/月/年" 与 "N 个单位前" 是**参数化**的, 见下面两条正则。
_PHRASES: dict[str, str] = {
    "今天": "back 0 day", "昨天": "back 1 day", "前天": "back 2 day", "大前天": "back 3 day",
    "本周": "last 0 week", "这周": "last 0 week",
    "上周": "last 1 week", "上上周": "last 2 week", "上上上周": "last 3 week",
    "上星期": "last 1 week", "上个星期": "last 1 week",
    "本月": "last 0 month", "这个月": "last 0 month",
    "上个月": "last 1 month", "上上月": "last 2 month",
    "今年": "last 0 year", "去年": "last 1 year", "前年": "last 2 year",
    "上周的今天": "back 1 week", "上个月的今天": "back 1 month", "去年的今天": "back 1 year",
}

_AGO = re.compile(r"^(?P<n>\d{1,2}|[一两二三四五六七八九十])\s*(?:个)?\s*"
                  r"(?P<u>天|日|周|星期|个月|年)\s*前(?:的今天)?$")
_RECENT = re.compile(r"^最近\s*(?P<n>\d{1,2}|[一两二三四五六七八九十])\s*"
                     r"(?P<u>天|日|周|星期|个?月|年)$")

#: 中文数量词（**只到十**, 且只收单字 —— 「十一」「二十三」一律不认, 她会改用数字）。
#: ⚠️ 「两」是「两天前」的自然说法, 「二」也收（她会写"二天前"吗? 少见但无害）。
_CN_NUM: dict[str, int] = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
                           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _num(raw: str) -> int | None:
    """正则抓到的那一格 → 数字（阿拉伯数字原样, 中文单字查表, 其余不认）。"""
    return int(raw) if raw.isdigit() else _CN_NUM.get(raw)

#: 「今年圣诞 / 去年圣诞 / 前年圣诞 / 上个圣诞」—— **相对年词 + 节日名**（`§2.6` 点名的形态）。
_REL_YEAR: dict[str, int] = {"这个": 0, "今年": 0, "上个": 1, "去年": 1, "上上": 2, "前年": 2}

#: 「最近 N <单位>」→ 规范形式（⛔ 月/年走日历, 天/周走天数 —— 各自精确, 不近似）。
_RECENT_UNIT: dict[str, str] = {
    "天": "day", "日": "day", "周": "week", "星期": "week",
    "月": "month", "个月": "month", "年": "year",
}


@dataclass(frozen=True)
class When:
    """她写的时间 → **窗口**（+ 一个"落在将来"的合法空）。

    | 字段 | 是什么 |
    |---|---|
    | `exact` | 精确窗口 `(start, end)` —— **闭区间**, 粒度 day（两端都含） |
    | `wide` | 放宽后的窗口（⛔ `None` = 这一档不放宽）—— **只在 `exact` 查空时才用** |
    | `source` | **她写的原串**（`look` 的结果头回显它: 回显比二次渲染更忠实也更省） |
    | `future` | ⭐ 整段落在将来（**规则⑥: 合法但空**, 不是"她写错了"） |

    ⚠️ **`future` 与"认不出"必须分开**: 认不出 ⇒ `parse_when` 返 `None`（回她
    "认不出这个时间, 你给个日期"）; 落在将来 ⇒ `When(future=True)`。混成一个 `None`
    就是把"她问将来"回答成"你写错了"。
    """

    exact: tuple[date, date]
    wide: tuple[date, date] | None = None
    source: str = ""
    future: bool = False


# ---------------------------------------------------------------------------
# 单位与周期（`back` 一族 = 点 / `last` 一族 = 自然周期段）
# ---------------------------------------------------------------------------

def _ago(today: date, n: int, unit: str) -> date:
    """「`n` 个单位前的今天」—— `back` 那一族的原子操作。"""
    if unit == "day":
        return shift_days(today, -n)
    if unit == "week":
        return shift_days(today, -7 * n)
    if unit == "month":
        return shift_months(today, -n)
    return shift_years(today, -n)


def _period(today: date, n: int, unit: str) -> tuple[date, date]:
    """倒数第 `n` 个**自然周期** `[首日, 末日]`（`last` 那一族）。

    ⚠️ **只有 `n == 0` 的末日截到今天**（"本周"= 周一到今天）—— 这是本模块唯一的
    截断, 写错就是"上周"与"本周"差一天, 而且只有跨周那天在真机上看得出来。
    """
    if unit == "week":
        first = shift_days(week_start(today), -7 * n)
        last = shift_days(first, 6)
    elif unit == "month":
        first = shift_months(date(today.year, today.month, 1), -n)
        last = shift_days(shift_months(first, 1), -1)          # 下月一号前一天
    else:                                                      # year
        first = shift_years(date(today.year, 1, 1), -n)
        last = shift_days(shift_years(first, 1), -1)
    return first, (today if n == 0 else last)


def _occurrence(occ: Occasion, today: date, n: int) -> date | None:
    """**倒数第 `n` 个**「那个日子」是哪天（`n = 0` = **今年这一期**, 可能还没到）。

    ⚠️ **不替她回退**（要去年请写 `last 1`）—— 这正是"9 月问 `last 0 christmas`
    ⇒ 落在将来 ⇒ 规则⑥返空"的来源, 也是 `Occasion.target()` 的原语义
    （那个函数刻意答"这一期是哪天", 见它 docstring 里"第一版写错的地方"）。
    「最近一次**已过**」是**另一条路**: 裸节日名走 `_occurrence_past`。
    """
    if occ.year_fixed:                       # 一辈子一次的行 ⇒ 只有"那一次"
        return occ.on(occ.year) if n == 0 else None
    return occ.on(today.year - n)


def _occurrence_past(occ: Occasion, today: date) -> date | None:
    """**最近一次已过**的那个日子（裸节日名走这条 —— 与 `last 0` **刻意不同**）。

    ⭐ 两条路必须分开: 9 月问「圣诞节」= 去年 12/25（人话就是这个意思）,
    而 `last 0 christmas` = 今年 12/25 ⇒ **落在将来 ⇒ 返空**（规则⑥）。
    共用一条路 ⇒ 要么裸名返空、要么 `last 0` 悄悄变去年, **两个都是静默错范围**。
    """
    if occ.year_fixed:
        return occ.on(occ.year)
    y = today.year
    if occ.on(y) > today:                    # 今年的还没到 ⇒ 最近一次是去年
        y -= 1
    return occ.on(y)


def _window_by_unit(today: date, rng: tuple[int, int, bool],
                    unit: str) -> tuple[date, date] | None:
    """`back` 一族（**偏移空间**）, 以及 `last` 里周期长度 = 1 天的那些单位。

    ⚠️ **半开在这里是"挪一天"不是"挪一个周期"**（偏移空间与周期序号空间不同 ——
    `_parse_spec` 里 `last` 那一支用的是 `b - 1`, 这里必须用 `+1 天`）:
    `back 6..7 week` = 49 周天前**那一天不含** ⇒ `[48 天前, 42 天前]`（7 天）。
    写成一个 `hi = b - 1` 会让所有 `unit != day` 的区间**塌成一天**（静默）。
    """
    a, b, closed = rng
    start = _ago(today, b, unit)
    if not closed:
        start = shift_days(start, 1)               # `..` 不含 B 那一端
    end = _ago(today, a, unit)
    return (start, end) if start <= end else None  # 端点反了 ⇒ 拒（不交换）


# ---------------------------------------------------------------------------
# 三条解析路径（绝对 / 前缀 / 人话）
# ---------------------------------------------------------------------------

def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _abs_point(y: int | None, m: int, d: int, today: date) -> date | None:
    """一个绝对日期。**无年份 ⇒ 最近一次已过的那天**（她抄记忆头就是 `9/26` 这个形态）。

    ⚠️ 往回找 8 年是为了 `2/29`: 今年不是闰年时, "最近一次 2/29"在几年前。
    """
    if y is not None:
        return _safe_date(y, m, d)
    for back in range(0, 8):
        got = _safe_date(today.year - back, m, d)
        if got is not None and got <= today:
            return got
    return None


def _parse_abs(text: str, today: date, occs) -> tuple[date, date] | None:
    """绝对形式: 单点 / 区间 / 整月 / 整年。

    ⚠️ **区间两端必须各是一个完整日期**（`9/20..=9/28` 或 `2026/9/20..=2026/9/28`）;
    两端都不带年份时**各按"最近一次已过"独立解** ⇒ 跨年的 `12/28..=1/3` 会解成
    "去年 12/28 到今年 1/3"（正是那种说法的意思）。若这样解出来 `start > end`
    ⇒ **拒**（不自动跨年 —— 那才是猜）。
    """
    left, op, right = _split_range(text)
    if op:
        lm, rm = _ABS_DAY.match(left), _ABS_DAY.match(right)
        if not (lm and rm):
            return None
        start = _abs_point(_int_or_none(lm.group("y")), int(lm.group("m")),
                           int(lm.group("d")), today)
        end = _abs_point(_int_or_none(rm.group("y")), int(rm.group("m")),
                         int(rm.group("d")), today)
        if start is None or end is None:
            return None
        if op == "..":                       # 半开 ⇒ 末端不含
            end = shift_days(end, -1)
        return (start, end) if start <= end else None
    m = _ABS_DAY.match(text)
    if m:
        got = _abs_point(_int_or_none(m.group("y")), int(m.group("m")),
                         int(m.group("d")), today)
        return (got, got) if got else None
    m = _ABS_MONTH.match(text)
    if m:
        first = _safe_date(int(m.group("y")), int(m.group("m")), 1)
        return (first, shift_days(shift_months(first, 1), -1)) if first else None
    m = _ABS_YEAR.match(text)
    if m:
        first = _safe_date(int(m.group("y")), 1, 1)
        return (first, shift_days(shift_years(first, 1), -1)) if first else None
    return None


def _split_range(text: str) -> tuple[str, str, str]:
    """`A..B` / `A..=B` ⇒ `(A, 运算符, B)`; 不是区间 ⇒ `(全文, "", "")`。"""
    parts = re.split(r"(\.\.=?)", text, maxsplit=1)
    return (parts[0], parts[1], parts[2]) if len(parts) == 3 else (text, "", "")


def _int_or_none(v: str | None) -> int | None:
    return int(v) if v else None


def _parse_range(raw: str) -> tuple[int, int, bool] | None:
    """`N` / `A..B` / `A..=B` / `..=B` ⇒ `(A, B, closed)`; ⛔ `A..`（无下界）拒。"""
    s = raw.replace(" ", "")
    if _BARE.match(s):
        n = int(s)
        return (n, n, True) if n <= _N_MAX else None
    m = _RANGE.match(s)                      # `A..` 匹配不上（B 必填）⇒ 自然拒
    if not m:
        return None
    a = int(m.group("a") or 0)               # 起点省 = 0
    b = int(m.group("b"))
    if a > _N_MAX or b > _N_MAX:
        return None
    return a, b, m.group("dots") == "..="


def _find_occasion(occs: list[Occasion], raw: str) -> Occasion | None:
    """节日名（**id 或中文 `name`**）→ 表里那一行。

    ⚠️ 也认 `name` 的**前缀简称**（**≥2 字**: 「圣诞」→「圣诞节」）—— 作者手编的表里
    只写全名（"手机日历上那个标记的字面"）, 而日常说法常是简称（`§2.6` 的
    「上个圣诞」就是这个形态）。⛔ **歧义就拒**（两个节日共享前缀 ⇒ 不猜）;
    ⛔ 表外具名日一样认不出（`§2.5`: 一次补一行, 不在这里发明）。
    """
    want = raw.casefold()
    exact = [o for o in occs if o.sig_key.casefold() == want or o.name == raw]
    if len(exact) == 1:
        return exact[0]
    if exact:                                # 同一个名字对上两行 ⇒ 表有问题, 不猜
        return None
    # ⚠️ 判据是 **`not raw.isascii()`**（不是 `isalnum()` —— 汉字也是 alnum!）:
    # 中文简称走前缀, latin 一律要写全 id（`christ` 不该命中 `christmas`）。
    if len(raw) >= 2 and not raw.isascii():
        near = [o for o in occs if o.name.startswith(raw)]
        if len(near) == 1:
            return near[0]
    return None


def _parse_spec(text: str, today: date, occs: list[Occasion]) -> tuple[date, date] | None:
    """规范语法: `last` / `back` + 区间 + 单位（中英文单位都收）。"""
    mp = _PREFIX.match(text)
    if not mp:
        return None
    kind = mp.group(1).lower()
    mt = _UNIT_TAIL.match(mp.group("rest").strip())
    if not mt:
        return None
    rng = _parse_range(mt.group("rng"))
    if rng is None:
        return None
    a, b, closed = rng
    unit = _UNITS.get(mt.group("unit").casefold())
    occ = _find_occasion(occs, mt.group("unit")) if unit is None else None
    if unit is None and occ is None:
        return None                                    # 单位不认 / 表外具名日
    if occ is not None:
        if not closed or a != b:                       # 节日名**只许单点**（圣诞之间隔一年）
            return None
        got = _occurrence(occ, today, a)
        return (got, got) if got else None
    if kind == "last" and unit != "day":
        hi = b if closed else b - 1
        if hi < a:
            return None
        return _period(today, hi, unit)[0], _period(today, a, unit)[1]
    return _window_by_unit(today, rng, unit)           # `back` 与"1 天周期"的那些


def _parse_phrase(text: str, today: date, occs: list[Occasion]) -> tuple[date, date] | None:
    """人话（**同义改写**）: 固定短语表 + 两条参数化正则 + 裸节日名。"""
    fixed = _PHRASES.get(text)
    if fixed:
        return _parse_spec(fixed, today, occs)
    m = _AGO.match(text)
    if m:
        n = _num(m.group("n"))
        if n is None:
            return None
        return _parse_spec(f"back {n} {m.group('u')}", today, occs)
    m = _RECENT.match(text)
    if m:
        n, unit = _num(m.group("n")), _RECENT_UNIT.get(m.group("u"))
        if n is None or n < 1 or unit is None:
            return None
        spec = {"day": f"back 0..={n - 1} day", "week": f"back 0..={7 * n - 1} day",
                "month": f"back 0..={n} month", "year": f"back 0..={n} year"}[unit]
        return _parse_spec(spec, today, occs)
    for pre, n in _REL_YEAR.items():                   # 「去年圣诞」「上个圣诞」
        if text.startswith(pre):
            occ = _find_occasion(occs, text[len(pre):].lstrip("的"))
            if occ is not None:
                got = _occurrence(occ, today, n)
                return (got, got) if got else None
    occ = _find_occasion(occs, text)                   # 裸节日名 = **最近一次已过**
    if occ is not None:
        got = _occurrence_past(occ, today)
        return (got, got) if got else None
    return None


# ---------------------------------------------------------------------------
# 出口
# ---------------------------------------------------------------------------

def parse_when(raw: object, *, now: object) -> When | None:
    """她写的 `when` → `When`; **认不出 ⇒ `None`**（⛔ 不猜, ⛔ 不抛）。

    Args:
        raw: 她写的原串（`look` 载荷里的 `when`）。
        now: **现在**（`datetime` 或 `ts` 串）—— **必填**（同 `age.age_days` 的纪律:
            不许模块偷偷读壁钟; 回放与测试也要能钉死"现在"）。

    Returns: `When`; 认不出 ⇒ `None`。认不出的清单（都是**确定地拒**, 不是猜）:
        空串 · 语法不认（`back 4 wek` / `back 1..` / `N > 99`）· 表外具名日 ·
        端点反了（`last 1..0` / `10/1..=9/30`）· 节日名写成区间（`last 1..=2 christmas`）。

    ⚠️ **空串与"认不出"都返 `None`** —— 调用方自己知道她给没给 `when`（载荷里有没有
    那个键）, 不需要本模块替它区分。
    """
    text = str(raw or "").strip()
    today = date_of(now)
    if today is None and isinstance(now, date) and not hasattr(now, "hour"):
        today = now          # 直接给一个 `date` 也行（这一层的粒度本来就是"哪一天"）
    if not text or today is None:
        return None
    occs = load_occasions()
    for parse in (_parse_abs, _parse_spec, _parse_phrase):
        try:
            got = parse(text, today, occs)
        except Exception as e:                         # noqa: BLE001 — 解析绝不炸主链
            logger.warning("when 解析异常（按认不出处理）: %r — %s", text, e)
            return None
        if got is None:
            continue
        start, end = got
        future = start > today
        wide = None
        if not future and start == end:                # ⭐ **只有单日窗口才放宽**
            wide = (shift_days(start, -WIDEN_DAYS),
                    min(shift_days(end, WIDEN_DAYS), today))   # ⚠️ 末端夹到今天
        return When(exact=(start, end), wide=wide, source=text, future=future)
    return None


__all__ = ["WIDEN_DAYS", "When", "parse_when"]
