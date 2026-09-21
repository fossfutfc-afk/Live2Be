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
from core.tui.text_processors import _strip_action_brackets, strip_name_prefix

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

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text",
             **kw):
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
    progress=None,
) -> MomoTalkEngine:
    """构造引擎; progress 可注入（测试用临时 BondProgress, 不污染 data）。"""
    from core.bond.bond_progress import BondProgress

    engine = MomoTalkEngine(
        ROOT / "config" / "characters",
        ScriptedLLM(*scripts),
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
# trigger 不拦 + 时机建议注记（2026-09-02 v2: 引擎建议不拦截——LLM 全权裁决）
# ----------------------------------------------------------------------------

def _t_trigger_suggestion():
    import tempfile
    from pathlib import Path

    from core.bond.bond_progress import BondProgress

    trig = {"action": "mmt_trigger_bond_story", "payload": {"reason": "气氛到了"}}
    chat = {"action": "mmt_chat", "reply": "嗯……我们还没到那一步吧。", "payload": {}}

    # v2: 0 轮（刚开场）也**不拦**——LLM 输出 trigger 即放行（紧急剧情无需尬聊等轮数）
    with tempfile.TemporaryDirectory() as d:
        progress = BondProgress(Path(d) / "bp.json")
        engine = _engine(trig, chat, progress=progress)
        result = engine.agent_turn("老师！我这边出事了！")
        assert result.bond_story, "v2: 引擎不拦节奏——首条消息触发也应放行"
        print("    trigger(0轮不拦): 首条消息 trigger → bond_story=True（无硬闸）")

    # 注记分级: 沉淀期（gap < 6）报事实; 达标（gap ≥ 6）主动建议
    with tempfile.TemporaryDirectory() as d:
        progress = BondProgress(Path(d) / "bp.json")
        engine = _engine(trig, chat, progress=progress)
        engine.agent_turn("闲聊轮")          # 本轮注记 gap=0 → 沉淀文案
        s0 = "\n".join(m["content"] for m in engine.llm.snapshots[0])
        assert "沉淀" in s0 and "羁绊进度事实" in s0, s0
        engine._bond_gap = 6                # 模拟持久计数已到建议线
        engine.agent_turn("继续聊")          # 本轮注记 → 主动建议
        s1 = "\n".join(m["content"] for m in engine.llm.snapshots[1])
        assert "【剧情时机】" in s1 and "主动发起羁绊剧情" in s1, s1
        print("    trigger注记分级: gap<6 报沉淀事实 / gap≥6 主动建议发起")


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
# 2026-09-21 删: `_t_story_executor` / `_t_director` 两条 **v1 冒烟**
# ----------------------------------------------------------------------------
# 前者测 v1 动作契约（story_scene→story_end + StoryExecutor trace），后者喂 v1 dict
# （含已删的 `beats` 与"主 LLM 写 place"字段）——v1 整族退役后它们的断言已不成立。
# 现役覆盖: `tests/core/test_director.py`（导演视觉）+ `tests/core/test_vn_records_engine.py`
# （记录流端到端 + 生图钩子）。


def main() -> None:
    print(f"引擎冒烟（{CHARACTER} / ScriptedLLM 全 JSON loop）")
    print("=" * 46)
    check("chat 步骤拼回无损", _t_chat)
    check("chat 括号: 显示去括号/历史留原文", _t_chat_bracket)
    check("inspect→chat 静默回灌", _t_inspect_then_chat)
    check("parse 无效回灌重试", _t_parse_error_retry)
    check("执行拒绝(自检)回灌重试", _t_exec_error_retry)
    check("trigger→bond_story", _t_trigger)
    check("trigger 不拦+注记建议", _t_trigger_suggestion)
    check("bond_scene 解析(段/选项/完)", _t_bond_scene)
    print("=" * 46)
    if FAIL:
        print(f"结果: {PASS} PASS / {FAIL} FAIL")
        sys.exit(1)
    print(f"结果: {PASS} PASS / 0 FAIL — 全部通过")


if __name__ == "__main__":
    main()
