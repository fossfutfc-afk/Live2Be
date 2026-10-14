"""`graph.py` 的测试（DESIGN_GRAPH_V4 §2.1 · **G1 + G4**）。

判据 = §2.1 那张"六类查询"的表 + 推断表 —— **够不够用**就是这几条断言。
真机形状（world1/haruka 的 5 个点, 盘上还是旧字段名）单列一条, 免得推断只在
手工数据上成立。

⚠️ G4 起 `infer_edges` 吃的是**点表的原始行**（dict），不是 `BrainNode` ——
`links`/`contradictions` 字段已从节点上删除, 自举活在文件格式层。
"""
import json
import pathlib
import sys

import pytest

from core.brain import WikiStoreV2
from core.brain.graph import (
    REL_ABOUT,
    REL_CONTRADICTS,
    REL_SUPPORTS,
    REL_UNKNOWN,
    Edge,
    Graph,
    classify_pair,
    graph_of,
    infer_edges,
    iter_edges,
)
from core.brain.nodes import BrainNode


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
    而 `entity`/`group` 正是车道查询要提前验形状的东西）。"""
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
        _row("e0001", "profile", links=["m0002"]),
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

def test_default_faces_fill_the_lane_but_never_the_graph():
    """⭐ **归属的兜底**（2026-10-14 用户裁"R1 的 `entity` 留空默认 self+sensei"）。

    四条判据（缺一条就会把"归属"这个信号弄坏）:
      ① 没写归属的 `episode` ⇒ **算进** self / sensei 的车道（这才是"默认"）;
      ② **明确写了别人**的 ⇒ **不算**（写了谁就只是谁 —— 否则车道退化成全集）;
      ③ **那个对象不存在** ⇒ 车道仍空（没有这个对象就谈不上它的车道）;
      ④ ⛔ **一条边都不落**: 它是**读侧口径**, `about` 边表不许因为默认而变长
         （真机算过: 落边 = +46 条常数边, 且图里再也分不出"明确说"与"默认"）。
     顺便钉住 `belief` 那一行**还没加**（L2 的默认随碰撞那一件落）。
    """
    from core.brain.entities import SELF_ID, SENSEI_ID
    from core.brain.graph import DEFAULT_FACES, default_faces

    # ⚠️ `graph.py` 零项目内 import ⇒ 保留号只能写字面量 —— 这条用例钉住"两处不许漂"
    assert DEFAULT_FACES["episode"] == (SELF_ID, SENSEI_ID), DEFAULT_FACES
    assert default_faces("episode") == (SELF_ID, SENSEI_ID)
    assert default_faces("belief") == (), "belief 那一行还没加（L2 落地时再加）"
    assert default_faces("experience") == ()

    nodes = [_node("x0000", "entity"), _node("x0001", "entity"),
             _node("m0010", "episode"),                       # 没写归属 ⇒ 默认面
             _node("m0011", "episode"),                       # 明确写了小玉 ⇒ 不兜底
             _node("m0012", "episode"),                       # 明确写了老师 ⇒ 直连
             _node("m0013", "belief"),                        # belief 没有默认面
             _node("x0002", "entity")]
    g = Graph(edges=[Edge(REL_ABOUT, "m0011", "x0002"),
                     Edge(REL_ABOUT, "m0012", "x0001")], nodes=nodes)

    # ① 默认面 + 明确的都在; ② 写了小玉的不在（self 那条没有明确的, 只剩默认面）
    assert g.lane(SELF_ID) == ["m0010"], g.lane(SELF_ID)
    assert g.lane(SENSEI_ID) == ["m0012", "m0010"], g.lane(SENSEI_ID)
    assert g.lane("x0002") == ["m0011"], "非保留号照旧**只认明确写过的**（筛子还在）"
    # ③ 对象不在 ⇒ 不兜底（旧档/单测里 x0000 常常不存在）
    g2 = Graph(edges=[Edge(REL_ABOUT, "m0011", "x0002")],
               nodes=[n for n in nodes if n.id not in (SELF_ID, SENSEI_ID)])
    assert g2.lane(SELF_ID) == [], g2.lane(SELF_ID)
    # kind 过滤照旧（belief 没有默认面 ⇒ 只剩明确的）
    assert g.lane(SELF_ID, "belief") == []
    # ④ 一条边都没落
    assert [e.rel for e in g.edges] == [REL_ABOUT, REL_ABOUT]
    # `unattributed` 的语义变了: 它们不是"没归属", 而是"没被明确写过"
    assert set(g.unattributed()) == {"m0010", "m0013"}


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


def test_support_queries():
    """查询 2: 支撑来源（`sources` 侧）**不按 kind 过滤**。

    ⏸ 原 `test_promise_and_support_queries` 还验 `parties` / `formed_by` 两条查询 ——
    它们与 `from`/`to`/`formed_by` 三条边 2026-09-29 随 promise 退图一起删掉
    （判据: 起点 kind 没了 ⇒ 那些边永远不会有走法）。
    """
    nodes = [_node("x0001", "entity"), _node("m0020", "episode"),
             _node("m0021", "episode"), _node("m0022", "belief")]
    g = Graph.from_edges([
        {"rel": REL_SUPPORTS, "src": "m0020", "dst": "m0022"},      # 经历长出认知
        {"rel": REL_SUPPORTS, "src": "m0021", "dst": "m0022"},
        {"rel": REL_ABOUT, "src": "m0022", "dst": "x0001"},
    ], nodes=nodes)
    assert g.beliefs_of("x0001") == ["m0022"]
    assert g.supporters("m0022") == ["m0020", "m0021"]
    assert g.supporters("m0020") == []
    # 边表的磁盘形状（G3 落盘用）: dict ↔ Edge 往返
    e = Edge(rel=REL_SUPPORTS, src="m0020", dst="m0022", ts="2026-09-20T10:00:00")
    assert Edge.from_dict(json.loads(json.dumps(e.to_dict()))) == e
    assert Edge.from_dict({"rel": "supports"}) is None          # 坏行 → None, 不抛
    # ⏸ 旧档里的 promise 专属边**仍然读得进**（`from_dict` 不校验 rel 名单）
    legacy = Edge.from_dict({"rel": "formed_by", "src": "p0001", "dst": "m0020"})
    assert legacy is not None and legacy.rel == "formed_by"


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
    {"id": "e0001", "kind": "profile", "significance": 0.5,
     "epistemic": "observed_fact", "ts": "2026-09-20T14:58:46+08:00",
     "links": ["m0002"], "pattern": "先说好意再道歉", "subject": "我表达善意时的习惯"},
]


def _real_store(tmp_path) -> WikiStoreV2:
    """真机 haruka 的 5 个点, 盘上照抄旧字段名（narration/content/pattern + links +
    已退役的 `epistemic`）—— 旧键读得进、不抛, 也不进新写的行。"""
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


# ---------------------------------------------------------------------------
# 边表词汇量（2026-09-25 用户裁决: 删 `source`；2026-09-29 N1a: 加 `akin`）
# ---------------------------------------------------------------------------

def test_edge_vocabulary_is_the_six():
    """⭐ 边 = **6 条**（删 `source` · 加 `akin`(N1a) · 加 `member_of`(N1b) ·
    删 `formed_by`/`from`/`to`(2026-09-29, promise 退图)）。

    `source` 唯一的形状是 `fact → episode`，而 **`fact` 这个 kind 早在 2026-09-02 就退役**了
    （`nodes.KINDS` 里没有它 ⇒ 节点根本建不出来）⇒ 那是一条**永远不会有走法**的边。
    §2.2 的判据 = "边的存在理由 = 有一条能走的路"; 而 `contradicts` / `evolved_from`
    今天虽零写者, 但 kind 都在、**将来会有**走法 —— "还没有"与"永远不会有"是两件事。
    ⭐ 同理: `from`/`to`/`formed_by` 的唯一起点 kind 是 `promise`, 而它退出了图
    （用户 2026-09-29 裁决）⇒ 三条边一起删（真机本来也是 **0 条**）。

    `akin`（N1a）：她发现"这两条是同一类事" ⇒ **`noticed` 记录行的落点**。
    `member_of`（N1b）：**L2 判定"它属于这一类"** ⇒ 与 `akin` 是**输入与输出**，不能合并。
    """
    from core.brain import graph as G

    assert set(G.RELS) == {"about", "supports", "contradicts",
                           "evolved_from", "akin", "member_of"}
    assert len(G.RELS) == 6 and len(set(G.RELS)) == 6
    assert not hasattr(G, "REL_SOURCE"), "source 已删（连常量都不留）"
    for gone in ("REL_FORMED_BY", "REL_FROM", "REL_TO"):
        assert not hasattr(G, gone), f"{gone} 已随 promise 退图删掉（常量也不留）"


def test_member_of_is_directed_and_experience_is_aboutable():
    """`member_of` **有向**（不进 `SYMMETRIC_RELS`）；`experience` 进 `_ABOUTABLE`（经验可归属 entity）。"""
    from core.brain import graph as G

    assert G.REL_MEMBER_OF == "member_of"
    assert "member_of" not in G.SYMMETRIC_RELS
    # 有向 ⇒ 原样返回（不被"顺手"规范化）
    assert G.canonical_for("member_of", "g0001", "m0001") == ("g0001", "m0001")
    # 群 → entity 判 about（先开接口; 今天零写者, 要 L2 才写）
    assert classify_pair("entity", "experience", "x0001", "g0001") == (REL_ABOUT, "g0001", "x0001")
    assert classify_pair("experience", "entity", "g0001", "x0001") == (REL_ABOUT, "g0001", "x0001")
    # ⚠️ 经验**不是认知** —— episode ↔ experience 判不出 supports（那是 member_of 的活, 写路径显式写）
    assert classify_pair("episode", "experience", "m0001", "g0001") == \
        (REL_UNKNOWN, "g0001", "m0001")


def test_symmetric_rels_are_one_list_and_canonical_for_obeys_it():
    """⭐ 对称性**只有一份清单**（`SYMMETRIC_RELS`），`canonical_for` 是它的唯一实现。

    为什么要有这条用例: 对称性原来**只活在自举的调用方**（按"来自 `links` 还是
    `contradictions`"传 `symmetric=`），而 `store.add_edge` 完全不知道 ⇒
    `akin(B, A)` 与 `akin(A, B)` 会被当成两条边各写一条。
    """
    from core.brain import graph as G

    assert G.SYMMETRIC_RELS == frozenset({"contradicts", "akin"})
    # 对称 → 端点规范化
    assert G.canonical_for("akin", "m0009", "m0003") == ("m0003", "m0009")
    assert G.canonical_for("contradicts", "m0009", "m0003") == ("m0003", "m0009")
    # ⚠️ 有向边**原样返回** —— 顺手规范化会悄悄改掉方向语义（member_of / supports）
    assert G.canonical_for("member_of", "m0009", "g0001") == ("m0009", "g0001")
    assert G.canonical_for("supports", "m0009", "m0003") == ("m0009", "m0003")
    # 幂等
    assert G.canonical_for("akin", "m0003", "m0009") == ("m0003", "m0009")


def test_akin_is_deliberately_not_inferred():
    """⭐ `episode ↔ episode` **不进推断表**（有意为之, 别"修"）。

    旧档的 `links` 只声称"这两条**挨着 / 相关**"，而 `akin` 声称"**同类**" —— 那是**判断**。
    推断表替旧数据做判断就是猜（与"`belief↔belief` 不判 `evolved_from`"同一条纪律）。
    ⇒ 旧档的 `episode↔episode` 继续落 `unknown`，在 `stats()["unknown"]` 里如实可见。
    """
    assert classify_pair("episode", "episode", "m0001", "m0002") == \
        (REL_UNKNOWN, "m0001", "m0002")
    assert classify_pair("belief", "belief", "m0003", "m0008") == \
        (REL_UNKNOWN, "m0003", "m0008")


def test_fact_is_not_aboutable():
    """`fact` 从 `_ABOUTABLE` 摘掉 —— 那是**死配置**（kind 已退役, 白名单永远匹配不到）。

    行为判据（不只看表）: 一个 fact 与 entity 的旧档对 → `unknown`（不猜成 `about`）。
    """
    assert classify_pair("entity", "fact", "x0001", "m0001") == (REL_UNKNOWN, "m0001", "x0001")
    assert classify_pair("fact", "entity", "m0001", "x0001") == (REL_UNKNOWN, "m0001", "x0001")
    # 同形状的活 kind 照旧判 about（防"顺手把整条路也关了"）
    assert classify_pair("entity", "profile", "x0001", "e0001") == (REL_ABOUT, "e0001", "x0001")
