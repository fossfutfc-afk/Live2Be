"""WikiStore v2 — 图式 wiki 的存储（点 / 边两文件 + 笔记缓存）。

职责单一: jsonl 读写 · 原子整写 · id 分配 · 内存索引 · 快照 · 去重水位。
不做: 修订契约的校验与执行（`revise.py`）· 渲染（`read/render.py`）· 召回（`read/recall.py`）。

文件（点边分离）:
    soul/wiki.jsonl    点 —— 一行一条 `BrainNode`（边不写在这里）
    soul/edges.jsonl   边 —— 一行一条 `Edge {rel, src, dst, ts}`
    随身笔记**不在本模块**: 它是事件流的派生物, 由 `notes.fold(events)` 现折（无落盘）。

规则:
    - 写: 内存操作（add / update / delete / add_edge…）→ `save()` 原子整写两个文件
    - 护栏: add / update 前过 `node.validate()`, 无效节点 raise（宁缺勿错）
    - 去重: 水位 `digested_seq`（增量幂等）
    - 自举: 没有 `edges.jsonl` 的旧档 → 载入时从 `links` / `contradictions` 推断出边
      （`graph.infer_edges`）, 下一次 `save()` 落盘 —— 无迁移脚本

两个文件**不是一次事务**（两次 replace）。一致性靠读侧宽容: 边指向不存在的点 → 保留,
但在 `audit()` / `Graph.dangling()` 里可见。写序 = **先点后边** —— 点成功边失败只让边表陈旧
（记忆正文完好, 可重算）; 反过来会留下一批悬空边。
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from contract.errors import err
from core.brain.graph import (
    Edge,
    Graph,
    canonical_for,
    conflicting,
    infer_edges,
    related,
)
from core.brain.nodes import BrainNode, format_id
from core.session.io import atomic_write_json, atomic_write_lines, read_jsonl

logger = logging.getLogger(__name__)

#: kind → id 前缀（relation/fact 已砍, c 前缀退役 2026-09-02）
#: `x0000`（self）/ `x0001`（sensei）是**保留号**, 见 `entities.py` —— `next_id("x")` 因此从 x0002 起。
#: `p`（promise 节点）2026-09-29 **退役** —— promise 退图（见 `nodes.KINDS`）;
#: 旧档里若有 `p…` 行仍读得进（`from_dict` 按 kind 降级成 episode 之外, 不炸）。
#: 2026-10-06 改名: **号段跟着数据走, 不跟着名字走** —— `experience`（经验, 原 `group`）
#: 沿用 `g`（老 `g…` 语义不变）。
#: `e`（原 `profile` 玩家画像）**2026-10-14 随那个 kind 一起退役** —— 旧档里若有
#: `e…` 行仍读得进（`from_dict` 对认不出的 kind 降级成 episode, 不炸）。
#: `p` 不能用: 承诺退图后 `test_promise_prefix_is_gone` 钉着"不许再有 `p` 号";
#: 前缀不许撞车（只有 `m` 可共用, 见 `test_every_kind_has_an_explicit_id_prefix`）
#: —— **必须显式登记**: `add()` 走
#: `_PREFIX.get(kind, "m")`，漏了会拿到 `m` 号并与 episode/belief **撞号**。
_PREFIX = {"experience": "g", "episode": "m", "belief": "m", "entity": "x"}

#: 节点字段白名单（update patch 只接受这些——防任意字段注入）
_FIELDS = set(BrainNode.__dataclass_fields__.keys())

#: 边表文件名（与 wiki.jsonl 同目录 —— 记忆层自包含, §0.1）
EDGES_NAME = "edges.jsonl"
#: 提交日志（两阶段提交的中间态: 点 + 边 + meta 一次写全, 再逐份应用）
TXN_NAME = "wiki.txn.json"

#: **内存态快照**（点 + 边）—— `clone_state` 交出、`restore_state` 原样吃回。
#: 两边用同一个形状才有意义: 回滚漏拷边 = 边上留着、点没了（悬空 + "回滚没回干净"）。
Snapshot = tuple[dict[str, BrainNode], list[Edge]]


class WikiStoreV2:
    """图式 wiki 存储（per 世界线, 单文件 jsonl）。"""

    def __init__(self, data_root: str | Path = "data", *,
                 world_id: str = "world1", char_id: str = "",
                 path: str | Path | None = None):
        # soul/ = 记忆层子目录（角色目录下开 soul 收编记忆
        # 子系统——events 原材料 + wiki 成品 + 变更史 + 出厂快照自包含; 会话层
        # meta/progress/sessions 留在 characters/{char}/ 原地）
        self.path = Path(path) if path is not None else (
            Path(data_root) / "worlds" / world_id / "characters"
            / char_id / "soul" / "wiki.jsonl")
        #: 边表（点边分离的另一半 —— **2026-09-21 G3 起边的唯一落盘处**）
        self.edges_path = self.path.with_name(EDGES_NAME)
        self.meta_path = self.path.with_name("wiki.meta.json")
        #: 提交日志路径（加载时若残留 ⇒ 补完那次提交, 见 `_roll_forward`）
        self.txn_path = self.path.with_name(TXN_NAME)
        #: 世界根定位
        self._data_root = Path(data_root)
        self._world_id = world_id
        self._roll_forward()                     # 上次提交写到一半 ⇒ 先补完它
        self.meta: dict = self._load_meta()
        self._nodes: dict[str, BrainNode] = {}
        self._edges: list[Edge] = []
        self._load()
        self._heal_watermark()

    # ------------------------------------------------------------------
    # 提交（两阶段: 先写日志, 再应用）
    # ------------------------------------------------------------------

    def commit(self) -> None:
        """⭐ **一次提交** —— 点 + 边 + meta 三份文件要么全变、要么全不变。

        做法: 先把三份内容**一次性原子写**进 `wiki.txn.json`, 再逐份覆盖真文件, 最后删日志。
        任何一步之后被杀, 下次加载 `_roll_forward` 都会照日志把三份补齐 —— 所以不存在
        "图新、水位旧"（那会让同一批事件被再喂一遍 ⇒ 重复记忆）也不会"边新、点旧"。

        代价: 每次提交多写一份同样大小的日志（今天 wiki 才几十 KB; 这是买"提交不可分割"）。
        """
        payload = {
            "v": 1,
            "nodes": [n.to_json_line() for n in self._nodes.values()],
            "edges": [e.to_json_line() for e in self._edges],
            "meta": dict(self.meta),
        }
        atomic_write_json(self.txn_path, payload, indent=0)
        self._apply_txn(payload)
        try:
            self.txn_path.unlink()
        except OSError as e:                     # 删不掉也无害: 下次加载会重放同一份
            logger.warning("提交日志删除失败（下次加载会重放它）: %s", e)

    def _apply_txn(self, payload: dict) -> None:
        """把日志内容写进三份真文件（点 → 边 → meta; 三份都是原子整写）。"""
        atomic_write_lines(self.path, payload["nodes"])
        atomic_write_lines(self.edges_path, payload["edges"])
        meta = payload.get("meta")
        atomic_write_json(self.meta_path, meta if isinstance(meta, dict) else self.meta)

    def _roll_forward(self) -> None:
        """加载时补完上一次被打断的提交（**幂等**: 重放同一份日志结果不变）。"""
        import json

        try:
            raw = json.loads(self.txn_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            logger.warning("提交日志读不出来（丢弃它, 以现有文件为准）: %s", e)
            self.txn_path.unlink(missing_ok=True)
            return
        if not isinstance(raw, dict) or not isinstance(raw.get("nodes"), list):
            logger.warning("提交日志形状不对（丢弃它）: %s", self.txn_path)
            self.txn_path.unlink(missing_ok=True)
            return
        logger.warning("补完上次被打断的提交: %d 个节点 / %d 条边",
                       len(raw["nodes"]), len(raw.get("edges") or []))
        self._apply_txn(raw)
        self.txn_path.unlink(missing_ok=True)

    def _heal_watermark(self) -> None:
        """把水位从"图上实际覆盖到哪"自愈一次（**只在加载时**, 只改内存, 不写盘）。

        为什么需要: 一次提交是"先 `save()` 图、后 `save_meta()`"两次原子替换。中间被
        进程杀掉（Ctrl+C / 崩溃 / 任务管理器）就成了**图新、水位旧** —— 下一段的取窗
        判据是 `seq > 水位`（排他）, 于是同一批事件被再喂一遍; 正文略有不同就多出一份
        记忆（`revise._find_duplicate` 只在事件 seq 相交且正文相同时才复用旧 id）。

        图里的 `event_seq` 本来就是"她覆盖过"的事实, 取大者即恢复正确水位。
        **只在加载时做**: 进程内的 `meta` 改动（测试、探针）应当照原样生效。
        **绝不落盘**: 探针按只读口径打开 wiki, 加载期写入就是污染真机数据。
        """
        covered = max((max(n.event_seq) for n in self._nodes.values() if n.event_seq),
                      default=0)
        saved = self.digested_seq                    # 脏 meta（非数字）在这里已经按 0 处理
        if covered > saved:
            logger.warning("digest 水位自愈: meta=%s → 图上覆盖=%d"
                           "（上一次提交在两次写盘之间被打断）", saved, covered)
            self.meta["digested_seq"] = covered

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

        G4 起自举吃的是**原始行**（`graph.infer_edges(rows)`）而不是节点对象 ——
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

        原"出厂基座只允许 notes 追加"守卫（SeedImmutable）2026-09-21 删——
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
    # 边—— **2026-09-21 G3 起边的唯一真源**
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

        有向 rel（`supports` / `about` / `member_of` / `evolved_from`）别用它。
        """
        return related(self._edges, nid, rel)

    def conflicting(self, a: str, b: str) -> bool:
        """`a` 与 `b` 是否互相打架（`contradicts`, **对称 ⇒ 两个方向都算**）。"""
        return conflicting(self._edges, a, b)

    def add_edge(self, rel: str, src: str, dst: str, *, ts: str = "") -> None:
        """加一条类型化边（幂等: 同 `(rel, src, dst)` 已存在则跳过）。

        **两端必须存在**（悬空即拒）——"悬空引用在构造上不可能存在"（§2.1）
        靠的就是写路径在这里关门; 读路径（`_load_edges`）相反, **宽容保留**,
        因为那是旧档（宽容读 ≠ 允许写坏）。

        **对称 rel 先规范化**（2026-09-29 N1a）: `contradicts` / `akin` 走
        `graph.canonical_for`（对称性的**唯一实现处**）—— 必须在幂等检查**之前**,
        否则 `akin(B, A)` 与 `akin(A, B)` 会被当成两条边各写一条。

        `ts` = 这条边**建立**的时刻。不给 → 取当下（2026-09-22: 原先默认空串, 结果
        写路径产的边全没有 ts —— 真机一轮后 `edges.jsonl` 里一半有、一半没有）。
        调用方知道更准的时刻就显式传（digest 传的是**本段日期**, 不是"写库时刻"）。
        读侧不编: 旧档边表里没有 `ts` 的仍保持空串（哨兵纪律）。
        """
        if src not in self._nodes or dst not in self._nodes:
            raise ValueError(err("DanglingEdge",
                                 f"边端点不存在: {src} -{rel}-> {dst}"))
        if src == dst:
            raise ValueError(err("SelfEdge", f"边不能自环: {src}"))
        src, dst = canonical_for(rel, src, dst)      # 幂等检查之前
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
        """整写点 + 边（= `commit()`, 连 meta 一起进同一个事务）。

        随身笔记**不在这里**（它是事件流的派生物, 没有可写的缓存）。
        """
        self.commit()

    def clone_state(self) -> Snapshot:
        """深拷贝当前**点 + 边**（修订包/digest 的原子性快照——revise.py 用）。

        **边必须一起拷**: 只拷点的话, 失败回滚会把这一轮新加的边**留在原地**
        （节点没了边还在 ⇒ 悬空 + "回滚没回干净"）。节点会被原地铁改（add_edge 等）,
        所以点也要深拷贝而非浅拷 dict。

        **两边都走 `from_dict(to_dict())`，不手抄字段**（2026-09-29 N1a 修）:
        边原来是 `Edge(e.rel, e.src, e.dst, e.ts)` —— **位置参数**，给 `Edge` 加字段时
        会**静默丢掉**那个字段（而它是 digest 事务回滚的基础 ⇒ 回滚把状态回成"少了一半属性"）。
        与点侧同一写法之后，"加字段忘了改这里"这一类 bug 在**构造上**不可能存在。
        守门用例: `tests/core/test_wiki_store.py::test_clone_state_copies_edges_field_complete`
        （含一条**结构性**断言: 本函数源码里不许再出现 `Edge(`）。
        """
        clones = (Edge.from_dict(e.to_dict()) for e in self._edges)
        return ({nid: BrainNode.from_dict(n.to_dict()) for nid, n in self._nodes.items()},
                [e for e in clones if e is not None])

    def restore_state(self, state: Snapshot) -> None:
        """恢复内存态（点 + 边; 回滚用——不落盘, 调用方决定是否 save）。"""
        self._nodes, self._edges = state

    # EXT: save-point-r6 — 存档点语义（R6 未落地）; 勿删（docs/EXTENSION_POINTS.md）
    def snapshot_to(self, dest: str | Path) -> None:
        """快照 = **点 + 边**两个文件（`dest` 是点表路径, 边表 = 同目录 `edges.jsonl`）。

        R6 存档点语义: 自包含。**只写点的话, 快照回来的记忆是断连的**
        （entity 车道 / 支撑链全空）——而边是可重算的派生物,
        点不是, 所以快照必须两样都带。
        **随身笔记不进快照**: 它是事件流的派生物, 而快照不带事件流 ——
        单独带上它只会造出"半个世界"（本子指着的世界已经不在快照里了）。
        """
        dest = Path(dest)
        atomic_write_lines(dest, (n.to_json_line() for n in self._nodes.values()))
        atomic_write_lines(dest.with_name(EDGES_NAME),
                           (e.to_json_line() for e in self._edges))

    # EXT: save-point-r6 — 存档点语义（R6 未落地）; 勿删（docs/EXTENSION_POINTS.md）
    def restore_from(self, src: str | Path) -> None:
        """从快照恢复（点 + 同目录边表; 调用方随后 save() 落盘）。

        无边界表的**旧快照** → 从点上残留的旧字段自举（宽容读）。不改编
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
