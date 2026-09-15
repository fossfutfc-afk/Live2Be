# -*- coding: utf-8 -*-
"""剧情时间的数据模型与槽位算术（`core.worldtime` 的叶子模块）。

**纯函数、无 IO、不 import 项目内任何模块。**

## ★ 量纲：`sim_day` 的推进单位 = **一个时相（1/5 叙事日）**

`DESIGN_WIKI_V3.md §4.2` 写的是 `"sim_day": 9` 与"单次跨度 ≤ 30 sim_day"——读起来
像"天"。但**槽位算术要求一个更细的单位**，否则下面这条必然矛盾：

```
凌晨 是 five-phase 循环的第 5 格。若 sim_day 只在整天时 +1, 则
"每场互动 +1 时相" 与 "sim_day = 天数" 互相打架 → 跨午夜时日历与计数器失同步。
```

**定死**：`sim_day` 是**整数**，单位 = **一个 `phase`**（= `PHASE_STEP` = 1/5 叙事日）。

| 常量 | 值 | 含义 |
|---|---|---|
| `PHASES_PER_DAY` | 5 | 一个叙事日 = 晨/昼/夕/夜/凌晨 五格 |
| `PHASE_STEP` | 1 | `sim_day` 每推进一格 +1（**单位就是格**） |
| `DAYS_TO_SIM` | 5 | `days:N` → `sim_day += 5N` |

**好处**：`sim_day` 整数 → **无浮点、无漂移、天然单调（I6）**。
叙事日数 = `sim_day / 5`（只在显示/半衰期换算时除）。
**`DESIGN_WIKI_V3.md §4.2` 的示例值需按此口径订正**（`9` 其实是"第 1.8 天"）。

## ★ 凌晨归属：**旋转发生在「进凌晨」这一刻**

用户点名的崩溃点：*"4/30 凌晨 = 4 月第 4 周，不是 5 月第 1 周"*。

| 时相序号 | 时相 | `sim_day` 增量 | 日历（周/月/年）旋转？ |
|---|---|---|---|
| 1 | 晨 | +1 | ✅ 旋进新的一天 |
| 2 | 昼 | +1 | — |
| 3 | 夕 | +1 | — |
| 4 | 夜 | +1 | — |
| **5** | **凌晨** | +1 | — （**属于刚结束的那一天**） |

即：**一天的五格 = 晨,昼,夕,夜,凌晨**，`sim_day` 是 5 的倍数处开始新的一天。
`4/30 的夜 → 4/30 的凌晨` **仍是 4 月第 4 周**；再进 `晨` 才翻到 5 月。

**为什么这样定**：若在"进凌晨"时翻日历，则"4/30 的夜"之后日历已经跳到 5/1，
`凌晨` 就落在 5 月 —— **正是用户点名要避免的**。
（另一条路是让 `凌晨` 不推进 `sim_day`，但那会让它与其他时相量纲不一致。）

## 日历派生：**日历永远由 `sim_day` 导出**

`week`/`month`/`year` 是 `sim_day` 的**纯函数**：

```
每 PHASES_PER_DAY 格  →  week + 1
week > 4              →  month + 1, week = 1
month > 12            →  year + 1, month = 1
```

`anchor`（作者锚点，默认 `{year:1, month:4}` = 开学）是**世界起点**。
**这个派生保证：日历与 `sim_day` 结构上不可能失同步** —— 不存在"两个计数器"。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: 一个叙事日的时相数（晨/昼/夕/夜/凌晨）
PHASES_PER_DAY = 5
#: `sim_day` 每推进一个时相的增量（单位就是"格"，故恒 1）
PHASE_STEP = 1
#: `days:N` → `sim_day` 的换算系数
DAYS_TO_SIM = PHASES_PER_DAY

#: 时相（**顺序即时间顺序**；循环回绕，见模块 docstring 的凌晨归属）
PHASES: tuple[str, ...] = ("晨", "昼", "夕", "夜", "凌晨")

#: 一周的周数 / 一年的月数
WEEKS_PER_MONTH = 4
MONTHS_PER_YEAR = 12

#: 默认锚点（BA 口径: 开学 = 四月）
DEFAULT_ANCHOR = {"year": 1, "month": 4}

#: 单次推进的上限（格）—— 30 叙事日 × 5（§4.3 的夹取）
MAX_STEP = 30 * DAYS_TO_SIM


@dataclass(frozen=True)
class StoryTime:
    """一个**剧情时间点** —— 不可变（`frozen`）。

    为什么 frozen: 它一旦 stamp 到节点上就**永不改**（与 `event_seq` 同性质）。
    冻结让"误改"变成 TypeError, 而不是一次静默的时间倒流。

    字段:
        year/month/week/phase —— **面向角色的日历槽**（渲染/措辞用）
        sim_day               —— **单调计数器**（排序/算 age 用; 单位 = 时相格）
        step                  —— 即 sim_day 的别名语义（此处只保留 sim_day 一个字段）

    `sim_day` 是**唯一**可比较量的来源 —— 槽位字段不参与 age 计算
    （跨年回绕会让槽位差失真, 见 `age.age_sim_days`）。
    """

    year: int = 1
    month: int = 4
    week: int = 1
    phase: str = PHASES[0]
    sim_day: int = 0

    # -- 构造 -----------------------------------------------------------
    @classmethod
    def from_sim_day(cls, sim_day: int,
                     anchor: dict | None = None) -> "StoryTime":
        """由 `sim_day` 与锚点**导出**完整时间点（日历是 sim_day 的纯函数）。

        日历约定（与 `§4.2` 的"`month` = 4 周"同源）:
            锚点当月第 1 周 = 起点; 每 7 个叙事日进一周; 每 4 周进一月。
            → `week = 1 + (days // 7) % 4`
            → `months_elapsed = days // 28`
        **`week` 与 `month` 是同一个计数的两种粒度**, 不存在第二个计数器
        （故结构上不可能失同步）。
        """
        anchor = _norm_anchor(anchor)
        n = max(0, int(sim_day))
        days, phase_idx = divmod(n, DAYS_TO_SIM)
        year = anchor["year"]
        month = anchor["month"]
        week = 1 + (days // 7) % WEEKS_PER_MONTH
        month += days // (WEEKS_PER_MONTH * 7)
        year += (month - 1) // MONTHS_PER_YEAR
        month = (month - 1) % MONTHS_PER_YEAR + 1
        return cls(year=year, month=month, week=week,
                   phase=PHASES[phase_idx], sim_day=n)

    # -- 比较（**只用 sim_day**）---------------------------------------
    def __lt__(self, other: "StoryTime") -> bool:
        return self.sim_day < other.sim_day

    def __le__(self, other: "StoryTime") -> bool:
        return self.sim_day <= other.sim_day

    def __gt__(self, other: "StoryTime") -> bool:
        return self.sim_day > other.sim_day

    def __ge__(self, other: "StoryTime") -> bool:
        return self.sim_day >= other.sim_day

    # -- 派生 -----------------------------------------------------------
    @property
    def story_day(self) -> float:
        """叙事日数（**仅显示/换算用**）——`sim_day / 5`。"""
        return self.sim_day / DAYS_TO_SIM

    def to_dict(self) -> dict:
        """节点序列化形态（与 `§4.2` 的 `story_time` 同构）。"""
        return {"year": self.year, "month": self.month, "week": self.week,
                "phase": self.phase, "sim_day": self.sim_day}

    def __str__(self) -> str:
        return (f"{self.year}年{self.month}月第{self.week}周{self.phase}"
                f"(sim_day={self.sim_day})")


def _norm_anchor(anchor: dict | None) -> dict:
    """锚点归一（缺失/坏值 → 默认; **不抛**——宁缺勿错, §4.3）。"""
    a = dict(DEFAULT_ANCHOR)
    if isinstance(anchor, dict):
        for k in ("year", "month"):
            v = anchor.get(k)
            if isinstance(v, int) and not isinstance(v, bool):
                a[k] = v
    a["year"] = max(1, a["year"])
    a["month"] = min(MONTHS_PER_YEAR, max(1, a["month"]))
    return a


def advance(st: StoryTime | None, span: str, *,
            anchor: dict | None = None) -> StoryTime:
    """推进时间点 —— **引擎承担全部算术**（§4.3）。

    `span` 已由 `span.parse_span` 校验/夹取过（本函数只做算术, 不判合法性）。
    语义:

        same      → 同一天内的下一格（时相 +1）
        halfday   → 时相 +1（**不推到整天**; 半天是"时相级"的措辞, 不是 2.5 格）
        day       → 叙事日 +1（= 5 格）
        days:N    → 叙事日 +N
        week      → 叙事日 +7
        weeks:N   → 叙事日 +7N
        month     → 叙事日 +28（= 4 周, 与 WEEKS_PER_MONTH 同源）

    `st=None`（无前序时间）→ 从 `sim_day=0`（锚点）起算。
    结果**恒 ≥ 输入**（I6 单调）—— 由构造保证, 不是靠断言。
    """
    base = st.sim_day if st is not None else 0
    # ★ 先过 `span.parse_span` 归一（坏形态的兜底在那里, 单一真源）——
    # 直接喂原始串会让 `days:` / `days:abc` 走到 `_n` 的 except, 但
    # `days:` 这种"前缀对、数字空"的形态会绕过兜底。
    from core.worldtime.span import parse_span
    delta = min(max(1, _span_to_sim(parse_span(span))), MAX_STEP)
    return StoryTime.from_sim_day(base + delta, anchor=anchor)


def _span_to_sim(span: str) -> int:
    """span → `sim_day` 增量（格）。未知形态 → `same`（1 格, 与 §4.3 的默认同源）。"""
    s = str(span or "").strip().lower()
    if s == "day":
        return DAYS_TO_SIM
    if s == "week":
        return 7 * DAYS_TO_SIM
    if s == "month":
        return WEEKS_PER_MONTH * 7 * DAYS_TO_SIM
    if s.startswith("days:"):
        return _n(s) * DAYS_TO_SIM
    if s.startswith("weeks:"):
        return _n(s) * 7 * DAYS_TO_SIM
    # same / halfday / 未知 → 同一天内的下一格
    return PHASE_STEP


def _n(s: str) -> int:
    """`days:N` / `weeks:N` 取 N（坏值 → 1; 上限由 `advance` 统一夹到 `MAX_STEP`）。"""
    try:
        return max(1, int(s.partition(":")[2]))
    except (TypeError, ValueError):
        return 1


def parse_story_time(raw: Any) -> StoryTime | None:
    """宽松解析节点上的 `story_time` dict —— **缺/坏 → None, 不抛**。

    `None`（未采集/旧档）**绝不折成 `sim_day=0`** —— 那会让旧记忆冒充
    "世界起点发生的"，与 `aff_at_encoding` / `emo_*` 同一条哨兵纪律。
    """
    if not isinstance(raw, dict):
        return None
    sd = raw.get("sim_day")
    if not isinstance(sd, int) or isinstance(sd, bool) or sd < 0:
        return None
    # 槽位字段以 sim_day 为准重导（防手写不一致的 dict 带进矛盾值）
    anchor = {"year": raw.get("year"), "month": raw.get("month")}
    return StoryTime.from_sim_day(sd, anchor=anchor)
