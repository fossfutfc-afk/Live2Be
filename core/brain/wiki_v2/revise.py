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
from core.brain.wiki_v2.nodes import BrainNode, KINDS, make_node
from core.brain.wiki_v2.store import WikiStoreV2
from core.common import err

#: create entry 里 LLM 可用的本地引用（后续动作/链接用 ref 指代新条目）
_REF_KEY = "ref"
#: create entry 里引擎忽略的字段（id/ts 由引擎分配——确定性归引擎）
_IGNORED_ON_CREATE = ("id", "ts")
#: update.patch 允许的字段（图边/epistemic/history 引擎管理, LLM 不可碰）
_PATCH_FIELDS = ("subject", "content", "pattern", "significance", "tags", "growth")


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
    segment_id: str = "",
    event_seq: list[int] | None = None,
) -> list[str]:
    """执行 Round B 决策表（板块 4a）: touch / update / add 行 → 图操作。

    行已过 registry.parse_round_b 结构校验（episode/target 引用、覆盖检查）;
    本函数只做执行语义:
        touch  —— add_link(episode → 认知)（不动原文）
        update —— 部分字段合并（空=保留; patch 白名单）+ content 变更 → history 追加
                  + 自动链 episode
        add    —— 新建 belief/experience（引擎字段归属）+ 链回 episode

    Args:
        id_map: 渲染本地 id（u0001..）→ 真实节点 id
        ts/segment_id/event_seq: 引擎字段（digest 上下文; add 建节点用）

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
            store.add_link(ep_id, real)
            log.append({"pkg": "digest", "action": "touch", "episode": ep_id,
                        "target": real, "ts": ts})
        elif decision == "update":
            _ensure_cognition(store, real)
            node = store.get(real)
            patch = {k: v for k, v in (row.get("patch") or {}).items()
                     if k in _PATCH_FIELDS and v not in (None, "", [], 0)}
            if not patch:
                continue                        # 空 patch 无操作（parse 已警告级放过）
            history = list(node.history)
            new_content = patch.get("content")
            if isinstance(new_content, str) and new_content.strip() \
                    and new_content.strip() != node.content:
                history.append({"episode_id": ep_id, "content": new_content.strip(),
                                "ts": ts})
            if history != node.history:
                patch["history"] = history
            store.update(real, patch)
            store.add_link(ep_id, real)
            log.append({"pkg": "digest", "action": "update", "episode": ep_id,
                        "target": real, "changed": sorted(patch), "ts": ts})
        else:                                   # add
            kind = row.get("kind", "belief")
            fields: dict[str, Any] = {}
            for f in ("subject", "content", "pattern", "example", "tags",
                      "significance", "growth"):
                v = row.get(f)
                if v not in (None, "", []):
                    fields[f] = v
            if kind == "experience" and fields.get("example"):
                fields["examples"] = [fields.pop("example")]
            node = make_node(kind, **fields)
            node.ts = ts
            if segment_id:
                node.segment_id = segment_id
            if event_seq:
                node.event_seq = list(event_seq)
            # 崩溃窗口重跑幂等: (kind, event_seq, 主文本) 命中 → 只补链, 不双写
            dup = _find_duplicate(store, node)
            if dup is not None:
                store.add_link(ep_id, dup.id)
                continue
            errors = node.validate()
            if errors:
                raise ValueError(err("InvalidNode",
                                     f"add 节点无效: {'; '.join(errors)}"))
            nid = store.add(node)
            created.append(nid)
            store.add_link(ep_id, nid)          # 链回 episode（支撑链）
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
        result.ok = True                    # 空包合法（digest_v2 规则 14: 无值得记的）
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
            action = raw.get("action")
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
    node.links = [ref_map.get(x, x) for x in raw_links]
    node.contradictions = [ref_map.get(x, x) for x in raw_contr]
    node.ts = datetime.now().isoformat(timespec="seconds")
    return node, ref, {"links": node.links, "contradictions": node.contradictions}


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
        if node.is_seed() and set(patch) - {"notes"}:
            return _err(result, "update 不得修改出厂基座（只允许 notes 追加）")
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
        if not merged.links:
            return _err(result, "merge 产物必须至少 1 条链接（无孤立节点）")
        merged.ts = datetime.now().isoformat(timespec="seconds")
        new_id = store.add(merged)
        scope.add(new_id)                    # merge 产物可被包内后续动作引用
        # 入边重接: 指向源节点的 link/contradiction 改指 merged——合并 = 源被产物
        # 替代, 图连通性与 belief 支撑不丢（只继承出边会断掉入边的支撑链）
        for other in store.all():
            if other.id == new_id or other.id in ids:
                continue
            had_link = any(i in other.links for i in ids)
            had_contr = any(i in other.contradictions for i in ids)
            if not (had_link or had_contr):
                continue
            other.links = [x for x in other.links if x not in ids]
            other.contradictions = [x for x in other.contradictions if x not in ids]
            if had_link:
                store.add_link(new_id, other.id)
            if had_contr:
                store.add_contradiction(new_id, other.id)
        for i in ids:
            store.delete(i)
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
    store.add_link(eid, ep.id)
    merged_seq = list(dict.fromkeys(exp.event_seq + ep.event_seq))   # 去重保序
    store.update(eid, {"event_seq": merged_seq})
    if occ.get("example"):
        store.update(eid, {"examples": (exp.examples + [str(occ["example"])])[:3]})
    pending_log.append({"pkg": pkg, "action": "accrue", "id": eid,
                        "episode": ep.id, "event_seq": ep.event_seq})
    return True


def _build_merged(store: WikiStoreV2, ids: list[str], into: dict) -> BrainNode | None:
    """merge 产物: into 字段 + 继承源条目的 links/contradictions/event_seq 并集。"""
    sources = [store.get(i) for i in ids]
    into = {k: v for k, v in into.items() if k not in _IGNORED_ON_CREATE}
    kind = str(into.get("kind", "")).strip() or (
        sources[0].kind if len({s.kind for s in sources}) == 1 else "")
    if not kind or kind not in KINDS:
        return None
    node = make_node(kind, **{k: v for k, v in into.items() if k != "kind"})
    node.links = sorted({l for s in sources for l in s.links if l not in ids})
    node.contradictions = sorted(
        {c for s in sources for c in s.contradictions if c not in ids})
    node.event_seq = sorted({seq for s in sources for seq in s.event_seq})
    node.epistemic = str(into.get("epistemic", "")).strip() or sources[0].epistemic
    node.source = "digest"
    return node


# ---------------------------------------------------------------------------
# 包级后检 / 助手
# ---------------------------------------------------------------------------

def _connection_rule_violations(store: WikiStoreV2, ref_map: dict) -> list[str]:
    """规则 7: 每条新 episode 必须 links 含 belief/experience（已有或新建）。"""
    created_ids = set(ref_map.values())
    bad: list[str] = []
    for n in store.all():
        if n.id not in created_ids or n.kind != "episode":
            continue
        supported = any(
            store.get(l) is not None and store.get(l).kind in ("belief", "experience")
            for l in n.links)
        if not supported:
            bad.append(n.id)
    return bad


def _find_duplicate(store: WikiStoreV2, node: BrainNode) -> BrainNode | None:
    """(kind, event_seq 交集, 主文本相同) 去重——digest 崩溃窗口重跑防双写。"""
    if not node.event_seq:
        return None
    main = node.main_text
    for n in store.all():
        if n.kind != node.kind or not (set(n.event_seq) & set(node.event_seq)):
            continue
        if n.main_text == main:
            return n
    return None


def _err(result: RevisionResult, msg: str) -> bool:
    result.errors.append(msg)
    return False


def _as_str_list(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, str) and x.strip()]
