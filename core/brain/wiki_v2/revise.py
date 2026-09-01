"""revise.py — 修订契约（AGENT_BRAIN.md §5 / M2b）。

职责: 校验 + 原子执行 LLM 输出的修订包（revisions 数组）, 成功时写 evolution_log。
不做: 渲染（render.py）· 召回（recall.py）· 存储细节（store.py 原语）。

流程（引擎侧）:
    1. 全量校验（规则 1~8, 见 AGENT_BRAIN.md §5）——任一违反 → 整包拒绝
    2. 执行（create 先过, 建立 ref→id 映射; 其余按序）——store 原语异常 → reload 回滚
    3. 包级后检: 连接裁定（规则 7）
    4. 成功 → evolution_log 落盘（内存暂存, 成功才追加）; 调用方随后 store.save()

原子性: 磁盘文件 = 提交前状态（save 由调用方在成功后执行）——
执行中任何失败 → store.reload() 丢弃内存改动, 零残留（宁缺勿错）。
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
    snapshot = store.clone_state()           # 原子性: 执行前内存快照

    def fail(msg: str) -> RevisionResult:
        store.restore_state(snapshot)        # 回滚内存（不落盘——磁盘本就是提交态）
        result.errors.append(msg)
        return result

    try:
        # ── pass 1: create（先建, 建立 ref→id 映射）──
        for i, raw in enumerate(revisions):
            if not isinstance(raw, dict) or raw.get("action") != "create":
                continue
            node, ref, entry_links = _parse_create(raw, scope, ref_map, result)
            if node is None:
                return fail(f"revisions[{i}] {result.errors[-1]}")
            if dedupe:
                dup = _find_duplicate(store, node)
                if dup is not None:
                    ref_map[ref] = dup.id          # 幂等: 指向已存在节点
                    continue
            nid = store.add(node)
            ref_map[ref] = nid
            pending_log.append({"pkg": result.pkg, "action": "create",
                                "id": nid, "kind": node.kind})
            # 链接补挂（entry 里的 links/contradictions 引用, 含 ref）
            for other in entry_links.get("links", []):
                if other in scope or other in ref_map:
                    store.add_link(nid, other)
            for other in entry_links.get("contradictions", []):
                if other in scope or other in ref_map:
                    store.add_contradiction(nid, other)

        # ── pass 2: 其余动作（id 引用解析 ref）──
        for i, raw in enumerate(revisions):
            if not isinstance(raw, dict) or raw.get("action") == "create":
                continue
            action = raw.get("action")
            if not _apply_action(store, raw, scope, ref_map, pending_log,
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
    ref = str(entry.pop(_REF_KEY, "")).strip()
    ref = ref or f"n{len(result.created) + 1}"     # 缺省本地引用名
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
    main = _main_text(node)
    for n in store.all():
        if n.kind != node.kind or not (set(n.event_seq) & set(node.event_seq)):
            continue
        if _main_text(n) == main:
            return n
    return None


def _main_text(node: BrainNode) -> str:
    """节点主文本（去重比较用）: episode→narration, experience→pattern, 其余→content。"""
    if node.kind == "episode":
        return node.narration
    if node.kind == "experience":
        return node.pattern
    if node.kind == "relation":
        return f"{node.subject}|{node.object}|{node.relation}"
    return node.content


def _err(result: RevisionResult, msg: str) -> bool:
    result.errors.append(msg)
    return False


def _as_str_list(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, str) and x.strip()]
