# -*- coding: utf-8 -*-
"""人工核对: 抽样打印 digest 产出的 narration（与官方剧本对照）。"""
import json
from pathlib import Path

rows = json.loads(Path(".testtmp/ba_digest_results.json").read_text("utf-8"))
# 抽: 1 条负 valence、1 条 span/int 差最大、1 条高 SIG
by_key = {}
for r in rows:
    if r["val"] is not None and r["val"] <= -0.5:
        by_key.setdefault("最负 valence", r)
    if r["span"] is not None and r["int"] is not None:
        d = abs(r["span"] - r["int"])
        if "span/int 差最大" not in by_key or \
                d > abs(by_key["span/int 差最大"]["span"]
                        - by_key["span/int 差最大"]["int"]):
            by_key["span/int 差最大"] = r
    if r["sig"] >= 0.9:
        by_key.setdefault("最高 SIG", r)

for k, r in by_key.items():
    print(f"===== {k} =====")
    print(f"  {r['gid']} {r['ch']} {r['id']}  「{r['title']}」")
    print(f"  SIG={r['sig']:.2f} span={r['span']} int={r['int']} "
          f"val={r['val']}")
    print(f"  narration: {r['narration']}")
    print()
