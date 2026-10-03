# -*- coding: utf-8 -*-
"""ledger.py — **creep 账**: 行形状 + 写 + 严格读（`core/creep` 的真源）。

## 这一行是什么

`events.jsonl` 里**一行没有 `seq`、不属于 `Event` 的 JSON** —— 记的是**引擎/世界的元事实**
（"这一段没能消化成记忆"），**不是剧情**。它住在世界线的事件流里，但**谁也读不到它**：

| 读侧 | 为什么看不见 |
|---|---|
| `parse_events` / `store.events()` | `Event.from_dict` 的**第一道**校验是 `seq ≥ 1`（本行没有 seq） |
| 上下文窗口 / digest 时间线 | 只吃 `Event`（上一行）|
| 回放 / 认章 / 状态推导 | 同上 |
| `append_event` 的发号 | 用 `max(解析出的 seq)`，本行不参与 ⇒ **不影响后续事件的 seq** |

⚠️ 这是**结构性**的隐身（不是"别忘了加白名单"那种纪律）: 哪天有人把 `type="creep"`
加进 `EVENT_TYPES`, 它**照样**进不来 —— seq 那一关先挡下了。

## 为什么不做成事件类型 / 不做成节点（2026-09-29 裁决）

* **不是事件类型**: 事件是"世界里发生的事"; 这是**世界的账**。而且一旦进白名单,
  历史账会一次性"活过来"灌进 digest 与她的记忆。
* **不是节点**（不进 `wiki.jsonl`）: 一进图就要被召回 / 注入 / 归属 / L2 分群全套消费;
  而且那是**引擎在编造她的内心**。§3.1 的两问判据也把它判给"痕迹" ⇒ 台账, 不是 kind。
* 与它同级、同样"自家真源"的先例 = `data/worlds/{world}/real_clock.json` 的 `rewind_count`
  （回退次数也不在事件流里, 也算不出来）。

## 纪律

1. **账不可重算**（wiki 失败能从事件流重算, 账不能）⇒ **写失败不许静默降级**。
2. **开关只影响读、永不影响写** —— 否则账随配置漂移, 将来的 cval 不可复算。
3. **读侧严格**: 别人的解析器宽容丢是我们要的; **自己的**宽容丢是危险的
   （写歪一个 kind 会永远查不出来）⇒ 坏行一律 `logger.warning` + 从 `bad_out` 出去。
4. **写入路径唯一** = `SessionStore.append_raw_row()`（拿现成那把锁）——
   本模块**不自己碰文件**, 锁与"无 seq"约定都只有一处。
"""
from __future__ import annotations

import logging
from typing import Any

from core.session.io import read_jsonl

logger = logging.getLogger(__name__)

#: 行类型 —— ⚠️ **永不进 `EVENT_TYPES`**（见模块 docstring: 它靠"没有 seq"隐身）
TYPE_CREEP = "creep"

#: ⭐ 账的类别词表。**只加有写者的**（今天的写者 = 刀 2 放弃那一刻）。
#: 候选（未实现, 别提前加）: `time_rewind`（回退, `real_clock.rewind_count` 已有信号）·
#: `node_overwrite`（`evolution.jsonl` 的 `changed` 已有证据）· `dangling_ref`（`noticed` 落空）。
KIND_DIGEST_SKIP = "digest_skip"
KINDS: tuple[str, ...] = (KIND_DIGEST_SKIP,)

#: 行里必须有的键（`read_raw` 按它判"坏行"）
_REQUIRED = ("ts", "type", "kind")


def make_row(kind: str, *, at_seq: int, skeptical: str = "",
             evidence: dict | None = None, ts: str = "") -> dict:
    """行形状的**唯一实现**（别在调用点手拼 dict）。

    Args:
        kind: `KINDS` 里的值（不在词表 → 照样写, 但读侧会记一条坏行）
        at_seq: ⭐ **事件流的坐标**（引用, **不占号**）—— "这事发生在她经历的第几段之后"。
            digest 侧给水位 / 交互上界; 拿不到给 `0`（读侧认它 = 无坐标）。
        skeptical: `skeptical.pick(kind)` 的产物, **写时冻结**
        evidence: 引擎账（区间 / 次数 / 错误…）—— 🚫 **永不进 LLM**
        ts: 写的时刻（空 → `age.now_ts()`, 与事件同一个时钟）
    """
    from core.worldtime.age import now_ts
    row: dict[str, Any] = {
        "ts": (ts or "").strip() or now_ts(),
        "type": TYPE_CREEP,
        "kind": str(kind or "").strip(),
    }
    try:
        at = int(at_seq)
    except (TypeError, ValueError):
        at = 0
    if at > 0:
        row["at_seq"] = at
    if skeptical:
        row["skeptical"] = skeptical
    if evidence:
        row["evidence"] = dict(evidence)
    return row


def build(kind: str, *, at_seq: int = 0, evidence: dict | None = None,
          rng: Any = None) -> dict:
    """造一行账（**含写时取一的那句存疑文本**）—— **不落盘**。

    ⭐ 为什么要有它（而不是只有 `record`）: digest 那一侧**拿不到事件流**
    （`digest_segment` 只有 `WikiStore2`, 事件流归调用方管）⇒ 它只能把**造好的行**
    交出去（`DigestResult.creep_rows`）, 由调用方 append。两条路共用本函数 ⇒
    "取哪一句"仍然只有一处实现。
    """
    from core.creep.skeptical import pick
    return make_row(kind, at_seq=at_seq, skeptical=pick(kind, rng=rng),
                    evidence=evidence)


def record(store, char_id: str, *, session_id: str = "", kind: str, at_seq: int = 0,
           evidence: dict | None = None, rng: Any = None) -> dict:
    """记一笔账（**写入路径的唯一入口**）—— 返回写下去的那一行。

    ⚠️ **写失败会抛**（不吞）: 账是"不可重算"的那一半, 静默降级 = 无声地丢掉事实。
    调用方若在关键路径上, 自己决定要不要 try（但**别在 `record` 里吞**）。
    """
    row = build(kind, at_seq=at_seq, evidence=evidence, rng=rng)
    store.append_raw_row(char_id, session_id, row)
    return row


def read_raw(store, char_id: str, *, session_id: str = "",
             bad_out: list[str] | None = None) -> list[dict]:
    """读回本世界线的全部 creep 账（**严格**: 坏行要响, 不静默丢）。

    Args:
        bad_out: 可选传出参数 —— 坏行说明（同 `parse_round_a` 的 `on_mind_out` 手法:
            不改返回签名, 老调用方零改动）。坏行**一律**另打一条 `logger.warning`。

    Returns:
        `[{ts, type, kind, at_seq?, skeptical?, evidence?}, …]`（**文件序** = 写入序）
    """
    out: list[dict] = []
    bad: list[str] = []
    try:
        rows = read_jsonl(store.events_path(char_id, session_id))
    except OSError as e:                      # 文件不存在/读不了 ⇒ 没有账（不是坏行）
        logger.debug("creep 账读取失败（当空）: %s", e)
        return out
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or row.get("type") != TYPE_CREEP:
            continue                          # 不是本模块的行（正常事件 / 别的账）
        missing = [k for k in _REQUIRED if not str(row.get(k) or "").strip()]
        if missing:
            bad.append(f"第 {i} 行: 缺 {'/'.join(missing)}")
            continue
        if str(row.get("kind")) not in KINDS:
            bad.append(f"第 {i} 行: kind {row.get('kind')!r} 不在词表里"
                       f"（{'/'.join(KINDS)}）—— 行收下, 但这行是写的代码有问题")
        out.append(dict(row))
    if bad:
        for b in bad:
            logger.warning("creep 账有坏行: %s", b)
        if bad_out is not None:
            bad_out.extend(bad)
    return out
