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

from core.brain.entities import SELF_ID, SENSEI_ID, find_entity, normalize_entity_tags
from core.brain.evolution import EvolutionLog
from core.brain.graph import (
    REL_ABOUT,
    REL_CONTRADICTS,
    REL_EVOLVED_FROM,
    REL_SUPPORTS,
)
from core.brain.nodes import (
    KINDS,
    PLAYER_SUBJECT,
    BrainNode,
    make_node,
)
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
_ATTACHABLE = ("episode", "belief", "profile")
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


def apply_relations(store: WikiStoreV2, rows: list[dict], *, ts: str = "",
                    log: EvolutionLog | None = None,
                    id_map: dict[str, str] | None = None) -> list[dict]:
    """⭐ **L1（判关系）的落地**: 边行 → 边表 —— **只落边, 一个节点都不建**。

    行形 = `{"rel", "src", "dst", "on"?}`（`digest_registry.parse_relations` 的产出）。

    ⚠️ **两套 id 空间**（与设计 §9.1 逐字一致, ⛔ 别把这一步当成多余）:
      · 经历 / 对象那一端是**真实 id**（`m…` / `x…` —— 料里就是这么印的）;
      · 认知那一端是**本地号**（`u0001…`, `render_cognition_list` 发的 —— 它的 docstring
        写着"parse 层只认本地 id, 防 LLM 猜真实 id"）。
      ⇒ `id_map`（本地 → 真实）就是这两者之间的那道翻译, 与 `apply_decisions` 同构。
      不在表里的 id **原样过**（真实 id 本来就不在表里）。

    与 `apply_decisions` 的分工（⛔ 别混）:
      · 那边 = **决策表**（`touch`/`update`/`add`）—— 会**建节点 / 改正文**;
      · 这边 = **关系**（`supports`/`akin`/`contradicts`/`about`）—— **正文一个字都不写**。

    ⚠️ **方向**: `about` 在行里已经归一成"节点 → entity"（`parse_relations` 做的）;
    `akin` / `contradicts` 的对称性由 `store.add_edge` 内部归一（`canonical_for`）——
    这里**不再判方向**（判两遍就是两个真源）。

    ⚠️ `on`（轴上的那个词）**也留痕**: 将来"这个概念是怎么长出来的"要可回溯。

    Args:
        id_map: **本地号 → 真实 id**（`{"u0001": "m0031"}`）。缺省 `None` = 两端
            本来就是真实 id（单测 / 将来 L2 若直接印真实 id 也走这条）。

    Returns: 落下的那些行（原样回传, 编排层拿去记账）。
    """
    log = log or EvolutionLog.for_store(store)
    ts = ts or datetime.now().isoformat(timespec="seconds")
    out: list[dict] = []
    for row in rows:
        rel, src, dst = row["rel"], row["src"], row["dst"]
        if id_map:                                    # 本地号 → 真实 id（真实 id 原样过）
            src, dst = id_map.get(src, src), id_map.get(dst, dst)
        store.add_edge(rel, src, dst, ts=ts)          # 幂等 + 拒悬空 / 拒自环
        entry: dict = {"pkg": "digest", "action": "relate", "rel": rel,
                       "from": src, "to": dst, "ts": ts}
        if row.get("on"):
            entry["on"] = row["on"]
        log.append(entry)
        out.append(dict(row))
    return out



@dataclass
class CognitionResult:
    """L2（`cognize`）执行结果 —— 编排层拿去记账。"""

    created: list[str] = field(default_factory=list)
    """本轮**新造**的 belief id（按行序）。"""
    reused: list[str] = field(default_factory=list)
    """⭐ 幂等命中而**复用**的 id（崩溃窗口重跑: 同一段、`event_seq` 相交、正文又一样）。"""
    strangers: list[str] = field(default_factory=list)
    """看法 `tags` 里那些 `#entity:` **解析不到**的名字（= 还没建的人/地方）——
    ⚠️ 它们是**认人那一轮的线索**（`about` 只能指已存在的 id）; 不是错误。"""
    edges: list[dict] = field(default_factory=list)
    """落下的边（原样回传, 编排层记账用）。"""
    soaked: list[str] = field(default_factory=list)
    """**覆写了沉淀**的类 id（同一个类只会有一条 —— 契约层已去重）。"""


def apply_cognitions(store: WikiStoreV2, rows: list[dict], *, ts: str = "",
                     log: EvolutionLog | None = None,
                     id_map: dict[str, str] | None = None,
                     event_seq: list[int] | None = None) -> CognitionResult:
    """⭐ **L2（造看法 / 写沉淀）的落地** —— 只做三件事, **一个字都不删**。

    行形 = `{"action": "belief" | "experience", …}`（`digest_registry.parse_cognitions` 的产出）。

    | 行 | 做什么 |
    |---|---|
    | `belief` | 造节点（`kind=belief`: 正文 / `subject` / `significance`）+ **出生自带边**: `supports`（经历 → 新看法）· `evolved_from`（新看法 → 旧看法）· `contradicts`（对称）|
    | `experience` | **覆写**那个类的沉淀正文 —— ⛔ `title` / `ts` 一律不动（名字是地址, 时间是"这一类事"的时间）|

    ⚠️ **幂等 = `_find_duplicate`**（`(kind, event_seq 交集, 主文本相同)` ⇒ 复用旧 id,
    不重复创建）—— 与 R1 的 episode **同一个判据、同一个实现**, ⛔ 不另写一份
    （崩溃窗口重跑防双写; 见 `apply_revision_package` 的 `dedupe=`）。
    ⚠️ **两套 id 空间**（同 `apply_relations`）: `supports` 的值是**经历真身**（`m…`,
    料里就是这么印的）; `evolved_from` / `contradicts` 的值是**认知本地号**（`u…`）⇒ 过 `id_map`。
    ⚠️ **方向不再判**（契约层已归一）: `supports` = 经历 → 新看法 · `evolved_from` =
    新看法 → 旧看法 · `contradicts` **对称**（`add_edge` 内部走 `canonical_for`）。
    ⚠️ **改写既有正文必须留痕**（同 `_rewrite` / `apply_decisions` 的 update 行）:
    `{"action": "rewrite", "id": …, "changed": {"text": [旧, 新]}, "ts": …}` —— 崩溃窗口
    重跑时记的是一个 **空 `changed`**（"这次没改任何东西", 一眼可判; ⛔ 不是不留账）。
    ⚠️ **不吞错**: 能走到这里说明契约层已经挡过形状问题 ⇒ 剩下的异常都是真 bug,
    照 `_rewrite` 的口径抛（整段回滚 / 只丢自己是编排层的事, 见 `RoundOut`）。
    """
    log = log or EvolutionLog.for_store(store)
    ts = ts or datetime.now().isoformat(timespec="seconds")
    id_map = id_map or {}
    res = CognitionResult()
    for row in rows:
        if row.get("action") == "experience":
            _soak(store, row, ts=ts, log=log, res=res)
            continue
        nid = _create_belief(store, row, ts=ts, log=log,
                             event_seq=event_seq, res=res)
        for ep in row.get("supports") or ():
            _add_edge(store, REL_SUPPORTS, str(ep), nid, ts=ts, log=log, res=res)
        evo = str(row.get("evolved_from") or "")
        if evo:
            _add_edge(store, REL_EVOLVED_FROM, nid, id_map.get(evo, evo),
                      ts=ts, log=log, res=res)
        for other in row.get("contradicts") or ():
            _add_edge(store, REL_CONTRADICTS, nid, id_map.get(str(other), str(other)),
                      ts=ts, log=log, res=res)
    return res


def _create_belief(store: WikiStoreV2, row: dict, *, ts: str, log: EvolutionLog,
                   event_seq: list[int] | None, res: CognitionResult) -> str:
    """造一条看法（或**复用**同段同正文的那条）—— 返回真实 id。"""
    node = make_node("belief", text=row["text"], subject=row.get("subject", ""),
                     significance=row.get("significance", 0.5),
                     tags=list(row.get("tags", []) or []),
                     ts=ts, event_seq=list(event_seq or []))
    dup = _find_duplicate(store, node)
    if dup is not None:
        res.reused.append(dup.id)
        logger.info("digest_cognize reuse=%s（同段 event_seq 相交且正文相同 —— 防双写）",
                    dup.id)
        return dup.id
    nid = store.add(node)
    # ⭐ 边由**引擎从 tag 派生**（零 LLM）—— `link_entity_tags` 是唯一实现
    _targets, strangers = link_entity_tags(store, nid, ts=ts)
    res.strangers.extend(strangers)
    res.created.append(nid)
    log.append({"pkg": "digest", "action": "create", "id": nid,
                "text": node.text, "ts": ts})
    return nid


def _soak(store: WikiStoreV2, row: dict, *, ts: str, log: EvolutionLog,
          res: CognitionResult) -> None:
    """给**已有的类**覆写沉淀正文（⛔ 不建类、不改名、不动 `ts`）。

    ⚠️ **留痕口径照 `apply_decisions` 的 update 行**（那里写着这条纪律）:
    **照记一笔**, 而 `changed` 只收**真的变了**的键 ⇒ 崩溃窗口重跑时留下的是一个
    **空 `changed`**, 一眼可判"这次没改任何东西"（⛔ 不是"不留账"）。
    `res.soaked` 只收**真变了**的那些（它是"覆写了"的账, 不是"收到过这一行"的账）。
    """
    gid = str(row["group"])
    node = store.get(gid)
    if node is None:
        raise ValueError(err("BadSoak", f"要写沉淀的类不存在: {gid}"))
    new_text = str(row["text"]).strip()
    before = node.text
    changed = before != new_text
    if changed:
        store.update(gid, {"text": new_text})
        res.soaked.append(gid)
    log.append({"pkg": "digest", "action": "rewrite", "id": gid,
                "changed": {"text": [before, new_text]} if changed else {},
                "ts": ts})


def _add_edge(store: WikiStoreV2, rel: str, src: str, dst: str, *, ts: str,
              log: EvolutionLog, res: CognitionResult) -> None:
    """落一条边 + 一条账（形状与 `apply_relations` 逐字相同 —— 同一个含义同一个印法）。"""
    store.add_edge(rel, src, dst, ts=ts)
    entry = {"pkg": "digest", "action": "relate", "rel": rel,
             "from": src, "to": dst, "ts": ts}
    log.append(entry)
    res.edges.append(dict(entry))


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
            # `kind == "profile"` 时生效, 而 `add` 的契约**只许 belief**
            # （`parse_round_b` 直接拒 experience）⇒ 那两行从来没跑到过;
            # 而 belief 那条路把 `example` 原样传进 `make_node`, 又被
            # `from_dict` 静默丢掉（belief 没有 `example`/`examples` 的读者）。
            if kind == "profile":
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
    if node is None or node.kind not in ("belief", "profile"):
        raise ValueError(err("BadTarget", f"target 必须是 belief/experience: {nid!r}"))


# ---------------------------------------------------------------------------
# 第 3 轮: 归属 + entity 维护（D2b —— DESIGN_GRAPH_V4 §8 第 3 轮）
# ---------------------------------------------------------------------------

def apply_entities(store: WikiStoreV2, rows: list[dict], *, ts: str = "",
                   event_seq: list[int] | None = None,
                   log: EvolutionLog | None = None) -> list[str]:
    """R3（`attribute`）的执行器 —— ⭐ **只认人**（E4, 2026-10-08）。

    把"**她还不认识的名字**"建成 `entity` 节点。⛔ **不写正文、不连边**:
      · 归属边（`about`）由**引擎**从节点 `tags` 里的 `#entity:` 派生 —— 这一轮**建完对象
        之后回头补边**（`link_entity_tags`, 同一段内闭合）;
      · entity 的"印象 / 现状"归 **belief** ⇒ 这里一个字都不写（判据见 `DESIGN_ENTITY_TAGS §6.1`）。

    ⚠️ **准入门槛**（旧口径原样保留）: `name` 必填 · **`reason` 必填**（建对象是**永久成本**:
    此后每一轮的候选表里都有它）· **重名不重复建**（名字或别名对得上既有对象 ⇒ 跳过 + 留痕）。
    ⚠️ **保留号防撞**: `self` / `sensei` 不在 ⇒ **跳过全部** —— `next_id("x")` 会发出 `x0001`,
    那是 sensei 的保留号（谁先建谁占坑）。
    ⚠️ **不吞错**: 能走到这里说明契约层已经挡过形状问题 ⇒ 剩下的异常都是真 bug（照 `_rewrite` 的口径抛）。

    Returns: **真新建**的 entity id（重名跳过的**不算**）。
    """
    log = log or EvolutionLog.for_store(store)
    ts = ts or datetime.now().isoformat(timespec="seconds")
    out: list[str] = []
    if not _entities_ready(store):
        logger.warning("apply_entities 跳过: self/sensei 保留号不在 —— "
                       "next_id('x') 会撞上保留号（先跑 ensure_entities）")
        return out
    for i, row in enumerate(rows):
        name = str(row.get("name", "")).strip()
        if not name:
            raise ValueError(err("BadName", f"entities[{i}] 缺 name"))
        reason = str(row.get("reason", "")).strip()
        if not reason:
            raise ValueError(err("NoReason",
                                 f"entities[{i}] 必须给一句理由（建对象是永久成本）"))
        aliases = _as_str_list(row.get("aliases"))
        dup, _why = find_entity(store, name)
        if dup is not None:
            logger.info("apply_entities 已有同名对象, 不重复建: %s（%s）—— 那一行丢",
                        name, dup.id)
            log.append({"pkg": "digest", "action": "new_entity.dup", "id": dup.id,
                        "name": name, "ts": ts})
            continue
        node = make_node("entity", name=name, aliases=aliases, ts=ts)
        node.event_seq = list(event_seq or [])
        bad = node.validate()
        if bad:
            raise ValueError(err("InvalidNode", f"entities[{i}] 无效: {'; '.join(bad)}"))
        nid = store.add(node)
        out.append(nid)
        log.append({"pkg": "digest", "action": "new_entity", "id": nid, "name": name,
                    "reason": reason, "ts": ts})
        logger.info("digest_attribute new_entity=%s name=%r aliases=%s",
                    nid, name, aliases)
    return out


def _entities_ready(store: WikiStoreV2) -> bool:
    """两个**保留号**都在吗（`x0000` 她 / `x0001` 老师）—— 不在就不能建新对象。"""
    return SELF_ID in store and SENSEI_ID in store


def link_entity_tags(store: WikiStoreV2, nid: str, *, ts: str = ""
                     ) -> tuple[list[str], list[str]]:
    """⭐ **一个节点 `tags` 里的 `#entity:` ⇒ `about` 边** —— **唯一实现**（引擎派生, 零 LLM）。

    三处调用: R1 造 episode（`episodes._create_a_nodes`）· L2 造看法（`_create_belief`）·
    R3 **建完新对象之后回头补边**（`rounds/attribute.py` —— 它把"先写 tag 后建对象"接上）。
    做三件事: ① 归一（能解析的叫法换成**主名**）② 落 `about`（节点 → 对象）③ 把归一后的
    `tags` **写回节点**（她下次看到的与库里一致）。

    ⚠️ `ts` 缺省 = **节点自己的时刻**（不是我落边的时刻）; 幂等靠 `store.add_edge`;
    ⚠️ 解析不到的**原样留着**（那是"认人"的线索, 见 `entities.normalize_entity_tags`）。
    ⛔ **不留 `evolution` 账** —— 边是 tag 的**派生**（可重建）, 不是她的一个决定。

    Returns: `(落下的对象 id, 解析不到的名字)`。
    """
    node = store.get(nid)
    if node is None:
        return [], []
    tags, targets, strangers = normalize_entity_tags(store, node.tags)
    if tags != list(node.tags or []):
        store.update(nid, {"tags": tags})
    stamp = ts or node.ts
    for eid in targets:
        store.add_edge(REL_ABOUT, nid, eid, ts=stamp)
    return targets, strangers


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
    """accrue: 同类事件并入 profile（玩家画像）——引擎数 occurrence, 不信任 LLM 的 count。

    证据 episode 由 occurrence.episode_ref（包内新建的 ref）或 occurrence.episode_id
    （子图内已有 id）指定——LLM 不猜 event_seq（引擎从 episode 继承, 防幻觉）。
    应用: add_link(exp, episode) + event_seq 去重并入 + example 追加（cap 3）。
    """
    eid = ref_map.get(str(raw.get("id", "")), str(raw.get("id", "")))
    occ = raw.get("occurrence")
    if eid not in scope or not isinstance(occ, dict):
        return _err(result, "accrue 需要子图内的 experience id 和 occurrence 对象")
    exp = store.get(eid)
    if exp is None or exp.kind != "profile":
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
    """规则 7: 每条新 episode 必须与 belief/profile 相连（已有或新建）。

    G3 起"相连"看**边表**（点上的 `links` 已不再被写）。
    """
    created_ids = set(ref_map.values())
    g = store.graph()
    bad: list[str] = []
    for n in store.all():
        if n.id not in created_ids or n.kind != "episode":
            continue
        supported = any(
            store.get(t) is not None and store.get(t).kind in ("belief", "profile")
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
