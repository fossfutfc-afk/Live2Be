# -*- coding: utf-8 -*-
"""VN 记录流契约（记录流 v2）——"行 → 记录"解析 + 群/位置校验。

设计: `docs/DESIGN_VN_UPGRADE.md` §2（文法）/ §6（群与推进）/ §8（与 registry 的关系）。
本模块只做**行级解析**与**块内结构校验**；配额、状态机、标注门控是引擎的活。

记录形状（每条恰好含 `character` 或 `stage` 之一 + `text`）::

    {"character": "haruka",   "text": "……老师，你、你来了。"}
    {"character": "sensei",   "text": "是我来晚了。"}
    {"character": "narrator", "text": "（她低下头。）"}
    {"stage": "switch",   "text": "深夜的杂草屋"}
    {"stage": "art",      "text": "她终于把话说出口的一刻：抬头、眼中有泪光"}
    {"stage": "memorial", "text": "（她抬起头，朝我笑了一下。）"}
    {"stage": "end",      "text": "（夜风停了。）"}

**sensei 群**（规范 8）：最长连续 `sensei` 段 = 一个群，长度 1~3；
run=1 单选项、run=2~3 多选项；群一律弹选项（不做"自动播的剧本台词"）。

容错纪律（宁缺勿错 + 局部错误隔离；实测依据见设计文档 §14）：
    ① 代码围栏行（```…）→ 静默丢弃；
    ② 数组行（LLM 手痒包了一层）→ 拍平成多条记录；
    ③ 末行悬空（字符串未闭合）→ 追加 `"}` 重试一次（EOF 处无歧义）；
    ④ 其余解析失败 / 形状违规 → 丢行 + 记 `ParseDiag`（**不抛异常**，由上层计数与反馈）。
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# 文法常量（单一真源：schema 渲染 / 解析器 / 引擎校验共用）
# ---------------------------------------------------------------------------

KIND_CHARACTER = "character"
KIND_STAGE = "stage"
KINDS = (KIND_CHARACTER, KIND_STAGE)

#: `character` 的保留取值（其余一律视为角色 id）
CHARACTER_NARRATOR = "narrator"
CHARACTER_SENSEI = "sensei"
CHARACTER_SPECIALS = (CHARACTER_NARRATOR, CHARACTER_SENSEI)

STAGE_SWITCH = "switch"
STAGE_ART = "art"
STAGE_MEMORIAL = "memorial"
STAGE_END = "end"
STAGE_EXIT = "exit"
STAGE_VALUES = (STAGE_SWITCH, STAGE_ART, STAGE_MEMORIAL, STAGE_END, STAGE_EXIT)

#: 位置约束
STAGE_BLOCK_HEAD = (STAGE_ART,)                    # 必须块首（或紧随开章 switch）
STAGE_BLOCK_TAIL = (STAGE_END, STAGE_EXIT)         # 必须块尾（其后不得再有记录）
STAGE_FORBIDDEN_IN_MEMORIAL = (STAGE_SWITCH, STAGE_ART)   # 纪念区间内禁止（换场 / 二次预告）
#: `text` 可省略的唯一取值
TEXT_OPTIONAL_STAGES = (STAGE_EXIT,)

#: sensei 群上限（最长连续段）
MAX_SENSEI_RUN = 3
#: 末行悬空修复候选（依次尝试）
_TAIL_REPAIRS = ('"}', "}")


# ---------------------------------------------------------------------------
# 数据对象
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VnRecord:
    """一条记录（解析成功的最小单元）。"""

    kind: str                 # KIND_CHARACTER | KIND_STAGE
    value: str                # 角色 id / sensei / narrator ｜ stage 取值
    text: str
    line_no: int = 0

    @property
    def is_sensei(self) -> bool:
        return self.kind == KIND_CHARACTER and self.value == CHARACTER_SENSEI

    @property
    def is_narration(self) -> bool:
        return self.kind == KIND_CHARACTER and self.value == CHARACTER_NARRATOR

    @property
    def is_stage(self) -> bool:
        return self.kind == KIND_STAGE

    @property
    def stage(self) -> str:
        """stage 记录取值；非 stage 记录返回空串。"""
        return self.value if self.kind == KIND_STAGE else ""

    def to_dict(self) -> dict[str, str]:
        """回写为 LLM 可见 wire 形状（落库 / 回放 / 历史渲染共用）。"""
        return {self.kind: self.value, "text": self.text}


@dataclass(frozen=True)
class ParseDiag:
    """一条解析诊断（dropped=True 表示该行被丢弃）。"""

    line_no: int
    raw: str
    error: str
    dropped: bool = True

    def __str__(self) -> str:                        # pragma: no cover - 展示用
        tag = "DROP" if self.dropped else "NOTE"
        return f"[line {self.line_no}][{tag}] {self.error} | {self.raw[:80]}"


@dataclass(frozen=True)
class ParseResult:
    """一次流式解析的结果（记录 + 诊断）。"""

    records: tuple[VnRecord, ...] = ()
    diags: tuple[ParseDiag, ...] = ()

    @property
    def dropped(self) -> tuple[ParseDiag, ...]:
        return tuple(d for d in self.diags if d.dropped)

    @property
    def notes(self) -> tuple[ParseDiag, ...]:
        return tuple(d for d in self.diags if not d.dropped)

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(d.error for d in self.dropped)

    def texts(self, value: str | None = None) -> list[str]:
        """取文本（value=None → 全部；否则按 value 过滤）。"""
        return [r.text for r in self.records if value is None or r.value == value]


# ---------------------------------------------------------------------------
# 行解析（P0-2）
# ---------------------------------------------------------------------------


def _record_from_obj(obj: Any) -> tuple[VnRecord | None, str]:
    """dict → VnRecord；形状违规返回 (None, 原因)。"""
    if not isinstance(obj, dict):
        return None, f"记录必须是 JSON 对象（实得 {type(obj).__name__}）"
    keys = set(obj)
    has_char, has_stage = KIND_CHARACTER in keys, KIND_STAGE in keys
    if has_char and has_stage:
        return None, "记录同时含 character 与 stage（必须恰好其一）"
    if not (has_char or has_stage):
        return None, "记录既无 character 也无 stage"
    kind = KIND_CHARACTER if has_char else KIND_STAGE
    value = obj.get(kind)
    if not isinstance(value, str) or not value.strip():
        return None, f"{kind} 必须是非空字符串（实得 {value!r}）"
    value = value.strip()
    if kind == KIND_STAGE and value not in STAGE_VALUES:
        return None, f"未知 stage 值 {value!r}（合法: {'/'.join(STAGE_VALUES)}）"

    text = obj.get("text", "")
    if text is None:
        text = ""
    if not isinstance(text, str):
        return None, f"text 必须是字符串（实得 {type(text).__name__}）"
    text = text.strip()
    if not text and value not in TEXT_OPTIONAL_STAGES:
        return None, f"{kind}={value} 的 text 不能为空"
    return VnRecord(kind=kind, value=value, text=text), ""


def _tail_repair(line: str) -> Any | None:
    """末行悬空修复：补 `"}` / `}`（EOF 处无歧义）。失败返回 None。"""
    if line.endswith("}"):
        return None
    for suffix in _TAIL_REPAIRS:
        try:
            return json.loads(line + suffix)
        except json.JSONDecodeError:
            continue
    return None


def _parse_line_multi(line: str, line_no: int) -> tuple[list[VnRecord], ParseDiag | None]:
    """一行 → 记录列表（数组行拍平）+ 诊断。围栏/空行 → 空列表。"""
    text = (line or "").strip().lstrip("\ufeff")
    if not text or text.startswith("```"):
        return [], None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        repaired = _tail_repair(text)
        if repaired is None:
            return [], ParseDiag(line_no, text, f"JSON 解析失败: {e.msg}")
        rec, why = _record_from_obj(repaired)
        if rec is None:
            return [], ParseDiag(line_no, text, f"JSON 解析失败: {e.msg}（修复后仍不合法: {why}）")
        return [rec], ParseDiag(line_no, text, '末行悬空 → 补 `"}` 救回', dropped=False)

    if isinstance(obj, list):                     # 数组行 → 拍平
        out: list[VnRecord] = []
        for item in obj:
            rec, why = _record_from_obj(item)
            if rec is not None:
                out.append(rec)
        if not out:
            return [], ParseDiag(line_no, text, "数组行内无合法记录")
        note = ParseDiag(line_no, text, f"数组行 → 拍平 {len(out)} 条", dropped=False)
        return out, note

    rec, why = _record_from_obj(obj)
    if rec is None:
        return [], ParseDiag(line_no, text, why)
    extra = set(obj) - {KIND_CHARACTER, KIND_STAGE, "text"}
    if extra:
        return [rec], ParseDiag(line_no, text, f"多余字段已丢弃: {sorted(extra)}", dropped=False)
    return [rec], None


def parse_line(raw: str, line_no: int = 0) -> tuple[VnRecord | None, ParseDiag | None]:
    """解析**一行**（返回首个记录）。批量请用 `parse_stream`（会拍平数组行）。"""
    recs, diag = _parse_line_multi(raw, line_no)
    first = recs[0] if recs else None
    if first is not None and line_no:
        first = VnRecord(first.kind, first.value, first.text, line_no)
    return first, diag


def parse_stream(source: str | Iterable[str]) -> ParseResult:
    """批量解析（整块文本或行迭代器）——数组行拍平、坏行丢弃并记账。"""
    lines = source.splitlines() if isinstance(source, str) else list(source)
    records: list[VnRecord] = []
    diags: list[ParseDiag] = []
    for idx, raw in enumerate(lines, start=1):
        recs, diag = _parse_line_multi(raw, idx)
        records.extend(VnRecord(r.kind, r.value, r.text, idx) for r in recs)
        if diag is not None:
            diags.append(diag)
    return ParseResult(tuple(records), tuple(diags))


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


def check_block(records: Iterable[VnRecord]) -> list[str]:
    """块内结构校验（返回问题描述；空 = 合规）。**不做配额/状态判定**。"""
    recs = list(records)
    if not recs:
        return ["空块：没有任何记录"]
    issues: list[str] = []
    n = len(recs)

    for i, rec in enumerate(recs):
        if not rec.is_stage:
            continue
        if rec.value in STAGE_BLOCK_TAIL and i != n - 1:
            issues.append(f"{rec.value} 必须块尾（实现在第 {i + 1}/{n} 条）")
        if rec.value in STAGE_BLOCK_HEAD and i not in (0, 1):
            issues.append(f"{rec.value} 必须块首（实现在第 {i + 1} 条）")
        if rec.value in STAGE_BLOCK_HEAD and i == 1:
            head = recs[0]
            if not (head.is_stage and head.value == STAGE_SWITCH):
                issues.append(f"{rec.value} 位于第 2 条，但首条不是 switch")

    memorial_at = [i for i, r in enumerate(recs) if r.stage == STAGE_MEMORIAL]
    if len(memorial_at) > 1:
        issues.append(f"同块出现 {len(memorial_at)} 条 memorial（每块至多 1）")
    if memorial_at:
        for i in range(memorial_at[0] + 1, n):
            if recs[i].stage in STAGE_FORBIDDEN_IN_MEMORIAL:
                issues.append(f"纪念区间内出现 {recs[i].stage}（第 {i + 1} 条）")

    n_art = sum(1 for r in recs if r.stage == STAGE_ART)
    if n_art > 1:
        issues.append(f"同块出现 {n_art} 条 art（每块至多 1）")

    for g in sensei_groups(recs):
        if len(g) > MAX_SENSEI_RUN:
            issues.append(
                f"sensei 群过长（第 {g[0] + 1}~{g[-1] + 1} 条共 {len(g)}，上限 {MAX_SENSEI_RUN}）")
    return issues
