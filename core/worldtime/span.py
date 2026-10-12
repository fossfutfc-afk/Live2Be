"""LLM 面对的时间语法 —— **粒度枚举的契约层**（`§4.3`）。

**为什么单独一个模块**: 它是**契约**, 不是数据模型。`story.py` 永远不沾 LLM 概念;
契约要跟 `contract/` 层对齐、要刷 prompt 夹具。分开后 `story`/`clock`/`age`
三个模块永远是纯引擎代码。

## 为什么不让 LLM 给"间隔天数"（`§4.3` 的原话）

*"LLM 给的数字既不准也无法验证，而**粒度枚举是可枚举、可校验、可兜底的**。
'跨了三天'这种叙事事实由 LLM 给（`days:3`），'这三天落在哪一周'由引擎算
——正是项目'LLM 演、引擎判'的老分工。"*

## 枚举（本模块是唯一真源）

| span | 含义 | `sim_day` 增量（格） |
|---|---|---|
| `same` | 紧接着（同一天内的下一格） | 1 |
| `halfday` | 半日（**时相级措辞, 不推到整天**） | 1 |
| `day` | 跨了一天 | 5 |
| `days:2..7` | 跨了 2~7 天 | 5N |
| `week` | 跨了一周 | 35 |
| `weeks:2..4` | 跨了 2~4 周 | 35N |
| `month` | 跨了一个月（= 4 周） | 140 |

**`days:N` 上限 7** —— 超过一周就该用 `week`/`weeks:N`。
**粒度枚举本身要防止模型用 `days:30` 绕过周**（§4.3 的夹取 ≤30 天是最后一道闸）。

⚠️ **命名注意**: `halfday` 曾叫 `phase`，与时相字段（晨/昼/夕/夜/凌晨）**重名**，
读文档时极易把"LLM 选了 phase"误读成"LLM 选了时相"。**已改名**。
"""
from __future__ import annotations

import re

#: 合法枚举（正则形态; `N` 的范围在下面单独夹）
_SIMPLE = ("same", "halfday", "day", "week", "month")
_N_RE = re.compile(r"^(days|weeks):(\d{1,2})$")

#: `days:N` 的 N 上限（超过就该用 week）
DAYS_N_MAX = 7
#: `weeks:N` 的 N 上限（超过就该用 month）
WEEKS_N_MAX = 4

#: 越界/无法解析时的默认（§4.3: 非法值 → 走默认 +1 时相）
DEFAULT_SPAN = "halfday"

#: 台账/文档用: 全部合法形态
SPANS: tuple[str, ...] = (
    *_SIMPLE,
    *(f"days:{i}" for i in range(2, DAYS_N_MAX + 1)),
    *(f"weeks:{i}" for i in range(2, WEEKS_N_MAX + 1)),
)


class SpanError(ValueError):
    """span 非法（**由 `parse_span` 内部吃掉, 只在显式 strict 时抛**）。"""


def parse_span(raw, *, strict: bool = False) -> str:
    """LLM 输出 → 合法 span —— **永不抛**（除非 `strict=True`）。

    归一: 去空白 / 小写 / `days:1` → `day` / `weeks:1` → `week`。
    越界（`days:30`）→ 夹到上限（`days:7`）并告警——**夹取比丢弃好**:
    叙事事实"跨了很久"比"精确多久"重要。
    无法识别 → `DEFAULT_SPAN`（+1 时相）。

    Returns: 恒 ∈ `SPANS` 的字符串。
    """
    s = str(raw or "").strip().lower().replace(" ", "")
    if not s:
        return _or_raise(DEFAULT_SPAN, strict, "空值")
    if s in _SIMPLE:
        return s
    m = _N_RE.match(s)
    if m:
        unit, n = m.group(1), int(m.group(2))
        hi = DAYS_N_MAX if unit == "days" else WEEKS_N_MAX
        if n < 1:
            return _or_raise(DEFAULT_SPAN, strict, f"{s} 的 N < 1")
        n = min(n, hi)                       # ★ 夹取而不丢弃
        if n == 1:
            return unit[:-1]                 # days:1 → day / weeks:1 → week
        return f"{unit}:{n}"
    return _or_raise(DEFAULT_SPAN, strict, f"无法识别: {raw!r}")


def _or_raise(fallback: str, strict: bool, why: str) -> str:
    if strict:
        raise SpanError(why)
    return fallback


#: ⚠️ `to_sim_days()` 已于 2026-09-17 删除（时间轴换代, `ESSAY_TIME_MODEL §10`）——
#: 它把 span 换算成 **`sim_day` 格数**（1 格 = 1/5 叙事日, 转调 `story._span_to_sim`）。
#: 那个单位随**剧情日历**一起作废（唯一日期轴 = 现实日期; `story.py` 已删）。
#:
#: ## ★ 本模块现在只剩"枚举定义"这一个职责
#:
#: `SPANS` / `parse_span` —— **没有任何运行时消费方**。
#:
#: 契约侧的 `time_span` 字段**也已删**（2026-09-17 用户裁决, 见
#: `contract/digest_registry.py` 的删除说明）。当时给它和本模块的免死理由是
#: "为衰减新模型预留" —— **那个理由不成立**: 新模型的年龄单位是**活跃日/会话**,
#: 输入是 `node.ts` + 事件流, `time_span` 不是它的输入。
#:
#: **为什么仍然保留本模块**: 契约死了, 语法不必跟着死。将来真要有"她口述那阵子
#: 跨了多久"的需求（渲染层, 不是召回层）, 这套枚举 + `parse_span` 的夹取可以直接
#: 拿回来用, 不必重写。

