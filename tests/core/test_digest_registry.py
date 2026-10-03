"""digest_registry 测试（AGENT_BRAIN.md §3 重构 / 板块 2）——LLM 契约层单源。"""
from contract.digest_registry import (
    PHASE_CLOSE,
    PHASE_RECORD,
    PHASE_UNDERSTAND,
    PINNED_OUTCOMES,
    digest_registry,
)


# ---------------------------------------------------------------------------
# 收口相位 —— `{"add": […], "close": […]}`
# ⛔ ~~全景轮（写卡）~~ 2026-09-29（N4a/N4e）整条退役: `habits` 与 `on_mind` 两个槽都没了。
# ---------------------------------------------------------------------------

def test_schema_close_phase():
    text = digest_registry.build_schema(PHASE_CLOSE)
    assert '"add": [' in text and '"close": [' in text
    assert "两个键**都要在**" in text
    for w in PINNED_OUTCOMES:
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
    # ⭐ 2026-09-29: `evidence` 退役 —— schema 里**不许再出现它**（防契约键名的回音长回来）
    assert "affection_exp_delta" in text and "evidence" not in text
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
         "tags": ["睦月", "阿露"],
         "observer": "asagi_mutsuki", "significance": 0.6},
    ]}
    items, result = digest_registry.parse_round_a(raw)
    assert result.is_valid, result.errors
    assert len(items) == 2
    assert items[0]["text"].startswith("老师约我")
    assert items[0].get("observer", "") == ""           # 不写 observer = 亲历（没有 epistemic 了）
    assert items[1]["observer"] == "asagi_mutsuki"      # ⭐ 来源只剩这一个字段（2026-09-29）
    assert "epistemic" not in items[1]


def test_round_a_rejects_bad_entries():
    raw = {"episodes": [
        {"title": "没有正文"},                       # 缺 text
        {"text": "x" * 400},                    # 超长
        {"text": "旧 prompt 缓存带来的键", "title": "旧键",
         "epistemic": "reported_fact", "observer": "阿露"},   # ⏸ 退役键: 只告警
        {"text": "ok", "title": "t", "id": "m9999"},   # 引擎字段应被忽略(警告)
    ]}
    items, result = digest_registry.parse_round_a(raw)
    assert not result.is_valid
    assert any("text" in e for e in result.errors)          # 缺正文
    assert any("300 字" in e for e in result.errors)             # 超长
    assert any("引擎字段" in w for w in result.warnings)         # id 忽略
    assert any("已退役" in w for w in result.warnings)           # ⏸ 旧 epistemic 只告警
    # 坏条目丢弃, 好的保留（退役键那一条照收 —— 信息在 observer 里, 没丢）
    assert [i["text"] for i in items] == ["旧 prompt 缓存带来的键", "ok"]
    assert items[0]["observer"] == "阿露" and "epistemic" not in items[0]


def test_round_a_caps_and_defaults():
    raw = {"episodes": [{"text": f"e{i}", "title": f"t{i}"} for i in range(7)]}
    items, result = digest_registry.parse_round_a(raw)
    assert len(items) == 5                       # MAX_EPISODES 截断
    assert items[0]["significance"] == 0.5       # 缺省
    assert "epistemic" not in items[0]           # ⏸ 字段已退役（缺省不再是"给个默认值"）
    assert any("5 条" in e for e in result.errors)


def test_round_a_not_dict():
    items, result = digest_registry.parse_round_a(["nope"])
    assert items == [] and not result.is_valid


def test_round_a_kind_is_exception_only():
    """⭐ 2026-09-29: **`kind` 只在例外时写**（用户裁决: 轮次决定的常量不该由 LLM 声明）。

    默认 = 经历（缺键 / 空串都算）; 唯一要显式写的例外 = `experience`（玩家画像）;
    写坏值照旧**拒**（不静默降级 —— 静默改 kind 会让模型下次还这么写）。
    """
    raw = {"episodes": [
        {"text": "老师约我去公园散步。", "title": "公园散步", "tags": ["公园"]},
        {"kind": "", "text": "空串也算默认。", "title": "空 kind", "tags": ["x"]},
        {"kind": "experience", "text": "玩家的生日是 5 月 20 日",
         "verbatim": ["3.0"], "tags": ["玩家"], "significance": 0.7},
        {"kind": "experience", "title": "忘了 text"},          # 缺 text → 拒
    ]}
    items, result = digest_registry.parse_round_a(raw)
    assert not result.is_valid                                # 只有第 4 条坏
    assert any("text" in e for e in result.errors)
    assert len(items) == 3
    assert [it["kind"] for it in items] == ["episode", "episode", "experience"]
    assert items[0]["text"].startswith("老师约我")            # 不写 kind ⇒ 经历
    assert items[1]["kind"] == "episode"                     # 空串 ⇒ 也是经历
    assert items[2]["subject"] == "player"                   # 引擎固定, 不信任 LLM
    assert items[2]["text"].startswith("玩家的生日")
    assert items[2]["verbatim_seq"] == ["3.0"]               # 玩家原话走**记录行号**（`[N.0]`）


def test_round_a_bad_kind_rejected():
    """坏 kind 拒 → 不静默降级; 错误文案要教它"不写 = 经历"（2026-09-29 改口径）。"""
    items, result = digest_registry.parse_round_a({"episodes": [
        {"kind": "belief", "text": "不是合法形态"},
        {"kind": "episode", "text": "显式写 episode 仍然合法（旧 prompt 缓存）",
         "title": "t", "tags": ["x"]},
    ]})
    assert not result.is_valid
    assert any("kind 非法" in e for e in result.errors)
    assert any("不写 = 经历" in e for e in result.errors)      # 指路牌
    assert len(items) == 1 and items[0]["kind"] == "episode"  # 显式的照收


# ---------------------------------------------------------------------------
# T14 板指针 event_seq + verbatim 记录行号（2026-09-15; ⑤ 2026-09-29 收成单通道）
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


def test_round_a_verbatim_is_record_indices_only():
    """★ `verbatim` **只有记录行号一条通道**（文本通道 2026-09-29 退役, `REDUNDANCY.md` #6）。"""
    # ① 记录行号 → 落 verbatim_seq（此时还没有文本——解析要事件流, 在 digest.py）
    items, result = digest_registry.parse_round_a(
        {"episodes": [_ep(verbatim=["28.3", "20.p", "30"])]}, seq_set={28, 20, 30})
    assert items[0]["verbatim_seq"] == ["28.3", "20.p", "30"], items[0]
    assert "verbatim" not in items[0]
    # ② ⛔ 文本通道已退役: 字符串**不落库**（也不兜底）+ 告警
    items2, res2 = digest_registry.parse_round_a(
        {"episodes": [_ep(verbatim="它想认识你。")]})
    assert "verbatim" not in items2[0] and "verbatim_seq" not in items2[0], items2[0]
    assert any("必须是数组" in w for w in res2.warnings), res2.warnings
    # ③ 显式 verbatim_seq 字段等价; 两条并存 → 合并去重（**verbatim 列表在先**,
    #    因为 schema 里 verbatim 是主字段, verbatim_seq 是它的显式别名）
    items3, _ = digest_registry.parse_round_a(
        {"episodes": [_ep(verbatim_seq=["28.3"], verbatim=["28.5"])]}, seq_set={28})
    assert items3[0]["verbatim_seq"] == ["28.5", "28.3"]
    # ④ 行号 ⊆ 校验: 段外编号丢弃; 全坏 → 不落 verbatim_seq
    items4, res4 = digest_registry.parse_round_a(
        {"episodes": [_ep(verbatim=["999.1"])]}, seq_set={28})
    assert "verbatim_seq" not in items4[0]
    assert any("999.1" in w for w in res4.warnings)
    # ⑤ 非数组 → 忽略（不废整包）
    items5, res5 = digest_registry.parse_round_a(
        {"episodes": [_ep(verbatim_seq="28.3")]}, seq_set={28})
    assert "verbatim_seq" not in items5[0]
    assert any("必须是数组" in w for w in res5.warnings)
    print("    verbatim: 记录行号 / 显式字段 / ⊆ 校验 / 文本通道已退役（字符串忽略）")


def test_schema_documents_pointer_and_channels():
    """schema 文案必须描述位置字段与 verbatim 的记录行号（镜像防漂移）。

    ⭐ **N3（2026-09-29）改了位置字段的形状**: `event_seq: ["28","30"]`（逐点挑选）
    → **`span: [28, 30]`**（区间, 引擎负责展开）。⚠️ 示例才是形状的来源（陷阱 3/46）
    ⇒ 这条镜像断言必须跟着改，否则文案漂了没人知道。
    ⭐ **⑤（2026-09-29）把 `verbatim` 收成一条通道**（记录行号）⇒ 这里同时钉住
    "只给行号"与"字符串会被忽略"，防那条老通道被谁顺手加回来。
    ⭐ **⑥（2026-09-29）把 `kind` 收成"例外才写"** ⇒ 这里钉住契约文案说了这句话,
    并且**示例 JSON 里不再带 `"kind": "episode"`**（示例才是形状的来源, 陷阱 3/46）。
    """
    text = digest_registry.build_schema(PHASE_RECORD)
    assert "span" in text and "指位置, 不是打分" in text
    assert "覆盖【哪一段】" in text
    assert "28.3" in text and "20.p" in text
    assert "记录行号" in text
    assert "只给行号" in text and "写成字符串会被忽略" in text
    assert "默认就是" in text and "不用写 `kind`" in text
    # ⚠️ 旧形状**不再**出现在给 LLM 看的文案里（只在 parse 层作兼容收下）
    assert '"event_seq"' not in text
    assert "两条通道" not in text
    assert '"kind": "episode"' not in text            # 示例里不该再出现这一行
    print("    schema: 位置区间(span) + verbatim 记录行号 + kind 只在例外时写")


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
    """⚠️ `kind` 2026-09-29 起**只在例外时写** —— 夹具保留显式的 `"kind": "episode"`
    正是为了钉住"旧 prompt 缓存里带着它也一样收"（见 `test_round_a_bad_kind_rejected`）。"""
    base = {"kind": "episode", "text": "她笑了一下。", "title": "测试条目",
            "tags": ["测试"]}
    base.update(over)
    return base


def test_round_a_about_hint_retired():
    """⏸ `about_hint` **2026-09-29 退役** —— schema 里不许再出现, parse 也不认它。

    退役理由: 与 R3 的"挂谁"**判两次**（R1 猜一次、R3 再判一次, 还可能不一致）,
    而 R3 本来就有全量候选表 + 新节点正文 ⇒ 引擎不必替它预判（`REDUNDANCY.md` #2）。
    ⚠️ 这条是**反向守门**: 防它（或 `items` 那种同款）悄悄长回契约里。
    """
    text = digest_registry.build_schema(PHASE_RECORD)
    assert "about_hint" not in text, "about_hint 已退役, schema 里不许再出现"
    assert '"items"' not in text, "items 已退役（物品面走 inventory 旁路）"

    items, result = digest_registry.parse_round_a({"episodes": [
        _ep(about_hint="老师")]})                      # ← 过时字段: 应当被无视
    assert result.is_valid, result.errors
    assert "about_hint" not in items[0]
    print("    守门: schema 不含 about_hint / items; parse 也不认它们 ✓")


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
    ], "affection_exp_delta": 30}
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
    """⏸ 原「patch 不得含 epistemic」那条守卫 2026-09-29 随字段退役 —— 它今天只是
    白名单外的未知键, 由执行器（`revise._PATCH_FIELDS` 滤空 ⇒ 拒整包）拦下。"""
    raw = {"decisions": [
        {"episode": "m0002", "decision": "update", "target": "u0001",
         "patch": {}},                                     # 空 patch
        {"episode": "m0003", "decision": "add", "kind": "belief",
         "text": "老师总说摸鱼"},                          # add 走 belief（含模式句）
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001", "m0002", "m0003"}, target_ids={"u0001"})
    assert not result.is_valid
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
    """⭐ `links` = R2 的**补充边**（做决策表做不到的事）: 「看法支撑看法」· 取代 · 打架。

    ⚠️ 它与决策行**同一个数组**交出去（执行器一个循环处理两类）, 但**不参与覆盖统计**
    （`link` 行没有 episode —— 覆盖检查说的还是"每个 episode 恰好一行 decision"）。
    ⭐ **2026-09-29 用户裁决**: `supports` 的**两种形状都留** —— 决策表写
    `episode → 认知`, `links` 写 `认知 → 认知`（真机有 2 条实例 `m0003→m0008`/`m0003→m0018`）
    ⇒ 这一档**不是冗余入口**, 别当"两个入口"删掉。
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
    """⏸ **原 §9-13 的那条**（"承诺进 `link_ids` 但**不进 `target_ids`**"）**2026-09-29 作废** ——
    承诺退图, 不再有"两个 id 空间故意不同"这回事。

    留下的守门: ① `link_ids` 与 `target_ids` **可以不同**（参数照旧分开传, 那是通用形状）,
    不同的一条照样被拒; ② 端点必须在渲染列表里 —— 一条 **episode id** 进 `links`
    会被拒（这正是"`links` 写不出 `episode → 认知`"那条分工的机器守门）。
    """
    rows, result = digest_registry.parse_round_b(
        {"decisions": [{"episode": "m0001", "decision": "touch", "target": "u0009"}]},
        episode_ids={"m0001"}, target_ids={"u0001"}, link_ids={"u0001", "u0009"})
    assert not result.is_valid
    assert any("不在可 touch/update 的列表内" in e for e in result.errors)
    # 同一个 id 走 links 就合法（它只在 link_ids 里）
    rows, result = digest_registry.parse_round_b(
        {"decisions": [{"episode": "m0001", "decision": "add", "kind": "belief",
                        "subject": "s", "text": "t"}],
         "links": [{"from": "u0009", "rel": "supports", "to": "u0001"}]},
        episode_ids={"m0001"}, target_ids={"u0001"}, link_ids={"u0001", "u0009"})
    assert result.is_valid, result.errors
    # ⚠️ **episode 不在 `links` 的可达域**: `links` 只能写"看法之间"的边
    rows, result = digest_registry.parse_round_b(
        {"decisions": [{"episode": "m0001", "decision": "add", "kind": "belief",
                        "subject": "s", "text": "t"}],
         "links": [{"from": "m0001", "rel": "supports", "to": "u0001"}]},
        episode_ids={"m0001"}, target_ids={"u0001"}, link_ids={"u0001", "u0009"})
    assert not result.is_valid
    assert any("不在渲染列表内" in e for e in result.errors)


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
