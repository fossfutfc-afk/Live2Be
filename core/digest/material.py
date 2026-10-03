# -*- coding: utf-8 -*-
"""material.py — digest 各轮的**料**（2026-09-29 从 `pipeline.py` 拆出）。

"这一轮吃什么"的真源是 `rounds.ROUNDS` 的 `material` 格（段标题 + 顺序）;
本模块是那些**正文**的构造者（引擎侧, 零 LLM）:

| 给谁 | 函数 | 料 |
|---|---|---|
| R1 | `_collect_visual_prompts` · `_segment_emotion_keys` | 画面记忆 · 本段情绪标尺 |
| R4 | `_open_promises_text` · `_episode_lines` | 还开着的约定（带编号）· 本段新增经历 |
| R2 | `_round_b_material` | 新经历 + 每条候选（正文/被引/边/为什么） |
| R3 | `_node_texts` | 本轮**动过**的节点正文（喂 `entities.hit_set`） |
| 全体 | `_sections_for` · `_join_sections` | 按表校对段标题 → 拼成 user 串 |

⚠️ **两条纪律**（拆出来也要带着走）:
1. **LLM 轮的输入一律走 `_sections_for`**（先拿轮次表校对段标题, 再拼）——
   直接调 `_join_sections` = 绕过校对, `test_sections_check_is_wired` 会红。
2. **行格式只有一个实现**: 段头走 `marks.section`, 记忆行头走 `marks.head`
   （`〔m0021｜《标题》〕`）, note 行走 `notes.render_item` —— 本模块**只拼不造**。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from core.brain import marks
from core.digest.rounds import RoundSpec

if TYPE_CHECKING:                       # 仅注解求值期（避免与编排层循环 import）
    from core.brain.read.recall import EmbedFn
    from core.brain.store import WikiStoreV2

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 段落的校对与拼装（全体共用）
# ---------------------------------------------------------------------------

def _sections_for(spec: RoundSpec, sections: list[tuple[str, str]]) -> str:
    """按表校对**料的段标题**再拼装 —— 表说这一轮吃什么, 这里就必须是那几段。

    ⚠️ 只校标题（"吃什么"的地图）, 不校正文（正文由各家现算）。对不上 = 表在骗人,
    所以**当场炸**而不是静默放行 —— 这正是"料跨 3~4 个文件"的解药:
    想知道 R2 吃什么, 看表一行就够, 而表**不可能**与实际不符。
    """
    got = tuple(title for title, _ in sections)
    if got != spec.material:
        raise AssertionError(
            f"digest {spec.key!r} 的料与轮次表不一致: 表={spec.material} 实际={got}"
            "（改料就要改 core/digest/rounds.py 的 ROUNDS）")
    return _join_sections(sections)


def _join_sections(sections: list[tuple[str, str]]) -> str:
    """输入块拼装: 非空块才注入（省 token）; 空块跳过。

    ⚠️ 段头 `【】` 的构造在 `marks.section`（括号表唯一实现）—— 本函数只管"拼"。
    ⚠️ **LLM 轮的输入一律走 `_sections_for`**（它先拿轮次表校对段标题, 再调这里）——
    直接调本函数 = 绕过料校对, `test_sections_check_is_wired` 会红。
    """
    parts = [f"{marks.section(title)}\n{body}" for title, body in sections if body]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 公共料: 画面记忆 / 情绪标尺
# ---------------------------------------------------------------------------

def _collect_visual_prompts(events) -> list[str]:
    """l2d 事件的 gallery png → 同名 json 的 prompt（视觉记忆）。"""
    prompts: list[str] = []
    for e in events:
        if e.type != "l2d":
            continue
        for img in e.payload.get("images", []) or []:
            if not isinstance(img, str) or not img:
                continue
            gjson = Path(img).with_suffix(".json")
            try:
                meta = json.loads(gjson.read_text(encoding="utf-8"))
                prompt = meta.get("prompt", "")
                if isinstance(prompt, str) and prompt.strip():
                    prompts.append(prompt.strip())
            except (OSError, ValueError):
                continue
    return prompts


def _segment_emotion_keys(events) -> list[str]:
    """本段所有 bond 板里**出现过的**情绪键（按首次出现顺序, 去重）。

    来源 = `payload.paragraphs[i].emotion`（标注层产物, 真源在事件流里）。
    只读不写——用于决定"给 Round A 注哪些键的标尺"（§3.3.2）。
    缺字段/坏结构 → 跳过, 不抛（宁缺勿错: 少注一个键, 不阻断 digest）。
    """
    keys: list[str] = []
    seen: set[str] = set()
    for e in events:
        if getattr(e, "type", None) != "bond":
            continue
        payload = getattr(e, "payload", None) or {}
        for p in payload.get("paragraphs") or []:
            if not isinstance(p, dict):
                continue
            k = p.get("emotion")
            if isinstance(k, str) and k.strip() and k.strip() not in seen:
                seen.add(k.strip())
                keys.append(k.strip())
    return keys


# ---------------------------------------------------------------------------
# R4 的料: 还开着的约定 / 本段新增经历
# ---------------------------------------------------------------------------

def _open_promises_text(items: list) -> str:
    """R4 输入之一: **还开着的约定**（带编号 —— 它要照着 `id` 写 `close`）。

    行格式复用注入块的 `notes.render_item`（`n3 周六模型店 (m0009)  ← 记于 3 天前`）——
    ⚠️ **一份行格式只有一个实现**（两个写者必然漂移）。
    """
    from core.brain.notes import render_item
    return "\n".join(f"- {render_item(it)}" for it in items)


def _episode_lines(store: "WikiStoreV2", episode_ids: list[str]) -> str:
    """R4 输入之二: **本段新增的经历**（真 id —— `add`/`close` 的 `refs` 只能引它们）。

    ⭐ **2026-09-29**: 行首那一段从 `- m0021 「标题」 正文` 改成 **`- 〔m0021｜《标题》〕正文`**
    —— 与 R2 的新经历行（`_round_b_material`）**同一个头**, 由 `marks.head` 出
    （唯一实现）。⚠️ 原来标题写 `「」`, 而她那份视图里 `「」` 是**逐字原话**
    ⇒ 同形不同义; 而 `「」` 恰恰是会让她**抄错东西**的那种形状。
    ⚠️ **没起名就不出名字格**（不印"（无题）"这种假名字）—— 钥匙仍在, 她照样引得到。
    """
    lines: list[str] = []
    for nid in episode_ids:
        node = store.get(nid)
        if node is None:
            continue
        head = node.text if len(node.text) <= 120 else node.text[:120] + "…"
        lines.append(f"- {marks.head(node, key=node.id)}{head}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# R2 / R3 的料
# ---------------------------------------------------------------------------

def _node_texts(store: "WikiStoreV2", ids: list[str]) -> list[str]:
    """**要归属的那些节点的正文**（喂 `entities.hit_set` 扫称呼用）。

    连 `title` / `verbatim` 一起给 —— 称呼常出现在这两处（"老师"多半在标题或原话里,
    而不在她自己那句总结里）。取不到 → 跳过（绝不编）。
    """
    out: list[str] = []
    for nid in ids:
        node = store.get(str(nid))
        if node is None:
            continue
        for t in (node.text, node.title, node.verbatim):
            if isinstance(t, str) and t.strip():
                out.append(t)
    return out


def _round_b_material(store: "WikiStoreV2", episode_ids: list[str],
                      local_of: dict[str, str],
                      embed_fn: "EmbedFn | None",
                      *, char_id: str = "") -> str:
    """Round B 输入: 新经历摘要 + 每条引擎候选提示（板块 5）。

    每条 episode 用 text 走 recommend_candidates 与现有认知碰撞,
    把最像的几条**列出来给 LLM 参考**（⭐ N2 起: 带正文 + 被引 + 边 + 为什么）。

    ⭐ **N2（2026-09-29）两处形态变化**（都是"看不见就写不出来"那条）:
      · 新经历行: `m0025 「标题」 正文` → **`〔m0025｜《标题》〕正文`**
        （编号是钥匙、书名号里是 gist; 顺带修 `「」` 与她视图里"逐字原话"的同形不同义）
      · 候选行: `→ 候选(sim 0.72): u0001 u0003` → **每条候选一行**,
        带 `〔u0001｜belief｜被引 3〕正文` + 边续行 + `为什么: tags[…]/语义 …`
        （旧形态要求 LLM 自己去翻上面那张表, 而"为什么推荐"完全看不见）

    ⚠️ **候选只是提示, 不分档、不强制**（2026-09-15 T17）: 原先
    `≥CAND_HIGH` 会标【疑似同主题】并让 parse 层**结构强制**禁 `add`——
    而那个阈值从未标定过、实测两模型皆 6/6 全越线 → 新认知永远长不出来。
    现在排序取 top-k 无条件列出，判断全在 LLM（判 add 要在 note 里说明理由）。

    **2026-09-13 V3-0（DESIGN_WIKI_V3 §3.5）**: 末尾打一行**写路径召回台账**
    `recall_write char=… eps=… cands=… best=… mode=…`。

    Returns: episodes_text（含候选提示行）。
    """
    from core.brain.read import recall_ledger
    from core.brain.read.recall import _thr, CAND_K
    from core.brain.read.recall import recommend_candidates
    from core.brain.read.render import render_cognition_line

    thr_k = int(_thr("cand_k", CAND_K))
    acc = recall_ledger.CollisionAccount(char_id)
    modes: list[str] = []

    lines: list[str] = []
    for nid in episode_ids:
        node = store.get(nid)
        if node is None:
            continue
        head = node.text
        if len(head) > 120:
            head = head[:120] + "…"
        # 头由 `marks.head` 出（**唯一实现**）—— `〔m0025｜《今天的杂草屋》〕正文`。
        # 编号是**钥匙**（R2 的 decisions 用它指 episode, 真实 id）；
        # 书名号里是**gist**（正文被截到 120 字, 8~16 字的名字是"这是哪件事"的压缩）。
        lines.append(f"{marks.head(node, key=node.id)}{head}")
        if node.verbatim:
            lines.append(f"    原话: {node.verbatim}")
        query = f"{node.text} {node.verbatim}".strip()
        why: list[str] = []
        cands = recommend_candidates(store, query, embed_fn=embed_fn,
                                     mode_out=modes, why_out=why)
        cands = [(c, s) for c, s in cands if c.id in local_of]   # 只标已渲染的
        acc.episode(n_cand=len(cands),
                    best_sim=(cands[0][1] if cands else 0.0))
        if cands:
            # ⭐ N2: 候选不再只给编号 —— **编号 + 正文 + 被引 + 边 + 为什么被推荐**。
            # 旧形态 `→ 候选(sim 0.72): u0001 u0003` 要求它自己去翻上面那张表,
            # 而"为什么推荐"（tags 命中 / 语义）今天完全看不见 —— 看不见就判不准。
            best = cands[0][1]
            reason = why[0] if why else ""
            lines.append(f"    → 候选 {best:.2f}（为什么: {reason}）:")
            graph = store.graph()
            for i, (c, _s) in enumerate(cands):
                rows = render_cognition_line(store, c, graph, local_of, max_body=60,
                                             indent="       ")
                # ⭐ 只有第一个候选带边续行（后面几个是备选, 印全了纯占地方）
                lines.extend(rows if i == 0 else rows[:1])
            lines.append("       （仅供参照, 同主题就 touch/update, 不同主题就 add）")

    # 通道口径: 全程 semantic / 全程 keyword / 混合（部分 episode 失败降级）
    if modes and all(m == "semantic" for m in modes):
        acc.mode = "semantic"
    elif modes and all(m == "keyword" for m in modes):
        acc.mode = "keyword"
    elif modes:
        acc.mode = "mixed"
    acc.log(thr_k=thr_k)
    return "\n".join(lines) or "（无）"
