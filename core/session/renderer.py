# -*- coding: utf-8 -*-
"""事件流派生视图 — 喂 LLM / 回放过滤 / 状态推导 / brain 时间线。

设计（core/DESIGN_SAVE.md §4.2/§4.6/§六）: **events.jsonl 是唯一真源**,
消息 / 回放 / brain 全是实时渲染, 不落盘（无冗余）:

    render_events     → [{role, content}]（恢复/继续喂 LLM; 与引擎 history 格式一致:
                        mmt = "[动作名] 回复", bond = **叙事提取**（句段行 + 句末 emotion,
                        2026-09-05 统一窗口定稿——见 render_bond_scene_text/window_messages）
    filter_bond       → type=bond 事件（回放源; 消费方转 BondScene, 本模块不 import bond 防循环）
    session_status    → {ended, in_vn, parent_session_id, vn_state}（marker 推导, 无状态机; parent 恒 None, 单流兼容）
    render_timeline   → 叙事时间线文本（brain 消化, 含板块标签）

事件 payload 约定（引擎接入时遵守）:
    mmt 事件:   {player, reply, ...} —— 同轮动作列表只有**第一个动作**带 player
                （同轮后续动作 player 空, render 自然去重; 2026-08-23 定稿）
    bond 事件:  {input, paragraphs(含内联 emotion), choices, picked, place, ...} —— input=本场触发输入
"""

from __future__ import annotations

from typing import Any

from core.session.events import (
    M_MEMORIAL_ENTER,
    M_MEMORIAL_EXIT,
    M_SESSION_END,
    M_VN_ABANDON,
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
from contract.records import render_records
from contract.timeline_index import REC_PICKED, format_event, format_record

#: brain 时间线的板块标签
_LABELS: dict[str, str] = {
    TYPE_MMT: "【MMT对话】",
    TYPE_BOND: "【羁绊剧情】",
    TYPE_L2D: "【L2D生成】",
    TYPE_OFFICIAL: "【官方剧情】",
}


def render_bond_scene_text(payload: dict[str, Any]) -> str:
    """bond 事件 payload → 叙事文本（2026-09-05 统一上下文窗口定稿, DESIGN_CONTEXT_WINDOW §2.1）。

    **记录流 v2（2026-09-10, P0-5）**: payload 带 `records` 时走记录渲染
    （`contract.records.render_records`）——说话人前缀用**记录里的取值**
    （角色 id / 老师 / 旁白无前缀），群内未选候选不出现，`picked` 非空则在群位置
    **物化**为一条 `老师：{picked}`。因为只看 payload、不看外部名字表，
    live 历史与 resume/回放**逐字节同形**（构造性成立）。

    旧契约 payload（无 records）保持原行为（旧档回放冻结不改）:
        契约层 paragraphs = **切分后句段**——每行 `{text}（{emotion}）`
        （emotion 随行保留: 词表键不翻译, 回放表情时间轴基础; 缺失 → 不标）;
        inner（内心独白）→ 独立行; title → `「{title}」`;
        choices + picked → （选项: … / 选择了: …）; is_end → （本章结束）。
    返回 "" = 无可渲染叙事。
    """
    records = payload.get("records")
    if isinstance(records, list) and records:
        text = render_records(
            [r for r in records if isinstance(r, dict)],
            choices=payload.get("choices") or (),
            picked=payload.get("picked") or "")
        title = payload.get("title")
        if isinstance(title, str) and title.strip():
            text = f"{title.strip()}\n{text}" if text else title.strip()
        return text

    lines: list[str] = []
    title = payload.get("title")
    if isinstance(title, str) and title.strip():
        lines.append(f"「{title.strip()}」")
    paras = payload.get("paragraphs")
    if isinstance(paras, str):
        paras = [paras]                                  # 兼容裸字符串段落
    if isinstance(paras, list):
        for p in paras:
            if isinstance(p, str):
                if p.strip():
                    lines.append(p.strip())
                continue
            if not isinstance(p, dict):
                continue
            text = p.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            line = text.strip()
            emo = p.get("emotion")
            if isinstance(emo, str) and emo.strip():
                line += f"（{emo.strip()}）"
            lines.append(line)
            inner = p.get("inner")
            if isinstance(inner, str) and inner.strip():
                lines.append(f"（{inner.strip()}）")
    choices = payload.get("choices")
    choice_texts: list[str] = []
    if isinstance(choices, list):
        for c in choices:
            if isinstance(c, str) and c.strip():
                choice_texts.append(c.strip())
    if choice_texts:
        lines.append("（选项: " + " / ".join(choice_texts) + "）")
        picked = payload.get("picked")
        if isinstance(picked, str) and picked.strip() and picked != "（继续）":
            lines.append(f"（选择了: {picked.strip()}）")
    if payload.get("is_end"):
        lines.append("（本章结束）")
    return "\n".join(lines)


def render_events(events: list[Event]) -> list[dict[str, str]]:
    """事件流 → LLM 消息（[{role, content}]）, 与引擎 history 格式一致。

    mmt:   user=player（同轮后续动作 player 空 → 不重复）; assistant="[动作名] reply"
    bond:  user=input（本场触发输入）; assistant=叙事提取（render_bond_scene_text——
           2026-09-05: 不再整 payload JSON——上下文只放"发生过什么的叙事+情绪",
           不放 place/emotion 外的结构元数据）
    l2d:   payload 带 paragraphs（纪念时刻文字）→ 同提取, 行首标（画面）; 纯资产 → 跳过
    marker/affection: 跳过（状态标记与系统结算不进对话上下文）
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
            if isinstance(inp, str) and inp.strip():
                out.append({"role": "user", "content": inp.strip()})
            text = render_bond_scene_text(e.payload)
            if text:
                out.append({"role": "assistant", "content": text})
        elif e.type == TYPE_L2D:
            # 纪念时刻（预留）: 文字进上下文（她是这段剧情的亲历者）, 图不进
            text = render_bond_scene_text(e.payload)
            if text:
                out.append({"role": "assistant",
                            "content": "（纪念画面出现——）\n" + text})
        # marker / affection / 其余 → 跳过
    return out


def window_messages(events: list[Event], *, max_units: int = 120) -> list[dict[str, str]]:
    """统一上下文窗口（2026-09-05 定稿, DESIGN_CONTEXT_WINDOW §3）: 从事件流倒序
    装填最近叙事, 预算 = 叙事单元数（一行 = 一单元: mmt reply 切块 / bond 句段行）。

    超预算 → 丢更老的整条消息（整单元驱逐, 不半切）。返回与 render_events 同格式
    （用户/历史直接灌 _history——任何域的唯一上下文入口）。
    注: 超长单行（>500 字异常）按 1 单元宽松计——切分器已限句段/切块长度,
    实际极少出现; 句子化折计留待滑动窗口升级（TODO 未来项）。
    """
    msgs = render_events(events)
    kept: list[dict[str, str]] = []
    units = 0
    for m in reversed(msgs):
        u = len(str(m["content"]).split("\n"))
        if kept and units + u > max_units:
            break
        units += u
        kept.append(m)
    return list(reversed(kept))

def filter_bond(events: list[Event]) -> list[Event]:
    """过滤 type=bond 事件（回放源; 消费方逐条 BondScene.from_dict(payload) 渲染）。"""
    return [e for e in events if e.type == TYPE_BOND]


def session_status(events: list[Event]) -> dict[str, Any]:
    """从 marker 事件推导会话状态（无状态机, DESIGN_SAVE.md §5.1）。

    Returns:
        ended              — 有 session_end marker
        in_vn              — 最后 vn_enter 之后无 vn_exit/vn_abandon/session_end
                              （vn_abandon 视同收尾——废弃段关闭, 2026-09-07）
        in_memorial        — 纪念子模式中（§4.7）: 最后 memorial_enter 之后
                             无 memorial_exit/session_end
        parent_session_id  — 恒 None（2026-08-24 单流无子会话, 保留字段兼容）
        vn_state           — 最后一个 vn_state marker 的 VNState.to_dict()（None = 无）
    """
    ms = [e for e in events if e.is_marker]
    ended = any(m.subtype == M_SESSION_END for m in ms)

    # in_vn = 仍有未关的 vn_enter（2026-09-07 改为 open 栈推导——定向废弃只关
    # 指定段后, 更早的在押段仍应推导 in_vn=True）:
    #   vn_enter      → 入栈
    #   vn_exit       → 关最近一个在押段
    #   vn_abandon    → 按 payload.start_seq 关指定段（无 start → 关最近, 兼容）
    #   session_end   → 全关
    in_vn = False
    parent_session_id: str | None = None
    opens: list = []
    last_enter_payload: dict = {}
    for m in ms:
        if m.subtype == M_VN_ENTER:
            opens.append(m)
            last_enter_payload = m.payload      # parent 语义: 最近一次 vn_enter（无论开合）
        elif m.subtype == M_VN_EXIT:
            if opens:
                opens.pop()
        elif m.subtype == M_VN_ABANDON:
            try:
                s = int(m.payload.get("start_seq", 0) or 0)
            except (TypeError, ValueError):
                s = 0
            if s > 0:
                opens = [o for o in opens if o.seq != s]
            elif opens:
                opens.pop()
        elif m.subtype == M_SESSION_END:
            opens = []
    in_vn = bool(opens)
    p = last_enter_payload.get("parent_session_id")
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


def render_timeline(events: list[Event], *, indexed: bool = False) -> str:
    """事件流 → 叙事时间线文本（brain 消化输入, §4.6; 含板块标签, **不截断**）。

    设计（2026-08-27 修正）:
    - **紧凑文本, 非 jsonl**——省 token（无 JSON 键名/结构开销）; 叙事流不被
      数据结构打断（角色扮演语境, 不 rigid）。
    - **表情标注（2026-08-28 收敛）**: bond 段落显式带 emotion → 段落后 ` (emotion)`——
      digest 提炼时"她当时的表情/反应"是难忘细节的原料（人设感记忆, 不 OOC 靠记忆不靠状态）;
      缺省段不标注（契约语义: 缺省 = 延续上一段, 见 digest.md 输入说明）。
    - **两形态（T14, 2026-09-15）**:

      | `indexed` | 形态 | 消费者 |
      |---|---|---|
      | `False`（默认） | **每事件一行**, 记录用 `" / "` 拼 | 上下文窗口 / 回放（`window_messages`、CLI） |
      | `True` | **每记录一行**, 行首带行索引 | `digest.py`（Round A 唯一输入） |

      ⚠️ 2026-09-21: 该表原把 `consolidation.py`（digest v1 legacy）列为 `False` 形态的
      消费者——v1 记忆已整体删除, 现役消费者是上下文窗口/回放。

      `indexed=True` 的形态（词汇表见 `contract/timeline_index.py`）::

          [28] 【羁绊剧情】                 ← 事件头: 板指针 event_seq 抄这个
          [28.0] ……这块，给你。 (smile)     ← 记录: verbatim 抄这个
          [28.1] 库呼呼～
          [28.p] 老师: 要不要再来一块？      ← 玩家裁决行
          [20] 【MMT对话】
          [20.0] 玩家: 你好呀
          [20.1] 角色: 库呼呼～老师你可千万别告诉她哦

      **为什么记录级**（2026-09-15 实测）: `verbatim` 的语义是"印象最深的一句原话",
      而"一句"是**记录**不是事件（一板 3~12 条记录）。代价实测 **×0.92 / ×0.98**
      （mutsuki / haruka 真机时间线）——**比现行还省**, 因为 `" / "` 分隔符
      与 `[seq N]` 标签被短索引替掉了。所以这是纯收益, 不是 trade-off。

      **说话人前缀刻意不加**: 记录文本原样保留（不加 `角色id:` 前缀）——
      那是**另一个**改动（会同时改变 Round A 看到的全部内容）, 与本变更不同批。

    - **不截断（2026-09-13, Q26 落地）**: 原 `max_paragraph_chars=120` 已删。它是
      "防出厂记忆挤占窗口"的补丁, 而**补丁对象已死**（出厂记忆直注、不进 wiki）。
      实测板均 73~163 字、阈值正卡在之上一点, 砍的全是正常板——且砍掉的正是
      **全章情感落点**（如 haruka 板 6 的 `outburst` 与收束 `smile`）与**玩家裁决行**。
      `verbatim`「印象最深的一句原话, 逐字复制」在 12 条大板上摊到每记录 ≈10 字,
      **物理上常常拿不到**。删后输入仅 ×1.11~×1.50（§8.1 实测）。
      本函数是 **digest Round A 的唯一输入**——不截断 = LLM 看得见完整情绪弧。

    ⚠️ **`include_seq` 参数已删**（T14）: 它的旧语义是"每事件行前缀 `[seq N]`",
    唯一调用方是 digest——而那个前缀**从来没有被消费**（`event_seq` 被
    `_clean_episode` 丢弃 + 被 `digest.py` 覆写成常量 `[interact_max]`）。
    现在换成真正可指的 `indexed`, 不留死旋钮。
    """
    lines: list[str] = []
    for e in events:
        if e.is_marker:
            continue
        label = _LABELS.get(e.type, f"【{e.type}】")
        if e.type == TYPE_MMT:
            player = e.payload.get("player", "")
            reply = e.payload.get("reply", "")
            if indexed:
                lines.append(f"{format_event(e.seq)} {label}")
                lines.append(f"{format_record(e.seq, 0)} 玩家: {player or '—'}")
                if reply:
                    lines.append(f"{format_record(e.seq, 1)} 角色: {reply}")
                continue
            parts = [f"玩家: {player or '—'}"]
            if reply:
                parts.append(f"角色: {reply}")
            lines.append(f"{label} {' / '.join(parts)}")
        elif e.type == TYPE_BOND:
            paras = e.payload.get("paragraphs", [])
            picked = e.payload.get("picked")
            # 玩家裁决行（记录流 v2: 物化成 `老师：X` 记录, 但不在派生 paragraphs 里）
            # ——digest 消化"这段戏说了什么"时, 玩家那句同样是内容（v1 也漏, 顺手补）
            has_picked = isinstance(picked, str) and bool(picked.strip())
            if indexed:
                lines.append(f"{format_event(e.seq)} {label}")
                for i, p in enumerate(paras):
                    t = p.get("text", "") if isinstance(p, dict) else str(p)
                    if not isinstance(t, str) or not t:
                        continue
                    emo = p.get("emotion") if isinstance(p, dict) else None
                    if isinstance(emo, str) and emo.strip():
                        t = f"{t} ({emo.strip()})"
                    # 索引 = `paragraphs` 的**数组下标**（跳过空项也保留原下标）——
                    # 地址必须指向真源里的位置, 不能是"渲染后的第几条"
                    lines.append(f"{format_record(e.seq, i)} {t}")
                if has_picked:
                    lines.append(f"{format_record(e.seq, REC_PICKED)} 老师: {picked.strip()}")
                continue
            texts = []
            for p in paras:
                t = p.get("text", "") if isinstance(p, dict) else str(p)
                if not isinstance(t, str) or not t:
                    continue
                emo = p.get("emotion") if isinstance(p, dict) else None
                if isinstance(emo, str) and emo.strip():
                    texts.append(f"{t} ({emo.strip()})")
                else:
                    texts.append(t)
            if has_picked:
                texts.append(f"老师: {picked.strip()}")
            lines.append(f"{label} {' / '.join(texts)}")
        elif e.type == TYPE_L2D:
            imgs = e.payload.get("images", [])
            img = imgs[0] if isinstance(imgs, list) and imgs else "?"
            if indexed:
                lines.append(f"{format_event(e.seq)} {label}")
                lines.append(f"{format_record(e.seq, 0)} 生成: {img}")
                continue
            lines.append(f"{label} 生成: {img}")
    return "\n".join(lines)
