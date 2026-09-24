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

from core.brain.wiki_v2 import notes, panorama, recall
from core.brain.wiki_v2.panorama import build_input
from core.brain.wiki_v2.store import WikiStoreV2

NOW = datetime(2026, 9, 25, 12, 0, 0)


def _store(tmp_path) -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id="c")


def _ep(st, text, *, tags=(), items=(), place=(), sig=0.6, ts="2026-09-20T10:00:00+09:00"):
    from core.brain.wiki_v2 import make_node
    nid = st.add(make_node("episode", text=text, tags=list(tags), items=list(items),
                           place=list(place), significance=sig, ts=ts))
    return st.get(nid)


def _note_state(**kw) -> notes.NotesState:
    return notes.NotesState(**kw)


# ---------------------------------------------------------------------------
# 字面锚点通道（今天的主力）
# ---------------------------------------------------------------------------

def test_shared_tag_links_a_candidate(tmp_path):
    st = _store(tmp_path)
    _ep(st, "旧的：橱窗里的模型", tags=["模型店", "橱窗"], sig=0.9)
    new = _ep(st, "新的：又路过那家店", tags=["模型店", "纸兔子"])

    inp = build_input(st, _note_state(), new_ids=[new.id])

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

    inp = build_input(st, _note_state(), new_ids=[new.id])

    assert [c.id for c in inp.candidates] == ["m0003"]
    assert [n.id for n in inp.others] == ["m0001"]        # 无关的落进"其余"索引


def test_generic_anchor_is_capped_per_anchor(tmp_path):
    """泛词（"约定"这种）不能把池子冲爆 —— 每个锚点封顶（**预算, 不是判据**）。"""
    st = _store(tmp_path)
    for i in range(5):
        _ep(st, f"旧的 {i}", tags=["约定"], sig=0.5 + i * 0.05)
    new = _ep(st, "新的", tags=["约定"])

    inp = build_input(st, _note_state(), new_ids=[new.id], cap_per_anchor=2)

    assert len(inp.candidates) == 2                       # 只带 2 条（显著性最高的两条）
    assert [c.id for c in inp.candidates] == ["m0005", "m0004"]


def test_rarer_anchor_outranks_generic_one(tmp_path):
    """排序: **具体的证据**比"重要的节点"更像"同一件事"。"""
    st = _store(tmp_path)
    for i in range(3):
        _ep(st, f"泛词 {i}", tags=["约定"], sig=0.95)      # DF=4（三条 + 新的）
    rare = _ep(st, "稀有的那件事", tags=["纸兔子"], sig=0.50)   # DF=2
    new = _ep(st, "新的", tags=["约定", "纸兔子"])

    inp = build_input(st, _note_state(), new_ids=[new.id])

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

    inp = build_input(st, _note_state(), new_ids=[n1.id, n2.id])

    first, second = inp.candidates[0], inp.candidates[1]
    assert (first.id, second.id) == (twice.id, once.id)
    assert first.rarity == second.rarity == 3               # 稀有度打平 —— 只由命中数决定
    assert first.hits > second.hits == 1
    assert first.sig < second.sig                           # 显著性更低却排在前面


def test_verbatim_is_not_an_anchor(tmp_path):
    """真机实测: verbatim 共词（"那个"）命中一堆无关条目 —— 不做锚点。"""
    from core.brain.wiki_v2 import make_node
    st = _store(tmp_path)
    st.add(make_node("episode", text="旧的", verbatim="那个东西", ts="2026-09-20T10:00:00+09:00"))
    new = st.add(make_node("episode", text="新的", verbatim="那个时候",
                           ts="2026-09-21T10:00:00+09:00"))

    inp = build_input(st, _note_state(), new_ids=[new])
    assert inp.candidates == [] and inp.mode == "anchor"


# ---------------------------------------------------------------------------
# 金字塔递归那一半
# ---------------------------------------------------------------------------

def test_habit_refs_enter_the_pool_with_lowest_priority(tmp_path):
    st = _store(tmp_path)
    cited = _ep(st, "我上次引用过的", tags=["无关标签"], sig=0.9)
    anchored = _ep(st, "被锚点连上的", tags=["模型店"], sig=0.5)
    new = _ep(st, "新的", tags=["模型店"])

    state = _note_state(habits=[notes.NoteItem(id="n1", text="惯例", refs=[cited.id])])
    inp = build_input(st, _note_state(habits=state.habits), new_ids=[new.id])

    ids = [c.id for c in inp.candidates]
    assert cited.id in ids and anchored.id in ids
    assert ids[0] == anchored.id                          # 新料（锚点命中）优先
    cited_c = next(c for c in inp.candidates if c.id == cited.id)
    assert "你上次引用了它" in cited_c.why


def test_dangling_habit_ref_is_skipped(tmp_path):
    st = _store(tmp_path)
    new = _ep(st, "新的", tags=["模型店"])
    state = _note_state(habits=[notes.NoteItem(id="n1", text="惯例", refs=["m9999"])])

    inp = build_input(st, state, new_ids=[new.id])
    assert inp.candidates == []                           # 悬空引用不炸、也不进池
    assert inp.habits[0].id == "n1"                       # 但上一版惯例照样摆出来


# ---------------------------------------------------------------------------
# 语义近邻通道（本机服务未起 ⇒ 只有假 embedder 能测）
# ---------------------------------------------------------------------------

def _fake_embed(texts):
    """按关键词造向量 —— 只让"兔子"这一轴相似（tags 完全不重合）。"""
    return [[1.0, 0.0] if "兔子" in t else [0.0, 1.0] for t in texts]


def test_semantic_channel_finds_pairs_without_shared_tags(tmp_path):
    st = _store(tmp_path)
    _ep(st, "旧的：我缝了一只布兔子", tags=["手工"])       # 无共享 tag
    new = _ep(st, "新的：兔子的耳朵歪了", tags=["针线"])

    inp = build_input(st, _note_state(), new_ids=[new.id], embed_fn=_fake_embed)

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

    with caplog.at_level(logging.INFO, logger="core.brain.wiki_v2.panorama"):
        inp = build_input(st, _note_state(), new_ids=[new.id], embed_fn=_boom)

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

    inp = build_input(st, _note_state(), new_ids=[new.id], index_cap=2)

    assert [c.id for c in inp.candidates] == ["m0001"]
    assert "m0001" not in [n.id for n in inp.others]      # 候选不进索引（不重复摆料）
    assert len(inp.others) == 2 and inp.others_dropped == 2
    assert "还有 2 条更早的没有列出来" in inp.render()


def test_worth_running_needs_new_material_or_pending_close(tmp_path):
    st = _store(tmp_path)
    new = _ep(st, "新的", tags=["模型店"])

    assert build_input(st, _note_state(), new_ids=[new.id]).worth_running is True
    closed = notes.NoteItem(id="n1", text="买花", closed_at="x", reason="送出去了")
    assert build_input(st, _note_state(promise=[closed]), new_ids=[]).worth_running is True
    # 只有新旧惯例、没有新料也没有待结清 ⇒ 别跑（跑了只是措辞空转）
    habits = [notes.NoteItem(id="n2", text="惯例", refs=["m0001"])]
    assert build_input(st, _note_state(habits=habits), new_ids=[]).worth_running is False


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def test_render_is_natural_language_with_evidence_and_caveats(tmp_path):
    st = _store(tmp_path)
    _ep(st, "旧的：橱窗", tags=["模型店"], sig=0.9)
    _ep(st, "旧的：无关的一条", tags=["别的"])
    new = _ep(st, "新的：又路过那家店", tags=["模型店"])
    state = _note_state(
        promise=[notes.NoteItem(id="n1", text="周六模型店", refs=["m0001"],
                                since="2026-09-20T10:00:00+09:00"),
                 notes.NoteItem(id="n2", text="买花", refs=["m0001"],
                                closed_at="2026-09-21T10:00:00+09:00",
                                reason="送出去了")],
        habits=[notes.NoteItem(id="n4", text="他总先问我想要哪个", refs=["m0001"])],
        on_mind=notes.NoteItem(text="我不想再隔着玻璃看", refs=["m0001"]))

    text = build_input(st, state, new_ids=[new.id]).render(now=NOW)
    lines = text.splitlines()

    assert lines[0].startswith("【你手上还开着的约定】")
    assert "  n1 周六模型店 (m0001)  ← 记于 5 天前" in lines
    assert any(l.startswith("【已经结清、图里还没接住的】") for l in lines)
    assert any("  n2 买花 (m0001)  ← 已结清（送出去了）" == l for l in lines)
    assert any(l.startswith("【你之前记下的惯例】") for l in lines)
    assert any(l.startswith("【你最近在想】") for l in lines)
    assert any(l.startswith("【这次新消化的经历】") for l in lines)
    assert any("**不一定是同一件事**" in l for l in lines)      # 如实说"这不是判据"
    assert any(l.startswith("【其余的经历】") for l in lines)
    assert any("（与 m0003 同 tag: 模型店" in l for l in lines)     # 来源标注 = 圆括号
    assert any("你上次引用了它）" in l for l in lines)            # 递归那一半也标出来
    for junk in ("{", "}", "[", "]", '"', "promise", "habits", "on_mind", "refs"):
        assert junk not in text, junk


def test_render_omits_empty_blocks(tmp_path):
    st = _store(tmp_path)
    new = _ep(st, "新的", tags=["模型店"])
    text = build_input(st, _note_state(), new_ids=[new.id]).render()

    assert "【这次新消化的经历】" in text
    for absent in ("【你手上还开着的约定】", "【已经结清、图里还没接住的】",
                   "【你之前记下的惯例】", "【你最近在想】", "【可能相关的旧经历】"):
        assert absent not in text


def test_empty_library_renders_nothing(tmp_path):
    inp = build_input(_store(tmp_path), _note_state(), new_ids=["m9999"])
    assert inp.render() == "" and inp.worth_running is False


def test_render_without_now_omits_time_phrase(tmp_path):
    st = _store(tmp_path)
    new = _ep(st, "新的", tags=["模型店"])
    state = _note_state(promise=[notes.NoteItem(id="n1", text="约定", refs=["m0001"],
                                                since="2026-09-20T10:00:00+09:00")])
    text = build_input(st, state, new_ids=[new.id]).render(now=None)
    assert "  n1 约定 (m0001)\n" in text                  # 不加时间短语, 也不编一个
    assert "记于" not in text
