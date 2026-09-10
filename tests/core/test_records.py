# -*- coding: utf-8 -*-
"""VN 记录流契约单测 — 行解析（P0-2）+ 群/位置校验（P0-1）。

覆盖设计文档 §2 文法与 §9 失败口径：三类坏行的容错（未转义引号 / 末行悬空 / 数组行）、
形状违规丢行、sensei 群语义（用户样例）、块内位置约束。

运行: python -m pytest tests/core/test_records.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from contract.records import (CHARACTER_NARRATOR, CHARACTER_SENSEI,  # noqa: E402
                              KIND_CHARACTER, KIND_STAGE, MAX_SENSEI_RUN,
                              VnRecord, check_block, parse_line, parse_stream,
                              sensei_group_labels, sensei_groups)


def _rec(value, text="x", kind=KIND_CHARACTER, line_no=0) -> VnRecord:
    return VnRecord(kind=kind, value=value, text=text, line_no=line_no)


# ---------------------------------------------------------------------------
# 行解析：合法形状
# ---------------------------------------------------------------------------

def test_parse_all_record_kinds():
    """七种取值都能解析，且 to_dict 与 wire 形状对称。"""
    lines = [
        '{"character": "haruka", "text": "……老师，你、你来了。"}',
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
        "haruka", CHARACTER_SENSEI, CHARACTER_NARRATOR,
        "switch", "art", "memorial", "end", "exit"]
    assert res.records[-1].text == ""                      # exit 的 text 可省
    wire = res.records[0].to_dict()
    assert wire == {"character": "haruka", "text": "……老师，你、你来了。"}
    print("    parse: 七种取值 + exit 省 text + to_dict 对称")


def test_empty_and_fence_lines_are_silent():
    """空行 / 代码围栏 → 静默跳过（不算错误）。"""
    res = parse_stream(['```json', '', '{"character": "haruka", "text": "嗨"}', '```'])
    assert len(res.records) == 1 and not res.diags
    print("    parse: 空行/围栏静默跳过")


# ---------------------------------------------------------------------------
# 行解析：形状违规（丢行 + 记账，不抛）
# ---------------------------------------------------------------------------

def test_shape_violations_dropped_with_diag():
    """形状违规丢行并记账：双判别符 / 都无 / 未知 stage / 空 text / 非对象 / 多余字段为 NOTE。"""
    cases = [
        ('{"character": "haruka", "stage": "end", "text": "x"}', "同时含"),
        ('{"text": "没有判别符"}', "既无"),
        ('{"stage": "bogus", "text": "x"}', "未知 stage"),
        ('{"character": "haruka", "text": "   "}', "text 不能为空"),
        ('[1, 2, 3]', "数组行内无合法记录"),
        ('"裸字符串"', "必须是 JSON 对象"),
    ]
    for line, expect in cases:
        rec, diag = parse_line(line, 1)
        assert rec is None, line
        assert diag is not None and diag.dropped and expect in diag.error, (line, diag)
    # 多余字段：保留记录 + NOTE
    rec, diag = parse_line('{"character": "haruka", "text": "嗨", "emotion": "nomal"}', 1)
    assert rec is not None and diag is not None and not diag.dropped
    assert "多余字段" in diag.error
    print("    parse: 六类违规丢行 + 多余字段 NOTE")


def test_unescaped_quote_is_rescaped():
    """未转义半角引号 → 辅助转义救回 + NOTE（文本逐字节还原）。"""
    line = '{"character": "haruka", "text": "……不是 "别担心" 这种话。"}'
    rec, diag = parse_line(line, 3)
    assert rec is not None and rec.value == "haruka"
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
        '{"character": "haruka", "emotion": "normal", "text": "听 "心跳" 声。"}', 5)
    assert rec2 is not None and rec2.text == '听 "心跳" 声。'
    assert "多余字段" in diag2.error
    # 中文引号 / 已正确转义的半角引号（含结尾）/ 无引号：一律不触发修复
    for ok in ('{"character": "haruka", "text": "「别担心」这种话。"}',
               '{"character": "haruka", "text": "不是 \\"别担心\\" 这种话。"}',
               '{"character": "haruka", "text": "他问：\\"走吗？\\""}',
               '{"character": "haruka", "text": "走吧。"}'):
        r, d = parse_line(ok, 6)
        assert r is not None and d is None, (ok, d)
    print("    parse: 辅助转义边界（多引号/悬空/多余字段/正常引号不触发）")


def test_unescapable_line_still_dropped():
    """辅助转义不越界：非本类形状（缺逗号等）依旧丢行。"""
    for bad in ('{"character": "haruka" "text": "缺逗号"}',
                '{"character": "haruka", "text": ["不是字符串"]}'):
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
    line = ('[{"character": "haruka", "text": "一"}, '
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
        '{"character": "haruka", "text": "……老师。"}',
        '{"character": "haruka" "text": "缺逗号，不可救"}',                    # 坏行
        '{"character": "sensei", "text": "我想要的不是 "别担心" 这种话。"}',   # 可救
        '{"stage": "memorial", "text": "（她抬起头。）"}',
        '{"character": "haruka", "text": "「……」"}',
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
    seq = ["haruka", "haruka", CHARACTER_SENSEI,
           "haruka", "haruka", CHARACTER_SENSEI, CHARACTER_SENSEI, CHARACTER_SENSEI,
           "haruka"]
    recs = [_rec(v, text=f"台词{i}") for i, v in enumerate(seq)]
    groups = sensei_groups(recs)
    assert [[len(g) for g in groups]] == [[1, 3]], groups
    labels = sensei_group_labels(recs)
    assert labels[0] == ["台词2"] and len(labels[1]) == 3
    print("    groups: 用户样例 → 2 群（1 + 3）")


def test_sensei_run_over_limit_flagged():
    """群长度上限 3：4 连 → 块校验报错。"""
    recs = [_rec("haruka", "铺垫"), *[_rec(CHARACTER_SENSEI, f"话{i}") for i in range(4)],
            _rec("haruka", "回应")]
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
          _rec("haruka", "铺垫"), _rec("memorial", "触发", KIND_STAGE),
          _rec("haruka", "纪念正文"), _rec("end", "收尾", KIND_STAGE)]
    assert check_block(ok) == [], check_block(ok)

    bad_art = [_rec("haruka", "铺垫"), _rec("art", "意向", KIND_STAGE)]
    assert any("首条不是 switch" in i for i in check_block(bad_art))
    bad_art3 = [_rec("haruka", "一"), _rec("haruka", "二"), _rec("art", "意向", KIND_STAGE)]
    assert any("art 必须块首" in i for i in check_block(bad_art3))

    bad_tail = [_rec("end", "收尾", KIND_STAGE), _rec("haruka", "后面还有")]
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
            _rec("haruka", "铺垫"), _rec("memorial", "触发", KIND_STAGE)]
    assert check_block(recs) == [], check_block(recs)
    print("    block: 开章 switch + art 紧随 = 合规")


# ---------------------------------------------------------------------------
# P0-3：LLM 可见的契约文本（第三种形态）
# ---------------------------------------------------------------------------

def test_build_record_schema_covers_all_values():
    """schema 文本覆盖全部取值 + 关键软规则（含转义示范与群上限）。"""
    from contract.records import STAGE_VALUES
    from contract.schema import build_record_schema

    text = build_record_schema()
    for value in STAGE_VALUES:
        assert f'"{value}"' in text, value
    for value in ("haruka", CHARACTER_NARRATOR, CHARACTER_SENSEI):
        assert value in text, value
    assert "一行一条" in text
    assert '\\"' in text                       # 转义示范（实战唯一真实错误源）
    assert f"1~{MAX_SENSEI_RUN} 条" in text     # 群上限
    assert "不要数组" in text and "代码围栏" in text
    assert "stage=exit" in text and "块首" in text and "块尾" in text
    # 关掉示例时更短，但仍含硬规则
    brief = build_record_schema(with_examples=False)
    assert len(brief) < len(text) and "硬规则" in brief and "示例" not in brief
    print("    schema: 全取值 + 转义示范 + 群上限 + 可关示例")
