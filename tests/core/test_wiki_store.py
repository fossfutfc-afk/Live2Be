"""WikiStore v2 存储层测试（AGENT_BRAIN.md §2 / M1b）。"""
import pytest

from core.brain import WikiStoreV2, make_node
from core.brain.graph import Edge
from core.brain.nodes import format_id


def _store(tmp_path, char="igusa_haruka") -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id=char)


def test_add_save_reload_roundtrip(tmp_path):
    st = _store(tmp_path)
    n1 = make_node("episode", text="天台夜谈", significance=0.8,
                   event_seq=[42, 58], observer="igusa_haruka")
    n2 = make_node("belief", text="我被需要",
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
    assert st.add(make_node("belief", text="y",
                            links=["m0001"])) == "m0003"
    assert st.next_id("m") == "m0004"
    assert st.next_id("e") == "e0002"
    assert format_id("m", 3) == "m0003"


def test_promise_prefix_is_gone(tmp_path):
    """⏸ 原 `test_promise_prefix_and_persistence`（2026-09-29 承诺退图后作废）。

    `p` 前缀随 promise 一起退役 ⇒ `_PREFIX` 里没有它, 而 `add()` 对没有前缀的 kind
    一律走 `m`（兜底）。这里钉住"没留下一个还会发 `p` 号的静默写路"。
    """
    from core.brain.store import _PREFIX

    assert "promise" not in _PREFIX
    assert set(_PREFIX) == {"experience", "episode", "belief", "entity", "group"}
    assert "p" not in _PREFIX.values()


def test_add_rejects_invalid_node(tmp_path):
    st = _store(tmp_path)
    with pytest.raises(ValueError):
        st.add(make_node("episode"))                            # 缺 text
    with pytest.raises(ValueError):
        # 认知不伪装成事实 —— ⭐ 2026-09-29 起判据是 observer（`epistemic` 已退役）
        st.add(make_node("belief", text="x", observer="阿露"))
    with pytest.raises(ValueError):
        st.add(make_node("group"))                              # 缺 title（类名必填）
    # ⏸ 原第二条（"belief 无支撑"）**不在 add 这一层** —— 那条规则 2026-09-21 搬去
    # `store.audit()`（见 `test_wiki_audit.py`）, add 只跑 `validate()`。


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
    st.add(make_node("belief", text="b"))
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


def test_add_edge_symmetric_is_canonicalised(tmp_path):
    """⭐ 对称 rel（`contradicts` / `akin`）正反只留一条；**有向边不许被交换**（N1a）。

    实机后果（不修的话）: 同一次"她发现同类"在边表里写成**两行** ⇒ L2 分群时数两遍；
    而 `remove_edge` 反着传删不掉 ⇒ 留下一条谁也删不掉的边。
    """
    st = _store(tmp_path)
    st.add(make_node("episode", text="a", event_seq=[1]))
    st.add(make_node("episode", text="b", event_seq=[2]))
    st.add_edge("akin", "m0002", "m0001", ts="2026-09-29T10:00:00")   # 反着传
    st.add_edge("akin", "m0001", "m0002")                            # 正着传 → 幂等命中
    assert [(e.rel, e.src, e.dst) for e in st.edges()] == [("akin", "m0001", "m0002")]
    # ⚠️ 有向边**不许**被规范化 —— 方向就是语义（这里 m0003 > m0001, 规范化会把它翻过来）
    st.add(make_node("belief", text="c"))
    st.add_edge("supports", "m0003", "m0001")
    assert ("supports", "m0003", "m0001") in [(e.rel, e.src, e.dst) for e in st.edges()]
    # 反着传也删得掉（与 `add_edge` 共用同一个规范化）
    st.remove_edge("akin", "m0002", "m0001")
    assert all(e.rel != "akin" for e in st.edges())


def test_clone_state_copies_edges_field_complete(tmp_path):
    """⚠️ 守门（N1a）: `clone_state` 的边必须**逐字段**拷 —— 它是 digest 事务回滚的基础。

    历史坑: 原来是 `Edge(e.rel, e.src, e.dst, e.ts)` **位置参数** ⇒ 给 `Edge` 加字段时
    会**静默丢掉**那个字段（回滚把状态回成"少了一半属性"，而且一声不吭）。
    """
    import dataclasses
    import inspect

    st = _store(tmp_path)
    st.add(make_node("episode", text="a", event_seq=[1]))
    st.add(make_node("episode", text="b", event_seq=[2]))
    st.add_edge("akin", "m0001", "m0002", ts="2026-09-29T10:00:00")
    expected = {"rel": "akin", "src": "m0001", "dst": "m0002", "ts": "2026-09-29T10:00:00"}
    assert st.edges()[0].to_dict() == expected
    _nodes, edges = st.clone_state()
    st.delete("m0001")                                # 破坏现场（点删掉、边被筛掉）
    assert st.edges() == []
    st.restore_state((_nodes, edges))
    assert st.edges()[0].to_dict() == expected        # ⭐ 回滚后字段一个不少
    for f in dataclasses.fields(Edge):
        assert getattr(st.edges()[0], f.name) == getattr(edges[0], f.name)
    # ⭐ 结构性断言: 本函数**不许手工构造 Edge** —— 谁改回位置参数, 这条立刻红。
    #   ⚠️ 必须先剥掉 docstring 再扫: 上一版直接 `getsource` 扫，
    #   结果被**注释里那句 `Edge(e.rel, e.src, e.dst, e.ts)`** 自己绊倒。
    import ast
    import inspect
    import textwrap

    fn = ast.parse(textwrap.dedent(
        inspect.getsource(WikiStoreV2.clone_state))).body[0]
    fn.body = [n for n in fn.body
               if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                       and isinstance(n.value.value, str))]
    assert "Edge(" not in ast.unparse(fn), \
        "clone_state 必须走 Edge.from_dict(e.to_dict()) —— 位置参数会在加字段时静默丢属性"


def test_every_kind_has_an_explicit_id_prefix():
    """⭐ 结构性守门（N1b）: `KINDS` 里**每一个 kind** 都必须在 `_PREFIX` 里有前缀。

    为什么必须有这条: `add()` 走 `_PREFIX.get(kind, "m")` —— 漏登记的 kind 会**静默拿到
    `m` 号**，与 episode/belief 撞号。而 id 是边的端点 ⇒ **撞号会让边指错记忆**
    （真机后果: "她发现同类"落到另一条 episode 上，而且不报错）。
    """
    from core.brain import store as S
    from core.brain.nodes import KINDS

    missing = [k for k in KINDS if k not in S._PREFIX]
    assert not missing, f"这些 kind 没登记 id 前缀（会静默落到 m 号）: {missing}"
    # `m` 被 episode/belief **有意**共用（同一族"记忆条目"）；其余前缀两两不同
    others = [p for k, p in S._PREFIX.items() if p != "m"]
    assert len(set(others)) == len(others), f"前缀撞车: {sorted(others)}"


def test_group_node_prefix_and_roundtrip(tmp_path):
    """群节点（N1b）: 前缀 `g` · 只要 `title` · 落盘读回稳定。"""
    st = _store(tmp_path)
    assert st.add(make_node("group", title="苔藓")) == "g0001"
    st.add(make_node("episode", text="a", event_seq=[1]))
    assert st.add(make_node("belief", text="b")) == "m0002"
    st.save()
    st2 = _store(tmp_path)
    assert st2.get("g0001").kind == "group" and st2.get("g0001").title == "苔藓"


def test_group_without_title_is_rejected(tmp_path):
    """群**必须有类名**（`_REQUIRED["group"] = ("title",)`）—— 没名字的群不可被指向。"""
    st = _store(tmp_path)
    with pytest.raises(ValueError):
        st.add(make_node("group", text="只有正文没有名字"))


def test_member_of_edges_and_multi_membership(tmp_path):
    """⭐ 成员靠 `member_of` 边；**一个 episode 可以同时在两个群里**（多归属）。

    为什么不是"群节点上存 `members` 列表": 成员是**随时间一次次建立的**，每条**各有自己的
    `ts`** —— "什么时候加入的"是信息，列表只能给出群节点的 `ts`（见
    `DESIGN_MMT_NEW_ACTION §4.5.3`，那里记着我判错过一次）。
    """
    st = _store(tmp_path)
    st.add(make_node("episode", text="a", event_seq=[1]))       # m0001
    st.add(make_node("group", title="苔藓"))                    # g0001
    st.add(make_node("group", title="夏莱"))                    # g0002
    st.add_edge("member_of", "m0001", "g0001", ts="2026-09-29T10:00:00")
    st.add_edge("member_of", "m0001", "g0002", ts="2026-09-29T11:00:00")
    g = st.graph()
    assert g.sources("g0001", "member_of") == ["m0001"]
    assert g.sources("g0002", "member_of") == ["m0001"]          # ⭐ 多归属
    # 每条加入**各自的时刻**都留着
    assert [e.ts for e in st.edges() if e.rel == "member_of"] == \
        ["2026-09-29T10:00:00", "2026-09-29T11:00:00"]
    # ⚠️ `member_of` 是**有向**的（不在 SYMMETRIC_RELS）⇒ 反着写不会被规范化成同一条
    #   （方向由写路径保证 —— store 有意不做 rel/kind 配对校验, 那是契约层的事）
    st.add_edge("member_of", "g0001", "m0001")
    assert len([e for e in st.edges() if e.rel == "member_of"]) == 3
    # ⭐ `supports` 查询**不会**把群捞出来（`member_of` 是自己的 rel, 没混进认知侧）
    assert g.supporters("g0001") == [] and g.supporters("g0002") == []


def test_audit_does_not_treat_group_as_belief(tmp_path):
    """`audit()` 的"belief 必须有 supports 入边"**不适用于 group** —— 群不是认知。"""
    st = _store(tmp_path)
    st.add(make_node("group", title="苔藓"))
    st.add(make_node("episode", text="a", event_seq=[1]))
    st.add_edge("member_of", "m0001", "g0001")
    assert st.audit() == []


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
    st.add(make_node("belief", text="b"))
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
    st.add(make_node("belief", text="b"))
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
    from core.brain.read.render import _count_of
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
    st.add(make_node("belief", text="b"))
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
        (3, N_CLOSE, {"id": "n1", "afterwards": "去过了", "state": "kept"}),
    )


def test_notes_path_sits_beside_the_other_two(tmp_path):
    st = _store(tmp_path)
    assert st.notes_path.name == "notes.json"
    assert st.notes_path.parent == st.path.parent == st.edges_path.parent


def test_notes_state_folds_without_a_cache_and_does_not_write(tmp_path):
    st = _store(tmp_path)
    state = st.notes_state(_two_notes())

    assert [it.id for it in state.pinned] == ["n2"]      # n1 已被划掉（close = 移除）
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
    from core.session.events import N_UPDATE
    st = _store(tmp_path)
    events = _two_notes()
    st.save_notes(st.notes_state(events))

    tail = _note_events((4, N_UPDATE, {"id": "n2", "due": "2026-01-01"}))
    st.save_notes(st.notes_state(events + tail))
    assert [it.id for it in st.read_notes().pinned] == ["n2"]
    assert st.read_notes().pinned[0].due == "2026-01-01"      # 增量折叠真的接上了

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
