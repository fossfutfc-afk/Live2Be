# -*- coding: utf-8 -*-
"""MMT 回合级校验（`core/mmt/mmt_check.py`，⑥-2c 2026-09-25）。

覆盖:
    空轮 / 独占约束（inspect 静默轮 · trigger 唯一操作行）
    chapter_title 长度（⭐ registry **不校验**这条——b 阶段实测, 必须在这儿补）
    丢行记账（软, 一条汇总）
    码表完整 + 与 VN 的码表在同一张总表里共存（`contract.issues`）
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from contract.issues import IssueSeverity, declared_severity, split_issues   # noqa: E402
from contract.records import ISSUE_SEVERITY as VN_SEVERITY                   # noqa: E402
from contract.streams import ParseDiag                                       # noqa: E402
from core.mmt.mmt_check import (                                             # noqa: E402
    ISSUE_SEVERITY,
    MmtIssueCode,
    TITLE_MAX,
    TITLE_MIN,
    check_turn,
)
from core.mmt.mmt_lines import MmtLine                                       # noqa: E402


def _text(s="话"):
    return MmtLine(kind="text", text=s)


def _action(name, **payload):
    return MmtLine(kind="action", action=name, payload=payload)


def _codes(issues):
    return [i.code for i in issues]


# ---------------------------------------------------------------------------
# 组合约束
# ---------------------------------------------------------------------------

def test_clean_turn_has_no_issues():
    ok = [_text("老师你看这个！"), _action("mmt_send_media", image="夕阳"),
          _text("好看吧？")]
    assert check_turn(ok) == [], check_turn(ok)
    # trigger + 前面的消息行 = **合规**（见面的话写在它前面就是设计要的形状）
    trig = [_text("我马上过去找你！"), _action("mmt_trigger_bond_story",
                                              chapter_title="电车上的零食")]
    assert check_turn(trig) == [], check_turn(trig)
    print("    check: 正常轮（交错 / trigger 带前置消息）= 无问题")


def test_noticed_row_does_not_break_exclusivity():
    """⭐ N5b: **想起行不计入独占判据里的"行"** —— 它是账目不是内容。

    判据的目的是"这一轮**还有没有别的行**"（内容/别的操作才是问题）, 而想起行不上屏、
    零成本、不触发任何调用。把它算进去只会产出**假硬问题** ⇒ 整轮回灌重发一次
    （白跑）。⇒ 她和独占动作同轮顺手记一笔, 是允许的。

    ⚠️ 2026-10-08（D 笔）: 这条性质原来挂在 `inspect` 上（那时它是"整轮只有它一条行"
    的静默推理轮）—— 现在拿 `look`（唯一操作行那一款）来钉, 性质一字不变。
    """
    rows = [_action("mmt_look", clue="苔藓"),
            MmtLine(kind="noticed", noticed="瓦片缝里的苔藓")]
    assert check_turn(rows) == [], _codes(check_turn(rows))
    # 对照: 夹一条**消息行** —— look 允许话写在前面, 所以仍然合规（口径是"唯一**操作**行"）
    assert check_turn([*rows, _text("诶……")]) == []
    # 对照: 夹一条**别的操作行**才违规（内容不是问题, 独占才是）
    bad = [*rows, _action("mmt_send_media", image="苔藓")]
    assert MmtIssueCode.EXCLUSIVE_VIOLATION in _codes(check_turn(bad))
    print("    N5b: 想起行不算「别的行」（独占判据不误伤）")


def test_empty_turn_is_hard():
    issues = check_turn([])
    assert _codes(issues) == [MmtIssueCode.EMPTY_TURN]
    assert issues[0].hard, "空轮必须硬（否则模型以为说过了）"
    print("    check: 空轮 → mmt.empty-turn（硬）")


def test_trigger_must_be_only_action():
    bad = [_text("那还等什么～"),
           _action("mmt_trigger_bond_story", chapter_title="柴关拉面的邀请"),
           _action("mmt_send_media", image="拉面")]
    issues = check_turn(bad)
    assert MmtIssueCode.EXCLUSIVE_VIOLATION in _codes(issues)
    assert "mmt_send_media" in str(issues[0]), issues[0]
    print("    check: trigger 独占操作行（另有操作 → 违规，硬）")


def test_chapter_title_length_is_checked_here():
    """⭐ registry 只管"是字符串"（空标题放行）——长度由本层补（b 阶段实测）。"""
    for title in ("", "雨", "x" * (TITLE_MAX + 1)):
        issues = check_turn([_action("mmt_trigger_bond_story", chapter_title=title)])
        assert MmtIssueCode.CONTROL_INVALID in _codes(issues), (title, issues)
        assert f"{TITLE_MIN}-{TITLE_MAX} 字" in str(issues[0])
    # 边界内正常
    for title in ("雨" * TITLE_MIN, "雨" * TITLE_MAX):
        assert check_turn([_action("mmt_trigger_bond_story", chapter_title=title)]) == []
    print(f"    check: chapter_title {TITLE_MIN}-{TITLE_MAX} 字（registry 不管这条）")


# ---------------------------------------------------------------------------
# 丢行记账（软）+ 码表
# ---------------------------------------------------------------------------

def test_dropped_lines_are_soft_summary():
    diags = (ParseDiag(2, '{"nope": 1}', "行既无 text 也无 action"),
             ParseDiag(5, "这不是 JSON", "JSON 解析失败: Expecting value"))
    issues = check_turn([_text("好的")], diags)
    assert _codes(issues) == [MmtIssueCode.LINE_BAD]
    assert not issues[0].hard, "丢内容行只是少说一句（软）"
    hard, soft = split_issues(issues)
    assert not hard and soft == issues
    msg = str(issues[0])
    assert "第 2 行" in msg and "第 5 行" in msg and "共 2 行" in msg
    # 全丢光 → 软记账 + 硬空轮
    codes = _codes(check_turn([], diags))
    assert codes == [MmtIssueCode.LINE_BAD, MmtIssueCode.EMPTY_TURN], codes
    print("    check: 丢行 = 一条汇总软记账（含行号与原因）")


def test_severity_table_declared_and_coexists_with_vn():
    assert set(ISSUE_SEVERITY) == set(MmtIssueCode), \
        f"未声明严重度的码: {set(MmtIssueCode) - set(ISSUE_SEVERITY)}"
    assert declared_severity(MmtIssueCode.LINE_BAD) is IssueSeverity.SOFT
    assert declared_severity(MmtIssueCode.EMPTY_TURN) is IssueSeverity.HARD
    # 两域的表在同一张总表里共存（`declare_severity` 没把它们搞串）
    assert set(VN_SEVERITY) and all(declared_severity(c) is s for c, s in VN_SEVERITY.items())
    assert not (set(c for c in ISSUE_SEVERITY) & set(c for c in VN_SEVERITY))
    # 文案不影响分级（跨域版：塞满硬关键词的软码仍是软）
    from contract.issues import Issue
    stuffed = Issue(MmtIssueCode.CONTROL_UNEXECUTED, "空块 必须块尾 必须块首")
    assert not stuffed.hard
    print("    check: 5 个码全部声明 + 与 VN 表共存 + 文案不影响分级")
