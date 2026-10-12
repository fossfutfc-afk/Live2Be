"""⭐ N5b 端到端 —— 想起行的**落账链路**（2026-09-29）。

链路: 她写 `{"noticed": "名字"}` → 引擎拿名字找**唯一** episode → 找到就落一条
`noticed` 事件（**非内容事件**）; 找不到 / 有多条 ⇒ **丢**（不猜）+ 台账。
补边是 N5c（L1）, 这里只管**账**。

判据（`TODO.md` N5b）:
  · 编造的引用被丢          · 账可查（事件流里那一条）
  · 旧形状完全不受影响      · 前端/历史/digest 都不吃它（非内容事件）
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from core.brain import WikiStoreV2, make_node
from core.mmt.engine import MmtLoopError, MomoTalkEngine
from core.session import SessionStore
from core.session.renderer import window_messages
from llm import task_labels as T
from tests import stub_tasks

ROOT = Path(__file__).resolve().parents[2]
CHARACTER = "igusa_haruka"


class ScriptedLLM:
    """按脚本回**一行一条 JSON**；跑光了就复用最后一条。"""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.snapshots: list[list[dict]] = []

    def chat(self, messages, **kw):
        task = kw.get("task")
        self.snapshots.append([dict(m) for m in messages])
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:
            return reply
        if task in T.MAIN:
            return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        raise stub_tasks.unknown_task(task)


def _no_embed():
    def boom(texts):
        raise RuntimeError("embed backend off（用例走词面降级）")
    return boom


def _engine(tmp_path, llm) -> tuple[MomoTalkEngine, SessionStore, str]:
    store = SessionStore(data_root=tmp_path)
    eng = MomoTalkEngine(ROOT / "config" / "characters", llm, store=store,
                         embed_fn=_no_embed)
    name = eng.start_session(CHARACTER)
    root = store.create(CHARACTER, name)
    eng.attach_session(root.session_id)
    return eng, store, root.session_id


def _seed(tmp_path, title="瓦片缝里的苔藓", text="我把秘密基地告诉了老师",
          ts="2026-09-26T10:00:00") -> str:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)
    nid = st.add(make_node("episode", text=text, title=title, tags=["苔藓"], ts=ts,
                           significance=0.7, event_seq=[1]))
    st.save()          # ⚠️ `add` 只改内存; 引擎是另开一个 store 读的
    return nid


def _noticed_events(store: SessionStore, session_id: str) -> list:
    return [e for e in store.events(CHARACTER, session_id) if e.type == "noticed"]


TEXT_AND_NOTICE = '{"text": "……等等"}\n{"noticed": "瓦片缝里的苔藓"}'


# ---------------------------------------------------------------------------
# 命中 → 落账
# ---------------------------------------------------------------------------

def test_noticed_hits_and_logs(tmp_path):
    _seed(tmp_path)
    llm = ScriptedLLM([TEXT_AND_NOTICE])
    eng, store, sid = _engine(tmp_path, llm)
    eng.agent_turn("我今天又去看了看那片苔藓")
    rows = _noticed_events(store, sid)
    assert len(rows) == 1, [e.to_dict() for e in store.events(CHARACTER, sid)]
    assert rows[0].payload == {"title": "瓦片缝里的苔藓", "hit": "m0001"}
    print("    N5b: 命中 → 落一条 noticed（title + hit）")


def test_noticed_event_carries_no_speech_and_is_not_content(tmp_path):
    """⭐ 它是**账目**: 不进对话历史（resume 上下文）—— 与"这条事件存在"是两件事。"""
    _seed(tmp_path)
    llm = ScriptedLLM([TEXT_AND_NOTICE])
    eng, store, sid = _engine(tmp_path, llm)
    eng.agent_turn("我今天又去看了看那片苔藓")
    events = store.events(CHARACTER, sid)
    msgs = window_messages(events)
    joined = json.dumps(msgs, ensure_ascii=False)
    assert "noticed" not in joined, msgs
    assert "瓦片缝里的苔藓" not in joined, msgs          # 名字也不该漏进上下文
    assert "等等" in joined                              # 她的话照样在
    print("    N5b: 账目不进上下文（她的话照旧在）")


def test_noticed_logs_after_this_turn_speech(tmp_path):
    """⏱ **落账时机 = 本轮内容行之后** —— N5c 靠这个把账归到"本轮"。

    N5c 的归属判据 = "它之前最近的那条内容事件" ⇒ 若这条账落在她的话**之前**,
    它就会被归到**上一轮**（上一段）——静默错归属。
    """
    _seed(tmp_path)
    llm = ScriptedLLM([TEXT_AND_NOTICE])
    eng, store, sid = _engine(tmp_path, llm)
    eng.agent_turn("我今天又去看了看那片苔藓")
    events = [e for e in store.events(CHARACTER, sid) if e.type in ("mmt", "noticed")]
    kinds = [e.type for e in events]
    assert kinds.index("mmt") < kinds.index("noticed"), kinds
    assert events[-1].type == "noticed"
    print("    N5b: 账落在本轮话之后（seq 顺序 = 归属正确的前提）")


def test_noticed_tolerates_brackets_and_quotes(tmp_path):
    """容错: 带书名号 / 半全角引号 / 整段元信息抄进来 —— 都命中。

    ⚠️ 每轮**换一个数据根**: `SessionStore.create` 是**懒创建**（每世界每角色
    一条线, 重复调用返回同一线、事件流持续 append）⇒ 共用 tmp_path 的话
    第二轮会把第一轮的账一起数进来（写这条用例时踩到过）。
    """
    for i, raw in enumerate(('《瓦片缝里的苔藓》', '“瓦片缝里的苔藓”',
                             '《瓦片缝里的苔藓》｜5 天前｜9/26')):
        root = tmp_path / f"w{i}"
        _seed(root)
        llm = ScriptedLLM(['{"text": "嗯"}\n' + json.dumps({"noticed": raw},
                                                          ensure_ascii=False)])
        eng, store, sid = _engine(root, llm)
        eng.agent_turn("我今天又去看了看那片苔藓")
        assert len(_noticed_events(store, sid)) == 1, raw
    print("    N5b: 带书名号/引号/整段 → 都命中")


# ---------------------------------------------------------------------------
# 不命中 → 丢（不猜）
# ---------------------------------------------------------------------------

def test_fabricated_notice_is_dropped(tmp_path):
    _seed(tmp_path)
    llm = ScriptedLLM(['{"text": "嗯……"}\n{"noticed": "我和老师去看过极光"}'])
    eng, store, sid = _engine(tmp_path, llm)
    res = eng.agent_turn("今天天气不错")
    assert res.ok and res.reply                           # 对话照走
    assert _noticed_events(store, sid) == []              # 账不落
    print("    N5b: 编造的引用 → 丢（不阻断对话）")


def test_ambiguous_title_is_not_guessed(tmp_path):
    _seed(tmp_path)                                        # m0001「瓦片缝里的苔藓」
    _seed(tmp_path, text="另一条同名的", ts="2026-09-25T10:00:00")   # m0002 同名
    llm = ScriptedLLM([TEXT_AND_NOTICE])
    eng, store, sid = _engine(tmp_path, llm)
    eng.agent_turn("我今天又去看了看那片苔藓")
    assert _noticed_events(store, sid) == []
    print("    N5b: 同名两条 → 不猜（不落账）")


def test_no_noticed_line_no_event(tmp_path):
    """没写就是没写 —— 不产生任何账（旧形状的输出完全不受影响）。"""
    _seed(tmp_path)
    llm = ScriptedLLM(['{"text": "嗯，老师今天也在忙吗？"}'])
    eng, store, sid = _engine(tmp_path, llm)
    eng.agent_turn("在忙")
    assert _noticed_events(store, sid) == []
    assert [e.type for e in store.events(CHARACTER, sid)].count("mmt") == 1
    print("    N5b: 没写 → 零影响（事件流与改动前同形）")


# ---------------------------------------------------------------------------
# 边界
# ---------------------------------------------------------------------------

def test_noticed_alone_is_not_enough(tmp_path):
    """⭐ 只有一笔账 ⇒ 玩家屏幕上什么都没有 ⇒ 按"没有可见内容"处理（不能静默成功）。

    契约里那句"**想起行只是记账，不代替说话**"就是这条（`schema.py` 硬规则 6）。
    这里钉的是行为: 反复只写账 ⇒ 整轮失败, 而且**账也不落**（那一轮没有"当下"）。
    """
    _seed(tmp_path)
    llm = ScriptedLLM(['{"noticed": "瓦片缝里的苔藓"}'])
    eng, store, sid = _engine(tmp_path, llm)
    with pytest.raises(MmtLoopError):
        eng.agent_turn("我今天又去看了看那片苔藓")
    assert _noticed_events(store, sid) == []
    print("    N5b: 只有账没说话 → 不静默成功（账也不落）")


def test_bad_shapes_are_dropped(tmp_path):
    """形状坏的想起行被丢行记账（判别键恰好其一 / 值非空字符串）。"""
    _seed(tmp_path)
    llm = ScriptedLLM(['{"text": "嗯"}\n'
                       '{"text": "a", "noticed": "瓦片缝里的苔藓"}\n'
                       '{"noticed": ""}\n'
                       '{"noticed": 42}'])
    eng, store, sid = _engine(tmp_path, llm)
    eng.agent_turn("我今天又去看了看那片苔藓")
    assert _noticed_events(store, sid) == []
    print("    N5b: 坏形状 → 丢行记账（不落账）")
