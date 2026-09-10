# 留档: v1 时代 test_record_picked.py 的旧契约段（dict 场景 + （选择了: X））
# 退役于记录流 v2（P0-7c）——裁决改为物化 `老师：X`。
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


# ---------------------------------------------------------------------------
# 记录流 v2（P0-5）: 裁决 = **物化**（不是注解）——`老师：X` 取代"（选择了: X）"
# ---------------------------------------------------------------------------

RECORD_BLOCK = "\n".join([
    '{"stage": "switch", "text": "深夜的杂草屋"}',
    '{"character": "igusa_haruka", "text": "……老师，你来了。"}',
    '{"character": "sensei", "text": "我来了。"}',
    '{"character": "sensei", "text": "路上买了点东西。"}',
    '{"character": "igusa_haruka", "text": "「不、不用这样的……」"}',
])
RECORD_PICKED = "路上买了点东西。"
RECORD_OTHER = "我来了。"


def _record_engine():
    llm = ScriptedLLM(RECORD_BLOCK)
    engine = _engine(llm)
    engine.send_vn_scene("（旁白）本章：测试。", annotate=False)
    return engine


def test_record_pick_is_materialized_into_history():
    """裁决 → 群里物化一条 `老师：X`; 未选候选与旧注解都不出现。"""
    engine = _record_engine()
    before = engine.history[-1]["content"]
    assert "老师：" not in before                          # 生成时槽未定 → 老师的话不出现
    assert RECORD_OTHER not in before and RECORD_PICKED not in before

    engine.record_picked(RECORD_PICKED)
    after = engine.history[-1]["content"]
    assert f"老师：{RECORD_PICKED}" in after
    assert RECORD_OTHER not in after                       # 未选台词永不进上下文
    assert "（选择了:" not in after                         # 旧注解退役
    # 位置: 物化行落在群首 —— 角色反应在**下一板**（§6 槽挂板尾, 不在本板渲染里）
    lines = after.split("\n")
    assert lines.index("igusa_haruka：……老师，你来了。") < lines.index(f"老师：{RECORD_PICKED}")
    # 真源不受影响: payload 仍保留整群候选（未选只在渲染层消失）
    assert engine._last_payload["choices"] == [RECORD_OTHER, RECORD_PICKED]
    nxt = engine.send_vn_scene("（继续）", annotate=False)  # 待发板（0 LLM）= 反应
    assert [p["text"] for p in nxt.paragraphs] == ["「不、不用这样的……」"]
    assert RECORD_OTHER not in "\n".join(p["text"] for p in nxt.paragraphs)
    print("    picked: 裁决物化为 `老师：X`（未选候选不进上下文）")


def test_live_and_replay_byte_identical_on_records():
    """A1 不变式（记录流版）: live 尾部 == 事件流渲染（同一函数同一 payload+picked）。"""
    from core.session.events import make_event
    from core.session.renderer import render_events

    engine = _record_engine()
    engine.record_picked(RECORD_PICKED)
    live_tail = engine.history[-1]["content"]

    payload = dict(engine._last_payload)
    payload["input"] = "（旁白）本章：测试。"
    payload["picked"] = RECORD_PICKED
    event = make_event("bond", "story_scene", payload, seq=1)
    replayed = render_events([event])
    assert replayed[-1]["content"] == live_tail             # 逐字节同形
    assert "（选择了:" not in live_tail
    print("    picked: live == 回放（逐字节）")


def test_from_dict_materializes_pick_for_display():
    """显示层也物化: BondScene.from_dict(payload+picked) 把裁决行插回群首。"""
    from core.bond.bond_story import BondScene

    engine = _record_engine()
    payload = dict(engine._last_payload)
    payload["picked"] = RECORD_PICKED
    scene = BondScene.from_dict(payload)

    texts = [p["text"] for p in scene.paragraphs]
    assert RECORD_PICKED in texts and texts.index(RECORD_PICKED) == 1   # 群首位置
    assert all(p.get("speaker") for p in scene.paragraphs)  # 最小说话人形态齐备
    assert scene.paragraphs[1]["speaker"] == "sensei"
    assert RECORD_OTHER not in texts
    # 未给 picked → 显示层不含老师那句（生成时形态）
    plain = BondScene.from_dict(engine._last_payload)
    assert RECORD_PICKED not in [p["text"] for p in plain.paragraphs]
    print("    picked: 显示层物化（speaker=sensei 插回群首）")
