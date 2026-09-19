# -*- coding: utf-8 -*-
"""place_rename — 地点键改名工具（**扫引用面 + 改表 + 留台账**）——PL6, 2026-09-19。

## 它解决什么

用户 2026-09-19: *"key 是不可改的"*（回放按 key 查表）, 但作者在 tempo 里重整命名
时改名仍会发生。这条工具把它变成一件**可追溯**的事:

    ① 扫引用面   —— 表 / 事件流（含暂存）/ `_place_review.json` 里谁在用这个旧名
    ② 改表那一行 —— 只动 `place_entities.json` 的那个键（外层键 + 行内 `place`）
    ③ 留台账     —— `data/worlds/{world}/place_renames.jsonl`（append-only）
                    ⇒ `_place_bg()` 查不到旧名时会说"已改名为 X"而不是"素材未找到"

**事件流一个字都不改**（append-only 铁律）: 旧板记的是"当时按哪张图演"。

## 用法（**默认干跑**, 只报告不落盘）

    python -m core.media.place_rename --from OLD --to NEW [--reason "…"] [--apply] [--world w]

两个入口形态（自动识别）:

* **表里还是旧名**（改名还没做）→ 干跑打印将改的两行; `--apply` 就地重写表 + 写台账
* **表里已经是新名**（在你那边/tempo 改过了）→ 只扫引用面 + 写台账（`--apply`）

⚠️ **表的同步方向是 tempo → repo**（用户 2026-09-19 裁定）: 就地改 repo 的表只对本机
有效, 下次从 tempo 同步会被覆盖 ⇒ `--apply` 时会提醒你**在 tempo 侧也改一遍**
（tempo 的工作台自己会导出新表, 那时这行改动自然合流）。

⚠️ **拒绝就地改**的情形: 表不是 tempo 的导出格式（`indent=1` / 无尾换行 / 无 BOM）
—— 那说明有人手搓过, 盲改会顺手重排整个文件; 此时只报告并让你在源头改。

## 扫描面（`payload.place_hint` **不动**——它是 writer 原文）

| 面 | 命中的形态 |
|---|---|
| 事件流 | `payload.place`、`payload.paragraphs[*].place`（v1 句项 / v2 记录同一处） |
| 暂存 | `soul/staging/events.jsonl`（章内暂存, 与真源分开报） |
| 审校表 | `assets/background/_place_review.json`（外层键 `SDIR\\|DIR\\|key` + 行内 `place`）|
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from core import paths
from core.media import place_renames
from core.media.place_table import DEFAULT_TABLE_PATH, load_table, reset_cache

#: 审校表（作者的 `active` 裁决; 在 `assets/` 里, 可能不存在）
REVIEW_PATH = paths.BACKGROUND_DIR / "_place_review.json"

#: tempo 导出格式（就地改表的**前提**: 能逐字节复原才敢重写）
_EXPORT_DUMP = {"indent": 1, "ensure_ascii": False}


# ---------------------------------------------------------------------------
# ① 扫引用面
# ---------------------------------------------------------------------------

def _scan_events(text: str, *, key: str, world: str, char: str, path: Path) -> list[dict]:
    """一行行看事件流, 找出**值等于 `key`** 的引用位置（只读, 不改）。

    只看两个面: `payload.place`（板级）与 `payload.paragraphs[*].place`
    （v1 句项 / v2 记录都在这一处）。`payload.place_hint` 是 **writer 原文, 不动**。
    """
    hits: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or f'"{key}"' not in line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        p = ev.get("payload") if isinstance(ev, dict) else None
        if not isinstance(p, dict):
            continue
        if str(p.get("place") or "").strip() == key:
            hits.append({"world": world, "char": char, "line": lineno,
                         "where": "payload.place", "file": str(path)})
        for i, rec in enumerate(p.get("paragraphs") or []):
            if isinstance(rec, dict) and str(rec.get("place") or "").strip() == key:
                hits.append({"world": world, "char": char, "line": lineno,
                             "where": f"paragraphs[{i}].place", "file": str(path)})
    return hits


def scan(old: str, *, worlds_dir: Path | str | None = None,
         review_path: Path | str | None = None,
         table_path: Path | str | None = None) -> dict:
    """扫引用面（**只读**）。返回 `{"events": [...], "staging": [...], "review": [...], "table": [...]}`。

    `table` = 表里的现状: `["old"]` / `["new"]` / `[]`（都没有）/ `["old","new"]`（撞车）。
    """
    old = (old or "").strip()
    worlds_root = Path(worlds_dir) if worlds_dir else paths.WORLDS_DIR
    events: list[dict] = []
    staging: list[dict] = []
    for world in place_renames.all_worlds(worlds_dir=worlds_root):
        chars = worlds_root / world / "characters"
        try:
            char_dirs = sorted(d for d in chars.iterdir() if d.is_dir())
        except OSError:
            continue
        for cd in char_dirs:
            for name, bucket in (("events.jsonl", events),
                                 ("staging/events.jsonl", staging)):
                f = cd / "soul" / name
                try:
                    text = f.read_text(encoding="utf-8")
                except OSError:
                    continue
                if f'"{old}"' not in text:            # 粗筛（绝大多数文件直接跳过）
                    continue
                bucket.extend(_scan_events(text, key=old, world=world,
                                           char=cd.name, path=f))
    review: list[str] = []
    rp = Path(review_path) if review_path else REVIEW_PATH
    try:
        raw = json.loads(rp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = None
    if isinstance(raw, dict):
        for k, v in raw.items():
            in_key = isinstance(k, str) and re.split(r"[|]", k)[-1] == old
            in_row = isinstance(v, dict) and str(v.get("place") or "") == old
            if in_key or in_row:
                review.append(str(k))
    return {"events": events, "staging": staging, "review": review,
            "table": _table_state(old, table_path)}


def _table_state(old: str, path: Path | str | None = None) -> list[str]:
    """表里 `old` / `old` 的新名各在不在。"""
    t = load_table(path)
    keys = set(t.keys())
    new = place_renames.resolve(old)
    return [k for k in (old, new) if k and k in keys]


# ---------------------------------------------------------------------------
# ② 改表那一行（**逐字节可复原**才敢动）
# ---------------------------------------------------------------------------

def table_text_rename(old: str, new: str, *, path: Path | str | None = None) -> str:
    """重写表文本（外层键 + 行内 `place`）; 表不是导出格式 → `ValueError`。

    逐字节验证: 先用同一组 dump 参数把原对象 dump 一遍, 与磁盘比对——不一致
    说明有人手搓过, 盲改会顺手重排整个文件（那是不可审的 diff）。
    """
    p = Path(path) if path else DEFAULT_TABLE_PATH
    raw = p.read_text(encoding="utf-8")
    obj = json.loads(raw)
    if json.dumps(obj, **_EXPORT_DUMP) != raw:
        raise ValueError(
            f"表不是 tempo 的导出格式（indent=1/无尾换行）, 拒绝就地改: {p}\n"
            "  请在 tempo 侧改名并重新导出; 或者先让格式回归导出格式。")
    if old not in obj:
        raise ValueError(f"表里没有 {old!r}（已被改过? 用 --from-table-new 只记台账）")
    if new in obj:
        raise ValueError(f"表里已经有 {new!r} —— 改名会撞车（两个键同名）")
    out: dict = {}
    for k, v in obj.items():
        if k != old:
            out[k] = v
            continue
        row = dict(v)
        row["place"] = new
        out[new] = row
    return json.dumps(out, **_EXPORT_DUMP)


# ---------------------------------------------------------------------------
# ③ 主流程
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m core.media.place_rename",
        description="地点键改名: 扫引用面 + 改表 + 留台账（默认干跑）")
    ap.add_argument("--from", dest="old", required=True, help="旧键")
    ap.add_argument("--to", dest="new", required=True, help="新键")
    ap.add_argument("--reason", default="", help="改名原因（写进台账）")
    ap.add_argument("--world", default="", help="只给这个世界线写台账（默认: 有引用的都写）")
    ap.add_argument("--worlds-dir", default="", help="世界线根（默认 data/worlds; 测试/换数据根用）")
    ap.add_argument("--review", default="", help="审校表路径（默认 assets/background/_place_review.json）")
    ap.add_argument("--apply", action="store_true", help="真的落盘（默认干跑）")
    ap.add_argument("--table", default="", help="表路径（默认 place_entities.json）")
    args = ap.parse_args(argv)

    old, new = args.old.strip(), args.new.strip()
    table_path = Path(args.table) if args.table else None
    worlds_dir = Path(args.worlds_dir) if args.worlds_dir else None
    review_path = Path(args.review) if args.review else None
    report = scan(old, worlds_dir=worlds_dir, review_path=review_path,
                  table_path=table_path)
    state = report["table"]

    print(f"地点改名: {old!r} → {new!r}")
    print(f"  表里现状: {state or '（两个名字都不在表里）'}")
    print(f"  事件流命中: {len(report['events'])} 处 "
          f"（角色 {sorted({h['char'] for h in report['events']})}）")
    for h in report["events"][:20]:
        print(f"    · {h['world']}/{h['char']} {h['where']} @{h['line']}")
    if len(report["events"]) > 20:
        print(f"    … 还有 {len(report['events']) - 20} 处")
    print(f"  暂存命中: {len(report['staging'])} 处（章内尚未提交）")
    print(f"  审校表命中: {report['review'] or '（无）'}")

    if old in state:
        try:
            text = table_text_rename(old, new, path=table_path)
        except ValueError as e:
            print(f"\n✗ 改表被拒: {e}")
            return 2
        print(f"\n表: 将把外层键 {old!r} 与行内 place 改成 {new!r}"
              f"（{len(text)} 字符, 其余逐字节不变）")
        if not args.apply:
            print("（干跑——加 --apply 落盘）")
            return 0
        p = table_path or DEFAULT_TABLE_PATH
        p.write_text(text, encoding="utf-8")
        reset_cache()
        print(f"✓ 表已改: {p}")
        print("⚠️ 同步方向是 tempo → repo: 记得在 tempo 侧也改一遍, 否则下次同步会覆盖")
    elif new in state:
        print("\n表里已经是新名 —— 只记台账（你在 tempo/手工改过了）")
    else:
        print(f"\n⚠️ 表里 {old!r} 与 {new!r} 都不在: 只记台账（不影响回放解释）")

    worlds = ([args.world] if args.world
              else sorted({h["world"] for h in report["events"] + report["staging"]}))
    if not args.apply:
        print(f"\n台账（干跑）: 将给 {worlds or '（无世界线命中）'} 各 append 一行")
        return 0
    for w in worlds:
        row = place_renames.append(old, new, world=w, reason=args.reason,
                                   events=len([h for h in report["events"]
                                               if h["world"] == w]),
                                   worlds_dir=worlds_dir)
        print(f"✓ 台账: {place_renames.ledger_path(w, worlds_dir=worlds_dir)} "
              f"← {json.dumps(row, ensure_ascii=False)}")
    if not worlds:
        print("（没有世界线引用旧名 ⇒ 未写台账; 需要的话用 --world 指定）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
