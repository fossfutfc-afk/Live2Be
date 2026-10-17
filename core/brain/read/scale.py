"""scale.py — 分数的尺度与归一的**唯一实现**（`read/` 的中性算术层）。

两条读路径共用同一份算术: 旧的 `channels` / `compose`（多链路合成）与新的 `like`（情境 ⇒ 最像的
k 条）各自注入轴的含义, 形状函数只有这一份 —— 与 `infra/fuse.py` 同一条纪律。

为什么住这儿: 新件（`like` / `pack` / `find`）**不许 import 旧族**（`test_read_like.py` 守门⑤）,
所以共用件只能落在这种两边都够得着、且谁也不拥有的中性件里。

零依赖: 不 import 任何 `read/` 兄弟, 不碰 store。
"""
from __future__ import annotations

import math
from collections.abc import Sequence

#: 原始分的尺度声明（合成层据此归一; 链路**不自己归一**）
#: `unit` **不是"保证 ≤1"**: A 的行列式是两格之和, 值域 [0, 2] —— 合成层不按声明夹 PRIOR 轴
SCALE_UNIT = "unit"             # [0, 1]（C 的 magic）; A 用它但值域 [0, 2]
SCALE_SIGNED = "signed"         # [−1, 1]
SCALE_COSINE = "cosine"         # [−1, 1], 但通常落在窄带 ⇒ 用池内 min-max 归一
SCALE_UNBOUNDED = "unbounded"   # 无界（合成层需先 log / 截断）
SCALES = (SCALE_UNIT, SCALE_SIGNED, SCALE_COSINE, SCALE_UNBOUNDED)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """余弦相似（空向量 / 零向量 → 0.0, 不抛）。"""
    if not a or not b:
        return 0.0
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def pool_minmax(values: dict[str, float]) -> dict[str, float]:
    """池内 min-max: 池内全同分 → 有正值则都算 1.0（"都一样相关"）, 全非正 → 0.0。

    只给 `SCALE_COSINE` 那类用: 它的原始分是**相对量**（谁比谁更像）。
    `SCALE_UNIT` 那类是绝对分, 拉到池内相对会**凭空制造"最差的一定是 0"**。
    """
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    span = hi - lo
    if span <= 1e-9:
        return dict.fromkeys(values, 1.0 if hi > 0.0 else 0.0)
    return {k: (v - lo) / span for k, v in values.items()}
