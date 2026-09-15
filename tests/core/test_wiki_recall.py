"""recall.py 召回测试（AGENT_BRAIN.md §6 / M4 + 板块5 候选推荐）。"""
import random
from datetime import datetime, timedelta

from core.brain.wiki_v2 import BrainNode, WikiStoreV2, make_node
from core.brain.wiki_v2.recall import (
    recommend_candidates,
    recall_subgraph,
)


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
# 通道2（珍贵保底——episode 同权参与, fact 已退役）
# ---------------------------------------------------------------------------

def test_precious_floor_and_episodes(tmp_path):
    nodes = _ids([
        _ep("日常闲聊", sig=0.5),
        _ep("天台夜谈", sig=0.9),
        make_node("episode", narration="拆炸弹的出厂经历", source="experience",
                  source_key="self.regular.1", significance=0.9),
    ])
    st = _store(tmp_path, nodes)
    out = recall_subgraph(st, query="", n_precious=2, n_random=0)
    assert [n.id for n in out] == ["m0002", "m0003"]     # sig 降序, 出厂 episode 同权
    assert out[1].kind == "episode"


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


# ============================================================================
# 板块5: recommend_candidates（Round B 候选推荐）
# ============================================================================

def _cog_store(tmp_path) -> WikiStoreV2:
    """稳定认知库: 猫粮约定 belief + 摸鱼 experience + 出厂 episode（不应被候选）。

    id: episode m0001 / belief m0002 / experience e0001 / 出厂 episode m0003。
    """
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(make_node("episode", narration="天台旧事", event_seq=[1]))
    st.add(make_node("belief", content="老师会记得给猫带猫粮的约定", subject="老师与我的约定",
                     epistemic="inferred_belief", significance=0.9, tags=["猫", "约定"],
                     links=["m0001"], event_seq=[1]))
    st.add(make_node("experience", pattern="老师总说摸鱼", subject="sensei",
                     significance=0.85, tags=["摸鱼"], links=["m0001"], event_seq=[1]))
    st.add(make_node("episode", narration="遥香喜欢杂草", source="experience",
                     source_key="self.regular.1"))
    return st


def test_candidates_kind_filter_and_embed_path(tmp_path):
    st = _cog_store(tmp_path)

    # 确定性假 embed: 文本含"猫"→ [1,0], 含"摸鱼"→ [0,1], 其他 → [0.2,0.2]
    def fake_embed(texts):
        out = []
        for t in texts:
            if "猫" in t:
                out.append([1.0, 0.0])
            elif "摸鱼" in t:
                out.append([0.0, 1.0])
            else:
                out.append([0.2, 0.2])
        return out

    cands = recommend_candidates(st, "老师带着猫粮来喂猫", embed_fn=fake_embed)
    assert [n.id for n, _ in cands] == ["m0002"]       # 只有 belief（episode 不参与）
    assert cands[0][1] > 0.9                           # 相似度原样给出（**不判档**）

    cands2 = recommend_candidates(st, "老师又说摸鱼", embed_fn=fake_embed)
    assert cands2[0][0].id == "e0001" and cands2[0][1] > 0.9


def test_candidates_are_hints_not_gates(tmp_path):
    """★ T17: **候选只是提示** —— 不返回任何"档位"、不携带判定。

    `CAND_HIGH`/`CAND_MED` 已删（Q11/Q31/Q32）: 阈值从未标定过、实测两模型下
    候选 6/6 全越线 → 结构强制把"全部分侧面"判成"同一件事" → 新认知长不出来。
    这里钉的是**返回值形态**: 只有 `(node, score)`, 分值连续、不夹带档位。
    """
    st = _cog_store(tmp_path)

    def fake_embed(texts):
        return [[1.0, 0.0] if "猫" in t else [0.0, 1.0] if "摸鱼" in t
                else [0.6, 0.6] for t in texts]

    # 无关 query 也能拿到候选（相似度低而已）——没有阈值拦它
    out = recommend_candidates(st, "今天天气不错但我要说猫", embed_fn=fake_embed)
    assert out, "候选提示不该被阈值拦掉"
    assert isinstance(out[0][1], float)
    # 模块里不再有任何 CAND_* 阈值常量
    import core.brain.wiki_v2.recall as R
    assert not hasattr(R, "CAND_HIGH") and not hasattr(R, "CAND_MED")
    # 配置面也没有
    from core.brain.wiki_v2 import recall_config as rc
    assert "cand_high" not in rc.DEFAULTS and "cand_med" not in rc.DEFAULTS
    assert "accept_hit_rate" not in rc.DEFAULTS
    # 契约层不再有结构强制参数
    import inspect
    from contract.digest_registry import digest_registry
    sig = inspect.signature(digest_registry.parse_round_b)
    assert "must_touch" not in sig.parameters, "结构强制未删干净"
    print("    cand_high 全删: 无阈值常量 / 无配置项 / parse_round_b 无 must_touch")


def test_candidates_keyword_fallback(tmp_path):
    st = _cog_store(tmp_path)
    # tags 命中（检索导向最强信号）
    out = recommend_candidates(st, "今天又和老师去喂猫了", embed_fn=None)
    assert out and out[0][0].id == "m0002"
    assert out[0][1] >= 0.6
    # subject 点名 → 高分
    out2 = recommend_candidates(st, "老师与我的约定我记在心里", embed_fn=None)
    assert out2 and out2[0][0].id == "m0002" and out2[0][1] == 0.85
    # 无关 query → 无候选（保守）
    assert recommend_candidates(st, "今天天气不错适合散步", embed_fn=None) == []


def test_candidates_empty_and_cap(tmp_path):
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    assert recommend_candidates(st, "任何", embed_fn=None) == []     # 空库
    assert recommend_candidates(st, "", embed_fn=None) == []         # 空 query


def test_candidates_backend_failure_degrades_to_keyword(tmp_path):
    st = _cog_store(tmp_path)

    def broken(texts):
        raise RuntimeError("vector db down")

    out = recommend_candidates(st, "今天又和老师去喂猫了", embed_fn=broken)
    assert out and out[0][0].id == "m0002"             # 降级到关键词, 不炸
