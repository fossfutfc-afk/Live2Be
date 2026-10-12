"""fuse — 两轴融合的三个形状（**唯一实现**）。

## 为什么单独一个模块

用户 2026-09-20 定了两件事:

1. 形状 = **调和平均**（*"一个特殊的 magic function, 在两根轴都高的时候值高, 反之一般"*）
2. *"函数只写一份"* —— **召回侧**（`compose.py` 的"相关 × 强度"、`PlaceGate` 的
   "叙事 × 素材"）与**解析侧**（writer 原话 → 键）**各自注入轴的含义, 共用同一份形状函数**。

原先它长在 `core/media/place_fuse.py` 里（地点专属）。合成层要用同一个函数, 而
`brain` 反向依赖 `media` 是层次倒挂 ⇒ 形状搬到 `core/common/`（**纯算术, 零依赖**）,
`place_fuse` 原样 re-export（老调用方 / 老测试零改动）。

## 形状（三选一, `mode` 是**代码选项不是配置项**）

| 形状 | 两轴都高 | **一高一低** | 两轴都低 |
|---|---|---|---|
| 加权和 | 高 | **高**（单轴就能拉满 —— 不是用户要的） | 低 |
| 乘积 | 高 | 低（惩罚过狠, "一般"被打成"很低"） | 低 |
| 几何平均 | 高 | 中（略高于调和） | 低 |
| **调和平均** | 高 | **中（"反之一般"）** | 低 |

严格顺序（正数、不相等时）: **乘积 ≤ 调和平均 ≤ 几何平均**（`HM ≤ GM` 是恒等式）。
实测 `(0.8, 0.4)`: 乘积 0.32 / 调和 0.533 / 几何 0.566; `(0.9, 0.3)`: 0.27 / 0.45 / 0.52。

`fuse(高, 0) == 0` 是形状自带的语义: **一根轴为零 ⇒ 两条没关系**（不是"弱关系"）。

## `clamp` 参数（2026-09-20 用户裁决带出来的）

用户裁决: **`A` 的行列式不归一**（*"这个矩阵携带的信息本身就比较重很合理"*）——
而 `det = SIG·TIME + emo_span·emo_int` 是**两格之和**, 值域 **[0, 2]**
（`IntensityPrior.scale` 声明 `unit` 但上界是 2, 见那里的注释）。

* `clamp=True`（默认, 解析侧 / 地点两轴）: 轴一律夹到 **[0, 1]**（cos 的浮点过冲
  `1+1e-16` 常出现, 不夹会让合成层拿到量纲外的分）
* `clamp=False`（合成层的强度轴）: 只做**下界**（负 → 0）, 上界**不夹** —— 否则
  `prior > 1` 的那部分会被压平, "矩阵信息重"这条裁决就落不了地

## 🚫 无阈值、无旋钮（T17）

配置面不许有阈值旋钮（`test_no_threshold_knobs_left` 钉着）。本模块**只出分**;
"取前 k 条"是合成层的事（`channels.py` 纪律 #2/#3）。
"""
from __future__ import annotations

from collections.abc import Callable


def harmonic(a: float, b: float) -> float:
    """调和平均 `2ab/(a+b)`（**默认形状**）。两轴有一为 0 → 0（不抛）。"""
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
MODES: dict[str, Callable[[float, float], float]] = {
    "harmonic": harmonic, "geometric": geometric, "product": product,
}

#: 默认形状（用户 2026-09-20 选定）
DEFAULT_MODE = "harmonic"


def fuse(a: float, b: float, *, mode: str = DEFAULT_MODE,
         clamp: bool = True) -> float:
    """两轴融合（见模块 docstring; 默认调和平均）。未知 mode → `ValueError`。

    Args:
        a, b: 两根轴的分数。**必须不同源**才有意义（同源 ⇒ 两轴相关 ⇒ 融合退化成单轴）。
        mode: `MODES` 的键。
        clamp: `True` → 两轴都夹到 [0,1]（解析侧 / 地点两轴）;
            `False` → 只夹下界（合成层的强度轴可以 >1, 用户裁决"不归一"）。
    """
    f = MODES.get(mode)
    if f is None:
        raise ValueError(f"未知融合形状: {mode!r}（可选 {sorted(MODES)}）")
    x, y = float(a or 0.0), float(b or 0.0)
    if clamp:
        x, y = min(1.0, max(0.0, x)), min(1.0, max(0.0, y))
    else:
        x, y = max(0.0, x), max(0.0, y)   # 负相关不是"弱相关" → 一律 0（上界不夹）
    if x <= 0.0 or y <= 0.0:
        return 0.0
    return f(x, y)


#: 兼容名 / 用户叫法（*"一个特殊的 magic function"*）——**与 `fuse` 是同一个函数对象**
#: （`place_fuse.magic is fuse` 这条有测试钉着: 形状只写一份）
magic = fuse

__all__ = ["DEFAULT_MODE", "MODES", "fuse", "geometric", "harmonic", "magic",
           "product"]
