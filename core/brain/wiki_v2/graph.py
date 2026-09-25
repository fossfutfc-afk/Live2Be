# -*- coding: utf-8 -*-
"""graph.py — 类型化边与邻接索引（`DESIGN_GRAPH_V4.md` §2 / §2.1 · **G1: 只读层**）。

G1 的边界（写死, 免得这一步膨胀）:
    · **只读**: 不改节点、不落盘、不建文件; 现有代码**零改动**（连 `__init__.py`
      都不加导出——本模块按全路径 import, 免得动 API 面快照夹具）
    · **纯 stdlib**
    · 边的真实来源（`soul/edges.jsonl`）是 **G3** ⇒ 本层从今天那根无类型的
      `links` / `contradictions` **推断**出类型与方向（`infer_edges`）

为什么先写这一层（§2.1 的验收口径）: 把"§2.1 那六类查询够不够用"**零风险**地验掉
——够用再谈落盘。推断表见 `classify_pair`。

⚠️ 今天**还没有 `entity`**（v4 §1 的新 kind 未落地）⇒ 真机上推断产出 **0 条 `about`**;
entity 车道的查询在 G1 阶段只能验形状（测试里用直接构造的 entity 节点验）。

⚠️ `REL_UNKNOWN` 是**推断层专有**的兜底, **不属于** §2 的八种 rel。为什么发它而不是
丢掉: 丢掉会让 1-hop 扩展比今天的 `links` **更窄**（行为回退）; 发出来则"连接关系"
与今天等价, 而"类型判不出来"这件事在 `stats()["unknown"]` 里可见 —— G3 落盘后
写路径总是知道 rel, 那个计数应当归零, **它就是那条验收线**。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

# ---------------------------------------------------------------------------
# 边类型（`DESIGN_GRAPH_V4.md` §2 的八种）
# ---------------------------------------------------------------------------

REL_ABOUT = "about"                  # belief/episode/experience/promise → entity（归属）
REL_SUPPORTS = "supports"            # episode → belief · promise → belief（支撑）
REL_FORMED_BY = "formed_by"          # promise → episode × N（这条承诺怎么一次次说定）
REL_CONTRADICTS = "contradicts"      # 同层之间（她后来发现不对; **对称**）
REL_EVOLVED_FROM = "evolved_from"    # belief → belief（新看法取代旧的）
REL_FROM = "from"                    # promise → entity（承诺方）
REL_TO = "to"                        # promise → entity（被承诺方）

#: 全部合法 rel（**唯一清单**; 新增边类型只改这里 + `classify_pair` 的判据）
#: ⭐ **7 条**（2026-09-25 删 `source`）: 它唯一的形状是 `fact → episode`，而 **`fact`
#: 这个 kind 早在 2026-09-02 就退役了**（`nodes.KINDS` 里没有它 ⇒ 建都建不出来）
#: ⇒ 那是一条**永远不会有走法**的边（§2.2 的判据: 没走法的边是装饰）。用户裁决删。
#: （`contradicts` / `evolved_from` 今天同样零写者，但它们的 kind 都在、将来会有走法
#: —— "还没有走法"与"永远不会有走法"是两件事。）
#: ⚠️ 盘上若真有旧 `source` 行，**照旧读得进**（`Edge.from_dict` 不校验 rel 名单），
#: 只是不再有任何写者/分类器产生它。
RELS: tuple[str, ...] = (REL_ABOUT, REL_SUPPORTS, REL_FORMED_BY, REL_CONTRADICTS,
                         REL_EVOLVED_FROM, REL_FROM, REL_TO)

#: ⚠️ 推断层兜底 —— **不在 `RELS` 里**（见模块 docstring 的第二条警告）
REL_UNKNOWN = "unknown"

#: v4 §1 的 entity（今天不在 `nodes.KINDS` 里; G1 只认 kind 字符串, 不碰那张表）
KIND_ENTITY = "entity"

#: 会挂 `about` 的 kind（§2: belief/episode/experience/promise）。
#: ⚠️ `fact` 2026-09-25 摘掉 —— 它是**死配置**（kind 已退役 ⇒ 这条白名单永远匹配不到
#: 任何节点）。`experience` **留着**，但理由换了: 不再是"押 §9-3 的合并预案"（那条
#: 2026-09-25 由用户关掉），而是**它本身就是"关于老师的事"** ⇒ 该被 `about → sensei`
#: 指着（§9-8）。
_ABOUTABLE = ("belief", "episode", "experience", "promise")
#: 认知侧（`supports` 的 dst）: 她的结论 + 玩家画像（两者都是"稳定下来的东西"）
_COGNITION = ("belief", "experience")


# ---------------------------------------------------------------------------
# Edge
# ---------------------------------------------------------------------------

@dataclass
class Edge:
    """一条**有向**类型化边（`soul/edges.jsonl` 的一行 = 这一个对象的 JSON）。

    键名用 `src`/`dst` 而不是 `from`/`to` —— 后者是 rel 名, 落到 JSON 键会撞
    Python 关键字（§2.1）。
    """

    rel: str
    src: str
    dst: str
    #: 边的建立时刻。G1 的推断值是**近似**（取两端较晚的那个 `ts`）——今天没有
    #: 边表可查; G3 起由写路径如实落。
    ts: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"rel": self.rel, "src": self.src, "dst": self.dst}
        if self.ts:
            d["ts"] = self.ts
        return d

    def to_json_line(self) -> str:
        """jsonl 一行（紧凑, 中文不转义——与 `BrainNode.to_json_line` 同款）。"""
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_dict(cls, raw: Any) -> "Edge | None":
        """宽松解析（坏行 → None, 不抛; 与 `read_jsonl` 的"旧档宽容读"同一纪律）。"""
        if not isinstance(raw, dict):
            return None
        rel, src, dst = raw.get("rel"), raw.get("src"), raw.get("dst")
        if not all(isinstance(x, str) and x.strip() for x in (rel, src, dst)):
            return None
        ts = raw.get("ts")
        return cls(rel=rel.strip(), src=src.strip(), dst=dst.strip(),
                   ts=ts.strip() if isinstance(ts, str) else "")


# ---------------------------------------------------------------------------
# 推断（G1 的过渡手段; G3 起由 edges.jsonl 取代）
# ---------------------------------------------------------------------------

def infer_edges(rows: Iterable[Any]) -> list[Edge]:
    """从**旧档点表的原始行**推断类型化边（没有边表时的自举）。

    ## 为什么吃"原始行"而不是节点对象（2026-09-21 G4）

    `links` / `contradictions` 两个字段**已从 `BrainNode` 删除** —— 自举因此必须活在
    **文件格式层**: 盘上还留着那些键（旧档），对象上已经没有了。传 `read_jsonl` 的原始
    dict 即可（任何能 `get` 出同样键的对象都行）。

    ## 判据按**盘上的 kind 字符串**，不做 `KINDS` 归一

    这样 `entity` / `promise` 一落地，自举与运行时就自动一致；而按 `KINDS` 归一会把
    "还没进 `KINDS` 的新 kind" 悄悄当成 episode 处理（`from_dict` 的兜底就是那么做的，
    那是**读点**的事，不该污染**读边**）。

    ## 两条去重纪律（都源于"旧档的边是**无向**的"）

    1. `links` / `contradictions` 都是**双向存**的 ⇒ 无向对只出一条边（否则翻倍）。
    2. 对称 rel（`contradicts`）**规范化到 id 小的那头当 src** —— 不规范化的话，
       方向取决于字典遍历顺序，同一份数据能给出两种结果（不可复现）。

    Returns: 边的顺序 = 行序 × 邻接表序（**稳定**；测试与 diff 可依赖）。
    """
    meta: dict[str, tuple[str, str]] = {}            # id → (kind, ts)
    for raw in rows:
        nid = _s(raw, "id")
        if nid and nid not in meta:
            meta[nid] = (_s(raw, "kind"), _s(raw, "ts"))
    out: list[Edge] = []
    # ⚠️ 两个 seen **不能合并**: `links` 与 `contradictions` 是两种关系,
    # 同一对节点可以既是 link 又是 contradiction（旧 `audit` 也是分开查的）。
    seen_link: set[tuple[str, str]] = set()
    seen_contr: set[tuple[str, str]] = set()
    for raw in rows:
        nid = _s(raw, "id")
        if nid not in meta:
            continue
        for other in _list(raw, "links"):
            _emit(out, seen_link, meta, nid, other, symmetric=False)
        for other in _list(raw, "contradictions"):
            _emit(out, seen_contr, meta, nid, other, symmetric=True)
    return out


def _emit(out: list[Edge], seen: set, meta: dict, a: str, b: str, *,
          symmetric: bool) -> None:
    """一对邻接引用 → 至多一条边（不存在的对端 / 自环 / 已发过的对 → 跳过）。"""
    if b not in meta or a == b:
        return
    key = (a, b) if a <= b else (b, a)
    if key in seen:
        return
    seen.add(key)
    if symmetric:
        rel, src, dst = REL_CONTRADICTS, key[0], key[1]
    else:
        rel, src, dst = classify_pair(meta[a][0], meta[b][0], a, b)
    out.append(Edge(rel=rel, src=src, dst=dst, ts=_edge_ts(meta, src, dst)))


def classify_pair(ka: str, kb: str, a_id: str, b_id: str) -> tuple[str, str, str]:
    """两端 kind + 两个 id → `(rel, src, dst)`。**唯一**的分类表。

    两个调用方: ① 旧档**自举**（`infer_edges` 从盘上的 `links`/`contradictions` 推）
    ② 写路径的**旧接口 shim**（`store.add_link` —— 那条窄路径只知道"这两条挨着"，
    不知道 rel）。活路径**一律走 `store.add_edge(rel, …)`**，显式 rel 才有"类型化"。

    ## 推断表（今天能判的只有这些）

    | 对 | 判成 | 依据 |
    |---|---|---|
    | `episode` ↔ `belief` / `experience` | `supports`（**经历 → 认知**） | §2; 方向由 kind 定, 不是猜 |
    | `entity` ↔ `belief` / `episode` / `experience` / `promise` | `about`（**对方 → entity**） | §2 归属 |
    | 其余（`belief`↔`belief`、`belief`↔`experience`、`episode`↔`episode`、`entity`↔`entity`） | `unknown` | **不猜** |

    ⚠️ 为什么 `belief`↔`belief` 不判成 `evolved_from`: 那条边的语义是"**新看法取代
    旧的**"，而一条无向边说不出谁取代谁 —— **猜错方向比不判更贵**（错的方向会让
    "认知演化链"倒着长）。`evolved_from` 只能由知道作者意图的写路径产生。
    """
    if ka == KIND_ENTITY and kb == KIND_ENTITY:
        return REL_UNKNOWN, *canonical_pair(a_id, b_id)
    if ka == KIND_ENTITY or kb == KIND_ENTITY:
        ent_first = ka == KIND_ENTITY
        other = kb if ent_first else ka
        if other in _ABOUTABLE:
            # 方向恒为"节点 → entity"（entity 永远当 dst）
            return ((REL_ABOUT, b_id, a_id) if ent_first
                    else (REL_ABOUT, a_id, b_id))
        return REL_UNKNOWN, *canonical_pair(a_id, b_id)
    if ka == "episode" and kb in _COGNITION:
        return REL_SUPPORTS, a_id, b_id
    if kb == "episode" and ka in _COGNITION:
        return REL_SUPPORTS, b_id, a_id
    return REL_UNKNOWN, *canonical_pair(a_id, b_id)


def canonical_pair(a: str, b: str) -> tuple[str, str]:
    """无方向可言的边 → 端点规范化（id 小的当 src; 保证可复现）。"""
    return (a, b) if a <= b else (b, a)


def _edge_ts(meta: dict, src: str, dst: str) -> str:
    """推断边的时刻 —— 取两端 `ts` 中**较晚**的那个（≈ 这条关系形成的时刻）。

    旧档没有边表, 这是**近似值**; G3 起的写路径如实落。两端都没有 `ts` → `""`
    （哨兵纪律: **不编**一个时刻 —— 与 `render._time_phrase` 同一条）。
    """
    ts = [t for t in (meta.get(src, ("", ""))[1], meta.get(dst, ("", ""))[1]) if t]
    return max(ts) if ts else ""


def _s(raw: Any, key: str) -> str:
    """原始行取值（非 dict / 非 str / 空白 → `""`，绝不抛）。"""
    if not isinstance(raw, dict):
        return ""
    v = raw.get(key)
    return v.strip() if isinstance(v, str) else ""


def _list(raw: Any, key: str) -> list[str]:
    """原始行的字符串数组（坏项逐条丢弃，与 `nodes._str_list` 同纪律）。"""
    if not isinstance(raw, dict):
        return []
    v = raw.get(key)
    if not isinstance(v, list):
        return []
    return [x.strip() for x in v if isinstance(x, str) and x.strip()]


# ---------------------------------------------------------------------------
# Graph（= §2.1 的三个索引 + 六类查询）
# ---------------------------------------------------------------------------

@dataclass
class Graph:
    """一条世界线的边视图。**只读、纯内存**（G1 不落盘）。

    三个索引（§2.1）: `out`（我指向谁）· `inc`（谁指向我）· `by_rel`（所有 about 边）。

    `nodes` 只用来回答"这头是什么 kind"（entity 车道 / 未归属清单都要它）——
    给了就顺带能报 `dangling()`（悬空引用）; 不给则 kind 相关查询返回空。
    """

    edges: list[Edge] = field(default_factory=list)
    nodes: tuple = ()
    out: dict[str, list[Edge]] = field(default_factory=dict, init=False)
    inc: dict[str, list[Edge]] = field(default_factory=dict, init=False)
    by_rel: dict[str, list[Edge]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.edges = list(self.edges)
        self.nodes = tuple(self.nodes)
        self._by_id: dict[str, Any] = {
            n.id: n for n in self.nodes if getattr(n, "id", "")}
        for e in self.edges:
            self.out.setdefault(e.src, []).append(e)
            self.inc.setdefault(e.dst, []).append(e)
            self.by_rel.setdefault(e.rel, []).append(e)

    # ── 构造 ──

    @classmethod
    def from_rows(cls, rows: Iterable[Any], nodes: Iterable[Any] = ()) -> "Graph":
        """**旧档自举入口**: 点表的原始行 → 推断出的边 + 索引。

        （原 `from_nodes` 于 G4 删除 —— 它从 `BrainNode.links` 推断, 而那个字段没了;
        自举改在**文件格式层**做, 见 `infer_edges`。）
        """
        return cls(edges=infer_edges(rows), nodes=list(nodes))

    @classmethod
    def from_edges(cls, edges: Iterable[Any], nodes: Iterable[Any] = ()) -> "Graph":
        """**读边表入口**: 磁盘上的边（dict 或 `Edge`）→ 建索引（坏行逐条丢弃, 不抛）。"""
        parsed = [e if isinstance(e, Edge) else Edge.from_dict(e) for e in edges]
        return cls(edges=[e for e in parsed if e is not None], nodes=list(nodes))

    # ── 索引读取（薄封装, 缺键 → 空, 绝不 KeyError） ──

    def edges_from(self, nid: str, rel: str | None = None) -> list[Edge]:
        return [e for e in self.out.get(nid, ()) if rel is None or e.rel == rel]

    def edges_to(self, nid: str, rel: str | None = None) -> list[Edge]:
        return [e for e in self.inc.get(nid, ()) if rel is None or e.rel == rel]

    def targets(self, nid: str, rel: str | None = None) -> list[str]:
        """`nid` 指出去的边对端（`out` 侧）。"""
        return [e.dst for e in self.edges_from(nid, rel)]

    def sources(self, nid: str, rel: str | None = None) -> list[str]:
        """指向 `nid` 的边另一端（`inc` 侧）。"""
        return [e.src for e in self.edges_to(nid, rel)]

    def kind_of(self, nid: str) -> str:
        """节点 kind（没给 nodes / id 不存在 → `""`, 不猜）。"""
        node = self._by_id.get(nid)
        return str(getattr(node, "kind", "")) if node is not None else ""

    def node(self, nid: str):
        return self._by_id.get(nid)

    # ── 六类查询（§2.1 的表; 这就是"够不够用"的验收口径） ──

    def lane(self, entity_id: str, kind: str | None = None) -> list[str]:
        """**entity 车道**（查询 1 的推广）: 挂着 `about` → E 的节点, 可选按 kind 过滤。

        `about` 边的方向是"节点 → entity"（`inc[E]` 才是车道; `out[E]` 是空的）。
        """
        return [src for src in self.sources(entity_id, REL_ABOUT)
                if kind is None or self.kind_of(src) == kind]

    def beliefs_of(self, entity_id: str) -> list[str]:
        """查询 1: entity E 下的 beliefs。"""
        return self.lane(entity_id, "belief")

    def supporters(self, nid: str) -> list[str]:
        """查询 2: 支撑这条认知的来源（`supports` 的 src 侧）。

        ⚠️ **方向**: `supports` 是"**经历 → 认知**", 所以支撑者是 `sources` 不是
        `targets` —— 反了会让"这条看法是从哪来的"指向未来。

        ⚠️ **不按 kind 过滤**: §2.1 那行查询写的是"支撑**经历**", 今天也确实只有
        `episode`（§9-3 合并 `experience` 后仍是）; 但 v4 §2 里 `promise → belief`
        也是 `supports`。过滤会让"没给 nodes"时**静默返回空**（G3 只读边表那种情形）
        —— 要分开就用 `kind_of` 自己分, 别让查询层替调用方猜。
        """
        return self.sources(nid, REL_SUPPORTS)

    def formed_by(self, promise_id: str) -> list[str]:
        """查询 3a: 这条承诺由哪些经历一次次说定（共有）。"""
        return self.targets(promise_id, REL_FORMED_BY)

    def parties(self, promise_id: str) -> list[str]:
        """查询 3b: 承诺双方（`from` / `to`）。"""
        return self.targets(promise_id, REL_FROM) + self.targets(promise_id, REL_TO)

    def neighbors(self, nid: str) -> list[str]:
        """查询 4: 1-hop 扩展（`out[n] + inc[n]`, 去重保序）。"""
        seen: dict[str, None] = {}
        for other in self.targets(nid) + self.sources(nid):
            seen.setdefault(other, None)
        return list(seen)

    def unattributed(self) -> list[str]:
        """查询 5: **未归属清单** = 非 entity 节点 − 有 `about` 边的节点。

        ⚠️ 宇宙必须**排掉 entity 自己** —— entity 永远不会是 `about` 的 src
        （边是"节点 → entity"）, 不排的话每个 entity 都会冒充"未归属"
        （2026-09-21 复核 §2.1 那行查询时发现; 已按此实现）。
        """
        attributed = {e.src for e in self.by_rel.get(REL_ABOUT, ())}
        return [nid for nid, n in self._by_id.items()
                if n.kind != KIND_ENTITY and nid not in attributed]

    def without(self, nid: str) -> list[Edge]:
        """查询 6: 删节点的**边表那一半**（纯函数, 返回过滤后的边）。

        `store.delete` 那一半是 G2 的事; 这里保证"悬空引用与双向一致在**构造上**
        不可能存在"（§2.1）——只要写路径走这里过滤一遍。
        """
        return [e for e in self.edges if e.src != nid and e.dst != nid]

    # ── 审计（观测层, 零行为影响） ──

    def dangling(self) -> list[Edge]:
        """端点不存在的边。**只在给了 nodes 时有意义**（没给 = 无从判断）。"""
        if not self._by_id:
            return []
        return [e for e in self.edges
                if e.src not in self._by_id or e.dst not in self._by_id]

    def stats(self) -> dict:
        """一行台账用（`unknown` 与 `dangling` 是 G1/G3 的两条验收线）。"""
        return {
            "nodes": len(self._by_id),
            "edges": len(self.edges),
            "by_rel": {rel: len(v) for rel, v in sorted(self.by_rel.items())},
            "unknown": len(self.by_rel.get(REL_UNKNOWN, ())),
            "about": len(self.by_rel.get(REL_ABOUT, ())),
            "dangling": len(self.dangling()),
        }

    def __len__(self) -> int:
        return len(self.edges)


# ---------------------------------------------------------------------------
# 与 store 的接缝（2026-09-21 G3: 换装已完成）
# ---------------------------------------------------------------------------

def graph_of(store) -> Graph:
    """`WikiStoreV2` → `Graph`（= store 内存里的**点 + 边**）。

    ⚠️ **G3 起边的真源是 `soul/edges.jsonl`**（`store._edges`）; 推断只在
    **没有边表的旧档**上发生, 而且那一步在 `store._load_edges`（自举）, 不在这里。
    """
    return store.graph()


def iter_edges(store, *, rel: str | None = None) -> Iterator[Edge]:
    """遍历一条世界线的边（`rel` 给了则过滤）。

    dev 侧要图算法时一行建 nx 图（§2.1 的桥; **运行时不许 import networkx**）::

        G = nx.DiGraph()
        G.add_edges_from((e.src, e.dst, {"rel": e.rel}) for e in iter_edges(store))
    """
    for e in graph_of(store).edges:
        if rel is None or e.rel == rel:
            yield e


__all__ = [
    "KIND_ENTITY",
    "RELS",
    "REL_ABOUT",
    "REL_CONTRADICTS",
    "REL_EVOLVED_FROM",
    "REL_FORMED_BY",
    "REL_FROM",
    "REL_SUPPORTS",
    "REL_TO",
    "REL_UNKNOWN",
    "Edge",
    "Graph",
    "canonical_pair",
    "classify_pair",
    "graph_of",
    "infer_edges",
    "iter_edges",
]
