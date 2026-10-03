# -*- coding: utf-8 -*-
"""akin.py — **本段的「想起」账 → `akin` 边**（2026-09-29 从 `pipeline.py` 拆出）。

`DESIGN_MMT_NEW_ACTION §4.3 ④` / **N5c**。这是 digest 里**唯一零 LLM 的一步**:

    她在 MMT 那一刻写 `{"noticed": "名字"}` → 引擎落一条 `noticed` 事件（N5b）
    → **本模块**（L1 建完 episode 之后）: 找到"她说话那一刻属于哪条新 episode"
      → `akin{新 → 她指的}`

⚠️ 只此一个函数 —— 单独成文件是因为它在轮次表里是**独立的一步**（`key="akin"`），
和 R1/R2/R3/R4 并列，却谁都不属于。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.brain.graph import REL_AKIN

if TYPE_CHECKING:                       # 仅注解求值期
    from core.brain.store import WikiStoreV2

logger = logging.getLogger(__name__)


def _link_akin(store: WikiStoreV2, episode_ids: list[str], noticed: list, *,
               ts: str) -> tuple[int, int, int]:
    """⭐ **N5c** · 本段的「想起」账 → `akin` 边。返回 `(落了几条, 未认领, 自环跳过)`。

    链路（`DESIGN_MMT_NEW_ACTION §4.3/§4.4`，已裁 = **只记账 + L1 落地**）::

        她在 MMT 那一刻写 {"noticed": "名字"} → 引擎落一条 `noticed` 事件（N5b）
        → **本函数**: 找到"她说话那一刻属于哪条新 episode" → akin{新 → 她指的}

    ⚠️ **归属判据 = "该账之前、最近的、被某条 episode 认领的内容事件"**
    （`bisect` 在认领 seq 集合里取 `≤ noticed.seq` 的最大者）, 而不是"区间包含" ——
    `noticed` 是**非内容事件**, 它自己的 seq 不在任何 episode 的 `event_seq` 里
    （`digest.new_events` 按 `is_content_event` 过滤）⇒ 包含式判据永远落空。
    ⚠️ 这**依赖 N5b 的落账时机**（账写在那一轮她的话**之后**）: 否则"最近的前一条内容"
      会落到**上一轮**（静默错归属 —— 边连到了错误的那条记忆上）。

    ⚠️ **一跳都不猜**: 找不到归属（本段没产出 episode / 那笔落在所有内容之前）⇒
    **不落边 + 记账**（`unclaimed`）。⚠️ `PROCEED §3` 待裁 #7（"下次 L1 要不要重扫"）
    按 2026-09-29 用户裁决**先不做**: 先丢 + 看台账, 真机上 `unclaimed` 多起来再谈
    （重扫要新存一个"未认领水位", 而"零新存储"正是这条设计的好处之一）。

    幂等: `add_edge` 同 `(rel, src, dst)` 跳过（且 `akin` 对称 ⇒ `canonical_for` 归一）。
    ⚠️ **因此"新 → 旧"的方向不体现在边表里**（对称边被规范成固定顺序）——
    方向只在台账里（`digest_akin new= old=`）。这是**有意的**: `akin` 的语义就是
    "她觉得这两条像"（对称, 见 `DESIGN_MMT_NEW_ACTION §4.5.2`）, 方向不带信息。
    """
    import bisect

    # seq → 主人（本段产的 episode）。⚠️ **区间会交叠**（真机实测 1 对: m0015 ⊃ m0016,
    # 用户裁决"两条都保留"）⇒ 同一 seq 可能有两个主人。取**靠后**那条（其起点更大 =
    # 更"当下"的那件; 按 min(event_seq) 排序后后写覆盖, 结果与 id 顺序无关）。
    owner: dict[int, str] = {}
    for nid in sorted(episode_ids,
                      key=lambda i: min((store.get(i).event_seq or [10 ** 9]))):
        node = store.get(nid)
        if node is None:
            continue
        for s in node.event_seq or []:
            try:
                owner[int(s)] = nid
            except (TypeError, ValueError):
                continue
    claimed = sorted(owner)
    edges = lost = self_skip = 0
    for e in noticed:
        hit = str(((getattr(e, "payload", None) or {}).get("hit") or "")).strip()
        if not hit or store.get(hit) is None:            # 她指的那条不在库里（旧档/被清）
            lost += 1
            logger.info("digest_akin skip=no_target hit=%r", hit)
            continue
        i = bisect.bisect_right(claimed, e.seq) - 1      # 最近的前一条"有主"内容
        if i < 0:
            lost += 1
            logger.info("digest_akin skip=unclaimed seq=%d title=%r", e.seq,
                        (getattr(e, "payload", None) or {}).get("title"))
            continue
        src = owner[claimed[i]]
        if src == hit:                                   # 本段那条就是她指的那条
            self_skip += 1
            continue
        store.add_edge(REL_AKIN, src, hit, ts=(getattr(e, "ts", "") or ts))
        edges += 1
        logger.info("digest_akin new=%s old=%s", src, hit)
    return edges, lost, self_skip
