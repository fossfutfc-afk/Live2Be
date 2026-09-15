# -*- coding: utf-8 -*-
"""core.worldtime —— **时间**（独立包，叶子依赖）。

## 为什么单开一个包（2026-09-13 用户裁决）

*"这个时间有没有单开一个包的可能, 我想让它成为更加独立的设计"* —— 采纳。

**判据有两条, 一条是技术性的**:

1. **它不 import 项目内任何模块**。只依赖 stdlib。这是"独立设计"的可验证定义
2. **它被多处消费, 且方向不能反**。若时间住在 `core/brain/wiki_v2/`, 那渲染层
   要拿"3 周前"就得 import 记忆模块 —— **渲染依赖记忆, 方向反了**。
   时间是**横切关注点**, 不是记忆的子概念

先例: `core/affection/` 是同一形状（领域概念 + 自带数值层与状态 + 多消费方 + 可独立测）。

⚠️ **包名不叫 `core/time/`** —— 全库 7 处 `import time`（stdlib）, 同名包会造成歧义。
`worldtime` 同时容纳**两个时钟**（剧情时间 / 现实日历）, 与用户裁决的
"两个独立时钟, 永不试图同步"正对应。

## 模块职责（四条纪律）

| 模块 | 管什么 | 不管什么 |
|---|---|---|
| `story.py` | **时间点的数据模型 + 槽位算术**（纯函数, 无 IO） | 不读盘、不知道 LLM |
| `clock.py` | **游标真源**（`world_clock.json` 读写）+ 推进 + I6 单调校验 | 不算 age |
| `age.py` | **双出口**: 连续 `age` → `freshness`; 同一 age → `render_relative` 短语 | 不做排序、不知道 score |
| `span.py` | **LLM 面对的时间语法**（枚举 + 校验 + 夹取 + 默认） | 不做进位（那是 `story` 的） |
| `realtime.py` | 现实日历（②）+ 触发器幂等 + 目标日吸附 | **与 `story` 永不互算** |

## ★ 三条硬边界（违反即失去独立性）

1. **`core.worldtime` 不 import 项目内任何模块**。消费方单向依赖它。
   （唯一例外: `__init__` 内部的相对导入）
2. **时间概念在这里, 打分概念不在这里**。
   `freshness`（∈[0,1] 的新鲜度）是时间概念 —— 在这里;
   `det = SIG·freshness + emo_span·emo_int` 是**打分** —— 在
   `core/brain/wiki_v2/channel_impl.py`。**否则时间包迟早长出"权重"概念。**
3. **两个时钟永不互算**: `story` 的槽位算术**绝不**读 `realtime` 的日期;
   `realtime` 的触发器**绝不**改 `story` 的游标 —— 唯一交汇点是
   `realtime.snap_to(target)`（吸附, §4.6）, 且它**只能向前**（I6）。

## 与 `§4` 的关系

`DESIGN_WIKI_V3.md §4` 是**设计稿**（三层时钟 / 离散槽位 / 粒度枚举 / 凌晨归属 /
目标日吸附 / 模糊措辞）。本包是它的**实现**。文档与代码冲突时以文档的裁决为准,
但**新发现的事实写回文档**（§4.11 起）。
"""
from __future__ import annotations

from core.worldtime.age import age_sim_days, freshness, render_relative
from core.worldtime.clock import WorldClock
from core.worldtime.span import SPANS, SpanError, parse_span, to_sim_days
from core.worldtime.story import (
    PHASES,
    StoryTime,
    advance,
    parse_story_time,
)

__all__ = [
    # story —— 时间点与槽位算术
    "StoryTime",
    "PHASES",
    "advance",
    "parse_story_time",
    # clock —— 游标真源
    "WorldClock",
    # age —— 双出口
    "age_sim_days",
    "freshness",
    "render_relative",
    # span —— LLM 面对的时间语法
    "SPANS",
    "SpanError",
    "parse_span",
    "to_sim_days",
]
