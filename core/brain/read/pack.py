# -*- coding: utf-8 -*-
"""pack — 召回的**候选包**（读路径的形状层, 2026-10-08）。

「一个包、两个类」里的那个**包**: 不分候选是怎么来的, 上层与台账拿到的都是同一个形状。

| 类 | 输入 | 要什么 | 分是什么 |
|---|---|---|---|
| `find`（定向寻找） | 一个**锚**（名字 / 对象 / 类 / 时间 / 轴 / 关系） | **全部**符合的（漏一条即错） | 只是展示顺序 |
| `like`（相似召回） | 一段**情境**（玩家这一句 / 本段经历） | **最像的 k 条** | **就是答案** |

所以 `Candidate` 不假设"分越小越像"或"分有绝对含义"——`find` 会把全部结果塞进来,
`like` 会把 top-k 塞进来; 上层要做的只是**按顺序渲染**。

⚠️ **本模块只有形状**: 检索逻辑在 `find.py` / `like.py`。
⭐ **渲染**（`render_candidates`）住在 **`render.py`** —— 与 `render_cognition_line`
同款先例（"一个行渲染器、两个调用者共用"住渲染层, 不住形状层）: 它的两个调用者
（P19「你想起的事」/ 将来的 `look`）都只是**不同的文案**, 身体是同一支。

⚠️ **分层**: 只读, 不写图（`read/` 的包纪律）; 不 import `compose` / `recall`
（旧召回件保持零调用, 见 `tests/core/test_read_like.py` 的 import 黑名单守门）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

logger = logging.getLogger(__name__)

#: 台账里 `top=` 最多印几条（印多了没人读; "有几条"由 `cand=` 承担 —— 少花 ≠ 少信息）
LEDGER_TOP = 3


@dataclass(frozen=True)
class Candidate:
    """一条候选: **节点 + 分 + 凭什么**。

    ⚠️ `why` 由**打分函数顺手写下**（`like.part_*` 返回的第二个值拼起来),
    **绝不事后重算**: 重算就是第二个真源, 迟早与出分那一刻的 `max` / 权重语义漂开
    （`recall._keyword_candidates` 的注释里踩过这条 —— 它同一个函数里就写了两遍,
    只好靠"`if s > best` 逐个比较"来保证同步）。

    ⚠️ **没有 `parts`**: 中间量（各轴原始分）留在 `part_*` 里 ——
    那些函数**各自可单测**（`part_temporal(age=200)` 直接断言等于 `floor`）,
    不必从候选身上挖。多路召回真接进来（语义/结构/轴）时若还需要"这个分是谁给的",
    再议。
    """

    node: object
    score: float = 0.0
    why: str = ""


def _one_line(text: object, cap: int = 40) -> str:
    """日志安全的一行: 去换行、截断（台账是**日志**, 不进她的视图）。"""
    s = " ".join(str(text or "").split())
    return s if len(s) <= cap else s[:cap] + "…"


def ledger_line(cands: Iterable[Candidate], *, query: str = "", pool: int = 0,
                k: int = 0, spec: str = "", skip: Iterable[str] = (),
                weights: dict | None = None, note: str = "") -> str:
    """一行召回台账（**只给日志/探针**, 不写盘、不给她看 —— 编号在这儿是允许的）。

    形如::

        recall_like spec=turn q=「老师，你今天有空吗」 pool=21 cand=1 k=3 skip=struct(权重0) \
top=m0014:0.520←tags[老师] · 2 周前 · 重要 0.85

    Args:
        cands: **截断前**的候选（已降序）—— `cand=` 由它的长度算,
            所以"够 k 条"和"只有 2 条"在台账里一眼能分。
        pool: 参与打分的节点数（选面过滤之后）—— 与 `cand` 一起看才知道
            是"没料"还是"料都被筛掉了"。
        spec: 档位名（哪个场景在问）。
        skip: **没参与的路 + 为什么**（`名字(权重0)` / `名字(无emo_now)`）——
            ⚠️ 这一格是"这次调用到底调了哪几路"的唯一线索, 别省。
        weights: 调用方的一次性覆盖（只印出来的那几路, 便于复盘"这次为什么不同"）。
        note: 可选的附加说明（降级原因等）; 空则不出这一段。
    """
    items = list(cands)
    top = "; ".join(f"{getattr(c.node, 'id', '?')}:{c.score:.3f}"
                    + (f"←{c.why}" if c.why else "")
                    for c in items[:LEDGER_TOP]) or "-"
    line = (f"recall_like{' spec=' + spec if spec else ''} "
            f"q=「{_one_line(query)}」 pool={int(pool)} "
            f"cand={len(items)} k={int(k)} top={top}")
    if skip:
        line += f" skip={','.join(str(s) for s in skip)}"
    if weights:
        line += " w=" + ",".join(f"{n}{float(v):.2f}" for n, v in sorted(weights.items()))
    return line + (f" note={_one_line(note, 60)}" if note else "")


__all__ = ["LEDGER_TOP", "Candidate", "ledger_line"]
