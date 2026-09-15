# -*- coding: utf-8 -*-
"""剧情时间游标 —— **唯一真源**（`§4.2` 的 `world_clock.json`）。

```
data/worlds/{world}/world_clock.json
{
  "schema_version": 3,
  "anchor":  {"year": 1, "month": 4},                              // 作者锚点
  "cursor":  {"year":1,"month":4,"week":1,"phase":"晨","sim_day":9}, // 当前时间点
  "updated_at": "…壁钟…"                                            // 审计（③, 不参与任何判定）
}
```

## 三条不变量

- **I6 单调**: `advance` 的结果 `sim_day` **恒 ≥ 输入** —— 由 `story.advance`
  的构造保证（增量 `max(1, …)`），本模块只**断言**不改。
- **`cursor` 只增不减**: 任何"回退"都走 `realtime.rewind_count`（§4.8 第四面墙），
  **绝不动 `cursor`**。这是 story 与 realtime 两条时钟不互相污染的落点。
- **写盘是原子的**: 先写临时文件再替换 —— 半截文件会让游标回退（等于时间倒流）。

## `updated_at` 用壁钟（③）

它**只做审计**（"这个文件什么时候被写的"），不参与 age/渲染/排序的任何判定。
与 `§4.1` 的红线一致: 壁钟只回答"这段是几点跑出来的"。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from core.worldtime.story import (
    DEFAULT_ANCHOR,
    MAX_STEP,
    StoryTime,
    advance,
    parse_story_time,
)

logger = logging.getLogger(__name__)

#: schema 版本（与 §4.2 对齐）
SCHEMA_VERSION = 3


class WorldClock:
    """剧情时间游标（per 世界线）。

    用法::

        clk = WorldClock.load(path, anchor={"year": 1, "month": 4})
        nxt = clk.advance("days:3")      # 推进并**不落盘**
        clk.cursor = nxt                 # 显式赋值
        clk.save()                       # 原子写

    为什么 `advance` 不自动落盘: **写路径的时序是先推进再 stamp 节点**
    （`§4.11`），若推进就落盘, 而 stamp 或 Round B 失败, 游标已经走掉了 ——
    重跑会二次推进。**落盘时机由调用方与节点写入同临界区决定。**
    """

    def __init__(self, path: str | Path, *,
                 anchor: dict | None = None,
                 cursor: StoryTime | None = None) -> None:
        self.path = Path(path)
        self.anchor = dict(anchor or DEFAULT_ANCHOR)
        self.cursor = cursor or StoryTime.from_sim_day(0, anchor=self.anchor)

    # -- 读写 -----------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path, *,
             anchor: dict | None = None) -> "WorldClock":
        """读盘 → 游标。**文件缺失/损坏 → 从锚点起算**（宁缺勿错, 不抛）。

        损坏时**不静默重置已有世界**: 只有当文件真的读不出 `cursor` 时才回锚点,
        并打 WARNING —— 让"时间被重置"在日志里可见, 而不是静默发生。
        """
        p = Path(path)
        if not p.is_file():
            return cls(p, anchor=anchor)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.warning("world_clock 读取失败, 游标回锚点: %s", e)
            return cls(p, anchor=anchor)
        if not isinstance(data, dict):
            logger.warning("world_clock 形态非法, 游标回锚点")
            return cls(p, anchor=anchor)
        a = data.get("anchor") if isinstance(data.get("anchor"), dict) else anchor
        cur = parse_story_time(data.get("cursor"))
        if cur is None:
            logger.warning("world_clock 无可用 cursor, 从锚点起算")
        return cls(p, anchor=a, cursor=cur)

    def save(self) -> bool:
        """**原子**写盘（临时文件 + 替换）。失败 → WARNING 返回 False（不抛）。"""
        payload = {
            "schema_version": SCHEMA_VERSION,
            "anchor": dict(self.anchor),
            "cursor": self.cursor.to_dict(),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            os.replace(tmp, self.path)
            return True
        except OSError as e:
            logger.warning("world_clock 写盘失败: %s", e)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    # -- 推进 -----------------------------------------------------------
    def advance(self, span: str) -> StoryTime:
        """推进并返回**新游标**（不落盘, 见类 docstring）。

        I6: 结果 `sim_day` 恒 ≥ 当前 —— 断言失败即 TypeError（结构性错误,
        宁可炸也不要静默的时间倒流）。
        """
        nxt = advance(self.cursor, span, anchor=self.anchor)
        if nxt.sim_day < self.cursor.sim_day:
            raise AssertionError(
                f"I6 违反: sim_day 回退 {self.cursor.sim_day} → {nxt.sim_day}")
        return nxt

    def advance_and_commit(self, span: str) -> StoryTime:
        """推进 + 落盘（**只在不需要与节点写入同临界区时用**）。

        ⚠️ 写路径请用 `advance()` + 显式 `save()`（见类 docstring 的时序理由）。
        """
        self.cursor = self.advance(span)
        self.save()
        return self.cursor

    # -- 派生 -----------------------------------------------------------
    @property
    def sim_day(self) -> int:
        return self.cursor.sim_day

    def __str__(self) -> str:
        return f"WorldClock({self.cursor})"


def world_clock_path(data_root: str | Path, world_id: str = "world1") -> Path:
    """`data/worlds/{world}/world_clock.json`（布局集中在这里, 不散落调用方）。"""
    return Path(data_root) / "worlds" / world_id / "world_clock.json"


__all__ = ["WorldClock", "world_clock_path", "SCHEMA_VERSION", "MAX_STEP"]
