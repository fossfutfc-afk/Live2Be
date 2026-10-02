# -*- coding: utf-8 -*-
"""recall_ledger — 召回台账（观测层，零行为影响）。

**为什么需要它**（DESIGN_WIKI_V3 §3.5，2026-09-13 V3-0）:

记忆链路目前有两条**看不见的**路径，而它们正是所有"记忆不对劲"报障的所在:

| 路径 | 现状 | 看不见的后果 |
|---|---|---|
| **写路径**（候选碰撞） | `recommend_candidates` 抬出几条候选**提示**给 Round B（**2026-09-15 T17 起不再分档、不再结构强制**——阈值从未标定过、实测两模型下候选 6/6 全越线，闸门把"全部分侧面"判成同一件事） | 一段跑完有没有抬出候选？覆盖度与最高分分布，一行可查 |
| **读路径**（注入视图） | `render_character_view` 静态分桶（**2026-09-13 cap 已删**） | 这轮到底给了 LLM 哪几条？**曾经没有任何日志**。第 6 条以后的 belief 永远读不出来，却不告警——**这正是 cap 被删的原因**（cap 就是旧召回机制, 由 v3 实体车道接管） |

这与当初给 VN 加 `bond_board_deliver`（"这一板是怎么到玩家眼前的"）是同一个理由:
**先让事实可观测，再谈调优**。没有台账，V3-1~V3-6 每一步都无法验收。

## 日志口径（可 grep，值全为 `k=v`）

    写路径: `recall_write char=… eps=4 collide=12 hi=4 med=11 forced=100% mode=semantic thr=0.50/0.25`
    读路径: `recall_read char=… total=8 picked=8 dropped=0 mode=… buckets=belief:4 episode:4 …`
    合成层: `recall_compose char=… cands=12 ranked=4 pending=1 no_rel=6 mode=harmonic rel=[0.00,1.00] prior=[0.30,0.42] degraded=B_emotion_rag,C_place top=m0003:0.84,…`
    （2026-09-20 加第三条: 四条召回道路的**最终分**是怎么算出来的 —— 见 `compose.py`）

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

    用法（`digest._round_b_material` 内）::

        acc = CollisionAccount(char_id)
        acc.episode(n_cand=len(cands), best_sim=(cands[0][1] if cands else 0.0))
        acc.log(thr_k=k)          # mode 由调用方在 log 前设好
    """

    def __init__(self, char_id: str = "") -> None:
        self.char_id = char_id
        self.episodes = 0
        self.with_cand = 0       # 至少抬出一条候选的 episode 数
        self.no_cand = 0
        self.cands = 0
        self.best_sim = 0.0
        self.mode = "off"

    def episode(self, *, n_cand: int, best_sim: float = 0.0) -> None:
        """记一条 episode 的碰撞结果。

        ⚠️ 2026-09-15（T17）: `hi`/`med` 两档**已删**（候选不再分档、不再有阈值）。
        原先的 `forced%`（被结构强制 touch/update 的 episode 占比）随之消失——
        它就是"阈值把全部 episode 判成同一件事"那个失效模式的观测口，
        而结构强制本身已按 Q11/Q31/Q32 取消。
        """
        self.episodes += 1
        self.cands += int(n_cand)
        if best_sim > self.best_sim:
            self.best_sim = best_sim
        if n_cand > 0:
            self.with_cand += 1
        else:
            self.no_cand += 1

    def log(self, *, thr_k: int = 0, char_id: str = "") -> None:
        """打一行写路径台账（`mode` 由调用方在 `log` 前设好）。

        保留的观测量: `collide%`（有候选的 episode 占比——**它高不再是坏事**，
        因为候选只是提示；但**恒 0%** 说明 embedding 降级或库太空，
        那才是要查的）与 `best`（最高相似度，看分布用）。
        """
        if not ENABLED:
            return
        try:
            who = char_id or self.char_id
            rate = _pct(self.with_cand, self.episodes)
            warn = ""
            if self.episodes >= 3 and self.with_cand == 0:
                warn = " ⚠no_candidate"          # 一条候选都抬不出来 → 查后端/空库
            logger.info(
                "recall_write char=%s eps=%d collide=%s none=%d cands=%d "
                "best=%.2f mode=%s k=%d%s",
                who, self.episodes, rate, self.no_cand, self.cands,
                self.best_sim, self.mode, int(thr_k), warn)
        except Exception as e:                       # noqa: BLE001 — 台账绝不阻断
            logger.debug("recall_ledger 写路径打点失败: %s", e)


# ---------------------------------------------------------------------------
# 读路径（注入视图）
# ---------------------------------------------------------------------------

def log_read(*, char_id: str, total: int, picked: int, buckets: dict[str, str],
             mode: str = "", surface: str = "chara") -> None:
    """打一行读路径台账。

    Args:
        total: 图里全部节点数
        picked: 实际进入注入文本的节点数
        buckets: `{桶名: 注入条数}`（如 `{"belief": "4", "episode": "3"}`）。
            **2026-09-13 cap 全删后不再是 "选中/cap"**——桶内即全量, 无分母可言;
            故 `picked` 恒等于各桶之和（`dropped` 因此恒 0, 除非渲染层另有过滤）。
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


# ---------------------------------------------------------------------------
# 合成层（四条道路 → 最终分; `compose.py`）
# ---------------------------------------------------------------------------

def log_compose(*, char_id: str = "", cands: int = 0, ranked: int = 0,
                pending: int = 0, no_rel: int = 0, mode: str = "harmonic",
                rel_band: tuple[float, float] = (0.0, 0.0),
                prior_band: tuple[float, float] = (0.0, 0.0),
                degraded: str = "-", top: str = "-") -> None:
    """打一行合成台账（**"最终分是怎么来的"**——一条链路不够用时的排查口）。

    用法（合成层是纯函数, 打点由消费方做）::

        res = recall_now(store, ctx)
        log_compose(char_id=char, **res.ledger_fields())

    字段口径:
        cands    进过合成的候选数（= ranked + pending + no_rel + 被融合成 0 的）
        ranked   真的出了最终分、可参与注入的条数
        pending  有相关证据但**先验缺席**（A 的 `raw=None`: 旧档无 `ts`）→ 待补
        no_rel   只被 A 命中（**A 不能单独准入**）
        rel_band / prior_band  两根轴这次的实际分数带 —— 判断"是不是某一轴在独裁"
        degraded 这次降级的链路（**缺席, 不是 0 分**）
    """
    if not ENABLED:
        return
    try:
        logger.info(
            "recall_compose char=%s cands=%d ranked=%d pending=%d no_rel=%d "
            "mode=%s rel=[%.2f,%.2f] prior=[%.2f,%.2f] degraded=%s top=%s",
            char_id or "-", int(cands), int(ranked), int(pending), int(no_rel),
            mode, rel_band[0], rel_band[1], prior_band[0], prior_band[1],
            degraded or "-", top or "-")
    except Exception as e:                           # noqa: BLE001 — 台账绝不阻断
        logger.debug("recall_ledger 合成层打点失败: %s", e)
