# -*- coding: utf-8 -*-
"""时间的**双出口**（`§3.8` / `§4.9`）—— 同一个 `age`，两种消费方式。

```
node.story_time.sim_day ──┬──→ age（整数, 单调）──→ freshness(age, hl) ∈ [0,1]   给 det 的 TIME 格
                          └──→ render_relative(age) ──→ "3 周前"                给注入注记 / 渲染后缀
```

**为什么两个出口都要**（`§3.8` 已经定了"只在渲染层做，不落数据"）：

| 出口 | 需要什么 | 消费方 |
|---|---|---|
| `freshness` | **连续值**（`exp(−age/half_life)` 要算） | `A_intensity` 链路的 `det` |
| `render_relative` | **虚化短语** | ① 召回结果的渲染后缀 ② **防失忆注记** |

## ★ 硬约束：`render_relative` **绝不输出精确值**

- "三周前" —— 人回忆时的自然说法 ✅
- "21 天前" / "3.0 周前" / 任何日期 —— ❌ 两条理由:
  1. **破角色口径**（角色没有日历，会读成"她在数日子"）
  2. **诱导 LLM 做算术** —— 而那正是我们花两轮避免的

所以本模块的短语表**不接受自定义数字格式**；要改粒度就改表。

## ★ age 只用 `sim_day`（不跨 epoch 回绕）

`sim_day` 是单调整数（单位 = 时相格）。`year`/`month`/`week` **不参与** age 计算
——跨年时槽位会回绕，用槽位差会算出负数或跳变（`§4.9` 的原始表也提醒过
"跨吸附点要用吸附后的 sim_days 算"）。

## 新鲜度语义（用户裁决 2026-09-13）

`half_life` 表达 **新鲜度**（不是遗忘曲线）——"最近发生的浮上来"。
默认 **5 叙事日**。用户判断: *"遗忘曲线没办法适用了，60 天跨度太大了"* ——
且**不需要 X 轴缩放**: 新鲜度的自然尺度就是一周上下, `sim_day` 本来就是叙事时间,
量纲天然对齐。
"""
from __future__ import annotations

import math

from core.worldtime.story import DAYS_TO_SIM, StoryTime

#: 半衰期默认（**叙事日**）——进 `settings.toml [recall].time_half_life_days`
DEFAULT_HALF_LIFE_DAYS = 5.0

#: 措辞桶（`§3.8` / `§4.9` 的表）—— `(阈值上限叙事日, 单数, 复数)`
#: 顺序即判定顺序（从上往下第一个 age < 上限的胜出）。
_BUCKETS: tuple[tuple[float, str, str], ...] = (
    (1 / DAYS_TO_SIM, "刚才", "刚才"),      # < 1 时相
    (1.0, "今天", "今天"),                  # < 1 叙事日
    (2.0, "昨天", "N 天前"),
    (7.0, "N 天前", "N 天前"),              # 2~7 天
    (14.0, "上周", "N 周前"),
    (28.0, "N 周前", "N 周前"),             # 2~4 周
    (56.0, "上个月", "N 个月前"),
    (336.0, "N 个月前", "N 个月前"),        # 2~11 月
    (float("inf"), "去年", "N 年前"),
)

#: 高 significance 的旧事换更"贴身"的措辞（`§3.8`: "我一直记得那天" 而非 "三年前"）
_SIG_PRECIOUS = 0.8


def age_sim_days(node_st: StoryTime | None, now_st: StoryTime | None) -> int | None:
    """`age` = `now.sim_day − node.sim_day`（**整数, 单位 = 时相格**）。

    Returns:
        None = **任一侧缺值**（旧档未采集 / 游标未就绪）——调用方必须降级,
        **不得折成 0**（那会让旧记忆冒充"刚发生"，`det` 直接虚高）。
    """
    if node_st is None or now_st is None:
        return None
    return max(0, int(now_st.sim_day) - int(node_st.sim_day))


def freshness(age: int | None, half_life_days: float = DEFAULT_HALF_LIFE_DAYS
              ) -> float | None:
    """`age` → 新鲜度 ∈ (0, 1] —— **`det` 的 TIME 格**。

    `0.5 ** (age_days / half_life_days)`，`age_days = age / 5`（格 → 叙事日）。
    `age=0` → 1.0（刚发生）; `age = half_life` 处**正好 0.5**（半衰期的定义）;
    `age → ∞` → 0（但**永不取负**）。

    Returns: None = `age` 不可用（同上, 调用方降级）。
    """
    if age is None:
        return None
    hl = float(half_life_days) if half_life_days else DEFAULT_HALF_LIFE_DAYS
    if hl <= 0:
        hl = DEFAULT_HALF_LIFE_DAYS
    # `age` 的单位是**时相格**, 先换成叙事日再套半衰期
    return 0.5 ** ((age / DAYS_TO_SIM) / hl)


def render_relative(age: int | None, significance: float = 0.5) -> str:
    """`age` → **虚化短语**（`§3.8`）—— 注入注记 / 渲染后缀用。

    `age=None`（旧档）→ `"很久以前"`（**不显式暴露"未知"**——角色口径里
    "记不清多久了"本来就该这么说）。

    ★ **绝不输出精确值**（见模块 docstring）。
    """
    if age is None:
        return "很久以前"
    days = age / DAYS_TO_SIM
    for hi, singular, plural in _BUCKETS:
        if days < hi:
            return _phrase(days, singular, plural)
    return "很久以前"


def _phrase(days: float, singular: str, plural: str) -> str:
    """桶内取词: 含 `N` 的按数量替换（数量**已取整为人类口径**）。"""
    if "N" not in plural:
        return singular
    # 各桶的 N 单位不同 —— 按桶的语义取整（不是按 days 取整）
    if days < 2.0:
        n = 1                                  # "昨天"
        return "昨天" if plural == "N 天前" else plural.replace("N", str(n))
    if days < 14.0:
        n = int(round(days)) if days < 8 else int(round(days / 7))
        unit = "天前" if days < 8 else "周前"
        return f"{n} {unit}"
    if days < 56.0:
        return f"{int(round(days / 7))} 周前"
    if days < 336.0:
        return f"{int(round(days / 30))} 个月前"
    return f"{int(round(days / 365))} 年前"


def is_precious(significance: float) -> bool:
    """是否"珍贵档"——措辞可更贴身（`§3.8` 的情绪权重）。"""
    return float(significance or 0.0) >= _SIG_PRECIOUS
