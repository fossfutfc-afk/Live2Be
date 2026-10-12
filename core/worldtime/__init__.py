"""core.worldtime —— **时间**（独立包，叶子依赖）。

## 为什么单开一个包（2026-09-13 用户裁决）

*"这个时间有没有单开一个包的可能, 我想让它成为更加独立的设计"* —— 采纳。

**判据有两条, 一条是技术性的**:

1. **它不 import 项目内任何模块**。只依赖 stdlib。这是"独立设计"的可验证定义
2. **它被多处消费, 且方向不能反**。若时间住在 `core/brain/`, 那渲染层
   要拿"3 周前"就得 import 记忆模块 —— **渲染依赖记忆, 方向反了**。
   时间是**横切关注点**, 不是记忆的子概念

先例: `core/affection/` 是同一形状（领域概念 + 自带数值层与状态 + 多消费方 + 可独立测）。

⚠️ **包名不叫 `core/time/`** —— 全库 7 处 `import time`（stdlib）, 同名包会造成歧义。
`worldtime` 同时容纳**两个时钟**（剧情时间 / 现实日历）, 与用户裁决的
"两个独立时钟, 永不试图同步"正对应。

## 模块职责（四条纪律）

| 模块 | 管什么 | 不管什么 |
|---|---|---|
| `age.py` | **双出口**: 连续 `age` → `freshness`; 同一 age → `render_relative` 短语 | 不做排序、不知道 score |
| `cal.py` | **日历算术**（位移 + 夹取: 月末 / 闰日 / 周首日）—— 纯 stdlib | 不做语法、不认人话 |
| `when.py` | ⭐ **她写的时间 → 检索窗口**（`last` / `back` 两族 + 绝对形式 + 人话容错） | ⛔ 不读壁钟、⛔ 不从整句话里抽时间、⛔ 不猜 |
| `prompt_time.py` | **进 prompt 的时间注记**（现实间隔 / 手机日期）—— 纯渲染, 无 IO | 不读盘、不判定 |
| `span.py` | **LLM 面对的时间语法**（枚举 + 校验; 输出但不消费, 等衰减新模型） | 不做进位、不做衰减 |
| `realtime.py` | **现实日历（②）**: 特殊日期表 + 触发幂等 + `real_clock.json` 台账 | **只做由头, 不做时钟**（不持有任何时钟） |

⚠️ **`when.py` 与 `span.py` 不是重复**: `span` 是"LLM 说**跨了多久**"（剧情粒度枚举, 已无
运行时消费方）; `when` 是"她问**哪一段时间的事**"（检索区间）。一个管叙事事实, 一个管检索。

⚠️ **`story.py` / `clock.py` 已于 2026-09-17「时间轴换代」删除** —— 剧情游标
（`world_clock.json`）不再是时间事实, 唯一日期轴 = 现实日期（`age.py` docstring）。

## ★ 三条硬边界（违反即失去独立性）

1. **`core.worldtime` 不 import 项目内任何模块**。消费方单向依赖它。
   （唯一例外: `__init__` 内部的相对导入）
2. **时间概念在这里, 打分概念不在这里**。
   `freshness`（∈[0,1] 的新鲜度）是时间概念 —— 在这里;
   `det = SIG·freshness + emo_span·emo_int` 是**打分** —— 在
   `core/brain/read/channel_impl.py`。**否则时间包迟早长出"权重"概念。**
3. **没有第二个时钟可算**: 剧情时间不进账（不累积、不落库）, 现实日期是唯一轴。
   故**不存在**"两个时钟互算"的问题 —— 那曾是 `snap_to`（目标日吸附）的唯一
   理由, 而吸附的前提已随换代取消。`realtime` 与 `age` 各算各的, 互不引用。

## 与 `§4` 的关系

`DESIGN_WIKI_V3.md §4` 是**旧的**三层时钟设计稿（已随换代作废, 见
`docs/ESSAY_TIME_MODEL.md §10` 与 `TODO.md`「时间轴换代」）; `§4.11` 的
"时间注记进 prompt"仍然有效。文档与代码冲突时**以代码为准**。
"""
from __future__ import annotations

from core.worldtime.age import (
    DEFAULT_FRESHNESS_FLOOR,
    DEFAULT_HALF_LIFE_DAYS,
    REAL_TZ,
    age_days,
    date_of,
    freshness,
    is_precious,
    now_ts,
    parse_ts,
    render_date,
    render_relative,
)
from core.worldtime.prompt_time import (
    notes as time_notes,
)
from core.worldtime.prompt_time import (
    phone_date_note,
    real_gap_note,
)
from core.worldtime.realtime import (
    Occasion,
    load_clock,
    load_occasions,
)
from core.worldtime.realtime import (
    due_notes as realtime_notes,
)
from core.worldtime.span import SPANS, SpanError, parse_span
from core.worldtime.when import WIDEN_DAYS, When, parse_when

__all__ = [
    # age —— 双出口（2026-09-17: 年龄改由**现实日期**算, §10）
    "REAL_TZ",
    "DEFAULT_HALF_LIFE_DAYS",
    "DEFAULT_FRESHNESS_FLOOR",
    "age_days",
    "date_of",
    "freshness",
    "render_relative",
    # ⭐ N5（2026-09-29）: **绝对日期**（引擎坐标）—— 与虚化短语两个都要
    # （模糊是她的口吻, 绝对是坐标; 见 `PROCEED §2 #16`）
    "render_date",
    "is_precious",
    "now_ts",
    "parse_ts",
    # span —— LLM 面对的时间语法（**枚举定义**；⚠️ 契约侧 `time_span` 字段
    # 已于 2026-09-17 删除, 本模块现无运行时消费方 —— 留的是语法, 见 span.py）
    "SPANS",
    "SpanError",
    "parse_span",
    # prompt_time —— 进 prompt 的注记（⚠️ `FICTIONAL_YEAR` 已于 2026-09-17 删除:
    # 手机上的日期现在**就是真实日期**, 见该模块 docstring）
    "time_notes",
    "phone_date_note",
    "real_gap_note",
    # realtime —— 现实日历（②）: 表 + 台账（⚠️ 尚未接进 MMT; 接入点见 TODO）
    "Occasion",
    "load_occasions",
    "load_clock",
    "realtime_notes",
    # ⭐ when —— 她写的时间 → 检索窗口（2026-10-08; `last` / `back` 两族 + 人话容错）
    "WIDEN_DAYS",
    "When",
    "parse_when",
]
