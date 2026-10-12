"""creep — **世界线的账**: 引擎/世界的元事实（"这一段没能消化成记忆"…）。

## 它是什么 / 不是什么

| | |
|---|---|
| **是** | 一条**谁都不该读到的账**（append-only, 住在世界线的事件流里） |
| **不是** | 事件（不是"世界里发生的事"）· 节点（不进 `wiki.jsonl`）· 记忆 · 剧情 |
| **靠什么隐身** | ⭐ **它没有 `seq`** —— `Event.from_dict` 的第一道校验就把它挡在外面。**结构性的**, 不靠纪律（详见 `ledger.py`） |

它跟 `real_clock.json` 的 `rewind_count` 同级（都"算不出来"⇒ 都是自家真源）,
但**住在世界线里**（`soul/events.jsonl`, 与记忆同居）而不是世界级文件 —— 见的账跟线走。

## 今天是"只留接口"（2026-09-29 用户裁决）

**已落**：行 + 写 + 严格读 + **第一个写者**（`digest_skip`：digest 试满 3 次放弃一段时）。
以下**都还没做**, 别以为它在跑：
* **让她看见**（`kind` → 存疑文本 → 每轮注记）—— `skeptical.py` 已经有文本池, 但**没有注入口**
* **cval**（世界线的"墙被推开多少"）与**解锁**（OS / 记忆编辑）
* 别的 `kind`（候选见 `ledger.KINDS` 的注释, **只加有写者的**）

## 纪律（改这里之前必读）

1. **账不可重算** ⇒ 写失败**不许静默降级**（wiki 能从事件流重算, 账不能）。
2. **开关只影响读、永不影响写** —— 否则账随配置漂移, 将来的 cval 不可复算。
3. **`type="creep"` 永不进 `EVENT_TYPES`** —— 靠"没有 seq"隐身, 别给它发号。
4. **写入路径唯一** = `SessionStore.append_raw_row()`（拿 `append_event` 那把锁）。
5. **不给归因**：存疑文本只说"有什么不对", 永不说"因为 X"。
"""
from core.creep.ledger import (
    KIND_DIGEST_GAP,
    KIND_DIGEST_SKIP,
    KINDS,
    TYPE_CREEP,
    build,
    make_row,
    read_raw,
    record,
)
from core.creep.skeptical import pick

__all__ = [
    "KIND_DIGEST_GAP",
    "KIND_DIGEST_SKIP",
    "KINDS",
    "TYPE_CREEP",
    "build",
    "make_row",
    "pick",
    "read_raw",
    "record",
]
