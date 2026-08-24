# -*- coding: utf-8 -*-
"""海马体（hippocampus）— session wiki 读写（Brain 算法的一部分）。

**brain 是算法, 不是跨 session 实体**: 每个 session 是平行世界, 各自独有一个
wiki（sessions/{id}/brain/wiki.json）——由 consolidation 算法从该 session 的
events.jsonl 生成（加载 session 时调算法 → 生成/更新本 session 的 wiki）。
另一个世界线的成长与本 session 无关: 无角色级 wiki、无归并、无迁移。

结构（schema_version 2）:
    {conversation_id, summary, facts[], beliefs[], relations[], updated_at}
    facts[{content, importance, tags}] / beliefs[{content, importance}]
    / relations[{subject, object, relation, note}]

用法:
    from core.brain.hippocampus import WikiStore
    ws = WikiStore()                                    # 默认 data/
    wiki = ws.load("igusa_haruka", sid)                 # 缺失 → 空模板
    ws.save("igusa_haruka", sid, wiki)                  # 原子写
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core.session.io import atomic_write_json
from core.common import err

DEFAULT_DATA_ROOT = Path("data")

SCHEMA_VERSION = 2


def _now_iso() -> str:
    return datetime.now().isoformat()


def _empty_wiki(conversation_id: str) -> dict:
    """session wiki 空模板（首次 digest 前/缺失时）。"""
    return {
        "schema_version": SCHEMA_VERSION,
        "conversation_id": conversation_id,
        "summary": "",
        "facts": [],
        "beliefs": [],
        "relations": [],
        "updated_at": _now_iso(),
    }


class WikiStore:
    """session wiki 存储（海马体）: 单会话读写（平行世界, 无跨 session 概念）。"""

    def __init__(self, data_root: str | Path = DEFAULT_DATA_ROOT):
        self.data_root = Path(data_root)

    # ------------------------------------------------------------------
    # 路径 / 读写
    # ------------------------------------------------------------------

    def wiki_path(self, char_id: str, session_id: str) -> Path:
        return self.data_root / char_id / "sessions" / session_id / "brain" / "wiki.json"

    def load(self, char_id: str, session_id: str) -> dict:
        """读本 session 的 wiki（缺失/坏 json → 空模板, 宁缺勿错）。"""
        try:
            data = json.loads(self.wiki_path(char_id, session_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _empty_wiki(session_id)
        if not isinstance(data, dict):
            return _empty_wiki(session_id)
        return self._fill_defaults(data, session_id)

    def save(self, char_id: str, session_id: str, wiki: dict) -> None:
        """原子写本 session 的 wiki（补默认字段, 防手写遗漏）。"""
        atomic_write_json(self.wiki_path(char_id, session_id),
                          self._fill_defaults(dict(wiki), session_id))

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _fill_defaults(wiki: dict, session_id: str) -> dict:
        for key in ("schema_version", "summary", "facts", "beliefs", "relations"):
            wiki.setdefault(key, SCHEMA_VERSION if key == "schema_version"
                            else "" if key == "summary" else [])
        wiki.setdefault("conversation_id", session_id)
        wiki.setdefault("updated_at", _now_iso())
        return wiki
