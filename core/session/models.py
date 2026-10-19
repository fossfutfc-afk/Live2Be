"""会话模型 — meta 纯索引 + VN 恢复点 payload（core/session/.md）。

SessionMeta — meta.json: **纯索引, 无状态机**（用户决策 2026-08-23: 状态由
    events 的 marker 事件推导, 见 §4.2/§5.1）; type 创建时确定, 列表显示用
VNState     — marker vn_state 的 payload（每场 VN 轮 append, 恢复取最后一个）

解析全部容错（宁缺勿错）: from_dict 对坏字段降级为默认, 不 raise;
to_dict 只含非空字段（None/空省略, 保持文件小而稳）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.session.events import TYPE_MMT  # 板块类型值单源（见下方注释; events.py 才是真源）

#: 会话类型（= 会话内主导事件板块）——**板块词表真源 = `events.py`**。
#: ⚠️ 原 `TYPE_MMT = "mmt"` / `TYPE_BOND = "bond"` 两份本模块副本 2026-09-21 合并:
#: `TYPE_MMT` 改为从 events import; `TYPE_BOND` 删（本模块无消费者——要 bond 板块
#: 常量去 events.py 拿, 那边是唯一真源）。
TYPE_CONVERSATION = "conversation"   # ★ 2026-08-24: 单事件流会话（mmt+bond+l2d 全板块一目录）


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
    """会话元数据（meta.json, 纯索引——创建时写一次, 之后不再变）。"""

    schema_version: int = 1
    session_id: str = ""
    type: str = TYPE_CONVERSATION      # conversation（单流 2026-08-24）; 旧 mmt/bond 值兼容读取
    character_id: str = ""
    character_name: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "type": self.type,
            "character_id": self.character_id,
            "created_at": self.created_at,
        }
        if self.character_name:
            d["character_name"] = self.character_name
        return d

    @classmethod
    def from_dict(cls, raw: dict | None) -> SessionMeta:
        """宽松解析（坏字段 → 默认, 不 raise）。"""
        if not isinstance(raw, dict):
            return cls()
        return cls(
            schema_version=_int_field(raw, "schema_version", 1),
            session_id=_str_field(raw, "session_id"),
            type=_str_field(raw, "type", TYPE_MMT),
            character_id=_str_field(raw, "character_id"),
            character_name=_str_field(raw, "character_name"),
            created_at=_str_field(raw, "created_at"),
        )


@dataclass
class VNState:
    """VN 恢复点（marker vn_state 的 payload, core/session/.md）。"""

    round: int = 1                    # 当前第几场（vn_cli 的 i, 下一场 = round+1）
    seed: str = ""                    # 下一场 user_input（= 上一场 picked/choice）
    completed: bool = False
    force_after: int = 32             # end_rounds+2（恢复后继续计数用）
    visual: dict = field(default_factory=dict)   # 导演 VisualState.to_dict()

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "round": self.round,
            "seed": self.seed,
            "completed": bool(self.completed),
            "force_after": self.force_after,
        }
        if self.visual:
            d["visual"] = dict(self.visual)
        return d

    @classmethod
    def from_dict(cls, raw: dict | None) -> VNState:
        if not isinstance(raw, dict):
            return cls()
        visual = raw.get("visual")
        return cls(
            round=_int_field(raw, "round", 1),
            seed=_str_field(raw, "seed"),
            completed=_bool_field(raw, "completed"),
            force_after=_int_field(raw, "force_after", 32),
            visual=dict(visual) if isinstance(visual, dict) else {},
        )
