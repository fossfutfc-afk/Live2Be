# -*- coding: utf-8 -*-
"""随机事件实现 — 记忆突然浮现 / 角色自己想说话。

记忆浮现（bond_start）: 从 wiki_v2 双通道随机摘 1 段 episode（珍贵保底 +
  遗忘曲线, random_flash_segment）——角色在剧情开始前突然想起一件事。
  **soft**: 不要求 AI 一定做反馈——记忆浮现是情绪底色,
  "如果合适可以自然流露, 不必刻意提起"（用户定调: 低频惊喜, 不是指令）。
主动说话（mmt_turn）: 角色有点想和老师说点别的话——soft 倾向, 不是指令。
"""

from __future__ import annotations

from typing import Any

from core.random_events.spec import (
    TRIGGER_BOND_START,
    TRIGGER_MMT_TURN,
    EventSpec,
)


def _memory_flash_fire(ctx: dict[str, Any]) -> str | None:
    """记忆突然浮现: 摘到的 episode 段 → 第一人称"你突然想起…"。

    ctx 需含 segment（BrainNode, 调用方用 wiki_v2 random_flash_segment 预摘）;
    无记忆可浮（空库/无 episode）→ None。
    """
    seg = ctx.get("segment")
    if seg is None:
        return None
    # 2026-09-21: 原为 `seg.narration if seg.kind=="episode" else seg.main_text`——
    # 那个三元是**死分支**（`main_text` 的 episode 分支本来就是 narration）;
    # 三槽合流成 `text` 后直接取，非节点（调用方也可能塞字符串）照旧回落 str()。
    text = seg.text if hasattr(seg, "kind") else str(seg)
    if not text:
        return None
    return (f"（在剧情开始前，你突然想起了一件事：{text}。"
            "它自然地浮现在心头——如果合适，可以自然地流露；不必刻意提起。）")


def _want_to_speak_fire(ctx: dict[str, Any]) -> str:
    """角色自己想说话: soft 提示（倾向, 不是指令）。"""
    return ("（你现在有点想和老师说点别的——一件放在心上、想说又没说的话。"
            "如果时机合适，主动开口吧；觉得不合适也可以不说。）")


def build_default_events() -> list[EventSpec]:
    """默认事件集（mmt/bond 开场钩子消费）。"""
    return [
        EventSpec(
            name="memory_flash",
            trigger=TRIGGER_BOND_START,
            probability=0.25,           # 记忆浮现概率（低频惊喜, 作者可调）
            fire=_memory_flash_fire,
            cooldown=1,                 # bond 每场只开场一次, 冷却意义小
            soft=True,
        ),
        EventSpec(
            name="want_to_speak",
            trigger=TRIGGER_MMT_TURN,
            probability=0.12,           # 主动说话概率（低——"想说话"是稀缺时刻）
            fire=_want_to_speak_fire,
            cooldown=6,                 # 触发后 6 轮内不再提示（防连发打断）
            soft=True,
        ),
    ]
