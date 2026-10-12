"""evolution.py — evolution_log（AGENT_BRAIN.md §2 / M2b）。

审计日志（append-only, 与 wiki.jsonl 整写模式区分——日志就是追加）:
    路径: {char_dir}/evolution.jsonl（wiki.jsonl 同目录）
    条目: {ts, pkg, action, id/ids, changed/detail…}

职责: 记录每次修订（create/update/merge/link/accrue…）的 before/after 与包归属——
审计 + R6 记忆损坏回滚的依据（"这包改了什么"可精确还原）。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from core.session.io import append_jsonl, read_jsonl


class EvolutionLog:
    """修订审计日志（per 世界线, 与 wiki.jsonl 同目录）。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @classmethod
    def for_store(cls, store) -> EvolutionLog:
        """默认位置: wiki.jsonl 同目录下 evolution.jsonl。"""
        return cls(store.path.parent / "evolution.jsonl")

    # ------------------------------------------------------------------
    # 写 / 读
    # ------------------------------------------------------------------

    def append(self, entry: dict[str, Any]) -> None:
        """追加一条（补 ts）。"""
        entry = dict(entry)
        entry.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
        append_jsonl(self.path, entry)

    def read(self) -> list[dict]:
        """全部条目（坏行丢弃, 宁缺勿错）。"""
        return [e for e in read_jsonl(self.path) if isinstance(e, dict)]

    def next_pkg_id(self) -> str:
        """下一个修订包 id（r0001, r0002, …——按现有条目数推导）。"""
        return f"r{len(self.read()) + 1:04d}"
