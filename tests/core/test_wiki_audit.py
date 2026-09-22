"""store.audit() 图不变量测试——图算法正确性确认（邻接表策略闭环定义）。

覆盖: 干净图零违规 / 悬空引用 / 非双向 / count 不变量 / belief 支撑 /
      merge+delete 后仍干净 / revise 全链路后审计干净 / ref 唯一性回归。
"""
from core.brain.wiki_v2 import WikiStoreV2, make_node
from core.brain.wiki_v2.revise import apply_revision_package


def _store(tmp_path) -> WikiStoreV2:
    """真实流程同款 fixture: belief/experience 带支撑 links 创建, 再 add_link 补双向。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(make_node("episode", narration="拆炸弹初遇", event_seq=[1]))
    st.add(make_node("belief", content="老师是第一个不会嫌弃我的人", subject="sensei",
                     epistemic="inferred_belief", significance=0.9,
                     links=["m0001"], event_seq=[1]))
    st.add(make_node("experience", pattern="提到工作繁忙", subject="sensei",
                     significance=0.85, links=["m0001"], event_seq=[1]))
    st.add(make_node("episode", narration="出厂经历", source="experience",
                     significance=0.9))
    st.add_link("m0001", "m0002")
    st.add_link("m0001", "e0001")
    return st


def test_clean_graph_no_violations(tmp_path):
    st = _store(tmp_path)
    assert st.audit() == []


def test_dangling_reference_detected(tmp_path):
    st = _store(tmp_path)
    st.get("m0002").links.append("ghost999")       # 手工制造悬空
    bad = st.audit()
    assert any("悬空引用: m0002 → ghost999" in b for b in bad)


def test_non_bidirectional_detected(tmp_path):
    st = _store(tmp_path)
    st.get("e0001").links.remove("m0001")          # 手工破坏双向共识
    bad = st.audit()
    assert any("link 非双向: m0001 ↔ e0001" in b for b in bad)


def test_count_invariant_detected_and_repaired(tmp_path):
    st = _store(tmp_path)
    st.get("e0001").count = 5                      # 手工破坏引擎计数
    bad = st.audit()
    assert any("count 不变量破坏: e0001" in b for b in bad)
    st.update("e0001", {"significance": 0.8})      # update 后 normalize 修复
    assert st.audit() == []


def test_belief_orphan_after_delete_detected(tmp_path):
    """删除 belief 的唯一支撑 episode → 入边清理后 belief 无支撑——审计检出。"""
    st = _store(tmp_path)
    st.delete("m0001")
    bad = st.audit()
    assert any("belief 无支撑链接: m0002" in b for b in bad)


def test_merge_and_delete_keep_graph_clean(tmp_path):
    """merge 删源 + 入边清理后, 图保持全不变量。"""
    st = _store(tmp_path)
    st.add(make_node("episode", narration="天台夜谈", event_seq=[2]))
    st.add_link("m0004", "m0002")
    st.add_link("m0004", "e0001")
    scope = {n.id for n in st.all()}
    res = apply_revision_package(st, [
        {"action": "merge", "ids": ["m0001", "m0003"],
         "into": {"kind": "episode", "narration": "和老师的两次难忘日常"}},
    ], subgraph_ids=scope)
    assert res.ok, res.errors
    # 源 m0001 的入边（m0002/e0001 → m0001）被 delete 清理 → 图干净
    assert st.audit() == []


def test_full_revision_chain_audit_clean(tmp_path):
    """create(×2)+accrue+contradict+link 全链路后图仍干净（动作可引用包内新 id）。"""
    st = _store(tmp_path)
    scope = {n.id for n in st.all()}
    res = apply_revision_package(st, [
        {"action": "create", "ref": "n1", "entry": {
            "kind": "episode", "narration": "老师带我去甜品店", "event_seq": [3],
            "links": ["m0002"]}},
        {"action": "create", "ref": "n2", "entry": {
            "kind": "belief", "content": "老师会认真听我说话", "subject": "sensei",
            "epistemic": "inferred_belief", "links": ["n1"]}},
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
            "kind": "episode", "narration": "甜品店", "event_seq": [3],
            "links": ["m0002"]}},
        {"action": "create", "entry": {
            "kind": "episode", "narration": "天台夜谈", "event_seq": [4],
            "links": ["m0002"]}},
        {"action": "accrue", "id": "e0001",
         "occurrence": {"episode_ref": "n2", "example": "第二次"}},
    ]
    res = apply_revision_package(st, pkg, subgraph_ids=scope)
    assert res.ok, res.errors
    # n1→第一个 episode(m0004), n2→第二个(m0005); accrue 证据 = n2(天台夜谈, seq 4)
    exp = st.get("e0001")
    assert exp.links == ["m0001", "m0005"] and exp.event_seq == [1, 4]
