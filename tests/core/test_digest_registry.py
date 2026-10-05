"""digest_registry 测试（AGENT_BRAIN.md §3 重构 / 板块 2）——LLM 契约层单源。"""
from contract.digest_registry import (
    MAX_SEGMENTS,
    PHASE_CLOSE,
    PHASE_RECORD,
    PHASE_SPLIT,
    PHASE_UNDERSTAND,
    PINNED_OUTCOMES,
    ROW_FIELDS,
    STATE_VALUES,
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
# R0 切分轮 —— 划区间 + abstract + **账目**（`state` / `id` / `due`）
# ⭐ 2026-10-05（L1）: `keep` 退役, 骨架与账目合成一张表（`DESIGN_DIGEST_LEDGER`）
# ---------------------------------------------------------------------------

def test_parse_split_keeps_the_five_legal_shapes():
    """⭐ 一行的合法形状只有五种（见 `parse_split` 的表）—— 一包全过, 零告警。"""
    segs, res = digest_registry.parse_split(
        {"segments": [
            {"span": [28, 30], "abstract": "老师在周日突然邀请我去了咖啡厅吃东西"},
            {"span": [31, 31], "abstract": "答应老师：以后每年生日都一起过",
             "state": "open", "due": "2027-05-13"},
            {"span": [32, 32], "abstract": "老师生日是 5/13", "state": "open", "id": "n3",
             "due": "2027-05-13"},
            {"span": [33, 33], "abstract": "我把团子带来了", "state": "close", "id": "n5"},
            {"span": None, "abstract": "生日那天，老师没有来", "state": "close", "id": "n4"},
        ]},
        seq_set={28, 29, 30, 31, 32, 33}, note_ids={"n3", "n4", "n5"},
        overdue_ids={"n4"})
    assert res.errors == () and res.warnings == () and res.drops == ()
    assert segs == [
        {"span": [28, 30], "abstract": "老师在周日突然邀请我去了咖啡厅吃东西"},
        {"span": [31, 31], "abstract": "答应老师：以后每年生日都一起过",
         "state": "open", "due": "2027-05-13"},
        {"span": [32, 32], "abstract": "老师生日是 5/13", "state": "open", "id": "n3",
         "due": "2027-05-13"},
        {"span": [33, 33], "abstract": "我把团子带来了", "state": "close", "id": "n5"},
        {"span": None, "abstract": "生日那天，老师没有来", "state": "close", "id": "n4"},
    ]


def test_parse_split_shape_errors_reject_the_package():
    """**顶层形状错 = 拒整包**（重试有用）—— 同 `parse_close` 的口径。"""
    for raw, want in ((["nope"], "必须是 JSON 对象"),
                      ({}, "segments 必须是数组"),
                      ({"segments": {}}, "segments 必须是数组"),
                      ({"segments": ["x"]}, "segments[0] 必须是对象")):
        segs, res = digest_registry.parse_split(raw)
        assert any(want in e for e in res.errors), (raw, res.errors)
        assert segs == [], raw


def test_parse_split_span_problems_are_losses_not_errors():
    """⭐ **区间坏了 = 丢那一条**（不废整包）—— 且进 `drops`（真丢: 那一段事没了）。

    区间那套规矩**全部复用 `_clean_span`**（端点存在性 / 起止反 / >2 端点 /
    记录级编号）—— 本用例钉的是"它真的接上了", 不是重测 `_clean_span`。
    """
    raw = {"segments": [
        {"span": [28, 99], "abstract": "端点抄到时间线外"},
        {"span": [33, 31], "abstract": "起止反了"},
        {"span": "nope", "abstract": "形状不是数组"},
        {"span": [], "abstract": "空数组"},
        {"span": [31, 33], "abstract": "这条是好的", "state": "open"},
    ]}
    segs, res = digest_registry.parse_split(raw, seq_set={28, 29, 30, 31, 32, 33})
    assert res.errors == (), "区间毛病不该废整包（重试治不了'划错了一刀'）"
    assert [s["span"] for s in segs] == [[31, 33]]
    assert len(res.drops) == 4, res.drops
    assert all(d in res.warnings for d in res.drops)      # drops ⊆ warnings（同 `_drop`）


def test_parse_split_abstract_missing_is_a_loss_but_long_is_a_warning():
    """`abstract` 缺/空 ⇒ **真丢**（下一轮没东西可照着写）; 超长 ⇒ **收下 + 告警**。

    ⭐ **上限分档**: 有区间 ≤60（骨架提示）· **`span: null` 那行 ≤300**（它就是正文）。
    """
    segs, res = digest_registry.parse_split(
        {"segments": [{"span": [28, 30]},                       # 缺
                      {"span": [31, 32], "abstract": "   "},    # 空
                      {"span": [33, 34], "abstract": "长" * 61}]},
        seq_set={28, 29, 30, 31, 32, 33, 34})
    assert res.errors == ()
    assert [s["span"] for s in segs] == [[33, 34]], "缺/空的丢掉, 超长的要留下"
    assert len(res.drops) == 2 and len(res.warnings) == 3   # 2 条丢 + 1 条超长
    assert segs[0]["abstract"] == "长" * 61
    assert any("abstract" in w and "字" in w for w in res.warnings)

    # 没有区间那一行按**正文**的尺子量（61 字不告警）
    free, res2 = digest_registry.parse_split(
        {"segments": [{"span": None, "state": "close", "id": "n1",
                       "abstract": "长" * 61}]},
        note_ids={"n1"}, overdue_ids={"n1"})
    assert res2.warnings == () and free[0]["span"] is None
    # 但它也有上限（301 字 ⇒ 告警）
    _free2, res3 = digest_registry.parse_split(
        {"segments": [{"span": None, "state": "close", "id": "n1",
                       "abstract": "长" * 301}]},
        note_ids={"n1"}, overdue_ids={"n1"})
    assert any("300" in w for w in res3.warnings), res3.warnings


def test_parse_split_bad_state_falls_back_to_no_ledger():
    """`state` 值不在词表 ⇒ **按「无账目」收下** + 告警（内容不丢 —— 那一行本身是好的）。

    ⚠️ 判据是**别把"没写对形状"升级成"丢了内容"**; 而账目效果丢了会**自愈**
    （那条约定下一段还在名单里）。
    """
    segs, res = digest_registry.parse_split(
        {"segments": [{"span": [28, 30], "abstract": "缺 state"},
                      {"span": [31, 32], "state": "yes", "abstract": "旧口径的值"},
                      {"span": [33, 34], "state": True, "abstract": "布尔"}]},
        seq_set={28, 29, 30, 31, 32, 33, 34})
    assert res.errors == () and res.drops == ()
    assert all("state" not in s for s in segs), segs
    assert len(res.warnings) == 2, res.warnings      # "yes" 与 True; 缺键不告警


def test_parse_split_duplicate_row_is_dropped_but_same_span_is_legal():
    """⭐ 2026-10-05: **同 span 可以有两行**（出+进 / 一个时刻两条记忆）;

    只有**同 span 且同 `abstract`**（整行逐字重复）才丢后一条。
    ⚠️ 部分重叠一直是合法的（真机 `m0015` 与 `m0016` 整段嵌套）。
    """
    segs, res = digest_registry.parse_split(
        {"segments": [
            {"span": [28, 30], "abstract": "第一件"},
            {"span": [28, 30], "abstract": "第一件"},                    # 整行逐字重复 ⇒ 丢
            {"span": [28, 30], "abstract": "同一时刻的另一条记忆"},       # ✅ 合法
            {"span": [29, 31], "abstract": "部分重叠 —— 合法"}]},
        seq_set={28, 29, 30, 31})
    assert [s["abstract"] for s in segs] == [
        "第一件", "同一时刻的另一条记忆", "部分重叠 —— 合法"]
    assert any("完全一样" in d for d in res.drops)


def test_parse_split_null_span_needs_close_and_a_qualification():
    """`span: null` 只有一种合法用法: **close + 名单里那条 + 引擎发了资格位**。

    ⚠️ 坏形状走 `warnings`、**不进 `drops`** —— `span: null` 的行本来就没有库内容
    （它是 R0 凭资格位写出来的一句）, 没有"内容离开过库"这回事。
    """
    raw = {"segments": [
        {"span": None, "abstract": "不是 close"},                                # ①
        {"span": None, "abstract": "close 但没有 id", "state": "close"},          # ②
        {"span": None, "abstract": "id 不在名单", "state": "close", "id": "n9"},   # ③
        {"span": None, "abstract": "没发资格位", "state": "close", "id": "n1"},    # ④
        {"span": None, "abstract": "老师生日那天没有来",
         "state": "close", "id": "n2"},                                          # ✅
    ]}
    segs, res = digest_registry.parse_split(raw, note_ids={"n1", "n2"},
                                            overdue_ids={"n2"})
    assert [s["abstract"] for s in segs] == ["老师生日那天没有来"]
    assert res.drops == (), "没有区间那几行没有库内容可丢 ⇒ 不进 drops"
    assert len(res.warnings) == 4, res.warnings


def test_parse_split_unknown_id_downgrades_the_row():
    """`id` 不在名单 ⇒ **降级成普通一行**（那一刻照样是记忆）+ 告警; ⛔ **不新建**。

    名单没给（老调用方 / 单测）⇒ 不校验闭集。
    """
    segs, res = digest_registry.parse_split(
        {"segments": [{"span": [28, 30], "state": "close", "id": "n9",
                       "abstract": "了结某条（id 是编的）"},
                      {"span": [31, 32], "state": "open", "id": "n9",
                       "abstract": "更正某条（id 是编的）"}]},
        seq_set={28, 29, 30, 31, 32}, note_ids={"n1"})
    assert all("state" not in s and "id" not in s for s in segs), segs
    assert res.drops == () and len(res.warnings) == 2, res.warnings

    loose, res2 = digest_registry.parse_split(
        {"segments": [{"span": [28, 30], "state": "close", "id": "n9",
                       "abstract": "名单没给就不校验"}]},
        seq_set={28, 29, 30})
    assert loose[0]["state"] == "close" and loose[0]["id"] == "n9"
    assert res2.warnings == ()


def test_parse_split_due_is_a_full_date_or_nothing():
    """`due` 只收**全日期**; 解析不了 ⇒ **当没有期限**（静默 —— 不告警、不丢整行）。

    ⭐ **过去的日期照收**（用户 2026-10-05: *"LLM 有自己的理由…下一轮就反应过来了"*）——
    引擎下一段算出的资格位就是"超期", 那条约定会被摆到 R0 眼前 ⇒ 自愈。
    """
    raw = {"segments": [
        {"span": [28, 28], "abstract": "全日期", "state": "open", "due": "2027-05-13"},
        {"span": [29, 29], "abstract": "不是全日期", "state": "open", "due": "5/13"},
        {"span": [30, 30], "abstract": "过去的日期", "state": "open", "due": "2020-01-01"},
        {"span": [31, 31], "abstract": "close 上的 due 不算", "state": "close",
         "id": "n1", "due": "2027-05-13"},
    ]}
    segs, res = digest_registry.parse_split(raw, seq_set={28, 29, 30, 31},
                                            note_ids={"n1"})
    assert res.errors == () and res.warnings == ()
    assert segs[0]["due"] == "2027-05-13"
    assert "due" not in segs[1], "解析不了 ⇒ 当没有期限（不告警）"
    assert segs[2]["due"] == "2020-01-01", "⭐ 过去的日期照收"
    assert "due" not in segs[3], "due 只跟 state=open"


def test_parse_split_truncates_at_max_segments():
    """切太碎 ⇒ 截断 + 告警（**唯一的防"流水账"边界** —— 见 `MAX_SEGMENTS`）。"""
    raw = {"segments": [{"span": [i, i], "abstract": f"第{i}件"}
                        for i in range(1, MAX_SEGMENTS + 4)]}
    segs, res = digest_registry.parse_split(raw, seq_set=set(range(1, MAX_SEGMENTS + 4)))
    assert len(segs) == MAX_SEGMENTS
    assert any("流水账" in w for w in res.warnings)


def test_parse_split_empty_is_legal():
    """没有值得记的 ⇒ 空数组合法（且**不该**报"一条都没留下"那条告警）。"""
    segs, res = digest_registry.parse_split({"segments": []}, seq_set={28})
    assert segs == [] and res.errors == () and res.warnings == ()


def _row_block() -> str:
    """逐字段那一块（`ROW_FIELDS`）—— 示例必须**逐字**带上它（只差整体缩进, 见下）。"""
    return ROW_FIELDS


def test_schema_split_phase():
    text = digest_registry.build_schema(PHASE_SPLIT)
    assert '"segments": [' in text
    for key in ("span", "abstract", "state", "id", "due"):
        assert f'"{key}"' in text
    # ⭐ **示例与逐字段说明同源**（防"三处强度不一"——见 `_SPAN_FIELD` 那段注释）:
    # **逐字段那一整块**必须**逐字**在示例里出现过（示例 = 它整体缩 5 格）。
    assert _row_block() in text, "示例没有逐字带上逐字段那一块 —— 同源破了"
    # 判据那段必须真在里面（它是这个字段的灵魂, 不是装饰）
    assert "她还会不会一直带着它" not in text, "那句判据太宽, 2026-10-04 已收窄"
    assert "失约会真的伤到谁" in text, "分量那一档"
    assert "办完就没了" in text and "往后一直算数" in text, "小事 vs 往后事的界线"
    assert "不会等到翻备忘录才想起来" in text, "『答应了』本身不是理由"
    assert "欠着的债, 不是想通的道理" in text
    assert "日常安排" in text and "夸奖与安慰" in text
    # ⭐ 收窄的那两条: **当时的领悟**要明确划出去（它是 belief 的活）
    assert "当时的领悟与触动" in text
    # ⭐ L1（2026-10-05）新增的三段
    assert "这一段结束时还开着" in text, "只标本段结束时还开着的"
    assert "没有那一刻" in text and "那条回忆的正文" in text, "close 的两种情形"
    assert "后来才知道" in text, "更正那一格（`open` + `id`）"
    assert "全日期" in text, "due 的格式"
    # 取值词表 + 上一轮的形状声明
    for v in STATE_VALUES:
        assert v in text
    assert "可以重叠" in text
    assert '"segments": []' in text                      # 空包合法也要说


def test_schema_split_reuses_the_domain_contract_by_reference():
    """⭐ 切分的**条数契约** `_DOMAIN_CONTRACT` **只服务 R0**（3b-2 起与 R1 分家）。

    ⚠️ 从前它与 `record` 共用一份（因为切分权在 R1）; 3b-2 把切分权冻结给 R0 之后,
    record 换成了 `_RECORD_CONTRACT`（"按骨架填"）—— **两句话术不同**:
    一份说"怎么切", 一份说"怎么填"。谁把它们合回去, `test_schema_record_phase`
    与这条会一起红。
    """
    bond = digest_registry.build_schema(PHASE_SPLIT, domain="bond")
    mmt = digest_registry.build_schema(PHASE_SPLIT, domain="mmt")
    assert "这一章恰好 1 件" in bond
    assert "需要切分" in mmt and "必须覆盖全部" in mmt
    # 多章时那份改写也在
    multi = digest_registry.build_schema(PHASE_SPLIT, domain="bond", chapter_count=2)
    assert "本段含 **2 章**" in multi
    # ⭐ 两边**不共用**了: record 那份说的是"骨架里每一条切片给一行"
    rec = digest_registry.build_schema(PHASE_RECORD, domain="mmt")
    assert "每一条切片给一行" in rec and "必须覆盖全部" not in rec


def test_split_prompt_does_not_restate_the_schema_criteria():
    """⭐ **判据只有一处**: `digest_split.md` 是"你是谁 / 看什么", 判据全在 schema 里。

    为什么值得钉: 这次特意把账目的判据**只写在契约层**, 因为 `contract/schema.py`
    那条纪律说 *"示例才是形状的来源"* —— 一旦 prompt 里也抄一份, 两处迟早强度不一,
    而模型只学会它看到的那一份（2026-09-20 art 命中率 0/5 就是这么来的）。

    ⚠️ **例外（2026-10-04）**: prompt 里可以出现**一句**"别怕丢"的分工说明 ——
    它不是判据, 是**边界声明**（"领悟归下一轮的 belief"）。那条守门只拦判据原文。
    """
    from llm.prompts import load_prompt

    raw = load_prompt("digest_split")
    assert "{{digest_schema}}" in raw, "prompt 必须留契约占位符（否则判据根本进不去）"
    for phrase in ("欠着的债", "忘了它, 就真会出问题", "日常安排", "随口一说",
                   "夸奖与安慰", "三个去处", "她还会不会一直带着它",
                   "这一段结束时还开着", "没有那一刻"):
        assert phrase not in raw, (
            f"判据原文 {phrase!r} 出现在 prompt 文件里了 —— 它只该在契约层"
            "（`STATE_SEMANTICS` / `CLOSE_SEMANTICS` …）。两处各写一份 = 迟早强度不一。")
    # ⭐ **判据指针必须真在**（"怎么判在契约里"这件事本身要说出来 —— 2026-10-05 L2）
    assert "以那里为准" in raw
    # ⭐ 边界声明该在（"别自作聪明"的那道闸; 与判据无关）: 正文/领悟不归它 + 输出示范
    assert "下一轮会把它写成一条**看法**" in raw
    assert "输出示范" in raw, "prompt 靠示范教形状（示例才是形状的来源）"


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

def test_round_a_position_fields_are_retired():
    """⛔ **`event_seq` / `span` 都退役了**（3b-2, 2026-09-29）—— 位置归 R0 的骨架。

    从前这两条是"她指位置"的两代写法（`event_seq` 逐点 → `span` 区间）,
    各自带一整套 ⊆ 校验 / 退化 / 记录级收下。切分权归 R0 之后,
    **没有"她的位置"可错了**（位置是引擎按骨架算的）⇒ 整套逻辑随之消失,
    只剩下"写了就记一句 warning"（让契约漂移**可见**, 但不影响产出）。

    ⚠️ 这条用例钉的是**退役的形状**: 谁想把 `span` 加回来, 它会先红。
    """
    for gone, val in (("event_seq", ["28", "30"]), ("span", [28, 30])):
        items, res = digest_registry.parse_round_a(
            {"episodes": [_ep(**{gone: val})]}, seq_set={28, 30})
        assert gone not in items[0], items[0]
        assert any(gone in w and "退役" in w for w in res.warnings), res.warnings
        assert res.errors == ()                      # 退役字段不废整包
    # 契约文本里也不许再有它（防"示例又把形状教回来"）
    assert '"span"' not in digest_registry.build_schema(PHASE_RECORD)
    print("    span/event_seq: 已退役（写了只记 warning, 契约里不再渲染）")


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
    assert "28.3" in text and "20.p" in text
    assert "记录行号" in text
    assert "只给行号" in text and "写成字符串会被忽略" in text
    assert "默认就是" in text and "不用写 `kind`" in text
    # ⭐ **3b-2（2026-09-29）: 位置归骨架** —— 契约要同时说清两件新事
    assert "本段骨架" in text, "契约没告诉它按骨架填"
    assert "顺序一一对应" in text
    assert '"drop"' in text and "drop" in text
    # ⛔ 两代"她指位置"的写法都退役了（谁想把它们加回来, 这条先红）
    assert '"span"' not in text
    assert '"event_seq"' not in text
    assert "两条通道" not in text
    assert '"kind": "episode"' not in text            # 示例里不该再出现这一行
    print("    schema: 按骨架填 + drop + verbatim 记录行号 + kind 只在例外时写")


# ---------------------------------------------------------------------------
# ⛔ N3 的 `span`（区间）与更早的 `event_seq`（逐点）**2026-09-29 / 3b-2 退役** ——
#    位置（一条经历覆盖哪一段）改由 **R0 的骨架**定, R1 只按顺序填。
#    真机病根不复存在: 从前"她挑点/划区间"必然漏（覆盖率 67.9%）, 现在切分员
#    的产出**可机械校验**（未认领 = 0）。
# ---------------------------------------------------------------------------

def test_position_fields_are_gone_and_do_not_break_the_pack():
    """退役后的形状: 写了 `span`/`event_seq` ⇒ **只记一句 warning**, 内容照收。"""
    for gone, val in (("span", [28, 30]), ("event_seq", ["28", "30"])):
        items, res = digest_registry.parse_round_a(
            {"episodes": [_ep(**{gone: val})]}, seq_set={28, 29, 30})
        assert len(items) == 1 and items[0]["text"]
        assert gone not in items[0]
        assert any(gone in w and "退役" in w for w in res.warnings), res.warnings
        assert res.errors == ()


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
