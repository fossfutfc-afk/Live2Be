"""digest_registry 测试（AGENT_BRAIN.md §3 重构 / 板块 2）——LLM 契约层单源。"""
from contract.digest_registry import (
    PHASE_CLOSE,
    PHASE_RECORD,
    PHASE_UNDERSTAND,
    PROMISE_OUTCOMES,
    digest_registry,
)


# ---------------------------------------------------------------------------
# R4 收口（`{"add": […], "close": […]}`）
# ---------------------------------------------------------------------------

def test_schema_close_phase():
    text = digest_registry.build_schema(PHASE_CLOSE)
    assert '"add": [' in text and '"close": [' in text
    assert "两个键**都要在**" in text
    for w in PROMISE_OUTCOMES:
        assert w in text
    assert "必填" in text                       # reason 必填
    # 示例只有一种形状（设计稿陷阱 3/4）: 契约里出现的示例行就是那两行
    assert text.count('"text": "周六模型店"') == 1
    assert text.count('"id": "n1"') == 1


def test_parse_close_keeps_good_rows():
    rows, res = digest_registry.parse_close({
        "add": [{"text": "周六模型店", "refs": ["m0013"], "due": "2026-09-26"},
                {"text": "还他笔记", "refs": ["m0004", "m0005"]}],
        "close": [{"id": "n1", "state": "kept", "reason": "周六真的去了"}]})
    assert res.errors == ()
    assert rows[0] == {"action": "add", "text": "周六模型店", "refs": ["m0013"],
                       "due": "2026-09-26"}
    assert "due" not in rows[1]                 # 空 due 不落键
    assert rows[2] == {"action": "close", "id": "n1", "state": "kept",
                       "reason": "周六真的去了"}


def test_parse_close_shape_errors_reject_the_package():
    """**形状错 = 拒整包**（重试有用）: 缺键 / 不是数组 / 行不是对象 / 值域 / 必填。"""
    cases = [
        (["nope"], "必须是 JSON 对象"),
        ({"add": []}, "缺键 'close'"),
        ({"add": {}, "close": []}, "add 必须是数组"),
        ({"add": ["x"], "close": []}, "add[0] 必须是对象"),
        ({"add": [{"refs": ["m1"]}], "close": []}, "add[0] 缺 text"),
        ({"add": [{"text": "x"}], "close": []}, "add[0] 缺 refs"),
        ({"add": [], "close": [{"state": "kept", "reason": "x"}]}, "close[0] 缺 id"),
        ({"add": [], "close": [{"id": "n1", "state": "done", "reason": "x"}]},
         "state 非法"),
        ({"add": [], "close": [{"id": "n1", "state": "kept"}]}, "缺理由"),
    ]
    for raw, want in cases:
        rows, res = digest_registry.parse_close(raw)
        assert any(want in e for e in res.errors), (raw, res.errors)
        assert rows == [], raw


def test_parse_close_dedupes_with_warning():
    rows, res = digest_registry.parse_close({
        "add": [], "close": [
            {"id": "n1", "state": "kept", "reason": "去了"},
            {"id": "n1", "state": "broken", "reason": "没去"}]})
    assert res.errors == () and len(rows) == 1 and rows[0]["state"] == "kept"
    assert any("重复" in w for w in res.warnings)


# ---------------------------------------------------------------------------
# schema 渲染
# ---------------------------------------------------------------------------

def test_schema_record_phase():
    text = digest_registry.build_schema(PHASE_RECORD)
    assert '"episodes": [' in text
    assert "text" in text and "内联约束" in text or "必填" in text
    assert "title" in text and "verbatim" in text and "tags" in text
    assert "significance" in text
    # 内联约束注释（A-MEM 式: 规则贴字段）
    assert "检索导向" in text
    assert "行为锚点" in text
    # 语义与范例
    assert "【record_episode 释义】" in text
    assert "【范例】" in text


def test_schema_understand_phase():
    text = digest_registry.build_schema(PHASE_UNDERSTAND)
    assert '"decisions": [' in text
    for name in ("touch", "update", "add"):
        assert f"【{name} 释义】" in text
    assert "evidence" in text and "affection_exp_delta" in text
    assert "编造 id → 整包拒" in text
    assert "疑似印证" in text


def test_actions_by_phase():
    assert {a.name for a in digest_registry.actions(PHASE_RECORD)} == {"record_episode"}
    assert {a.name for a in digest_registry.actions(PHASE_UNDERSTAND)} == {
        "touch", "update", "add"}
    assert digest_registry.actions()  # 全量非空


def test_unknown_phase_rejected():
    import pytest
    with pytest.raises(ValueError):
        digest_registry.build_schema("deep")     # deep 未注册动作 → 暂不支持


# ---------------------------------------------------------------------------
# Round A parse
# ---------------------------------------------------------------------------

def test_round_a_valid_entries():
    raw = {"episodes": [
        {"text": "老师约我去公园散步, 我紧张但努力答应了。", "title": "公园散步",
         "tags": ["公园"], "significance": 0.8},
        {"text": "听睦月说阿露昨天又翻车了", "title": "阿露翻车",
         "tags": ["睦月", "阿露"], "epistemic": "reported_fact",
         "observer": "asagi_mutsuki", "significance": 0.6},
    ]}
    items, result = digest_registry.parse_round_a(raw)
    assert result.is_valid, result.errors
    assert len(items) == 2
    assert items[0]["text"].startswith("老师约我")
    assert items[1]["epistemic"] == "reported_fact"
    assert items[1]["observer"] == "asagi_mutsuki"


def test_round_a_rejects_bad_entries():
    raw = {"episodes": [
        {"title": "没有正文"},                       # 缺 text
        {"text": "x" * 400},                    # 超长
        {"text": "转述却没写转述者", "epistemic": "reported_fact"},
        {"text": "ok", "title": "t", "id": "m9999"},   # 引擎字段应被忽略(警告)
    ]}
    items, result = digest_registry.parse_round_a(raw)
    assert not result.is_valid
    assert any("text" in e for e in result.errors)          # 缺正文
    assert any("300 字" in e for e in result.errors)             # 超长
    assert any("observer" in e for e in result.errors)           # reported 缺转述者
    assert any("引擎字段" in w for w in result.warnings)         # id 忽略
    # 坏条目丢弃, 好的保留
    assert len(items) == 1 and items[0]["text"] == "ok"


def test_round_a_caps_and_defaults():
    raw = {"episodes": [{"text": f"e{i}", "title": f"t{i}"} for i in range(7)]}
    items, result = digest_registry.parse_round_a(raw)
    assert len(items) == 5                       # MAX_EPISODES 截断
    assert items[0]["significance"] == 0.5       # 缺省
    assert items[0]["epistemic"] == "observed_fact"
    assert any("5 条" in e for e in result.errors)


def test_round_a_not_dict():
    items, result = digest_registry.parse_round_a(["nope"])
    assert items == [] and not result.is_valid


def test_round_a_player_portrait_entry():
    """MMT 专则: kind=experience（玩家画像）条目——text 必填, subject 引擎固定。"""
    raw = {"episodes": [
        {"kind": "experience", "text": "玩家的生日是 5 月 20 日",
         "verbatim": "我生日是 5 月 20 日哦", "tags": ["玩家"], "significance": 0.7},
        {"kind": "experience", "title": "忘了 text"},          # 缺 text → 拒
    ]}
    items, result = digest_registry.parse_round_a(raw)
    assert not result.is_valid
    assert any("text" in e for e in result.errors)
    assert len(items) == 1
    assert items[0]["kind"] == "experience"
    assert items[0]["subject"] == "player"          # 引擎固定, 不信任 LLM
    assert items[0]["text"].startswith("玩家的生日")


def test_round_a_bad_kind_rejected():
    items, result = digest_registry.parse_round_a({"episodes": [
        {"kind": "belief", "text": "不是合法形态"},
    ]})
    assert not result.is_valid
    assert any("kind 非法" in e for e in result.errors)


# ---------------------------------------------------------------------------
# T14 板指针 event_seq + verbatim 两条通道（2026-09-15）
# ---------------------------------------------------------------------------

def test_round_a_event_seq_pointer_validated():
    """★ `event_seq` = **板指针**（§3.3.1）——⊆ 本段 seq 集, 抄错丢弃。

    旧版把它列为引擎字段**直接丢弃**, 而 `digest.py` 又覆写成常量
    → 板指针从来没存在过（实测 `[60]` 而板最大 55）。
    """
    items, result = digest_registry.parse_round_a(
        {"episodes": [_ep(event_seq=["28", "30", "999", "坏"])]},
        seq_set={28, 30, 32})
    assert items[0]["event_seq"] == [28, 30], items[0]   # 999/坏 逐条丢弃
    assert any("999" in w for w in result.warnings)
    # 去重 + 记录级写法按事件收下（并提醒）
    items2, res2 = digest_registry.parse_round_a(
        {"episodes": [_ep(event_seq=["28", "28", "30.1"])]}, seq_set={28, 30})
    assert items2[0]["event_seq"] == [28, 30]
    assert any("记录级" in w for w in res2.warnings)
    # 不传 seq_set → 不校验（老调用方/单测）
    items3, _ = digest_registry.parse_round_a({"episodes": [_ep(event_seq=[7])]})
    assert items3[0]["event_seq"] == [7]
    # 没有 event_seq → **不落字段**（引擎回落段级常量, 不编）
    items4, _ = digest_registry.parse_round_a({"episodes": [_ep()]}, seq_set={28})
    assert "event_seq" not in items4[0]
    print("    event_seq: 板指针 ⊆ 校验 + 坏项逐条丢弃 + 缺省不落字段")


def test_round_a_verbatim_two_channels():
    """★ `verbatim` 两条通道（用户 2026-09-15: 保留文本通道）。"""
    # ① 索引通道 → 落 verbatim_seq（此时还没有文本——解析要事件流, 在 digest.py）
    items, result = digest_registry.parse_round_a(
        {"episodes": [_ep(verbatim=["28.3", "20.p", "30"])]}, seq_set={28, 20, 30})
    assert items[0]["verbatim_seq"] == ["28.3", "20.p", "30"], items[0]
    assert "verbatim" not in items[0]
    # ② 文本通道 → 原样
    items2, _ = digest_registry.parse_round_a({"episodes": [_ep(verbatim="它想认识你。")]})
    assert items2[0]["verbatim"] == "它想认识你。"
    assert "verbatim_seq" not in items2[0]
    # ③ 显式 verbatim_seq 字段等价; 两条并存 → 合并去重（**verbatim 列表在先**,
    #    因为 schema 里 verbatim 是主字段, verbatim_seq 是它的显式别名）
    items3, _ = digest_registry.parse_round_a(
        {"episodes": [_ep(verbatim_seq=["28.3"], verbatim=["28.5"])]}, seq_set={28})
    assert items3[0]["verbatim_seq"] == ["28.5", "28.3"]
    # ④ 索引 ⊆ 校验: 段外编号丢弃; 全坏 → 不落 verbatim_seq
    items4, res4 = digest_registry.parse_round_a(
        {"episodes": [_ep(verbatim=["999.1"])]}, seq_set={28})
    assert "verbatim_seq" not in items4[0]
    assert any("999.1" in w for w in res4.warnings)
    # ⑤ verbatim_seq 非数组 → 忽略（不废整包）
    items5, res5 = digest_registry.parse_round_a(
        {"episodes": [_ep(verbatim_seq="28.3")]}, seq_set={28})
    assert "verbatim_seq" not in items5[0]
    assert any("必须是数组" in w for w in res5.warnings)
    print("    verbatim: 索引通道 / 文本通道 / 显式字段 / ⊆ 校验 / 坏形态忽略")


def test_schema_documents_pointer_and_channels():
    """schema 文案必须描述 T14 的两个字段（镜像防漂移）。"""
    text = digest_registry.build_schema(PHASE_RECORD)
    assert "event_seq" in text and "指位置, 不是打分" in text
    assert "28.3" in text and "20.p" in text
    assert "给一条即可" in text
    print("    schema: 板指针 + verbatim 两通道 已文档化")


# ---------------------------------------------------------------------------
# Round A 情绪两标量 emo_int / emo_span（§3.3.3, 2026-09-13）
# （`emo_valence` 2026-09-21 删——有生产零消费; 极性由 `emo_shape` 逐键承担）
# ---------------------------------------------------------------------------

def _ep(**over):
    base = {"kind": "episode", "text": "她笑了一下。", "title": "测试条目",
            "tags": ["测试"]}
    base.update(over)
    return base


def test_round_a_hint_and_items():
    """D1: `about_hint`（归属线索, **不落库**）与 `items`（物品台账）的契约形状。

    三层判据: ① schema 必须**写明**这两个字段（文案漂移守门, 同下面那条 pointer 用例）
    ② 正常值透传 ③ 坏形态/超限的处理（空 hint 不落字段、items 截到 3、非字符串项丢弃）。
    """
    text = digest_registry.build_schema(PHASE_RECORD)
    assert "about_hint" in text and "三个月后再提到它" in text
    assert '"items"' in text and "得到/失去了什么实物" in text

    items, result = digest_registry.parse_round_a({"episodes": [
        _ep(about_hint=" 老师 ", items=["一盆杂草", "锈饼干盒", "", 7])]})
    assert result.is_valid, result.errors
    assert items[0]["about_hint"] == "老师"                   # 去空白
    assert items[0]["items"] == ["一盆杂草", "锈饼干盒"]        # 非字符串项丢弃
    # 缺/空 → **整条字段不存在**（不是空串/空数组）
    items2, _ = digest_registry.parse_round_a({"episodes": [
        _ep(about_hint="  ", items=[])]})
    assert "about_hint" not in items2[0] and "items" not in items2[0]
    # 超限截断
    items3, _ = digest_registry.parse_round_a({"episodes": [
        _ep(items=["1", "2", "3", "4"])]})
    assert items3[0]["items"] == ["1", "2", "3"]
    print("    about_hint/items: schema 已文档化 + 清洗（空省略 / 截断 / 坏项丢弃）")


def test_round_a_emo_fields_pass_through():
    items, result = digest_registry.parse_round_a({"episodes": [
        _ep(emo_int=0.8, emo_span=0.7)]})
    assert result.is_valid, result.errors
    assert items[0]["emo_int"] == 0.8
    assert items[0]["emo_span"] == 0.7
    print("    emo_int/emo_span: 原样透传")


def test_round_a_emo_absent_stays_absent():
    """★ 缺 → **不落字段**（None 哨兵）——「未采集」≠「真的毫无波澜」。"""
    items, result = digest_registry.parse_round_a({"episodes": [_ep()]})
    assert result.is_valid
    for f in ("emo_int", "emo_span", "emo_valence"):
        assert f not in items[0], f"{f} 不该出现"
    print("    emo_*: 缺 → 字段不存在（不折成 0.0）")


def test_round_a_emo_zero_is_kept():
    """0.0 是合法值（无波澜 / 全程一个调子）——必须保留。"""
    items, result = digest_registry.parse_round_a({"episodes": [
        _ep(emo_int=0.0, emo_span=0.0)]})
    assert result.is_valid
    assert items[0]["emo_int"] == 0.0
    assert items[0]["emo_span"] == 0.0
    print("    emo_*: 0.0 保留（不是缺省）")


def test_round_a_emo_clamped_and_bad_ignored():
    # 越界 → 夹紧（值仍可用, 不整条丢）
    items, _ = digest_registry.parse_round_a({"episodes": [
        _ep(emo_int=9, emo_span=9)]})
    assert items[0]["emo_int"] == 1.0
    assert items[0]["emo_span"] == 1.0, "emo_span 上界 1.0"
    # ★ emo_span 声明非负: 负值被夹到 0（不是丢字段）
    items, _ = digest_registry.parse_round_a({"episodes": [_ep(emo_span=-0.5)]})
    assert items[0]["emo_span"] == 0.0, "emo_span 负值应夹到 0（是幅度不是方向）"
    # 坏值 → 忽略该字段（不折成 0.0）, 条目本身仍有效
    for bad in ("abc", True, float("nan"), [], {}):
        items, result = digest_registry.parse_round_a({"episodes": [
            _ep(emo_int=bad, emo_span=bad)]})
        assert result.is_valid, f"{bad!r} 不该让整条失效"
        for f in ("emo_int", "emo_span", "emo_valence"):
            assert f not in items[0], f"{bad!r} 的 {f} 应被忽略而非折成 0.0"
    print("    emo_*: 越界夹紧（span 负值→0） / 坏值忽略（不折 0.0, 不整条丢）")


# ---------------------------------------------------------------------------
# Round B parse
# ---------------------------------------------------------------------------

def test_round_b_valid_decisions():
    raw = {"decisions": [
        {"episode": "m0001", "decision": "touch", "target": "u0001"},
        {"episode": "m0002", "decision": "update", "target": "u0002",
         "patch": {"text": "新表述", "significance": 0.9}},
        {"episode": "m0003", "decision": "add", "kind": "belief",
         "subject": "我对老师的信任", "text": "老师是第一个不嫌弃我的人",
         "tags": ["信任"], "significance": 0.85},
    ], "evidence": [{"function": "fe", "confidence": 0.9,
                     "quote": "老师把猫抱到我腿边"}],
       "affection_exp_delta": 30}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001", "m0002", "m0003"},
        target_ids={"u0001", "u0002", "u0003"})
    assert result.is_valid, result.errors
    assert len(rows) == 3
    assert rows[0] == {"episode": "m0001", "decision": "touch", "target": "u0001"}
    assert rows[1]["patch"]["text"] == "新表述"
    assert rows[2]["kind"] == "belief" and rows[2]["text"]


def test_round_b_coverage_required():
    raw = {"decisions": [
        {"episode": "m0001", "decision": "touch", "target": "u0001"},
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001", "m0002"}, target_ids={"u0001"})
    assert not result.is_valid
    assert any("未覆盖" in e and "m0002" in e for e in result.errors)


def test_round_b_id_discipline():
    raw = {"decisions": [
        {"episode": "ghost001", "decision": "touch", "target": "u0001"},  # 编造 episode
        {"episode": "m0001", "decision": "touch", "target": "u0099"},      # 编造 target
        {"episode": "m0002", "decision": "add", "kind": "belief",
         "subject": "s", "text": "c"},
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001", "m0002"}, target_ids={"u0001"})
    assert not result.is_valid
    assert any("episode 不在本轮" in e for e in result.errors)
    assert any("target 不在渲染列表" in e for e in result.errors)


def test_round_b_update_guards():
    raw = {"decisions": [
        {"episode": "m0001", "decision": "update", "target": "u0001",
         "patch": {"epistemic": "observed_fact"}},         # epistemic 禁改
        {"episode": "m0002", "decision": "update", "target": "u0001",
         "patch": {}},                                     # 空 patch
        {"episode": "m0003", "decision": "add", "kind": "experience",
         "text": "老师总说摸鱼"},                        # experience 也认 text（三槽合流）
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001", "m0002", "m0003"}, target_ids={"u0001"})
    assert not result.is_valid
    assert any("epistemic" in e for e in result.errors)
    assert any("patch" in e for e in result.errors)
    assert len(rows) == 1 and rows[0]["kind"] == "experience"


def test_round_b_bad_decision_kind():
    raw = {"decisions": [
        {"episode": "m0001", "decision": "delete"},       # 非法决策
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001"}, target_ids={"u0001"})
    assert not result.is_valid
    assert any("decision 非法" in e for e in result.errors)


# ---------------------------------------------------------------------------
# must_touch 已删（T17, 2026-09-15）——候选降为提示，引擎不设闸门
# ---------------------------------------------------------------------------

def test_round_b_add_is_never_gated():
    """★ **引擎不再禁 add**（Q11/Q31/Q32）。

    旧行为: 引擎候选 ≥ `CAND_HIGH` → 该 episode 出 `add` 整行作废。
    那个阈值从未标定过、实测两模型下候选 6/6 全越线 → **新认知永远长不出来**。
    现在判 add/touch/update 全归 LLM（prompt 要求判 add 时在 note 里说明理由）。
    """
    raw = {"decisions": [
        {"episode": "m0001", "decision": "add", "kind": "belief",
         "subject": "s", "text": "一条全新的认知", "note": "与候选只是字面像"},
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001"}, target_ids={"u0001"})
    assert result.is_valid, result.errors
    assert len(rows) == 1 and rows[0]["decision"] == "add"
    # 引擎里不再有任何"候选 → 禁 add"的入口
    import inspect
    sig = inspect.signature(digest_registry.parse_round_b)
    assert "must_touch" not in sig.parameters
    assert not any("疑似同主题" in e for e in result.errors)
    print("    Round B: add 不再被引擎闸门拦（must_touch 已删）")
