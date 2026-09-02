# -*- coding: utf-8 -*-
"""MMT 轮级协议单测（2026-09-02 定稿: 说话 = 默认产物, 动作只放真操作）。

核心行为:
    1. 纯说话轮 {"reply": "…"}（无 actions）→ 隐含 mmt_chat 走原管线
    2. 空轮（无 reply 无 actions）→ feedback 整轮重试
    3. trigger 新格式: {"reply": 邀约话, "actions": [trigger]} 独占放行
    4. 旧输出兼容: actions 里混 mmt_chat / 动作带 reply → 并入轮级 reply
    5. registry 动作集收敛（不含 mmt_chat, 外壳 {action, payload}）
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


def test_pure_reply_round():
    """纯说话轮: 无 actions → reply 包装成隐含 mmt_chat（事件流/历史格式不变）。"""
    llm = ScriptedLLM({"reply": "嗯……我、我其实很开心的！"})
    engine = _engine(llm)
    r = engine.agent_turn("你好呀")
    assert r.ok and r.action == "mmt_chat"
    assert "很开心" in r.reply
    assert r.steps and any("很开心" in s.text for s in r.steps)
    # 历史: [mmt_chat] 前缀（隐含动作, 渲染零改动）
    assert engine.history[-1]["content"].startswith("[mmt_chat]")
    print("    pure reply 轮: 无 actions → 隐含 mmt_chat, 历史/渲染格式不变")


def test_empty_round_feedback_retry():
    """空轮（无 reply 无 actions）→ feedback → LLM 修正后成功。"""
    llm = ScriptedLLM({}, {"reply": "刚才卡了一下……老师你说什么？"})
    engine = _engine(llm)
    r = engine.agent_turn("在吗")
    assert r.ok and "刚才卡了一下" in r.reply
    # feedback 说明了轮级协议（reply/actions 用法）
    all_text = "\n".join(m["content"] for m in llm.snapshots[1])
    assert "reply" in all_text and "actions" in all_text, all_text
    print("    empty round: {} → feedback（协议说明）→ LLM 修正成功")


def test_trigger_new_format_exclusive():
    """trigger 新格式: reply 邀约话 + actions 独占 trigger → 放行切剧情。"""
    trig = {"reply": "我们当面说吧！",
            "actions": [{"action": "mmt_trigger_bond_story",
                         "payload": {"reason": "邀约"}}]}
    llm = ScriptedLLM(trig)
    engine = _engine(llm)
    engine.executor.set_session_rounds(6)            # 门槛 6 放行
    r = engine.agent_turn("好啊")
    assert r.bond_story, r
    assert "当面说吧" in r.reply
    print("    trigger 新格式: reply 邀约话 + actions 独占 → bond_story=True")


def test_legacy_mmt_chat_merged():
    """旧输出兼容: actions 里混 mmt_chat ×2 → 并入轮级 reply（消息不丢）。"""
    llm = ScriptedLLM({"actions": [
        {"action": "mmt_chat", "reply": "第一句", "payload": {}},
        {"action": "mmt_send_media", "reply": "配图的话",
         "payload": {"media_type": "image", "image": "天台"}},
        {"action": "mmt_chat", "reply": "第三句", "payload": {}},
    ]})
    engine = _engine(llm)
    r = engine.agent_turn("看看")
    assert r.ok
    assert "第一句" in r.reply and "配图的话" in r.reply and "第三句" in r.reply
    print("    legacy 兼容: mmt_chat/动作 reply 并入轮级 reply, 消息不丢")


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
    for fn in (test_pure_reply_round, test_empty_round_feedback_retry,
               test_trigger_new_format_exclusive, test_legacy_mmt_chat_merged,
               test_registry_actionset_shrunk):
        fn()
    print("MMT 轮级协议: 全部通过")
