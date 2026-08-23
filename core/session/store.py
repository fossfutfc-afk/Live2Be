# -*- coding: utf-8 -*-
"""SessionStore — 会话生命周期（core/DESIGN_SAVE.md §五/§六）。

create / open_vn / append_event / append_marker / update_session_progress /
finish / list_open / resume（读路径）。

路径（角色根目录, §三）:
    data/{char_id}/sessions/{session_id}/meta.json     （纯索引, 创建时写一次）
    data/{char_id}/sessions/{session_id}/events.jsonl  （事件流唯一真源）
    data/{char_id}/sessions/{session_id}/progress.json （会话内轮数）

seq 分配: 实例缓存（首次 append 从文件算最大 seq, 之后递增）——**单写者假设**
（单进程 CLI; 未来 web 多会话各自写自己的目录, 天然隔离）。

状态: 无状态机——ended/in_vn 由 events 的 marker 推导（renderer.session_status）。
"""

from __future__ import annotations

import json
import random
import string
from datetime import datetime
from pathlib import Path

from core.session.events import (
    M_SESSION_END,
    M_SESSION_START,
    M_VN_ENTER,
    Event,
    make_event,
    marker,
    parse_events,
)
from core.session.io import append_jsonl, atomic_write_json, read_jsonl
from core.session.models import TYPE_BOND, TYPE_MMT, SessionMeta
from core.session.renderer import session_status

DEFAULT_DATA_ROOT = Path("data")


def _new_session_id() -> str:
    """角色目录内唯一: {YYYYMMDD_HHMMSS}_{rand4}。"""
    rand4 = "".join(random.choice(string.hexdigits.lower()) for _ in range(4))
    return f"{datetime.now():%Y%m%d_%H%M%S}_{rand4}"


class SessionStore:
    """会话生命周期管理器（路径参数化 data_root, 默认 data/）。"""

    def __init__(self, data_root: str | Path = DEFAULT_DATA_ROOT):
        self.data_root = Path(data_root)
        self._seqs: dict[str, int] = {}      # session_id → 已分配最大 seq（单写者）

    # ------------------------------------------------------------------
    # 路径
    # ------------------------------------------------------------------

    def char_dir(self, char_id: str) -> Path:
        return self.data_root / char_id

    def sessions_dir(self, char_id: str) -> Path:
        return self.char_dir(char_id) / "sessions"

    def session_dir(self, char_id: str, session_id: str) -> Path:
        return self.sessions_dir(char_id) / session_id

    def meta_path(self, char_id: str, session_id: str) -> Path:
        return self.session_dir(char_id, session_id) / "meta.json"

    def events_path(self, char_id: str, session_id: str) -> Path:
        return self.session_dir(char_id, session_id) / "events.jsonl"

    def progress_path(self, char_id: str, session_id: str) -> Path:
        return self.session_dir(char_id, session_id) / "progress.json"

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def create(self, char_id: str, char_name: str = "") -> SessionMeta:
        """新建 MMT 根会话: 写 meta（纯索引）+ append marker session_start。"""
        session_id = _new_session_id()
        meta = SessionMeta(
            session_id=session_id,
            type=TYPE_MMT,
            character_id=char_id,
            character_name=char_name,
            created_at=datetime.now().isoformat(),
        )
        self._write_meta(char_id, meta)
        self.append_marker(char_id, session_id, M_SESSION_START)
        return meta

    def open_vn(
        self,
        char_id: str,
        parent_session_id: str,
        reason: str = "",
        char_name: str = "",
    ) -> SessionMeta:
        """新建 bond 子会话: meta(type=bond) + session_start + vn_enter{parent, reason}。"""
        session_id = _new_session_id()
        meta = SessionMeta(
            session_id=session_id,
            type=TYPE_BOND,
            character_id=char_id,
            character_name=char_name,
            created_at=datetime.now().isoformat(),
        )
        self._write_meta(char_id, meta)
        self.append_marker(char_id, session_id, M_SESSION_START)
        self.append_marker(char_id, session_id, M_VN_ENTER,
                           {"parent_session_id": parent_session_id, "reason": reason})
        return meta

    def finish(self, char_id: str, session_id: str, ended: bool = True) -> Event:
        """会话收尾: append marker session_end{ended}（没写 = 中断, 零成本表达）。"""
        return self.append_marker(char_id, session_id, M_SESSION_END, {"ended": ended})

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------

    def append_event(self, char_id: str, session_id: str, event: Event) -> Event:
        """append 一个事件（seq 自动分配: 实例缓存递增; 首次从文件算最大 seq）。"""
        if session_id not in self._seqs:
            evs = parse_events(read_jsonl(self.events_path(char_id, session_id)))
            self._seqs[session_id] = max((e.seq for e in evs), default=0)
        self._seqs[session_id] += 1
        ev = Event(
            seq=self._seqs[session_id],
            ts=event.ts or datetime.now().isoformat(),
            type=event.type,
            subtype=event.subtype,
            payload=dict(event.payload),
        )
        append_jsonl(self.events_path(char_id, session_id), ev.to_dict())
        return ev

    def append_marker(
        self, char_id: str, session_id: str, subtype: str, payload: dict | None = None,
    ) -> Event:
        """append 一个 marker 事件（状态标记）。"""
        return self.append_event(char_id, session_id, marker(subtype, payload))

    def update_session_progress(self, char_id: str, session_id: str, rounds: int) -> None:
        """写会话内轮数（data/{char}/sessions/{sid}/progress.json, 展示用）。"""
        atomic_write_json(self.progress_path(char_id, session_id), {
            "rounds": rounds,
            "updated_at": datetime.now().isoformat(),
        })

    # ------------------------------------------------------------------
    # 读路径
    # ------------------------------------------------------------------

    def meta(self, char_id: str, session_id: str) -> SessionMeta:
        """读 meta.json（缺失 → 空 SessionMeta, 宁缺勿错）。"""
        return SessionMeta.from_dict(self._read_json(self.meta_path(char_id, session_id)))

    def events(self, char_id: str, session_id: str) -> list[Event]:
        """读 events.jsonl（行级容错, 坏骨架事件丢弃）。"""
        return parse_events(read_jsonl(self.events_path(char_id, session_id)))

    def resume(self, char_id: str, session_id: str) -> dict:
        """恢复读路径: {meta, events, status}（调用方用 render_events + session_status 重建引擎）。"""
        evs = self.events(char_id, session_id)
        return {
            "meta": self.meta(char_id, session_id),
            "events": evs,
            "status": session_status(evs),
        }

    def list_open(self) -> list[SessionMeta]:
        """列出全部未结束会话（无 session_end marker, 按 created_at 倒序）。

        扫 data/*/sessions/*/meta.json; 每会话读 events 判 ended（本地会话少, 可接受）。
        """
        out: list[SessionMeta] = []
        for meta_path in sorted(self.data_root.glob("*/sessions/*/meta.json")):
            meta = SessionMeta.from_dict(self._read_json(meta_path))
            if not meta.session_id:
                continue
            char_id = meta.character_id
            status = session_status(
                parse_events(read_jsonl(self.events_path(char_id, meta.session_id))))
            if not status["ended"]:
                out.append(meta)
        out.sort(key=lambda m: m.created_at, reverse=True)
        return out

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _write_meta(self, char_id: str, meta: SessionMeta) -> None:
        atomic_write_json(self.meta_path(char_id, meta.session_id), meta.to_dict())

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None
