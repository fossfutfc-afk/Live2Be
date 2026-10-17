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
import ast
import sys
import tempfile
from pathlib import Path

from cli.vn_cli import run_bond_story_vn, simulate_vn_scene
from core.bond.bond_story import BondScene, BondStoryEngine
from core.mmt.engine import MomoTalkEngine
from core.session import SessionStore
from core.session.events import M_VN_EXIT
from llm import task_labels as T
from tests import stub_tasks
from tests.vn_fixtures import scene

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"


# ----------------------------------------------------------------------------
# ScriptedLLM — chat(json_object) 按调用顺序返回预设动作 dict; snapshots 记
# 每次调用的 messages 副本（供推导系统注记 / 断言 feedback 回灌）
# ----------------------------------------------------------------------------

class ScriptedLLM:
    """带 chat(json_object) 的脚本化 LLM——agent_turn 与 send_vn_scene 都走它。
    两轮 digest（async_digest 后台）自动返回空包, 不消耗脚本。
    emotion 标注调用（2026-09-02: 骨架 emotion 丢弃 → 标注层全量回填）自动
    返回同长 nomal 数组——从 system 里的编号行数推断句数, 不消耗脚本。"""

    def __init__(self, *scripts: dict):
        self._scripts = list(scripts)
        self.snapshots: list[list[dict]] = []
        self.tasks: list[str | None] = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text",
             **kw):
        task = kw.get("task")
        self.snapshots.append([dict(m) for m in messages])
        self.tasks.append(task)
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:                # 标注/digest 两轮 → 标准应答
            return reply
        if task in T.MAIN:
            if not self._scripts:
                raise RuntimeError("ScriptedLLM 脚本耗尽")
            # 注: 内联 dict 场景的用例仍走**旧动作开关**（P0-7c 收尾项: 脚本计数需按
            # v2 板数重算后再接适配器）; 常量 SCENE_A/STORY_END 已是记录流。
            return self._scripts.pop(0)
        raise stub_tasks.unknown_task(task)

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


def _seen_notes(llm: ScriptedLLM) -> list[list[str]]:
    """每次**场景轮** chat 调用的系统**约束注记**（= 第一个 system 主 prompt 之后的
    system 消息）。emotion/place 标注调用（按 `task` 判, 2026-09-21 节点 5b 起不再
    认文案）不算场景轮, 过滤掉; task 卡（本场任务, 目标层——2026-09-07 promptkit
    §4）也不属于约束注记, 过滤掉（卡槽位由 test_promptkit_baseline 锁定）。"""
    out: list[list[str]] = []
    for msgs, task in zip(llm.snapshots, llm.tasks):
        if task not in T.MAIN:
            continue                      # 标注/翻译/选图/digest 不产生场景轮
        notes = [m["content"] for m in msgs if m["role"] == "system"][1:]
        out.append([n for n in notes
                    if not n.startswith("本场任务：")
                    and not n.startswith("本回合任务：")])
    return out


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


# 记录流 v2（P0-7c 迁移）: 块 = 一行一条 JSON 记录; 槽 = 连续 sensei（挂板尾）
SCENE_A = scene(switch_to="教室", lines=["段落一。"], sensei=["选A", "选B"],
                after=["分支一。"])
STORY_END = scene(lines=["收尾了。"], end_text="（幕落。）")


# ----------------------------------------------------------------------------
# send_vn_scene: story_scene/story_end 契约 → BondScene 结构 + 紧凑 JSON 历史
# ----------------------------------------------------------------------------

def test_send_vn_scene():
    """记录流一场: 正文进显示、群 → 选项; 历史 = 叙事渲染（**槽内候选不进上下文**）。"""
    vn = BondStoryEngine(ROOT / "config" / "characters", ScriptedLLM(SCENE_A))
    vn.start_session(CHARACTER)
    scene = vn.send_vn_scene("（开场）")
    assert [p["text"] for p in scene.paragraphs] == ["段落一。"], scene.paragraphs
    assert scene.paragraphs[0]["speaker"] == CHARACTER
    assert scene.choices == ["选A", "选B"], scene.choices
    assert not scene.is_end and scene.place_hint == "教室"
    assert vn.history_length == 2, f"send_vn_scene 应记 2 条历史: {vn.history_length}"
    # 历史 = 记录流叙事渲染（2026-09-05 统一窗口——与 render_events/事件流渲染同构）;
    # 未选候选永不进上下文（A1）
    hist = vn.history[-1]["content"]
    assert "段落一。" in hist and "教室" in hist
    assert "选A" not in hist and "选B" not in hist
    print(f"    send_vn_scene: 1 段 + 2 选项（槽候选不进历史）, {vn.history_length} 条")

    # 收尾块（stage=end → is_end）
    vn2 = BondStoryEngine(ROOT / "config" / "characters", ScriptedLLM(STORY_END))
    vn2.start_session(CHARACTER)
    scene2 = vn2.send_vn_scene("继续")
    assert scene2.is_end and [p["text"] for p in scene2.paragraphs] == ["收尾了。", "（幕落。）"], scene2
    assert not scene2.choices
    print("    send_vn_scene: stage=end → 收尾块, 无选项")


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
    scene1 = scene(switch_to="天台", lines=["遥香在天台等你。"],
                   sensei=["走过去", "喊她名字"])
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
    # vn_exit 带剧情完成标志（2026-09-01）: 完整剧情 → completed=True
    exit_ev = [e for e in evs if e.subtype == M_VN_EXIT][0]
    assert exit_ev.payload.get("completed") is True, exit_ev.payload
    print("    run_vn(选项): 选 1 → 推进 → is_end 退出, 事件流 picked 落盘")


# ----------------------------------------------------------------------------
# run_bond_story_vn: 无选项自由输入推进 → is_end 退出
# ----------------------------------------------------------------------------

def test_run_vn_free_input(tmp_path):
    scene1 = scene(lines=["遥香静静地看着你。"])
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
    scene1 = scene(lines=["遥香看着你，欲言又止。"])
    engine, st, sid = _store_engine(ScriptedLLM(scene1), tmp_path)
    completed = run_bond_story_vn(engine, input_fn=lambda p: "b", char_ms=0, store=st)
    assert completed is False, "b 提前退出应返回 completed=False"
    evs = st.events(CHARACTER, sid)
    subs = [e.subtype for e in evs]
    assert M_VN_EXIT in subs and M_SESSION_END in subs, "统一收尾: vn_exit + session_end"
    end_ev = [e for e in evs if e.subtype == M_SESSION_END][0]
    assert end_ev.payload["ended"] is False, end_ev.payload
    # vn_exit 带剧情完成标志（2026-09-01）: 中途退出 → completed=False
    exit_ev = [e for e in evs if e.subtype == M_VN_EXIT][0]
    assert exit_ev.payload.get("completed") is False, exit_ev.payload
    print("    run_vn(提前退出): 输入 b → 立即回 MomoTalk, 统一收尾 ended=False")


# ----------------------------------------------------------------------------
# run_bond_story_vn 双层收尾兜底（调试值 15 提醒 / 22 建议收尾 / 24 硬兜底）
# ----------------------------------------------------------------------------

def _scenes(n: int, start: int = 1) -> list[str]:
    """n 个不 is_end 的单板记录流（永远不用 stage=end 收尾——测兜底注记）。"""
    return [scene(lines=[f"场景{i}。"]) for i in range(start, start + n)]


def test_run_vn_two_layer_force(tmp_path):
    """模型 24 轮仍不 is_end → 15 场提醒 / 22 场上限注记 / 耗尽 = 中断退出
    （2026-09-09 CLI 对齐: 不再程序兜底伪收场——completed=False, 不落 story_end）。"""
    llm = ScriptedLLM(*_scenes(24))
    engine, st, sid = _store_engine(llm, tmp_path)
    completed = run_bond_story_vn(engine, input_fn=lambda p: "1", char_ms=0,
                                  remind_rounds=15, end_rounds=22, store=st)
    assert completed is False, "篇幅耗尽 = 中断退出（不伪收场）"
    notes = _seen_notes(llm)
    assert len(notes) == 24, f"应跑满 24 场: {len(notes)}"
    # 第 1 场可能有 memory_flash 随机事件（wiki 出厂记忆落盘后生效, 概率 25%）;
    # 其余 2~14 场不得有注记
    assert all(len(n) <= 1 for n in notes[:14]), "前 14 场只允许第 1 场的记忆浮现"
    assert len(notes[14]) == 1 and "剩余约 7 轮" in notes[14][0], notes[14]
    assert all(not n for n in notes[15:21]), "16~21 场不应注入注记"
    assert len(notes[21]) == 1 and "已达剧情篇幅上限" in notes[21][0], notes[21]
    assert all(not n for n in notes[22:]), "23~24 场（余量）不应注入注记"
    evs = st.events(CHARACTER, sid)
    bond_n = [e for e in evs if e.type == "bond"]
    assert len(bond_n) == 24, f"24 场真实内容, 无兜底假收尾: {len(bond_n)}"
    exits = [e for e in evs if e.type == "marker" and e.subtype == "vn_exit"]
    assert exits and exits[-1].payload.get("completed") is False
    print("    双层兜底: 15 场提醒/22 场上限注记; 耗尽 = 中断退出（零伪收场）")


class _FailFirst(ScriptedLLM):
    """前 n 次 LLM 调用抛异常（send 内每 attempt 一次）, 之后正常出脚本。"""

    def __init__(self, fail_calls: int, *scripts):
        super().__init__(*scripts)
        self._fails = fail_calls

    def chat(self, messages, temperature=0.8, max_tokens=4096,
             response_format="text", **kw):
        task = kw.get("task")
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:                # 标注类自动应答（不耗脚本/不耗失败）
            return reply
        if task not in T.MAIN:
            raise stub_tasks.unknown_task(task)
        if self._fails > 0:
            self._fails -= 1
            raise RuntimeError("api down")
        return super().chat(messages, temperature=temperature,
                            max_tokens=max_tokens,
                            response_format=response_format, **kw)


def test_run_vn_gen_fail_retry_then_end(tmp_path):
    """生成失败自动重试（同输入, ≤3 次）→ 恢复成功 → 自然收尾 completed=True。"""
    end = scene(lines=["收尾了。"], end_text="")
    # send1: 3 attempts 全败 → 自动重试; send2: 首 attempt 再败 → 第 2 attempt 成功
    llm = _FailFirst(4, end)
    engine, st, sid = _store_engine(llm, tmp_path)
    completed = run_bond_story_vn(engine, input_fn=lambda p: "b", char_ms=0,
                                  remind_rounds=15, end_rounds=22, store=st)
    assert completed is True, "失败自动重试后自然 story_end → completed=True"
    evs = st.events(CHARACTER, sid)
    assert ("bond", "story_end") in [(e.type, e.subtype) for e in evs]
    exits = [e for e in evs if e.type == "marker" and e.subtype == "vn_exit"]
    assert exits and exits[-1].payload.get("completed") is True
    print("    CLI 失败: 自动重试恢复 → 自然收尾（completed=True 且落库正常）")


def test_run_vn_gen_fail_abort(tmp_path):
    """连续失败超限（4 send × 3 attempts）→ 中断退出: completed=False、
    不落任何 bond 场景/结束事件（旧语义曾落 closing story_end + completed）。"""
    llm = _FailFirst(12)
    engine, st, sid = _store_engine(llm, tmp_path)
    completed = run_bond_story_vn(engine, input_fn=lambda p: "1", char_ms=0,
                                  remind_rounds=15, end_rounds=22, store=st)
    assert completed is False, "连续失败超限 → 中断退出（completed=False）"
    evs = st.events(CHARACTER, sid)
    assert not any(e.type == "bond" for e in evs), "零伪收场（无 bond 场景落库）"
    exits = [e for e in evs if e.type == "marker" and e.subtype == "vn_exit"]
    assert exits and exits[-1].payload.get("completed") is False
    print("    CLI 失败超限: 中断退出（completed=False / 零 bond 事件 / vn_exit False）")


def test_run_vn_remind_then_natural_end(tmp_path):
    """模型 17 场自然 is_end → 只吃到 15 场提醒, 不走上限注记与硬兜底。"""
    end = scene(lines=["收尾了。"], end_text="")
    llm = ScriptedLLM(*_scenes(16), end)
    engine, st, sid = _store_engine(llm, tmp_path)
    completed = run_bond_story_vn(engine, input_fn=lambda p: "1", char_ms=0,
                                  remind_rounds=15, end_rounds=22, store=st)
    assert completed is True, "自然 is_end 应 completed=True"
    notes = _seen_notes(llm)
    assert len(notes) == 17, f"应跑 17 场: {len(notes)}"
    assert len(notes[14]) == 1 and "剩余约 7 轮" in notes[14][0], notes[14]
    assert all(len(n) <= 1 for n in notes[:14]), "前 14 场只允许第 1 场记忆浮现"
    assert all(not n for n in notes[15:]), "16 场后不应注入注记"
    evs = st.events(CHARACTER, sid)
    bond_n = [e for e in evs if e.type == "bond"]
    assert len(bond_n) == 17, bond_n
    print("    双层兜底: 15场提醒后第17场自然 is_end, 无上限注记/硬兜底")


# ----------------------------------------------------------------------------
# send_vn_scene: 无效动作 feedback 回灌 → LLM 修正重试
# ----------------------------------------------------------------------------
# wrapup_after_vn: 剧情结束后的手机收尾（agent_turn 走 ScriptedLLM.chat）
# ----------------------------------------------------------------------------

def test_wrapup_after_vn():
    from cli.vn_cli import wrapup_after_vn
    from core.bond.bond_progress import BondProgress

    # 行协议（⑥-2e）: 一行一条 JSON; trigger payload = chapter_title
    trig = '{"action": "mmt_trigger_bond_story", "payload": {"chapter_title": "天台的气氛"}}'
    wrap = '{"text": "今天去了天台……我很开心。下次再一起吧！"}'

    with tempfile.TemporaryDirectory() as d:
        progress = BondProgress(data_root=Path(d))
        progress.record_turn(CHARACTER)          # 全局累计（仅偏好统计, 不参与节奏）
        llm = ScriptedLLM(trig, wrap)
        engine = MomoTalkEngine(ROOT / "config" / "characters", llm,
                                bond_progress=progress)
        engine.start_session(CHARACTER)
        result = engine.agent_turn("今天我们聊了很多")
        assert result.bond_story, "v2: 引擎不拦节奏——trigger 即放行"
        assert engine.history_length == 2
        wrapup_after_vn(engine)
        # 收尾只记 assistant（record_input=False, 不污染假 user 消息）;
        # ⑥-2e 起一行 = 一个气泡（不再切片）→ 收尾正好 +1 条历史
        assert engine.history_length == 3, f"收尾应 +1 条历史: {engine.history_length}"
        wrap_tail = engine.history[2:]
        assert any(h["content"].startswith("[mmt_chat]") for h in wrap_tail)
        assert "下次再一起吧" in "".join(h["content"] for h in wrap_tail)
        # 收尾注记注入（第二次 chat 调用: 尾序 = 系统注记 → task 卡 → user,
        # 2026-09-07 promptkit §4: 卡 = 目标层, 恒在注记后 user 前）
        tail = llm.snapshots[1]
        note = tail[-3]["content"]                        # P17 收尾注记
        assert "羁绊剧情" in note and "收尾" in note and "本章: 天台的气氛" in note, note
        assert tail[-2]["content"].startswith("本回合任务：")   # wrapup 卡
        assert "只发**消息行**" in tail[-2]["content"]
        print("    wrapup_after_vn: 收尾 +1 历史(仅 assistant), 注记引述章名, 回几段话")


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
    # bond 事件含 input（本场触发输入）+ picked（玩家裁决）+ 记录真源
    scene_ev = [e for e in evs if e.subtype == "story_scene"][0]
    assert scene_ev.payload["input"].startswith("（旁白）")
    assert scene_ev.payload["picked"] == "选A"
    assert scene_ev.payload["records"][0] == {"stage": "switch", "text": "教室"}
    assert [p["text"] for p in scene_ev.payload["paragraphs"]] == ["段落一。"]
    # vn_enter 单流无 parent
    enter = [e for e in evs if e.subtype == M_VN_ENTER][0]
    assert "parent_session_id" not in enter.payload
    # 状态推导: 收尾（vn_exit + session_end）→ ended
    st2 = session_status(evs)
    assert st2["ended"] is True and st2["in_vn"] is False
    print("    vn-store: enter_vn 单流 + bond 事件(input/picked) + vn_state + vn_exit/session_end")


# ----------------------------------------------------------------------------
# 触发节奏 v2（2026-09-02 用户复盘）: 引擎**建议不拦截**——轮数无硬闸,
# LLM 输出 trigger 即放行; 时机靠每轮注记分级建议（gap<6 沉淀事实 / ≥6 主动提示）
# ----------------------------------------------------------------------------

_TRIG = '{"action": "mmt_trigger_bond_story", "payload": {"chapter_title": "气氛到了"}}'
_CHAT = '{"text": "嗯……好啊。"}'


def test_trigger_no_gate_and_suggestion_notes():
    """v2 语义: 0 轮 trigger 也放行（不拦——紧急剧情无需尬聊等轮数）;
    注记分级: 沉淀期报事实, 达建议线（6）主动建议发起。"""
    # 0 轮（刚开场）→ trigger 直接放行
    llm = ScriptedLLM(_TRIG)
    engine = _engine(llm)
    engine.start_session(CHARACTER)
    r = engine.agent_turn("老师！我这边有危险，快来！")
    assert r.bond_story, "v2: 引擎不拦节奏——首条消息 trigger 也应放行"
    print("    trigger v2: 0 轮放行（无硬闸, 紧急剧情 LLM 全权裁决）")

    # 注记分级: 跑到建议线后建议语出现; 早期是沉淀事实语
    # （注记在每轮 LLM 调用前注入——第 i 轮注记显示 gap=i-1）
    chat7 = [_CHAT] * 7
    llm2 = ScriptedLLM(*chat7)
    engine2 = _engine(llm2)
    engine2.start_session(CHARACTER)
    for i in range(7):
        engine2.agent_turn(f"闲聊 {i}")
        msgs = llm2.snapshots[i]
        # 尾序（2026-09-07 promptkit §4）: 注记们 → task 卡 → user
        # ⚠️ **注记按下标取, 不要全文搜** —— 前几轮的注记已渲染进 history,
        #    搜旧文案会命中**历史里那条旧的**（2026-09-13 加时间注记时踩到）。
        assert msgs[-2]["content"].startswith("本回合任务：")      # chat 卡
        assert msgs[-1]["role"] == "user"
        # ⛔ P16「羁绊进度注记」**已封印**（2026-10-08 用户裁决）—— 从前这里断言它两档
        #    分级（沉淀期 / 【剧情时机】建议）; 现在**整轮注入面都不许**再有轮次驱动的
        #    时机表态（触发只由规则书的契机判据 + LLM 判断决定）。
        #    封印的守门在 `tests/core/test_mmt_trigger_note_sealed.py`; 这里只保留
        #    "别改回来"的轻量一瞥（防止有人顺手恢复注记却发现用例早被删了）。
        joined = "\n".join(m.get("content") or "" for m in msgs)
        assert "【剧情时机】" not in joined and "羁绊进度事实" not in joined, \
            "P16 注记被改回来了？（2026-10-08 已封印）"
    print("    P16 已封印: gap≥6 也不再出现轮次驱动的触发建议（不拦截语义不变）")


def test_bond_gap_persist_and_clear(tmp_path):
    """rounds_since_bond 持久化 + vn_exit 清零时机（用户拍板）:
    完整剧情结束（completed）→ 清零; 中途退出 → 保留; 断线重连继续累计。
    （v2: 该计数只驱动建议注记, 不再拦截——清零让注记重新报沉淀期）"""
    # 聊 1 轮 → gap=1; 断线重连（新引擎 attach 同会话）→ gap 仍 1
    st = SessionStore(tmp_path)
    llm = ScriptedLLM(_CHAT)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    engine.agent_turn("你好呀")
    assert st.read_bond_gap(CHARACTER) == 1, st.read_bond_gap(CHARACTER)
    # 重连（模拟重启: 新引擎实例 attach 同一角色线）→ 不从 0 开始
    llm2 = ScriptedLLM(_CHAT)
    engine2 = MomoTalkEngine(ROOT / "config" / "characters", llm2, store=st)
    engine2.start_session(CHARACTER)
    engine2.attach_session(root.session_id)
    assert engine2._bond_gap == 1, "attach 应恢复持久计数"
    engine2.agent_turn("继续聊")
    assert st.read_bond_gap(CHARACTER) == 2
    # 中途退出 bond（b）→ completed=False → gap 保留
    llm3 = ScriptedLLM(scene(lines=["缺口场。"]))
    engine3 = MomoTalkEngine(ROOT / "config" / "characters", llm3, store=st)
    engine3.start_session(CHARACTER)
    engine3.attach_session(root.session_id)
    completed = run_bond_story_vn(engine3, input_fn=lambda p: "b", char_ms=0,
                                  remind_rounds=15, end_rounds=22, store=st)
    assert completed is False
    assert st.read_bond_gap(CHARACTER) == 2, "中途退出不清零（只有完整演过才值得冷却）"
    # 完整剧情结束 → vn_exit completed → 清零
    llm4 = ScriptedLLM(scene(lines=["缺口场。"]), STORY_END)
    engine4 = MomoTalkEngine(ROOT / "config" / "characters", llm4, store=st)
    engine4.start_session(CHARACTER)
    engine4.attach_session(root.session_id)
    completed4 = run_bond_story_vn(engine4, input_fn=lambda p: "1", char_ms=0,
                                   remind_rounds=15, end_rounds=22, store=st)
    assert completed4 is True
    assert st.read_bond_gap(CHARACTER) == 0, "完整剧情结束 → rounds_since_bond 清零"
    print("    bond_gap: 持久(断线继续) + 中途退出保留 + vn_exit completed 清零")


def test_bond_gap_legacy_migration(tmp_path):
    """旧 progress.json（仅 rounds 键, 死数据）→ read_bond_gap 视为 0（2026-09-02
    用户拍板: 旧值作废置 0, 宁缺勿错——新语义从零起算）。"""
    import json as _json
    st = SessionStore(tmp_path)
    root = st.create(CHARACTER)
    p = st.progress_path(CHARACTER)
    p.write_text(_json.dumps({"rounds": 42, "updated_at": "2026-01-01"}), encoding="utf-8")
    assert st.read_bond_gap(CHARACTER) == 0
    # 缺失/损坏 → 0
    assert st.read_bond_gap("no_such_char") == 0
    print("    bond_gap 迁移: 旧 rounds 字段作废置 0; 缺失/损坏 → 0")


def test_main_app_injects_store_into_vn():
    """`cli/main.py` 那条生产路径必须把 store 传进 `run_bond_story_vn`。

    不传 ⇒ `truth = store = None`, 整章剧情的事件全被 `if store is not None` 跳过
    （`vn_enter` / 每场 bond / marker / `commit_staging` / `finish`）——**跑起来一切正常**,
    只是事件流里没有这段剧情 ⇒ 收尾窗口、digest、回放全空。
    本文件其余用例都自己传 store, 所以只有这条能守它。
    """
    src = (ROOT / "cli" / "main.py").read_text(encoding="utf-8")
    calls = [
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "run_bond_story_vn"
    ]
    assert calls, "cli/main.py 里找不到 run_bond_story_vn 调用"
    for call in calls:
        kw = {k.arg: k.value for k in call.keywords if k.arg}
        assert "store" in kw, f"第 {call.lineno} 行没传 store ⇒ 剧情不落事件流"
        assert not (isinstance(kw["store"], ast.Constant) and kw["store"].value is None), \
            f"第 {call.lineno} 行 store=None, 等于没传"
    print("    cli/main.py: VN 调用带 store（剧情落事件流）")
