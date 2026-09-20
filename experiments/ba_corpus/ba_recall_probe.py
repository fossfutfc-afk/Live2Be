# -*- coding: utf-8 -*-
"""ba_recall_probe.py — **粒度假设**的对照测量（episode 要不要一章一条）。

## 用户 2026-09-20 的怀疑

> *"我怀疑现在的 episode 组织不利好 RAG 召回，似乎 episode 最好与 bond 一一对应，
> 这样召回才好"*

现状（实测）: **一章 → 2~4 条 episode**（真档 haruka 一章 seg-30 出 4 条;
BA 语料 14 章 / 31 条）。若一章一条, 召回单位 = 章; 若一章多条, 召回单位 = 片段。

## 量三件事（**只用本地 embedding, 零 API 成本**）

| # | 量什么 | 说明"一章一条"会不会更好 |
|---|---|---|
| 1 | 同章对 / 跨章对 / 域外的 cos 分数带 | 太挤 ⇒ 片段级分不开章 ⇒ 粗粒度也救不了 |
| 2 | 留一法: 拿一条 episode 当 query, 能不能找到**同章的其他条** | 片段级召回的**上限**（能找回同章 = 召回有效） |
| 3 | 章向量（该章各条均值）之间的 cos | **粗粒度的代价**: 章向量互相像不像（越像越分不开章） |

⚠️ 本脚本**不做**真机 digest 重跑 —— 那要花钱; 它量的是"粒度改动的收益上限"。

用法:
    python experiments/ba_corpus/ba_recall_probe.py [--results .testtmp/ba_digest_results.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.rag.brain import make_embed_fn                    # noqa: E402
from core.rag.embedder import LocalEmbedder                 # noqa: E402

#: 用户点名的五档（gid → 用户叫法）
FIVE = {
    "1600002": "错误收信人1",
    "1600003": "错误沟通2",
    "1600005": "错误方式3",
    "1600006": "错误揣测4",
    "1600008": "错误地点5(memorial)",
}

#: 域外 query（探"无关"基线）
OFF_DOMAIN = [
    "今天的数学作业还没写完, 我先去趟便利店买点饭团。",
    "The quick brown fox jumps over the lazy dog.",
]


def _cos(a, b) -> float:
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if not na or not nb:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _mean(vs):
    if not vs:
        return []
    n = len(vs)
    return [sum(v[i] for v in vs) / n for i in range(len(vs[0]))]


def _band(vs) -> str:
    if not vs:
        return "-"
    return f"n={len(vs):<3} min={min(vs):.3f} mean={sum(vs)/len(vs):.3f} max={max(vs):.3f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=".testtmp/ba_digest_results.json")
    args = ap.parse_args()

    rows = json.loads(Path(ROOT / args.results).read_text(encoding="utf-8"))
    emb = LocalEmbedder()
    print(f"[后端] model={emb.model!r} health={emb.health()}")
    if not emb.health():
        print("embedding 服务不可用 → 本脚本无事可做")
        return 2
    embed_fn = make_embed_fn(emb)

    texts = [r["narration"] for r in rows]
    vecs = embed_fn(texts + OFF_DOMAIN)
    ev, off = vecs[:len(rows)], vecs[len(rows):]
    idx = {r["id"] + r["gid"]: i for i, r in enumerate(rows)}

    print(f"[语料] {len(rows)} 条 episode / {len({r['gid'] for r in rows})} 章 / "
          f"{len({r['ch'] for r in rows})} 个角色")

    # ── 1. 分数带 ─────────────────────────────────────────────────────
    same, cross = [], []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            c = _cos(ev[i], ev[j])
            (same if rows[i]["gid"] == rows[j]["gid"] else cross).append(c)
    offband = [_cos(q, v) for q in off for v in ev]
    print("\n=== 1. 片段级 cos 分数带 ===")
    print(f"  同章对   {_band(same)}")
    print(f"  跨章对   {_band(cross)}")
    print(f"  域外 query {_band(offband)}")
    if same and cross:
        sep = (sum(same) / len(same)) - (sum(cross) / len(cross))
        print(f"  分层: 同章均值 − 跨章均值 = {sep:+.3f}"
              f"{'  ← 几乎没分层' if abs(sep) < 0.03 else ''}")

    # ── 2. 留一法: 一条片段能不能找回同章的其他条 ────────────────────
    print("\n=== 2. 留一法（同章召回率; 只对同章 ≥2 条的章有意义）===")
    hit1 = hit3 = asked = 0
    detail = defaultdict(list)
    for i, r in enumerate(rows):
        mates = [j for j, o in enumerate(rows)
                 if j != i and o["gid"] == r["gid"]]
        if not mates:
            continue
        asked += 1
        ranked = sorted((( _cos(ev[i], ev[j]), j) for j in range(len(rows)) if j != i),
                        key=lambda t: -t[0])
        rank_of_first_mate = next(k for k, (_, j) in enumerate(ranked, 1)
                                  if rows[j]["gid"] == r["gid"])
        if rank_of_first_mate == 1:
            hit1 += 1
        if rank_of_first_mate <= 3:
            hit3 += 1
        name = FIVE.get(r["gid"], r["gid"])
        detail[name].append((r["id"], rank_of_first_mate,
                             [f"{rows[j]['id']}@{s:.3f}" for s, j in ranked[:3]]))
    print(f"  top1 是同章: {hit1}/{asked}   top3 内有同章: {hit3}/{asked}")
    for name in sorted(detail):
        for rid, rk, top3 in detail[name]:
            flag = "✓" if rk == 1 else ("~" if rk <= 3 else "✗")
            print(f"    {flag} {name:<22} {rid} 同章首现名次={rk}  top3={top3}")

    # ── 3. 章向量（粗粒度代理）────────────────────────────────────────
    by_ch = defaultdict(list)
    for i, r in enumerate(rows):
        by_ch[r["gid"]].append(ev[i])
    chv = {g: _mean(vs) for g, vs in by_ch.items()}
    ch_cross = []
    gids = sorted(chv)
    for a in range(len(gids)):
        for b in range(a + 1, len(gids)):
            ch_cross.append(_cos(chv[gids[a]], chv[gids[b]]))
    print("\n=== 3. 章向量（粗粒度代理）===")
    print(f"  章↔章（均值向量）{_band(ch_cross)}")
    print(f"  （对照: 片段级跨章 {_band(cross)}）← 章向量互相更像 = 粗粒度把章揉成一团")
    # 片段去认自己的章 —— **必须把 query 那条排除出它自己所属章的池子**,
    # 否则 `max` 会取到 cos(query, query)=1.0 → 恒命中。
    # （第一版就是这么写错的: 印出来的 31/31 是泄漏, 已修。）
    ok_max = ok_mean = asked3 = 0
    for i, r in enumerate(rows):
        sc_max, sc_mean = {}, {}
        for g in by_ch:
            members = [j for j in range(len(rows))
                       if rows[j]["gid"] == g and j != i]
            if not members:
                continue                 # 该章只剩 0 条（单条章被抽走）→ 不计
            sc_max[g] = max(_cos(ev[i], ev[j]) for j in members)
            sc_mean[g] = _cos(ev[i], _mean([ev[j] for j in members]))
        if r["gid"] not in sc_max:
            continue                     # 自己的章没得比 → 不入分母
        asked3 += 1
        ok_max += (max(sc_max, key=lambda g: sc_max[g]) == r["gid"])
        ok_mean += (max(sc_mean, key=lambda g: sc_mean[g]) == r["gid"])
    print(f"  片段认章（max-cos 聚合, 已排自己）: {ok_max}/{asked3}")
    print(f"  片段认章（均值向量,   已排自己）: {ok_mean}/{asked3}")
    print(f"  （分母 = 同章 ≥2 条的片段数; 单条章被抽走后无从对比）")

    # ── 4. 五档各自的章内/章外分数 ────────────────────────────────────
    print("\n=== 4. 五档（用户点名）章内 vs 章外 ===")
    for gid, name in FIVE.items():
        mine = [i for i, r in enumerate(rows) if r["gid"] == gid]
        others = [i for i, r in enumerate(rows) if r["gid"] != gid]
        ins = [_cos(ev[i], ev[j]) for a, i in enumerate(mine) for j in mine[a + 1:]]
        outs = [_cos(ev[i], ev[j]) for i in mine for j in others]
        print(f"  {name:<22} 条数={len(mine)}  章内 {_band(ins) if ins else '(单条)'}"
              f"  章外 {_band(outs)}")
    # ── 5. 文本形态对照（用户 2026-09-20: *"添加更多文本说不定反而会增加 RAG 能力"*）──
    # 同一批 query（26 个"同章 ≥2 条"的片段，认自己的章），三种文本形态，**都排除 query 自己**:
    #   ① 原子（只有 narration）
    #   ② 带标签原子（title 打头 —— 对标 AgentGal 的"高密度字段拼装"）
    #   ③ **章拼接**（同章各条 narration 拼成一篇长文档 = "一章一条"的真身）
    print("\n=== 5. 文本形态对照（片段 → 认自己的章 top-1; 都排除 query 自己）===")
    ch_of = sorted({r["gid"] for r in rows})
    ev_lab = embed_fn([f"{r.get('title', '')}\n{r['narration']}" for r in rows])

    def _mates(i: int, g: str) -> list[int]:
        """章 g 里除了 query 自己以外的成员下标。"""
        return [j for j in range(len(rows))
                if rows[j]["gid"] == g and not (g == rows[i]["gid"] and j == i)]

    def _doc_len(i: int, g: str) -> int:
        return len("\n".join(rows[j]["narration"] for j in _mates(i, g)))

    _concat_cache: dict[tuple[int, str], str] = {}
    for i, r in enumerate(rows):
        for g in ch_of:
            m = _mates(i, g)
            if m:                             # 章 g 里剔掉 query 自己后的原文
                _concat_cache[(i, g)] = "\n".join(rows[j]["narration"] for j in m)
    # ⚠️ **一次批式** embedding: 逐条 `embed_fn([txt])` 会变成 300+ 次 HTTP（实测把脚本拖死）
    _uniq = sorted(set(_concat_cache.values()))
    _vmap = dict(zip(_uniq, embed_fn(_uniq)))

    def _s_concat(i: int, g: str) -> float:
        v = _vmap.get(_concat_cache.get((i, g), ""))
        return _cos(ev[i], v) if v else -1.0

    def _s_atom(i: int, g: str) -> float:
        m = _mates(i, g)
        return max((_cos(ev[i], ev[j]) for j in m), default=-1.0)

    def _s_atom_lab(i: int, g: str) -> float:
        m = _mates(i, g)
        return max((_cos(ev_lab[i], ev_lab[j]) for j in m), default=-1.0)

    def _acc(score_fn) -> tuple[int, int]:
        hit = asked = 0
        for i, r in enumerate(rows):
            if not _mates(i, r["gid"]):
                continue                      # 单条章: 抽走自己就没得比
            sc = {g: score_fn(i, g) for g in ch_of}
            asked += 1
            hit += (max(sc, key=lambda g: sc[g]) == r["gid"])
        return hit, asked

    lengths = [_doc_len(i, g) for i, r in enumerate(rows) for g in ch_of
               if g != r["gid"] or _mates(i, g)]
    print(f"  章拼接文档长度: min={min(lengths)} max={max(lengths)} 字"
          f"（⚠️ 过长会被模型截断, 本机 nomic 的上下文窗口未知）")
    for name, fn in (("① 原子(narration)", _s_atom),
                     ("② 带标签原子(title+正文)", _s_atom_lab),
                     ("③ 章拼接(长文本)", _s_concat)):
        hit, asked = _acc(fn)
        print(f"  {name:<24} 认回自己的章 {hit}/{asked}")

    in_d, out_d = [], []
    for i, r in enumerate(rows):
        m = _mates(i, r["gid"])
        if m:
            in_d.append(_s_concat(i, r["gid"]))
        out_d += [_s_concat(i, g) for g in ch_of if g != r["gid"]]
    print(f"  章拼接分层: 章内 {_band(in_d)}")
    print(f"  章拼接分层: 章外 {_band(out_d)}")
    print(f"  （原子对照: 章内 {_band(same)} / 章外 {_band(cross)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
