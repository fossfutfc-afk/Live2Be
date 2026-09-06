# -*- coding: utf-8 -*-
"""事件流维护 — events.jsonl 的"补记式"自修正（不删旧行, 只追加宣告 + 读侧过滤）。

背景（2026-09-07 拍板）: 中断的羁绊段若被新章节压掉（从未续写/走完）= **废弃**,
内容视为"未发生"——必须从 LLM 上下文（窗口）与记忆（digest 输入）排除,
否则 AI 会带着半截旧章进新章、把未发生的剧情写进 wiki。

机制: 追加 marker `vn_abandon {start_seq, end_seq}` 宣告废弃区间（append-only,
旧行不动, 审计/回放保留完整）; 读侧 `exclude_abandoned()` 按区间滤掉 bond 事件。

段三态:
    vn_exit completed=True   → 正典（回放/续写/记忆都保留）
    vn_exit completed=False / 无收尾(open) → 中断候选（续同一段 or 回放续写）
    vn_abandon               → 废弃（上下文/记忆排除; 回放列表仅作档案标注）

本模块是唯一的"流维护"出口: 段扫描 / 自愈计划 / 废弃判定 / 区间过滤 全在此;
消费方（momotalk / bond / vn_cli / digest）只 import 纯函数, 不各自实现。

命令行（自愈旧数据, 默认 dry-run 只预览不写）:
    python -m core.session.maintenance [--root data] [--char igusa_haruka]
                                        [--mode heal|supersede] [--apply]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from core.session.events import (
    TYPE_BOND,
    TYPE_MARKER,
    M_VN_ENTER,
    M_VN_EXIT,
    M_VN_ABANDON,
    marker,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 段扫描（与 webgui.replay_attempts 同构的纯事件逻辑; 这里补 closing 类型）
# ---------------------------------------------------------------------------

def attempt_spans(events: list) -> list[dict]:
    """事件流 → 羁绊段清单（按 vn_enter 分段; 含关闭状态与场景计数）。

    每段: {enter_seq, close_seq(None=未关), close_kind(None|'exit'|'abandon'),
           completed(bool), title, scenes(int), range_start, range_end}
    close_kind='exit' 时 completed 取 payload; 'abandon' 一律废弃。
    """
    spans: list[dict] = []
    cur: dict | None = None

    def close(cur_, kind, seq, completed=False):
        cur_["close_seq"] = seq
        cur_["close_kind"] = kind
        cur_["completed"] = bool(completed) if kind == "exit" else False
        spans.append(cur_)

    for e in events:
        if not e.is_marker:
            if cur is not None:
                cur["range_end"] = e.seq          # 段尾 = 段内最后一条内容事件
                if e.type == TYPE_BOND:
                    cur["scenes"] += 1
            continue
        if e.subtype == M_VN_ENTER:
            if cur is not None:
                spans.append(cur)          # 未关 → 段保持 open（interrupted）
            cur = {"enter_seq": e.seq, "close_seq": None, "close_kind": None,
                   "completed": False, "title": str(e.payload.get("chapter_title") or ""),
                   "scenes": 0, "range_start": e.seq, "range_end": e.seq}
        elif cur is not None:
            if e.subtype == M_VN_EXIT:
                close(cur, "exit", e.seq,
                      bool(e.payload.get("completed")))
                cur = None
            elif e.subtype == M_VN_ABANDON:
                close(cur, "abandon", e.seq)
                cur = None
    if cur is not None:
        spans.append(cur)                  # 流尾未关 → open
    return spans


def abandoned_ranges(events: list) -> list[tuple[int, int]]:
    """已宣告的废弃区间（含/不含端点均可; 过滤按 [start, end] 闭区间内 bond 事件）。"""
    out: list[tuple[int, int]] = []
    for e in events:
        if e.is_marker and e.subtype == M_VN_ABANDON:
            try:
                out.append((int(e.payload.get("start_seq", 0)),
                            int(e.payload.get("end_seq", 0))))
            except (TypeError, ValueError):
                continue
    return out


def exclude_abandoned(events: list) -> list:
    """读侧过滤: 丢弃废弃区间内的 **bond 事件**（mmt/对白保留——真实发生过的聊天;
    marker 保留——推导与分段仍需边界; 消费方自行忽略）。无标记 → 原样返回。"""
    ranges = abandoned_ranges(events)
    if not ranges:
        return list(events)
    out = []
    for e in events:
        if e.type == TYPE_BOND and any(
                a <= e.seq <= b for a, b in ranges):
            continue
        out.append(e)
    return out


# ---------------------------------------------------------------------------
# 计划（纯推导, 不写）: heal = 旧数据自愈; supersede = 新章节压掉所有在押段
# ---------------------------------------------------------------------------

def _substantive(sp: dict) -> bool:
    """段是否有"内容"（场景 > 0 或有章节标题）——空壳重启段判定用。"""
    return sp["scenes"] > 0 or bool(sp["title"])


def heal_plan(events: list) -> list[tuple[int, int, str]]:
    """旧数据自愈: 保留"最新一条有内容的 open 段"为续写目标, 其余 **有内容**
    open 段补 vn_abandon（空壳段无可弃内容, 由回放接入时定向压掉——见
    close_other_opens_plan）。返回 [(start_seq, end_seq, note)]。
    """
    opens = [sp for sp in attempt_spans(events) if sp["close_kind"] is None]
    if not opens:
        return []
    # 从尾向前找最新有内容段（不关闭它）
    target = None
    for sp in reversed(opens):
        if _substantive(sp):
            target = sp
            break
    plan = []
    for sp in opens:
        if sp is target:
            continue
        if sp["range_start"] >= sp["range_end"]:
            continue                              # 空壳: 无内容可弃
        plan.append((sp["range_start"], sp["range_end"],
                     f"heal: 被更新的羁绊段压掉（{sp['title'] or '无标题'}）"))
    return plan


def supersede_plan(events: list) -> list[tuple[int, int, str]]:
    """新章节开始（新 vn_enter 写入前）: 压掉**全部** open 在押段（含空壳——
    空区间标记仅作关闭宣告, 过滤天然无操作）。"""
    plan = []
    for sp in attempt_spans(events):
        if sp["close_kind"] is None:
            plan.append((sp["range_start"], sp["range_end"],
                         f"supersede: 新章节开启（旧段 {sp['title'] or '无标题'} 废弃）"))
    return plan


def close_other_opens_plan(events: list, keep_enter_seq: int) -> list[tuple[int, int, str]]:
    """回放续写接入: 只保留 keep_enter_seq 的段为续写目标, 其余 open 段全部
    压掉（含空壳）——否则续写事件会按 vn_enter 归属追加到**最新空壳段**,
    分段与记忆归属错乱（2026-09-07 实测修正）。"""
    plan = []
    for sp in attempt_spans(events):
        if sp["close_kind"] is None and sp["enter_seq"] != keep_enter_seq:
            plan.append((sp["range_start"], sp["range_end"],
                         f"replay-adopt: 保留段 {keep_enter_seq}, 其余在押废弃"))
    return plan


# ---------------------------------------------------------------------------
# 应用（store/文件写入, 幂等）
# ---------------------------------------------------------------------------

def apply_plan(append_fn, plan: list[tuple[int, int, str]]) -> int:
    """把计划写成 vn_abandon marker。append_fn(event) 由调用方提供（store 或文件）。
    幂等: 已存在同 start_seq 的 abandon → 跳过。返回实际写入数。"""
    written = 0
    for start_seq, end_seq, note in plan:
        if start_seq >= end_seq:
            continue                       # 空段（无任何内容）不标
        append_fn(marker(M_VN_ABANDON, {
            "start_seq": start_seq, "end_seq": end_seq,
            "note": note,
        }))
        written += 1
    return written


def abandon_open_attempts(store, char_id: str, session_id: str = "") -> int:
    """store 级便捷（新章节开启时压掉全部 open 在押段）: vn_abandon 宣告, 幂等。

    返回写入数。写失败静默跳过（宁缺勿错——过滤缺失只是上下文脏, 不阻断剧情）。
    """
    return _apply_store_plan(store, char_id, session_id,
                             supersede_plan)


def abandon_opens_except(store, char_id: str, session_id: str,
                         keep_enter_seq: int) -> int:
    """store 级便捷（回放续写接入）: 保留 keep_enter_seq 段, 压掉其余 open。"""
    return _apply_store_plan(store, char_id, session_id,
                             lambda evs: close_other_opens_plan(
                                 evs, keep_enter_seq))


def _apply_store_plan(store, char_id: str, session_id: str,
                      planner) -> int:
    """通用: planner(events) → plan → 逐个 append vn_abandon（幂等: 已关段自然
    不在计划; 空区间（start==end）也写——作关闭宣告, 过滤无操作）。"""
    try:
        evs = store.events(char_id, session_id)
    except Exception:                                # noqa: BLE001 — 读失败跳过
        return 0
    written = 0
    for start_seq, end_seq, note in planner(evs):
        try:
            store.append_marker(
                char_id, session_id, M_VN_ABANDON,
                {"start_seq": start_seq, "end_seq": end_seq, "note": note})
            written += 1
        except Exception:                            # noqa: BLE001 — 单条失败跳过
            continue
    return written


def _existing_abandon_starts(events: list) -> set[int]:
    return {int(e.payload.get("start_seq", 0))
            for e in events if e.is_marker and e.subtype == M_VN_ABANDON}


# ---------------------------------------------------------------------------
# 命令行（旧数据自愈; 默认 dry-run）
# ---------------------------------------------------------------------------

def _discover(root: Path) -> list[tuple[Path, str]]:
    """root/worlds/*/characters/*/meta.json → [(soul_dir, char_id)]（含 events 文件）。"""
    found: list[tuple[Path, str]] = []
    for meta in (root / "worlds").glob("*/characters/*/meta.json"):
        soul = meta.parent / "soul"
        if (soul / "events.jsonl").is_file():
            found.append((soul, meta.parent.name))
    return found


def _read_events(soul: Path) -> list:
    from core.session.events import parse_events
    from core.session.io import read_jsonl
    return parse_events(read_jsonl(soul / "events.jsonl"))


def _append(soul: Path, ev) -> None:
    from core.session.io import append_jsonl
    append_jsonl(soul / "events.jsonl", ev.to_dict())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="事件流维护: 中断羁绊段废弃自愈")
    ap.add_argument("--root", default=str(PROJECT_ROOT / "data"),
                    help="data 根（默认项目 data/）")
    ap.add_argument("--char", default="",
                    help="只处理指定角色（默认全部自动发现）")
    ap.add_argument("--mode", choices=("heal", "supersede"), default="heal")
    ap.add_argument("--apply", action="store_true",
                    help="真正写 vn_abandon 标记（缺省 dry-run 只打印计划）")
    args = ap.parse_args(argv)

    root = Path(args.root)
    targets = [(soul, c) for soul, c in _discover(root)
               if not args.char or c == args.char]
    if not targets:
        print(f"未发现 events.jsonl: {root / 'worlds'}/*/characters/*/soul/")
        return 1
    total = 0
    for soul, char in sorted(targets, key=lambda t: t[1]):
        evs = _read_events(soul)
        plan = (supersede_plan if args.mode == "supersede" else heal_plan)(evs)
        existing = _existing_abandon_starts(evs)
        plan = [(s, e, n) for s, e, n in plan
                if s not in existing and s < e]      # 幂等: 已标/空段跳过
        if not plan:
            print(f"{char}: 无需修正（{args.mode}）")
            continue
        print(f"{char}: 计划废弃 {len(plan)} 段")
        for s, e, note in plan:
            print(f"    vn_abandon {s}..{e}  {note}")
        if args.apply:
            written = apply_plan(lambda ev: _append(soul, ev), plan)
            total += written
            print(f"    → 已写入 {written} 个标记（文件: {soul / 'events.jsonl'}）")
    print(f"合计写入 {total}（dry-run 模式为 0; 加 --apply 生效）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
