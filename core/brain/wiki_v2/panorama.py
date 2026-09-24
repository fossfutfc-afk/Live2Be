# -*- coding: utf-8 -*-
"""panorama.py — **全景轮**（DESIGN_GRAPH_V4 §8.6）: 取料。

全景轮 = 低频 · **全量视野** · 遍历后的一次整理: 把 note 的 B 类两槽
（`habits` / `on_mind`）**整体重写**, 顺手结清已经了结的约定。
⭐ 它**不碰图** ⇒ 不进 digest 事务、不需要 `clone_state` 快照、失败也不带走 digest。

本模块**只做取料**: 纯函数、零 IO、零 LLM —— 把料摆到她面前, **判断全交给那一次调用**。
（调用侧: `llm/prompts/panorama.md` + `digest.panorama` 标签 + 解析/执行器 —— 下一步。）

## 料从哪来（递归金字塔, §12.1 学 BaiShou）

    上一版 `habits`（她自己归纳的, 承载长周期 —— 递归的那一半）
  ∪ 候选池（与本轮**新增** episode 相关的旧 episode —— 跨时段发现新"同类"）
  ∪ 本轮新增（正文）
  ∪ 还开着的约定 / 已结清未退场的（顺手结清 + 交回退场）
  ∪ `on_mind`（还成立就照抄原文, `since` 才保得住）

## 候选池的两条通道

| 通道 | 判据 | 今天的状态 |
|---|---|---|
| **语义近邻** | `embed_fn` 给得出向量 → **余弦 top-k**（低频现算, **不落盘** —— 同 recall 的"零漂移"纪律） | 接口就位; 本机 embedding 服务未起 ⇒ 实际走下面那条 |
| **字面锚点**（降级） | `tag` / `items` / `place` 的**值相同**（设计稿 §8.6 的降级路径） | **今天的主力** |

⚠️ **`verbatim` 共词不做锚点** —— 真机实测前两字 "那个" 命中 3 条, 纯噪音。
⚠️ 锚点按**稀有度**排（DF 小 = 具体）+ **每个锚点封顶** —— 否则"约定"（真机 4 条）这类
   泛词会把池子冲爆（长世界里必然）。**是不是同类仍归 LLM 判**。
⚠️ 候选**如实标注来源**（"与 m0013 同 tag: 纸兔子"）—— 她看得见"这两条只是共享一个泛词",
   才拒得掉。引擎替她过滤 = 引擎做判定（越界）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from core.brain.wiki_v2.nodes import BrainNode
from core.brain.wiki_v2.notes import NoteItem, NotesState, render_item
from core.brain.wiki_v2.store import WikiStoreV2
# 与 recall 共用"什么文本会被嵌入"和余弦 —— 两份实现必然漂移（镜像纪律）
from core.brain.wiki_v2.recall import _cosine, _embed_text

logger = logging.getLogger(__name__)

#: 每个锚点最多带几条候选（防泛词冲爆池子; ⚠️ 不是"同类判据", 只是预算）
DEFAULT_CAP_PER_ANCHOR = 3
#: 候选池总数上限（超了按稀有度/显著性截断）
DEFAULT_MAX_CANDIDATES = 12
#: "其余经历"索引上限（只有 id + 开头; 超了如实说明还有多少没列）
DEFAULT_INDEX_CAP = 40
#: 索引里每条截断到几个字（够认出是哪件事就行）
INDEX_CHARS = 24

#: 锚点三元组的两轴: **值的类型**（同 tag / 同 item / 同 place 是三种证据, 别混成一堆）
ANCHOR_TAG = "tag"
ANCHOR_ITEM = "item"
ANCHOR_PLACE = "place"


@dataclass
class Candidate:
    """一条候选旧经历（**带来源标注** —— 这是它存在的意义: 让 LLM 看得见"为什么被抬出来"）。"""

    id: str
    text: str
    sig: float
    #: 共享锚点里最稀有的那个的 DF（越小越具体; 泛词 = 大）—— 排序用
    rarity: int = 0
    #: 被**几条新经历**独立命中（同一锚点值算一条链）—— 命中越多证据越强, 排序用
    hits: int = 0
    #: 人可读的来源（"与 m0013 同 tag: 纸兔子" / "你上次引用了它"）
    why: list[str] = field(default_factory=list)


@dataclass
class PanoramaInput:
    """全景轮的输入（四块 + 索引 + 候选池）。`render()` 出来就是喂给那一次调用的料。"""

    new: list[BrainNode] = field(default_factory=list)          # 本轮新增的 episode
    candidates: list[Candidate] = field(default_factory=list)   # 候选旧经历（跨时段）
    others: list[BrainNode] = field(default_factory=list)       # 其余经历（只有 id + 开头）
    others_dropped: int = 0                                     # 索引被截掉几条（如实说明）
    promise: list[NoteItem] = field(default_factory=list)       # 还开着的约定
    closed: list[NoteItem] = field(default_factory=list)        # 已结清、等图侧接住
    habits: list[NoteItem] = field(default_factory=list)        # 上一版惯例（递归的那一半）
    on_mind: NoteItem | None = None
    #: 实际走的通道: `semantic` / `anchor` / `none`（可观测 —— 同 recall 的 `mode_out`）
    mode: str = "none"

    @property
    def worth_running(self) -> bool:
        """值不值得跑这一次调用。

        **有新材料**（本轮新增）或**有待结清**（已结清未退场 ⇒ 交回固化）才值得;
        两者都空时重写一遍只会让 `since` 与措辞空转（该不该跑的**时机**是另一回事,
        由触发频率决定 —— 这里是"有没有料"）。
        """
        return bool(self.new or self.closed)

    def render(self, *, now: object | None = None) -> str:
        """→ 喂给那一次调用的**料**（自然语言小节; 空块整块不出现）。

        ⚠️ **调用方先看 `worth_running`** —— 没料时这里照样会渲出"其余的经历"索引
        （它是纯渲染, 不做决定）; 而没料就不该花那一次调用。

        这一段是**证据**, 不是指令: 任务、严苛三判据、输出契约在
        `llm/prompts/panorama.md`（下一步）。这里只保证"她看得见该看见的东西,
        且看得见每一条**为什么**被摆到她面前"。
        """
        blocks: list[str] = []
        if self.promise:
            blocks.append(
                "【你手上还开着的约定】（顺手看: 哪些其实已经了结了 —— 了结的必须写理由）\n"
                + "\n".join(f"  {render_item(it, now=now)}" for it in self.promise))
        if self.closed:
            blocks.append(
                "【已经结清、图里还没接住的】（核对过确实已经进长期记忆的, 报编号退场）\n"
                + "\n".join(f"  {render_item(it)}" for it in self.closed))
        if self.habits:
            blocks.append(
                "【你之前记下的惯例】（延续的**照抄原文与编号**; 不再成立的不要写回来）\n"
                + "\n".join(f"  {render_item(it, now=now)}" for it in self.habits))
        if self.on_mind is not None:
            blocks.append("【你最近在想】（还成立就照抄原文）\n"
                          f"  {self.on_mind.text}")
        if self.new:
            blocks.append("【这次新消化的经历】\n"
                          + "\n".join(f"  {n.id} {n.text}" for n in self.new))
        if self.candidates:
            how = ("语义相近" if self.mode == "semantic" else "按**字面**找到")
            lines = [f"  {c.id}（{', '.join(c.why)}）{c.text}" for c in self.candidates]
            blocks.append(f"【可能相关的旧经历】（这些是{how}的, **不一定是同一件事**"
                          " —— 你自己判）\n" + "\n".join(lines))
        if self.others:
            lines = [f"  {n.id} {_clip(n.text)}" for n in self.others]
            if self.others_dropped:
                lines.append(f"  （还有 {self.others_dropped} 条更早的没有列出来）")
            blocks.append("【其余的经历】（只给编号与开头; 要引用哪条直接用编号）\n"
                          + "\n".join(lines))
        return "\n\n".join(blocks)


def build_input(store: WikiStoreV2, note_state: NotesState, *,
                new_ids: Iterable[str] = (),
                embed_fn: Any = None,
                cap_per_anchor: int = DEFAULT_CAP_PER_ANCHOR,
                max_candidates: int = DEFAULT_MAX_CANDIDATES,
                index_cap: int = DEFAULT_INDEX_CAP) -> PanoramaInput:
    """取料: 图 + 笔记状态 + 本轮新增 → `PanoramaInput`。

    Args:
        new_ids: 本轮 digest 新建的 episode id（`DigestResult.created`）。**空也照跑**
            （可能只是来结清/退场）, 但那种情况下 `worth_running` 会告诉你别调 LLM。
        embed_fn: 语义后端（`wiki_v2.recall.EmbedFn`）; 给了就走向量近邻通道,
            没给或它抛异常 → **降级字面锚点**（并打一行日志, 同 `recommend_candidates`）。
    """
    eps = [n for n in store.all() if n.kind == "episode" and n.id]
    by_id = {n.id: n for n in eps}
    new = [by_id[i] for i in new_ids if i in by_id]
    new_set = {n.id for n in new}

    cands: dict[str, Candidate] = {}
    mode = "none"
    if new:
        if embed_fn is not None:
            try:
                cands = _semantic_pairs(eps, new, embed_fn, k=cap_per_anchor)
                mode = "semantic"
            except Exception as e:                     # noqa: BLE001 — 后端故障降级
                logger.info("panorama_pairs fallback=anchor reason=embed_error err=%s "
                            "eps=%d（候选池改用字面锚点）", e, len(eps))
        if mode != "semantic":
            cands = _anchor_pairs(eps, new, cap_per_anchor=cap_per_anchor)
            mode = "anchor"

    _add_habit_refs(cands, by_id, note_state, new_set, total_eps=len(eps))
    # 排序: **越具体**（共享锚点越稀有）→ **被越多条新经历命中** → 越显著 → id。
    # `hits` 放在 sig 前面: "三条新经历都连着它"比"它自己很重要"更像"同一件事"。
    ordered = sorted(cands.values(),
                     key=lambda c: (c.rarity, -c.hits, -c.sig, c.id))[:max_candidates]

    shown = {c.id for c in ordered} | new_set
    rest = [n for n in sorted(eps, key=lambda n: (n.ts or "", n.id), reverse=True)
            if n.id not in shown]

    return PanoramaInput(
        new=new, candidates=ordered,
        others=rest[:index_cap], others_dropped=max(0, len(rest) - index_cap),
        promise=[it for it in note_state.promise if not it.closed],
        closed=[it for it in note_state.promise if it.closed],
        habits=list(note_state.habits), on_mind=note_state.on_mind,
        mode=mode)


# ---------------------------------------------------------------------------
# 两条通道
# ---------------------------------------------------------------------------

def _anchors(node: BrainNode) -> list[tuple[str, str]]:
    """可当锚点的**值**（带类型轴）。

    ⚠️ **不含 `verbatim` 共词**（真机实测 "那个" 命中 3 条）; 也**不含 `emo_shape`/`place_raw`**
    —— 前者是召回侧信号（绝不进 LLM 上下文）, 后者实测无重复值。
    """
    out: list[tuple[str, str]] = []
    out += [(ANCHOR_TAG, str(t).strip()) for t in node.tags if str(t).strip()]
    out += [(ANCHOR_ITEM, str(i).strip()) for i in node.items if str(i).strip()]
    out += [(ANCHOR_PLACE, str(p).strip()) for p in node.place if str(p).strip()]
    return out


def _anchor_pairs(eps: list[BrainNode], new: list[BrainNode], *,
                  cap_per_anchor: int) -> dict[str, Candidate]:
    """字面锚点通道（降级 = 今天的主力）。

    对**每条新 episode**: 取它的锚点值 → 命中同一锚点值的旧 episode 即候选;
    每个锚点按（显著性, id）取前 `cap_per_anchor` 条。同一锚点值只出现在这一条上
    （DF = 1）不构成"同类"线索 ⇒ 跳过。
    """
    new_set = {n.id for n in new}
    df: dict[tuple[str, str], int] = {}
    anchors_of: dict[str, set[tuple[str, str]]] = {}
    for n in eps:
        a = set(_anchors(n))
        anchors_of[n.id] = a
        for key in a:
            df[key] = df.get(key, 0) + 1

    out: dict[str, Candidate] = {}
    for n in new:
        for key in sorted(anchors_of[n.id]):
            if df.get(key, 0) < 2:                     # 只在这一条上出现 ⇒ 连不上谁
                continue
            hits = [m for m in eps if m.id not in new_set and key in anchors_of[m.id]]
            hits.sort(key=lambda m: (-m.significance, m.id))
            for m in hits[:cap_per_anchor]:
                c = out.get(m.id)
                if c is None:
                    c = Candidate(id=m.id, text=m.text or "", sig=m.significance,
                                  rarity=df[key])
                    out[m.id] = c
                c.rarity = min(c.rarity, df[key])
                c.hits += 1
                why = f"与 {n.id} 同 {key[0]}: {key[1]}"
                if why not in c.why:
                    c.why.append(why)
    return out


def _semantic_pairs(eps: list[BrainNode], new: list[BrainNode], embed_fn: Any, *,
                    k: int) -> dict[str, Candidate]:
    """语义近邻通道: **一次批量**嵌入全部 episode（低频现算、不落盘）, 每条新 episode 取 top-k。

    ⚠️ 不引入向量库（§8.6 用户裁决）—— 百来条短文秒级, 且保住"embedding 派生不落盘 ⇒ 内容
    改动零漂移"。⚠️ 文本口径与 `recall._embed_text` **同源**（共用那个函数, 不另写一份）。
    """
    new_set = {n.id for n in new}
    vecs = embed_fn([_embed_text(n) for n in eps])
    vec_of = {n.id: v for n, v in zip(eps, vecs)}
    out: dict[str, Candidate] = {}
    for n in new:
        qv = vec_of.get(n.id)
        if not qv:
            continue
        scored = sorted(
            ((_cosine(qv, vec_of[m.id]), m) for m in eps
             if m.id not in new_set and vec_of.get(m.id)),
            key=lambda t: t[0], reverse=True)
        for s, m in scored[:k]:
            if s <= 0:                                 # 零/负相似不算候选（同 recall 口径）
                continue
            c = out.get(m.id)
            if c is None:
                c = Candidate(id=m.id, text=m.text or "", sig=m.significance, rarity=0)
                out[m.id] = c
            c.rarity = min(c.rarity, 0)
            c.hits += 1
            why = f"与 {n.id} 语义相近（{s:.2f}）"
            if why not in c.why:
                c.why.append(why)
    return out


def _add_habit_refs(cands: dict[str, Candidate], by_id: dict[str, BrainNode],
                    note_state: NotesState, new_set: set[str], *,
                    total_eps: int) -> None:
    """金字塔的**递归那一半**: 上一版 `habits` 引用过的 episode 也进池子。

    为什么: 她上次的归纳要能被**当场核对**（"我引用的那几条现在还在吗、还是那几条吗"）,
    否则重写就是凭记忆重写。⚠️ 优先级最低（`rarity` 给最大）—— 它已经在金字塔里了,
    新料（跨时段的锚点命中）更值钱。悬空引用（节点已不在）直接跳过。
    """
    for it in note_state.habits:
        for rid in it.refs:
            m = by_id.get(rid)
            if m is None or m.id in new_set:
                continue
            c = cands.get(m.id)
            if c is None:
                c = Candidate(id=m.id, text=m.text or "", sig=m.significance,
                              rarity=max(total_eps, 1))
                cands[m.id] = c
            if "你上次引用了它" not in c.why:
                c.why.append("你上次引用了它")


def _clip(text: str, limit: int = INDEX_CHARS) -> str:
    """索引行截断（够认出是哪件事就行; 不截断会让"全量视野"在长世界里爆掉）。"""
    t = (text or "").strip()
    return t if len(t) <= limit else t[:limit] + "…"
