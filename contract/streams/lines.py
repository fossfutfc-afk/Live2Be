"""`contract.streams` 的**行骨架**：一行文本 → 若干行对象 + 一条诊断。

从 `contract.records.parse._parse_line_multi` 提出（⑥-1, **逐字未改**——只是把
域相关的三步改成注入：判别 / 已知字段 / 辅助转义救援）。

五条容错纪律里的四条在这里（第 ⑤ 条"形状违规丢行记账"由 `ParseDiag` 承载）：
    ① 代码围栏行（```…）与空行 → 静默丢弃；
    ② 数组行（LLM 手痒包了一层）→ 拍平成多条；
    ③ 末行悬空（字符串未闭合）→ 追加 `"}` 重试一次（EOF 处无歧义）；
    ④ 辅助转义 → 交注入的 `rescue`（**只有本域自己知道该形状**）。

## 纪律

· 本模块**只 import stdlib**（`json` / `dataclasses`）——不认识任何域；
· ⚠️ `tail_repair` 只对**以字符串结尾**的行有意义（补 `"}`）；
  `payload` 是对象的行（如 MMT 的 action 行）截断后补不上 ⇒ 直接丢行，别硬救。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

#: 末行悬空修复候选（依次尝试）
TAIL_REPAIRS = ('"}', "}")


# ---------------------------------------------------------------------------
# 诊断
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParseDiag:
    """一条解析诊断（`dropped=True` 表示该行被丢弃）。

    ⚠️ 真家 = 本模块（`contract.streams.lines`）；`contract.records` 仍再导出它
    （对外面稳定，`DESIGN_STREAM_CONTRACT.md` §10.1 A3：只有它上提，`ParseResult`
    留在 `records`——那个类型绑 `VnRecord`）。
    """

    line_no: int
    raw: str
    error: str
    dropped: bool = True

    def __str__(self) -> str:                        # pragma: no cover - 展示用
        tag = "DROP" if self.dropped else "NOTE"
        return f"[line {self.line_no}][{tag}] {self.error} | {self.raw[:80]}"


# ---------------------------------------------------------------------------
# 末行悬空修复（通用）
# ---------------------------------------------------------------------------


def tail_repair(line: str) -> Any | None:
    """末行悬空修复：补 `"}` / `}`（EOF 处无歧义）。失败返回 None。"""
    if line.endswith("}"):
        return None
    for suffix in TAIL_REPAIRS:
        try:
            return json.loads(line + suffix)
        except json.JSONDecodeError:
            continue
    return None


# ---------------------------------------------------------------------------
# 行骨架（判别函数由调用方注入）
# ---------------------------------------------------------------------------


def parse_line_items(
    line: str,
    line_no: int,
    *,
    classify: Callable[[Any], tuple[Any | None, str]],
    known_keys: Iterable[str] = (),
    rescue: Callable[[str], tuple[Any | None, str]] | None = None,
) -> tuple[list[Any], ParseDiag | None]:
    """一行 → 行对象列表（数组行拍平）+ 诊断。围栏/空行 → 空列表。

    Args:
        classify:   `obj -> (item|None, 原因)`——**本域**的判别（VN: character/stage）。
        known_keys: 本域认得的字段集合；行里多出来的字段记一条 `dropped=False` 的 note。
        rescue:     可选的辅助转义救援 `line -> (item|None, note)`；
                    返回 `(None, "")` 表示"不属于我能救的那类错误"，交回原有诊断。
    """
    text = (line or "").strip().lstrip("\ufeff")
    if not text or text.startswith("```"):
        return [], None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        if rescue is not None:
            item, note = rescue(text)
            if item is not None:
                return [item], ParseDiag(line_no, text, note, dropped=False)
        repaired = tail_repair(text)
        if repaired is None:
            return [], ParseDiag(line_no, text, f"JSON 解析失败: {e.msg}")
        item, why = classify(repaired)
        if item is None:
            return [], ParseDiag(line_no, text, f"JSON 解析失败: {e.msg}（修复后仍不合法: {why}）")
        return [item], ParseDiag(line_no, text, '末行悬空 → 补 `"}` 救回', dropped=False)

    if isinstance(obj, list):                     # 数组行 → 拍平
        out: list[Any] = []
        for entry in obj:
            item, _why = classify(entry)
            if item is not None:
                out.append(item)
        if not out:
            return [], ParseDiag(line_no, text, "数组行内无合法记录")
        note = ParseDiag(line_no, text, f"数组行 → 拍平 {len(out)} 条", dropped=False)
        return out, note

    item, why = classify(obj)
    if item is None:
        return [], ParseDiag(line_no, text, why)
    extra = set(obj) - set(known_keys)
    if extra:
        return [item], ParseDiag(line_no, text, f"多余字段已丢弃: {sorted(extra)}", dropped=False)
    return [item], None
