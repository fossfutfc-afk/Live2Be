# -*- coding: utf-8 -*-
"""MEMORIAL 域动作 — 纪念立绘（bond 剧情中的纪念瞬间, 2026-08-24）。

动作:
    memorial_generate  纪念瞬间: 煽情文字 + 选项, 独占一轮 → 引擎生成纪念立绘

与 story 域（story_scene/story_end）并列, **独立 registry**（build_memorial_registry）
——不混入 story registry（用户拍板 2026-08-24）。

contract 设计（2026-08-24, 简单版; 预判式设计讨论中）:
    - **只有文字和选项**（paragraphs + choices）——不调 emotion/place/背景, 省时省力
    - **要求 AI 煽情**: payload_schema 引导"纪念时刻的定格感/余韵"
    - 独占一轮: 输出后本场生成纪念立绘, 下一场继续剧情
    - 生图 prompt 不在本动作里——预判式设计下由"进剧情前的预判环节"承担
      （讨论中, 见 DESIGN_SAVE.md §4.7 关联）; 当前简单版 parse 兼容后续字段扩展
"""

from __future__ import annotations

from typing import Any

from contract import (
    ActionSpec,
    APPROVAL_AUTO,
    ContractError,
    MemorialActionRegistry,
)

#: 选项数量上限（同 story 域收敛分支）
MAX_MEMORIAL_CHOICES = 3


def _parse_paragraphs(payload: dict[str, Any]) -> list[str]:
    """必填 paragraphs: 煽情文字数组（机器侧容错: 单段裸字符串 → 包成单元素列表）。"""
    raw = payload.get("paragraphs")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ContractError("paragraphs 必须是数组（每项一段文字或字符串）")
    paragraphs = [p.strip() for p in raw if isinstance(p, str) and p.strip()]
    if not paragraphs:
        raise ContractError("paragraphs 至少需要一个非空段落")
    return paragraphs


def _parse_choices(payload: dict[str, Any]) -> list[str]:
    """可选 choices: 给 sensei 的回应选项（容错 + 截断到上限）。"""
    raw = payload.get("choices", [])
    if isinstance(raw, str):
        raw = [raw]
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ContractError("choices 必须是字符串数组（或单个字符串）")
    return [c.strip() for c in raw if isinstance(c, str) and c.strip()][:MAX_MEMORIAL_CHOICES]


def parse_memorial_generate(payload: dict[str, Any]) -> dict[str, Any]:
    """memorial_generate payload 白名单校验 + 机器侧容错。

    返回 {paragraphs: [str], choices: [str]?}——只有文字和选项（简单版 contract）。
    生图 prompt 不在本动作（预判式设计下由剧情前预判承担, 见模块 docstring）。
    """
    paragraphs = _parse_paragraphs(payload)
    choices = _parse_choices(payload)
    result: dict[str, Any] = {"paragraphs": paragraphs}
    if choices:
        result["choices"] = choices
    return result


def build_memorial_registry() -> MemorialActionRegistry:
    """构建 memorial 域注册表（独立 registry, 与 story 域隔离）。"""
    registry = MemorialActionRegistry()
    registry.register(ActionSpec(
        "memorial_generate",
        parse_memorial_generate,
        APPROVAL_AUTO,
        prompt_fields=frozenset({"action", "payload"}),
        payload_schema=(
            "payload 字段（memorial_generate 纪念立绘参数）:\n"
            "  paragraphs: 必填, 数组——纪念瞬间的煽情文字（此刻的情感定格, 1~3 句）:\n"
            "      **要求煽情**: 这是值得生成纪念立绘的时刻, 文字要配得上它——\n"
            "      定格感、余韵、让 sensei 心头一紧的那种瞬间, 而不是平淡的叙述\n"
            "  choices: 可选, 数组——给 sensei 的回应选项（1~3 个; 缺省 = sensei 自由输入）\n"
            "约束: memorial_generate 是**纪念时刻动作**, 独占一轮——输出后引擎生成\n"
            "      纪念立绘, 下一场继续剧情（story_scene/story_end）。字符串一律双引号。\n"
            "      每次只输出一个动作。"
        ),
    ))
    return registry
