"""revise.py — 修订执行器（AGENT_BRAIN.md §5 / 板块 4a 扩展）。

职责: 图语义执行 + 原子性。三个入口:
    apply_revision_package   —— 修订包（revisions 数组, ref 机制）: 深度整理轮用
    apply_decisions          —— Round B 决策表（板块 4a: digest 两轮化的执行器）:
                                touch/update/add 三类行 → 图操作 + history 溯源
    apply_attribution        —— **第 3 轮**决策表（D2b: 归属 + entity 维护）:
                                attach/new_entity/rewrite 三类行 → `about` 边 + entity 载荷

不做: 渲染（render.py）· 召回（recall.py）· LLM 契约校验（contract/digest_registry.py
parse 层——结构校验在那; 本文件只管执行语义）· 存储细节（store.py 原语）。

原子性由编排层保证（digest 全程快照, 任一失败 restore_state）; 本文件执行中抛
ValueError → 编排层回滚（宁缺勿错）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.brain import notes as note_ops
from core.brain.entities import SELF_ID, SENSEI_ID, surface_forms
from core.brain.evolution import EvolutionLog
from core.brain.graph import (
    REL_ABOUT,
    REL_SUPPORTS,
)
from core.brain.nodes import (
    PLAYER_SUBJECT,
    BrainNode,
    KINDS,
    make_node,
)
from core.brain.notes import NotesState
from core.brain.store import WikiStoreV2
from core.common import err

logger = logging.getLogger(__name__)

#: create entry 里 LLM 可用的本地引用（后续动作/链接用 ref 指代新条目）
_REF_KEY = "ref"
#: create entry 里引擎忽略的字段（id/ts 由引擎分配——确定性归引擎）
_IGNORED_ON_CREATE = ("id", "ts")
#: update.patch 允许的字段（图边 / 来源字段由引擎管, LLM 不可碰）
_PATCH_FIELDS = ("subject", "text", "significance", "tags", "growth")
#: `about` 边的可归属 kind（§2: belief → entity · episode → entity）。
#: ⚠️ **含 `experience`**: 今天的"玩家画像"（`subject=player`）就落在它上面, 它显然是
#: "关于老师的"; §9-3 把 experience 并成 `belief + nature=pattern` 之后删掉这一项。
#: ⏸ `promise` 2026-09-29 摘掉（它退出了图 —— 见 `nodes.KINDS`）。
_ATTACHABLE = ("episode", "belief", "experience")
#: hint 写回别名的长度上限 —— 超过这个长度的东西**不是称呼, 是一句话**。
#: （同 `core.parsing.names.MAX_NAME_LEN` 的口径; 本模块**不 import 它** ——
#: `brain` 的运行时依赖要保持纯 stdlib, 而 names 会拖进 yaml。）
MAX_ALIAS_LEN = 8


@dataclass
class RevisionResult:
    """修订包执行结果。"""

    ok: bool
    errors: list[str] = field(default_factory=list)
    created: dict[str, str] = field(default_factory=dict)   # ref → 真实 id
    pkg: str = ""


@dataclass
class ClosureResult:
    """R4 收口的执行结果 —— ⭐ **只剩 note 面**（2026-09-29: 承诺退图）。

    ⏸ 原来还有"节点面"（`nodes` = 固化出来的 promise 节点, 随 digest 事务提交;
      `pairs` = (note id, 节点 id) 对, 给将来的 `retire` 用）—— 那两个字段 2026-09-29
      随退图一起删（promise 退图后**永远为空**, 判据① 没读者就删）。
    ⚠️ 连带: §8 那条"R4 必须排在 R2/R3 之前"的理由（承诺节点要先就位, 后面两轮才好连它）
    **随之消失** —— 编排顺序今天照旧, 但不再是正确性要求。

    ops: 待落库的 note 操作（add 先, close 后）—— **调用方在整批 ok 之后**才 append。
    warnings: 世界校验剔掉的东西（记账）。
    """

    ops: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


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
        link   —— ⭐ **补充边**（§9-13, 2026-09-25）: `{"action":"link","rel","from","to"}`
                  两端是**本地 id**（`u0001..`）—— 让"承诺 → 看法"（`supports`）、
                  "新承诺盖过旧的"（`evolved_from`）、"这两条打架"（`contradicts`）
                  有处可写。⚠️ 这是**决策行之外的第二种行**, 它没有 `episode`,
                  也不参与覆盖统计（`parse_round_b` 已按 `link_ids` 校验过两端）。

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
        if row.get("action") == "link":          # 补充边（没有 episode 字段）
            src, dst = id_map.get(row["from"]), id_map.get(row["to"])
            if not src or not dst:
                # parse 层已按 link_ids 校验; 走到这里 = 调用方与契约不同步（宁缺勿错: 拒）
                raise ValueError(err("BadLink",
                                     f"link 端点解析不出真实 id: {row!r}"))
            store.add_edge(row["rel"], src, dst, ts=ts)     # 幂等 + 拒悬空/自环
            log.append({"pkg": "digest", "action": "link", "rel": row["rel"],
                        "from": src, "to": dst, "ts": ts})
            continue
        ep_id = row["episode"]
        real = id_map.get(row["target"]) if row.get("target") else None
        decision = row["decision"]
        if decision == "touch":
            _ensure_cognition(store, real)
            store.add_edge(REL_SUPPORTS, ep_id, real, ts=ts)
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
            store.add_edge(REL_SUPPORTS, ep_id, real, ts=ts)
            log.append({"pkg": "digest", "action": "update", "episode": ep_id,
                        "target": real,
                        "changed": {k: [v, getattr(new, k, None)]
                                    for k, v in before.items()},
                        "ts": ts})
        else:                                   # add
            kind = row.get("kind", "belief")
            fields: dict[str, Any] = {}
            for f in ("subject", "text", "tags",
                      "significance", "growth"):
                v = row.get(f)
                if v not in (None, "", []):
                    fields[f] = v
            # ⏸ 原 `example → examples` 的映射 **2026-09-29 删** —— 它只在
            # `kind == "experience"` 时生效, 而 `add` 的契约**只许 belief**
            # （`parse_round_b` 直接拒 experience）⇒ 那两行从来没跑到过;
            # 而 belief 那条路把 `example` 原样传进 `make_node`, 又被
            # `from_dict` 静默丢掉（belief 没有 `example`/`examples` 的读者）。
            if kind == "experience":
                # ⚠️ §5.1: `experience` = 玩家画像 ⇒ `subject` **强制** `player`
                # （可见性不许挂在自由文本上; 今天这一路的产品写者已收掉,
                #  但 `apply_revision_package` 等口径仍可能传进来自造的 subject）。
                fields["subject"] = PLAYER_SUBJECT
            node = make_node(kind, **fields)
            # ⏸ 原「epistemic 引擎归属」2026-09-29 删 —— 字段退役;
            # 新认知的"来源"就是**没有 observer**（它由 R2 推出来, 不是听谁说的）。
            node.ts = ts
            if event_seq:
                node.event_seq = list(event_seq)
            # 崩溃窗口重跑幂等: (kind, event_seq, 主文本) 命中 → 只补链, 不双写
            dup = _find_duplicate(store, node)
            if dup is not None:
                store.add_edge(REL_SUPPORTS, ep_id, dup.id, ts=ts)
                continue
            errors = node.validate()            # supports 边已不在字段校验里（G3）
            if errors:
                raise ValueError(err("InvalidNode",
                                     f"add 节点无效: {'; '.join(errors)}"))
            nid = store.add(node)
            created.append(nid)
            # belief 的支撑不变量（原在 `nodes.validate`: links ≥ 1）—— 现在住在边表,
            # 所以**先入仓再补边**（§2.1: add_edge 拒悬空 ⇒ 点必须先在）
            store.add_edge(REL_SUPPORTS, ep_id, nid, ts=ts)
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


# ---------------------------------------------------------------------------
# 第 3 轮: 归属 + entity 维护（D2b —— DESIGN_GRAPH_V4 §8 第 3 轮）
# ---------------------------------------------------------------------------

def apply_attribution(
    store: WikiStoreV2,
    rows: list[dict],
    *,
    id_map: dict[str, str],
    local_of: dict[str, str],
    log: EvolutionLog | None = None,
    ts: str | None = None,
    event_seq: list[int] | None = None,
) -> list[str]:
    """执行第 3 轮决策表（归属 + entity 维护）—— 返回**本次新建的 entity id**。

    三种行（形状见 §8 第 3 轮; 产出它的契约层 = D3）:

        {"action": "attach",     "entity": "c0001", "hint": "老师", "nodes": ["u0001"]}
        {"action": "new_entity", "name": "小玉", "aliases": ["tama"],
                                 "reason": "…", "nodes": ["u0002"]}
        {"action": "rewrite",    "entity": "c0001", "text": "…", "state": ["…"]}

    分工与纪律:
        · `attach`  = 归属的**唯一落地形式**（写 `about` 边）—— **有边 = 归好了,
          没边 = 没归**（§2: `about_state` 三态已退回未定, 判不出就别建边, 也不追踪）。
        · `hint`    = **顺手写回别名**（§3.0: 模型既然判定了"hint 就是这个人",
          写进去是零额外成本 —— 而不是专门造一条别名维护路径）。
        · `rewrite` = **entity 载荷的唯一入口**（§8.1: 写者唯一 = 第 3 轮）。
        · `reason`  = `new_entity` 的**准入门槛**（§3.0: 必须给一句理由）, 空 → 拒。
        · `nodes`  = 这一行要归属的**节点**（本地 id, 同 Round B 的 `u0001`）。新对象
          的正文写在它自己的行里（`new_entity` 没有本地 id 可被 `attach` 引用）。

    Args:
        id_map: 本地节点 id → 真实节点 id（Round B 同款; 引擎防 LLM 猜真实 id）
        local_of: 真实 entity id → 本地 entity id（`entities.candidate_table` 那一份,
            **必须是同一份** —— 换一份就等于换了对象）
        ts/event_seq: 引擎字段（digest 上下文; 新 entity 用）

    ⚠️ **行级违约一律抛**（引用不在候选表里的 entity / 不可归属的 kind / 缺 name /
    缺 reason）—— 与 `apply_decisions` 同款: 编排层有快照, 整包回滚（宁缺勿错）。
    ⚠️ **保留号防撞**（`_entities_ready`）: `self`/`sensei` 不在 → **跳过全部
    `new_entity`** 并打 WARNING（归属与载荷照做）。理由: 空表时 `next_id("x")` 发出的是
    **x0001** —— sensei 的保留号, 谁先建谁占坑（见 `entities.ensure_entities`）。
    ⚠️ `rewrite` 的**空值 = 保留**（同 `apply_decisions` 的 patch 口径）: 今天没有
    "删掉一条 state"的机制（"谁判它过期" = §9-4 未定）⇒ 想删得整段重写。
    """
    log = log or EvolutionLog.for_store(store)
    ts = ts or datetime.now().isoformat(timespec="seconds")
    event_seq = list(event_seq or [])
    by_local = {v: k for k, v in local_of.items()}       # 本地 entity id → 真实 id
    ready = _entities_ready(store)
    created: list[str] = []

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(err("BadRow", f"attributions[{i}] 必须是对象"))
        action = str(row.get("action", "")).strip()
        if action == "attach":
            ent = _resolve_entity(store, row, i, by_local)
            n = _attach_nodes(store, row, i, id_map=id_map, entity_id=ent, ts=ts)
            log.append({"pkg": "digest", "action": "attach", "entity": ent,
                        "nodes": n, "alias": _write_alias(store, ent, row.get("hint")),
                        "ts": ts})
        elif action == "new_entity":
            ent = _new_entity(store, row, i, ready=ready, log=log, ts=ts,
                              event_seq=event_seq, created=created)
            if ent is None:                               # 保留号没就位 → 跳过（已告警）
                continue
            _attach_nodes(store, row, i, id_map=id_map, entity_id=ent, ts=ts)
        elif action == "rewrite":
            _rewrite(store, row, i, by_local, log=log, ts=ts)
        else:
            raise ValueError(err("BadAction", f"attributions[{i}] 未知动作: {action!r}"))
    return created


def _entities_ready(store: WikiStoreV2) -> bool:
    """保留号（`self`/`sensei`）是否已就位。

    ⚠️ 不就位时**不许**建新 entity: `store.next_id("x")` 扫不到同前缀就从 1 起 ⇒
    发出的第一个 id 是 **x0001**, 正是 sensei 的坑位（此后 `ensure_entities` 按 id 判
    幂等 ⇒ sensei 永远不再被建）。生产侧由 `_ensure_char_entities`（D3a）保证先建;
    这条是给"执行器被单独调用"（测试/别的路径）兜的底。
    """
    return SELF_ID in store and SENSEI_ID in store


def _resolve_entity(store: WikiStoreV2, row: dict, i: int,
                    by_local: dict[str, str]) -> str:
    """行里的 `entity`（本地 id）→ 真实 id; 不在候选表里 → 抛。"""
    local = str(row.get("entity", "")).strip()
    real = by_local.get(local)
    node = store.get(real) if real else None
    if node is None or node.kind != "entity":
        raise ValueError(err("BadEntity",
                             f"attributions[{i}] entity 必须是候选表里的本地 id: {local!r}"))
    return real


def _attach_nodes(store: WikiStoreV2, row: dict, i: int, *,
                  id_map: dict[str, str], entity_id: str, ts: str) -> int:
    """把这一行 `nodes` 里的每个节点挂 `about` 边（`add_edge` 幂等 ⇒ 重跑不重复）。"""
    nodes = row.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError(err("BadNodes",
                             f"attributions[{i}] 缺 nodes（要归属的节点本地 id 列表）"))
    n = 0
    for local in nodes:
        real = id_map.get(str(local).strip())
        node = store.get(real) if real else None
        if node is None or node.kind not in _ATTACHABLE:
            raise ValueError(err("BadNode",
                                 f"attributions[{i}] 只能归属 {'/'.join(_ATTACHABLE)}: "
                                 f"{local!r}"))
        store.add_edge(REL_ABOUT, real, entity_id, ts=ts)
        n += 1
    return n


def _write_alias(store: WikiStoreV2, entity_id: str, hint: Any) -> bool:
    """`hint` 顺手写回别名（已是名字/别名 → 不动 = False）。

    ⚠️ 长度上限 `MAX_ALIAS_LEN`: hint 是"我在写谁"的**称呼**; 超长的那种是一句话,
    写进别名只会在下次 `hit_set` 里误命中。
    """
    hint = str(hint or "").strip()
    if not hint or len(hint) > MAX_ALIAS_LEN:
        return False
    node = store.get(entity_id)
    if any(hint.casefold() == f.casefold() for f in surface_forms(node)):
        return False
    store.update(entity_id, {"aliases": [*node.aliases, hint]})
    return True


def _new_entity(store: WikiStoreV2, row: dict, i: int, *, ready: bool,
                log: EvolutionLog, ts: str, event_seq: list[int],
                created: list[str]) -> str | None:
    """建一个新 entity（**带理由**）; 名字/别名已存在 → 复用（崩溃窗口重跑幂等）。

    `created` 只收**真新建**的 id（复用的不进 —— 与 `apply_decisions` 的 add 同口径）。
    """
    name = str(row.get("name", "")).strip()
    reason = str(row.get("reason", "")).strip()
    if not name:
        raise ValueError(err("BadName", f"attributions[{i}] new_entity 缺 name"))
    if not reason:
        raise ValueError(err("NoReason",
                             f"attributions[{i}] new_entity 必须给一句理由"
                             "（§3.0: 三个月后再提到, 需要一致吗？）"))
    if not ready:
        logger.warning("new_entity 跳过（%s）: self/sensei 保留号不在 —— "
                       "空表时 next_id('x') 会发出 x0001（sensei 的坑位）; "
                       "先跑 entities.ensure_entities", name)
        return None
    aliases = [str(a).strip() for a in (row.get("aliases") or []) if str(a).strip()]
    dup = _find_entity(store, name, aliases)
    if dup is not None:
        # 崩溃窗口重跑幂等: 落盘成功但水位未推进 ⇒ 同一个人会被再提一次
        log.append({"pkg": "digest", "action": "new_entity.dup", "id": dup.id,
                    "name": name, "ts": ts})
        return dup.id
    node = BrainNode()
    node.kind = "entity"
    node.name = name
    node.aliases = aliases
    node.text = str(row.get("text", "")).strip()
    node.state = [str(s).strip() for s in (row.get("state") or []) if str(s).strip()]
    node.ts = ts
    if event_seq:
        node.event_seq = list(event_seq)
    errors = node.validate()
    if errors:
        raise ValueError(err("InvalidNode", f"new_entity 无效: {'; '.join(errors)}"))
    nid = store.add(node)
    created.append(nid)
    # 理由进 evolution（append-only + 不进 LLM 上下文）——"为什么它有资格成为对象"
    # 是这条记录唯一的存在理由（§3.0 的准入门槛要留痕才可审）
    log.append({"pkg": "digest", "action": "new_entity", "id": nid, "name": name,
                "reason": reason, "ts": ts})
    return nid


def _find_entity(store: WikiStoreV2, name: str, aliases: list[str]) -> BrainNode | None:
    """按**精确相等**（忽略大小写）在现有 entity 里找同名者（同 `_find_duplicate` 的用途）。

    不做模糊匹配 —— 那是第 3 轮 LLM 的活; 这里只防"同一个人被建两次"。
    """
    want = {f.casefold() for f in (name, *aliases) if f}
    if not want:
        return None
    for n in store.all():
        if n.kind == "entity" and want & {f.casefold() for f in surface_forms(n)}:
            return n
    return None


def _rewrite(store: WikiStoreV2, row: dict, i: int, by_local: dict[str, str], *,
             log: EvolutionLog, ts: str) -> None:
    """重写 entity 载荷（`text` 立场 / `state` 物理状况）—— 空值 = 保留。"""
    real = _resolve_entity(store, row, i, by_local)
    node = store.get(real)
    patch: dict[str, Any] = {}
    if str(row.get("text", "")).strip():
        patch["text"] = str(row["text"]).strip()
    state = [str(s).strip() for s in (row.get("state") or []) if str(s).strip()]
    if state:
        patch["state"] = state
    if not patch:
        raise ValueError(err("BadPatch",
                             f"attributions[{i}] rewrite 没给可改字段（text/state）"))
    before = {k: getattr(node, k, None) for k in patch
              if getattr(node, k, None) != patch[k]}
    new = store.update(real, patch)
    log.append({"pkg": "digest", "action": "rewrite", "id": real,
                "changed": {k: [v, getattr(new, k, None)] for k, v in before.items()},
                "ts": ts})


def apply_closures(
    store: WikiStoreV2,
    rows: list[dict],
    *,
    note_state: NotesState,
    log: EvolutionLog | None = None,
    ts: str | None = None,
) -> ClosureResult:
    """执行 R4 收口决策表（**只记笔记**）—— 见 `DESIGN_GRAPH_V4 §6`。

    两种行（形状见 `contract.digest_registry.parse_close`）::

        {"action": "add",   "text": "周六模型店，有点等不及", "refs": ["m0013"], "due": "…"}
        {"action": "close", "id": "n1", "state": "kept", "refs": ["m0013"],
         "afterwards": "周六真的去了"}

    ⏸ **2026-09-29: 承诺退图**（用户裁决: 承诺太轻, 不足以长期记录）⇒ 本函数**只产
    note 操作**, 不再建节点、不再写任何边。从前那套"`close` = 固化"（promise 节点 +
    `from`/`to`/`formed_by`）连同那三条边一起删掉了; "这条经历里有个约定"今天由
    **`tags`** 承担（筛选用, 不承担路由）。

    分工与纪律:
        · `add`   = 她**此刻还背着**的约定 ⇒ 一条 note 操作（工作记忆）
        · `close` = 结清 ⇒ 一条 `note/close` 操作（含 `state`/`afterwards`）。
          ⚠️ `afterwards`（"后来怎么了"）今天**只活在 note 面**（注入块上那句尾巴）——
          从前它还会并进 promise 节点的正文, 那条路随退图消失。
        · ⚠️ **全部操作交给调用方落库**: 必须等 digest 事务 `ok` 之后才 append
          （事件流 append-only, 提前写就回不去了; 见 `ClosureResult`）。
        · ⚠️ **世界校验剔掉、不拒整包**: 引用指不到的 ⇒ 剔那条 ref; 剔完没 refs 的条目
          整条丢; `close` 指向"不还开着"的条目 ⇒ 丢这一行。都进 `warnings` 记账。
          ⭐ 这一条同时是"同一段里说定又翻篇"那个麻烦的兜底: 那种条目此刻还不在名单里
          （它的编号要等这批 add 落库才发出来）⇒ `close` 指不到它, 只会被丢 + 记账,
          **不会写坏**; 所以 R4 的判据要求"到本段结束还没有下文的约定才写 `add`"。

    Args:
        note_state: 折叠出来的笔记状态（`close.id` 在这里查）
    """
    log = log or EvolutionLog.for_store(store)
    ts = ts or datetime.now().isoformat(timespec="seconds")
    # ⚠️ 2026-10-05 起条目不可能是"已结清但留着"的了（`close` = 划掉即移除）
    open_items = {it.id: it for it in note_state.pinned}
    out = ClosureResult()

    for row in rows:
        action = row.get("action")
        if action == "close":
            _close_one(store, row, open_items, log=log, ts=ts, out=out)
        elif action == "add":
            _add_one(store, row, out)
        else:                                       # 形状错本该在 parse 层拦下
            out.warnings.append(f"未知动作（跳过）: {action!r}")

    return out


def _add_one(store: WikiStoreV2, row: dict, out: ClosureResult) -> None:
    """`add`: 引用剔干净后产一条 note 操作（开放期**不进图**）。"""
    refs: list[str] = []
    for r in row.get("refs") or []:
        node = store.get(r)
        if node is None or node.kind != "episode":
            out.warnings.append(f"add {row.get('text')!r}: 引用不是现存经历 → 剔掉 {r!r}")
            continue
        refs.append(r)
    if not refs:
        out.warnings.append(f"add {row.get('text')!r}: 剔完没有有效引用 → 整条丢")
        return
    out.ops.append(note_ops.add_op(str(row.get("text") or ""), refs,
                                   due=str(row.get("due") or "")))


def _close_one(store: WikiStoreV2, row: dict, open_items: dict,
               *, log: EvolutionLog, ts: str, out: ClosureResult) -> None:
    """`close`: **划掉**一条还开着的约定 —— 产一条 `note/close` 操作（**不碰图**）。

    这里只剩三件事: 查名单 · 核 refs · 产操作。
    ⚠️ `refs`（"了结它的那条经历"）**仍然校验但不落任何边** —— 它留在 note 面,
    将来看"这条约定是被哪段经历了结的"时还查得到（真源 = note 事件）。
    ⚠️ **2026-10-05**: `afterwards` / `state` **不再进 op**（note 面没有读者了 ——
    `close` = 划掉即移除, 那句"后来怎么了"改由**图里那条经历**承担）,
    但它们**仍进 evolution 日志**（审计账, 见下面的 `log.append`）。
    """
    nid = str(row.get("id") or "")
    item = open_items.get(nid)
    if item is None:
        out.warnings.append(f"close {nid!r}: 不在「还开着」的约定里 → 丢这一行")
        return
    closed_by = [r for r in (row.get("refs") or []) if _is_episode(store, r)]
    for r in row.get("refs") or []:
        if r not in closed_by:
            out.warnings.append(f"close {nid!r}: finish episode 不是现存经历 → 剔掉 {r!r}")
    log.append({"pkg": "digest", "action": "close", "note": nid,
                "state": str(row.get("state") or ""), "refs": closed_by, "ts": ts})
    out.ops.append(note_ops.close_op(nid))


def _is_episode(store: WikiStoreV2, nid: Any) -> bool:
    node = store.get(str(nid))
    return node is not None and node.kind == "episode"


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
        # ⏸ 原「update 不得改变 epistemic」2026-09-29 删 —— 字段退役后它就是白名单外
        # 的未知键, `store.update` 的未知字段守卫已经拦得住（错误文案从"不得改变 epistemic"
        # 变成"未知字段", 语义同一条: LLM 不许碰来源）。
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
        # 指向源节点的边**改指产物**（只继承出边会断掉入边的支撑链）; rel 与 **ts**
        # 都原样保留（merge 是端点 remap, 不是"新建一条边"—— 重置时刻会丢掉历史）;
        # 源之间的内部边变自环 → 丢。先收集再删源（delete 会过滤掉所有触及源的边）。
        remap = {i: new_id for i in ids}
        keep: list[tuple[str, str, str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for e in store.edges():
            src, dst = remap.get(e.src, e.src), remap.get(e.dst, e.dst)
            if src == dst or (e.rel, src, dst) in seen:
                continue
            seen.add((e.rel, src, dst))
            keep.append((e.rel, src, dst, e.ts))
        for i in ids:
            store.delete(i)
        for rel, src, dst, ts in keep:
            store.add_edge(rel, src, dst, ts=ts)
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
    # ⏸ 原「epistemic 随赢家继承」2026-09-29 删 —— 字段退役。
    # ⚠️ `observer` **故意不继承**: 合并的语义是"这几条说的是同一件事", 而不是
    # "它们的来源也一样"；真要带来源得由写入方显式给（今天没有这种调用方）。
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
