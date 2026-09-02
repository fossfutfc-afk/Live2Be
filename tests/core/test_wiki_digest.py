"""digest.py 两轮管线测试（板块 4a）——假 LLM 按序吐 Round A / Round B 响应。"""
from core.brain.wiki_v2 import WikiStoreV2, make_node
from core.brain.wiki_v2.digest import digest_segment
from core.brain.wiki_v2.evolution import EvolutionLog
from core.session import make_event


class FakeLLM:
    """假 LLM: 按序吐出预置响应（A 轮/反馈/B 轮…）; 记录调用。"""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, **kw):
        self.calls.append(messages)
        if self.responses:
            return self.responses.pop(0)
        raise RuntimeError("responses 耗尽")


def _events(*items):
    """合成事件流: (type, subtype, payload, seq) 元组列表 → Event 列表。"""
    out = []
    for typ, sub, payload, seq in items:
        e = make_event(typ, sub, payload)
        e.seq = seq
        out.append(e)
    return out


def _seed_store(tmp_path) -> WikiStoreV2:
    """预置: m0001 episode + m0002 belief + e0001 experience（含 link）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(make_node("episode", narration="天台夜谈", event_seq=[2], ts="2026-09-01T10:00:00",
                     links=["m0002"]))
    st.add(make_node("belief", content="老师是第一个不会嫌弃我的人", subject="sensei",
                     epistemic="inferred_belief", significance=0.9,
                     links=["m0001"], event_seq=[2]))
    st.add(make_node("experience", pattern="提到工作繁忙", subject="sensei",
                     significance=0.85, links=["m0001"], event_seq=[2]))
    return st


def _mmt(seq, player, reply):
    return ("mmt", "chat", {"player": player, "reply": reply}, seq)


def _a_episode(narration="老师请我吃了甜品，还说下次再去", sig=0.8, title="甜点之约",
               verbatim="下次再去吃甜品吧", tags=("甜品", "老师")):
    return {"episodes": [
        {"narration": narration, "title": title, "verbatim": verbatim,
         "tags": list(tags), "significance": sig}]}


def _b_ok(**over):
    out = {"decisions": [
        {"episode": "m0003", "decision": "update", "target": "u0001",
         "patch": {"content": "老师会记得我的喜好——连甜品店也会挑好", "significance": 0.95}},
        {"episode": "m0003", "decision": "add", "kind": "experience",
         "subject": "sensei", "pattern": "老师会带我去吃甜品", "example": "「这家店不错吧」"},
    ], "evidence": [
        {"function": "fe", "confidence": 0.85, "quote": "下次再去吃甜品吧"},
        {"function": "ni", "confidence": 0.5, "quote": "低置信度应该被丢"},
    ], "affection_exp_delta": 30}
    out.update(over)
    return out


# ---------------------------------------------------------------------------
# 增量 / 无新增
# ---------------------------------------------------------------------------

def test_no_new_events_no_llm_call(tmp_path):
    st = _seed_store(tmp_path)
    st.meta["digested_seq"] = 99
    llm = FakeLLM()
    res = digest_segment(st, llm, _events(_mmt(1, "hi", "hello")))
    assert res.ok and res.llm_calls == 0
    assert res.created == []


def test_affection_markers_excluded_from_digest_input(tmp_path):
    st = _seed_store(tmp_path)
    llm = FakeLLM({"episodes": []},
                  {"decisions": [], "evidence": [], "affection_exp_delta": 0})
    events = _events(
        _mmt(3, "老师好", "啊、老师好……"),
        ("affection", "digest", {"delta": 5}, 4),
    )
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.llm_calls == 2                          # A 空也跑 B（affection/evidence 归 B）
    assert res.affection_delta == 0
    assert st.digested_seq == 4


# ---------------------------------------------------------------------------
# 完整通过: A 建 episode → B touch/update/add → evidence/好感/水位/log
# ---------------------------------------------------------------------------

def test_full_pipeline(tmp_path):
    st = _seed_store(tmp_path)
    llm = FakeLLM(_a_episode(), _b_ok())
    events = _events(_mmt(3, "老师", "下次再去吃甜品吧"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.llm_calls == 2
    # A: episode 建好, 引擎字段归属
    assert res.created == ["m0003"]
    ep = st.get("m0003")
    assert ep.kind == "episode" and ep.event_seq == [3]
    assert ep.segment_id == "seg-3" and ep.ts and ep.title == "甜点之约"
    # B: update → 认知改写 + history 溯源; add → 新 experience 链回 episode
    bel = st.get("m0002")
    assert bel.significance == 0.95
    assert bel.history and bel.history[0]["episode_id"] == "m0003"
    exp = st.get("e0002")
    assert exp.kind == "experience" and exp.pattern == "老师会带我去吃甜品"
    assert exp.count == 1                              # links = [m0003]
    assert "e0002" in ep.links and "m0002" in ep.links
    # evidence: 低置信度丢弃
    assert [e["function"] for e in res.evidence] == ["fe"]
    assert res.affection_delta == 30
    assert st.digested_seq == 3
    # evolution log（apply_decisions 追加）
    entries = EvolutionLog.for_store(st).read()
    assert [e["action"] for e in entries] == ["update", "add"]


def test_touch_decision_links_only(tmp_path):
    st = _seed_store(tmp_path)
    llm = FakeLLM(
        _a_episode(narration="又和老师在天台安静坐着"),
        {"decisions": [{"episode": "m0003", "decision": "touch", "target": "u0001",
                        "note": "又是安静的陪伴"}],
         "evidence": [], "affection_exp_delta": 5})
    events = _events(_mmt(3, "x", "天台很安静"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    bel = st.get("m0002")
    assert bel.history == []                           # touch 不改内容
    assert "m0003" in bel.links                        # 只连边


# ---------------------------------------------------------------------------
# 冷启动: 无旧记忆 → B 只能 add（belief 路径: epistemic 引擎归属 + 先链后入仓）
# ---------------------------------------------------------------------------

def test_cold_start_add_belief(tmp_path):
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")   # 空库
    llm = FakeLLM(
        _a_episode(narration="老师帮我把杂草搬回了家"),
        {"decisions": [
            {"episode": "m0001", "decision": "add", "kind": "belief",
             "subject": "老师对我的照顾", "content": "老师会记得我随口提过的事",
             "tags": ["老师"], "significance": 0.85}],
         "evidence": [], "affection_exp_delta": 10})
    events = _events(_mmt(3, "x", "杂草我帮你搬"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.created == ["m0001"]
    bel = st.get("m0002")                              # 空库 belief → m0002
    assert bel.kind == "belief"
    assert bel.epistemic == "inferred_belief"          # 引擎归属, 非 LLM
    assert "m0001" in bel.links                        # 先链后入仓（validate 通过）
    assert "m0002" in st.get("m0001").links            # 反向边
    # 冷启动 B 输入提示"尚无稳定认知"
    assert "尚无稳定认知" in llm.calls[1][1]["content"]


# ---------------------------------------------------------------------------
# deadline: 全程时间预算（撞上 → 回滚, 水位不推进）
# ---------------------------------------------------------------------------

def test_deadline_budget_fails_atomically(tmp_path):
    st = _seed_store(tmp_path)

    class SlowLLM:
        def __init__(self, responses):
            self.responses = list(responses)
            self.calls = 0

        def chat(self, messages, **kw):
            import time
            time.sleep(0.2)                            # 每次调用都超预算
            self.calls += 1
            if self.responses:
                return self.responses.pop(0)
            raise RuntimeError("responses 耗尽")

    before = {n.id: n.to_dict() for n in st.all()}
    llm = SlowLLM([_a_episode(), _b_ok()])
    events = _events(_mmt(3, "x", "y"))
    res = digest_segment(st, llm, events, deadline_seconds=0.05)
    assert not res.ok
    assert any("时间预算" in e for e in res.errors)
    after = {n.id: n.to_dict() for n in st.all()}
    assert after == before                              # A 建的节点也回滚
    assert st.digested_seq == 0


def test_budget_check_between_rounds(tmp_path):
    """A 慢到吞掉预算 → B 的预检直接中止, 不发起 B 调用。"""
    st = _seed_store(tmp_path)
    calls = []

    class SlowALM:
        def chat(self, messages, **kw):
            import time
            time.sleep(0.25)                            # A 超预算
            calls.append(messages)
            return _a_episode()

    res = digest_segment(st, SlowALM(), _events(_mmt(3, "x", "y")),
                         deadline_seconds=0.1)
    assert not res.ok and any("时间预算" in e for e in res.errors)
    assert len(calls) == 1                              # B 未发起
    assert st.digested_seq == 0


# ---------------------------------------------------------------------------
# 反馈回灌（feedback 语义: assistant 原文 + 错误, 同一上下文）
# ---------------------------------------------------------------------------

def test_round_a_rejected_retried_with_feedback(tmp_path):
    st = _seed_store(tmp_path)
    llm = FakeLLM(
        {"episodes": [{"title": "缺正文"}]},            # parse 拒绝（无 narration）
        _a_episode(),
        _b_ok(),
    )
    events = _events(_mmt(3, "x", "y"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.llm_calls == 3                          # A1(拒) + A2(过) + B
    # 反馈追加在同一上下文: system,user,assistant,user(反馈)
    msgs = llm.calls[1]
    assert len(msgs) == 4 and msgs[2]["role"] == "assistant"
    assert "引擎校验反馈" in msgs[3]["content"]
    assert st.digested_seq == 3


def test_round_b_rejected_retried_with_feedback(tmp_path):
    st = _seed_store(tmp_path)
    llm = FakeLLM(
        _a_episode(),
        {"decisions": [], "evidence": [], "affection_exp_delta": 0},   # 漏 m0003 → 拒
        _b_ok(),
    )
    events = _events(_mmt(3, "x", "y"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.llm_calls == 3
    assert "引擎校验反馈" in llm.calls[2][-1]["content"]
    assert st.digested_seq == 3


def test_b_rejected_twice_fails_atomically(tmp_path):
    st = _seed_store(tmp_path)
    before = {n.id: n.to_dict() for n in st.all()}
    bad_b = {"decisions": [], "evidence": [], "affection_exp_delta": 0}
    llm = FakeLLM(_a_episode(), dict(bad_b), dict(bad_b))
    events = _events(_mmt(3, "x", "y"))
    res = digest_segment(st, llm, events)
    assert not res.ok
    assert any("未覆盖" in e for e in res.errors)
    after = {n.id: n.to_dict() for n in st.all()}
    assert after == before                             # 原子: A 的 episode 也回滚
    assert st.digested_seq == 0                        # 水位不推进 → 可重算


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
    assert not res.ok and llm.calls == 3               # 调用级重试 3 次后降级
    assert st.digested_seq == 0
    assert len(st.all()) == 3                          # 无残留


# ---------------------------------------------------------------------------
# 好感 clamp / 空 A
# ---------------------------------------------------------------------------

def test_affection_clamped(tmp_path):
    st = _seed_store(tmp_path)
    llm = FakeLLM({"episodes": []},
                  {"decisions": [], "evidence": [], "affection_exp_delta": 999})
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")))
    assert res.ok and res.affection_delta == 100


# ---------------------------------------------------------------------------
# 幂等: 崩溃窗口重跑（落盘成功但水位未推进）不双写
# ---------------------------------------------------------------------------

def test_dedupe_on_rerun(tmp_path):
    st = _seed_store(tmp_path)
    events = _events(_mmt(3, "x", "y"))
    ok = (_a_episode(), _b_ok())
    st.meta["digested_seq"] = 0
    res1 = digest_segment(st, FakeLLM(*ok), events)
    assert res1.ok
    n_before = len(st.all())
    st.meta["digested_seq"] = 0                        # 模拟崩溃窗口: 落盘但水位没推进
    res2 = digest_segment(st, FakeLLM(*ok), events)
    assert res2.ok
    assert len(st.all()) == n_before                   # 同内容 episode 去重, 不双写
    assert st.digested_seq == 3
