# -*- coding: utf-8 -*-
"""好感度（羁绊值）——查表方案。

行为: 好感度计算 = AI 在总结（digest）时返回"增加多少 exp"，根据 exp 查表算等级。
表: data/basic/affection.json（游戏数据, 不好拟合所以查表）:
  - Level-EXPgap-TotalRequiredEXP: {level: [gap, total]}——[当前升级所需经验, 累计门槛经验]
    table["2"] = [30, 15]: 2 级门槛 = 累计 15 exp, 升 3 级需再 30 exp
  - AffectionRaiser: 行为 → exp（cafe_ex/日程/礼物等——以后其他行为加好感统一进来）

规则:
  - level 1-100, 初始 1; 到 100 级经验继续增长但等级不动（BA 同款: 满级后仍累计）
  - **经验可增可减（2026-09-13 立项: 关系能变坏）**——`exp` 是**带符号的累计量**,
    地板 MIN_EXP=0（不出现负经验; 关系恶化到 0 = 回到中性, 等级回 MIN_LEVEL）。
    历史上的"只增不减"契约（BA 无降好感机制）**已推翻**——理由:
    现有全部召回信号都是单调累积量, **没有一个能表达"变坏"**;
    带符号后才有 `mood_congruence = 1 − |aff_now − aff_at_encoding|/量程`
    这个同频召回轴（docs/DESIGN_WIKI_V3.md §3.3.3）。
  - bonus（概率双倍经验）预留: 调用方在 add_exp 前自行翻倍, 本类不管随机
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from core.common.errors import err

logger = logging.getLogger(__name__)

#: 好感表路径（项目根绝对路径——cwd 无关）
_AFFECTION_JSON = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "basic" / "affection.json"
)

MIN_LEVEL = 1
MAX_LEVEL = 100

#: 累计 exp 地板（关系恶化到底 = 中性; 不出现负经验）
MIN_EXP = 0

#: `to_scalar()` 的尺度常数（exp）——`tanh(exp/此值)` → (−1, 1)。
#: **按真机量级定，不是拍的**（2026-09-13 实测）: 真机一个完整章节的 digest
#: delta = **75 exp**（haruka/mutsuki 两条线皆然）。初版拍 5000 → `tanh(75/5000)`
#: = **+0.015**，几乎为 0——那种尺度下同频信号要几十章才浮得出来，**等于没有**。
#: 取 300 → 一章好感 ≈ **+0.245**（有区分度的量级）; 满级 240,225 exp → 饱和 1.0。
#: ⚠️ 这个常数**只影响同频召回的差值分辨率**，不是玩法数值——
#: 它不进等级/不进面板/不喂 LLM。
SCALAR_SCALE = 300.0


def load_affection_table() -> dict[str, tuple[int, int]]:
    """读好感表 → {level_str: (gap, total)}; 缺失/损坏 → 抛 err 异常。"""
    if not _AFFECTION_JSON.is_file():
        raise FileNotFoundError(err("AffectionTable", f"好感表不存在: {_AFFECTION_JSON}"))
    try:
        data = json.loads(_AFFECTION_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(err("AffectionTable", f"好感表损坏: {e}")) from e
    table: dict[str, tuple[int, int]] = {}
    for lv, pair in (data.get("Level-EXPgap-TotalRequiredEXP") or {}).items():
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            table[str(lv)] = (int(pair[0]), int(pair[1]))
    if not table:
        raise ValueError(err("AffectionTable", "好感表为空（无 Level-EXPgap-TotalRequiredEXP）"))
    return table


# EXT: affection-behavior — "未来行为加好感"（events.py 的 TYPE_AFFECTION 注释）的接口;
# 当前无 live 调用（审计台账已记）——接线前不要删（docs/EXTENSION_POINTS.md）
def load_raiser_table() -> dict[str, int]:
    """读行为加好感表 → {行为名: exp}（AffectionRaiser; 缺失 → 空 dict, 不阻塞）。"""
    if not _AFFECTION_JSON.is_file():
        return {}
    try:
        data = json.loads(_AFFECTION_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning(err("AffectionTable", f"AffectionRaiser 读取失败: {e}"))
        return {}
    raiser = data.get("AffectionRaiser") or {}
    return {str(k): int(v) for k, v in raiser.items() if isinstance(v, (int, float))}


class Affection:
    """好感度（level 1-100 + **带符号**累计 exp, 查表）。

    >>> a = Affection(table=load_affection_table())
    >>> a.add_exp(50)          # 50 >= 45 → level 3（累计 exp 50）
    >>> a.level, a.exp
    (3, 50)
    >>> a.add_exp(-70)         # 恶化 → 触发 exp 地板 0, 等级回 1
    >>> a.level, a.exp
    (1, 0)
    """
    def __init__(
        self,
        level: int = MIN_LEVEL,
        exp: int = 0,
        table: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        self._table = table if table is not None else load_affection_table()
        self.level = int(level)
        self.exp = max(MIN_EXP, int(exp))       # 地板: 不出现负经验
        self._recalc_level()

    # -- 状态 -----------------------------------------------------------
    @property
    def is_max(self) -> bool:
        """满级（100 级后经验仍累计, 等级不动）。"""
        return self.level >= MAX_LEVEL

    # EXT: affection-view — 好感可视化（进度条, 未立项）; 勿删（docs/EXTENSION_POINTS.md）
    def progress(self) -> float:
        """当前等级内进度 0-1（进度条用）; 满级 → 1.0。"""
        if self.is_max:
            return 1.0
        gap, total = self._table.get(str(self.level), (0, 0))
        if gap <= 0:
            return 0.0
        return min(1.0, max(0.0, (self.exp - total) / gap))

    # EXT: affection-view — 好感可视化（升级差额, 未立项）; 勿删（docs/EXTENSION_POINTS.md）
    def exp_to_next(self) -> int:
        """升下一级还差多少 exp; 满级 → 0。"""
        if self.is_max:
            return 0
        gap, total = self._table.get(str(self.level), (0, 0))
        return max(0, gap - (self.exp - total))

    # -- 变更 -----------------------------------------------------------
    def add_exp(self, delta: int) -> None:
        """加/减经验 → 查表更新等级（cap 100）。

        **2026-09-13 起 delta 可为负**（关系能变坏）; 累计 exp 触地板 MIN_EXP=0
        （不出现负经验, 恶化到底 = 中性）。`delta == 0` 早退（无变化不重算）。
        行为本身不变: 仍是"只做累加 + 重查表", 负值走同一条路径。
        """
        if delta == 0:
            return
        self.exp = max(MIN_EXP, self.exp + int(delta))
        self._recalc_level()

    def to_scalar(self) -> float:
        """带符号标量 ∈ (−1, 1) —— **同频召回用**（§3.3.3）。

        `tanh(exp / SCALAR_SCALE)`：保号、单调、饱和、`exp=0 → 0.0`（中性）。
        尺度不敏感是**故意的**——同频只关心 `|now − at_encoding|` 的**差**，
        不关心绝对量级；且好感是慢变量, 本函数不假装能顶替"心情"。
        真机锚点（`SCALAR_SCALE=300`）: 一章好感 75 exp → **+0.245**。
        """
        return math.tanh(self.exp / SCALAR_SCALE)

    # EXT: affection-behavior — "未来行为加好感"（行为名 → exp）的接口; 接线前不要删
    # （docs/EXTENSION_POINTS.md）——当前零调用者（审计台账已记）
    def add_behavior(self, behavior: str, raiser: dict[str, int] | None = None) -> int:
        """按行为加好感（AffectionRaiser 表, 如 gift_orange_l=60）→ 返回加的 exp。

        行为不在表里 → 记 warning + 加 0（不抛——宽容, 未来行为名扩展）。
        """
        table = raiser if raiser is not None else load_raiser_table()
        exp = table.get(behavior, 0)
        if exp <= 0:
            logger.warning(err("AffectionRaiser", f"行为不在好感表: {behavior}"))
            return 0
        self.add_exp(exp)
        return exp

    # -- 序列化 ---------------------------------------------------------
    def to_dict(self) -> dict:
        return {"level": self.level, "exp": self.exp}

    @classmethod
    def from_dict(cls, d: dict, table: dict[str, tuple[int, int]] | None = None) -> "Affection":
        return cls(level=d.get("level", MIN_LEVEL), exp=d.get("exp", 0), table=table)

    # -- 内部 -----------------------------------------------------------
    def _recalc_level(self) -> None:
        """按累计 exp 找等级: 最大的 lv 使 table[lv].total <= exp; cap MAX_LEVEL。"""
        lv = MIN_LEVEL
        for lv_str, (_gap, total) in self._table.items():
            if total <= self.exp:
                lv = int(lv_str)
            else:
                break
        self.level = min(max(lv, MIN_LEVEL), MAX_LEVEL)


def load_affection_from_events(events, up_to_seq: int | None = None) -> dict | None:
    """从事件流累计好感（**真源**; wiki.affection 只是缓存）。

    好感变化以 affection 事件入 events.jsonl（append-only）——累计 delta 查表算等级。
    up_to_seq: rewind 用——只累计 seq ≤ up_to_seq 的 affection 事件（回退到某点
    的好感 = 该点之前所有好感事件的累计, 自动正确）。

    Args:
        events: SessionStore.events() 事件列表（含 .type/.payload/.seq）。
        up_to_seq: 可选回退点（互动 seq 上限）; None = 全部。

    Returns:
        {level, exp}；**该 session 没有任何好感事件 → None**（= "无数据"）。
        事件存在但累计 ≤0（含**恶化到地板**）→ `{level: 1, exp: 0}`——
        2026-09-13 语义变更: 旧口径把"累计 ≤0"也当 None, 但**"关系中性/已恶化"
        与"无数据"是两件事**; 前者在 `best_affection` 里应当参与比较（它是一次
        真实的关系状态）, 后者应当被跳过。
    """
    total = 0
    seen = False
    for e in events:
        if getattr(e, "type", None) != "affection":
            continue
        # 过滤键 = 该好感事件覆盖的互动上限（digested_seq）——affection 事件自身的
        # seq 在互动之后, 用自身 seq 过滤会把"该次 digest 的结果"误排除
        covered = int(e.payload.get("digested_seq", getattr(e, "seq", 0)) or 0)
        if up_to_seq is not None and covered > up_to_seq:
            continue
        seen = True
        try:
            total += int(e.payload.get("delta", 0) or 0)
        except (TypeError, ValueError, AttributeError):
            continue
    if not seen:
        return None                             # 该 session 根本没有好感事件
    aff = Affection(exp=total)                  # 负累计 → 构造器吃地板 → 中性
    return aff.to_dict()
