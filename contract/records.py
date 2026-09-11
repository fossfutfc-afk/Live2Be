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

容错纪律（宁缺勿错 + 局部错误隔离；实测依据见设计文档 §15 附录）：
    ① 代码围栏行（```…）→ 静默丢弃；
    ② 数组行（LLM 手痒包了一层）→ 拍平成多条记录；
    ③ 末行悬空（字符串未闭合）→ 追加 `"}` 重试一次（EOF 处无歧义）；
    ④ 未转义半角引号 → **辅助转义**（按文法形状确定性重建, 见 `_rescape_repair`）；
    ⑤ 其余解析失败 / 形状违规 → 丢行 + 记 `ParseDiag`（**不抛异常**，由上层计数与反馈）。
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
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
#: `text` 可省略的取值（2026-09-10 用户裁决: `end` 的 text 是**收尾字段**而非台词,
#: 留空 = 直接黑屏收尾——"角色最后一句 + switch + end('')"是常用收尾组合）
TEXT_OPTIONAL_STAGES = (STAGE_END, STAGE_EXIT)

#: sensei 群上限（最长连续段）
MAX_SENSEI_RUN = 3
#: 末行悬空修复候选（依次尝试）
_TAIL_REPAIRS = ('"}', "}")
#: 辅助转义用：判别符前缀（`text` 是最后字段，我们 few-shot 的形状）
_RECORD_HEAD_RE = re.compile(
    r'^\{\s*"(?P<kind>character|stage)"\s*:\s*"(?P<value>[^"]*)"\s*,')
#: 辅助转义用：`text` 字段的起始（取判别符之后的**第一个**，正文里的同名子串不干扰）
_TEXT_FIELD_RE = re.compile(r'"text"\s*:\s*"')
#: 辅助转义护栏：疑似 JSON 结构残留（多记录粘在一行 / 记录重启）→ 宁可丢行
_JSON_ISH_RE = re.compile(r'\}\s*\{|"\s*:\s*"|"\s*,\s*"')


# ---------------------------------------------------------------------------
# 数据对象
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VnRecord:
    """一条记录（解析成功的最小单元）。

    `line_no` 是**解析期定位信息**（诊断/回放定位用），不参与相等性——记录的
    身份 = (kind, value, text)，故 payload 往返比较稳定（P0-6 回放逐字节同形）。
    """

    kind: str                 # KIND_CHARACTER | KIND_STAGE
    value: str                # 角色 id / sensei / narrator ｜ stage 取值
    text: str
    line_no: int = field(default=0, compare=False)

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


def _rescape_repair(line: str) -> tuple[VnRecord | None, str]:
    """辅助转义：`text` 尾部含**未转义半角引号**时，切出文本段重新转义后重建。

    这不是通用 JSON 修复，而是**利用我们文法的确定性形状**：`text` 恒为最后一个
    字段、正文恒在行尾，所以前缀可由正则切出，剩下的一律是文本。步骤：
    判别符前缀 + `"text": "` 定界 → 去掉行尾可选的 `}` / `"` → 直接用 dict 重建
    对象走正常校验（引号已在数据层，无需再拼 JSON 字符串）。
    不适用/救不回 → (None, "")，交回原有诊断。
    """
    m = _RECORD_HEAD_RE.match(line)
    if not m:
        return None, ""
    field = _TEXT_FIELD_RE.search(line, m.end())
    if field is None:
        return None, ""
    tail = line[field.end():].rstrip()
    if tail.endswith("}"):
        tail = tail[:-1].rstrip()
    if tail.endswith('"'):
        tail = tail[:-1]
    if '"' not in tail or not tail.strip():
        return None, ""                       # 无未转义引号 → 不属于本类错误
    if _JSON_ISH_RE.search(tail):
        # 结构残留（如模型把两条记录粘在一行 `..."x"}{"character":...`）：吞下去会
        # 把 JSON 碎片当正文 → 宁可丢行（宁缺勿错；护栏失效时最多退回旧行为）
        return None, ""
    rec, _why = _record_from_obj({m.group("kind"): m.group("value"), "text": tail})
    if rec is None:
        return None, ""
    note = f"text 内 {tail.count(chr(34))} 处未转义引号 → 辅助转义救回"
    if line[m.end():field.start()].strip():
        note += "（中间多余字段已丢弃）"
    return rec, note


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
        rec, note = _rescape_repair(text)
        if rec is not None:
            return [rec], ParseDiag(line_no, text, note, dropped=False)
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


# ---------------------------------------------------------------------------
# 块载体（P0-4）：记录数组 + 群 + 位置元数据 + 两种出口（落库 dict / 渲染文本）
# ---------------------------------------------------------------------------

#: 说话人显示名兜底（引擎可用 names 覆盖；角色 id → 显示名）
SPEAKER_SENSEI_LABEL = "老师"
DEFAULT_SPEAKER_NAMES: dict[str, str] = {CHARACTER_SENSEI: SPEAKER_SENSEI_LABEL}


def _speaker_key(value: str) -> str:
    """说话人比较键：去空白/下划线/连字符 + 小写（`伊草 遥香` ≡ `伊草遥香`）。"""
    return re.sub(r"[\s_\-·]+", "", value or "").lower()


def is_main_speaker(value: str, main_id: str,
                    aliases: Iterable[str] = ()) -> bool:
    """该说话人取值是否算"主角自己"（id / 别名 / 显示名）。

    与 `normalize_main_character` **同一判据**（同一比较键）, 供消费方复用——
    emo 标注层据此把"其他角色（客串/NPC）的台词"挑出来（无差分可切, 不送标注;
    见 `BondStoryEngine._annotate_text_group`）。空值（旁白无 speaker 字段）不算
    主角——由调用方自行判定。
    """
    key = _speaker_key(value)
    if not key:
        return False
    main = (main_id or "").strip()
    if not main:
        return False
    if key == _speaker_key(main):
        return True
    return key in {_speaker_key(a) for a in aliases if str(a).strip()}


def normalize_main_character(records: Iterable[VnRecord], main_id: str,
                             aliases: Iterable[str] = ()) -> tuple[tuple[VnRecord, ...], tuple[str, ...]]:
    """把主角的别名写法归一到 `main_id`（决策 #21 引擎侧）。

    单人模式下写作 `character` 值的合法说话人只有三种: 主角、`narrator`、`sensei`。
    模型偶尔会用显示名/昵称（`伊草 遥香` / `遥香`）——**归一兜底**而不是丢行或另起
    一个"角色"（未来 NPC table 会取代这条兜底）。

    Returns:
        (归一后的记录, NOTE 列表)——没发生改名时 NOTE 为空。
    """
    main = (main_id or "").strip()
    if not main:
        return tuple(records), ()
    out: list[VnRecord] = []
    notes: list[str] = []
    for rec in records:
        if rec.kind == KIND_CHARACTER and rec.value not in (CHARACTER_NARRATOR,
                                                            CHARACTER_SENSEI,
                                                            main):
            if is_main_speaker(rec.value, main, aliases):
                notes.append(f"[NOTE line {rec.line_no}] 说话人 {rec.value!r} → {main}（别名归一）")
                out.append(VnRecord(rec.kind, main, rec.text, rec.line_no))
                continue
            # 单人模式下"不认识的名字"也归主角（防丢台词）；NOTE 记账以便观测
            notes.append(f"[NOTE line {rec.line_no}] 未知说话人 {rec.value!r} → {main}"
                         "（单人模式归一；未来 NPC table 细分）")
            out.append(VnRecord(rec.kind, main, rec.text, rec.line_no))
            continue
        out.append(rec)
    return tuple(out), tuple(notes)


@dataclass(frozen=True)
class VnBlock:
    """一个**块**（= 引擎最小提交单元：一次 LLM 回合产出的全部记录）。

    纯数据载体——解析校验（`check_block`）只出"问题清单"，**不拦不修**；
    配额/状态判定（章级 memorial ≤1、槽频率等）归引擎（见 DESIGN §4 分工）。
    """

    records: tuple[VnRecord, ...] = ()
    notes: tuple[str, ...] = ()       # 解析期 NOTE（修复/拍平/多余字段）——可观测，不进 LLM 上下文
    issues: tuple[str, ...] = ()      # 块内结构校验结果（空 = 合规）

    # --- 构造 --------------------------------------------------------------
    @classmethod
    def from_records(cls, records: Iterable[VnRecord], *, notes: Iterable[str] = (),
                     validate: bool = True) -> VnBlock:
        recs = tuple(records)
        return cls(recs, tuple(notes), tuple(check_block(recs)) if validate else ())

    @classmethod
    def from_text(cls, text: str, *, validate: bool = True, main_id: str = "",
                  aliases: Iterable[str] = ()) -> VnBlock:
        """整块文本（LLM 原始输出）→ 块；坏行不阻断，NOTE/DROP 全部记账。

        `main_id`/`aliases` 非空时顺带做**主角别名归一**（决策 #21）。
        """
        res = parse_stream(text)
        notes = [f"[NOTE line {d.line_no}] {d.error}" for d in res.notes]
        notes += [f"[DROP line {d.line_no}] {d.error}" for d in res.dropped]
        recs, alias_notes = normalize_main_character(res.records, main_id, aliases)
        return cls.from_records(recs, notes=[*notes, *alias_notes], validate=validate)

    @classmethod
    def from_dict(cls, data: Any) -> VnBlock:
        """落库 payload → 块（回放/存档）。旧契约 payload 显式拒绝而非猜。"""
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if "records" not in data:
                legacy = sorted(set(data) & {"paragraphs", "choices", "branches", "scene",
                                             "text", "emotions"})
                hint = f"（疑似旧契约字段 {legacy}）" if legacy else ""
                raise ValueError(f"payload 缺少 records 字段{hint}——旧档冻结策略见 §3/§11 P0-6")
            items = data.get("records") or []
        else:
            raise ValueError(f"payload 必须是 dict 或 list（实得 {type(data).__name__}）")
        records: list[VnRecord] = []
        for item in items:
            if isinstance(item, VnRecord):
                records.append(item)
                continue
            rec, why = _record_from_obj(item)
            if rec is None:
                raise ValueError(f"payload 内含非法记录: {why}（{item!r}）")
            records.append(rec)
        raw_notes = data.get("notes", []) if isinstance(data, dict) else []
        return cls.from_records(records, notes=[str(x) for x in raw_notes])

    # --- 派生视图 ----------------------------------------------------------
    @property
    def groups(self) -> tuple[tuple[int, ...], ...]:
        """sensei 群（连续 `sensei` 段的下标组）——run=1 单选项 / run≥2 多选项。"""
        return tuple(tuple(g) for g in sensei_groups(self.records))

    @property
    def group_texts(self) -> tuple[tuple[str, ...], ...]:
        """各群的候选台词（= 交互槽的选项文本）。"""
        recs = self.records
        return tuple(tuple(recs[i].text for i in g) for g in self.groups)

    def _first_stage(self, value: str) -> int | None:
        for i, rec in enumerate(self.records):
            if rec.stage == value:
                return i
        return None

    @property
    def switch_at(self) -> int | None:
        return self._first_stage(STAGE_SWITCH)

    @property
    def art_at(self) -> int | None:
        return self._first_stage(STAGE_ART)

    @property
    def memorial_at(self) -> int | None:
        return self._first_stage(STAGE_MEMORIAL)

    @property
    def end_at(self) -> int | None:
        return self._first_stage(STAGE_END)

    @property
    def exit_at(self) -> int | None:
        return self._first_stage(STAGE_EXIT)

    @property
    def has_choices(self) -> bool:
        return bool(self.groups)

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def before(self, index: int | None) -> tuple[VnRecord, ...]:
        """`index` 之前的记录（index=None → 全部）——如纪念闸门前的可渲染前缀。"""
        return self.records if index is None else self.records[:index]

    def after(self, index: int | None) -> tuple[VnRecord, ...]:
        """`index` 之后的记录（不含 index）——如纪念区间本体。"""
        return () if index is None else self.records[index + 1:]

    # --- 出口 --------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """落库 / 回放 payload（唯一真源形态）。"""
        data: dict[str, Any] = {"records": [r.to_dict() for r in self.records]}
        if self.notes:
            data["notes"] = list(self.notes)
        return data

    def render_text(self, names: Mapping[str, str] | None = None, *,
                    speaker: bool = True) -> str:
        """**最小形态**渲染（块级——诊断/日志用）；板级（含槽与裁决）见 `render_records`。

        - 角色/老师：`显示名：正文`（names 覆盖，默认 sensei→老师，角色 id→id）
        - 旁白：正文（不加前缀）
        - stage：`switch`/`memorial`/`end` 回显自己的文本；`art` 是**不可见声明**、
          `exit` 无文本 → 跳过（视觉键不进 LLM 上下文，见 §4）
        """
        return render_records(self.records, names=names, speaker=speaker)


#: 不算"裁决"的占位输入（渲染时跳过——与旧渲染函数同语义）
NON_PICKS = ("（继续）",)


def materialize_pick(records: Iterable[Any], picked: str) -> tuple[VnRecord, ...]:
    """**裁决物化**（P0-5）: 被选中的候选 → 群里的一条 `sensei` 记录，其余候选消失。

    位置的语义: 老师那句就落在他原本开口的地方（群首位），其后的角色反应顺序不变。
    找不到匹配候选 → 用第一个群; 整块无群 → 追加到末尾（CLI 自由文本兜底）。
    这是回录与回放**共用的唯一变换**（live 与 resume 同形靠它成立）。
    """
    picked = (picked or "").strip()
    recs = _coerce_records(records)
    if not picked:
        return tuple(recs)
    groups = sensei_groups(recs)
    target: list[int] | None = None
    for g in groups:
        if any(recs[i].text.strip() == picked for i in g):
            target = g
            break
    if target is None and groups:
        target = groups[0]
    line = VnRecord(KIND_CHARACTER, CHARACTER_SENSEI, picked)
    if target is None:
        return tuple(recs) + (line,)
    return tuple(recs[:target[0]] + [line] + recs[target[-1] + 1:])


def _coerce_records(records: Iterable[Any]) -> list[VnRecord]:
    """记录容器宽容化: 接受 `VnRecord` 或 wire dict（payload 回放走后者）。"""
    out: list[VnRecord] = []
    for r in records:
        if isinstance(r, VnRecord):
            out.append(r)
            continue
        if isinstance(r, dict):
            rec, _why = _record_from_obj(r)
            if rec is not None:
                out.append(rec)
    return out


def render_records(records: Iterable[Any], *, choices: Iterable[str] = (),                   picked: str = "", names: Mapping[str, str] | None = None,
                   speaker: bool = True) -> str:
    """记录流 → 叙事文本（**历史/回放唯一渲染源**，P0-5）。

    - 记录按序出: 角色/老师 → `说话人：正文`（sensei→老师; 角色默认回落到 id，
      由调用方用 `names` 覆盖）; 旁白 → 正文; `switch`/`memorial`/`end` → 自己的文本;
      `art`/`exit` 与空 text → 跳过;
    - **群内候选（`choices` 里的 sensei 记录）不出现**——未选台词永不进任何视图/上下文;
    - `picked` 非空且不是 `（继续）` → 在该群位置**物化**一条 `老师：{picked}`
      （与 `materialize_pick` 同语义: 回录/回放逐字节同形）。
    """
    recs = _coerce_records(records)
    cand = {c.strip() for c in choices if isinstance(c, str) and c.strip()}
    table = dict(DEFAULT_SPEAKER_NAMES)
    if names:
        table.update(names)
    pick_line = (picked or "").strip()
    pick_rec = (VnRecord(KIND_CHARACTER, CHARACTER_SENSEI, pick_line)
                if pick_line and pick_line not in NON_PICKS else None)
    lines: list[str] = []
    emitted = False
    for rec in recs:
        if pick_rec is not None and not emitted and rec.is_sensei and rec.text.strip() in cand:
            lines.append(_speaker_line(pick_rec, table, speaker))   # 裁决物化在群首
            emitted = True
        if rec.is_sensei and rec.text.strip() in cand:
            continue                                                # 其余候选不出现
        line = _speaker_line(rec, table, speaker)
        if line:
            lines.append(line)
    if pick_rec is not None and not emitted:                        # 无群（CLI 自由文本）
        lines.append(_speaker_line(pick_rec, table, speaker))
    return "\n".join(lines)


def _speaker_line(rec: VnRecord, table: Mapping[str, str], speaker: bool) -> str:
    """单条记录 → 叙事行（不可见记录 → 空串）。"""
    if not rec.text:
        return ""
    if rec.is_narration:
        return rec.text
    if rec.kind == KIND_CHARACTER:
        if not speaker:
            return rec.text
        return f"{table.get(rec.value, rec.value)}：{rec.text}"
    if rec.stage in (STAGE_SWITCH, STAGE_MEMORIAL, STAGE_END):
        return rec.text
    return ""


def pick_insert_index(records: Iterable[Any], choices: Iterable[str] = ()) -> int:
    """裁决行的插入位置（在**显示行**序列里的下标）——群首之前。

    `BondScene.from_dict` 渲染显示层时用它把 `老师：{picked}` 插回原位
    （派生 paragraphs 已剔除整群, 所以位置要按"显示行"数）。
    """
    cand = {c.strip() for c in choices if isinstance(c, str) and c.strip()}
    idx = 0
    for rec in _coerce_records(records):
        if rec.is_sensei and rec.text.strip() in cand:
            return idx
        if _speaker_line(rec, {}, True):
            idx += 1
    return idx


# ---------------------------------------------------------------------------
# 增量解析（流式: chunk → 完整行 → 板闭合即交付）
# ---------------------------------------------------------------------------


class BlockStreamParser:
    """**流式**块解析器: 逐 chunk 喂入, 板一闭合即可取走（`pop_ready()`）。

    为什么现在才可能: 记录流是**行分隔**的——chunk 里出现换行就能解析那一行;
    旧契约是"整回复单个 JSON 对象", 半个 JSON 无法解析, 只能等全量收完。

    切板规则与批式 `_board_spans` **同源**（只是增量推进）:
        · 槽挂板尾: sensei 连续段结束（后一行不是 sensei）= 板结束, 后一行开新板
        · 换场前必切: `switch` 开新板
        · 超长群: 满 MAX_SENSEI_RUN 先收槽, 新群从下一条起
        · `art` 是块级声明 → 不参与切板（由调用方挂到 scene.art_hint）
    容错与批式一致: 复用 `_parse_line_multi`（围栏/数组/辅助转义/丢行记账）。
    """

    def __init__(self, *, main_id: str = "", aliases: Iterable[str] = ()) -> None:
        self._main_id = main_id
        self._aliases = tuple(aliases)
        self._text_buf = ""                     # 未闭合的行缓冲
        self._cur: list[VnRecord] = []          # 当前板缓冲（不含尾部群）
        self._run: list[VnRecord] = []          # 当前尾部 sensei 群
        self._art = ""                          # 块级画面意向
        self._ready: list[tuple[VnRecord, ...]] = []
        self._notes: list[str] = []
        self.records: list[VnRecord] = []       # 全量（诊断/trace）
        self.line_no = 0

    # --- 喂入 --------------------------------------------------------------
    def feed(self, chunk: str) -> None:
        """喂一段文本（可以切在行中间）——完整行即时解析、满板即时闭合。"""
        self._text_buf += chunk or ""
        while "\n" in self._text_buf:
            line, self._text_buf = self._text_buf.split("\n", 1)
            self._consume_line(line)

    def finish(self) -> None:
        """流结束: 收残余行 + 闭合最后一个板。"""
        if self._text_buf.strip():
            self._consume_line(self._text_buf)
            self._text_buf = ""
        self._close()

    # --- 产出 --------------------------------------------------------------
    def pop_ready(self) -> list[tuple[VnRecord, ...]]:
        """取走已闭合的板（可多次调用; 返回自上次以来新闭合的）。"""
        out, self._ready = self._ready, []
        return out

    @property
    def notes(self) -> tuple[str, ...]:
        return tuple(self._notes)

    @property
    def art_hint(self) -> str:
        return self._art

    # --- 内部 --------------------------------------------------------------
    def _consume_line(self, raw: str) -> None:
        self.line_no += 1
        recs, diag = _parse_line_multi(raw, self.line_no)
        if diag is not None:
            tag = "DROP" if diag.dropped else "NOTE"
            self._notes.append(f"[{tag} line {diag.line_no}] {diag.error}")
        for rec in recs:
            self._push(rec)

    def _push(self, rec: VnRecord) -> None:
        self.records.append(rec)
        if rec.is_stage and rec.stage == STAGE_ART:
            self._art = rec.text                # 块级声明（不切板）
            return
        if rec.is_sensei:
            if len(self._run) >= MAX_SENSEI_RUN:
                self._close()                   # 超长群切槽: 满 3 先收
            self._run.append(rec)
            return
        if self._run:                           # 群结束 → 槽挂板尾, 收板
            self._close()
        if rec.stage == STAGE_SWITCH and self._cur:
            self._close()                       # 换场前必切
        self._cur.append(rec)

    def _close(self) -> None:
        board = self._cur + self._run
        self._cur, self._run = [], []
        if board:
            self._ready.append(tuple(board))

    def all_boards(self) -> list[tuple[VnRecord, ...]]:
        """当前累计的板（含已取走的? 否——仅未取走的; 全量见 `records`）。"""
        return list(self._ready)
