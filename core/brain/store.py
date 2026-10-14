"""WikiStore v2 — 图式 wiki 存储（AGENT_BRAIN.md §2 / M1b + DESIGN_GRAPH_V4 §2.1 **G3**）。

职责（单一）: jsonl 读写 + 原子整写 + id 分配 + 内存索引 + 快照 + 去重检查。
不做: 修订契约校验/执行（revise.py）· 渲染（render.py）· 召回（recall.py）·
      出厂 digest（seed.py）——引擎侧流程在 revise.py 编排。

规则:
    - 文件（**点边分离两文件**, DESIGN_GRAPH_V4 §2.1）:
        soul/wiki.jsonl    点 —— 一行一条 BrainNode（**边不再写在这里**）
        soul/edges.jsonl   边 —— 一行一条 Edge `{rel,src,dst,ts}`（**2026-09-21 G3 起**）
        soul/notes.json    随身笔记的**派生缓存**（§3.2）—— ⚠️ **不归 `save()`**:
                           它的真源是**事件流的 note 操作**, 由 `notes_state()` / `save_notes()`
                           单独读写（`notes.py` 是纯函数层, 本类只管它的落盘）
    - 写: 内存操作（add/update/delete/add_edge…）→ save() 原子整写**两个文件**
    - 护栏: add/update 前过 node.validate()——无效节点拒绝（宁缺勿错, raise）
    - 去重: 水位 `digested_seq`（增量幂等）——⚠️ 原 `find_by_event_seq()` 查重辅助
      2026-09-21 删（零调用者）
    - id: 前缀 + 4 位零填充（m=episode/belief, e=experience）
    - 快照: snapshot_to/restore_from = **点 + 边**两个文件（R6 存档快照语义）
    - **自举**: 没有 `edges.jsonl` 的旧档 → 载入时从 `links`/`contradictions`
      **推断**出边（`graph.infer_edges`, 只读点上残留的旧字段）; 下一次 `save()`
      把它落盘 —— 迁移就完成了（**无迁移脚本**, 与"旧档宽容读"同一条纪律）

⚠️ 两个文件**不是一次事务**（两次 replace）。一致性靠**读侧宽容**: 边指向不存在的
点 → 保留, 但在 `audit()` / `Graph.dangling()` 里可见。写序 = **先点后边** ——
点写成功而边写失败, 后果是"边表陈旧（少几条新边）", 而记忆正文完好可重算;
反过来则会留下一批悬空边。两条都只降级不损坏, 但前者更好收拾。
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from core.brain.graph import (
    Edge,
    Graph,
    canonical_for,
    conflicting,
    infer_edges,
    related,
)
from core.brain.nodes import BrainNode, format_id
from core.brain.notes import NotesState, fold
from core.common import err
from core.session.events import TYPE_NOTE
from core.session.io import atomic_write_json, atomic_write_lines, read_jsonl

logger = logging.getLogger(__name__)

#: kind → id 前缀（AGENT_BRAIN.md §2 + v4 §3.0 的 `x`; relation/fact 已砍——c 前缀退役 2026-09-02）
#: ⚠️ `x0000`（self）/ `x0001`（sensei）是**保留号**, 见 `entities.py` —— `next_id("x")` 因此从 x0002 起。
#: ⏸ `p`（promise 节点）2026-09-29 **退役** —— promise 退图（见 `nodes.KINDS`）;
#: ⚠️ 旧档里若有 `p…` 行仍读得进（`from_dict` 按 kind 降级成 episode 之外, 不炸）。
#: ⭐ 2026-10-06 改名: **号段跟着数据走, 不跟着名字走** —— `experience`（经验, 原 `group`）
#: 沿用 `g`（老 `g…` 语义不变）。
#: ⏸ `e`（原 `profile` 玩家画像）**2026-10-14 随那个 kind 一起退役** —— 旧档里若有
#: `e…` 行仍读得进（`from_dict` 对认不出的 kind 降级成 episode, 不炸）。
#: ⛔ `p` 不能用: 承诺退图后 `test_promise_prefix_is_gone` 钉着"不许再有 `p` 号";
#: ⛔ 前缀不许撞车（只有 `m` 可共用, 见 `test_every_kind_has_an_explicit_id_prefix`）
#: —— ⚠️ **必须显式登记**: `add()` 走
#: `_PREFIX.get(kind, "m")`，漏了会拿到 `m` 号并与 episode/belief **撞号**。
_PREFIX = {"experience": "g", "episode": "m", "belief": "m", "entity": "x"}

#: 节点字段白名单（update patch 只接受这些——防任意字段注入）
_FIELDS = set(BrainNode.__dataclass_fields__.keys())

#: 边表文件名（与 wiki.jsonl 同目录 —— 记忆层自包含, §0.1）
EDGES_NAME = "edges.jsonl"
#: 随身笔记缓存文件名（§3.2; 同目录 —— 与点/边一样属于"记忆层自包含"那一份）
NOTES_NAME = "notes.json"


class WikiStoreV2:
    """图式 wiki 存储（per 世界线, 单文件 jsonl）。"""

    def __init__(self, data_root: str | Path = "data", *,
                 world_id: str = "world1", char_id: str = "",
                 path: str | Path | None = None):
        # soul/ = 记忆层子目录（2026-09-04 用户拍板: 角色目录下开 soul 收编记忆
        # 子系统——events 原材料 + wiki 成品 + 变更史 + 出厂快照自包含; 会话层
        # meta/progress/sessions 留在 characters/{char}/ 原地）
        self.path = Path(path) if path is not None else (
            Path(data_root) / "worlds" / world_id / "characters"
            / char_id / "soul" / "wiki.jsonl")
        #: 边表（点边分离的另一半 —— **2026-09-21 G3 起边的唯一落盘处**）
        self.edges_path = self.path.with_name(EDGES_NAME)
        self.meta_path = self.path.with_name("wiki.meta.json")
        #: 随身笔记缓存（§3.2 —— 与点/边同目录; 不进 `save()` / 快照, 见模块 docstring）
        self.notes_path = self.path.with_name(NOTES_NAME)
        #: 世界根定位
        self._data_root = Path(data_root)
        self._world_id = world_id
        self.meta: dict = self._load_meta()
        self._nodes: dict[str, BrainNode] = {}
        self._edges: list[Edge] = []
        self._load()

    # ------------------------------------------------------------------
    # meta（digest 水位等 per 世界线元数据——wiki.meta.json, 原子整写）
    # ------------------------------------------------------------------

    def _load_meta(self) -> dict:
        import json
        try:
            raw = json.loads(self.meta_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_meta(self) -> None:
        """原子写 meta（digest 水位推进后调用）。"""
        atomic_write_json(self.meta_path, self.meta)

    @property
    def digested_seq(self) -> int:
        """digest 水位: 已消化的最大事件 seq（0 = 从未消化）。"""
        try:
            return int(self.meta.get("digested_seq", 0) or 0)
        except (TypeError, ValueError):
            return 0

    # ------------------------------------------------------------------
    # 剧情时间游标（§4.11 —— 写路径的唯一入口）
    # ------------------------------------------------------------------

    @property
    def world_id(self) -> str:
        return self._world_id

    @property
    def data_root(self) -> Path:
        return self._data_root

    # ── 剧情游标 API：**已整族退役**（2026-09-17, `ESSAY_TIME_MODEL §10`）──
    # 删掉的是 `clock_path` / `clock()` / `save_clock()` / `peek_clock_cursor()`
    # / `restore_clock_cursor()`（以及 `self._clock` 与 `WorldClock`/`StoryTime` 导入）。
    # 它们服务的是**剧情日历**（`world_clock.json` 的游标）—— 而唯一日期轴
    # 现在是**现实日期**（`node.ts`），故整族无人调用、整族删除。
    # `digest` 侧同步: 推进块与游标提交都已删（见 `digest.py`）。

    # ------------------------------------------------------------------
    # 载入 / 查询
    # ------------------------------------------------------------------

    def _load(self) -> None:
        rows: list[dict] = []
        for raw in read_jsonl(self.path):
            node = BrainNode.from_dict(raw)
            if node.id and not node.validate():      # 坏条目跳过（宁缺勿错）
                self._nodes[node.id] = node
                if isinstance(raw, dict):
                    rows.append(raw)                 # 自举只看**读进来的那些行**
        self._edges = self._load_edges(rows)

    def _load_edges(self, rows: list[dict]) -> list[Edge]:
        """边表 → 内存。**有边表读边表, 没有则从点表的原始行自举**（旧档, §2.1）。

        ⚠️ G4 起自举吃的是**原始行**（`graph.infer_edges(rows)`）而不是节点对象 ——
        `links`/`contradictions` 字段已从 `BrainNode` 删除, 自举因此活在**文件格式层**。
        自举只在内存里发生（读路径不写盘）; 落盘交给下一次 `save()`。
        """
        got = _read_edge_file(self.edges_path)
        if got is not None:
            return got
        edges = infer_edges(rows)                     # 自举: 旧档只有点
        if edges:
            logger.info("wiki 边表自举: %s ← 点上残留的 links/contradictions %d 条"
                        "（下一次 save() 落盘, 之后就与节点字段无关了）",
                        self.edges_path.name, len(edges))
        return edges

    def get(self, nid: str) -> BrainNode | None:
        return self._nodes.get(nid)

    def all(self) -> list[BrainNode]:
        """全部节点（插入序 = 创建序）。"""
        return list(self._nodes.values())

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, nid: str) -> bool:
        return nid in self._nodes

    # ------------------------------------------------------------------
    # id 分配
    # ------------------------------------------------------------------

    def next_id(self, prefix: str) -> str:
        """下一个 id（扫描现有同前缀最大序号 +1）。"""
        seq = 0
        for nid in self._nodes:
            if nid.startswith(prefix):
                try:
                    seq = max(seq, int(nid[len(prefix):]))
                except ValueError:
                    continue
        return format_id(prefix, seq + 1)

    # ------------------------------------------------------------------
    # 写入（内存; 落盘走 save()——引擎在修订包全量通过后统一 save）
    # ------------------------------------------------------------------

    def add(self, node: BrainNode) -> str:
        """新增节点（自动分配 id; 无效节点拒绝）。返回 id。

        入仓前 normalize——字段级不变量（significance clamp）**必须在入仓这一处钉死**,
        别指望每个调用方自己记得。边不在这里（边表是 `add_edge` 的家）。
        """
        if not node.id:
            node.id = self.next_id(_PREFIX.get(node.kind, "m"))
        node.normalize()
        errors = node.validate()
        if errors:
            raise ValueError(err("InvalidNode",
                                 f"{node.kind} 节点无效: {'; '.join(errors)}"))
        if node.id in self._nodes:
            raise ValueError(err("DuplicateId", f"节点 id 已存在: {node.id}"))
        self._nodes[node.id] = node
        return node.id

    def update(self, nid: str, patch: dict) -> BrainNode:
        """打补丁更新（patch 键必须是节点字段）。返回新节点。

        ⚠️ 原"出厂基座只允许 notes 追加"守卫（SeedImmutable）2026-09-21 删——
        它判的是 `is_seed()`（`source == "experience"`），而出厂记忆早已不进 wiki
        （见 `nodes.py` 模块 docstring）。节点现在没有不可变区。
        """
        node = self._nodes.get(nid)
        if node is None:
            raise KeyError(err("NotFound", f"节点不存在: {nid}"))
        unknown = set(patch) - _FIELDS
        if unknown:
            raise ValueError(err("BadPatch", f"未知字段: {sorted(unknown)}"))
        new = BrainNode.from_dict({**node.to_dict(), **patch})
        errors = new.validate()
        if errors:
            raise ValueError(err("InvalidNode",
                                 f"更新后节点无效: {'; '.join(errors)}"))
        new.normalize()                        # 维护不变量（significance clamp）
        self._nodes[nid] = new
        return new

    def delete(self, nid: str) -> bool:
        """删除节点 + **过滤边表**（返回是否存在）。

        §2.1 的闭环: 删节点 = 点表删 + 边表过滤一遍 ⇒ **"悬空引用"与"双向一致"
        在构造上不可能存在**。旧版那套"遍历他人 `links`/`contradictions` 清死引用"
        的补丁随之删除（它服务的无向边已经不存在了）。
        """
        if nid not in self._nodes:
            return False
        self._nodes.pop(nid)
        self._edges = [e for e in self._edges if e.src != nid and e.dst != nid]
        return True

    # ------------------------------------------------------------------
    # 边（DESIGN_GRAPH_V4 §2.1）—— **2026-09-21 G3 起边的唯一真源**
    # ------------------------------------------------------------------

    def edges(self) -> list[Edge]:
        """全部边（插入序 = 建立序）。"""
        return list(self._edges)

    def graph(self) -> Graph:
        """当前内存态的边视图（查询走 §2.1 那六类; 每次现构造, 不缓存）。"""
        return Graph(edges=self._edges, nodes=self._nodes.values())

    def neighbors(self, nid: str) -> list[str]:
        """1-hop 邻居（任意 rel; 去重保序）—— 召回的一跳扩展走这里。"""
        out: dict[str, None] = {}
        for e in self._edges:
            if e.src == nid:
                out.setdefault(e.dst, None)
            elif e.dst == nid:
                out.setdefault(e.src, None)
        return list(out)

    def related(self, nid: str, rel: str) -> list[str]:
        """**对称 rel 的一跳对端**（两个方向都算, 按边的**建立序**）—— 见 `graph.related`。

        ⚠️ 有向 rel（`supports` / `about` / `member_of` / `evolved_from`）别用它。
        """
        return related(self._edges, nid, rel)

    def conflicting(self, a: str, b: str) -> bool:
        """`a` 与 `b` 是否互相打架（`contradicts`, **对称 ⇒ 两个方向都算**）。"""
        return conflicting(self._edges, a, b)

    def add_edge(self, rel: str, src: str, dst: str, *, ts: str = "") -> None:
        """加一条类型化边（幂等: 同 `(rel, src, dst)` 已存在则跳过）。

        ⚠️ **两端必须存在**（悬空即拒）——"悬空引用在构造上不可能存在"（§2.1）
        靠的就是写路径在这里关门; 读路径（`_load_edges`）相反, **宽容保留**,
        因为那是旧档（宽容读 ≠ 允许写坏）。

        ⭐ **对称 rel 先规范化**（2026-09-29 N1a）: `contradicts` / `akin` 走
        `graph.canonical_for`（对称性的**唯一实现处**）—— 必须在幂等检查**之前**,
        否则 `akin(B, A)` 与 `akin(A, B)` 会被当成两条边各写一条。

        `ts` = 这条边**建立**的时刻。不给 → 取当下（2026-09-22: 原先默认空串, 结果
        写路径产的边全没有 ts —— 真机一轮后 `edges.jsonl` 里一半有、一半没有）。
        调用方知道更准的时刻就显式传（digest 传的是**本段日期**, 不是"写库时刻"）。
        ⚠️ 读侧不编: 旧档边表里没有 `ts` 的仍保持空串（哨兵纪律）。
        """
        if src not in self._nodes or dst not in self._nodes:
            raise ValueError(err("DanglingEdge",
                                 f"边端点不存在: {src} -{rel}-> {dst}"))
        if src == dst:
            raise ValueError(err("SelfEdge", f"边不能自环: {src}"))
        src, dst = canonical_for(rel, src, dst)      # ⭐ 幂等检查之前
        for e in self._edges:
            if e.rel == rel and e.src == src and e.dst == dst:
                return                                # 幂等
        if not ts:
            from datetime import datetime
            ts = datetime.now().isoformat(timespec="seconds")
        self._edges.append(Edge(rel=rel, src=src, dst=dst, ts=ts))

    def remove_edge(self, rel: str, src: str, dst: str) -> None:
        """删一条边（**对称 rel 反着传也删得掉** —— 同 `add_edge` 共用规范化）。"""
        src, dst = canonical_for(rel, src, dst)
        self._edges = [e for e in self._edges
                       if not (e.rel == rel and e.src == src and e.dst == dst)]

    def _require(self, nid: str) -> BrainNode:
        node = self._nodes.get(nid)
        if node is None:
            raise KeyError(err("NotFound", f"节点不存在: {nid}"))
        return node

    # ------------------------------------------------------------------
    # 持久化 / 快照
    # ------------------------------------------------------------------

    def save(self) -> None:
        """原子整写**两个文件**（点 + 边; 写序理由见模块 docstring）。

        ⚠️ **不含 `notes.json`** —— note 的真源是事件流, 它的提交点在"事件 append 之后"
        （见 `save_notes`）。并进来的话, digest 的一次回滚就会把她的本子一起带走。
        """
        atomic_write_lines(self.path, (n.to_json_line() for n in self._nodes.values()))
        atomic_write_lines(self.edges_path, (e.to_json_line() for e in self._edges))

    def clone_state(self) -> tuple[dict[str, BrainNode], list[Edge]]:
        """深拷贝当前**点 + 边**（修订包/digest 的原子性快照——revise.py 用）。

        ⚠️ **边必须一起拷**: 只拷点的话, 失败回滚会把这一轮新加的边**留在原地**
        （节点没了边还在 ⇒ 悬空 + "回滚没回干净"）。节点会被原地铁改（add_edge 等）,
        所以点也要深拷贝而非浅拷 dict。

        ⭐ **两边都走 `from_dict(to_dict())`，不手抄字段**（2026-09-29 N1a 修）:
        边原来是 `Edge(e.rel, e.src, e.dst, e.ts)` —— **位置参数**，给 `Edge` 加字段时
        会**静默丢掉**那个字段（而它是 digest 事务回滚的基础 ⇒ 回滚把状态回成"少了一半属性"）。
        与点侧同一写法之后，"加字段忘了改这里"这一类 bug 在**构造上**不可能存在。
        守门用例: `tests/core/test_wiki_store.py::test_clone_state_copies_edges_field_complete`
        （含一条**结构性**断言: 本函数源码里不许再出现 `Edge(`）。
        """
        return ({nid: BrainNode.from_dict(n.to_dict()) for nid, n in self._nodes.items()},
                [Edge.from_dict(e.to_dict()) for e in self._edges])

    def restore_state(self, state: tuple[dict[str, BrainNode], list[Edge]]) -> None:
        """恢复内存态（点 + 边; 回滚用——不落盘, 调用方决定是否 save）。"""
        self._nodes, self._edges = state

    # EXT: save-point-r6 — 存档点语义（R6 未落地）; 勿删（docs/EXTENSION_POINTS.md）
    def snapshot_to(self, dest: str | Path) -> None:
        """快照 = **点 + 边**两个文件（`dest` 是点表路径, 边表 = 同目录 `edges.jsonl`）。

        R6 存档点语义: 自包含。⚠️ **只写点的话, 快照回来的记忆是断连的**
        （entity 车道 / 支撑链全空）——而边是可重算的派生物,
        点不是, 所以快照必须两样都带。
        ⚠️ **`notes.json` 不进快照**: 它是**事件流的**派生缓存, 而快照不带事件流 ——
        单独带上它只会造出"半个世界"（本子指着的世界已经不在快照里了）。
        """
        dest = Path(dest)
        atomic_write_lines(dest, (n.to_json_line() for n in self._nodes.values()))
        atomic_write_lines(dest.with_name(EDGES_NAME),
                           (e.to_json_line() for e in self._edges))

    # EXT: save-point-r6 — 存档点语义（R6 未落地）; 勿删（docs/EXTENSION_POINTS.md）
    def restore_from(self, src: str | Path) -> None:
        """从快照恢复（点 + 同目录边表; 调用方随后 save() 落盘）。

        无边界表的**旧快照** → 从点上残留的旧字段自举（宽容读）。⚠️ 不改编
        `self.edges_path`——恢复完还是要写回本世界线自己的边表。
        """
        src = Path(src)
        self._nodes = {}
        rows: list[dict] = []
        for raw in read_jsonl(src):
            node = BrainNode.from_dict(raw)
            if node.id and not node.validate():
                self._nodes[node.id] = node
                if isinstance(raw, dict):
                    rows.append(raw)
        side = _read_edge_file(src.with_name(EDGES_NAME))
        self._edges = side if side is not None else infer_edges(rows)

    def lines(self) -> Iterable[str]:
        """当前全部节点的 jsonl 行（调试/审计用）。"""
        return (n.to_json_line() for n in self._nodes.values())

    # ------------------------------------------------------------------
    # 随身笔记（DESIGN_GRAPH_V4 §3.2）—— `notes.py` 的落盘, 只此三个出口
    # ------------------------------------------------------------------

    def read_notes(self) -> NotesState | None:
        """读笔记缓存; **不存在 / 读不动 → None**（与"读出来是空的"区分, 同 `_read_edge_file`）。"""
        import json
        try:
            raw = json.loads(self.notes_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:          # 坏文件 = 没有（现折一遍就回来）
            logger.warning("笔记缓存读不动（当没有, 会全量重折）: %s", e)
            return None
        return NotesState.from_dict(raw)

    def notes_state(self, events: Iterable[object]) -> NotesState:
        """事件流 → 笔记状态（缓存优先; ⚠️ **读路径不写盘**, 同 `ensure_entities` 那条纪律）。

        - 缓存已覆盖全部 note 操作 ⇒ 直接用（省一次折叠）
        - 否则**增量折叠**（`base` = 缓存）; 缓存丢了/坏了 ⇒ **全量重折**
          —— 两条路结果相同（`notes.fold` 的保证），所以"缓存可重建"这句话是真的
        """
        events = list(events)                        # 可能是一次性可迭代; 下面要走两遍
        newest = max((int(getattr(e, "seq", 0) or 0) for e in events
                      if getattr(e, "type", None) == TYPE_NOTE), default=0)
        cached = self.read_notes()
        if cached is not None and cached.up_to_seq >= newest:
            return cached
        return fold(events, base=cached)

    def save_notes(self, state: NotesState) -> None:
        """原子整写笔记缓存 —— ⚠️ 它**只是派生缓存**（真源 = 事件流的 note 操作）, 删了现折就回来。

        提交点 = **事件 append 之后**（先真源、后缓存）: 反过来写会出现"本子上有、事件流没有"
        —— 那条笔记没有人能重建它。**不并入 `save()`**: 两个写者（图事务 / note 操作）
        各落各的文件, digest 的一次回滚不该把她的本子带走。
        """
        atomic_write_json(self.notes_path, state.to_dict())

    # ------------------------------------------------------------------
    # 图不变量审计（图算法正确性确认——冒烟/R6 完整性检查用）
    # ------------------------------------------------------------------

    # EXT: save-point-r6 — 图不变量审计（冒烟/R6 完整性检查用）; 勿删（docs/EXTENSION_POINTS.md）
    def audit(self) -> list[str]:
        """图不变量审计: 返回违规列表（空 = 干净）。**2026-09-21 G3 起走边表**。

        检查项:
          - **悬空引用**: 边端点必须存在（`add_edge` 已拒; 再出现即 bug 或旧档）
          - **belief 支撑**: 每条 belief 至少 1 条 `supports` 入边 —— 这条从
            `nodes.validate` **搬来**（支撑关系住在边表里, 字段级校验看不见它）

        （删除的两条: "link/contradiction 双向一致" —— 点边分离后无向边不存在,
        那条不变量在构造上不可能被破坏; "count == len(links)" 更早已是派生属性。）
        """
        g = self.graph()
        problems = [f"悬空引用: {e.src} -{e.rel}-> {e.dst}" for e in g.dangling()]
        for nid, node in self._nodes.items():
            if node.kind == "belief" and not g.supporters(nid):
                problems.append(f"belief 无支撑: {nid}")
        return problems


def _read_edge_file(path: Path) -> list[Edge] | None:
    """读边表 → `[Edge]`; **文件不存在 → None**（= 该自举, 与"读出来是空的"区分）。

    坏行逐条丢弃（宁缺勿错）; 指向不存在的点的边**保留**（读侧宽容, 由 audit 报）。
    """
    if not path.is_file():
        return None
    out: list[Edge] = []
    for raw in read_jsonl(path):
        e = Edge.from_dict(raw)
        if e is not None:
            out.append(e)
    return out
