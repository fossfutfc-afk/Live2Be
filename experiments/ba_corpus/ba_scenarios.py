# -*- coding: utf-8 -*-
"""官方剧本抽取（BA ScenarioScriptDBSchema.json）—— 按 GroupId 前缀分组导出。

为什么要它（而不是 ba_dump4.py）:
  - `ba_dump4` 把 ScriptKr 截断到 260 字, 而 `#st;{txt};{delay}` 是**碎片化**的
    （一句台词被拆进好几条记录）→ 截断后接不起来
  - 本工具导出**未截断的原始字段**, 一条记录一个 dict, 供后续重建叙事

用法:
    python .testtmp/ba_scenarios.py <SchemaJson> <GroupId前缀> <输出目录>

输出: <输出目录>/ba_<GroupId>.json = [{idx, fields{...}, script, jp}, ...]
BigFile 用 ijson 流式读（202MB, 不可整体 load）。
"""
import json
import sys
from pathlib import Path

import ijson

FIELDS = ("SelectionGroup", "Transition", "BGName", "BGEffect", "BGMId",
          "PopupFileName", "VoiceId", "Sound")


def main() -> None:
    schema, prefix, outdir = Path(sys.argv[1]), str(sys.argv[2]), Path(sys.argv[3])
    outdir.mkdir(parents=True, exist_ok=True)

    groups: dict[str, list[dict]] = {}
    rows = 0
    with open(schema, "rb") as f:
        for obj in ijson.items(f, "item"):
            rows += 1
            b = obj.get("Bytes") or {}
            gid = obj.get("GroupId") or b.get("GroupId")
            if gid is None:
                continue
            gid = str(gid)
            if not gid.startswith(prefix):
                continue
            fields = {}
            for k in FIELDS:
                v = b.get(k)
                if v not in (None, 0, "", [], {}):
                    fields[k] = v
            groups.setdefault(gid, []).append({
                "idx": len(groups.get(gid, [])) + 1,
                "fields": fields,
                "script": (b.get("ScriptKr") or "").replace("\r\n", "\n"),
                "jp": (b.get("TextJp") or "").replace("\r\n", "\n"),
            })

    total = 0
    for gid in sorted(groups):
        recs = groups[gid]
        total += len(recs)
        out = outdir / f"ba_{gid}.json"
        out.write_text(json.dumps(recs, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        # 一句话摘要: 标题 + 记录数 + 对话条数
        title = ""
        for r in recs:
            for line in r["script"].splitlines():
                if line.startswith("#title;"):
                    title = line[len("#title;"):].strip()
                    break
            if title:
                break
        n_st = sum(1 for r in recs if "#st;" in r["script"])
        n_na = sum(1 for r in recs if "#na;" in r["script"])
        n_sel = sum(1 for r in recs if r["fields"].get("SelectionGroup"))
        print(f"  {gid}  记录={len(recs):<4} 台词={n_st:<4} 旁白={n_na:<4} "
              f"表态点={n_sel:<3} 标题={title!r}")

    print(f"\n扫过 {rows:,} 行; 命中 {len(groups)} 个 GroupId / {total} 条记录 "
          f"→ {outdir}")


if __name__ == "__main__":
    main()
