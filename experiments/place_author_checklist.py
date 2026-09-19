# -*- coding: utf-8 -*-
"""PL7 作者侧清单: 把"该你改什么"变成可直接照着改的表。

只读表 + 磁盘, **不改任何东西**。四组:
  A. `files.night` 混装（状态变体 / 白天天气）——逐条列出该挪去哪
  B. 写了 note 却没 active / active 但没图 / 只有夜没有昼 之类的形状问题
  C. 覆盖率: 磁盘上没进表的图（作者可选补）
  D. note 写法: 哪些多图键**没有**说明该用哪张（第二遍选图会自己挑）
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from core.media.background import derive_background, VARIANT_TOKENS  # noqa: E402
from core.media.place_table import MOMENT_VARIANTS, load_table       # noqa: E402

BG = ROOT / "assets" / "background"
REVIEW = BG / "_place_review.json"

#: 时刻/天气（选图会用的）vs 剧情状态（现在没人告诉标注层"这场戏停电了"）
STATE_VARIANTS = sorted(set(VARIANT_TOKENS) - set(MOMENT_VARIANTS) - {"day"})

t = load_table()
assert t.ok, t.error
print(f"表: {len(t)} 键 / {sum(len(e.aliases()) for e in t.all())} 别名\n")

# ── A. files.night 里混了不该在那儿的 ────────────────────────────────
print("=" * 78)
print("A. `files.night` 里的混装（时刻/天气该留, 剧情状态/白天天气该挪走）")
print("=" * 78)
misfiled: dict[str, list[tuple[str, str]]] = defaultdict(list)
for e in t.all():
    for rel in e.night:
        _, v = derive_background(Path(rel).stem)
        if v and v not in MOMENT_VARIANTS:
            misfiled[v].append((e.place, Path(rel).name))
for v in STATE_VARIANTS:
    items = misfiled.get(v)
    if items:
        print(f"  [{v}] {len(items)} 张  ←  {'剧情状态' if v not in ('fog','rain','cloudy','dawn','sky','fineday') else '白天天气'}")
        for place, name in items[:6]:
            print(f"        {place:24} {name}")
        if len(items) > 6:
            print(f"        … 还有 {len(items) - 6} 张")
total_misfiled = sum(len(v) for v in misfiled.values())
print(f"  ── 合计 {total_misfiled} 张（建议: 时刻类留在 night; 状态类另立一个 files 键,"
      f" 或干脆从该键移除——它们现在进不了选图候选, 也不影响运行）")

# ── B. 形状问题 ──────────────────────────────────────────────────────
print()
print("=" * 78)
print("B. 形状问题（逐条可改）")
print("=" * 78)
no_day = [e.place for e in t.all() if not e.day]
no_note = [e.place for e in t.all() if not e.note]
single = [e.place for e in t.all() if len(e.image_candidates()) == 1]
multi_no_note_hint = []
note_hint = re.compile(r"(请|建议|优先|推荐|默认|一般|通常|最好).{0,6}(用|使用|选|是)")
for e in t.all():
    if len(e.image_candidates()) > 1 and not (e.note and note_hint.search(e.note)):
        multi_no_note_hint.append(e.place)
print(f"  只有夜、没有昼: {len(no_day)} → {no_day}")
print(f"  note 为空: {len(no_note)} → {no_note}")
print(f"  只有一张图（选图不会问 LLM）: {len(single)}")

# ── C. 覆盖率（磁盘 vs 表）───────────────────────────────────────────
print()
print("=" * 78)
print("C. 覆盖率: 磁盘上有、但没进任何键的图")
print("=" * 78)
on_disk = {p.relative_to(BG).as_posix() for p in BG.rglob("*.jpg")
           if not any(part.startswith((".", "_")) for part in p.parts)}
in_table = {rel for e in t.all() for rel in e.day + e.night}
extra = sorted(on_disk - in_table)
print(f"  磁盘 {len(on_disk)} 张 / 表引用 {len(in_table)} 张 / **未进表 {len(extra)} 张**（{len(extra) * 100 // max(len(on_disk), 1)}%）")
by_dir = Counter(rel.split("/")[0] for rel in extra)
print("  按 SDIR 分布:", dict(by_dir.most_common()))
for rel in extra[:8]:
    print(f"      {rel}")
if len(extra) > 8:
    print(f"      … 还有 {len(extra) - 8} 张（全量见下方清单文件）")

# ── D. note 写法（第二遍选图会照办 note）─────────────────────────────
print()
print("=" * 78)
print("D. 多图键里 **note 没说该用哪张** 的（选图只能自己判）")
print("=" * 78)
print(f"  多图键 {sum(1 for e in t.all() if len(e.image_candidates()) > 1)} 个,"
      f" 其中 note 里带'请/建议/默认用…'这类偏好的只有 "
      f"{sum(1 for e in t.all() if len(e.image_candidates()) > 1 and e.note and note_hint.search(e.note))} 个")
for place in multi_no_note_hint[:14]:
    e = t.get(place)
    print(f"  · {place:24} {len(e.image_candidates())} 张: "
          f"{[Path(r).name for r, _ in e.image_candidates()][:3]}")
    if e.note:
        print(f"      note: {e.note[:60]}")
if len(multi_no_note_hint) > 14:
    print(f"  … 还有 {len(multi_no_note_hint) - 14} 个")

# ── 落盘一份可勾选的清单（作者照着改）───────────────────────────────
out = ROOT / ".testtmp" / "pl7_checklist.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({
    "misfiled_night": {k: v for k, v in misfiled.items()},
    "no_day": no_day, "no_note": no_note, "single_image": single,
    "not_in_table": extra,
    "multi_image_without_note_preference": multi_no_note_hint,
}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\n（清单已落盘: {out.relative_to(ROOT)}）")

# ── 参考: 作者 note 里已经写了偏好的（选图会照办, 列出来对照）────────
print()
print("=" * 78)
print("参考. note 里已经写明偏好的键（第二遍选图会照办, 已验证 2/2）")
print("=" * 78)
for e in t.all():
    if e.note and note_hint.search(e.note) and len(e.image_candidates()) > 1:
        print(f"  · {e.place}: {e.note[:70]}")
