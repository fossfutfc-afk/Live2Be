"""revise.py 修订契约测试（AGENT_BRAIN.md §5 / M2b / 板块 4b 决策执行器）。"""
import copy
import logging

import pytest

from core.brain.wiki_v2 import WikiStoreV2, make_node
from core.brain.wiki_v2.entities import candidate_table, ensure_entities
from core.brain.wiki_v2.evolution import EvolutionLog
from core.brain.wiki_v2.revise import (apply_attribution, apply_decisions,
                                       apply_revision_package)


def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")
    # 固定子图: m0001 episode(拆炸弹) + m0002 belief(信任) + m0003 episode(天台) + e0001 experience
    st.add(make_node("episode", text="拆炸弹初遇", event_seq=[1], ts="2026-08-01T00:00:00"))
    st.add(make_node("belief", text="老师是第一个不会嫌弃我的人", subject="sensei",
                     epistemic="inferred_belief", significance=0.9, event_seq=[1]))
    st.add(make_node("episode", text="天台夜谈", event_seq=[2], ts="2026-08-02T00:00:00"))
    st.add(make_node("experience", text="提到工作繁忙", subject="sensei",
                     significance=0.7, event_seq=[2]))
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
                                       "text": "老师带我去甜品店",
                                       "event_seq": [3], "links": ["m0002"]}},
        {"action": "create", "entry": {"ref": "n2", "kind": "belief",
                                       "text": "老师会认真听我说话", "subject": "sensei",
                                       "epistemic": "inferred_belief",
                                       "links": ["n1"]}},
    ]
    res = apply_revision_package(st, pkg, subgraph_ids=_scope(st))
    assert res.ok, res.errors
    assert res.created == {"n1": "m0004", "n2": "m0005"}
    ep = st.get("m0004")
    # 两条出边都在（G3: 边表）—— n1→m0002 与 belief 的支撑链 supports→m0005
    assert ep.text == "老师带我去甜品店"
    assert set(st.graph().targets("m0004", "supports")) == {"m0002", "m0005"}
    bel = st.get("m0005")
    assert bel.text == "老师会认真听我说话"
    assert st.graph().supporters("m0005") == ["m0004"]
    assert st.audit() == []                      # 全链路后图干净
    # evolution log
    entries = _log(st).read()
    assert [e["action"] for e in entries] == ["create", "create"]
    assert entries[0]["pkg"] == "r0001" and entries[0]["id"] == "m0004"


def test_connection_rule_violation_rejected_atomic(tmp_path):
    st = _store(tmp_path)
    pkg = [{"action": "create", "entry": {"kind": "episode",
                                          "text": "孤立的日常", "event_seq": [9]}}]
    res = apply_revision_package(st, pkg, subgraph_ids=_scope(st))
    assert not res.ok
    assert any("连接裁定" in e for e in res.errors)
    assert len(st) == 4 and st.get("m0004") is None      # 原子: 无残留
    assert _log(st).read() == []                          # 失败不写日志


def test_create_id_ts_engine_assigns(tmp_path):
    st = _store(tmp_path)
    pkg = [{"action": "create", "entry": {"id": "hack0001", "ts": "1999-01-01T00:00:00",
                                          "kind": "episode", "text": "x",
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
    # ⏸ 原"出厂基座只允许 notes 追加"那半段 2026-09-21 删——`is_seed()`/`source`/`notes`
    # 整族退役（生产者已归档, 真机 0 个 seed 节点）。update 现在只受字段白名单约束。


def test_merge_inherits_and_deletes_sources(tmp_path):
    st = _store(tmp_path)
    scope = _scope(st)
    res = apply_revision_package(st, [{"action": "merge", "ids": ["m0001", "m0003"],
                                       "into": {"kind": "episode",
                                                "text": "和老师的两次难忘日常"}}],
                                 subgraph_ids=scope)
    assert res.ok, res.errors
    merged = st.get("m0004")
    assert merged is not None and merged.text == "和老师的两次难忘日常"
    assert merged.event_seq == [1, 2]
    # 出边继承（m0001/m0003 原有支撑 m0002）+ 端点 remap 到产物（G3: 边表）
    assert set(st.graph().targets("m0004", "supports")) == {"m0002", "e0001"}
    assert "m0004" in st.graph().supporters("m0002")     # belief 支撑不断链
    assert st.graph().supporters("e0001") == ["m0004"]   # 入边重接
    assert st.get("m0001") is None and st.get("m0003") is None
    entries = _log(st).read()
    assert entries[-1]["action"] == "merge" and entries[-1]["ids"] == ["m0001", "m0003"]


def test_merge_orphan_rejected(tmp_path):
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="x")
    st.add(make_node("episode", text="a", event_seq=[1]))
    st.add(make_node("episode", text="b", event_seq=[2]))
    scope = _scope(st)
    res = apply_revision_package(st, [{"action": "merge", "ids": ["m0001", "m0002"],
                                       "into": {"kind": "episode",
                                                "text": "合并"}}],
                                 subgraph_ids=scope)
    assert not res.ok and any("至少 1 条边" in e for e in res.errors)
    assert len(st) == 2                                   # 原子


def test_link_unlink_contradict_resolve(tmp_path):
    st = _store(tmp_path)
    scope = _scope(st)
    ok = apply_revision_package(st, [
        {"action": "link", "from": "m0001", "to": "m0003"},
        {"action": "contradict", "a": "m0001", "b": "m0003"},
    ], subgraph_ids=scope)
    assert ok.ok
    assert "m0003" in st.neighbors("m0001")
    assert st.graph().edges_from("m0001", "contradicts")
    ok = apply_revision_package(st, [
        {"action": "unlink", "from": "m0001", "to": "m0003"},
        {"action": "resolve", "a": "m0001", "b": "m0003"},
    ], subgraph_ids=scope)
    assert ok.ok
    assert st.graph().targets("m0001") == ["m0002"]
    assert st.graph().edges_from("m0001", "contradicts") == []


def test_accrue_counts_by_engine(tmp_path):
    st = _store(tmp_path)
    scope = _scope(st)
    pkg = [
        {"action": "create", "entry": {"ref": "n1", "kind": "episode",
                                       "text": "老师又说忙到深夜", "event_seq": [7],
                                       "links": ["e0001"]}},
        {"action": "accrue", "id": "e0001",
         "occurrence": {"episode_ref": "n1", "example": "「这周又忙成狗了」"}},
    ]
    res = apply_revision_package(st, pkg, subgraph_ids=scope)
    assert res.ok, res.errors
    exp = st.get("e0001")
    assert exp.event_seq == [2, 7]                        # 从证据 episode 继承
    assert st.graph().supporters("e0001") == ["m0003", "m0004"]   # 证据 episode 链入
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
    assert st.graph().supporters("e0001") == ["m0003", "m0001"]
    assert exp.event_seq == [2, 1]


def test_ids_outside_subgraph_rejected(tmp_path):
    st = _store(tmp_path)
    # 子图只含 m0001
    res = apply_revision_package(st, [{"action": "update", "id": "m0002",
                                       "patch": {"significance": 0.5}}],
                                 subgraph_ids={"m0001"})
    assert not res.ok and any("子图" in e for e in res.errors)
    # create 的 links 引用子图外 id
    res = apply_revision_package(st, [{"action": "create", "entry": {
        "kind": "episode", "text": "x", "event_seq": [5], "links": ["m0002"]}}],
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
        {"action": "create", "entry": {"kind": "episode", "text": "会成功的",
                                       "event_seq": [3], "links": ["m0002"]}},
        {"action": "update", "id": "m0002", "patch": {"epistemic": "observed_fact"}},
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
    """决策执行的引擎字段（apply_decisions 的 ts/event_seq）。"""
    return {"ts": "2026-09-02T12:00:00", "event_seq": [3]}


def _episode(st, text="老师请我吃甜品"):
    """决策行引用的 episode 已由 Round A 建好（本测试直接预置）。"""
    st.add(make_node("episode", text=text, event_seq=[3],
                     ts="2026-09-02T12:00:00"))


def test_decisions_update_logs_before_after(tmp_path):
    """update 的溯源**落在 evolution 日志**（before/after）, 不在节点字段里。

    2026-09-21 之前是往 `belief.history` 追加"改写后的正文"——那个字段只写不读,
    且记的是**新值**（原文丢失）, 不是可用的溯源。现在同一件事记在 evolution.jsonl,
    形状与修订包路径的 `changed: {k: [before, after]}` 对齐。
    """
    st = _store(tmp_path)
    _episode(st)
    rows = [
        {"episode": "m0004", "decision": "update", "target": "u0001",
         "patch": {"text": "老师会记得我的喜好", "significance": 0.95}},
    ]
    created = apply_decisions(st, rows, id_map={"u0001": "m0002"}, **_ctx_kw())
    assert created == []
    bel = st.get("m0002")
    assert bel.text == "老师会记得我的喜好" and bel.significance == 0.95
    assert not hasattr(bel, "history")                  # 字段已退役
    assert "m0004" in st.graph().supporters("m0002")
    row = _log(st).read()[-1]
    assert row["action"] == "update" and row["target"] == "m0002"
    assert row["changed"]["text"][1] == "老师会记得我的喜好"   # after
    assert row["changed"]["text"][0] != "老师会记得我的喜好"  # before（旧正文）
    assert row["changed"]["significance"] == [0.9, 0.95]


def test_decisions_update_rerun_logs_nothing_changed(tmp_path):
    """崩溃窗口重跑: 同正文重放 → before == after ⇒ `changed` 是空 dict（幂等可判）。"""
    st = _store(tmp_path)
    _episode(st)
    rows = [{"episode": "m0004", "decision": "update", "target": "u0001",
             "patch": {"text": "老师会记得我的喜好"}}]
    for _ in range(2):
        apply_decisions(st, rows, id_map={"u0001": "m0002"}, **_ctx_kw())
    bel = st.get("m0002")
    assert bel.text == "老师会记得我的喜好"
    rows_log = [r for r in _log(st).read() if r.get("action") == "update"]
    assert len(rows_log) == 2
    assert rows_log[0]["changed"]["text"][1] == "老师会记得我的喜好"   # 首次: 真改了
    assert rows_log[1]["changed"] == {}                                  # 重跑: 无变化


def test_decisions_update_patch_outside_whitelist_rejected(tmp_path):
    """patch 只有引擎字段（links 等）→ 白名单滤空 = 行无操作 → 整包拒。"""
    st = _store(tmp_path)
    _episode(st)
    rows = [{"episode": "m0004", "decision": "update", "target": "u0001",
             "patch": {"links": ["e0001"]}}]            # parse 能过（非空）但不可执行
    with pytest.raises(ValueError, match="patch 不含可改字段"):
        apply_decisions(st, rows, id_map={"u0001": "m0002"}, **_ctx_kw())


def test_decisions_add_belief_linked_before_store(tmp_path):
    """add belief: 引擎归属 epistemic + 入仓后立刻补 supports 边（G3: 边表）。"""
    st = _store(tmp_path)
    _episode(st, text="老师把猫抱到我腿边")
    rows = [{"episode": "m0004", "decision": "add", "kind": "belief",
             "subject": "老师的温柔", "text": "老师会把小猫抱到我腿上", "significance": 0.85}]
    created = apply_decisions(st, rows, id_map={}, **_ctx_kw())
    assert created == ["m0005"]                          # belief 与 episode 同 m 前缀
    bel = st.get("m0005")
    assert bel.epistemic == "inferred_belief"            # 引擎归属
    assert st.graph().supporters("m0005") == ["m0004"]
    # 边带**本段日期**（digest 传的 ts, 不是"写库时刻"）—— 2026-09-22 补
    e = st.graph().edges_to("m0005", "supports")[0]
    assert e.ts == _ctx_kw()["ts"]
    assert st.audit() == []


def test_decisions_touch_target_must_be_cognition(tmp_path):
    """target 解析到 episode（非认知）→ _ensure_cognition 拒（防御兜底）。"""
    st = _store(tmp_path)
    _episode(st, text="天台夜谈二号")
    rows = [{"episode": "m0004", "decision": "touch", "target": "u0001"}]
    with pytest.raises(ValueError, match="target 必须是 belief/experience"):
        apply_decisions(st, rows, id_map={"u0001": "m0001"}, **_ctx_kw())  # m0001 是 episode


def test_decisions_empty_rows_noop(tmp_path):
    st = _store(tmp_path)
    before = {n.id: n.to_dict() for n in st.all()}
    assert apply_decisions(st, [], id_map={}, **_ctx_kw()) == []
    after = {n.id: n.to_dict() for n in st.all()}
    assert after == before


# ---------------------------------------------------------------------------
# D2b —— 第 3 轮执行器（归属 + entity 维护）
# ---------------------------------------------------------------------------

def _attr_store(tmp_path) -> WikiStoreV2:
    """`_store` + 两个初始化 entity（`self`/`sensei`）—— 第 3 轮的前提。"""
    st = _store(tmp_path)
    ensure_entities(st, char_name="伊草 遥香", aliases=("遥香",), player_name="阿宅")
    return st


def test_attribution_accepts_promise_nodes(tmp_path):
    """固化出来的 `promise` 节点也要能被归属（§6: "关于他的承诺"是 entity 车道要答的问题）。

    ⚠️ `_ATTACHABLE` 2026-09-25 加了 `promise` —— 漏了这一项, 承诺进了图却没人认领。
    """
    st = _attr_store(tmp_path)
    pid = st.add(make_node("promise", text="周六模型店", outcome="kept",
                           event_seq=[3], ts="2026-09-02T12:00:00"))
    _, local_of = candidate_table(st)

    assert apply_attribution(st, [{"action": "attach", "entity": local_of["x0001"],
                                   "hint": "老师", "nodes": ["u0001"]}],
                             id_map={"u0001": pid}, local_of=local_of, **_ctx_kw()) == []
    assert st.graph().targets(pid, "about") == ["x0001"]


def test_attribution_attaches_and_writes_alias(tmp_path):
    """`attach` = 归属的唯一落地形式（写 `about` 边）+ hint 顺手写回别名。"""
    st = _attr_store(tmp_path)
    _, local_of = candidate_table(st)
    rows = [
        {"action": "attach", "entity": local_of["x0001"], "hint": "老师",
         "nodes": ["u0001", "u0003"]},                    # "老师" 已是主名 → 不写
        {"action": "attach", "entity": local_of["x0000"], "hint": "先生",
         "nodes": ["u0002"]},                             # 新称呼 → 写回别名
    ]
    assert apply_attribution(st, rows, id_map={"u0001": "m0001", "u0002": "m0002",
                                               "u0003": "m0003"},
                             local_of=local_of, **_ctx_kw()) == []
    g = st.graph()
    assert g.targets("m0001", "about") == ["x0001"]        # 边方向 = 节点 → entity
    assert g.targets("m0003", "about") == ["x0001"]
    assert g.targets("m0002", "about") == ["x0000"]
    assert st.get("x0000").aliases[-1] == "先生"
    assert st.audit() == []
    # 幂等: 同一份表重跑 → 边不重复、别名不重复
    apply_attribution(st, rows, id_map={"u0001": "m0001", "u0002": "m0002",
                                        "u0003": "m0003"},
                      local_of=local_of, **_ctx_kw())
    assert len(g := st.graph().edges_from("m0001", "about")) == 1
    assert st.get("x0000").aliases.count("先生") == 1
    # 台账: 每条 attach 一行（含写了几条边 / 是否写了别名）
    entries = [e for e in _log(st).read() if e["action"] == "attach"]
    assert [e["nodes"] for e in entries] == [2, 1, 2, 1]
    assert [e["alias"] for e in entries] == [False, True, False, False]


def test_attribution_new_entity_needs_reason_and_is_idempotent(tmp_path):
    """`new_entity`: 必给理由 + 载荷可随行给 + 重跑复用（崩溃窗口幂等）。"""
    st = _attr_store(tmp_path)
    _, local_of = candidate_table(st)
    rows = [{"action": "new_entity", "name": "小玉", "aliases": ["tama"],
             "reason": "本章登场两次, 三个月后再提到要一致",
             "text": "杂草屋隔壁的孩子", "state": ["抱着一只破旧的兔子玩偶"],
             "nodes": ["u0002"]}]
    assert apply_attribution(st, rows, id_map={"u0002": "m0002"},
                             local_of=local_of, **_ctx_kw()) == ["x0002"]
    n = st.get("x0002")
    assert (n.kind, n.name, n.aliases, n.text, n.state) == (
        "entity", "小玉", ["tama"], "杂草屋隔壁的孩子", ["抱着一只破旧的兔子玩偶"])
    assert st.graph().targets("m0002", "about") == ["x0002"]
    assert st.next_id("x") == "x0003"                    # 保留号仍挡住 0/1
    entry = _log(st).read()[-1]
    assert entry["action"] == "new_entity" and "三个月" in entry["reason"]

    # 重跑: 同名 → 复用（**不建第二个**）, 边也不重复, created 为空
    assert apply_attribution(st, rows, id_map={"u0002": "m0002"},
                             local_of=local_of, **_ctx_kw()) == []
    assert [x.id for x in st.all() if x.kind == "entity"] == ["x0000", "x0001", "x0002"]
    assert len(st.graph().edges_to("x0002", "about")) == 1
    assert _log(st).read()[-1]["action"] == "new_entity.dup"

    # 准入门槛: 缺理由 → 拒（§3.0）
    with pytest.raises(ValueError, match="必须给一句理由"):
        apply_attribution(st, [{"action": "new_entity", "name": "小玉二号",
                                "nodes": ["u0002"]}],
                          id_map={"u0002": "m0002"}, local_of=local_of, **_ctx_kw())


def test_attribution_rewrite_and_guards(tmp_path, caplog):
    """`rewrite` 重写载荷（空值=保留）+ 三道闸: 保留号 / 候选表 / 可归属 kind。"""
    st = _attr_store(tmp_path)
    _, local_of = candidate_table(st)
    apply_attribution(st, [{"action": "rewrite", "entity": local_of["x0001"],
                            "text": "他是第一个不会嫌弃我的人",
                            "state": ["今天戴了眼镜"]}],
                      id_map={}, local_of=local_of, **_ctx_kw())
    assert st.get("x0001").text == "他是第一个不会嫌弃我的人"
    # 空 state（None/[]）→ **保留**（今天没有"删掉一条 state"的机制 —— §9-4 未定）
    apply_attribution(st, [{"action": "rewrite", "entity": local_of["x0001"],
                            "text": "他是唯一会等我的人"}],
                      id_map={}, local_of=local_of, **_ctx_kw())
    assert st.get("x0001").state == ["今天戴了眼镜"]
    assert _log(st).read()[-1]["changed"]["text"][0] == "他是第一个不会嫌弃我的人"
    # rewrite 什么都不给 → 拒（不是静默 no-op）
    with pytest.raises(ValueError, match="没给可改字段"):
        apply_attribution(st, [{"action": "rewrite", "entity": local_of["x0001"]}],
                          id_map={}, local_of=local_of, **_ctx_kw())

    with pytest.raises(ValueError, match="候选表"):
        apply_attribution(st, [{"action": "attach", "entity": "c0099",
                                "nodes": ["u0001"]}],
                          id_map={"u0001": "m0001"}, local_of=local_of, **_ctx_kw())
    with pytest.raises(ValueError, match="只能归属"):     # entity 自己不是可归属对象
        apply_attribution(st, [{"action": "attach", "entity": local_of["x0001"],
                                "nodes": ["u0009"]}],
                          id_map={"u0009": "x0000"}, local_of=local_of, **_ctx_kw())
    with pytest.raises(ValueError, match="未知动作"):
        apply_attribution(st, [{"action": "mentions", "entity": local_of["x0001"]}],
                          id_map={}, local_of=local_of, **_ctx_kw())

    # 保留号不在（= D3a 没跑过）→ **跳过 new_entity** 并告警（归属边照写）
    bare = _store(tmp_path / "bare")
    _, none_local = candidate_table(bare)
    with caplog.at_level(logging.WARNING):
        assert apply_attribution(
            bare, [{"action": "new_entity", "name": "小玉", "reason": "r",
                    "nodes": ["u0001"]}],
            id_map={"u0001": "m0001"}, local_of=none_local) == []
    assert [n.id for n in bare.all() if n.kind == "entity"] == []
    assert any("x0001" in r.getMessage() for r in caplog.records)
