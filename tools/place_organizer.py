# -*- coding: utf-8 -*-
"""place_organizer.py — 背景资产生体归纳工具 Stage 1（预分类草案）。

把 assets/background/ 的 1094 张图归纳为**叙事实体**（语义地点, ~几百）——第二层
整理（第一层 = 历史 .py 按文件名前缀分目录, 已产生 195 个 BG_* 目录）。

本阶段（纯本地, 零 LLM）: 扫描 → 族合并（同 scene 族: 数字尾/变体尾自动归并）→
输出 assets/_place_draft.json（待人工/LLM 确认的候选清单 + 统计）。

用法:
    python tools/place_organizer.py            # 输出 draft + 打印统计
    python tools/place_organizer.py --json     # 只输出 json 路径
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.media.catalog import MediaCatalog           # noqa: E402
from core.media.background import VARIANT_TOKENS      # noqa: E402

OUT = ROOT / "assets" / "_place_draft.json"

#: scene_id 尾部噪声（数字/时刻后缀 → 同一实体的多图/角度/变体, 自动归并）
_TAIL_RE = re.compile(
    r"_(?:[0-9]+|(?:%s)(?:_[0-9]+)?)$" % "|".join(sorted(VARIANT_TOKENS)))


def root_of(scene_id: str) -> str:
    """scene_id → 实体族键（去尾部噪声）: abydos_council_room_2 → abydos_council_room。"""
    return _TAIL_RE.sub("", scene_id) or scene_id


def build_draft() -> dict:
    cat = MediaCatalog()
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for scene_id, entries in cat._backgrounds.items():
        d = entries[0].path.parent.name
        groups[(d, root_of(scene_id))].append(scene_id)

    # 目录 → 中文候选 region 提示（BG_Gehenna → gehenna; BG_Other → 混杂）
    items = []
    for (d, root), members in sorted(groups.items()):
        n_files = sum(len(cat._backgrounds[s]) for s in members)
        items.append({
            "key": f"{d}|{root}",
            "dir": d,
            "root": root,
            "scenes": sorted(members),
            "files": n_files,
            "suspect": d in ("BG_Other",),      # 杂物袋: 每 scene 单独族, 需看图归属
        })
    stats = {
        "scene_ids": len(cat._backgrounds),
        "groups": len(items),
        "multi_member": sum(1 for i in items if len(i["scenes"]) > 1),
        "dirs": len({i["dir"] for i in items}),
        "other_pending": sum(1 for i in items if i["dir"] == "BG_Other"),
    }
    return {"stats": stats, "items": items}


def main() -> None:
    ap = argparse.ArgumentParser(description="背景资产生体归纳 Stage 1: 预分类草案")
    ap.add_argument("--json", action="store_true", help="只打印输出路径")
    args = ap.parse_args()

    draft = build_draft()
    OUT.write_text(json.dumps(draft, ensure_ascii=False, indent=1), encoding="utf-8")
    s = draft["stats"]
    print(f"scene_id {s['scene_ids']} → 预分组 {s['groups']} 族"
          f"（多成员自动合并 {s['multi_member']}; 目录 {s['dirs']}; "
          f"BG_Other 待看图 {s['other_pending']}）")
    if not args.json:
        print("\n样例（多成员族）:")
        shown = 0
        for it in draft["items"]:
            if len(it["scenes"]) > 1 and shown < 8:
                print(f"  [{it['dir']}] {it['root']} ← {it['files']} 张: {it['scenes'][:4]}")
                shown += 1
        print("\nBG_Other（杂物袋, 每项需看图归属）:")
        for it in draft["items"]:
            if it["dir"] == "BG_Other":
                print(f"  {it['root']} ({it['files']} 张)")
    print(f"\ndraft 已写: {OUT}")


if __name__ == "__main__":
    main()
