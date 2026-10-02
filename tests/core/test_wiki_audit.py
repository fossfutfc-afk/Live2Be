"""store.audit() 图不变量测试（**2026-09-21 G3 起走边表**）。

覆盖: 干净图零违规 / 悬空引用 / belief 无支撑 / merge+delete 后仍干净 /
      revise 全链路后审计干净 / ref 唯一性回归。

⏸ 已删的两条（测的是不再存在的世界）:
  · `test_non_bidirectional_detected` —— 点边分离后**无向边不存在**, "双向共识"
    这条不变量在构造上不可能被破坏（一个方向一条边, 查两端都走 `out`/`inc`）。
  · `test_count_invariant_detected_and_repaired` —— `count` 连属性本身都没了。
"""
from core.brain import WikiStoreV2, make_node
from core.brain.graph import Edge
from core.brain.revise import apply_revision_package


def _store(tmp_path) -> WikiStoreV2:
    """真实流程同款 fixture: episode 支撑 belief/experience 各一条 supports 边。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(make_node("episode", text="拆炸弹初遇", event_seq=[1]))
    st.add(make_node("belief", text="老师是第一个不会嫌弃我的人", subject="sensei",
                     significance=0.9, event_seq=[1]))
    st.add(make_node("experience", text="提到工作繁忙", subject="sensei",
                     significance=0.85, event_seq=[1]))
    st.add(make_node("episode", text="出厂经历", significance=0.9))
    st.add_edge("supports", "m0001", "m0002")
    st.add_edge("supports", "m0001", "e0001")
    return st


def test_clean_graph_no_violations(tmp_path):
    st = _store(tmp_path)
    assert st.audit() == []


def test_dangling_reference_detected(tmp_path):
    """悬空边——`add_edge` 会拒, 所以这里直接塞进内存态（模拟旧档/坏档）。"""
    st = _store(tmp_path)
    st._edges.append(Edge(rel="supports", src="m0002", dst="ghost999"))
    bad = st.audit()
    assert any("悬空引用: m0002 -supports-> ghost999" in b for b in bad)


def test_belief_orphan_after_delete_detected(tmp_path):
    """删掉 belief 的唯一支撑 episode → 边被过滤 → 审计检出"无支撑"。

    这条不变量 2026-09-21（G3）从 `nodes.validate` **搬到这里**（支撑住在边表,
    字段级校验看不见它）。
    """
    st = _store(tmp_path)
    st.delete("m0001")
    bad = st.audit()
    assert any("belief 无支撑: m0002" in b for b in bad)


def test_merge_and_delete_keep_graph_clean(tmp_path):
    """merge 删源 + 边重接后, 图保持全不变量。"""
    st = _store(tmp_path)
    st.add(make_node("episode", text="天台夜谈", event_seq=[2]))
    st.add_edge("supports", "m0004", "m0002")
    st.add_edge("supports", "m0004", "e0001")
    scope = {n.id for n in st.all()}
    res = apply_revision_package(st, [
        {"action": "merge", "ids": ["m0001", "m0003"],
         "into": {"kind": "episode", "text": "和老师的两次难忘日常"}},
    ], subgraph_ids=scope)
    assert res.ok, res.errors
    # 源 m0001 的 supports 出边（→ m0002 / e0001）remap 到产物 ⇒ belief 仍有支撑
    assert st.audit() == []


def test_full_revision_chain_audit_clean(tmp_path):
    """create(×2)+accrue+contradict+link 全链路后图仍干净（动作可引用包内新 id）。"""
    st = _store(tmp_path)
    scope = {n.id for n in st.all()}
    res = apply_revision_package(st, [
        {"action": "create", "ref": "n1", "entry": {
            "kind": "episode", "text": "老师带我去甜品店", "event_seq": [3],
            "links": ["m0002"]}},
        {"action": "create", "ref": "n2", "entry": {
            "kind": "belief", "text": "老师会认真听我说话", "subject": "sensei",
            "links": ["n1"]}},
        {"action": "accrue", "id": "e0001",
         "occurrence": {"episode_ref": "n1", "example": "「这家店不错」"}},
        {"action": "contradict", "a": "m0001", "b": "n2"},   # ref → 本包新建的 belief
        {"action": "link", "from": "n2", "to": "m0002"},
    ], subgraph_ids=scope)
    assert res.ok, res.errors
    assert st.audit() == []


def test_refs_unique_by_default(tmp_path):
    """回归: 缺省 ref 用包内序号兜底——多 create 不互相覆盖（曾全部兜底成 n1）。"""
    st = _store(tmp_path)
    scope = {n.id for n in st.all()}
    pkg = [
        {"action": "create", "entry": {
            "kind": "episode", "text": "甜品店", "event_seq": [3],
            "links": ["m0002"]}},
        {"action": "create", "entry": {
            "kind": "episode", "text": "天台夜谈", "event_seq": [4],
            "links": ["m0002"]}},
        {"action": "accrue", "id": "e0001",
         "occurrence": {"episode_ref": "n2", "example": "第二次"}},
    ]
    res = apply_revision_package(st, pkg, subgraph_ids=scope)
    assert res.ok, res.errors
    # n1→第一个 episode(m0004), n2→第二个(m0005); accrue 证据 = n2(天台夜谈, seq 4)
    exp = st.get("e0001")
    assert exp.event_seq == [1, 4]
    assert set(st.graph().supporters("e0001")) == {"m0001", "m0005"}
