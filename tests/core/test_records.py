# -*- coding: utf-8 -*-
"""VN 记录流契约单测 — 行解析（P0-2）+ 群/位置校验（P0-1）+ 块载体（P0-4）。

覆盖设计文档 §2 文法与 §9 失败口径：三类坏行的容错（未转义引号 / 末行悬空 / 数组行）、
形状违规丢行、sensei 群语义（用户样例）、块内位置约束、VnBlock 派生视图与两种出口。

运行: python -m pytest tests/core/test_records.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from contract.records import (CHARACTER_NARRATOR, CHARACTER_SENSEI,  # noqa: E402
                              KIND_CHARACTER, KIND_STAGE, MAX_SENSEI_RUN,
                              VnBlock, VnRecord, check_block, is_main_speaker,
                              normalize_main_character, parse_line,
                              parse_stream, sensei_group_labels, sensei_groups)


def _rec(value, text="x", kind=KIND_CHARACTER, line_no=0) -> VnRecord:
    return VnRecord(kind=kind, value=value, text=text, line_no=line_no)


def test_is_main_speaker_judgement():
    """主角身份判据与别名归一**同源**（emo 标注层据此挑出 NPC 台词）。"""
    aliases = ["伊草 遥香", "春香"]
    for value in ("igusa_haruka", "伊草 遥香", "伊草遥香", "春香", "IGUSA_HARUKA"):
        assert is_main_speaker(value, "igusa_haruka", aliases), value
    # 别的角色/老师/旁白/空值 都不算"主角自己"
    for value in ("asagi_mutsuki", "浅黄 睦月", CHARACTER_SENSEI,
                  CHARACTER_NARRATOR, "", "   "):
        assert not is_main_speaker(value, "igusa_haruka", aliases), value
    assert not is_main_speaker("igusa_haruka", "", aliases)      # 无主角 → 不判
    # 与归一函数同一判据: 别名 → 归一; 未知名 → 也归主角但 NOTE 措辞不同
    recs, notes = normalize_main_character(
        [_rec("伊草遥香"), _rec("asagi_mutsuki")], "igusa_haruka", aliases)
    assert [r.value for r in recs] == ["igusa_haruka"] * 2
    assert "别名归一" in notes[0] and "未知说话人" in notes[1]
    print("    speaker: 主角判据 = id/别名/显示名（NPC/老师/旁白不是）")


# ---------------------------------------------------------------------------
# 行解析：合法形状
# ---------------------------------------------------------------------------

def test_parse_all_record_kinds():
    """七种取值都能解析，且 to_dict 与 wire 形状对称。"""
    lines = [
        '{"character": "igusa_haruka", "text": "……老师，你、你来了。"}',
        '{"character": "sensei", "text": "是我来晚了。"}',
        '{"character": "narrator", "text": "（她低下头。）"}',
        '{"stage": "switch", "text": "深夜的杂草屋"}',
        '{"stage": "art", "text": "她终于把话说出口的一刻：抬头、眼中有泪光"}',
        '{"stage": "memorial", "text": "（她抬起头，朝我笑了一下。）"}',
        '{"stage": "end", "text": "（夜风停了。）"}',
        '{"stage": "exit"}',
    ]
    res = parse_stream(lines)
    assert not res.dropped and not res.errors, res.errors
    assert [r.value for r in res.records] == [
        "igusa_haruka", CHARACTER_SENSEI, CHARACTER_NARRATOR,
        "switch", "art", "memorial", "end", "exit"]
    assert res.records[-1].text == ""                      # exit 的 text 可省
    wire = res.records[0].to_dict()
    assert wire == {"character": "igusa_haruka", "text": "……老师，你、你来了。"}
    print("    parse: 七种取值 + exit 省 text + to_dict 对称")


def test_empty_and_fence_lines_are_silent():
    """空行 / 代码围栏 → 静默跳过（不算错误）。"""
    res = parse_stream(['```json', '', '{"character": "igusa_haruka", "text": "嗨"}', '```'])
    assert len(res.records) == 1 and not res.diags
    print("    parse: 空行/围栏静默跳过")


# ---------------------------------------------------------------------------
# 行解析：形状违规（丢行 + 记账，不抛）
# ---------------------------------------------------------------------------

def test_shape_violations_dropped_with_diag():
    """形状违规丢行并记账：双判别符 / 都无 / 未知 stage / 空 text / 非对象 / 多余字段为 NOTE。"""
    cases = [
        ('{"character": "igusa_haruka", "stage": "end", "text": "x"}', "同时含"),
        ('{"text": "没有判别符"}', "既无"),
        ('{"stage": "bogus", "text": "x"}', "未知 stage"),
        ('{"character": "igusa_haruka", "text": "   "}', "text 不能为空"),
        ('[1, 2, 3]', "数组行内无合法记录"),
        ('"裸字符串"', "必须是 JSON 对象"),
    ]
    for line, expect in cases:
        rec, diag = parse_line(line, 1)
        assert rec is None, line
        assert diag is not None and diag.dropped and expect in diag.error, (line, diag)
    # 多余字段：保留记录 + NOTE
    rec, diag = parse_line('{"character": "igusa_haruka", "text": "嗨", "emotion": "nomal"}', 1)
    assert rec is not None and diag is not None and not diag.dropped
    assert "多余字段" in diag.error
    print("    parse: 六类违规丢行 + 多余字段 NOTE")


def test_unescaped_quote_is_rescaped():
    """未转义半角引号 → 辅助转义救回 + NOTE（文本逐字节还原）。"""
    line = '{"character": "igusa_haruka", "text": "……不是 "别担心" 这种话。"}'
    rec, diag = parse_line(line, 3)
    assert rec is not None and rec.value == "igusa_haruka"
    assert rec.text == '……不是 "别担心" 这种话。'
    assert diag is not None and not diag.dropped and "辅助转义" in diag.error
    print("    parse: 未转义引号 → 辅助转义救回")


def test_rescape_repair_edge_cases():
    """辅助转义的边界：多对引号 / 同时悬空 / 夹多余字段 / 正常引号不触发。"""
    # 多对未转义引号 + 悬空（既缺收尾引号又缺右括号）
    rec, diag = parse_line('{"character": "sensei", "text": "她说 "好" 又说 "不好"。', 4)
    assert rec is not None and rec.text == '她说 "好" 又说 "不好"。'
    assert not diag.dropped and "辅助转义" in diag.error
    # 夹一个不含引号的多余字段：救回并记账
    rec2, diag2 = parse_line(
        '{"character": "igusa_haruka", "emotion": "normal", "text": "听 "心跳" 声。"}', 5)
    assert rec2 is not None and rec2.text == '听 "心跳" 声。'
    assert "多余字段" in diag2.error
    # 中文引号 / 已正确转义的半角引号（含结尾）/ 无引号：一律不触发修复
    for ok in ('{"character": "igusa_haruka", "text": "「别担心」这种话。"}',
               '{"character": "igusa_haruka", "text": "不是 \\"别担心\\" 这种话。"}',
               '{"character": "igusa_haruka", "text": "他问：\\"走吗？\\""}',
               '{"character": "igusa_haruka", "text": "走吧。"}'):
        r, d = parse_line(ok, 6)
        assert r is not None and d is None, (ok, d)
    print("    parse: 辅助转义边界（多引号/悬空/多余字段/正常引号不触发）")


def test_unescapable_line_still_dropped():
    """辅助转义不越界：非本类形状（缺逗号等）+ 疑似结构残留依旧丢行。"""
    for bad in ('{"character": "igusa_haruka" "text": "缺逗号"}',
                '{"character": "igusa_haruka", "text": ["不是字符串"]}',
                # 两条记录粘在一行：护栏拦住，不把 JSON 碎片当正文吞下去
                '{"character": "igusa_haruka", "text": "甲"}{"character": "igusa_haruka", "text": "乙"}'):
        rec, diag = parse_line(bad, 7)
        assert rec is None and diag is not None and diag.dropped, bad
    print("    parse: 不可救行仍丢行（不越界修复）")


def test_tail_truncation_is_repaired():
    """末行悬空（缺收尾 `"}`）→ 救回 + NOTE（EOF 处无歧义）。"""
    rec, diag = parse_line('{"character": "sensei", "text": "当然。今晚早点休息，好吗？', 9)
    assert rec is not None and rec.value == CHARACTER_SENSEI
    assert rec.text == "当然。今晚早点休息，好吗？"
    assert diag is not None and not diag.dropped and "悬空" in diag.error
    print("    parse: 末行悬空 → 补 `\"}` 救回")


def test_array_line_is_flattened():
    """数组行 → 拍平成多条记录（NOTE，不丢）。"""
    line = ('[{"character": "igusa_haruka", "text": "一"}, '
            '{"character": "sensei", "text": "二"}]')
    res = parse_stream([line])
    assert [r.text for r in res.records] == ["一", "二"]
    assert len(res.notes) == 1 and "拍平" in res.notes[0].error
    print("    parse: 数组行拍平")


# ---------------------------------------------------------------------------
# 混合块：坏行只死自己
# ---------------------------------------------------------------------------

def test_mixed_block_local_failure_isolation():
    """坏行只死自己，其余记录照常收下（行级隔离）；可救行救回不丢。"""
    block = "\n".join([
        '{"stage": "switch", "text": "深夜的杂草屋"}',
        '{"character": "igusa_haruka", "text": "……老师。"}',
        '{"character": "igusa_haruka" "text": "缺逗号，不可救"}',                    # 坏行
        '{"character": "sensei", "text": "我想要的不是 "别担心" 这种话。"}',   # 可救
        '{"stage": "memorial", "text": "（她抬起头。）"}',
        '{"character": "igusa_haruka", "text": "「……」"}',
    ])
    res = parse_stream(block)
    assert len(res.records) == 5, res.records
    assert res.records[2].text == '我想要的不是 "别担心" 这种话。'
    assert len(res.dropped) == 1 and res.dropped[0].line_no == 3
    assert len(res.notes) == 1 and "辅助转义" in res.notes[0].error
    print("    parse: 坏行隔离（坏行丢、可救行救）")


# ---------------------------------------------------------------------------
# sensei 群（规范 8 的用户样例）
# ---------------------------------------------------------------------------

def test_sensei_groups_user_example():
    """`遥香 遥香 sensei 遥香 遥香 sensei sensei sensei 遥香` = 2 群（单 + 三）。"""
    seq = ["igusa_haruka", "igusa_haruka", CHARACTER_SENSEI,
           "igusa_haruka", "igusa_haruka", CHARACTER_SENSEI, CHARACTER_SENSEI, CHARACTER_SENSEI,
           "igusa_haruka"]
    recs = [_rec(v, text=f"台词{i}") for i, v in enumerate(seq)]
    groups = sensei_groups(recs)
    assert [[len(g) for g in groups]] == [[1, 3]], groups
    labels = sensei_group_labels(recs)
    assert labels[0] == ["台词2"] and len(labels[1]) == 3
    print("    groups: 用户样例 → 2 群（1 + 3）")


def test_sensei_run_over_limit_flagged():
    """群长度上限 3：4 连 → 块校验报错。"""
    recs = [_rec("igusa_haruka", "铺垫"), *[_rec(CHARACTER_SENSEI, f"话{i}") for i in range(4)],
            _rec("igusa_haruka", "回应")]
    issues = check_block(recs)
    assert any("sensei 群过长" in i for i in issues), issues
    assert MAX_SENSEI_RUN == 3
    print("    groups: 4 连 → 报错")


# ---------------------------------------------------------------------------
# 块内位置校验
# ---------------------------------------------------------------------------

def test_check_block_positions():
    """art 块首 / end 块尾 / 纪念区间禁换场 / 二次纪念 / 二次 art / 空块 / 配对与章末（软）。"""
    from core.bond.bond_story import split_board_issues

    ok = [_rec("switch", "开场景", KIND_STAGE), _rec("art", "意向", KIND_STAGE),
          _rec("igusa_haruka", "铺垫"), _rec("memorial", "触发", KIND_STAGE),
          _rec("igusa_haruka", "纪念正文"), _rec("igusa_haruka", "纪念正文二")]
    assert check_block(ok) == [], check_block(ok)

    # 收尾轮：另起一块（2026-09-20 M6: 纪念轮默认不写 end）——这才是推荐形状
    ok_end = [_rec("igusa_haruka", "晚安。"), _rec("end", "收尾", KIND_STAGE)]
    assert check_block(ok_end) == [], check_block(ok_end)

    bad_art = [_rec("igusa_haruka", "铺垫"), _rec("art", "意向", KIND_STAGE)]
    assert any("首条不是 switch" in i for i in check_block(bad_art))
    bad_art3 = [_rec("igusa_haruka", "一"), _rec("igusa_haruka", "二"), _rec("art", "意向", KIND_STAGE)]
    assert any("art 必须块首" in i for i in check_block(bad_art3))

    bad_tail = [_rec("end", "收尾", KIND_STAGE), _rec("igusa_haruka", "后面还有")]
    assert any("end 必须块尾" in i for i in check_block(bad_tail))

    bad_switch = [_rec("memorial", "触发", KIND_STAGE), _rec("switch", "换场", KIND_STAGE)]
    assert any("纪念区间内出现 switch" in i for i in check_block(bad_switch))

    two_memorial = [_rec("memorial", "一", KIND_STAGE), _rec("memorial", "二", KIND_STAGE)]
    assert any("2 条 memorial" in i for i in check_block(two_memorial))

    two_art = [_rec("art", "一", KIND_STAGE), _rec("art", "二", KIND_STAGE)]
    assert any("2 条 art" in i for i in check_block(two_art))

    # 软违规（2026-09-20）: 配对缺失 / 章末压在纪念轮 —— 记录但不打回
    for issues in (check_block([_rec("memorial", "触发", KIND_STAGE),
                                _rec("igusa_haruka", "正文")]),
                   check_block([_rec("art", "意向", KIND_STAGE),
                                _rec("memorial", "触发", KIND_STAGE),
                                _rec("end", "收尾", KIND_STAGE)])):
        soft = [i for i in issues if "没有 art" in i or "与 end 在同一轮" in i]
        assert soft, issues
        assert split_board_issues(issues)[1] == issues, f"软问题不该被判成硬: {issues}"

    assert check_block([]) == ["空块：没有任何记录"]
    print("    block: 位置/区间/重复/空块 + 配对与章末（软）八项判定")


def test_block_head_art_after_opening_switch():
    """开章块：switch 首条 + art 紧随其后 → 合规（不算 art 位置错）。"""
    recs = [_rec("switch", "开场景", KIND_STAGE), _rec("art", "意向", KIND_STAGE),
            _rec("igusa_haruka", "铺垫"), _rec("memorial", "触发", KIND_STAGE)]
    assert check_block(recs) == [], check_block(recs)
    print("    block: 开章 switch + art 紧随 = 合规")


# ---------------------------------------------------------------------------
# P0-3：LLM 可见的契约文本（第三种形态）
# ---------------------------------------------------------------------------

def test_build_record_schema_covers_all_values():
    """schema 文本覆盖全部取值 + 关键规则 + 三条文案纪律（用户裁决 #24）。

    ⚠️ `exit` **故意不在覆盖范围内**（2026-09-20, docs/DESIGN_MEMORIAL.md 节点 A1）:
    它是 v1 遗留值，解析层 `STAGE_VALUES` 仍认（旧档回放要读），但**不再教给 LLM**
    ——注入清单里有它就等于告诉模型"可以写 exit"，而 v2 里它恒不会被产出。
    """
    from contract.records import STAGE_EXIT, STAGE_VALUES
    from contract.schema import build_record_schema

    text = build_record_schema()
    for value in STAGE_VALUES:
        if value == STAGE_EXIT:
            assert f'"{value}"' not in text, "exit 是解析层遗留值, 不该出现在注入文本里"
            continue
        assert f'"{value}"' in text, value
    for value in ("igusa_haruka", CHARACTER_NARRATOR, CHARACTER_SENSEI):
        assert value in text, value
    assert "一行一条" in text
    assert '\\"' in text                       # 转义示范（实战唯一真实错误源）
    assert f"1~{MAX_SENSEI_RUN} 条" in text     # 群上限
    assert "不要数组" in text and "不要围栏" in text
    assert "stage=end 外必填" in text           # end 的 text 可留空（收尾字段）
    assert "不是老师的话" in text and "黑屏收尾" in text
    # art ↔ memorial 配对（2026-09-20 M1）: 三处都要说到（取值说明/硬规则/示例）
    assert "与 memorial 同轮成对出现" in text
    assert "必须同轮成对" in text
    assert text.count('"stage": "art"') >= 2    # 取值行 + 示例行
    # 文案纪律: 范例不出现「」; 不写"不要写地点/情绪字段"式负面提醒（白熊效应）
    assert "「" not in text and "」" not in text
    assert "地点键" not in text and "情绪键" not in text
    assert "choices" not in text and "branches" not in text
    # 关掉示例时更短，但仍含硬规则
    brief = build_record_schema(with_examples=False)
    assert len(brief) < len(text) and "硬规则" in brief and "示例" not in brief
    print("    schema: 全取值 + 转义示范 + end 可空 + 无「」/无负面提醒")


def test_build_record_schema_is_session_bound():
    """schema 随会话角色渲染: 记录取真实 id（连默认值也不再是 `haruka` 这类短名）。"""
    from contract.schema import build_record_schema

    text = build_record_schema(char_id="igusa_haruka", char_display="伊草 遥香")
    assert '"character": "igusa_haruka"' in text
    assert "伊草 遥香" in text
    assert text.count("igusa_haruka") >= 5             # 取值行 + 示例行
    # 默认值与真实调用同形（决策 #24: 范例统一真实 id, 不留占位短名）
    default = build_record_schema()
    assert '"character": "igusa_haruka"' in default
    assert '"igusa_haruka"' not in default.replace('"igusa_haruka"', "")
    print("    schema: 随会话角色渲染（id/显示名）")


def test_end_text_is_optional_and_separate_from_sensei():
    """`end` 的 text = 收尾字段（不是老师的话）且**可留空**（直接黑屏收尾）。"""
    # 留空 / 整字段省略 → 都合法
    for line in ('{"stage": "end", "text": ""}', '{"stage": "end"}'):
        rec, diag = parse_line(line, 1)
        assert rec is not None and rec.stage == "end" and rec.text == "", (line, diag)
        assert diag is None, (line, diag)
    # 其它 stage 的 text 仍必填
    for line in ('{"stage": "switch", "text": "  "}', '{"stage": "memorial", "text": ""}'):
        rec, diag = parse_line(line, 1)
        assert rec is None and diag is not None and diag.dropped, line
    # 收尾组合（用户样例）: 老师一句 → 空镜 → 黑屏退场 —— 三条记录都在同一块里
    block = "\n".join([
        '{"character": "sensei", "text": "你看那边，多漂亮啊"}',
        '{"stage": "switch", "text": "星空"}',
        '{"stage": "end", "text": ""}',
    ])
    res = parse_stream(block)
    assert [r.stage or r.value for r in res.records] == ["sensei", "switch", "end"]
    assert check_block(res.records) == [], check_block(res.records)
    # 空 text 不进渲染文本（不留空行）
    assert VnBlock.from_records(res.records).render_text() == "老师：你看那边，多漂亮啊\n星空"
    print("    parse: end 的 text 可留空（收尾字段, 组合技巧可解析）")


# ---------------------------------------------------------------------------
# 流式增量解析（P2-1 前置）: chunk → 完整行 → 板闭合即交付
# ---------------------------------------------------------------------------

def test_block_stream_parser_incremental():
    """逐 chunk 喂入, 板一闭合即可取走——切板规则与批式同源。"""
    from contract.records import BlockStreamParser, check_block, parse_stream

    block = "\n".join([
        '{"stage": "art", "text": "画面意向"}',
        '{"stage": "switch", "text": "教室"}',
        '{"character": "igusa_haruka", "text": "一"}',
        '{"character": "sensei", "text": "A"}',
        '{"character": "sensei", "text": "B"}',
        '{"character": "igusa_haruka", "text": "二"}',
        '{"character": "sensei", "text": "C"}',
        '{"stage": "end", "text": ""}',
    ])
    p = BlockStreamParser()
    got: list[list[str]] = []
    for i in range(0, len(block), 7):          # 7 字节一切 → 行被切在中间
        p.feed(block[i:i + 7])
        for b in p.pop_ready():
            got.append([r.stage or r.value for r in b])
    p.finish()
    for b in p.pop_ready():
        got.append([r.stage or r.value for r in b])
    assert got == [["switch", "igusa_haruka", "sensei", "sensei"],
                   ["igusa_haruka", "sensei"], ["end"]], got
    assert p.art_hint == "画面意向"                       # 块级声明不入板
    assert len(p.records) == 8 and not p.notes
    assert check_block(parse_stream(block).records) == []  # 与批式边界一致
    print("    stream: 逐 chunk 增量解析 + 板边界与批式同源")


def test_board_split_batch_stream_equivalence():
    """**批式与流式切板必须逐板等价**（2026-09-13 审计 B2 复核 → 补钉住）。

    两条实现独立: 批式 `bond_story._board_spans`（CLI 与 webgui 预生成的唯一
    路径）、流式 `records.BlockStreamParser`（渐进渲染路径）。它们对**同一块**
    必须切出同样的板——否则同一段内容走两条路会得到不同的板边界, 而板边界是
    `place_hint`/choices/落库单位（append-only, 事后无法对齐）。

    审计曾报"批式 `i > start` 会把板首 switch 并进上一板"——复核为**误报**:
    槽后收板已把 `start` 推到 switch 之后, 守卫因此成立。本用例把五种边界
    （群后 switch / 超长群 / 群中 switch / 群结尾 / art+memorial）逐板比对,
    含 `place_hint`, 防的是"以后改一边忘了另一边"。
    """
    from contract.records import (STAGE_ART, BlockStreamParser,  # noqa: E402
                                  MAX_SENSEI_RUN)
    from core.bond.bond_story import BondScene, _board_spans  # noqa: E402

    S = lambda t: '{"stage": "switch", "text": "%s"}' % t          # noqa: E731
    C = lambda c, t: '{"character": "%s", "text": "%s"}' % (c, t)  # noqa: E731
    H = "igusa_haruka"
    cases = {
        "群后紧跟 switch": [S("教室"), C(H, "老师"), C("sensei", "嗯。"),
                            S("天台"), C(H, "风好大")],
        "switch 在群前": [C(H, "老师"), C("sensei", "嗯。"),
                          S("天台"), C(H, "风好大")],
        f"超长群（{MAX_SENSEI_RUN + 1} 连 sensei）":
            [S("教室")] + [C("sensei", f"第{i}句")
                           for i in range(1, MAX_SENSEI_RUN + 2)] + [C(H, "嗯。")],
        "switch 落在群中间": [S("教室"), C(H, "老师"), C("sensei", "嗯。"),
                              S("天台"), C("sensei", "那边"), C(H, "好")],
        "群结尾即块尾": [S("教室"), C(H, "老师"), C("sensei", "嗯。")],
        "相邻双 switch": [S("教室"), S("天台"), C(H, "老师")],
        "art 在块首 + memorial":
            ['{"stage": "art", "text": "她在坡道回头"}', S("坡道"), C(H, "老师"),
             '{"stage": "memorial", "text": "她笑了。"}'],
    }
    for name, lines in cases.items():
        block = "\n".join(lines)
        flow = tuple(r for r in parse_stream(block).records if r.stage != STAGE_ART)

        batch: list[tuple] = []
        for a, b, group in _board_spans(flow):
            sl = flow[a:b]
            sc = BondScene.from_board(sl, group=tuple(i - a for i in group))
            batch.append((tuple(r.value for r in sl), sc.place_hint))

        p = BlockStreamParser()
        p.feed(block + "\n")
        p.finish()
        stream = []
        for b in p.all_boards():
            sc = BondScene.from_board(b, group=())
            stream.append((tuple(r.value for r in b), sc.place_hint))

        assert batch == stream, f"[{name}] 批式/流式切板分歧:\n  批式={batch}\n  流式={stream}"
        assert batch, f"[{name}] 不该切出空板"
    print(f"    records: 批式/流式切板逐板等价（{len(cases)} 种边界, 含 place_hint）")


def test_block_stream_parser_edge_cases():
    """流式边界: 超长群切槽 / 丢行记账 / 空流。"""
    from contract.records import BlockStreamParser

    p = BlockStreamParser()
    p.feed("\n".join([
        '{"character": "sensei", "text": "1"}',
        '{"character": "sensei", "text": "2"}',
        '{"character": "sensei", "text": "3"}',
        '{"character": "sensei", "text": "4"}',       # 第 4 条 → 切槽
        '{"character": "igusa_haruka" "text": "缺逗号"}',   # 坏行 → DROP 记账
    ]))
    p.finish()
    boards = [[r.text for r in b] for b in p.pop_ready()]
    assert boards == [["1", "2", "3"], ["4"]], boards
    assert any("DROP" in n for n in p.notes), p.notes

    empty = BlockStreamParser()
    empty.feed("")
    empty.finish()
    assert empty.pop_ready() == [] and empty.records == []
    print("    stream: 超长群切槽 + 丢行记账 + 空流不炸")


# ---------------------------------------------------------------------------
# P0-4：块载体（记录数组 + 群 + 位置 + 两种出口）
# ---------------------------------------------------------------------------

_BLOCK_TEXT = "\n".join([
    '{"stage": "art", "text": "她在坡道上回头，眼里有一点水光"}',   # art 必须块首（配对）
    '{"stage": "switch", "text": "深夜的杂草屋"}',
    '{"character": "igusa_haruka", "text": "……老师。"}',
    '{"character": "sensei", "text": "是我来晚了。"}',
    '{"character": "igusa_haruka", "text": "「……」"}',
    '{"character": "sensei", "text": "先坐下吧。"}',
    '{"character": "sensei", "text": "要说的话，慢慢说。"}',
    '{"stage": "memorial", "text": "（她抬起头。）"}',
    '{"character": "igusa_haruka", "text": "「那种话，我不想再听了。」"}',
])


def test_vn_block_derived_views():
    """块载体：群 / 位置 / 前后切片 —— 位置元数据齐备，且与校验结论一致。

    ⚠️ 2026-09-20 起这块是**成对形状**（art 在首条 + memorial 在后）——art 与
    memorial 必须同轮成对（docs/DESIGN_MEMORIAL.md M1），夹具跟着走。
    """
    blk = VnBlock.from_text(_BLOCK_TEXT)
    assert len(blk.records) == 9 and blk.is_valid and blk.issues == ()
    assert blk.art_at == 0 and blk.switch_at == 1 and blk.memorial_at == 7
    assert blk.end_at is None and blk.exit_at is None
    # 两群：run=1（第 4 条）+ run=2（第 6~7 条）
    assert blk.groups == ((3,), (5, 6))
    assert blk.group_texts == (("是我来晚了。",), ("先坐下吧。", "要说的话，慢慢说。"))
    assert blk.has_choices
    # 纪念闸门切片：闸门前可渲染前缀 / 纪念区间本体
    assert len(blk.before(blk.memorial_at)) == 7
    assert [r.text for r in blk.after(blk.memorial_at)] == ["「那种话，我不想再听了。」"]
    assert blk.after(None) == ()
    print("    block: 群/位置/前后切片")


def test_vn_block_render_and_roundtrip():
    """两种出口：渲染文本（最小说话人形态）与 to_dict/from_dict 往返稳定。"""
    blk = VnBlock.from_text(_BLOCK_TEXT)
    text = blk.render_text()
    assert "老师：是我来晚了。" in text
    assert "haruka：「……」" in text            # 未给名字表 → 回落到 id
    assert "深夜的杂草屋" in text                # switch 回显自己的话
    assert "（她抬起头。）" in text              # memorial 文本照常显示
    assert "春香：「……」" in blk.render_text({"igusa_haruka": "春香"})       # 名字表覆盖 id
    assert "haruka：" not in blk.render_text({"igusa_haruka": "春香"})
    assert "是我来晚了。" in blk.render_text(speaker=False)           # 关前缀 → 纯文本
    assert "老师：" not in blk.render_text(speaker=False)
    # 往返：payload → 块 → payload 逐字节一致
    payload = blk.to_dict()
    assert payload["records"][0] == {"stage": "art", "text": "她在坡道上回头，眼里有一点水光"}
    assert payload["records"][1] == {"stage": "switch", "text": "深夜的杂草屋"}
    back = VnBlock.from_dict(payload)
    assert back.records == blk.records and back.to_dict() == payload
    # 裸 list 也吃（历史存档里可能是纯数组）
    assert VnBlock.from_dict(payload["records"]).records == blk.records
    print("    block: 渲染（最小说话人形态）+ payload 往返")


def test_vn_block_records_notes_and_legacy_rejection():
    """块载体：坏行/修复进 notes（可观测）；旧契约 payload 显式拒绝而非猜。"""
    blk = VnBlock.from_text("\n".join([
        '{"character": "igusa_haruka", "text": "她说 "好"。"}',      # 可救 → NOTE
        '{"character": "igusa_haruka" "text": "缺逗号"}',            # 不可救 → DROP
    ]))
    assert [r.text for r in blk.records] == ['她说 "好"。']
    joined = "\n".join(blk.notes)
    assert "NOTE" in joined and "辅助转义" in joined
    assert "DROP" in joined and "JSON 解析失败" in joined
    assert blk.to_dict()["notes"] == list(blk.notes)
    # 旧契约 payload（现网 paragraphs/choices/branches）→ 明确报错，不静默降级
    for legacy in ({"paragraphs": ["a"], "choices": ["b"]}, {"scene": {}, "text": "x"}):
        try:
            VnBlock.from_dict(legacy)
        except ValueError as e:
            assert "records" in str(e) and "旧" in str(e), e
        else:                                                  # pragma: no cover
            raise AssertionError(f"旧契约 payload 应被拒绝: {legacy}")
    print("    block: 修复/丢行记账 + 旧档拒绝")


def test_vn_block_keeps_issues_not_blocks():
    """校验只出问题清单：不合规块照样装得下（拦不拦是引擎的判断）。"""
    # ① end 不在块尾 + ② sensei 群超上限
    recs = [_rec("igusa_haruka", "开场"), _rec("end", "收尾", KIND_STAGE),
            _rec("igusa_haruka", "后面还有话"),
            _rec(CHARACTER_SENSEI, "一"), _rec(CHARACTER_SENSEI, "二"),
            _rec(CHARACTER_SENSEI, "三"), _rec(CHARACTER_SENSEI, "四")]
    blk = VnBlock.from_records(recs)
    assert len(blk.records) == 7 and not blk.is_valid
    assert any("必须块尾" in i for i in blk.issues), blk.issues
    assert any("群过长" in i for i in blk.issues), blk.issues
    assert blk.issues == tuple(check_block(recs))
    # ③ memorial 之后出现 switch → 纪念区间违规（switch 本身位置自由）
    mid = VnBlock.from_records([_rec("igusa_haruka", "开口"),
                                _rec("memorial", "触发", KIND_STAGE),
                                _rec("switch", "换场", KIND_STAGE)])
    assert any("纪念区间" in i for i in mid.issues), mid.issues
    # validate=False → 只当容器（引擎自行判定时用）
    assert VnBlock.from_records(recs, validate=False).issues == ()
    print("    block: 校验只出清单，不拦不修")
