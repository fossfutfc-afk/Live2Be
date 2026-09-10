# -*- coding: utf-8 -*-
"""VN 记录流引擎接线单测（P0-4b）—— 块解析 → 板派生 → 群/槽 → 待发板 → 历史隔离。

覆盖设计文档 §6（板 = 引擎派生单位: 换场/槽前必切）、§2（文法）、决策 #21（别名归一）:
    记录流一场      : 字符串输出 → 板（switch/群/art 不进显示, end 行进 is_end）
    待发板          : 一块多群 → 首板本次发, 尾板 **0 LLM** 领出
    别名归一 + 辅助转义: 显示名/未知说话人 → 主角 id; 未转义引号救回
    硬违规/空块      : feedback 回灌重试; 耗尽抛 SceneLoopError
    历史隔离        : switch 文本与未选候选**不进 LLM 上下文**（A1 语义）

不碰 API: ScriptedLLM（场景轮返回记录流字符串; annotate=False 免标注调用）。
运行: python -m pytest tests/core/test_vn_records_engine.py
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import BondStoryEngine, SceneLoopError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"

#: 一块两群（run=2 + run=1）+ 换场 + art 预告 + 收尾
TWO_GROUP_BLOCK = "\n".join([
    '{"stage": "switch", "text": "深夜的杂草屋"}',
    '{"character": "igusa_haruka", "text": "……老师。"}',
    '{"character": "narrator", "text": "（她把灯往我这边挪了挪。）"}',
    '{"character": "sensei", "text": "我来了。"}',
    '{"character": "sensei", "text": "路上买了点东西。"}',
    '{"character": "igusa_haruka", "text": "「不、不用这样的……」"}',
    '{"character": "sensei", "text": "先坐下。"}',
    '{"character": "igusa_haruka", "text": "「……好。」"}',
    '{"stage": "end", "text": "（夜风停了。）"}',
])


class ScriptedLLM:
    """场景轮按脚本返回**记录流字符串**；标注调用（emotion/place/换场翻译）按关键字
    自动应答, 不消耗脚本。每个脚本用完即提示（防静默多发调用）。"""

    def __init__(self, *scripts, place_reply: str = ""):
        self._scripts = list(scripts)
        self.snapshots = []
        self.place_reply = place_reply

    def chat_full(self, messages, **kw):
        return self.chat(messages, **kw)

    def chat(self, messages, **kw):
        self.snapshots.append([dict(m) for m in messages])
        last = messages[-1]["content"] if messages else ""
        head = messages[0]["content"] if messages else ""
        if "情绪标签数组" in last:                       # emotion 标注 → 全 nomal
            import re as _re
            n = len(_re.findall(r"(?m)^\d+: ", head))
            return ["nomal"] * max(n, 1)
        if "地点 id JSON" in last:                       # switch → 背景键（P0-7）
            return {"place": self.place_reply}
        if "变更句数组" in last:                          # 旧 place 标注 → 无变更
            return []
        if not self._scripts:
            raise AssertionError("ScriptedLLM 脚本耗尽——引擎多发了一次 LLM 调用")
        return self._scripts.pop(0)


def _engine(llm) -> BondStoryEngine:
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    return engine


# ---------------------------------------------------------------------------
# 板派生（换场/槽前必切）
# ---------------------------------------------------------------------------

def test_record_turn_splits_boards_at_switch_and_slots():
    """一块多群 + 换场 → 切成多板: 首板 = switch 后的正文 + 第一群（choices）。"""
    llm = ScriptedLLM(TWO_GROUP_BLOCK)
    engine = _engine(llm)
    scene = engine.send_vn_scene("（开场）", annotate=False)

    # 首板: 群（run=2）成为 choices; 正文不含 switch/群内候选
    assert scene.choices == ["我来了。", "路上买了点东西。"]
    assert [p["text"] for p in scene.paragraphs] == [
        "……老师。", "（她把灯往我这边挪了挪。）"]
    assert scene.place_hint == "深夜的杂草屋"
    assert not scene.is_end
    # 记录流真源: 本板记录里 switch 仍在（落库/回放不丢信号）
    assert scene.records[0] == {"stage": "switch", "text": "深夜的杂草屋"}
    assert len(engine.history) == 2                       # user + assistant
    print("    engine: 换场/槽前必切板 + 群 → choices")


def test_pending_board_costs_zero_llm():
    """尾板已在手 → 后续调用 **0 LLM** 直接发（槽在板尾、反应在下一板）。"""
    llm = ScriptedLLM(TWO_GROUP_BLOCK)
    engine = _engine(llm)
    first = engine.send_vn_scene("（开场）", annotate=False)
    second = engine.send_vn_scene("（继续）", annotate=False)
    third = engine.send_vn_scene("（继续）", annotate=False)

    assert len(llm.snapshots) == 1                        # 后两次都没碰 LLM
    assert first.choices == ["我来了。", "路上买了点东西。"]
    assert second.choices == ["先坐下。"]                  # 第二个群（run=1 也弹）
    assert [p["text"] for p in second.paragraphs] == ["「不、不用这样的……」"]
    assert third.choices == [] and third.is_end is True    # 末板: 收尾（end 行进 is_end）
    assert [p["text"] for p in third.paragraphs] == ["「……好。」", "（夜风停了。）"]
    assert engine._trace[0]["action"] == "record_stream/pending"
    # 历史: 三板各 user+assistant
    assert len(engine.history) == 6
    print("    engine: 待发板 0 LLM（读屏期间预生成下一板的最朴素形态）")


def test_history_excludes_slot_candidates_keeps_switch_text():
    """历史隔离: **槽内候选不进 LLM 上下文**（A1 语义）; switch 回显 writer 自己的地点话。"""
    llm = ScriptedLLM(TWO_GROUP_BLOCK)
    engine = _engine(llm)
    for _ in range(3):
        engine.send_vn_scene("（继续）", annotate=False)
    joined = "\n".join(m["content"] for m in engine.history)
    assert "我来了。" not in joined and "先坐下。" not in joined   # 未选候选不出现
    assert "老师：" not in joined                            # 槽候选不当台词灌历史
    assert "深夜的杂草屋" in joined                           # §4: switch 回显自己写的地点话
    assert "「……好。」" in joined                             # 正文照常入历史
    print("    engine: 历史不含槽候选（switch 按 §4 回显）")


# ---------------------------------------------------------------------------
# 别名归一 + 辅助转义（决策 #21 / P0-2 修复）
# ---------------------------------------------------------------------------

def test_alias_normalization_and_rescape_in_engine():
    """显示名/未知说话人 → 主角 id（NOTE）; 未转义引号在引擎路径上被救回。"""
    block = "\n".join([
        '{"stage": "switch", "text": "教室"}',
        '{"character": "伊草 遥香", "text": "「老师……」"}',
        '{"character": "遥香", "text": "我想要的不是 "别担心" 这种话。"}',
    ])
    llm = ScriptedLLM(block)
    engine = _engine(llm)
    scene = engine.send_vn_scene("（开场）", annotate=False)

    assert [r["character"] for r in scene.records if "character" in r] == [CHARACTER] * 2
    assert scene.paragraphs[1]["text"] == '我想要的不是 "别担心" 这种话。'
    assert any("别名归一" in n for n in scene.notes)
    assert any("辅助转义" in n for n in scene.notes)
    print("    engine: 别名归一 + 辅助转义（真机路径生效）")


# ---------------------------------------------------------------------------
# 硬违规 / 空块 → feedback 重试
# ---------------------------------------------------------------------------

def test_hard_violation_retries_with_feedback():
    """art 不在本轮首条（形状硬违规）→ 打回重发, 第二次守约则收下。"""
    bad = "\n".join([
        '{"stage": "switch", "text": "教室"}',
        '{"character": "igusa_haruka", "text": "……"}',
        '{"stage": "art", "text": "画面意向"}',
    ])
    llm = ScriptedLLM(bad, TWO_GROUP_BLOCK)
    engine = _engine(llm)
    scene = engine.send_vn_scene("（开场）", annotate=False)

    assert len(llm.snapshots) == 2
    retry_messages = "\n".join(m["content"] for m in llm.snapshots[1])
    assert "记录流不合规" in retry_messages and "art" in retry_messages
    assert scene.choices == ["我来了。", "路上买了点东西。"]
    assert engine.trace[0]["parse_valid"] is False and engine.trace[1]["parse_valid"] is True
    print("    engine: 硬违规 → feedback 回灌重试")


def test_empty_block_exhausts_retries():
    """一直给不出合法记录 → 重试耗尽抛 SceneLoopError（宁缺勿错: 循环必须终结）。"""
    llm = ScriptedLLM("这不是记录流", "还是不是", "仍然不是")
    engine = _engine(llm)
    with pytest.raises(SceneLoopError):
        engine.send_vn_scene("（开场）", annotate=False)
    assert len(llm.snapshots) == 3
    print("    engine: 空块重试耗尽 → SceneLoopError")


def test_art_declaration_is_not_its_own_board():
    """`art` 是块级声明（真机实证: 模型把它放在首条）——不许切出一个纯声明的空板。"""
    block = "\n".join([
        '{"stage": "art", "text": "她在破屋后院里抱着半株杂草抬起头"}',
        '{"stage": "switch", "text": "黄昏的破屋后院"}',
        '{"character": "igusa_haruka", "text": "老师，就是这里。"}',
        '{"stage": "memorial", "text": "（她第一次直视我的眼睛。）"}',
        '{"character": "igusa_haruka", "text": "这些话我想说很久了。"}',
    ])
    llm = ScriptedLLM(block)
    engine = _engine(llm)
    scene = engine.send_vn_scene("（开场）", annotate=False)

    assert scene.paragraphs and scene.place_hint == "黄昏的破屋后院"
    assert scene.memorial is True
    assert scene.art_hint == "她在破屋后院里抱着半株杂草抬起头"     # 声明挂到纪念板
    print("    engine: art 声明不切空板（挂纪念板 art_hint）")


def test_invisible_board_merges_forward_without_losing_records():
    """连发两条 switch（无可显示内容）→ 不产生空板: 地点顺延, 记录并入下一板真源。"""
    block = "\n".join([
        '{"stage": "switch", "text": "走廊"}',
        '{"stage": "switch", "text": "天台"}',
        '{"character": "igusa_haruka", "text": "……风很大。"}',
    ])
    llm = ScriptedLLM(block)
    engine = _engine(llm)
    scene = engine.send_vn_scene("（开场）", annotate=False)

    assert [p["text"] for p in scene.paragraphs] == ["……风很大。"]
    assert scene.place_hint == "走廊"                       # 空板地点顺延（首条 switch）
    assert [r.get("text") for r in scene.records][:4] == ["走廊", "天台", "……风很大。"]
    assert engine._pending_boards == []                     # 只有一板
    print("    engine: 空板记录并入下一板（真源不丢）")


def test_empty_end_board_is_kept_for_blackout_finish():
    """收尾组合③（老师一句 → 空镜 → end 留空）: 空段落板因 is_end 保留, 直接黑屏结束。"""
    block = "\n".join([
        '{"character": "igusa_haruka", "text": "……"}',
        '{"character": "sensei", "text": "你看那边，多漂亮啊"}',
        '{"stage": "switch", "text": "星空"}',
        '{"stage": "end", "text": ""}',
    ])
    llm = ScriptedLLM(block)
    engine = _engine(llm)
    first = engine.send_vn_scene("（开场）", annotate=False)
    assert first.choices == ["你看那边，多漂亮啊"]         # 老师一句 = run=1 的群
    assert first.is_end is False
    second = engine.send_vn_scene("（继续）", annotate=False)   # 0 LLM
    assert second.is_end is True and second.paragraphs == []    # 纯黑屏收尾板
    assert second.place_hint == "星空"
    assert len(llm.snapshots) == 1
    print("    engine: end 留空 = 黑屏收尾板（空段落也保留）")


# ---------------------------------------------------------------------------
# 换场翻译（P0-7）: switch 记录 → 背景键
# ---------------------------------------------------------------------------

def test_legacy_action_input_is_rejected_by_default():
    """P0-7b: **默认只吃记录流**——旧动作 JSON 被打回重发; 开关打开才放行（存量桩）。"""
    legacy = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "（旧契约）段落。"}]}}
    llm = ScriptedLLM(legacy, legacy, legacy)
    engine = BondStoryEngine(ROOT / "config" / "characters", llm,
                             allow_legacy_action=False)
    engine.start_session(CHARACTER)
    with pytest.raises(SceneLoopError):
        engine.send_vn_scene("（开场）", annotate=False)
    assert engine.trace[0]["action"] == "legacy_action_rejected"
    assert any("输出形态无效" in m["content"] for m in llm.snapshots[-1])

    # 开关打开（存量测试桩通道）→ 旧路径仍可用, 且用 json_object 形态
    llm2 = ScriptedLLM(legacy)
    engine2 = BondStoryEngine(ROOT / "config" / "characters", llm2,
                              allow_legacy_action=True)
    engine2.start_session(CHARACTER)
    scene = engine2.send_vn_scene("（开场）", annotate=False)
    assert [p["text"] for p in scene.paragraphs] == ["（旧契约）段落。"]
    print("    engine: 旧动作默认被拒 / 开关放行（P0-7b）")


def test_switch_record_resolves_to_background_key():
    """`switch` 记录走换场翻译（place 档位）→ scene.place = 词表键; 失败 keep。"""
    from core.bond.place_annotate import _RESOLVE_CACHE
    _RESOLVE_CACHE.clear()                         # 进程内缓存跨用例, 先清
    llm = ScriptedLLM(TWO_GROUP_BLOCK, place_reply="school_rooftop")
    engine = _engine(llm)
    engine._lexicon_keys = []                      # 关掉 emotion 标注, 只测换场
    scene = engine.send_vn_scene("（开场）", annotate=True)
    assert scene.place == "school_rooftop"         # 背景键就位（导演/前端据此切图）
    assert engine._current_place == "school_rooftop"   # 延续态顺延

    # 翻译失败（词表外/空）→ keep: place 为空, 画面保持（换一句地点话, 避开缓存）
    block = TWO_GROUP_BLOCK.replace("深夜的杂草屋", "某个不知名的地方")
    llm2 = ScriptedLLM(block, place_reply="")
    engine2 = _engine(llm2)
    engine2._lexicon_keys = []
    scene2 = engine2.send_vn_scene("（开场）", annotate=True)
    assert scene2.place is None and engine2._current_place == ""
    print("    engine: switch → 背景键（失败 keep）")


def test_soft_violation_overlong_slot_is_chunked():
    """超长 sensei 群（软违规）→ 切成 ≤3 的槽而不是整块重发（内容零损失）。"""
    block = "\n".join([
        '{"stage": "switch", "text": "教室"}',
        '{"character": "igusa_haruka", "text": "「那个……」"}',
        '{"character": "sensei", "text": "一"}',
        '{"character": "sensei", "text": "二"}',
        '{"character": "sensei", "text": "三"}',
        '{"character": "sensei", "text": "四"}',
        '{"character": "sensei", "text": "五"}',
    ])
    llm = ScriptedLLM(block)
    engine = _engine(llm)
    first = engine.send_vn_scene("（开场）", annotate=False)
    assert first.choices == ["一", "二", "三"]              # 首槽截到上限 3
    assert len(llm.snapshots) == 1                          # 没有整块重发
    second = engine.send_vn_scene("（继续）", annotate=False)
    assert second.choices == ["四", "五"]                    # 尾槽接着发
    assert len(llm.snapshots) == 1
    print("    engine: 超长群切槽（软违规不重发）")
