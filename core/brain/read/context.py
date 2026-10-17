"""context.py — 召回**输入契约**的唯一声明（`RecallContext`）。

一次召回里"现在几点 / 什么心情 / 在哪儿 / 对谁"只能有一份: 各路自己去 store / 事件流里捞,
同一次召回就会把这些算出好几份, 台账也复现不出来 ⇒ 输入在这里声明一次, 各路只读它。

字段分两半: **输入**（调用方填, 本模块）· **派生**（`like.RecallCtx` + `build_ctx` 现算）。
输入那几个是**对称的**: 情绪 / 地点各一对"键 + 原文", 因为它们服务的路不同
（键做集合比较, 原文做语义比较）。**这些都不进 LLM 上下文** —— 召回侧信号, 参与筛选不参与写作。

`now` **必填且无默认值**（要给 None 也得显式写）: 逼调用方在调用处说明"现在是什么时候",
不许模块偷偷读壁钟（同 `age_days` 的纪律）。

为什么住这儿: 新旧两条读路径都要用它, 而新件（`like` / `pack` / `find`）**不许 import 旧族**
（`test_read_like.py` 守门⑤）⇒ 契约只能落在谁也不拥有的中性件里。冻结值: 要变体就 `replace`。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RecallContext:
    """一次召回的输入（所有路共用同一个）。"""

    #: 当前**时刻** —— `datetime` 或 `ts` 串（`core/worldtime/age.py` 认这几种）; 给 None = 本路不用时间
    now: object | None
    #: 情境文本（MMT 每轮 = 玩家这一句; digest = 本段新经历）
    query: str = ""
    #: 当前**情绪键序列**（B 链路的 query 侧）—— 如 `("tease", "smile")`; `()` = 未知（那一路降级）
    emo_now: tuple[str, ...] = ()
    #: 当前地点**键**（C 链路的素材轴）—— `""` = 未知
    place_now: str = ""
    #: 当前地点的 **writer 原文**（switch 短语原话, C 链路的叙事轴）—— 键不能当地名用
    #: （一键多义 / 一地多键）, 所以"是不是同一个地方"只能靠原文的语义相似。`""` = 未知
    place_raw_now: str = ""
    #: 当前**好感标量** ∈ [−1, 1]（`Affection.to_scalar()`）—— 关系层信号
    aff_now: float | None = None
    #: 检索后端（`texts → 等长向量列表`）; None ⇒ 需要它的那几路自动降级
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None
    #: 本角色 id（词表 / 资产定位用）
    char_id: str = ""
