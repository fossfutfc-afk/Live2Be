# -*- coding: utf-8 -*-
"""时间映射 —— **现实日期 → 年龄 → 双出口**（`§10` 暂定模型, 2026-09-17）。

```
node.ts ──┬──→ age_days（整数, 单位 = 现实日）──→ freshness(age, hl) ∈ [0,1]  给 det 的 TIME 格
          └──→ render_relative(age) ──────────→ "3 周前"                    给注入注记 / 渲染后缀
```

## ★ 唯一日期轴 = 现实日期（`docs/ESSAY_TIME_MODEL.md §10`）

旧口径是 `node.story_time.sim_day` —— 一个由 `time_span` 累加出来的"剧情日历"。
**已作废：它是里程表冒充日期**（见 ESSAY §2.5）。现行模型：

| | |
|---|---|
| 唯一日期轴 | **现实日期**（`ts`） |
| 剧情内部的流逝 | 自由（一场戏可从日到夜、可跨几天），但 **不累积、不进账、不构成第二个日历** |
| 记忆的年龄 | `today − date(node.ts)`，**整数日历日** |
| 「昨天」 | 现实的昨天 —— **玩家 / 引擎 / 角色 三方同一个** |

**为什么必须是"整数日历日"，不是"小时差"**：玩家说的是"昨天/今天"，那是**日历日**。

```
记忆 ts = 9/16 23:00   ，   现在 = 9/17 01:00
  小时差   = 2 小时  → 桶表判 < 1 天  → 「今天」   ❌ 玩家会说"昨天晚上"
  日历日差 = 1 天    → 桶表判 1      → 「昨天」   ✅ 与玩家同一个词
```

用小时差 = 引擎又持有了一个**独立于日历的连续时间量** —— 那就是又造了第二个时间量，
而 `ESSAY §8.2` 已经证明：**只要有两个时间量，就一定存在一个观察者能看见它们不一致**
（这里那个观察者就是玩家）。**引擎的时间坐标必须和玩家的是同一个。**

**与 `prompt_time.real_gap_note` 的分工 —— 两者可以不一致，而且是故意的**：

| | 轴 | 口径 |
|---|---|---|
| 记忆前缀（本模块） | **日历日** | 「（昨天）」—— 记忆的**坐标**，跨条可比、玩家可验证 |
| `real_gap_note` | **滚动小时** | 「她刚刚还在和老师说话」—— **间隔 / 感受**，单点 |

真人就是这样说话的：**凌晨 1 点，"他刚刚还在这儿"与"那是昨天的事"同时为真。**

（小时级的"刚才"因此没有丢 —— 它归 `real_gap_note`，不归记忆前缀。）

**承重墙**：*差速可以发生在「戏里」，不能发生在「账上」。*

## ★ 时区定死（ESSAY §10.3 约束 1）

`ts` 是 `datetime.now().isoformat()` 写下的**朴素本地时间**。若按"运行时的本地时区"切日，
换时区 / 改系统设置会让往事被重新贴标签（"昨天"变成"今天"）。
故本模块 **`REAL_TZ` 定死**，朴素 `ts` 一律按它解释、按它切日。

写入侧**已收敛**到 `now_ts()`（带固定时区, 见其 docstring）—— 事件流 / 节点 /
暂存 / digest 兜底四处都转调它。旧数据仍是朴素本地时间, `parse_ts()` 对两种都吃
（朴素按 `REAL_TZ` 解释）, **不回溯改旧数据**（append-only, 且没必要）。

## ★ 哨兵纪律（ESSAY §10.3 约束 4）

```
ts 缺失 / 空串 / 坏值  →  date_of() = None  →  age_days() = None
                      →  freshness() = None（**该节点**降级, 不是整条链路）
                      →  调用方不加短语（**绝不编一个"很久以前"**）

绝不折成 age = 0 —— 那会让旧记忆冒充"刚发生", `det` 直接虚高。
（与 `aff_at_encoding` / `emo_*` / 旧的 `story_time is None` 同一条哨兵纪律。）
```

## ★ 硬约束：`render_relative` **绝不输出精确值**

- "三周前" —— 人回忆时的自然说法 ✅
- "21 天前" / "3.0 周前" / 任何日期 —— ❌ 两条理由:
  1. **破角色口径**（角色没有日历，会读成"她在数日子"）
  2. **诱导 LLM 做算术** —— 而那正是我们花两轮避免的

所以本模块的短语表**不接受自定义数字格式**；要改粒度就改表。

## 新鲜度语义

`half_life` 表达 **新鲜度**（不是遗忘曲线）——"最近发生的浮上来"。

## ⚠️ 记忆衰减：**换轴之后两个方向都变了 —— 而这正是问题所在**

`DEFAULT_HALF_LIFE_DAYS` 的**量纲已从"叙事日"换成"现实日"，数值与模型都待重做**：

| | 旧（叙事日） | 新（现实日） |
|---|---|---|
| 玩家**在玩**（密集成块） | `age` 随剧情推进 +N → 衰减快 | `age` 基本不动（同一现实日）→ 衰减慢 |
| 玩家**不在玩**（间隔） | `age` 完全不动（没玩就没推进）→ **不衰减** | `age` 随现实流逝 → **衰减快** |

而**玩家的游玩时间天然是密集成块的离散**（一口气玩 3 小时 → 隔一周 → 又 3 小时），
记忆曲线假设时间**连续均匀** —— **不匹配**。

⇒ **这不是调 `half_life` 数值能解决的，需要新模型**（用户 2026-09-17 裁决：
*"由于玩家游玩的时间通常是密集成块的离散，不能用记忆曲线，需要新模型"*）。

⚠️ **2026-09-17 核实后纠正两条**（以代码为准）:

1. **"在玩时衰减慢"不成立** —— `age` 是现实日历日差, 与玩没玩无关
   （9/7 玩 3 小时、9/11 再玩 → 9/7 的记忆 `age=4`、`freshness=0.574`）
2. **Round A 的 `time_span` 不是新模型的输入** —— 它的年龄单位是**活跃日/会话**,
   输入是 `node.ts` + 事件流。那个字段**已删**（契约侧 + 本模块的注释都已改）


唯一的缓冲：矩阵第二行 `emo_span·emo_int` **不衰减** —— 强情绪记忆不受影响，
沉的只有日常记忆。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

#: ★ 定死的时区（约束 1）—— 朴素 `ts` 一律按它解释、按它切日。
#: 选 UTC+8 是因为本机与作者都在该时区；它只管"哪一天"，不管"几点"。
REAL_TZ = timezone(timedelta(hours=8))

#: 半衰期默认（**现实日**）—— 进 `settings.toml [recall].time_half_life_days`
#: ⚠️ 量纲已由"叙事日"改为"现实日"，数值**待重标定**（见模块 docstring）。
DEFAULT_HALF_LIFE_DAYS = 5.0

#: 措辞桶 —— `(阈值上限（现实日）, 单数, 复数)`
#: 顺序即判定顺序（从上往下第一个 `age < 上限` 的胜出）。
#:
#: ⚠️ **"刚才"那一档已删**（原为 `< 1 时相`）—— 整数日历日不可能落在它里面，
#: 留着会让 `age=0`（今天发生）被渲染成"刚才"。小时级的措辞归 `real_gap_note`。
#:
#: ⚠️ 注意本表**不承担精度**——精度归 `freshness`（连续值, 进 `det`）;
#: 短语只是"她怎么记得", 粗一点无害（见 `render_relative` docstring）。
_BUCKETS: tuple[tuple[float, str, str], ...] = (
    (1.0, "今天", "今天"),
    (1.5, "昨天", "昨天"),
    (7.0, "N 天前", "N 天前"),
    (14.0, "上周", "N 周前"),
    (28.0, "N 周前", "N 周前"),             # 2~4 周
    (56.0, "上个月", "N 个月前"),
    (336.0, "N 个月前", "N 个月前"),        # 2~11 月
    (float("inf"), "去年", "N 年前"),
)

#: 高 significance 的旧事换更"贴身"的措辞（`§3.8`: "我一直记得那天" 而非 "三年前"）
_SIG_PRECIOUS = 0.8


# ---------------------------------------------------------------------------
# ts ↔ 日期
# ---------------------------------------------------------------------------

def now_ts() -> str:
    """当前时刻的 `ts` 写法（**带固定时区**）——**写入侧的单一真源**。

    事件流与节点的一切 `ts` 都应经它写下（`events.now_iso` / `store.append_event`
    / `staging` / `digest` 兜底 —— 四处都转调这里）。不收敛的话，本模块的
    `REAL_TZ` 只是**读侧的一厢情愿**，而不是写入时的事实。

    ## 格式（2026-09-17 收敛）

    ```
    旧:  2026-09-07T03:37:20.037943     ← 朴素本地时间（无时区）
    新:  2026-09-07T03:37:20.037943+08:00
    ```

    **保留微秒**：真机事件流本来就是微秒精度（95/95 条），降精度是白白损失。
    故对旧数据的差异**只有"多带时区"一项**，其余逐字节一致。

    新旧并存是安全的：`parse_ts()` 对带时区与朴素两种都吃（朴素按 `REAL_TZ` 解释），
    而两者本就是同一时刻。**不回溯改旧数据**（append-only，且没必要）。
    """
    return datetime.now(REAL_TZ).isoformat()


def parse_ts(ts: object) -> datetime | None:
    """宽松解析一个 `ts` —— **缺/坏 → None, 不抛**。

    接受 `datetime` / ISO 字符串。**朴素时间按 `REAL_TZ` 解释**
    （历史 `ts` 都是 `datetime.now()` 写下的朴素本地时间）。
    """
    if isinstance(ts, datetime):
        dt = ts
    elif isinstance(ts, str) and ts.strip():
        try:
            dt = datetime.fromisoformat(ts.strip())
        except ValueError:
            return None
    else:
        return None
    return dt.replace(tzinfo=REAL_TZ) if dt.tzinfo is None else dt


def date_of(ts: object, *, tz: timezone = REAL_TZ) -> date | None:
    """`ts` → **日历日**（按定死的时区切）。**缺/坏 → None**。"""
    dt = parse_ts(ts)
    return None if dt is None else dt.astimezone(tz).date()


def age_days(node_ts: object, *, now: object, tz: timezone = REAL_TZ) -> int | None:
    """`age` = 今天 − 节点那天（**整数, 单位 = 现实日**）。

    `now` **必填**（不留默认值）—— 同 `RecallContext` 的纪律：
    逼调用方在调用处显式说明"现在是什么时候"，而不是让模块偷偷读壁钟。

    Returns:
        None = **任一侧缺值**（旧档 / 空 `ts` / 坏值）——调用方必须降级,
        **不得折成 0**（那会让旧记忆冒充"刚发生"，`det` 直接虚高）。
        未来日（时钟回拨 / 时区误配）**夹到 0**，不返回负数。
    """
    d0 = date_of(node_ts, tz=tz)
    d1 = date_of(now, tz=tz)
    if d0 is None or d1 is None:
        return None
    return max(0, (d1 - d0).days)


# ---------------------------------------------------------------------------
# 出口 1：连续值（给 det 的 TIME 格）
# ---------------------------------------------------------------------------

def freshness(age: int | None,
              half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float | None:
    """`age`（**现实日**）→ 新鲜度 ∈ (0, 1] —— **`det` 的 TIME 格**。

    `0.5 ** (age_days / half_life_days)`，`age=0` → 1.0（刚发生）;
    `age = half_life` 处**正好 0.5**（半衰期的定义）; `age → ∞` → 0（**永不取负**）。

    Returns: None = `age` 不可用（同上, 调用方降级）。
    """
    if age is None:
        return None
    hl = float(half_life_days) if half_life_days else DEFAULT_HALF_LIFE_DAYS
    if hl <= 0:
        hl = DEFAULT_HALF_LIFE_DAYS
    return 0.5 ** (float(age) / hl)


# ---------------------------------------------------------------------------
# 出口 2：虚化短语（给注入注记 / 渲染后缀）
# ---------------------------------------------------------------------------

def render_relative(age: int | None, significance: float = 0.5) -> str:
    """`age`（**现实日**）→ **虚化短语**（`§3.8`）。

    `age=None`（缺 `ts` / 旧档）→ `"很久以前"`（**不显式暴露"未知"**——
    角色口径里"记不清多久了"本来就该这么说）。

    ★ **绝不输出精确值**（见模块 docstring）。
    """
    if age is None:
        return "很久以前"
    days = float(age)
    for hi, singular, plural in _BUCKETS:
        if days < hi:
            return _phrase(days, singular, plural)
    return "很久以前"


def _phrase(days: float, singular: str, plural: str) -> str:
    """桶内取词 —— 含 `N` 的按数量替换（数量已取整为人类口径）。

    各桶的 `N` 单位不同, 故按桶语义换算（不是按 days 取整一次就完）。
    """
    if "N" not in plural:
        return singular                          # 今天/昨天/上周/上个月/去年
    if days <= 7.0:
        return f"{max(2, int(round(days)))} 天前"
    if days <= 28.0:                             # 2~4 周
        return f"{int(round(days / 7))} 周前"
    if days <= 56.0:
        return f"{int(round(days / 30))} 个月前"
    if days <= 336.0:                            # 2~11 月
        return f"{int(round(days / 30))} 个月前"
    return f"{int(round(days / 365))} 年前"


def is_precious(significance: float) -> bool:
    """是否"珍贵档"——措辞可更贴身（`§3.8` 的情绪权重）。"""
    return float(significance or 0.0) >= _SIG_PRECIOUS


__all__ = [
    "REAL_TZ",
    "DEFAULT_HALF_LIFE_DAYS",
    "now_ts",
    "parse_ts",
    "date_of",
    "age_days",
    "freshness",
    "render_relative",
    "is_precious",
]
