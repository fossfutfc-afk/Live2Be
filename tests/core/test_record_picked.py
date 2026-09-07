# -*- coding: utf-8 -*-
"""方案A-A1 选项回录（DESIGN_PROMPTKIT §5, Phase 4）单测。

核心: record_picked 重渲引擎历史尾部（含 `（选择了: X）`）——与事件流
render_events 同一渲染函数同一参数形态 → live 与 resume/wrapup 预灌逐字节同形。
branches 内容仍不进上下文（A1 语义——未选分支/选中分支文本都只存在于事件,
A2 留档）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import BondStoryEngine
from core.session.renderer import render_bond_scene_text

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"

SCENE = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "（测试）她站在窗边，听到声音回过头来。"},
                   {"text": "那个……有些话，我一直想找机会跟你说。"}],
    "choices": ["走过去，在她身边坐下", "笑着说：说吧，我在听"],
    "branches": {
        "走过去，在她身边坐下": [{"text": "（测试分支）她张了张嘴，小声说：那我说了哦。"}],
        "笑着说：说吧，我在听": [{"text": "（测试分支）她松了口气，声音轻快了些。"}],
    },
}}
PICKED = "走过去，在她身边坐下"


class ScriptedLLM:
    def __init__(self, *scripts):
        self._scripts = list(scripts)
        self.snapshots = []

    def chat_full(self, messages, **kw):
        self.snapshots.append([dict(m) for m in messages])
        return self._scripts.pop(0)

    def chat(self, messages, **kw):
        self.snapshots.append([dict(m) for m in messages])
        return self._scripts.pop(0)


def _engine(llm) -> BondStoryEngine:
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    return engine


def test_record_picked_rewrites_tail_with_choice():
    """裁决回录: 尾部重渲含 （选择了: X）; 内容 = 同一渲染函数对 payload+picked。"""
    llm = ScriptedLLM(SCENE)
    engine = _engine(llm)
    engine.send_vn_scene("（旁白）本章：测试。", annotate=False)

    before = engine.history[-1]["content"]
    assert "（选择了:" not in before                      # 生成时无 picked

    engine.record_picked(PICKED)
    after = engine.history[-1]["content"]
    assert "（选择了: 走过去，在她身边坐下）" in after

    payload = dict(SCENE["payload"])
    payload["picked"] = PICKED
    assert after == render_bond_scene_text(payload)       # live == 事件渲染函数


def test_record_picked_excludes_branch_text():
    """A1: 选中分支内容不进上下文——只有选择行（A2 才叙事化分支, 见设计 §5.4）。"""
    llm = ScriptedLLM(SCENE)
    engine = _engine(llm)
    engine.send_vn_scene("（旁白）测试。", annotate=False)
    engine.record_picked(PICKED)
    after = engine.history[-1]["content"]
    assert "（测试分支）她张了张嘴" not in after          # 分支正文不注入
    assert "（测试分支）她松了口气" not in after
    assert "（选择了:" in after


def test_record_picked_continuity_two_scenes():
    """连续两场: 第一场裁决行保留; 第二场只动自己的尾部。"""
    llm = ScriptedLLM(SCENE, SCENE)
    engine = _engine(llm)
    engine.send_vn_scene("（旁白）第一场。", annotate=False)
    engine.record_picked(PICKED)
    first_tail = engine.history[-1]["content"]

    engine.send_vn_scene("（继续）", annotate=False)      # 第二场（LLM 已见裁决行）
    assert len(engine.history) == 4                       # user/assistant × 2
    assert engine.history[1]["content"] == first_tail     # 第一场行不变
    assert "（选择了:" not in engine.history[-1]["content"]  # 第二场无裁决 → 干净
    engine.record_picked("笑着说：说吧，我在听")           # 只重渲尾部第二场
    assert "（选择了: 笑着说：说吧，我在听）" in engine.history[-1]["content"]
    assert engine.history[1]["content"] == first_tail     # 第一场仍不变


def test_record_picked_noops():
    """未消费/无场景/空白/继续 → 安全 no-op（历史不破坏）。"""
    llm = ScriptedLLM(SCENE)
    engine = _engine(llm)

    engine.record_picked(PICKED)                          # 未 send → 无动作
    assert engine.history == []

    engine.send_vn_scene("（旁白）测试。", annotate=False)
    before = engine.history[-1]["content"]
    engine.record_picked("")                              # 空白
    engine.record_picked(None)                            # 非 str
    assert engine.history[-1]["content"] == before

    engine.record_picked("（继续）")                        # 渲染器跳过继续 → 行不变
    assert engine.history[-1]["content"] == before
