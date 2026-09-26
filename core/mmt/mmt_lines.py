# -*- coding: utf-8 -*-
"""MMT **行流**（⑥-2b, 2026-09-25）——"一行一条 JSON" → `MmtLine`。

契约形式: `docs/DESIGN_STREAM_CONTRACT.md` §1（六条）/ §2（两域对照）/
§10.2 B5（两段式校验）。

两类行（判别键行内可判）::

    {"text": "角色说的话"}                      → MmtLine(kind="text",  text=…)
    {"action": "<动作名>", "payload": {…}}      → MmtLine(kind="action", action=…, payload={…})

⭐ 与 VN 共用 `contract/streams`（行骨架 + 增量缓冲），**唯一差别是交付单元**：
VN 把行聚合成**板**；MMT **一行就是一条消息**（`MmtStream._accept` 直接进 `_ready`）。

## 纪律

· **两段式校验，不新增第三处**（§10.2 B5）：本模块只看**形状**——
  "是 JSON 对象 / 判别键合法且非空 / payload 是对象"；
  字段级（`character_id` / `chapter_title` / `image`）一律留给
  `registry.parse`（`contract/registry.py` 的动作契约）；
· 坏行丢行 + 记账（`ParseDiag`），不抛；
· ⚠️ `line_no` = "本轮第几行"（**数组行拍平后多条共用同一号**）⇒
  **气泡序号别用它**，落库时按"已交付行计数"另给（§10.1 A6）；
· 不做辅助转义救援（§10.1 A5）：MMT 行短，转义错就丢行（宁缺勿错）。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from contract.streams import LineStreamBase, ParseDiag, parse_line_items

#: 判别键 = 行的类别（行内可判）
KIND_TEXT = "text"
KIND_ACTION = "action"
KINDS = (KIND_TEXT, KIND_ACTION)

#: 本域认得的字段（多出来的 → 记一条 `dropped=False` 的 note）
KNOWN_KEYS = frozenset({KIND_TEXT, KIND_ACTION, "payload"})


@dataclass(frozen=True)
class MmtLine:
    """一条已解析的 MMT 行。

    `line_no` 是**解析期定位信息**（诊断用），不参与相等性——行的身份 =
    (kind, text, action, payload)。
    ⚠️ `payload` 是普通 dict ⇒ **action 行不可 hash**（别把它塞进 set / dict 键）。
    """

    kind: str                                         # KIND_TEXT | KIND_ACTION
    text: str = ""                                    # text 行：气泡正文
    action: str = ""                                  # action 行：动作名
    payload: dict[str, Any] = field(default_factory=dict)
    line_no: int = field(default=0, compare=False)

    @property
    def is_text(self) -> bool:
        return self.kind == KIND_TEXT

    @property
    def is_action(self) -> bool:
        return self.kind == KIND_ACTION

    def to_dict(self) -> dict[str, Any]:
        """回写为 LLM 可见的 wire 形状（`{"text": …}` / `{"action": …, "payload": {…}}`）。"""
        if self.kind == KIND_TEXT:
            return {KIND_TEXT: self.text}
        return {KIND_ACTION: self.action, "payload": dict(self.payload)}

    def to_line(self) -> str:
        """回写为**一行 JSONL**（续写轮的 assistant 位 / trace / 探针用）。"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


def line_from_obj(obj: Any) -> tuple[MmtLine | None, str]:
    """dict → MmtLine（**只判形状**）；违规返回 (None, 原因)。

    注入给 `contract.streams.parse_line_items` 的 `classify`。
    """
    if not isinstance(obj, dict):
        return None, f"行必须是 JSON 对象（实得 {type(obj).__name__}）"
    keys = set(obj)
    has_text, has_action = KIND_TEXT in keys, KIND_ACTION in keys
    if has_text and has_action:
        return None, "一行同时含 text 与 action（必须恰好其一）"
    if not (has_text or has_action):
        return None, "行既无 text 也无 action"

    if has_text:
        text = obj.get(KIND_TEXT)
        if not isinstance(text, str):
            return None, f"text 必须是字符串（实得 {type(text).__name__}）"
        if not text.strip():
            return None, "text 不能为空（空行直接别写）"
        return MmtLine(kind=KIND_TEXT, text=text.strip()), ""

    action = obj.get(KIND_ACTION)
    if not isinstance(action, str):
        return None, f"action 必须是字符串（实得 {type(action).__name__}）"
    if not action.strip():
        return None, "action 不能为空（空行直接别写）"
    payload = obj.get("payload", {})
    if not isinstance(payload, dict):
        return None, f"payload 必须是对象（实得 {type(payload).__name__}）"
    return MmtLine(kind=KIND_ACTION, action=action.strip(),
                   payload=dict(payload)), ""


def to_action_raw(line: MmtLine) -> dict[str, Any]:
    """行 → `registry.parse` 吃的 raw dict（§10.2 B6：桥放 MMT 侧）。

    `registry.parse` 只认 `{"action": …, "payload": {…}}`（与旧协议同款），
    所以行解析出来**直接喂**，执行链一个字不用改。
    """
    return {"action": line.action, "payload": dict(line.payload)}


def _parse_row(line: str, line_no: int) -> tuple[list[MmtLine], ParseDiag | None]:
    """一行 → 行对象列表（数组行拍平）+ 诊断。围栏/空行 → 空列表。

    = 通用行骨架（`contract.streams.parse_line_items`）+ MMT 的判别与已知字段；
    **不注入 rescue**（不做辅助转义，见模块 docstring）。
    """
    items, diag = parse_line_items(
        line, line_no, classify=line_from_obj, known_keys=KNOWN_KEYS)
    return list(items), diag


def parse_lines(source: str | Iterable[str]) -> tuple[list[MmtLine], list[ParseDiag]]:
    """批量解析（整块文本或行迭代）——数组行拍平、坏行丢弃并记账。

    批量入口返回裸 `(行, 诊断)`（VN 那个 `ParseResult` 绑 `VnRecord`，
    留在 `contract.records`——§10.1 A3）。
    """
    lines = source.splitlines() if isinstance(source, str) else list(source)
    out: list[MmtLine] = []
    diags: list[ParseDiag] = []
    for idx, raw in enumerate(lines, start=1):
        items, diag = _parse_row(raw, idx)
        out.extend(replace(it, line_no=idx) for it in items)
        if diag is not None:
            diags.append(diag)
    return out, diags


class MmtStream(LineStreamBase):
    """MMT **流式**行解析器: 逐 chunk 喂入，**行一完整就交付**。

    ⭐ 交付单元 = **行本身**（VN 的 `BlockStreamParser` 是把行聚合成板）——
    所以 `pop_ready()` 返回 `list[MmtLine]`，调用方拿到就能上屏 / 落事件
    （C4：行交付即 append 事件，前端轮询天然拿增量，不需要 SSE）。
    """

    def __init__(self) -> None:
        super().__init__(parse_row=_parse_row)

    def pop_ready(self) -> list[MmtLine]:             # type: ignore[override]
        """取走已解析的行（可多次调用）。"""
        return super().pop_ready()

    @property
    def texts(self) -> list[str]:
        """已交付行里的气泡正文（诊断/探针用）。"""
        return [ln.text for ln in self._ready if ln.is_text]

    # --- 交付单元 = 行（基类只做行级） --------------------------------------
    def _accept(self, line: MmtLine) -> None:
        # 补行号（通用骨架只给 ParseDiag 设了号）：数组行拍平后**多条共用同一号**，
        # 所以它只做诊断定位用，**气泡序号另给**（§10.1 A6）。
        self._ready.append(replace(line, line_no=self.line_no))

    def _flush(self) -> None:
        """收尾无动作：行是即时交付的，没有"最后一个单元要闭合"。"""
        return None
