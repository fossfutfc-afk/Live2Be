"""revise.py — 修订执行器: 图语义 + 原子性。

三趟各一个入口（与 `ROUNDS` 的三轮一一对应）:
    apply_relations   —— L1「判关系」: 四类边 → 边表（**一个字的正文都不写**）
    apply_cognitions  —— L2「造认知 / 写正文」: 造 belief / 覆写沉淀 + 出生自带边
    apply_entities    —— R3「认人」: entity 载荷 + `about` 边

不做: 渲染 · 召回 · 契约的结构校验（`contract/digest/parse.py`）· 存储原语（`store.py`）。

原子性由编排层保证（digest 全程快照, 任一失败 restore_state）; 本文件执行中抛
ValueError → 编排层回滚（宁缺勿错）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from contract.errors import err
from core.brain.entities import (
    SELF_ID,
    SENSEI_ID,
    find_entity,
    form_key,
    normalize_entity_refs,
)
from core.brain.evolution import EvolutionLog
from core.brain.graph import (
    REL_ABOUT,
    REL_AKIN,
    REL_CONTRADICTS,
    REL_EVOLVED_FROM,
    REL_SUPPORTS,
)
from core.brain.nodes import (
    BrainNode,
    make_node,
)
from core.brain.store import WikiStoreV2

logger = logging.getLogger(__name__)

#: create entry 里 LLM 可用的本地引用（后续动作/链接用 ref 指代新条目）
_REF_KEY = "ref"
#: create entry 里引擎忽略的字段（id/ts 由引擎分配——确定性归引擎）
_IGNORED_ON_CREATE = ("id", "ts")
#: `about` 边的可归属 kind（§2: belief → entity · episode → entity · experience → entity）。
#: ⏸ `promise` 2026-09-29 摘掉（它退出了图 —— 见 `nodes.KINDS`）。
#: ⏸ `profile`（玩家画像）**2026-10-14 摘掉** —— 整个 kind 删格式（见 `nodes.KINDS`）。
_ATTACHABLE = ("episode", "belief", "experience")
#: hint 写回别名的长度上限 —— 超过这个长度的东西**不是称呼, 是一句话**。
#: （同 `core.parsing.names.MAX_NAME_LEN` 的口径; 本模块**不 import 它** ——
#: `brain` 的运行时依赖要保持纯 stdlib, 而 names 会拖进 yaml。）
MAX_ALIAS_LEN = 8
#: **`akin` 并边上限**（**每条 belief**）: 一次归纳最多把几条"她认过的同类"并进证据。
#: 为什么需要额度: 并进来的边与她亲手点的证据**在图里同形**（用户 2026-10-13 裁决"接受"）
#: ⇒ 这个数就是"引擎替她说了多少话"的上限。5 ≈ 一次归纳的立足点规模, 且真机全库
#: `akin` 只有 5 条 ⇒ 生产上基本触不到（触到了也只是"少并几条", 不是错）。
AKIN_JOIN_MAX = 5


def apply_relations(store: WikiStoreV2, rows: list[dict], *, ts: str = "",
                    log: EvolutionLog | None = None,
                    id_map: dict[str, str] | None = None) -> list[dict]:
    """**L1（判关系）的落地**: 边行 → 边表 —— **只落边, 一个节点都不建**。

    行形 = `{"rel", "src", "dst", "on"?}`（`digest_registry.parse_relations` 的产出）。

    **两套 id 空间**（与设计 §9.1 逐字一致, 别把这一步当成多余）:
      · 经历 / 对象那一端是**真实 id**（`m…` / `x…` —— 料里就是这么印的）;
      · 认知那一端是**本地号**（`u0001…`, `render_cognition_list` 发的 —— 它的 docstring
        写着"parse 层只认本地 id, 防 LLM 猜真实 id"）。
      ⇒ `id_map`（本地 → 真实）就是这两者之间的那道翻译。
      不在表里的 id **原样过**（真实 id 本来就不在表里）。

    与 `apply_cognitions` 的分工（别混）:
      · 那边 = **认知**（`belief` / `experience`）—— 会**建节点 / 改正文**;
      · 这边 = **关系**（`supports` / `akin` / `contradicts` / `about`）—— **正文一个字都不写**。

    **方向**: `about` 在行里已经归一成"节点 → entity"（`parse_relations` 做的）;
    `akin` / `contradicts` 的对称性由 `store.add_edge` 内部归一（`canonical_for`）——
    这里**不再判方向**（判两遍就是两个真源）。

    `on`（轴上的那个词）**也留痕**: 将来"这个概念是怎么长出来的"要可回溯。

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
        # ⏸ `on`（`akin` 的"那个共同的东西"）2026-10-14 随 `topics` 一起退役 ——
        # 契约不再要它、parse 也不再收（白名单外）⇒ 这一格不再有来源。
        log.append(entry)
        out.append(dict(row))
    return out



@dataclass
class CognitionResult:
    """L2（`cognize`）执行结果 —— 编排层拿去记账。"""

    created: list[str] = field(default_factory=list)
    """本轮**新造**的 belief id（按行序）。"""
    reused: list[str] = field(default_factory=list)
    """幂等命中而**复用**的 id（崩溃窗口重跑: 同一段、`event_seq` 相交、正文又一样）。"""
    strangers: list[str] = field(default_factory=list)
    """看法 `tags` 里那些 `#entity:` **解析不到**的名字（= 还没建的人/地方）——
    它们是**认人那一轮的线索**（`about` 只能指已存在的 id）; 不是错误。"""
    edges: list[dict] = field(default_factory=list)
    """落下的边（原样回传, 编排层记账用）。"""
    soaked: list[str] = field(default_factory=list)
    """**覆写了沉淀**的类 id（同一个类只会有一条 —— 契约层已去重）。"""
    akin_joined: int = 0
    """**引擎并进来的证据边数**（`akin` 一跳邻域 → `supports`; 零 LLM）。
    口径同 `edges=`: 记的是"**这一趟算了 N 条**", 不是"新落了 N 条"
    （重跑窗口里 `add_edge` 幂等, 但账照记 —— 与 `supports` 逐字同口径）。"""
    patched: list[str] = field(default_factory=list)
    """**改过的已有看法**（`id` 在场那一行; 只记**真的写了格子**的那些）。"""
    empty_skips: list[str] = field(default_factory=list)
    """`"<id>:<格>"` —— 键在但值是空 ⇒ **"这一格没话可说"**（不是清空, 同 `settle`）。"""
    watermark_skips: list[str] = field(default_factory=list)
    """`"<id>:text"` —— **水位**挡住的那一格（本段已经写过它, 重跑不许再改一遍）。"""


def apply_cognitions(store: WikiStoreV2, rows: list[dict], *, ts: str = "",
                     log: EvolutionLog | None = None,
                     id_map: dict[str, str] | None = None,
                     event_seq: list[int] | None = None) -> CognitionResult:
    """**L2（造看法 / 写沉淀）的落地** —— 只做三件事, **一个字都不删**。

    行形 = `{"action": "belief" | "experience", …}`（`digest_registry.parse_cognitions` 的产出）。

    | 行 | 做什么 |
    |---|---|
    | `belief` | 造节点（`kind=belief`: 正文 / `subject` / `significance`）+ **出生自带边**: `supports`（经历 → 新看法）· `evolved_from`（**旧看法 → 新看法**）· `contradicts`（对称）· **`akin` 并边**（见下）|
    | `experience` | **覆写**那个类的沉淀正文 —— `title` / `ts` 一律不动（名字是地址, 时间是"这一类事"的时间）|

    **`akin` 并边**（2026-10-13, 零 LLM）: `supports` 落完之后, 把**每条证据的一跳
    `akin` 邻居**也并成这条看法的证据（`_join_akin`, 额度 `AKIN_JOIN_MAX`）。
    它接的是 `experience` 退役留下的那个位置: **"一类事"这个门槛不废、换载体** ——
    从前"一群同类经历 → 一条沉淀", 今天"一群同类经历 → 一条看法", 而"一群"由**她自己
    认过的 `akin`** 说了算。并进来的边与她亲手点的**图里同形**, 只有变更史分得出
    （`"via": "akin"`）—— 这是用户 2026-10-13 的裁决（代价: 她的「被引 N」会变大, 只影响读数）。

    **幂等 = `_find_duplicate`**（`(kind, event_seq 交集, 主文本相同)` ⇒ 复用旧 id,
    不重复创建）—— 与 R1 的 episode **同一个判据、同一个实现**, 不另写一份
    （它是崩溃窗口重跑的防双写网）。
    **两套 id 空间**（同 `apply_relations`）: `supports` 的值是**经历真身**（`m…`,
    料里就是这么印的）; `evolved_from` / `contradicts` 的值是**认知本地号**（`u…`）⇒ 过 `id_map`。
    **方向在这里摆正**（她那一行行首写的是**新**看法, 而图上恒为 **旧 → 新**）:
    `supports` = 经历 → 新看法 · `evolved_from` = **旧看法 → 新看法**（2026-10-14 翻过,
    改过方向; 契约层那一行没变, 只是落边时把两端摆成时间顺向）·
    `contradicts` **对称**（`add_edge` 内部走 `canonical_for`）。
    **改写既有正文必须留痕**（`_soak` 那一段写着口径）:
    `{"action": "rewrite", "id": …, "changed": {"text": [旧, 新]}, "ts": …}` —— 崩溃窗口
    重跑时记的是一个 **空 `changed`**（"这次没改任何东西", 一眼可判; 不是不留账）。
    **不吞错**: 能走到这里说明契约层已经挡过形状问题 ⇒ 剩下的异常都是真 bug,
    照「不吞错」的口径抛（整段回滚 / 只丢自己是编排层的事, 见 `RoundOut`）。
    """
    log = log or EvolutionLog.for_store(store)
    ts = ts or datetime.now().isoformat(timespec="seconds")
    id_map = id_map or {}
    seq = max(event_seq) if event_seq else 0
    res = CognitionResult()
    for row in rows:
        if row.get("action") == "experience":
            _soak(store, row, ts=ts, log=log, res=res)
            continue
        supports = [str(ep) for ep in (row.get("supports") or ())]
        # **排除集要在落 `contradicts` 之前算** —— 那几条边在下面才落（"先落 supports,
        #    再算邻居"是顺序纪律; 而"跟这条看法打架的不算它的证据"这条规则不能等它们落完）。
        blocked = {id_map.get(str(x), str(x)) for x in (row.get("contradicts") or ())}
        bid = str(row.get("id") or "")
        if bid:
            # **改那一路**（`id` 在场）: 只改写出来的格子 + 只加边; 不并 `akin` 邻居。
            _apply_belief_patch(store, row, ts=ts, log=log, res=res, seq=seq)
            for ep in supports:
                _add_edge(store, REL_SUPPORTS, ep, bid, ts=ts, log=log, res=res)
            for other in row.get("contradicts") or ():
                _add_edge(store, REL_CONTRADICTS, bid, id_map.get(str(other), str(other)),
                          ts=ts, log=log, res=res)
            continue
        nid = _create_belief(store, row, ts=ts, log=log,
                             event_seq=event_seq, res=res)
        for ep in supports:
            _add_edge(store, REL_SUPPORTS, ep, nid, ts=ts, log=log, res=res)
        # **她从一条证据看出结论, 引擎把"同一类事"的其他几条也并进来**（零 LLM）
        _join_akin(store, nid, supports, excluded=blocked,
                   ts=ts, log=log, res=res)
        evo = str(row.get("evolved_from") or "")
        if evo:
            # **旧 → 新**（2026-10-14 起）: 她那一行行首是**新**看法, 这里把两端摆正
            _add_edge(store, REL_EVOLVED_FROM, id_map.get(evo, evo), nid,
                      ts=ts, log=log, res=res)
        for other in row.get("contradicts") or ():
            _add_edge(store, REL_CONTRADICTS, nid, id_map.get(str(other), str(other)),
                      ts=ts, log=log, res=res)
    return res


def _akin_neighbors(store: WikiStoreV2, nid: str) -> list[str]:
    """一跳 `akin` 邻居 —— 实现住在图层（`store.related`, 两个方向都算）。

    **为什么要双向**: `akin` 对称、写进去时被 `canonical_for` 归一（`store.add_edge`）
    —— 归一只保证"同一条边不会存两遍", 不保证**起点落在 `src`**。只查 `src == nid`
    会漏掉一半（她指认的那条恰好是 id 小的那个时）, 而漏哪一半取决于**字典序**。
    **只走 `akin`**: 并证据只认"她亲口认过的像"（`walk.py` 的窄门同一条判据）——
    `member_of` 是分类, `supports` 是看法, 都不是"同类"。
    """
    return store.related(nid, REL_AKIN)


def _join_akin(store: WikiStoreV2, nid: str, evidence: list[str], *,
               excluded: set[str], ts: str, log: EvolutionLog,
               res: CognitionResult, cap: int = AKIN_JOIN_MAX) -> list[str]:
    """**把每条已落证据的一跳 `akin` 邻居并进 `supports`**（零 LLM, 返回并进来的 id）。

    这是 `experience`（"一类事"）退役之后**那个门槛的新载体**（用户 2026-10-13 裁:
    "门槛不废换载体 —— `akin` 簇直接对着 belief"）: 从前"一群同类的经历 → 一条沉淀",
    今天"一群同类的经历 → 一条看法", 而"一群"由**她自己认过的 `akin`** 说了算。

    ## 四条纪律（都是判据, 不是实现细节）

    1. **起点只有她写的那几条**（`supports`）—— 绝不把**上一趟并进来的**当起点:
       那会每次重跑都往外长一圈（滚雪球）, 而 `supports` 是幂等的。
    2. **先落 `supports` 再算邻居**: 邻居是"跟她点的证据像的那些", 不是"跟这条看法像的"
       —— 顺序反了就成了拿结论去找证据。
    3. **排除打架的**: 与这条 belief 有 `contradicts` 的（`excluded`）· 与**证据集里任一
       节点**有 `contradicts` 的 —— 后者一条规则同时管住"跟证据打架的"和"两条候选互相
       打架的"（先并进来的那条把后来的挡在门外）。打架的证据**不能**共撑一个结论。
    4. **额度 `cap`**: 见 `AKIN_JOIN_MAX`（超了就少并几条, 不报错、不重试）。

    **只并 `episode`**（`akin` 契约上就是 ep↔ep; 这是防御, 不是判据）。
    **轨迹**: 边本身与她自己点的 `supports` **同形**（用户已接受）⇒ 唯一分得出的是
    `evolution.jsonl` 里那一条多带的 `"via": "akin"`（见 `_add_edge`）。
    """
    have: list[str] = list(evidence)
    joined: list[str] = []
    for ep in evidence:
        for cand in _akin_neighbors(store, ep):
            if len(joined) >= cap:
                break
            node = store.get(cand)
            if node is None or str(node.kind) != "episode":
                continue
            if cand in have or cand in excluded:
                continue
            if any(store.conflicting(cand, other) for other in have):
                continue                                    # 打架的不共撑一个结论
            _add_edge(store, REL_SUPPORTS, cand, nid, ts=ts, log=log, res=res,
                      via="akin")
            joined.append(cand)
            have.append(cand)
        if len(joined) >= cap:
            break
    if joined:
        res.akin_joined += len(joined)
        logger.info("digest_cognize akin_joined=%d belief=%s evidence=%d"
                    "（一跳 akin 并进证据 —— 零 LLM）",
                    len(joined), nid, len(evidence))
    return joined


def _create_belief(store: WikiStoreV2, row: dict, *, ts: str, log: EvolutionLog,
                   event_seq: list[int] | None, res: CognitionResult) -> str:
    """造一条看法（或**复用**同段同正文的那条）—— 返回真实 id。"""
    node = make_node("belief", text=row["text"], subject=row.get("subject", ""),
                     significance=row.get("significance", 0.5),
                     tags=list(row.get("tags", []) or []),
                     entity=list(row.get("entity", []) or []),
                     ts=ts, event_seq=list(event_seq or []))
    dup = _find_duplicate(store, node)
    if dup is not None:
        res.reused.append(dup.id)
        logger.info("digest_cognize reuse=%s（同段 event_seq 相交且正文相同 —— 防双写）",
                    dup.id)
        return dup.id
    nid = store.add(node)
    # 边由**引擎从引用派生**（零 LLM）—— `link_entity_refs` 是唯一实现
    _targets, strangers = link_entity_refs(store, nid, ts=ts)
    res.strangers.extend(strangers)
    res.created.append(nid)
    log.append({"pkg": "digest", "action": "create", "id": nid,
                "text": node.text, "ts": ts})
    return nid


def _apply_belief_patch(store: WikiStoreV2, row: dict, *, ts: str, log: EvolutionLog,
                        res: CognitionResult, seq: int = 0) -> None:
    """**改一条已有的看法**（`id` 在场那一行）—— **只改写出来的格子**。

    四条纪律**照抄 `apply_stances`**（`settle` 那一层立的, 同一个道理）:
      ① **空 = 不改**（键在但值是空串/空数组 ⇒ "这一格没话可说", 不是清空）;
      ② **值没变 ⇒ 不写**（但**照记一笔空 `changed`** —— "这次没改任何东西"一眼可判）;
      ③ **水位只守 `text`**（它是这一层唯一的单槽改写; `tags`/`entity`/`significance`
         天然幂等 —— 同一个值再写一次等于没写）;
      ④ **删不掉东西**: `supports` / `contradicts` 由调用方**只增**（`add_edge` 幂等）。

    **为什么不在这里并 `akin` 邻居**: 并边属于**归纳**（她认了这一簇、正在下结论
    的那一刻, 见 `_join_akin`）—— 而这一行只是"改改说法 / 补一条证据"。
    用户 2026-10-14 裁: *"挂证据不算归纳"*（同 L1 挂证据时不并）。
    """
    bid = str(row["id"])
    node = store.get(bid)
    if node is None:
        raise ValueError(err("BadCognition",
                             f"要改的看法不存在: {bid}（料里刚印过它, 不该消失 —— "
                             "这是引擎侧的 bug）"))
    patch: dict = {}
    changed: dict = {}
    for f in ("text", "subject", "tags", "entity", "significance"):
        if f not in row:
            continue
        new = row[f]
        if f == "text":
            new = str(new or "").strip()
            if not new:                                     # ① 空 = 不改
                res.empty_skips.append(f"{bid}:text")
                continue
            if seq and int(node.text_seq or 0) >= seq:       # ③ 水位
                res.watermark_skips.append(f"{bid}:text")
                logger.info("digest_cognize text_skip=%s 水位 %s ≥ 本段 %s"
                            "（这一段已经改过它了）", bid, node.text_seq, seq)
                continue
        elif f == "significance":
            if new is None:                                  # ① 空 = 不改
                res.empty_skips.append(f"{bid}:{f}")
                continue
        elif not new:                                        # ① "" / [] = 不改
            res.empty_skips.append(f"{bid}:{f}")
            continue
        old = getattr(node, f, None)
        if new == old:                                       # ② 值没变 ⇒ 不写
            continue
        patch[f] = new
        changed[f] = [old, new]
    if patch:
        if "text" in patch:
            patch["text_seq"] = seq                          # 与那句话同住一个原子单位
        store.update(bid, patch)
        res.patched.append(bid)
        logger.info("digest_cognize patch=%s 改了 %s", bid, "、".join(sorted(changed)))
    log.append({"pkg": "digest", "action": "rewrite", "id": bid,
                "changed": changed, "ts": ts})               # 空 changed = 这次没改东西


def _soak(store: WikiStoreV2, row: dict, *, ts: str, log: EvolutionLog,
          res: CognitionResult) -> None:
    """给**已有的类**覆写沉淀正文（不建类、不改名、不动 `ts`）。

    **留痕口径**（这一条是纪律, 不是这段代码的细节）:
    **照记一笔**, 而 `changed` 只收**真的变了**的键 ⇒ 崩溃窗口重跑时留下的是一个
    **空 `changed`**, 一眼可判"这次没改任何东西"（不是"不留账"）。
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
              log: EvolutionLog, res: CognitionResult, via: str = "") -> None:
    """落一条边 + 一条账（形状与 `apply_relations` 逐字相同 —— 同一个含义同一个印法）。

    `via` 只有一处会传: **引擎自己并进来的证据**（`_join_akin` → `"akin"`）。
    为什么只在这一格留痕: 边表（`Edge`）只有 `rel/src/dst/ts`, **图里分不出**"她点的"
    与"引擎并的"（用户 2026-10-13 裁"接受" —— 它们的语义**确实**是同一条: 这条经历撑着
    这条看法）; 而变更史是审计用的, 那里必须分得出是谁的手。
    """
    store.add_edge(rel, src, dst, ts=ts)
    entry: dict = {"pkg": "digest", "action": "relate", "rel": rel,
                   "from": src, "to": dst, "ts": ts}
    if via:
        entry["via"] = via
    log.append(entry)
    res.edges.append(dict(entry))
# ---------------------------------------------------------------------------

def apply_entities(store: WikiStoreV2, rows: list[dict], *, ts: str = "",
                   event_seq: list[int] | None = None,
                   log: EvolutionLog | None = None) -> list[str]:
    """R3（`settle`）的执行器 —— **只认人**（E4, 2026-10-08）。

    把"**她还不认识的名字**"建成 `entity` 节点。**不写正文、不连边**:
      · 归属边（`about`）由**引擎**从节点 `tags` 里的 `#entity:` 派生 —— 这一轮**建完对象
        之后回头补边**（`link_entity_refs`, 同一段内闭合）;
      · entity 的"印象 / 现状"归 **belief** ⇒ 这里一个字都不写（判据见 `DESIGN_ENTITY_TAGS §6.1`）。

    **准入门槛**（旧口径原样保留）: `name` 必填 · **`reason` 必填**（建对象是**永久成本**:
    此后每一轮的候选表里都有它）· **重名不重复建**（名字或别名对得上既有对象 ⇒ 跳过 + 留痕）。
    **保留号防撞**: `self` / `sensei` 不在 ⇒ **跳过全部** —— `next_id("x")` 会发出 `x0001`,
    那是 sensei 的保留号（谁先建谁占坑）。
    **不吞错**: 能走到这里说明契约层已经挡过形状问题 ⇒ 剩下的异常都是真 bug（照「不吞错」的口径抛）。

    Returns: **真新建**的 entity id（重名跳过的**不算**）。
    """
    log = log or EvolutionLog.for_store(store)
    ts = ts or datetime.now().isoformat(timespec="seconds")
    out: list[str] = []
    #: 水位 = **这一段的上界**（`event_seq` 的上界; settle 传 `[ctx.interact_max]`）
    seq = max(event_seq) if event_seq else 0
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
        # **刚认识就有话说 ⇒ 顺手装上第一句看法**（行里带了 `text` 才写; **空 = 不写**）。
        # 「没话说就不写」是常态 —— 别因为这一格可选就把它变成必填。
        text = str(row.get("text", "") or "").strip()
        if text:
            node.text = text
            node.text_seq = seq
        bad = node.validate()
        if bad:
            raise ValueError(err("InvalidNode", f"entities[{i}] 无效: {'; '.join(bad)}"))
        nid = store.add(node)
        out.append(nid)
        log.append({"pkg": "digest", "action": "new_entity", "id": nid, "name": name,
                    "reason": reason, "ts": ts})
        logger.info("digest_settle new_entity=%s name=%r aliases=%s",
                    nid, name, aliases)
    return out


def _entities_ready(store: WikiStoreV2) -> bool:
    """两个**保留号**都在吗（`x0000` 她 / `x0001` 老师）—— 不在就不能建新对象。"""
    return SELF_ID in store and SENSEI_ID in store


@dataclass
class StanceResult:
    """`apply_stances` 的执行结果 —— 编排层拿去记账。"""

    renamed: list[str] = field(default_factory=list)
    """**真改了名**的对象 id（旧主名已降级成别名）。"""
    rewritten: list[str] = field(default_factory=list)
    """**真覆写了看法**的对象 id（一字未变不进这里 —— 同 `soaked_groups` 的口径）。"""
    collisions: list[str] = field(default_factory=list)
    """**撞车被丢掉的改名**（`"x0004:小玉"`）—— 那个名字已经属于**别的**对象（绝不合并）。"""
    empty_skips: list[str] = field(default_factory=list)
    """**空值被当成"不改"而跳过的格**（`"x0001:text"`）—— 见 `apply_stances` 的纪律①:
    `""` 不是"清空", 是"没话可说"。只记账, 不算失败。"""
    watermark_skips: list[str] = field(default_factory=list)
    """**被水位挡下的改写**（`"x0001:text"`）—— 这一段已经写过它了（段级重跑）。"""


def apply_stances(store: WikiStoreV2, rows: list[dict], *, ts: str = "",
                  log: EvolutionLog | None = None,
                  event_seq: list[int] | None = None) -> StanceResult:
    """**`settle`「改已有的对象」的执行器**（2026-10-13）—— **改名 / 写看法**, 一个节点都不建。

    行形 = `{"action": "update", "id", ["name"], ["text"]}`（`parse_attribution` 的产出）。

    | 行里有什么 | 做什么 |
    |---|---|
    | `name` | **改名**: 旧主名**降级成别名**（两个叫法从此都指它）+ 留痕 `rename` |
    | `text` | **写看法**: 覆盖 `entity.text` + 落**水位** `text_seq` + 留痕 `rewrite` |

    ## 四条纪律（每一条都对应一个具体的坏结果）

    ① **空值 = 明确的不改**（用户 2026-10-13 裁）: `{"id": "x0001", "text": ""}`
       是"**这一格没话可说**", **不是"把看法清空"** —— 引擎什么都不做, 只记一笔
       `empty_skips`（不记 `drops`: 这里**没有东西可丢**）。同理 `name: ""` = 不改名。
    ② **改名撞车 ⇒ 丢这一格**（**绝不合并**）: 新名字已经属于**别的**对象 ⇒ 那是
       "把两个人并成一个"、**不可逆**（重复建对象还能合并, 身份并错分不开）——
       只丢 `name`, 同一行的 `text` 照写。
    ③ **值没变 = 不写、不留痕**（同 `_soak` 的口径）: 段级重跑时她上次已经改过 ⇒ 料里印的
       就是新值 ⇒ 她再写同一个 ⇒ 这里 no-op ⇒ **改名天然幂等**（所以它不需要水位）。
    ④ **`text` 要过水位**（它是这一层**唯一不幂等**的写入）: "整段重写"每次措辞都可能不同 ⇒
       段级重跑**不能**再折一遍 —— `最大 event_seq ≤ node.text_seq` ⇒ 那一段已经写过 ⇒
       **丢掉这一格 + 记账**（`watermark_skips`）。水位必须与它守的那句话**同住一个节点**
       （见 `nodes.BrainNode.text_seq` 的注释: 两种失败语义因此都对）。

    **不吞错**: 能走到这里说明契约层已经挡过形状问题 ⇒ 剩下的异常都是真 bug（照「不吞错」抛）。
    """
    log = log or EvolutionLog.for_store(store)
    ts = ts or datetime.now().isoformat(timespec="seconds")
    seq = max(event_seq) if event_seq else 0
    res = StanceResult()
    for i, row in enumerate(rows):
        nid = str(row.get("id", "")).strip()
        node = store.get(nid)
        if node is None:
            raise ValueError(err("BadStance",
                                 f"entities[{i}] 要改的对象不存在: {nid}"
                                 "（料里刚印过它, 不该消失 —— 这是引擎侧的 bug）"))
        # ── 改名 ──
        new_name = str(row.get("name", "") or "").strip()
        if not new_name:
            if "name" in row:                             # 纪律①: 空 = 不改名
                res.empty_skips.append(f"{nid}:name")
        else:
            old = str(node.name or "").strip()
            if form_key(new_name) == form_key(old):
                pass                                      # 纪律③: 值没变 ⇒ 不写、不留痕
            else:
                hit, _why = find_entity(store, new_name)
                if hit is not None and hit.id != nid:
                    res.collisions.append(f"{nid}:{new_name}")    # 纪律②: 只丢这一格
                    logger.warning("digest_settle rename_clash id=%s %r 已属于 %s —— 丢掉这一格",
                                   nid, new_name, hit.id)
                else:
                    aliases = list(node.aliases or [])
                    if old and all(form_key(old) != form_key(a) for a in aliases):
                        aliases.append(old)               # 旧主名降级成别名
                    store.update(nid, {"name": new_name, "aliases": aliases})
                    res.renamed.append(nid)
                    log.append({"pkg": "digest", "action": "rename", "id": nid,
                                "changed": {"name": [old, new_name]}, "ts": ts})
                    logger.info("digest_settle rename=%s %r → %r", nid, old, new_name)
        # ── 写看法 ──
        if "text" not in row:
            continue
        new_text = str(row.get("text", "") or "").strip()
        if not new_text:                                  # 纪律①: 空 = 不改（不是清空）
            res.empty_skips.append(f"{nid}:text")
            continue
        if seq and int(node.text_seq or 0) >= seq:        # 纪律④: 水位
            res.watermark_skips.append(f"{nid}:text")
            logger.info("digest_settle text_skip=%s 水位 %s ≥ 本段 %s（这一段已经写过）",
                        nid, node.text_seq, seq)
            continue
        before = str(node.text or "")
        if before == new_text:                            # 纪律③: 值没变
            log.append({"pkg": "digest", "action": "rewrite", "id": nid,
                        "changed": {}, "ts": ts})
            continue
        store.update(nid, {"text": new_text, "text_seq": seq})
        res.rewritten.append(nid)
        log.append({"pkg": "digest", "action": "rewrite", "id": nid,
                    "changed": {"text": [before, new_text]}, "ts": ts})
        logger.info("digest_settle rewrite=%s（%d → %d 字）", nid, len(before), len(new_text))
    return res


def link_entity_refs(store: WikiStoreV2, nid: str, *, ts: str = ""
                     ) -> tuple[list[str], list[str]]:
    """**一个节点 `entity` 里的引用 ⇒ `about` 边** —— **唯一实现**（引擎派生, 零 LLM）。

    三处调用: R1 造 episode（`episodes._create_a_nodes`）· L2 造看法（`_create_belief`）·
    `settle` **建完新对象之后回头补边**（`rounds/settle.py` —— 它把"先写引用后建对象"接上）。
    做三件事: ① 归一（能解析的叫法换成**主名**）② 落 `about`（节点 → 对象）③ 把归一后的
    引用**写回节点**（她下次看到的与库里一致）。

    **2026-10-13 改口**: 从前它读 `tags` 里的 `#entity:名字`（那时叫 `link_entity_refs`）;
    现在读**独立字段** `node.entity`（名字就是她写的那个叫法）。老档的迁移在
    `nodes.BrainNode.from_dict`。
    `ts` 缺省 = **节点自己的时刻**（不是我落边的时刻）; 幂等靠 `store.add_edge`;
    解析不到的**原样留着**（那是"认人"的线索, 见 `entities.normalize_entity_refs`）。
    **不留 `evolution` 账** —— 边是引用的**派生**（可重建）, 不是她的一个决定。

    Returns: `(落下的对象 id, 解析不到的名字)`。
    """
    node = store.get(nid)
    if node is None:
        return [], []
    refs, targets, strangers = normalize_entity_refs(store, node.entity)
    if refs != list(node.entity or []):
        store.update(nid, {"entity": refs})
    stamp = ts or node.ts
    for eid in targets:
        store.add_edge(REL_ABOUT, nid, eid, ts=stamp)
    return targets, strangers


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


def _as_str_list(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, str) and x.strip()]
