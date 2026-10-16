"""好感度（羁绊值）—— 查表算等级。

exp 是**带符号的累计量**（关系能变坏），地板 0；等级 1-100，满级后 exp 继续涨但等级不动。
表 = `data/basic/affection.json`：`Level-EXPgap-TotalRequiredEXP`（每级 [升下一级所需, 累计门槛]）
+ `AffectionRaiser`（行为 → exp；当前零调用方）。

带符号的理由：同频召回要算 `|现在 − 编码时|`（见 `to_scalar`），只增不减的量表达不了"变坏"。
"""
from __future__ import annotations

import json
import logging
import math

from contract.errors import err
from infra import paths

logger = logging.getLogger(__name__)

#: 好感表路径（与 `data/basic/` 下其他运行时数据同源 = `paths.DATA_DIR`）
_AFFECTION_JSON = paths.DATA_DIR / "basic" / "affection.json"

MIN_LEVEL = 1
MAX_LEVEL = 100

#: 累计 exp 地板（关系恶化到底 = 中性; 不出现负经验）
MIN_EXP = 0

#: `to_scalar()` 的尺度（exp）: `tanh(exp / 此值)` → (−1, 1)。
#: 300 按真机量级定：一个完整章节的 digest delta ≈ 75 exp ⇒ 一章 ≈ +0.245（有区分度）。
#: 它只影响同频召回的差值分辨率——不进等级、不进面板、不喂 LLM。
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


# EXT: affection-behavior — "行为加好感"的接口（零调用方; docs/EXTENSION_POINTS.md）
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
    """好感度（等级 1-100 + 带符号累计 exp）。

    >>> a = Affection(table=load_affection_table())
    >>> a.add_exp(50)          # 50 ≥ 门槛 45 → 3 级
    >>> a.level, a.exp
    (3, 50)
    >>> a.add_exp(-70)         # 恶化 → exp 触地板 0, 等级回 1
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

    # EXT: affection-view — 进度条（未立项; docs/EXTENSION_POINTS.md）
    def progress(self) -> float:
        """当前等级内进度 0-1（进度条用）; 满级 → 1.0。"""
        if self.is_max:
            return 1.0
        gap, total = self._table.get(str(self.level), (0, 0))
        if gap <= 0:
            return 0.0
        return min(1.0, max(0.0, (self.exp - total) / gap))

    # EXT: affection-view — 升级差额（未立项; docs/EXTENSION_POINTS.md）
    def exp_to_next(self) -> int:
        """升下一级还差多少 exp; 满级 → 0。"""
        if self.is_max:
            return 0
        gap, total = self._table.get(str(self.level), (0, 0))
        return max(0, gap - (self.exp - total))

    # -- 变更 -----------------------------------------------------------
    def add_exp(self, delta: int) -> None:
        """加/减经验 → 重查表（等级 cap 100）。负 delta 走同一条路径; 累计触地板归中性。"""
        if delta == 0:
            return
        self.exp = max(MIN_EXP, self.exp + int(delta))
        self._recalc_level()

    def to_scalar(self) -> float:
        """带符号标量 ∈ (−1, 1) —— 同频召回用（`tanh(exp / SCALAR_SCALE)`）。

        保号、单调、饱和、`exp=0 → 0.0`; 只看两点的**差**, 不假装能顶替"心情"。
        """
        return math.tanh(self.exp / SCALAR_SCALE)

    # EXT: affection-behavior — 行为名 → exp（零调用方; docs/EXTENSION_POINTS.md）
    def add_behavior(self, behavior: str, raiser: dict[str, int] | None = None) -> int:
        """按行为加好感（`AffectionRaiser` 表）→ 返回加的 exp; 行为不在表里 → warning + 0。"""
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
    def from_dict(cls, d: dict, table: dict[str, tuple[int, int]] | None = None) -> Affection:
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
    """从事件流累计好感（**真源**; `wiki.affection` 只是缓存）→ `{level, exp}`。

    `up_to_seq` = rewind 用: 只累计覆盖范围 ≤ 它的 affection 事件（回退到某点 = 该点
    之前全部 delta 的累计, 自动正确）。过滤键取事件的 `digested_seq`（它覆盖的互动上限）
    ——用事件自身的 seq 会把"该次 digest 的结果"误排除。

    该 session **一条好感事件都没有 → None**（无数据）; 有事件但累计 ≤ 0（含恶化到地板）
    → `{level: 1, exp: 0}`。"关系中性"与"无数据"是两件事, 前者要参与 `best_affection` 的比较。
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
