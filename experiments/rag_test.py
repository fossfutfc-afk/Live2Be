#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""rag_test.py — core/rag 能力冒烟测试（跨语言检索）。

跑法: python experiments/rag_test.py [--model <embedding 模型 key>]

前提: Bionic/LM Studio 服务运行 + 已加载跨语言 embedding 模型
（lms server start; lms load <embedding> -y）。服务/模型缺失时精确兜底与
降级路径仍会被覆盖, 语义检索用例会打印 SKIP。

覆盖:
    1. place 检索: 中文自由话语 → **地点表键**（PL4 起语料 = `place_entities.json`）
    2. place 精确兜底: 表键 / 别名整串直接命中（零依赖, 0 调用）
    3. place 跨语言: 中/英/日 query —— ⚠️ **表里没有假名别名, 拉丁别名是 slug**
       ⇒ 这一节纯看 embedding 模型的跨语言能力（miss 是预期内的, 不计入失败）
    4. place 低分不匹配 → []（宁缺勿错: 保持上一场景语义）
    5. brain 记忆召回: 临时 wiki 造节点, 跨语言 query 语义召回 top 命中

⚠️ **PL4（2026-09-19）语料换基座**: 旧版读手维护的 `places.yml`（31 条资产 scene slug,
`class_room`/`ramen_ya`/`onsen`）, 现在读**地点表本身**（168 键 / 428 别名）——
返回的是**表键**（`classroom`）, 不是资产 scene_id（`class_room`）。
表里**没有温泉**（旧语料有 `onsen`）这类条目 ⇒ 期望值按表改过。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.brain.nodes import BrainNode, format_id
from core.brain.store import WikiStoreV2
from core.rag import LocalEmbedder, PlaceRetriever, recall_with
from core.rag.embedder import RagError

PASS = "✓"
FAIL = "✗"
SKIP = "⏭"


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    model = None
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]
    try:
        emb = LocalEmbedder(model=model)
        have_model = bool(emb.health())
        if have_model:
            print(f"embedding 模型: {emb.model} @ {emb.base_url}")
    except Exception as e:                     # noqa: BLE001
        emb = None
        have_model = False
        print(f"[rag_test] embedder 初始化失败（将测降级路径）: {e}")

    fails = 0

    # ────────────────────────────────────────────────────────────
    # 1. place 检索（中文自由话语 → 地点表键）
    # ────────────────────────────────────────────────────────────
    section("1. place 检索（自由话语 → 表键; 语料 = place_entities.json）")
    retriever = PlaceRetriever()
    print(f"语料地点键数: {len(retriever.scenes())}")
    cases = [
        # (query, 期望表键) —— 期望值都是**表里的真实键**, 不是资产 scene_id
        ("她们在教学楼天台上看星星", "school_rooftop"),
        ("在教室上课", "classroom"),
        ("一起去拉面店吃面", "foodcart_ramen"),
        ("在便利店里买零食", "convenience_store"),
        ("便利屋68的办公室里商量委托", "68office"),
        ("放学后在图书馆自习", "library"),
        ("夏天去海边玩", "beachside"),
    ]
    for query, want in cases:
        hits = retriever.resolve(query, k=1)
        got = hits[0][0] if hits else None
        score = hits[0][1] if hits else 0.0
        if got == want:
            print(f"{PASS} {query!r:30s} → {got} ({score:.3f})")
        elif not have_model:
            print(f"{SKIP} {query!r:30s} → 无 embedding 模型（期望 {want}, 精确兜底未覆盖）")
        else:
            print(f"{FAIL} {query!r:30s} → {got}（期望 {want}）score={score:.3f}")
            fails += 1

    # ────────────────────────────────────────────────────────────
    # 2. place 精确兜底（零依赖: 表键 / 别名整串, 0 次 embedding）
    # ────────────────────────────────────────────────────────────
    section("2. place 精确兜底（零依赖, 0 调用）")
    for query, want in [("school_rooftop", "school_rooftop"),
                        ("教室", "classroom"),
                        ("图书馆", "library")]:
        got = retriever.resolve_one(query)
        ok = got == want
        if not ok:
            fails += 1
        print(f"{PASS if ok else FAIL} {query!r} → {got}" + ("" if ok else f"（期望 {want}）"))

    # ────────────────────────────────────────────────────────────
    # 3. 跨语言（**表里没有假名别名, 拉丁别名是 slug** —— 全靠模型）
    # ────────────────────────────────────────────────────────────
    section("3. 跨语言（表无假名别名: 这一节纯看 embedding 模型, miss 不计失败）")
    for query, want in [("屋上で星を見ている", "school_rooftop"),
                        ("ラーメン屋で待ち合わせ", "foodcart_ramen"),
                        ("コンビニでお菓子を買う", "convenience_store"),
                        ("rooftop at night under the stars", "school_rooftop")]:
        hits = retriever.resolve(query, k=1)
        got = hits[0][0] if hits else None
        score = hits[0][1] if hits else 0.0
        flag = PASS if got == want else (SKIP if not have_model else "…")
        print(f"{flag} {query!r:34s} → {got} ({score:.3f})（期望 {want}）"
              + ("" if got == want else "  ← 想要字面命中: 在 tempo 表里给该键加这条别名"))

    # ────────────────────────────────────────────────────────────
    # 4. 低分不匹配 → []（宁缺勿错: 上层保持上一场景）
    # ────────────────────────────────────────────────────────────
    section("4. 词表外/低分不匹配")
    hits = retriever.resolve("量子物理实验室里的粒子对撞机", k=1)
    print(f"{PASS if not hits else FAIL} 超纲地点 → {hits if hits else '[]（保持上一场景）'}")
    if hits:
        fails += 1

    # ────────────────────────────────────────────────────────────
    # 5. brain 记忆召回（RAG × brain, 跨语言 query）
    # ────────────────────────────────────────────────────────────
    section("5. brain 记忆召回（临时 wiki + 跨语言 query）")
    with tempfile.TemporaryDirectory() as td:
        store = WikiStoreV2(path=Path(td) / "wiki.jsonl")
        seed_nodes = [
            # 中/日/英混合的记忆（模拟 digest 产物: episode/experience/belief）
            BrainNode(id=format_id("m", 1), kind="episode",
                      significance=0.9, tags=["拆弹", "第一次"],
                      text="第一次帮老师拆炸弹, 手抖得厉害, 但老师说相信我",
                      event_seq=[1]),
            BrainNode(id=format_id("m", 2), kind="episode",
                      significance=0.7, tags=["礼物", "杂草"],
                      text="送了一盆杂草给老师当谢礼",
                      event_seq=[2]),
            BrainNode(id=format_id("m", 3), kind="episode",
                      significance=0.6, tags=["拉面", "夜"],
                      text="深夜和老师蹲在路边摊吃拉面, 热气腾腾",
                      event_seq=[3]),
            BrainNode(id=format_id("m", 4), kind="belief",
                      significance=0.85, tags=["信任"],
                      text="老师是唯一不会嫌弃我的人, 我愿意为他做任何事"),
            BrainNode(id=format_id("m", 5), kind="profile",
                      significance=0.5, subject="player", tags=["口头禅"],
                      text="老师每次夸我, 我都会慌慌张张地道歉"),
        ]
        for n in seed_nodes:
            errors = n.validate()
            if errors:
                print(f"{FAIL} 种子节点校验失败: {n.id} {errors}")
                fails += 1
            store.add(n)
        store.save()

        queries = [
            # (query, 期望命中的节点 id) —— 语义命中（RAG 目的）: 字符不重叠也要召回
            ("她还记得第一次帮老师拆炸弹的事吗", "m0001"),
            ("老师送她什么她都想报答——杂草礼物的回忆", "m0002"),
            ("ラーメンを一緒に食べた夜の記憶", "m0003"),
            ("她觉得自己配不上老师吗——信任相关的认知", "m0004"),
        ]
        for query, want_id in queries:
            recalled = recall_with(store, query=query, k_sim=3, n_precious=1,
                                   n_random=0, embedder=emb)
            if not recalled:
                print(f"{FAIL} query {query!r} → 无召回（期望含 {want_id}）")
                fails += 1
                continue
            ids = [n.id for n in recalled]
            hit = want_id in ids[:3]
            flag = PASS if hit else (SKIP if not have_model else FAIL)
            if flag == FAIL:
                fails += 1
            top = recalled[0]
            text = f"{top.narration} {top.content} {top.pattern}".strip()
            print(f"{flag} query {query!r:44s} → top: {top.id} {text[:28]!r}"
                  + ("" if hit else f"（期望 {want_id} 在 top3）"))
            for n in recalled[1:3]:
                t = f"{n.narration} {n.content} {n.pattern}".strip()
                print(f"        └ {n.id} {t[:40]!r}")

    print("\n" + ("🎉 全部通过" if fails == 0 else f"❌ {fails} 项失败"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
