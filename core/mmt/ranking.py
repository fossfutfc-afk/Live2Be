# -*- coding: utf-8 -*-
"""MMT 列表排序（**统一文件**——排序逻辑都在这, 未来加名字/生日/未读排序也加这里）。

当前两种模式:
  - SORT_RECENT（最新活跃）: 哪个角色最近在聊排前面（BA 未读列表同款逻辑）;
    无活跃记录 → 排最后（stable, 保持白名单顺序兜底）。
  - SORT_AFFECTION（好感度）: per-char 好感聚合值（best_affection——"你和她
    最好的那一次关系"）倒序; 无好感 → 排最后。

排序是纯函数（数据由调用方提供: recent/affection map）——不碰 IO, 可单测。
"""
from __future__ import annotations

#: 排序模式常量
SORT_RECENT = "recent"           # 最新活跃（默认）
SORT_AFFECTION = "affection"     # 好感度（per-char 聚合, 最高 session）
SORT_MODES: tuple[str, ...] = (SORT_RECENT, SORT_AFFECTION)


def best_affection(session_affections: list[dict | None] | None) -> dict | None:
    """per-char 好感聚合: 多个 session 的好感取 **exp 最高** 的一个。

    语义: 该角色所有世界线中"你和她最好的一次"——平行世界下 per-char 的可比值
    （DESIGN 决策: 好感排序用最高 session, 而非跨世界线平均/总和）。
    session_affections: [{level, exp} | None, ...]。
        **None = 该 session 无好感事件**（跳过）;
        `{level: 1, exp: 0}` = 有事件但净变化 ≤0（**参与比较**——"中性/已恶化"
        是一次真实状态, 与"无数据"不同, 2026-09-13 §3.3.3）。
    全 None/空 → None。
    """
    best: dict | None = None
    for aff in session_affections or []:
        if not aff:
            continue
        if best is None or int(aff.get("exp", 0) or 0) > int(best.get("exp", 0) or 0):
            best = aff
    return best


def sort_characters(
    chars: list[dict],
    mode: str = SORT_RECENT,
    *,
    recent: dict[str, str] | None = None,
    affection: dict[str, dict] | None = None,
) -> list[dict]:
    """对 MMT 角色列表排序（返回新列表, 不修改入参）。

    Args:
        chars: [{id, ...}, ...]（MMT 路由已填充的成员列表）。
        mode: SORT_RECENT / SORT_AFFECTION（未知 → SORT_RECENT 兜底）。
        recent: {char_id: ISO 时间串} 最近活跃时间——倒序（ISO 可字典序比较）。
        affection: {char_id: {level, exp}} per-char 好感聚合——按 exp 倒序。

    无对应数据（recent 缺失 / 无好感）→ 排最后; 同为"最后"的保持白名单相对顺序
    （sorted 稳定）。
    """
    if mode == SORT_AFFECTION:
        # 按好感 exp 倒序; exp 相同 → 保持白名单原序（sorted 稳定, 作者编排优先）
        return sorted(
            chars,
            key=lambda c: -int((affection or {}).get(c["id"], {}).get("exp", 0) or 0),
        )
    return sorted(
        chars,
        key=lambda c: (recent or {}).get(c["id"], ""),
        reverse=True,
    )
