# -*- coding: utf-8 -*-
"""MMT **行协议**接线（⑥-2d 接线 / ⑥-2f 起是唯一路径）。

契约: `docs/DESIGN_STREAM_CONTRACT.md` §3（内容行/控制行）/ §4（兜底分级 +
重试三段式）/ §10.3（三个注入点）。本文件钉新路径的行为：

    逐行交付      text 行 = 一个气泡；事件**行交付即 append**（C4）；历史一行一条
    丢行隔离      坏行只丢自己（软, 不触发回灌）
    独占+不回灌   inspect 混排 → **整轮不交付** + 行级续写（只补控制行）
    ⭐ B9        inspect 查到的资料**回灌**后继续这一轮（旧路径把它丢了）
    形状级预算    整段不是 JSONL → 整轮重发 ≤ SHAPE_RETRY_MAX 次 → 失败
    行级预算      修不了的操作行 → 续写 ≤ LINE_REASK_MAX 次 → 失败
    软丢行注记    send_media 修不了 ⇒ 丢行 + **下一轮**注记念一次（自清）
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.mmt.engine import (                                    # noqa: E402
    LINE_REASK_MAX,
    SHAPE_RETRY_MAX,
    MmtLoopError,
    MomoTalkEngine,
)
from core.session import SessionStore                            # noqa: E402
from llm import task_labels as T                                 # noqa: E402
from tests import stub_tasks                                     # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"


class ScriptedLLM:
    """主链按脚本回**裸文本**（行协议走 `response_format="text"`）。"""

    def __init__(self, *scripts):
        self._scripts = list(scripts)
        self.snapshots: list[list[dict]] = []
        self.kwargs: list[dict] = []

    def chat(self, messages, **kw):
        task = kw.get("task")
        self.snapshots.append([dict(m) for m in messages])
        self.kwargs.append(dict(kw))
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:                    # 标注/digest → 空包
            return reply
        if task in T.MAIN:
            if not self._scripts:
                raise RuntimeError("脚本耗尽")
            return self._scripts.pop(0)
        raise stub_tasks.unknown_task(task)

    def format_messages(self, **kw):
        return []


def _engine(llm, tmp_path):
    from core.bond.bond_progress import BondProgress
    st = SessionStore(tmp_path)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm,
                            bond_progress=BondProgress(data_root=tmp_path),
                            store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    return engine, st, root.session_id


def _last_user(llm, call: int) -> str:
    return llm.snapshots[call][-1]["content"]


def _joined(llm, call: int) -> str:
    return "\n".join(m.get("content") or "" for m in llm.snapshots[call])


# ---------------------------------------------------------------------------
# 逐行交付
# ---------------------------------------------------------------------------

def test_rows_delivered_in_order(tmp_path):
    """交错轮：话 → 图 → 话 —— 逐行交付、事件**行序**、历史一行一条。"""
    llm = ScriptedLLM(
        '{"text": "老师你看这个！"}\n'
        '{"action": "mmt_send_media", "payload": {"media_type": "image", "image": "天台夕阳"}}\n'
        '{"text": "是我特意拍的…好看吧？"}')
    engine, st, sid = _engine(llm, tmp_path)
    r = engine.agent_turn("看看")

    assert r.ok and llm.kwargs[0]["response_format"] == "text", "行协议必须走裸文本"
    assert [a["action"] for a in r.actions] == ["mmt_chat", "mmt_send_media", "mmt_chat"]
    assert r.reply == "老师你看这个！\n是我特意拍的…好看吧？"
    bubbles = [s.text for s in r.steps if not s.typing]
    assert len(bubbles) == 2, bubbles                    # ⭐ 一行一个气泡（不切句）
    assert "老师你看这个！" in bubbles[0] and "好看吧" in bubbles[1]
    assert r.action == "mmt_chat" and not r.bond_story

    # 事件：**行交付即 append**（C4），顺序 = 行序；首条带 player
    evs = [e for e in st.events(CHARACTER, sid) if e.type == "mmt"]
    assert [e.subtype for e in evs] == ["mmt_chat", "mmt_send_media", "mmt_chat"]
    assert evs[0].payload.get("player") == "看看"
    assert evs[0].payload.get("reply") == "老师你看这个！"
    assert evs[1].payload.get("image") == "天台夕阳" and not evs[1].payload.get("player")
    assert "reply" not in evs[1].payload or evs[1].payload["reply"] == ""

    # 历史：user + 一行一条
    assert engine.history[0] == {"role": "user", "content": "看看"}
    assert [h["content"].split("]")[0] + "]" for h in engine.history[1:]] == \
        ["[mmt_chat]", "[mmt_send_media]", "[mmt_chat]"]
    print("    rows: 逐行交付（气泡 2 / 事件 3 / 历史一行一条, 事件即落库）")


def test_bad_row_only_loses_itself(tmp_path):
    """坏行只丢自己（软）——其余行照常交付, **不触发回灌**（只 1 次 LLM 调用）。"""
    llm = ScriptedLLM('{"text": "好的"}\n'
                      '这不是 JSON\n'
                      '{"text": "那我先走啦"}')
    engine, _st, _sid = _engine(llm, tmp_path)
    r = engine.agent_turn("在吗")
    assert r.ok and r.reply == "好的\n那我先走啦"
    assert len(llm.snapshots) == 1, "软问题不该回灌"
    assert len(r.actions) == 2
    print("    rows: 坏行只丢自己（软, 零回灌）")


# ---------------------------------------------------------------------------
# 独占 + B9：inspect 回路
# ---------------------------------------------------------------------------

def test_inspect_mixed_is_not_delivered_and_loop_is_connected(tmp_path):
    """⭐ 混排 → 整轮**不交付** + 行级续写；查到的资料**回灌**后继续这一轮（AUDIT §B9）。"""
    insp = '{"action": "mmt_inspect_character", "payload": {"character_id": "rikuhachima_aru"}}'
    llm = ScriptedLLM(
        '{"text": "我想想…"}\n' + insp,      # ① 坏形状：话 + inspect 混排
        insp,                                 # ② 续写轮：只补那一条控制行
        '{"text": "阿露她啊，是个爱闹的人。"}')   # ③ 拿到资料后说话
    engine, st, sid = _engine(llm, tmp_path)
    r = engine.agent_turn("阿露是个什么样的人？")

    assert r.ok and r.reply == "阿露她啊，是个爱闹的人。"
    # ① 那一轮的话**没有**上屏（否则就是"没查到就先答"）
    assert "我想想" not in r.reply
    assert all("我想想" not in (h.get("content") or "") for h in engine.history)
    assert [e.subtype for e in st.events(CHARACTER, sid) if e.type == "mmt"] == ["mmt_chat"]
    # ② 那轮的回灌话术：只补缺失的控制行
    assert "只补" in _last_user(llm, 1) and "不要再重复" in _last_user(llm, 1)
    # ⭐ ③ inspect 的资料进了模型上下文（B9：旧路径把它丢了）
    fed = llm.snapshots[2][-1]
    assert fed["role"] == "user" and fed["content"].startswith("[已查阅 rikuhachima_aru")
    assert "访问层级" in fed["content"]
    print("    inspect: 混排不交付 + 只补控制行 + 资料回灌后继续说话（B9 已接上）")


def test_inspect_alone_still_works(tmp_path):
    """独占轮本身：只有 inspect 一条行 → 执行 → 回灌 → 下一轮说话。"""
    insp = '{"action": "mmt_inspect_character", "payload": {"character_id": "rikuhachima_aru"}}'
    llm = ScriptedLLM(insp, '{"text": "她是便利屋68的社长。"}')
    engine, _st, _sid = _engine(llm, tmp_path)
    r = engine.agent_turn("她是谁")
    assert r.ok and r.reply == "她是便利屋68的社长。"
    assert len(llm.snapshots) == 2
    print("    inspect: 独占轮 → 回灌 → 说话（两跳）")


def test_inspect_id_normalized_by_repair(tmp_path):
    """写歪的 id（中文名）→ 自愈归一后**照常执行**（不是回灌）。"""
    llm = ScriptedLLM(
        '{"action": "mmt_inspect_character", "payload": {"character_id": "睦月"}}',
        '{"text": "睦月啊，爱搞恶作剧的那个。"}')
    engine, _st, _sid = _engine(llm, tmp_path)
    r = engine.agent_turn("睦月是个什么样的人")
    assert r.ok and r.reply == "睦月啊，爱搞恶作剧的那个。"
    # 归一成真实 id 后执行器认得（否则"角色不存在"→ 回灌）
    assert "asagi_mutsuki" in _last_user(llm, 1), _last_user(llm, 1)
    print("    inspect: 写歪的 id 由自愈归一（零回灌）")


# ---------------------------------------------------------------------------
# 预算：形状级 / 行级
# ---------------------------------------------------------------------------

def test_shape_level_retry_then_fail(tmp_path):
    """整段不是 JSONL → 整轮重发 ≤ SHAPE_RETRY_MAX 次 → MmtLoopError。"""
    llm = ScriptedLLM("今天天气不错呢。", "我随便说点什么。", "还是不用 JSON。")
    engine, _st, _sid = _engine(llm, tmp_path)
    with pytest.raises(MmtLoopError) as ei:
        engine.agent_turn("在吗")
    assert "形状级重发" in str(ei.value)
    assert len(llm.snapshots) == 1 + SHAPE_RETRY_MAX, len(llm.snapshots)
    assert "一行一条 JSON" in _last_user(llm, 1)          # 回灌话术
    print(f"    budget: 形状级 {SHAPE_RETRY_MAX} 次后失败（{len(llm.snapshots)} 次调用）")


def test_line_reask_budget(tmp_path):
    """修不了的操作行（胡编的 id）→ 续写 ≤ LINE_REASK_MAX 次 → MmtLoopError。"""
    bad = '{"action": "mmt_inspect_character", "payload": {"character_id": "胡编的名字"}}'
    llm = ScriptedLLM(bad, bad, bad)
    engine, _st, _sid = _engine(llm, tmp_path)
    with pytest.raises(MmtLoopError) as ei:
        engine.agent_turn("查一下那个人")
    assert "行级续写" in str(ei.value)
    assert len(llm.snapshots) == 1 + LINE_REASK_MAX, len(llm.snapshots)
    print(f"    budget: 行级续写 {LINE_REASK_MAX} 次后失败（{len(llm.snapshots)} 次调用）")


def test_droppable_action_row_is_noted_next_turn(tmp_path):
    """`send_media` 修不了 ⇒ 丢行 + 气泡照常交付 + **下一轮**注记念一次（自清）。"""
    llm = ScriptedLLM(
        '{"text": "给你看张图"}\n{"action": "mmt_send_media", "payload": {"media_type": "image"}}',
        '{"text": "在的"}',
        '{"text": "怎么啦"}')
    engine, _st, _sid = _engine(llm, tmp_path)
    r = engine.agent_turn("看看")
    assert r.ok and [a["action"] for a in r.actions] == ["mmt_chat"], "图那行被丢, 气泡保留"
    engine.agent_turn("在吗")                       # ← 注记在**下一轮**才出现
    assert any("上一轮有一行操作没执行" in (m.get("content") or "")
               for m in llm.snapshots[1] if m["role"] == "system"), "缺下一轮注记"
    engine.agent_turn("在吗2")
    assert not any("上一轮有一行操作没执行" in (m.get("content") or "")
                   for m in llm.snapshots[2] if m["role"] == "system"), "注记应自清（只念一次）"
    print("    drop: 丢行 + 下一轮注记念一次（自清）")

