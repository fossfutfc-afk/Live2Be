"""revise.py 修订契约测试（AGENT_BRAIN.md §5 / M2b）。"""
import copy

import pytest

from core.brain.wiki_v2 import BrainNode, WikiStoreV2, make_node
from core.brain.wiki_v2.evolution import EvolutionLog
from core.brain.wiki_v2.revise import apply_revision_package


def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")
    # 固定子图: m0001 episode(拆炸弹) + m0002 belief(信任) + m0003 episode(天台) + e0001 experience
    st.add(make_node("episode", narration="拆炸弹初遇", event_seq=[1], ts="2026-08-01T00:00:00"))
    st.add(make_node("belief", content="老师是第一个不会嫌弃我的人", subject="sensei",
                     epistemic="inferred_belief", significance=0.9,
                     links=["m0001"], event_seq=[1]))
    st.add(make_node("episode", narration="天台夜谈", event_seq=[2], ts="2026-08-02T00:00:00",
                     links=["m0002"]))
    st.add(make_node("experience", pattern="提到工作繁忙", subject="sensei",
                     significance=0.7, links=["m0003"], event_seq=[2]))
    return st


def _scope(st) -> set[str]:
    return {n.id for n in st.all()}


def _log(st) -> EvolutionLog:
    return EvolutionLog.for_store(st)


def test_create_and_link_package(tmp_path):
    st = _store(tmp_path)
    pkg = [
        {"action": "create", "entry": {"ref": "n1", "kind": "episode",
                                       "narration": "老师带我去甜品店",
                                       "event_seq": [3], "links": ["m0002"]}},
        {"action": "create", "entry": {"ref": "n2", "kind": "belief",
                                       "content": "老师会认真听我说话", "subject": "sensei",
                                       "epistemic": "inferred_belief",
                                       "links": ["n1"]}},
    ]
    res = apply_revision_package(st, pkg, subgraph_ids=_scope(st))
    assert res.ok, res.errors
    assert res.created == {"n1": "m0004", "n2": "m0005"}
    ep = st.get("m0004")
    assert ep.narration == "老师带我去甜品店" and ep.links == ["m0002"]
    bel = st.get("m0005")
    assert bel.content == "老师会认真听我说话" and bel.links == ["m0004"]
    # evolution log
    entries = _log(st).read()
    assert [e["action"] for e in entries] == ["create", "create"]
    assert entries[0]["pkg"] == "r0001" and entries[0]["id"] == "m0004"


def test_connection_rule_violation_rejected_atomic(tmp_path):
    st = _store(tmp_path)
    pkg = [{"action": "create", "entry": {"kind": "episode",
                                          "narration": "孤立的日常", "event_seq": [9]}}]
    res = apply_revision_package(st, pkg, subgraph_ids=_scope(st))
    assert not res.ok
    assert any("连接裁定" in e for e in res.errors)
    assert len(st) == 4 and st.get("m0004") is None      # 原子: 无残留
    assert _log(st).read() == []                          # 失败不写日志


def test_create_id_ts_engine_assigns(tmp_path):
    st = _store(tmp_path)
    pkg = [{"action": "create", "entry": {"id": "hack0001", "ts": "1999-01-01T00:00:00",
                                          "kind": "episode", "narration": "x",
                                          "event_seq": [9], "links": ["m0002"]}}]
    res = apply_revision_package(st, pkg, subgraph_ids=_scope(st))
    assert res.ok
    node = st.get("m0004")
    assert node is not None and node.id == "m0004" and node.ts != "1999-01-01T00:00:00"


def test_update_rules(tmp_path):
    st = _store(tmp_path)
    scope = _scope(st)
    # 正常 update
    res = apply_revision_package(st, [{"action": "update", "id": "m0001",
                                       "patch": {"significance": 0.95}}],
                                 subgraph_ids=scope)
    assert res.ok and st.get("m0001").significance == 0.95
    # epistemic 不可改
    res = apply_revision_package(st, [{"action": "update", "id": "m0002",
                                       "patch": {"epistemic": "observed_fact"}}],
                                 subgraph_ids=scope)
    assert not res.ok and any("epistemic" in e for e in res.errors)
    # 出厂基座只允许 notes（先造一个 fact）
    st.add(make_node("fact", content="出厂经历", epistemic="canon_fact",
                     source="experience", source_key="k", significance=0.9))
    scope.add("c0001")
    res = apply_revision_package(st, [{"action": "update", "id": "c0001",
                                       "patch": {"significance": 1.0}}],
                                 subgraph_ids=scope)
    assert not res.ok and any("出厂基座" in e for e in res.errors)
    res = apply_revision_package(st, [{"action": "update", "id": "c0001",
                                       "patch": {"notes": "世界线 1 验证过"}}],
                                 subgraph_ids=scope)
    assert res.ok and st.get("c0001").notes == ["世界线 1 验证过"]


def test_merge_inherits_and_deletes_sources(tmp_path):
    st = _store(tmp_path)
    scope = _scope(st)
    res = apply_revision_package(st, [{"action": "merge", "ids": ["m0001", "m0003"],
                                       "into": {"kind": "episode",
                                                "narration": "和老师的两次难忘日常"}}],
                                 subgraph_ids=scope)
    assert res.ok, res.errors
    merged = st.get("m0004")
    assert merged is not None and merged.narration == "和老师的两次难忘日常"
    assert merged.event_seq == [1, 2]
    assert merged.links == ["m0002"]                     # 并集去 self
    assert st.get("m0001") is None and st.get("m0003") is None
    entries = _log(st).read()
    assert entries[-1]["action"] == "merge" and entries[-1]["ids"] == ["m0001", "m0003"]


def test_merge_orphan_rejected(tmp_path):
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="x")
    st.add(make_node("episode", narration="a", event_seq=[1]))
    st.add(make_node("episode", narration="b", event_seq=[2]))
    scope = _scope(st)
    res = apply_revision_package(st, [{"action": "merge", "ids": ["m0001", "m0002"],
                                       "into": {"kind": "episode",
                                                "narration": "合并"}}],
                                 subgraph_ids=scope)
    assert not res.ok and any("至少 1 条链接" in e for e in res.errors)
    assert len(st) == 2                                   # 原子


def test_link_unlink_contradict_resolve(tmp_path):
    st = _store(tmp_path)
    scope = _scope(st)
    ok = apply_revision_package(st, [
        {"action": "link", "from": "m0001", "to": "m0003"},
        {"action": "contradict", "a": "m0001", "b": "m0003"},
    ], subgraph_ids=scope)
    assert ok.ok
    assert "m0003" in st.get("m0001").links
    assert "m0003" in st.get("m0001").contradictions
    ok = apply_revision_package(st, [
        {"action": "unlink", "from": "m0001", "to": "m0003"},
        {"action": "resolve", "a": "m0001", "b": "m0003"},
    ], subgraph_ids=scope)
    assert ok.ok
    assert st.get("m0001").links == [] and st.get("m0001").contradictions == []


def test_accrue_counts_by_engine(tmp_path):
    st = _store(tmp_path)
    scope = _scope(st)
    pkg = [
        {"action": "create", "entry": {"ref": "n1", "kind": "episode",
                                       "narration": "老师又说忙到深夜", "event_seq": [7],
                                       "links": ["e0001"]}},
        {"action": "accrue", "id": "e0001",
         "occurrence": {"episode_ref": "n1", "example": "「这周又忙成狗了」"}},
    ]
    res = apply_revision_package(st, pkg, subgraph_ids=scope)
    assert res.ok, res.errors
    exp = st.get("e0001")
    assert exp.event_seq == [2, 7]                        # 从证据 episode 继承
    assert exp.links == ["m0003", "m0004"]                # 证据 episode 链入
    assert exp.count == 2                                 # 引擎计数 = len(links)
    assert "「这周又忙成狗了」" in exp.examples
    # accrue 无证据 → 拒绝
    res = apply_revision_package(st, [{"action": "accrue", "id": "e0001",
                                       "occurrence": {"episode_ref": "nope"}}],
                                 subgraph_ids=scope)
    assert not res.ok and any("证据" in e for e in res.errors)


def test_accrue_existing_episode_by_id(tmp_path):
    st = _store(tmp_path)
    scope = _scope(st)
    res = apply_revision_package(st, [{"action": "accrue", "id": "e0001",
                                       "occurrence": {"episode_id": "m0001",
                                                      "example": "旧例"}}],
                                 subgraph_ids=scope)
    assert res.ok, res.errors
    exp = st.get("e0001")
    assert exp.links == ["m0003", "m0001"] and exp.event_seq == [2, 1]
    assert exp.count == 2


def test_ids_outside_subgraph_rejected(tmp_path):
    st = _store(tmp_path)
    # 子图只含 m0001
    res = apply_revision_package(st, [{"action": "update", "id": "m0002",
                                       "patch": {"significance": 0.5}}],
                                 subgraph_ids={"m0001"})
    assert not res.ok and any("子图" in e for e in res.errors)
    # create 的 links 引用子图外 id
    res = apply_revision_package(st, [{"action": "create", "entry": {
        "kind": "episode", "narration": "x", "event_seq": [5], "links": ["m0002"]}}],
        subgraph_ids={"m0001"})
    assert not res.ok and any("子图外" in e for e in res.errors)


def test_unknown_action_rejected(tmp_path):
    st = _store(tmp_path)
    res = apply_revision_package(st, [{"action": "teleport", "id": "m0001"}],
                                 subgraph_ids=_scope(st))
    assert not res.ok and any("未知修订动作" in e for e in res.errors)


def test_failure_writes_no_log_and_reloads(tmp_path):
    st = _store(tmp_path)
    # 深拷贝——to_dict 的列表字段是原节点引用, 直接存会被原地铁改污染
    before = {n.id: copy.deepcopy(n.to_dict()) for n in st.all()}
    pkg = [
        {"action": "create", "entry": {"kind": "episode", "narration": "会成功的",
                                       "event_seq": [3], "links": ["m0002"]}},
        {"action": "update", "id": "m0002", "patch": {"epistemic": "canon_fact"}},
    ]
    res = apply_revision_package(st, pkg, subgraph_ids=_scope(st))
    assert not res.ok
    after = {n.id: n.to_dict() for n in st.all()}
    assert after == before                                 # 内存回滚到磁盘态
    assert _log(st).read() == []                           # 日志零残留
