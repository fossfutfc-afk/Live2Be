# -*- coding: utf-8 -*-
"""wiki_viz — wiki.jsonl 图式可视化（dev 工具, 人读图谱——不是 AI 看 jsonl 快吐了）。

读 data/worlds/{world}/characters/{char}/wiki.jsonl → 图（networkx）:
    - 节点: episode / experience / belief（kind 着色, significance 决定大小,
      出厂 episode 用方框区分——不可变基座）
    - 边: belief/experience → links 支撑（episode）, 带箭头
    - contradictions: 红色虚线

用法:
    python tools/wiki_viz.py --char igusa_haruka              # 默认 world1, PNG 存同目录
    python tools/wiki_viz.py --char igusa_haruka --world w2 --out view.png
    python tools/wiki_viz.py --char igusa_haruka --mermaid    # 输出 mermaid 文本(零依赖替代)

中文渲染: Windows 用 Microsoft YaHei; 无中文字体环境加 --ascii（fallback 转义）。
运行时图操作仍是 dict 邻接（千级节点 O(1)）——networkx 只在此可视化工具（双真源决策不变,
AGENT_BRAIN.md §0.1: dev 工具可选 networkx+matplotlib, requirements-dev 已加）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # 仓库根——任意 cwd 可跑
sys.path.insert(0, str(ROOT))

import networkx as nx                       # dev 依赖（requirements-dev; 运行时不用）

from core.brain.wiki_v2 import WikiStoreV2
from core.brain.wiki_v2.nodes import BrainNode

#: kind → 颜色 / 标签
KIND_STYLE = {
    "episode":     {"color": "#6fa8dc", "label": "经历 episode"},
    "experience":  {"color": "#93c47d", "label": "模式 experience"},
    "belief":      {"color": "#f6b26b", "label": "认知 belief"},
}


def _short(text: str, limit: int = 40) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def build_graph(nodes: list[BrainNode]) -> tuple:
    """→ (networkx.DiGraph, 文本摘要行)。"""
    g = nx.DiGraph()
    for n in nodes:
        main = n.main_text or n.narration or n.content or n.pattern or ""
        g.add_node(n.id, kind=n.kind, sig=n.significance,
                   label=_short(main), seed=n.is_seed())
    for n in nodes:
        for target in n.links:
            if target in g:
                g.add_edge(n.id, target, kind="link")
        for target in n.contradictions:
            if target in g:
                g.add_edge(n.id, target, kind="contra")
    lines = []
    for n in nodes:
        kind_tag = "出厂" if n.is_seed() else n.kind
        lines.append(f"{n.id} [{kind_tag}, sig {n.significance:.2f}] {_short(n.main_text, 60)}")
    return g, lines


def render_png(g, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    # 中文字体（Windows YaHei; 找不到 → 拉丁回退 + 警告）
    font_ok = False
    for name in ("Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC"):
        try:
            font_manager.findfont(name, fallback_to_default=False)
            plt.rcParams["font.family"] = name
            font_ok = True
            break
        except Exception:
            continue
    if not font_ok:
        print("⚠ 无中文字体——图中文字可能显示为方块（--ascii 可换拼音标签）")
    plt.rcParams["axes.unicode_minus"] = False

    pos = _layout(g)
    fig, ax = plt.subplots(figsize=(16, 12))
    for kind, st in KIND_STYLE.items():
        ids = [n for n, d in g.nodes(data=True) if d["kind"] == kind]
        if not ids:
            continue
        sizes = [400 + 2600 * g.nodes[n]["sig"] for n in ids]
        seed_ids = [n for n in ids if g.nodes[n]["seed"]]
        live_ids = [n for n in ids if not g.nodes[n]["seed"]]
        if live_ids:
            nx.draw_networkx_nodes(g, pos, nodelist=live_ids, node_size=sizes,
                                   node_color=st["color"], alpha=0.9, ax=ax,
                                   node_shape="o")
        if seed_ids:                                   # 出厂基座: 方框
            nx.draw_networkx_nodes(g, pos, nodelist=seed_ids,
                                   node_size=[400 + 2600 * g.nodes[n]["sig"]
                                              for n in seed_ids],
                                   node_color=st["color"], alpha=0.9, ax=ax,
                                   node_shape="s",
                                   edgecolors="#333333", linewidths=1.5)
    links = [(u, v) for u, v, d in g.edges(data=True) if d["kind"] == "link"]
    contras = [(u, v) for u, v, d in g.edges(data=True) if d["kind"] == "contra"]
    if links:
        nx.draw_networkx_edges(g, pos, edgelist=links, arrows=True,
                               arrowstyle="-|>", arrowsize=12, width=1.0,
                               edge_color="#999999", alpha=0.7, ax=ax)
    if contras:
        nx.draw_networkx_edges(g, pos, edgelist=contras, arrows=True,
                               arrowstyle="-|>", arrowsize=10, width=1.4,
                               edge_color="#e06666", style="dashed", ax=ax)
    labels = {n: f"{n}\n{_short(g.nodes[n]['label'], 18)}"
              for n in g.nodes}
    nx.draw_networkx_labels(g, pos, labels, font_size=7, ax=ax)
    # 图例
    handles = [plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=st["color"],
                          markersize=11, label=f"{st['label']}（方框 = 出厂基座）"
                          if i == 0 else st["label"])
               for i, st in enumerate(KIND_STYLE.values())]
    ax.legend(handles=handles, loc="upper left", fontsize=9)
    ax.set_title(f"wiki 图谱 — {out.parent.name}（实线 = 支撑链接, 红色虚线 = 矛盾）")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"PNG 已写: {out}")


def _layout(g):
    try:
        return nx.spring_layout(g, k=2.2, seed=42, iterations=120)
    except Exception:
        return nx.circular_layout(g)


def render_mermaid(g, lines: list[str]) -> str:
    """mermaid 图（零依赖, GitHub/VSCode/typora 可渲染）——人类速览兜底。"""
    out = ["```mermaid", "graph LR"]
    for n, d in g.nodes(data=True):
        shape = "[[" if d["kind"] == "belief" else "["
        label = _short(d["label"], 24).replace('"', "'")
        out.append(f'    {n}{shape}"{n}: {label}"{"]" if d["kind"] == "belief" else "]" if d["kind"] == "episode" else "]"}')
    for u, v, d in g.edges(data=True):
        style = "-." if d["kind"] == "contra" else "-->"
        out.append(f"    {u} {style} {v}")
    out.append("```")
    out.append("")
    out.append("节点清单:")
    out.extend(f"- {ln}" for ln in lines)
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="wiki.jsonl 图谱可视化（dev 工具）")
    ap.add_argument("--world", default="world1")
    ap.add_argument("--char", required=True)
    ap.add_argument("--out", default="", help="PNG 输出路径（默认 wiki_viz_{char}.png）")
    ap.add_argument("--mermaid", action="store_true", help="输出 mermaid 文本而非 PNG")
    args = ap.parse_args()

    st = WikiStoreV2(str(ROOT / "data"), world_id=args.world, char_id=args.char)
    if not len(st):
        print(f"空库（或路径不存在）: {st.path}")
        return
    g, lines = build_graph(st.all())
    print(f"{args.char}: {len(g.nodes)} 节点 / {len(g.edges)} 边")
    if args.mermaid:
        print(render_mermaid(g, lines))
        return
    out = Path(args.out) if args.out else Path(f"wiki_viz_{args.char}.png")
    render_png(g, out)


if __name__ == "__main__":
    main()
