# -*- coding: utf-8 -*-
"""海马体（hippocampus）— 记忆存储层（Brain 模块, DESIGN_BRAIN.md §3/§4）。

对应脑科学: 海马体是情景记忆（episodic memory）形成与存储的核心脑区——
本文件就是"角色记忆的存储区": LLM WIKI 双层级（会话级 + 角色级）的读写、
归并、哈希校验。与 events.jsonl（episodic 真源）的关系: wiki 是**派生视图**
（可删可重算, 原子写; 唯一真源仍是事件流）。

结构（schema_version 2）:
    会话级  data/{char}/sessions/{sid}/brain/wiki.json  本对话消化产物
    角色级  data/{char}/brain/wiki.json                 跨会话汇总 + character_hash/self_hash

条目:
    facts[{content, importance, tags}]   关键事件/约定（角色会记住的）
    beliefs[{content, importance}]       抽象信念（改变行为的关键层; 矛盾保留）
    relations[{subject, object, relation, note}]  关系变化（去重取最近）

哈希（DESIGN_BRAIN.md §1.3）:
    character_hash  — 五层卡内容哈希（变更检测: 人设被改 → 记忆迁移）
    self_hash       — 本 wiki 文件自身哈希（篡改检测: 手动改 wiki → 视为记忆被外部植入）

用法:
    from core.brain.hippocampus import WikiStore
    ws = WikiStore()                                   # 默认 data/
    wiki = ws.load_char_wiki("igusa_haruka")           # 缺失 → 空模板
    ws.save_session_wiki("igusa_haruka", sid, session_wiki)
    merged = ws.merge_char_wiki("igusa_haruka", session_wiki)   # 归并（不落盘, 调用方决定）
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from core.common import err
from core.session.io import atomic_write_json

DEFAULT_DATA_ROOT = Path("data")

SCHEMA_VERSION = 2

#: 五层卡文件名（哈希/副本用, 存在的才算）
CARD_FILES = (
    "profile.yml",
    "personality.yml",
    "knowledge.yml",
    "experience.yml",
    "typical.yml",
)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _empty_session_wiki(conversation_id: str, character_hash: str = "") -> dict:
    """会话级 wiki 空模板（首次 digest 前/缺失时）。"""
    return {
        "schema_version": SCHEMA_VERSION,
        "conversation_id": conversation_id,
        "character_hash": character_hash,
        "summary": "",
        "facts": [],
        "beliefs": [],
        "relations": [],
        "updated_at": _now_iso(),
    }


def _empty_char_wiki(character_id: str, character_hash: str = "") -> dict:
    """角色级 wiki 空模板（首次 digest 前/缺失时）。"""
    return {
        "schema_version": SCHEMA_VERSION,
        "character_id": character_id,
        "character_hash": character_hash,
        "self_hash": "",
        "summary": "",
        "facts": [],
        "beliefs": [],
        "relations": [],
        "digested_through_ts": None,
        "updated_at": _now_iso(),
    }


def compute_character_hash(files: list[str | Path]) -> str:
    """五层卡内容哈希（变更检测基准, DESIGN_BRAIN.md §1.3）。

    存在的文件按名排序拼接内容（缺失文件跳过——角色可只配部分层）;
    返回 12 位 sha1 前缀。任何文件变更 → 哈希变化。
    """
    h = hashlib.sha1()
    for p in sorted(Path(f) for f in files):
        if p.is_file():
            h.update(p.name.encode("utf-8"))
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


def _entry_key(e: dict) -> str:
    """条目去重键（facts/beliefs: content; relations 用 (subject, object, relation)）。"""
    return e.get("content", "")


class WikiStore:
    """LLM WIKI 存储（海马体）: 双层级读写 + 归并 + 哈希校验。路径参数化 data_root。"""

    def __init__(self, data_root: str | Path = DEFAULT_DATA_ROOT):
        self.data_root = Path(data_root)

    # ------------------------------------------------------------------
    # 路径
    # ------------------------------------------------------------------

    def session_wiki_path(self, char_id: str, session_id: str) -> Path:
        return self.data_root / char_id / "sessions" / session_id / "brain" / "wiki.json"

    def char_wiki_path(self, char_id: str) -> Path:
        return self.data_root / char_id / "brain" / "wiki.json"

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------

    def load_session_wiki(self, char_id: str, session_id: str) -> dict:
        """读会话级 wiki（缺失/坏 json → 空模板, 宁缺勿错）。"""
        wiki = self._read_json(self.session_wiki_path(char_id, session_id))
        if not wiki:
            return _empty_session_wiki(session_id)
        return self._fill_session_defaults(wiki, session_id)

    def load_char_wiki(self, char_id: str) -> dict:
        """读角色级 wiki（缺失/坏 json → 空模板）。

        返回带 `memory_tampered` 标记（self_hash 校验失败 = 文件被外部改过——
        RP 演出/迁移触发用, DESIGN_BRAIN.md §1.3）。
        """
        wiki = self._read_json(self.char_wiki_path(char_id))
        if not wiki:
            return _empty_char_wiki(char_id)
        base = {k: v for k, v in wiki.items() if k != "self_hash"}
        stored = wiki.get("self_hash", "")
        wiki["memory_tampered"] = bool(stored) and self._content_hash(base) != stored
        return wiki

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------

    def save_session_wiki(self, char_id: str, session_id: str, wiki: dict) -> None:
        """原子写会话级 wiki（补 conversation_id/schema 默认, 防手写遗漏）。"""
        wiki = self._fill_session_defaults(dict(wiki), session_id)
        atomic_write_json(self.session_wiki_path(char_id, session_id), wiki)

    def save_char_wiki(self, char_id: str, wiki: dict) -> None:
        """原子写角色级 wiki（写前重算 self_hash——篡改检测基准）。"""
        wiki = self._fill_char_defaults(dict(wiki), char_id)
        wiki["self_hash"] = self._content_hash({k: v for k, v in wiki.items() if k != "self_hash"})
        atomic_write_json(self.char_wiki_path(char_id), wiki)

    # ------------------------------------------------------------------
    # 归并（会话级 → 角色级; 不落盘, 调用方决定是否 save）
    # ------------------------------------------------------------------

    def merge_char_wiki(self, char_id: str, session_wiki: dict) -> dict:
        """会话级 wiki 归并进角色级（DESIGN_BRAIN.md §3 层级 2 规则）:

        facts/beliefs: 同 content 去重, importance 取 max, tags union;
        relations: (subject,object,relation) 去重, note 取最近（新覆盖旧）;
        summary: 最新会话的 summary 覆盖（主线更新）;
        character_hash: 取会话级（= 本次 digest 的副本哈希）;
        digested_through_ts: 前移为会话结束时间（updated_at）。
        """
        char_wiki = self.load_char_wiki(char_id)
        char_wiki["facts"] = self._merge_by_content(
            char_wiki.get("facts", []), session_wiki.get("facts", []))
        char_wiki["beliefs"] = self._merge_by_content(
            char_wiki.get("beliefs", []), session_wiki.get("beliefs", []))
        char_wiki["relations"] = self._merge_relations(
            char_wiki.get("relations", []), session_wiki.get("relations", []))

        summary = session_wiki.get("summary", "")
        if isinstance(summary, str) and summary.strip():
            char_wiki["summary"] = summary
        char_hash = session_wiki.get("character_hash", "")
        if isinstance(char_hash, str) and char_hash:
            char_wiki["character_hash"] = char_hash
        ts = session_wiki.get("updated_at", "")
        if isinstance(ts, str) and ts:
            char_wiki["digested_through_ts"] = ts
        char_wiki["updated_at"] = _now_iso()
        return char_wiki

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_by_content(existing: list, new: list) -> list:
        """facts/beliefs 归并: content 精确去重, importance 取 max, tags union。"""
        by_content: dict[str, dict] = {}
        for e in list(existing) + list(new):
            if not isinstance(e, dict):
                continue
            content = e.get("content", "")
            if not isinstance(content, str) or not content:
                continue
            cur = by_content.get(content)
            if cur is None:
                by_content[content] = dict(e)
            else:
                cur["importance"] = max(
                    float(cur.get("importance", 0) or 0), float(e.get("importance", 0) or 0))
                tags = set(cur.get("tags", []) or []) | set(e.get("tags", []) or [])
                if tags:
                    cur["tags"] = sorted(t for t in tags if isinstance(t, str))
        return list(by_content.values())

    @staticmethod
    def _merge_relations(existing: list, new: list) -> list:
        """relations 归并: (subject,object,relation) 去重, note 取新（后者覆盖）。"""
        by_key: dict[tuple, dict] = {}
        for r in list(existing) + list(new):
            if not isinstance(r, dict):
                continue
            key = (r.get("subject", ""), r.get("object", ""), r.get("relation", ""))
            if not any(key):
                continue
            by_key[key] = dict(r)           # 后者（新会话）覆盖 note
        return list(by_key.values())

    @staticmethod
    def _content_hash(wiki: dict) -> str:
        """wiki 内容哈希（self_hash 用: 排除自身字段后规范化序列化）。"""
        d = json.dumps(wiki, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha1(d).hexdigest()[:12]

    def _read_json(self, path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    @staticmethod
    def _fill_session_defaults(wiki: dict, session_id: str) -> dict:
        for key in ("schema_version", "character_hash", "summary",
                    "facts", "beliefs", "relations"):
            wiki.setdefault(key, (SCHEMA_VERSION if key == "schema_version"
                                  else "" if key in ("character_hash", "summary")
                                  else []))
        wiki.setdefault("conversation_id", session_id)
        wiki.setdefault("updated_at", _now_iso())
        return wiki

    @staticmethod
    def _fill_char_defaults(wiki: dict, char_id: str) -> dict:
        for key in ("schema_version", "character_hash", "self_hash", "summary",
                    "facts", "beliefs", "relations"):
            wiki.setdefault(key, (SCHEMA_VERSION if key == "schema_version"
                                  else "" if key in ("character_hash", "self_hash", "summary")
                                  else []))
        wiki.setdefault("character_id", char_id)
        wiki.setdefault("digested_through_ts", None)
        wiki.setdefault("updated_at", _now_iso())
        return wiki
