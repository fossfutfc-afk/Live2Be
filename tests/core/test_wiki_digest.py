"""digest.py 两轮管线测试（板块 4a）——假 LLM 按序吐 Round A / Round B 响应。

⚠️ 2026-09-25 起每段是**四步**（`R1 → R4 → R2 → R3`，§8）: 本文件的 `FakeLLM` 按
**task 身份**把 R4（`digest.close`）短路成标准空包（"这一段没有约定的事"），
所以位置队列里仍然只排 **A / B** 两轮 —— 与产品桩（`tests/stub_tasks.py`）同一口径。
要测 R4 本身 → `tests/core/test_round_close.py`。
"""
from core.brain import WikiStoreV2, make_node
from core.brain.digest import digest_segment
from core.brain.evolution import EvolutionLog
from core.session import make_event
from llm import task_labels as T

#: R4 的标准应答（"这一段没有约定的事"）—— 与 `tests/stub_tasks.py` 同形
CLOSE_EMPTY = {"add": [], "close": []}


class FakeLLM:
    """假 LLM: 按序吐出预置响应（A 轮/反馈/B 轮…）; 记录调用。

    R4（`task == digest.close`）与 R3（`digest.attr`）**不进位置队列** —— 按 task 短路成
    标准空包（"这一段没有约定的事 / 没有可归属的"）。`close_calls` 单独记,
    免得"R4 有没有真的被调"要靠数位置。
    """

    def __init__(self, *responses, close=None):
        self.responses = list(responses)
        self.calls = []
        self.close = CLOSE_EMPTY if close is None else close
        self.close_calls = 0

    def chat(self, messages, **kw):
        task = kw.get("task")
        if task == T.DIGEST_CLOSE:
            self.close_calls += 1
            return self.close
        if task == T.DIGEST_ATTR:
            return {"attributions": []}
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
    """预置: m0001 episode 支撑 m0002 belief + e0001 experience（边走边表）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(make_node("episode", text="天台夜谈", event_seq=[2], ts="2026-09-01T10:00:00"))
    st.add(make_node("belief", text="老师是第一个不会嫌弃我的人", subject="sensei",
                     significance=0.9, event_seq=[2]))
    st.add(make_node("experience", text="提到工作繁忙", subject="sensei",
                     significance=0.85, event_seq=[2]))
    st.add_edge("supports", "m0001", "m0002")
    st.add_edge("supports", "m0001", "e0001")
    return st


def _mmt(seq, player, reply):
    return ("mmt", "chat", {"player": player, "reply": reply}, seq)


def _a_episode(text="老师请我吃了甜品，还说下次再去", sig=0.8, title="甜点之约",
               verbatim=("3.1",), tags=("甜品", "老师")):
    """⚠️ `verbatim` 从 2026-09-29 起是**记录行号**（文本通道退役）——
    默认那条指的正是 `_events(_mmt(3, …))` 的回复记录 `[3.1]`。"""
    ep = {"text": text, "title": title,
          "tags": list(tags), "significance": sig}
    if verbatim:
        ep["verbatim"] = list(verbatim)
    return {"episodes": [ep]}


def _b_ok(**over):
    out = {"decisions": [
        {"episode": "m0003", "decision": "update", "target": "u0001",
         "patch": {"text": "老师会记得我的喜好——连甜品店也会挑好", "significance": 0.95}},
        {"episode": "m0003", "decision": "add", "kind": "belief",
         "subject": "sensei", "text": "老师会带我去吃甜品", "example": "「这家店不错吧」"},
    ], "affection_exp_delta": 30}
    out.update(over)
    return out


def _mmt_at(seq, ts, player="老师", reply="嗯"):
    """一条带**指定时刻**的 mmt 事件（④-① 的用例要能区分先后）。"""
    e = make_event("mmt", "chat", {"player": player, "reply": reply})
    e.seq, e.ts = seq, ts
    return e


def test_node_ts_follows_its_own_events(tmp_path):
    """⭐ ④-①（2026-09-25）: 一条节点的时刻 = **它自己指向的那些事件里最后一条**,
    不再"整段一个 ts"（那会让一批记忆共享同一天, 读不出先后）。

    ⚠️ 只有**第 1 轮的节点**（episode / 玩家画像）走这条 —— 它们手里有真事件指针;
    第 2/4 轮的信念/承诺继续用段 ts（"她什么时候想明白的 = 消化那一刻"）。
    """
    st = _seed_store(tmp_path)
    evs = [_mmt_at(3, "2026-09-20T10:00:00", "老师", "第一件事"),
           _mmt_at(4, "2026-09-21T20:00:00", "老师", "第二件事")]
    a = {"episodes": [
        {"text": "第一件事", "title": "第一件事", "tags": ["a"], "event_seq": [3]},
        {"text": "第二件事", "title": "第二件事", "tags": ["b"], "event_seq": [4]},
        {"text": "跨两块的那条", "title": "跨两块", "tags": ["c"], "event_seq": [3, 4]},
        {"text": "没有指针的那条", "title": "无指针", "tags": ["d"]}]}
    b = {"decisions": [{"episode": f"m000{i}", "decision": "add", "kind": "belief",
                        "subject": "sensei", "text": f"关于 m000{i}"}
                       for i in (3, 4, 5, 6)],
         "evidence": [], "affection_exp_delta": 0}

    res = digest_segment(st, FakeLLM(a, b), evs)

    assert res.ok, res.errors
    got = {st.get(i).title: st.get(i).ts for i in res.created}
    assert got == {
        "第一件事": "2026-09-20T10:00:00",           # 它自己那块
        "第二件事": "2026-09-21T20:00:00",
        "跨两块": "2026-09-21T20:00:00",             # 多指针 → 取**最后**一条
        "无指针": "2026-09-21T20:00:00"}             # 回落段 ts（= 段内最后一条内容事件）
    # 认知（R2 产的）**仍然是段 ts** —— 只有第 1 轮的节点按自己的事件算
    assert st.get("m0007").ts == "2026-09-21T20:00:00"


# ---------------------------------------------------------------------------
# 增量 / 无新增
# ---------------------------------------------------------------------------

def test_round_a_about_hint_is_ignored(tmp_path):
    """⏸ `about_hint` **2026-09-29 退役** —— R1 若还写它, 引擎**整个忽略**。

    退役理由: 它和 R3 的"挂谁"**判两次**（还可能不一致）, 而 R3 本来就拿得到全量候选表
    + 新节点正文 ⇒ 引擎不必替它预判一个名字（`REDUNDANCY.md` #2）。
    ⚠️ 这里钉的是"**没有任何通道**": 不落库（不是节点字段）· 也不再有 `DigestResult.hints`
    —— 否则它就是一条**静默残路**（模型写了、引擎假装收下了, 谁也不消费）。
    """
    st = _seed_store(tmp_path)
    llm = FakeLLM(
        {"episodes": [{"text": "老师说这个给你。", "title": "送我一盆杂草",
                       "tags": ["杂草"], "significance": 0.7,
                       "about_hint": "老师"}]},          # ← 过时字段: 应当被无视
        {"decisions": [{"episode": "m0003", "decision": "touch", "target": "u0001"}],
         "affection_exp_delta": 0})   # B 必须覆盖全部 episode（结构检查）
    res = digest_segment(st, llm, _events(_mmt(3, "x", "送你一盆杂草")))
    assert res.ok, res.errors
    ep = st.get(res.created[0])
    assert "about_hint" not in ep.to_dict()            # 不落库
    assert not hasattr(res, "hints"), "hints 通道已删 —— 别让它回来"


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

def test_round_a_produces_on_mind_note_op(tmp_path):
    """⭐ N4a（2026-09-29）: **L1 产 `on_mind`** —— 从前那是全景轮每 10 段的活。

    形状: Round A 的应答里多一个同级键 `on_mind`（缺键 = 不变, 不是清空）;
    引擎把它变成一条 `rewrite` 操作挂进 `notes_ops`（调用方**整批 ok 之后**才写）。
    """
    st = _seed_store(tmp_path)
    a = _a_episode()
    a["on_mind"] = "我给瓦片留了缝让它见光——也想给自己留一道"
    res = digest_segment(st, FakeLLM(a, _b_ok()), _events(_mmt(3, "老师", "嗯")))
    assert res.ok, res.errors
    ops = [op for op in res.notes_ops if op.get("action") == "rewrite"]
    assert len(ops) == 1 and ops[0]["on_mind"] == a["on_mind"], res.notes_ops

    # 缺键 ⇒ **不产操作**（不变, 不是清空）
    res2 = digest_segment(_seed_store(tmp_path / "b"), FakeLLM(_a_episode(), _b_ok()),
                          _events(_mmt(3, "老师", "嗯")))
    assert res2.ok, res2.errors
    assert not [op for op in res2.notes_ops if op.get("action") == "rewrite"]


def test_full_pipeline(tmp_path):
    st = _seed_store(tmp_path)
    llm = FakeLLM(_a_episode(), _b_ok())
    events = _events(_mmt(3, "老师", "下次再去吃甜品吧"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.llm_calls == 4                          # A + R4（收口）+ B + R3（归属）
    # A: episode 建好, 引擎字段归属
    assert res.created == ["m0003"]
    ep = st.get("m0003")
    assert ep.kind == "episode" and ep.event_seq == [3]
    assert ep.ts and ep.title == "甜点之约"
    # B: update → 认知改写（变更进 evolution 日志）; add → 新 belief 链回 episode
    bel = st.get("m0002")
    assert bel.significance == 0.95
    added = [n for n in st.all()
             if n.kind == "belief" and n.text == "老师会带我去吃甜品"]
    assert len(added) == 1 and added[0].observer == ""   # ⭐ 新认知不是"听说的"（observer 空）
    nid = added[0].id
    assert st.graph().supporters(nid) == ["m0003"]       # 次数 = supports 入边（G3）
    assert set(st.graph().targets("m0003")) == {nid, "m0002"}   # episode 的两条出边
    assert res.affection_delta == 30
    assert st.digested_seq == 3
    # evolution log（apply_decisions 追加）: update 那行带 before/after
    entries = EvolutionLog.for_store(st).read()
    assert [e["action"] for e in entries] == ["update", "add"]
    upd = entries[0]
    assert upd["target"] == "m0002" and upd["changed"]["text"][1]
    assert upd["changed"]["text"][0] != upd["changed"]["text"][1]


def test_touch_decision_links_only(tmp_path):
    st = _seed_store(tmp_path)
    llm = FakeLLM(
        _a_episode(text="又和老师在天台安静坐着"),
        {"decisions": [{"episode": "m0003", "decision": "touch", "target": "u0001",
                        "note": "又是安静的陪伴"}],
         "evidence": [], "affection_exp_delta": 5})
    events = _events(_mmt(3, "x", "天台很安静"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    bel = st.get("m0002")
    assert bel.significance == 0.9                     # touch 不改内容
    assert "m0003" in st.graph().supporters("m0002")   # 只连边（G3: supports 入边）


# ---------------------------------------------------------------------------
# T14: 板指针 event_seq + verbatim 索引通道 → 逐字原文（2026-09-15）
# ---------------------------------------------------------------------------

def _mmt_ev(seq, player, reply):
    return ("mmt", "chat", {"player": player, "reply": reply}, seq)


def test_event_seq_pointer_and_verbatim_resolve(tmp_path):
    """★ 板指针真的落库（不再被覆写成常量）+ 索引解析出**逐字原文**。"""
    st = _seed_store(tmp_path)
    a = {"episodes": [{
        "text": "老师突然约我去咖啡厅, 说好久没见要请我吃甜点。",
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


def test_verbatim_text_channel_is_retired(tmp_path):
    """⛔ 文本通道已退役 → **字符串一律忽略**（`REDUNDANCY.md` #6）。

    从前"两条都给 → 文本优先"是个安全决定（错的原话一眼看得出, 错的索引看不出）;
    今天行号是唯一入口, 解析不出就**留空绝不编** —— 宁可这条记忆没有原话。
    """
    st = _seed_store(tmp_path)
    a = {"episodes": [{
        "text": "她递给我一块甜点。", "title": "甜点",
        "event_seq": ["11"],
        "verbatim": "……这块，给你。",            # ⛔ 文本通道: 忽略
        "verbatim_seq": ["11.0"],               # 行号: 解析得出
        "tags": ["甜点"], "significance": 0.6}]}
    b = {"decisions": [{"episode": "m0003", "decision": "touch", "target": "u0001"}],
         "evidence": [], "affection_exp_delta": 0}
    events = _events(("bond", "story_scene", {
        "paragraphs": [{"text": "……这块，给你。"}]}, 11))
    res = digest_segment(st, FakeLLM(a, b), events)
    assert res.ok, res.errors
    ep = st.get(res.created[0])
    assert ep.verbatim == "……这块，给你。", ep.verbatim      # 来自事件流的逐字原文
    assert ep.verbatim_seq == ["11.0"], ep.verbatim_seq     # 行号留在库里（可重解析）
    # 只给文本、没有行号 → 落空（**不兜底**）
    st2 = _seed_store(tmp_path / "b")
    a2 = {"episodes": [{"text": "只有文本", "title": "x", "event_seq": ["11"],
                        "verbatim": "……这块，给你。", "tags": ["t"], "significance": 0.5}]}
    res2 = digest_segment(st2, FakeLLM(a2, b), events)
    assert res2.ok, res2.errors
    ep2 = st2.get(res2.created[0])
    assert ep2.verbatim == "" and ep2.verbatim_seq == []
    # 坏行号（越界）→ 同样留空, 但行号本身留着（可追溯性不受解析成败影响）
    st3 = _seed_store(tmp_path / "c")
    a3 = {"episodes": [{"text": "只有坏行号", "title": "x", "event_seq": ["11"],
                        "verbatim": ["11.99"], "tags": ["t"], "significance": 0.5}]}
    res3 = digest_segment(st3, FakeLLM(a3, b), events)
    assert res3.ok, res3.errors
    ep3 = st3.get(res3.created[0])
    assert ep3.verbatim == "" and ep3.verbatim_seq == ["11.99"]
    print("    verbatim: 文本通道退役（字符串忽略）+ 坏行号留空不编")


def test_event_seq_falls_back_to_segment_constant(tmp_path):
    """没有板指针 → 回落段级常量（旧行为, 不编）。"""
    st = _seed_store(tmp_path)
    res = digest_segment(st, FakeLLM(_a_episode(verbatim=None), _b_ok()),
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
        "text": "杂草屋里她第一次笑出来。", "title": "杂草屋",
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


def test_place_materialized_from_board_pointer(tmp_path):
    """★ M3（2026-09-19）: 板指针 → **地点键序列 + 剧情地理**物化到节点。

    与 `emo_shape` 同一手。带的是 **标注层解出的键**（不是 writer 本名）:
    「放学后的教室」/「傍晚的学校天台」三个字符串在节点上只有一个身份 ——
    `classroom` / `school_rooftop`, 因为 C 链路比的是相等。
    """
    st = _seed_store(tmp_path)
    a = {"episodes": [{
        "text": "她带我去了天台。", "title": "天台",
        "event_seq": ["20", "22", "24"],
        "tags": ["天台"], "significance": 0.8}]}
    b = {"decisions": [{"episode": "m0003", "decision": "touch", "target": "u0001"}],
         "evidence": [], "affection_exp_delta": 0}
    events = _events(
        _mmt(20, "在吗", "在的"),                                   # MMT → 无地点
        ("bond", "story_scene", {                                   # 板: switch 教室
            "place": "classroom", "place_hint": "格黑娜学院·放学后的教室",
            "paragraphs": [{"text": "她放下书包。"}]}, 22),
        ("bond", "story_scene", {                                   # 板: switch 天台 + 句级锚点
            "place": "school_rooftop", "place_hint": "傍晚的学校天台",
            "paragraphs": [{"text": "晚风迎面。"},
                           {"text": "她又走下楼梯回到教室。",
                            "place": "classroom"}]}, 24),
    )
    res = digest_segment(st, FakeLLM(a, b), events)
    assert res.ok, res.errors
    ep = st.get(res.created[0])
    # 键序列: 板级 place 在前、句级锚点在后; **相邻去重**（同地反复会留多次）
    assert ep.place == ["classroom", "school_rooftop", "classroom"], ep.place
    # **叙事轴**: writer 原文序列（键不是地名的双射 → 判"同地"只能靠它做语义）
    assert ep.place_raw == ["格黑娜学院·放学后的教室", "傍晚的学校天台"], ep.place_raw
    # `region` 已撤（2026-09-19 用户: "基本没有太多作用，也不必落库"）
    assert "region" not in ep.to_dict()
    print(f"    place 物化: {ep.place}  raw={ep.place_raw}")


def test_place_absent_when_no_place_data(tmp_path):
    """没地点数据 → `[]`（**哨兵: 未采集 ≠ 某个地点**）, 绝不编。"""
    st = _seed_store(tmp_path)
    events = _events(_mmt(3, "老师", "下次再去吃甜品吧"))
    res = digest_segment(st, FakeLLM(_a_episode(), _b_ok()), events)
    assert res.ok, res.errors
    ep = st.get(res.created[0])
    assert ep.place == [] and ep.place_raw == []
    assert "place" not in ep.to_dict() and "place_raw" not in ep.to_dict(), \
        "空值该被省略（行小）——也顺手钉住 to_dict 的省略口径"
    print("    place: 无数据 → []（哨兵）, to_dict 省略")


def test_place_raw_keeps_writer_wording(tmp_path):
    """★ 叙事轴: `place_raw` 存的是 **writer 的原话**（不归一、不改写）。

    它是唯一能判"是不是同一个地方"的输入（键不是地名的双射）——
    所以**必须原样保留**, 归一化留给检索时的语义比较。
    """
    st = _seed_store(tmp_path)
    a = {"episodes": [{"text": "在杂草屋", "title": "x", "event_seq": ["22"],
                       "tags": ["t"], "significance": 0.5}]}
    b = {"decisions": [{"episode": "m0003", "decision": "touch", "target": "u0001"}],
         "evidence": [], "affection_exp_delta": 0}
    events = _events(("bond", "story_scene", {
        "place": "ruinschoolcorridor", "place_hint": "深夜的杂草屋",
        "paragraphs": [{"text": "……"}]}, 22))
    res = digest_segment(st, FakeLLM(a, b), events)
    assert res.ok, res.errors
    ep = st.get(res.created[0])
    assert ep.place == ["ruinschoolcorridor"]           # 素材轴: 键
    assert ep.place_raw == ["深夜的杂草屋"], ep.place_raw  # 叙事轴: 原话一字不动
    print(f"    place_raw: 键={ep.place} 原话={ep.place_raw}（不归一）")


# ---------------------------------------------------------------------------
# 板块5: 引擎候选提示（T17 后**仅提示** —— 曾为"疑似同主题 → 禁 add"的结构强制）
# ---------------------------------------------------------------------------

def _cat_store(tmp_path) -> WikiStoreV2:
    """带"猫"tags 的 belief——关键词降级通道下, 猫相关 episode 必被标注。

    id: episode m0001 / belief m0002（A 轮新 episode 顺延 m0003）。
    """
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(make_node("episode", text="喂猫旧事", event_seq=[2]))
    st.add(make_node("belief", text="老师会记得给猫带猫粮", subject="老师与猫的约定",
                     significance=0.9, tags=["猫"],
                     event_seq=[2]))
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
        _a_episode(text="老师带猫粮来喂猫, 猫绕着我转了两圈"),
        {"decisions": [
            {"episode": "m0003", "decision": "add", "kind": "belief",
             "subject": "猫", "text": "老师会带猫粮来喂猫",
             "note": "与候选只是字面像, 不是同一件事"},
         ], "evidence": [], "affection_exp_delta": 5},
    )
    events = _events(_mmt(3, "x", "猫粮带来了"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.llm_calls == 4                          # A + R4 + B + R3（**没有**拒绝重试）
    # 候选提示仍在输入里（只是不再带"禁 add"的措辞）
    assert "候选" in llm.calls[1][1]["content"]
    assert "禁 add" not in llm.calls[1][1]["content"]
    # add 真的落地了（新认知长出来了——这正是删阈值的直接目的）
    added = [n for n in st.all() if n.kind == "belief" and n.text == "老师会带猫粮来喂猫"]
    assert added, "add 被引擎拦掉了——结构强制没删干净"
    print("    候选仅提示: add 不再被拒（新认知能长出来）")


def test_no_candidate_when_unrelated(tmp_path):
    """无关键词关联 → 无候选提示行 → LLM 自由 add（本来也不再有强制）。"""
    st = _cat_store(tmp_path)
    llm = FakeLLM(
        _a_episode(text="老师送我一盆新的杂草", tags=("杂草",)),
        {"decisions": [
            {"episode": "m0003", "decision": "add", "kind": "belief",
             "subject": "杂草", "text": "杂草是遥香安心的事物"},
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
            {"text": "老师说下周放假带我去看烟火大会, 我紧张得直结巴还是答应了",
             "title": "烟火大会之约", "verbatim": ["3.1"],
             "tags": ["约定", "烟火"], "significance": 0.85},
            {"kind": "experience", "text": "玩家的生日是 5 月 20 日",
             "verbatim": ["3.0"], "tags": ["玩家生日"],
             "significance": 0.7},
        ]},
        {"decisions": [
            {"episode": "m0001", "decision": "add", "kind": "belief",
             "subject": "和老师的约定", "text": "老师会认真对待与我的约定"},
         ], "evidence": [], "affection_exp_delta": 15})
    events = _events(_mmt(3, "我生日是 5 月 20 日哦", "下周放假, 一起去看烟火吧"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.created == ["m0001"]                    # episode 正常建
    p = st.get("e0001")                                # 画像条目 → subject=player experience
    assert p is not None and p.kind == "experience"
    assert p.subject == "player" and p.text.startswith("玩家的生日")
    assert p.verbatim == "我生日是 5 月 20 日哦"        # 玩家原话 = 行号 `[3.0]` → 逐字原文
    assert p.event_seq == [3]
    # B 的认知列表不含刚建的画像条目（冷启动提示仍在 = 无认知可组织）
    b_user = llm.calls[1][1]["content"]
    assert "玩家的生日" not in b_user
    assert "尚无稳定认知" in b_user or "u0001" in b_user  # 画像被排除后无旧认知
    assert "m0001" in b_user                           # episode 摘要正常进 B


# ---------------------------------------------------------------------------
# 冷启动: 无旧记忆 → B 只能 add（belief 路径: 先链后入仓; 来源字段引擎不留痕）
# ---------------------------------------------------------------------------

def test_cold_start_add_belief(tmp_path):
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")   # 空库
    llm = FakeLLM(
        _a_episode(text="老师帮我把杂草搬回了家"),
        {"decisions": [
            {"episode": "m0001", "decision": "add", "kind": "belief",
             "subject": "老师对我的照顾", "text": "老师会记得我随口提过的事",
             "tags": ["老师"], "significance": 0.85}],
         "evidence": [], "affection_exp_delta": 10})
    events = _events(_mmt(3, "x", "杂草我帮你搬"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.created == ["m0001"]
    bel = st.get("m0002")                              # 空库 belief → m0002
    assert bel.kind == "belief"
    assert bel.observer == ""                            # ⭐ 来源字段为空（不是"听说的"）
    # 支撑不变量（G3: 入仓后立刻补 supports 边; 字段层不再判它）
    assert st.graph().supporters("m0002") == ["m0001"]
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
            if kw.get("task") == T.DIGEST_CLOSE:       # R4: 同样要超预算（本用例测的是预算）
                time.sleep(0.2)
                self.calls += 1
                return CLOSE_EMPTY
            if kw.get("task") == T.DIGEST_ATTR:        # R3 同理
                time.sleep(0.2)
                self.calls += 1
                return {"attributions": []}
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
        {"episodes": [{"title": "缺正文"}]},            # parse 拒绝（无 text）
        _a_episode(),
        _b_ok(),
    )
    events = _events(_mmt(3, "x", "y"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.llm_calls == 5                          # A1(拒) + A2(过) + R4 + B + R3
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
    assert res.llm_calls == 5                          # A + R4 + B1(拒) + B2(过) + R3
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
# 情绪两标量 emo_int / emo_span 落到 episode 节点（§3.3.3）
# （`emo_valence` 2026-09-21 删——有生产零消费; 极性由 emo_shape 逐键承担）
# ---------------------------------------------------------------------------

def test_emo_scalars_land_on_episode_nodes(tmp_path):
    """Round A 给了 → 必须一路落到节点（契约清洗 → make_node → 落盘）。"""
    st = _seed_store(tmp_path)
    a = _a_episode()
    a["episodes"][0]["emo_int"] = 0.85
    a["episodes"][0]["emo_span"] = 0.9
    llm = FakeLLM(a, _b_ok())
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")))
    assert res.ok and res.created
    ep = st.get(res.created[0])
    assert ep.emo_int == 0.85, f"emo_int 未落节点: {ep.emo_int}"
    assert ep.emo_span == 0.9, f"emo_span 未落节点: {ep.emo_span}"
    print(f"    emo_*: 落节点 {res.created[0]} int={ep.emo_int} span={ep.emo_span}")


def test_emo_scalars_absent_when_llm_silent(tmp_path):
    """Round A 没给 → 节点上必须是 None（不是 0.0）。"""
    st = _seed_store(tmp_path)
    llm = FakeLLM(_a_episode(), _b_ok())
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")))
    ep = st.get(res.created[0])
    assert ep.emo_int is None and ep.emo_span is None
    d = ep.to_dict()
    for f in ("emo_int", "emo_span", "emo_valence"):
        assert f not in d, f"{f} 不该落库"
    print("    emo_*: LLM 没给 → None（不冒充'毫无波澜'）")


def test_emo_scalars_zero_is_written(tmp_path):
    """0.0 是合法值（事务性寒暄 / 全程一个调子）——必须落库。"""
    st = _seed_store(tmp_path)
    a = _a_episode()
    for f in ("emo_int", "emo_span"):
        a["episodes"][0][f] = 0.0
    llm = FakeLLM(a, _b_ok())
    res = digest_segment(st, llm, _events(_mmt(3, "x", "y")))
    ep = st.get(res.created[0])
    assert ep.emo_int == 0.0 and ep.emo_span == 0.0
    d = ep.to_dict()
    for f in ("emo_int", "emo_span"):
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
    from core.brain.digest import _segment_emotion_keys
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


# ---------------------------------------------------------------------------
# 段类型: 粒度跟着**作者单位**走（2026-09-20 用户裁决）
#   bond = 一章羁绊剧情（`vn_enter`..`vn_exit`, 边界**引擎已知**）→ **恰好 1 条** episode
#   mmt  = 碎聊（无作者单位）                                → 0~5 条, **需要切分的是它**
#
# 用户原话: *"离散的是 mmt，但 bond story 不应该连续吗"* /
#           *"episode 应该 informative but single，belief 则是 brief but descriptive"*
# ---------------------------------------------------------------------------

def _bond_span(seq_in=3, seq_out=6, title="错误的地点", bond_seq=None):
    """一个 **bond 段**（一章）: 两条 marker 夹一段内容 —— 边界在真源里, 引擎不用猜。

    ⚠️ 名字不叫 `_bond` —— 文件上方已有一个 `_bond`（"一板"的球面事件构造器,
    情绪标尺那组用例在用）。**别撞名**: 撞了会静默覆盖, 表现为别处的用例莫名报错。

    ⚠️ 里面**同时放了一条 MMT 聊天**（真档的窗口就是混的: haruka 13 聊天 + 5 剧情）——
    "一章一条"只该管**这一章**的条目, 聊天那些要按 0~5 条留着。
    """
    bs = seq_in + 2 if bond_seq is None else bond_seq
    return [("marker", "vn_enter", {"chapter_title": title}, seq_in),
            _mmt(seq_in + 1, "老师", "……"),
            ("bond", "story_scene",
             {"paragraphs": [{"text": "第1条", "emotion": "smile"}]}, bs),
            ("marker", "vn_exit", {"completed": True}, seq_out)]


def _prompt(llm, i=0) -> str:
    return "\n".join(str(m) for m in llm.calls[i])


def test_bond_segment_asks_for_exactly_one_episode(tmp_path):
    """★ bond 段: 产出契约 = **恰好 1 条** + 本章标题注入（title 用本章标题）。"""
    st = _seed_store(tmp_path)
    llm = FakeLLM(_a_episode(), _b_ok())
    res = digest_segment(st, llm, _events(*_bond_span()))
    assert res.ok, res.errors
    a = _prompt(llm, 0)
    assert "恰好 1 条" in a, a[:400]
    assert "作者单位" in a
    assert "informative but single" in a
    assert "本章标题" in a and "错误的地点" in a        # 标题进了 user 段
    assert len(res.created) == 1
    print("    bond: 产出契约(恰好 1 条) + 本章标题注入 ✓")


def test_mmt_segment_still_splits(tmp_path):
    """★ mmt 段: 无作者单位 → 契约仍是 0~5 条（**不要**把切分能力一起改掉）。"""
    st = _seed_store(tmp_path)
    two = {"episodes": [
        {"text": "老师约我明天去喂猫", "title": "老师约我明天去喂猫",
         "tags": ["约定", "猫"], "significance": 0.8},
        {"text": "老师说他也总忘带伞", "title": "老师说他也总忘带伞",
         "tags": ["口癖"], "significance": 0.5}]}
    # Round B 的决策必须**逐条覆盖**本轮 episode（引擎结构检查）——
    # 建了两条就得给两条决策, 否则 B 被整包拒 + 反馈重试 → 假 LLM 响应耗尽。
    b = _b_ok()
    b["decisions"].append({"episode": "m0004", "decision": "add",
                           "kind": "belief", "subject": "sensei",
                           "text": "老师也总忘带伞", "example": "「我也总忘带伞」"})
    llm = FakeLLM(two, b)
    res = digest_segment(st, llm,
                         _events(_mmt(3, "老师", "明天带猫粮去喂猫吧")))
    assert res.ok, res.errors
    a = _prompt(llm, 0)
    assert "需要切分" in a
    assert "恰好输出 1 条" not in a
    assert len(res.created) == 2, res.created          # 两条都留下
    print("    mmt: 契约仍是 0~5 条, 两条都建 ✓")


def test_bond_extra_episodes_collapse_to_one(tmp_path, caplog):
    """★ 提示词没压住时**引擎确定性收口**: 留 significance 最高的 + 留一行告警。

    为什么丢弃而不是合并文本: 合并是创作（要 LLM）, 引擎只做判定; 而"一章一条"
    的前提本来就是**那条总结该覆盖全章**。

    ⚠️ 三条都**声明自己属于这一章**（`event_seq` 与 bond 块相交）才会被收口 ——
    见下一条用例: 聊天那些不属于这一章, 不能被一起压掉。
    """
    st = _seed_store(tmp_path)
    three = {"episodes": [
        {"text": "她照常去破房子照料杂草, 抬头发现老师站在那儿",
         "title": "去破房子照料杂草", "tags": ["杂草"], "significance": 0.6,
         "event_seq": ["5"]},
        {"text": "老师说这里就是只属于我和他的秘密场所",
         "title": "只属于两人的秘密场所", "tags": ["约定"], "significance": 0.9,
         "event_seq": ["5"]},
        {"text": "她又道歉了一次", "title": "她又道歉了一次",
         "tags": ["道歉"], "significance": 0.4, "event_seq": ["5"]}]}
    llm = FakeLLM(three, _b_ok())
    with caplog.at_level("WARNING"):
        res = digest_segment(st, llm, _events(*_bond_span()))
    assert res.ok, res.errors
    assert len(res.created) == 1, res.created           # 一章一条
    ep = st.get(res.created[0])
    assert ep.title == "只属于两人的秘密场所", ep.title               # 留 significance 最高的
    msgs = [r.getMessage() for r in caplog.records]
    assert any("contract=bond" in m for m in msgs), msgs
    print("    bond: 3 条 → 1 条（留 sig 最高）+ 告警可 grep ✓")


def test_bond_window_keeps_mmt_atoms(tmp_path):
    """★★ **窗口是混的**（真档实测: haruka 13 条聊天 + 5 块剧情, mutsuki 26 + 13）:
    "一章一条"只收口**属于这一章**的条目 —— 聊天那些按 0~5 条留着。

    第一版按"窗口里有 `vn_enter` ⇒ 整段 bond"写, 会把聊天里的记忆一起压成 1 条。
    """
    st = _seed_store(tmp_path)
    mixed = {"episodes": [
        # ① 聊天条目: event_seq 指向 seq 4（那条 mmt）, 不在本章的 bond 块里
        {"text": "老师约我明天去喂猫", "title": "老师约我明天去喂猫",
         "tags": ["约定"], "significance": 0.8, "event_seq": ["4"]},
        # ② 本章: 两条都指向 bond 块 5 → 收口成 1
        {"text": "她在破房子遇到老师", "title": "在破房子遇到老师",
         "tags": ["杂草"], "significance": 0.7, "event_seq": ["5"]},
        {"text": "老师说这里是秘密场所", "title": "只属于两人的秘密场所",
         "tags": ["约定"], "significance": 0.9, "event_seq": ["5"]}]}
    b = _b_ok()
    b["decisions"].append({"episode": "m0004", "decision": "add",
                           "kind": "belief", "subject": "sensei",
                           "text": "老师会约我喂猫", "example": "「明天带猫粮」"})
    llm = FakeLLM(mixed, b)
    res = digest_segment(st, llm, _events(*_bond_span()))
    assert res.ok, res.errors
    titles = sorted(st.get(i).title for i in res.created)
    assert titles == ["只属于两人的秘密场所", "老师约我明天去喂猫"], titles
    print(f"    bond 窗口: 聊天原子留着 + 本章收口成 1 条 → {titles} ✓")


def test_two_chapters_in_one_window_each_get_one(tmp_path):
    """★★ **窗口里可能有多章**（水位被清 / 重跑时**必然**如此）:
    "一章一条"必须**按章**分组收口 —— 两章压成一条就丢了一整章。

    这是 2026-09-20 用户要"删掉旧数据重跑 igusa_haruka"时暴露的场景:
    水位归零 ⇒ 第一次 digest 的窗口 = 旧章的 31 条 + 新章的几十条 = **两章同窗**。
    """
    st = _seed_store(tmp_path)
    # 两章: 章A 的 bond 块 = seq 5, 章B 的 bond 块 = seq 12
    evs = _events(*_bond_span(3, 7, title="错误的地点"),
                  _mmt(8, "老师", "……"),
                  ("marker", "vn_enter", {"chapter_title": "错误的收信人"}, 10),
                  ("bond", "story_scene",
                   {"paragraphs": [{"text": "第1条", "emotion": "smile"}]}, 12),
                  ("marker", "vn_exit", {"completed": True}, 13))
    four = {"episodes": [
        # 章A 的两条 → 该压成 1
        {"text": "章A 片段一", "title": "章A 的第一条记忆", "tags": ["a"],
         "significance": 0.7, "event_seq": ["5"]},
        {"text": "章A 片段二", "title": "章A 的第二条记忆", "tags": ["a"],
         "significance": 0.9, "event_seq": ["5"]},
        # 章B 的两条 → 也该各自压成 1（不是被章A 一起吞掉）
        {"text": "章B 片段一", "title": "章B 的第一条记忆", "tags": ["b"],
         "significance": 0.6, "event_seq": ["12"]},
        {"text": "章B 片段二", "title": "章B 的第二条记忆", "tags": ["b"],
         "significance": 0.8, "event_seq": ["12"]}]}
    b = {"decisions": [
        {"episode": "m0003", "decision": "add", "kind": "belief",
         "subject": "章A 的模式", "text": "章A 的模式", "example": "「A」"},
        {"episode": "m0004", "decision": "add", "kind": "belief",
         "subject": "章B 的模式", "text": "章B 的模式", "example": "「B」"}],
        "evidence": [], "affection_exp_delta": 0}
    res = digest_segment(st, FakeLLM(four, b), evs)
    assert res.ok, res.errors
    titles = sorted(st.get(i).title for i in res.created)
    assert titles == ["章A 的第二条记忆", "章B 的第二条记忆"], titles   # 每章各留 sig 最高的
    print(f"    两章同窗: 每章各收口成 1 条 → {titles} ✓")


# ---------------------------------------------------------------------------
# ⭐ N3（2026-09-29）: 位置 = **区间** —— 引擎把 `span` 展开成区间内全部内容 seq
#    真机病根: LLM 逐点挑选必然漏 —— 覆盖率只有 67.9%（218 条内容事件里 70 条没进任何记忆）,
#    缺口动辄 12~18 处（`m0004` 36 点/跨度 50 · `m0009` 19 点/跨度 40）
# ---------------------------------------------------------------------------

def _span_episode(span, *, text="老师带我去看了瓦片缝里的苔藓",
                  title="瓦片缝里的苔藓", sig=0.7):
    return {"episodes": [{"text": text, "title": title, "span": list(span),
                          "tags": ["苔藓"], "significance": sig}]}


def test_expand_spans_fills_gap_and_pops_the_key():
    """⭐ 区间展开成**全部**内容 seq；`span` 就地摘掉；未认领与共享**如实报告**。

    ⚠️ `span` 必须被 `pop`：`_create_a_nodes` 走 `make_node("episode", **ent)`，
    留在条目里的 `span` 会被 `from_dict` **静默忽略**（这个项目最恨的静默 no-op ——
    `about_hint` 当年就是为这个专门 pop 的）。
    """
    from core.brain.digest import _expand_spans

    entries = [{"span": [10, 13], "text": "a"}, {"span": [12, 14], "text": "b"}]
    unclaimed, shared = _expand_spans(entries, {10, 11, 12, 13, 14, 20})
    assert entries[0]["event_seq"] == [10, 11, 12, 13]      # 缺口被填满
    assert entries[1]["event_seq"] == [12, 13, 14]
    assert all("span" not in e for e in entries)
    assert unclaimed == [20]                                # 谁也没认领的那条
    assert shared == 2                                      # 12/13 被两条共享（⚠️ **不裁**）
    # 旧形状（逐点）**不展开**：那是她自己挑的点，展开等于替她加上她没声称的事件
    legacy = [{"event_seq": [10, 12, 14]}]
    un2, sh2 = _expand_spans(legacy, {10, 11, 12, 13, 14})
    assert legacy[0]["event_seq"] == [10, 12, 14] and un2 == [11, 13] and sh2 == 0
    print("    _expand_spans: 填缺口 / pop span / 未认领 / 共享只记账 / 旧形状不动")


def test_span_expansion_runs_before_bond_collapse():
    """⚠️ **结构性守门**: `_expand_spans` 必须排在 `_collapse_bond_episodes` **之前**。

    为什么：那一章的归属判据 `_in_seqs` 靠"条目的 `event_seq` 与章块的**相交**" ——
    展开前条目只有 `span`（还没有 `event_seq`）⇒ 相交恒为 False ⇒ **整章那一条会被判成
    "不属于本章"**（`_collapse_bond_episodes` 收口也就跟着失效）。
    """
    import ast
    import inspect
    import textwrap
    from core.brain.digest import digest_segment

    fn = ast.parse(textwrap.dedent(inspect.getsource(digest_segment))).body[0]
    code = ast.unparse(fn)
    assert "_expand_spans(" in code and "_collapse_bond_episodes(" in code, \
        "digest_segment 里少了展开或收口"
    assert code.index("_expand_spans(") < code.index("_collapse_bond_episodes("), \
        "_expand_spans 必须在 _collapse_bond_episodes 之前（否则章的归属判据恒假）"
    print("    结构: _expand_spans 在 _collapse_bond_episodes 之前 ✓")


def test_span_end_to_end_expands_and_sets_node_time(tmp_path):
    """端到端: Round A 给 `span` ⇒ 落库节点 `event_seq` = **展开后的区间**，
    且 `ts` 取区间**最后一条**（`_node_ts` 的既有语义, 一行没改）。"""
    st = _seed_store(tmp_path)
    evs = _events(_mmt(10, "老师", "一"), _mmt(11, "老师", "二"),
                  _mmt(12, "老师", "三"), _mmt(13, "老师", "四"))
    res = digest_segment(st, FakeLLM(_span_episode([10, 12]), _b_ok()), evs)
    assert res.ok, res.errors
    node = st.get(res.created[0])
    assert node.event_seq == [10, 11, 12], node.event_seq     # ⭐ 不是 [10, 12]
    assert node.ts == evs[2].ts                               # 区间最后一条 ⇒ 自己的时刻
    # 未认领的 13 **不落节点**（归闲聊）—— 本段只建了 1 条 episode
    assert len(res.created) == 1
    print("    span 端到端: event_seq 展开 + ts 取区间末尾 + 未认领不落节点 ✓")
