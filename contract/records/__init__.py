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
## 包结构（C10, `docs/EXEC_SPLIT.md`）

拆分前 `contract/records.py` 是一个 910 行的单文件（文法常量 / 解析 / 校验 / 载体 /
增量解析五件事一层）。现在它是包（**逐字搬迁**, 零行为改动）:

| 模块 | 管什么 |
|---|---|
| `grammar.py` | 取值表（kind/stage/speaker/上限 + 正则）+ `VnRecord` / `ParseDiag` / `ParseResult` —— **叶子** |
| `parse.py` | 行 → 记录（五条容错纪律）+ `parse_line` / `parse_stream` / `BlockStreamParser` |
| `check.py` | `sensei_groups` + `Issue` 软硬分级 + `check_block` / `check_board` |
| `carrier.py` | `VnBlock` + 说话人身份 + `render_records` / `materialize_pick` / `pick_insert_index` |

import 路径 `contract.records` **不变** ⇒ 全仓 28 处引用（`contract/__init__.py` ·
`contract/schema.py` · `core/session/renderer.py` · `core/bond/bond_story/engine.py` ·
`tests/`）**一个字都不用改**。

## 纪律

· 本文件**只做再导出**; 名字增删请同步这里与 `tests/fixtures/api_surface.txt`
  （`SPLIT_API_UPDATE=1` 刷新）—— 守门会以"丢了/多出 X"指路;
· ⚠️ **不定义 `__all__`**（它会被 API 面快照记成一个新名字）;
· 52 个名字**全部**在本包四个模块里（无"路过"的借用名）。
"""

from __future__ import annotations


from contract.records.grammar import (          # C10: 文法常量 + 记录形状（VnRecord / ParseDiag / ParseResult）
    CHARACTER_NARRATOR,
    CHARACTER_SENSEI,
    KINDS,
    KIND_CHARACTER,
    KIND_STAGE,
    MAX_SENSEI_RUN,
    ParseDiag,
    ParseResult,
    STAGE_ART,
    STAGE_BLOCK_HEAD,
    STAGE_BLOCK_TAIL,
    STAGE_END,
    STAGE_EXIT,
    STAGE_FORBIDDEN_IN_MEMORIAL,
    STAGE_MEMORIAL,
    STAGE_SWITCH,
    STAGE_VALUES,
    TEXT_OPTIONAL_STAGES,
    VnRecord,
    _JSON_ISH_RE,
    _RECORD_HEAD_RE,
    _TAIL_REPAIRS,
    _TEXT_FIELD_RE,
)

from contract.records.parse import (          # C10: 行解析 + 增量解析（两段都在这里）
    BlockStreamParser,
    _parse_line_multi,
    _record_from_obj,
    _rescape_repair,
    _tail_repair,
    parse_line,
    parse_stream,
)

from contract.records.check import (          # C10: sensei 群分组 + 契约问题（软硬分级）+ 块/板校验
    ISSUE_SEVERITY,
    Issue,
    IssueCode,
    IssueSeverity,
    check_block,
    check_board,
    format_issues,
    sensei_group_labels,
    sensei_groups,
    split_issues,
)

from contract.records.carrier import (          # C10: 块载体（VnBlock）+ 渲染/取选项
    DEFAULT_SPEAKER_NAMES,
    NON_PICKS,
    SPEAKER_SENSEI_LABEL,
    VnBlock,
    _coerce_records,
    _speaker_key,
    _speaker_line,
    is_main_speaker,
    materialize_pick,
    normalize_main_character,
    pick_insert_index,
    render_records,
)
