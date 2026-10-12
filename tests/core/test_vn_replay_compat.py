"""VN 记录流 P0-6 —— 落库 / 回放 / 存档：新档逐字节可复原、**旧档冻结不炸**。

覆盖:
    新档落库      : 板 payload 带 records → SessionStore 往返后逐字节一致
    新档回放      : render_events == live 尾部（含裁决物化 `老师：X`）
    恢复同形      : window_messages 灌出的历史 == live 历史（构造性）
    旧档冻结      : 旧契约 payload（paragraphs/choices/branches）仍走旧渲染
                    （「title」/（选项: …）/（选择了: …）/（本章结束））——不转换不改写
    混合存档      : 新旧事件同流 → 各自语法渲染, 互不干扰, 不炸
    坏 payload    : BondScene.from_dict 宁缺勿错（降级空场景, 不 raise）;
                    VnBlock.from_dict 对旧契约显式拒绝（防误当记录流）

运行: python -m pytest tests/core/test_vn_replay_compat.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from contract.records import VnBlock                                   # noqa: E402
from core.bond.bond_story import BondScene, BondStoryEngine            # noqa: E402
from core.session import SessionStore                                  # noqa: E402
from core.session.renderer import (render_bond_scene_text,             # noqa: E402
                                  render_events, window_messages)

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"

#: 记录流板（v2）: switch + 正文 + 群（run=2）
V2_PAYLOAD = {
    "records": [
        {"stage": "switch", "text": "深夜的杂草屋"},
        {"character": "igusa_haruka", "text": "……老师，你来了。"},
        {"character": "sensei", "text": "我来了。"},
        {"character": "sensei", "text": "路上买了点东西。"},
    ],
    "paragraphs": [{"text": "……老师，你来了。", "speaker": "igusa_haruka"}],
    "choices": ["我来了。", "路上买了点东西。"],
    "is_end": False,
    "place_hint": "深夜的杂草屋",
}
V2_PICKED = "路上买了点东西。"

#: 旧契约板（v1, 已冻结）: 段落 + 选项 + 分支
V1_PAYLOAD = {
    "paragraphs": [{"text": "（测试）她站在窗边。", "emotion": "nomal"},
                   {"text": "那个……我一直想找机会跟你说。", "emotion": "embarrass"}],
    "choices": ["走过去", "笑着说：说吧"],
    "branches": {"走过去": [{"text": "（测试分支）她张了张嘴。"}],
                 "笑着说：说吧": [{"text": "（测试分支）她松了口气。"}]},
    "title": "预先应对",
    "is_end": True,
}
V1_PICKED = "走过去"


class ScriptedLLM:
    def __init__(self, *scripts):
        self._scripts = list(scripts)

    def chat_full(self, messages, **kw):
        return self._scripts.pop(0)

    def chat(self, messages, **kw):
        return self._scripts.pop(0)


# ---------------------------------------------------------------------------
# 新档: 落库 / 回放 / 恢复
# ---------------------------------------------------------------------------

def test_v2_payload_roundtrips_through_store(tmp_path):
    """板 payload（records）经事件流往返 → 逐字节一致, 渲染不变。"""
    st = SessionStore(tmp_path / "worlds", world_id="world1")
    meta = st.create(CHARACTER, "伊草 遥香")
    payload = dict(V2_PAYLOAD, input="（旁白）本章：测试。", picked=V2_PICKED)
    st.append_event(CHARACTER, meta.session_id, type="bond",
                    subtype="story_scene", payload=payload)

    events = st.events(CHARACTER, meta.session_id)
    bond = [e for e in events if e.type == "bond"][0]
    assert bond.payload["records"] == V2_PAYLOAD["records"]      # 真源原样
    assert bond.payload["choices"] == V2_PAYLOAD["choices"]
    assert render_bond_scene_text(bond.payload) == render_bond_scene_text(payload)
    # 裁决物化: 老师那句出现, 未选候选不出现
    text = render_bond_scene_text(bond.payload)
    assert f"老师：{V2_PICKED}" in text and "老师：我来了。" not in text
    print("    store: v2 payload 往返逐字节 + 渲染稳定")


def test_v2_replay_matches_live_history():
    """回放 == live: 引擎跑一板 → 用同一 payload 造事件 → render_events 与历史尾部同形。"""
    llm = ScriptedLLM("\n".join([
        '{"stage": "switch", "text": "深夜的杂草屋"}',
        '{"character": "igusa_haruka", "text": "……老师，你来了。"}',
        '{"character": "sensei", "text": "我来了。"}',
        '{"character": "sensei", "text": "路上买了点东西。"}',
    ]))
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    engine.send_vn_scene("（旁白）本章：测试。", annotate=False)
    engine.record_picked(V2_PICKED)
    live_tail = engine.history[-1]["content"]

    from core.session.events import make_event
    payload = dict(engine._last_payload, input="（旁白）本章：测试。", picked=V2_PICKED)
    replayed = render_events([make_event("bond", "story_scene", payload, seq=1)])
    assert replayed[-1]["content"] == live_tail                   # 逐字节
    assert replayed[0] == {"role": "user", "content": "（旁白）本章：测试。"}
    print("    replay: 事件流渲染 == live 历史（逐字节）")


def test_resume_window_seeds_same_history():
    """恢复同形: window_messages 灌出的历史尾部 == live 尾部（同一渲染源）。"""
    llm = ScriptedLLM("\n".join([
        '{"stage": "switch", "text": "教室"}',
        '{"character": "igusa_haruka", "text": "……那个。"}',
        '{"character": "sensei", "text": "我在听。"}',
    ]))
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    engine.send_vn_scene("（旁白）本章：测试。", annotate=False)
    engine.record_picked("我在听。")
    live = engine.history

    from core.session.events import make_event
    payload = dict(engine._last_payload, input="（旁白）本章：测试。", picked="我在听。")
    win = window_messages([make_event("bond", "story_scene", payload, seq=1)])
    assert [m["content"] for m in win] == [m["content"] for m in live]
    print("    resume: 窗口灌入 == live 历史（逐字节）")


# ---------------------------------------------------------------------------
# 旧档冻结
# ---------------------------------------------------------------------------

def test_v1_payload_stays_frozen():
    """旧契约 payload 走旧渲染（不转换、不改写）: 修复旧档不是本次目标。"""
    text = render_bond_scene_text(dict(V1_PAYLOAD, picked=V1_PICKED))
    assert text.split("\n")[0] == "「预先应对」"                    # title 行（旧形态）
    assert "（测试）她站在窗边。（nomal）" in text                  # emotion 随行
    assert "（选项: 走过去 / 笑着说：说吧）" in text
    assert f"（选择了: {V1_PICKED}）" in text                       # 旧注解语义
    assert "（本章结束）" in text
    assert "（测试分支）" not in text                               # branches 不进上下文
    scene = BondScene.from_dict(V1_PAYLOAD)
    assert scene.choices == ["走过去", "笑着说：说吧"]
    assert scene.branches and scene.is_end is True
    assert scene.records == []                                     # 旧档没有记录真源
    print("    legacy: 旧契约 payload 冻结（旧渲染 + 旧结构）")


def test_v1_payload_rejected_by_record_carrier():
    """旧契约 payload 不许被当成记录流（显式拒绝, 不静默降级为空块）。"""
    try:
        VnBlock.from_dict(V1_PAYLOAD)
    except ValueError as e:
        assert "records" in str(e)
    else:                                                          # pragma: no cover
        raise AssertionError("旧契约 payload 应被 VnBlock 拒绝")
    print("    legacy: VnBlock 显式拒绝旧契约 payload")


# ---------------------------------------------------------------------------
# 混合存档 + 坏数据
# ---------------------------------------------------------------------------

def test_mixed_archive_renders_both_grammars(tmp_path):
    """新旧事件同流: 各自语法渲染, 不互相污染, 窗口预算照算。"""
    st = SessionStore(tmp_path / "worlds", world_id="world1")
    meta = st.create(CHARACTER, "伊草 遥香")
    st.append_event(CHARACTER, meta.session_id, type="bond", subtype="story_scene",
                    payload=dict(V1_PAYLOAD, input="（旁白）旧章。", picked=V1_PICKED))
    st.append_event(CHARACTER, meta.session_id, type="bond", subtype="story_scene",
                    payload=dict(V2_PAYLOAD, input="（继续）", picked=V2_PICKED))

    msgs = render_events(st.events(CHARACTER, meta.session_id))
    joined = "\n".join(m["content"] for m in msgs)
    assert "（选择了: 走过去）" in joined          # 旧档行
    assert f"老师：{V2_PICKED}" in joined          # 新档行
    assert [m["role"] for m in msgs] == ["user", "assistant"] * 2
    win = window_messages(st.events(CHARACTER, meta.session_id), max_units=1000)
    assert len(win) == len(msgs)
    print("    mixed: 新旧语法共存（旧档冻结 + 新档记录）")


def test_bad_payload_degrades_without_raising():
    """坏 payload: 显示层宁缺勿错（降级空场景）; 旧渲染/新渲染都不抛。"""
    for bad in (None, {}, {"records": "not-a-list"}, {"records": [1, 2]},
                {"paragraphs": "裸字符串"}, {"choices": "不是列表"}):
        scene = BondScene.from_dict(bad)
        assert isinstance(scene, BondScene)
        render_bond_scene_text(bad if isinstance(bad, dict) else {})
    print("    bad: 坏 payload 降级不抛（宁缺勿错）")


def test_timeline_includes_picked_line():
    """digest 消化时间线: 玩家裁决那句也是内容（记录流 v2 里它不在派生 paragraphs）。"""
    from core.session.events import make_event
    from core.session.renderer import render_timeline

    ev = make_event("bond", "story_scene",
                    dict(V2_PAYLOAD, input="（旁白）本章：测试。", picked=V2_PICKED),
                    seq=9)
    line = render_timeline([ev])
    assert "老师: " + V2_PICKED in line, line
    assert "……老师，你来了。" in line
    # 无裁决的板 → 不伪造玩家台词
    ev2 = make_event("bond", "story_scene", dict(V2_PAYLOAD, picked=None), seq=10)
    assert "老师: " not in render_timeline([ev2])
    print("    digest: 时间线含玩家裁决行（无裁决不伪造）")
