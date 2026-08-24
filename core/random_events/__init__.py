# -*- coding: utf-8 -*-
"""随机事件系统 — 概率性引擎行为（引擎唯一入口: fire_event）。

事件 = 引擎层在特定时机按概率触发的行为（注入 system_note 等）。
引擎（momotalk/bond_story）只留时机钩子调 fire_event, 事件逻辑隔离在本模块。

判定链: 全局启用 → 事件存在 → 冷却通过 → 概率命中 → fire(ctx) 返回注入文本
（None = 不触发）。soft 事件的注入文本自带"不要求反馈"语义（见 events.py）。

用法（引擎钩子）:
    from core.random_events import fire_event
    note = fire_event("want_to_speak", {"round": round_no, "_cooldowns": cooldowns})
    if note:
        messages.append({"role": "system", "content": note})

测试/确定性场景: set_enabled(False) 全局禁用（零影响现有测试）。
"""

from __future__ import annotations

import random
from typing import Any

from core.random_events.spec import EventSpec, get_event, register
from core.random_events.events import build_default_events

#: 全局开关（False → fire_event 恒返回 None; 测试/确定性场景）
_ENABLED = True


def set_enabled(flag: bool) -> None:
    """全局启用/禁用随机事件（测试/确定性场景禁用; 生产默认启用）。"""
    global _ENABLED
    _ENABLED = flag


def fire_event(name: str, ctx: dict[str, Any], rng=None) -> str | None:
    """触发事件（概率 + 冷却判定）; 返回注入文本, None = 不触发。

    ctx 约定:
        round: 当前轮数（冷却基准, 默认 0）
        _cooldowns: 冷却状态 dict（同一 dict 跨调用传入——per-session 不串）
        事件各自需要的字段（如 memory_flash 的 events/wiki/digested_seq）
    """
    if not _ENABLED:
        return None
    spec = get_event(name)
    if spec is None:
        return None
    round_no = int(ctx.get("round", 0) or 0)
    cooldowns: dict[str, int] = ctx.get("_cooldowns")
    if cooldowns is None:
        cooldowns = {}
        ctx["_cooldowns"] = cooldowns
    last = cooldowns.get(name, -spec.cooldown)
    if round_no - last < spec.cooldown:
        return None
    if (rng or random).random() >= spec.probability:
        return None
    if rng is not None:                    # 透传给事件 fire（内部随机可注入, 测试用）
        ctx["_rng"] = rng
    text = spec.fire(ctx)
    if not text:
        return None
    cooldowns[name] = round_no
    return text


def ensure_defaults() -> None:
    """注册默认事件（幂等——引擎启动时调用; 重复注册覆盖同名）。"""
    for spec in build_default_events():
        register(spec)


# 模块导入即注册默认事件（引擎钩子可直接 fire）
ensure_defaults()
