# -*- coding: utf-8 -*-
"""契约问题的**通用载体**（a₀, 2026-09-25）——从 `contract.records.check` 上提。

搬来的四件（节点 6, 2026-09-21 的成果）：
`IssueSeverity`（硬/软）· `Issue`（code + message，severity 是**派生属性**）·
`format_issues`（清单 → 一行文本的唯一出口）· `split_issues`（清单 → (硬, 软)）。

⭐ **机制共用、码表各自声明**（`docs/DESIGN_STREAM_CONTRACT.md` §10.2 B4）：
每个域 import 时用 `declare_severity(自己的表)` 声明一次，`Issue.severity` 查它。
VN 的表在 `contract/records/check.py`（`ISSUE_SEVERITY`，码 `block.*` / `board.*`）；
MMT 的表在 `core/mmt/mmt_check.py`（码 `mmt.*`）。

## 纪律（这条是 2026-09-21 那次事故的产物，别退化）

**严重度只跟 `code` 走，跟 `message` 文案毫无关系。** 历史：之前硬/软靠中文子串匹配
（`HARD_BLOCK_ISSUE_MARKS`），给一条软问题换个措辞——哪怕只是写进"必须块尾"四个字——
就会**静默**升级成"整轮重发"（ARCH_REVIEW P0-3）。所以：
· 新增规则 = 加码 + 在自己域的表里**显式声明**一行（忘了声明 → 查表 KeyError，当场炸）；
· 同一个码被两个域声明成不同严重度 → `declare_severity` 直接报错（防串台）。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class IssueSeverity(str, Enum):
    """问题严重度——决定引擎对它的**本回合**处置。

    · `HARD`: 形状类（块首/块尾/纪念区间/空块/板上 end 后有记录）→ **打回重发整轮**;
    · `SOFT`: 只记录（切群 / 统计口径 / 建议）——流式已交付时硬问题也降级走这条路。
    """

    HARD = "hard"
    SOFT = "soft"


#: 各域声明的**软硬唯一真源**（码 → 严重度）；由 `declare_severity` 填充。
_SEVERITY: dict[str, IssueSeverity] = {}


def _key(code: Any) -> str:
    """码归一成字符串（`str` Enum 取 `.value`，裸字符串原样）。"""
    return code.value if isinstance(code, Enum) else str(code)


def declare_severity(table: Mapping[Any, IssueSeverity]) -> None:
    """域在 **import 时**声明自己的码表（`Issue.severity` 查这张总表）。

    Raises:
        ValueError: 同一个码被声明成两种严重度（两个域的码重名 ⇒ 早点炸，别串台）。
    """
    for code, severity in table.items():
        key = _key(code)
        if key in _SEVERITY and _SEVERITY[key] is not severity:
            raise ValueError(
                f"[issues.py][SeverityConflict][码 {key!r} 已声明为 {_SEVERITY[key].value}, "
                f"不能改声明成 {severity.value}——码要全仓唯一, 换个前缀]")
        _SEVERITY[key] = severity


def declared_severity(code: Any) -> IssueSeverity:
    """查一个码的严重度（未声明 → 带指路的 KeyError）。"""
    key = _key(code)
    try:
        return _SEVERITY[key]
    except KeyError:
        raise KeyError(
            f"[issues.py][SeverityUndeclared][码 {key!r} 没有声明严重度——"
            f"在自己域的 check 模块里 declare_severity(表) 加一行]") from None


@dataclass(frozen=True)
class Issue:
    """一条契约问题：`code`（机器）+ `message`（人读中文）。

    `severity` 是**派生属性**（查本域声明进 `_SEVERITY` 的表）——想改分级只能改那张表，
    没法在构造点"顺手"把它变成硬/软，也没法靠文案影响它。

    ⚠️ `code` 的类型是**各域自己的码**（VN = `IssueCode` 枚举；MMT = `MmtIssueCode`），
    所以这里不写死类型——共用层只认"码 → 表"这条规则。
    """

    code: Any
    message: str

    @property
    def severity(self) -> IssueSeverity:
        return declared_severity(self.code)

    @property
    def hard(self) -> bool:
        return self.severity is IssueSeverity.HARD

    def __str__(self) -> str:                        # 日志/反馈/注记直接 f-string 即可
        return self.message


def format_issues(issues: Iterable[Issue], sep: str = "; ") -> str:
    """问题清单 → 一行文本（日志 / trace / feedback / 下一轮注记的**唯一出口**）。

    ⚠️ 别写 `sep.join(issues)`——`Issue` 不是 `str`（只有 `__str__`），join 会 TypeError。
    """
    return sep.join(str(i) for i in issues)


def split_issues(issues: Iterable[Issue]) -> tuple[list[Issue], list[Issue]]:
    """问题清单 → (硬, 软)。判据**只是** `Issue.severity`（不读文案）。"""
    hard: list[Issue] = []
    soft: list[Issue] = []
    for i in issues:
        (hard if i.hard else soft).append(i)
    return hard, soft
