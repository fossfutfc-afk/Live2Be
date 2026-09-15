# -*- coding: utf-8 -*-
"""官方剧本 → Live2Be 事件流（真语料, 用于真机 digest 验证）—— 定稿版。

实测形态（ba_debug_sel.py / ba_debug_elems.py）:
  一条记录一个指令, 每类指令的"块类型"由**首个 token** 决定:
    `#title;X`      标题
    `#na;(…)`       旁白
    `#st;{pos};{mode};{n};{txt};{delay}`   台词碎片（一句跨多条, 需拼接）
    `N;{char};{emo};{txt}`  ← **以数字开头**（如 `3;하루카;04;…`）, 也是台词/选项
    `[sN] {txt}` / `[nsN] {txt}`  台词槽 / 动作槽（**选项文本就在这**）
    `#wait;` `#clearST` `#all;hide` `#3;em;[?!]`  指令
  表态点: `SelectionGroup=N` 挂在**落地记录**上; 连续两个编号若文本逐字相同
    → 同一个表态点复用反应段（取第一条）。

输出: 与 `core.session.events` 同构的事件 dict 列表。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_WA = re.compile(r"\[wa:\d+\]")
_ST_PREFIX = re.compile(r"^#st;(?:\[[^\]]*\];)?(?:[a-z_]+;)?(?:\d+;)?")
_ST_CHAR = re.compile(r"^(\d+);([^;]*);([^;]*);(.*)$", re.S)   # `3;하루카;04;文本`
_SLOT = re.compile(r"^\[(n?s)(\d*)\]\s*")
_SPRITE = re.compile(r"^#3;")
_CMD = re.compile(r"^#[a-zA-Z]+;?")


def _clean(t: str) -> str:
    t = _WA.sub("", t)
    t = t.replace("⏎", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", t).strip()


def elements(recs: list[dict]) -> list[dict]:
    """原始记录 → 叙事元素。

    kind: narration | line | option | reaction | title
    reaction 带 sg = SelectionGroup 值（落地记录）。
    """
    out: list[dict] = []
    buf: list[str] = []                      # 台词碎片缓冲

    def flush() -> None:
        nonlocal buf
        if buf:
            t = _clean("".join(buf))
            buf = []
            if t:
                out.append({"kind": "line", "text": t})

    for r in recs:
        raw = r["script"] or ""
        sg = r["fields"].get("SelectionGroup")

        # 换场 / 隐藏立绘 → 断句
        if r["fields"].get("Transition"):
            flush()

        # 表态点的选项文本: **整条记录只由 [sN]/[nsN] 槽行组成**才算选项组
        # （`[s] "……?"` 这种无编号槽是台词, 不能当选项）
        lines_all = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        slot_lines = [ln for ln in lines_all if _SLOT.match(ln)]
        numbered = [ln for ln in slot_lines if _SLOT.match(ln).group(2)]
        if numbered and len(numbered) == len(lines_all):
            flush()
            for ln in numbered:
                t = _clean(_SLOT.sub("", ln))
                if t:
                    out.append({"kind": "option", "text": t})
            continue

        if sg:                               # 落地记录
            flush()
            # 落地文本 = 该记录的正文（旁白或台词）
            body = ""
            for line in raw.splitlines():
                line = line.strip()
                if not line or _CMD.match(line):
                    continue
                m = _ST_CHAR.match(line)
                if m:
                    body = m.group(4)
                    break
                body = line
                break
            out.append({"kind": "reaction", "sg": int(sg),
                        "text": _clean(body)})
            continue

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#title;"):
                flush()
                out.append({"kind": "title",
                            "text": _clean(line[len("#title;"):])})
                continue
            if line.startswith("#na;"):
                flush()
                out.append({"kind": "narration",
                            "text": _clean(line[len("#na;"):])})
                continue
            if line.startswith("#st;"):
                buf.append(_ST_PREFIX.sub("", line))
                continue
            m = _ST_CHAR.match(line)
            if m and len(m.group(4).strip()) >= 2:   # `3;角色;表情;文本`（纯 `3;하루카;08` 是立绘指令）
                flush()
                out.append({"kind": "line", "text": _clean(m.group(4))})
                continue
            if line.startswith("#clearST"):
                flush()
                continue
            if _SPRITE.match(line) or _CMD.match(line):
                continue                             # 立绘/时序/换场指令
            # 无标记正文（罕见）→ 当旁白
            flush()
            out.append({"kind": "narration", "text": _clean(line)})
    flush()
    return out


def merge_reactions(elems: list[dict]) -> list[dict]:
    """连续 reaction 若文本逐字相同 → 合并为一个表态点（取第一条）。"""
    out: list[dict] = []
    for e in elems:
        if (e["kind"] == "reaction" and out
                and out[-1]["kind"] == "reaction"
                and out[-1]["text"] == e["text"]):
            continue
        out.append(e)
    return out


def to_boards(elems: list[dict], *, max_records: int = 8) -> list[list[dict]]:
    """叙事元素 → 板。表态点=选项组, 槽后收板（与引擎语义一致）。"""
    boards: list[list[dict]] = []
    cur: list[dict] = []
    pending_opts: list[str] = []

    def close() -> None:
        nonlocal cur, pending_opts
        if pending_opts and cur:
            cur[-1]["_choices"] = pending_opts[:3]
        if cur:
            boards.append(cur)
        cur, pending_opts = [], []

    for e in elems:
        k = e["kind"]
        if k == "title":
            continue
        if k == "option":
            pending_opts.append(e["text"])
            continue
        if k == "reaction":
            # 反应段落在选项之后 → 属于**下一板**（槽在板尾、反应在下一板）
            close()
            cur.append({"narrator": e["text"]})
            continue
        if k == "narration":
            cur.append({"narrator": e["text"]})
        else:
            cur.append({"speaker": "CHAR", "text": e["text"]})
        if len(cur) >= max_records:
            close()
    close()
    return boards


def build_events(recs: list[dict], *, char_id: str, start_seq: int = 10,
                 max_records: int = 8) -> list[dict]:
    elems = merge_reactions(elements(recs))
    boards = to_boards(elems, max_records=max_records)
    events: list[dict] = []
    seq = start_seq
    for bi, brecs in enumerate(boards):
        paras, choices = [], []
        for rec in brecs:
            if "_choices" in rec:
                choices = rec["_choices"]
                continue                    # 选项载体, 不是记录
            if "text" not in rec:           # 防御: 坏元素不进 payload
                continue
            item = {"text": rec["text"],
                    "speaker": char_id if rec.get("speaker") else "narrator"}
            paras.append(item)
        if not paras:
            continue
        events.append({
            "type": "bond", "subtype": "story_scene", "seq": seq,
            "payload": {
                "paragraphs": paras,
                "records": [
                    ({"character": char_id, "text": p["text"]}
                     if p["speaker"] == char_id
                     else {"stage": "narrate", "text": p["text"]})
                    for p in paras],
                "choices": choices,
                "picked": choices[0] if choices else None,
                "is_end": bi == len(boards) - 1,
                "input": "（继续）",
            }})
        seq += 2
    return events


if __name__ == "__main__":
    import sys
    from collections import Counter
    gid = sys.argv[1] if len(sys.argv) > 1 else "1600008"
    ch = sys.argv[2] if len(sys.argv) > 2 else "igusa_haruka"
    recs = json.loads(Path(f".testtmp/ba_scenarios/ba_{gid}.json").read_text("utf-8"))
    elems = merge_reactions(elements(recs))
    print(f"=== {gid} · {ch} ===")
    print("元素类型:", dict(Counter(e["kind"] for e in elems)))
    print("选项数:", sum(1 for e in elems if e["kind"] == "option"))
    evs = build_events(recs, char_id=ch)
    print(f"板/事件 {len(evs)} 块, 记录 "
          f"{sum(len(e['payload']['paragraphs']) for e in evs)} 条, "
          f"带选项的板 {sum(1 for e in evs if e['payload']['choices'])}")
    print("\n--- 前 2 板 ---")
    for e in evs[:2]:
        print(f"[seq {e['seq']}] choices={e['payload']['choices']}")
        for p in e["payload"]["paragraphs"]:
            who = "旁白" if p["speaker"] == "narrator" else "角色"
            print(f"    {who}: {p['text'][:72]}")
    print("\n--- 末板 (is_end) ---")
    e = evs[-1]
    print(f"[seq {e['seq']}] is_end={e['payload']['is_end']}")
    for p in e["payload"]["paragraphs"]:
        who = "旁白" if p["speaker"] == "narrator" else "角色"
        print(f"    {who}: {p['text'][:72]}")
