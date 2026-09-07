# -*- coding: utf-8 -*-
"""盒 = 会话级 system prompt 装配（DESIGN_PROMPTKIT §4.1, 盒A v2 起）。

盒 = 域 → 块 id 有序清单; build_box 依清单渲染并 "\n\n" 连接（缺席块跳过）。
盒A v2（MMT, 2026-09-07）: 称呼行归位盒顶（身份先行）——此前称呼行夹在
environment 与 rules 之间（位置不伦不类, 用户拍板调整）。其余顺序/文案
逐字节沿用现网（黄金夹具锁定）。
"""
from __future__ import annotations

from core.promptkit.blocks import BlockContext, render_block

#: 各域盒的块清单（顺序即注入顺序; 改 = 显式更新黄金夹具并留 diff）
DOMAIN_BOXES: dict[str, list[str]] = {
    "mmt": [
        "greeting",        # 称呼行（v2 首段）
        "persona_mmt",     # 角色设定全量 + 行为规则
        "world",           # 世界常识/规则
        "story_tone",      # 本角色剧情基调
        "mmt_tone",        # MMT 风格（条件）
        "interperson",     # 人际层（条件）
        "environment_mmt", # MMT 环境
        "rules_mmt",       # MMT 规则书
        "schema",          # 可用动作 schema
    ],
    # 盒B v2（Bond, 2026-09-07 Phase 3）: 称呼行归位盒顶——此前夹在 bond_tone
    # 与 rules 之间; 其余顺序/文案逐字节沿用现网（黄金夹具锁定）。
    # 2026-09-07 v2 单源切换（P3b-2）: 地点词表块移除——place 判定移交标注层
    # （place_annotate 模板持有词表）, 主 LLM 不再写地点
    "bond": [
        "greeting",            # 称呼行（v2 首段, 剧情行为规则指向）
        "persona_bond",        # 角色设定两层 + 行为规则
        "world",               # 世界常识/规则
        "story_tone",          # 本角色剧情基调
        "bond_tone",           # 羁绊剧情建议（条件）
        "rules_bond",          # 羁绊剧情规则书
        "schema",              # 可用动作 schema（story 域）
        "lexicon_emotion",     # 表情标注词表（条件）
        "brain",               # 记忆段（条件）
    ],
}


def box_chunks(domain: str, ctx: BlockContext) -> list[tuple[str, str]]:
    """渲染盒的 (块 id, 文本) 清单（缺席块跳过）。describe 与 build_box 共用。"""
    ids = DOMAIN_BOXES.get(domain)
    if ids is None:
        raise ValueError(
            f"未知盒域: {domain!r}（可用: {', '.join(sorted(DOMAIN_BOXES))}）")
    rows: list[tuple[str, str]] = []
    for bid in ids:
        text = render_block(bid, ctx)
        if text is not None:
            rows.append((bid, text))
    return rows


def build_box(domain: str, ctx: BlockContext) -> str:
    """装配会话级 system prompt（一次拼死; 每轮复用, 逐字节稳定）。"""
    return "\n\n".join(text for _, text in box_chunks(domain, ctx))
