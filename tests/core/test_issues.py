"""契约问题原语（`contract/issues.py`，a₀ 2026-09-25）——跨域共用的机制。

搬来的四件在 VN 侧已由 `tests/core/test_records.py` 覆盖行为（软硬分级不看文案那条
守门用例也在那儿）。这里只钉**新增的那一层**：机制共用 + **码表各自声明**。

覆盖:
    声明表       域 import 时 declare_severity(自己的表) → Issue.severity 查得到
    未声明       查不到的码 → KeyError，且报错文本**带指路**（别让人猜）
    冲突         两个域把同一个码声明成不同严重度 → ValueError（防串台）
    跨域共存     两个域各自的码在同一张总表里互不干扰（MMT/VN 并存的前提）
    文案无关     同一码换文案, 分级不变（跨域的版本；VN 的版本在 test_records）
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from contract.issues import (                                    # noqa: E402
    Issue,
    IssueSeverity,
    declare_severity,
    declared_severity,
    format_issues,
    split_issues,
)


class FakeCode(str):
    """假的域码（`str` 子类，模拟各域的 `str` Enum）。"""


def test_declared_table_resolves_and_ignores_message():
    declare_severity({FakeCode("fake.soft"): IssueSeverity.SOFT,
                      FakeCode("fake.hard"): IssueSeverity.HARD})
    soft = Issue(FakeCode("fake.soft"), "必须块尾 空块 条 memorial")   # 文案全是硬关键词
    hard = Issue(FakeCode("fake.hard"), "小建议")
    assert soft.severity is IssueSeverity.SOFT and not soft.hard
    assert hard.severity is IssueSeverity.HARD and hard.hard
    h, s = split_issues([soft, hard])
    assert h == [hard] and s == [soft]
    assert format_issues([soft, hard]) == "必须块尾 空块 条 memorial; 小建议"
    print("    issues: 分级只跟码走（文案塞满硬关键词也不动）+ format/split")


def test_undeclared_code_raises_with_pointer():
    try:
        declared_severity("nobody.declared-this")
    except KeyError as e:
        assert "declare_severity" in str(e), str(e)      # 报错要带指路
        print("    issues: 未声明的码 → KeyError（带指路）")
    else:
        raise AssertionError("未声明的码应当直接炸（别静默给个默认软硬）")


def test_conflicting_declaration_rejected():
    """两个域把同一个码声明成不同严重度 → 当场报错（码要全仓唯一）。"""
    declare_severity({FakeCode("dup.code"): IssueSeverity.SOFT})
    try:
        declare_severity({FakeCode("dup.code"): IssueSeverity.HARD})
    except ValueError as e:
        assert "dup.code" in str(e)
        print("    issues: 同码冲突声明 → ValueError")
    else:
        raise AssertionError("同码两种严重度必须报错——否则两域会静默串台")
    # 同码**同**严重度重复声明是允许的（幂等; 模块被重复 import 时不炸）
    declare_severity({FakeCode("dup.code"): IssueSeverity.SOFT})
