"""store.audit() 图不变量测试（**2026-09-21 G3 起走边表**）。

覆盖: 干净图零违规 / 悬空引用 / belief 无支撑。

⏸ 已删的用例（测的是不再存在的世界）:
  · `test_non_bidirectional_detected` —— 点边分离后**无向边不存在**, "双向共识"
    这条不变量在构造上不可能被破坏（一个方向一条边, 查两端都走 `out`/`inc`）。
  · `test_count_invariant_detected_and_repaired` —— `count` 连属性本身都没了。
  · `test_merge_and_delete_keep_graph_clean` / `test_full_revision_chain_audit_clean` /
    `test_refs_unique_by_default` —— 2026-10-12 随 v1 的万能修订包执行器
    `revise.apply_revision_package` 整簇删除（`audit()` 本身的覆盖面由上面三条守着,
    "merge 后边重接"那个形状今天**没有任何活路径会产生**）。
"""
from core.brain import WikiStoreV2, make_node
from core.brain.graph import Edge


def _store(tmp_path) -> WikiStoreV2:
    """真实流程同款 fixture: 一条 episode 支撑一条 belief（audit 最小不变量样本）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(make_node("episode", text="拆炸弹初遇", event_seq=[1]))
    st.add(make_node("belief", text="老师是第一个不会嫌弃我的人", subject="sensei",
                     significance=0.9, event_seq=[1]))
    st.add_edge("supports", "m0001", "m0002")
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
