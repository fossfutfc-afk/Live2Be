"""⭐ N2 —— Round B（L2）的输入视图（2026-09-29）。

三件事（`TODO.md` N2）:
  ① 认知行 `〔u0001｜belief｜被引 3〕正文` + 缩进续行 `edges: …`（今天只有 experience 印次数、一条边都不印）
  ② 候选行从"只有编号"变成"**编号 + 正文 + 被引 + 边 + 为什么被推荐**"
  ③ 新经历行 `〔m0025｜《标题》〕正文`（编号是钥匙、书名号里是 gist）

⚠️ 本地 id 纪律: **认知印 `u0001`、episode 印真实 `m0004`**（R2 的 decisions 本来就用真实
id 指 episode）; **列表外的认知只报数, 绝不编一个看不到正文的号**。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brain import WikiStoreV2, make_node          # noqa: E402
from core.digest.material import _round_b_material        # noqa: E402
from core.brain.read.recall import recommend_candidates     # noqa: E402
from core.brain.read.render import (                        # noqa: E402
    render_cognition_line, render_cognition_list,
)


def _belief(st, text, *, subject="", sig=0.9, tags=None, eid=None):
    return st.add(make_node("belief", text=text, subject=subject, significance=sig,
                            tags=list(tags or []), event_seq=[1], id=eid) if eid
                  else make_node("belief", text=text, subject=subject, significance=sig,
                                 tags=list(tags or []), event_seq=[1]))


def _store(tmp_path) -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id="c")


# ---------------------------------------------------------------------------
# ① 认知行形态 + 边
# ---------------------------------------------------------------------------

def test_cognition_line_shape_and_edges(tmp_path):
    st = _store(tmp_path)
    a = st.add(make_node("belief", text="老师是第一个不会嫌弃我的人", subject="sensei", significance=0.9))
    b = st.add(make_node("belief", text="重要东西要收起来", subject="我", significance=0.8))
    ep1 = st.add(make_node("episode", text="天台夜谈", title="天台", event_seq=[1]))
    ep2 = st.add(make_node("episode", text="杂草屋", title="杂草屋", event_seq=[2]))
    st.add_edge("supports", ep1, a)
    st.add_edge("supports", ep2, a)
    st.add_edge("supports", a, b)
    st.add_edge("contradicts", a, b)

    text, local = render_cognition_list(st)
    assert "〔u0001｜belief｜被引 2｜sig 0.90〕sensei：老师是第一个不会嫌弃我的人" in text, text
    # 边: episode 印**真实 id**、认知印**本地号**（顺序不保证 ⇒ 按集合断言）
    edge_line = next(ln for ln in text.splitlines() if "edges:" in ln)
    assert set(edge_line.strip().split()[1:]) == {
        "supports→u0002", "contradicts→u0002", "supports←m0003", "supports←m0004"}, edge_line
    print("    认知行: 元信息进 `〔〕` + 边续行（episode 真实 id / 认知本地号）")


def test_cognition_edges_outside_are_counted_not_numbered(tmp_path):
    """列表外的认知**只报数** —— 绝不给它编一个看不到正文的号。"""
    st = _store(tmp_path)
    a = st.add(make_node("belief", text="看得见的",
                         significance=0.9))
    far = st.add(make_node("belief", text="列表外的",
                           significance=0.1))
    st.add_edge("supports", a, far)
    ent = st.add(make_node("entity", name="sensei", text=""))
    st.add_edge("about", a, ent)
    text, _local = render_cognition_list(st, cap=1)          # cap=1 ⇒ far 不在列表里
    assert "（另有 2 条边指向列表外）" in text, text
    assert far not in text and ent not in text
    print("    认知边: 列表外的只计数（不编号）")


def test_cognition_edges_capped(tmp_path):
    """边封顶（`被引 N` 已经说明有几条）—— 20 条边不该印 20 个。"""
    st = _store(tmp_path)
    a = st.add(make_node("belief", text="被很多人印证",
                         significance=0.9))
    for i in range(12):
        ep = st.add(make_node("episode", text=f"第{i}次", title=f"第{i}次",
                              event_seq=[i + 1]))
        st.add_edge("supports", ep, a)
    text, _ = render_cognition_list(st)
    assert "被引 12" in text and "…（另有 6 条）" in text, text
    print("    认知边: 封顶 6 条 + 计数（少花 ≠ 少信息）")


def test_cognition_line_shared_by_list_and_candidate(tmp_path):
    """⭐ 两个调用者**共用同一份**渲染（`render_cognition_line`）—— 各写一份必漂。"""
    st = _store(tmp_path)
    st.add(make_node("belief", text="x" * 200, subject="sensei", significance=0.9))
    row_list = render_cognition_line(st, st.all()[0], st.graph(), {"m0001": "u0001"})
    row_cand = render_cognition_line(st, st.all()[0], st.graph(), {"m0001": "u0001"},
                                     max_body=60, indent="  ")
    assert row_list[0].startswith("〔u0001｜belief｜被引 0｜sig 0.90〕sensei：")
    assert row_cand[0].startswith("  〔u0001｜belief｜被引 0｜sig 0.90〕")
    assert len(row_list[0]) > len(row_cand[0])               # 正文截断长度不同
    print("    认知行: 列表与候选共用同一份渲染（只有截断长度/缩进不同）")


# ---------------------------------------------------------------------------
# ② 候选行 + why
# ---------------------------------------------------------------------------

def test_candidate_block_carries_body_and_why(tmp_path):
    """候选行不再是光秃秃的编号 —— 正文 / 被引 / why 都在。"""
    st = _store(tmp_path)
    st.add(make_node("belief", text="我喜欢照顾杂草", subject="杂草", significance=0.9,
                     tags=["杂草"]))
    ep = st.add(make_node("episode", text="今天又去看了杂草", title="看杂草",
                          tags=["杂草"], event_seq=[1]))
    _text, local_of = render_cognition_list(st)
    out = _round_b_material(st, [ep], local_of, None)
    assert "〔m0002｜《看杂草》〕今天又去看了杂草" in out, out
    # ⚠️ 本用例里 subject 命中（0.85）压过 tags（0.60）—— 取最大值的语义
    assert "→ 候选 0.85（为什么: subject 点名）:" in out, out
    assert "       〔u0001｜belief｜被引 0｜sig 0.90〕杂草：我喜欢照顾杂草" in out, out
    assert "仅供参照" in out
    print("    候选行: 编号 + 正文 + 被引 + why（tags 命中）")


def test_why_sources_are_parallel_to_result(tmp_path):
    """`why_out` 与返回值**等长同序**，且三种字面来源都说得出来。"""
    st = _store(tmp_path)
    st.add(make_node("belief", text="关于猫的看法", subject="夜猫子", significance=0.9, tags=["猫"]))
    st.add(make_node("belief", text="老师会记得给猫带猫粮的约定", subject="老师与我的约定", significance=0.8, tags=["猫"]))
    why: list[str] = []
    cands = recommend_candidates(st, "老师带着猫粮来喂猫", why_out=why)
    assert len(why) == len(cands) and why, (why, cands)
    assert all(w for w in why)
    assert any(w.startswith("tags[") for w in why)
    # subject 点名那条（subject 整体出现在 query 里）
    why2: list[str] = []
    recommend_candidates(st, "老师与我的约定", why_out=why2)
    assert "subject 点名" in why2, why2
    print("    why: 与结果等长同序（tags / subject / 2-gram）")


def test_why_semantic_channel(tmp_path):
    """语义通道也说得出来（`语义 0.xx`）—— 至少能分清"是语义还是字面"。"""
    st = _store(tmp_path)
    st.add(make_node("belief", text="拆炸弹",
                     significance=0.9))
    st.add(make_node("belief", text="甜品店",
                     significance=0.8))

    def embed(texts):
        return [[1.0 if "甜品" in t else 0.0, 1.0 if "炸弹" in t else 0.0]
                for t in texts]

    why: list[str] = []
    cands = recommend_candidates(st, "甜品", embed_fn=embed, why_out=why)
    assert why and why[0].startswith("语义 "), why
    assert len(why) == len(cands)
    print("    why: 语义通道 = `语义 0.xx`")


def test_why_out_absent_keeps_old_behaviour(tmp_path):
    """不传 `why_out` ⇒ 行为与签名都不变（现有调用方零改动）。"""
    st = _store(tmp_path)
    st.add(make_node("belief", text="我喜欢照顾杂草",
                     significance=0.9, tags=["杂草"]))
    out = recommend_candidates(st, "杂草")
    assert out and isinstance(out[0][1], float)
    print("    why_out: 不传 = 旧行为（不改返回签名）")
