# -*- coding: utf-8 -*-
"""place_real_probe.py — 真档上 C 链路的"单轴修复"前后对照（零 API, 只用本地向量后端）。

## 为什么单独一个探针

真档的 wiki 是 2026-09-11/12 消化的: 那时 `place` / `place_raw` **都还没落地**
（`place_raw` 是 09-19 才加的）。所以现在跑 C 是**降级**——不是链路的问题, 是**字段没物化**。

本探针把"重消化之后会怎样"在本地**模拟**出来（不改真档、不写任何东西）:

1. 从真事件流里取每板的 `payload.place_hint`（writer 原话）+ 每板记录数;
2. 把这些原话**按章**贴到该章的 episode 节点上（= `digest` 的 `_place_raw` 会做的事）;
3. 跑 `C_place.gather` 两次: **修复前**（只有素材轴, 没键 → `magic(s, 0) = 0` → 空手）
   与**修复后**（键未知 → 走叙事轴单轴, 用户 2026-09-20 裁决）;
4. 顺便量 `emo_shape` 的原料（`paragraphs[].emotion`）齐不齐 —— B 路能不能活。

⚠️ 这是**模拟**: `place` 键仍然没有（要跑标注层才有）, 所以 `detail.by` 会是 `no_key`。
真东西要重消化 + 补标注层才会出现（见探针输出末尾的提示）。

用法:
    python experiments/place_real_probe.py [--char igusa_haruka] [--now 深夜的杂草屋]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.brain import RecallContext, WikiStoreV2, get_channel   # noqa: E402
from core.rag.embedder import LocalEmbedder                             # noqa: E402


def _events(char: str, world: str = "world1") -> list:
    p = ROOT / "data" / "worlds" / world / "characters" / char / "soul" / "events.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--char", default="igusa_haruka")
    ap.add_argument("--now", default="深夜的杂草屋", help="当前场地的 writer 原话（模拟）")
    ap.add_argument("--key", default="ruinschoolcorridor", help="当前场地的键（C 要求的输入）")
    args = ap.parse_args()

    evs = _events(args.char)
    bond = [e for e in evs if e.get("type") == "bond"]
    emo = sum(1 for e in bond for p in (e.get("payload", {}).get("paragraphs") or [])
              if p.get("emotion"))
    recs = sum(len(e.get("payload", {}).get("paragraphs") or []) for e in bond)
    hints = [e["payload"].get("place_hint") for e in bond if e["payload"].get("place_hint")]
    print(f"[事件流] {args.char}: bond 场={sum(1 for e in bond if e.get(chr(34)+chr(34)) or e.get('subtype') == 'story_scene')} 记录={recs} 带 emotion={emo}"
          f"（{emo * 100 // max(recs, 1)}%）; place_hint={hints}")
    print(f"[事件流] place 键（板首/句级）= "
          f"{sum(1 for e in bond if e['payload'].get('place')) + sum(1 for e in bond for p in (e['payload'].get('paragraphs') or []) if p.get('place'))}"
          f"  ← 0 = 标注层没跑过, 键要补")

    st = WikiStoreV2(ROOT / "data", world_id="world1", char_id=args.char)
    eps = [n for n in st.all() if n.kind == "episode"]
    print(f"[真档 wiki] episode={len(eps)}: "
          + ", ".join(f"{n.id}(place={n.place or '—'}, raw={n.place_raw or '—'})" for n in eps))

    emb = LocalEmbedder()
    print(f"[后端] {emb.model!r} health={emb.health()}")
    if not emb.health():
        return 2
    from core.rag.brain import make_embed_fn
    embed_fn = make_embed_fn(emb)

    def _run(tag: str) -> None:
        ctx = RecallContext(now="2026-09-20", char_id=args.char, embed_fn=embed_fn,
                            place_now=args.key, place_raw_now=args.now)
        r = get_channel("C_place").gather(st, ctx)
        print(f"\n  {tag}: degraded={r.degraded} note={r.note or '-'}")
        print(f"    knobs={r.knobs}")
        for h in r.hits:
            print(f"    {h.node.id} raw={h.raw:.3f} by={h.detail['by']} "
                  f"axes={h.detail['axes']} sem={h.detail['sem']} key_sim={h.detail['key_sim']}")

    _run("① 修复前（`place_raw` 也没物化 —— 现在的真档就是这样）")

    # 模拟重消化: 把该章的 writer 原话贴回 episode（`_place_raw` 会做的事）
    for n in eps:
        n.place_raw = list(hints)
    _run("② 模拟重消化（`place_raw` 有了, 键仍没有 → **走单轴**）")

    print("\n⚠️ 模拟到此为止: `place` 键要跑**标注层**（每板一次 place 调用）才有;"
          "\n   那之后 C 的两轴才真正齐（`detail.axes=2`）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
