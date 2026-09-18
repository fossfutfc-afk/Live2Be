# -*- coding: utf-8 -*-
"""章暂存区 —— 「**章内的一切先进暂存，见到 `vn_exit` 才整段 append 进真源**」。

## 为什么（用户 2026-09-17 立项）

缓存架构的真正优势是「**删除**」变成「**丢弃**」：

| | 直接落真源 | 暂存 |
|---|---|---|
| 让一段内容"不进上下文" | **需要删除/遮断操作** —— `vn_abandon` 标记 + **每条读路径都得记得** `exclude_abandoned`。漏一处就污染，而且**遮断标记自己也进了真源** | **丢掉即可** —— 它从来没进过真源，**没有任何地方需要"记得过滤"** |

**三种结局，两种提交：**

```
章内（暂存 —— 什么都不进真源）
  ├─ 拒绝 / 从未进入   →  丢缓存                   →【从未发生】      ← 零删除操作
  ├─ 中途退出          →  vn_exit completed=False  →【发生过，但没读完】
  └─ 正常读完          →  vn_exit completed=True   →【完整发生过】
```

⇒ **`vn_abandon` 那一族（`exclude_abandoned` / `maintenance.heal` / `supersede` /
`abandon_open_attempts`）存在的唯一理由 = "真源里有未闭合的段"。**
暂存之后未闭合的段只存在于暂存里 → 那一族可以整个退休（B2）。

## 形态

```
data/worlds/{world}/characters/{char}/soul/events.jsonl            ← 真源（只有闭合的章）
data/worlds/{world}/characters/{char}/soul/staging/events.jsonl    ← 暂存（章内）
```

**同名同形**于真源，且 `StagingStore` **继承** `SessionStore`：

| 方法 | 行为 |
|---|---|
| `events()` | **真源 + 暂存**（合并；暂存 seq **接续真源** → 天然有序） |
| `append_event()` / `append_marker()` | 写**暂存**，`seq = max(真源, 暂存) + 1` |
| 其余（`meta` / `resume` / 路径 …） | 与 `SessionStore` 相同（`resume` 自然拿到合并视图 ✓） |

⇒ **章外（暂存空）逐字节等价于真源** —— 所以调用方可以**无条件**用它，
不需要判断"章在不在进行中"，也就不会有"漏改一个读点"的幽灵。

## ★ 不变量（commit 的原子性由它兜底，而不是靠事务）

> **真源里任何时刻都不留未闭合的段。**

`commit_staging` 逐条 append，**不追求原子性** —— 中途失败就留半截。但那半截
**语义正确**（玩家确实读过那几块），而暂存**保留**（可重试）；不变量由
**下一次 commit 的第 ① 步** `close_open_attempts()` 维护。

## 与既有旁路的关系

`soul/prewarm.json`（跨重启首场缓存）与 `soul/bond_draft.json`（待发板队列）
原本是**性能优化**；本模块把它们升格为**架构**的一部分 —— 职责变了，不是新发明。
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from core.session.events import (
    M_SESSION_END,
    M_VN_ABANDON,
    M_VN_ENTER,
    M_VN_EXIT,
    Event,
    make_event,
    parse_events,
)
from core.session.io import append_jsonl, read_jsonl
from core.session.store import _GLOBAL_APPEND_LOCK, SessionStore

logger = logging.getLogger(__name__)

#: 暂存目录名（挂在 `soul/` 下，与真源同层）
STAGING_DIRNAME = "staging"
#: 暂存文件名（**与真源同名** —— 便于整段搬迁时逐条 append）
STAGING_FILENAME = "events.jsonl"

#: 视为"段已闭合"的 marker（`_pending_in_vn` 与 `renderer.session_status` 同源）
_CLOSERS = (M_VN_EXIT, M_VN_ABANDON, M_SESSION_END)


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

def source_events_path(store: SessionStore, char_id: str) -> Path:
    """**真源** `events.jsonl` 路径 —— 即使 `store` 本身是 `StagingStore` 也返回真源。

    直接调基类实现（不走 `store.events_path`）—— 否则 `StagingStore` 会递归。
    """
    return SessionStore.events_path(store, char_id, "")


def staging_path(store: SessionStore, char_id: str) -> Path:
    """暂存文件路径 —— 由**真源路径**派生（布局只在 `events_path` 定义一处）。"""
    return (source_events_path(store, char_id).parent
            / STAGING_DIRNAME / STAGING_FILENAME)


def _read_safe(p: Path) -> list:
    """读 jsonl —— 缺文件/坏文件 → `[]`（宁缺勿错）。"""
    try:
        return read_jsonl(p)
    except Exception as e:                       # noqa: BLE001 — 读失败按空
        logger.warning("事件流读取失败（按空处理）: %s", e)
        return []


class StagingStore(SessionStore):
    """**章内的统一读写口** —— 读 = 真源 + 暂存；写 = **暂存**。

    | 方法 | 行为 |
    |---|---|
    | `events()` | **真源 + 暂存**（合并；暂存 seq 接续真源 → **天然有序**） |
    | `append_event()` | 写**暂存**，seq = `max(真源, 暂存) + 1` |
    | 其余（`meta` / 路径 / `resume` …） | 与 `SessionStore` 相同（`resume` 自然拿到合并视图 ✓） |

    ## ★ 为什么 seq 要**接续真源**，而不是从 1 数

    章内若形成两个**独立** seq 空间，那么任何"合并两者"的读点
    （恢复窗口 `window_messages` / 回放分段 / `_pending_in_vn` / `_open_vn_seq`）
    都会撞号 → 排序歧义。**接续之后，「真源 + 暂存」就是一个连续 seq 空间。**

    ## ★ 章外逐字节等价于真源

    暂存为空时 `events()` ≡ 真源 —— 所以调用方**永远不需要判断"章在不在进行中"**，
    直接无条件用本 store 即可。

    ⚠️ **`commit_staging()` 必须传真源 store**（本类的 `append_event` 会写回暂存）。
    它内部自建真源 store，与传入什么无关 —— 见 `_truth_store()`。
    """

    def events_path(self, char_id: str, session_id: str = "") -> Path:
        return staging_path(self, char_id)

    def events(self, char_id: str, session_id: str = "") -> list[Event]:
        """**真源 + 暂存**（有序：暂存 seq 接续真源）。"""
        return (parse_events(_read_safe(source_events_path(self, char_id)))
                + parse_events(_read_safe(self.events_path(char_id, session_id))))

    def append_event(self, char_id: str, session_id: str = "",
                     event: Event | None = None, **kwargs) -> Event:
        """append 到**暂存**；`seq` **接续真源**（见类 docstring）。

        持**同一个进程级写锁**（`_GLOBAL_APPEND_LOCK`）—— 与 `SessionStore.append_event`
        同源，故生图线程等异步写者与主线程天然串行。
        ⚠️ 锁**不可重入**，故这里一次性完成，**不嵌套** `SessionStore.append_event`。
        """
        if event is None:
            event = make_event(kwargs.pop("type", "mmt"),
                               kwargs.pop("subtype", "mmt_chat"),
                               kwargs.pop("payload", {}))
        with _GLOBAL_APPEND_LOCK:
            truth_max = max((e.seq for e in parse_events(
                _read_safe(source_events_path(self, char_id)))), default=0)
            staged = parse_events(_read_safe(self.events_path(char_id, session_id)))
            seq = max(truth_max, max((e.seq for e in staged), default=0)) + 1
            ev = Event(seq=seq, ts=event.ts or datetime.now().isoformat(),
                       type=event.type, subtype=event.subtype,
                       payload=dict(event.payload))
            p = self.events_path(char_id, session_id)
            p.parent.mkdir(parents=True, exist_ok=True)
            append_jsonl(p, ev.to_dict())
        return ev


def staging_store(store: SessionStore) -> StagingStore:
    """按已有 store 的 `data_root` / `world_id` 造一个暂存 store（**无状态, 可重复造**）。"""
    return StagingStore(store.data_root, world_id=store.world_id)


# ---------------------------------------------------------------------------
# 读
# ---------------------------------------------------------------------------

def staging_events(store: SessionStore, char_id: str,
                   session_id: str = "") -> list[Event]:
    """**只**读暂存文件（**不含真源**）—— 无文件 / 读失败 → `[]`。

    ⚠️ 不能用 `StagingStore.events()`：那是"真源 + 暂存"的**合并视图**；
    此处要的是暂存**自己**装了什么（commit 要搬的就是这些）。
    """
    return parse_events(_read_safe(staging_path(store, char_id)))


def truth_store(store: SessionStore) -> SessionStore:
    """**真源** store —— 无论传入的是不是 overlay, 都返回写/读真源的那个。

    `commit_staging` 必须用它: `StagingStore.append_event` 会写回暂存（死循环）。
    """
    return SessionStore(store.data_root, world_id=store.world_id)


def open_attempt(events: list[Event]) -> Event | None:
    """最后一个**未闭合**的 `vn_enter`（`None` = 所有段都已闭合）。"""
    open_e: Event | None = None
    for e in events:
        if getattr(e, "type", None) != "marker":
            continue
        sub = getattr(e, "subtype", "")
        if sub == M_VN_ENTER:
            open_e = e
        elif sub in _CLOSERS:
            open_e = None
    return open_e


def staging_open(store: SessionStore, char_id: str, session_id: str = "") -> bool:
    """暂存里是否有一个**未闭合**的章（= 章正在进行中）。"""
    return open_attempt(staging_events(store, char_id, session_id)) is not None


# ---------------------------------------------------------------------------
# 写 / 提交 / 丢弃
# ---------------------------------------------------------------------------

def close_open_attempts(store: SessionStore, char_id: str,
                        session_id: str = "") -> int:
    """给**真源**里未闭合的段补一条 `vn_exit completed=False`（不变量维护）。

    **为什么需要它**：`commit_staging` 不追求原子性，中途失败会留半截。
    那半截语义正确（玩家确实读过那几块），而"真源里不留未闭合段"这条不变量
    由**每次 commit 之前的这一步**维护 —— 这比事务便宜，也不会丢内容。

    Returns: 补了几条（`0` = 无未闭合段, 幂等）。
    """
    try:
        evs = store.events(char_id, session_id)
    except Exception as e:                       # noqa: BLE001 — 维护失败不阻断
        logger.warning("真源读取失败（跳过收尾）: %s", e)
        return 0
    if open_attempt(evs) is None:
        return 0
    store.append_marker(char_id, session_id, M_VN_EXIT,
                        {"completed": False, "reason": "staging:superseded"})
    logger.info("收尾真源未闭合段: char=%s（completed=False）", char_id)
    return 1


def commit_staging(store: SessionStore, char_id: str, session_id: str = "",
                   *, completed: bool = True) -> int:
    """把暂存**整段**搬进真源，成功则删暂存。

    顺序**不能换**：

        ① `close_open_attempts(真源)`  —— **有条件**（见下）: 先收尾真源里的旧未闭合段
        ② 逐条 append 暂存事件          —— **`seq` 由真源重算**（暂存里的是局部号），
                                          而 **`ts` 原样保留**（它是 digest 定段日期的输入）
        ③ 删暂存                        —— 「删除」在这里就等于「丢弃」

    ## ⚠️ ① 是有条件的 —— 这条规则同时守住「不变量」与「本章语义」

    `close_open_attempts` **只在暂存自带 `vn_enter` 时才跑**：

    | 暂存内容 | 真源里那个未闭合段是谁 | 该不该收尾 |
    |---|---|---|
    | 自带 `vn_enter`（整章） | 必然是**旧的**（我们正在开新的一段） | ✅ 收尾它 |
    | 不带 `vn_enter`（过渡期：暂存只装本章的尾巴） | **就是本章本身** | ❌ 收尾它 = 把本章误判成"没读完"，且真源里会冒出**两个 `vn_exit`** |

    **不追求原子性**：②中途失败 → 真源留半截（语义正确），暂存**保留**（可重试）。

    `completed` 只用于日志与调用方语义（真正的 `vn_exit` 是暂存里那条，
    由 `bond_finish` 写入）—— 见 `docs/ESSAY_TIME_MODEL.md §10`。

    Returns: 搬过去的条数（`0` = 暂存为空, 无副作用）。
    """
    staged = staging_events(store, char_id, session_id)
    if not staged:
        return 0
    truth = truth_store(store)                   # ★ 必须写真源（overlay 会写回暂存）
    if any(e.type == "marker" and e.subtype == M_VN_ENTER for e in staged):
        close_open_attempts(truth, char_id, session_id)
    n = 0
    for e in staged:
        truth.append_event(char_id, session_id, event=e)
        n += 1
    discard_staging(store, char_id)
    logger.info("章暂存提交: char=%s n=%d completed=%s", char_id, n, completed)
    return n


def discard_staging(store: SessionStore, char_id: str) -> bool:
    """**丢**暂存 —— 这就是"删除"的全部：没有 marker、没有区间、没有需要记得过滤的地方。"""
    p = staging_path(store, char_id)
    try:
        p.unlink(missing_ok=True)
        return True
    except OSError as e:                         # noqa: BLE001 — 丢弃失败不阻断
        logger.warning("暂存丢弃失败: %s", e)
        return False


__all__ = [
    "STAGING_DIRNAME",
    "STAGING_FILENAME",
    "StagingStore",
    "commit_staging",
    "close_open_attempts",
    "discard_staging",
    "open_attempt",
    "source_events_path",
    "staging_events",
    "staging_open",
    "staging_path",
    "staging_store",
    "truth_store",
]
