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

⚠️ `REL_UNKNOWN` 是**推断层专有**的兜底, **不属于** §2 的 rel 清单。为什么发它而不是
丢掉: 丢掉会让 1-hop 扩展比今天的 `links` **更窄**（行为回退）; 发出来则"连接关系"
与今天等价, 而"类型判不出来"这件事在 `stats()["unknown"]` 里可见 —— G3 落盘后
写路径总是知道 rel, 那个计数应当归零, **它就是那条验收线**。
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 边类型（`DESIGN_GRAPH_V4.md` §2）
# ---------------------------------------------------------------------------

REL_ABOUT = "about"                  # belief/episode/experience → entity（归属）
REL_SUPPORTS = "supports"            # ⭐ **两种形状**: episode → 认知（决策表 touch 写）·
                                     #    认知 → 认知（R2 的 `links` 写 —— "这条看法支撑那条",
                                     #    真机有实例; 2026-09-29 用户裁决"belief-belief 以后也需要"）
REL_CONTRADICTS = "contradicts"      # 同层之间（她后来发现不对; **对称**）
#: ⭐ **`evolved_from`（旧 → 新）**: 她后来想通了 ⇒ 从旧那条长出新的那条。
#: ⚠️ **方向 2026-10-14 翻过**（用户裁"顺序太怪, 改一下, 名字不动"）: 从前存的是"新 → 旧"
#: （跟着边名读），今天存的是**时间顺向**（旧 → 新）—— 与 `supports`（经历 → 看法, 也是顺向）
#: **同向**了, 而"谁取代了我"变成**入边**（`sources`）。
#: ⚠️ 翻的时候真机**零条**这种边（`contradicts` / `evolved_from` 到今天都没写过）
#: ⇒ **没有老档要迁移**; 旧档里若真有"新 → 旧"的行, 读出来方向就是反的（记着这条）。
REL_EVOLVED_FROM = "evolved_from"
#: ⏸ `formed_by`（promise → episode）· `from` / `to`（promise → entity）**2026-09-29 删** ——
#: 它们唯一的起点 kind 是 `promise`，而 **promise 退出了图**（用户裁决: 承诺太轻,
#: 不足以长期记录 ⇒ 留在 note 当工作记忆, 见 `notes.SLOT_PINNED`）。
#: 判据与当年删 `source` 边同一条: **起点 kind 没了 ⇒ 这些边永远不会有走法**。
#: ⚠️ 盘上若真有旧行照旧读得进（`Edge.from_dict` 不校验名单），只是没有写者了。
#: ⭐ **`akin`（N1a, 2026-09-29）：她发现"这两条是同一类事"** —— episode ↔ episode，**对称**。
#:
#: 它是 **`noticed` 记录行的落点**（`docs/DESIGN_MMT_NEW_ACTION.md §4.3`）：她在对话里指一条
#: 旧 episode，L1 建完新 episode 之后由引擎落这条边。⇒ **写者只有她（经 L1）**，不是推断层。
#:
#: ⚠️ **为什么叫 `akin` 而不是 `same_kind`**：`kind` 在本项目里已经**确切地**指"节点类型"
#: （episode / belief / entity / group）⇒ `same_kind(A, B)` 会被读成
#: *"这两条 kind 相同"*（一句废话），而它真正说的是"**同一类事**"（语义同类）。
#:
#: ⚠️ **`episode ↔ episode` 为什么不进 `classify_pair` 的推断表**（有意为之, 别"修"）:
#: 旧档的 `links` 只声称"这两条**挨着 / 相关**"，而 `akin` 声称"**同类**" —— 那是**判断**。
#: 推断表替旧数据做判断就是猜（与"`belief↔belief` 不判 `evolved_from`"同一条纪律）;
#: 旧档的 `episode↔episode` 继续落 `REL_UNKNOWN`，在 `stats()["unknown"]` 里如实可见。
REL_AKIN = "akin"
#: ⭐ **`member_of`（N1b, 2026-09-29）：L2 判定"这条经历属于这一类"** —— episode → group，**有向**。
#:
#: 与 `akin` 的分工（**两条都要, 不许合并**）:
#:     `akin(ep ↔ ep)`      = ⭐ **她的原始发现**（"这两条像"）—— 有噪音、可能只是两两
#:     `member_of(ep → grp)` = ⭐ **L2 的归纳判定**（"它属于这一类"）—— 可合并 / 拆分 / 多归属
#: **前者是输入，后者是输出。** 混成一条会让"她觉得像"和"判定同类"不可区分
#: （真机证据: dense 相似度组内最低 < 组外最高，最差 **0.425** ⇒ 她的"像"必须被复判）。
#:
#: ⚠️ **为什么成员不能存成群节点上的 `members` 列表**：成员是**随时间一次次建立的**，
#: 每条**各有自己的 `ts`**（"什么时候加入的"是信息，列表只能给出群节点的 `ts`）;
#: 而且边是 append + 幂等，列表是读-改-写。⚠️ 这一格我在设计时判错过一次，记档在
#: `docs/DESIGN_MMT_NEW_ACTION.md §4.5.3`。
REL_MEMBER_OF = "member_of"

#: 全部合法 rel（**唯一清单**; 新增边类型只改这里 + `classify_pair` 的判据）
#: ⭐ **6 条**（2026-09-25 删 `source` · **2026-09-29 N1a 加 `akin`**、N1b 加 `member_of`、
#: 同日删 `formed_by`/`from`/`to` 三条 promise 专属边）:
#: `source` 唯一的形状是 `fact → episode`，而 **`fact`
#: 这个 kind 早在 2026-09-02 就退役了**（`nodes.KINDS` 里没有它 ⇒ 建都建不出来）
#: ⇒ 那是一条**永远不会有走法**的边（§2.2 的判据: 没走法的边是装饰）。用户裁决删。
#: （`contradicts` / `evolved_from` 今天同样零写者，但它们的 kind 都在、将来会有走法
#: —— "还没有走法"与"永远不会有走法"是两件事。）
#: ⚠️ 盘上若真有旧 `source` 行，**照旧读得进**（`Edge.from_dict` 不校验 rel 名单），
#: 只是不再有任何写者/分类器产生它。
RELS: tuple[str, ...] = (REL_ABOUT, REL_SUPPORTS, REL_CONTRADICTS,
                         REL_EVOLVED_FROM, REL_AKIN, REL_MEMBER_OF)

#: ⭐ **对称 rel 的唯一清单**（2026-09-29 N1a）。
#:
#: 为什么必须有这个常量: 对称性原来**只活在自举的调用方**（`infer_edges` 按"这一对来自
#: `links` 还是 `contradictions`"传 `symmetric=`），而 **`store.add_edge` 完全不知道这件事**
#: ⇒ `add_edge("akin", B, A)` 与 `add_edge("akin", A, B)` 会被当成两条不同的边
#: （幂等键是 `(rel, src, dst)`，而且是**有向**的）。
#: ⇒ 现在 `store.add_edge` / `store.remove_edge` / 自举 `_emit` **共用这一份**（两份实现必漂）。
#: ⚠️ `member_of` **不在**这里 —— 它是 `episode → group` 的**有向**边（"谁属于哪一类"）。
SYMMETRIC_RELS: frozenset[str] = frozenset({REL_CONTRADICTS, REL_AKIN})

#: ⚠️ 推断层兜底 —— **不在 `RELS` 里**（见模块 docstring 的第二条警告）
REL_UNKNOWN = "unknown"

#: v4 §1 的 entity（G1 起只认 kind 字符串, 不碰 `nodes.KINDS` 那张表）
KIND_ENTITY = "entity"
#: ⭐ `experience`（经验; 2026-10-06 定名, 原 `group`）—— **L2 归纳出来的"一类事"**，
#: 成员靠 `member_of` 指过来。
#: ⚠️ 它**不在 `_COGNITION` 里**：群不是"稳定下来的认知"（那是 belief/experience），
#: 而是**分类**。所以 `member_of` 必须是自己的 rel，不能混进 `supports`
#: （混了会让 `graph.supporters()` 把群也捞出来 —— 而它今天用来算"被引数"）。
KIND_EXPERIENCE = "experience"

#: 会挂 `about` 的 kind（§2: belief/episode/experience）。
#: ⚠️ `fact` 2026-09-25 摘掉 —— 它是**死配置**（kind 已退役 ⇒ 这条白名单永远匹配不到
#: 任何节点）。`experience` **留着**，但理由换了: 不再是"押 §9-3 的合并预案"（那条
#: 2026-09-25 由用户关掉），而是**它本身就是"关于老师的事"** ⇒ 该被 `about → sensei`
#: 指着（§9-8）。⚠️ `promise` 2026-09-29 摘掉（它退出了图）。
#: ⭐ `experience`（经验; 原 `group`）**加进来** —— 经验也能归属 entity（"苔藓"属于老师那条线）。
#: 今天**零写者**（要 L2 才写），这是"先开接口、别锁死"。
#: ⏸ `profile`（玩家画像）**2026-10-14 摘掉** —— 整个 kind 删格式（见 `nodes.KINDS`）。
_ABOUTABLE = ("belief", "episode", "experience")
#: 认知侧（`supports` 的 dst）: 她的结论（"稳定下来的东西"）
#: ⚠️ **经验不在这里** —— 见 `KIND_EXPERIENCE` 的注释。
#: ⏸ `profile` **2026-10-14 随 kind 删** —— 当年它在这里的理由是"画像也是稳定下来的东西"。
_COGNITION = ("belief",)


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
    def from_dict(cls, raw: Any) -> Edge | None:
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

    这样新 kind（`entity` / `group`）一落地，自举与运行时就自动一致；而按 `KINDS` 归一会把
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
    # ⭐ 对称性**只在 `canonical_for` 一处判**（`store.add_edge` 走同一个函数, 防两份实现漂）
    src, dst = canonical_for(rel, src, dst)
    out.append(Edge(rel=rel, src=src, dst=dst, ts=_edge_ts(meta, src, dst)))


def classify_pair(ka: str, kb: str, a_id: str, b_id: str) -> tuple[str, str, str]:
    """两端 kind + 两个 id → `(rel, src, dst)`。**唯一**的分类表。

    唯一调用方 = 旧档**自举**（`infer_edges` 从盘上的 `links`/`contradictions` 推）——
    那条路只有"这两条挨着", 说不出 rel, 所以只能靠这张表猜。活路径**一律走
    `store.add_edge(rel, …)`**, 显式 rel 才有"类型化"（2026-10-12: 旧接口 shim
    `store.add_link` 已删, 这张表只剩自举一个调用方）。

    ## 推断表（今天能判的只有这些）

    | 对 | 判成 | 依据 |
    |---|---|---|
    | `episode` ↔ `belief` | `supports`（**经历 → 认知**） | §2; 方向由 kind 定, 不是猜 |
    | `entity` ↔ `belief` / `episode` / `experience` | `about`（**对方 → entity**） | §2 归属 |
    | 其余（`belief`↔`belief`、`belief`↔`experience`、`episode`↔`experience`、`episode`↔`episode`、`entity`↔`entity`） | `unknown` | **不猜** |

    ⚠️ **`experience` 不进 `_COGNITION`, 这是有意的**（别"顺手"补上）: 经验**不是认知**,
    `episode ↔ experience` 之间那条边是 `member_of` 的活, 由写路径显式写 ——
    自举猜成 `supports` 会把它变成"这类事的一次证据"。⛔ 也别把早就退役的 `fact`
    或改名前的 `group` 补回白名单 —— 那些 kind 只会出现在旧档的 `links` 里,
    给它们判 `about`/`supports` 就是**替旧数据编意图**（`test_wiki_graph.py` 钉着这两条）。

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


def canonical_for(rel: str, src: str, dst: str) -> tuple[str, str]:
    """按 `rel` 规范化端点 —— ⭐ **对称性的唯一实现处**（N1a, 2026-09-29）。

    * **对称 rel**（`SYMMETRIC_RELS`: `contradicts` / `akin`）→ `canonical_pair`
    * 其余 → **原样返回**（有向边不许被"顺手"规范化 —— 那会悄悄改掉 `member_of`
      这类边的方向语义）

    ⚠️ **必须在幂等检查之前调用**：`add_edge` 的幂等键是 `(rel, src, dst)` 且**有向**，
    不先规范化的话，`akin(B, A)` 与 `akin(A, B)` 会被当成两条不同的边，各写一条
    （真机后果: 同一次"她发现同类"在边表里出现两行，L2 分群时数两遍）。
    """
    return canonical_pair(src, dst) if rel in SYMMETRIC_RELS else (src, dst)


def related(edges: Iterable[Edge], nid: str, rel: str) -> list[str]:
    """⭐ **对称 rel 的一跳对端**（两个方向都算, 按传入的边序 = **建立序**, 去重保序）。

    ⚠️ **为什么必须有它**: `akin` / `contradicts` 是**对称**的, 但存进去时被
    `canonical_for` 归一到"id 小的当 `src`" ⇒ 只查 `targets`（或只查 `sources`）
    **必然漏一半**, 而漏的是哪一半取决于两个 id 的**字典序**, 不是语义。
    （真机后果: 她认过的相似时灵时不灵 —— 连"看起来像不像"都做不到。）
    ⛔ **有向 rel 别用它**: 那会把方向语义抹平（`supports` 的"谁支撑谁"就没了）。
    """
    out: dict[str, None] = {}
    for e in edges:
        if e.rel != rel:
            continue
        if e.src == nid:
            out.setdefault(e.dst, None)
        elif e.dst == nid:
            out.setdefault(e.src, None)
    return list(out)


def conflicting(edges: Iterable[Edge], a: str, b: str) -> bool:
    """`a` 与 `b` 之间有没有一条 `contradicts`（**对称 ⇒ 两个方向都算**）。

    ⚠️ 与 `related` 同一个理由: 一条"打架"的边可能把 `a` 存在 `src`、也可能存在 `dst`。
    """
    for e in edges:
        if e.rel != REL_CONTRADICTS:
            continue
        if (e.src == a and e.dst == b) or (e.src == b and e.dst == a):
            return True
    return False


# ---------------------------------------------------------------------------
# 归属的兜底（2026-10-14 用户裁: "R1 的 `entity` 留空 ⇒ 默认 self+sensei"）
# ---------------------------------------------------------------------------

#: ⭐ **`entity` 留空时, 这条记录默认属于谁**（`kind` → 保留号）。
#: 判据: 这个介质里"她的事"**天然**是"她与老师的事" ⇒ R1 不必每条都写一遍。
#:
#: ⛔ **只当读侧的口径, 绝不落边**（两个理由都是真机算过的）:
#:   · 落边 = 21 条经历 + 4 条看法会多出 **46 条常数边**（图 58 → ~104）;
#:   · `Edge` 里**没有位置**记"这条边是默认来的" ⇒ 图里再也分不出"她明确说关于老师"
#:     与"她没说、按介质默认" —— 而**那个区分正是"归属"这个信号的全部价值**。
#: ⚠️ 那两个串 = `core.brain.entities.SELF_ID` / `SENSEI_ID`（守门用例钉住不许漂）——
#:   本模块**零项目内 import** 是它刻意的性质（同 `marks.py`）, 所以只能写字面量。
#: ⏸ **`belief` 那一行还没加** —— L2（`cognize`）的"留空 ⇒ self"用户已裁,
#:   等它的默认随碰撞那一件落地时一起加（今天加了没有第二个读者）。
DEFAULT_FACES: dict[str, tuple[str, ...]] = {
    "episode": ("x0000", "x0001"),
}


def default_faces(kind: str) -> tuple[str, ...]:
    """`entity` 留空时那条记录**默认归属谁**（没有兜底的 kind ⇒ `()`）。

    ⭐ 与 `lane` **同一张表**（`DEFAULT_FACES`）—— 将来"面"（碰撞分组）也走这里,
    ⛔ 别在别处再写一份默认。
    """
    return DEFAULT_FACES.get(str(kind), ())


def _edge_ts(meta: dict, src: str, dst: str) -> str:
    """推断边的时刻 —— 取两端 `ts` 中**较晚**的那个（≈ 这条关系形成的时刻）。

    旧档没有边表, 这是**近似值**; G3 起的写路径如实落。两端都没有 `ts` → `""`
    （哨兵纪律: **不编**一个时刻 —— 与 `marks.relative` 同一条）。
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
    def from_rows(cls, rows: Iterable[Any], nodes: Iterable[Any] = ()) -> Graph:
        """**旧档自举入口**: 点表的原始行 → 推断出的边 + 索引。

        （原 `from_nodes` 于 G4 删除 —— 它从 `BrainNode.links` 推断, 而那个字段没了;
        自举改在**文件格式层**做, 见 `infer_edges`。）
        """
        return cls(edges=infer_edges(rows), nodes=list(nodes))

    @classmethod
    def from_edges(cls, edges: Iterable[Any], nodes: Iterable[Any] = ()) -> Graph:
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
        """**entity 车道**: 关于 E 的全部记录 = **她明确写明的** + ⭐ **默认归属的**。

        `about` 边的方向是"节点 → entity"（`inc[E]` 才是车道; `out[E]` 是空的）。

        ⭐ **2026-10-14（用户裁"R1 的 `entity` 留空默认 self+sensei"）**: 车道加上
        **兜底那一面** —— 没写归属的 `episode` 也算进 self / sensei 的车道
        （`default_faces`）。⚠️ 两条边界:
          ① **明确写了别人**（有任何 `about` 出边）**就不兜底** —— 否则"归属"这个筛子
             会退化成全集（她写了 `["小玉"]` 就是"关于小玉");
          ② **那个对象不存在 ⇒ 车道仍空** —— 没有这个对象, 就谈不上它的车道
             （旧档与单测里 `x0000` 经常不存在）。
        ⚠️ 保留号（self / sensei）的车道**天然接近全量** —— 那是**语义如此**,
        ⛔ 不是 bug（P19 的 `name` 段早就为此把保留号排除在"提到了谁"之外）。
        ⚠️ 顺序: **明确写的在前**, 兜底的在后（`dict` 保插入序）。
        """
        want = None if kind is None else str(kind)
        seen: dict[str, None] = {}
        for src in self.sources(entity_id, REL_ABOUT):
            if want is None or self.kind_of(src) == want:
                seen.setdefault(src, None)
        if self._by_id.get(entity_id) is None:              # ② 对象不在 ⇒ 不兜底
            return list(seen)
        for k, faces in DEFAULT_FACES.items():              # ① 只有"有默认面"的 kind
            if entity_id not in faces or (want is not None and want != k):
                continue
            for nid, node in self._by_id.items():
                if str(getattr(node, "kind", "")) != k:
                    continue
                if self.targets(nid, REL_ABOUT):            # ① 明确写了谁 ⇒ 不兜底
                    continue
                seen.setdefault(nid, None)
        return list(seen)

    def beliefs_of(self, entity_id: str) -> list[str]:
        """查询 1: entity E 下的 beliefs。"""
        return self.lane(entity_id, "belief")

    def supporters(self, nid: str) -> list[str]:
        """查询 2: 支撑这条认知的来源（`supports` 的 src 侧）。

        ⚠️ **方向**: `supports` 是"**经历 → 认知**", 所以支撑者是 `sources` 不是
        `targets` —— 反了会让"这条看法是从哪来的"指向未来。

        ⚠️ **不按 kind 过滤**: §2.1 那行查询写的是"支撑**经历**", 今天也确实只有
        `episode`（§9-3 合并 `experience` 后仍是）。过滤会让"没给 nodes"时**静默返回空**
        （G3 只读边表那种情形）—— 要分开就用 `kind_of` 自己分, 别让查询层替调用方猜。
        """
        return self.sources(nid, REL_SUPPORTS)

    def neighbors(self, nid: str) -> list[str]:
        """查询 4: 1-hop 扩展（`out[n] + inc[n]`, 去重保序）。"""
        seen: dict[str, None] = {}
        for other in self.targets(nid) + self.sources(nid):
            seen.setdefault(other, None)
        return list(seen)

    def unattributed(self) -> list[str]:
        """查询 5: **未归属清单** = 非 entity 节点 − 有 `about` 边的节点。

        ⭐ **2026-10-14 起这个名字要读准**: 它们**不是"没有归属"**, 而是**走了默认面**
        （`lane` 的兜底: `episode` ⇒ self + sensei）—— 这张清单的用途因此变成
        "**谁没被明确写过**"（观测用）, ⛔ 不再是缺陷清单。

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
    "DEFAULT_FACES",
    "KIND_ENTITY",
    "KIND_EXPERIENCE",
    "RELS",
    "SYMMETRIC_RELS",
    "REL_ABOUT",
    "REL_AKIN",
    "REL_CONTRADICTS",
    "REL_EVOLVED_FROM",
    "REL_MEMBER_OF",
    "REL_SUPPORTS",
    "REL_UNKNOWN",
    "Edge",
    "Graph",
    "canonical_for",
    "canonical_pair",
    "classify_pair",
    "conflicting",
    "default_faces",
    "graph_of",
    "infer_edges",
    "iter_edges",
    "related",
]
