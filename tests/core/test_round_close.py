# -*- coding: utf-8 -*-
"""R4 收口（约定记账）的**编排**测试 —— DESIGN_GRAPH_V4 §6 / §8。

三件事在这里被钉住:
    ① 它排在 **R1 之后、R2 之前**（⏸ 2026-09-29 承诺退图后这条**不再是正确性要求**,
       但编排顺序照旧 —— 用例继续钉住它, 免得有人顺手挪了还以为没事）;
    ② 它产的 note 操作**不进事件流**, 而是交给调用方在**整批 ok 之后**才 append
       （§8: 失败 = 整批回滚 ⇒ 那条约定原样开着）;
    ③ 没事可做时（没有开着的约定 + 本段没有新经历）**不发这次调用**（0 次 LLM）。

⭐ **2026-09-29: 承诺退图**（用户裁决）—— R4 从"记账 + 固化"缩成**只记账**:
它**不再建 promise 节点、不再写任何边**（`from`/`to`/`formed_by` 三条边一起删）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brain import WikiStoreV2, make_node, notes
from core.digest.pipeline import digest_segment
from core.brain.entities import ensure_entities
from core.mmt.engine import MomoTalkEngine
from core.session import SessionStore, make_event
from core.session.events import TYPE_NOTE
from llm import task_labels as T
from tests import stub_tasks

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"
CHAR = "c"


class RoundLLM:
    """四轮可控: A / R4 / B / R3 各给一份应答（R3 默认空包 —— 那些用例不测归属）。

    `split`（可选）: 手工指定 R0 那份应答。缺省 = "照搬 R1 声明的区间; R1 空 ⇒
    空骨架"（**空骨架是有判据的**: 编排层会拿它跳过后面几轮 —— 见
    `RoundSpec.needs_segments`）。要测"这一段没有新经历、但有开着的约定"那种情形时,
    必须**手工给 R0 一条非空骨架**, 否则链条在 R0 就停了。
    """

    def __init__(self, a, close, b, attr=None, *, split=None):
        self.a, self.close, self.b = a, close, b
        self.attr = {"attributions": []} if attr is None else attr
        self.split = split
        self.calls: list[list[dict]] = []
        self.tasks: list[str | None] = []

    def chat(self, messages, **kw):
        self.calls.append([dict(m) for m in messages])
        task = kw.get("task")
        self.tasks.append(task)
        if task == T.DIGEST_SPLIT:            # ⭐ R0: 缺省照搬 R1 那份应答里的区间
            return (self.split if self.split is not None
                    else stub_tasks.split_for_scripted(messages, self.a))
        if task == T.DIGEST_RECORD:
            return self.a
        if task == T.DIGEST_CLOSE:
            return self.close
        if task in (T.DIGEST_UNDERSTAND, T.DIGEST):
            return self.b
        if task == T.DIGEST_ATTRIBUTE:
            return self.attr
        raise RuntimeError(f"意外调用 task={task!r}")

    def user_of(self, task: str | None = None) -> str:
        """最后一条 user 消息（R4 的料就在里面）。"""
        idx = (self.tasks.index(task) if task is not None else len(self.calls) - 1)
        msgs = self.calls[idx]
        return msgs[-1]["content"]


def _store(tmp_path) -> WikiStoreV2:
    """带 self/sensei 的干净库。"""
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
    """R4 夹在 R1 与 R2 之间: 它拿得到**本段新建的 episode 真 id**。

    ⏸ 2026-09-29 之前这条顺序还有第二个理由（"承诺节点要先就位, R2/R3 才好连它"）——
    承诺退图后**理由只剩这一个**, 而顺序照旧。
    """
    st = _store(tmp_path)
    note = _open_promise()                        # n1 周六模型店（那条约定在事件流里）
    close = {"add": [{"text": "拍一张模型店的照", "refs": ["m0001"]}],
             "close": [{"id": "n1", "state": "kept", "refs": ["m0001"],
                        "afterwards": "周六真的去了"}]}
    llm = RoundLLM(_a("模型店门口", "又路过那家店"), close, _b(["m0001", "m0002"]))

    res = digest_segment(st, llm, _events(note, _mmt(3)))
    assert res.ok, res.errors

    # 三次调用 + 顺序: R0 → A → close → B（R3 归属也跑了, 但那些用例不测它）
    assert llm.tasks[:4] == [T.DIGEST_SPLIT, T.DIGEST_RECORD, T.DIGEST_CLOSE,
                             T.DIGEST_UNDERSTAND], llm.tasks
    # ⭐ R4 的料 = 还开着的约定（带编号）+ 本段新增经历（真 id）
    r4 = llm.user_of(T.DIGEST_CLOSE)
    assert "周六模型店" in r4 and "n1" in r4
    assert "m0001" in r4 and "m0002" in r4
    # ⭐ 行形态 = `- 〔m0001｜《模型店门口》〕正文`（头由 `marks.head` 出 —— 唯一实现;
    # 2026-09-29 之前是 `- m0001 「模型店门口」 正文`, 而 `「」` 在她视图里是"逐字原话"）
    assert "- 〔m0001｜《模型店门口》〕模型店门口" in r4, r4
    # ⭐ 产出: 一条 add + 一条 close（**没进事件流** —— 那是调用方的活）
    assert [op["action"] for op in res.notes_ops] == ["add", "close"]
    assert res.notes_ops[0]["text"] == "拍一张模型店的照"
    assert res.notes_ops[0]["refs"] == ["m0001"]
    assert res.notes_ops[1] == {"action": "close", "id": "n1"}
    # ⚠️ 2026-10-05: `afterwards` / `state` **不再进 op**（note 面没有读者了 ——
    #    划掉即移除）; 它们只进 evolution 日志（审计账）
    print(f"    R4 顺序={llm.tasks} 料={r4.splitlines()[0][:30]!r} ops={len(res.notes_ops)}")
    # ⭐ 2026-09-29: **只产 note 操作, 不碰图** —— 承诺节点与它的三条专属边一条都不许出现
    kinds = {n.kind for n in st.all()}
    assert kinds == {"entity", "episode", "belief"}, kinds    # R1 建经历 / R2 建看法, 没有 promise
    assert {e.rel for e in st.graph().edges} <= {"supports"}, \
        sorted({e.rel for e in st.graph().edges})


def test_r4_skipped_when_nothing_to_do(tmp_path):
    """没有开着的约定 **且** 本段没有新经历 ⇒ 这一轮必然空转 ⇒ **0 次调用**。"""
    st = _store(tmp_path)
    llm = RoundLLM({"episodes": []}, {"add": [], "close": []},
                   {"decisions": [], "evidence": [], "affection_exp_delta": 0})

    res = digest_segment(st, llm, _events(_mmt(3)))
    assert res.ok, res.errors
    assert T.DIGEST_CLOSE not in llm.tasks            # R4 没被调
    assert res.notes_ops == []


def test_r4_runs_without_new_episodes_when_something_is_open(tmp_path):
    """本段没有新经历, 但**有开着的约定** ⇒ 照跑（她可能在这一段里把它翻篇了）。"""
    st = _store(tmp_path)
    st.add(make_node("episode", text="模型店门口", event_seq=[3],
                     ts="2026-09-20T09:00:00"))       # n1 的 refs = ["m0001"]（真的在）
    note = _open_promise()
    # ⚠️ R0 **手工给一条非空骨架**: 本用例测的是"R1 没记东西, 但 R4 照跑" ——
    # 若让 R0 也回空骨架, 编排层会在 R0 就跳过后面几轮（那是另一条判据）
    llm = RoundLLM({"episodes": []},
                   {"add": [], "close": [{"id": "n1", "state": "broken",
                                          "afterwards": "没去成"}]},
                   {"decisions": [], "evidence": [], "affection_exp_delta": 0},
                   # span 只能指**内容事件**（note/add 是账目, 不进时间线 ⇒ 不在 `seq_set` 里）;
                   # 本用例的内容事件只有 `_mmt(3)` 那一条
                   split={"segments": [{"span": [3, 3], "keep": "temporary",
                                        "abstract": "这一段"}]})

    res = digest_segment(st, llm, _events(note, _mmt(3)))
    assert res.ok, res.errors
    assert llm.tasks[:4] == [T.DIGEST_SPLIT, T.DIGEST_RECORD, T.DIGEST_CLOSE,
                             T.DIGEST_UNDERSTAND], llm.tasks
    assert res.notes_ops[0] == {"action": "close", "id": "n1"}
    # ⚠️ 2026-10-05: 只剩 `id` —— `state`（结局）与 `afterwards`（"后来怎么了"）都不再进 op;
    #    指不出 finish episode ⇒ 连 `refs` 都没有（这一条与今天一致）
    # ⭐ 2026-09-29: close **不建节点**（从前这里验的是 `formed_by` 只连"说定它"那条）
    assert [n.id for n in st.all() if n.kind not in ("episode", "entity")] == []


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
    assert res.notes_ops == []
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
    assert res.notes_ops == []                                     # 雷拆了
    # ⭐ 2026-09-29: R4 本来就不建节点了 ⇒ 这一批的图面本来就是干净的
    assert [n.id for n in st.all() if n.kind not in ("episode", "entity")] == []


# ---------------------------------------------------------------------------
# 调用侧: 整批 ok 之后才 append（先真源后缓存）
# ---------------------------------------------------------------------------

class EngineLLM:
    """引擎级: A/R4/B 三份应答（其余旁路走标准桩 —— 含 R3 归属）。"""

    def __init__(self, a, close, b, *, split=None):
        self.a, self.close, self.b = a, close, b
        self.split = split
        self.tasks: list[str | None] = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text",
             **kw):
        task = kw.get("task")
        self.tasks.append(task)
        if task == T.DIGEST_SPLIT:            # ⭐ R0: 显式给就用它, 否则照搬 R1 的区间
            return (self.split if self.split is not None
                    else stub_tasks.split_for_scripted(messages, self.a))
        if task == T.DIGEST_RECORD:
            return self.a
        if task == T.DIGEST_CLOSE:
            return self.close
        if task in (T.DIGEST_UNDERSTAND, T.DIGEST):
            return self.b
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:
            return reply
        raise RuntimeError(f"意外调用 task={task!r}")


def test_engine_writes_r1_kept_note_and_does_not_duplicate_on_rerun(tmp_path):
    """⭐ 3b-3 端到端: `keep=always` 的切片 ⇒ 约定**落进真源与注入块**; **重跑不重复记**。

    两条判据:
      · R1 产的 `add` 与 R4 产的那条**走同一条交付通道**（`result.notes_ops` →
        引擎 `_write_note_ops` 先真源后缓存 + 重建注入）;
      · 重跑（同一段再消化一次）时, 节点面由 `_find_duplicate` 复用 ⇒ **不产新 op**;
        就算产了, 笔记面还有 `notes.ALREADY_PINNED` 那道（按"指向哪条经历"去重）。
    """
    st = SessionStore(tmp_path)
    engine = MomoTalkEngine(ROOT / "config" / "characters", None, store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    engine._session_rounds = 25
    e = make_event("mmt", "mmt_chat", {"player": "老师", "reply": "嗯"})
    st.append_event(CHARACTER, "", e)
    # ⚠️ 区间要落在**本段真有的那个 seq** 上（号由 store 发 —— `append_event` 不改
    # 我们手里那个对象, 所以从真源读回来）
    seq = st.events(CHARACTER)[-1].seq
    split = {"segments": [{"span": [seq, seq], "keep": "always",
                           "abstract": "明天把两个团子带去夏莱, 别多想"}]}
    engine.llm = EngineLLM(_a("她答应了带团子"), {"add": [], "close": []},
                           _b(["m0001"]), split=split)

    engine._run_digest(CHARACTER, engine._session_id)          # 同步跑

    evs = [e for e in st.events(CHARACTER) if e.type == TYPE_NOTE]
    assert len(evs) == 1 and evs[0].subtype == "add", evs
    assert evs[0].payload["text"] == "明天把两个团子带去夏莱, 别多想"
    assert evs[0].payload["refs"] == ["m0001"]
    ws = WikiStoreV2(st.data_root, world_id=st.world_id, char_id=CHARACTER)
    state = ws.read_notes()
    assert state is not None and [it.text for it in state.pinned] == [
        "明天把两个团子带去夏莱, 别多想"]
    assert "两个团子" in engine._brain_injection

    # ⭐ 重跑: 水位没推进（模拟崩溃窗口）⇒ 同一段再消化一次
    ws.meta["digested_seq"] = 0
    ws.save_meta()
    engine._run_digest(CHARACTER, engine._session_id)
    evs2 = [e for e in st.events(CHARACTER) if e.type == TYPE_NOTE]
    assert len(evs2) == 1, f"同一条经历不该被钉第二次: {[e.payload for e in evs2]}"


def test_r2_list_has_no_promise_anymore(tmp_path):
    """⏸ §9-13（2026-09-25 补的"承诺进 R2 视野 + 可 link"）**2026-09-29 作废** ——
    承诺退图 ⇒ R2 的列表里不再有它, `links` 的端点只有看法。

    这条用例钉的是**退役的形状**, 免得"承诺要能连边"那套又被加回来:
    列表渲染只认 kind ∈ {belief, experience}（`render_cognition_list`）,
    而 `must_include` 那个为承诺专开的参数**已经删掉**（零调用方）。
    """
    from core.brain.read.render import render_cognition_list
    st = _store(tmp_path)
    st.add(make_node("belief", text="老师答应的事都做到了", subject="sensei",
                     significance=0.9, event_seq=[2]))
    # 盘上可能还有旧档留下的 promise 行（`from_dict` 会把未知 kind 降级成 episode）
    st.save()

    text, local_of = render_cognition_list(st, cap=12)
    assert len(local_of) == 1 and "老师答应的事都做到了" in text
    assert "promise" not in text                     # 类型标签里不该再有这个词
    import inspect
    assert "must_include" not in inspect.signature(render_cognition_list).parameters


def test_cognition_list_cap_still_truncates(tmp_path):
    """⏸ 原 `must_include`（"本轮 R4 物化的承诺必进, 不受 cap 截断"）**2026-09-29 随退图删** ——
    为承诺专开的参数, 承诺一退它就是死参数（判据① 没读者就删）。

    这里留下 cap 本身的行为: 按 significance 降序取前 `cap` 条。
    """
    from core.brain.read.render import render_cognition_list
    st = _store(tmp_path)
    for i in range(3):
        st.add(make_node("belief", text=f"看法{i}", subject="sensei",
                         significance=0.9 - i * 0.1))
    st.save()

    text, local_of = render_cognition_list(st, cap=1)

    assert len(local_of) == 1 and "看法0" in text
    assert "看法1" not in text and "看法2" not in text


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
    assert state is not None and [it.text for it in state.pinned] == ["周六模型店，有点等不及"]
    assert "周六模型店" in engine._brain_injection, engine._brain_injection
    assert "你自己记下的约定" in engine._brain_injection
