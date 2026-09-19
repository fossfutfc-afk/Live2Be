# -*- coding: utf-8 -*-
"""事件流维护 —— **只剩读侧**（写入侧已于 2026-09-17 随章暂存区 B0 退役）。

## 为什么写入侧没了

旧机制（2026-09-07）: 中断的羁绊段被新章压掉 = **废弃**，靠追加
`vn_abandon {start_seq, end_seq}` marker 宣告"这段**没发生过**"，读侧再过滤掉。

**B0（整章暂存）之后它失去存在理由** —— 章内容在见到 `vn_exit` 之前
**根本不进真源**，所以：

| | 旧 | 新 |
|---|---|---|
| 玩家拒绝 / 从未进入 | 需要 `vn_abandon` 遮断 | **丢掉暂存**（真源里从来没有过） |
| 玩家中途退出 | `vn_abandon`（"没发生过"） | **`vn_exit completed=False`**（发生过但没读完） |

而且旧语义是**素材损失**：玩家确实陪她走完了那半段，那是**有意义的叙事事件**
（她可能失落），`vn_abandon` 把它删掉了。详见 `docs/ESSAY_TIME_MODEL.md §10`
与 `TODO.md`「整章暂存」。

## 本模块现在是什么

**旧档的读侧** —— 真机当前 `vn_abandon` 计数为 **0**（全库扫过），
所以这几个函数实际是空转；保留它们只是为了：**任何仍带 `vn_abandon` 的历史数据
不会被突然放回上下文/记忆**。等确认无此类旧档后可整份删除。

    attempt_spans()      段清单（`chapters.py` 用）
    abandoned_ranges()   废弃区间
    exclude_abandoned()  读侧过滤（digest / momotalk / bond / vn_cli 用）
"""

from __future__ import annotations

from pathlib import Path

from core import paths
from core.session.events import (
    TYPE_BOND,
    M_VN_ABANDON,
    M_VN_ENTER,
    M_VN_EXIT,
)

PROJECT_ROOT = paths.ROOT


# ---------------------------------------------------------------------------
# 段扫描（与 webgui.replay_attempts 同构的纯事件逻辑; 这里补 closing 类型）
# ---------------------------------------------------------------------------

def attempt_spans(events: list) -> list[dict]:
    """事件流 → 羁绊段清单（按 vn_enter 分段; 含关闭状态与场景计数）。

    每段: {enter_seq, close_seq(None=未关), close_kind(None|'exit'|'abandon'),
           completed(bool), title, scenes(int), range_start, range_end}
    close_kind='exit' 时 completed 取 payload; 'abandon'（**旧档专有**）一律废弃。
    """
    spans: list[dict] = []
    cur: dict | None = None

    def close(cur_, kind, seq, completed=False):
        cur_["close_seq"] = seq
        cur_["close_kind"] = kind
        cur_["completed"] = bool(completed) if kind == "exit" else False
        spans.append(cur_)

    for e in events:
        if not e.is_marker:
            if cur is not None:
                cur["range_end"] = e.seq          # 段尾 = 段内最后一条内容事件
                if e.type == TYPE_BOND:
                    cur["scenes"] += 1
            continue
        if e.subtype == M_VN_ENTER:
            if cur is not None:
                spans.append(cur)          # 未关 → 段保持 open（interrupted）
            cur = {"enter_seq": e.seq, "close_seq": None, "close_kind": None,
                   "completed": False, "title": str(e.payload.get("chapter_title") or ""),
                   "scenes": 0, "range_start": e.seq, "range_end": e.seq}
        elif cur is not None:
            if e.subtype == M_VN_EXIT:
                close(cur, "exit", e.seq,
                      bool(e.payload.get("completed")))
                cur = None
            elif e.subtype == M_VN_ABANDON:
                close(cur, "abandon", e.seq)
                cur = None
    if cur is not None:
        spans.append(cur)                  # 流尾未关 → open
    return spans


def abandoned_ranges(events: list) -> list[tuple[int, int]]:
    """已宣告的废弃区间（**旧档专有**; 过滤按 [start, end] 闭区间内 bond 事件）。"""
    out: list[tuple[int, int]] = []
    for e in events:
        if e.is_marker and e.subtype == M_VN_ABANDON:
            try:
                out.append((int(e.payload.get("start_seq", 0)),
                            int(e.payload.get("end_seq", 0))))
            except (TypeError, ValueError):
                continue
    return out


def exclude_abandoned(events: list) -> list:
    """读侧过滤: 丢弃废弃区间内的 **bond 事件**（mmt/对白保留——真实发生过的聊天;
    marker 保留——推导与分段仍需边界; 消费方自行忽略）。无标记 → 原样返回。

    **新数据永远是空转**（B0 之后不再写 `vn_abandon`）—— 只为旧档保留。
    """
    ranges = abandoned_ranges(events)
    if not ranges:
        return list(events)
    out = []
    for e in events:
        if e.type == TYPE_BOND and any(
                a <= e.seq <= b for a, b in ranges):
            continue
        out.append(e)
    return out


__all__ = ["attempt_spans", "abandoned_ranges", "exclude_abandoned"]
