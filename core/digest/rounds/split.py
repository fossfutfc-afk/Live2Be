"""split.py — ⓪ R0「切分员」: 本段时间线 → **切片骨架 + 账目**（区间 · `abstract` · `state`/`id`/`due`）。

料（表里那五行, `ctx.sections_for` 逐字校对）: 本段新增互动 · **本段的时间** · **日子** ·
**还开着的约定**（带编号 + 期限）· 本章标题。

⭐ **L3（2026-10-05）: 账目的两只手都接上了** ——
· **料**: 没有【本段的时间】她就折算不出"生日那天是哪天", 没有【还开着的约定】她就
  引用不到任何 `id`（`close` / 更正两格全是死的）;
· **资格位**: 名单同时是 `parse_split` 的**闭集**; 超期 ∧ 本段没提到它的那些才允许
  写 `span: null`（"没有那一刻"）—— 引擎**只摆事实, 不替她判**。

⚠️ **画面记忆 / 人设 / 情绪标尺不给它**: 切分是**结构判断**, 不需要人设; 给了反而诱使它
写文学化的 `abstract`（那是 R1 的活）。⚠️ **日期也不给 R1**（正文不走绝对日期）。

写: **段内中间产物** `ctx.result.segments`（`{span, keep, abstract, seqs}` 的列表）——
⛔ 不建节点、不碰图、不写 note。它交出去的是**骨架**, R1 照着它往里面填血肉。

⭐ **它是本段的第一步, 也是唯一能"叫停整段"的一步**: `{"segments": []}` = 这一段
没有值得记的 ⇒ 编排层跳过对着切片的那几轮（收口例外 —— 它吃备忘录, 见 `pipeline`）。
⚠️ 那个判据**不在本文件的 `run()` 里** —— "跳过一整段"要同时决定水位推不推,
那是整段级的账, 归编排（表里这一轮的 `skip` 格也故意留空）。

## ⭐ 3b-1: 这里还住着三件**确定性**的事（从 R1 搬过来）

切分权归 R0 之后, "区间 → 图"就该在**产出点**做（谁决定形状, 谁承担后果）:

1. **`seqs`**: `span` 区间展开成区间内的全部内容 seq（`_expand_spans`）——
   ⚠️ **保留 `span`**: 它是这条切片的身份（R1 照它对位、收口靠它并区间、台账要印它）;
2. **章收口**: 一章切成几件 = **切分违约** ⇒ 当场按章收口（`_collapse_bond_episodes`）,
   并把丢掉那几条的**区间并回**保留那条（收口只该决定"合成几件事", 不该让位置消失）;
3. **覆盖率那本账**: 认领 / 未认领 / 共享 / 章内未覆盖（`_coverage`）—— 可重算, 只进日志。

⚠️ **顺序是正确性**: 展开**必须早于**收口 —— 章的归属靠"seq 与章块**相交**",
展开前只有两个端点, 章块夹在中间时会漏判（守门用例钉住这条）。

⚠️ **它拿走了 R1 从前最重的那件事（划区间）** ⇒ 图的形状（几个节点、每个覆盖哪段）
从此由它一个人决定。所以它的产出必须**可校验**（区间在不在时间线里 —— 契约层的
`parse_split`）且**可观测**（下面那行日志）。
"""
from __future__ import annotations

import logging

from core.digest.material import (
    _ledger_ids,
    _open_pinned_text,
    _overdue_detail,
    _segment_days,
    _segment_time_text,
    _special_days_text,
)
from core.digest.rounds.base import Ctx, RoundOut
from core.digest.segment import _collapse_bond_episodes, _coverage, _expand_spans, _tail_and_holes

logger = logging.getLogger(__name__)


def run(ctx: Ctx) -> RoundOut:
    """⓪ 切 —— 时间线 + 时间/日子/还开着的约定 → 切片骨架（展开 + 章收口都在这里）。"""
    spec = ctx.enter("split")
    # ⭐ **账目那两样（L3, 2026-10-05）** —— 名单只有一份, 两个用途:
    #   ① 印进料（她照着 `id` 写 `close` / 更正）② 当 `parse_split` 的**闭集**白名单。
    # 资格位（`overdue_ids`）只多一条: 超期 ∧ 本段没提到它 ⇒ 才允许写 `span: null`。
    open_pinned = list(ctx.store.notes_state(ctx.events).items)
    days = _segment_days(ctx.by_seq.values())
    today = days[-1] if days else None
    note_ids, overdue_ids = _ledger_ids(ctx.store, open_pinned, seq_set=ctx.seq_set,
                                       timeline=ctx.timeline, today=today)
    system = ctx.system_for(spec, domain=ctx.domain, chapter_count=len(ctx.chapters))
    user = ctx.sections_for(spec, [
        ("本段新增互动", ctx.timeline),
        ("本段的时间", _segment_time_text(days)),
        ("日子", _special_days_text(char_id=getattr(ctx.store, "char_id", ""))),
        ("还开着的约定", _open_pinned_text(open_pinned, now=ctx.now_ts, today=today,
                                          first_day=days[0] if days else None)),
        ("本章标题", " / ".join(c["title"] for c in ctx.chapters if c["title"])),
    ])
    segments, _resp = ctx.call(
        spec, system, user,
        parse_fn=ctx.parse_for(spec, seq_set=ctx.seq_set,
                               note_ids=note_ids, overdue_ids=overdue_ids))
    if segments is None:
        return RoundOut.failed()
    # ⭐ 契约层**当场丢掉的切片数** —— `items.in`（"这一段本来有几件"）要用它:
    # 丢的那几条在 `segments` 里已经不存在了, 但账上的 "in" 说的是**切分员交了几件**。
    # ⚠️ 只数"切片面"的掉（`segments[i]`）—— `verbatim` 那种掉是**同一个切片内部**的,
    # 不算少了一件。
    ctx.result.segment_dropped = sum(1 for d in ctx.result.contract_drops
                                     if d.startswith(f"{spec.key}: segments["))
    # ⭐ 区间 → seq。**早于收口**: 章的归属靠"相交", 展开前只有两个端点
    _unclaimed, _shared = _expand_spans(segments, ctx.seq_set)
    # ⭐ 一章一件（切分违约时的确定性兜底）+ 丢掉那几条的区间并回保留那条
    collapsed: list[dict] = []
    segments = _collapse_bond_episodes(segments, ctx.chapters, dropped_out=collapsed)
    ctx.result.segments = segments
    # ⭐ D1 的**条目面**台账: 章收口丢掉的那几条骨架**只在这一刻存在**
    # （它们的 `abstract` 之后世上没有第二份）。⚠️ 记在**自己的字段**上, 不占
    # `record_gaps` —— 那一格是 record 那一轮交出去的账（表里它的 `result_fields`）,
    # 两个写者会互相覆盖。`record` 跑起来之后把这一半接过去拼成一行完整账。
    ctx.result.segment_collapsed = collapsed
    # ⚠️ 未认领要在**收口之后**重算 —— 章块的区间并回让"章内那几条"从"未认领"变"已认领"
    unclaimed, uncovered = _coverage(segments, ctx.seq_set, ctx.chapters)
    # ⭐ S2（2026-10-06）: 未认领要分**尾部**（会重喂, 合法欠账）与**洞**（不重喂, 真病）——
    # 混在一个数里, 日志就分不出"契约没压住"和"她故意留了没结束的那一截"。
    tail, holes = _tail_and_holes(unclaimed, ctx.seq_set)
    logger.info("digest_split segments=%d open=%d close=%d 无区间=%d 名单=%d 超期=%s "
                "认领=%d 尾部=%d 洞=%d 共享=%d 章内未覆盖=%d 未认领seq=%s",
                len(segments),
                sum(1 for s in segments if s.get("state") == "open"),
                sum(1 for s in segments if s.get("state") == "close"),
                sum(1 for s in segments if s.get("span") is None),
                len(note_ids),
                # ⭐ L9: **超期未决**逐条摆出来（体检账, 不是判决; 用户裁"不进 creep 账"）
                _overdue_detail(open_pinned, overdue_ids, today=today),
                len(ctx.seq_set) - len(unclaimed), len(tail), len(holes), _shared,
                len(uncovered), unclaimed[:20] or "-")
    return RoundOut.done()
