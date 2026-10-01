# -*- coding: utf-8 -*-
"""groups.py — **L2-a 分群**: 引擎切块 → 一轮 LLM 起名 → 群节点 + `member_of` 边（N7, 2026-09-29）。

## 这一步在整条链里的位置

    她（MMT）── `{"noticed": "…"}` ──→ `noticed` 事件 ──(L1)──→ **`akin` 边**（她连的两件事）
                                                                    │
    digest 每段的**最后一步** ◀──────────────────────────────────────┘
      `ungrouped()` → `build_blocks()` → 一轮 LLM（**只起名**）→ `apply_groups()` → **群节点 + `member_of`**

⭐ **为什么切块是引擎的活**: `akin` 是**她的原始发现**（"这两条像"）—— 有噪音、可能只是两两。
把它原样当"组"喂给 LLM 就是把她的噪音当成结论。引擎只干一件事: 把**连通块**切出来,
⭐ **边不进视野**（她连的先后、连了几条, 与"这块叫什么"无关）。

⭐ **为什么锚点兜底不做**（原设计有, 这里**有意留白**）: 锚点（同 tag / 同对象）选不好会造出
**假块** ⇒ 假群 ⇒ 将来 `ignite`（N8）为它写一条**假 belief**。落单的事继续等 —— 她下段真连上
一个同伴, 它自然成块（**增量天然成立**）。判据 = 宁缺勿错 > 覆盖率。

## 它**不**做什么

- **不判"像不像"** —— 那是她那一轮的活; 这里只问"这块叫什么"。
- **不产 belief** —— 那是 L2-b `ignite`（N8）。
- **不做 `merge`（群撞群）** —— 那要 LLM 判"名字同义", 是下一刀; 但 ⭐ **同名即并**在这里做
  （`apply_groups`）: 它是同一个病最便宜的那一半。
- **不进她的视图** —— `PROCEED §2 #2`: 群上不放关键信息, 判断归 belief（写两处必漂）。
  这一刀的全部产出**只在图上**。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

from core.brain.wiki_v2 import marks
from core.brain.wiki_v2.address import find_group, normalize_title, unique_title
from core.brain.wiki_v2.graph import REL_AKIN, REL_MEMBER_OF, iter_edges
from core.brain.wiki_v2.nodes import make_node

if TYPE_CHECKING:                       # 仅注解求值期可见（避免运行时循环导入）
    from core.brain.wiki_v2.store import WikiStoreV2

logger = logging.getLogger(__name__)

#: 一次最多发**几块**（超出的下一段再来 —— 增量的, 不丢东西）
MAX_BLOCKS = 6
#: 一块最多摆几条成员（头里的「N 条」是**真实总数**, 这里只管摆几条）
MAX_BLOCK_MEMBERS = 8
#: 「已有的类」最多摆几个（按"最近有成员"排 —— 她此刻在碰的那些类才相关;
#: ⚠️ 没摆出来的类**不会**因此被重复建: `apply_groups` 的同名闸兜着）
MAX_GROUPS_SHOWN = 12
#: 每个类最多摆几条成员
MAX_GROUP_MEMBERS = 4
#: 正文截断: 块里的给宽一点（那是要被起名的货）, 类里的只要"这个类长什么样"
BODY_BLOCK = 60
BODY_GROUP = 40

_INDENT = "  "


@dataclass(frozen=True)
class Block:
    """一个块 = 引擎切的**同类候选**（她连过的几件事）。

    `bid` 是**本次调用的把手**（`b1`…）—— ⚠️ 它**不是节点 id**, 只在这一轮有效
    （下一次调用重新发号, 所以块与把手**没有长期对应关系**）。
    """

    bid: str
    episodes: tuple[str, ...]            # 真 id（按 ts 升序）


@dataclass
class GroupApplyResult:
    """分群执行的结果（记账; 不阻断 —— 见 `apply_groups`）。"""

    nodes: list[str] = field(default_factory=list)       # 新建的群节点 id
    grouped: list[str] = field(default_factory=list)     # 挂上类的 episode（去重保序）
    edges: int = 0                                       # 真写进去的 `member_of` 条数
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 引擎切块（0 LLM）
# ---------------------------------------------------------------------------

def _key(store: WikiStoreV2, nid: str) -> tuple[str, str]:
    """排序键 = `(ts, id)` —— 无 ts 的排最前（同"一条河"的哨兵纪律, 不编时刻）。"""
    node = store.get(nid)
    return ((node.ts or "") if node is not None else "", nid)


def ungrouped(store: WikiStoreV2) -> list[str]:
    """**还没有类**的 episode id（按 ts 升序）—— 归过群的直接出局（增量就靠这一条）。

    判据 = 它有没有出边 `member_of`（边方向是 `episode → group`）。
    """
    g = store.graph()
    out = [n for n in store.all()
           if n.kind == "episode" and n.id and not g.targets(n.id, REL_MEMBER_OF)]
    return [n.id for n in sorted(out, key=lambda n: (n.ts or "", n.id))]


def build_blocks(store: WikiStoreV2, cand: Iterable[str],
                 *, max_blocks: int = MAX_BLOCKS) -> list[Block]:
    """未归群的 episode → **`akin` 连通块**（≥2 条才算块; 新块先发）。

    ⚠️ **只认 `akin`**（她连过的）—— 见模块 docstring 那条"锚点兜底有意不做"。
    ⚠️ 落单的**不进块**（也**不进料**）: 一次调用只为"能起名的块"付钱。
    """
    ids = [i for i in cand if store.get(i) is not None]
    in_play = set(ids)
    adj: dict[str, set[str]] = {i: set() for i in ids}
    for e in iter_edges(store, rel=REL_AKIN):
        if e.src in in_play and e.dst in in_play and e.src != e.dst:
            adj[e.src].add(e.dst)
            adj[e.dst].add(e.src)

    comps: list[list[str]] = []
    seen: set[str] = set()
    for i in ids:
        if i in seen or not adj[i]:
            continue
        stack, comp = [i], []
        seen.add(i)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nb in sorted(adj[cur]):
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        if len(comp) >= 2:
            comps.append(sorted(comp, key=lambda x: _key(store, x)))
    # 新的块先发（记忆是"最近的事先组织"）—— 超上限的那些**留着**, 下段再来
    comps.sort(key=lambda c: _key(store, c[-1]), reverse=True)
    return [Block(bid=f"b{k}", episodes=tuple(c))
            for k, c in enumerate(comps[:max_blocks], start=1)]


# ---------------------------------------------------------------------------
# 渲染（料; 头一律走 `marks.head` = 括号的唯一实现）
# ---------------------------------------------------------------------------

def _split_members(ids: list[str], cap: int) -> tuple[list[str], list[str], int]:
    """要摆出来的成员: **最早 2 条 + 最新 (cap-2) 条**, 中间略过。

    类是从某处长起来的 —— **两头都要看得见**（origin 说明它本来指什么, 最新说明它现在指什么）;
    只取最新会把"这一类最初是哪件事"丢掉（那正是判"这块属不属于它"的关键）。
    """
    if len(ids) <= cap:
        return list(ids), [], 0
    head = ids[:2]
    tail = ids[-(cap - 2):]
    return head, tail, len(ids) - len(head) - len(tail)


def _ep_line(store: WikiStoreV2, nid: str, body: int) -> str:
    """一条经历（块内 / 类内都是这一份）: `- 〔m0021｜《今天的杂草屋》〕正文…`。"""
    node = store.get(nid)
    if node is None:
        return ""
    text = node.text or ""
    if len(text) > body:
        text = text[:body] + "…"
    return f"- {marks.head(node, key=node.id)}{text}"


def render_blocks(store: WikiStoreV2, blks: list[Block],
                  *, body: int = BODY_BLOCK, cap: int = MAX_BLOCK_MEMBERS) -> str:
    """块 → 料。头 `〔b1｜3 条〕`（条数 = **真实总数**, 不是摆出来的条数）。"""
    lines: list[str] = []
    for b in blks:
        lines.append(marks.head(None, key=b.bid, extra=[f"{len(b.episodes)} 条"]))
        head, tail, skipped = _split_members(list(b.episodes), cap)
        for nid in head:
            lines.append(f"{_INDENT}{_ep_line(store, nid, body)}")
        if skipped:
            lines.append(f"{_INDENT}…（中间 {skipped} 条略）")
        for nid in tail:
            lines.append(f"{_INDENT}{_ep_line(store, nid, body)}")
    return "\n".join(lines)


def _groups_sorted(store: WikiStoreV2) -> list:
    """全部群节点（按"最近有成员"降序 —— 她此刻在碰的类排前面）。"""
    groups = [n for n in store.all() if n.kind == "group" and n.id]
    g = store.graph()

    def recent(n) -> tuple[str, str]:
        members = g.sources(n.id, REL_MEMBER_OF)
        return (max((_key(store, m)[0] for m in members), default=""), n.id)

    return sorted(groups, key=recent, reverse=True)


def render_groups(store: WikiStoreV2, *, body: int = BODY_GROUP,
                  cap: int = MAX_GROUP_MEMBERS, shown: int = MAX_GROUPS_SHOWN) -> str:
    """已有的类 → 料（空库 → `""`, 由调用方决定怎么说明"一个都还没有"）。

    ⭐ 类的**钥匙是它的名字**（不是 `g0001`）: 群这个 kind 本来就被要求有 `title`
    （`PROCEED §2 #11`）—— 有名字正是为了被指; 而印编号会让 L2 开始猜号（老毛病）。
    """
    g = store.graph()
    lines: list[str] = []
    for n in _groups_sorted(store)[:shown]:
        members = sorted(g.sources(n.id, REL_MEMBER_OF), key=lambda x: _key(store, x))
        lines.append(marks.head(n, extra=[f"{len(members)} 条"]))
        head, tail, skipped = _split_members(members, cap)
        for nid in head:
            lines.append(f"{_INDENT}{_ep_line(store, nid, body)}")
        if skipped:
            lines.append(f"{_INDENT}…（中间 {skipped} 条略）")
        for nid in tail:
            lines.append(f"{_INDENT}{_ep_line(store, nid, body)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 执行器（世界校验在这里: **只剔不拒**, 同 `apply_closures` 的口径）
# ---------------------------------------------------------------------------

def apply_groups(store: WikiStoreV2, rows: list[dict], blks: list[Block],
                 *, ts: str = "", event_seq: list[int] | None = None) -> GroupApplyResult:
    """分群行 → **群节点 + `member_of` 边**。

    | 行 | 干什么 |
    |---|---|
    | `{"action": "attach", "block": "b1", "group": "那盆苔藓"}` | 挂到**已有**的类（名字解析走 `address.find_group`, 印剥同源） |
    | `{"action": "new", "block": "b2", "title": "模型店的那些事"}` | 建**新**类（`unique_title` 写入时强制唯一）后挂上去 |

    ⭐ **同名即并**（引擎闸, 纯计算）: `new` 的名字撞上已有的类 ⇒ **挂到那个类**, 不建新群、
    也**不加数字**。理由: "同一类裂成两个名字"是这一步最贵的错（将来 N8 会为两个群各写一条
    belief）, 而"它又起了一遍同一个名字"正是它想 attach 的信号。
    ⚠️ 设计稿里那条"**成员重叠 ≥ 阈值 ⇒ 引擎直接并**"在当前契约下**永远不会触发**
    （块都是未归群的 ⇒ 新群的成员不可能已经属于谁）—— 它要等有**多归属**的 `merge` 那一刀。

    ⚠️ **命中 0 / 歧义 / 空名字 ⇒ 只记账、丢这一行**: 那个块**留着**, 下一段再来
    （丢一条行 ≠ 丢一件事）。
    """
    by_bid = {b.bid: b for b in blks}
    out = GroupApplyResult()
    before_edges = len(store.edges())
    seen_ep: dict[str, None] = {}

    for i, row in enumerate(rows):
        bid = str(row.get("block") or "")
        blk = by_bid.get(bid)
        if blk is None:
            out.warnings.append(f"分群[{i}] 块 {bid!r} 不在本轮名单里 → 丢这一行")
            continue
        if row.get("action") == "attach":
            node, why = find_group(store, str(row.get("group") or ""))
            if node is None:
                out.warnings.append(
                    f"分群[{i}] 类 {row.get('group')!r} 没找到（{why}）→ 丢这一行")
                continue
        else:
            title = normalize_title(str(row.get("title") or ""))
            if not title:
                out.warnings.append(f"分群[{i}] 新类名是空的 → 丢这一行")
                continue
            node, _ = find_group(store, title)
            if node is not None:
                out.warnings.append(
                    f"分群[{i}] 新类名 {title!r} 与已有类同名 → 并到 {node.id}（不建新群）")
            else:
                node = store.get(store.add(make_node(
                    "group", title=unique_title(store, title, kind="group"), ts=ts)))
                out.nodes.append(node.id)
                logger.info("digest_group new=%s title=%r", node.id, node.title)
        for nid in blk.episodes:
            store.add_edge(REL_MEMBER_OF, nid, node.id, ts=ts)
            seen_ep.setdefault(nid, None)

    out.grouped = list(seen_ep)
    out.edges = len(store.edges()) - before_edges      # 幂等跳过的**不算**（真写了几条）
    return out
