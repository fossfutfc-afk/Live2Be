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
# T14: 板指针 event_seq + verbatim 索引通道 → 逐字原文（2026-09-15）
# ---------------------------------------------------------------------------

def _mmt_ev(seq, player, reply):
    return ("mmt", "chat", {"player": player, "reply": reply}, seq)


def test_event_seq_pointer_and_verbatim_resolve(tmp_path):
    """★ 板指针真的落库（不再被覆写成常量）+ 索引解析出**逐字原文**。"""
    st = _seed_store(tmp_path)
    a = {"episodes": [{
        "narration": "老师突然约我去咖啡厅, 说好久没见要请我吃甜点。",
        "title": "咖啡厅的甜点陷阱",
        "event_seq": ["9", "11"],
        # `9.p` 是 MMT 事件、没有裁决行 → 取不到原文, **静默跳过**（绝不编）;
        # 但索引本身留在 verbatim_seq 里（可追溯性不受解析成败影响）
        "verbatim": ["11.1", "9.p", "11.p"],
        "tags": ["咖啡厅", "甜点"], "significance": 0.82}]}
    b = {"decisions": [{"episode": "m0003", "decision": "touch", "target": "u0001"}],
         "evidence": [], "affection_exp_delta": 0}
    events = _events(
        _mmt(9, "你好呀", "库呼呼～老师～"),
        ("bond", "story_scene", {
            "paragraphs": [{"text": "……这块，给你。"},
                           {"text": "刚才推过来那块是唯一一块没被我动过的。"}],
            "picked": "那就谢谢了"}, 11),
    )
    res = digest_segment(st, FakeLLM(a, b), events)
    assert res.ok, res.errors
    ep = st.get(res.created[0])
    # 板指针: 条目自带 → 不再覆写成常量 interact_max(=11)
    assert ep.event_seq == [9, 11], ep.event_seq
    assert ep.verbatim_seq == ["11.1", "9.p", "11.p"], ep.verbatim_seq
    # 索引 → 逐字原文（引擎从真源取, 不是 LLM 复述的）; 解析不出的那条不进文本
    assert ep.verbatim == "刚才推过来那块是唯一一块没被我动过的。 / 那就谢谢了", ep.verbatim
    print(f"    event_seq={ep.event_seq} verbatim_seq={ep.verbatim_seq}")
    print(f"    verbatim={ep.verbatim!r}")


def test_verbatim_text_channel_wins_over_index(tmp_path):
    """★ 两条都给 → **文本优先**（用户裁决"错索引进待办"的安全前提）。

    坏索引（这里 `11.99` 越界）取不到非空原文 → 文本原样保留。
    这正是"台账做出来之前, 索引不该掌握内容"。
    """
    st = _seed_store(tmp_path)
    a = {"episodes": [{
        "narration": "她递给我一块甜点。", "title": "甜点",
        "event_seq": ["11"],
        "verbatim": "……这块，给你。",            # 文本通道
        "verbatim_seq": ["11.99"],              # 越界索引（取不到）
        "tags": ["甜点"], "significance": 0.6}]}
    b = {"decisions": [{"episode": "m0003", "decision": "touch", "target": "u0001"}],
         "evidence": [], "affection_exp_delta": 0}
    events = _events(("bond", "story_scene", {
        "paragraphs": [{"text": "……这块，给你。"}]}, 11))
    res = digest_segment(st, FakeLLM(a, b), events)
    assert res.ok, res.errors
    ep = st.get(res.created[0])
    assert ep.verbatim == "……这块，给你。", ep.verbatim   # 文本一字不动
    assert ep.verbatim_seq == ["11.99"]                   # 索引留着（可追溯）
    # 全坏索引且**无文本** → verbatim 留空（绝不编）
    st2 = _seed_store(tmp_path / "b")
    a2 = {"episodes": [{"narration": "只有坏索引", "title": "x", "event_seq": ["11"],
                        "verbatim": ["11.99"], "tags": ["t"], "significance": 0.5}]}
    res2 = digest_segment(st2, FakeLLM(a2, b), events)
    assert res2.ok, res2.errors
    ep2 = st2.get(res2.created[0])
    assert ep2.verbatim == "" and ep2.verbatim_seq == ["11.99"]
    print("    verbatim: 文本优先（越界索引不顶替）+ 无文本时留空不编")


def test_event_seq_falls_back_to_segment_constant(tmp_path):
    """没有板指针 → 回落段级常量（旧行为, 不编）。"""
    st = _seed_store(tmp_path)
    res = digest_segment(st, FakeLLM(_a_episode(), _b_ok()),
                         _events(_mmt(3, "老师", "下次再去吃甜品吧")))
    assert res.ok, res.errors
    assert st.get("m0003").event_seq == [3]            # interact_max
    assert st.get("m0003").verbatim_seq == []          # 未采集
    assert st.get("m0003").emo_shape == []             # 板不是 bond → 无键


def test_emo_shape_materialized_from_board_pointer(tmp_path):
    """★ T15: 板指针 → **板级情绪键序列**物化到节点（B 链路的唯一输入）。

    为什么物化: `Channel.gather(store, ctx)` 只拿得到节点、拿不到事件流。
    """
    st = _seed_store(tmp_path)
    a = {"episodes": [{
        "narration": "杂草屋里她第一次笑出来。", "title": "杂草屋",
        "event_seq": ["20", "22", "24"],   # 20 是 MMT → 无键; 22/24 是板
        "tags": ["杂草屋"], "significance": 0.7}]}
    b = {"decisions": [{"episode": "m0003", "decision": "touch", "target": "u0001"}],
         "evidence": [], "affection_exp_delta": 0}
    events = _events(
        _mmt(20, "在吗", "在的"),
        ("bond", "story_scene", {"paragraphs": [
            {"text": "……这里就是，我一直在照顾它们的地方。", "emotion": "expectant"},
            {"text": "（她蹲下来碰了碰叶子）", "emotion": ""},      # 空键跳过
            {"text": "它们都长得很好。", "emotion": "smile"},
        ]}, 22),
        ("bond", "story_scene", {"paragraphs": [
            {"text": "谢谢您，老师……！", "emotion": "outburst"},
            {"text": "我会好好照顾它们的。", "emotion": "strive"},
        ]}, 24),
    )
    res = digest_segment(st, FakeLLM(a, b), events)
    assert res.ok, res.errors
    ep = st.get(res.created[0])
    # 按 seq 序拼接; MMT(20) 无键; 空键跳过 —— 弧的形状保留, 不补位
    assert ep.emo_shape == ["expectant", "smile", "outburst", "strive"], ep.emo_shape
    assert ep.event_seq == [20, 22, 24]
    print(f"    emo_shape 物化: {ep.emo_shape}")


def test_emo_shape_absent_when_no_pointer(tmp_path):
    """无板指针（回落段级常量）→ 段级常量指向的若恰好是 bond, 键序列仍会物化;
    若指向 MMT → 空。**绝不编。**"""
    st = _seed_store(tmp_path)
    events = _events(("bond", "story_scene", {"paragraphs": [
        {"text": "她笑了。", "emotion": "smile"}]}, 3))
    res = digest_segment(st, FakeLLM(_a_episode(), _b_ok()), events)
    assert res.ok, res.errors
    ep = st.get(res.created[0])
    assert ep.event_seq == [3]
    assert ep.emo_shape == ["smile"]           # 回落常量指向 bond → 照样物化
    print(f"    无板指针(回落 {ep.event_seq}) → emo_shape={ep.emo_shape}")


# ---------------------------------------------------------------------------
# 板块5: 引擎候选提示（T17 后**仅提示** —— 曾为"疑似同主题 → 禁 add"的结构强制）
# ---------------------------------------------------------------------------

def _cat_store(tmp_path) -> WikiStoreV2:
    """带"猫"tags 的 belief——关键词降级通道下, 猫相关 episode 必被标注。

    id: episode m0001 / belief m0002（A 轮新 episode 顺延 m0003）。
    """
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(make_node("episode", narration="喂猫旧事", event_seq=[2]))
    st.add(make_node("belief", content="老师会记得给猫带猫粮", subject="老师与猫的约定",
                     epistemic="inferred_belief", significance=0.9, tags=["猫"],
                     links=["m0001"], event_seq=[2]))
    return st


def test_high_candidate_no_longer_forces_touch_update(tmp_path):
    """★ T17（2026-09-15）: **候选降为提示, LLM 判 add 不再被拒**。

    旧行为: 候选 ≥ `CAND_HIGH` → 该 episode 出 `add` 整行作废 → 引擎反馈重试。
    而那个阈值从未标定过、实测两模型下候选 **6/6 全越线** → 结构强制把
    "全部分侧面"判成"同一件事" → **新认知永远长不出来**（Q11/Q31/Q32 已裁）。

    现在: 候选照样摆给 LLM（**输入里仍能看到**），但 `add` 不触发任何拒绝/重试。
    """
    st = _cat_store(tmp_path)
    llm = FakeLLM(
        _a_episode(narration="老师带猫粮来喂猫, 猫绕着我转了两圈"),
        {"decisions": [
            {"episode": "m0003", "decision": "add", "kind": "belief",
             "subject": "猫", "content": "老师会带猫粮来喂猫",
             "note": "与候选只是字面像, 不是同一件事"},
         ], "evidence": [], "affection_exp_delta": 5},
    )
    events = _events(_mmt(3, "x", "猫粮带来了"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.llm_calls == 2                          # A + B（**没有**拒绝重试）
    # 候选提示仍在输入里（只是不再带"禁 add"的措辞）
    assert "候选" in llm.calls[1][1]["content"]
    assert "禁 add" not in llm.calls[1][1]["content"]
    # add 真的落地了（新认知长出来了——这正是删阈值的直接目的）
    added = [n for n in st.all() if n.kind == "belief" and n.content == "老师会带猫粮来喂猫"]
    assert added, "add 被引擎拦掉了——结构强制没删干净"
    print("    候选仅提示: add 不再被拒（新认知能长出来）")


def test_no_candidate_when_unrelated(tmp_path):
    """无关键词关联 → 无候选提示行 → LLM 自由 add（本来也不再有强制）。"""
    st = _cat_store(tmp_path)
    llm = FakeLLM(
        _a_episode(narration="老师送我一盆新的杂草", tags=("杂草",)),
        {"decisions": [
            {"episode": "m0003", "decision": "add", "kind": "belief",
             "subject": "杂草", "content": "杂草是遥香安心的事物"},
         ], "evidence": [], "affection_exp_delta": 3})
    events = _events(_mmt(3, "x", "这盆杂草送给你"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert "→ 候选" not in llm.calls[1][1]["content"]         # 无候选提示行
    bel = st.get("m0004")                              # add 成功（m0003 episode + m0004 belief）
    assert bel.kind == "belief"


# ---------------------------------------------------------------------------
# MMT 专则: 玩家画像条目（kind=experience, subject=player）
# ---------------------------------------------------------------------------

def test_player_portrait_entry_lands_and_hides_from_round_b(tmp_path):
    """A 轮画像条目 → subject=player experience 落库; 不进本轮认知列表（B 只组织 episode）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    llm = FakeLLM(
        {"episodes": [
            {"narration": "老师说下周放假带我去看烟火大会, 我紧张得直结巴还是答应了",
             "title": "烟火大会之约", "verbatim": "下周放假, 一起去看烟火吧",
             "tags": ["约定", "烟火"], "significance": 0.85},
            {"kind": "experience", "pattern": "玩家的生日是 5 月 20 日",
             "verbatim": "我生日是 5 月 20 日哦", "tags": ["玩家生日"],
             "significance": 0.7},
        ]},
        {"decisions": [
            {"episode": "m0001", "decision": "add", "kind": "belief",
             "subject": "和老师的约定", "content": "老师会认真对待与我的约定"},
         ], "evidence": [], "affection_exp_delta": 15})
    events = _events(_mmt(3, "老师", "下周放假, 一起去看烟火吧"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.created == ["m0001"]                    # episode 正常建
    p = st.get("e0001")                                # 画像条目 → subject=player experience
    assert p is not None and p.kind == "experience"
    assert p.subject == "player" and p.pattern.startswith("玩家的生日")
    assert p.verbatim == "我生日是 5 月 20 日哦"        # 原话直存（无 episode 载体）
    assert p.event_seq == [3] and p.segment_id == "seg-3"
    # B 的认知列表不含刚建的画像条目（冷启动提示仍在 = 无认知可组织）
    b_user = llm.calls[1][1]["content"]
    assert "玩家的生日" not in b_user
    assert "尚无稳定认知" in b_user or "u0001" in b_user  # 画像被排除后无旧认知
    assert "m0001" in b_user                           # episode 摘要正常进 B


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


def test_affection_negative_passes_through(tmp_path):
    """★ 2026-09-13: delta 下界由 0 放开到 -100——关系能变坏（§3.3.3）。

    旧行为: -30 被夹成 0（关系只能变好）。新行为: -30 原样透出。
    """
    st = _seed_store(tmp_path)
    llm = FakeLLM({"episodes": []},
                  {"decisions": [], "evidence": [], "affection_exp_delta": -30})
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")))
    assert res.ok and res.affection_delta == -30


def test_affection_negative_clamped_at_floor(tmp_path):
    """下界对称: -999 夹到 -100（单段不能暴跌穿底）。"""
    st = _seed_store(tmp_path)
    llm = FakeLLM({"episodes": []},
                  {"decisions": [], "evidence": [], "affection_exp_delta": -999})
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")))
    assert res.ok and res.affection_delta == -100


# ---------------------------------------------------------------------------
# aff_at_encoding: 编码时好感快照落 episode 节点（§3.3.3）
# ---------------------------------------------------------------------------

def test_aff_at_encoding_lands_on_episode_nodes(tmp_path):
    """传入 → 落进**新建的 episode 节点**; 快照语义 = 写入时定。"""
    st = _seed_store(tmp_path)
    llm = FakeLLM(_a_episode(), _b_ok())
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")),
                         aff_at_encoding=-0.42)
    assert res.ok and res.created, "应建出 episode"
    ep = st.get(res.created[0])
    assert ep.aff_at_encoding == -0.42
    print(f"    aff_at_encoding: 落节点 {res.created[0]} = {ep.aff_at_encoding}")


def test_aff_at_encoding_absent_when_not_passed(tmp_path):
    """不传（CLI/旧调用方）→ 字段**不落库**, 与 0.0（中性）区分。"""
    st = _seed_store(tmp_path)
    llm = FakeLLM(_a_episode(), _b_ok())
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")))
    assert res.ok and res.created
    ep = st.get(res.created[0])
    assert ep.aff_at_encoding is None
    assert "aff_at_encoding" not in ep.to_dict()
    print("    aff_at_encoding: 未传 → None（不落库, 不冒充中性）")


def test_aff_at_encoding_zero_is_written(tmp_path):
    """0.0 是真值（当时关系中性）——**必须落库**, 不能被空值省略规则吃掉。"""
    st = _seed_store(tmp_path)
    llm = FakeLLM(_a_episode(), _b_ok())
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")), aff_at_encoding=0.0)
    ep = st.get(res.created[0])
    assert ep.aff_at_encoding == 0.0
    assert "aff_at_encoding" in ep.to_dict()
    print("    aff_at_encoding: 0.0 落库（中性 ≠ 未采集）")


# ---------------------------------------------------------------------------
# 情绪三标量 emo_int / emo_span / emo_valence 落到 episode 节点（§3.3.3）
# ---------------------------------------------------------------------------

def test_emo_scalars_land_on_episode_nodes(tmp_path):
    """Round A 给了 → 必须一路落到节点（契约清洗 → make_node → 落盘）。"""
    st = _seed_store(tmp_path)
    a = _a_episode()
    a["episodes"][0]["emo_int"] = 0.85
    a["episodes"][0]["emo_span"] = 0.9
    a["episodes"][0]["emo_valence"] = -0.4
    llm = FakeLLM(a, _b_ok())
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")))
    assert res.ok and res.created
    ep = st.get(res.created[0])
    assert ep.emo_int == 0.85, f"emo_int 未落节点: {ep.emo_int}"
    assert ep.emo_span == 0.9, f"emo_span 未落节点: {ep.emo_span}"
    assert ep.emo_valence == -0.4, f"emo_valence 未落节点: {ep.emo_valence}"
    print(f"    emo_*: 落节点 {res.created[0]} int={ep.emo_int} "
          f"span={ep.emo_span} val={ep.emo_valence}")


def test_emo_scalars_absent_when_llm_silent(tmp_path):
    """Round A 没给 → 节点上必须是 None（不是 0.0）。"""
    st = _seed_store(tmp_path)
    llm = FakeLLM(_a_episode(), _b_ok())
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")))
    ep = st.get(res.created[0])
    assert ep.emo_int is None and ep.emo_span is None and ep.emo_valence is None
    d = ep.to_dict()
    for f in ("emo_int", "emo_span", "emo_valence"):
        assert f not in d, f"{f} 不该落库"
    print("    emo_*: LLM 没给 → None（不冒充'毫无波澜'）")


def test_emo_scalars_zero_is_written(tmp_path):
    """0.0 是合法值（事务性寒暄 / 全程一个调子 / 中性色彩）——必须落库。"""
    st = _seed_store(tmp_path)
    a = _a_episode()
    for f in ("emo_int", "emo_span", "emo_valence"):
        a["episodes"][0][f] = 0.0
    llm = FakeLLM(a, _b_ok())
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")))
    ep = st.get(res.created[0])
    assert ep.emo_int == 0.0 and ep.emo_span == 0.0 and ep.emo_valence == 0.0
    d = ep.to_dict()
    for f in ("emo_int", "emo_span", "emo_valence"):
        assert f in d, f"{f} 0.0 应落库"
    print("    emo_*: 0.0 落库（≠ 未采集）")

# ---------------------------------------------------------------------------
# 情绪标尺注入 Round A（§3.3.2）
# ---------------------------------------------------------------------------

_LEX = {
    "smile": {"comment": "眯眼开心: 发自心底的开心", "eg": "", "path": "03"},
    "outburst": {"comment": "失控瞪眼: 终极失控, 角色灵魂表情", "eg": "", "path": "13"},
    "tease": {"comment": "带调戏意味的微笑", "eg": "", "path": "10"},
}


def _bond(seq, keys):
    """一板: payload.paragraphs[i].emotion = 键（其余字段 digest 不关心）。"""
    return ("bond", "story_scene",
            {"paragraphs": [{"text": f"第{i}条", "emotion": k}
                            for i, k in enumerate(keys, 1)]}, seq)


def test_segment_emotion_keys_order_and_dedup():
    from core.brain.wiki_v2.digest import _segment_emotion_keys
    evs = _events(_bond(1, ["tease", "smile"]), _bond(2, ["smile", "outburst"]),
                  _mmt(3, "hi", "yo"))
    assert _segment_emotion_keys(evs) == ["tease", "smile", "outburst"]
    # 坏结构 / 缺字段 → 跳过, 不抛
    evs2 = _events(("bond", "story_scene", {"paragraphs": ["坏", {"no": 1}, None]}, 1),
                   ("bond", "story_scene", {}, 2))
    assert _segment_emotion_keys(evs2) == []
    print("    _segment_emotion_keys: 首次出现顺序 + 去重; 坏结构不抛")


def test_emotion_scale_reaches_round_a(tmp_path):
    """★ 给了词表 → Round A 的 user 里出现**只含本段出现的键**的标尺。"""
    st = _seed_store(tmp_path)
    llm = FakeLLM(_a_episode(), _b_ok())
    res = digest_segment(st, llm, _events(_bond(3, ["smile", "outburst"])),
                         emotion_lexicon=_LEX)
    assert res.ok, res.errors
    user_a = llm.calls[0][1]["content"]         # calls[0] = Round A
    assert "【本段情绪标尺】" in user_a, "标尺未注入 Round A"
    assert "outburst: 失控瞪眼" in user_a
    assert "smile: 眯眼开心" in user_a
    assert "tease" not in user_a, "未在本段出现的键被注入（应只注出现的键）"
    print("    Round A: 标尺注入且只含本段出现的键（tease 未出现 → 不注）")


def test_emotion_scale_absent_without_lexicon(tmp_path):
    """不给词表 → 不注入, 但 digest 照跑（宁缺勿错）。"""
    st = _seed_store(tmp_path)
    llm = FakeLLM(_a_episode(), _b_ok())
    res = digest_segment(st, llm, _events(_bond(3, ["smile"])))
    assert res.ok, res.errors
    assert "【本段情绪标尺】" not in llm.calls[0][1]["content"]
    print("    Round A: 无词表 → 不注标尺, digest 照跑")


def test_emotion_scale_absent_when_segment_has_no_labels(tmp_path):
    """本段没有任何情绪标注（如纯 MMT 段）→ 标尺为空, 不注入空块。"""
    st = _seed_store(tmp_path)
    llm = FakeLLM(_a_episode(), _b_ok())
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")),
                         emotion_lexicon=_LEX)
    assert res.ok, res.errors
    assert "【本段情绪标尺】" not in llm.calls[0][1]["content"]
    print("    Round A: 本段无标注 → 无标尺块（不注空块）")


# ---------------------------------------------------------------------------
# 剧情时间: 写路径时序（§4.11 —— I-a 先推进再 stamp / I-b Round B 不许碰）
# ---------------------------------------------------------------------------















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
