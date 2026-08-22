# -*- coding: utf-8 -*-
"""导演 prompt 拼装 — 两段流（背景分层）。

第一段 build_director_prompt: 人设 + 当前视觉状态 + 表情白名单 + 常用场景/目录
    + 触发原因 + nudge/收尾注记 + 本轮段落 → 导演输出 {sprite, background}。
    background 语义: scene_id(常用列表直给) / 目录名(走第二段拍板) / keep 或 null(保持)。
第二段 build_drill_prompt: 某目录的可选 scene_id 清单 → 导演输出最终 {background}。

长段静态规则在 llm/prompts/director_rules.md; 这里只拼动态上下文。
"""

from __future__ import annotations


def _state_line(state) -> str:
    """当前视觉状态行（state 恒有值, 冷启动用默认）。"""
    return f"当前视觉状态: sprite={state.sprite}, background={state.background}"


def build_director_prompt(
    *,
    rules: str,
    persona: str,
    state,
    emotions: list[str],
    common_scenes: list[str],
    common_dirs: list[str],
    trigger_reason: str,
    nudge: bool,
    unchanged: int,
    is_end: bool,
    text: str,
) -> str:
    """第一段: 完整导演调用 prompt。"""
    parts: list[str] = [rules]
    if persona:
        parts.append(persona)

    lines = [_state_line(state)]
    lines.append("合法 sprite: " + (", ".join(emotions) if emotions else "（无）"))
    lines.append(
        "常用场景（可直接输出 scene_id）: "
        + (", ".join(common_scenes) if common_scenes else "（无）")
    )
    lines.append(
        "可用目录（场景不在常用列表时选目录名, 导演会再给该目录的内容）: "
        + (", ".join(common_dirs) if common_dirs else "（无）")
    )
    if trigger_reason:
        lines.append(f"羁绊剧情起因: {trigger_reason}")
    if nudge:
        lines.append(
            f"（系统提示）表情已连续保持 {unchanged} 场未变化。"
            "剧情若有起伏，请在接下来的场景换 sprite；剧情平静时保持也正确。"
        )
    if is_end:
        lines.append(
            "（系统提示）这是收尾场景，收尾表情由你自然选择（微笑收尾很常见），"
            "不必强制回到默认。"
        )
    parts.append("视觉上下文:\n" + "\n".join(lines))

    parts.append("本轮段落:\n" + text)

    parts.append(
        '输出: 单个 JSON 对象 {"sprite": "<合法sprite或null>", '
        '"background": "<scene_id 或 目录名 或 keep 或 null>"}。'
        "只输出 JSON, 不要解释。"
    )
    return "\n\n".join(parts)


def build_drill_prompt(
    *,
    dir_name: str,
    scenes: list[str],
    state,
    text: str,
) -> str:
    """第二段: 背景分层拍板 prompt（导演已选目录 → 给目录内可选场景）。"""
    parts: list[str] = [
        "你是羁绊剧情视觉导演，负责选定本场背景。",
        f"你判断本场剧情发生在目录 {dir_name}。该目录可选背景 scene_id:\n"
        + (", ".join(scenes) if scenes else "（空）"),
        _state_line(state),
        "本轮段落:\n" + text,
        '输出: 单个 JSON 对象 {"background": "<上列 scene_id 之一>"}。'
        "选不准就给当前背景或 keep。只输出 JSON, 不要解释。",
    ]
    return "\n\n".join(parts)
