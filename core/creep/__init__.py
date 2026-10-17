"""creep — 世界线的账: 引擎/世界的元事实（"这一段没能消化成记忆"…）。

账是 append-only 的一行, 住在世界线的事件流里（`soul/events.jsonl`）, 但**谁也读不到**:
账行没有 `seq`, `Event.from_dict` 的第一道校验就把它挡在外面 —— 隐身是结构性的, 不靠纪律。
所以它既不是事件、也不是节点: 不进上下文窗口, 不进 `wiki.jsonl`, 不进记忆。
它和 `real_clock.json` 的 `rewind_count` 同级（都算不出来 ⇒ 都是自家真源）, 区别是账跟线走。

现状: 行 + 写 + 严格读 + 第一个写者（`digest_skip`）已落; "让她看见"（`kind` → 存疑文本 →
每轮注记）、`cval`、解锁、别的 kind 都还没做 —— `skeptical.py` 的文本池有了, 但没有注入口。

纪律（改这里之前必读）:
1. 账不可重算 ⇒ 写失败**不许静默降级**（wiki 能从事件流重算, 账不能）。
2. 开关只影响读、永不影响写, 否则账随配置漂移, 将来的 cval 不可复算。
3. `type="creep"` **永不进 `EVENT_TYPES`** —— 靠"没有 seq"隐身, 别给它发号。
4. 写入路径唯一 = `SessionStore.append_raw_row()`（拿 `append_event` 那把锁）。
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
    "KINDS",
    "KIND_DIGEST_GAP",
    "KIND_DIGEST_SKIP",
    "TYPE_CREEP",
    "build",
    "make_row",
    "pick",
    "read_raw",
    "record",
]
