# -*- coding: utf-8 -*-
"""VN CLI 单测 — story_scene/story_end 双动作契约 + 双核（parse+exec）+ 事件流存档。

send_vn_scene      : ScriptedLLM（chat 返回契约 dict）→ BondScene 结构正确 + 记紧凑 JSON 历史
                    + 无效动作/执行拒绝 feedback 回灌重试 + 3 次失败抛 SceneLoopError
                    + trace 逐轮留痕（attempt/parse/exec）
run_bond_story_vn  : fake input_fn 模拟「选选项 → 推进 → story_end 收尾」闭环
                    + 无选项自由输入路径 + b 退出路径; 每场 append type=bond 事件进事件流
双层兜底            : 15 场提醒 / 22 场上限注记 / 24 场程序兜底收尾（调试值）
wrapup_after_vn    : 剧情结束后的手机收尾（不变）

全部用 ScriptedLLM（不碰 API）; 存档验证走 SessionStore 事件流（tmp_path, 不污染 data/）。
运行: python -m pytest tests/core/test_vn_cli.py
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.momotalk import MomoTalkEngine
from core.bond.bond_story import BondScene, BondStoryEngine, SceneLoopError
from core.bond.bond_executor import StoryExecError, StoryExecutor
from core.session import SessionStore
from core.ui.vn_cli import run_bond_story_vn, simulate_vn_scene

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"


# ----------------------------------------------------------------------------
# ScriptedLLM — chat(json_object) 按调用顺序返回预设动作 dict; snapshots 记
# 每次调用的 messages 副本（供推导系统注记 / 断言 feedback 回灌）
# ----------------------------------------------------------------------------

class ScriptedLLM:
    """带 chat(json_object) 的脚本化 LLM——agent_turn 与 send_vn_scene 都走它。"""

    def __init__(self, *scripts: dict):
        self._scripts = list(scripts)
        self.snapshots: list[list[dict]] = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text"):
        self.snapshots.append([dict(m) for m in messages])
        if not self._scripts:
            raise RuntimeError("ScriptedLLM 脚本耗尽")
        return self._scripts.pop(0)

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


def _seen_notes(llm: ScriptedLLM) -> list[list[str]]:
    """每次 chat 调用的系统注记（= 第一个 system 主 prompt 之后的 system 消息）。"""
    return [[m["content"] for m in msgs if m["role"] == "system"][1:]
            for msgs in llm.snapshots]


def _engine(llm) -> MomoTalkEngine:
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    return engine


def _store_engine(llm, tmp_path) -> tuple[MomoTalkEngine, SessionStore, str]:
    """引擎 + 事件流会话（enter_vn 单流, 存档验证用）。"""
    st = SessionStore(tmp_path)
    engine = _engine(llm)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    return engine, st, root.session_id


# story_scene/story_end 契约动作（与 bond_story_rules.md few-shot 同构）
SCENE_A = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "段落一。"}], "choices": ["选A", "选B"]}}
STORY_END = {"action": "story_end", "payload": {
    "paragraphs": [{"text": "收尾了。"}]}}


# ----------------------------------------------------------------------------
# send_vn_scene: story_scene/story_end 契约 → BondScene 结构 + 紧凑 JSON 历史
# ----------------------------------------------------------------------------

def test_send_vn_scene():
    vn = BondStoryEngine(ROOT / "config" / "characters", ScriptedLLM(SCENE_A))
    vn.start_session(CHARACTER)
    scene = vn.send_vn_scene("（开场）")
    assert scene.paragraphs == [{"text": "段落一。"}], scene.paragraphs
    assert scene.choices == ["选A", "选B"], scene.choices
    assert not scene.is_end
    assert vn.history_length == 2, f"send_vn_scene 应记 2 条历史: {vn.history_length}"
    # 历史存紧凑 JSON（中文完好, 无空格分隔符; story_scene 无 is_end——动作类型推导）
    hist = json.loads(vn.history[-1]["content"])
    assert hist["paragraphs"] == [{"text": "段落一。"}] and hist["choices"] == ["选A", "选B"]
    assert "is_end" not in hist, f"story_scene 历史不应含 is_end: {hist}"
    print(f"    send_vn_scene: 1 段 + 2 选项, 历史紧凑 JSON 中文完好无 is_end, {vn.history_length} 条")

    # 收尾场景（story_end 动作 → is_end 推导为 true）
    vn2 = BondStoryEngine(ROOT / "config" / "characters", ScriptedLLM(STORY_END))
    vn2.start_session(CHARACTER)
    scene2 = vn2.send_vn_scene("继续")
    assert scene2.is_end and scene2.paragraphs == [{"text": "收尾了。"}], scene2
    assert not scene2.choices
    print("    send_vn_scene: story_end 动作 → 收尾场景, 无选项")


# ----------------------------------------------------------------------------
# BondScene 序列化往返 + 宽松容错（一解析器两用: 运行时 + 回放读档）
# ----------------------------------------------------------------------------

def test_bondscene_roundtrip():
    scene = BondScene.from_dict({
        "paragraphs": [{"text": "一段。"}, {"text": "二段。"}], "choices": ["A", "B"], "is_end": True})
    back = BondScene.from_dict(scene.to_dict())
    assert back == scene, "to_dict/from_dict 往返应相等"

    # 宽松: 缺字段 / 混非 str / 无 is_end → 降级不 raise
    plain = BondScene.from_dict({"paragraphs": ["她静静地看着你。"]})
    assert plain.paragraphs == [{"text": "她静静地看着你。"}]
    assert not plain.choices and not plain.is_end
    robust = BondScene.from_dict({"paragraphs": ["好", 42, None], "choices": ["A", 1]})
    assert robust.paragraphs == [{"text": "好"}] and robust.choices == ["A"], robust
    empty = BondScene.from_dict(None)
    assert not empty.paragraphs and not empty.is_end
    print("    bondscene_roundtrip: 往返相等 + 缺字段/坏数据降级（宁缺勿错）")


# ----------------------------------------------------------------------------
# simulate_vn_scene: 选项渲染 → 选择文本; 收尾场景 → None
# ----------------------------------------------------------------------------

def test_simulate_vn_scene():
    scene = BondScene(paragraphs=[{"text": "（她在等你）"}], choices=["走过去", "喊她"])
    picked = simulate_vn_scene(scene, input_fn=lambda p: "2", char_ms=0)
    assert picked == "喊她", f"选 2 应返回第 2 个选项: {picked!r}"

    end = BondScene(paragraphs=[{"text": "再见。"}], is_end=True)
    assert simulate_vn_scene(end, input_fn=lambda p: "1", char_ms=0) is None
    print("    simulate_vn_scene: 选 2→'喊她'; is_end→None")


# ----------------------------------------------------------------------------
# run_bond_story_vn: 选项 → 推进 → is_end 退出, 全程 fake input_fn + 事件流存档
# ----------------------------------------------------------------------------

def test_run_vn_choice_flow(tmp_path):
    scene1 = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "遥香在天台等你。"}], "choices": ["走过去", "喊她名字"]}}
    engine, st, sid = _store_engine(ScriptedLLM(scene1, STORY_END), tmp_path)
    calls = {"n": 0}

    def fake_input(prompt=""):
        calls["n"] += 1
        return "1"

    completed = run_bond_story_vn(engine, input_fn=fake_input, char_ms=0, store=st)
    assert calls["n"] == 1, f"应只出一次选择: {calls['n']}"
    assert completed is True, "走到 is_end 应返回 completed=True"
    evs = st.events(CHARACTER, sid)
    scene_ev = [e for e in evs if e.subtype == "story_scene"][0]
    assert scene_ev.payload["picked"] == "走过去", scene_ev.payload
    print("    run_vn(选项): 选 1 → 推进 → is_end 退出, 事件流 picked 落盘")


# ----------------------------------------------------------------------------
# run_bond_story_vn: 无选项自由输入推进 → is_end 退出
# ----------------------------------------------------------------------------

def test_run_vn_free_input(tmp_path):
    scene1 = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "遥香静静地看着你。"}], "choices": []}}
    engine, st, sid = _store_engine(ScriptedLLM(scene1, STORY_END), tmp_path)
    seq = ["（继续）"]

    def fake_input(prompt=""):
        return seq.pop(0) if seq else "b"

    run_bond_story_vn(engine, input_fn=fake_input, char_ms=0, store=st)
    assert not seq, "自由输入推进后应到 is_end 退出, 不再需要输入"
    evs = st.events(CHARACTER, sid)
    scene_ev = [e for e in evs if e.subtype == "story_scene"][0]
    assert scene_ev.payload["picked"] == "（继续）", scene_ev.payload
    print("    run_vn(自由输入): 无选项 → 输入推进 → is_end 退出, 事件流 picked 记输入")


# ----------------------------------------------------------------------------
# run_bond_story_vn: b 提前退出回 MomoTalk（vn_exit + session_end{ended:false}）
# ----------------------------------------------------------------------------

def test_run_vn_early_exit(tmp_path):
    from core.session.events import M_SESSION_END, M_VN_EXIT
    scene1 = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "遥香看着你，欲言又止。"}], "choices": []}}
    engine, st, sid = _store_engine(ScriptedLLM(scene1), tmp_path)
    completed = run_bond_story_vn(engine, input_fn=lambda p: "b", char_ms=0, store=st)
    assert completed is False, "b 提前退出应返回 completed=False"
    evs = st.events(CHARACTER, sid)
    subs = [e.subtype for e in evs]
    assert M_VN_EXIT in subs and M_SESSION_END in subs, "统一收尾: vn_exit + session_end"
    end_ev = [e for e in evs if e.subtype == M_SESSION_END][0]
    assert end_ev.payload["ended"] is False, end_ev.payload
    print("    run_vn(提前退出): 输入 b → 立即回 MomoTalk, 统一收尾 ended=False")


# ----------------------------------------------------------------------------
# run_bond_story_vn 双层收尾兜底（调试值 15 提醒 / 22 建议收尾 / 24 硬兜底）
# ----------------------------------------------------------------------------

def _scenes(n: int, start: int = 1) -> list[dict]:
    """n 个带选项的未结束 story_scene（永远不用 story_end 收尾）。"""
    return [{"action": "story_scene", "payload": {
        "paragraphs": [{"text": f"场景{i}。"}], "choices": ["继续", "换种方式"]}}
        for i in range(start, start + n)]


def test_run_vn_two_layer_force(tmp_path):
    """模型 24 轮仍不 is_end → 第15场提醒、第22场上限注记、第24场程序兜底收尾。"""
    llm = ScriptedLLM(*_scenes(24))
    engine, st, sid = _store_engine(llm, tmp_path)
    completed = run_bond_story_vn(engine, input_fn=lambda p: "1", char_ms=0,
                                  remind_rounds=15, end_rounds=22, store=st)
    assert completed is True, "模型 24 轮不 is_end → 程序兜底应 completed=True"
    notes = _seen_notes(llm)
    assert len(notes) == 24, f"应跑满 24 场: {len(notes)}"
    assert all(not n for n in notes[:14]), "前 14 场不应注入注记"
    assert len(notes[14]) == 1 and "剩余约 7 轮" in notes[14][0], notes[14]
    assert all(not n for n in notes[15:21]), "16~21 场不应注入注记"
    assert len(notes[21]) == 1 and "已达剧情篇幅上限" in notes[21][0], notes[21]
    assert all(not n for n in notes[22:]), "23~24 场（硬兜底余量）不应注入注记"
    evs = st.events(CHARACTER, sid)
    bond_n = [e for e in evs if e.type == "bond"]
    assert len(bond_n) == 25, f"24 真实 + 1 兜底收尾: {len(bond_n)}"
    print("    双层兜底: 15场提醒/22场上限注记, 24场程序兜底 completed=True")


def test_run_vn_remind_then_natural_end(tmp_path):
    """模型 17 场自然 is_end → 只吃到 15 场提醒, 不走上限注记与硬兜底。"""
    end = {"action": "story_end", "payload": {
        "paragraphs": [{"text": "收尾了。"}]}}
    llm = ScriptedLLM(*_scenes(16), end)
    engine, st, sid = _store_engine(llm, tmp_path)
    completed = run_bond_story_vn(engine, input_fn=lambda p: "1", char_ms=0,
                                  remind_rounds=15, end_rounds=22, store=st)
    assert completed is True, "自然 is_end 应 completed=True"
    notes = _seen_notes(llm)
    assert len(notes) == 17, f"应跑 17 场: {len(notes)}"
    assert len(notes[14]) == 1 and "剩余约 7 轮" in notes[14][0], notes[14]
    assert all(not n for n in notes[:14] + notes[15:]), "只应在 15 场注入一次提醒"
    evs = st.events(CHARACTER, sid)
    bond_n = [e for e in evs if e.type == "bond"]
    assert len(bond_n) == 17, bond_n
    print("    双层兜底: 15场提醒后第17场自然 is_end, 无上限注记/硬兜底")


# ----------------------------------------------------------------------------
# send_vn_scene: 无效动作 feedback 回灌 → LLM 修正重试
# ----------------------------------------------------------------------------

def test_send_vn_scene_invalid_retry():
    bad = {"action": "mmt_teleport", "payload": {}}
    llm = ScriptedLLM(bad, SCENE_A)
    vn = BondStoryEngine(ROOT / "config" / "characters", llm)
    vn.start_session(CHARACTER)
    scene = vn.send_vn_scene("（开场）")
    assert scene.paragraphs == [{"text": "段落一。"}], scene.paragraphs
    # 第一次调用无效 → feedback 回灌（第二次调用的最后一条 user）
    fb = llm.snapshots[1][-1]["content"]
    assert "动作无效" in fb and "未知动作" in fb, fb
    # 历史只记最终有效场景（失败轮不进 history）
    assert vn.history_length == 2, vn.history_length
    print("    send_vn_scene 无效动作: 回灌重试成功, 失败轮不进历史")


# ----------------------------------------------------------------------------
# send_vn_scene: MAX_SCENE_RETRIES 次无效 → SceneLoopError（循环必须终结）
# ----------------------------------------------------------------------------

def test_send_vn_scene_loop_exhausted():
    bad = {"action": "mmt_teleport", "payload": {}}
    vn = BondStoryEngine(ROOT / "config" / "characters", ScriptedLLM(bad, bad, bad))
    vn.start_session(CHARACTER)
    with pytest.raises(SceneLoopError):
        vn.send_vn_scene("（开场）")
    print("    send_vn_scene 耗尽: 3 次无效 → SceneLoopError（宁缺勿错）")


# ----------------------------------------------------------------------------
# 双核执行层: story_end 空段落 parse 拒绝 / exec 拒绝回灌 / exec 耗尽 / trace
# ----------------------------------------------------------------------------

def test_story_end_empty_paragraphs_rejected():
    """story_end 空 paragraphs → parse ContractError → feedback 回灌 → LLM 修正重试。"""
    bad = {"action": "story_end", "payload": {"paragraphs": []}}
    llm = ScriptedLLM(bad, STORY_END)
    vn = BondStoryEngine(ROOT / "config" / "characters", llm)
    vn.start_session(CHARACTER)
    scene = vn.send_vn_scene("继续")
    assert scene.is_end and scene.paragraphs == [{"text": "收尾了。"}], scene
    fb = llm.snapshots[1][-1]["content"]
    assert "动作无效" in fb and "paragraphs" in fb, fb
    print("    story_end 空段落: parse ContractError → 回灌修正重试成功")


def test_story_exec_reject_retry():
    """StoryExecError → feedback 回灌 → LLM 修正重试成功（双核执行层拦截）。"""

    class RejectingExecutor(StoryExecutor):
        """executor stub: 第一次 story_end 抛 StoryExecError, 之后正常。"""
        def __init__(self):
            super().__init__()
            self.rejected = 0
        def execute(self, action):
            if action.action == "story_end" and self.rejected == 0:
                self.rejected += 1
                raise StoryExecError("收尾场景暂不可执行——请重试")
            return super().execute(action)

    llm = ScriptedLLM(STORY_END, STORY_END)
    vn = BondStoryEngine(ROOT / "config" / "characters", llm)
    vn.start_session(CHARACTER)
    vn.executor = RejectingExecutor()
    scene = vn.send_vn_scene("继续")
    assert scene.is_end, "StoryExecError 回灌重试后应成功"
    fb = llm.snapshots[1][-1]["content"]
    assert "暂不可执行" in fb, fb
    print("    story_exec 拒绝: StoryExecError → 回灌修正重试成功")


def test_story_exec_exhaustion_raises_scene_loop():
    """executor 连续拒 3 次 → SceneLoopError（语义扩展: 解析或执行任一失败超限）。"""

    class AlwaysReject(StoryExecutor):
        def execute(self, action):
            raise StoryExecError("总是拒绝")

    vn = BondStoryEngine(ROOT / "config" / "characters",
                         ScriptedLLM(STORY_END, STORY_END, STORY_END))
    vn.start_session(CHARACTER)
    vn.executor = AlwaysReject()
    with pytest.raises(SceneLoopError):
        vn.send_vn_scene("继续")
    print("    story_exec 耗尽: exec 拒 3 次 → SceneLoopError（循环必须终结）")


def test_trace_records_attempts():
    """trace 逐轮留痕: 1 次 parse 失败 + 1 次成功, attempt/parse/exec 字段齐全。"""
    bad = {"action": "mmt_teleport", "payload": {}}
    llm = ScriptedLLM(bad, SCENE_A)
    vn = BondStoryEngine(ROOT / "config" / "characters", llm)
    vn.start_session(CHARACTER)
    vn.send_vn_scene("（开场）")
    trace = vn.trace
    assert len(trace) == 2, f"1 次解析失败 + 1 次成功: {len(trace)}"
    # 第一次: parse 失败, 无 exec 字段
    assert trace[0]["attempt"] == 0 and trace[0]["action"] is None
    assert trace[0]["parse_valid"] is False and trace[0]["parse_errors"]
    assert "exec_ok" not in trace[0], "parse 失败轮不应有 exec 字段"
    # 第二次: parse 成功 + exec 成功
    assert trace[1]["attempt"] == 1 and trace[1]["action"] == "story_scene"
    assert trace[1]["parse_valid"] is True and not trace[1]["parse_errors"]
    assert trace[1]["exec_ok"] is True and trace[1]["exec_message"] == "中段场景已就绪"
    assert trace[1]["payload"]["paragraphs"] == [{"text": "段落一。"}]
    print("    trace: 1 失败 + 1 成功, attempt/parse/exec 字段齐全")


# ----------------------------------------------------------------------------
# wrapup_after_vn: 剧情结束后的手机收尾（agent_turn 走 ScriptedLLM.chat）
# ----------------------------------------------------------------------------

def test_wrapup_after_vn():
    from core.bond.bond_progress import BondProgress
    from core.ui.vn_cli import wrapup_after_vn

    # 动作列表格式（2026-08-23: MMT 输出 {"actions": [...]}）
    trig = {"actions": [
        {"action": "mmt_trigger_bond_story", "payload": {"reason": "气氛到了"}}]}
    wrap = {"actions": [
        {"action": "mmt_chat",
         "reply": "今天去了天台……我很开心。下次再一起吧！", "payload": {}}]}

    with tempfile.TemporaryDirectory() as d:
        progress = BondProgress(data_root=Path(d))
        progress.record_turn(CHARACTER)          # 预积累 1 轮, 满足软门槛兜底
        llm = ScriptedLLM(trig, wrap)
        engine = MomoTalkEngine(ROOT / "config" / "characters", llm,
                                bond_progress=progress)
        engine.start_session(CHARACTER)
        result = engine.agent_turn("今天我们聊了很多")
        assert result.bond_story, "第 2 轮触发应成功（软门槛）"
        assert engine.history_length == 2
        wrapup_after_vn(engine)
        # 收尾只记 assistant（record_input=False, 不污染假 user 消息）
        assert engine.history_length == 3, f"收尾应 +1 条历史: {engine.history_length}"
        assert engine.history[-1]["content"].startswith("[mmt_chat]")
        # 收尾注记注入（第二次 chat 调用: 倒数第 2 = 系统注记, 倒数第 1 = user）
        note = llm.snapshots[1][-2]["content"]
        assert "羁绊剧情" in note and "收尾" in note and "气氛到了" in note, note
        print("    wrapup_after_vn: 收尾 +1 历史(仅 assistant), 注记引述起因, 回几段话")


# ----------------------------------------------------------------------------
# 事件流接入: run_bond_story_vn + store → 单流 enter_vn + bond 事件 + vn_state + 收尾
# ----------------------------------------------------------------------------

def test_vn_event_stream(tmp_path):
    from core.session.events import M_SESSION_END, M_SESSION_START, M_VN_ENTER, M_VN_EXIT, M_VN_STATE
    from core.session.renderer import session_status

    st = SessionStore(tmp_path)
    llm = ScriptedLLM(SCENE_A, STORY_END)
    engine = _engine(llm)
    root = st.create(CHARACTER)                 # 单事件流会话（main 层行为）
    engine.attach_session(root.session_id)
    completed = run_bond_story_vn(
        engine, input_fn=lambda p: "1", char_ms=0,
        remind_rounds=15, end_rounds=22, store=st)
    assert completed

    # 单事件流: 根会话即全部（enter_vn 无子会话, mmt+bond 同文件）
    evs = st.events(CHARACTER, root.session_id)
    subs = [e.subtype for e in evs]
    assert subs[:2] == [M_SESSION_START, M_VN_ENTER], subs
    assert "story_scene" in subs and "story_end" in subs
    assert M_VN_STATE in subs and M_VN_EXIT in subs and M_SESSION_END in subs
    # bond 事件含 input（本场触发输入）+ picked（玩家裁决）
    scene_ev = [e for e in evs if e.subtype == "story_scene"][0]
    assert scene_ev.payload["input"].startswith("（旁白）")
    assert scene_ev.payload["picked"] == "选A"
    assert scene_ev.payload["paragraphs"] == [{"text": "段落一。"}]
    # vn_enter 单流无 parent
    enter = [e for e in evs if e.subtype == M_VN_ENTER][0]
    assert "parent_session_id" not in enter.payload
    # 状态推导: 收尾（vn_exit + session_end）→ ended
    st2 = session_status(evs)
    assert st2["ended"] is True and st2["in_vn"] is False
    print("    vn-store: enter_vn 单流 + bond 事件(input/picked) + vn_state + vn_exit/session_end")
