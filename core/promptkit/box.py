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
