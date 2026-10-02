# -*- coding: utf-8 -*-
"""groups.py — **L2-a 分群**: 引擎切块 → 一轮 LLM 起名 → 群节点 + `member_of` 边（N7/N7b, 2026-09-29）。

## 这一步在整条链里的位置

    她（MMT）── `{"noticed": "…"}` ──→ `noticed` 事件 ──(L1)──→ **`akin` 边**（她连的两件事）
                                                                    │
    digest 每段的**最后一步** ◀──────────────────────────────────────┘
      `ungrouped()` → `build_blocks()` → 一轮 LLM（**只起名 / 认出已有的类 / 认出重复的类**）
                                        → `apply_groups()` / `apply_merges()` → **群节点 + `member_of`**

⭐ **为什么切块是引擎的活**: `akin` 是**她的原始发现**（"这两条像"）—— 有噪音、可能只是两两。
把它原样当"组"喂给 LLM 就是把她的噪音当成结论。引擎只干一件事: 把**连通块**切出来,
⭐ **边不进视野**（她连的先后、连了几条, 与"这块叫什么"无关）。

⭐ **为什么锚点兜底不做**（原设计有, 这里**有意留白**）: 锚点（同 tag / 同对象）选不好会造出
**假块** ⇒ 假群 ⇒ 将来 `ignite`（N8）为它写一条**假 belief**。落单的事继续等 —— 她下段真连上
一个同伴, 它自然成块（**增量天然成立**）。判据 = 宁缺勿错 > 覆盖率。

## 它**不**做什么

- **不判"像不像"** —— 那是她那一轮的活; 这里只问"这块叫什么 / 这两个类是不是一个"。
- **不产 belief** —— 那是 L2-b `ignite`（N8）。
- **不进她的视图** —— `PROCEED §2 #2`: 群上不放关键信息, 判断归 belief（写两处必漂）。
  这两刀的产出**只在图上**。

## 两件事, 一轮调用（N7b 起）

| 键 | 治什么 | 引擎这一侧 |
|---|---|---|
| `attach` / `new` | 新连出来的块**归到哪个类**（或起个新类名） | 切块（`akin` 连通块）+ 同名即并 |
| `merge` | **同一个类裂成了两个名字**（两边的成员互不相识, 纯计算抓不到 ⇒ 必须问 LLM） | 提候选（**跨群的 `akin` 边**）+ 端点 remap + 删输家 |

⚠️ 设计稿里那条"**成员重叠 ≥ 阈值 ⇒ 引擎直接并**"在今天**永远不会触发** ——
块都是未归群的 ⇒ 两个群的成员必然不重叠。真正会发生的病是"**名字同义、成员不重叠**",
那只能问 LLM。⇒ N7b 的候选判据只有一条: ⭐ **跨群的 `akin` 边**（她连过 ⇒ 这是她
"它们本来是一类"的直接证据）。**名字相近那条先不做**（中文短名会撞上"的事 / 那些"这类
虚词 ⇒ 全是假候选; 而真需要并的类几乎一定有跨群的 `akin`）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

from core.brain import marks
from core.brain.address import find_group, normalize_title, unique_title
from core.brain.graph import REL_AKIN, REL_MEMBER_OF, iter_edges
from core.brain.nodes import make_node

if TYPE_CHECKING:                       # 仅注解求值期可见（避免运行时循环导入）
    from core.brain.store import WikiStoreV2

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
#: 一次最多提几对"可能重复的类"（超出的下一段再说 —— 增量的, 不丢东西）
MAX_MERGE_PAIRS = 3
#: 一对候选最多摆几条"她跨连的"成员行（那是**证据**, 不是清单）
MAX_MERGE_EVIDENCE = 6
#: 一个单条块最多摆出它连到的几个类（够它选就行 —— 摆全部会盖过它自己那一行）
MAX_LINKED_SHOWN = 3

_INDENT = "  "


@dataclass(frozen=True)
class Block:
    """一个块 = 引擎切的**同类候选**（她连过的几件事）。

    `bid` 是**本次调用的把手**（`b1`…）—— ⚠️ 它**不是节点 id**, 只在这一轮有效
    （下一次调用重新发号, 所以块与把手**没有长期对应关系**）。

    `linked`（⭐ N7c）: 这个块（**单条**时）**她连到的那些类**（群 id）。
    单条能进料**只因为**它连到了某个已有的类 —— 那是它的全部依据（引擎不替她判"算不算"）。
    """

    bid: str
    episodes: tuple[str, ...]            # 真 id（按 ts 升序）
    linked: tuple[str, ...] = ()         # 她连到的类（空 = 普通块, ≥2 条或还没成类）


@dataclass(frozen=True)
class MergeCandidate:
    """一对**可能重复的类**（引擎提的候选 —— 判不判在 LLM）。

    `pairs` = **跨这两个群的 `akin` 边**（她连的）: 它既是候选的**依据**,
    也是要摆给 LLM 的**证据**。
    """

    left: str                            # 群 id（小的在前 —— 只为稳定, 无优劣含义）
    right: str
    pairs: tuple[tuple[str, str], ...]    # 跨群的 akin 边（每条 = 两端的 episode id）


@dataclass
class MergeApplyResult:
    """并群的结果（记账; 不阻断）。"""

    merged: list[tuple[str, str]] = field(default_factory=list)   # (输家 id, 赢家 id)
    moved: int = 0                                                # 改指到赢家的成员边数
    warnings: list[str] = field(default_factory=list)


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


def _group_of(store: WikiStoreV2) -> dict[str, set[str]]:
    """episode → 它所属的群（一个 episode 理论上可多归属 —— 设计允许, 今天发现不了第二个）。"""
    out: dict[str, set[str]] = {}
    for e in iter_edges(store, rel=REL_MEMBER_OF):
        out.setdefault(e.src, set()).add(e.dst)
    return out


def build_blocks(store: WikiStoreV2, cand: Iterable[str],
                 *, max_blocks: int = MAX_BLOCKS) -> list[Block]:
    """未归群的 episode → **`akin` 连通块**（新块先发）。

    两种块:

    | 形状 | 判据 | 为什么它能进料 |
    |---|---|---|
    | **≥2 条** | 未归群的几条被她连成一块 | 她连出来的同类候选 —— 有同伴, 类名起得出来 |
    | ⭐ **1 条**（N7c） | 它**连到了某个已有的类**（`linked` 非空） | 那是"它属于这一类"的直接线索; ⚠️ 以前这种单条被"≥2"直接扔掉 ⇒ **她那条边永远没人读** |

    ⚠️ **只有一种仍然进不了料**: 一条 `akin` 都没有的（**完全孤立**）—— 没有任何依据,
    不替她猜; 等她自己连上谁（增量天然成立）。

    ⚠️ **只认 `akin`**（她连过的）—— 见模块 docstring 那条"锚点兜底有意不做"。
    """
    ids = [i for i in cand if store.get(i) is not None]
    in_play = set(ids)
    grp_of = _group_of(store)
    adj: dict[str, set[str]] = {i: set() for i in ids}
    linked: dict[str, set[str]] = {}          # 候选 → 它连到的类（群 id）
    for e in iter_edges(store, rel=REL_AKIN):
        if e.src in in_play and e.dst in in_play and e.src != e.dst:
            adj[e.src].add(e.dst)
            adj[e.dst].add(e.src)
            continue
        # 只一边在候选池里 ⇒ 另一边**已经归了类**（`grp_of` 里没有的返回空集 ⇒ 自然过滤）
        if e.src in in_play and e.src != e.dst:
            linked.setdefault(e.src, set()).update(grp_of.get(e.dst, ()))
        elif e.dst in in_play:
            linked.setdefault(e.dst, set()).update(grp_of.get(e.src, ()))

    comps: list[tuple[list[str], tuple[str, ...]]] = []
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
            comps.append((sorted(comp, key=lambda x: _key(store, x)), ()))
    for i in ids:                             # ⭐ N7c: 落单但连到了某个类的
        if adj[i] or not linked.get(i):
            continue
        comps.append(([i], tuple(sorted(linked[i]))))
    # 新的块先发（记忆是"最近的事先组织"）—— 超上限的那些**留着**, 下段再来
    comps.sort(key=lambda c: _key(store, c[0][-1]), reverse=True)
    return [Block(bid=f"b{k}", episodes=tuple(members), linked=lk)
            for k, (members, lk) in enumerate(comps[:max_blocks], start=1)]


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


def _group_head(store: WikiStoreV2, gid: str) -> str:
    """`〔《那片苔藓》｜4 条〕` —— **类头**（料的每一处都共用这一份: 已有的类 / 合并候选 / 单条块）。"""
    node = store.get(gid)
    if node is None:
        return ""
    n = len(store.graph().sources(gid, REL_MEMBER_OF))
    return marks.head(node, extra=[f"{n} 条"])


def render_blocks(store: WikiStoreV2, blks: list[Block],
                  *, body: int = BODY_BLOCK, cap: int = MAX_BLOCK_MEMBERS) -> str:
    """块 → 料。头 `〔b1｜3 条〕`（条数 = **真实总数**, 不是摆出来的条数）。

    ⭐ **N7c 的单条块**在头后面接上**她连到的那些类**::

        〔b1｜1 条〕 与 〔《那片苔藓》｜4 条〕 —— 她把它连到这一类
          - 〔m0009｜《窗台上的苔藓》〕窗台那盆是我从楼梯拐角分出来的…

    ⚠️ 类名仍在 `〔〕` 里（头的第二段）, 不落进正文 —— 名字只在头里, 这是括号表那条。
    """
    lines: list[str] = []
    for b in blks:
        head = marks.head(None, key=b.bid, extra=[f"{len(b.episodes)} 条"])
        if b.linked:
            shown = [h for h in (_group_head(store, g) for g in b.linked[:MAX_LINKED_SHOWN]) if h]
            if shown:
                word = "这一类" if len(shown) == 1 else "这些类"
                head += f" 与 {'、'.join(shown)} —— 她把它连到{word}"
        lines.append(head)
        head_ids, tail_ids, skipped = _split_members(list(b.episodes), cap)
        for nid in head_ids:
            lines.append(f"{_INDENT}{_ep_line(store, nid, body)}")
        if skipped:
            lines.append(f"{_INDENT}…（中间 {skipped} 条略）")
        for nid in tail_ids:
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
        lines.append(_group_head(store, n.id))
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
    也**不加数字**。理由: "同一类裂成两个名字"是这一步最贵的错（N8 会为两个群各写一条
    belief）, 而"它又起了一遍同一个名字"正是它想 attach 的信号。
    ⚠️ **名字不同、意思相同**的那一半它抓不到（纯计算没有语义）——
    那归 `merge_candidates` / `apply_merges`（N7b, 同一轮里另两个键）。

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
        action = row.get("action")
        if action not in ("attach", "new"):
            out.warnings.append(f"分群[{i}] 这里只收 attach / new（收到 {action!r}）→ 丢这一行")
            continue
        if action == "attach":
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


# ---------------------------------------------------------------------------
# merge（N7b）: 同一个类裂成两个名字 ⇒ 并回去
# ---------------------------------------------------------------------------

def merge_candidates(store: WikiStoreV2,
                     *, max_pairs: int = MAX_MERGE_PAIRS) -> list[MergeCandidate]:
    """⭐ **跨群的 `akin` 边** → 可能重复的类（0 LLM）。

    判据只有这一条, 因为 `akin` 是**她的原始发现** —— 两个类之间被她连过, 就是
    "它们本来是一类"的直接证据（真需要并的类几乎一定有跨群的 `akin`: 她正是因此觉得像）。
    ⚠️ **名字相近那条先不做**: 中文短名会撞上"的事 / 那些"这类虚词 ⇒ 全是假候选,
    而假候选要花一次 LLM 判定才知道是假的。
    ⚠️ **两个类里的成员互不相识时它提不出来** —— 那正是"纯计算抓不到语义"的诚实边界;
    真机数据说明有漏, 再加名字/语义通道（代价: 假候选）。
    """
    grp_of = _group_of(store)
    acc: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for e in iter_edges(store, rel=REL_AKIN):
        left, right = grp_of.get(e.src) or set(), grp_of.get(e.dst) or set()
        for x in sorted(left):
            for y in sorted(right):
                if x == y:
                    continue
                key = (x, y) if x < y else (y, x)
                acc.setdefault(key, []).append((e.src, e.dst))
    out = [MergeCandidate(left=k[0], right=k[1], pairs=tuple(v)) for k, v in acc.items()]
    out.sort(key=lambda c: (-len(c.pairs), c.left, c.right))    # 跨连多的先问
    return out[:max_pairs]


def render_merge_candidates(store: WikiStoreV2, cands: list[MergeCandidate],
                            *, body: int = BODY_GROUP,
                            cap: int = MAX_MERGE_EVIDENCE) -> str:
    """候选 → 料（**两个类头 + 她跨连的那些成员行** —— 那是证据, 不是清单）。

    ⚠️ 摆的是**跨连的那几条**, 不是两个类的全部成员: 判"是不是一个类"靠的是
    "她连着的那几对长什么样", 而把两边的成员全摆出来只是占地方。
    """
    lines: list[str] = []
    for i, c in enumerate(cands, start=1):
        members = sorted({m for pair in c.pairs for m in pair},
                         key=lambda x: _key(store, x))
        lines.append(f"{i}. {_group_head(store, c.left)} 与 {_group_head(store, c.right)}"
                     f" —— 她把这 {len(c.pairs)} 对连过")
        for nid in members[:cap]:
            lines.append(f"{_INDENT}{_ep_line(store, nid, body)}")
        if len(members) > cap:
            lines.append(f"{_INDENT}…（另有 {len(members) - cap} 条）")
    return "\n".join(lines)


def apply_merges(store: WikiStoreV2, rows: list[dict],
                 cands: list[MergeCandidate], *, ts: str = "") -> MergeApplyResult:
    """`{"action": "merge", "from": …, "into": …}` → **并群**。

    照 `revise` 里那个 `merge` 的先例: **端点 remap + 删源**, ⚠️ 边的 `ts` **原样保留**
    （"什么时候加入这个类"是信息 —— 重置成"现在"就把它抹了）。

    ⚠️ **只并引擎提过的那些对**（闭集校验放在**这里**, 不放契约: 名字解析要归一,
    而契约层不依赖 core —— 放契约就得在那边抄一份剥括号的逻辑, 那就是"两处必然漂"）。
    ⚠️ **输掉的名字写进赢家的 `aliases`**（数据留住 —— 名字是**地址**, 将来 `note.index`
    里就有指向它的东西; "解析侧认不认 aliases"是另一件事, 属于裁决 #10）。
    """
    allowed = {frozenset((c.left, c.right)) for c in cands}
    out = MergeApplyResult()
    for i, row in enumerate(rows):
        loser, why_l = find_group(store, str(row.get("from") or ""))
        winner, why_w = find_group(store, str(row.get("into") or ""))
        if loser is None or winner is None:
            out.warnings.append(f"并群[{i}] 类名没找到（{why_l if loser is None else why_w}）"
                                f"→ 丢这一行")
            continue
        if loser.id == winner.id:
            out.warnings.append(f"并群[{i}] from 与 into 是同一个类 → 丢这一行")
            continue
        if frozenset((loser.id, winner.id)) not in allowed:
            out.warnings.append(f"并群[{i}] 这一对不在本轮候选里 → 丢这一行")
            continue
        moved = _merge_into(store, loser, winner)
        out.merged.append((loser.id, winner.id))
        out.moved += moved
        logger.info("digest_group merge loser=%s(%r) → winner=%s(%r) moved=%d",
                    loser.id, loser.title, winner.id, winner.title, moved)
    return out


def _merge_into(store: WikiStoreV2, loser, winner) -> int:
    """把输家的边**端点 remap 到赢家**（`ts` 原样）, 然后删掉输家。返回搬过来的成员边数。"""
    moved = len(store.graph().sources(loser.id, REL_MEMBER_OF))
    keep: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for e in store.edges():
        src = winner.id if e.src == loser.id else e.src
        dst = winner.id if e.dst == loser.id else e.dst
        if src == dst or (e.rel, src, dst) in seen:
            continue
        seen.add((e.rel, src, dst))
        keep.append((e.rel, src, dst, e.ts))
    store.delete(loser.id)                  # 删节点 = 边表过滤（§2.1 的闭环）
    for rel, src, dst, ets in keep:
        store.add_edge(rel, src, dst, ts=ets)
    names = list(winner.aliases)
    if loser.title and loser.title not in names:
        names.append(loser.title)
    store.update(winner.id, {"aliases": names})
    return moved
