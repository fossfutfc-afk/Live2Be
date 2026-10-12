"""好感度（羁绊值）子系统——查表 + digest 返回 exp 增量（AI 总结时加好感）。"""
from core.affection.affection_calc import (
    MAX_LEVEL,
    MIN_LEVEL,
    Affection,
    load_affection_from_events,
    load_affection_table,
    load_raiser_table,
)

__all__ = [
    "Affection",
    "MAX_LEVEL",
    "MIN_LEVEL",
    "load_affection_from_events",
    "load_affection_table",
    "load_raiser_table",
]
