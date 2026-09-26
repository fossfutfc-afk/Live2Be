# -*- coding: utf-8 -*-
"""MMT 轮协议单测（**⑥-2e 起 = 行流**：一行一条 JSON，取代 2026-09-02 的 messages 消息流）。

核心行为:
    1. 纯说话轮 → 一行消息行 → 隐含 mmt_chat 走原管线
    2. 交错节奏: 话 → 发图 → 话（行序即事件序）
    3. 空轮 / 坏行 → 形状级重发 / 丢行记账（旧协议的"整轮回灌"已换成 §4 的分级）
    4. trigger 独占操作行（见面的话可前置）; inspect 单独一轮
    5. **旧形状（`{"messages": […]}` / `{"reply","actions"}`）必须被拒**
    6. registry 动作集收敛（3 真操作, 外壳 {action, payload}）

设计: `docs/DESIGN_STREAM_CONTRACT.md` §1/§2/§4。引擎侧接线细节另见
`tests/core/test_mmt_lines_protocol.py`。
"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.mmt.engine import SHAPE_RETRY_MAX, MmtLoopError, MomoTalkEngine
from llm import task_labels as T
from tests import stub_tasks

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"
#: ⚠️ 进度落盘走**临时目录**——`BondProgress` 的 data_root 指到真机 `data/` 会把
#: `data/basic/bond_progress.json` 里真实角色的累计轮数刷上去（2026-09-26 实测刷到 50）。
_PROGRESS_ROOT = Path(tempfile.mkdtemp(prefix="mmt_proto_progress_"))


class ScriptedLLM:
    """主链按脚本回**裸文本**（行协议）。"""

    def __init__(self, *scripts):
        self._scripts = list(scripts)
        self.snapshots = []

    def chat(self, messages, **kw):
        task = kw.get("task")
        self.snapshots.append([dict(m) for m in messages])
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:                    # digest 两轮 → 空包
            return reply
        if task in T.MAIN:
            if not self._scripts:
                raise RuntimeError("脚本耗尽")
            return self._scripts.pop(0)
        raise stub_tasks.unknown_task(task)

    def format_messages(self, **kw):
        return []


def _engine(llm, store=None):
    from core.bond.bond_progress import BondProgress
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm,
                            bond_progress=BondProgress(data_root=_PROGRESS_ROOT),
                            store=store)
    engine.start_session(CHARACTER)
    return engine


def test_pure_text_round():
    """纯说话轮: 一行消息行 → 隐含 mmt_chat（历史格式 [mmt_chat] 不变）。"""
    llm = ScriptedLLM('{"text": "嗯……我、我其实很开心的！"}')
    engine = _engine(llm)
    r = engine.agent_turn("你好呀")
    assert r.ok and r.action == "mmt_chat"
    assert "很开心" in r.reply
    assert engine.history[-1]["content"].startswith("[mmt_chat]")
    print("    pure text 轮: 一行消息行 → 隐含 mmt_chat, 历史格式不变")


def test_interleaved_rhythm():
    """交错节奏: 行序 = 事件序（mmt_chat, mmt_send_media, mmt_chat）。"""
    llm = ScriptedLLM(
        '{"text": "老师你看这个！"}\n'
        '{"action": "mmt_send_media", "payload": {"media_type": "image", "image": "天台夕阳"}}\n'
        '{"text": "是我特意拍的…好看吧？"}')
    engine = _engine(llm)
    r = engine.agent_turn("看看")
    assert r.ok
    assert [a["action"] for a in r.actions] == \
        ["mmt_chat", "mmt_send_media", "mmt_chat"], [a["action"] for a in r.actions]
    print("    交错节奏: 话→图→话 按序交付（行序即事件流顺序）")


def test_empty_and_bad_line():
    """空轮 → 形状级重发（回灌话术点明"一行一条 JSON"）→ 修正成功。"""
    llm = ScriptedLLM("", '{"text": "刚才卡了一下……老师你说什么？"}')
    engine = _engine(llm)
    r = engine.agent_turn("在吗")
    assert r.ok and "刚才卡了一下" in r.reply
    fed = "\n".join(m["content"] for m in llm.snapshots[1])
    assert "一行一条 JSON" in fed, fed
    # 坏行（既无 text 也无 action）只丢自己 → 其余行照常（1 次调用, 不重发）
    llm2 = ScriptedLLM('{"foo": 1}\n{"text": "抱歉刚才消息发坏了"}')
    engine2 = _engine(llm2)
    r2 = engine2.agent_turn("嗯?")
    assert r2.ok and "发坏了" in r2.reply and len(llm2.snapshots) == 1
    print("    empty/bad line: 空轮 → 形状级重发; 坏行 → 丢行（不重发）")


def test_trigger_text_before_action():
    """trigger 行 + 前置消息行 → 放行切剧情; trigger 与其他操作行混排 → 回灌修正。"""
    llm = ScriptedLLM(
        '{"text": "我们当面说吧！"}\n'
        '{"action": "mmt_trigger_bond_story", "payload": {"chapter_title": "当面说清楚"}}')
    engine = _engine(llm)
    r = engine.agent_turn("好啊")
    assert r.bond_story, r
    assert "当面说吧" in r.reply
    # 混排两个操作行 → 独占违规 → 行级续写（只补控制行）
    llm2 = ScriptedLLM(
        '{"action": "mmt_send_media", "payload": {"image": "x"}}\n'
        '{"action": "mmt_trigger_bond_story", "payload": {"chapter_title": "雨中的秘密基地"}}',
        '{"text": "那个……刚才我发错了"}')
    engine2 = _engine(llm2)
    r2 = engine2.agent_turn("嗨")
    assert not r2.bond_story and r2.ok
    assert "发错了" in r2.reply
    assert "唯一操作行" in "\n".join(m["content"] for m in llm2.snapshots[1])
    print("    trigger: 消息行前置放行; 与其他操作行混排 → 回灌（唯一操作行）")


def test_inspect_alone():
    """inspect 单独一轮（静默）: 执行 → **资料回灌** → 继续说话; 混排 → 回灌修正。"""
    insp = '{"action": "mmt_inspect_character", "payload": {"character_id": "rikuhachima_aru"}}'
    llm = ScriptedLLM(insp, '{"text": "阿露她啊，是便利屋68的社长。"}')
    engine = _engine(llm)
    r = engine.agent_turn("她是个什么样的人")
    assert r.ok and r.reply == "阿露她啊，是便利屋68的社长。"
    fed = llm.snapshots[1][-1]
    assert fed["role"] == "user" and fed["content"].startswith("[已查阅 rikuhachima_aru")
    # 混排消息行 → 独占违规 → 行级续写
    llm2 = ScriptedLLM('{"text": "问问看"}\n' + insp, '{"text": "啊……还是算了"}')
    engine2 = _engine(llm2)
    r2 = engine2.agent_turn("在吗")
    assert r2.ok and r2.reply == "啊……还是算了"
    assert "静默推理轮" in "\n".join(m["content"] for m in llm2.snapshots[1])
    print("    inspect: 单独一轮合法（资料回灌后继续）; 混排 → 回灌")


def test_legacy_shape_rejected():
    """⭐ 旧形状必须被拒：`{"messages": […]}` / `{"reply","actions"}` 都不是行流。

    （⑥-2f 会把这些形状的**代码分支**整段删掉；本用例先钉住"喂旧形状 = 形状级失败"。）
    """
    for legacy in ('{"messages": [{"text": "旧协议的一句话"}]}',
                   '{"reply": "旧协议的一句话", "actions": []}'):
        llm = ScriptedLLM(*([legacy] * (1 + SHAPE_RETRY_MAX)))
        engine = _engine(llm)
        with pytest.raises(MmtLoopError):
            engine.agent_turn("看看")
    print("    legacy: 旧形状 → 形状级重发耗尽 → 拒（不再兼容）")


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
