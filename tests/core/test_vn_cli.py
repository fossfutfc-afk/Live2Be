# -*- coding: utf-8 -*-
"""VN CLI 单测 — 结构化场景 + 收敛分支循环。

send_vn_scene  : StreamLLM（有 chat_stream）→ 段落/选项/完结构正确 + 记历史
run_bond_story_vn: fake input_fn 模拟「选选项 → 推进 → 【完】退出」闭环
                    + 无选项自由输入路径 + b 退出路径

断言全部子串/等值; 不碰 API, 不污染 data/。
运行: python -m pytest tests/core/test_vn_cli.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.momotalk import MomoTalkEngine
from core.bond_story import BondStoryEngine
from core.ui.vn_cli import run_bond_story_vn, simulate_vn_scene

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"

PASS = 0
FAIL = 0


def check(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS {name}")
    except Exception as e:  # noqa: BLE001
        FAIL += 1
        print(f"  FAIL {name}: {type(e).__name__}: {e}")


# ----------------------------------------------------------------------------
# StreamLLM — chat_stream 依次 yield 预设文本（逐 token）
# ----------------------------------------------------------------------------

class StreamLLM:
    """LLMClient 兼容面: format_messages + chat_stream（无 chat 也无所谓）。"""

    def __init__(self, *texts: str):
        self._texts = list(texts)
        self.seen_notes: list[list[str]] = []   # 每次调用注入的系统注记（无 = []）

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs

    def chat_stream(self, messages, temperature=0.8, max_tokens=1024):
        if not self._texts:
            raise RuntimeError("StreamLLM 脚本耗尽")
        text = self._texts.pop(0)
        # 注记 = 第一个 system（主 prompt）之后的 system 消息（history 无 system）
        self.seen_notes.append(
            [m["content"] for m in messages[1:] if m["role"] == "system"]
        )
        for ch in text:
            yield ch


class ScriptedLLM:
    """带 chat(json_object) 的脚本化 LLM——wrapup_after_vn 走 agent_turn 需要。"""

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


def _engine(llm) -> MomoTalkEngine:
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    return engine


# ----------------------------------------------------------------------------
# send_vn_scene: 段落/选项/完结构 + 记历史
# ----------------------------------------------------------------------------

def test_send_vn_scene():
    text = "段落一。\n\n【选择】\n1. 选A\n2. 选B"
    vn = BondStoryEngine(ROOT / "config" / "characters", StreamLLM(text))
    vn.start_session(CHARACTER)
    scene = vn.send_vn_scene("（开场）")
    assert scene.paragraphs == ["段落一。"], scene.paragraphs
    assert scene.choices == ["选A", "选B"], scene.choices
    assert not scene.is_end
    assert vn.history_length == 2, f"send_vn_scene 应记 2 条历史: {vn.history_length}"
    print(f"    send_vn_scene: 1 段 + 2 选项, 历史 {vn.history_length} 条")

    # 完场景
    vn2 = BondStoryEngine(ROOT / "config" / "characters",
                          StreamLLM("收尾了。\n\n【完】"))
    vn2.start_session(CHARACTER)
    scene2 = vn2.send_vn_scene("继续")
    assert scene2.is_end and scene2.paragraphs == ["收尾了。"]
    print("    send_vn_scene: 【完】→ is_end=True")


# ----------------------------------------------------------------------------
# _parse_scene 容错: 模型分隔段落的换行不一致（\n\n / \n / '  \n' 都出现过）
# ----------------------------------------------------------------------------

def test_parse_scene_robust():
    # 模型实际风格: 行尾两空格 + 单换行分隔, 标记被埋 → 旧解析器永远检测不到
    text = ("（听到邀请）她一愣。  \n"
            "（偷偷瞄一眼）不是我想单独吃饭哦。  \n"
            "【选择】\n1. 笑着点头\n2. 故意逗她")
    scene = BondStoryEngine._parse_scene(text)
    assert scene.paragraphs == ["（听到邀请）她一愣。\n（偷偷瞄一眼）不是我想单独吃饭哦。"], scene.paragraphs
    assert scene.choices == ["笑着点头", "故意逗她"], scene.choices
    assert not scene.is_end

    # 单换行 + 【完】无空行 → 仍能识别结束
    scene2 = BondStoryEngine._parse_scene("她笑了。\n【完】")
    assert scene2.is_end and scene2.paragraphs == ["她笑了。"]

    # 全角顿号 / 句点编号 → 也能剥前缀
    scene3 = BondStoryEngine._parse_scene("【选择】\n1．走过去\n2、喊她")
    assert scene3.choices == ["走过去", "喊她"], scene3.choices
    print("    _parse_scene 容错: '  \\n'/单换行/全角编号 → 选项与【完】均检出")


# ----------------------------------------------------------------------------
# simulate_vn_scene: 选项渲染 → 选择文本; 完场景 → None
# ----------------------------------------------------------------------------

def test_simulate_vn_scene():
    scene = BondStoryEngine._parse_scene("【选择】\n1. 走过去\n2. 喊她")
    picked = simulate_vn_scene(scene, input_fn=lambda p: "2", char_ms=0)
    assert picked == "喊她", f"选 2 应返回第 2 个选项: {picked!r}"

    end = BondStoryEngine._parse_scene("再见。\n\n【完】")
    assert simulate_vn_scene(end, input_fn=lambda p: "1", char_ms=0) is None
    print("    simulate_vn_scene: 选 2→'喊她'; 完场景→None")


# ----------------------------------------------------------------------------
# run_bond_story_vn: 选项 → 推进 → 【完】退出, 全程 fake input_fn
# ----------------------------------------------------------------------------

def test_run_vn_choice_flow():
    scene1 = "遥香在天台等你。\n\n【选择】\n1. 走过去\n2. 喊她名字"
    scene2 = "她转过身来，笑了。\n\n【完】"
    engine = _engine(StreamLLM(scene1, scene2))
    calls = {"n": 0}

    def fake_input(prompt=""):
        calls["n"] += 1
        return "1"

    completed = run_bond_story_vn(engine, input_fn=fake_input, char_ms=0)
    assert calls["n"] == 1, f"应只出一次选择: {calls['n']}"
    assert completed is True, "走到【完】应返回 completed=True"
    print("    run_vn(选项): 选 1 → 推进 → 【完】退出, 选择调用 1 次")


# ----------------------------------------------------------------------------
# run_bond_story_vn: 无选项自由输入推进 → 【完】退出
# ----------------------------------------------------------------------------

def test_run_vn_free_input():
    scene1 = "遥香静静地看着你。"
    scene2 = "结束了。\n\n【完】"
    engine = _engine(StreamLLM(scene1, scene2))
    seq = ["（继续）"]

    def fake_input(prompt=""):
        return seq.pop(0) if seq else "b"

    run_bond_story_vn(engine, input_fn=fake_input, char_ms=0)
    assert not seq, "自由输入推进后应到【完】退出, 不再需要输入"
    print("    run_vn(自由输入): 无选项 → 输入推进 → 【完】退出")


# ----------------------------------------------------------------------------
# run_bond_story_vn: b 提前退出回 MomoTalk
# ----------------------------------------------------------------------------

def test_run_vn_early_exit():
    scene1 = "遥香看着你，欲言又止。"
    engine = _engine(StreamLLM(scene1))
    completed = run_bond_story_vn(engine, input_fn=lambda p: "b", char_ms=0)
    assert completed is False, "b 提前退出应返回 completed=False"
    print("    run_vn(提前退出): 输入 b → 立即回 MomoTalk")


# ----------------------------------------------------------------------------
# run_bond_story_vn 双层收尾兜底（调试值 15 提醒 / 22 建议收尾 / 24 硬兜底）
# ----------------------------------------------------------------------------

def _scenes(n: int, start: int = 1) -> list[str]:
    """n 个带【选择】的未结束场景（永远不输出【完】）。"""
    return [f"场景{i}。\n\n【选择】\n1. 继续\n2. 换种方式" for i in range(start, start + n)]


def test_run_vn_two_layer_force():
    """模型 24 轮仍不【完】→ 第15场提醒、第22场建议收尾、第24场程序兜底收尾。"""
    llm = StreamLLM(*_scenes(24))
    engine = _engine(llm)
    completed = run_bond_story_vn(engine, input_fn=lambda p: "1", char_ms=0,
                                  remind_rounds=15, end_rounds=22)
    assert completed is True, "模型 24 轮不【完】→ 程序兜底应 completed=True"
    notes = llm.seen_notes
    assert len(notes) == 24, f"应跑满 24 场: {len(notes)}"
    assert all(not n for n in notes[:14]), "前 14 场不应注入注记"
    assert len(notes[14]) == 1 and "剩余约 7 轮" in notes[14][0], notes[14]
    assert all(not n for n in notes[15:21]), "16~21 场不应注入注记"
    assert len(notes[21]) == 1 and "已达剧情篇幅上限" in notes[21][0], notes[21]
    assert all(not n for n in notes[22:]), "23~24 场（硬兜底余量）不应注入注记"
    print("    双层兜底: 15场提醒/22场上限注记, 24场程序兜底 completed=True")


def test_run_vn_remind_then_natural_end():
    """模型 17 场自然【完】→ 只吃到 15 场提醒, 不走上限注记与硬兜底。"""
    llm = StreamLLM(*_scenes(16), "收尾了。\n\n【完】")
    engine = _engine(llm)
    completed = run_bond_story_vn(engine, input_fn=lambda p: "1", char_ms=0,
                                  remind_rounds=15, end_rounds=22)
    assert completed is True, "自然【完】应 completed=True"
    notes = llm.seen_notes
    assert len(notes) == 17, f"应跑 17 场: {len(notes)}"
    assert len(notes[14]) == 1 and "剩余约 7 轮" in notes[14][0], notes[14]
    assert all(not n for n in notes[:14] + notes[15:]), "只应在 15 场注入一次提醒"
    print("    双层兜底: 15场提醒后第17场自然【完】, 无上限注记/硬兜底")


# ----------------------------------------------------------------------------
# wrapup_after_vn: 剧情【完】后的手机收尾（agent_turn 走 ScriptedLLM.chat）
# ----------------------------------------------------------------------------

def test_wrapup_after_vn():
    import tempfile
    from pathlib import Path

    from core.bond_progress import BondProgress
    from core.ui.vn_cli import wrapup_after_vn

    trig = {"action": "mmt_trigger_bond_story", "payload": {"reason": "气氛到了"}}
    wrap = {"action": "mmt_chat",
            "reply": "今天去了天台……我很开心。下次再一起吧！", "payload": {}}

    with tempfile.TemporaryDirectory() as d:
        progress = BondProgress(Path(d) / "bp.json")
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


def main() -> None:
    print(f"VN CLI 单测（{CHARACTER} / StreamLLM + ScriptedLLM）")
    print("=" * 46)
    check("send_vn_scene 结构 + 历史", _t_send_vn_scene)
    check("simulate_vn_scene 选择/完", _t_simulate_vn_scene)
    check("run_vn 选项→推进→完", _t_run_vn_choice_flow)
    check("run_vn 自由输入推进", _t_run_vn_free_input)
    check("run_vn b 提前退出", _t_run_vn_early_exit)
    check("wrapup_after_vn 手机收尾", _t_wrapup_after_vn)
    print("=" * 46)
    if FAIL:
        print(f"结果: {PASS} PASS / {FAIL} FAIL")
        sys.exit(1)
    print(f"结果: {PASS} PASS / 0 FAIL — 全部通过")


if __name__ == "__main__":
    main()
