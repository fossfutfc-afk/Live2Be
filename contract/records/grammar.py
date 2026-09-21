# -*- coding: utf-8 -*-
"""`contract.records` 的**文法层**（C10, `docs/EXEC_SPLIT.md`）。

单一真源的取值表（kind / stage / speaker / 上限）+ 三个**纯叶子**数据对象:
`VnRecord`（一条记录）· `ParseDiag`（一条坏行诊断）· `ParseResult`（一次解析的结果）。

## 纪律

· 本模块是包的**最底层**: 只 import stdlib（`re` / `dataclasses`），
  同包其它三个模块都往下看它; 搬进来的代码**逐字未改**。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 文法常量（单一真源：schema 渲染 / 解析器 / 引擎校验共用）
# ---------------------------------------------------------------------------

KIND_CHARACTER = "character"
KIND_STAGE = "stage"
KINDS = (KIND_CHARACTER, KIND_STAGE)

#: `character` 的保留取值（其余一律视为角色 id）
CHARACTER_NARRATOR = "narrator"
CHARACTER_SENSEI = "sensei"

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
