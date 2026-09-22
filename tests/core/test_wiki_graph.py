# -*- coding: utf-8 -*-
"""`graph.py` 的测试（DESIGN_GRAPH_V4 §2.1 · **G1 + G4**）。

判据 = §2.1 那张"六类查询"的表 + 推断表 —— **够不够用**就是这几条断言。
真机形状（world1/haruka 的 5 个点, 盘上还是旧字段名）单列一条, 免得推断只在
手工数据上成立。

⚠️ G4 起 `infer_edges` 吃的是**点表的原始行**（dict），不是 `BrainNode` ——
`links`/`contradictions` 字段已从节点上删除, 自举活在文件格式层。
"""
import json
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from core.brain.wiki_v2 import WikiStoreV2                      # noqa: E402
from core.brain.wiki_v2.graph import (                          # noqa: E402
    REL_ABOUT,
    REL_CONTRADICTS,
    REL_FORMED_BY,
    REL_SUPPORTS,
    REL_UNKNOWN,
    Edge,
    Graph,
    classify_pair,
    graph_of,
    infer_edges,
    iter_edges,
)
from core.brain.wiki_v2.nodes import BrainNode                  # noqa: E402


def _row(nid: str, kind: str, *, links=(), contradictions=(), ts="") -> dict:
    """旧档点表的**一行**（自举的输入形态）。"""
    d: dict = {"id": nid, "kind": kind}
    if links:
        d["links"] = list(links)
    if contradictions:
        d["contradictions"] = list(contradictions)
    if ts:
        d["ts"] = ts
    return d


def _node(nid: str, kind: str) -> BrainNode:
    """直接构造节点并钉 id（**绕开 `from_dict`** —— 它把不认识的 kind 归一成 episode,
    而 `entity`/`promise` 今天还不在 `KINDS` 里, 正是车道查询要提前验形状的东西）。"""
    n = BrainNode()
    n.id, n.kind = nid, kind
    return n


# ---------------------------------------------------------------------------
# 推断表
# ---------------------------------------------------------------------------

def test_infer_types_and_direction():
    """`episode → 认知` = supports（方向由 kind 定）; 判不出的对 → unknown。"""
    rows = [
        _row("m0001", "episode", links=["m0003"]),           # ↔ belief
        _row("m0003", "belief", links=["m0001", "m0004"]),
        _row("m0004", "belief"),                             # belief↔belief: 单边也算
        _row("m0002", "episode", links=["e0001"]),           # ↔ experience（押 §9-3）
        _row("e0001", "experience", links=["m0002"]),
    ]
    got = {(e.rel, e.src, e.dst) for e in infer_edges(rows)}
    assert got == {
        (REL_SUPPORTS, "m0001", "m0003"),       # 经历 → 认知（不是反向）
        (REL_UNKNOWN, "m0003", "m0004"),        # 谁取代谁判不出 → **不猜**
        (REL_SUPPORTS, "m0002", "e0001"),
        # ⚠️ 无向边只出一条: links 双向存, 不去重会翻倍
    }
    assert len(infer_edges(rows)) == 3


def test_infer_contradictions_is_separate_and_canonical():
    """`contradictions` 规范化到 id 小的那头; 与 `links` **互不吞并**。"""
    rows = [
        _row("m0002", "belief", links=["m0001"], contradictions=["m0001"]),
        _row("m0001", "belief", links=["m0002"], contradictions=["m0002"]),
    ]
    assert {(e.rel, e.src, e.dst) for e in infer_edges(rows)} == {
        (REL_UNKNOWN, "m0001", "m0002"),        # links 那一条
        (REL_CONTRADICTS, "m0001", "m0002"),    # contradiction 那一条（同方向）
    }


def test_infer_keeps_raw_kind_without_coercion():
    """自举按**盘上的 kind 字符串**判, 不做 `KINDS` 归一。

    证据: `entity` 今天还不在 `KINDS` 里 —— 若自举顺手归一成 episode, 这条边会变成
    `supports`; 现在它是 `about`（与 `entity` 真落地那天的行为一致）。
    """
    rows = [_row("m0010", "belief", links=["x0000"]), _row("x0000", "entity")]
    assert [(e.rel, e.src, e.dst) for e in infer_edges(rows)] == [
        (REL_ABOUT, "m0010", "x0000")]


# ---------------------------------------------------------------------------
# §2.1 的六类查询
# ---------------------------------------------------------------------------

def test_entity_lane_and_unattributed():
    """查询 1/5: entity 车道 = `inc[E]`; **未归属清单必须排掉 entity 自己**。"""
    # 分类表: 方向恒为"节点 → entity"（entity 永远当 dst, 两种入参顺序都对）
    assert classify_pair("belief", "entity", "m0010", "x0000") == \
        (REL_ABOUT, "m0010", "x0000")
    assert classify_pair("entity", "episode", "x0000", "m0011") == \
        (REL_ABOUT, "m0011", "x0000")
    nodes = [_node("x0000", "entity"), _node("m0010", "belief"),
             _node("m0011", "episode"), _node("m0012", "belief")]
    g = Graph(edges=[Edge(REL_ABOUT, "m0010", "x0000"),
                     Edge(REL_ABOUT, "m0011", "x0000")], nodes=nodes)
    assert g.lane("x0000") == ["m0010", "m0011"]
    assert g.beliefs_of("x0000") == ["m0010"]
    assert g.kind_of("x0000") == "entity"
    # ⚠️ 这条就是 2026-09-21 复核 §2.1 时发现的那个坑: 不排 entity 的话
    # 每个 entity 都会冒充"未归属"（它永远不会是 about 的 src）
    assert set(g.unattributed()) == {"m0012"}       # 有 about 边的两条**不算**未归属


def test_promise_and_support_queries():
    """查询 2/3: 支撑来源（`sources` 侧）+ 承诺的共有经历与双方。"""
    nodes = [_node("p0001", "promise"), _node("x0000", "entity"),
             _node("x0001", "entity"), _node("m0020", "episode"),
             _node("m0021", "episode"), _node("m0022", "belief")]
    g = Graph.from_edges([
        {"rel": "from", "src": "p0001", "dst": "x0000", "ts": "2026-09-20T10:00:00"},
        {"rel": "to", "src": "p0001", "dst": "x0001"},
        {"rel": "formed_by", "src": "p0001", "dst": "m0020"},
        {"rel": "formed_by", "src": "p0001", "dst": "m0021"},
        {"rel": REL_SUPPORTS, "src": "p0001", "dst": "m0022"},      # 承诺长出认知
        {"rel": REL_ABOUT, "src": "m0022", "dst": "x0001"},
    ], nodes=nodes)
    assert g.parties("p0001") == ["x0000", "x0001"]
    assert g.formed_by("p0001") == ["m0020", "m0021"]
    assert g.beliefs_of("x0001") == ["m0022"]
    assert g.supporters("m0022") == ["p0001"]           # 不按 kind 过滤（见 docstring）
    assert g.supporters("p0001") == []
    # 边表的磁盘形状（G3 落盘用）: dict ↔ Edge 往返
    e = Edge(rel=REL_FORMED_BY, src="p0001", dst="m0020", ts="2026-09-20T10:00:00")
    assert Edge.from_dict(json.loads(json.dumps(e.to_dict()))) == e
    assert Edge.from_dict({"rel": "supports"}) is None          # 坏行 → None, 不抛


def test_neighbors_without_and_dangling():
    """查询 4/6 + 读侧宽容: 指向不存在的点 → 保留但 `dangling()` 可见。"""
    rows = [_row("m0003", "belief", links=["m0001", "m0004"]),
            _row("m0001", "episode"), _row("m0004", "episode")]
    nodes = [_node("m0003", "belief"), _node("m0001", "episode"),
             _node("m0004", "episode")]
    g = Graph.from_rows(rows, nodes)
    assert g.neighbors("m0003") == ["m0001", "m0004"]           # out + inc, 去重保序
    assert g.without("m0003") == []                             # 删节点 = 边表过滤一遍
    # 边方向是"经历 → 认知": 去掉 m0001 后剩下 m0004 → m0003
    assert [(e.src, e.dst) for e in g.without("m0001")] == [("m0004", "m0003")]
    assert g.dangling() == []

    bad = Graph.from_edges([{"rel": REL_SUPPORTS, "src": "m0001", "dst": "m9999"}],
                           nodes=[_node("m0001", "episode")])
    assert len(bad.edges) == 1 and bad.dangling() == bad.edges  # 宽容读, 但可见


def test_bad_rows_are_skipped():
    """坏行/坏项不抛（宁缺勿错）: 非 dict / 缺 id / 自环 / 对端不存在 / 坏数组。"""
    rows = [None, "nope", {"kind": "episode"}, _row("m0001", "episode"),
            _row("m0001", "episode", links=["m0001", "m9999", 7]),
            {"id": "m0002", "kind": "belief", "links": "not-a-list"}]
    assert infer_edges(rows) == []


# ---------------------------------------------------------------------------
# 真机形状（盘上还是旧字段名）
# ---------------------------------------------------------------------------

_REAL_LINES = [
    {"id": "m0001", "kind": "episode", "significance": 0.85,
     "epistemic": "observed_fact", "ts": "2026-09-20T14:58:46+08:00",
     "links": ["m0003"], "narration": "杂草屋的环境调研", "segment_id": "seg-30"},
    {"id": "m0002", "kind": "episode", "significance": 0.55,
     "epistemic": "observed_fact", "ts": "2026-09-20T14:58:46+08:00",
     "links": ["e0001"], "narration": "明天的复印件约定"},
    {"id": "m0003", "kind": "belief", "significance": 0.95,
     "epistemic": "inferred_belief", "ts": "2026-09-21T22:16:15+08:00",
     "links": ["m0001", "m0004"], "content": "老师接纳了我",
     "subject": "sensei对我的接纳与珍视", "history": [{"episode_id": "m0004"}]},
    {"id": "m0004", "kind": "episode", "significance": 0.9,
     "epistemic": "observed_fact", "ts": "2026-09-21T22:16:15+08:00",
     "links": ["m0003"], "narration": "和老师的第一顿高级料理"},
    {"id": "e0001", "kind": "experience", "significance": 0.5,
     "epistemic": "observed_fact", "ts": "2026-09-20T14:58:46+08:00",
     "links": ["m0002"], "pattern": "先说好意再道歉", "subject": "我表达善意时的习惯"},
]


def _real_store(tmp_path) -> WikiStoreV2:
    """真机 haruka 的 5 个点, 盘上照抄旧字段名（narration/content/pattern + links）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")
    st.path.parent.mkdir(parents=True, exist_ok=True)
    st.path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in _REAL_LINES),
                       encoding="utf-8")
    return WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")


def test_real_shaped_store(tmp_path):
    """真机形状 → 3 条 supports / 0 条 about / 0 条 unknown（§2.1 的验收线）。"""
    st = _real_store(tmp_path)
    assert st.get("m0001").text == "杂草屋的环境调研"       # 旧字段名兼容读
    g = graph_of(st)
    assert g.stats() == {"nodes": 5, "edges": 3,
                         "by_rel": {REL_SUPPORTS: 3},
                         "unknown": 0, "about": 0, "dangling": 0}
    assert g.supporters("m0003") == ["m0001", "m0004"]      # 认知的两个来源
    assert g.supporters("e0001") == ["m0002"]
    # entity 今天不存在 ⇒ 车道恒空（G1 只验形状）; 未归属 = 全部非 entity 节点
    assert g.lane("x0000") == []
    assert set(g.unattributed()) == {"m0001", "m0002", "m0003", "m0004", "e0001"}
    assert len(list(iter_edges(st, rel=REL_SUPPORTS))) == 3
    assert list(iter_edges(st, rel=REL_ABOUT)) == []
