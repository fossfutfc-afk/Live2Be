# -*- coding: utf-8 -*-
"""事件流派生视图 — 喂 LLM / 回放过滤 / 状态推导 / brain 时间线。

设计（core/DESIGN_SAVE.md §4.2/§4.6/§六）: **events.jsonl 是唯一真源**,
消息 / 回放 / brain 全是实时渲染, 不落盘（无冗余）:

    render_events     → [{role, content}]（恢复/继续喂 LLM; 与引擎 history 格式一致:
                        mmt = "[动作名] 回复", bond = 紧凑 payload JSON）
    filter_bond       → type=bond 事件（回放源; 消费方转 BondScene, 本模块不 import bond 防循环）
    session_status    → {ended, in_vn, parent_session_id, vn_state}（marker 推导, 无状态机; parent 恒 None, 单流兼容）
    render_timeline   → 叙事时间线文本（brain 消化, 含板块标签）

事件 payload 约定（引擎接入时遵守）:
    mmt 事件:   {player, reply, ...} —— 同轮动作列表只有**第一个动作**带 player
                （同轮后续动作 player 空, render 自然去重; 2026-08-23 定稿）
    bond 事件:  {input, paragraphs(含内联 emotion), choices, picked, place, ...} —— input=本场触发输入
"""

from __future__ import annotations

import json
from typing import Any

from core.session.events import (
    M_MEMORIAL_ENTER,
    M_MEMORIAL_EXIT,
    M_SESSION_END,
    M_SESSION_START,
    M_VN_ENTER,
    M_VN_EXIT,
    M_VN_STATE,
    TYPE_BOND,
    TYPE_L2D,
    TYPE_MMT,
    TYPE_OFFICIAL,
    Event,
)
from core.session.models import VNState
from core.ui.text_processors import _strip_action_brackets, split_reply_chunks

#: brain 时间线的板块标签
_LABELS: dict[str, str] = {
    TYPE_MMT: "【MMT对话】",
    TYPE_BOND: "【羁绊剧情】",
    TYPE_L2D: "【L2D生成】",
    TYPE_OFFICIAL: "【官方剧情】",
}


def render_events(events: list[Event]) -> list[dict[str, str]]:
    """事件流 → LLM 消息（[{role, content}]）, 与引擎 history 格式一致。

    mmt:   user=player（同轮后续动作 player 空 → 不重复）; assistant="[动作名] reply"
    bond:  user=input（本场触发输入）; assistant=紧凑 payload JSON（与 bond_story 历史一致）
    marker/l2d: 跳过（状态标记与资产引用不进对话上下文）
    """
    out: list[dict[str, str]] = []
    for e in events:
        if e.type == TYPE_MMT:
            player = e.payload.get("player", "")
            reply = e.payload.get("reply", "")
            if isinstance(player, str) and player:
                out.append({"role": "user", "content": player})
            # 切片回灌: 角色回复去括号 → split_reply_chunks 切块（模拟逐条消息,
            # 让 LLM 看到的上下文更贴近真实聊天, 把握语境）; 只第一块带动作名前缀
            text = _strip_action_brackets(reply).strip() if isinstance(reply, str) else ""
            chunks = split_reply_chunks(text) if text else []
            if chunks:
                for i, chunk in enumerate(chunks):
                    prefix = f"[{e.subtype}] " if i == 0 else ""
                    out.append({"role": "assistant", "content": f"{prefix}{chunk}"})
            else:
                out.append({"role": "assistant", "content": f"[{e.subtype}]"})
        elif e.type == TYPE_BOND:
            inp = e.payload.get("input", "")
            if isinstance(inp, str) and inp:
                out.append({"role": "user", "content": inp})
            out.append({"role": "assistant", "content": json.dumps(
                e.payload, ensure_ascii=False, separators=(",", ":"))})
        # marker / l2d → 跳过（l2d 是资产引用, 恢复时无需告知 LLM）
    return out

def filter_bond(events: list[Event]) -> list[Event]:
    """过滤 type=bond 事件（回放源; 消费方逐条 BondScene.from_dict(payload) 渲染）。"""
    return [e for e in events if e.type == TYPE_BOND]


def session_status(events: list[Event]) -> dict[str, Any]:
    """从 marker 事件推导会话状态（无状态机, DESIGN_SAVE.md §5.1）。

    Returns:
        ended              — 有 session_end marker
        in_vn              — 最后 vn_enter 之后无 vn_exit/session_end
        in_memorial        — 纪念子模式中（§4.7）: 最后 memorial_enter 之后
                             无 memorial_exit/session_end
        parent_session_id  — 恒 None（2026-08-24 单流无子会话, 保留字段兼容）
        vn_state           — 最后一个 vn_state marker 的 VNState.to_dict()（None = 无）
    """
    ms = [e for e in events if e.is_marker]
    ended = any(m.subtype == M_SESSION_END for m in ms)

    in_vn = False
    parent_session_id: str | None = None
    enter_idxs = [i for i, m in enumerate(ms) if m.subtype == M_VN_ENTER]
    if enter_idxs:
        last = enter_idxs[-1]
        in_vn = not any(
            m.subtype in (M_VN_EXIT, M_SESSION_END) for m in ms[last + 1:])
        p = ms[last].payload.get("parent_session_id")
        parent_session_id = p if isinstance(p, str) and p else None

    # 纪念子模式状态（§4.7: enter 后 exit 前, 中断恢复据此 resume 到纪念场景）
    in_memorial = False
    m_enter_idxs = [i for i, m in enumerate(ms) if m.subtype == M_MEMORIAL_ENTER]
    if m_enter_idxs:
        last = m_enter_idxs[-1]
        in_memorial = not any(
            m.subtype in (M_MEMORIAL_EXIT, M_SESSION_END) for m in ms[last + 1:])

    vn_state: dict | None = None
    for m in reversed(ms):
        if m.subtype == M_VN_STATE:
            vn_state = VNState.from_dict(m.payload).to_dict()
            break

    return {
        "ended": ended,
        "in_vn": in_vn,
        "in_memorial": in_memorial,
        "parent_session_id": parent_session_id,
        "vn_state": vn_state,
    }


def render_timeline(events: list[Event], *, max_paragraph_chars: int = 120) -> str:
    """事件流 → 叙事时间线文本（brain 消化输入, §4.6; 含板块标签, 段落截断）。

    设计（2026-08-27 修正）:
    - **每事件一行**（行号 = 事件序号, 1 起）——digest 的 index.position 按行号
      引用: LLM 顺序阅读天然理解"第几个事件", 不需要也不应该感知真实 seq
      （引擎负责 position → 真实 seq 映射, 权威）。
    - **紧凑文本, 非 jsonl**——省 token（无 JSON 键名/结构开销）; 叙事流不被
      数据结构打断（角色扮演语境, 不 rigid）。
    """
    lines: list[str] = []
    for e in events:
        if e.is_marker:
            continue
        label = _LABELS.get(e.type, f"【{e.type}】")
        if e.type == TYPE_MMT:
            player = e.payload.get("player", "")
            reply = e.payload.get("reply", "")
            parts = [f"玩家: {player or '—'}"]
            if reply:
                parts.append(f"角色: {reply}")
            lines.append(f"{label} {' / '.join(parts)}")
        elif e.type == TYPE_BOND:
            paras = e.payload.get("paragraphs", [])
            texts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in paras]
            text = " / ".join(texts)
            if len(text) > max_paragraph_chars:
                text = text[:max_paragraph_chars] + "…"
            lines.append(f"{label} {text}")
        elif e.type == TYPE_L2D:
            imgs = e.payload.get("images", [])
            img = imgs[0] if isinstance(imgs, list) and imgs else "?"
            lines.append(f"{label} 生成: {img}")
    return "\n".join(lines)
