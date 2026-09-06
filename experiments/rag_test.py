#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""rag_test.py — core/rag 能力冒烟测试（跨语言检索）。

跑法: python experiments/rag_test.py [--model <embedding 模型 key>]

前提: Bionic/LM Studio 服务运行 + 已加载跨语言 embedding 模型
（lms server start; lms load <embedding> -y）。服务/模型缺失时精确兜底与
降级路径仍会被覆盖, 语义检索用例会打印 SKIP。

覆盖:
    1. place 跨语言检索: 中/英/日 query → scene_id（背景管线用例）
    2. place 精确兜底: 词表 id / 别名子串直接命中（零依赖路径）
    3. place 低分不匹配 → []（宁缺勿错: 保持上一场景语义）
    4. brain 记忆召回: 临时 wiki 造节点, 跨语言 query 语义召回 top 命中
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.brain.wiki_v2.nodes import BrainNode, format_id
from core.brain.wiki_v2.store import WikiStoreV2
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
    # 1. place 跨语言检索
    # ────────────────────────────────────────────────────────────
    section("1. place 跨语言检索（LLM 话语 → scene_id）")
    retriever = PlaceRetriever()
    print(f"语料 scene 数: {len(retriever.scenes())}")
    cases = [
        # (query, 期望 scene)
        ("她们在教学楼天台上看星星", "school_rooftop"),
        ("rooftop at night under the stars", "school_rooftop"),
        ("屋上で星を見ている", "school_rooftop"),
        ("在教室上课", "class_room"),
        ("classroom", "class_room"),
        ("一起去拉面店吃面", "ramen_ya"),
        ("ラーメン屋で待ち合わせ", "ramen_ya"),
        ("便利屋68的部室里商量委托", "gehenna_club_room"),
        ("在便利店里买零食", "convenience_store"),
        ("コンビニでお菓子を買う", "convenience_store"),
        ("泡温泉放松", "onsen"),
        ("beach in summer", "beachside"),
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
    # 2. place 精确兜底（零依赖: id / 别名整串）
    # ────────────────────────────────────────────────────────────
    section("2. place 精确兜底（零依赖）")
    for query, want in [("school_rooftop", "school_rooftop"),
                        ("教室", "class_room"),
                        ("屋上", "school_rooftop")]:
        got = retriever.resolve_one(query)
        ok = got == want
        if not ok:
            fails += 1
        print(f"{PASS if ok else FAIL} {query!r} → {got}" + ("" if ok else f"（期望 {want}）"))

    # ────────────────────────────────────────────────────────────
    # 3. 低分不匹配 → []（宁缺勿错: 上层保持上一场景）
    # ────────────────────────────────────────────────────────────
    section("3. 词表外/低分不匹配")
    hits = retriever.resolve("量子物理实验室里的粒子对撞机", k=1)
    print(f"{PASS if not hits else FAIL} 超纲地点 → {hits if hits else '[]（保持上一场景）'}")
    if hits:
        fails += 1

    # ────────────────────────────────────────────────────────────
    # 4. brain 记忆召回（RAG × wiki_v2, 跨语言 query）
    # ────────────────────────────────────────────────────────────
    section("4. brain 记忆召回（临时 wiki + 跨语言 query）")
    with tempfile.TemporaryDirectory() as td:
        store = WikiStoreV2(path=Path(td) / "wiki.jsonl")
        seed_nodes = [
            # 中/日/英混合的记忆（模拟 digest 产物: episode/experience/belief）
            BrainNode(id=format_id("m", 1), kind="episode", epistemic="observed_fact",
                      significance=0.9, tags=["拆弹", "第一次"],
                      narration="第一次帮老师拆炸弹, 手抖得厉害, 但老师说相信我",
                      event_seq=[1]),
            BrainNode(id=format_id("m", 2), kind="episode", epistemic="observed_fact",
                      significance=0.7, tags=["礼物", "杂草"],
                      narration="送了一盆杂草给老师当谢礼",
                      event_seq=[2]),
            BrainNode(id=format_id("m", 3), kind="episode", epistemic="observed_fact",
                      significance=0.6, tags=["拉面", "夜"],
                      narration="深夜和老师蹲在路边摊吃拉面, 热气腾腾",
                      event_seq=[3]),
            BrainNode(id=format_id("m", 4), kind="belief", epistemic="inferred_belief",
                      significance=0.85, tags=["信任"],
                      content="老师是唯一不会嫌弃我的人, 我愿意为他做任何事",
                      links=["m0001"]),
            BrainNode(id=format_id("m", 5), kind="experience", epistemic="observed_fact",
                      significance=0.5, subject="player", tags=["口头禅"],
                      pattern="老师每次夸我, 我都会慌慌张张地道歉", count=5),
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
