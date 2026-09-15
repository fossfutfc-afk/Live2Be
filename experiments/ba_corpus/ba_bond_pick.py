# -*- coding: utf-8 -*-
"""精确抽「羁绊剧情」——GroupId 模式 = `{slot}{story}`。

官方羁绊剧情 5 档, 个位固定 2/3/5/6/8（1/4/7/9 预留或用于他处）:
    X0002 / X0003 / X0005 / X0006 / X0008
其中 X = 角色槽×10（Haruka 1600* / Mutsuki 1300* / Kayoko 1200* / Aru 1000*）。

判定标准（不靠猜）: 把 5 个候选都抽出来, 看结构是否自洽——
  ① 有 `#title;` ② 有表态点（SelectionGroup）③ 有记忆大厅（SpineBG_Lobby）
  ④ 记录数在几百量级（单章） ⑤ 5 档的标题应当成组

Live2Be 五角色 → 官方槽位（由 CharacterDBSchema.DevName 的 `Xxx_default` 反推）:
    rikuhachima_aru   Aru     10000 → 槽 1000
    onikata_kayoko    Kayoko  12000 → 槽 1200
    asagi_mutsuki     Mutsuki 13000 → 槽 1300
    igusa_haruka      Haruka  16000 → 槽 1600
    shiraishi_kokoro  Kokoro  17000 → 槽 1700
"""
import json
from pathlib import Path

SLOTS = {
    "rikuhachima_aru": "1000",
    "onikata_kayoko": "1200",
    "asagi_mutsuki": "1300",
    "igusa_haruka": "1600",
    "shiraishi_kokoro": "1700",
}
STORIES = ("2", "3", "5", "6", "8")

D = Path(".testtmp/ba_scenarios")


def summarize(recs):
    title, n_st, n_na, n_sel, n_lobby = "", 0, 0, 0, 0
    for r in recs:
        s = r["script"]
        if not title:
            for line in s.splitlines():
                if line.startswith("#title;"):
                    title = line[len("#title;"):].strip()
                    break
        if "#st;" in s:
            n_st += 1
        if "#na;" in s:
            n_na += 1
        if r["fields"].get("SelectionGroup"):
            n_sel += 1
        if "SpineBG_Lobby" in str(r["fields"].get("BGName", "")):
            n_lobby += 1
    return title, n_st, n_na, n_sel, n_lobby


print(f"{'角色':<18} {'GroupId':<9} {'记录':>5} {'台词':>5} {'旁白':>5} "
      f"{'表态':>5} {'大厅':>5}  标题")
found = {}
for ch, slot in SLOTS.items():
    print(f"-- {ch}（槽 {slot}）")
    for st in STORIES:
        gid = f"{slot}00{st}"
        p = D / f"ba_{gid}.json"
        if not p.is_file():
            print(f"   {gid:<9} —— 未抽到（该槽无此档）")
            continue
        recs = json.loads(p.read_text(encoding="utf-8"))
        title, n_st, n_na, n_sel, n_lobby = summarize(recs)
        flag = ""
        if not title:
            flag += " ⚠无标题"
        if n_sel == 0:
            flag += " ⚠无表态点"
        print(f"   {gid:<9} {len(recs):>5} {n_st:>5} {n_na:>5} {n_sel:>5} "
              f"{n_lobby:>5}  {title!r}{flag}")
        found.setdefault(ch, []).append((gid, len(recs), title))
    print()

print("=== 汇总 ===")
for ch, items in found.items():
    print(f"  {ch}: {len(items)} 档, 共 {sum(x[1] for x in items)} 条记录")
