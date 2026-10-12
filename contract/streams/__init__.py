"""`contract.streams` —— **域无关的行流解析层**（⑥-1, 2026-09-25）。

从 `contract.records.parse` 提出来的通用件：**"一行一个 JSON 对象"的骨架**
与**增量缓冲**。MMT（手机消息流）与 VN（记录流）共用它，各自只注入三样东西：

| 注入 | 是什么 | VN 注入的 |
|---|---|---|
| `classify(obj)` | dict → 域自己的行对象（`(item \\| None, reason)`） | `_record_from_obj`（`character`/`stage` 判别） |
| `known_keys` | 该域认得的字段集合（多出来的字段记一条 note） | `{character, stage, text}` |
| `rescue(line)` | 可选的"辅助转义"救援（靠**本域**的文法形状） | `_rescape_repair`（靠 `text` 恒为最后字段） |

设计: `docs/DESIGN_STREAM_CONTRACT.md` §1（契约形式六条）/ §7（复用判定表）/
§10.1（落地细节：base 只做行级，**交付单元留给子类**）。

## 纪律

· 本包**不认识任何域**——不 import `records` / `core` / `webgui`（依赖方向单向:
  `records` → `streams`）；
· 坏行一律**丢行 + 记 `ParseDiag`**，不抛异常（宁缺勿错）；
· ⚠️ **`line_no` 是"喂进来的第几行"**：数组行拍平后**多条共用同一 `line_no`**
  ⇒ 需要"第几个交付单元"的序号时**不要用它**（落库/气泡序号各自另给）。
"""

from __future__ import annotations


from contract.streams.lines import (        # 行骨架（判别注入）+ 诊断 + 末行悬空
    ParseDiag,
    TAIL_REPAIRS,
    parse_line_items,
    tail_repair,
)

from contract.streams.stream import (       # 增量缓冲基类（交付单元留子类）
    LineStreamBase,
)
