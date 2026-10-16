"""`core.bond.bond_story` 的**板派生与交付模式**。

`DeliveryMode`（BLOCK 批式 / STREAM 流式）· `_board_spans`（一块记录按 `switch` / 老师群
切板）· `_BoardAssembler`（记录流 → 板, 内含板级闸 `check_board`）· `MAX_BOARDS_PER_TURN`。

依赖方向: `boards` → `scene`; **不许** import `engine`（engine 反过来用这里的三件）。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from enum import Enum
from typing import TYPE_CHECKING

from contract import (
    MAX_SENSEI_RUN,
    STAGE_MEMORIAL,
    STAGE_SWITCH,
    sensei_groups,
)
from core.bond.bond_story.scene import BondScene

if TYPE_CHECKING:               # 仅注解求值期 —— 运行期 import engine 会成环（见模块头纪律）
    from core.bond.bond_story.engine import BondStoryEngine

logger = logging.getLogger(__name__)


MAX_BOARDS_PER_TURN = 24


def _board_spans(records: tuple) -> list[tuple[int, int, tuple[int, ...]]]:
    """记录流块 → 板切分。

    板边界: ① **换场点前**（`switch` 记录另起一板）; ② **交互槽后**（老师的候选台词挂在
    本板末尾——"槽在板尾、反应在下一板"）。超长群（> `MAX_SENSEI_RUN`）再按上限切槽,
    每板一组候选项, 内容零损失。

    Returns: `[(起, 止, 本板群内记录下标)]`——止为开区间; 空块 → `[]`。
    """
    group_ends: dict[int, tuple[int, ...]] = {}
    for group in sensei_groups(records):
        for k in range(0, len(group), MAX_SENSEI_RUN):
            chunk = tuple(group[k:k + MAX_SENSEI_RUN])
            group_ends[chunk[-1]] = chunk
    spans: list[tuple[int, int, tuple[int, ...]]] = []
    start = 0
    for i, rec in enumerate(records):
        if i in group_ends:                      # 槽后收板（候选 = 本板 choices）
            spans.append((start, i + 1, group_ends[i]))
            start = i + 1
        elif i and getattr(rec, "stage", "") == STAGE_SWITCH and i > start:
            spans.append((start, i, ()))         # 换场前必切（已在板首则不重复切）
            start = i
    if start < len(records):
        spans.append((start, len(records), ()))
    return spans


class DeliveryMode(str, Enum):
    """交付模式 —— 决定"校验违规时是**拦**还是**记**"。

    · `BLOCK`（整块交付）: 块级 + 板级校验**都拦**（打回重发整轮）。
    · `STREAM`（增量交付, 生产）: 板级只在"还没有任何板交付出去"时拦; 一旦交付过
      就一律 advisory（只记账 + 日志）——"打回重发"产出的是**另一段文本**, 玩家侧表现为
      "同一段戏讲两遍"。块级同理（板已上屏, 无法回滚）。
    """

    BLOCK = "block"
    STREAM = "stream"


class _BoardAssembler:
    """记录 → 板 的**唯一装配器**——批式与流式共用一套语义（单源）。

    · **不可见板 → 向前合并**: 无可显示段落 + 无选项 + 非 end 的板, 记录并入下一板
      （真源不丢）; 若它是块的**最后一板**（无处可并）→ 照原样成板。向前而不向后并,
      是为了不动流式的首板即时交付（向后并要扣住一板不交付, 会吃掉首屏优化）。
    · **板上限**: 超出丢弃 + 一次 WARNING。
    · **`art` 挂首个板**（块级声明）。
    · **章内第二次 memorial** → `_demote_repeat_memorial` 静默降级。

    用法: 流式 `push(闭合板记录)` → 本次可交付的板, 块尾 `finish()`; 批式依次 push 再
    finish, 收 `boards`。两条路曾经的每一处分叉都钉在 `tests/core/test_pipeline_parity.py`。
    """

    def __init__(self, engine: BondStoryEngine, *, block_art: str = "",
                 notes: Iterable[str] = (),
                 max_boards: int = MAX_BOARDS_PER_TURN) -> None:
        self._engine = engine
        self._block_art = (block_art or "").strip()
        self._notes = tuple(notes)
        self._max_boards = max_boards
        self._out: list[BondScene] = []
        self._spare: tuple = ()
        self._art_attached = False
        self._cap_warned = False
        self._memorial_logged = False
        #: 本块是否已见过 `memorial` 记录（→ 之后的板都在纪念窗口里; 见 `_make`）
        self._memorial_seen = False

    # -- 块级上下文（流式下随流到达）----------------------------------------
    def set_block_art(self, art: str) -> None:
        """块级画面意向（流式下 `art` 行到达后才知道）——首个板交付前有效。"""
        if not self._art_attached and (art or "").strip():
            self._block_art = art.strip()

    def set_notes(self, notes: Iterable[str]) -> None:
        """解析 NOTE（流式下随流累积）——板交付时带上当前值。"""
        self._notes = tuple(notes)

    # -- 内部 ---------------------------------------------------------------
    @staticmethod
    def _group(records: tuple) -> tuple[int, ...]:
        """板内 sensei 群（= 本板候选项）——切板规则保证群在板尾。"""
        return tuple(i for i, r in enumerate(records) if r.is_sensei)

    def _cap_reached(self) -> bool:
        if len(self._out) < self._max_boards:
            return False
        if not self._cap_warned:
            self._cap_warned = True
            logger.warning("[vn][records] 本回合派生超过 %d 板 → 只发前 %d（其余丢弃）",
                           self._max_boards, self._max_boards)
        return True

    def _make(self, records: tuple) -> BondScene:
        """造板（**批式与流式唯一的造板口**）。

        在这里给 `in_memorial` 拍快照: 窗口 = 本块的 `memorial` 记录之后到块尾, 所以本块
        此后每一板都算; 只有组装器在造板这一刻必然知道它 —— 不依赖引擎那个会被预热提前
        翻掉的活标志。`push()` 里**先降级再调本函数**, 所以被静默拒绝的第二个 memorial
        不会误开窗口。
        """
        has_memorial = any(getattr(r, "stage", "") == STAGE_MEMORIAL for r in records)
        scene = BondScene.from_board(records, self._group(records),
                                     notes=list(self._notes),
                                     in_memorial=bool(has_memorial or self._memorial_seen))
        self._memorial_seen = self._memorial_seen or has_memorial   # 窗口开到块尾
        return scene

    def _emit(self, scene: BondScene) -> BondScene:
        if self._block_art and not self._art_attached:
            scene.art_hint = self._block_art          # 块级声明 → 挂首个板
            self._art_attached = True
        if scene.memorial:
            self._engine._memorial_used = True        # 章内 ≤1（区间 = 本板）
            if not self._memorial_logged:
                self._memorial_logged = True
                logger.info("[vn][records] 本回合含纪念触发（区间 = 本板; v2 不切模式）")
        self._out.append(scene)
        return scene

    # -- 对外 ---------------------------------------------------------------
    def push(self, records: Iterable) -> list[BondScene]:
        """喂一块**已闭合**的板记录 → 本次可交付的板（空 = 被挂起 / 超上限）。"""
        recs = tuple(records or ())
        if not recs:
            return []
        if self._spare:                               # 承接上一块的不可见记录
            recs = self._spare + recs
            self._spare = ()
        recs = self._engine._demote_repeat_memorial(recs)
        if self._cap_reached():
            return []
        scene = self._make(recs)
        if not scene.paragraphs and not scene.choices and not scene.is_end:
            self._spare = recs                        # 不可见 → 挂起, 并入下一板
            return []
        return [self._emit(scene)]

    def finish(self) -> list[BondScene]:
        """块尾: 挂起的不可见板**照原样成板**（无处可并; 与批式同规则）。"""
        if not self._spare:
            return []
        recs, self._spare = self._spare, ()
        if self._cap_reached():
            return []
        return [self._emit(self._make(recs))]

    @property
    def boards(self) -> list[BondScene]:
        return list(self._out)
