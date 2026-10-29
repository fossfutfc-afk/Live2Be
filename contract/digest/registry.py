"""digest 注册表 —— **建表 + 渲染 LLM 可见的那份 schema**。

渲染 = **读 `prompts/<相位>.md` + 填槽** —— 每个相位要说给 LLM 听的那段字住在 md 里
（人可改、可 diff）, 本模块只管"取哪份 / 槽填什么"。字段约束不再是 Python 字符串。

六个 `parse_*` 是**薄委托**: 实现在 `contract.digest.parse`
（含已停产的 `group` —— 只为老档保留, 见 `tables.PHASE_GROUP`）。

引擎执行层 = `core/digest/pipeline.py`（编排）+ `core/brain/revise.py`（落图;
退役的 `groups.py` 那一族在 `archive/digest_group/`）。
⭐ **轮次真源 = `core/digest/rounds/__init__.py` 的 `ROUNDS`**（key / 步序 / LLM 身份 /
prompt / 相位 / parse / 料 / 写什么 / 跳过 / 预算一处说全）。
"""
from __future__ import annotations

import textwrap
from typing import Any

import contract.digest.parse as digest_parse
from contract.digest.docs import DEFAULT_ACTIONS, OUTPUT_DISCIPLINE, DigestAction
from contract.digest.prompts import fill, fragment, load
from contract.digest.tables import (
    ABSTRACT_MAX,
    MAX_COGNITIONS,
    PHASE_COGNIZE,
    PHASE_RECORD,
    PHASE_RELATE,
    PHASE_SETTLE,
    PHASE_SPLIT,
)
from contract.errors import err
from contract.model import ValidationResult

#: 相位 → 它那份契约文本（`prompts/<名字>.md`）。没有条目 = 这个相位没有契约可渲染。
#: ⏸ `PHASE_GROUP` 2026-10-13 退役 ⇒ 那一格摘掉（md 搬 `archive/digest_group/group.md`）;
#:    `parse_group` 与相位名**留着**（老档/回放仍要解析, 见 `tables.PHASE_GROUP`）。
PHASE_FILES = {
    PHASE_SPLIT: "split",
    PHASE_RECORD: "record",
    PHASE_RELATE: "relate",
    PHASE_COGNIZE: "cognize",
    PHASE_SETTLE: "settle",
}

#: `digest._segment_domain` 只产这两个; 认不得的按 mmt 收（与拆包前同口径）
DOMAINS = ("mmt", "bond")

class DigestRegistry:
    """digest 动作注册表: schema 渲染 + 结构解析（LLM 契约层）。"""

    domain = "digest"

    def __init__(self, actions=DEFAULT_ACTIONS):
        self._actions: dict[str, DigestAction] = {}
        for a in actions:
            self.register(a)

    def register(self, action: DigestAction) -> None:
        if action.name in self._actions:
            raise ValueError(f"digest 动作重复注册: {action.name}")
        self._actions[action.name] = action

    def spec(self, name: str) -> DigestAction | None:
        return self._actions.get(name)

    def actions(self, phase: str | None = None) -> list[DigestAction]:
        out = [a for a in self._actions.values()
               if phase is None or a.phase == phase]
        return sorted(out, key=lambda a: a.name)

    def build_schema(self, phase: str, *, domain: str = "mmt",
                     chapter_count: int = 1) -> str:
        """渲染某一轮的**输出契约** —— 注进 prompt 的 `{{digest_schema}}` 槽。

        每一个字都在 `contract/digest/prompts/*.md`; 本方法只决定**取哪份**与**槽填什么**
        （字段约束与示例同源那条纪律因此还在: 见 `_domain_contract` 与 `row_fields` 两处）。

        `domain`（2026-09-20 用户裁决）—— **粒度跟着"作者单位"走**: `bond` 是作者写的有始
        有终的一章, `mmt` 是一次覆盖多轮碎聊。⚠️ 只有 `split` / `record` 两个相位随它变。

        `chapter_count` > 1 = 这一段的窗口里有**多章**（水位被清 / 重跑时必然如此）——
        契约要写成"**每章各 1 条**", 否则两章会被压成一条。同样只有 `split` 用。
        """
        name = PHASE_FILES.get(phase)
        if name is None:
            raise ValueError(f"未知 digest phase: {phase!r}")
        slots: dict[str, str] = {"discipline": OUTPUT_DISCIPLINE}
        if phase == PHASE_SPLIT:
            slots["domain_contract"] = _domain_contract(domain, chapter_count)
            # ⭐ 示例与【逐字段】**同源**: 填一次, 缩进那份由它派生（不是各写一份文案）
            row_fields = fill(fragment("row_fields"),
                              {"abstract_max": str(ABSTRACT_MAX)}, where="row_fields.md")
            slots["row_fields"] = row_fields
            slots["row_fields_i5"] = textwrap.indent(row_fields, " " * 5)
        elif phase == PHASE_RECORD:
            rec = self.actions(PHASE_RECORD)
            # ⚠️ 这里刻意**按相位取文档**（不是 `spec("record_episode")`）: 相位是契约里的
            # 事实, 动作名是后来起的 —— 硬编码名字的话, 哪天改了名, 这里会静默少一份文档。
            if len(rec) != 1:
                raise ValueError(err("BadPhaseDocs",
                                     f"record 相位该恰好 1 份文档, 实得 {len(rec)}"))
            slots["record_contract"] = _domain_part("record", domain)
        elif phase == PHASE_COGNIZE:
            slots["max_cognitions"] = str(MAX_COGNITIONS)
        return fill(load(name), slots, where=f"{name}.md")

    # ------------------------------------------------------------------
    # 解析（结构校验; 引用级/图语义在引擎执行层）
    # ⚠️ **实现在 `contract.digest.parse`** —— 这里只留薄委托，让 `ROUNDS` 与测试里
    #    那几十处 `digest_registry.parse_x(...)` 的调用点不用改。
    #    （1b-2a 时这六个委托用的是**函数内 import**，为了绕开
    #     `parse → 常量 → 本模块` 的环; 1b-2b 把常量搬去 `digest_tables` 之后环没了,
    #     import 已收回模块级 —— 见模块 docstring 的"加载顺序"。）
    # ------------------------------------------------------------------

    def parse_round_a(self, raw: Any, *, seq_set: set[int] | None = None
                      ) -> tuple[list[dict], ValidationResult]:
        """实现在 `contract.digest.parse.parse_round_a`（本模块只转交）。"""
        return digest_parse.parse_round_a(raw, seq_set=seq_set)

    def parse_relations(self, raw: Any, *, episode_ids: set[str] | None = None,
                        target_ids: set[str] | None = None,
                        kind_of: dict[str, str] | None = None,
                        ) -> tuple[list[dict], ValidationResult]:
        """实现在 `contract.digest.parse.parse_relations`（本模块只转交）。"""
        return digest_parse.parse_relations(raw, episode_ids=episode_ids, target_ids=target_ids, kind_of=kind_of)

    def parse_cognitions(self, raw: Any, *,
                         evidence_ids: set[str] | None = None,
                         cognition_ids: set[str] | None = None,
                         group_ids: set[str] | None = None,
                         kind_of: dict[str, str] | None = None,
                         ) -> tuple[list[dict], ValidationResult]:
        """实现在 `contract.digest.parse.parse_cognitions`（本模块只转交）。"""
        return digest_parse.parse_cognitions(raw, evidence_ids=evidence_ids, cognition_ids=cognition_ids, group_ids=group_ids, kind_of=kind_of)

    def parse_split(self, raw: Any, *, seq_set: set[int] | None = None,
                    note_ids: set[str] | None = None,
                    overdue_ids: set[str] | None = None,
                    ) -> tuple[list[dict], ValidationResult]:
        """实现在 `contract.digest.parse.parse_split`（本模块只转交）。"""
        return digest_parse.parse_split(raw, seq_set=seq_set, note_ids=note_ids, overdue_ids=overdue_ids)

    def parse_group(self, raw: Any, *, block_ids: set[str]
                    ) -> tuple[list[dict], ValidationResult]:
        """实现在 `contract.digest.parse.parse_group`（本模块只转交）。"""
        return digest_parse.parse_group(raw, block_ids=block_ids)

    def parse_attribution(self, raw: Any, *, known_names: set[str] | None = None,
                          object_ids: set[str] | None = None,
                          self_id: str = "",
                          ) -> tuple[list[dict], ValidationResult]:
        """实现在 `contract.digest.parse.parse_attribution`（本模块只转交）。"""
        return digest_parse.parse_attribution(raw, known_names=known_names,
                                              object_ids=object_ids,
                                              self_id=self_id)

def _part(name: str) -> str:
    """取一份共用片段（`prompts/parts/*.md`）。"""
    return fragment(name)


def _domain_part(kind: str, domain: str) -> str:
    """`domain.<域>` / `record.<域>` —— 认不得的域按 mmt 收（与拆包前同口径）。"""
    return fragment(f"{kind}.{domain if domain in DOMAINS else 'mmt'}")


def _domain_contract(domain: str, chapter_count: int) -> str:
    """段类型那份契约（`parts/domain.<域>.md`）。

    ⚠️ 窗口里有多章时, 那一行"切几件"要换说法（`parts/scope.multi.md`）—— 两句话术
    **同源**: 只有 `bond` 有这一行, 所以槽也只给它。
    """
    if domain != "bond":
        return _domain_part("domain", domain)
    scope = _part("scope.multi" if chapter_count > 1 else "scope.one")
    if chapter_count > 1:
        scope = fill(scope, {"chapter_count": str(chapter_count)}, where="scope.multi.md")
    return fill(_domain_part("domain", domain), {"scope_line": scope}, where="domain.bond.md")


digest_registry = DigestRegistry()
