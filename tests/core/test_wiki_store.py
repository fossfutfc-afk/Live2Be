"""WikiStore v2 存储层测试（AGENT_BRAIN.md §2 / M1b）。"""
import pytest

from core.brain.wiki_v2 import WikiStoreV2, make_node
from core.brain.wiki_v2.nodes import format_id


def _store(tmp_path, char="igusa_haruka") -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id=char)


def test_add_save_reload_roundtrip(tmp_path):
    st = _store(tmp_path)
    n1 = make_node("episode", text="天台夜谈", significance=0.8,
                   event_seq=[42, 58], observer="igusa_haruka")
    n2 = make_node("belief", text="我被需要", epistemic="inferred_belief",
                   links=["m0001"])
    st.add(n1)
    st.add(n2)
    assert st.save() is None
    # 重载
    st2 = _store(tmp_path)
    assert len(st2) == 2
    assert st2.get("m0001").text == "天台夜谈"
    assert st2.get("m0002").kind == "belief"
    # id 自动分配按前缀
    assert st2.get("m0001").id == "m0001" and st2.get("m0002").id == "m0002"


def test_id_allocation_prefixes(tmp_path):
    st = _store(tmp_path)
    assert st.add(make_node("episode", text="拆炸弹")) == "m0001"
    assert st.add(make_node("episode", text="x")) == "m0002"
    assert st.add(make_node("experience", text="摸鱼", subject="player")) == "e0001"
    assert st.add(make_node("belief", text="y", epistemic="inferred_belief",
                            links=["m0001"])) == "m0003"
    assert st.next_id("m") == "m0004"
    assert st.next_id("e") == "e0002"
    assert format_id("m", 3) == "m0003"


def test_promise_prefix_and_persistence(tmp_path):
    """promise 节点（§6 固化产物）: 自己的前缀 `p`, 且**结局落库可读回**。"""
    st = _store(tmp_path)
    nid = st.add(make_node("promise", text="周六模型店", outcome="kept",
                           event_seq=[42], ts="2026-09-20T10:00:00+09:00"))
    assert nid == "p0001" and st.next_id("p") == "p0002"
    st.save()

    reloaded = _store(tmp_path).get("p0001")
    assert (reloaded.kind, reloaded.text, reloaded.outcome) \
        == ("promise", "周六模型店", "kept")
    assert reloaded.event_seq == [42]


def test_add_rejects_invalid_node(tmp_path):
    st = _store(tmp_path)
    with pytest.raises(ValueError):
        st.add(make_node("belief", text="无支撑升华"))      # links 空
    with pytest.raises(ValueError):
        st.add(make_node("episode"))                            # 缺 text
    with pytest.raises(ValueError):
        st.add(make_node("episode", text="x",
                         epistemic="inferred_belief"))          # 认知不伪装成经历


def test_duplicate_id_rejected(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", text="a"))
    dup = make_node("episode", text="b")
    dup.id = "m0001"
    with pytest.raises(ValueError):
        st.add(dup)


def test_dedup_helper_removed(tmp_path):
    """（2026-09-21）`find_by_event_seq` 是查重**辅助**, 全仓零产品消费者 → 已删。

    现役去重 = `digested_seq` 水位（增量幂等）; 这里守门: 辅助不许无声回来
    （要恢复就得连着它的消费者一起）。
    """
    st = _store(tmp_path)
    st.add(make_node("episode", text="第一次", event_seq=[10, 11]))
    assert not hasattr(st, "find_by_event_seq")
    assert [n.text for n in st.all()] == ["第一次"]


def test_update_patch_and_unknown_field(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", text="a", significance=0.5))
    node = st.update("m0001", {"significance": 0.9, "tags": ["杂草"]})
    assert node.significance == 0.9 and node.tags == ["杂草"]
    with pytest.raises(ValueError):
        st.update("m0001", {"imaginary_field": 1})            # 未知字段拒绝
    with pytest.raises(ValueError):
        st.update("m0001", {"text": ""})                  # 更新后无效
    # `links` 现在是**未知字段**（G4 删了它; 边一律走 `add_edge`）—— 顺手钉住,
    # 免得有人"顺手"把它加回节点上
    with pytest.raises(ValueError):
        st.update("m0001", {"links": ["m0002"]})


# ⏸ `test_seed_immutable_notes_only` —— 2026-09-21 删：它钉的"出厂基座只允许 notes
# 追加"随 `source`/`is_seed()`/`notes` 整族退役（那个生产者已归档, 真机 0 个 seed 节点）。
# `update` 现在没有不可变区; 未知字段与"更新后无效"两条护栏仍由上面的用例守着。


def test_edge_primitives(tmp_path):
    """边原语（G3 起边住在 `edges.jsonl`; 节点上的 `links` 只作旧档读入）。"""
    st = _store(tmp_path)
    st.add(make_node("episode", text="e1", event_seq=[1]))
    st.add(make_node("episode", text="e2", event_seq=[2]))
    st.add(make_node("belief", text="b", epistemic="inferred_belief"))
    st.add_link("m0001", "m0002")            # 无向 link → rel 由两端 kind 推断
    st.add_link("m0001", "m0002")            # 幂等
    # episode ↔ episode 判不出类型 → unknown（**不猜**, 见 graph.classify_pair）
    assert [(e.rel, e.src, e.dst) for e in st.edges()] == [("unknown", "m0001", "m0002")]
    assert st.edges()[0].ts                   # 不给 ts → 取当下（边总有时刻）
    assert st.neighbors("m0001") == ["m0002"]         # 无向: 两边都算邻居
    assert st.neighbors("m0002") == ["m0001"]
    st.add_link("m0002", "m0003")            # episode → belief = supports
    assert ("supports", "m0002", "m0003") in [(e.rel, e.src, e.dst) for e in st.edges()]
    st.add_contradiction("m0001", "m0003")
    assert ("contradicts", "m0001", "m0003") in [(e.rel, e.src, e.dst) for e in st.edges()]
    st.remove_link("m0001", "m0002")
    st.remove_link("m0002", "m0003")
    st.remove_contradiction("m0001", "m0003")
    assert st.edges() == []


def test_add_edge_rejects_dangling_and_self(tmp_path):
    """写路径关门: 悬空 / 自环一律拒（"悬空引用在构造上不可能存在", §2.1）。"""
    st = _store(tmp_path)
    st.add(make_node("episode", text="a"))
    with pytest.raises(ValueError):
        st.add_edge("supports", "m0001", "m9999")     # 对端不存在
    with pytest.raises(ValueError):
        st.add_edge("supports", "m0001", "m0001")     # 自环
    assert st.edges() == []


def test_edges_persist_and_reload(tmp_path):
    """边表落盘 ⇄ 读回（点边两个文件; 再载入不再走推断）。"""
    st = _store(tmp_path)
    st.add(make_node("episode", text="a", event_seq=[1]))
    st.add(make_node("belief", text="b", epistemic="inferred_belief"))
    st.add_edge("supports", "m0001", "m0002", ts="2026-09-21T10:00:00")
    st.save()
    assert st.edges_path.is_file() and st.edges_path.name == "edges.jsonl"
    st2 = _store(tmp_path)
    assert [(e.rel, e.src, e.dst) for e in st2.edges()] == [("supports", "m0001", "m0002")]
    assert st2.graph().supporters("m0002") == ["m0001"]
    assert st2.audit() == []


def test_delete(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", text="a"))
    assert st.delete("m0001") is True
    assert st.delete("m0001") is False
    assert "m0001" not in st


def test_delete_filters_edges(tmp_path):
    """删节点 = 点表删 + **边表过滤一遍** ⇒ 悬空引用在构造上不可能存在。"""
    st = _store(tmp_path)
    st.add(make_node("episode", text="hub", event_seq=[1]))
    st.add(make_node("episode", text="a", event_seq=[2]))
    st.add(make_node("belief", text="b", epistemic="inferred_belief"))
    st.add_link("m0002", "m0001")
    st.add_link("m0003", "m0001")
    st.add_contradiction("m0001", "m0003")
    assert len(st.edges()) == 3
    st.delete("m0001")
    assert st.edges() == []                    # 三条边全部触及 hub → 全清
    # 支撑随边一起没了 → 全局兜底（audit）看得见, 不再是静默
    assert st.audit() == ["belief 无支撑: m0003"]


def test_experience_count_comes_from_edges(tmp_path):
    """次数（原 `count`）的**新家** = `supports` 入边数（`render._count_of`）。"""
    from core.brain.wiki_v2.render import _count_of
    st = _store(tmp_path)
    st.add(make_node("experience", text="提到工作繁忙", subject="sensei", event_seq=[1]))
    st.add(make_node("episode", text="老师又说忙", event_seq=[2]))
    g = st.graph()
    assert _count_of(st.get("e0001"), g) == 0
    st.add_edge("supports", "m0001", "e0001")
    assert _count_of(st.get("e0001"), st.graph()) == 1
    st.remove_edge("supports", "m0001", "e0001")
    assert _count_of(st.get("e0001"), st.graph()) == 0
    assert _count_of(st.get("e0001"), None) == 0       # 没给边表 → 0（不编）


def test_snapshot_restore(tmp_path):
    """快照 = **点 + 边**两个文件（只写点的话, 捞回来的记忆是断连的）。"""
    st = _store(tmp_path)
    st.add(make_node("episode", text="a", event_seq=[1]))
    st.add(make_node("belief", text="b", epistemic="inferred_belief"))
    st.add_edge("supports", "m0001", "m0002")
    snap = tmp_path / "snap_001.jsonl"
    st.snapshot_to(snap)
    assert (tmp_path / "edges.jsonl").is_file()        # 边表跟着走
    # 继续演化后回滚
    st.add(make_node("episode", text="c", event_seq=[2]))
    assert len(st) == 3
    st.restore_from(snap)
    assert len(st) == 2
    assert st.get("m0001") is not None and st.get("m0003") is None
    assert st.graph().supporters("m0002") == ["m0001"]  # 边也回来了


def test_bad_lines_skipped_on_load(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", text="ok"))
    st.save()
    # 混入坏行
    with open(st.path, "a", encoding="utf-8") as fh:
        fh.write("{broken json\n")
    st2 = _store(tmp_path)
    assert len(st2) == 1 and st2.get("m0001").text == "ok"


def test_all_insertion_order(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", text="a"))
    st.add(make_node("episode", text="b"))
    st.add(make_node("experience", text="p", subject="player"))
    assert [n.text or n.text for n in st.all()] == ["a", "b", "p"]
    # 2026-09-21: `by_kind()` 零产品消费者 → 已删; 按 kind 过滤直接用 all()
    assert [n.kind for n in st.all() if n.kind == "episode"] == ["episode", "episode"]


def test_missing_file_empty(tmp_path):
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="nobody")
    assert len(st) == 0
    st.save()                                     # 空库也能原子落盘
    assert st.path.is_file()


# ---------------------------------------------------------------------------
# 随身笔记的落盘（§3.2 —— `notes.py` 的派生缓存, 真源是事件流的 note 操作）
# ---------------------------------------------------------------------------

def _note_events(*items):
    """`(seq, subtype, payload)` → note 事件列表。"""
    from core.session import make_event
    from core.session.events import TYPE_NOTE
    return [make_event(TYPE_NOTE, sub, payload, seq=seq, ts="2026-09-20T21:04:11+09:00")
            for seq, sub, payload in items]


def _two_notes():
    from core.session.events import N_ADD, N_CLOSE
    return _note_events(
        (1, N_ADD, {"text": "周六模型店", "refs": ["m0001"]}),
        (2, N_ADD, {"text": "还他笔记", "refs": ["m0002"]}),
        (3, N_CLOSE, {"id": "n1", "reason": "去过了"}),
    )


def test_notes_path_sits_beside_the_other_two(tmp_path):
    st = _store(tmp_path)
    assert st.notes_path.name == "notes.json"
    assert st.notes_path.parent == st.path.parent == st.edges_path.parent


def test_notes_state_folds_without_a_cache_and_does_not_write(tmp_path):
    st = _store(tmp_path)
    state = st.notes_state(_two_notes())

    assert [it.id for it in state.promise] == ["n1", "n2"]
    assert state.promise[0].closed is True
    # ⚠️ 读路径**不写盘**（缓存由写者在事件 append 之后落）
    assert not st.notes_path.exists()


def test_save_notes_roundtrip_and_cache_hit(tmp_path):
    st = _store(tmp_path)
    events = _two_notes()
    state = st.notes_state(events)
    st.save_notes(state)

    assert st.notes_path.is_file()
    assert st.read_notes().to_dict() == state.to_dict()
    assert st.notes_path.read_text(encoding="utf-8").rstrip().endswith("}")   # 是一个对象
    # 缓存已覆盖全部操作 ⇒ 直接用它（增量折叠与全量重折结果相同）
    assert st.notes_state(events).to_dict() == state.to_dict()
    assert st.notes_state([]).to_dict() == state.to_dict()      # 给空列表也不倒退回空状态


def test_notes_state_refolds_incrementally_and_recovers_from_loss(tmp_path):
    from core.session.events import N_RETIRE
    st = _store(tmp_path)
    events = _two_notes()
    st.save_notes(st.notes_state(events))

    tail = _note_events((4, N_RETIRE, {"id": "n1"}))
    st.save_notes(st.notes_state(events + tail))
    assert [it.id for it in st.read_notes().promise] == ["n2"]

    # 缓存丢了 → 全量重折, 结果与缓存**逐字节一致**（"可重建"这句话的证据）
    before = st.read_notes().to_dict()
    st.notes_path.unlink()
    assert not st.notes_path.exists()
    assert st.notes_state(events + tail).to_dict() == before

    # 缓存坏了 → 当没有（不炸）, 也现折回来
    st.notes_path.write_text("{不是 json", encoding="utf-8")
    assert st.read_notes() is None
    assert st.notes_state(events + tail).to_dict() == before


def test_notes_are_not_part_of_save_or_snapshot(tmp_path):
    """note 的真源是**事件流** —— 并进图事务/快照 = digest 一次回滚带走她的本子。"""
    st = _store(tmp_path)
    st.add(make_node("episode", text="a"))
    st.save_notes(st.notes_state(_two_notes()))

    st.save()                                          # 图那一半
    st.snapshot_to(tmp_path / "snap.jsonl")
    assert not (tmp_path / "snap.jsonl").with_name("notes.json").exists()
    assert st.notes_path.is_file()                     # 但它自己还在（没被 save 清掉）
