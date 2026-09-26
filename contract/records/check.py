# -*- coding: utf-8 -*-
"""`contract.records` 的**校验层**（C10, `docs/EXEC_SPLIT.md`）。

`sensei_groups` / `sensei_group_labels`（把记录流切成"老师群"——群是换板与选项的判据）·
**VN 的码表** `IssueCode` / `ISSUE_SEVERITY`（**严重度只跟 code 走**，与中文文案无关）·
`check_block`（块级硬软判定）· `check_board`（板级闸）。

⭐ **机制上提了**（a₀, 2026-09-25）：`IssueSeverity` / `Issue` / `format_issues` /
`split_issues` 的真家 = **`contract/issues.py`**（跨域共用：机制共用、**码表各自声明**）。
本模块 import 它们并**再导出**（`contract.records` 对外面不变），并在 import 时把
VN 的表 `declare_severity(ISSUE_SEVERITY)` 声明进去。

## 纪律

· 依赖方向: `check` → `grammar` · `contract.issues`; **不许** import `parse` / `carrier`
  （`carrier` 反过来用这里的 `check_block`）;
· 新增 VN 规则 = 加码 + 在 `ISSUE_SEVERITY` 显式声明一行（忘了 → 守门用例直接红，
  且 `Issue.severity` 查表会炸）;
· 搬进来的代码**逐字未改**。
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from contract.issues import (                    # a₀: 机制真家在 contract/issues.py
    Issue,
    IssueSeverity,
    declare_severity,
    format_issues,
    split_issues,
)
from contract.records.grammar import (
    MAX_SENSEI_RUN,
    STAGE_ART,
    STAGE_BLOCK_HEAD,
    STAGE_BLOCK_TAIL,
    STAGE_END,
    STAGE_FORBIDDEN_IN_MEMORIAL,
    STAGE_MEMORIAL,
    STAGE_SWITCH,
    VnRecord,
)


# ---------------------------------------------------------------------------
# 块内结构校验（P0-1 文法；引擎复用）
# ---------------------------------------------------------------------------


def sensei_groups(records: Iterable[VnRecord]) -> list[list[int]]:
    """连续 `sensei` 段 = 群（返回每群的下标列表，按出现顺序）。"""
    groups: list[list[int]] = []
    current: list[int] = []
    for i, rec in enumerate(records):
        if rec.is_sensei:
            current.append(i)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def sensei_group_labels(records: Iterable[VnRecord]) -> list[list[str]]:
    """各群的候选台词文本（引擎生成交互槽用）。"""
    recs = list(records)
    return [[recs[i].text for i in g] for g in sensei_groups(recs)]


# ---------------------------------------------------------------------------
# VN 的码表（机制在 `contract.issues`；**码与严重度是 VN 自己的**）
# ---------------------------------------------------------------------------

class IssueCode(str, Enum):
    """问题**机器码**（稳定标识: 测试断言 / 日志 grep / 未来策略表都认它）。

    命名 = `层级.规则`：`block.*` 出自 `check_block`（块级）、`board.*` 出自
    `check_board`（板级闸）。
    """

    # ---- 块级 · 硬（形状类 → 打回重发）----
    BLOCK_EMPTY = "block.empty"
    BLOCK_TAIL = "block.tail"
    BLOCK_HEAD = "block.head"
    BLOCK_HEAD_NOT_SWITCH = "block.head-not-switch"
    BLOCK_MEMORIAL_REPEAT = "block.memorial-repeat"
    BLOCK_MEMORIAL_FORBIDDEN_STAGE = "block.memorial-forbidden-stage"
    BLOCK_ART_REPEAT = "block.art-repeat"
    # ---- 块级 · 软（只记录）----
    BLOCK_ART_PAIR_MISSING = "block.art-pair-missing"
    BLOCK_MEMORIAL_WITH_END = "block.memorial-with-end"
    BLOCK_SENSEI_RUN_TOO_LONG = "block.sensei-run-too-long"
    # ---- 板级（`check_board`）: 全部硬（板级闸"非空即拦"）----
    BOARD_TAIL = "board.tail"
    BOARD_MEMORIAL_REPEAT = "board.memorial-repeat"
    BOARD_MEMORIAL_FORBIDDEN_STAGE = "board.memorial-forbidden-stage"


#: **VN 的软硬真源**：severity 只跟 `code` 走，跟 `message` 文案无关。
#:
#: 为什么这样设计（节点 6；来源 ARCH_REVIEW P0-3）：2026-09-21 之前硬/软由
#: `bond_story.HARD_BLOCK_ISSUE_MARKS` 的**中文子串**匹配判——给一条软问题换个措辞
#: （哪怕只是写进"必须块尾"四个字）就会**静默**变成"整轮重发"。现在文案随便改，
#: 分级不动；新增规则必须在这里显式声明严重度（`tests/core/test_records.py`
#: 有一条守门用例扫这张表的完整性）。
#:
#: ⭐ a₀ 起这张表**声明进 `contract.issues`**（`Issue.severity` 查那张总表）——
#: 机制共用、码表各自声明；MMT 的表在 `core/mmt/mmt_check.py`。
ISSUE_SEVERITY: dict[IssueCode, IssueSeverity] = {
    IssueCode.BLOCK_EMPTY: IssueSeverity.HARD,
    IssueCode.BLOCK_TAIL: IssueSeverity.HARD,
    IssueCode.BLOCK_HEAD: IssueSeverity.HARD,
    IssueCode.BLOCK_HEAD_NOT_SWITCH: IssueSeverity.HARD,
    IssueCode.BLOCK_MEMORIAL_REPEAT: IssueSeverity.HARD,
    IssueCode.BLOCK_MEMORIAL_FORBIDDEN_STAGE: IssueSeverity.HARD,
    IssueCode.BLOCK_ART_REPEAT: IssueSeverity.HARD,
    IssueCode.BLOCK_ART_PAIR_MISSING: IssueSeverity.SOFT,
    IssueCode.BLOCK_MEMORIAL_WITH_END: IssueSeverity.SOFT,
    IssueCode.BLOCK_SENSEI_RUN_TOO_LONG: IssueSeverity.SOFT,
    IssueCode.BOARD_TAIL: IssueSeverity.HARD,
    IssueCode.BOARD_MEMORIAL_REPEAT: IssueSeverity.HARD,
    IssueCode.BOARD_MEMORIAL_FORBIDDEN_STAGE: IssueSeverity.HARD,
}

declare_severity(ISSUE_SEVERITY)      # a₀: 把 VN 的码表登记给共用层


def check_block(records: Iterable[VnRecord]) -> list[Issue]:
    """块内结构校验（返回 `Issue` 清单；空 = 合规）。**不做配额/状态判定**。

    分级由 `Issue.code` 声明的 `ISSUE_SEVERITY` 决定，与 `message` 文案**无关**：
    硬 = 形状类（块首/块尾/纪念区间/空块）→ 打回重发；
    软 = 超长群（切群）/ **art↔memorial 配对缺失** / **memorial 与 end 同轮**（只记录）。
    """
    recs = list(records)
    if not recs:
        return [Issue(IssueCode.BLOCK_EMPTY, "空块：没有任何记录")]
    issues: list[Issue] = []
    n = len(recs)

    for i, rec in enumerate(recs):
        if not rec.is_stage:
            continue
        if rec.value in STAGE_BLOCK_TAIL and i != n - 1:
            issues.append(Issue(IssueCode.BLOCK_TAIL,
                                f"{rec.value} 必须块尾（实现在第 {i + 1}/{n} 条）"))
        if rec.value in STAGE_BLOCK_HEAD and i not in (0, 1):
            issues.append(Issue(IssueCode.BLOCK_HEAD,
                                f"{rec.value} 必须块首（实现在第 {i + 1} 条）"))
        if rec.value in STAGE_BLOCK_HEAD and i == 1:
            head = recs[0]
            if not (head.is_stage and head.value == STAGE_SWITCH):
                issues.append(Issue(IssueCode.BLOCK_HEAD_NOT_SWITCH,
                                    f"{rec.value} 位于第 2 条，但首条不是 switch"))

    memorial_at = [i for i, r in enumerate(recs) if r.stage == STAGE_MEMORIAL]
    if len(memorial_at) > 1:
        issues.append(Issue(IssueCode.BLOCK_MEMORIAL_REPEAT,
                            f"同块出现 {len(memorial_at)} 条 memorial（每块至多 1）"))
    if memorial_at:
        for i in range(memorial_at[0] + 1, n):
            if recs[i].stage in STAGE_FORBIDDEN_IN_MEMORIAL:
                issues.append(Issue(
                    IssueCode.BLOCK_MEMORIAL_FORBIDDEN_STAGE,
                    f"纪念区间内出现 {recs[i].stage}（第 {i + 1} 条）"))

    n_art = sum(1 for r in recs if r.stage == STAGE_ART)
    if n_art > 1:
        issues.append(Issue(IssueCode.BLOCK_ART_REPEAT,
                            f"同块出现 {n_art} 条 art（每块至多 1）"))

    # ---- 下面两条是**软**违规（只记录/打日志, 不打回）-------------------------
    # ⚠️ 分级只看 code（`ISSUE_SEVERITY`）——文案随便改，不会再像 2026-09-21 之前那样
    # 因为串里出现"必须块尾"之类字样就被静默升级成"整轮重发"（ARCH_REVIEW P0-3）。
    #
    # ① 配对缺失（2026-09-20 M1/M7）: 有 memorial 却没有 art ⇒ 生图 prompt 退回用
    #    memorial 的**转场句**当画面意向（真机那一章就是这样出的图）。
    #    为什么放这里而不是 `_build_record_boards` 里的 WARNING: **流式路径根本不走
    #    那个函数**（板由 `_feed` 交付）, 那条 WARNING 在生产主链上是死的。
    if memorial_at and n_art == 0:
        issues.append(Issue(
            IssueCode.BLOCK_ART_PAIR_MISSING,
            "含 memorial 但没有 art（画面意向缺失, 生图将退回用转场句当 prompt）"))

    # ② 章末压在纪念轮（2026-09-20 用户裁决）: *"硬要这样也行，不拒绝，但不建议
    #    ——建议不直接在 memo 结束，除非你真的认为这很有意境"* ⇒ 软记录, 供 grep 统计。
    if memorial_at and any(r.stage == STAGE_END for r in recs):
        issues.append(Issue(IssueCode.BLOCK_MEMORIAL_WITH_END,
                            "memorial 与 end 在同一轮（建议纪念之后再留一轮收尾）"))

    for g in sensei_groups(recs):
        if len(g) > MAX_SENSEI_RUN:
            issues.append(Issue(
                IssueCode.BLOCK_SENSEI_RUN_TOO_LONG,
                f"sensei 群过长（第 {g[0] + 1}~{g[-1] + 1} 条共 {len(g)}，上限 {MAX_SENSEI_RUN}）"))
    return issues


def check_board(records: Iterable[VnRecord]) -> list[Issue]:
    """**板级**校验（节点 2′, 2026-09-21）——只收**单板记录**就能判的规则。

    ## 为什么需要单独一条通道

    `check_block` 是**块级**（一次 LLM 调用的全部输出）。流式交付下板是逐块闭合、
    边到边发给玩家的, 块级校验只能在整块收完后才跑——那时板**已经在玩家屏上**,
    打回重发等于"同一段戏讲两遍"（LLM 不复现原文, 见 `docs/DESIGN_RESEND.md` §3）。
    所以能在**交付前**判的规则必须单独成一条通道。

    ## 单板可判（⇒ 能在交付前拦）

    · `stage:end`/`exit` 之后还有记录（必须块尾）
    · 同板出现多条 `memorial`（每板至多 1 条）
    · 板内 `memorial` 之后出现 `switch`（纪念区间内禁换场）

    ## 单板**判不了**（留块级 `check_block`；流式下只能是 advisory）

    · `art` 写了但整块没有 `memorial`（配对——`memorial` 可能在本块后段才出现）
    · `memorial` 与 `end` 同轮（跨板语义）
    · 空块 / 块首不是 `switch` / `art` 不在块首（需要整块视角）

    ⚠️ 本函数**全部**问题都是硬（板级闸按"非空即拦"处理）——分级同样走
    `ISSUE_SEVERITY`（`board.*` 码全 HARD），没有中文子串判定。
    """
    recs = tuple(records)
    issues: list[Issue] = []
    if not recs:
        return issues
    n = len(recs)
    # ① end/exit 之后不得再有记录（= 块尾规则的单板版）
    for i, rec in enumerate(recs):
        if rec.stage in STAGE_BLOCK_TAIL and i != n - 1:
            issues.append(Issue(IssueCode.BOARD_TAIL,
                                f"{rec.value} 必须块尾（板内第 {i + 1}/{n} 条）"))
    # ② 每板至多 1 条 memorial
    n_mem = sum(1 for r in recs if r.stage == STAGE_MEMORIAL)
    if n_mem > 1:
        issues.append(Issue(IssueCode.BOARD_MEMORIAL_REPEAT,
                            f"同板出现 {n_mem} 条 memorial（每板至多 1）"))
    # ③ 板内 memorial 之后禁 switch/art（纪念区间内禁换场）
    mem_at = next((i for i, r in enumerate(recs) if r.stage == STAGE_MEMORIAL), None)
    if mem_at is not None:
        for i in range(mem_at + 1, n):
            if recs[i].stage in STAGE_FORBIDDEN_IN_MEMORIAL:
                issues.append(Issue(
                    IssueCode.BOARD_MEMORIAL_FORBIDDEN_STAGE,
                    f"纪念区间内出现 {recs[i].stage}（板内第 {i + 1} 条）"))
    return issues
