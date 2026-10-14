"""digest_registry 测试（AGENT_BRAIN.md §3 重构 / 板块 2）——LLM 契约层单源。"""
import pytest

from contract.digest import (
    ABSTRACT_MAX,
    COGNIZE_ACTIONS,
    COGNIZE_KEYS,
    COGNIZE_RETIRED,
    MAX_COGNITIONS,
    MAX_SEGMENTS,
    OUTPUT_DISCIPLINE,
    OUTPUT_RULES,
    PHASE_COGNIZE,
    PHASE_GROUP,
    PHASE_RECORD,
    PHASE_RELATE,
    PHASE_SETTLE,
    PHASE_SPLIT,
    RELATION_ACTIONS,
    RELATION_ANCHORS,
    STATE_VALUES,
    DigestRegistry,
    digest_registry,
    fill,
    fragment,
)

# ---------------------------------------------------------------------------
# 收口相位 —— `{"add": […], "close": […]}`
# ⛔ ~~全景轮（写卡）~~ 2026-09-29（N4a/N4e）整条退役: `habits` 与 `on_mind` 两个槽都没了。
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
            {"span": None, "abstract": "生日那天，老师没有来", "state": "close", "id": "n4",
             "title": "生日那天", "significance": 0.9},
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
        {"span": None, "abstract": "生日那天，老师没有来", "state": "close", "id": "n4",
         "title": "生日那天", "significance": 0.9},
    ]


def test_parse_split_shape_errors_reject_the_package():
    """**顶层形状错 = 拒整包**（重试有用）—— 同 `parse_round_b` 的口径。"""
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
                       "title": "生日那天", "significance": 0.9,
                       "abstract": "长" * 61}]},
        note_ids={"n1"}, overdue_ids={"n1"})
    assert res2.warnings == () and free[0]["span"] is None
    assert free[0]["title"] == "生日那天" and free[0]["significance"] == 0.9
    # 但它也有上限（301 字 ⇒ 告警）
    _free2, res3 = digest_registry.parse_split(
        {"segments": [{"span": None, "state": "close", "id": "n1",
                       "title": "生日那天", "abstract": "长" * 301}]},
        note_ids={"n1"}, overdue_ids={"n1"})
    assert any("300" in w for w in res3.warnings), res3.warnings


def test_parse_split_spanless_row_wants_a_title():
    """⭐ 无区间那一行**要 `title` + `significance`**（L7）—— 缺了**不拒**, 退回摘要前 12 字。

    理由: 那一行没有事件、也不经过写正文的那一轮 ⇒ 标题只能由 R0 给; 而"没标题"
    只是让她在视图里引不到它, 比"整条记忆没了"轻得多。
    """
    segs, res = digest_registry.parse_split(
        {"segments": [{"span": None, "state": "close", "id": "n1",
                       "abstract": "生日那天，老师没有来, 我在校门口等到天黑"}]},
        note_ids={"n1"}, overdue_ids={"n1"})
    assert segs[0]["title"] == "生日那天，老师没有来, "[:12], segs[0]["title"]
    assert segs[0]["significance"] == 0.5
    assert any("title" in w for w in res.warnings), res.warnings


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
         "state": "close", "id": "n2", "title": "生日那天",
         "significance": 0.9},                                                   # ✅
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
    """逐字段那一块（`prompts/parts/row_fields.md`）—— 示例必须**逐字**带上它
    （只差整体缩进, 见下）。⚠️ 与渲染侧读**同一个片段**, 不是抄一份进来。"""
    return fill(fragment("row_fields"), {"abstract_max": str(ABSTRACT_MAX)})


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
    """⭐ 切分的**条数契约**（`prompts/parts/domain.*.md`）**只服务 R0**（3b-2 起与 R1 分家）。

    ⚠️ 从前它与 `record` 共用一份（因为切分权在 R1）; 3b-2 把切分权冻结给 R0 之后,
    record 换成了 `parts/record.*.md`（"按骨架填"）—— **两句话术不同**:
    一份说"怎么切", 一份说"怎么填"。谁把它们合回去, `test_schema_record_phase`
    与这条会一起红。
    """
    bond = digest_registry.build_schema(PHASE_SPLIT, domain="bond")
    mmt = digest_registry.build_schema(PHASE_SPLIT, domain="mmt")
    # ⭐ S1（2026-10-06）: 措辞收窄成"**这一段**恰好 1 件" —— 段 = Trigger+Bond+Finish
    assert "这一段恰好 1 件" in bond
    assert "一件 = 一次见面 / 一段连续聊天" in mmt and "不能留空档" in mmt
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
                   "这一段结束时还开着", "没有那一刻",
                   # ⭐ S1（2026-10-06）: "一件 = 一场戏" 那套判据也不许抄进 prompt
                   "一次见面 / 一段连续聊天", "都还是同一件事", "另一件事真的开始了",
                   # ⭐ S2（2026-10-06）: "没结束的那一截可以留着" 同样只在契约层
                   "最后那一截"):
        assert phrase not in raw, (
            f"判据原文 {phrase!r} 出现在 prompt 文件里了 —— 它只该在契约层"
            "（`prompts/split.md` 里那四段语义）。两处各写一份 = 迟早强度不一。")
    # ⭐ **判据指针必须真在**（"怎么判在契约里"这件事本身要说出来 —— 2026-10-05 L2）
    assert "以那里为准" in raw
    # ⭐ 边界声明该在（"别自作聪明"的那道闸; 与判据无关）: 正文/领悟不归它 + 输出示范
    assert "下一轮会把它写成一条**看法**" in raw
    assert "输出示范" in raw, "prompt 靠示范教形状（示例才是形状的来源）"


def test_split_says_one_scene_is_one_item():
    """⭐ S1（2026-10-06）: **一件 = 一场戏** —— 真机那种"一个段切成 5 件"被判为错。

    真机证据（haruka）: 09-23 那次调用把**一个段**（Trigger 三段闲聊 `132-157` +
    Bond 一章 `158-200` + Finish `202-206`）切成 **5 件** —— 直接违反
    `DESIGN_SEGMENT.md` 的"段是最小单元、**根本不产生截断**"。

    肇事者三处（都在这条用例的射程内）:
      · **bond 支末尾那三行**（明写"MT 聊天**另行切件**"）—— 混合窗口下它逼 R0 多切;
      · mmt 支"**必须覆盖全部** …… 连闲聊也要给它自己的那一件";
      · 那把**太松的尺子**（"三十条消息切成十五件"才算流水账 ⇒ 隐含许可 2:1,
        而 R0 实际做到 8:1, 自认为很克制）+ `MAX_SEGMENTS` 12→20 抬上限。
    """
    import re

    from llm.prompts import load_prompt

    mmt = digest_registry.build_schema(PHASE_SPLIT, domain="mmt")
    bond = digest_registry.build_schema(PHASE_SPLIT, domain="bond")
    # ① 判据在契约里（mmt 侧）
    assert "一件 = 一次见面 / 一段连续聊天" in mmt
    assert "都还是同一件事" in mmt
    # ② bond 侧不许再说"聊天另行切件"（混合窗口的肇事者）
    assert "另行切件" not in bond
    assert "写进这一件里" in bond
    # ③ 上限收回 —— 上限从来不只是上限, 它是标尺
    assert MAX_SEGMENTS == 12
    # ④ ⭐ 示范必须示范"多话题一场戏 = 一行"（示例才是形状的来源）
    raw = load_prompt("digest_split")
    assert "一场戏 = 一行" in raw
    spans = re.findall(r'"span": \[(\d+), (\d+)\]', raw)
    assert any(a != b for a, b in spans), "示范里必须有一条**跨多行**的 span"


def test_split_lets_the_unfinished_tail_wait():
    """⭐ S2（2026-10-06）: **没结束的那一截可以留着不写** —— 下次跟后文连成一件。

    为什么要有这条出口: R0 拿到的窗口是"数到就切"出来的 ⇒ 一场戏可能正说到一半;
    硬给它一个收尾, 那半件事就变成**一条闭合的假记忆**（她以后召回它, 会以为事情完了）。

    ⚠️ 但**不能无限拖**: 窗口超 `DIGEST_WINDOW_EVENTS_CAP`(120) 会丢**最老的未认领**
    ⇒ 契约写的是"**明显**没结束才留", 不是"拿不准就留"。
    ⚠️ 这条**只在契约层** —— prompt 不许抄（见 `test_split_prompt_...` 的黑名单）。
    """
    mmt = digest_registry.build_schema(PHASE_SPLIT, domain="mmt")
    both = digest_registry.build_schema(PHASE_SPLIT, domain="bond")
    assert "最后那一截如果明显还没结束" in mmt
    assert '只有"明显"才留' in mmt
    assert "最后那一截明显没结束" in both      # 三条判据那块两个段类型共用


def test_the_output_discipline_lives_only_in_the_contract():
    """⭐ **G1（2026-10-05）: "输出纪律"只有一个家** —— `OUTPUT_DISCIPLINE`, 六个相位共用。

    从前是**同一句话两处各一份**: 契约层每个相位开头一行（"不要任何解释文字 /
    不要 ```json 代码块"）+ 每个 `digest_*.md` 结尾又一行（"必须输出完整 JSON（键名开头）"）
    ⇒ 同一次调用的 system 里就重了两遍, 而模型只学会它看到的那一份。

    ⚠️ **两半都要查**: ① prompt 里不许出现它的任何一条 ② 六个相位的 schema 里必须真有它
    —— 只查①的话"两边都删掉"也能绿, 那才是真的把话说丢了。
    判据直接从 `OUTPUT_RULES` 取: 改常量 ⇒ 守门跟着改, 不留一句过期的禁词。

    ⚠️ **修复轮的话术不在范围内**: `core/digest/call.py` 的 feedback 与 `llm/client.py`
    的 JSON 修复循环各留一份是**故意的**（输出被拒之后模型才需要被提醒一次）。
    """
    from pathlib import Path

    from llm import prompts as prompts_pkg

    assert OUTPUT_RULES, "常量格式变了, 这条守门的判据要跟着改"
    assert OUTPUT_DISCIPLINE.endswith(":"), "每个相位那一行以冒号收尾（后面接形状）"

    for path in sorted(Path(prompts_pkg.__file__).parent.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        for rule in OUTPUT_RULES:
            assert rule not in raw, (
                f"{path.name} 又抄了一遍输出纪律: {rule!r} —— 它只该住契约层"
                "（`contract.digest.OUTPUT_RULES`）。")

    # ⏸ `PHASE_GROUP` 2026-10-13 退役（那一格从 `PHASE_FILES` 摘了, md 搬 archive）
    for phase in (PHASE_SPLIT, PHASE_RECORD, PHASE_SETTLE, PHASE_COGNIZE):
        assert OUTPUT_DISCIPLINE in digest_registry.build_schema(phase), (
            f"{phase} 相位的 schema 里没有输出纪律 —— 那句话现在谁都不说了。")


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


def test_actions_by_phase():
    assert {a.name for a in digest_registry.actions(PHASE_RECORD)} == {"record_episode"}
    assert {a.name for a in digest_registry.actions(PHASE_RELATE)} == {
        "supports", "akin", "contradicts", "evolved_from"}
    assert digest_registry.actions()  # 全量非空


def test_unknown_phase_rejected():
    with pytest.raises(ValueError):
        digest_registry.build_schema("deep")     # deep 未注册动作 → 暂不支持


def test_record_phase_demands_exactly_one_document():
    """⭐ `record` 相位该**恰好 1 份文档**。

    从前这里是硬编码查名（`a = self.spec("record_episode")`）—— 名字一改，`spec()`
    返回 `None`，报出来是一句难懂的 `AttributeError`，看不出是哪份契约缺了。
    现在按**相位**取，缺了/多了都当场点名。
    """
    reg = DigestRegistry(actions=())                 # 故意不含 record_episode
    with pytest.raises(ValueError, match="record 相位该恰好 1 份文档"):
        reg.build_schema(PHASE_RECORD)
    print("    build_schema: record 相位缺文档 → 明确报错（不是 AttributeError）")


# ---------------------------------------------------------------------------
# Round A parse
# ---------------------------------------------------------------------------

def test_affection_lives_in_the_record_phase_only():
    """⭐ **M1（2026-10-05）: 好感归 R1**（与 `significance` 同族: 都是打分）。

    两处判据一起钉:
      · **判据（打分档位）在契约里** —— 不许只在 prompt 里说（文体五条 #1）;
      · **只有一份** —— 它是从 R2 相位**搬过来**的, 不是抄一份（抄 = 迟早两套尺子）。
    """
    from llm.prompts import load_prompt

    rec = digest_registry.build_schema(PHASE_RECORD)
    assert "affection_exp_delta" in rec
    assert "0~10" in rec and "负值" in rec                 # 档位与负值判据都在契约层

    # ⭐ "不必都写"（M1 顺手加的那一句）: 骨架**不是硬双射**
    assert "也不必都写" in rec and "不是硬性一一对应" in rec

    rec_prompt = load_prompt("digest_record")
    rel_prompt = load_prompt("digest_relate")
    assert "affection_exp_delta" in rec_prompt, "R1 那一轮要点名这个键（否则它不会写）"
    assert "0~10" not in rec_prompt, "档位判据只在契约里 —— prompt 不许抄第二遍"
    assert "affection_exp_delta" not in rel_prompt and "0~10" not in rel_prompt


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
    """⭐ `kind` 只在"例外"时写（2026-09-29 裁决: 轮次决定的常量不该由 LLM 声明）。

    默认 = 经历（缺键 / 空串都算）; 写坏值照旧**拒**（不静默降级 —— 静默改 kind
    会让模型下次还这么写）。

    ⏸ **2026-10-12 停产, 2026-10-14 连格式一起删**（`profile` 玩家画像; 见 `nodes.KINDS`）
    —— 用户先裁 *"`entity.text` 取代了它的定位"*, 后裁"顺手删掉"。判据因此变成三条:
      · 契约不再要它（`record.md` 里没有这个字段了）;
      · 她惯性还写得出 ⇒ **认得出**（⛔ 不判非法: 那会罚她重写整段）,
        但**不产条目**（丢行进 `drops` 的账）;
      · 图与 `_PREFIX` 里**都没有那个 kind 了**（老档若还有 `e…` 行, 读进来降级成经历）。
    """
    raw = {"episodes": [
        {"text": "老师约我去公园散步。", "title": "公园散步", "tags": ["公园"]},
        {"kind": "", "text": "空串也算默认。", "title": "空 kind", "tags": ["x"]},
        {"kind": "profile", "text": "玩家的生日是 5 月 20 日",
         "verbatim": ["3.0"], "tags": ["玩家"], "significance": 0.7},
    ]}
    items, result = digest_registry.parse_round_a(raw)
    assert result.is_valid, result.errors          # ⭐ 退役**不是**错误
    assert len(items) == 2 and [it["kind"] for it in items] == ["episode", "episode"]
    assert items[0]["text"].startswith("老师约我")            # 不写 kind ⇒ 经历
    assert items[1]["kind"] == "episode"                     # 空串 ⇒ 也是经历
    # 丢了东西要**有账**（`drops` 与 `warnings` 分家）
    assert any("profile" in d and "退役" in d for d in result.drops), result.drops
    assert not any("profile" in e for e in result.errors)


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
    ⭐ **⑥（2026-09-29）把 `kind` 收成"例外才写"**; ⏸ **2026-10-12 停产、2026-10-14
    连那个例外（`profile` 玩家画像）一起删** ⇒ 今天契约要**明说没有 `kind` 这个字段**,
    并且**示例 JSON 里既不带 `"kind": "episode"` 也不带 `"kind": "profile"`**
    （示例才是形状的来源, 陷阱 3/46）。
    """
    text = digest_registry.build_schema(PHASE_RECORD)
    assert "28.3" in text and "20.p" in text
    assert "记录行号" in text
    assert "只给行号" in text and "写成字符串会被忽略" in text
    assert "没有 `kind` 这个字段" in text, "契约没告诉她不要写 kind"
    # ⭐ **3b-2（2026-09-29）: 位置归骨架** —— 契约要同时说清两件新事
    assert "本段骨架" in text, "契约没告诉它按骨架填"
    assert "顺序一一对应" in text
    assert '"drop"' in text and "drop" in text
    # ⛔ 两代"她指位置"的写法都退役了（谁想把它们加回来, 这条先红）
    assert '"span"' not in text
    assert '"event_seq"' not in text
    assert "两条通道" not in text
    assert '"kind": "episode"' not in text            # 示例里不该再出现这一行
    assert '"kind": "profile"' not in text            # ⏸ 已删的那一档更不该出现（`kind` 只有 episode 合法）
    print("    schema: 按骨架填 + drop + verbatim 记录行号 + 今天没有 kind 例外")


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
    from core.brain.nodes import KINDS
    assert set(RELATION_ANCHORS) <= set(KINDS), set(RELATION_ANCHORS) - set(KINDS)
    assert "entity" not in RELATION_ANCHORS, "E3 之后没有关系以对象为左端"
    print("    P1a: 四个动作名 ∈ graph.RELS; 锚点类型 ⊆ nodes.KINDS（entity 除外）")


def test_relate_contract_says_no_body_text():
    """⭐ P1a: L1 的契约 —— 一个字的正文都不写（没有 text/subject 那些键）。

    ⏸ **2026-10-14**: `akin` 的 `on` 那一格与"必须是两端 `topics` 交集里的词"那句
    **一起退役**（用户裁 A2）—— 判据的载体（`topics`）没了, 留一个没有判据的必填格
    只会教她写空话（"假威胁"那条纪律的反面）。
    """
    text = digest_registry.build_schema(PHASE_RELATE)
    assert '"relations": [' in text
    for key in ('"supports"', '"akin"', '"contradicts"', '"evolved_from"'):
        assert key in text, key
    assert "不写正文" in text and "没话说就不写" in text
    assert "同一件事的先后两段" in text and "平行同类" in text
    assert "整包拒" in text
    assert "topics" not in text and '"on"' not in text, "退役的两格不该还在契约里"
    # ⛔ 本趟没有"写正文"的键
    for gone in ('"text":', '"subject":', '"decision"'):
        assert gone not in text, f"{gone} 不该出现在 L1 的契约里"
    print("    P1a: L1 契约（四个动作 · 不写正文 · 两极校验; `on`/`topics` 已退役）")


def test_parse_relations_legal_rows_and_two_tiers():
    """⭐ P1a: `parse_relations` —— 合法行全过; **丢行**与**整包拒**分两档。"""
    eps, targets = {"m0014", "m0015", "m0017"}, {"u0003", "m0009", "m0014"}
    raw = {"relations": [
        {"episode": "m0017", "akin": "m0014"},
        {"episode": "m0017", "supports": "u0003"},
        {"episode": "m0015", "contradicts": "m0009"},
        {"belief": "u0003", "supports": "u0003"},          # 候选对: 两端都已有（形状合法）
    ]}
    rows, res = digest_registry.parse_relations(
        raw, episode_ids=eps, target_ids=targets)
    assert res.is_valid, res.errors
    assert [r["rel"] for r in rows] == ["akin", "supports", "contradicts", "supports"]
    assert rows[0] == {"rel": "akin", "src": "m0017", "dst": "m0014"}
    assert rows[3] == {"rel": "supports", "src": "u0003", "dst": "u0003"}
    assert not res.drops and not res.warnings

    # ① 形状坏 ⇒ **丢行**（锚点 0 个 / 关系 2 个 / 值不是字符串 / 未知键不算锚点）
    bad_shape = {"relations": [
        {"supports": "u0003"},                                  # 没有锚点
        {"episode": "m0014", "akin": "m0017", "contradicts": "m0009"},   # 两个关系键
        {"episode": 17, "supports": "u0003"},                   # id 不是字符串
    ]}
    rows2, res2 = digest_registry.parse_relations(
        bad_shape, episode_ids=eps, target_ids=targets)
    assert rows2 == [] and not res2.errors and len(res2.drops) == 3, res2.drops

    # ② 编造 id ⇒ **整包拒** —— ⚠️ **两端都要管**: 锚点那一端（`m9999`）与右端（`u9999`）。
    # （2026-10-08 E3 变异验红逼出来的: 只测锚点那一端时, "右端不校验"的变异**全绿**。）
    rows3, res3 = digest_registry.parse_relations(
        {"relations": [{"episode": "m9999", "supports": "u0003"}]},
        episode_ids=eps, target_ids=targets)
    assert rows3 == [] and res3.errors and "整包拒" in res3.errors[0]
    rows3b, res3b = digest_registry.parse_relations(
        {"relations": [{"episode": "m0014", "supports": "u9999"}]},
        episode_ids=eps, target_ids=targets)
    assert rows3b == [] and res3b.errors and "整包拒" in res3b.errors[0], res3b.errors

    # ③ ⏸ **2026-10-14: `akin` 不再要 `on`** —— 缺了照落; 她惯性还写着 ⇒
    #    **静默忽略**（白名单外的键, 同 `topics` 的先例: 不丢行、不告警）
    rows4, res4 = digest_registry.parse_relations(
        {"relations": [{"episode": "m0017", "akin": "m0014"},
                       {"episode": "m0015", "akin": "m0009", "on": "苔藓"}]},
        episode_ids=eps, target_ids=targets)
    assert [r["rel"] for r in rows4] == ["akin", "akin"], res4.drops
    assert all("on" not in r for r in rows4), rows4
    assert not res4.drops and not res4.warnings, (res4.drops, res4.warnings)

    # ④ ⏸ 非 akin 行写了 `on` 也一样: 静默忽略（不再有"只有 akin 用它"那句 warning）
    rows5, res5 = digest_registry.parse_relations(
        {"relations": [{"episode": "m0017", "supports": "u0003", "on": "苔藓"}]},
        episode_ids=eps, target_ids=targets)
    assert len(rows5) == 1 and "on" not in rows5[0] and not res5.warnings

    # ⑤ ⭐ **2026-10-08（E3）: `about` 不再是 L1 的动作** ⇒ 那种行**形状坏**（关系键 0 个）
    #    ⇒ **丢这一行**。归属改由**引擎**从节点 `entity` 派生
    #    （判据见 `DESIGN_ENTITY_TAGS`）—— 这条钉住"别把 `about` 加回动作面"。
    rows6, res6 = digest_registry.parse_relations(
        {"relations": [{"episode": "m0014", "about": "x0001"}]},
        episode_ids=eps, target_ids=targets)
    assert rows6 == [] and res6.drops and not res6.errors, (res6.errors, res6.drops)
    assert "形状坏" in res6.drops[0], res6.drops

    # ⑥ ⭐ P2: **两端类型**（`kind_of` 给得出时）—— 丢行, 不毁整包
    kinds = {"m0014": "episode", "m0017": "episode", "m0009": "episode",
             "u0003": "belief"}
    rows7, res7 = digest_registry.parse_relations(
        {"relations": [{"episode": "m0017", "akin": "u0003"}]},
        episode_ids=eps, target_ids=targets, kind_of=kinds)
    assert rows7 == [] and res7.drops and not res7.errors, (res7.errors, res7.drops)
    assert "两端必须都是经历" in res7.drops[0]
    # ⚠️ 不给 `kind_of`（老调用方 / 单测）⇒ **不校验类型** —— 同一条行照过
    rows7b, res7b = digest_registry.parse_relations(
        {"relations": [{"episode": "m0017", "akin": "u0003"}]},
        episode_ids=eps, target_ids=targets)
    assert len(rows7b) == 1 and not res7b.drops, res7b.drops
    # `contradicts` 要**同侧**: 经历 ↔ 看法 ⇒ 丢; 看法 ↔ 看法 ⇒ 落
    rows8, res8 = digest_registry.parse_relations(
        {"relations": [{"episode": "m0014", "contradicts": "u0003"},
                       {"belief": "u0003", "contradicts": "u0003"}]},
        episode_ids=eps, target_ids=targets, kind_of=kinds)
    assert [r["rel"] for r in rows8] == ["contradicts"] and len(res8.drops) == 1, res8.drops
    assert "必须同侧" in res8.drops[0]
    print("    P1a: parse_relations 合法/丢行/整包拒 三档分得开（+ P2 两端类型）")

def test_apply_relations_writes_edges_only():
    """⭐ P1b-1: `apply_relations` —— **只落边**（一个节点都不建）。

    用桩 store/log（不建真库）: 这条要钉的正是"它**只**做两件事" ——
    `add_edge` 与 `log.append`; 多碰一样（建节点 / 改正文）就红。
    ⏸ **2026-10-14**: `on` 随 `topics` 退役 ⇒ 变更史那一条**不再有 `on` 格**
    （她惯性还写着也会被 parse 丢掉 —— 见上一条用例）。
    """
    from core.brain.revise import apply_relations

    class _Store:
        def __init__(self):
            self.edges: list[tuple[str, str, str]] = []

        def add_edge(self, rel, src, dst, *, ts=""):
            self.edges.append((rel, src, dst))

    class _Log:
        def __init__(self):
            self.rows: list[dict] = []

        def append(self, row):
            self.rows.append(row)

    st, log = _Store(), _Log()
    rows = [{"rel": "akin", "src": "m0017", "dst": "m0014"},
            {"rel": "about", "src": "m0014", "dst": "x0001"}]
    out = apply_relations(st, rows, ts="2026-10-07T00:00", log=log)
    assert st.edges == [("akin", "m0017", "m0014"), ("about", "m0014", "x0001")]
    assert out == rows
    assert log.rows[0] == {"pkg": "digest", "action": "relate", "rel": "akin",
                           "from": "m0017", "to": "m0014", "ts": "2026-10-07T00:00"}
    print("    P1b-1: apply_relations 只落边（变更史那一条没有 `on` 了）")


def test_relate_prompt_points_at_the_contract():
    """⭐ P1b-2（2026-10-07）: L1 的 prompt **只指路, 不抄判据** —— 判据的唯一家是契约。

    黑名单 = **这一趟词汇表之外**的东西: 旧一族（`touch`/`update`/`add`/`decisions`）
    与别的轮的边（`member_of`）。她照抄一句 "同主题就 touch/update"
    出来, 就是一条坏行 + 一次白跑的重试。
    ⚠️ **`evolved_from` 2026-10-08 起不在黑名单里了** —— 它成了 L1 自己的第五个动作
    （P7 第 2 笔）; 但 prompt 仍**不许抄它的判据**（判据的家是契约）。

    ⚠️ 指针**要指得准**: prompt 里那句"其余判据都在上面的…"必须对着契约里**真有的**
    标题（`relations 规则` / 【… 释义】）—— 指一个不存在的段落等于没指。
    """
    from llm.prompts import load_prompt

    raw = load_prompt("digest_relate")
    for word in ("touch", "update", "add", "decisions", "member_of"):
        assert word not in raw, f"L1 的 prompt 里出现了 {word!r}（那是别处的词汇）"
    assert "relations 规则" in raw and "rels 规则" not in raw, "指针要对准契约里真有的标题"
    assert "以那里为准" in raw

    # 契约那一侧: 五个动作 + "这一趟不写正文" 都在（prompt 不重复它们）
    text = digest_registry.build_schema(PHASE_RELATE)
    for name in ("supports", "akin", "contradicts", "evolved_from"):
        assert f"【{name} 释义】" in text
    assert "relations 规则" in text
    assert "这一趟不写正文" in text
    print("    L1 prompt: 只指路（旧词汇一个都不在），判据全在契约里")


def test_topics_is_retired_everywhere():
    """⏸ **2026-10-14: `topics` 退役**（用户裁"先把 topics 退役掉"）—— 判据三面一起撤:

      ① **契约不再教它**（`record.md` 的键块与示例、`digest_record.md` 的示例与讲评）;
      ② **parse 不再登记它**（她惯性还写着 ⇒ 白名单外的键**静默不落库**, 同 `about_hint`
         的先例: ⛔ 不丢行、不告警 —— 那一行本身没毛病）;
      ③ **`ROUNDS.writes` 摘掉它**（那张表是"这一步往哪写"的地图, 漏了功能不报错, 地图就错了）。

    ⚠️ 节点上的字段**留着**（停产不删格式）—— 老档那几格还读得回来,
    见下一条用例。退役的**判据**（`akin` 的 `on` ∈ 两端交集）同批撤, 见 `test_relate_*`。
    ⛔ **别拿它跟已删的 `profile` 比**: 那是整个 kind 删格式（`KINDS` 里没有它了）,
    而 `topics` 是**行内一格**退役 ⇒ 字段留着（见坑 4.32 那两条先例）。
    """
    from core.digest.rounds import BY_KEY
    from llm.prompts import load_prompt

    rec = digest_registry.build_schema(PHASE_RECORD)
    assert "topics" not in rec, "契约里还在教它"
    assert "topics" not in load_prompt("digest_record"), "prompt 里还在教它"
    assert "topics" not in dict(BY_KEY["record"].writes)["episode"], "writes 没摘干净"

    # 她惯性还写着 ⇒ **收下这一行, 只是不登记那一格**（空数组也一样: 不告警）
    items, res = digest_registry.parse_round_a(
        {"episodes": [{"text": "一段经历", "title": "标题", "tags": ["a"],
                       "topics": ["苔藓", "生日"]}]})
    assert items[0]["tags"] == ["a"] and "topics" not in items[0], items[0]
    assert not res.warnings and not res.drops, (res.warnings, res.drops)
    print("    停产: 契约/prompt/writes 三面都不再提 topics; parse 静默不收（不丢行）")


def test_topics_round_trips_on_the_node():
    """节点面: `topics` **停产不删格式** —— 老档那几格存得进盘、读得回来（空 ⇒ 省略）。"""
    from core.brain.nodes import BrainNode

    d = BrainNode(id="m0001", kind="episode", text="…",
                  topics=["苔藓", "生日"]).to_dict()
    assert d["topics"] == ["苔藓", "生日"]
    assert BrainNode.from_dict(d).topics == ["苔藓", "生日"]
    assert "topics" not in BrainNode(id="m0002").to_dict()
    print("    停产: topics 在节点上仍往返（老档读得回来; 今天没有写者）")


# ---------------------------------------------------------------------------
# ⭐⭐ L2「造看法 / 写沉淀」（`cognize`）—— P7 契约（2026-10-08 用户定稿）
# ---------------------------------------------------------------------------

def test_cognize_keys_come_from_the_two_truth_sources():
    """⭐ P7: 这一族的键**全是 `nodes.KINDS`**（L1 那一族全是 `RELS`）—— 域仍只有两个真源。

    `belief` / `experience` = 节点 kind; `supports` / `evolved_from` / `contradicts` = 边名。
    **零新增键**（§4 的"两个真源、零第三处维护"在第二趟上同样成立）。
    ⛔ 也没有 `evidence` —— 那个键 2026-09-29 退役了（零产品消费者）。

    ⭐ **2026-10-13 起"动作"与"键域"分家**（`group` 退役带出来的）:
      · `COGNIZE_ACTIONS` = **她该写的动作** ⇒ 只剩 `belief`;
      · `COGNIZE_KEYS` = **她写了我们认得的键域** ⇒ `experience` 仍在里面 ——
        掉出去它就成了"未知键", 连同一行里合法的 `belief` 一起丢（见那一格的注释）。
    """
    from core.brain.graph import RELS
    from core.brain.nodes import KINDS

    names = [a.name for a in COGNIZE_ACTIONS]
    assert names == ["belief"], names
    assert set(names) <= set(KINDS)
    assert not (set(names) & set(RELS)), "锚点键是 kind, 不是边名"
    assert COGNIZE_RETIRED == ("experience",), COGNIZE_RETIRED
    assert not (set(COGNIZE_RETIRED) & set(COGNIZE_ACTIONS)), "停产的键不许还在动作面上"
    assert set(COGNIZE_KEYS) == {"belief", "experience", "supports",
                                 "evolved_from", "contradicts"}, COGNIZE_KEYS
    assert set(COGNIZE_KEYS) <= set(KINDS) | set(RELS), COGNIZE_KEYS
    print("    P7: L2 的动作 1 个 / 键域 5 个（全 ∈ KINDS ∪ RELS, 无 evidence）")


def test_cognize_contract_shapes_and_rules():
    """⭐ P7: 契约里**看法那一行 + 硬规则**都在; ⏸ **停产的那一半一个字都不许剩**。"""
    text = digest_registry.build_schema(PHASE_COGNIZE)

    # 看法那一行（造看法 · 证据 / 进化 / 打架）
    assert '"cognitions": [' in text
    assert '"belief": {' in text
    assert '"supports": ["m0007", "m0011"]' in text
    assert '"evolved_from": "u0002"' in text
    assert '"contradicts": ["u0005"]' in text
    # 硬规则
    assert "整包拒" in text
    assert "没话说就不写" in text
    assert f"一段最多造 {MAX_COGNITIONS} 条新看法" in text
    assert "引擎发" in text                       # ⛔ 别写 id / ts / event_seq
    assert "【belief 释义】" in text              # include_examples 默认开
    # ⏸ **停产（`group` 退役, 2026-10-13）: 契约不再要它** ⇒ 教她写的那些字都不许剩,
    #    否则她照旧写得出来（而那是**丢行**）—— "契约不再要"必须落到文案上才算数。
    assert '"experience"' not in text
    assert "【experience 释义】" not in text
    assert "沉淀" not in text and "整段重写" not in text and "不建新类" not in text
    assert '"id": "g0001"' not in text
    # ⛔ 退役键名的回声 / 别的相位的壳
    assert "evidence" not in text
    assert "relations" not in text and '"decisions"' not in text
    print("    P7: L2 契约（看法一行 · 多值 · 上限 · 不写 id · 沉淀那一半已停产）")


def test_cognize_two_states_id_decides_create_or_patch():
    """⭐ 2026-10-14（L2 碰撞那一刀）: **带 `id` = 改那条已有的 · 不带 `id` = 造一条新的**。

    三档要分得开（判据见 `parse_attribution` 的 docstring —— **锚点 id 错 ⇒ 丢行**;
    **证据 id 错 ⇒ 整包拒**）:
      · 命中 ⇒ 收下（就是"改"那一路）, 且**不数进 `MAX_COGNITIONS`**（上限管的是"长出新节点"）;
      · 没命中 ⇒ **丢这一行**（⛔ 不连坐同包其他行 —— 同 `settle`）;
      · 空转行（带 id 一格没写）⇒ 丢这一行;
      · 带 id 又写 `evolved_from` ⇒ **只丢那一格**（改口 ≠ 取代）;
      · 前缀容错: `u2` → `u0002`（**唯一命中**才救, 且记一行 warning）。
    """
    common = {"evidence_ids": {"m0007"}, "cognition_ids": {"u0001", "u0002"},
              "kind_of": {"u0001": "belief", "u0002": "belief"}}
    rows, vr = digest_registry.parse_cognitions({"cognitions": [
        {"belief": {"id": "u0001"}, "supports": ["m0007"]},                 # 只挂证据（text 留空）
        {"belief": {"id": "u2", "text": "改得更准一点"}},                    # 前缀容错 + 改正文
        {"belief": {"id": "u0001", "text": "改措辞"}, "evolved_from": "u0002"},  # 改口 ≠ 取代
        {"belief": {"id": "u0003", "text": "编的号"}},                       # 没命中 ⇒ 丢行
        {"belief": {"id": "u0002"}},                                        # 空转行 ⇒ 丢行
    ]}, **common)
    assert vr.is_valid, vr.errors                       # ⛔ 一条都没到"整包拒"那一档
    assert len(rows) == 3, rows
    assert rows[0] == {"action": "belief", "id": "u0001", "supports": ["m0007"]}, rows[0]
    assert rows[1]["id"] == "u0002" and rows[1]["text"] == "改得更准一点"
    assert rows[2]["id"] == "u0001" and "evolved_from" not in rows[2], rows[2]
    joined = " | ".join(vr.drops)
    assert "不在【现有认知】里" in joined and "空转行" in joined, vr.drops
    assert any("唯一匹配" in w and "u0002" in w for w in vr.warnings), vr.warnings

    # ⭐ **上限只数新建**: 造 6 条（只收 5）+ 改 3 条 —— 改的那 3 条一条都不许被上限挤掉
    many = [{"belief": {"text": f"新结论{i}"}, "supports": ["m0007"]} for i in range(6)]
    many += [{"belief": {"id": "u0001", "text": "改一下"}} for _ in range(3)]
    ok, vr3 = digest_registry.parse_cognitions({"cognitions": many}, **common)
    assert len([r for r in ok if not r.get("id")]) == MAX_COGNITIONS, ok
    assert len([r for r in ok if r.get("id")]) == 3, ok
    assert sum("最多造" in d for d in vr3.drops) == 1, vr3.drops


def test_parse_cognitions_three_tiers():
    """⭐ P7: 合法行全过; **丢行**与**整包拒**分两档（与 L1 同一口径）。"""
    common = dict(evidence_ids={"m0007", "m0011"}, cognition_ids={"u0001", "u0002"},
                  group_ids={"g0001"}, kind_of={"u0001": "belief", "u0002": "belief"})

    ok, vr = digest_registry.parse_cognitions({"cognitions": [
        {"belief": {"text": "老师会把我说的话记在心上", "significance": 0.7},
         "supports": ["m0007", "m0011"], "contradicts": ["u0001"]},
        {"belief": {"text": "我大概不值得谁特意跑一趟"}, "evolved_from": "u0002"},
    ]}, **common)
    assert vr.is_valid and len(ok) == 2, (ok, vr.errors)
    assert ok[0]["supports"] == ["m0007", "m0011"]
    assert ok[0]["contradicts"] == ["u0001"] and ok[0]["significance"] == 0.7
    assert ok[1]["evolved_from"] == "u0002"

    # ⭐ 单条也收（形状规则的①就是"值是字符串"）—— 多值只是省行
    one, _ = digest_registry.parse_cognitions(
        {"cognitions": [{"belief": {"text": "只有一条证据"}, "supports": "m0007"}]}, **common)
    assert one[0]["supports"] == ["m0007"], one

    # 丢行（**不废整包**）
    rows, vr2 = digest_registry.parse_cognitions({"cognitions": [
        {"belief": {"text": "没有立足点"}},                                    # 两个都没给
        {"belief": {"text": "想改已有的（但号不在名单里）", "id": "m0003"},
         "supports": ["m0007"]},                                              # ⭐ 锚点 id 没命中 ⇒ 丢行
        {"nonsense": {"text": "x"}},                                          # 不是锚点 kind
        {"belief": {"text": "跟不是看法的一端打架"}, "supports": ["m0007"],
         "contradicts": ["u0002"]},                                          # 另一端不是看法
    ]}, evidence_ids={"m0007"}, cognition_ids={"u0001", "u0002"},
        group_ids={"g0001"}, kind_of={"u0001": "belief", "u0002": "experience"})
    assert rows == []
    assert vr2.is_valid, "这些都该是**丢行**, 不是整包拒"
    joined = " | ".join(vr2.drops)
    for want in ("没有立足点", "不在【现有认知】里", "形状坏", "contradicts 的另一端"):
        assert want in joined, (want, vr2.drops)

    # 整包拒（编造 id）
    bad, vr3 = digest_registry.parse_cognitions(
        {"cognitions": [{"belief": {"text": "编的"}, "supports": ["m9999"]}]},
        evidence_ids={"m0007"}, cognition_ids=set(), group_ids=set())
    assert bad == [] and not vr3.is_valid and "不在列表里" in vr3.errors[0], vr3.errors
    print("    P7: 三档分得开（2 收 · 4 丢 · 1 整包拒）")


def test_retired_soak_row_is_dropped_not_a_package_reject():
    """⏸ **2026-10-13 止血那一刀**: 停产之后她写一行 `experience` ⇒ **丢那一行**, ⛔ 不整包拒。

    ⚠️ **这一条测的是真口子**: 停产前 `experience` 是锚点, 而 `group` 退役后 `group_ids`
    恒是**空集** ⇒ `_clean_soak` 判"不在名单里" ⇒ **整包拒** ⇒ 这一段的看法全丢
    （她能写得出来: 【现有认知】里渲染的 `u…` 含 `experience` 节点, 老契约又教了两版）。
    判据 = B 案第三档（停止生产 ≠ 判非法）。
    """
    rows, vr = digest_registry.parse_cognitions(
        {"cognitions": [{"experience": {"id": "g0001", "text": "给类写沉淀"}}]},
        evidence_ids={"m0007"}, group_ids=set())           # ⭐ 空集 —— 就是生产里的样子
    assert rows == [] and vr.is_valid, (rows, vr.errors)
    assert any("已停产" in d for d in vr.drops), vr.drops
    assert not vr.errors, "⛔ 停产的行不许整包拒（那会陪葬同段合法的看法）"

    # ⭐ 混写: 活的那个锚点**照收**（停产的半条只告警, ⛔ 不为它丢一行看法）
    rows2, vr2 = digest_registry.parse_cognitions(
        {"cognitions": [{"belief": {"text": "同一条里混写了停产键"},
                         "experience": {"id": "g0001", "text": "x"},
                         "supports": ["m0007"]}]},
        evidence_ids={"m0007"}, group_ids=set())
    assert len(rows2) == 1 and rows2[0]["action"] == "belief", rows2
    assert vr2.is_valid and not vr2.drops, (vr2.drops, vr2.errors)
    assert any("已停产" in w for w in vr2.warnings), vr2.warnings
    print("    ⏸ 停产: 一行 experience 丢行不整包拒; 混写的看法照收")


def test_parse_cognitions_caps_beliefs():
    """⭐ P7: 造看法有上限（`MAX_COGNITIONS`）; ⏸ 停产那一行不占额度（它本来就丢了）。"""
    rows, vr = digest_registry.parse_cognitions(
        {"cognitions": [{"belief": {"text": f"第 {i} 条"}, "supports": ["m0007"]}
                        for i in range(MAX_COGNITIONS + 2)]},
        evidence_ids={"m0007"})
    assert len(rows) == MAX_COGNITIONS and vr.is_valid, (rows, vr.drops)
    assert sum(1 for d in vr.drops if "一段最多造" in d) == 2, vr.drops

    rows2, vr2 = digest_registry.parse_cognitions({"cognitions": [
        *[{"belief": {"text": f"第 {i} 条"}, "supports": ["m0007"]}
          for i in range(MAX_COGNITIONS)],
        {"experience": {"id": "g0001", "text": "停产的行不算条数"}},
    ]}, evidence_ids={"m0007"}, group_ids=set())
    assert len(rows2) == MAX_COGNITIONS and vr2.is_valid, (rows2, vr2.drops)
    assert any("已停产" in d for d in vr2.drops), vr2.drops
    print(f"    P7: 看法上限 {MAX_COGNITIONS}（超出的丢行）, 停产行既不占额度也不陪葬")


def test_relate_evolved_from_is_belief_to_belief_only():
    """⭐ P7 第 2 笔: L1 的第五个动作 —— **两条已有看法之间**才写; 经历那一头丢行。

    ⚠️ 这条用例是**探针抓出来的那个真 bug** 的守门: 校验一度只挂在
    `rel in ("akin", "contradicts")` 那个 `if` 里 ⇒ `{"episode": …, "evolved_from": …}`
    一路绿灯（经历"进化"了）。
    ⭐ **2026-10-14**: 图上的方向翻成 **旧 → 新**（用户裁"顺序太怪, 名字不动"）——
    她那一行**行首仍写较新的那条**（`{"belief": "u0001", …}`）, 而**契约层把两端摆正**
    ⇒ 落出来的行是 `src=旧的 / dst=新的`（执行侧不再判方向, 与 `supports` 同一条纪律）。
    """
    rows, vr = digest_registry.parse_relations(
        {"relations": [
            {"belief": "u0001", "evolved_from": "u0002"},      # ✅ 行首 = 新的; u0002 = 旧的
            {"episode": "m0023", "evolved_from": "u0002"},      # ⇒ 丢: 经历没有"进化"
            {"belief": "u0001", "supports": "u0002"},           # ✅ 看法撑看法（本来就能）
        ]},
        episode_ids={"m0023"}, target_ids={"u0001", "u0002"},
        kind_of={"u0001": "belief", "u0002": "belief", "m0023": "episode"})
    assert [r["rel"] for r in rows] == ["evolved_from", "supports"], rows
    assert rows[0] == {"rel": "evolved_from", "src": "u0002", "dst": "u0001"}, rows[0]
    assert vr.is_valid and len(vr.drops) == 1, vr.drops
    assert "evolved_from 两端必须都是" in vr.drops[0], vr.drops
    print("    P7-2: evolved_from 只认看法 ↔ 看法（经历那头丢行）; 落边恒为 旧 → 新")
