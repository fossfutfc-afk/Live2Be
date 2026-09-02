# -*- coding: utf-8 -*-
"""MMT 消息流协议单测（2026-09-02 定稿: 聊天 = 消息序列, text 单元说话）。

核心行为:
    1. 纯说话轮 {"messages": [{"text": "…"}]} → 隐含 mmt_chat 走原管线
    2. 交错节奏: 话 → 发图 → 话（微信式, 旧协议表达不了的顺序）
    3. 空轮 / 坏单元 → feedback 整轮重试
    4. trigger 单元独占操作（text 邀约话可前置）; inspect 单独一轮
    5. 旧协议兼容: reply / actions / mmt_chat 动作 / 动作内 reply → 归一
    6. registry 动作集收敛（3 真操作, 外壳 {action, payload}）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.momotalk import MomoTalkEngine

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"


class ScriptedLLM:
    def __init__(self, *scripts):
        self._scripts = list(scripts)
        self.snapshots = []

    def chat(self, messages, **kw):
        self.snapshots.append([dict(m) for m in messages])
        head = messages[0]["content"]
        if "记录员" in head or "整理者" in head:
            return {"episodes": []} if "记录员" in head \
                else {"decisions": [], "evidence": [], "affection_exp_delta": 0}
        if not self._scripts:
            raise RuntimeError("脚本耗尽")
        return self._scripts.pop(0)

    def format_messages(self, **kw):
        return []


def _engine(llm, store=None):
    from core.bond.bond_progress import BondProgress
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm,
                            bond_progress=BondProgress(data_root=ROOT / "data"),
                            store=store)
    engine.start_session(CHARACTER)
    return engine


def test_pure_text_round():
    """纯说话轮: 单个 text 单元 → 隐含 mmt_chat（历史格式 [mmt_chat] 不变）。"""
    llm = ScriptedLLM({"messages": [{"text": "嗯……我、我其实很开心的！"}]})
    engine = _engine(llm)
    r = engine.agent_turn("你好呀")
    assert r.ok and r.action == "mmt_chat"
    assert "很开心" in r.reply
    assert engine.history[-1]["content"].startswith("[mmt_chat]")
    print("    pure text 轮: text 单元 → 隐含 mmt_chat, 历史格式不变")


def test_interleaved_rhythm():
    """交错节奏（回归: 旧协议"说话→发图→说话"的能力）: text/action 按序执行,
    事件流顺序 = 消息顺序（mmt_chat, send_media, mmt_chat）。"""
    from core.session import SessionStore
    llm = ScriptedLLM({"messages": [
        {"text": "老师你看这个！"},
        {"action": "mmt_send_media",
         "payload": {"media_type": "image", "image": "天台夕阳"}},
        {"text": "是我特意拍的…好看吧？"},
    ]})
    st = SessionStore(ROOT / "data")
    engine = _engine(llm)
    r = engine.agent_turn("看看")
    assert r.ok
    assert [a["action"] for a in r.actions] == \
        ["mmt_chat", "mmt_send_media", "mmt_chat"], [a["action"] for a in r.actions]
    print("    交错节奏: 话→图→话 按序执行（消息流顺序即事件流顺序）")


def test_empty_and_bad_unit_feedback():
    """空轮 / 坏单元 → feedback 说明协议 → LLM 修正成功。"""
    llm = ScriptedLLM({"messages": []},
                      {"messages": [{"text": "刚才卡了一下……老师你说什么？"}]})
    engine = _engine(llm)
    r = engine.agent_turn("在吗")
    assert r.ok and "刚才卡了一下" in r.reply
    all_text = "\n".join(m["content"] for m in llm.snapshots[1])
    assert "messages" in all_text, all_text
    # 坏单元（既无 text 也无 action）→ feedback
    llm2 = ScriptedLLM({"messages": [{"foo": 1}]},
                       {"messages": [{"text": "抱歉刚才消息发坏了"}]})
    engine2 = _engine(llm2)
    r2 = engine2.agent_turn("嗯?")
    assert r2.ok and "发坏了" in r2.reply
    print("    empty/bad unit: feedback（协议说明）→ 修正成功")


def test_trigger_text_before_action():
    """trigger 单元 + 前置 text 邀约话 → 放行切剧情（v2: 无轮数硬闸, 即触即放）。"""
    trig = {"messages": [
        {"text": "我们当面说吧！"},
        {"action": "mmt_trigger_bond_story", "payload": {"reason": "邀约"}},
    ]}
    llm = ScriptedLLM(trig)
    engine = _engine(llm)
    r = engine.agent_turn("好啊")
    assert r.bond_story, r
    assert "当面说吧" in r.reply
    # trigger 与其他操作混排 → feedback → LLM 修正（纯 text 轮）
    llm2 = ScriptedLLM(
        {"messages": [
            {"action": "mmt_send_media", "payload": {"image": "x"}},
            {"action": "mmt_trigger_bond_story", "payload": {"reason": "r"}},
        ]},
        {"messages": [{"text": "那个……刚才我发错了"}]})
    engine2 = _engine(llm2)
    r2 = engine2.agent_turn("嗨")
    assert not r2.bond_story and r2.ok
    assert "发错了" in r2.reply
    print("    trigger: text 邀约话前置放行; 与其他 action 混排 → 拒 + 修正")


def test_inspect_alone():
    """inspect 单独一轮（静默）: 解析接受（引擎内查完回灌/返回）; 混排 → feedback。"""
    insp = {"action": "mmt_inspect_character", "payload": {"character_id": "rikuhachima_aru"}}
    llm = ScriptedLLM({"messages": [insp]})
    engine = _engine(llm)
    r = engine.agent_turn("她是个什么样的人")
    assert r.ok and r.action == "mmt_inspect_character"   # 静默轮: 无可见回复, 解析/执行接受
    # 混排 text → feedback → LLM 修正（纯 text 轮）
    llm2 = ScriptedLLM({"messages": [{"text": "问问看"}, insp]},
                       {"messages": [{"text": "啊……还是算了"}]})
    engine2 = _engine(llm2)
    r2 = engine2.agent_turn("在吗")
    assert r2.ok
    assert "静默" in "\n".join(m["content"] for m in llm2.snapshots[1])
    print("    inspect: 单独一轮合法（静默）; 混排 text → feedback + 修正")


def test_legacy_formats_merged():
    """旧协议兼容: reply/actions/mmt_chat 动作/动作内 reply → 归一消息单元。"""
    # 旧 reply+actions（含 mmt_chat 与动作内 reply）
    llm = ScriptedLLM({
        "reply": "开头一句",
        "actions": [
            {"action": "mmt_chat", "reply": "中间一句", "payload": {}},
            {"action": "mmt_send_media", "reply": "配图的话",
             "payload": {"media_type": "image", "image": "天台"}},
            {"action": "mmt_chat", "reply": "结尾一句", "payload": {}},
        ]})
    engine = _engine(llm)
    r = engine.agent_turn("看看")
    assert r.ok
    assert "开头一句" in r.reply and "中间一句" in r.reply and "配图的话" in r.reply \
        and "结尾一句" in r.reply
    print("    legacy 兼容: reply/mm_chat/动作内 reply → 归一消息单元, 消息不丢")


def test_registry_actionset_shrunk():
    """动作集收敛: registry 只含 3 个真操作（无 mmt_chat）; 外壳字段 {action, payload}。"""
    from core.mmt.mmt_actions import build_mmt_registry
    reg = build_mmt_registry()
    assert reg.action_names() == [
        "mmt_inspect_character", "mmt_send_media", "mmt_trigger_bond_story"], \
        reg.action_names()
    for name in reg.action_names():
        spec = reg.spec(name)
        assert spec.prompt_fields == frozenset({"action", "payload"}), name
    print("    registry: 3 动作（无 mmt_chat）, 外壳 {action, payload}")


if __name__ == "__main__":
    for fn in (test_pure_text_round, test_interleaved_rhythm,
               test_empty_and_bad_unit_feedback, test_trigger_text_before_action,
               test_inspect_alone, test_legacy_formats_merged,
               test_registry_actionset_shrunk):
        fn()
    print("MMT 消息流协议: 全部通过")
