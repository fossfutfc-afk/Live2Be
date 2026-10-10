# -*- coding: utf-8 -*-
"""MMT **回合级校验**（⑥-2c, 2026-09-25）——码表 + 组合约束。

设计: `docs/DESIGN_STREAM_CONTRACT.md` §1（六条）/ §4（兜底分级）/
§10.2 B4·B5（码表各自声明 · 两段式校验）。

## 这一层判什么（**别越界**）

判**组合**（单行看不出来的）与 registry **不管**的字段：

· `mmt.empty-turn`        本轮一行都没有（硬）
· `mmt.exclusive-violation` 三个独占动作被破坏（硬）——
  `mmt_inspect_character` 是**静默推理轮**（整轮只有它一条行）；
  `mmt_trigger_bond_story` 是模式切换（操作行里只有它，见面的话写在它前面的消息行里）；
  ⭐ `mmt_look` 是 **trigger 式**（2026-10-08 用户裁）：**唯一操作行 + 放在最后一行**——
  她想先说一句"唔……我找找看"再翻是自然的（`inspect` 那款"整轮只有它一条行"会逼她
  中断），所以话可以写在它**前面**；而它**后面**不许再有行（块尾执行 + 回灌 ⇒
  写在后面的话是在没看到结果时写的 —— 这一条**只教不判**，见下面的分支注释）
· `mmt.control-invalid`   操作行字段不合**且引擎修不了**（硬）——
  ⭐ 实测（⑥-2b）：`chapter_title` 的"必填 3-16 字"**只写在提示词里**，
  `parse_mmt_trigger_bond_story` 只校验"是字符串"（空标题放行）⇒ 这条得在这儿补
· `mmt.line-bad`          坏行被丢（**软**：内容行丢行只是少说一句，记账即可）

**不判**：动作名是否存在、payload 各字段的类型 —— 那是 `registry.parse` 的活
（`contract/registry.py`，硬错误）。两处都判 = 两处会漂。

⚠️ `mmt.control-unexecuted`（软）**由引擎挂**（⑥-2d）：它要"已交付 / 执行失败"的
上下文，check 这层看不到——码先在这里声明，免得 d 那天临时加码漏声明。
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from contract.issues import Issue, IssueSeverity, declare_severity
from contract.streams import ParseDiag
from core.mmt.mmt_lines import KIND_ACTION, MmtLine

#: `chapter_title` 长度（schema 文案写的 3-16 字；registry 不校验，见模块 docstring）
TITLE_MIN = 3
TITLE_MAX = 16

#: 触发动作名（模式切换；判复合约束用）
ACTION_TRIGGER = "mmt_trigger_bond_story"
#: 静默推理动作名（整轮只有它一条行）
ACTION_INSPECT = "mmt_inspect_character"
#: ⭐ 翻阅自己的记忆（2026-10-08）—— 与 `inspect` 同族（静默轮 + 查到的东西**回灌**,
#: 她带着资料接着把这一轮说完）, ⚠️ 但**独占口径不同款**: 见下面 `exclusive-violation`。
ACTION_LOOK = "mmt_look"

#: ⭐ **查询族**（静默轮 + 回灌 + 继续这一轮）—— `engine._run_lines` 判定 `need_more`
#: 时读它。⛔ `trigger` **不在内**: 它是模式切换, 不是"查完接着说"。
#: 加一个查询动作 = 加进这个集合 + 进 `WHOLE_TURN_ACTIONS`（两处, 见各自注释）。
QUERY_ACTIONS: frozenset[str] = frozenset({ACTION_INSPECT, ACTION_LOOK})

#: 修不了的**操作行**里，哪些可以"丢行"（软）——判据 = **丢掉之后模型会不会带着错的前提继续**
#: · `mmt_send_media`：只是图没发出去（"话说了图没发"完全可接受）⇒ 丢行 + 下一轮注记；
#: · 其余（inspect / trigger）：会让模型以为"查过了""进剧情了" ⇒ **必须回灌**（硬）。
DROPPABLE_ACTIONS: frozenset[str] = frozenset({"mmt_send_media"})

#: **必须整轮可见才能办理的动作**（⑥-3a 流式交付的暂存集）。
#:
#: 判据 = "这一行的合法性/后果**取决于同一轮里还有没有别的行**"：
#: · `mmt_inspect_character` / `mmt_look` / `mmt_trigger_bond_story` 都是**独占**行——
#:   单看自己永远合法，混排才违规（见下面的 `mmt.exclusive-violation`）。
#: ⇒ 流式下内容行（`text` / `mmt_send_media`）到达即交付，这几条**攒到块尾**
#: 等整轮写完再判/执行——否则"独占被破坏"这类硬问题会被流式绕过，而且
#: `trigger` 一旦跑出去就收不回（模式切换）。
#: ⚠️ 新增动作时想清楚放哪一边：独占/有整轮前置条件的进这里，纯内容行不用。
WHOLE_TURN_ACTIONS: frozenset[str] = frozenset({ACTION_TRIGGER, ACTION_INSPECT, ACTION_LOOK})


class MmtIssueCode(str, Enum):
    """MMT 的问题**机器码**（稳定标识：测试断言 / 日志 grep / 下一轮纠偏都认它）。

    命名 = `mmt.<规则>`。
    """

    # ---- 硬（本回合要处理：回灌 / 失败）----
    EMPTY_TURN = "mmt.empty-turn"
    EXCLUSIVE_VIOLATION = "mmt.exclusive-violation"
    CONTROL_INVALID = "mmt.control-invalid"
    # ---- 软（只记录 / 下一轮纠偏）----
    LINE_BAD = "mmt.line-bad"
    CONTROL_UNEXECUTED = "mmt.control-unexecuted"


#: **MMT 的软硬真源**（机制在 `contract.issues`；码与严重度是 MMT 自己的）。
#:
#: 判据 = "这一条会不会让**模型以为自己做到了**"：
#: · 硬 = 会让模型带着错的前提继续（查资料没成 / 没切成剧情 / 整轮空）⇒ 必须回灌或失败；
#: · 软 = 只是少说一句 / 图没发出去（内容行无副作用）⇒ 记账 + 下一轮纠偏就够。
ISSUE_SEVERITY: dict[MmtIssueCode, IssueSeverity] = {
    MmtIssueCode.EMPTY_TURN: IssueSeverity.HARD,
    MmtIssueCode.EXCLUSIVE_VIOLATION: IssueSeverity.HARD,
    MmtIssueCode.CONTROL_INVALID: IssueSeverity.HARD,
    MmtIssueCode.LINE_BAD: IssueSeverity.SOFT,
    MmtIssueCode.CONTROL_UNEXECUTED: IssueSeverity.SOFT,
}

declare_severity(ISSUE_SEVERITY)      # 登记给共用层（`Issue.severity` 查它）


def check_turn(lines: Iterable[MmtLine], diags: Iterable[ParseDiag] = ()) -> list[Issue]:
    """一轮（= 一次 LLM 调用）的行清单 → `Issue` 清单（空 = 合规）。

    Args:
        lines: 解析成功的行（顺序 = 输出的行序）。
        diags: 行解析的诊断（`ParseDiag`；`dropped=True` 的进 `line-bad` 记账）。

    分级由 `ISSUE_SEVERITY` 决定（与 message 文案无关）。
    """
    rows = list(lines)
    issues: list[Issue] = []

    dropped = [d for d in diags if d.dropped]
    if dropped:
        head = "; ".join(f"第 {d.line_no} 行: {d.error}" for d in dropped[:3])
        more = f"（共 {len(dropped)} 行）" if len(dropped) > 1 else ""
        issues.append(Issue(MmtIssueCode.LINE_BAD, f"有行被丢弃{more}: {head}"))

    if not rows:
        issues.append(Issue(MmtIssueCode.EMPTY_TURN, "本轮没有任何行（至少要说话或做一件事）"))
        return issues

    actions = [ln for ln in rows if ln.kind == KIND_ACTION]
    n_text = sum(1 for ln in rows if ln.is_text)
    n_notice = sum(1 for ln in rows if ln.is_noticed)
    # ⭐ **想起行不计入"行数"**（N5b）: 它是**账目**不是内容 —— 见下面的独占约束。
    shown = [ln for ln in rows if not ln.is_noticed]

    # ---- 独占约束（组合级：单行看不出来）--------------------------------
    # ⚠️ **"整轮只有它一条行"里的"行" = 内容行 + 操作行, 不含想起行**（N5b 口径）:
    #   那条规则的目的是"静默轮**一句话都不该上屏**"（内容是问题）, 而想起行
    #   不上屏、零成本、不触发任何调用。把它算进去只会产出**假硬问题**
    #   ⇒（`inspect` 混排 ⇒ 整轮回灌重发）白跑一次续写。
    #   ⇒ 她和 `inspect` 同轮顺手记一笔, 是允许的（账照落, 见 `engine._log_notices`）。
    inspects = [a for a in actions if a.action == ACTION_INSPECT]
    looks = [a for a in actions if a.action == ACTION_LOOK]
    triggers = [a for a in actions if a.action == ACTION_TRIGGER]
    if inspects and (len(shown) > 1 or len(inspects) > 1):
        issues.append(Issue(
            MmtIssueCode.EXCLUSIVE_VIOLATION,
            f"{ACTION_INSPECT} 是静默推理轮——那一轮只能有它一条行"
            f"（实得 {len(shown)} 行: {n_text} 条消息 + {len(actions)} 条操作"
            + (f" + {n_notice} 条想起" if n_notice else "") + "）"))
    if looks and len(actions) > 1:
        # ⭐ **trigger 式, 不是 inspect 式**（用户 2026-10-08 裁）:
        # `look` 是"她想用起某件旧事"才做的一件事 —— 先说一句"唔……我找找看"再翻
        # 完全自然; 照 `inspect` 判"整轮只有它一条行"会**逼她中断**（话与翻二选一）。
        # ⇒ 只要求**唯一操作行**（同 `trigger`）, 话写在它前面。
        # ⚠️ **"放在最后一行"只教不判**: 它块尾执行 + 回灌 ⇒ 写在它后面的话是在没看到
        #    结果时写的（契约与规则书都建议放最后）; 但那是**写法建议**, 判成硬问题
        #    只会白跑一次续写。⚠️ 也别改成 `len(shown)`: `shown` 含消息行, 会把
        #    "先说一句再翻"重新判成违规（改回旧口径就是这么改的）。
        others = [a.action for a in actions if a.action != ACTION_LOOK]
        issues.append(Issue(
            MmtIssueCode.EXCLUSIVE_VIOLATION,
            f"{ACTION_LOOK} 必须是那一轮**唯一的操作行**"
            f"（另有: {'/'.join(others) or '它自己重复了'}）"
            f"——想说的话请写在它**前面**的消息行里（它放在那一轮的最后一行）"))
    if triggers and (len(actions) > 1 or len(triggers) > 1):
        others = [a.action for a in actions if a.action != ACTION_TRIGGER]
        issues.append(Issue(
            MmtIssueCode.EXCLUSIVE_VIOLATION,
            f"{ACTION_TRIGGER} 必须是唯一操作行（另有: {'/'.join(others) or '它自己重复了'}）"
            f"——见面的话请写在它前面的消息行里"))

    # ---- 引擎修不了的字段问题（⭐ chapter_title: registry 不校验）---------
    for a in triggers:
        title = str(a.payload.get("chapter_title") or "").strip()
        if not (TITLE_MIN <= len(title) <= TITLE_MAX):
            issues.append(Issue(
                MmtIssueCode.CONTROL_INVALID,
                f"chapter_title 必须是 {TITLE_MIN}-{TITLE_MAX} 字"
                f"（实得 {len(title)} 字: {title!r}）"))
    return issues
