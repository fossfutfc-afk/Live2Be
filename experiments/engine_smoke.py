# -*- coding: utf-8 -*-
"""引擎冒烟 — 验证全 JSON 动作 loop 的五条输出路径。

chat   : agent_turn(chat 动作)   → …打字指示 + 气泡, 拼回不丢字
inspect: inspect(静默) → 结果回灌 → chat(可见) → 历史只记可见输出
纠错   : parse 无效 / 执行拒绝（自检）→ feedback 回灌 → LLM 修正重试
trigger: trigger 成功 → bond_story=True → 历史记动作名
history: resume_session 回放 + 继续对话不丢历史

用 ScriptedLLM（不碰 API）按调用顺序喂预设动作 dict，断言回灌内容。
用法: python experiments/engine_smoke.py   （需项目根环境, 推荐 live2be env）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.momotalk import MomoTalkEngine
from core.ui.text_processors import _strip_action_brackets, strip_name_prefix

ROOT = Path(__file__).resolve().parent.parent
CHARACTER = "igusa_haruka"
INSPECT_TARGET = "rikuhachima_aru"   # interperson: igusa_haruka→aru 权重 2 → inspect 可成功

# 含连续标点 + 动作括号的高危文本（回归: 修前会丢 "！" 或全标点段）
REPLY = "（轻笑）今天天气真不错呢！！我们一起去天台吧？？"

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
# ScriptedLLM — 按调用顺序返回预设动作 dict, 记录每次调用的 messages 快照
# ----------------------------------------------------------------------------

class ScriptedLLM:
    """脚本化 LLMClient 兼容面: chat(json_object) 依次返回预设动作 dict。

    snapshots[i] = 第 i 次调用时的 messages 副本（含 system + 历史 + 回灌修正）,
    供断言"回灌内容确实送回了 LLM"。
    """

    def __init__(self, *scripts):
        self._scripts = list(scripts)
        self.snapshots: list[list[dict]] = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text"):
        self.snapshots.append([dict(m) for m in messages])
        if not self._scripts:
            raise RuntimeError("ScriptedLLM 脚本耗尽: 预设回复已用完")
        return self._scripts.pop(0)

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


def _engine(
    *scripts: dict,
    threshold: int = 0,
    progress=None,
) -> MomoTalkEngine:
    """构造引擎。默认 threshold=0（不加门槛, 保现有用例语义）;
    progress 可注入（门槛测试用临时 BondProgress, 不污染 data/basic/）。"""
    from core.bond.bond_progress import BondProgress

    engine = MomoTalkEngine(
        ROOT / "config" / "characters",
        ScriptedLLM(*scripts),
        affection_threshold=threshold,
        bond_progress=progress or BondProgress(),
    )
    engine.start_session(CHARACTER)
    return engine


CHAT = {"action": "mmt_chat", "reply": "今天天气真不错呢！！我们一起去天台吧？？", "payload": {}}
CHAT_BRACKET = {"action": "mmt_chat", "reply": REPLY, "payload": {}}


# ----------------------------------------------------------------------------
# chat: 一次 mmt_chat 动作 → 步骤拼回不丢字 + 历史记动作名
# ----------------------------------------------------------------------------

def _t_chat():
    engine = _engine(CHAT)
    result = engine.agent_turn("我们去天台吧？")
    assert result.ok and result.action == "mmt_chat" and not result.bond_story
    name = engine.current_character.display_name
    joined = "".join(strip_name_prefix(s.text, name) for s in result.steps if not s.typing)
    assert joined == result.reply, f"显示丢字: {joined!r} != {result.reply!r}"
    h = engine.history
    assert len(h) == 2, f"历史条数 {len(h)}"
    assert h[1]["content"] == f"[mmt_chat] {result.reply}"
    print(f"    chat: {result.reply!r} → {len(result.steps)} 步骤")


# ----------------------------------------------------------------------------
# chat + 动作括号: 显示剥离括号, 历史保留原文（宁缺勿错, 不丢舞台指示）
# ----------------------------------------------------------------------------

def _t_chat_bracket():
    engine = _engine(CHAT_BRACKET)
    result = engine.agent_turn("我们去天台吧？")
    name = engine.current_character.display_name
    shown = "".join(strip_name_prefix(s.text, name) for s in result.steps if not s.typing)
    assert shown == _strip_action_brackets(result.reply), f"括号剥离不符: {shown!r}"
    assert "轻笑" not in shown, "显示不应含动作括号内容"
    assert "轻笑" in engine.history[1]["content"], "历史应保留原文舞台指示"
    print(f"    chat_bracket: 显示去括号, 历史留原文 → {shown!r}")


# ----------------------------------------------------------------------------
# inspect → chat: inspect 静默成功, 结果回灌 LLM, 历史只记可见输出
# ----------------------------------------------------------------------------

def _t_inspect_then_chat():
    inspect = {"action": "mmt_inspect_character", "payload": {"character_id": INSPECT_TARGET}}
    engine = _engine(inspect, CHAT)
    result = engine.agent_turn("那个便利屋68的社长是个什么样的角色？")
    assert result.action == "mmt_chat"
    trace = engine.trace
    assert len(trace) == 2, f"轨迹应含 inspect + chat 两步: {trace}"
    assert trace[0]["action"] == "mmt_inspect_character"
    assert trace[1]["action"] == "mmt_chat"
    # inspect 结果回灌到了 LLM（第二次调用的最后一条 user）
    fed = engine.llm.snapshots[1][-1]["content"]
    assert fed.startswith(f"[已查阅 {INSPECT_TARGET} 资料"), f"回灌内容不符: {fed[:60]!r}"
    # 历史只有用户可见输出（inspect 静默不入历史）
    h = engine.history
    assert len(h) == 2 and h[1]["content"].startswith("[mmt_chat]")
    print(f"    inspect→chat: 轨迹 2 步, 回灌 {len(fed)} 字符, 历史仅可见输出")


# ----------------------------------------------------------------------------
# parse 无效: feedback 回灌 → LLM 修正重试
# ----------------------------------------------------------------------------

def _t_parse_error_retry():
    bad = {"action": "mmt_teleport", "payload": {}}
    engine = _engine(bad, CHAT)
    result = engine.agent_turn("我们去天台吧？")
    assert result.action == "mmt_chat"
    fed = engine.llm.snapshots[1][-1]["content"]
    assert "动作无效" in fed and "未知动作" in fed, f"回灌不符: {fed!r}"
    print(f"    parse_error: 回灌 {len(fed)} 字符 → LLM 修正重试成功")


# ----------------------------------------------------------------------------
# 执行拒绝（自检守卫）: MmtExecError 回灌 → LLM 修正重试
# ----------------------------------------------------------------------------

def _t_exec_error_retry():
    self_inspect = {"action": "mmt_inspect_character", "payload": {"character_id": CHARACTER}}
    engine = _engine(self_inspect, CHAT)
    result = engine.agent_turn("我是什么样的人？")
    assert result.action == "mmt_chat"
    fed = engine.llm.snapshots[1][-1]["content"]
    assert "不要查自己" in fed, f"自检回灌不符: {fed!r}"
    print(f"    exec_error(自检): 回灌 {len(fed)} 字符 → LLM 修正重试成功")


# ----------------------------------------------------------------------------
# trigger: 成功 → bond_story=True → 历史记动作名
# ----------------------------------------------------------------------------

def _t_trigger():
    trig = {"action": "mmt_trigger_bond_story", "payload": {"reason": "气氛到了"},
            "reply": "遥香有件事想和你说……"}
    engine = _engine(trig)
    result = engine.agent_turn("我们今天做了好多事啊")
    assert result.bond_story, "trigger 成功应置 bond_story=True"
    assert result.action == "mmt_trigger_bond_story"
    h = engine.history
    assert h[1]["content"].startswith("[mmt_trigger_bond_story]"), h[1]["content"]
    print(f"    trigger: bond_story=True → {h[1]['content']!r}")


# ----------------------------------------------------------------------------
# trigger 门槛: 轮数 < threshold → MmtExecError 回灌含「轮」; 达标 → 触发成功
# ----------------------------------------------------------------------------

def _t_trigger_threshold():
    import tempfile
    from pathlib import Path

    from core.bond.bond_progress import BondProgress

    trig = {"action": "mmt_trigger_bond_story", "payload": {"reason": "气氛到了"}}
    chat = {"action": "mmt_chat", "reply": "嗯……我们还没到那一步吧。", "payload": {}}

    # 软门槛·兜底: 门槛开启且首条消息（0 轮）→ 程序兜底拒绝 → 回灌 → LLM 转普通聊天
    with tempfile.TemporaryDirectory() as d:
        progress = BondProgress(Path(d) / "bp.json")
        engine = _engine(trig, chat, threshold=5, progress=progress)
        result = engine.agent_turn("今天我们聊了很多")
        assert result.action == "mmt_chat", f"首条消息不应触发: {result.action}"
        assert not result.bond_story
        fed = engine.llm.snapshots[1][-1]["content"]
        assert "轮" in fed, f"兜底回灌应含「轮」: {fed!r}"
        # 轮数参考注记已注入 LLM context（软门槛的依据）
        assert any("羁绊进度参考" in m["content"] for m in engine.llm.snapshots[0]), \
            "应注入羁绊进度参考注记"
        print(f"    trigger_threshold(兜底): 0 轮 → 回灌 {len(fed)} 字符 → 转普通聊天")

    # 软门槛·提前: 轮数 2 < 5, 但 AI 裁决剧情需要 → 允许提前触发
    with tempfile.TemporaryDirectory() as d:
        progress = BondProgress(Path(d) / "bp.json")
        for _ in range(2):
            progress.record_turn(CHARACTER)
        engine = _engine(trig, threshold=5, progress=progress)
        result = engine.agent_turn("（触发尝试，气氛已到）")
        assert result.bond_story, "软门槛: 轮数不足但 AI 裁决 → 应触发成功"
        print("    trigger_threshold(提前): 轮数 2 < 5 → AI 裁决触发成功")

    # 达标: 轮数 5 ≥ 门槛 5 → 触发成功
    with tempfile.TemporaryDirectory() as d:
        progress = BondProgress(Path(d) / "bp.json")
        for _ in range(5):
            progress.record_turn(CHARACTER)
        engine = _engine(trig, threshold=5, progress=progress)
        result = engine.agent_turn("现在我们够熟了吧")
        assert result.bond_story, "轮数达标应触发成功"
        print("    trigger_threshold(达标): 轮数 5 ≥ 5 → bond_story=True")


# ----------------------------------------------------------------------------
# bond_scene: BondScene.to_dict/from_dict 往返 — 段落 / 选项 / is_end 结构
# ----------------------------------------------------------------------------

def _t_bond_scene():
    from core.bond.bond_story import BondScene

    scene = BondScene.from_dict({
        "paragraphs": ["遥香坐在天台边缘……", "（她微微一笑，靠在你肩上）"],
        "choices": ["陪她坐一会儿", "问她怎么了"],
        "is_end": True,
    })
    assert len(scene.paragraphs) == 2, f"段落数 {len(scene.paragraphs)}"
    assert scene.choices == ["陪她坐一会儿", "问她怎么了"], scene.choices
    assert scene.is_end
    back = BondScene.from_dict(scene.to_dict())
    assert back == scene, "to_dict/from_dict 往返应相等"
    print(f"    bond_scene: {len(scene.paragraphs)} 段 + {len(scene.choices)} 选项 + is_end")

    # 宽松容错: 缺字段 / 混入非 str / 无 is_end → 降级不 raise
    plain = BondScene.from_dict({"paragraphs": ["她静静地看着你。"]})
    assert plain.paragraphs == ["她静静地看着你。"]
    assert not plain.choices and not plain.is_end
    robust = BondScene.from_dict({"paragraphs": ["好", 42, None], "choices": ["A", 1]})
    assert robust.paragraphs == ["好"] and robust.choices == ["A"], robust
    empty = BondScene.from_dict(None)
    assert not empty.paragraphs and not empty.is_end
    print("    bond_scene: 纯段落场景 + 坏数据降级（宁缺勿错）")


# ----------------------------------------------------------------------------
# story_executor: 双动作 story_scene→story_end, is_end 动作推导 + 引擎 trace
# ----------------------------------------------------------------------------

def _t_story_executor():
    from core.bond.bond_story import BondStoryEngine
    from core.bond.bond_executor import StoryExecutor

    scene = {"action": "story_scene", "payload": {
        "paragraphs": ["遥香坐在天台边缘……"],
        "choices": ["陪她坐一会儿", "问她怎么了"]}}
    end = {"action": "story_end", "payload": {
        "paragraphs": ["她笑了，靠在你肩上。今晚，谢谢你。"]}}
    vn = BondStoryEngine(ROOT / "config" / "characters", ScriptedLLM(scene, end))
    vn.start_session(CHARACTER)
    assert isinstance(vn.executor, StoryExecutor), "引擎应持有 StoryExecutor（双核）"

    s1 = vn.send_vn_scene("（开场）")
    assert not s1.is_end and s1.choices == ["陪她坐一会儿", "问她怎么了"], s1
    assert vn.trace[-1]["action"] == "story_scene" and vn.trace[-1]["exec_ok"] is True

    s2 = vn.send_vn_scene("陪她坐一会儿")
    assert s2.is_end, "story_end 动作应推导 is_end=True"
    assert not s2.choices and s2.paragraphs == ["她笑了，靠在你肩上。今晚，谢谢你。"]
    t = vn.trace
    assert t[-1]["action"] == "story_end"
    assert t[-1]["exec_message"] == "收尾场景已就绪, 剧情将结束"
    print("    story_executor: story_scene→story_end, is_end 推导 + trace 2 场")


# ----------------------------------------------------------------------------
# director: 导演组件 → BondScene 视觉字段 + 历史不含（不污染主 LLM 契约）
# ----------------------------------------------------------------------------

def _t_director():
    import json as _json

    from core.bond.bond_story import BondStoryEngine
    from core.director import Director, DirectorSuggestion
    from core.media import MediaCatalog

    class DirStub:
        def __init__(self):
            self.prompts: list[str] = []

        def suggest(self, prompt):
            self.prompts.append(prompt)
            return DirectorSuggestion(sprite="embarass", background="class_room")

    scene = {"action": "story_scene", "payload": {
        "paragraphs": ["她脸红了，低下头。"], "choices": []}}
    director = Director(
        MediaCatalog(), CHARACTER,
        persona="角色概要: 自卑敏感", rules="RULES",
        llm=DirStub(), common={"scenes": ["class_room"], "dirs": []})
    vn = BondStoryEngine(
        ROOT / "config" / "characters", ScriptedLLM(scene), director=director)
    vn.start_session(CHARACTER)
    s = vn.send_vn_scene("（开场）")
    assert s.sprite == "embarass" and s.background == "class_room", s
    assert "sprite" not in _json.loads(vn.history[-1]["content"]), "历史应无视觉字段"
    print(f"    director: sprite={s.sprite} background={s.background} 历史不含视觉字段")

    # 纯文本模式（无导演注入）
    vn2 = BondStoryEngine(ROOT / "config" / "characters", ScriptedLLM(scene))
    vn2.start_session(CHARACTER)
    s2 = vn2.send_vn_scene("（开场）")
    assert s2.sprite is None and s2.background is None
    print("    director: 无导演 → 纯文本, 无视觉字段")


# ----------------------------------------------------------------------------
# history: resume_session 回放 + 继续对话不丢历史
# ----------------------------------------------------------------------------

def _t_history():
    from core.momotalk import Session

    session = Session(
        character_id=CHARACTER,
        character_name="测试",
        history=[
            {"role": "user", "content": "之前说的"},
            {"role": "assistant", "content": "[mmt_chat] 好呀！"},
        ],
    )
    path = ROOT / "data" / "sessions" / "_smoke_session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    session.to_json(path)
    try:
        engine = MomoTalkEngine(ROOT / "config" / "characters", ScriptedLLM(CHAT))
        restored = engine.resume_session(path)
        assert len(restored.history) == 2, f"历史条数 {len(restored.history)}"
        assert engine.history_length == 2
        # 恢复后继续对话, 历史前缀仍在（不会因 loop 丢消息）
        result = engine.agent_turn("继续说")
        assert result.action == "mmt_chat"
        assert engine.history_length == 4, f"继续对话后历史 {engine.history_length}"
        assert "之前说的" in engine.history[0]["content"]
        assert engine.history[2]["content"] == "继续说"
        print(f"    history: 恢复 2 条 → 续聊 {engine.history_length} 条")
    finally:
        path.unlink(missing_ok=True)


def main() -> None:
    print(f"引擎冒烟（{CHARACTER} / ScriptedLLM 全 JSON loop）")
    print("=" * 46)
    check("chat 步骤拼回无损", _t_chat)
    check("chat 括号: 显示去括号/历史留原文", _t_chat_bracket)
    check("inspect→chat 静默回灌", _t_inspect_then_chat)
    check("parse 无效回灌重试", _t_parse_error_retry)
    check("执行拒绝(自检)回灌重试", _t_exec_error_retry)
    check("trigger→bond_story", _t_trigger)
    check("trigger 轮数门槛(拒/过)", _t_trigger_threshold)
    check("bond_scene 解析(段/选项/完)", _t_bond_scene)
    check("story 双动作 scene→end 推导+trace", _t_story_executor)
    check("导演组件 BondScene 视觉字段", _t_director)
    check("history 恢复 + 续聊无损", _t_history)
    print("=" * 46)
    if FAIL:
        print(f"结果: {PASS} PASS / {FAIL} FAIL")
        sys.exit(1)
    print(f"结果: {PASS} PASS / 0 FAIL — 全部通过")


if __name__ == "__main__":
    main()
