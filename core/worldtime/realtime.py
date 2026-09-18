# -*- coding: utf-8 -*-
"""现实日历（②）—— **只做由头，不做时钟**（2026-09-17 换代后实现）。

```
今天是不是某个日子？  ← 本模块只答这一句
所以呢？              ← 主 LLM 的（发不发、发几条、怎么措辞）
```

## 本模块持有什么、不持有什么

| 持有 | 不持有 |
|---|---|
| **一张表**（`config/eggs/festivals.json`, 作者手编） | ❌ 任何时钟 —— 时间只从 `now` 参数进来 |
| **一本台账**（`real_clock.json`: 见过哪天 / 跟谁说过哪个日子） | ❌ 任何"所以呢" —— 概率、冷却、措辞都不在这 |

旧的 `world_clock.json`（剧情游标）与它**无关**, 那套已随"时间轴换代"作废
（见 `age.py` 模块 docstring 与 `docs/ESSAY_TIME_MODEL.md §10`）。

## ★ 为什么改成了"查表"而不是"代码里写死三个节日"

用户裁决（2026-09-17）: *"我希望维护一个特殊节日 json 表，从中读取信息，
这样十分易于扩展"* —— 采纳。判据是 `CLAUDE.md §8` 那条的同一把尺子:
**引擎不知道"圣诞节"是什么**。所有语义都在表里, 代码里**不存在**任何
`if id == "christmas"`。加一个节日 = 加一行。

## ★ 四条不直观但要命的设计决定

### 1. `year` 栏干两份活 —— 匹配条件 **+** 幂等键的生成器

| `year` 栏 | 匹配 | 幂等键 | 效果 |
|---|---|---|---|
| 留空 | 任意年 | `christmas:2026` | **每年一次**（圣诞 / 情人节 / 生日） |
| 写死 `2027` | 只有 2027 | `anniv:2027` | **一辈子一次**（周年 / 开服纪念） |

所以**一张表同时表达"每年"和"一次"**, 不需要额外的 `repeat` 字段。
`key` 缺省 = `id`（生日要 8 个人共用 `birthday` 这个 id, 才需要显式写 `key`）。

### 2. 幂等键的年份用**现实年** —— 而这一条现在**不再有张力**了

原本这里有一处别扭: 她看到的是 `prompt_time.FICTIONAL_YEAR = 2100`（**定死**）,
而键必须按现实年递增, 否则"每年一次"会退化成"一辈子一次" —— 代价是同一个角色的
两个不同年的圣诞, 在她眼里是同一个 `2100-12-25`（double date 的又一症状）。

**2026-09-17: 虚构年被删除**（用户裁决 *"既然时间同步了，FICTIONAL_YEAR 还有
必要吗"* → **直接删**）。现在她手机上就是真实年份, 于是:

- **键的年份 = 显示的年份 = 事件流 `ts` 的年份 = 同一个**。三处终于同源
- "两个不同年的圣诞在她眼里是同一个"这条后果**消失**
- 本决定退化成一句废话（"键用年份"）, 但**保留在文档里**: 它是踩过的坑,
  且将来任何人想再引入"显示用另一套日历"时, 这就是那条反对意见

### 3. 台账必须**按角色分桶** —— 而它住在**世界级**的文件里

`real_clock.json` 是一世界一条线（`last_seen_date` / `rewind_count` 天然世界级）,
但"这个日子跟她说过了没有"是**角色级**的事: 同一个世界里有 5 个角色, 不分组的话
遥香过完圣诞, 阿露就永远收不到圣诞。⇒ `fired` 两层: `fired[char_id][signature]`。

### 4. 触发条件是 `今天 >= 那个日子`, **不是** `今天 == 那个日子`

`>=` 买到两件事:

1. **那天她没上线, 第二天仍然算** —— "最近一次那个日子"还停在昨天 ⇒ 该点火就
   点火（但 `fired` 只在第一个说得上话的回合记一次）
2. **时钟回拨 / 改系统时间 / 跨时区全部自愈** —— 键写在未来 → 时间退回去后
   "已触发"判定为假 → 到了那天重新点火（正确）; 键留在过去 → 仍判"已触发"
   → 不重发（正确）

⚠️ **但它单独用会出事**: 12/25 那天四个节日的 `target` 全都 ≤ today, 于是同时
到期。必须配 `due_occasions` 的"考古地板" —— 那是冒烟试出来的, 见该函数闸 ②。

## ★ 两条边界（违反即出错）

1. **只注 MMT, 不注 VN**。同 `prompt_time.phone_date_note`: 产品内 VN 没有自由
   打字通道, 玩家的"话"只经选项说出 → 问不出"今天什么日子"。注了只会污染剧情
   创作（写出"老师，今天是圣诞节呢"而场景里连圣诞树都没有）。
2. **注记里有归因**（"手机日历上标着"）。没有归因, 她就成了**在读取世界状态** ——
   同 `phone_date_note` 的"这是你手机上显示的日期"。她不是知道今天是什么日子,
   她是**掏手机看了一眼**。

## ★ 给将来的一条提醒（不是规矩, 是反对意见）

`nth_weekday`（母亲节 = 5 月第二个周日）这类匹配器将来要做时, 口径是**真实日历**
—— 因为 2026-09-17 起"她手机上显示的日期"**就是真实日期**（虚构年已删）。

⚠️ 这里曾经写着一条"必须按虚构年日历重算, 否则当场矛盾"的规矩 —— **那是我写错的**:
`phone_date` 本来就是按虚构年算星期几的, 她前后自洽（"9 月 13 日是星期一",
而 2100-09-13 正是星期一）。**虚构年被删之后这条顾虑彻底不存在了。**
留给将来的只有一句: **别再引入"显示用另一套日历"** —— 那正是 `FICTIONAL_YEAR`
被删的原因（它成了唯一不前进的年份, 而 `fired` 已按现实年记账）。

## 落地边界（这一轮做到哪）

| 做 | 不做 |
|---|---|
| 表解析 + `occasions_on` / `due_occasions` / `mark_fired` / `due_notes` | ❌ `snap_to` / 目标日吸附 / 迟到档 / `time_jump`（**不做吸附**, 前提已取消） |
| `real_clock.json` 台账（`last_seen_date` / `rewind_count` / 按角色的 `fired`） | ❌ 补发（q5: 不补发 —— 新角色零补发, 只有"她上次在场之后"的日子算） |
| 生日读 `profile.yml` 的 `SIG~birthday`（走 `OccasionSource` 扩展点, **尚未接**） | ❌ 农历 / `nth_weekday` 匹配器（扩展点已留, 未实现） |

⚠️ **接入尚未做**: `momotalk.py` 那个 MMT 每轮装配点上**还没有**调 `due_notes`。
落地位置已定（P17 时间注记之后、P18 随机事件之前）, 是独立的一步。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

#: 定死的时区 —— 与 `age.REAL_TZ` 同源（本模块只是不在导入期绑死依赖关系）。
try:                                            # pragma: no cover — 恒走 try
    from core.worldtime.age import REAL_TZ as _REAL_TZ
except Exception:                               # noqa: BLE001 — 独立性兜底
    _REAL_TZ = timezone(timedelta(hours=8))

#: 台账 `schema_version`（将来改结构时用来决定怎么读旧档）
CLOCK_SCHEMA_VERSION = 1

#: 表 `schema_version`
TABLE_SCHEMA_VERSION = 1

#: 项目根（cwd 无关 —— uvicorn / IDE 从任意目录启动）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

#: 默认表路径（作者手编; `config/eggs/` = 作者塞东西的地方, `namegg.json` 的邻居）
DEFAULT_TABLE_PATH = _PROJECT_ROOT / "config" / "eggs" / "festivals.json"

#: 台账文件名（**落在 `store.world_dir()` 下** —— 世界级, 与角色目录并列）
CLOCK_FILENAME = "real_clock.json"


def default_table_path() -> Path:
    """默认节日表路径（调用方要传路径时用它, 别自己拼）。"""
    return DEFAULT_TABLE_PATH


def clock_path(world_dir: str | Path) -> Path:
    """`real_clock.json` 的路径（给 `store.world_dir()` 即得）。"""
    return Path(world_dir) / CLOCK_FILENAME


# ---------------------------------------------------------------------------
# Occasion —— 表里一行
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Occasion:
    """一个特殊日子（表里一行）。

    `year=None` = **任意年**（每年一次）; `year=2027` = **只那一年**（一辈子一次）
    —— 见模块 docstring 决定 1。`load_occasions` 会把 `""` 归一成 `None`。
    """

    id: str
    month: int
    day: int
    name: str
    proactive: bool
    year: int | None = None
    key: str = ""
    note_text: str = ""

    @property
    def sig_key(self) -> str:
        """幂等键的名字部分（`key` 缺省 = `id`）。"""
        return self.key or self.id

    @property
    def year_fixed(self) -> bool:
        """`year` 栏是否写死了（True = 一辈子一次）。"""
        return self.year is not None

    def _on(self, year: int) -> date:
        """那一年里"这个日子"是哪天（`2/29` 而当年非闰年 → 落到 `3/1`）。

        同 `prompt_time.phone_date` 的闰年处置: **绝不构造一个不存在的日期**。
        """
        try:
            return date(year, self.month, self.day)
        except ValueError:
            return date(year, 3, 1)

    def target(self, today: date) -> date:
        """这个日子**在 `today` 所在的这一期里**是哪天（**可能还没到**）。

        - `year` 写死 → 就是那一年那一天
        - `year` 留空 → **今年**的那一天（今年还没到就返回未来的日期）

        ⚠️ **这里刻意不"回退到上一次"** —— 那是我第一版写错的地方, 记在这里。
        若 `today > 今年那天` 时回退到去年, 那么:
        **12/25 建的新档会在 3/1 收到"圣诞快乐"**（去年的圣诞"已经过了"）,
        而那是**补发**, q5 裁决是不补发。

        ⇒ `target` 只回答"这一期是哪天", **"过没过"由 `due_occasions` 判**
        （`target <= today`）。两件事分开, 才拦得住"去年的那个日子"。
        """
        if self.year is not None:
            return self._on(self.year)
        return self._on(today.year)

    def signature(self, today: date) -> str:
        """幂等键 —— `{key}:{year}`（年份 = `target(today).year`, 现实年）。

        2026-09-17 之前这里要特意声明"**不是她看到的 `2100`**"（那时虚构年定死,
        拿它当键会让"每年一次"退化成"一辈子一次"）。虚构年删掉之后就没有这层
        区别了 —— **键的年份、显示的年份、`ts` 的年份是同一个**。
        """
        return f"{self.sig_key}:{self.target(today).year}"

    def note(self) -> str:
        """进 prompt 的注记（表里写了 `note_text` 就用它, 否则走默认模板）。

        默认模板 = **归因**（"手机日历上标着"）+ 名字 + `proactive` 时的许可半句。
        归因不可省 —— 见模块 docstring 边界 2。
        """
        if self.note_text.strip():
            return self.note_text.strip()
        head = f"（手机日历上标着：{self.name}）"
        if self.proactive:
            return head + "如果合适，你可以主动提起这件事。"
        return head


#: `year` 栏的"任意年"写法 —— 空串（作者会这么写）/ `None`（程序会吐这个）/ `"*"`（显式）
_BLANK_STR = ("", "*")


def _blank(v: object) -> bool:
    """这个格子是不是"留空 = 匹配任意"（作者写空串、程序吐 `None`, 两者都得吃）。"""
    return v is None or (isinstance(v, str) and v.strip() in _BLANK_STR)


def _norm_year(v: object) -> int | None:
    """`year` 栏 → `int | None`（空/坏 → None = 任意年, 不抛）。"""
    if _blank(v):
        return None
    try:
        return int(v)                                  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 表 —— 读 `festivals.json`
# ---------------------------------------------------------------------------

def load_occasions(path: str | Path | None = None) -> list[Occasion]:
    """读节日表 → `list[Occasion]`（**文件缺失 / 损坏 → `[]`**, 宁缺勿错）。

    逐行容错: 缺必填（`id` / `month` / `day` / `name` / `proactive`）或值非法的
    那一行**跳过并 WARNING**, 其余照常可用 —— "表里有一行写坏了"绝不该让
    整个节日系统停工。

    ★ **`proactive` 是必填**（用户裁决: 逐行手写, 不设默认值）——
    这样"这一行为什么能主动提"在文件里一眼看得出, 不靠代码里的默认值猜。

    `enabled: false` 的行**读进来就丢**（已触发过的账留在 `fired` 里, 删行会丢账）。

    返回顺序 = **文件顺序**（作者手编, 顺序即作者意图; 不排序）。
    """
    p = Path(path) if path is not None else default_table_path()
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError:
        logger.warning("节日表读不到（视为空）: %s", p)
        return []
    # ★ 允许 `//` 注释行（与 `namegg.json` 同款——作者手编的文件得像配置, 不像 JSON）
    text = "\n".join(ln for ln in raw.splitlines()
                     if not ln.lstrip().startswith("//"))
    try:
        data = json.loads(text)
    except ValueError as e:
        logger.warning("节日表不是合法 JSON（视为空）: %s — %s", p, e)
        return []
    if not isinstance(data, dict):
        logger.warning("节日表根不是对象（视为空）: %s", p)
        return []
    rows = data.get("festivals")
    if not isinstance(rows, list):
        logger.warning("节日表缺 festivals 数组（视为空）: %s", p)
        return []

    out: list[Occasion] = []
    seen: set[tuple[str, bool]] = set()
    for i, row in enumerate(rows):
        occ = _parse_row(row, where=f"{p}#festivals[{i}]")
        if occ is None:
            continue
        # 同 key 的"任意年"与"写死年"并存 → 两边都想写同一笔账; 后到的丢
        bucket = (occ.sig_key, occ.year_fixed)
        if bucket in seen:
            logger.warning("节日表 key 重复（跳过后到的）: %s %s", occ.sig_key, bucket[1])
            continue
        seen.add(bucket)
        out.append(occ)
    return out


def _parse_row(row: object, *, where: str) -> Occasion | None:
    """表里一行 → `Occasion`; 不合格 → `None`（打 WARNING）。

    宽松: 数字写成字符串（`"12"`）也吃 —— 手编文件里 `"12"` 和 `12` 是同一个意思,
    为此让一行失效不值得。
    """
    if not isinstance(row, dict):
        logger.warning("节日表行不是对象（跳过）: %s", where)
        return None
    if row.get("enabled") is False:
        logger.info("节日表行已停用（跳过）: %s", where)
        return None
    oid = str(row.get("id") or "").strip()
    name = str(row.get("name") or "").strip()
    if not oid or not name:
        logger.warning("节日表行缺 id / name（跳过）: %s", where)
        return None
    try:
        month, day = int(row.get("month")), int(row.get("day"))   # type: ignore[arg-type]
    except (TypeError, ValueError):
        logger.warning("节日表行 month / day 不是数字（跳过）: %s", where)
        return None
    if not (1 <= month <= 12) or not (1 <= day <= 31):
        logger.warning("节日表行 month / day 越界（跳过）: %s — %s/%s",
                       where, month, day)
        return None
    if "proactive" not in row or not isinstance(row.get("proactive"), bool):
        logger.warning("节日表行缺 proactive（必填, 不设默认值; 跳过）: %s", where)
        return None
    return Occasion(
        id=oid,
        month=month,
        day=day,
        name=name,
        proactive=bool(row["proactive"]),
        year=_norm_year(row.get("year")),
        key=str(row.get("key") or "").strip(),
        note_text=str(row.get("note_text") or ""),
    )


# ---------------------------------------------------------------------------
# 判定（纯函数, 无 IO）
# ---------------------------------------------------------------------------

def _as_day(now: object = None) -> date:
    """`now` → **日历日**（缺 / 坏 → 现在）。

    吃 `None` / `date` / `datetime` / ISO 串 —— 朴素时间一律按定死的时区解释
    （同 `age.parse_ts` 的纪律: 朴素 `ts` 是历史遗留, 按本地时区读）。
    """
    if now is None:
        return datetime.now(_REAL_TZ).date()
    if isinstance(now, datetime):
        dt = now
    elif isinstance(now, date):
        return now
    elif isinstance(now, str) and now.strip():
        try:
            dt = datetime.fromisoformat(now.strip())
        except ValueError:
            return datetime.now(_REAL_TZ).date()
    else:
        return datetime.now(_REAL_TZ).date()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_REAL_TZ)
    return dt.astimezone(_REAL_TZ).date()


def occasions_on(day: object = None, *,
                 occasions: list[Occasion] | None = None,
                 path: str | Path | None = None) -> list[tuple[Occasion, date]]:
    """**表里每个日子在这一期是哪天** —— `[(Occasion, 那天), …]`（纯投影）。

    `day` 吃 `date` / `datetime` / ISO 串 / `None`(=现在)。
    `occasions` 给了就用它（测试注入）, 否则读 `path`（缺省默认表）。

    ⚠️ **它不过滤任何东西** —— "过没过 / 说过没说过"是 `due_occasions` 的事。
    这个函数只做"表 → 日期"这一步投影, 好让两边都能单独验。
    """
    today = _as_day(day)
    occs = occasions if occasions is not None else load_occasions(path)
    return [(o, o.target(today)) for o in occs]


def due_occasions(char_id: str, clock: dict | None, day: object = None, *,
                  occasions: list[Occasion] | None = None,
                  path: str | Path | None = None) -> list[Occasion]:
    """**今天该跟她说的那些日子** —— 三条闸全过的才算。

    ```
    ① 已经过了   target <= today          ← 这一期的那个日子已经到了
    ② 不是考古   target >= 地板            ← ★ 见下, 这条防"补发"
    ③ 没说过     signature 不在 fired 里   ← 恰好一次
    ```

    ## ★ 为什么需要 ②（冒烟试出来的, 不是想出来的）

    只有 ① ③ 的话, **12/25 那天四个节日会同时到期** —— 元旦(1/1)、情人节(2/14)、
    教师节(9/10) 的 `target` 全 ≤ today。一个刚建的档第一天收到四条节日祝福,
    那不是节日系统, 那是补发（q5 裁决: **不补发**）。

    更糟的是我第一版把 `target` 写成"回退到最近一次", 于是**12/25 建的新档在
    3/1 也能收到"圣诞快乐"**（去年的圣诞"已经过了"）。所以 `target` 现在只答
    "这一期是哪天", "过没过"由本函数判 —— 两件事分开才拦得住去年的日子。

    ## 地板 = **上次跟她说过话那天**（两条特例）

    ```
    说过话      →  地板 = last_seen_date        ← 她不在场那段日子, 整段不算
    从没说过话  →  地板 = 今天 − 1 天            ← ★ 她还没有过去, 只认"今天"
    ```

    | 地板 | 挡什么 | 放过什么 |
    |---|---|---|
    | `last_seen_date` | 她**不在场**时发生的所有日子 | "一周没上线 → 回来补上上周那件事" |
    | **从没说过话 → 今天 − 1 天** | 她**还不存在**时的所有日子 | 建号当天赶上的节日 |

    ★ **两条特例都是试出来的, 记在这里免得被"简化"掉**:

    1. **`last_seen_date` 不能退化成"今天 − 1 年"**。用"一年以内"当窗口时,
       12/25 那天**四个节日的 target 全落进窗口**, 一次冒出四条。改成
       "上次跟她说过话那天" 之后, 短期离开照样补得上（12/25 玩过、12/27 回来
       仍能听到圣诞）, 而**她不在场那几个月的事一件都不会翻出来**
    2. **`last_seen_date` 为空不能当成"一年前"**。第一版让它退化成"今天 − 1 年",
       于是**新档第一天收到元旦+情人节两条祝福**; 根因是 `new_clock()` 当时把
       `last_seen_date` 初始化成了"今天"—— 一个"她早就见过老师"的假事实。
       现在空账本就是空, 窗口**零**, 第一次说话之后才打开

    ⇒ **新角色零补发**; ⇒ **短暂离开会补上**（那是"她还记着上周那件事"）;
    ⇒ **长期离开不翻旧账**（离场期间的事一件不提, 从现在重新开始）。

    ③ 用 `signature`（年份 —— 见模块 docstring 决定 2）: 说了就不再说, 这就是"恰好一次"。
    """
    today = _as_day(day)
    fired = _fired_of(clock, char_id)
    seen = _last_seen_day(clock)
    # ★ 她还没说过话 → 窗口是**零**, 不是"一年"（见 docstring 特例 2）
    floor = (today - timedelta(days=1)) if seen is None else seen
    if floor > today:                               # 台账写到未来（回拨残留）
        floor = today
    out: list[Occasion] = []
    for o, tgt in occasions_on(today, occasions=occasions, path=path):
        if tgt > today:                         # ① 还没到
            continue
        if o.signature(today) in fired:         # ③ 没说过
            continue
        if tgt < floor:                         # ② 不是考古
            continue
        out.append(o)
    return out


# ---------------------------------------------------------------------------
# 台账 —— 读 / 写 `real_clock.json`
# ---------------------------------------------------------------------------

def new_clock() -> dict:
    """一张空台账。

    ⚠️ **`last_seen_date` 空着, 不是"设为今天"** —— 它必须表示"**她还没有过去**",
    这样 `due_occasions` 的地板才会退化成"只认今天"（新角色零补发）。
    第一版这里写的是 `_as_day(day).isoformat()`, 于是**新档第一天就收到元旦+
    情人节两条祝福** —— 一个"她早就见过老师"的假事实被写进了新账本。
    谁是"说过话"的唯一判定处是 `mark_seen`。
    """
    return {
        "schema_version": CLOCK_SCHEMA_VERSION,
        "last_seen_date": "",
        "rewind_count": 0,
        "fired": {},
    }


def load_clock(world_dir: str | Path) -> dict:
    """读台账（**缺失 / 损坏 → 新建的空台账**, 宁缺勿错, 不抛）。

    ⚠️ 损坏时**不覆盖**磁盘上的文件 —— 只返回空台账; 下次 `save_clock` 才会写。
    这样"手抖改坏了"至少还能人工救回来, 而不是下次启动就被空账覆盖掉。
    """
    p = clock_path(world_dir)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return new_clock()
    if not isinstance(data, dict):
        return new_clock()
    out = new_clock()
    try:
        out["schema_version"] = int(data.get("schema_version")
                                    or CLOCK_SCHEMA_VERSION)
    except (TypeError, ValueError):
        out["schema_version"] = CLOCK_SCHEMA_VERSION      # 坏值 → 当当前版
    ls = data.get("last_seen_date")
    if isinstance(ls, str) and ls.strip():
        out["last_seen_date"] = ls.strip()
    try:
        out["rewind_count"] = max(0, int(data.get("rewind_count") or 0))
    except (TypeError, ValueError):
        out["rewind_count"] = 0
    fired = data.get("fired")
    if isinstance(fired, dict):
        for cid, keys in fired.items():
            if isinstance(keys, dict):
                out["fired"][str(cid)] = {str(k): str(v)
                                          for k, v in keys.items()}
    return out


def save_clock(world_dir: str | Path, clock: dict) -> None:
    """原子写台账（失败只 WARNING —— **绝不阻断对话**）。"""
    p = clock_path(world_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(clock, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(p)
    except OSError as e:
        logger.warning("台账写失败（本轮不记）: %s — %s", p, e)


def _fired_of(clock: dict | None, char_id: str) -> dict:
    """取某角色的已触发表（缺 → 空 dict, 不建）。"""
    if not isinstance(clock, dict):
        return {}
    fired = clock.get("fired")
    if not isinstance(fired, dict):
        return {}
    bucket = fired.get(char_id)
    return bucket if isinstance(bucket, dict) else {}


def _last_seen_day(clock: dict | None) -> date | None:
    """台账里的 `last_seen_date` → `date`（缺 / 坏 → None）。"""
    if not isinstance(clock, dict):
        return None
    v = clock.get("last_seen_date")
    if not (isinstance(v, str) and v.strip()):
        return None
    try:
        return date.fromisoformat(v.strip())
    except ValueError:
        return None


def _minus_one_year(d: date) -> date:
    """`d` 往前一年（`2/29` 而目标年不是闰年 → 落到 `2/28`）。

    ⚠️ **当前没有调用点** —— `due_occasions` 的窗口已简化为"上次跟她说过话那天"
    （见该函数 docstring 的两条特例）。留着是因为"周年"类需求迟早要用它,
    而闰年那一格是那种"不写就必然写错"的地方。
    """
    try:
        return d.replace(year=d.year - 1)
    except ValueError:                      # 2/29 → 去年无此日
        return d.replace(year=d.year - 1, day=28)


def mark_seen(clock: dict, day: object = None) -> dict:
    """记下"她今天见过老师"（同 `mark_fired`, 但不涉及任何节日）。

    `last_seen_date` **只向前**; 退回过去时 `rewind_count += 1`
    （第四面墙接口的落点之一 —— `docs/DESIGN_FOURTH_WALL.md`, 本模块只记账）。

    ⚠️ 它同时是 `due_occasions` 的**考古地板**（闸 ③）: 往后退会让早先"本该
    补发"的日子重新进入窗口。这是**对的** —— 时间都退回去了, 那些日子确实
    "还没发生"。而 `fired` 里的键**不退**, 所以不会重发已经说过的。
    """
    today = _as_day(day)
    prev_d = _last_seen_day(clock)
    if prev_d is None or today > prev_d:
        clock["last_seen_date"] = today.isoformat()
    elif today < prev_d:
        clock["rewind_count"] = int(clock.get("rewind_count") or 0) + 1
        logger.info("台账: 时间回退 %s → %s（rewind_count=%d）",
                    prev_d.isoformat(), today.isoformat(), clock["rewind_count"])
        clock["last_seen_date"] = today.isoformat()
    clock.setdefault("schema_version", CLOCK_SCHEMA_VERSION)
    clock.setdefault("fired", {})
    return clock


def mark_fired(clock: dict, char_id: str, occs: list[Occasion],
               day: object = None) -> list[str]:
    """把 `occs` 记成"已跟她说过" → 返回写下的键（幂等: 重复调用不重复记）。

    签名取 `occ.signature(today)`（现实年 —— 见模块 docstring 决定 2）。
    """
    if not occs:
        return []
    today = _as_day(day)
    fired = clock.setdefault("fired", {})
    bucket = fired.setdefault(char_id, {})
    keys: list[str] = []
    for o in occs:
        sig = o.signature(today)
        if sig in bucket:
            continue
        bucket[sig] = today.isoformat()
        keys.append(sig)
    return keys


# ---------------------------------------------------------------------------
# 引擎入口（MMT 每轮一次）
# ---------------------------------------------------------------------------

def due_notes(char_id: str, world_dir: str | Path, *, now: object = None,
              occasions: list[Occasion] | None = None,
              path: str | Path | None = None) -> list[str]:
    """**MMT 每轮的唯一入口**: 该注的节日注记（并记账）。

    ```
    due_notes(char_id, store.world_dir())
      → 读台账 → 查表 ∩ 今天 ∩ 未点火 → 渲染注记 → 记 fired → 写回台账 → 返回
    ```

    ★ **调用即记账**（不是"返回了才算"）—— 否则 LLM 调用失败会让同一个日子
    下一轮再注一次。节日的注记是**当天一次**的事, 不是每轮都该出现的事。

    ⚠️ **只给 MMT 用**（模块 docstring 边界 1）: VN 不注。

    任何异常 → `[]`（宁缺勿错, **绝不阻断对话**）。
    """
    try:
        clock = load_clock(world_dir)
        occs = due_occasions(char_id, clock, now, occasions=occasions, path=path)
        mark_seen(clock, now)
        mark_fired(clock, char_id, occs, now)
        save_clock(world_dir, clock)
        return [o.note() for o in occs]
    except Exception as e:                       # noqa: BLE001 — 注记绝不阻断
        logger.warning("节日注记失败（本轮不注）: %s", e)
        return []


__all__ = [
    "CLOCK_FILENAME",
    "CLOCK_SCHEMA_VERSION",
    "DEFAULT_TABLE_PATH",
    "TABLE_SCHEMA_VERSION",
    "Occasion",
    "clock_path",
    "default_table_path",
    "due_notes",
    "due_occasions",
    "load_clock",
    "load_occasions",
    "mark_fired",
    "mark_seen",
    "new_clock",
    "occasions_on",
    "save_clock",
]
