# -*- coding: utf-8 -*-
"""`contract.records` 的**载体层**（C10, `docs/EXEC_SPLIT.md`）。

`VnBlock`（一块记录 + 群 + 位置元数据 + 两种出口: 落库 dict / 渲染文本）·
说话人身份（`_speaker_key` / `is_main_speaker` / `normalize_main_character` /
`SPEAKER_SENSEI_LABEL` / `DEFAULT_SPEAKER_NAMES`）· 记录集合的渲染与取选项
（`render_records` / `_speaker_line` / `materialize_pick` / `pick_insert_index` /
`_coerce_records` / `NON_PICKS`）。

## 纪律

· 依赖方向: `carrier` → `grammar` / `parse` / `check`（单向, 无环）;
· 搬进来的代码**逐字未改**。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from contract.records.check import (
    Issue,
    check_block,
    sensei_groups,
)
from contract.records.grammar import (
    CHARACTER_NARRATOR,
    CHARACTER_SENSEI,
    KIND_CHARACTER,
    STAGE_END,
    STAGE_MEMORIAL,
    STAGE_SWITCH,
    VnRecord,
)
from contract.records.parse import (
    _record_from_obj,
    parse_stream,
)


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
    issues: tuple[Issue, ...] = ()    # 块内结构校验结果（空 = 合规；分级见 ISSUE_SEVERITY）

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
    def _first_stage(self, value: str) -> int | None:
        for i, rec in enumerate(self.records):
            if rec.stage == value:
                return i
        return None

    @property
    def memorial_at(self) -> int | None:
        """纪念进入记录在块内的下标（前端黑屏从这一条开始, DESIGN_MEMORIAL M3）。

        ⚠️ 2026-09-21: 这里曾**成套声明**位置访问器（`switch_at`/`art_at`/
        `end_at`/`exit_at`）、群视图（`groups`/`group_texts`/`has_choices`）、
        切片助手（`before`/`after`）与渲染包装（`render_text`）——全仓零消费者
        （只剩测试在断言它们自己），**已删**。现役路径: 切板/群判定由
        `sensei_groups`（模块函数）与 `bond_story._board_spans` 直接做;
        渲染走 `render_records`（历史/回放的唯一渲染源）。
        要恢复某个位置访问器, 照下面这一行写回即可。
        """
        return self._first_stage(STAGE_MEMORIAL)

    @property
    def is_valid(self) -> bool:
        return not self.issues

    # --- 出口 --------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """落库 / 回放 payload（唯一真源形态）。"""
        data: dict[str, Any] = {"records": [r.to_dict() for r in self.records]}
        if self.notes:
            data["notes"] = list(self.notes)
        return data


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
