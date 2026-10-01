# -*- coding: utf-8 -*-
"""R4 收口（promise 记账）的**编排**测试 —— DESIGN_GRAPH_V4 §6 / §8。

三件事在这里被钉住:
    ① 它排在 **R1 之后、R2 之前**（否则 promise 节点"永远没边、永远没归属"）;
    ② 它产的 note 操作**不进事件流**, 而是交给调用方在**整批 ok 之后**才 append
       （§8: 失败 = 整批回滚 ⇒ 那条约定原样开着）;
    ③ 没事可做时（没有开着的约定 + 本段没有新经历）**不发这次调用**（0 次 LLM）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brain.wiki_v2 import WikiStoreV2, make_node, notes
from core.brain.wiki_v2.digest import digest_segment
from core.brain.wiki_v2.entities import ensure_entities
from core.mmt.engine import MomoTalkEngine
from core.session import SessionStore, make_event
from core.session.events import TYPE_NOTE
from llm import task_labels as T
from tests import stub_tasks

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"
CHAR = "c"


class RoundLLM:
    """四轮可控: A / R4 / B / R3 各给一份应答（R3 默认空包 —— 那些用例不测归属）。"""

    def __init__(self, a, close, b, attr=None):
        self.a, self.close, self.b = a, close, b
        self.attr = {"attributions": []} if attr is None else attr
        self.calls: list[list[dict]] = []
        self.tasks: list[str | None] = []

    def chat(self, messages, **kw):
        self.calls.append([dict(m) for m in messages])
        task = kw.get("task")
        self.tasks.append(task)
        if task == T.DIGEST_A:
            return self.a
        if task == T.DIGEST_CLOSE:
            return self.close
        if task in (T.DIGEST_B, T.DIGEST):
            return self.b
        if task == T.DIGEST_ATTR:
            return self.attr
        raise RuntimeError(f"意外调用 task={task!r}")

    def user_of(self, task: str | None = None) -> str:
        """最后一条 user 消息（R4 的料就在里面）。"""
        idx = (self.tasks.index(task) if task is not None else len(self.calls) - 1)
        msgs = self.calls[idx]
        return msgs[-1]["content"]


def _store(tmp_path) -> WikiStoreV2:
    """带 self/sensei 的干净库（承诺的 `from`/`to` 要有两端才写得出）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    ensure_entities(st, char_name="伊草 遥香", sensei_name="老师")
    st.save()
    return st


def _events(*items):
    """(type, subtype, payload, seq) 元组 **或现成的 Event** → 事件列表。"""
    out = []
    for it in items:
        if isinstance(it, tuple):
            typ, sub, payload, seq = it
            e = make_event(typ, sub, payload)
            e.seq = seq
            out.append(e)
        else:
            out.append(it)                       # 已是 Event（如 `_open_promise()`）
    return out


def _mmt(seq, player="老师", reply="嗯"):
    return ("mmt", "chat", {"player": player, "reply": reply}, seq)


def _a(*texts):
    return {"episodes": [{"text": t, "title": t[:8], "tags": ["约定"]} for t in texts]}


def _b(episode_ids):
    """Round B: 每条 episode 一条 `add kind=belief`（覆盖检查是硬要求）。"""
    return {"decisions": [{"episode": i, "decision": "add", "kind": "belief",
                           "subject": "sensei", "text": f"关于 {i} 的看法"}
                          for i in episode_ids],
            "evidence": [], "affection_exp_delta": 0}


def _open_promise() -> object:
    """预置一条**还开着**的约定 —— 返回那条 `note/add` **事件**（seq=1）。

    ⚠️ 必须把它放进喂给 `digest_segment` 的**事件流**里: R4 的"还开着的约定"
    来自 `store.notes_state(events)` —— 只造一个 `NotesState` 对象是看不见的
    （那正是"真源是事件流"这条纪律的日常体现）。
    """
    ev = notes.note_event(notes.add_op("周六模型店", ["m0001"], due="2026-09-26"))
    ev.seq = 1
    ev.ts = "2026-09-20T10:00:00"
    return ev


# ---------------------------------------------------------------------------
# 编排: 位置 / 料 / 产出
# ---------------------------------------------------------------------------

def test_r4_runs_after_r1_and_before_r2(tmp_path):
    """R4 夹在 R1 与 R2 之间: 它拿得到**本段新建的 episode 真 id**,
    产出的 promise 节点当场就在图里（R2 才看得到它 —— §8 的顺序理由）。"""
    st = _store(tmp_path)
    note = _open_promise()                        # n1 周六模型店（那条约定在事件流里）
    close = {"add": [{"text": "拍一张模型店的照", "refs": ["m0001"]}],
             "close": [{"id": "n1", "state": "kept", "refs": ["m0001"],
                        "afterwards": "周六真的去了"}]}
    llm = RoundLLM(_a("模型店门口", "又路过那家店"), close, _b(["m0001", "m0002"]))

    res = digest_segment(st, llm, _events(note, _mmt(3)))
    assert res.ok, res.errors

    # 三次调用 + 顺序: A → close → B（R3 归属也跑了, 但那些用例不测它）
    assert llm.tasks[:3] == [T.DIGEST_A, T.DIGEST_CLOSE, T.DIGEST_B], llm.tasks
    # ⭐ R4 的料 = 还开着的约定（带编号）+ 本段新增经历（真 id）
    r4 = llm.user_of(T.DIGEST_CLOSE)
    assert "周六模型店" in r4 and "n1" in r4
    assert "m0001" in r4 and "m0002" in r4
    # ⭐ 产出: 一条 add + 一条 close（**没进事件流** —— 那是调用方的活）
    assert [op["action"] for op in res.notes_ops] == ["add", "close"]
    assert res.notes_ops[0]["text"] == "拍一张模型店的照"
    assert res.notes_ops[0]["refs"] == ["m0001"]
    assert res.notes_ops[1] == {"action": "close", "id": "n1", "state": "kept",
                               "afterwards": "周六真的去了"}
    print(f"    R4 顺序={llm.tasks} 料={r4.splitlines()[0][:30]!r} ops={len(res.notes_ops)}")
    # ⭐ close 固化了 promise 节点（正文 = 条目那句 + afterwards）
    nid = res.promise_nodes[0]
    node = st.get(nid)
    assert node.kind == "promise" and node.outcome == "kept"
    assert node.text == "周六模型店 —— 周六真的去了"
    g = st.graph()
    assert g.targets(nid, "from") == ["x0000"] and g.targets(nid, "to") == ["x0001"]
    assert g.targets(nid, "formed_by") == ["m0001"]      # note.refs ∪ close.refs（去重）


def test_r4_skipped_when_nothing_to_do(tmp_path):
    """没有开着的约定 **且** 本段没有新经历 ⇒ 这一轮必然空转 ⇒ **0 次调用**。"""
    st = _store(tmp_path)
    llm = RoundLLM({"episodes": []}, {"add": [], "close": []},
                   {"decisions": [], "evidence": [], "affection_exp_delta": 0})

    res = digest_segment(st, llm, _events(_mmt(3)))
    assert res.ok, res.errors
    assert T.DIGEST_CLOSE not in llm.tasks            # R4 没被调
    assert res.notes_ops == [] and res.promise_nodes == []


def test_r4_runs_without_new_episodes_when_something_is_open(tmp_path):
    """本段没有新经历, 但**有开着的约定** ⇒ 照跑（她可能在这一段里把它翻篇了）。"""
    st = _store(tmp_path)
    st.add(make_node("episode", text="模型店门口", event_seq=[3],
                     ts="2026-09-20T09:00:00"))       # n1 的 refs = ["m0001"]（真的在）
    note = _open_promise()
    llm = RoundLLM({"episodes": []},
                   {"add": [], "close": [{"id": "n1", "state": "broken",
                                          "afterwards": "没去成"}]},
                   {"decisions": [], "evidence": [], "affection_exp_delta": 0})

    res = digest_segment(st, llm, _events(note, _mmt(3)))
    assert res.ok, res.errors
    assert llm.tasks[:3] == [T.DIGEST_A, T.DIGEST_CLOSE, T.DIGEST_B]
    assert res.notes_ops[0]["state"] == "broken"
    assert "refs" not in res.notes_ops[0]         # 指不出 finish episode ⇒ 连这个键都没有
    nid = res.promise_nodes[0]
    assert st.graph().targets(nid, "formed_by") == ["m0001"]   # 只剩"说定它"的那条经历


# ---------------------------------------------------------------------------
# 失败语义: 整批回滚 ⇒ note 操作一并作废
# ---------------------------------------------------------------------------

def test_r4_bad_shape_fails_the_batch(tmp_path):
    """R4 的形状错（缺键）⇒ 拒整包 + 反馈重试; 耗尽 ⇒ **整批失败**, 节点回滚。"""
    st = _store(tmp_path)
    note = _open_promise()
    llm = RoundLLM(_a("模型店门口"), {"add": []},            # 缺 close 键
                   {"decisions": [], "evidence": [], "affection_exp_delta": 0})

    res = digest_segment(st, llm, _events(note, _mmt(3)))
    assert not res.ok
    assert any("缺键" in e for e in res.errors)
    assert res.notes_ops == [] and res.promise_nodes == []
    assert [n.id for n in st.all() if n.kind == "episode"] == []   # A 建的节点也回滚了


def test_later_round_failure_drops_note_ops(tmp_path):
    """⭐ R4 成功、但**后面那轮失败** ⇒ `notes_ops` 必须作废（§8: 整批回滚）。

    这是"先固化、后退场"能成立的前提: note 事件 append **不可撤销**, 所以它必须
    等到整批 ok 才写 —— 结果对象里留着它就是一颗雷（这里钉住它被清掉）。
    """
    st = _store(tmp_path)
    note = _open_promise()
    close = {"add": [{"text": "拍一张模型店的照", "refs": ["m0001"]}],
             "close": [{"id": "n1", "state": "kept", "afterwards": "周六真的去了"}]}
    llm = RoundLLM(_a("模型店门口"), close, {"decisions": [{"episode": "m9999"}]})  # B 引用不存在

    res = digest_segment(st, llm, _events(note, _mmt(3)))
    assert not res.ok
    assert res.notes_ops == [] and res.promise_nodes == []         # 雷拆了
    assert [n.id for n in st.all() if n.kind == "promise"] == []   # 固化也回滚了


# ---------------------------------------------------------------------------
# 调用侧: 整批 ok 之后才 append（先真源后缓存）
# ---------------------------------------------------------------------------

class EngineLLM:
    """引擎级: A/R4/B 三份应答（其余旁路走标准桩 —— 含 R3 归属）。"""

    def __init__(self, a, close, b):
        self.a, self.close, self.b = a, close, b
        self.tasks: list[str | None] = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text",
             **kw):
        task = kw.get("task")
        self.tasks.append(task)
        if task == T.DIGEST_A:
            return self.a
        if task == T.DIGEST_CLOSE:
            return self.close
        if task in (T.DIGEST_B, T.DIGEST):
            return self.b
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:
            return reply
        raise RuntimeError(f"意外调用 task={task!r}")


def test_r2_sees_the_promise_and_can_link_it(tmp_path):
    """⭐ §9-13（2026-09-25）: R4 物化的承诺**当场就进 R2 的视野**, 而且 R2 有动作面
    去写那两条边（`links`: `supports(promise → belief)` / `evolved_from`）。

    不补视野 = 刚物化的节点看不见; 不补动作面 = 看得见却说不出口（决策表的三个动作
    一律只写 `supports(episode → target)`）。两件一起才闭合。
    """
    st = _store(tmp_path)
    st.add(make_node("belief", text="老师答应的事都做到了", subject="sensei",
                     epistemic="inferred_belief", significance=0.9, event_seq=[2]))
    st.add(make_node("promise", text="周日一起去看海 —— 还没去",
                     outcome="superseded", event_seq=[2], ts="2026-09-19T10:00:00"))
    st.save()
    note = _open_promise()
    close = {"add": [], "close": [{"id": "n1", "state": "superseded",
                                   "afterwards": "被新的那条盖过去了"}]}
    # 列表顺序（significance 降序）: u0001=看法, u0002=旧承诺; R4 新物化的承诺 = u0003
    # R2: 一条 add（覆盖本段的 episode m0002）+ 两条 link
    b = _b(["m0002"])
    b["links"] = [{"from": "u0003", "rel": "supports", "to": "u0001"},
                  {"from": "u0003", "rel": "evolved_from", "to": "u0002"}]
    llm = RoundLLM(_a("模型店门口"), close, b)

    res = digest_segment(st, llm, _events(note, _mmt(3)))
    assert res.ok, res.errors

    # ⭐ 视野: R2 的输入里看得见承诺（带结局的标签）+ note 里那条旧条目
    r2 = llm.user_of(T.DIGEST_B)
    assert "｜promise·被新的取代了｜" in r2
    assert "周六模型店" in r2
    # ⭐ 动作面: 两条边真的写出来了（按文本找 id, 不赌编号）
    belief_id = next(n.id for n in st.all()
                     if n.kind == "belief" and n.text.startswith("老师答应的事"))
    old_p = next(n.id for n in st.all()
                 if n.kind == "promise" and "看海" in n.text)
    new_p = res.promise_nodes[0]
    g = st.graph()
    assert g.targets(new_p, "supports") == [belief_id]        # 新承诺 → 看法
    assert g.targets(new_p, "evolved_from") == [old_p]        # 新承诺 → 旧承诺
    assert st.audit() == []


def test_cognition_list_must_include_bypasses_cap(tmp_path):
    """`must_include`（本轮 R4 物化的承诺）**不受 cap 截断** —— 否则 R2 又一次
    "看不见刚要写边的东西"（承诺的 significance 默认为 0.5, 真机上排在看法后面）。"""
    from core.brain.wiki_v2.render import render_cognition_list
    st = _store(tmp_path)
    for i in range(3):
        st.add(make_node("belief", text=f"看法{i}", subject="sensei",
                         epistemic="inferred_belief", significance=0.9 - i * 0.1))
    pid = st.add(make_node("promise", text="周六模型店 —— 真的去了", outcome="kept"))
    st.save()

    text, local_of = render_cognition_list(st, cap=1, must_include=[pid])

    assert pid in local_of and "周六模型店" in text
    assert len(local_of) == 2                       # cap=1 的那条 + 必进的承诺
    # ⭐ N2（2026-09-29）: kind 进了元信息段（`〔u0002｜promise·已兑现｜被引 0〕…`）
    assert "〔u0002｜promise·已兑现｜被引 0〕" in text, text


def test_engine_writes_note_ops_into_the_truth(tmp_path):
    """端到端: digest 成功 ⇒ 引擎把 note 操作 append 进**真源**、刷 `notes.json`,
    并且这一轮的注入块里就有那条约定（先真源后缓存 + 重建注入）。"""
    close = {"add": [{"text": "周六模型店，有点等不及", "refs": ["m0001"]}],
             "close": []}
    st = SessionStore(tmp_path)
    llm = EngineLLM(_a("模型店门口"), close, _b(["m0001"]))
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    engine._session_rounds = 25
    # （N4a 之前这里要把"写卡计数器"摆到离到点还早 —— 全景轮已退役, 不再需要）
    st.append_event(CHARACTER, "", make_event("mmt", "mmt_chat",
                                              {"player": "老师", "reply": "嗯"}))

    engine._run_digest(CHARACTER, engine._session_id)          # 同步跑（不经后台线程）

    evs = [e for e in st.events(CHARACTER) if e.type == TYPE_NOTE]
    assert len(evs) == 1 and evs[0].subtype == "add"
    assert evs[0].payload["text"] == "周六模型店，有点等不及"
    ws = WikiStoreV2(st.data_root, world_id=st.world_id, char_id=CHARACTER)
    state = ws.read_notes()
    assert state is not None and [it.text for it in state.promise] == ["周六模型店，有点等不及"]
    assert "周六模型店" in engine._brain_injection, engine._brain_injection
    assert "你自己记下的约定" in engine._brain_injection
