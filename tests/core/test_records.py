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
                              VnBlock, VnRecord, check_block, parse_line,
                              parse_stream, sensei_group_labels, sensei_groups)


def _rec(value, text="x", kind=KIND_CHARACTER, line_no=0) -> VnRecord:
    return VnRecord(kind=kind, value=value, text=text, line_no=line_no)


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
    """art 块首 / end·exit 块尾 / 纪念区间禁换场 / 二次纪念 / 二次 art / 空块。"""
    ok = [_rec("switch", "开场景", KIND_STAGE), _rec("art", "意向", KIND_STAGE),
          _rec("igusa_haruka", "铺垫"), _rec("memorial", "触发", KIND_STAGE),
          _rec("igusa_haruka", "纪念正文"), _rec("end", "收尾", KIND_STAGE)]
    assert check_block(ok) == [], check_block(ok)

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

    assert check_block([]) == ["空块：没有任何记录"]
    print("    block: 位置/区间/重复/空块 六项判定")


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
    """schema 文本覆盖全部取值 + 关键规则 + 三条文案纪律（用户裁决 #24）。"""
    from contract.records import STAGE_VALUES
    from contract.schema import build_record_schema

    text = build_record_schema()
    for value in STAGE_VALUES:
        assert f'"{value}"' in text, value
    for value in ("igusa_haruka", CHARACTER_NARRATOR, CHARACTER_SENSEI):
        assert value in text, value
    assert "一行一条" in text
    assert '\\"' in text                       # 转义示范（实战唯一真实错误源）
    assert f"1~{MAX_SENSEI_RUN} 条" in text     # 群上限
    assert "不要数组" in text and "不要围栏" in text
    assert "stage=end / exit 外必填" in text    # end 的 text 可留空（收尾字段）
    assert "不是老师的话" in text and "黑屏收尾" in text
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
# P0-4：块载体（记录数组 + 群 + 位置 + 两种出口）
# ---------------------------------------------------------------------------

_BLOCK_TEXT = "\n".join([
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
    """块载体：群 / 位置 / 前后切片 —— 位置元数据齐备，且与校验结论一致。"""
    blk = VnBlock.from_text(_BLOCK_TEXT)
    assert len(blk.records) == 8 and blk.is_valid and blk.issues == ()
    assert blk.switch_at == 0 and blk.art_at is None and blk.memorial_at == 6
    assert blk.end_at is None and blk.exit_at is None
    # 两群：run=1（第 3 条）+ run=2（第 5~6 条）
    assert blk.groups == ((2,), (4, 5))
    assert blk.group_texts == (("是我来晚了。",), ("先坐下吧。", "要说的话，慢慢说。"))
    assert blk.has_choices
    # 纪念闸门切片：闸门前可渲染前缀 / 纪念区间本体
    assert len(blk.before(blk.memorial_at)) == 6
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
    assert payload["records"][0] == {"stage": "switch", "text": "深夜的杂草屋"}
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
