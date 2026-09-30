"""digest_registry 测试（AGENT_BRAIN.md §3 重构 / 板块 2）——LLM 契约层单源。"""
from contract.digest_registry import (
    PHASE_CLOSE,
    PHASE_PANORAMA,
    PHASE_RECORD,
    PHASE_UNDERSTAND,
    PROMISE_OUTCOMES,
    digest_registry,
)


# ---------------------------------------------------------------------------
# 全景轮（写卡）—— `{"habits": […], "drop": […], "on_mind": {…}|null}`
# ---------------------------------------------------------------------------

def _card(**over):
    card = {"habits": [{"id": "n4", "text": "他总先问我想要哪个",
                        "refs": ["m0005", "m0010"]},
                       {"text": "周四晚上会发晚安", "refs": ["m0012", "m0013"]}],
            "drop": [{"id": "n7", "afterwards": "他最近不怎么喝咖啡了"}],
            "on_mind": {"text": "我不想再只是隔着玻璃看", "refs": ["m0009"]}}
    card.update(over)
    return card


def test_schema_panorama_phase():
    text = digest_registry.build_schema(PHASE_PANORAMA)
    for key in ('"habits": [', '"drop": [', '"on_mind": {'):
        assert key in text
    assert "三个键都要在" in text
    assert "不要盲删" in text and "漏写" in text          # 两条硬规则都在契约里
    assert "照抄" in text and "编号" in text              # 延续靠 id
    # 示例只有一种形状（设计稿陷阱 3/4）
    assert text.count('"id": "n4"') == 1 and text.count('"id": "n7"') == 1


def test_parse_panorama_normalizes_the_card():
    card, res = digest_registry.parse_panorama(_card(), habit_ids={"n4", "n7"})
    assert res.errors == ()
    assert card["habits"][0] == {"id": "n4", "text": "他总先问我想要哪个",
                                 "refs": ["m0005", "m0010"]}
    assert card["habits"][1]["id"] == ""                  # 新条目不写 id
    assert card["drop"] == [{"id": "n7", "afterwards": "他最近不怎么喝咖啡了"}]
    assert card["on_mind"]["text"] == "我不想再只是隔着玻璃看"


def test_parse_panorama_rejects_silent_drop():
    """⭐ 上一版有一条既没留也没删 ⇒ **拒整包**（沉默不是删除, 是漏写）。"""
    card, res = digest_registry.parse_panorama(_card(drop=[]), habit_ids={"n4", "n7"})
    assert card == {} and any("漏写" in e and "n7" in e for e in res.errors)


def test_parse_panorama_shape_and_reference_errors():
    cases = [
        (["nope"], "必须是 JSON 对象"),
        ({"habits": [], "drop": []}, "缺键 'on_mind'"),
        (_card(habits={}), "habits 必须是数组"),
        (_card(habits=["x"]), "habits[0] 必须是对象"),
        (_card(habits=[{"id": "n4"}]), "habits[0] 缺 text"),
        (_card(habits=[{"id": "n9", "text": "x"}]), "不在上一版的编号里"),
        (_card(habits=[{"id": "n4", "text": "a"}, {"id": "n4", "text": "b"}]),
         "id 重复"),
        (_card(drop=[{"id": "n4", "afterwards": "y"},
                     {"id": "n7", "afterwards": "z"}]), "既在 habits 又在 drop"),
        (_card(drop=[{"id": "n7"}]), "缺 afterwards"),
        (_card(drop=[{"id": "n9", "afterwards": "x"}]), "不在上一版的编号里"),
        (_card(on_mind="一句话"), "必须是对象或 null"),
        (_card(on_mind={"refs": ["m1"]}), "on_mind 缺 text"),
    ]
    for raw, want in cases:
        card, res = digest_registry.parse_panorama(raw, habit_ids={"n4", "n7"})
        assert any(want in e for e in res.errors), (raw, res.errors)
        assert card == {}, raw


def test_parse_panorama_clearing_and_empty_previous_card():
    # 上一版是空的 ⇒ 三个键都空也合法（没有覆盖压力）
    card, res = digest_registry.parse_panorama(
        {"habits": [], "drop": [], "on_mind": None}, habit_ids=set())
    assert res.errors == () and card == {"habits": [], "drop": [], "on_mind": None}
    # 全删（每条都在 drop 里点名）也合法 —— 但**必须点名**
    card2, res2 = digest_registry.parse_panorama(
        {"habits": [], "drop": [{"id": "n4", "afterwards": "不再成立了"}],
         "on_mind": None}, habit_ids={"n4"})
    assert res2.errors == () and card2["habits"] == []


# ---------------------------------------------------------------------------
# R4 收口（`{"add": […], "close": […]}`）
# ---------------------------------------------------------------------------

def test_schema_close_phase():
    text = digest_registry.build_schema(PHASE_CLOSE)
    assert '"add": [' in text and '"close": [' in text
    assert "两个键**都要在**" in text
    for w in PROMISE_OUTCOMES:
        assert w in text
    assert "必填" in text                       # afterwards 必填
    # 示例只有一种形状（设计稿陷阱 3/4）: 契约里出现的示例行就是那两行
    assert text.count('"text": "周六模型店"') == 1
    assert text.count('"id": "n1"') == 1


def test_parse_close_keeps_good_rows():
    rows, res = digest_registry.parse_close({
        "add": [{"text": "周六模型店", "refs": ["m0013"], "due": "2026-09-26"},
                {"text": "还他笔记", "refs": ["m0004", "m0005"]}],
        "close": [{"id": "n1", "state": "kept", "afterwards": "周六真的去了"}]})
    assert res.errors == ()
    assert rows[0] == {"action": "add", "text": "周六模型店", "refs": ["m0013"],
                       "due": "2026-09-26"}
    assert "due" not in rows[1]                 # 空 due 不落键
    assert rows[2] == {"action": "close", "id": "n1", "state": "kept",
                       "afterwards": "周六真的去了"}


def test_parse_close_shape_errors_reject_the_package():
    """**形状错 = 拒整包**（重试有用）: 缺键 / 不是数组 / 行不是对象 / 值域 / 必填。"""
    cases = [
        (["nope"], "必须是 JSON 对象"),
        ({"add": []}, "缺键 'close'"),
        ({"add": {}, "close": []}, "add 必须是数组"),
        ({"add": ["x"], "close": []}, "add[0] 必须是对象"),
        ({"add": [{"refs": ["m1"]}], "close": []}, "add[0] 缺 text"),
        ({"add": [{"text": "x"}], "close": []}, "add[0] 缺 refs"),
        ({"add": [], "close": [{"state": "kept", "afterwards": "x"}]}, "close[0] 缺 id"),
        ({"add": [], "close": [{"id": "n1", "state": "done", "afterwards": "x"}]},
         "state 非法"),
        ({"add": [], "close": [{"id": "n1", "state": "kept"}]}, "缺 afterwards"),
    ]
    for raw, want in cases:
        rows, res = digest_registry.parse_close(raw)
        assert any(want in e for e in res.errors), (raw, res.errors)
        assert rows == [], raw


def test_parse_close_dedupes_with_warning():
    rows, res = digest_registry.parse_close({
        "add": [], "close": [
            {"id": "n1", "state": "kept", "afterwards": "去了"},
            {"id": "n1", "state": "broken", "afterwards": "没去"}]})
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
    """schema 文案必须描述位置字段与 verbatim 两通道（镜像防漂移）。

    ⭐ **N3（2026-09-29）改了位置字段的形状**: `event_seq: ["28","30"]`（逐点挑选）
    → **`span: [28, 30]`**（区间, 引擎负责展开）。⚠️ 示例才是形状的来源（陷阱 3/46）
    ⇒ 这条镜像断言必须跟着改，否则文案漂了没人知道。
    """
    text = digest_registry.build_schema(PHASE_RECORD)
    assert "span" in text and "指位置, 不是打分" in text
    assert "覆盖【哪一段】" in text
    assert "28.3" in text and "20.p" in text
    assert "给一条即可" in text
    # ⚠️ 旧形状**不再**出现在给 LLM 看的文案里（只在 parse 层作兼容收下）
    assert '"event_seq"' not in text
    print("    schema: 位置区间(span) + verbatim 两通道 已文档化")


# ---------------------------------------------------------------------------
# ⭐ N3（2026-09-29）: 位置 = **区间** `span: [起, 止]`（原来是逐点挑选 `event_seq`）
#    病根真机实测: 挑点必然漏 —— 覆盖率只有 67.9%（218 条内容事件里 70 条没进任何记忆）
# ---------------------------------------------------------------------------

def test_span_accepts_interval_and_degenerates():
    """`span: [28, 30]` 收下；**单值退化成一块**；>2 端点只取首尾。"""
    items, res = digest_registry.parse_round_a(
        {"episodes": [_ep(span=[28, 30])]}, seq_set={28, 29, 30, 31})
    assert items[0]["span"] == [28, 30] and not res.errors
    items2, _ = digest_registry.parse_round_a(
        {"episodes": [_ep(span=28)]}, seq_set={28})
    assert items2[0]["span"] == [28, 28]
    items3, res3 = digest_registry.parse_round_a(
        {"episodes": [_ep(span=[28, 29, 30, 31])]}, seq_set={28, 31})
    assert items3[0]["span"] == [28, 31]
    assert any("只取首尾" in w for w in res3.warnings)
    print("    span: 区间 / 单值退化 / 多端点取首尾")


def test_span_rejects_bad_shape_without_killing_the_pack():
    """⚠️ 坏区间**告警不废整包** —— 一个坏区间不该让她重写整段（与 `_clean_seq_list` 同纪律）。

    坏法逐条: 起止反了（**不自动交换**）· 端点不存在 · 非数组 · 坏编号 · 空数组。
    四种坏法下 **`text` 都还在**（位置丢了 ≠ 记忆丢了）。
    """
    for bad, why in (([30, 28], "起止反了"), ([28, 99], "端点不存在"),
                     ("x", "不是编号"), ([], "空数组"), ({"a": 1}, "不是数组")):
        items, res = digest_registry.parse_round_a(
            {"episodes": [_ep(span=bad)]}, seq_set={28, 29, 30})
        assert len(items) == 1, f"{why}: 整条被丢了"
        assert items[0]["text"] and "span" not in items[0]
        assert res.warnings, f"{why}: 没告警"
    # 起止反了**不被偷偷交换**
    items, _ = digest_registry.parse_round_a(
        {"episodes": [_ep(span=[30, 28])]}, seq_set={28, 30})
    assert "span" not in items[0]
    print("    span: 五种坏法 ⇒ 告警 + 只丢位置, 丢不了记忆")


def test_span_accepts_record_level_index_with_warning():
    """端点写成记录级 `"28.3"` ⇒ 取事件部分 `28` + 告警（与 `_clean_seq_list` 同款）。"""
    items, res = digest_registry.parse_round_a(
        {"episodes": [_ep(span=["28.3", "30.p"])]}, seq_set={28, 30})
    assert items[0]["span"] == [28, 30]
    assert any("记录级" in w for w in res.warnings)
    print("    span: 记录级索引取事件部分")


def test_legacy_event_seq_still_accepted_but_warned():
    """⭐ **旧形状仍收**（防契约漂移时整条丢位置）, **但不展开** + 告警（宁缺勿错）。

    ⚠️ 为什么不把 `["14","16","18"]` 自动转成 `[14, 18]` 区间: 那是她**自己挑的点**,
    转区间 = **替她加上她没声称的事件**。位置形状的漂移要**看得见**（告警）, 不能替她猜。
    """
    items, res = digest_registry.parse_round_a(
        {"episodes": [_ep(event_seq=["14", "16", "18"])]}, seq_set={14, 16, 18})
    assert items[0]["event_seq"] == [14, 16, 18] and "span" not in items[0]
    assert any("旧形状 event_seq" in w for w in res.warnings)
    # `span` 优先: 两个都给 ⇒ 只收 span
    items2, _ = digest_registry.parse_round_a(
        {"episodes": [_ep(span=[14, 18], event_seq=["14", "16"])]},
        seq_set={14, 16, 18})
    assert items2[0]["span"] == [14, 18] and "event_seq" not in items2[0]
    # 两个都不给 ⇒ 没有位置（节点 `event_seq` 为空 ⇒ `_node_ts` 回落段 ts）
    items3, _ = digest_registry.parse_round_a({"episodes": [_ep()]}, seq_set={14})
    assert "span" not in items3[0] and "event_seq" not in items3[0]
    print("    span 优先 / 旧形状兼容 + 告警 / 都不给 = 没位置")


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
    assert any("target 不在可 touch/update 的列表内" in e for e in result.errors)


def test_round_b_update_guards():
    raw = {"decisions": [
        {"episode": "m0001", "decision": "update", "target": "u0001",
         "patch": {"epistemic": "observed_fact"}},         # epistemic 禁改
        {"episode": "m0002", "decision": "update", "target": "u0001",
         "patch": {}},                                     # 空 patch
        {"episode": "m0003", "decision": "add", "kind": "belief",
         "text": "老师总说摸鱼"},                          # add 走 belief（含模式句）
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001", "m0002", "m0003"}, target_ids={"u0001"})
    assert not result.is_valid
    assert any("epistemic" in e for e in result.errors)
    assert any("patch" in e for e in result.errors)
    assert len(rows) == 1 and rows[0]["kind"] == "belief"


def test_round_b_add_experience_is_rejected():
    """⭐ 2026-09-25（§5.1）: `add kind=experience` **被拒** —— 那个 kind 是
    玩家画像专用（写者只有第 1 轮），"反复出现的模式"要写成 `belief` 的模式句（§9-10）。

    为什么不是"悄悄降级成 belief": 契约要**教会**模型这条边界, 静默改 kind 会让它
    一直以为自己在写 experience（下次还写）; 拒一次带反馈, 它才学得会。
    """
    raw = {"decisions": [
        {"episode": "m0001", "decision": "add", "kind": "experience",
         "subject": "我表达善意时的习惯", "text": "我总先说好意再道歉"},
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001"}, target_ids=set())
    assert not result.is_valid and rows == []
    assert any("kind 非法" in e and "belief" in e for e in result.errors)


def test_round_b_links_are_extra_edges():
    """⭐ 2026-09-25（§9-13）: R2 的**补充边** `links` —— 让"承诺 → 看法"有处可写。

    ⚠️ 它与决策行**同一个数组**交出去（执行器一个循环处理两类）, 但**不参与覆盖统计**
    （`link` 行没有 episode —— 覆盖检查说的还是"每个 episode 恰好一行 decision"）。
    """
    raw = {"decisions": [{"episode": "m0001", "decision": "add", "kind": "belief",
                          "subject": "sensei", "text": "老师答应的事都做到了"}],
           "links": [{"from": "u0009", "rel": "supports", "to": "u0002"},
                     {"from": "u0007", "rel": "evolved_from", "to": "u0009"},
                     {"from": "u0003", "rel": "contradicts", "to": "u0005"},
                     {"from": "u0009", "rel": "supports", "to": "u0002"}]}   # 重复
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001"}, target_ids={"u0002"},
        link_ids={"u0002", "u0003", "u0005", "u0007", "u0009"})

    assert result.is_valid, result.errors
    links = [r for r in rows if r.get("action") == "link"]
    assert links == [
        {"action": "link", "rel": "supports", "from": "u0009", "to": "u0002"},
        {"action": "link", "rel": "evolved_from", "from": "u0007", "to": "u0009"},
        {"action": "link", "rel": "contradicts", "from": "u0003", "to": "u0005"}]
    assert any("重复" in w for w in result.warnings)          # 多说一遍 = warning 不是错
    assert [r for r in rows if r.get("action") != "link"][0]["decision"] == "add"


def test_round_b_links_reject_bad_shape():
    """形状错同样**拒整包**: rel 是契约词汇的一部分, 两端是列表里的编号。"""
    def _parse(links, **kw):
        return digest_registry.parse_round_b(
            {"decisions": [{"episode": "m0001", "decision": "add", "kind": "belief",
                            "subject": "s", "text": "t"}], "links": links},
            episode_ids={"m0001"}, target_ids={"u0001"},
            link_ids=kw.get("link_ids", {"u0001", "u0002"}))

    _, r = _parse([{"from": "u0001", "rel": "about", "to": "u0002"}])
    assert not r.is_valid and any("rel 非法" in e for e in r.errors)
    _, r = _parse([{"from": "u0009", "rel": "supports", "to": "u0002"}])
    assert not r.is_valid and any("不在渲染列表内" in e for e in r.errors)
    _, r = _parse([{"from": "u0001", "rel": "supports", "to": "u0001"}])
    assert not r.is_valid and any("自环" in e for e in r.errors)
    _, r = _parse({"from": "u0001"})
    assert not r.is_valid and any("links 必须是数组" in e for e in r.errors)
    # 省略这个键 = 合法（可选）
    rows, r = digest_registry.parse_round_b(
        {"decisions": [{"episode": "m0001", "decision": "add", "kind": "belief",
                        "subject": "s", "text": "t"}]},
        episode_ids={"m0001"}, target_ids={"u0001"})
    assert r.is_valid and not [x for x in rows if x.get("action") == "link"]


def test_promise_can_be_linked_but_not_touched():
    """⭐ 两个 id 空间**故意不同**（§5.1/§9-13）: 承诺进 `link_ids`（它要能被连）,
    但**不进 `target_ids`**（它不是看法, 正文在固化那一刻写死了）。"""
    rows, result = digest_registry.parse_round_b(
        {"decisions": [{"episode": "m0001", "decision": "touch", "target": "u0009"}]},
        episode_ids={"m0001"}, target_ids={"u0001"}, link_ids={"u0001", "u0009"})
    assert not result.is_valid
    assert any("不在可 touch/update 的列表内" in e for e in result.errors)
    # 同一条承诺走 links 就合法
    rows, result = digest_registry.parse_round_b(
        {"decisions": [{"episode": "m0001", "decision": "add", "kind": "belief",
                        "subject": "s", "text": "t"}],
         "links": [{"from": "u0009", "rel": "supports", "to": "u0001"}]},
        episode_ids={"m0001"}, target_ids={"u0001"}, link_ids={"u0001", "u0009"})
    assert result.is_valid, result.errors


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
