# -*- coding: utf-8 -*-
"""place_pick_real.py — 第二遍「选图」真机验收（拿真话考标注 LLM）。

## 为什么要单独一个脚本

选图是**一个判定**（不是整场生成）。用真剧情跑一轮只覆盖 1~2 次换场, 而这里直接
把"一句话 + 一个键 + 它的候选图 + 作者 note"喂给模型, **一轮考十几条**, 还能把
**反例**（用户给的四句）一起考了 —— 那是这一步唯一真正难的地方。

## 覆盖

| 组 | 考什么 |
|---|---|
| 时刻 | 明确写了深夜/夕阳/清晨 → 该选夜/夕/清晨 那张 |
| **差分** | 作者 note 里的偏好（*"请使用差分2"*）与描述（*"2则是正常沙滩"*）**是否被照办** |
| **反例** | 四句"看着像时刻词、其实不是时刻"的话 → **不该乱选**（空/默认图才算过） |
| 天气 | 雨/雾 → 有对应图就选, 没有就回落默认图（不黑屏） |

## 不写任何数据

只用 LLM + 表（`PlaceEntry`）, **不建引擎、不碰事件流**。生图硬关。

用法:
    python experiments/place_pick_real.py [--key school_rooftop] [--show-prompt]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("LIVE2BE_IMAGE", "off")            # 生图硬关（本脚本也不出图）

from core.bond.variant_annotate import pick_image         # noqa: E402
from core.media.background import derive_background       # noqa: E402
from core.media.place_table import load_table             # noqa: E402
from llm.client import LLMClient                          # noqa: E402

#: (文本, 键, 期望, 说明) —— 期望写法:
#:   `moment:night`        → 选中的图派生出的变体 == night
#:   `file:BG_X.jpg`       → 选中的文件名精确等于它
#:   `keep_or_base`        → 空（保持）或默认图都算过（**反例组用这个**）
CASES: list[tuple[str, str, str, str]] = [
    # ── 时刻 ──────────────────────────────────────────────────────────
    ("夜深了，我们溜到学校天台上去", "school_rooftop", "moment:night", "深夜 → 夜图"),
    ("放学后的天台，夕阳把影子拉得很长", "school_rooftop", "moment:sunset", "夕阳 → 夕图"),
    ("清晨的天台，天刚蒙蒙亮", "school_rooftop", "moment:dawn", "清晨 → 清晨图"),
    # ── 反例（用户 2026-09-19 给的四句）────────────────────────────────
    ("从早到晚，我都想一直陪在老师身边", "school_rooftop", "keep_or_base",
     "范围成语: 不该选夜/清晨"),
    ("这些灯光，感觉像在白天一样呢~", "school_rooftop", "moment:night",
     "比喻+否定: 其实是夜里（**该选夜图**）"),
    ("我一定要将老师的善良公布在光天化日之下！", "school_rooftop", "keep_or_base",
     "成语: 与时刻无关"),
    ("私は夜の散歩が一番好きです", "school_rooftop", "keep_or_base",
     "外语+意愿句: 喜欢夜里散步 ≠ 现在是夜里"),
    # ── 作者差分（note 说了算）────────────────────────────────────────
    ("阳光明媚的渔村，海风很舒服", "fishing_village", "file:BG_FishingVillage2.jpg",
     'note: "请使用差分2,差分2是阳光明媚的正常渔村"'),
    ("雾气浓浓的渔村码头", "fishing_village", "file:BG_FishingVillage.jpg",
     'note: "正常版本是雾气浓浓的"'),
    ("夜里的渔村", "fishing_village", "moment:night", "夜晚都一样 → 夜图"),
    # ── 天气（有就选, 没有就回落, 不许黑屏）────────────────────────────
    ("雨中的天台，我们撑着伞", "school_rooftop", "keep_or_base",
     "该键没有雨图 → 回落默认（不黑屏）"),
    ("大雾里的山谷，看不清湖面", "valley", "moment:fog", "valley 有雾萦差分"),
]


def _moment_of(rel: str) -> str:
    return derive_background(Path(rel).stem)[1] or ""


def check(picked: str, expect: str, entry) -> bool:
    if expect == "keep_or_base":
        return picked == "" or picked == (entry.asset() or "")
    if expect.startswith("moment:"):
        want = expect.split(":", 1)[1]
        return bool(picked) and _moment_of(picked) == want
    if expect.startswith("file:"):
        return picked.endswith(expect.split(":", 1)[1])
    return False


def main() -> int:
    show_prompt = "--show-prompt" in sys.argv
    only = None
    if "--key" in sys.argv:
        only = sys.argv[sys.argv.index("--key") + 1]

    table = load_table()
    if not table:
        print("✗ 表读不出来, 无法验收")
        return 2
    llm = LLMClient()
    print(f"模型: {llm.model if hasattr(llm, 'model') else '?'} | 表 {len(table)} 条 | "
          f"用例 {len(CASES)} 条\n")

    n_pass = 0
    results = []
    for text, key, expect, why in CASES:
        if only and key != only:
            continue
        entry = table.get(key)
        if entry is None:
            print(f"⏭ 表里没有 {key}")
            continue
        t0 = time.time()
        picked = pick_image(llm, text, entry, current_image="")
        dt = time.time() - t0
        ok = check(picked, expect, entry)
        n_pass += ok
        results.append((ok, text, key, picked, expect, why, dt))
        mark = "✓" if ok else "✗"
        print(f"{mark} [{key}] {text!r}")
        print(f"    选: {Path(picked).name if picked else '（空 = 保持）'}"
              f"    期望: {expect}    （{why}）  {dt:.1f}s")

    if show_prompt and results:
        ok, text, key, *_ = results[0]
        entry = table.get(key)
        from llm.prompts import load_prompt
        print("\n" + "=" * 70)
        print("（示例）实际喂进去的 system prompt:")
        print("=" * 70)
        print(load_prompt("place_variant")
              .replace("{place}", entry.place)
              .replace("{aliases}", "/".join(entry.keywords))
              .replace("{candidates}", entry.image_candidate_lines())
              .replace("{note}", entry.note)
              .replace("{current_image}", "（还没定）")
              .replace("{text}", text))

    total = len(results)
    print(f"\n{'=' * 70}\n选图验收: {n_pass}/{total} 通过")
    bad = [(t, k, p, e, w) for ok, t, k, p, e, w, _ in results if not ok]
    if bad:
        print("未过:")
        for t, k, p, e, w in bad:
            print(f"  · [{k}] {t!r} → {Path(p).name if p else '（空）'}（期望 {e}; {w}）")
    return 0 if n_pass == total else 1


if __name__ == "__main__":
    sys.exit(main())
