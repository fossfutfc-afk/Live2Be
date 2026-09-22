"""WikiStore v2 存储层测试（AGENT_BRAIN.md §2 / M1b）。"""
import pytest

from core.brain.wiki_v2 import WikiStoreV2, make_node
from core.brain.wiki_v2.nodes import format_id


def _store(tmp_path, char="igusa_haruka") -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id=char)


def test_add_save_reload_roundtrip(tmp_path):
    st = _store(tmp_path)
    n1 = make_node("episode", narration="天台夜谈", significance=0.8,
                   event_seq=[42, 58], observer="igusa_haruka")
    n2 = make_node("belief", content="我被需要", epistemic="inferred_belief",
                   links=["m0001"])
    st.add(n1)
    st.add(n2)
    assert st.save() is None
    # 重载
    st2 = _store(tmp_path)
    assert len(st2) == 2
    assert st2.get("m0001").narration == "天台夜谈"
    assert st2.get("m0002").kind == "belief"
    # id 自动分配按前缀
    assert st2.get("m0001").id == "m0001" and st2.get("m0002").id == "m0002"


def test_id_allocation_prefixes(tmp_path):
    st = _store(tmp_path)
    assert st.add(make_node("episode", narration="拆炸弹", source="experience")) == "m0001"
    assert st.add(make_node("episode", narration="x")) == "m0002"
    assert st.add(make_node("experience", pattern="摸鱼", subject="player")) == "e0001"
    assert st.add(make_node("belief", content="y", epistemic="inferred_belief",
                            links=["m0001"])) == "m0003"
    assert st.next_id("m") == "m0004"
    assert st.next_id("e") == "e0002"
    assert format_id("m", 3) == "m0003"


def test_add_rejects_invalid_node(tmp_path):
    st = _store(tmp_path)
    with pytest.raises(ValueError):
        st.add(make_node("belief", content="无支撑升华"))      # links 空
    with pytest.raises(ValueError):
        st.add(make_node("episode"))                            # 缺 narration
    with pytest.raises(ValueError):
        st.add(make_node("episode", narration="x",
                         epistemic="inferred_belief"))          # 认知不伪装成经历


def test_duplicate_id_rejected(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", narration="a"))
    dup = make_node("episode", narration="b")
    dup.id = "m0001"
    with pytest.raises(ValueError):
        st.add(dup)


def test_dedup_helper_removed(tmp_path):
    """（2026-09-21）`find_by_event_seq` 是查重**辅助**, 全仓零产品消费者 → 已删。

    现役去重 = `digested_seq` 水位（增量幂等）; 这里守门: 辅助不许无声回来
    （要恢复就得连着它的消费者一起）。
    """
    st = _store(tmp_path)
    st.add(make_node("episode", narration="第一次", event_seq=[10, 11]))
    assert not hasattr(st, "find_by_event_seq")
    assert [n.narration for n in st.all()] == ["第一次"]


def test_update_patch_and_unknown_field(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", narration="a", significance=0.5))
    node = st.update("m0001", {"significance": 0.9, "links": ["m0002"]})
    assert node.significance == 0.9 and node.links == ["m0002"]
    with pytest.raises(ValueError):
        st.update("m0001", {"imaginary_field": 1})            # 未知字段拒绝
    with pytest.raises(ValueError):
        st.update("m0001", {"narration": ""})                  # 更新后无效


def test_seed_immutable_notes_only(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", narration="拆炸弹", source="experience"))
    # 出厂基座（episode source=experience）: 只允许 notes 追加
    node = st.update("m0001", {"notes": "世界线 1 中已被验证"})
    assert node.notes == ["世界线 1 中已被验证"]
    node = st.update("m0001", {"notes": "第二次注记"})
    assert node.notes == ["世界线 1 中已被验证", "第二次注记"]
    # 其他字段一律拒绝
    with pytest.raises(ValueError):
        st.update("m0001", {"significance": 0.99})


def test_edge_primitives(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", narration="e1", event_seq=[1]))
    st.add(make_node("episode", narration="e2", event_seq=[2]))
    st.add(make_node("belief", content="b", epistemic="inferred_belief",
                     links=["m0001"]))
    st.add_link("m0001", "m0002")
    st.add_link("m0001", "m0002")                      # 幂等
    assert st.get("m0001").links == ["m0002"]
    assert st.get("m0002").links == ["m0001"]
    st.add_contradiction("m0001", "m0003")
    assert st.get("m0001").contradictions == ["m0003"]
    st.remove_link("m0001", "m0002")
    st.remove_contradiction("m0001", "m0003")
    assert st.get("m0001").links == [] and st.get("m0001").contradictions == []


def test_delete(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", narration="a"))
    assert st.delete("m0001") is True
    assert st.delete("m0001") is False
    assert "m0001" not in st


def test_delete_cleans_inbound_references(tmp_path):
    """邻接表闭环: 删节点 → 他人 links/contradictions 里的悬空 id 一并清除。"""
    st = _store(tmp_path)
    st.add(make_node("episode", narration="hub", event_seq=[1]))
    st.add(make_node("episode", narration="a", event_seq=[2], links=["m0001"]))
    st.add(make_node("belief", content="b", epistemic="inferred_belief",
                     links=["m0001", "m0002"]))
    st.add_contradiction("m0001", "m0003")
    assert st.get("m0002").links == ["m0001"]
    assert st.get("m0003").links == ["m0001", "m0002"]
    assert st.get("m0001").contradictions == ["m0003"]
    st.delete("m0001")
    assert st.get("m0002").links == []                     # 入边清理
    assert st.get("m0003").links == ["m0002"]              # 只清 m0001
    assert st.get("m0003").contradictions == []            # 矛盾边也清理


def test_add_link_refreshes_experience_count(tmp_path):
    """回归: 后建节点链入 experience（add_link 路径）→ count 立即刷新（不变量）。"""
    st = _store(tmp_path)
    st.add(make_node("experience", pattern="提到工作繁忙", subject="sensei",
                     significance=0.7, event_seq=[1]))
    assert st.get("e0001").count == 0
    st.add(make_node("episode", narration="老师又说忙", event_seq=[2]))
    st.add_link("m0001", "e0001")                          # episode 链入 experience
    exp = st.get("e0001")
    assert exp.links == ["m0001"] and exp.count == 1
    st.remove_link("m0001", "e0001")
    assert st.get("e0001").count == 0
    assert st.audit() == []


def test_snapshot_restore(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", narration="a", event_seq=[1]))
    st.add(make_node("belief", content="b", epistemic="inferred_belief", links=["m0001"]))
    snap = tmp_path / "snap_001.jsonl"
    st.snapshot_to(snap)
    # 继续演化后回滚
    st.add(make_node("episode", narration="c", event_seq=[2]))
    assert len(st) == 3
    st.restore_from(snap)
    assert len(st) == 2
    assert st.get("m0001") is not None and st.get("m0003") is None


def test_bad_lines_skipped_on_load(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", narration="ok"))
    st.save()
    # 混入坏行
    with open(st.path, "a", encoding="utf-8") as fh:
        fh.write("{broken json\n")
    st2 = _store(tmp_path)
    assert len(st2) == 1 and st2.get("m0001").narration == "ok"


def test_all_insertion_order(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", narration="a"))
    st.add(make_node("episode", narration="b"))
    st.add(make_node("experience", pattern="p", subject="player"))
    assert [n.narration or n.pattern for n in st.all()] == ["a", "b", "p"]
    # 2026-09-21: `by_kind()` 零产品消费者 → 已删; 按 kind 过滤直接用 all()
    assert [n.kind for n in st.all() if n.kind == "episode"] == ["episode", "episode"]


def test_missing_file_empty(tmp_path):
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="nobody")
    assert len(st) == 0
    st.save()                                     # 空库也能原子落盘
    assert st.path.is_file()
