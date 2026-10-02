# -*- coding: utf-8 -*-
"""panorama.py — **取料件**（原"全景轮"的取料那一半）。

> ⚠️ **状态（2026-09-29, N4a）: 全景轮已退役**（`habits` 槽取消 · `on_mind` 改由 L1 写）
> ⇒ 本模块**今天零产品调用者**。它留下的理由是**取料逻辑本身**（两条通道 + 候选带 `why`）——
> 那是 `TODO.md` 里 **N6（候选池 / 切块）** 的现成原料。
> ⚠️ **别再往这里加"卡"相关的东西**（`habits` / `on_mind` / 上次那张卡）: 那是退役的那一半。
> ⚠️ N6 会把它整形成"**切块**"（块的来源：她连的 `akin` + 引擎按锚点切）—— 那时改名/改形状
>    都归它, 现在**不为想象中的消费者预先改造**。

本模块**只做取料**: 纯函数、零 IO、零 LLM —— 把料摆出来, **判断全交给调用方**。

## 候选池的两条通道

| 通道 | 判据 | 今天的状态 |
|---|---|---|
| **语义近邻** | `embed_fn` 给得出向量 → **余弦 top-k**（低频现算, **不落盘** —— 同 recall 的"零漂移"纪律） | 接口就位; 本机 embedding 服务未起 ⇒ 实际走下面那条 |
| **字面锚点**（降级） | `tag` / `items` / `place` 的**值相同** | **今天的主力**（`PROCEED §4`: 字面精确度 1.00） |

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

from core.brain.nodes import BrainNode
from core.brain.store import WikiStoreV2
# 与 recall 共用"什么文本会被嵌入"和余弦 —— 两份实现必然漂移（镜像纪律）
from core.brain.recall import _cosine, _embed_text

logger = logging.getLogger(__name__)

#: 每个锚点最多带几条候选（防泛词冲爆池子; ⚠️ 不是"同类判据", 只是预算）
DEFAULT_CAP_PER_ANCHOR = 3
#: 候选池总数上限（超了按稀有度/命中数/显著性截断）。
#: ⚠️ 2026-09-25 从 12 调到 **20**：索引默认关之后**没有第二条呈现通道** ⇒ 这个上限
#: 从"软截断"变成了**硬截断**（落选就彻底看不见）。它是**一轮调用的输入预算**、
#: 不是注意力预算（低频调用，宁松勿紧）。**具体数字以后再按真机调**。
DEFAULT_MAX_CANDIDATES = 20
#: "其余经历"索引上限 —— ⚠️ **默认 0 = 关**（2026-09-23 定形）：那些条目她**看不到内容**,
#: 索引给的是"引用的诱惑"而不是"判断的依据"。旋钮留着, 真机上发现"明显相关的没被抬出来"再开。
DEFAULT_INDEX_CAP = 0
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
    """全景轮的输入（**上次那张卡 + 本轮新增 + 候选池**）。`render()` 出来就是喂给那一次调用的料。"""

    new: list[BrainNode] = field(default_factory=list)          # 本轮新增的 episode
    candidates: list[Candidate] = field(default_factory=list)   # 候选旧经历（跨时段）
    others: list[BrainNode] = field(default_factory=list)       # 其余经历（**默认关**, 见 `index_cap`）
    others_dropped: int = 0                                     # 索引被截掉几条（如实说明）
    #: 实际走的通道: `semantic` / `anchor` / `none`（可观测 —— 同 recall 的 `mode_out`）
    mode: str = "none"

    @property
    def worth_running(self) -> bool:
        """值不值得跑这一次调用 —— **只看有没有新材料**。

        没有本轮新增时重写一遍只是让措辞空转。（"什么时候该跑"是另一回事，由触发频率决定；
        这里答的是"有没有料"。）⚠️ **"待结清"不再是理由**（2026-09-23）：结清/固化/退场归 R4。
        """
        return bool(self.new)

    def render(self) -> str:
        """→ 喂给那一次调用的**料**（自然语言小节; 空块整块不出现）。

        ⚠️ **调用方先看 `worth_running`**（它是纯渲染, 不做决定）。
        ⚠️ 卡上**印编号**（`n4`）—— 契约里"照抄编号 = 还是那一条"（2026-09-25），
        不印就等于让模型没法延续。⚠️ 但**不印时间**：时间对"这条还成立吗"不是判据。

        这一段是**证据**, 不是指令: 任务、严苛三判据、输出契约在
        `llm/prompts/panorama.md`（任务）+ `contract.build_schema(PHASE_PANORAMA)`（形状）。
        这里只保证"她看得见该看见的东西, 且看得见每一条**为什么**被摆到她面前"。
        """
        blocks: list[str] = []
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


def build_input(store: WikiStoreV2, *,
                new_ids: Iterable[str] = (),
                embed_fn: Any = None,
                cap_per_anchor: int = DEFAULT_CAP_PER_ANCHOR,
                max_candidates: int = int(DEFAULT_MAX_CANDIDATES),
                index_cap: int = DEFAULT_INDEX_CAP) -> PanoramaInput:
    """取料: 图 + 笔记状态 + 本轮新增 → `PanoramaInput`。

    Args:
        new_ids: 本轮 digest 新建的 episode id（`DigestResult.created`）。**空也照跑**
            （可能只是来结清/退场）, 但那种情况下 `worth_running` 会告诉你别调 LLM。
        embed_fn: 语义后端（`brain.recall.EmbedFn`）; 给了就走向量近邻通道,
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
    # ⏸ 原 `ANCHOR_ITEM`（`node.items` 当锚点）**2026-09-29 删** —— `items` 字段退役
    # （零活读者; 物品面将来走 `inventory` 旁路）。`ANCHOR_ITEM` 常量先留着,
    # 等这个模块（零调用者, 留给切块）真正被接线时再决定要不要一起删。
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


def _clip(text: str, limit: int = INDEX_CHARS) -> str:
    """索引行截断（够认出是哪件事就行; 不截断会让"全量视野"在长世界里爆掉）。"""
    t = (text or "").strip()
    return t if len(t) <= limit else t[:limit] + "…"
