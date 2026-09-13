# -*- coding: utf-8 -*-
"""recall_ledger — 召回台账（观测层，零行为影响）。

**为什么需要它**（DESIGN_WIKI_V3 §3.5，2026-09-13 V3-0）:

记忆链路目前有两条**看不见的**路径，而它们正是所有"记忆不对劲"报障的所在:

| 路径 | 现状 | 看不见的后果 |
|---|---|---|
| **写路径**（候选碰撞） | `recommend_candidates` 把候选标成【疑似同主题】→ `parse_round_b` **结构强制**只能 touch/update | 阈值是否把全部 episode 都判成同主题？**没有任何日志**。实测两个模型下都是 6/6 全越线 → 会禁止一切 add |
| **读路径**（注入视图） | `render_character_view` 静态分桶 + cap 截断 | 这轮到底给了 LLM 哪几条？哪些被 cap 掉了？**没有任何日志**。第 6 条以后的 belief 永远读不出来，却不告警 |

这与当初给 VN 加 `bond_board_deliver`（"这一板是怎么到玩家眼前的"）是同一个理由:
**先让事实可观测，再谈调优**。没有台账，V3-1~V3-6 每一步都无法验收。

## 日志口径（可 grep，值全为 `k=v`）

    写路径: `recall_write char=… eps=4 collide=12 hi=4 med=11 forced=100% mode=semantic thr=0.50/0.25`
    读路径: `recall_read char=… total=8 picked=5 dropped=3 mode=… buckets=belief:4/5 episode:3/6 …`

`mode`: `semantic`（embedding 可用）/ `keyword`（降级——`_get_embed_fn` 探针失败时）/ `off`。

## 红线

本模块**只读事实、只打日志**:
- 不改任何节点、不写 `last_recalled_at`（那是 V3-3 的事，且要评估代价）
- 不参与判定、不抛异常（观测层坏了绝不能阻断剧情）
- 打点失败静默降级（`宁缺勿错`）
"""
from __future__ import annotations

import logging

logger = logging.getLogger("live2be.brain")

#: 台账开关（测试可关；默认开——V3-0 的目的就是让事实可见）
ENABLED = True


def _pct(part: int, whole: int) -> str:
    return f"{int(round(100.0 * part / whole))}%" if whole else "-"


# ---------------------------------------------------------------------------
# 写路径（digest 候选碰撞）
# ---------------------------------------------------------------------------

class CollisionAccount:
    """一次 Round B 候选碰撞的累加器（跨 episode 聚合，最后打一行）。

    用法（`digest._round_b_material` 内）:
        acc = CollisionAccount(char_id)
        acc.episode(forced=bool(highs), n_cand=len(cands), hi=len(highs), med=len(meds))
        acc.log(thresholds, mode)
    """

    def __init__(self, char_id: str = "") -> None:
        self.char_id = char_id
        self.episodes = 0
        self.with_cand = 0
        self.forced = 0          # 带【疑似同主题】标注（= 结构强制 touch/update，禁 add）
        self.med_only = 0
        self.no_cand = 0
        self.cands = 0
        self.best_sim = 0.0
        self.mode = "off"

    def episode(self, *, hi: int, med: int, n_cand: int,
                best_sim: float = 0.0) -> None:
        """记一条 episode 的碰撞结果。"""
        self.episodes += 1
        self.cands += int(n_cand)
        if best_sim > self.best_sim:
            self.best_sim = best_sim
        if hi > 0:
            self.forced += 1
        elif med > 0:
            self.med_only += 1
        else:
            self.no_cand += 1

    def log(self, *, thr_high: float, thr_med: float, char_id: str = "") -> None:
        """打一行写路径台账（`mode` 由调用方在 `log` 前设好）。"""
        if not ENABLED:
            return
        try:
            who = char_id or self.char_id
            # accept 命中率 = 被结构强制 touch/update 的 episode 占比。
            # 它接近 100% → 阈值把"全部分侧面"判成"同一件事" → 新认知永远长不出来
            # （v2 的失效模式，实测两模型皆 6/6）；接近 0% 且库里认知很多 →
            # 可能是 embedding 降级导致候选抬不出来（另一侧失效）。
            rate = _pct(self.forced, self.episodes)
            warn = ""
            try:
                from core.brain.wiki_v2 import recall_config
                if (self.episodes >= 3
                        and self.forced / max(self.episodes, 1)
                        >= recall_config.get("accept_hit_rate")):
                    warn = " ⚠forced_high"
            except Exception:                        # noqa: BLE001 — 告警线取不到就算了
                pass
            logger.info(
                "recall_write char=%s eps=%d collide=%d forced=%s med_only=%d none=%d "
                "cands=%d best=%.2f mode=%s thr=%.2f/%.2f%s",
                who, self.episodes, self.cands, rate, self.med_only,
                self.no_cand, self.cands, self.best_sim, self.mode,
                thr_high, thr_med, warn)
        except Exception as e:                       # noqa: BLE001 — 台账绝不阻断
            logger.debug("recall_ledger 写路径打点失败: %s", e)


# ---------------------------------------------------------------------------
# 读路径（注入视图）
# ---------------------------------------------------------------------------

def log_read(*, char_id: str, total: int, picked: int, buckets: dict[str, str],
             mode: str = "", surface: str = "chara") -> None:
    """打一行读路径台账。

    Args:
        total: 图里全部节点数（含未被选中/被 cap 掉的）
        picked: 实际进入注入文本的节点数
        buckets: `{桶名: "选中/cap"}`（如 `{"belief": "4/5", "episode": "3/6"}`）
        mode: `semantic` / `keyword` / `off`（embedding 可用性——读路径 v3 才用它，
              v2 的分桶视图不依赖向量，这里如实标 `off`）
        surface: `chara`（角色视图）/ `organize`（组织视图）
    """
    if not ENABLED:
        return
    try:
        dropped = max(total - picked, 0)
        bucket_txt = " ".join(f"{k}:{v}" for k, v in buckets.items())
        logger.info(
            "recall_read surface=%s char=%s total=%d picked=%d dropped=%d mode=%s buckets=%s",
            surface, char_id, total, picked, dropped, mode or "off", bucket_txt or "-")
    except Exception as e:                           # noqa: BLE001 — 台账绝不阻断
        logger.debug("recall_ledger 读路径打点失败: %s", e)
