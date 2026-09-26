# -*- coding: utf-8 -*-
"""`contract.records` 的**解析层**（C10 拆分；⑥-1 起通用件来自 `contract.streams`）。

**行 → 记录**：`_record_from_obj`（字典 → `VnRecord` 的形状归一）· 五条容错纪律的
**VN 侧绑定**（`_rescape_repair` 辅助转义 / `_parse_line_multi` = 通用行骨架 + VN 判别
注入）· `parse_line` / `parse_stream` 两个对外入口 ·
`BlockStreamParser`（增量解析: chunk → 完整行 → **板闭合即交付**）。

⭐ **通用件已上提**（⑥-1, `docs/DESIGN_STREAM_CONTRACT.md` §7 复用判定表 / §10.1）：
行骨架（跳空行围栏 / 数组行拍平 / 坏行记账）· 末行悬空修复 · `ParseDiag` ·
增量缓冲基类 `LineStreamBase` —— 都在 `contract.streams`，**逐字未改**。
本模块只留**VN 专有**的三样：判别（`character`/`stage`）· 辅助转义救援 ·
**切板规则**（交付单元 = 板）。

## 纪律

· 依赖方向: `parse` → `streams`（通用层）· `grammar`（取值表 / `VnRecord` / `ParseResult`）;
  **不许** import `check` / `carrier`（它俩反过来用这里的解析器）;
· 坏行一律丢行 + 记 `ParseDiag`, 不抛异常。
"""

from __future__ import annotations

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
    _TEXT_FIELD_RE,
)
from contract.streams import LineStreamBase, parse_line_items
from contract.streams import tail_repair as _tail_repair

#: VN 认得的字段（行里多出来的字段 → 记一条 `dropped=False` 的 note）
_VN_KNOWN_KEYS = frozenset({KIND_CHARACTER, KIND_STAGE, "text"})


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

    ⚠️ **本函数是 VN 专用的**（⑥-1 没上提）：它靠 `^\\{"(character|stage)":` 这条
    **记录文法**。MMT 的 action 行 `payload` 在 `text` 之后 ⇒ 前提不成立
    （`DESIGN_STREAM_CONTRACT.md` §7 复用判定表）。
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


def _parse_line_multi(line: str, line_no: int) -> tuple[list[VnRecord], ParseDiag | None]:
    """一行 → 记录列表（数组行拍平）+ 诊断。围栏/空行 → 空列表。

    = 通用行骨架（`contract.streams.parse_line_items`）+ **VN 的三样注入**
    （判别 / 已知字段 / 辅助转义）。保留本名与签名 ⇒ `records` 的对外面不变。
    """
    items, diag = parse_line_items(
        line, line_no,
        classify=_record_from_obj,
        known_keys=_VN_KNOWN_KEYS,
        rescue=_rescape_repair,
    )
    return list(items), diag


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


class BlockStreamParser(LineStreamBase):
    """**流式**块解析器: 逐 chunk 喂入, 板一闭合即可取走（`pop_ready()`）。

    为什么现在才可能: 记录流是**行分隔**的——chunk 里出现换行就能解析那一行;
    旧契约是"整回复单个 JSON 对象", 半个 JSON 无法解析, 只能等全量收完。

    ⭐ 缓冲/解析/记账在基类 `contract.streams.LineStreamBase`（⑥-1 上提）；
    **本类只定义交付单元**（`_accept` / `_flush`）——即下面这套切板规则。

    切板规则与批式 `_board_spans` **同源**（只是增量推进）:
        · 槽挂板尾: sensei 连续段结束（后一行不是 sensei）= 板结束, 后一行开新板
        · 换场前必切: `switch` 开新板
        · 超长群: 满 MAX_SENSEI_RUN 先收槽, 新群从下一条起
        · `art` 是块级声明 → 不参与切板（由调用方挂到 scene.art_hint）
    容错与批式一致: 基类复用通用行骨架（围栏/数组/辅助转义/丢行记账）。
    """

    def __init__(self, *, main_id: str = "", aliases: Iterable[str] = ()) -> None:
        super().__init__(parse_row=_parse_line_multi)
        self._main_id = main_id
        self._aliases = tuple(aliases)
        self._cur: list[VnRecord] = []          # 当前板缓冲（不含尾部群）
        self._run: list[VnRecord] = []          # 当前尾部 sensei 群
        self._art = ""                          # 块级画面意向

    # --- 产出 --------------------------------------------------------------
    @property
    def art_hint(self) -> str:
        return self._art

    def all_boards(self) -> list[tuple[VnRecord, ...]]:
        """当前累计的板（含已取走的? 否——仅未取走的; 全量见 `records`）。"""
        return list(self._ready)

    # --- 交付单元 = 板（基类只做行级） --------------------------------------
    def _accept(self, rec: VnRecord) -> None:
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

    def _flush(self) -> None:
        self._close()

    def _close(self) -> None:
        board = self._cur + self._run
        self._cur, self._run = [], []
        if board:
            self._ready.append(tuple(board))
