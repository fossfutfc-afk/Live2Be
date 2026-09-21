# -*- coding: utf-8 -*-
"""`contract.records` 的**解析层**（C10, `docs/EXEC_SPLIT.md`）。

**行 → 记录**：`_record_from_obj`（字典 → `VnRecord` 的形状归一）· 五条容错纪律的
实现（`_rescape_repair` 辅助转义 / `_tail_repair` 末行悬空 / `_parse_line_multi`
代码围栏与数组行）· `parse_line` / `parse_stream` 两个对外入口 ·
`BlockStreamParser`（增量解析: chunk → 完整行 → 板闭合即交付）。

## 纪律

· 依赖方向: `parse` → `grammar`（取值表 / `VnRecord` / `ParseDiag`）;
  **不许** import `check` / `carrier`（它俩反过来用这里的解析器）;
· 搬进来的代码**逐字未改**（坏行一律丢行 + 记 `ParseDiag`, 不抛异常）。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from contract.records.grammar import (
    KIND_CHARACTER,
    KIND_STAGE,
    MAX_SENSEI_RUN,
    ParseDiag,
    ParseResult,
    STAGE_ART,
    STAGE_SWITCH,
    STAGE_VALUES,
    TEXT_OPTIONAL_STAGES,
    VnRecord,
    _JSON_ISH_RE,
    _RECORD_HEAD_RE,
    _TAIL_REPAIRS,
    _TEXT_FIELD_RE,
)


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
