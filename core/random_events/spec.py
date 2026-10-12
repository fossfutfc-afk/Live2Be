"""随机事件规格（EventSpec + 注册表）— 概率性引擎行为。

事件 = 引擎层在**特定时机**按概率触发的行为（注入 system_note 等）。
隔离成独立模块: 事件种类会增长（记忆浮现/主动说话/未来论坛发言…）,
引擎（momotalk/bond_story）只留时机钩子调 fire_event, 不被事件逻辑污染。

- soft=True: 软提示（不要求 AI 一定反馈——"自然流露即可"）; False = 硬要求
- cooldown: 触发后冷却轮数（同 session, 防连发打断）
- probability: 0~1（作者可调; 全局可禁用 = set_enabled(False), 测试/确定性场景）
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: 触发时机常量（引擎钩子名）
TRIGGER_MMT_TURN = "mmt_turn"        # momotalk.agent_turn 每轮前
TRIGGER_BOND_START = "bond_start"    # 羁绊剧情开场（第一场前）


@dataclass
class EventSpec:
    """随机事件规格。"""

    name: str
    trigger: str                       # 触发时机（TRIGGER_* 常量）
    probability: float                 # 0~1 触发概率
    fire: Callable[[dict[str, Any]], str | None]  # ctx → 注入文本; None = 不触发
    cooldown: int = 5                  # 触发后冷却轮数（同 session）
    soft: bool = True                  # True = 软提示（不要求 AI 反馈）


#: 事件注册表（name → EventSpec）
_EVENTS: dict[str, EventSpec] = {}


def register(spec: EventSpec) -> None:
    """注册事件（重复注册同名 → 覆盖, 便于测试注入）。"""
    _EVENTS[spec.name] = spec


def get_event(name: str) -> EventSpec | None:
    return _EVENTS.get(name)


# EXT: random-events-introspection — 注册表内省（fire_event 才是活入口）; 勿删（docs/EXTENSION_POINTS.md）
def all_events() -> list[EventSpec]:
    return list(_EVENTS.values())
