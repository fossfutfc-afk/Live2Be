# -*- coding: utf-8 -*-
"""本回合任务卡（DESIGN_PROMPTKIT §4, task 卡）——Phase 2 启用。

现（Phase 1）占位返回 None（不注入, 行为与现网逐字节一致）; Phase 2 接入:
    · 模板 = llm/prompts/task_*.md（人可改; {char} 占位 replace, 同 digest 约定）
    · kind: mmt: chat / wrapup; bond: scene / memorial_exit（引擎自推或调用方显式传）
    · 预算 ≤ 100 token; 卡 = 目标层, 不重复规则书/注记内容
    · 槽位: history 之后、所有约束注记之后、user 之前（round_messages notes 尾部）
    · 开关: settings.toml [promptkit].task_card（config.task_card_enabled, 默认 true）
"""
from __future__ import annotations


def task_card(domain: str, kind: str, *, char: str = "") -> str | None:
    """构建本回合任务卡文本（None = 不注入）。Phase 2 实现模板加载与渲染。"""
    return None
