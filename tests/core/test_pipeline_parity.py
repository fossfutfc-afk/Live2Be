# -*- coding: utf-8 -*-
"""批式 vs 流式流水线的**特征化测试**（节点 1 建立 → 节点 2′ 更新为"统一后"）。

## 这个文件的双重身份

1. **特征化（characterization）**：记录两条路**当前**的可观测行为；
2. **回归网**：节点 2′ 统一流水线时它先红（5 例）——那时的红是**预期信号**，
   不是 bug；按新语义更新期望值即"统一完成"的证据。

## 两条流水线（节点 2′ 之后）

| | 批式 | 流式 |
|---|---|---|
| 触发 | 调用方**不传** `on_board`，或客户端没有 `chat_full` | 传了 `on_board` **且**有 `chat_full` |
| 切板 | `_board_spans`（整块视角） | `BlockStreamParser`（增量） |
| **装配** | **`_BoardAssembler`（同一个类）** | **`_BoardAssembler`（同一个类）** |
| 校验 | `check_block`（块级，拦）+ `check_board`（板级，拦） | `check_board`（板级，**仅首板交付前**拦）+ `check_block`（块级，advisory） |

⇒ 节点 2′ 之后**仅存的差异只有两类**，且都是**有意**的：
· **交付时机**（流式增量交付 vs 批式整块）——由 `DeliveryMode` 表达；
· **已交付后的校验是 advisory**（流式拦不住已上屏的板；打回重发会产出另一段文本
  = 玩家看到"同一段戏讲两遍"，见 `docs/DESIGN_RESEND.md` §3）。

## 节点 2′ 消掉的分叉（本文件逐条钉住）

| 差异 | 改动前 | 改动后 |
|---|---|---|
| 纯 `switch` 空板 | 批式合并 / 流式**照发空板** | 两侧都**向前合并** |
| 块尾纯 `switch` | 批式"向后并入末板" / 流式单独成板 | 两侧都**末板自成一板** |
| `art` 挂载 | 批式挂含 memorial 的板 / 流式挂首板 | 两侧都挂**首个板** |
| `MAX_BOARDS_PER_TURN` | 批式 24 / 流式**无上限** | 两侧都 24 |
| 硬违规（`end` 后有记录） | 批式拦 / 流式**照常交付** | 两侧都**拦**（流式仅首板前） |

运行: python -m pytest tests/core/test_pipeline_parity.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import (  # noqa: E402
    MAX_BOARDS_PER_TURN,
    BondStoryEngine,
    SceneLoopError,
)

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"


# ---------------------------------------------------------------------------
# 两个桩: 区别只有"有没有 chat_full"
# ---------------------------------------------------------------------------

class _BatchLLM:
    """只有 `chat()` —— 引擎看不到 `chat_full` ⇒ 走批式（`delivered` 恒空）。"""

    def __init__(self, block: str):
        self.block = block
        self.calls = 0

    def chat(self, messages, **kw):
        self.calls += 1
        return self.block


class _StreamLLM:
    """有 `chat_full` 且**真喂 chunk** ⇒ 走流式（板一闭合即 `on_board`）。"""

    def __init__(self, block: str, chunk: int = 0):
        self.block = block
        self.chunk = chunk
        self.calls = 0

    def chat_full(self, messages, **kw):
        self.calls += 1
        on_chunk = kw.get("on_chunk")
        if on_chunk:
            if self.chunk:
                for i in range(0, len(self.block), self.chunk):
                    on_chunk(self.block[i:i + self.chunk])
            else:
                on_chunk(self.block)          # 一次性喂（全部板在 finish 前闭合）
        return self.block

    def chat(self, messages, **kw):
        self.calls += 1
        return self.block


def _run(block: str, *, mode: str):
    """跑一条流水线 → (板列表, 异常或 None, LLM 调用次数)。

    `annotate=False`: 隔离标注调用（本文件只测板语义 / 交付语义）。
    """
    if mode == "batch":
        llm = _BatchLLM(block)
        engine = BondStoryEngine(ROOT / "config" / "characters", llm)
        engine.start_session(CHARACTER)
        try:
            first = engine.send_vn_scene("（开场）", annotate=False)
        except SceneLoopError as e:
            return [], e, llm.calls
        return [first] + list(engine._pending_boards), None, llm.calls

    llm = _StreamLLM(block)
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    got: list = []
    try:
        first = engine.send_vn_scene("（开场）", annotate=False, on_board=got.append)
    except SceneLoopError as e:
        assert got == [], "流式被拦时不该已经交付过板（闸只在首板前生效）"
        return [], e, llm.calls
    assert got and first is got[0], "流式: 返回值应即首个交付板"
    # 额外不变式: 交付列表 == 返回值 + 待发队列（同一条链, 不重复不丢）
    assert got == [first] + list(engine._pending_boards), \
        f"交付与待发队列不一致: {len(got)} vs {1 + len(engine._pending_boards)}"
    return list(got), None, llm.calls


def _digest(scene) -> dict:
    """板的可比较摘要（只取本文件关心的字段）。"""
    return {
        "texts": [p.get("text") for p in scene.paragraphs],
        "choices": list(scene.choices),
        "is_end": bool(scene.is_end),
        "memorial": bool(scene.memorial),
        "memorial_at": scene.memorial_at,
        "art": scene.art_hint,
        "recs": len(scene.records),
    }


def _shapes(boards) -> list[dict]:
    return [_digest(b) for b in boards]


def _haruka(text: str) -> str:
    return '{"character": "%s", "text": "%s"}' % (CHARACTER, text)


def _sensei(text: str) -> str:
    return '{"character": "sensei", "text": "%s"}' % text


def _switch(text: str) -> str:
    return '{"stage": "switch", "text": "%s"}' % text


def _lines(*rows: str) -> str:
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# 基准: 常规块两条路完全一致
# ---------------------------------------------------------------------------

def test_plain_block_is_identical():
    """常规块（无边界情形）: 两条路的板数/每板语义**逐字段相同**。"""
    block = _lines(
        _switch("教室"),
        _haruka("一"),
        _sensei("A"),
        _sensei("B"),
        _haruka("二"),          # ← 群结束, 首板闭合
        _sensei("C"),
        _haruka("三"),
        '{"stage": "end", "text": ""}',
    )
    batch, berr, bcalls = _run(block, mode="batch")
    stream, serr, scalls = _run(block, mode="stream")
    assert berr is None and serr is None, (berr, serr)
    assert _shapes(batch) == _shapes(stream), \
        f"常规块两条路必须一致:\n  批式={_shapes(batch)}\n  流式={_shapes(stream)}"
    assert bcalls == scalls == 1
    assert batch[-1].is_end, "末板应带 end"
    print(f"    parity: 常规块一致（{len(batch)} 板 / 各 1 次 LLM 调用）")


# ---------------------------------------------------------------------------
# 节点 2′ 消掉的分叉: 空板 / 板上限 / art 挂载
# ---------------------------------------------------------------------------

def test_pure_switch_board_merges_forward_both_paths():
    """相邻两条 `switch` → 第一条的记录**并入下一板**（不可见板向前合并）。

    改动前: 批式 `spare` 合并(1板) vs **流式交付一个空板**(2板) —— 玩家会多一次
    "点了没反应"的点击。改动后两侧同规则。
    """
    block = _lines(_switch("教室"), _switch("天台"), _haruka("一"))
    batch, _, _ = _run(block, mode="batch")
    stream, _, _ = _run(block, mode="stream")
    assert _shapes(batch) == _shapes(stream), (_shapes(batch), _shapes(stream))
    assert len(batch) == 1 and len(batch[0].records) == 3, _shapes(batch)
    assert [p["text"] for p in batch[0].paragraphs] == ["一"]
    print("    parity: 空板向前合并——两条路都 1 板（分叉消失）")


def test_trailing_switch_is_own_board_both_paths():
    """块尾只剩 `switch`（无处可并）→ **两条路都照原样成板**。

    改动前: 批式"向后并入末板"(1板) vs 流式单独成板(2板)。
    改动后: 统一为"向前合并 + 末板自成一板" → 两侧 2 板。
    ⚠️ 为什么不选"向后并入末板": 那需要"扣住一板不交付"的前瞻, 会吃掉 §9 的首屏优化。
    """
    block = _lines(_switch("教室"), _haruka("一"), _switch("天台"))
    batch, _, _ = _run(block, mode="batch")
    stream, _, _ = _run(block, mode="stream")
    assert _shapes(batch) == _shapes(stream), (_shapes(batch), _shapes(stream))
    assert len(batch) == 2 and batch[-1].paragraphs == [], _shapes(batch)
    assert len(batch[0].records) == 2, _shapes(batch)
    print("    parity: 块尾纯 switch——两条路都末板自成一板（2 板）")


def test_art_attaches_to_first_board_both_paths():
    """`art`（块级声明）→ 两条路都挂**首个板**。

    改动前: 批式挂"含 memorial 的板"、流式挂"首个交付板"。
    改动后: 统一为"首个板"。生图 prompt **不受影响**——`_fire_memorial_image` 用
    `art_hint or 任一板的 art_hint` 兜底取值。
    """
    block = _lines(
        '{"stage": "art", "text": "画面意向"}',
        _switch("破屋后院"),
        _haruka("一"),
        _sensei("A"),                      # ← 群结束, 首板闭合（不含 memorial）
        _haruka("二"),
        '{"stage": "memorial", "text": "（她抬起头。）"}',
    )
    batch, _, _ = _run(block, mode="batch")
    stream, _, _ = _run(block, mode="stream")
    assert _shapes(batch) == _shapes(stream), (_shapes(batch), _shapes(stream))
    assert [b.art_hint for b in batch] == ["画面意向", ""], _shapes(batch)
    # memorial 侧（板标记 + 记录级进入点）两侧一致
    assert batch[1].memorial and stream[1].memorial
    assert batch[1].memorial_at == stream[1].memorial_at == 1
    print("    parity: art 挂首个板——两条路一致（memorial 侧一致）")


def test_board_cap_applies_to_both_paths():
    """板上限 `MAX_BOARDS_PER_TURN` → 两条路都截断（改动前流式无上限）。"""
    rows = [_switch("起点")]
    for i in range(26):
        rows.append(_haruka(f"角色{i}"))
        rows.append(_sensei(f"选项{i}"))
    block = _lines(*rows)

    batch, _, _ = _run(block, mode="batch")
    stream, _, _ = _run(block, mode="stream")
    assert len(batch) == len(stream) == MAX_BOARDS_PER_TURN, (len(batch), len(stream))
    print(f"    parity: 板上限——两条路都截断到 {MAX_BOARDS_PER_TURN} 板")


# ---------------------------------------------------------------------------
# 板级闸（节点 2′ 的核心新增）
# ---------------------------------------------------------------------------

def test_hard_violation_gated_in_both_paths():
    """`end` 之后还有记录 → **两条路都拦**（板级闸）。

    改动前: 批式 `SceneLoopError`(3 次调用) vs **流式照常交付**(1 次调用)——
    等于"引擎判"的硬闸在生产路径上不执法（`bond_story.py` 原注释：
    *"流式下'硬违规'无法回滚（板已在玩家屏上）, 故只 trace/日志, 不打回重发"*）。
    改动后: 流式在**首板交付前**用 `check_board` 拦下 → 一块都没上屏 → 打回重发,
    3 次耗尽同样 `SceneLoopError`。
    """
    block = _lines(
        _switch("教室"),
        _haruka("一"),
        '{"stage": "end", "text": ""}',
        _haruka("二"),                     # ← end 之后还有记录 = 板级硬违规
    )
    batch, berr, bcalls = _run(block, mode="batch")
    stream, serr, scalls = _run(block, mode="stream")
    assert isinstance(berr, SceneLoopError) and batch == [] and bcalls == 3, \
        (berr, batch, bcalls)
    assert isinstance(serr, SceneLoopError) and stream == [] and scalls == 3, \
        (serr, stream, scalls)
    print("    parity: 板级闸——硬违规两条路都打回（3 次调用耗尽）")


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record) -> None:
        self.lines.append(record.getMessage())


def _capture_stream_run(block: str):
    """跑流式并抓 `core.bond.bond_story` 的日志（返回 (板, 异常, 调用次数, 日志)）。"""
    from core.bond import bond_story as bs

    logger = logging.getLogger(bs.__name__)
    cap = _Capture()
    logger.addHandler(cap)
    old_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        boards, err, calls = _run(block, mode="stream")
    finally:
        logger.removeHandler(cap)
        logger.setLevel(old_level)
    return boards, err, calls, "\n".join(cap.lines)


def test_late_violation_is_advisory_in_stream_only():
    """违规落在**后续板**（首板已交付）→ 流式 **advisory**: 照常交付 + 只记日志。

    这是**有意的模式差异**（`DeliveryMode`），不是分叉: 流式拦不住已上屏的板,
    而"打回重发"产出的是另一段文本 = 玩家看到"同一段戏讲两遍"
    （`docs/DESIGN_RESEND.md` §3）。批式（整块未交付）仍拦。
    """
    block = _lines(
        _switch("教室"),
        _haruka("一"),
        _sensei("A"),                      # ← 板 1 在这里闭合（正常）
        _haruka("二"),
        '{"stage": "end", "text": ""}',
        _haruka("三"),                     # ← 违规落在板 2
    )
    stream, serr, _, logs = _capture_stream_run(block)
    assert serr is None, "已交付之后的违规不该让流式炸（advisory）"
    assert len(stream) == 2, f"应照常交付 2 板: {[len(b.records) for b in stream]}"
    assert "板级违规（已交付 → 只记账, 不回滚）" in logs, logs
    batch, berr, bcalls = _run(block, mode="batch")
    assert isinstance(berr, SceneLoopError) and bcalls == 3, (berr, bcalls)
    print("    parity: 后续板违规——流式 advisory 照交付 vs 批式拦（有意模式差异）")


# ---------------------------------------------------------------------------
# 生产可观测（节点 1 补的；节点 2′ 后仍成立）
# ---------------------------------------------------------------------------

def test_stream_logs_block_issue_text_for_greppability():
    """流式也打**块级问题文本**: CLAUDE.md §12 教人 `grep "含 memorial 但没有 art"`
    来量 art 配对命中率——而生产走流式, 那行以前只打数量。

    这条是**块级 advisory**: `art` 配对单板判不了（memorial 可能在本块后段才出现）
    → 板级闸不管它 → 交付照旧 + 文本进日志。
    """
    block = _lines(
        _switch("教室"),
        _haruka("一"),
        '{"stage": "memorial", "text": "（她抬起头。）"}',   # 有 memorial 但无 art
    )
    stream, serr, _, logs = _capture_stream_run(block)
    assert serr is None and stream, "块级软问题不拦"
    assert "含 memorial 但没有 art" in logs, logs
    print("    parity: 流式日志含块级软问题文本（art 配对命中率可 grep）")
