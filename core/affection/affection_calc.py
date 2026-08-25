# -*- coding: utf-8 -*-
"""好感度（羁绊值）——查表方案。

行为: 好感度计算 = AI 在总结（digest）时返回"增加多少 exp"，根据 exp 查表算等级。
表: data/basic/affection.json（游戏数据, 不好拟合所以查表）:
  - Level-EXPgap-TotalRequiredEXP: {level: [gap, total]}——[当前升级所需经验, 累计门槛经验]
    table["2"] = [30, 15]: 2 级门槛 = 累计 15 exp, 升 3 级需再 30 exp
  - AffectionRaiser: 行为 → exp（cafe_ex/日程/礼物等——以后其他行为加好感统一进来）

规则:
  - level 1-100, 初始 1; 到 100 级经验继续增长但等级不动（BA 同款: 满级后仍累计）
  - 经验只增不减（好感不降——BA 无降好感机制）
  - bonus（概率双倍经验）预留: 调用方在 add_exp 前自行翻倍, 本类不管随机
"""
from __future__ import annotations

import json
import logging
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
    """好感度（level 1-100 + 累计 exp, 查表）。

    >>> a = Affection(table=load_affection_table())
    >>> a.add_exp(50)          # 50 >= 45 → level 3（累计 exp 50）
    >>> a.level, a.exp
    (3, 50)
    """
    def __init__(
        self,
        level: int = MIN_LEVEL,
        exp: int = 0,
        table: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        self._table = table if table is not None else load_affection_table()
        self.level = int(level)
        self.exp = int(exp)
        if self.exp < 0:
            self.exp = 0
        self._recalc_level()

    # -- 状态 -----------------------------------------------------------
    @property
    def is_max(self) -> bool:
        """满级（100 级后经验仍累计, 等级不动）。"""
        return self.level >= MAX_LEVEL

    def progress(self) -> float:
        """当前等级内进度 0-1（进度条用）; 满级 → 1.0。"""
        if self.is_max:
            return 1.0
        gap, total = self._table.get(str(self.level), (0, 0))
        if gap <= 0:
            return 0.0
        return min(1.0, max(0.0, (self.exp - total) / gap))

    def exp_to_next(self) -> int:
        """升下一级还差多少 exp; 满级 → 0。"""
        if self.is_max:
            return 0
        gap, total = self._table.get(str(self.level), (0, 0))
        return max(0, gap - (self.exp - total))

    # -- 变更 -----------------------------------------------------------
    def add_exp(self, delta: int) -> None:
        """加经验（只增不减, 负值按 0 处理）→ 查表更新等级（cap 100）。"""
        if delta <= 0:
            return
        self.exp += int(delta)
        self._recalc_level()

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
        {level, exp}; 无 affection 事件或累计 0 → None。
    """
    total = 0
    for e in events:
        if getattr(e, "type", None) != "affection":
            continue
        # 过滤键 = 该好感事件覆盖的互动上限（digested_seq）——affection 事件自身的
        # seq 在互动之后, 用自身 seq 过滤会把"该次 digest 的结果"误排除
        covered = int(e.payload.get("digested_seq", getattr(e, "seq", 0)) or 0)
        if up_to_seq is not None and covered > up_to_seq:
            continue
        try:
            total += int(e.payload.get("delta", 0) or 0)
        except (TypeError, ValueError, AttributeError):
            continue
    if total <= 0:
        return None
    aff = Affection(exp=total)
    return aff.to_dict()
