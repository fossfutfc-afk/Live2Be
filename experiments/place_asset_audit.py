# -*- coding: utf-8 -*-
"""地点表 ↔ 资产对账（PL0/PL1 的验收读数, 可复跑）。

用户 2026-09-19: tempo 是"**带实体的 development 分支**" —— 他在 tempo 整理,
然后同步 `SDIR`/`DIR` + 表进 repo。本脚本回答两个**不同**的问题:

    A. **表里 `files` 写的路径, 磁盘上有没有** —— 这是 PL0 的真验收
       （表里写 `SDIR_Inner/DIR_Class/BG_ClassRoom.jpg`, 而磁盘还是 `BG_Class/…`
        时, A 会全线飘红; 同步完应当 435/435）
    B. **运行时到底取不取得到图** —— 走的是真路径 `_place_bg(key)`
       （表键 → `files` 派生的资产 scene_id → catalog）。它比 A 宽松:
       **文件名不变** 所以即使目录层级还没换, B 也可能全绿。

两者都能答"玩家会不会看到黑屏", 但只有 A 能答"表和资产是不是同一个组织"。

用法: python experiments/place_asset_audit.py
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import paths                                            # noqa: E402
from core.media.place_table import load_table                     # noqa: E402

BG_ROOT = paths.BACKGROUND_DIR


def main() -> None:
    t = load_table()
    if not t.ok:
        print("表读不出来:", t.error)
        return
    print(f"表: {len(t)} 条 | 背景根: {BG_ROOT}")
    print(f"磁盘上的背景图: "
          f"{sum(1 for p in BG_ROOT.rglob('*') if p.is_file() and p.suffix.lower() in ('.jpg', '.jpeg', '.png'))}"
          f"（含缓存目录; 真图见下）")

    # ── A. 表 files 路径 vs 磁盘 ──
    miss_files: list[tuple[str, str]] = []
    n_files = 0
    ent_ok = ent_bad = 0
    no_files: list[str] = []
    for e in t.all():
        files = list(e.day) + list(e.night)
        if not files:
            no_files.append(e.place)
            continue
        n_files += len(files)
        bad = [f for f in files if not (BG_ROOT / f).is_file()]
        miss_files += [(e.place, f) for f in bad]
        if bad:
            ent_bad += 1
        else:
            ent_ok += 1
    print(f"\n=== A. 表 files ↔ 磁盘（PL0 的真验收）===")
    print(f"  条目 {len(t)}: 全对 {ent_ok} / 有缺 {ent_bad} / 无 files {len(no_files)}")
    print(f"  files 引用 {n_files} 个路径; 磁盘上缺 {len(miss_files)}")
    if miss_files:
        print("  ⚠️ 样例（表里写的是新组织, 磁盘还是旧组织?）:")
        for place, f in miss_files[:5]:
            print(f"     {place:<24} {f}")

    # ── B. 运行时实际取图（真路径 _place_bg）──
    from webgui.routers.bond import _place_bg                     # 延迟导入（重)
    ok = miss = 0
    blacklist: list[str] = []
    for key in t.keys():
        url, st = _place_bg(key)
        if st == "ok" and url:
            ok += 1
        else:
            miss += 1
            blacklist.append(key)
    print(f"\n=== B. 运行时取图 `_place_bg(key)`（玩家会不会看到黑屏）===")
    print(f"  取到图 {ok} / 缺失 {miss}")
    if blacklist:
        print(f"  ⚠️ 黑屏名单（{len(blacklist)}）: {blacklist[:12]}")

    # ── C. 组织形态 ──
    kinds = Counter()
    for p in BG_ROOT.iterdir():
        if p.is_dir():
            kinds["SDIR_*（工作区组织）" if p.name.startswith("SDIR_")
                  else "点/下划线（已剪枝）" if p.name.startswith((".", "_"))
                  else "BG_*（旧组织）"] += 1
    print(f"\n=== C. 目录形态 ===\n  {dict(kinds)}")
    print(f"\n判定: A 全绿 ⇒ 表和资产是同一组织（PL0 完成）; "
          f"B 全绿 ⇒ 玩家不会因缺图看黑屏")


if __name__ == "__main__":
    main()
