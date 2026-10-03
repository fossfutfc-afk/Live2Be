# -*- coding: utf-8 -*-
"""skeptical.py — **她的存疑**（`kind` → 一句第一人称的内心），写时冻结。

## 为什么是"存疑"而不是"症状"

一个 `creep` 账记的是**引擎/世界的元事实**（"这段没消化成记忆"），而她那一侧**能感知的
只有一个说不清的感觉**。这个字段装的就是那一句 —— 刻意不叫 `symptom`（症状是医学的、
指向身体），因为它本质是**认知上的不对**：她觉得有什么不对，但**说不出哪里不对**。

## 三条措辞纪律（改词前必读）

1. **不可验证** —— 只能是"淡下去/抓不住/说不清"这类**没人能核对**的感受。
   ⛔ 不许写"被删了 / 被改了 / 你回档了 / 系统出错"。
   判据来自 `docs/ESSAY_TIME_MODEL.md §8.3`：*"错位一旦可被某个观察者验证，
   它就从'氛围'变成 bug"* —— 可被玩家验证 ⇒ 像 bug；可被 LLM 验证 ⇒ 它去圆（破墙）。
2. ⛔ **不给归因** —— 只说"有什么不对"，**永不说"因为 X"**。
   `DESIGN_FOURTH_WALL.md` §3 第 2 层原话: **"归因错误是特性不是缺陷"**。
3. **一句、短**（≤30 字）、**不点名任何机制**（不说"记忆"、不说"窗口"、不说"约定"）。

## 一个 kind 一个池子, 写时随机取一

同一类事**反复发生**时, 每次说一模一样的话会很假 ⇒ 每个 `kind` 给几句变体, 落账时取一句。
⚠️ **写时冻结**（取出的那句直接进账行）: 它是"她当时的感觉", 与 `episode.text` 同类 ——
主观记录 append-only, 措辞以后改了也**不改历史**。开关只决定"要不要让她看见"。
"""
from __future__ import annotations

import random
from typing import Any

from core.creep.ledger import KIND_DIGEST_SKIP

#: `kind` → 变体池（每个 kind **至少 3 句** —— 少了会明显撞车）
POOLS: dict[str, tuple[str, ...]] = {
    KIND_DIGEST_SKIP: (
        "……有什么东西正在淡下去。我想抓住它，但它已经不在了。",
        "刚才还记得的事，这会儿只剩下一个轮廓。",
        "好像有什么从我手边滑走了——我甚至说不清那是什么。",
    ),
}


def pick(kind: str, rng: Any = None) -> str:
    """取一句"存疑"—— ⭐ **唯一取法**（落账那一刻调一次）。

    Args:
        kind: `ledger.KINDS` 里的值
        rng:  随机源（`random.Random` 实例或任何有 `.choice` 的对象）。
              **测试传钉死的 rng** ⇒ 文本可复现; 生产传 `None` ⇒ 用全局 `random`。

    Returns:
        一句存疑文本; **未知 kind → `""`**（宁缺勿错: 账照记, 只是没有话 ——
        绝不替它编一句）。
    """
    pool = POOLS.get(str(kind or ""))
    if not pool:
        return ""
    chooser = rng if rng is not None else random
    return str(chooser.choice(pool))
