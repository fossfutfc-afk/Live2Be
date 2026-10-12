"""时间 → 注入注记（`§4.11` 的"进 prompt"落地）—— 纯渲染, 无 IO, 无项目内依赖。

## 两行的分工（**互不参与判定**，见各自的注释）

```
【手机上的日期】2026年9月13日（星期日）        ← ③ 壁钟（**仅 MMT**, 见下）
【她上次见到老师是 12 天前】                  ← ② 现实间隔（模糊）
```

⚠️ **2026-09-17（时间轴换代）: 原来的第①行 `【现在是】1年4月·春·白天` 已删** ——
它读的是作废的**剧情游标**，留着会让两个时间事实并排在同一个 prompt 里
（`ESSAY §5.2` 的坑）。现在两行**同源**（都是壁钟），剧本内的时刻归场景文本。
详见 `story_time_note` 删除处的注释。

## ★ 为什么"手机上的日期"曾经是**虚构年份**（2100）—— 以及为什么删了

用户原裁决（2026-09-13）: *"开门的年份可以定死，定一个 2100 这种时间段，
日月重合，年不给重合；星期几要给。"* —— 即"月/日/星期几照真实、**年份不重合**"。

**2026-09-17 随日历换代删除**（用户裁决 *"既然时间同步了，FICTIONAL_YEAR 还有
必要吗"* → **直接删，就用真实年份**）。理由三条:

1. **它想防的和它实际防的不是一回事**。它防"她嘴里冒出真实年份"，而那是**破墙**
   问题 —— 真正的防线是**归因**（"这是你手机上显示的日期，问起才引用"），
   不是那个数字本身。删掉它，归因那半句照样承重
2. **它没有任何消费方**（全库查过: 只被本模块用来显示, 无一处反解析; 不进
   `det`/`age`/召回）—— 它不是承重墙, 是装饰
3. **⭐ 换代之后它成了"唯一不前进的年份"** —— 现实日期是唯一日期轴, 事件流 `ts`
   是真实年, `real_clock.fired` 的幂等键（`christmas:2026`）也按真实年递增,
   只有她手机永远停在 2100。**同一个角色过了第 N 个圣诞, 而她的日历上
   2100 年只有一个圣诞**。将来生日源进来（"我几岁了"）必然要对两套账

**现在还留着的一条纪律**（从旧设计继承, 与新方案无关）:

**归因不可省** —— 叫"手机上的日期"，不叫"今天是"。MMT 是手机，她回答日期 =
**掏出手机看了一眼**，不是"她知道现实世界"。**给了归因，模型才不会把它当
自己的时间轴**（否则会写出"上次见面是 9 月 1 日"这种破墙句）。

⚠️ 顺带纠正一条我（助手）写错又写进 `realtime.py` 的说法: `2100` 与真实年的
星期几确实差 1 天, 但 `phone_date` **本来就是按那个年份算星期几的** —— 她前后
自洽（"9 月 13 日是星期一"，而 2100-09-13 正是星期一）。所以"将来 `nth_weekday`
必须按虚构年重算"这条**前提不成立**; 删掉虚构年之后更是彻底不成立。

## 为什么 VN 不注"手机日期"

`CLAUDE.md §6.3`: **产品内 VN 没有自由打字通道**——玩家的"话"只经选项说出，
而选项由 LLM 生成 → 问不出"今天几号"。注了只会污染剧情创作。
`phone_date_note()` 由调用方决定要不要用（VN 不用）。
"""
from __future__ import annotations

from datetime import datetime

#: 星期名（`datetime.weekday()`: 0 = 周一）
WEEKDAYS: tuple[str, ...] = ("星期一", "星期二", "星期三", "星期四",
                             "星期五", "星期六", "星期日")


def phone_date(when: datetime | None = None) -> tuple[int, int, int, int, str]:
    """真实时刻 → 手机上的日期 —— **就是真实日期本身**。

    Returns: `(year, month, day, weekday_idx, weekday_name)`。

    ⚠️ **这里原来是 `FICTIONAL_YEAR = 2100`（定死）**, 2026-09-17 随日历换代删除
    （用户裁决）, 理由见模块 docstring。`2/29` 的特殊分支**一并消失** ——
    真实年份本来就是闰年就闰, 不必再平移。
    """
    now = when or datetime.now()
    return (now.year, now.month, now.day, now.weekday(),
            WEEKDAYS[now.weekday()])


#: ⚠️ **`story_time_note()` 已于 2026-09-17 删除**（时间轴换代, `ESSAY §10`）。
#:
#: 它渲染 `【现在是】1年4月·春·白天` —— 读的是**已作废的剧情游标**
#: （`world_clock.json` 的 `cursor`）。留着它会让**两个时间事实并排在同一个
#: prompt 里**（"1年4月·春" + 记忆前缀的"（7 天前）"）—— 正是 `ESSAY §5.2`
#: 记录的那个坑，而且其中一个读的是死数据。
#:
#: 现在进 prompt 的时间事实只剩两个, 且**同源**（都是壁钟）：
#:   ② `real_gap_note`   —— 现实间隔（"她上次见到老师是 12 天前"）
#:   ③ `phone_date_note` —— 现实日期（**仅 MMT**，带"手机上的"归因）
#: 而"**戏内**的时刻"（白天/夜里）由**场景文本**承载 → 标注层反推 → 背景变体。
#: 剧情日历不再以任何形式进 prompt。


def phone_date_note(when: datetime | None = None) -> str:
    """③ 手机日期注记 —— **仅 MMT 用**（见模块 docstring 的 VN 说明）。

    ⚠️ 措辞里必须同时有 **归因**（"手机上的"）与 **使用边界**（"问起才引用"）:
    少了归因 → 模型把它当自己的时间轴; 少了边界 → 它会主动提日期（破墙）。

    ⚠️ **虚构年删掉之后这两半更承重了** —— 原先还有"年份不重合"当第二道保险,
    现在她说的就是 2026, 全靠"这是手机上显示的"把它框在手机里。
    """
    y, m, d, _, wd = phone_date(when)
    return (f"【手机上的日期】{y}年{m}月{d}日（{wd}）"
            "——这是你手机上显示的日期; 玩家问起时才引用它, "
            "平时不要主动提日期、也不要把它写进你记得的事里")


def real_gap_note(last_ts: str | datetime | None,
                  now: datetime | None = None) -> str:
    """② 现实间隔注记 —— `【她上次见到老师是 12 天前】`（空/坏 → `""`）。

    ## 为什么是"间隔"而不是"日期"

    角色不会说"上次是 9 月 1 日"（她没日历）; 她会说"**好久没见到老师了**"。
    这正是"现实世界的模糊映射"——**映射的是间隔, 不是日期**。

    ⚠️ **措辞刻意虚化**（与 `age.render_relative` 同一条 I-c 纪律）:
    "刚刚/今天/N 天前/N 周前/很久". **绝不出现小时/分钟/精确日期**。
    """
    if not last_ts:
        return ""
    try:
        t = (datetime.fromisoformat(last_ts)
             if isinstance(last_ts, str) else last_ts)
    except (TypeError, ValueError):
        return ""
    # ★ 时区对齐（2026-09-17 收敛 `ts` 到带时区后**必做**）
    #   新 `ts` 带固定时区、旧 `ts` 是朴素本地时间，而 `now` 常是裸 `datetime.now()`。
    #   混算会 `TypeError` → 被下面的 except 吃成 `""` → **时间注记整条静默消失**
    #   （真机症状: `【她刚刚还在和老师说话】` 不再出现。测试当场抓到）。
    #   统一走 `age.parse_ts`: **朴素时间一律按 `REAL_TZ` 解释** ——
    #   与 `age_days` / `age.parse_ts` 同一条纪律, 单一真源。
    from core.worldtime.age import REAL_TZ, parse_ts
    t_ok, now_ok = parse_ts(t), (parse_ts(now) if now is not None else None)
    if t_ok is None:
        return ""
    now_ok = now_ok or datetime.now(REAL_TZ)
    mins = (now_ok - t_ok).total_seconds() / 60.0
    if mins < 0:
        return ""
    if mins < 60:
        return "【她刚刚还在和老师说话】"
    if mins < 24 * 60:
        return "【她今天已经和老师说过话了】"
    days = mins / (24 * 60)
    if days < 2:
        return "【她昨天和老师说过话】"
    if days < 7:
        return f"【她上次见到老师是 {int(round(days))} 天前】"
    if days < 30:
        return f"【她上次见到老师是 {int(round(days / 7))} 周前】"
    return "【她已经很久没见到老师了】"


def notes(*, last_ts: str | datetime | None = None,
          now: datetime | None = None, include_phone: bool = False,
          ) -> list[str]:
    """一次取全部时间注记（空行自动跳过）。

    `include_phone=True` → 加"手机上的日期"（**仅 MMT**）。

    2026-09-17（时间轴换代）: **不再接收 `story_now`** —— 剧情时间注记已删
    （理由见 `story_time_note` 删除处）。两个出口现在**同源**（都是壁钟），
    调用方那条纪律不变: `include_phone` 必须跟着 **store 有无**走。
    """
    out = [real_gap_note(last_ts, now)]
    if include_phone:
        out.append(phone_date_note(now))
    return [n for n in out if n]
