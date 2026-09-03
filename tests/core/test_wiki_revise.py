"""revise.py 修订契约测试（AGENT_BRAIN.md §5 / M2b / 板块 4b 决策执行器）。"""
import copy

import pytest

from core.brain.wiki_v2 import BrainNode, WikiStoreV2, make_node
from core.brain.wiki_v2.evolution import EvolutionLog
from core.brain.wiki_v2.revise import apply_decisions, apply_revision_package


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
    # 真实流程同款: 双向边走 add_link（audit 不变量要求双向共识）
    st.add_link("m0001", "m0002")
    st.add_link("m0003", "m0002")
    st.add_link("e0001", "m0003")
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
    # 双向语义: n2 链入 n1 → n1.links 含 n2（反向边正确补挂）
    assert ep.narration == "老师带我去甜品店" and ep.links == ["m0002", "m0005"]
    bel = st.get("m0005")
    assert bel.content == "老师会认真听我说话" and bel.links == ["m0004"]
    assert st.audit() == []                      # 全链路后图干净
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
    # 出厂基座只允许 notes（出厂 episode, source=experience; _store 已占 m0001-3/e0001）
    st.add(make_node("episode", narration="出厂经历", source="experience",
                     source_key="k", significance=0.9))
    scope.add("m0004")
    res = apply_revision_package(st, [{"action": "update", "id": "m0004",
                                       "patch": {"significance": 1.0}}],
                                 subgraph_ids=scope)
    assert not res.ok and any("出厂基座" in e for e in res.errors)
    res = apply_revision_package(st, [{"action": "update", "id": "m0004",
                                       "patch": {"notes": "世界线 1 验证过"}}],
                                 subgraph_ids=scope)
    assert res.ok and st.get("m0004").notes == ["世界线 1 验证过"]


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
    # 出边继承（m0003 原有支撑 m0002）+ 入边重接（e0001 曾指向 m0003 → 改指 merged）
    assert set(merged.links) == {"m0002", "e0001"}
    assert st.get("m0002").links == ["m0004"]            # belief 支撑不断链
    assert st.get("e0001").links == ["m0004"]            # 入边重接
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
    assert st.get("m0001").links == ["m0002"] and st.get("m0001").contradictions == []


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
        {"action": "update", "id": "m0002", "patch": {"epistemic": "speculation"}},
    ]
    res = apply_revision_package(st, pkg, subgraph_ids=_scope(st))
    assert not res.ok
    after = {n.id: n.to_dict() for n in st.all()}
    assert after == before                                 # 内存回滚到磁盘态
    assert _log(st).read() == []                           # 日志零残留


# ============================================================================
# 板块 4b: apply_decisions（Round B 决策表执行器护栏）
# ============================================================================

def _ctx_kw():
    """决策执行的引擎字段（apply_decisions 的 ts/segment_id/event_seq）。"""
    return {"ts": "2026-09-02T12:00:00", "segment_id": "seg-3", "event_seq": [3]}


def _episode(st, narration="老师请我吃甜品"):
    """决策行引用的 episode 已由 Round A 建好（本测试直接预置）。"""
    st.add(make_node("episode", narration=narration, event_seq=[3],
                     ts="2026-09-02T12:00:00", segment_id="seg-3"))


def test_decisions_update_adds_history_and_links(tmp_path):
    st = _store(tmp_path)
    _episode(st)
    rows = [
        {"episode": "m0004", "decision": "update", "target": "u0001",
         "patch": {"content": "老师会记得我的喜好", "significance": 0.95}},
    ]
    created = apply_decisions(st, rows, id_map={"u0001": "m0002"}, **_ctx_kw())
    assert created == []
    bel = st.get("m0002")
    assert bel.content == "老师会记得我的喜好" and bel.significance == 0.95
    assert bel.history == [{"episode_id": "m0004", "content": "老师会记得我的喜好",
                            "ts": "2026-09-02T12:00:00"}]
    assert "m0004" in bel.links and "m0002" in st.get("m0004").links


def test_decisions_update_history_not_duplicated_on_rerun(tmp_path):
    """崩溃窗口重跑: 同 content 重放 → history 不重复追加（幂等）。"""
    st = _store(tmp_path)
    _episode(st)
    rows = [{"episode": "m0004", "decision": "update", "target": "u0001",
             "patch": {"content": "老师会记得我的喜好"}}]
    for _ in range(2):
        apply_decisions(st, rows, id_map={"u0001": "m0002"}, **_ctx_kw())
    bel = st.get("m0002")
    assert len(bel.history) == 1


def test_decisions_update_patch_outside_whitelist_rejected(tmp_path):
    """patch 只有引擎字段（links 等）→ 白名单滤空 = 行无操作 → 整包拒。"""
    st = _store(tmp_path)
    _episode(st)
    rows = [{"episode": "m0004", "decision": "update", "target": "u0001",
             "patch": {"links": ["e0001"]}}]            # parse 能过（非空）但不可执行
    with pytest.raises(ValueError, match="patch 不含可改字段"):
        apply_decisions(st, rows, id_map={"u0001": "m0002"}, **_ctx_kw())


def test_decisions_add_belief_linked_before_store(tmp_path):
    """add belief: 引擎归属 epistemic + 先链后入仓（belief 校验 links ≥1）。"""
    st = _store(tmp_path)
    _episode(st, narration="老师把猫抱到我腿边")
    rows = [{"episode": "m0004", "decision": "add", "kind": "belief",
             "subject": "老师的温柔", "content": "老师会把小猫抱到我腿上", "significance": 0.85}]
    created = apply_decisions(st, rows, id_map={}, **_ctx_kw())
    assert created == ["m0005"]                          # belief 与 episode 同 m 前缀
    bel = st.get("m0005")
    assert bel.epistemic == "inferred_belief"            # 引擎归属
    assert bel.links == ["m0004"] and "m0005" in st.get("m0004").links
    assert st.audit() == []


def test_decisions_touch_target_must_be_cognition(tmp_path):
    """target 解析到 episode（非认知）→ _ensure_cognition 拒（防御兜底）。"""
    st = _store(tmp_path)
    _episode(st, narration="天台夜谈二号")
    rows = [{"episode": "m0004", "decision": "touch", "target": "u0001"}]
    with pytest.raises(ValueError, match="target 必须是 belief/experience"):
        apply_decisions(st, rows, id_map={"u0001": "m0001"}, **_ctx_kw())  # m0001 是 episode


def test_decisions_empty_rows_noop(tmp_path):
    st = _store(tmp_path)
    before = {n.id: n.to_dict() for n in st.all()}
    assert apply_decisions(st, [], id_map={}, **_ctx_kw()) == []
    after = {n.id: n.to_dict() for n in st.all()}
    assert after == before
