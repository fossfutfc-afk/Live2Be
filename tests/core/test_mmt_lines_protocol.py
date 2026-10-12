"""MMT **行协议**接线（⑥-2d 接线 / ⑥-2f 起是唯一路径）。

契约: `docs/DESIGN_STREAM_CONTRACT.md` §3（内容行/控制行）/ §4（兜底分级 +
重试三段式）/ §10.3（三个注入点）。本文件钉新路径的行为：

    逐行交付      text 行 = 一个气泡；事件**行交付即 append**（C4）；历史一行一条
    丢行隔离      坏行只丢自己（软, 不触发回灌）
    ⭐ 独占       look 混排 → 硬问题 + 行级续写（只补控制行）
    ⭐ 回灌       look 翻到的东西**回灌**后继续这一轮（AUDIT §B9 的洞）
    形状级预算    整段不是 JSONL → 整轮重发 ≤ SHAPE_RETRY_MAX 次 → 失败
    行级预算      修不了的操作行 → 续写 ≤ LINE_REASK_MAX 次 → 失败
    软丢行注记    send_media 修不了 ⇒ 丢行 + **下一轮**注记念一次（自清）
"""
import json
import sys
from pathlib import Path

import pytest

from core.mmt.engine import (
    LINE_REASK_MAX,
    SHAPE_RETRY_MAX,
    MmtLoopError,
    MomoTalkEngine,
)
from core.session import SessionStore
from llm import task_labels as T
from tests import stub_tasks

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
# ⑥-3a 流式交付（`chat_full(on_chunk=…)`）
# ---------------------------------------------------------------------------

class StreamingLLM(ScriptedLLM):
    """有 `chat_full` 的桩 —— **逐行喂** `on_chunk`（生产形状: 真客户端就是流式）。

    `on_row(line)` 在每一行喂完之后调用: 测试在**那一刻**读事件流, 于是"哪个气泡
    什么时候上屏"成为可断言的事实（批式桩永远断言不到）。
    """

    def __init__(self, *scripts, on_row=None):
        super().__init__(*scripts)
        self.on_row = on_row

    def chat_full(self, messages, temperature=0.8, max_tokens=4096,
                  response_format="text", on_chunk=None, **kw):
        out = self.chat(messages, temperature=temperature, max_tokens=max_tokens,
                        response_format=response_format, **kw)
        if not isinstance(out, str) or on_chunk is None:
            return out
        for line in out.splitlines(keepends=True):
            on_chunk(line)
            if self.on_row is not None:
                self.on_row(line)
        return out


def _streamed_engine(tmp_path, *scripts, probe=None):
    """带探针的流式引擎: `probe(mmt 事件子类型, 刚喂完的那一行)`。

    探针读的是**当时**的事件流（= 玩家此刻能轮询到的东西）。
    """
    box: dict = {}

    def on_row(line):
        if probe is not None:
            probe([e.subtype for e in box["st"].events(CHARACTER, box["sid"])
                   if e.type == "mmt"], line)

    llm = StreamingLLM(*scripts, on_row=on_row)
    engine, st, sid = _engine(llm, tmp_path)
    box["st"], box["sid"] = st, sid
    return llm, engine, st, sid


def _rows(*objs: dict) -> str:
    """若干行对象 → JSONL 文本（每行都带换行 —— 流式下"行一完整就交付"）。"""
    return "\n".join(json.dumps(o, ensure_ascii=False) for o in objs) + "\n"


def test_content_rows_deliver_immediately(tmp_path):
    """⭐ ⑥-3a **到达即交付**: 一行解析出来就上屏（一个字都不等）。

    ⚠️ 2026-10-12 用户裁**撤掉"一行前瞻"**：那个手法的唯一理由是"下一行可能是
    静默轮 `inspect`"（要留一手才收得回），而它 2026-10-08 退役 ⇒ 前瞻只剩
    "让最后一行晚一格上屏"这一个代价。今天每喂一行都立刻多一条气泡。
    """
    seen: list[int] = []

    def probe(subs, _line):
        seen.append(subs.count("mmt_chat"))

    _llm, engine, _st, _sid = _streamed_engine(
        tmp_path,
        _rows({"text": "第一句"}, {"text": "第二句"}, {"text": "第三句"}),
        probe=probe)
    r = engine.agent_turn("在吗")
    assert r.ok and r.reply == "第一句\n第二句\n第三句"
    # 喂完第 1/2/3 行 ⇒ 分别已经 1/2/3 条上屏（旧口径是 0/1/2）
    assert seen == [1, 2, 3], seen
    print("    stream: 内容行到达即交付（每行都立刻上屏）")


def test_whole_turn_action_waits_until_block_end(tmp_path):
    """独占行（`trigger`）**不在流中间执行** —— 它要整轮可见才判得出"我是不是唯一操作行"。"""
    seen: list[list[str]] = []

    def probe(subs, _line):
        seen.append(list(subs))

    _llm, engine, st, sid = _streamed_engine(
        tmp_path,
        _rows({"text": "我们当面说吧！"},
              {"action": "mmt_trigger_bond_story",
               "payload": {"chapter_title": "当面说清楚"}}),
        probe=probe)
    r = engine.agent_turn("好啊")
    assert r.ok and r.bond_story
    # 第 1 行（话）**到达即上屏**; 第 2 行（trigger）到达时只看到那一条 chat ——
    # trigger 自己攒到块尾才执行（不在这两次喂行的快照里）
    assert seen == [["mmt_chat"], ["mmt_chat"]], seen
    assert [e.subtype for e in st.events(CHARACTER, sid) if e.type == "mmt"] == \
        ["mmt_chat", "mmt_trigger_bond_story"]
    print("    stream: 独占行攒到块尾（流中间不执行）")


def test_look_keeps_the_words_that_came_before_it(tmp_path):
    """⭐ `look` 是 **trigger 式独占**（2026-10-08 用户裁）: 先说一句"我找找看"再翻 ——
    那句话**在它自己那一行到达时就上屏了**（到达即交付）, 而 `look` 自己
    攒到块尾才执行（它要整轮可见才判得出"我是不是唯一操作行"）。

    ⚠️ 这是"两条路径同形"的**流式**那一半（批式那一半在
    `test_mmt_look_action.py::test_words_may_come_before_the_look`）:
    （历史上"整轮只能有 look 一条行"的旧口径下, 这句话根本不允许存在。）
    """
    seen: list[list[str]] = []

    def probe(subs, _line):
        seen.append(list(subs))

    _llm, engine, _st, _sid = _streamed_engine(
        tmp_path,
        _rows({"text": "唔……我找找看"},
              {"action": "mmt_look", "payload": {"clue": "苔藓"}}),
        _rows({"text": "……嗯，想不起来了"}),
        probe=probe)
    r = engine.agent_turn("我们上次说的那件事？")
    assert r.ok and r.reply == "唔……我找找看\n……嗯，想不起来了", r.reply
    # ⚠️ 只看**头两次**喂行（第 1 块的两行）: 第 3 次是第二块的续写行（同一批事件流）。
    # 喂完第 1 行（话）: 已经上屏; 喂完第 2 行（look）: 仍然只有那一条 ——
    # look 自己不上屏（事件流里只有 mmt_chat, 没有 mmt_look）。
    assert seen[:2] == [["mmt_chat"], ["mmt_chat"]], seen
    print("    stream: 先说话再翻 —— 话在 look 那行到达时上屏, look 攒到块尾")



def test_late_hard_issue_after_delivery_does_not_rollback(tmp_path):
    """⭐ 已交付后判出的硬问题**不回滚、也不抛**（⑥-3a 折中方案）。

    真机语义: 话已经说出去了 —— 独占行不执行 + 记账 + **下一轮**念一次注记;
    整轮**不能**标成"发送失败"（前端会把玩家的消息画成感叹号, 而角色明明回了话）。
    """
    bad = _rows({"text": "我们当面说吧！"},
                {"action": "mmt_trigger_bond_story", "payload": {"chapter_title": "雨"}})
    llm = ScriptedLLM(bad, bad)              # 续写轮也修不好 → 行级预算耗尽
    engine, st, sid = _engine(llm, tmp_path)
    r = engine.agent_turn("好啊")            # ⚠️ 以前这里会抛 MmtLoopError
    assert r.ok and r.reply == "我们当面说吧！" and not r.bond_story
    assert [e.subtype for e in st.events(CHARACTER, sid) if e.type == "mmt"] == ["mmt_chat"]
    assert any("上一轮有一行操作没执行" in n for n in engine._line_notes), \
        "控制行没执行 → 必须记账（下一轮念一次）"
    assert any(t.get("action") == "line_stream/streamed" for t in engine.trace), \
        f"trace 里要有『已交付后判出问题』的留痕: {engine.trace}"
    print("    stream: 已交付后的硬问题不回滚、不抛（记账 + 下一轮注记）")


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

