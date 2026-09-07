# -*- coding: utf-8 -*-
"""describe() — 实际注入报表（DESIGN_PROMPTKIT §3 report.py, Phase 1 只读）。

把"某域当前实际注入了什么"渲染成 md——与 docs/PROMPT_INJECTION_MAP.md 同构,
是文档的代码化落点（防漂移: 装配改 = 报表跟着变, 地图文档更新有据可依）。
Phase 2 起把每轮动态尾（注记/卡）并入报表。
"""
from __future__ import annotations

from core.promptkit.blocks import BLOCK_DOC, BlockContext
from core.promptkit.box import DOMAIN_BOXES, box_chunks


def describe(domain: str, ctx: BlockContext) -> str:
    """渲染指定域的盒注入报表（块顺序 = DOMAIN_BOXES 声明）。"""
    ids = DOMAIN_BOXES.get(domain)
    if ids is None:
        raise ValueError(
            f"未知盒域: {domain!r}（可用: {', '.join(sorted(DOMAIN_BOXES))}）")
    rows = box_chunks(domain, ctx)
    lines = [
        f"# promptkit describe: {domain}（盒, 共 {len(ids)} 块声明 / {len(rows)} 块注入）",
        "",
        "| # | 块 id | 长度 | 说明 | 段首 |",
        "|---|---|---|---|---|",
    ]
    for i, (bid, text) in enumerate(rows, 1):
        head = text.split("\n")[0][:32].replace("|", "\\|").strip()
        doc = (BLOCK_DOC.get(bid) or "").replace("|", "\\|")
        lines.append(f"| {i} | {bid} | {len(text)} | {doc} | {head} |")
    absent = [bid for bid in ids if bid not in [b for b, _ in rows]]
    if absent:
        lines.append("")
        lines.append("缺席块（条件注入未命中）: " + ", ".join(absent))
    lines.append("")
    lines.append("注: 每轮动态尾（brain/注记/task 卡槽位）见 core.promptkit.tail "
                 ".round_messages 文档; task 卡 Phase 2 并入本报表。")
    return "\n".join(lines)
