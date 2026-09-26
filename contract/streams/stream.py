# -*- coding: utf-8 -*-
"""`contract.streams` 的**增量缓冲**：逐 chunk 喂入，行一完整就解析。

从 `contract.records.parse.BlockStreamParser` 提出骨架（⑥-1）。⭐ 分工
（`DESIGN_STREAM_CONTRACT.md` §10.1 A2）：

    base（本模块）= 缓冲切行 + 逐行解析 + 诊断记账 + `records` 全量 —— **只做行级**
    子类        = **交付单元**（`_accept` 收到一行做什么 / `_flush` 收尾怎么收）

    · VN（`records.BlockStreamParser`）：把行**聚合成板**，板一闭合进 `_ready`
      （`pop_ready()` 返回 `list[tuple[VnRecord, ...]]`）；
    · MMT：**行即交付单元**——`_accept` 直接把那一行放进 `_ready`。

## 纪律

· 本模块**只 import stdlib**；行解析通过构造参数 `parse_row` 注入（`records`
  传的是注入了 VN 判别的 `_parse_line_multi`）；
· `pop_ready()` 的语义 = "取走自上次以来**新交付**的单元"（可多次调用）；
· ⚠️ `records` 是**全量行对象**（诊断/回溯用），与 `_ready`（交付单元）是两回事。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from contract.streams.lines import ParseDiag

#: 行解析器签名: `(raw_line, line_no) -> (行对象列表, 诊断|None)`
ParseRow = Callable[[str, int], "tuple[list[Any], ParseDiag | None]"]


class LineStreamBase:
    """逐 chunk 喂入 → 完整行 → 解析 → 交给子类；**交付单元由子类定义**。

    子类需要实现两个钩子：
        `_accept(item)`  收到一个行对象（自己决定累积还是立刻交付）
        `_flush()`       输入结束时的收尾（把最后一个交付单元闭合）
    """

    def __init__(self, *, parse_row: ParseRow) -> None:
        self._parse_row = parse_row
        self._text_buf = ""                     # 未闭合的行缓冲
        self._ready: list[Any] = []             # 已交付待取（子类往里放）
        self._notes: list[str] = []             # 坏行/修复记账（`[DROP line N] …`）
        self.records: list[Any] = []            # **全量**行对象（诊断/trace）
        self.line_no = 0

    # --- 喂入 --------------------------------------------------------------
    def feed(self, chunk: str) -> None:
        """喂一段文本（可以切在行中间）——完整行即时解析、即时交给子类。"""
        self._text_buf += chunk or ""
        while "\n" in self._text_buf:
            line, self._text_buf = self._text_buf.split("\n", 1)
            self._consume_line(line)

    def finish(self) -> None:
        """流结束: 收残余行 + 交给子类收尾。"""
        if self._text_buf.strip():
            self._consume_line(self._text_buf)
            self._text_buf = ""
        self._flush()

    # --- 产出 --------------------------------------------------------------
    def pop_ready(self) -> list[Any]:
        """取走已交付的单元（可多次调用; 返回自上次以来新交付的）。"""
        out, self._ready = self._ready, []
        return out

    @property
    def notes(self) -> tuple[str, ...]:
        return tuple(self._notes)

    # --- 内部 --------------------------------------------------------------
    def _consume_line(self, raw: str) -> None:
        self.line_no += 1
        items, diag = self._parse_row(raw, self.line_no)
        if diag is not None:
            tag = "DROP" if diag.dropped else "NOTE"
            self._notes.append(f"[{tag} line {diag.line_no}] {diag.error}")
        for item in items:
            self.records.append(item)                    # 全量（与交付单元无关）
            self._accept(item)

    # --- 子类钩子 ----------------------------------------------------------
    def _accept(self, item: Any) -> None:            # pragma: no cover - 抽象
        raise NotImplementedError("子类必须实现 _accept（交付单元的定义在这里）")

    def _flush(self) -> None:                        # pragma: no cover - 抽象
        raise NotImplementedError("子类必须实现 _flush（收尾闭合最后一个交付单元）")
