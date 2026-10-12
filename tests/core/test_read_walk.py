"""`read/walk.py` —— 记忆图上的**联想扩散（BFS）** 接口（⛔ 未接线, 2026-10-12 用户:
*"near 就是 BFS 吧，可以留接口……先写一个接口，不调用但需要有"*）。

接口没人调用 ⇒ **守门全压在这里**（这就是"未接线但存在"的代价与保险）:

  ① ⛔ **默认只走窄门**（`about` 不在内 —— 它一跳就接近整条河）
  ② ⛔ **默认一跳**; `hops=2` 是实验位（真机那个 akin 簇两跳就串到别的簇）
  ③ ⭐ **同类兄弟算"语义一跳"**（我 → 我的类 → 兄弟）
  ④ ⭐ **分 = 父分 × 边权 × decay^(跳-1)**; 同一跳多父 ⇒ 取最强
  ⑤ ⭐ **最小跳优先**: 更远的路以更高分够到**不覆盖**（否则"第几跳"与排序口径打架）
  ⑥ **种子不吃分**（它本来就是内容命中）· `skip` 进来的不出现
  ⑦ ⛔ **`kinds` 只过滤结果**: 中途过滤会把"经历 → 类 → 兄弟经历"整条路**静默**掐断
  ⑧ **排序** = 跳数升序 → 分降序 → 新→旧
  ⑨ **宁缺勿错**: 空种子 / `hops<1` / 图坏了 ⇒ `[]`, 不抛

变异验红: `.testtmp/verify_walk_red.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest  # noqa: E402

from core.brain import WikiStoreV2, make_node  # noqa: E402
from core.brain.graph import REL_AKIN, REL_CONTRADICTS, REL_EVOLVED_FROM, REL_MEMBER_OF  # noqa: E402
from core.brain.read.walk import DECAY, DEEP, NARROW, bfs, chain, neighbors  # noqa: E402

CHAR = "igusa_haruka"

#: 种子的"内容分"（调用方给什么就是什么; 这里固定一个便于算账）
S = 0.8


def _store(tmp_path) -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)


def _ep(store, title: str, ts: str, *, kind: str = "episode"):
    return store.add(make_node(kind, text=f"{title} 的正文", title=title, ts=ts,
                               significance=0.5))


def _seed_graph(tmp_path) -> tuple[WikiStoreV2, dict[str, str]]:
    """一张小图:

        m1（种子）
          ├─ akin ── m2                     一跳（边权 1.00）
          ├─ member_of ── g1 ── member_of ── m3   一跳（同类兄弟, 边权 0.80）
          ├─ akin ── m4 ── akin ── m5       两跳（m5 只有 hops=2 才到）
          └─ about ── who ── about ── m7    两跳、**且中间那跳不是 episode**
        m6 挂 `about`（⛔ 不在窄门里 ⇒ 谁也不该够到它）
    """
    st = _store(tmp_path)
    ids = {t: _ep(st, t, ts) for t, ts in (("m1", "2026-10-01T10:00:00"),
                                           ("m2", "2026-10-02T10:00:00"),
                                           ("m3", "2026-10-03T10:00:00"),
                                           ("m4", "2026-10-04T10:00:00"),
                                           ("m5", "2026-10-05T10:00:00"),
                                           ("m6", "2026-10-06T10:00:00"),
                                           ("m7", "2026-10-07T10:00:00"))}
    g1 = st.add(make_node("experience", text="一类事", title="那一类", ts="2026-09-01T10:00:00"))
    st.add_edge(REL_AKIN, ids["m1"], ids["m2"])
    st.add_edge(REL_MEMBER_OF, ids["m1"], g1)
    st.add_edge(REL_MEMBER_OF, ids["m3"], g1)
    st.add_edge(REL_AKIN, ids["m1"], ids["m4"])
    st.add_edge(REL_AKIN, ids["m4"], ids["m5"])
    who = st.add(make_node("entity", name="某个人", text=""))
    st.add_edge("about", ids["m6"], who)                     # ⛔ 归属: 不在窄门里
    st.add_edge("about", ids["m1"], who)
    st.add_edge("about", ids["m7"], who)                     # 两跳、经 `who` 才到得了
    st.save()
    ids["g1"] = g1
    ids["who"] = who
    return st, ids


def test_default_is_one_hop_and_narrow_gates_only(tmp_path):
    """① + ② + ⑥ **默认口径**: 一跳、窄门、种子自己不在结果里、`about` 够不到。"""
    st, ids = _seed_graph(tmp_path)
    got = bfs(st, {ids["m1"]: S})
    assert NARROW == (REL_AKIN, REL_MEMBER_OF)
    # 一跳 = akin 的两条（m2 / m4）+ 同类兄弟 m3
    assert sorted(h.node_id for h in got) == sorted([ids["m2"], ids["m3"], ids["m4"]]), got
    assert ids["m1"] not in [h.node_id for h in got], "种子不该吃自己的结构分"
    assert ids["m5"] not in [h.node_id for h in got], "两跳的默认到不了"
    assert ids["m6"] not in [h.node_id for h in got], "about 不在窄门里"
    assert all(h.hop == 1 for h in got)
    # ⭐ **全边与窄门的差别要看得见**: 两跳时 `m1 →(about) who →(about) m7` 只有全边到得了
    assert ids["m7"] not in [h.node_id for h in bfs(st, {ids["m1"]: S}, hops=2)]
    wide = [h.node_id for h in bfs(st, {ids["m1"]: S}, hops=2, rels=None)]
    assert ids["m7"] in wide and ids["m5"] in wide, wide    # ⛔ 只给对照台
    print("    walk: 默认一跳 + 窄门（about 够不到）")


def test_class_sibling_counts_as_one_semantic_hop(tmp_path):
    """③ 同类兄弟算一跳 —— 而且**分按 0.80 边权**（与 `like._STRUCT_EDGES` 同一份）。"""
    st, ids = _seed_graph(tmp_path)
    got = {h.node_id: h for h in bfs(st, {ids["m1"]: S})}
    sib = got[ids["m3"]]
    assert sib.hop == 1 and sib.why == "同类兄弟", sib
    assert abs(sib.score - S * 0.80) < 1e-9, sib
    assert abs(got[ids["m2"]].score - S * 1.00) < 1e-9      # akin = 1.00
    print(f"    walk: 同类兄弟 = 一跳（{sib.score:.2f}）")


def test_two_hops_decay_and_the_nearest_hop_wins(tmp_path):
    """④ + ⑤ 两跳要乘 `decay`; 而**更远的路以更高分够到不覆盖**（最小跳优先）。"""
    st, ids = _seed_graph(tmp_path)
    got2 = {h.node_id: h for h in bfs(st, {ids["m1"]: S}, hops=2)}
    m5 = got2[ids["m5"]]
    assert m5.hop == 2, m5
    assert abs(m5.score - S * 1.00 * DECAY) < 1e-9, m5       # 父分 × akin × decay
    # m4 两跳内两条路都够得到（一跳 akin / 两跳绕 m2? 这里用"远路分更高"的构造验最小跳）
    assert got2[ids["m4"]].hop == 1, got2[ids["m4"]]
    # 两跳时**种子仍是种子**: 一跳那批的跳数不许被改写成 2
    assert got2[ids["m2"]].hop == 1 and got2[ids["m3"]].hop == 1
    print(f"    walk: 两跳 = ×{DECAY}（m5={m5.score:.2f}, hop=2）· 最小跳优先")


def test_order_is_near_then_strong_then_new(tmp_path):
    """⑧ 排序 = **跳数升序 → 分降序 → 新→旧**（同跳同分才比新旧）。"""
    st, ids = _seed_graph(tmp_path)
    got = bfs(st, {ids["m1"]: S}, hops=2)
    assert [h.hop for h in got] == sorted(h.hop for h in got), got
    one = [h for h in got if h.hop == 1]
    # akin(1.00) 那两条在前, 同分按**新→旧**; 兄弟(0.80) 在后
    assert [h.node_id for h in one] == [ids["m4"], ids["m2"], ids["m3"]], one
    assert got[-1].node_id == ids["m5"], got[-1]
    # 同跳同分 ⇒ 新的在前
    st2 = _store(tmp_path / "second")
    a = _ep(st2, "a", "2026-10-01T10:00:00")
    b = _ep(st2, "b", "2026-10-09T10:00:00")
    root = _ep(st2, "root", "2026-10-10T10:00:00")
    st2.add_edge(REL_AKIN, root, a)
    st2.add_edge(REL_AKIN, root, b)
    st2.save()
    assert [h.node_id for h in bfs(st2, {root: S})] == [b, a], "同分要新的在前"

    # ⭐ **"近"必须压过"强"**: 弱种子的**一跳**要排在强种子的**两跳**前面
    #   （弱种子的分低, 但它是近的那一环 —— 排错了这一条就红）
    st3 = _store(tmp_path / "third")
    strong = _ep(st3, "strong", "2026-10-01T10:00:00")
    mid = _ep(st3, "mid", "2026-10-02T10:00:00")
    far = _ep(st3, "far", "2026-10-03T10:00:00")
    weak = _ep(st3, "weak", "2026-10-04T10:00:00")
    near_weak = _ep(st3, "near_weak", "2026-10-05T10:00:00")
    st3.add_edge(REL_AKIN, strong, mid)
    st3.add_edge(REL_AKIN, mid, far)                        # far = 强种子的两跳
    st3.add_edge(REL_AKIN, weak, near_weak)                 # 弱种子的一跳
    st3.save()
    got3 = bfs(st3, {strong: 0.9, weak: 0.3}, hops=2)
    by_id = {h.node_id: h for h in got3}
    assert by_id[far].hop == 2 and by_id[near_weak].hop == 1
    assert by_id[far].score > by_id[near_weak].score, "夹具前提: 远的那条确实更强"
    assert [h.node_id for h in got3][:2] == [mid, near_weak], got3
    print("    walk: 近 → 强 → 新（弱种子的一跳压过强种子的两跳）")


def test_echo_style_relations_drop_the_siblings(tmp_path):
    """⭐ `rels=(akin,)` ⇒ **兄弟那一步不做** —— 这正是 `echo` 与 `near` 的唯一差别。"""
    st, ids = _seed_graph(tmp_path)
    got = [h.node_id for h in bfs(st, {ids["m1"]: S}, rels=(REL_AKIN,))]
    assert got == [ids["m4"], ids["m2"]], got                 # 同分 ⇒ 新的在前
    assert ids["m3"] not in got, "只要 akin 时不该走同类兄弟"
    print("    walk: `rels=(akin,)` = echo（不走兄弟）")


def test_kinds_filter_is_on_results_not_during_the_walk(tmp_path):
    """⑦ ⛔ **`kinds` 归结果**: 类节点要"经过", 但不许出现在结果里。

    ⚠️ 更正一句（2026-10-12, 变异验红时发现）: "同类兄弟"是**一跳内的原语**
    （`neighbors` 直接取兄弟）⇒ 早过滤**掐不断**它。早过滤真正会掐断的是**两跳里经过
    非 episode 节点的路**（这里那条 `m1 →(about) who →(about) m7`）。所以这条守卫
    落的判据是"**结果面干净**", 不是"兄弟还在".
    """
    st, ids = _seed_graph(tmp_path)
    got = [h.node_id for h in bfs(st, {ids["m1"]: S}, kinds=("episode",))]
    assert ids["m3"] in got, "同类兄弟照旧"
    assert ids["g1"] not in got, "类自己不该出现在结果里（结果面只要 episode）"
    # 结果面放宽 ⇒ 类可以进来
    assert ids["g1"] in [h.node_id for h in bfs(st, {ids["m1"]: S},
                                                kinds=("episode", "experience"))]
    # 两跳经过 `who`（entity）: 结果面要 episode ⇒ m7 在; 结果面只要 entity ⇒ 只剩 who
    wide2 = [h.node_id for h in bfs(st, {ids["m1"]: S}, hops=2, rels=None)]
    assert ids["m7"] in wide2 and ids["who"] not in wide2
    only_ent = [h.node_id for h in bfs(st, {ids["m1"]: S}, hops=2, rels=None,
                                       kinds=("entity",))]
    assert only_ent == [ids["who"]], only_ent
    print("    walk: `kinds` 只过滤结果（类要经过, 但不摆出来）")


def test_skip_and_degrades_never_raise(tmp_path):
    """⑥ + ⑨ `skip` 生效; 空种子 / `hops<1` / 图坏了 ⇒ `[]`（绝不抛）。"""
    st, ids = _seed_graph(tmp_path)
    got = [h.node_id for h in bfs(st, {ids["m1"]: S}, skip=(ids["m2"],))]
    assert ids["m2"] not in got and ids["m3"] in got, got
    assert bfs(st, {}) == [] and bfs(st, {ids["m1"]: S}, hops=0) == []

    class Broken:
        def get(self, _nid):                                 # pragma: no cover - 只验不抛
            return None

        def all(self):
            return []

    assert bfs(Broken(), {"m1": 1.0}) == []                  # 图取不到 ⇒ 空, 不抛
    print("    walk: skip 生效 · 空种子/坏图 ⇒ 空（不抛）")


def test_width_caps_the_flood_from_a_big_class(tmp_path):
    """⭐ **广度闸**: 一个 30 条的类不许把整段吃光 —— 每一跳最多收 `width` 条。

    没有它会发生什么（这是"超级大群"的真实形状）:
      · "同类兄弟"那一步一次带回 29 条（同分同跳）⇒ 她看到的由**渲染预算**先到先得,
        依据只剩"新→旧";
      · 两跳时**每个兄弟各自再展开** ⇒ 扇出平方放大; 台账那一行也会长到读不了。
    ⚠️ 它会**漏**（与 `find` 的"不漏即正确"相反）⇒ 缺省 `None` 不裁, 由调用方给值。
    """
    st = _store(tmp_path)
    seed = _ep(st, "seed", "2026-10-01T10:00:00")
    g1 = st.add(make_node("experience", text="一大类", title="很大的一类",
                          ts="2026-09-01T10:00:00"))
    st.add_edge(REL_MEMBER_OF, seed, g1)
    sibs = [_ep(st, f"s{i:02d}", f"2026-09-{i + 1:02d}T10:00:00") for i in range(29)]
    for s in sibs:
        st.add_edge(REL_MEMBER_OF, s, g1)
    st.save()

    assert len(bfs(st, {seed: S})) == 29, "缺省不裁（与没有这个参数逐字一致）"
    got = bfs(st, {seed: S}, width=3)
    assert len(got) == 3, got
    assert [h.node_id for h in got] == sibs[-1:-4:-1], "同分同跳时要留**最新**的三条"
    assert bfs(st, {seed: S}, width=0) == []
    print("    walk: `width` 掐住大群（29 → 3, 同分取最新）")


# ---------------------------------------------------------------------------
# ⭐ 深挖（DFS）: `chain` —— 找同类之外的另一种记忆机制
# ---------------------------------------------------------------------------

def _deep_graph(tmp_path):
    """看法进化链 + 一串矛盾 + **一个环**:

        b1 ──evolved_from──> b2 ──evolved_from──> b3      （新 → 旧）
        b1 ──contradicts─── b4 ──contradicts─── b5
        b4 ──contradicts─── b1                            ⇒ **环**（b1—b4—b5—b1… 不许转不出来）
        m1 ──about──> who                                 （⛔ 深挖不许走 about）
    """
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    b = {t: st.add(make_node("belief", text=f"{t} 的正文", ts=f"2026-10-0{i}T10:00:00"))
         for i, t in enumerate(("b1", "b2", "b3", "b4", "b5"), start=1)}
    st.add_edge(REL_EVOLVED_FROM, b["b1"], b["b2"])          # 新 → 旧
    st.add_edge(REL_EVOLVED_FROM, b["b2"], b["b3"])
    st.add_edge(REL_CONTRADICTS, b["b1"], b["b4"])           # 对称
    st.add_edge(REL_CONTRADICTS, b["b4"], b["b5"])
    who = st.add(make_node("entity", name="某个人", text=""))
    m1 = _ep(st, "m1", "2026-09-01T10:00:00")
    st.add_edge("about", m1, who)
    st.save()
    b["who"] = who
    b["m1"] = m1
    return st, b


def test_chain_walks_the_evolution_line_and_reports_the_direction(tmp_path):
    """⭐ 深挖一条**看法进化链**: 一路往回挖, 每一步都带**来路**与**方向**。"""
    st, b = _deep_graph(tmp_path)
    got = chain(st, b["b1"], rels=(REL_EVOLVED_FROM,))
    assert [(x.node_id, x.depth, x.via, x.rel, x.forward) for x in got] == [
        (b["b1"], 0, "", "", True),                          # ⭐ 链头自己在（一条链含第一节）
        (b["b2"], 1, b["b1"], REL_EVOLVED_FROM, True),
        (b["b3"], 2, b["b2"], REL_EVOLVED_FROM, True),
    ], got
    # 从最旧的那头出发 ⇒ 挖到的是"谁盖过了它" —— 方向如实报成 False, ⛔ 不替她决定
    back = chain(st, b["b3"], rels=(REL_EVOLVED_FROM,))
    assert [x.node_id for x in back] == [b["b3"], b["b2"], b["b1"]], back
    assert all(x.forward is False for x in back[1:]), back
    print("    walk: 深挖进化链（来路 + 方向都带出去）")


def test_chain_survives_a_cycle_and_visits_each_node_once(tmp_path):
    """⛔⭐ **已访问集是安全件**: `contradicts` 对称 ⇒ 环在真图里完全可能, 少了它就是**死循环**。"""
    st, b = _deep_graph(tmp_path)
    got = chain(st, b["b1"], rels=(REL_CONTRADICTS,))
    ids = [x.node_id for x in got]
    assert ids[0] == b["b1"] and sorted(ids) == sorted([b["b1"], b["b4"], b["b5"]]), ids
    assert len(ids) == len(set(ids)), "一个节点只许进一次"
    print(f"    walk: 环上不转圈（{len(ids)} 个节点各一次）")


def test_chain_order_is_deterministic_and_rel_driven(tmp_path):
    """链的走法必须**确定**: 先按 `rels` 给的顺序, 同 rel 内新→旧。"""
    st, b = _deep_graph(tmp_path)
    # 缺省 DEEP 的顺序 = (evolved_from, contradicts) ⇒ 先挖完进化那条, 再回来挖矛盾那条
    got = chain(st, b["b1"])
    assert [x.node_id for x in got] == [b["b1"], b["b2"], b["b3"], b["b4"], b["b5"]], got
    assert [x.rel for x in got][1:] == [REL_EVOLVED_FROM, REL_EVOLVED_FROM,
                                        REL_CONTRADICTS, REL_CONTRADICTS]
    # 换个顺序 ⇒ 走法跟着换（说明它真是"由 rels 驱动"的, 不是碰巧）
    swapped = chain(st, b["b1"], rels=(REL_CONTRADICTS, REL_EVOLVED_FROM))
    assert [x.node_id for x in swapped][:3] == [b["b1"], b["b4"], b["b5"]], swapped
    print("    walk: 链的走法由 `rels` 决定（确定、可复现）")


def test_chain_bounds_skip_and_refusals(tmp_path):
    """深度上限 / `skip` / ⛔ `rels=None` 当场炸 / 空 start / 坏图 ⇒ 各自的行为。"""
    st, b = _deep_graph(tmp_path)
    assert [x.node_id for x in chain(st, b["b1"], rels=(REL_EVOLVED_FROM,),
                                     max_depth=1)] == [b["b1"], b["b2"]]
    got = chain(st, b["b1"], rels=(REL_EVOLVED_FROM,), skip=(b["b1"], b["b3"],))
    assert [x.node_id for x in got] == [b["b2"]], "skip 只挡结果; 链头不摆但**照样从它出发**"
    with pytest.raises(ValueError):
        chain(st, b["b1"], rels=None)                        # ⛔ 深挖没有"走全部边"这回事
    assert chain(st, "", rels=(REL_EVOLVED_FROM,)) == []
    assert chain(st, b["b1"], rels=()) == []
    assert chain(st, b["b1"], rels=(REL_EVOLVED_FROM,), max_depth=-1) == []

    class Broken:
        def get(self, _nid):                                 # pragma: no cover - 只验不抛
            return None

        def all(self):
            return []

    assert chain(Broken(), "b1") == []
    # ⛔ 深挖不许走 about（那是"找同类"那一侧的对照台用法; 掺进来就退化成一坨）
    assert all(x.node_id != b["who"] for x in chain(st, b["m1"])), "about 不该被深挖走到"
    print("    walk: 深度上限 / skip / `rels=None` 当场炸 / 坏图不抛")


def test_neighbors_all_edges_mode_is_for_the_bench_only(tmp_path):
    """⚠️ `rels=None` = **全部边**（对照台用）: `about` 这时才进得来。"""
    st, ids = _seed_graph(tmp_path)
    plain = {n for n, _w, _y in neighbors(st.graph(), ids["m1"])}
    assert ids["m6"] not in plain                            # 窄门下够不到 m6
    everything = {n for n, _w, _y in neighbors(st.graph(), ids["m1"], rels=None)}
    assert ids["m2"] in everything and ids["g1"] in everything
    print("    walk: `rels=None` = 全边（只给对照台）")
