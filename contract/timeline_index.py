"""时间线行索引 —— **LLM 抄行号**的唯一词汇表（T14, 2026-09-15）。

## 为什么单独一个模块

`DESIGN_WIKI_V3 §3.3.1` 把 Round A 的职责定成「**只指位置, 不打分**」。
"位置"要有一种写法，而它同时出现在**三个地方**:

| 出现处 | 形态 |
|---|---|
| 渲染（`core/session/renderer.render_timeline(indexed=True)`） | 生成 `[28.3]` |
| prompt（`contract.digest.digest_registry.build_schema` 渲染的文案） | 告诉 LLM 抄哪个 |
| 解析（`contract.digest.parse` 的校验 + `digest.py` 的落库） | 读回 `(28, 3)` |

三处各写一遍 = 迟早漂移，而漂移的表现是**静默取错原文**（不是报错）。
所以词汇表在这里定义一次，三处都 import 它——与 `contract` 层
「LLM 可见 schema 与运行时校验同源」是同一条纪律（见 `AGENTS.md` 的「产品决策」）。

## 词汇表（两级）

    [28]      → 事件（= 一「板」。板指针 `event_seq` 抄这个）
    [28.3]    → 事件 28 的第 3 条记录（`payload.paragraphs[3]`）
    [28.p]    → 事件 28 的**玩家裁决行**（`payload.picked`）
    [20]      → MMT 事件（板指针同样收它——verbatim 有一半落在 MMT 上,
                实测 6 条 episode 里 3 条如此, 见 §3.3.1）

**地址是永久的**: `paragraphs` 落在 append-only 的 `events.jsonl` 里，永不改删。
所以存索引（而不是存文本）之后，"这句原话"可以被**无限次重新解析**出逐字原文——
这正是索引优于自由文本的根据（也是 `verbatim_seq` 字段存在的理由）。
"""
from __future__ import annotations

import re

__all__ = [
    "REC_PICKED",
    "format_event",
    "format_record",
    "parse_index",
    "parse_index_list",
]

#: 玩家裁决行在记录位上的标记（`payload.picked` 不是 `paragraphs` 的成员）
REC_PICKED = "p"

#: `[28]` / `[28.3]` / `[28.p]` —— 宽松读入（前后空白容忍, 其余一律拒）
_INDEX_RE = re.compile(r"^\[?\s*(\d+)\s*(?:\.\s*(\d+|p)\s*)?\]?$")


def format_event(seq: int) -> str:
    """事件头索引 —— `28` → `"[28]"`。"""
    return f"[{int(seq)}]"


def format_record(seq: int, rec: int | str) -> str:
    """记录索引 —— `(28, 3)` → `"[28.3]"`; `(28, "p")` → `"[28.p]"`。"""
    return f"[{int(seq)}.{rec}]"


def parse_index(text: str) -> tuple[int, int | str] | None:
    """`"[28.3]"` → `(28, 3)`; `"[28]"` → `(28, "")`（事件级）。

    **绝不抛**：不认识 → `None`（宁缺勿错——坏索引丢掉那一条, 不废整包）。
    事件级用 `""` 而不是 `None` 表示"没有记录位"，这样元组恒为二元。
    """
    if not isinstance(text, str):
        return None
    m = _INDEX_RE.match(text.strip())
    if not m:
        return None
    seq = int(m.group(1))
    rec = m.group(2)
    if rec is None:
        return (seq, "")
    return (seq, int(rec)) if rec.isdigit() else (seq, REC_PICKED)


def parse_index_list(raw: object) -> list[tuple[int, int | str]]:
    """宽松解析索引数组（LLM 输出）—— 坏项**逐条丢弃**, 不废整包。

    接受 `["28.3", "20.p"]` 也接受 `[28.3]`（数字形态）——后者是模型常见的
    "把索引写成浮点"的手滑, 按 `seq.rec` 读回（`28.30` 会被读成 rec=30,
    这是浮点写法固有的歧义; 故 prompt 侧明确要求**字符串**）。
    """
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[tuple[int, int | str]] = []
    for item in raw:
        if isinstance(item, str):
            got = parse_index(item)
        elif isinstance(item, int) and not isinstance(item, bool):
            got = (item, "")
        else:
            got = None
        if got is not None:
            out.append(got)
    return out
