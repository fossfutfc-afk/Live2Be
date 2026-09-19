# -*- coding: utf-8 -*-
"""place_fuse — **地点两轴融合**（叙事轴 × 素材轴）: 两个纯函数, 不给旋钮。

## 用户原话（2026-09-20）

> *"现在考虑一下背景 RAG，我觉得最好是混合策略，一个特殊的 magic function，
> 在 writer 词和 key 相似度都高的时候值高，反之一般"*

## 两根轴（**必须不同源**, 否则不叫混合）

| 轴 | 输入 | 算什么 | 谁提供 |
|---|---|---|---|
| **叙事轴 `sw`** | writer 原话 ↔ 记忆里的原话（`node.place_raw`） | **语义**（embedding cos） | 调用方（要 `embed_fn`） |
| **素材轴 `sk`** | 键 ↔ 键 | **字面**（别名 / 键名 token 重叠, 0 调用） | 本模块 `key_similarity()` |

⚠️ **素材轴刻意走字面**: 若键侧也拿别名文本去 embedding, 两轴**同源**（都是
文本↔文本的 cos）→ 高度相关 → 融合退化成单轴。实测也支持字面这条路（2026-09-20）:

* `天台` 指 3 个键（`school_rooftop` / `rooftop` / `building_roof_top`）——它们**别名直接相交**;
* 而 **`dir` 不能当"同一个地方"的判据**: 那三个键分属
  `DIR_SchoolRoodtop` / `DIR_Rooftop` / `DIR_Building` —— 作者的目录按**图族**组织,
  不是按地点身份（这正是本模块要补的那个洞）;
* "一个别名指多键"在真表里只有 2 例（`天台` / `楼顶`）——**少, 但都是真·同地不同键**。

## 形状: 调和平均（用户 2026-09-20 选定）

    magic(sw, sk) = 2·sw·sk / (sw + sk)

| 形状 | 两轴都高 | **一高一低** | 两轴都低 |
|---|---|---|---|
| 加权和 | 高 | **高**（单轴就能拉满 —— 不是用户要的） | 低 |
| 乘积 | 高 | 低（惩罚过狠, "一般"被打成"很低"） | 低 |
| 几何平均 | 高 | 中（略高于调和） | 低 |
| **调和平均** | 高 | **中（"反之一般"）** | 低 |

严格顺序（正数、不相等时）: **乘积 ≤ 调和平均 ≤ 几何平均**（`HM ≤ GM` 是恒等式）。
实测 `(0.8, 0.4)`: 乘积 0.32 / 调和 0.533 / 几何 0.566; `(0.9, 0.3)`: 0.27 / 0.45 / 0.52。

`magic(高, 0) == 0` 是形状自带的语义: **一根轴为零 ⇒ 两条没关系**（不是"弱关系"）——
所以"只有措辞像、键八竿子打不着"的候选照样进不来（假阳性不因融合而放开）。

## 🚫 无阈值、无旋钮（T17）

配置面不许有阈值旋钮（用户裁决; `test_no_threshold_knobs_left` 钉着）, 未标定的硬闸门
曾把新认知永远掐死。**本模块只出分**; "取前 k 条"是合成层的事
（`core/brain/wiki_v2/channels.py` 纪律 #2/#3: 链路只出 raw, 最终分由合成层算）。
`mode` 是**代码里的显式选项**（给对照/测试用）, 不是配置项。

## 两边共用（用户 2026-09-20 选定）

函数只写一份; **召回侧**（`channel_impl.PlaceGate`: `sw` = `place_raw` 语义相似、
`sk` = 键字面相似）与**解析侧**（writer 原话 → 键: `sw` = 原话之间像不像、
`sk` = 候选键与已知键近不近）各自注入, 两根轴的含义由**各自**定义。
"""
from __future__ import annotations

import re

from core.media.place_table import PlaceTable, load_table

#: 键名 token 的最短长度（与层1 `_MIN_NEEDLE` 同一条纪律: 单字会满地把误命中）
_MIN_TOKEN = 2

_SPLIT_TOKEN = re.compile(r"[^0-9a-z]+")


def harmonic(a: float, b: float) -> float:
    """调和平均 `2ab/(a+b)`（**默认形状**）。两轴都 0 → 0（不抛）。"""
    a, b = float(a or 0.0), float(b or 0.0)
    if a <= 0.0 or b <= 0.0:
        return 0.0
    return 2.0 * a * b / (a + b)


def geometric(a: float, b: float) -> float:
    """几何平均 `√(ab)`（备选: 单轴高时比调和平均略高）。"""
    a, b = float(a or 0.0), float(b or 0.0)
    if a <= 0.0 or b <= 0.0:
        return 0.0
    return (a * b) ** 0.5


def product(a: float, b: float) -> float:
    """乘积 `ab`（备选: 惩罚最狠 —— "只有两轴都对上才算数"）。"""
    a, b = float(a or 0.0), float(b or 0.0)
    if a <= 0.0 or b <= 0.0:
        return 0.0
    return a * b


#: 形状表（`mode` 取值 → 函数）——**代码里的显式选项, 不是配置项**
MODES = {"harmonic": harmonic, "geometric": geometric, "product": product}

#: 默认形状（用户 2026-09-20 选定）
DEFAULT_MODE = "harmonic"


def magic(sw: float, sk: float, *, mode: str = DEFAULT_MODE) -> float:
    """两轴融合（见模块 docstring; 默认调和平均）。未知 mode → `ValueError`。

    参数约定: 两轴都应是 **[0, 1]** 的正向相似度。两个夹取都在这一个地方做:

    * **负**（cos 落在负半轴 / None）→ 0: 负相关不是"弱相关", 它对"同一个地方"是**反证据**
    * **过冲 >1**（cos 的浮点误差常给 `1+1e-16`）→ 夹到 1: 免得合成层拿到量纲外的分
    """
    try:
        f = MODES[mode]
    except KeyError:
        raise ValueError(f"未知融合形状: {mode!r}（可选 {sorted(MODES)}）") from None
    a = min(1.0, max(0.0, float(sw or 0.0)))
    b = min(1.0, max(0.0, float(sk or 0.0)))
    return f(a, b)


# ---------------------------------------------------------------------------
# 素材轴: 键 ↔ 键的字面相似度
# ---------------------------------------------------------------------------

def _aliases(key: str, table: PlaceTable | None) -> set[str]:
    """一个键的别名集（`place` + `keywords`）; 表里没有这个键 → 只有键名本身。"""
    k = (key or "").strip()
    if not k:
        return set()
    e = table.get(k) if table is not None else None
    raw = e.aliases() if e is not None else (k,)
    return {a.strip().lower() for a in raw if a and a.strip()}


def _keyset(key: str, table: PlaceTable | None) -> set[str]:
    """键名 token 集（按非字母数字切, 丢掉 <2 字的碎片）。"""
    return {t for t in _SPLIT_TOKEN.split((key or "").strip().lower())
            if len(t) >= _MIN_TOKEN}


def _overlap(a: set[str], b: set[str]) -> float:
    """包含系数 `|A∩B| / min(|A|,|B|)`（不是 Jaccard —— 别名多寡不该稀释"同名"）。"""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def key_similarity_by(a: str, b: str, *,
                      table: PlaceTable | None = None) -> tuple[float, str]:
    """`(相似度, 来源)` —— 来源 ∈ `same` / `alias` / `token` / `none`。

    判据（取两法最大值, 都是**纯字面**, 0 调用）:

    1. **同名** → 1.0
    2. **别名相交**（`|A∩B|/min`）—— 真表实测: `天台` 把 `school_rooftop` /
       `building_roof_top` 连起来（1/3 ≈ 0.33）
    3. **键名 token 相交** —— `school_rooftop` vs `rooftop` → 1.0;
       `view_sky` vs `view_constellation` → 0.5（都是"看天"的族, 但不是同一张图）

    `table=None` → 自动 `load_table()`（**mtime 缓存**, 改表即生效）;
    表读不出来 → 退回"只有键名"（退化但不抛）。
    """
    x, y = (a or "").strip().lower(), (b or "").strip().lower()
    if not x or not y:
        return 0.0, "none"
    if x == y:
        return 1.0, "same"
    t = table if table is not None else load_table()
    if not t:
        t = None
    by_alias = _overlap(_aliases(x, t), _aliases(y, t))
    by_token = _overlap(_keyset(x, t), _keyset(y, t))
    if by_alias <= 0.0 and by_token <= 0.0:
        return 0.0, "none"
    if by_alias >= by_token:
        return float(by_alias), "alias"
    return float(by_token), "token"


def key_similarity(a: str, b: str, *, table: PlaceTable | None = None) -> float:
    """只要分数（来源见 `key_similarity_by`）。"""
    return key_similarity_by(a, b, table=table)[0]


def key_similarity_to_set(keys, query: str, *,
                          table: PlaceTable | None = None) -> tuple[float, str, str]:
    """一个键**集合**（如 `node.place`）与查询键的相似度 → `(分, 来源, 命中的那个键)`。

    取集合内最大 —— "这条记忆里只要有一个键跟当前这个地方对得上/同族"就够了。
    """
    best, best_by, best_key = 0.0, "none", ""
    for k in keys or ():
        s, by = key_similarity_by(str(k), query, table=table)
        if s > best:
            best, best_by, best_key = s, by, str(k)
    return best, best_by, best_key


__all__ = [
    "DEFAULT_MODE",
    "MODES",
    "geometric",
    "harmonic",
    "key_similarity",
    "key_similarity_by",
    "key_similarity_to_set",
    "magic",
    "product",
]
