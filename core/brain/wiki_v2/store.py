"""WikiStore v2 — 图式 wiki 存储（AGENT_BRAIN.md §2 / M1b）。

职责（单一）: jsonl 读写 + 原子整写 + id 分配 + 内存索引 + 快照 + 去重检查。
不做: 修订契约校验/执行（revise.py）· 渲染（render.py）· 召回（recall.py）·
      出厂 digest（seed.py）——引擎侧流程在 revise.py 编排。

规则:
    - 文件: data/worlds/{world}/characters/{char}/wiki.jsonl（一行一条 BrainNode）
    - 写: 内存操作（add/update/delete/link…）→ save() 原子整写（temp + os.replace）
    - 护栏: add/update 前过 node.validate()——无效节点拒绝（宁缺勿错, raise）
    - 去重: find_by_event_seq（(kind, event_seq) 键——同事件重复消化去重）
    - id: 前缀 + 4 位零填充（m=动态 episode/belief/relation, c=出厂基座, e=experience）
    - 快照: snapshot_to/restore_from = 整文件复制（R6 存档快照语义）
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from core.brain.wiki_v2.nodes import BrainNode, format_id
from core.common import err
from core.session.io import atomic_write_json, atomic_write_lines, read_jsonl

logger = logging.getLogger(__name__)

#: kind → id 前缀（AGENT_BRAIN.md §2; relation/fact 已砍——c 前缀退役 2026-09-02）
_PREFIX = {"experience": "e", "episode": "m", "belief": "m"}

#: 节点字段白名单（update patch 只接受这些——防任意字段注入）
_FIELDS = set(BrainNode.__dataclass_fields__.keys())


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
        self.meta_path = self.path.with_name("wiki.meta.json")
        #: 世界根定位
        self._data_root = Path(data_root)
        self._world_id = world_id
        self.meta: dict = self._load_meta()
        self._nodes: dict[str, BrainNode] = {}
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

    def _world_has_history(self) -> bool:
        """该角色线是否已有记忆（有节点或有水位即算）。"""
        return bool(self._nodes) or self.digested_seq > 0

    # ------------------------------------------------------------------
    # 载入 / 查询
    # ------------------------------------------------------------------

    def _load(self) -> None:
        for raw in read_jsonl(self.path):
            node = BrainNode.from_dict(raw)
            if node.id and not node.validate():      # 坏条目跳过（宁缺勿错）
                self._nodes[node.id] = node

    def get(self, nid: str) -> BrainNode | None:
        return self._nodes.get(nid)

    def all(self) -> list[BrainNode]:
        """全部节点（插入序 = 创建序）。"""
        return list(self._nodes.values())

    def by_kind(self, kind: str) -> list[BrainNode]:
        return [n for n in self._nodes.values() if n.kind == kind]

    def find_by_event_seq(self, kind: str, seq: int) -> BrainNode | None:
        """去重检查（AGENT_BRAIN.md §2）: 同 (kind, event_seq) 已存在 → 该事件已消化。"""
        for n in self._nodes.values():
            if n.kind == kind and seq in n.event_seq:
                return n
        return None

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

        入仓前 normalize——create 路径的 links 可能在构造后才补挂
        （revise._parse_create）, 不变量（experience.count = len(links)）必须入仓时钉死。
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
        """打补丁更新（patch 键必须是节点字段; 出厂基座只允许 notes 追加）。返回新节点。"""
        node = self._nodes.get(nid)
        if node is None:
            raise KeyError(err("NotFound", f"节点不存在: {nid}"))
        unknown = set(patch) - _FIELDS
        if unknown:
            raise ValueError(err("BadPatch", f"未知字段: {sorted(unknown)}"))
        if node.is_seed() and set(patch) - {"notes"}:
            raise ValueError(err("SeedImmutable",
                                 "出厂基座不可改——只允许 notes 追加（§5 规则 2）"))
        new = BrainNode.from_dict({**node.to_dict(), **patch})
        if node.is_seed() and patch.get("notes"):
            new.notes = node.notes + [str(patch["notes"])]
        errors = new.validate()
        if errors:
            raise ValueError(err("InvalidNode",
                                 f"更新后节点无效: {'; '.join(errors)}"))
        new.normalize()                        # 维护不变量（experience.count = len(links) 等）
        self._nodes[nid] = new
        return new

    def delete(self, nid: str) -> bool:
        """删除节点 + 清理入边（返回是否存在）。

        邻接表策略的闭环: 他人 links/contradictions 里指向被删节点的悬空 id
        一并清除——merge 删源/R6 回滚后不留死引用（组织视图不出现幽灵 id,
        revise 的"不存在"报错只可能是真幻觉）。
        """
        if nid not in self._nodes:
            return False
        self._nodes.pop(nid)
        for node in self._nodes.values():
            if nid in node.links:
                node.links.remove(nid)
            if nid in node.contradictions:
                node.contradictions.remove(nid)
        return True

    # ── 图边原语（虚边操作; 校验在 revise.py 的引用级, 这里只保证存在性） ──

    def add_link(self, a: str, b: str) -> None:
        """双向 link（无向边; 已存在则幂等）。

        边变化会破坏 experience.count = len(links) 不变量——受影响端点立即刷新
        （accrue/包内后建节点链入等路径都在这里闭环, audit 恒干净）。
        """
        for src, dst in ((a, b), (b, a)):
            node = self._nodes.get(src)
            if node is not None and dst not in node.links and dst in self._nodes:
                node.links.append(dst)
                if node.kind == "experience":
                    node.count = len(node.links)

    def remove_link(self, a: str, b: str) -> None:
        for src, dst in ((a, b), (b, a)):
            node = self._nodes.get(src)
            if node is not None and dst in node.links:
                node.links.remove(dst)
                if node.kind == "experience":
                    node.count = len(node.links)

    def add_contradiction(self, a: str, b: str) -> None:
        """双向 contradiction（已存在则幂等）。"""
        for src, dst in ((a, b), (b, a)):
            node = self._nodes.get(src)
            if node is not None and dst not in node.contradictions and dst in self._nodes:
                node.contradictions.append(dst)

    def remove_contradiction(self, a: str, b: str) -> None:
        for src, dst in ((a, b), (b, a)):
            node = self._nodes.get(src)
            if node is not None and dst in node.contradictions:
                node.contradictions.remove(dst)

    # ------------------------------------------------------------------
    # 持久化 / 快照
    # ------------------------------------------------------------------

    def save(self) -> None:
        """原子整写全部节点（temp + os.replace, 绝不半写）。"""
        atomic_write_lines(self.path, (n.to_json_line() for n in self._nodes.values()))

    def reload(self) -> None:
        """丢弃内存改动, 从磁盘重载（磁盘 = 最近一次 save 的提交态）。"""
        self._nodes = {}
        self._load()

    def clone_state(self) -> dict[str, BrainNode]:
        """深拷贝当前节点集（修订包执行前的原子性快照——revise.py 用）。

        节点会被原地铁改（add_link 等）, 所以必须深拷贝而非浅拷贝 dict。
        """
        return {nid: BrainNode.from_dict(n.to_dict()) for nid, n in self._nodes.items()}

    def restore_state(self, state: dict[str, BrainNode]) -> None:
        """恢复内存态（回滚用; 不落盘——调用方决定是否 save）。"""
        self._nodes = state

    # EXT: save-point-r6 — 存档点语义（R6 未落地）; 勿删（docs/EXTENSION_POINTS.md）
    def snapshot_to(self, dest: str | Path) -> None:
        """快照 = 复制当前全部节点到 dest（R6 存档点语义: 自包含）。"""
        atomic_write_lines(Path(dest), (n.to_json_line() for n in self._nodes.values()))

    # EXT: save-point-r6 — 存档点语义（R6 未落地）; 勿删（docs/EXTENSION_POINTS.md）
    def restore_from(self, src: str | Path) -> None:
        """从快照恢复（替换内存; 调用方随后 save() 落盘）。"""
        self._nodes = {}
        for raw in read_jsonl(Path(src)):
            node = BrainNode.from_dict(raw)
            if node.id and not node.validate():
                self._nodes[node.id] = node

    def lines(self) -> Iterable[str]:
        """当前全部节点的 jsonl 行（调试/审计用）。"""
        return (n.to_json_line() for n in self._nodes.values())

    # ------------------------------------------------------------------
    # 图不变量审计（图算法正确性确认——冒烟/R6 完整性检查用）
    # ------------------------------------------------------------------

    # EXT: save-point-r6 — 图不变量审计（冒烟/R6 完整性检查用）; 勿删（docs/EXTENSION_POINTS.md）
    def audit(self) -> list[str]:
        """图不变量审计: 返回违规列表（空 = 干净）。

        检查项（邻接表策略的闭环定义）:
          - 悬空引用: links/contradictions 目标必须存在（delete 已清入边, 再出现即 bug）
          - 双向一致: 无向边两端共识（a.links 含 b ⇔ b.links 含 a; contradiction 同款）
          - count 不变量: experience.count == len(links)（引擎计数, update 后 normalize）
          - belief 支撑: belief.links ≥ 1（删除路径可能抽走最后支撑——审计检出）
        """
        problems: list[str] = []
        for nid, node in self._nodes.items():
            for other in node.links + node.contradictions:
                if other not in self._nodes:
                    problems.append(f"悬空引用: {nid} → {other}")
            for other in node.links:
                if other in self._nodes and nid not in self._nodes[other].links:
                    problems.append(f"link 非双向: {nid} ↔ {other}")
            for other in node.contradictions:
                if other in self._nodes \
                        and nid not in self._nodes[other].contradictions:
                    problems.append(f"contradiction 非双向: {nid} ↔ {other}")
            if node.kind == "experience" and node.count != len(node.links):
                problems.append(f"count 不变量破坏: {nid} count={node.count} "
                                f"links={len(node.links)}")
            if node.kind == "belief" and not node.links:
                problems.append(f"belief 无支撑链接: {nid}")
        return problems
