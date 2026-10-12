"""本回合任务卡（DESIGN_PROMPTKIT §4）——Phase 2 启用（MMT chat/wrapup）。

职责: 卡 = 目标层（这回合达成什么）; 约束层（配额/提醒/边界）仍由引擎/调用方
注记承担——卡内不重复规则书/注记内容。

模板 = llm/prompts/task_*.md（人可改, {char} 占位 replace, 同 digest 约定）:
    task_<domain>.md            = 域默认 kind（mmt→chat; bond→scene, Phase 3）
    task_<domain>_<kind>.md     = 其他 kind（mmt_wrapup; bond_memorial, Phase 3）
预算 ≤ 100 token（超过即稀释, 作者改模板时自重）。模板缺失 → 不注入（宁缺勿错）。

槽位: history 之后、所有约束注记之后、user 之前——由 round_messages 调用方
（引擎）把卡作为 notes 末位追加。

开关: settings.toml [promptkit].task_card（config.task_card_enabled, 默认 true）;
enabled=None → 读配置; 显式 bool（引擎构造参数/测试）→ 覆盖。
"""
from __future__ import annotations

import logging

from core.promptkit.config import task_card_enabled
from llm.prompts import load_prompt

logger = logging.getLogger(__name__)

#: 各域默认 kind（模板 = task_<domain>.md）
_DEFAULT_KIND: dict[str, str] = {
    "mmt": "chat",
    "bond": "scene",           # Phase 3 接入
}


def _template_name(domain: str, kind: str) -> str:
    if kind == _DEFAULT_KIND.get(domain, ""):
        return f"task_{domain}"
    return f"task_{domain}_{kind}"


def task_card(
    domain: str,
    kind: str = "",
    *,
    char: str = "",
    enabled: bool | None = None,
) -> str | None:
    """构建本回合任务卡文本（None = 不注入）。

    Args:
        domain: "mmt" / "bond"
        kind: 空 → 域默认（mmt→chat, bond→scene）
        char: {char} 占位（display_name; 空 → 保留占位不替换）
        enabled: None → settings [promptkit].task_card; False → 恒不注入（A/B 对照）
    """
    if enabled is None:
        enabled = task_card_enabled()
    if not enabled:
        return None
    kind = (kind or _DEFAULT_KIND.get(domain, "")).strip()
    if not kind:
        return None
    try:
        text = load_prompt(_template_name(domain, kind))
    except FileNotFoundError:                # 模板未建（其他域/kind 未启用）→ 静默不注入
        return None
    if not text.strip():
        return None
    if "{char}" in text:
        text = text.replace("{char}", (char or "").strip())
    return text
