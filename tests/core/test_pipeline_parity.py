# -*- coding: utf-8 -*-
"""批式 vs 流式流水线的**特征化测试**（节点 1, 2026-09-21）。

## 为什么有这个文件

`docs/EXEC_PIPELINE_UNIFY.md` 要统一两条流水线（节点 2′）。但**统一之前必须先知道
它们现在差在哪**——否则"统一"就是把某些行为悄悄改掉，而没有任何测试拦得住。

现有唯一的相关测试是 `tests/core/test_records.py::test_board_split_batch_stream_equivalence`
——它只钉了**切板边界**（`_board_spans` vs `BlockStreamParser`）。本文件钉的是
**板语义与守卫**：`spare` 合并、`MAX_BOARDS_PER_TURN`、`art` 挂载规则、
硬违规的处理方式、调用次数。

⚠️ **本文件是"特征化（characterization）测试"，不是"需求测试"**：它记录的是
**现状**，其中一部分差异是**已知缺陷**（见下方清单）。统一流水线时这些期望值
**会红**——那时的正确反应是"按新语义更新期望值 + 在提交信息里说明"，不是绕过。

## 两条流水线怎么区分（现状）

| | 批式 | 流式 |
|---|---|---|
| 触发条件 | 调用方**不传** `on_board`，或客户端没有 `chat_full` | 传了 `on_board` **且**客户端有 `chat_full` |
| 解析 | `BondStoryEngine._build_record_boards` | `BlockStreamParser` + `_scene_from_records` |
| 生产上谁走 | `_pregenerate` / `_candidate_worker` / CLI / **多数测试** | `_generate`（玩家点击、真机） |

## 已知差异清单（本文件逐条钉住）

| # | 差异 | 现状 |
|---|---|---|
| 1 | 纯 `switch` 空板 | 批式 `spare` 并入下一板；**流式单独交付一个空板** |
| 2 | `art` 挂载目标 | 批式挂"含 memorial 的板"；流式挂**首个交付板** |
| 3 | `MAX_BOARDS_PER_TURN` | 批式截断到 24；流式**不截断** |
| 4 | 硬违规 | 批式打回重发（3 次后 `SceneLoopError`，共 3 次 LLM 调用）；流式**照常交付**（1 次调用） |
| 5 | 结尾纯 `switch` | 批式并入末板；流式单独成板 |
| 6 | 软/硬问题**文本**进日志 | 此前流式只打 `issues=%d`（数量）→ 生产上 grep 不到软问题串（本节点已补） |

运行: python -m pytest tests/core/test_pipeline_parity.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import BondStoryEngine, SceneLoopError  # noqa: E402

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

    `annotate=False`: 隔离标注调用（本文件只测板语义）。
    批式硬违规会打回重发 → 3 次耗尽抛 `SceneLoopError`（被捕获后由用例断言）。
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
    first = engine.send_vn_scene("（开场）", annotate=False, on_board=got.append)
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
# 基准: 常规块两条路**完全一致**
# ---------------------------------------------------------------------------

def test_plain_block_is_identical():
    """常规块（无边界情形）: 两条路的板数/每板语义**逐字段相同**——这是"同语义"的基准。

    它也是节点 2′ 的验收底线: 统一之后这个用例必须仍然绿。
    """
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
# 差异 1 / 5: 纯 switch 空板（批式 spare 合并 vs 流式单独交付）
# ---------------------------------------------------------------------------

def test_pure_switch_board_spare_vs_delivered():
    """相邻两条 `switch` → 第一条单独成板（空板）:

    · 批式: `spare` 把空板记录**并入下一板** → 1 板 / 3 条记录
    · 流式: **交付一个空板**（`paragraphs` 为空）→ 2 板

    ⚠️ 差异 1。这是玩家可见的: 空板等于"多一次点击/一段空白"。
    """
    block = _lines(_switch("教室"), _switch("天台"), _haruka("一"))
    batch, _, _ = _run(block, mode="batch")
    stream, _, _ = _run(block, mode="stream")
    assert len(batch) == 1 and batch[0].records and len(batch[0].records) == 3, \
        _shapes(batch)
    assert len(stream) == 2, f"流式应交付空板: {_shapes(stream)}"
    assert stream[0].paragraphs == [] and len(stream[0].records) == 1, _shapes(stream)
    assert [s["texts"] for s in _shapes(stream)] == [[], ["一"]]
    print("    parity: 纯 switch 空板——批式 spare 合并(1板) vs 流式交付空板(2板)")


def test_trailing_switch_spare_vs_delivered():
    """结尾只剩 `switch`（差异 5）: 批式并入末板, 流式单独成板。"""
    block = _lines(_switch("教室"), _haruka("一"), _switch("天台"))
    batch, _, _ = _run(block, mode="batch")
    stream, _, _ = _run(block, mode="stream")
    assert len(batch) == 1 and len(batch[0].records) == 3, _shapes(batch)
    assert len(stream) == 2 and stream[-1].paragraphs == [], _shapes(stream)
    print("    parity: 结尾纯 switch——批式并入末板(1板) vs 流式单独成板(2板)")


# ---------------------------------------------------------------------------
# 差异 2: art 挂载目标不同
# ---------------------------------------------------------------------------

def test_art_lands_on_different_board():
    """`art`（块首声明）挂到哪一板:

    · 批式: 挂**含 memorial 的板**（`target = next(s for s in boards if s.memorial)`）
    · 流式: 挂**首个交付板**（`if stream.art_hint and not delivered`）

    ⇒ 同一块内容, 两条路落库/回放的 `art_hint` 位置不同（下游 `prompt_source`
    归因与 board payload 都能看出差异）。
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
    assert len(batch) == 2 and len(stream) == 2, (_shapes(batch), _shapes(stream))
    # 批式: art 在含 memorial 的第 2 板; 流式: art 在首板
    assert [b.art_hint for b in batch] == ["", "画面意向"], _shapes(batch)
    assert [s.art_hint for s in stream] == ["画面意向", ""], _shapes(stream)
    # memorial 侧两条路一致（板 + 记录级进入点）
    assert batch[1].memorial and stream[1].memorial
    assert batch[1].memorial_at == stream[1].memorial_at == 1
    print("    parity: art 挂载——批式挂纪念板 vs 流式挂首板（memorial 侧一致）")


# ---------------------------------------------------------------------------
# 差异 3: MAX_BOARDS_PER_TURN
# ---------------------------------------------------------------------------

def test_board_cap_batch_only():
    """板上限 24（差异 3）: 批式截断（多余丢弃 + WARNING）, 流式不截断。"""
    rows = [_switch("起点")]
    for i in range(26):
        rows.append(_haruka(f"角色{i}"))
        rows.append(_sensei(f"选项{i}"))
    block = _lines(*rows)

    batch, _, _ = _run(block, mode="batch")
    stream, _, _ = _run(block, mode="stream")
    assert len(batch) == 24, f"批式应截断到 24, 实得 {len(batch)}"
    assert len(stream) == 26, f"流式不截断, 实得 {len(stream)}"
    print("    parity: 板上限——批式截断到 24 vs 流式 26 板全交")


# ---------------------------------------------------------------------------
# 差异 4: 硬违规
# ---------------------------------------------------------------------------

def test_hard_violation_batch_rejects_stream_delivers():
    """硬违规（`end` 之后还有记录）:

    · 批式: `check_block` 硬 → `feedback` 打回重发 → 3 次耗尽抛 `SceneLoopError`
      （**3 次 LLM 调用**）
    · 流式: 交付照旧（**1 次调用**）——`bond_story.py` 的注释原文: *"流式下'硬违规'
      无法回滚（板已在玩家屏上）, 故只 trace/日志, 不打回重发"*

    ⚠️ 这就是 ARCH_REVIEW P0-2/P0-3 的现场: **生产路径（流式）上硬闸不执法**。
    节点 2′ 的板级闸正是为它写的。
    """
    block = _lines(
        _switch("教室"),
        _haruka("一"),
        '{"stage": "end", "text": ""}',
        _haruka("二"),                     # ← end 之后还有记录 = 硬违规
    )
    batch, berr, bcalls = _run(block, mode="batch")
    stream, serr, scalls = _run(block, mode="stream")
    assert isinstance(berr, SceneLoopError), \
        f"批式应打回重发至耗尽（SceneLoopError）, 实得 {berr!r}"
    assert batch == [] and bcalls == 3, (batch, bcalls)
    assert serr is None and len(stream) == 1 and scalls == 1, (serr, scalls)
    assert stream[0].is_end is True, "流式照常交付（且 is_end=True）"
    assert [p["text"] for p in stream[0].paragraphs] == ["一", "二"]
    print("    parity: 硬违规——批式打回重发×3 耗尽 vs 流式照常交付（1 次调用）")


# ---------------------------------------------------------------------------
# 差异 6: 软/硬问题**文本**在生产路径（流式）可观测
# ---------------------------------------------------------------------------

class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record) -> None:
        self.lines.append(record.getMessage())


def test_stream_logs_issue_text_for_greppability():
    """节点 1 的可观测补丁: 流式路径也打**问题文本**（此前只有 `issues=%d` 数量）。

    为什么重要: CLAUDE.md §12 教人 `grep "含 memorial 但没有 art"` 来量 art 配对
    命中率——而**生产走的是流式**, 以前那行根本不打 ⇒ 该指标在生产上不可观测。
    """
    from core.bond import bond_story as bs

    block = _lines(
        _switch("教室"),
        _haruka("一"),
        '{"stage": "memorial", "text": "（她抬起头。）"}',   # 有 memorial 但无 art
    )
    logger = logging.getLogger(bs.__name__)
    cap = _Capture()
    logger.addHandler(cap)
    old_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        stream, serr, _ = _run(block, mode="stream")
    finally:
        logger.removeHandler(cap)
        logger.setLevel(old_level)
    assert serr is None and stream, "流式应交付（软问题不拦）"
    joined = "\n".join(cap.lines)
    assert "含 memorial 但没有 art" in joined, \
        f"流式日志应含软问题文本（可 grep）:\n{joined}"
    print("    parity: 流式日志含软问题文本（art 配对命中率在生产可 grep）")
