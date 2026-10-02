# -*- coding: utf-8 -*-
"""recall_compose_probe.py — 四条召回道路的**真实分**（合成层标定用）。

## 为什么要先量

合成层要么"按 `scale` 声明归一", 要么"按名次并"。两种都需要**先知道真实分数带**——
Q11 的教训就是"阈值从未标定过, 0.50 是拍的"。这个脚本拿**真档 + 真 embedding 后端**
把四件事量出来:

| # | 量什么 | 定什么 |
|---|---|---|
| 1 | D（narration cos）: 同角色对 / 跨角色对 / **域外 query** 的分数带 | cos 那一轴能不能不标定就用 |
| 2 | A（`det`）: 真档四格哪些有值 → 实际值域 | `det` 归一除几 |
| 3 | B / C: 真档缺什么字段 → 降级 note 原样打印 | 现在能不能靠真档验证 |
| 4 | 收敛: 一个节点被几条链路命中 | 用户判据"双链路都召回 = 最重要"有没有数据 |

**只读**: 不建引擎、不写事件流、不落库、不打台账。

用法:
    python experiments/recall_compose_probe.py [--char igusa_haruka] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.brain.read.channel_impl import build_channels          # noqa: E402
from core.brain.read.channels import RecallContext               # noqa: E402
from core.brain.store import WikiStoreV2                    # noqa: E402
from core.rag.brain import make_embed_fn                            # noqa: E402
from core.rag.embedder import LocalEmbedder                         # noqa: E402

#: 域外 query（探"无关"基线用）—— 与两个角色的档无任何关系
OFF_DOMAIN = [
    "今天的数学作业还没写完, 我先去趟便利店买点饭团。",
    "The quick brown fox jumps over the lazy dog.",
]


def _stores(world: str = "world1") -> dict[str, WikiStoreV2]:
    """真档（只扫存在的 wiki.jsonl, 空档跳过）。"""
    out: dict[str, WikiStoreV2] = {}
    base = ROOT / "data" / "worlds" / world / "characters"
    for d in sorted(base.iterdir()) if base.is_dir() else []:
        p = d / "soul" / "wiki.jsonl"
        if p.is_file() and p.stat().st_size > 0:
            out[d.name] = WikiStoreV2(ROOT / "data", world_id=world,
                                      char_id=d.name)
    return out


def _band(vals: list[float]) -> str:
    if not vals:
        return "-"
    return f"n={len(vals)} min={min(vals):.3f} mean={sum(vals)/len(vals):.3f} max={max(vals):.3f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default="world1")
    ap.add_argument("--json", action="store_true", help="机读输出（默认人读）")
    args = ap.parse_args()

    emb = LocalEmbedder()
    print(f"[后端] base_url={emb.base_url} model={emb.model!r} health={emb.health()}")
    if not emb.health():
        print("服务/模型不可用 → 本脚本无事可做（B/C/D 都要 embed_fn）")
        return 2
    embed_fn = make_embed_fn(emb)

    stores = _stores(args.world)
    print(f"[真档] {len(stores)} 个非空档: "
          + ", ".join(f"{k}({len(v.all())} 节点)" for k, v in stores.items()))

    # ── 1. D 那一轴的真实分数带 ────────────────────────────────────────
    from core.brain.read.recall import _cosine, _embed_text

    eps: list[tuple[str, object]] = []           # (char, episode node)
    for cid, st in stores.items():
        eps += [(cid, n) for n in st.all() if n.kind == "episode" and n.narration]
    texts = [_embed_text(n) for _, n in eps]
    vecs = embed_fn(texts + OFF_DOMAIN)
    node_vecs, off_vecs = vecs[:len(eps)], vecs[len(eps):]

    same, diff = [], []
    for i in range(len(eps)):
        for j in range(i + 1, len(eps)):
            c = _cosine(node_vecs[i], node_vecs[j])
            (same if eps[i][0] == eps[j][0] else diff).append(c)
    off = [_cosine(qv, nv) for qv in off_vecs for nv in node_vecs]

    print("\n=== 1. D 轴（narration cos, nomic）真实分数带 ===")
    print(f"  同角色对   {_band(same)}")
    print(f"  跨角色对   {_band(diff)}")
    print(f"  **域外 query** {_band(off)}   ← 无关基线（Q11 那条: nomic 基线高）")
    if same and off:
        print(f"  分层: 同角色 min={min(same):.3f} vs 域外 max={max(off):.3f} "
              f"→ {'可分' if min(same) > max(off) else '⚠重叠'}")

    # ── 2. A 链路 det 的真实值域 ──────────────────────────────────────
    print("\n=== 2. A 轴（det = SIG·TIME + emo_span·emo_int）真实值 ===")
    rows = []
    for cid, st in stores.items():
        ctx = RecallContext(now="2026-09-20", char_id=cid, embed_fn=embed_fn)
        res = next(c for c in build_channels()
                   if c.name == "A_intensity").gather(st, ctx)
        print(f"  [{cid}] knobs={res.knobs} note={res.note or '-'}")
        for h in res.hits:
            d = h.detail
            rows.append({"char": cid, "id": h.node.id, "raw": h.raw,
                         "sig": d.get("sig"), "time": d.get("time"),
                         "age": d.get("age"), "span": d.get("span"),
                         "int": d.get("int")})
    for r in rows:
        print(f"    {r['char']:>16} {r['id']} det={r['raw']:.4f} "
              f"(sig={r['sig']} time={r['time']} age={r['age']}d "
              f"span={r['span']} int={r['int']})")
    if rows:
        print("  ⇒ 真档第二行 (span·int) 全 0 → det 实际值域 = "
              f"[{min(r['raw'] for r in rows):.3f}, {max(r['raw'] for r in rows):.3f}]")

    # ── 3. B / C 在真档上能不能出分 ───────────────────────────────────
    print("\n=== 3. B / C 在真档上的现状（如实打印降级 note）===")
    for cid, st in stores.items():
        ctx = RecallContext(now="2026-09-20", char_id=cid, embed_fn=embed_fn,
                            emo_now=["tease", "smile"], place_now="school_rooftop",
                            place_raw_now="学校天台", query=eps[0][1].narration)
        for ch in build_channels():
            if ch.name in ("A_intensity", "E_unconscious"):
                continue
            r = ch.gather(st, ctx)
            print(f"  [{cid}] {ch.name:<15} hits={len(r.hits):<3} "
                  f"degraded={r.degraded} note={r.note or '-'}")

    # ── 4. D 的留一法排序 + 收敛 ──────────────────────────────────────
    print("\n=== 4. D 留一法（拿真 episode 当 query）与收敛 ===")
    dch = next(c for c in build_channels() if c.name == "D_deja_vu")
    ach = next(c for c in build_channels() if c.name == "A_intensity")
    for cid, st in stores.items():
        ctx = RecallContext(now="2026-09-20", char_id=cid, embed_fn=embed_fn)
        ares = ach.gather(st, ctx)
        a_rank = {h.node.id: h.rank for h in ares.hits if h.raw is not None}
        for n in st.all():
            if n.kind != "episode" or not n.narration:
                continue
            ctx.query = n.narration
            dres = dch.gather(st, ctx)
            top = dres.hits[:3]
            both = [h.node.id for h in dres.hits if h.node.id in a_rank]
            print(f"  [{cid}] query={n.id} → D top3: "
                  + ", ".join(f"{h.node.id}:{h.raw:.3f}" for h in top)
                  + f"   | A 同时命中 {len(both)} 条 "
                  f"(A 名次 {sorted(a_rank[i] for i in both)[:3]})")
            break                                    # 每档一条当样本, 免得刷屏

    # ── 5. 合成层（四条道路 → 最终分）──────────────────────────────────
    print("\n=== 5. 合成层（recall_now: 真链路 + 真向量 → 最终分）===")
    from core.brain.read.compose import recall_now
    for cid, st in stores.items():
        eps_c = [n for n in st.all() if n.kind == "episode" and n.narration]
        if not eps_c:
            continue
        # 拿真 episode 当"当前情境"（留一法）——B/C 在真档上会降级, 如实打印
        ctx = RecallContext(now="2026-09-20", char_id=cid, embed_fn=embed_fn,
                            query=eps_c[0].narration, emo_now=["tease", "smile"],
                            place_now="school_rooftop", place_raw_now="学校天台")
        res = recall_now(st, ctx)
        print(f"  [{cid}] ranked={len(res.items)} pending={len(res.pending)} "
              f"no_rel={res.dropped_no_rel} degraded={sorted(res.degraded)}")
        for c in res.items:
            print(f"    {c.node.id} final={c.final:.3f} rel={c.rel:.3f} "
                  f"prior={c.prior:.3f} via={c.per_channel}")
        for c in res.pending:
            print(f"    (pending) {c.node.id} rel={c.rel:.3f} —— 先验缺席（无 ts）")
        print(f"    knobs={res.knobs}")

    if args.json:
        print(json.dumps({"same": same, "diff": diff, "off": off, "a": rows},
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
