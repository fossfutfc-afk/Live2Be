# -*- coding: utf-8 -*-
"""会话元数据与 VN 恢复点 dataclass（core/DESIGN_SAVE.md §4）。

SessionMeta — meta.json: 状态机 + parent 关联 + schema 版本
VNState     — vn_state.json: bond story 中断恢复点

解析全部容错（宁缺勿错）: from_dict 对坏字段降级为默认, 不 raise;
to_dict 只含非空字段（None/空省略, 保持文件小而稳）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

#: 会话类型
TYPE_MMT = "momotalk"
TYPE_BOND = "bond_story"

#: 状态机（DESIGN_SAVE.md §5.1）
STATE_ACTIVE = "active"            # MMT 中（根会话）
STATE_PAUSED = "paused"            # VN 中（bond 子会话）
STATE_ENDED = "ended"              # 自然收尾
STATE_INTERRUPTED = "interrupted"  # 崩溃/断连（玩家手动 resume 时转回 active/paused）

_OPEN_STATES = (STATE_ACTIVE, STATE_PAUSED)


def now_iso() -> str:
    return datetime.now().isoformat()


def _str_field(raw: dict, key: str, default: str = "") -> str:
    """取字符串字段: 非 str / 空 → default（宁缺勿错, 坏类型不 raise）。"""
    v = raw.get(key)
    return v if isinstance(v, str) and v else default


def _int_field(raw: dict, key: str, default: int) -> int:
    """取整数字段: 非数字 / 空 → default。"""
    v = raw.get(key)
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _bool_field(raw: dict, key: str, default: bool = False) -> bool:
    """取布尔字段: 非 bool → default（"false" 字符串不误转 True）。"""
    v = raw.get(key)
    return v if isinstance(v, bool) else default


@dataclass
class SessionMeta:
    """一个互动会话的元数据（meta.json）。"""

    schema_version: int = 1
    session_id: str = ""
    type: str = TYPE_MMT                # momotalk | bond_story
    character_id: str = ""
    character_name: str = ""
    state: str = STATE_ACTIVE           # active | paused | ended | interrupted
    parent_session_id: str | None = None  # bond 子会话 = 所属 MMT 会话; 根会话 None
    created_at: str = ""
    updated_at: str = ""
    trigger_reason: str = ""            # bond 子会话触发原因; 根会话可空

    @property
    def is_open(self) -> bool:
        """是否未结束（可被 list_open 列出 / resume）。"""
        return self.state in _OPEN_STATES

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "type": self.type,
            "character_id": self.character_id,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.character_name:
            d["character_name"] = self.character_name
        if self.parent_session_id is not None:
            d["parent_session_id"] = self.parent_session_id
        if self.trigger_reason:
            d["trigger_reason"] = self.trigger_reason
        return d

    @classmethod
    def from_dict(cls, raw: dict | None) -> "SessionMeta":
        """宽松解析（坏字段 → 默认, 不 raise）。"""
        if not isinstance(raw, dict):
            return cls()
        parent = raw.get("parent_session_id")
        return cls(
            schema_version=_int_field(raw, "schema_version", 1),
            session_id=_str_field(raw, "session_id"),
            type=_str_field(raw, "type", TYPE_MMT),
            character_id=_str_field(raw, "character_id"),
            character_name=_str_field(raw, "character_name"),
            state=_str_field(raw, "state", STATE_ACTIVE),
            parent_session_id=parent if isinstance(parent, str) and parent else None,
            created_at=_str_field(raw, "created_at"),
            updated_at=_str_field(raw, "updated_at"),
            trigger_reason=_str_field(raw, "trigger_reason"),
        )


@dataclass
class VNState:
    """bond story 中断恢复点（vn_state.json, DESIGN_SAVE.md §4.4）。"""

    round: int = 1                    # 当前第几场（vn_cli 的 i, 下一场 = round+1）
    seed: str = ""                    # 下一场 user_input（= 上一场 picked/choice）
    completed: bool = False
    force_after: int = 32             # end_rounds+2（恢复后继续计数用）
    visual: dict = field(default_factory=dict)   # 导演 VisualState.to_dict()
    scenes_flushed: int = 0           # scenes.jsonl 已写场数（对齐校验）

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "round": self.round,
            "seed": self.seed,
            "completed": bool(self.completed),
            "force_after": self.force_after,
            "scenes_flushed": self.scenes_flushed,
        }
        if self.visual:
            d["visual"] = dict(self.visual)
        return d

    @classmethod
    def from_dict(cls, raw: dict | None) -> "VNState":
        if not isinstance(raw, dict):
            return cls()
        visual = raw.get("visual")
        return cls(
            round=_int_field(raw, "round", 1),
            seed=_str_field(raw, "seed"),
            completed=_bool_field(raw, "completed"),
            force_after=_int_field(raw, "force_after", 32),
            visual=dict(visual) if isinstance(visual, dict) else {},
            scenes_flushed=_int_field(raw, "scenes_flushed", 0),
        )
