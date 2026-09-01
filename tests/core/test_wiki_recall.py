"""recall.py 三通道召回测试（AGENT_BRAIN.md §6 / M4）。"""
import random
from datetime import datetime, timedelta

from core.brain.wiki_v2 import BrainNode, WikiStoreV2, make_node
from core.brain.wiki_v2.recall import recall_subgraph


def _ids(nodes):
    for i, n in enumerate(nodes, 1):
        n.id = f"m{i:04d}"
    return nodes


def _store(tmp_path, nodes) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    for n in nodes:
        st.add(n)
    return st


def _ep(narration, sig=0.5, tags=None, ts=None, links=None, contradictions=None,
        event_seq=None):
    kw = dict(narration=narration, significance=sig)
    if tags:
        kw["tags"] = tags
    if ts:
        kw["ts"] = ts
    if links:
        kw["links"] = links
    if contradictions:
        kw["contradictions"] = contradictions
    if event_seq:
        kw["event_seq"] = event_seq
    return make_node("episode", **kw)


def _now_iso(days_ago: int) -> str:
    return (datetime.now() - timedelta(days=days_ago)).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 通道1
# ---------------------------------------------------------------------------

def test_tags_fallback(tmp_path):
    nodes = _ids([
        _ep("拆炸弹的初遇", sig=0.9, tags=["炸弹", "初遇"]),
        _ep("甜品店约会", sig=0.8, tags=["甜品", "约会"]),
        _ep("除草日常", sig=0.7, tags=["杂草"]),
    ])
    st = _store(tmp_path, nodes)
    out = recall_subgraph(st, query="老师陪我拆炸弹的那天", k_sim=5,
                          n_precious=0, n_random=0)
    assert [n.id for n in out] == ["m0001"]          # 只有 tags 命中的


def test_embed_fn_top_k(tmp_path):
    # 假后端: 词袋向量（query 命中即相似）
    def embed(texts):
        return [[1.0 if "炸弹" in t else 0.0,
                 1.0 if "甜品" in t else 0.0,
                 1.0 if "杂草" in t else 0.0] for t in texts]
    nodes = _ids([
        _ep("拆炸弹的初遇", tags=["炸弹"]),
        _ep("甜品店约会", tags=["甜品"]),
        _ep("除草日常", tags=["杂草"]),
    ])
    st = _store(tmp_path, nodes)
    out = recall_subgraph(st, query="炸弹", k_sim=2, n_precious=0, n_random=0,
                          embed_fn=embed)
    assert [n.id for n in out] == ["m0001"]          # 命中且 top-k=2 内


def test_embed_fn_failure_degrades(tmp_path):
    """后端抛异常 → 自动降级 tags（宁缺勿错）。"""
    def boom(texts):
        raise RuntimeError("embed backend down")
    nodes = _ids([_ep("拆炸弹的初遇", tags=["炸弹"])])
    st = _store(tmp_path, nodes)
    out = recall_subgraph(st, query="炸弹", n_precious=0, n_random=0,
                          embed_fn=boom)
    assert [n.id for n in out] == ["m0001"]


# ---------------------------------------------------------------------------
# 通道2（珍贵保底, 含出厂 facts——D1）
# ---------------------------------------------------------------------------

def test_precious_floor_and_facts(tmp_path):
    nodes = _ids([
        _ep("日常闲聊", sig=0.5),
        _ep("天台夜谈", sig=0.9),
        make_node("fact", content="拆炸弹的出厂经历", epistemic="canon_fact",
                  source="experience", source_key="self.regular.1", significance=0.9),
    ])
    st = _store(tmp_path, nodes)
    out = recall_subgraph(st, query="", n_precious=2, n_random=0)
    assert [n.id for n in out] == ["m0002", "m0003"]     # sig 降序, fact 同权参与
    assert out[1].kind == "fact"


def test_precious_only_complements_channel1(tmp_path):
    nodes = _ids([
        _ep("拆炸弹的初遇", sig=0.95, tags=["炸弹"]),
        _ep("天台夜谈", sig=0.9),
    ])
    st = _store(tmp_path, nodes)
    out = recall_subgraph(st, query="炸弹", n_precious=1, n_random=0)
    # 通道1 已命中 m0001 → 珍贵补位只补 m0002
    assert {n.id for n in out} == {"m0001", "m0002"}


# ---------------------------------------------------------------------------
# 通道3（随机摘段）
# ---------------------------------------------------------------------------

def test_random_channel_off_and_on(tmp_path):
    nodes = _ids([_ep("a", sig=0.5, ts=_now_iso(1)),
                  _ep("b", sig=0.5, ts=_now_iso(2)),
                  _ep("c", sig=0.5, ts=_now_iso(3))])
    st = _store(tmp_path, nodes)
    assert recall_subgraph(st, query="", n_precious=0, n_random=0) == []
    out = recall_subgraph(st, query="", n_precious=0, n_random=1,
                          rng=random.Random(42))
    assert len(out) == 1 and out[0].id in {"m0001", "m0002", "m0003"}


def test_random_channel_precious_branch_deterministic(tmp_path):
    """rng 固定种子 → 结果可复现（测试确定性）。"""
    nodes = _ids([_ep(f"e{i}", sig=0.5 + i * 0.1, ts=_now_iso(i + 1))
                  for i in range(6)])
    st = _store(tmp_path, nodes)
    a = [n.id for n in recall_subgraph(st, query="", n_precious=0, n_random=2,
                                       rng=random.Random(7))]
    b = [n.id for n in recall_subgraph(st, query="", n_precious=0, n_random=2,
                                       rng=random.Random(7))]
    assert a == b and 1 <= len(a) <= 2   # 两次抽取可能抽中同一节点（去重后 ≥1）


# ---------------------------------------------------------------------------
# 一跳扩展（links ∪ contradictions——D5）
# ---------------------------------------------------------------------------

def test_hop_expands_links_and_contradictions(tmp_path):
    nodes = _ids([
        _ep("拆炸弹的初遇", sig=0.9, tags=["炸弹"],
            links=["m0002"], contradictions=["m0003"]),
        _ep("信任的支撑", sig=0.7),
        _ep("和初遇矛盾的记忆", sig=0.6),
        _ep("无关的日常", sig=0.4),
    ])
    st = _store(tmp_path, nodes)
    out = recall_subgraph(st, query="炸弹", n_precious=0, n_random=0)
    ids = {n.id for n in out}
    assert "m0002" in ids and "m0003" in ids        # 一跳带出 link + contradiction
    assert "m0004" not in ids                       # 二跳外的不到


def test_cap_enforced(tmp_path):
    nodes = _ids([_ep(f"e{i}", sig=0.9 - i * 0.01, tags=["炸弹"]) for i in range(20)])
    st = _store(tmp_path, nodes)
    out = recall_subgraph(st, query="炸弹", k_sim=20, n_precious=2, n_random=0,
                          cap=15)
    assert len(out) <= 15


# ---------------------------------------------------------------------------
# 边界
# ---------------------------------------------------------------------------

def test_empty_store(tmp_path):
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    assert recall_subgraph(st, query="任何东西") == []


def test_query_empty_skips_channel1(tmp_path):
    nodes = _ids([_ep("有标签的", sig=0.9, tags=["炸弹"])])
    st = _store(tmp_path, nodes)
    assert recall_subgraph(st, query="", n_precious=0, n_random=0) == []


def test_result_sorted_by_significance(tmp_path):
    nodes = _ids([_ep("低", sig=0.3, tags=["x"]), _ep("高", sig=0.95, tags=["x"]),
                  _ep("中", sig=0.6, tags=["x"])])
    st = _store(tmp_path, nodes)
    out = recall_subgraph(st, query="x", n_precious=0, n_random=0)
    assert [n.id for n in out] == ["m0002", "m0003", "m0001"]
