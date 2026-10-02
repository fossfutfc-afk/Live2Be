# -*- coding: utf-8 -*-
"""`panorama.py` —— 全景轮的**取料**（链路 ①b 第一步, 2026-09-23）。

覆盖: 两条通道（字面锚点 / 语义近邻 + 降级）· 锚点稀有度与封顶 · 命中数排序 ·
金字塔递归那一半（上一版 habits 的 refs）· 全量索引与截断 · `worth_running` ·
渲染（自然语言 + 如实标注来源 + 空块不出现）。

真机演练（读 world1/igusa_haruka）见 `.testtmp/probe_panorama.py`。
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brain.read import panorama, recall
from core.brain.read.panorama import build_input
from core.brain.store import WikiStoreV2

NOW = datetime(2026, 9, 25, 12, 0, 0)


def _store(tmp_path) -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id="c")


def _ep(st, text, *, tags=(), place=(), sig=0.6, ts="2026-09-20T10:00:00+09:00"):
    from core.brain import make_node
    nid = st.add(make_node("episode", text=text, tags=list(tags),
                           place=list(place), significance=sig, ts=ts))
    return st.get(nid)


# ---------------------------------------------------------------------------
# 字面锚点通道（今天的主力）
# ---------------------------------------------------------------------------

def test_shared_tag_links_a_candidate(tmp_path):
    st = _store(tmp_path)
    _ep(st, "旧的：橱窗里的模型", tags=["模型店", "橱窗"], sig=0.9)
    new = _ep(st, "新的：又路过那家店", tags=["模型店", "纸兔子"])

    inp = build_input(st, new_ids=[new.id])

    assert inp.mode == "anchor"
    assert [c.id for c in inp.candidates] == ["m0001"]
    c = inp.candidates[0]
    assert c.hits == 1 and c.rarity == 2                  # 两个 tag 各出现在 2 条上
    assert any("同 tag: 模型店" in w for w in c.why)      # **如实标注来源**
    assert "纸兔子" not in " ".join(c.why)                # 只在这一条上的 tag 不算线索
    assert new.id not in [c.id for c in inp.candidates]   # 新增自己不进候选


def test_candidate_must_share_an_anchor(tmp_path):
    st = _store(tmp_path)
    _ep(st, "旧的：完全无关的一件事", tags=["别的"])
    new = _ep(st, "新的", tags=["模型店"])
    _ep(st, "旧的：同 tag", tags=["模型店"])

    inp = build_input(st, new_ids=[new.id])

    assert [c.id for c in inp.candidates] == ["m0003"]
    # ⚠️ 无关的那条**不出现**（索引默认关）—— 她看不到内容的条目不该被摆出来诱惑引用
    assert inp.others == [] and "m0001" not in inp.render()


def test_generic_anchor_is_capped_per_anchor(tmp_path):
    """泛词（"约定"这种）不能把池子冲爆 —— 每个锚点封顶（**预算, 不是判据**）。"""
    st = _store(tmp_path)
    for i in range(5):
        _ep(st, f"旧的 {i}", tags=["约定"], sig=0.5 + i * 0.05)
    new = _ep(st, "新的", tags=["约定"])

    inp = build_input(st, new_ids=[new.id], cap_per_anchor=2)

    assert len(inp.candidates) == 2                       # 只带 2 条（显著性最高的两条）
    assert [c.id for c in inp.candidates] == ["m0005", "m0004"]


def test_rarer_anchor_outranks_generic_one(tmp_path):
    """排序: **具体的证据**比"重要的节点"更像"同一件事"。"""
    st = _store(tmp_path)
    for i in range(3):
        _ep(st, f"泛词 {i}", tags=["约定"], sig=0.95)      # DF=4（三条 + 新的）
    rare = _ep(st, "稀有的那件事", tags=["纸兔子"], sig=0.50)   # DF=2
    new = _ep(st, "新的", tags=["约定", "纸兔子"])

    inp = build_input(st, new_ids=[new.id])

    assert inp.candidates[0].id == rare.id                # 稀有锚点先出, 尽管 sig 更低
    assert inp.candidates[0].rarity < inp.candidates[1].rarity


def test_more_hits_beat_higher_significance(tmp_path):
    """"两条新经历都连着它"比"它自己很重要"更像同一件事（同稀有度时比命中数）。

    注意构造: 一条候选要被**两条新经历**命中, 它的锚点 DF 必然 ≥3 —— 所以对照组也得
    用一个 DF=3 的锚点, 否则比的是稀有度而不是命中数。
    """
    st = _store(tmp_path)
    twice = _ep(st, "被多次连上", tags=["乙", "丁"], sig=0.50)
    once = _ep(st, "被一次连上", tags=["丁"], sig=0.95)
    n1 = _ep(st, "新一", tags=["乙", "丁"])
    n2 = _ep(st, "新二", tags=["乙"])

    inp = build_input(st, new_ids=[n1.id, n2.id])

    first, second = inp.candidates[0], inp.candidates[1]
    assert (first.id, second.id) == (twice.id, once.id)
    assert first.rarity == second.rarity == 3               # 稀有度打平 —— 只由命中数决定
    assert first.hits > second.hits == 1
    assert first.sig < second.sig                           # 显著性更低却排在前面


def test_verbatim_is_not_an_anchor(tmp_path):
    """真机实测: verbatim 共词（"那个"）命中一堆无关条目 —— 不做锚点。"""
    from core.brain import make_node
    st = _store(tmp_path)
    st.add(make_node("episode", text="旧的", verbatim="那个东西", ts="2026-09-20T10:00:00+09:00"))
    new = st.add(make_node("episode", text="新的", verbatim="那个时候",
                           ts="2026-09-21T10:00:00+09:00"))

    inp = build_input(st, new_ids=[new])
    assert inp.candidates == [] and inp.mode == "anchor"


# ---------------------------------------------------------------------------
# 金字塔递归那一半
# ---------------------------------------------------------------------------

def _fake_embed(texts):
    """按关键词造向量 —— 只让"兔子"这一轴相似（tags 完全不重合）。"""
    return [[1.0, 0.0] if "兔子" in t else [0.0, 1.0] for t in texts]


def test_semantic_channel_finds_pairs_without_shared_tags(tmp_path):
    st = _store(tmp_path)
    _ep(st, "旧的：我缝了一只布兔子", tags=["手工"])       # 无共享 tag
    new = _ep(st, "新的：兔子的耳朵歪了", tags=["针线"])

    inp = build_input(st, new_ids=[new.id], embed_fn=_fake_embed)

    assert inp.mode == "semantic"
    assert [c.id for c in inp.candidates] == ["m0001"]    # 字面锚点连不上, 语义连上了
    assert "语义相近" in inp.candidates[0].why[0]
    assert "语义相近" in inp.render()                      # 渲染如实说明是哪种通道


def test_semantic_failure_degrades_to_anchor(tmp_path, caplog):
    st = _store(tmp_path)
    _ep(st, "旧的：橱窗", tags=["模型店"])
    new = _ep(st, "新的", tags=["模型店"])

    def _boom(texts):
        raise RuntimeError("embedding 服务没起")

    with caplog.at_level(logging.INFO, logger="core.brain.read.panorama"):
        inp = build_input(st, new_ids=[new.id], embed_fn=_boom)

    assert inp.mode == "anchor"                           # 降级, 不抛
    assert [c.id for c in inp.candidates] == ["m0001"]
    assert "fallback=anchor" in caplog.text               # 降级**可观测**（同 recall 口径）


def test_embed_text_is_shared_with_recall_not_reimplemented():
    """镜像防漂移: 嵌入口径只有一份（自己再写一份必然漂）。"""
    assert panorama._embed_text is recall._embed_text
    assert panorama._cosine is recall._cosine


# ---------------------------------------------------------------------------
# 索引 / 预算 / 值不值得跑
# ---------------------------------------------------------------------------

def test_others_index_drops_candidates_and_reports_truncation(tmp_path):
    st = _store(tmp_path)
    _ep(st, "被锚点连上", tags=["模型店"], ts="2026-09-20T10:00:00+09:00")
    for i in range(4):
        _ep(st, f"无关 {i}", tags=["别的"], ts=f"2026-09-2{i}T10:00:00+09:00")
    new = _ep(st, "新的", tags=["模型店"], ts="2026-09-24T10:00:00+09:00")

    inp = build_input(st, new_ids=[new.id], index_cap=2)

    assert [c.id for c in inp.candidates] == ["m0001"]
    assert "m0001" not in [n.id for n in inp.others]      # 候选不进索引（不重复摆料）
    assert len(inp.others) == 2 and inp.others_dropped == 2
    assert "还有 2 条更早的没有列出来" in inp.render()


def test_render_omits_empty_blocks(tmp_path):
    st = _store(tmp_path)
    new = _ep(st, "新的", tags=["模型店"])
    text = build_input(st, new_ids=[new.id]).render()

    assert "【这次新消化的经历】" in text
    for absent in ("【你上次给自己写的卡】", "【可能相关的旧经历】", "【其余的经历】"):
        assert absent not in text


def test_empty_library_renders_nothing(tmp_path):
    inp = build_input(_store(tmp_path), new_ids=["m9999"])
    assert inp.render() == "" and inp.worth_running is False
