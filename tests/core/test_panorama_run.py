# -*- coding: utf-8 -*-
"""全景轮（写卡）的**调用侧**测试 —— DESIGN_GRAPH_V4 §8.6。

两层:
  · `digest.run_panorama`: 取料 → 一次调用 → parse → 执行器 → **只返回该写什么**（不落盘）;
  · `MmtEngine._maybe_card_round`: 段计数器 + 触发 + **先真源后缓存**的提交（2026-09-25 接线）。

用户裁决（2026-09-25）: **每 10 段一次、章闭环不插队（只算那一段）、第一次也跑**;
⭐ **没跑成 / 没料 ⇒ 计数器不清零**（下一段再试）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brain.wiki_v2 import make_node, notes
from core.brain.wiki_v2.digest import (
    PANORAMA_COUNTER_KEY,
    PANORAMA_EVERY,
    run_panorama,
)
from core.brain.wiki_v2.store import WikiStoreV2
from core.mmt.engine import MomoTalkEngine
from core.session import SessionStore
from core.session.events import TYPE_NOTE, make_event
from llm import task_labels as T
from tests import stub_tasks

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"


# ---------------------------------------------------------------------------
# 图 + 上一版那张卡
# ---------------------------------------------------------------------------

def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)
    st.add(make_node("episode", text="模型店门口", tags=["模型店"],
                     event_seq=[1], ts="2026-08-01T00:00:00"))
    st.add(make_node("episode", text="又路过那家店", tags=["模型店"],
                     event_seq=[2], ts="2026-08-02T00:00:00"))
    return st


def _state(**kw) -> notes.NotesState:
    return notes.NotesState(**kw)


class CardLLM:
    """按 task 分派: 全景轮 → 队列里的那张卡（队列空 = 抛, 模拟调用失败）。

    `episodes` / `decisions` 给了就覆盖 Round A / Round B 的标准应答（需要 digest
    真产出 episode 的用例用 —— 全景轮的 `worth_running` 只看"本轮有没有新经历"）。
    """

    def __init__(self, *cards, episodes=None, decisions=None):
        self.cards = list(cards)
        self.episodes = episodes
        self.decisions = decisions
        self.tasks: list[str | None] = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text",
             **kw):
        task = kw.get("task")
        self.tasks.append(task)
        if task == T.DIGEST_A and self.episodes is not None:
            return {"episodes": list(self.episodes)}
        if task in (T.DIGEST_B, T.DIGEST) and self.decisions is not None:
            return {"decisions": list(self.decisions), "evidence": [],
                    "affection_exp_delta": 5}
        if task == T.DIGEST_PANORAMA:
            if not self.cards:
                raise RuntimeError("没有脚本了")
            return self.cards.pop(0)
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:
            return reply
        raise RuntimeError(f"意外调用 task={task!r}")

    @property
    def panorama_calls(self) -> int:
        return sum(1 for t in self.tasks if t == T.DIGEST_PANORAMA)


# ---------------------------------------------------------------------------
# run_panorama: 只算"该写什么", 不落盘
# ---------------------------------------------------------------------------

def test_run_panorama_returns_one_rewrite_op(tmp_path):
    st = _store(tmp_path)
    state = _state(habits=[notes.NoteItem(id="n1", text="他总先问我想要哪个",
                                          refs=["m0001"], since="2026-08-01T00:00:00")])
    llm = CardLLM({"habits": [{"id": "n1", "text": "他买东西时总先问我想要哪个",
                               "refs": ["m0001", "m0002"]}],
                   "drop": [],
                   "on_mind": {"text": "不想再隔着玻璃看", "refs": ["m0002"]}})

    run = run_panorama(st, llm, state, new_ids=["m0001", "m0002"])

    assert run.ran and run.ok, run.errors
    assert run.llm_calls == 1
    assert run.op["action"] == "rewrite"
    # 照抄编号 = 还是那一条（措辞改了也认）
    assert run.op["habits"] == [{"id": "n1", "text": "他买东西时总先问我想要哪个",
                                 "refs": ["m0001", "m0002"]}]
    assert run.op["on_mind"] == {"text": "不想再隔着玻璃看", "refs": ["m0002"]}
    assert (run.applied.kept, run.applied.added, run.applied.dropped) == (["n1"], [], [])
    # ⭐ 它**不碰图**、也**不落任何盘**: 事件没写、缓存没写（提交是调用方的事）
    assert [n.id for n in st.all() if n.kind == "promise"] == []
    assert not st.notes_path.exists()


def test_run_panorama_accounts_world_mistakes(tmp_path):
    """世界错**剔 + 记账**（不拒整包 —— 那是 parse 层的活, 这里只管"世上有没有那条经历"）。"""
    st = _store(tmp_path)
    llm = CardLLM({"habits": [{"text": "他总先问我想要哪个", "refs": ["m0001", "m0002"]},
                              {"text": "全是幻觉", "refs": ["m9999"]}],
                   "drop": [],
                   "on_mind": None})
    run = run_panorama(st, llm, _state(), new_ids=["m0001"])

    assert run.ok and [h["text"] for h in run.op["habits"]] == ["他总先问我想要哪个"]
    assert any("整条丢" in w for w in run.warnings)
    assert run.op["on_mind"] == ""                    # 没写 = 本次清空（键在, 值是空）


def test_run_panorama_skips_without_new_material(tmp_path):
    """没新料 ⇒ **0 次 LLM 调用**（重写一遍只是措辞空转）—— 调用方据此不清零计数器。"""
    st = _store(tmp_path)
    llm = CardLLM()
    run = run_panorama(st, llm, _state(), new_ids=[])

    assert run.ran is False and run.ok is False
    assert llm.panorama_calls == 0
    assert run.errors and "新消化" in run.errors[0]


def test_run_panorama_rejects_bad_shape_with_feedback(tmp_path):
    """形状错/漏写 ⇒ 拒整包 + 反馈重试一次; 两次都错 ⇒ `ok=False` 且**没有 op**。"""
    st = _store(tmp_path)
    state = _state(habits=[notes.NoteItem(id="n1", text="旧惯例", refs=["m0001"])])
    bad = {"habits": [], "drop": [], "on_mind": None}          # 漏写 n1 ⇒ 覆盖检查不通过
    llm = CardLLM(bad, bad)

    run = run_panorama(st, llm, state, new_ids=["m0001"])

    assert run.ran and not run.ok and run.op == {}
    assert llm.panorama_calls == 2                             # 反馈回灌重试一次
    assert any("漏写" in e for e in run.errors)


# ---------------------------------------------------------------------------
# 引擎侧: 段计数器 + 触发 + 先真源后缓存
# ---------------------------------------------------------------------------

def _engine(tmp_path, *cards, episodes=None, decisions=None):
    st = SessionStore(tmp_path)
    llm = CardLLM(*cards, episodes=episodes, decisions=decisions)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    engine._session_rounds = 25
    return engine, st, llm


def _wstore(st) -> WikiStoreV2:
    return WikiStoreV2(st.data_root, world_id=st.world_id, char_id=CHARACTER)


def _episodes(st) -> list[str]:
    """图里现成的两条经历（`new_ids` 的落点 —— 全景轮的料）。"""
    ws = _wstore(st)
    ids = [ws.add(make_node("episode", text="模型店门口", tags=["模型店"],
                            event_seq=[1], ts="2026-08-01T00:00:00")),
           ws.add(make_node("episode", text="又路过那家店", tags=["模型店"],
                            event_seq=[2], ts="2026-08-02T00:00:00"))]
    ws.save()
    return ids


def _mmt(st, n=1):
    for i in range(n):
        st.append_event(CHARACTER, "", make_event(
            "mmt", "mmt_chat", {"player": f"消息{i}", "reply": "回复"}))


def _set_counter(st, n: int) -> None:
    """摆好计数器（`n=None` = 干脆没有这个键 —— "从没写过卡"）。"""
    ws = _wstore(st)
    if n is None:
        ws.meta.pop(PANORAMA_COUNTER_KEY, None)
    else:
        ws.meta[PANORAMA_COUNTER_KEY] = n
    ws.save_meta()


def test_card_counter_counts_segments_below_threshold(tmp_path):
    """每消化成功一段 +1 并**落盘**（跨重启继续数）—— 没到 10 不调 LLM。"""
    engine, st, llm = _engine(tmp_path)
    ids = _episodes(st)
    _set_counter(st, 0)                                         # 已经写过卡 ⇒ 不许插队
    events = st.events(CHARACTER)

    out = engine._maybe_card_round(st, _wstore(st), CHARACTER, events, new_ids=ids)

    assert out is events                                        # 没写卡 ⇒ 事件流不动
    assert _wstore(st).meta[PANORAMA_COUNTER_KEY] == 1
    assert llm.panorama_calls == 0


def test_first_card_round_runs_at_once(tmp_path):
    """⭐ **第一次直接到点**（meta 里还没有计数器）—— 别让她等满 10 段才有第一张卡。"""
    card = {"habits": [{"text": "他总先问我想要哪个", "refs": ["m0001", "m0002"]}],
            "drop": [], "on_mind": None}
    engine, st, llm = _engine(tmp_path, card)
    ids = _episodes(st)
    _set_counter(st, None)

    engine._maybe_card_round(st, _wstore(st), CHARACTER, st.events(CHARACTER), new_ids=ids)

    assert [e for e in st.events(CHARACTER) if e.type == TYPE_NOTE], "第一次就该写出卡"
    assert int(_wstore(st).meta[PANORAMA_COUNTER_KEY]) == 0


def test_first_card_round_failure_is_not_swallowed(tmp_path):
    """⭐ 第一次那张卡写失败 ⇒ 计数器**停在阈值之上**（`第一张卡欠着`）——
    否则要再等 10 段, 而"第一次"这个理由已经用掉了。"""
    engine, st, llm = _engine(tmp_path, {"habits": []}, {"habits": []})   # 缺键 ⇒ 拒
    ids = _episodes(st)
    _set_counter(st, None)

    engine._maybe_card_round(st, _wstore(st), CHARACTER, st.events(CHARACTER), new_ids=ids)

    assert not [e for e in st.events(CHARACTER) if e.type == TYPE_NOTE]
    assert int(_wstore(st).meta[PANORAMA_COUNTER_KEY]) >= PANORAMA_EVERY, "第一张卡欠着"


def test_card_round_runs_at_threshold_and_resets(tmp_path):
    """数到 10 ⇒ 跑一次写卡: **note 事件进真源 → notes.json 落缓存 → 计数器归零**。"""
    card = {"habits": [{"text": "他总先问我想要哪个", "refs": ["m0001", "m0002"]}],
            "drop": [], "on_mind": {"text": "不想再隔着玻璃看", "refs": ["m0002"]}}
    engine, st, llm = _engine(tmp_path, card)
    ids = _episodes(st)
    _set_counter(st, PANORAMA_EVERY - 1)

    out = engine._maybe_card_round(st, _wstore(st), CHARACTER,
                                   st.events(CHARACTER), new_ids=ids)

    # 真源: 多了一条 note/rewrite（且返回值里就有它 —— 注入块要用新的那一份）
    assert [e for e in out if e.type == TYPE_NOTE] == \
        [e for e in st.events(CHARACTER) if e.type == TYPE_NOTE]
    notes_evs = [e for e in st.events(CHARACTER) if e.type == TYPE_NOTE]
    assert len(notes_evs) == 1 and notes_evs[0].subtype == "rewrite"
    # 缓存: notes.json 与事件流同形（真源先、缓存后）
    state = _wstore(st).read_notes()
    assert state is not None and [h.text for h in state.habits] == ["他总先问我想要哪个"]
    assert state.on_mind is not None and state.on_mind.refs == ["m0002"]
    assert int(_wstore(st).meta[PANORAMA_COUNTER_KEY]) == 0


def test_inject_brain_wires_the_card_round(tmp_path):
    """**端到端**: digest 真产出了 episode ⇒ 到点写卡 ⇒ 这一次注入块里就有新卡
    （不是"下一轮才看见" —— 写卡后事件流重读 + 笔记段重建）。"""
    card = {"habits": [{"text": "他总先问我想要哪个", "refs": ["m0001", "m0002"]}],
            "drop": [], "on_mind": None}
    engine, st, llm = _engine(
        tmp_path, card,
        episodes=[{"kind": "episode", "title": "模型店", "text": "模型店门口",
                   "tags": ["模型店"], "significance": 0.6},
                  {"kind": "episode", "title": "又路过", "text": "又路过那家店",
                   "tags": ["模型店"], "significance": 0.5}],
        decisions=[{"episode": "m0001", "decision": "add", "kind": "belief",
                    "text": "老师会等我", "subject": "sensei"},
                   {"episode": "m0002", "decision": "add", "kind": "belief",
                    "text": "模型店是他会记得的地方", "subject": "sensei"}])
    _mmt(st, 2)
    _set_counter(st, PANORAMA_EVERY - 1)

    engine._run_digest(CHARACTER, engine._session_id)          # 同步跑（不经后台线程）

    assert [e for e in st.events(CHARACTER) if e.type == TYPE_NOTE], "应写下那张卡"
    assert int(_wstore(st).meta[PANORAMA_COUNTER_KEY]) == 0
    assert "他总先问我想要哪个" in engine._brain_injection, engine._brain_injection


def test_card_round_keeps_counter_when_it_fails(tmp_path):
    """写卡失败（拒整包）⇒ **计数器不清零**（下一段再试）, 真源零改动。"""
    engine, st, llm = _engine(tmp_path, {"habits": []}, {"habits": []})   # 缺键 ⇒ 两次都拒
    ids = _episodes(st)
    _set_counter(st, PANORAMA_EVERY)

    engine._maybe_card_round(st, _wstore(st), CHARACTER, st.events(CHARACTER), new_ids=ids)

    assert not [e for e in st.events(CHARACTER) if e.type == TYPE_NOTE]
    assert not _wstore(st).notes_path.exists()
    # 没归零 = **还是"欠着一次"**（计数器照常 +1 ⇒ 下一段仍然 ≥ 阈值 ⇒ 立刻再试）
    assert int(_wstore(st).meta[PANORAMA_COUNTER_KEY]) == PANORAMA_EVERY + 1


def test_card_round_survives_dead_llm(tmp_path):
    """LLM 直接抛（调用失败）⇒ 只降级: 计数器保留、无 note 事件、不抛。"""
    engine, st, llm = _engine(tmp_path)                   # 卡片队列是空的 ⇒ 抛
    ids = _episodes(st)
    _set_counter(st, PANORAMA_EVERY)

    engine._maybe_card_round(st, _wstore(st), CHARACTER, st.events(CHARACTER), new_ids=ids)

    assert not [e for e in st.events(CHARACTER) if e.type == TYPE_NOTE]
    assert int(_wstore(st).meta[PANORAMA_COUNTER_KEY]) == PANORAMA_EVERY + 1
