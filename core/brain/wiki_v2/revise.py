"""revise.py — 修订执行器（AGENT_BRAIN.md §5 / 板块 4a 扩展）。

职责: 图语义执行 + 原子性。两个入口:
    apply_revision_package   —— 修订包（revisions 数组, ref 机制）: 深度整理轮用
    apply_decisions          —— Round B 决策表（板块 4a: digest 两轮化的执行器）:
                                touch/update/add 三类行 → 图操作 + history 溯源

不做: 渲染（render.py）· 召回（recall.py）· LLM 契约校验（contract/digest_registry.py
parse 层——结构校验在那; 本文件只管执行语义）· 存储细节（store.py 原语）。

原子性由编排层保证（digest 全程快照, 任一失败 restore_state）; 本文件执行中抛
ValueError → 编排层回滚（宁缺勿错）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.brain.wiki_v2.evolution import EvolutionLog
from core.brain.wiki_v2.graph import REL_SUPPORTS
from core.brain.wiki_v2.nodes import BrainNode, KINDS, make_node
from core.brain.wiki_v2.store import WikiStoreV2
from core.common import err

#: create entry 里 LLM 可用的本地引用（后续动作/链接用 ref 指代新条目）
_REF_KEY = "ref"
#: create entry 里引擎忽略的字段（id/ts 由引擎分配——确定性归引擎）
_IGNORED_ON_CREATE = ("id", "ts")
#: update.patch 允许的字段（图边/epistemic 引擎管理, LLM 不可碰）
_PATCH_FIELDS = ("subject", "text", "significance", "tags", "growth")


@dataclass
class RevisionResult:
    """修订包执行结果。"""

    ok: bool
    errors: list[str] = field(default_factory=list)
    created: dict[str, str] = field(default_factory=dict)   # ref → 真实 id
    pkg: str = ""


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def apply_decisions(
    store: WikiStoreV2,
    rows: list[dict],
    *,
    id_map: dict[str, str],
    log: EvolutionLog | None = None,
    ts: str | None = None,
    event_seq: list[int] | None = None,
) -> list[str]:
    """执行 Round B 决策表（板块 4a）: touch / update / add 行 → 图操作。

    行已过 registry.parse_round_b 结构校验（episode/target 引用、覆盖检查）;
    本函数只做执行语义:
        touch  —— add_link(episode → 认知)（不动原文）
        update —— 部分字段合并（空=保留; patch 白名单）+ **before/after 进 evolution 日志**
                  + 自动链 episode
        add    —— 新建 belief/experience（引擎字段归属）+ 链回 episode

    Args:
        id_map: 渲染本地 id（u0001..）→ 真实节点 id
        ts/event_seq: 引擎字段（digest 上下文; add 建节点用）

    Returns: 新建节点 id 列表。执行中抛 ValueError → 编排层快照回滚。
    """
    log = log or EvolutionLog.for_store(store)
    ts = ts or datetime.now().isoformat(timespec="seconds")
    event_seq = list(event_seq or [])
    created: list[str] = []
    for row in rows:
        ep_id = row["episode"]
        real = id_map.get(row["target"]) if row.get("target") else None
        decision = row["decision"]
        if decision == "touch":
            _ensure_cognition(store, real)
            store.add_edge(REL_SUPPORTS, ep_id, real)
            log.append({"pkg": "digest", "action": "touch", "episode": ep_id,
                        "target": real, "ts": ts})
        elif decision == "update":
            _ensure_cognition(store, real)
            node = store.get(real)
            patch = {k: v for k, v in (row.get("patch") or {}).items()
                     if k in _PATCH_FIELDS and v not in (None, "", [], 0)}
            if not patch:
                # parse 层只查"patch 非空"; 白名单外的字段（如 links/epistemic）
                # 在这里被滤空 → 行无操作 = 静默违约, 宁缺勿错: 整包拒
                raise ValueError(err("BadPatch",
                                     f"update 的 patch 不含可改字段: {sorted((row.get('patch') or {}).keys())}"))
            # 变更审计（2026-09-21）: before/after 落 evolution.jsonl。
            # 原实现是把"改写后的 content"追加进节点字段 `history`——它只写不读,
            # 且记的是**新值**（原文丢失）, 所以那不是一个可用的溯源。审计该待的地方
            # 是 evolution 日志（append-only + 带包归属 + 不进 LLM 上下文）,
            # 形状与修订包路径的 `changed: {k: [before, after]}` 对齐。
            # `changed` 只收**真的变了**的键 ⇒ 崩溃窗口重跑（before == after）
            # 落在日志里就是一个空 dict, 一眼可判"这次没改任何东西"。
            before = {k: getattr(node, k, None) for k in patch
                      if getattr(node, k, None) != patch[k]}
            new = store.update(real, patch)
            store.add_edge(REL_SUPPORTS, ep_id, real)
            log.append({"pkg": "digest", "action": "update", "episode": ep_id,
                        "target": real,
                        "changed": {k: [v, getattr(new, k, None)]
                                    for k, v in before.items()},
                        "ts": ts})
        else:                                   # add
            kind = row.get("kind", "belief")
            fields: dict[str, Any] = {}
            for f in ("subject", "text", "example", "tags",
                      "significance", "growth"):
                v = row.get(f)
                if v not in (None, "", []):
                    fields[f] = v
            if kind == "experience" and fields.get("example"):
                fields["examples"] = [fields.pop("example")]
            node = make_node(kind, **fields)
            # epistemic 引擎归属（LLM 不产——belief 必须是 inferred_belief, 护栏）
            node.epistemic = "inferred_belief" if kind == "belief" else "observed_fact"
            node.ts = ts
            if event_seq:
                node.event_seq = list(event_seq)
            # 崩溃窗口重跑幂等: (kind, event_seq, 主文本) 命中 → 只补链, 不双写
            dup = _find_duplicate(store, node)
            if dup is not None:
                store.add_edge(REL_SUPPORTS, ep_id, dup.id)
                continue
            errors = node.validate()            # supports 边已不在字段校验里（G3）
            if errors:
                raise ValueError(err("InvalidNode",
                                     f"add 节点无效: {'; '.join(errors)}"))
            nid = store.add(node)
            created.append(nid)
            # belief 的支撑不变量（原在 `nodes.validate`: links ≥ 1）—— 现在住在边表,
            # 所以**先入仓再补边**（§2.1: add_edge 拒悬空 ⇒ 点必须先在）
            store.add_edge(REL_SUPPORTS, ep_id, nid)
            log.append({"pkg": "digest", "action": "add", "episode": ep_id,
                        "id": nid, "kind": kind, "ts": ts})
    return created


def _ensure_cognition(store: WikiStoreV2, nid: str | None) -> None:
    """touch/update 的目标必须是 belief/experience 节点（结构保证的兜底）。"""
    if not nid:
        raise ValueError(err("BadTarget", "touch/update 缺 target"))
    node = store.get(nid)
    if node is None or node.kind not in ("belief", "experience"):
        raise ValueError(err("BadTarget", f"target 必须是 belief/experience: {nid!r}"))


def apply_revision_package(
    store: WikiStoreV2,
    revisions: Any,
    *,
    subgraph_ids: set[str] | None = None,
    log: EvolutionLog | None = None,
    dedupe: bool = False,
) -> RevisionResult:
    """校验 + 原子执行一个修订包。

    subgraph_ids: 本次渲染子图的 id 集（规则 1: 引用的 id 必须在此内; None = 全部节点,
    用于深度整理等全量场景）。created 条目可通过 ref 被包内其他动作引用。
    dedupe: 对 create 做 (kind, event_seq, 内容) 去重——命中已存在节点 → ref 指向
    旧 id, 不重复创建（digest 崩溃窗口重跑用: 落盘成功但水位未推进的场景）。
    """
    log = log or EvolutionLog.for_store(store)
    scope = subgraph_ids if subgraph_ids is not None else {n.id for n in store.all()}
    result = RevisionResult(ok=False, pkg=log.next_pkg_id())

    if not isinstance(revisions, list):
        result.errors.append("revisions 必须是数组")
        return result
    if not revisions:
        result.ok = True                    # 空包合法（无值得记的, 深度整理轮同样适用）
        return result

    pending_log: list[dict] = []
    ref_map: dict[str, str] = {}
    # 引用允许集 = 渲染子图 ∪ 包内新建 id（create/merge 产物）——动作可以引用
    # 本包新建的节点（ref 解析后落此集; 集合可变, merge 产物也加入）
    allowed = set(scope)
    snapshot = store.clone_state()           # 原子性: 执行前内存快照

    def fail(msg: str) -> RevisionResult:
        store.restore_state(snapshot)        # 回滚内存（不落盘——磁盘本就是提交态）
        result.errors.append(msg)
        return result

    try:
        # ── pass 1: create（先建, 建立 ref→id 映射）──
        create_i = 0
        for i, raw in enumerate(revisions):
            if not isinstance(raw, dict) or raw.get("action") != "create":
                continue
            # ref 约定在动作顶层（schema v2）; entry 内层兼容; 缺省 → 包内序号兜底
            if not (raw.get("ref")
                    or (isinstance(raw.get("entry"), dict) and raw["entry"].get("ref"))):
                raw = dict(raw)
                raw["ref"] = f"n{create_i + 1}"
            create_i += 1
            node, ref, entry_links = _parse_create(raw, scope, ref_map, result)
            if node is None:
                return fail(f"revisions[{i}] {result.errors[-1]}")
            if dedupe:
                dup = _find_duplicate(store, node)
                if dup is not None:
                    ref_map[ref] = dup.id          # 幂等: 指向已存在节点
                    allowed.add(dup.id)
                    continue
            nid = store.add(node)
            allowed.add(nid)
            ref_map[ref] = nid
            pending_log.append({"pkg": result.pkg, "action": "create",
                                "id": nid, "kind": node.kind})
            # 链接补挂: entry 的 links/contradictions 已在 _parse_create 解析为
            # 真实 id——目标 = 子图已有节点或本包已建节点（存在性检查; 曾误用
            # ref_map 键检查导致链到新建节点时反向边被跳过, 2026-09-02 修复）
            for other in entry_links.get("links", []):
                if store.get(other) is not None:
                    store.add_link(nid, other)
            for other in entry_links.get("contradictions", []):
                if store.get(other) is not None:
                    store.add_contradiction(nid, other)

        # ── pass 2: 其余动作（id 引用解析 ref; allowed 允许引用包内新 id）──
        for i, raw in enumerate(revisions):
            if not isinstance(raw, dict) or raw.get("action") == "create":
                continue
            if not _apply_action(store, raw, allowed, ref_map, pending_log,
                                 result, pkg=result.pkg):
                return fail(f"revisions[{i}] {result.errors[-1]}")
    except Exception as e:                     # noqa: BLE001 — 意外异常同样回滚
        return fail(f"修订执行异常: {e}")

    # ── 包级后检: 连接裁定（规则 7）──
    bad = _connection_rule_violations(store, ref_map)
    if bad:
        return fail("连接裁定: 新 episode 未链接任何 belief/experience——"
                    f"{', '.join(bad)}（必须连已有或新建并链接）")

    # ── 成功: 落 evolution_log（内存暂存, 全过才写）──
    for entry in pending_log:
        log.append(entry)
    result.ok = True
    result.created = dict(ref_map)
    return result


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

def _parse_create(raw: dict, scope: set[str], ref_map: dict,
                  result: RevisionResult) -> tuple[BrainNode | None, str, dict]:
    """解析 create 动作 → (节点, ref, 链接引用)。失败 → (None, …) 并记错误。"""
    entry = raw.get("entry")
    if not isinstance(entry, dict):
        result.errors.append("create 缺少 entry 对象")
        return None, "", {}
    entry = {k: v for k, v in entry.items() if k not in _IGNORED_ON_CREATE}
    # ref 顶层优先（schema v2 约定）; entry 内层兼容; 调用方已兜底序号, 此处防御
    ref = str(raw.get("ref") or entry.pop(_REF_KEY, "") or "").strip()
    if not ref:
        ref = f"n{len(ref_map) + 1}"
    kind = str(entry.pop("kind", "episode")).strip()
    if kind not in KINDS:
        result.errors.append(f"create 的 kind 非法: {kind!r}")
        return None, "", {}
    raw_links = _as_str_list(entry.get("links"))
    raw_contr = _as_str_list(entry.get("contradictions"))
    # 链接引用检查: 只能指子图内 id 或已创建的包内 ref（顺序依赖: 先建先引用）
    for other in raw_links + raw_contr:
        if other not in scope and other not in ref_map:
            result.errors.append(f"create.links 引用了子图外的 id: {other}")
            return None, "", {}
    # ref → 真实 id 就地解析（节点字段里不留 ref）
    entry.pop("links", None)
    entry.pop("contradictions", None)
    node = make_node(kind, **entry)
    node.ts = datetime.now().isoformat(timespec="seconds")
    # ⚠️ 边**不落在节点上**（G4: `links`/`contradictions` 字段已删）——解析好的真实 id
    # 交回调用方, 由它 `store.add_link` / `add_contradiction` 落进边表。
    resolved = {"links": [ref_map.get(x, x) for x in raw_links],
                "contradictions": [ref_map.get(x, x) for x in raw_contr]}
    return node, ref, resolved


# ---------------------------------------------------------------------------
# 其余动作
# ---------------------------------------------------------------------------

def _apply_action(store: WikiStoreV2, raw: dict, scope: set[str],
                  ref_map: dict, pending_log: list[dict],
                  result: RevisionResult, *, pkg: str) -> bool:
    action = raw.get("action")
    resolver = lambda x: ref_map.get(x, x)          # ref → 真实 id
    if action == "update":
        nid = resolver(str(raw.get("id", "")))
        patch = raw.get("patch")
        if not isinstance(patch, dict) or nid not in scope:
            return _err(result, "update 的 id 必须在子图内且 patch 为对象")
        node = store.get(nid)
        if node is None:
            return _err(result, f"update 目标不存在: {nid}")
        # ⚠️ 原"update 不得修改出厂基座（只允许 notes 追加）"守卫 2026-09-21 删——
        # 判据 `is_seed()` 随 `source` 退役（出厂记忆不进 wiki, 见 nodes.py docstring）。
        if "epistemic" in patch and patch["epistemic"] != node.epistemic:
            return _err(result, "update 不得改变 epistemic")
        before = {k: v for k, v in patch.items() if v != getattr(node, k, None)}
        new = store.update(nid, patch)
        pending_log.append({"pkg": pkg, "action": "update", "id": nid,
                            "changed": {k: [before.get(k), getattr(new, k, None)]
                                        for k in before}})
        return True
    if action == "merge":
        ids = [resolver(x) for x in _as_str_list(raw.get("ids"))]
        into = raw.get("into")
        if len(ids) < 2 or not isinstance(into, dict):
            return _err(result, "merge 需要 ≥2 个 ids 和 into 条目")
        if any(i not in scope or store.get(i) is None for i in ids):
            return _err(result, "merge 的 ids 必须在子图内且存在")
        merged = _build_merged(store, ids, into)
        if merged is None:
            return _err(result, "merge: into.kind 缺失且源 kind 不一致")
        merged.ts = datetime.now().isoformat(timespec="seconds")
        new_id = store.add(merged)
        scope.add(new_id)                    # merge 产物可被包内后续动作引用
        # ── 边重接（G3: 边在边表里, 不在节点字段里）──
        # 指向源节点的边**改指产物**（只继承出边会断掉入边的支撑链）, rel 原样保留;
        # 源之间的内部边变自环 → 丢。先收集再删源（delete 会过滤掉所有触及源的边）。
        remap = {i: new_id for i in ids}
        keep: list[tuple[str, str, str]] = []
        for e in store.edges():
            src, dst = remap.get(e.src, e.src), remap.get(e.dst, e.dst)
            if src == dst or (e.rel, src, dst) in keep:
                continue
            keep.append((e.rel, src, dst))
        for i in ids:
            store.delete(i)
        for rel, src, dst in keep:
            store.add_edge(rel, src, dst)
        if not any(e.src == new_id or e.dst == new_id for e in store.edges()):
            return _err(result, "merge 产物必须至少 1 条边（无孤立节点）")
        pending_log.append({"pkg": pkg, "action": "merge",
                            "ids": ids, "into": new_id, "kind": merged.kind})
        return True
    if action == "link":
        a, b = resolver(str(raw.get("from", ""))), resolver(str(raw.get("to", "")))
        if a == b or a not in scope or b not in scope or store.get(a) is None \
                or store.get(b) is None:
            return _err(result, "link 需要子图内两个不同且存在的 id")
        store.add_link(a, b)
        pending_log.append({"pkg": pkg, "action": "link", "a": a, "b": b})
        return True
    if action == "unlink":
        a, b = resolver(str(raw.get("from", ""))), resolver(str(raw.get("to", "")))
        if a not in scope or b not in scope:
            return _err(result, "unlink 的 id 必须在子图内")
        store.remove_link(a, b)
        pending_log.append({"pkg": pkg, "action": "unlink", "a": a, "b": b})
        return True
    if action == "contradict":
        a, b = resolver(str(raw.get("a", ""))), resolver(str(raw.get("b", "")))
        if a == b or a not in scope or b not in scope or store.get(a) is None \
                or store.get(b) is None:
            return _err(result, "contradict 需要子图内两个不同且存在的 id")
        store.add_contradiction(a, b)
        pending_log.append({"pkg": pkg, "action": "contradict", "a": a, "b": b})
        return True
    if action == "resolve":
        a, b = resolver(str(raw.get("a", ""))), resolver(str(raw.get("b", "")))
        if a not in scope or b not in scope:
            return _err(result, "resolve 的 id 必须在子图内")
        store.remove_contradiction(a, b)
        pending_log.append({"pkg": pkg, "action": "resolve", "a": a, "b": b})
        return True
    if action == "accrue":
        return _apply_accrue(store, raw, scope, ref_map, pending_log, result, pkg=pkg)
    return _err(result, f"未知修订动作: {action!r}")


def _apply_accrue(store: WikiStoreV2, raw: dict, scope: set[str],
                  ref_map: dict, pending_log: list[dict],
                  result: RevisionResult, *, pkg: str) -> bool:
    """accrue: 同类事件并入 experience——引擎数 occurrence, 不信任 LLM 的 count。

    证据 episode 由 occurrence.episode_ref（包内新建的 ref）或 occurrence.episode_id
    （子图内已有 id）指定——LLM 不猜 event_seq（引擎从 episode 继承, 防幻觉）。
    应用: add_link(exp, episode) + event_seq 去重并入 + example 追加（cap 3）。
    """
    eid = ref_map.get(str(raw.get("id", "")), str(raw.get("id", "")))
    occ = raw.get("occurrence")
    if eid not in scope or not isinstance(occ, dict):
        return _err(result, "accrue 需要子图内的 experience id 和 occurrence 对象")
    exp = store.get(eid)
    if exp is None or exp.kind != "experience":
        return _err(result, f"accrue 目标必须是 experience 节点: {eid}")
    ep_id = ""
    if occ.get("episode_ref"):
        ep_id = ref_map.get(str(occ["episode_ref"]), "")
    elif occ.get("episode_id"):
        ep_id = str(occ["episode_id"])
    ep = store.get(ep_id) if ep_id else None
    if ep is None or ep.kind != "episode":
        return _err(result,
                    "accrue 必须指向 episode 证据（occurrence.episode_ref 包内 ref "
                    "或 episode_id 子图 id——同类判定必须指向证据）")
    store.add_edge(REL_SUPPORTS, ep.id, eid)          # 经历 → 认知（G3: 边表）
    merged_seq = list(dict.fromkeys(exp.event_seq + ep.event_seq))   # 去重保序
    store.update(eid, {"event_seq": merged_seq})
    if occ.get("example"):
        store.update(eid, {"examples": (exp.examples + [str(occ["example"])])[:3]})
    pending_log.append({"pkg": pkg, "action": "accrue", "id": eid,
                        "episode": ep.id, "event_seq": ep.event_seq})
    return True


def _build_merged(store: WikiStoreV2, ids: list[str], into: dict) -> BrainNode | None:
    """merge 产物: into 字段 + 继承源条目的 `event_seq` 并集。

    ⚠️ **边不在这里继承**（G3）—— 边住在 `edges.jsonl`, 由调用方 remap 端点后重接。
    """
    sources = [store.get(i) for i in ids]
    into = {k: v for k, v in into.items() if k not in _IGNORED_ON_CREATE}
    kind = str(into.get("kind", "")).strip() or (
        sources[0].kind if len({s.kind for s in sources}) == 1 else "")
    if not kind or kind not in KINDS:
        return None
    node = make_node(kind, **{k: v for k, v in into.items() if k != "kind"})
    node.event_seq = sorted({seq for s in sources for seq in s.event_seq})
    node.epistemic = str(into.get("epistemic", "")).strip() or sources[0].epistemic
    return node


# ---------------------------------------------------------------------------
# 包级后检 / 助手
# ---------------------------------------------------------------------------

def _connection_rule_violations(store: WikiStoreV2, ref_map: dict) -> list[str]:
    """规则 7: 每条新 episode 必须与 belief/experience 相连（已有或新建）。

    G3 起"相连"看**边表**（点上的 `links` 已不再被写）。
    """
    created_ids = set(ref_map.values())
    g = store.graph()
    bad: list[str] = []
    for n in store.all():
        if n.id not in created_ids or n.kind != "episode":
            continue
        supported = any(
            store.get(t) is not None and store.get(t).kind in ("belief", "experience")
            for t in g.neighbors(n.id))
        if not supported:
            bad.append(n.id)
    return bad


def _find_duplicate(store: WikiStoreV2, node: BrainNode) -> BrainNode | None:
    """(kind, event_seq 交集, 主文本相同) 去重——digest 崩溃窗口重跑防双写。"""
    if not node.event_seq:
        return None
    main = node.text
    for n in store.all():
        if n.kind != node.kind or not (set(n.event_seq) & set(node.event_seq)):
            continue
        if n.text == main:
            return n
    return None


def _err(result: RevisionResult, msg: str) -> bool:
    result.errors.append(msg)
    return False


def _as_str_list(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, str) and x.strip()]
