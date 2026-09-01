"""digest.py 管线测试（AGENT_BRAIN.md §3 / M3）——假 LLM + 合成事件流。"""
from core.brain.wiki_v2 import WikiStoreV2, make_node
from core.brain.wiki_v2.digest import digest_segment
from core.brain.wiki_v2.evolution import EvolutionLog
from core.session import make_event


class FakeLLM:
    """假 LLM: 按序吐出预置响应; 记录调用。"""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, **kw):
        self.calls.append(messages)
        if self.responses:
            return self.responses.pop(0)
        raise RuntimeError("responses 耗尽")

    def raise_for(self, error):
        self.responses.insert(0, error)


def _events(*items):
    """合成事件流: (type, subtype, payload, seq) 元组列表 → Event 列表。"""
    out = []
    for typ, sub, payload, seq in items:
        e = make_event(typ, sub, payload)
        e.seq = seq
        out.append(e)
    return out


def _seed_store(tmp_path) -> WikiStoreV2:
    """预置子图: m0001 episode + m0002 belief + e0001 experience（含 link）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(make_node("episode", narration="天台夜谈", event_seq=[2], ts="2026-09-01T10:00:00",
                     links=["m0002"]))
    st.add(make_node("belief", content="老师是第一个不会嫌弃我的人", subject="sensei",
                     epistemic="inferred_belief", significance=0.9,
                     links=["m0001"], event_seq=[2]))
    st.add(make_node("experience", pattern="提到工作繁忙", subject="sensei",
                     significance=0.85, links=["m0001"], event_seq=[2]))
    # 注: e0001 提到 0.85 保证进珍贵保底 → 子图确定含它（accrue 目标必须在子图内）
    return st


def _mmt(seq, player, reply):
    return ("mmt", "chat", {"player": player, "reply": reply}, seq)


def _bond(seq, text):
    return ("bond", "story_scene",
            {"input": "", "paragraphs": [{"text": text, "emotion": "shy"}]}, seq)


# ---------------------------------------------------------------------------
# 增量 / 无新增
# ---------------------------------------------------------------------------

def test_no_new_events_no_llm_call(tmp_path):
    st = _seed_store(tmp_path)
    st.meta["digested_seq"] = 99
    llm = FakeLLM()
    res = digest_segment(st, llm, _events(_mmt(1, "hi", "hello")))
    assert res.ok and res.llm_calls == 0
    assert res.revision is None and res.created == []


def test_affection_markers_excluded_from_digest_input(tmp_path):
    st = _seed_store(tmp_path)
    llm = FakeLLM({"revisions": [], "evidence": [], "affection_exp_delta": 0})
    events = _events(
        _mmt(3, "老师好", "啊、老师好……"),
        ("affection", "digest", {"delta": 5}, 4),
    )
    res = digest_segment(st, llm, events)
    assert res.ok
    assert res.affection_delta == 0                     # affection 事件本身不进 digest
    assert st.digested_seq == 4


# ---------------------------------------------------------------------------
# 完整通过: create + accrue + update + 好感 + evidence
# ---------------------------------------------------------------------------

def test_full_pipeline(tmp_path):
    st = _seed_store(tmp_path)
    llm = FakeLLM({
        "revisions": [
            {"action": "create", "ref": "n1", "entry": {
                "kind": "episode", "narration": "老师请我吃了甜品，还说下次再去",
                "event_seq": [3], "links": ["m0002"]}},
            {"action": "accrue", "id": "e0001",
             "occurrence": {"episode_ref": "n1", "example": "「这家店的甜品不错」"}},
            {"action": "update", "id": "m0002", "patch": {"significance": 0.95}},
        ],
        "evidence": [
            {"function": "fe", "confidence": 0.85, "quote": "老师说下次再去"},
            {"function": "ni", "confidence": 0.5, "quote": "低置信度应该被丢"},
        ],
        "affection_exp_delta": 30,
    })
    events = _events(_mmt(3, "老师", "下次再去吃甜品吧"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    # 条目 + 修订落盘
    assert len(res.created) == 1
    ep = st.get(res.created[0])
    assert ep.kind == "episode" and ep.event_seq == [3]
    assert ep.segment_id == "seg-3" and ep.ts
    exp = st.get("e0001")
    assert exp.links == ["m0001", "m0003"] and exp.event_seq == [2, 3]
    assert exp.count == 2
    assert st.get("m0002").significance == 0.95
    # evidence: 低置信度丢弃
    assert [e["function"] for e in res.evidence] == ["fe"]
    # 好感 + 水位
    assert res.affection_delta == 30
    assert st.digested_seq == 3
    # evolution log
    entries = EvolutionLog.for_store(st).read()
    assert [e["action"] for e in entries] == ["create", "accrue", "update"]


# ---------------------------------------------------------------------------
# 校验反馈重试
# ---------------------------------------------------------------------------

def test_rejected_package_retried_with_feedback(tmp_path):
    st = _seed_store(tmp_path)
    llm = FakeLLM(
        {"revisions": [{"action": "create", "entry": {
            "kind": "episode", "narration": "孤立日常", "event_seq": [3]}}],
         "evidence": [], "affection_exp_delta": 0},     # 连接裁定违反 → 拒绝
        {"revisions": [{"action": "create", "entry": {
            "kind": "episode", "narration": "孤立日常", "event_seq": [3],
            "links": ["m0002"]}}],                       # 修正后通过
         "evidence": [], "affection_exp_delta": 0},
    )
    events = _events(_mmt(3, "x", "y"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.llm_calls == 2
    # 第二次调用带了引擎反馈
    assert "引擎校验反馈" in llm.calls[1][1]["content"]
    assert st.digested_seq == 3


def test_feedback_retry_exhausted_fails_atomically(tmp_path):
    st = _seed_store(tmp_path)
    before = {n.id: n.to_dict() for n in st.all()}
    bad = {"revisions": [{"action": "create", "entry": {
        "kind": "episode", "narration": "孤立日常", "event_seq": [3]}}],
        "evidence": [], "affection_exp_delta": 0}
    llm = FakeLLM(bad, bad)
    events = _events(_mmt(3, "x", "y"))
    res = digest_segment(st, llm, events)
    assert not res.ok and any("连接裁定" in e for e in res.errors)
    after = {n.id: n.to_dict() for n in st.all()}
    assert after == before                              # 原子: 无残留
    assert st.digested_seq == 0                         # 水位不推进 → 可重算


def test_llm_call_failure_degrades(tmp_path):
    st = _seed_store(tmp_path)

    class BrokenLLM:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kw):
            self.calls += 1
            raise RuntimeError("api down")

    llm = BrokenLLM()
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")))
    assert not res.ok and llm.calls == 3                # 重试 3 次后降级
    assert st.digested_seq == 0


# ---------------------------------------------------------------------------
# 引擎准备: event_seq 校验 / 好感 clamp
# ---------------------------------------------------------------------------

def test_event_seq_falls_back_to_segment_max(tmp_path):
    st = _seed_store(tmp_path)
    llm = FakeLLM({"revisions": [
        {"action": "create", "entry": {
            "kind": "episode", "narration": "老师送了暖宝宝",
            "event_seq": [999], "links": ["m0002"]}},    # 999 不在本段 → 落回
    ], "evidence": [], "affection_exp_delta": 0})
    events = _events(_mmt(3, "x", "y"))
    res = digest_segment(st, llm, events)
    assert res.ok
    ep = st.get(res.created[0])
    assert ep.event_seq == [3]


def test_affection_clamped(tmp_path):
    st = _seed_store(tmp_path)
    llm = FakeLLM({"revisions": [], "evidence": [],
                   "affection_exp_delta": 999})
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")))
    assert res.ok and res.affection_delta == 100
    llm2 = FakeLLM({"revisions": [], "evidence": [],
                    "affection_exp_delta": -5})
    res2 = digest_segment(st, llm2, _events(_mmt(4, "x", "y")))
    assert res2.ok and res2.affection_delta == 0


# ---------------------------------------------------------------------------
# 幂等: 崩溃窗口重跑（落盘成功但水位未推进）不双写
# ---------------------------------------------------------------------------

def test_dedupe_on_rerun(tmp_path):
    st = _seed_store(tmp_path)
    ok_resp = {"revisions": [
        {"action": "create", "ref": "n1", "entry": {
            "kind": "episode", "narration": "老师请我吃了甜品", "event_seq": [3],
            "links": ["m0002"]}},
    ], "evidence": [], "affection_exp_delta": 10}
    events = _events(_mmt(3, "x", "y"))
    # 第一次: 模拟"落盘成功但水位没推进"——手动还原 meta
    st.meta["digested_seq"] = 0
    res1 = digest_segment(st, FakeLLM(ok_resp), events)
    assert res1.ok
    n_before = len(st.all())
    # 第二次: 同一段重跑 → dedupe 命中, 不双写
    res2 = digest_segment(st, FakeLLM(ok_resp), events)
    assert res2.ok
    assert len(st.all()) == n_before
    assert st.digested_seq == 3
