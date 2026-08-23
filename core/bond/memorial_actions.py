# -*- coding: utf-8 -*-
"""MEMORIAL 域动作 — 纪念子模式收尾（2026-08-24 状态机设计, §4.7）。

动作:
    memorial_exit   纪念场景结束, 回到 bond（append marker memorial_exit）——独占一轮

与 story 域的关系（切换动作归发出方域, 仿 mmt_trigger_bond_story 属 mmt 域）:
    - **memorial_enter 属 bond（story）域**——bond 剧情中由主 LLM 输出, 注册在
      bond_actions.build_story_registry（story_scene/story_end/memorial_enter 三动作）
    - **本文件只有纪念模式内部的动作** memorial_exit——注册在独立 registry
      （build_memorial_registry, memorial 域）; 模式内动作归模式域

contract 设计（2026-08-24, 状态机定稿）:
    - 只有**可选的过渡文字**（paragraphs）——纯状态切换, 无图、无选项、无 prompt
    - 独占一轮: 输出后引擎 append marker memorial_exit, 下一场 LLM 继续
      story_scene/story_end（回 bond 模式）
"""

from __future__ import annotations

from typing import Any

from contract import (
    ActionSpec,
    APPROVAL_AUTO,
    ContractError,
    MemorialActionRegistry,
)


def parse_memorial_exit(payload: dict[str, Any]) -> dict[str, Any]:
    """memorial_exit payload 白名单校验（从纪念模式回到 bond）。

    返回 {paragraphs: [str]?}——只有可选的过渡文字（从纪念时刻回到日常的衔接,
    可空: 不写 = 纯状态切换, 无渲染内容）。容错: 单段裸字符串 → 包成单元素列表。
    """
    raw = payload.get("paragraphs")
    if raw is None:
        return {}
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ContractError("paragraphs 必须是数组（每项一段文字或字符串）")
    paragraphs = [p.strip() for p in raw if isinstance(p, str) and p.strip()]
    if not paragraphs:
        return {}
    return {"paragraphs": paragraphs}


def build_memorial_registry() -> MemorialActionRegistry:
    """构建 memorial 域注册表（独立 registry, 只含纪念模式内部的收尾动作）。"""
    registry = MemorialActionRegistry()
    registry.register(ActionSpec(
        "memorial_exit",
        parse_memorial_exit,
        APPROVAL_AUTO,
        prompt_fields=frozenset({"action", "payload"}),
        payload_schema=(
            "payload 字段（memorial_exit 纪念模式收尾）:\n"
            "  paragraphs: 可选, 数组——从纪念时刻回到日常的过渡文字\n"
            "      （可空: 不写 = 纯状态切换, 无渲染内容）\n"
            "约束: memorial_exit 在纪念场景结束后输出——回到 bond 模式, 之后继续\n"
            "      story_scene/story_end。字符串一律双引号。每次只输出一个动作。"
        ),
    ))
    return registry
