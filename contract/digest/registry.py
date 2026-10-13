"""digest 注册表 —— **建表 + 渲染 LLM 可见的那份 schema**。

`DigestRegistry` 把 `contract.digest.docs` 里的**文档定义**装成表, 再按相位渲染成注入
prompt 的输出格式文本（约束内联在字段旁, A-MEM Ps1 式: 规则贴着字段写, 不散成散文）。

七个 `parse_*` 是**薄委托**: 实现在 `contract.digest.parse`, 留着是为了 `ROUNDS` 与测试
那几十处 `digest_registry.parse_x(...)` 的调用点不用改。

⛔ 各相位的**框架散文**（"relations 规则: "那几段）仍在本模块的 `build_schema` 里 ——
它们与渲染顺序绑在一起; 外移到 `llm/prompts/*.md` 是批次 1c。

引擎执行层 = `core/digest/pipeline.py`（编排）+ `core/brain/revise.py` / `groups.py`。
⭐ **轮次真源 = `core/digest/rounds/__init__.py` 的 `ROUNDS`**（key / 步序 / LLM 身份 /
prompt / 相位 / parse / 料 / 写什么 / 跳过 / 预算一处说全）。
"""
from __future__ import annotations

import textwrap
from typing import Any

import contract.digest.parse as digest_parse
from contract.digest.docs import (
    _DOMAIN_CONTRACT,
    _RECORD_CONTRACT,
    ABSTRACT_SEMANTICS,
    CLOSE_SEMANTICS,
    DEFAULT_ACTIONS,
    LATE_DUE_SEMANTICS,
    OUTPUT_DISCIPLINE,
    ROW_FIELDS,
    STATE_SEMANTICS,
    DigestAction,
)
from contract.digest.tables import (
    MAX_COGNITIONS,
    PHASE_ATTRIBUTE,
    PHASE_COGNIZE,
    PHASE_GROUP,
    PHASE_RECORD,
    PHASE_RELATE,
    PHASE_SPLIT,
    PHASE_UNDERSTAND,
)
from contract.errors import err
from contract.model import ValidationResult


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

    # ------------------------------------------------------------------
    # schema 渲染（prompt 的 {{digest_schema}} 占位; 含内联约束 + 语义 + 范例）
    # ------------------------------------------------------------------

    def build_schema(self, phase: str, *, domain: str = "mmt",
                     chapter_count: int = 1) -> str:
        """渲染某一轮的输出格式文本。

        ⚠️ `include_examples` **2026-10-13 删**（批次 1b）: 全仓**没有任何地方**传过
        `False`（生产与测试都没有），而它对 `split` / `group` / `attribute` 三个相位
        本来就不生效（实测开关同结果）⇒ 一个"看着能调、实际不调"的假旋钮。
        示例一律带上；将来真需要"无示例"变体时再加，并同时补上那三个相位。

        record:     {"episodes": [...]}
        understand: {"decisions": [...], "affection_exp_delta": n}

        `domain`（2026-09-20, 用户裁决）—— **粒度跟着"作者单位"走**:

        | 段 | 边界 | 该切成几件事（**R0 的活**） |
        |---|---|---|
        | `bond` | `vn_enter`…`vn_exit`（**引擎已知**, 一章 = 作者写的有始有终的一段） | **每章恰好 1 件** = 这一章的总结 |
        | `mmt` | 无作者单位（一次 digest 覆盖多轮碎聊） | 一件一件切, **必须覆盖全部**（连闲聊自成一件） |

        ⚠️ **3b-2（2026-09-29）起 `record` 相位用的是另一份**（`_RECORD_CONTRACT`）:
        R1 只填骨架, 条数不归它。本表说的是**切分**（`split` 相位）。

        用户原话: *"真正的 episode 一个就可以定下，需要被切分的是长篇 MMT 等；
        episode 应该 **informative but single**，belief 则是 **brief but descriptive**"*。
        段类型与**章分组**由 `digest._segment_domain` 从 marker **派生**（不落库）。

        `chapter_count` > 1 = 这一段的窗口里有**多章**（水位被清 / 重跑时必然如此）——
        契约要写成"**每章各 1 条**", 否则两章会被压成一条。
        """
        if phase == PHASE_SPLIT:
            # ⭐ **本段类型那段契约与 R1 共用一份**（`_DOMAIN_CONTRACT`）—— 它是
            # "这一段该切成几件事"的唯一说明, 而**切分权在 R0** ⇒ 它必须在这儿出现。
            contract = _DOMAIN_CONTRACT.get(domain, _DOMAIN_CONTRACT["mmt"])
            if domain == "bond" and chapter_count > 1:
                contract = contract.replace(
                    "→ **这一段恰好 1 件**（它就是**这一段经历过的事**）:",
                    f"→ 本段含 **{chapter_count} 章** —— **每章各恰好 1 件**"
                    f"（共 {chapter_count} 条切片）, 每条就是**它那一章的总结**:")
            # 示例由字段常量拼（**不是另抄一份文案** —— 见 `_SPAN_FIELD` 那段注释）:
            # 整体缩 5 格就与"逐字段说明"那一份的注释列对齐
            example = "\n".join([
                "    {  // 一件事 = 一行; 顺序 = 时间顺序 //",
                textwrap.indent(ROW_FIELDS, " " * 5),
                "    }",
            ])
            return "\n".join([
                OUTPUT_DISCIPLINE,
                contract,
                "",
                '    {"segments": [',
                example,
                "    ]}",
                "",
                "  · **切成几件事**: 一件 = 一场戏（一次见面 / 一段连续聊天）——\n"
                "    换了话题 / 换了人 / 换了场景都**还是**同一件事（那只是它的过程）;\n"
                "    ⚠️ **别切太碎** —— 一场戏切成好几件, 那是流水账, 不是记忆;\n"
                "    ⚠️ 但也**别留空档** —— 没被任何一件覆盖的记录, 下一轮读不到它;\n"
                "    ⚠️ **最后那一截明显没结束 ⇒ 不要写它**（留给下一次, 它会跟后文连成一件）;\n"
                "  · `span` 只写**事件头编号**（`[28.0]` 那种记录行号不用管）;\n"
                "  · **一行一件事** —— 同一件事既了结旧的、又新说定一件 ⇒ 写**两行**\n"
                "    （同一个 span 出现两次, 那没关系）;\n"
                "  · 本段确实没有内容事件 → `\"segments\": []`（合法, 但很少见）。",
                "",
                "【逐字段】",
                ROW_FIELDS,
                "",
                STATE_SEMANTICS,
                "",
                CLOSE_SEMANTICS,
                "",
                LATE_DUE_SEMANTICS,
                "",
                ABSTRACT_SEMANTICS,
            ])

        if phase == PHASE_RECORD:
            # ⭐ **R1 的条数契约 = "骨架有几条就填几条"**（3b-2, 2026-09-29）——
            # 它**不再是**"一章恰好 1 条 / MMT 0~5 条": 那是**切分**的契约（归 R0）。
            # ⚠️ 这两句**故意不复用 `_DOMAIN_CONTRACT`**: 后者说的是"怎么切",
            # 而 R1 拿到的是**已经切好的骨架**, 它只需按顺序填 —— 两句话术不同。
            contract = _RECORD_CONTRACT.get(domain, _RECORD_CONTRACT["mmt"])
            lines = [
                OUTPUT_DISCIPLINE,
                contract,
                "",
                '    {"episodes": [',
            ]
            rec = self.actions(PHASE_RECORD)
            # ⚠️ 这里刻意**按相位取文档**（不是 `spec("record_episode")`）: 名字硬编码的话,
            # 哪天改了动作名, `spec()` 返回 None, 报出来的是一句难懂的
            # `AttributeError: 'NoneType' object has no attribute 'field_schema'`。
            if len(rec) != 1:
                raise ValueError(err("BadPhaseDocs",
                                     f"record 相位该恰好 1 份文档, 实得 {len(rec)}"))
            a = rec[0]
            lines.append(a.field_schema)
            lines.extend(["    ],",
                          '     "affection_exp_delta": 0  // ⭐ **整段**的好感净变化 -100~100（int）;',
                          '                                // 平淡寒暄 0~10 · 有意义的共同经历 30~60 ·',
                          '                                // 重要羁绊时刻 80~100;',
                          '                                // **负值 = 关系恶化**（被伤到/失望/决裂）;',
                          '                                // 判据 = **她对你的亲近感这一段的净变化**,',
                          '                                // 不是"这段剧情好不好"; 拿不准给 0',
                          "    }",
                          "",
                          f"【record_episode 释义】{a.role}",
                          "语义:", a.semantics])
            if a.example:
                lines.extend(["", "【范例】", a.example])
            return "\n".join(lines)

        if phase == PHASE_UNDERSTAND:
            actions = self.actions(PHASE_UNDERSTAND)
            lines = [
                OUTPUT_DISCIPLINE,
                '    {"decisions": [',
            ]
            for i, a in enumerate(actions):
                lines.append(a.field_schema)
                if i < len(actions) - 1:
                    lines.append("    , // ——或—— //")
            lines.extend([
                "    ],",
                '     "links": [ // 可选; 额外的边——把**上面列表里已有**的两条连起来;',
                '               // 只这三种 rel, 两端都必须是列表里出现过的本地 id;',
                '               // 没有就写 []（或省略这个键）//',
                '        {"from": "u0007", "rel": "supports", "to": "u0002"},',
                '        {"from": "u0009", "rel": "evolved_from", "to": "u0007"}',
                "     ],",
                "    }",
                "",
                "decisions 规则: 每个 episode 恰好一行; 必须覆盖全部 episode;",
                "id 只能引用上方渲染列表里出现的 id（编造 id → 整包拒）;",
                "引擎候选标注'疑似印证/疑似重复'时必须遵守（印证→touch, 重复→update）。",
                "",
                "links 规则（**可选的补充边**, 别拿它当主力）:",
                "  supports      —— 「**这条看法**支撑**那条看法**」（两端都是看法;",
                "                    「经历支撑看法」那种由决策表的 touch 写, 别在这里重复）;",
                "  contradicts   —— 「这两条互相打架」（无向: 写一次就够）;",
                "  evolved_from  —— 「这条是新的, 它把旧的盖过去了」（新 → 旧）;",
                "  ⚠️ 方向别写反（`from` 是新/被支撑的那一头）; 两端都不能是本轮新建的条目",
                "    （列表是这一轮**开始前**的样子 —— 新建的下一轮才连得上）。",
                "",
                "两层写法（别混, 2026-09-20 用户定）:",
                "  episode = **informative but single**（信息量足, 但只讲一件事）;",
                "  认知（belief/experience）= **brief but descriptive**（简短, 但描述性 ——",
                "  写的是模式/结论/看法, 不是事件; 不要复述剧情）;",
            ])
            lines.append("")
            for a in actions:
                lines.extend([f"【{a.name} 释义】{a.role}", "语义:", a.semantics,
                              "【范例】", a.example, ""])
            return "\n".join(lines)

        if phase == PHASE_RELATE:
            # ⭐⭐ L1「判关系」（`DESIGN_DIGEST_TWO_PASSES.md` §9）—— **一个字的正文都不写**。
            rel_actions = self.actions(PHASE_RELATE)
            lines = [
                OUTPUT_DISCIPLINE,
                '    {"relations": [',
            ]
            for i, a in enumerate(rel_actions):
                lines.append(a.field_schema)
                if i < len(rel_actions) - 1:
                    lines.append('    , // ——或—— //')
            lines.extend([
                "    ]}",
                "",
                "relations 规则:",
                "  · **一行一条关系**; 同一条经历有几条关系就写几行;",
                "  · 行首 = **本段新来的那条经历**（`\"episode\": \"m…\"`）——",
                "    例外: **【现有认知】列表里的两条之间**也可以直接连, 行首写"
                " `{\"belief\": \"u…\"}`",
                "    （那是**两条已有**的东西之间的关系 —— 引擎不摆也会发给你: 整份列表就在上面;",
                "     判得出来就写, `evolved_from` 只能这么写）;",
                "  · 右边只能引用**上方渲染列表里出现过**的 id（编造 id → **整包拒**）;",
                "  · ⭐ **没话说就不写** —— 不要求每条经历都出现（\"这条跟谁都没关系\"也是一个结论）;",
                "  · ⛔ **这一趟不写正文**: 没有 `text` / `subject` 这些键 ——",
                "    看到\"这里有话可说\"**不用写出来**, 下一趟会看到同一批料, 由它去写;",
                "  · **方向不用你操心**: 两端的类型天然定了方向（经历 → 看法 / 经历 → 对象 /",
                "    新看法 → 旧看法）; 对称的那两条（`akin` / `contradicts`）写哪边都一样。",
            ])
            lines.append("")
            for a in rel_actions:
                lines.extend([f"【{a.name} 释义】{a.role}", "语义:", a.semantics,
                              "【范例】", a.example, ""])
            return "\n".join(lines)

        if phase == PHASE_ATTRIBUTE:
            return "\n".join([
                OUTPUT_DISCIPLINE,
                '    {"entities": [ // 没有要认的就写 [] //',
                '        {"name": "小玉", "aliases": ["tama"],',
                '         "reason": "她第一次出场, 之后还会来"}',
                "    ]}",
                "",
                "一行 = 一个**她还不认识的人 / 地方 / 东西**（从【要认的名字】里挑）:",
                "  name    —— 它的名字（必填; 照【要认的名字】里那样写）;",
                "  aliases —— 可选; 别的叫法（同一个人的其它称呼, 最多 8 个）;",
                "  reason  —— **为什么值得记住它**（必填, 一句话）;",
                "",
                "规则:",
                "  ⛔ **只写「库里确实没有」的** —— 名单在【已有的对象】里; 那里有的**一个字都别写**;",
                "  ⛔ **不许编**: 【要认的名字】是引擎从**你自己写下的标记**里数出来的 ——",
                "    它里面没有的名字, 写了会被丢掉;",
                "  ⭐ **没把握就不写** —— 交 `[]` 是合法答案（「这个人不值得记」也是一个结论）;",
                "  ⛔ **不写正文、不连边**: 归属边由引擎按那个标记**自己连**（她写在哪条上,"
                " 边就落在哪条上）; 印象归**看法**（上一趟的活）。",
            ])

        if phase == PHASE_GROUP:
            return "\n".join([
                OUTPUT_DISCIPLINE,
                "    {",
                '     "attach": [ // 这些块属于**已有的类**（没有就写 []）;',
                '        {"block": "b1", "group": "那片苔藓"}',
                "     ],",
                '     "new": [ // 这些块是一个**新的类**（没有就写 []）;',
                '        {"block": "b2", "title": "模型店的那些事"}',
                "     ],",
                '     "merge": [ // 这两个名字**说的是同一个类**（没有就写 []）;',
                '        {"from": "苔藓的事", "into": "那片苔藓"}',
                "     ]",
                "    }",
                "",
                "三个键**都要在**（没有就写空数组 []）。",
                "⭐ **每个块恰好出现在 attach 或 new 里一个** —— 发下来的每个块都必须有归属;",
                "   漏一个块 = 整包被拒（引擎会带着「你漏了 b2」再问一次）。",
                "",
                "attach 一行 —— 这一块说的就是**已有的某个类**:",
                "  block —— 上面「还没归类的块」的把手（b1…）;",
                "  group —— 「已有的类」里那个类的名字（**照抄**它, 不要改写）;",
                "            名单里没有的名字不要写（写了会被丢掉, 那块留到下次）。",
                "",
                "new 一行 —— 这一块是一个**新的类**:",
                "  block —— 块的把手;",
                "  title —— 你给这个类起的名字（**2~16 字**, 短一点好）:",
                "            写「这类事的名字」, 不是某一件具体事的名字;",
                "            要**具体**（含一个具体的人 / 地方 / 东西）, 不要抽象类别词 ——",
                '            ✗「日常」「回忆」「和老师的相处」 ✓「那片苔藓」「模型店的那些事」。',
                "",
                "merge 一行 —— 库里**两个名字说的是同一个类**, 把它们并成一个:",
                "  from —— 被并掉的**那个名字**（以后不再用）;",
                "  into —— **留下来的**那个名字（成员都会挂到它下面）;",
                "  ⚠️ 只能并【可能重复的类】里出现过的那些名字;",
                "  ⚠️ **名字是地址**: 并掉一个名字 = 那个名字以后指不到东西了 ——",
                "     除非两个类确实是同一类, 否则别并（拿不准就不并, 空着最安全）。",
                "",
                "规则:",
                "  ⚠️ **能归已有的类就别新建** —— 同一个类裂成两个名字是这一步最贵的错"
                "（引擎会把同名的并回去, 但**名字不同、意思相同**的它认不出来）;",
                "  ⚠️ 块是**她自己觉得像**的几件事连起来的 —— 你**不用再判一次像不像**,",
                "     你的活是**给它们一个共同的名字**（或者认出它属于已有的哪个名字）;",
                "  ⚠️ 头里写着「**1 条**」的那种块 = **她把它连到了某个已有的类**（那一行里已经写出"
                "是哪个类）:",
                "     通常就是 attach 到那个类; **只有它明显不是那一类**时, 才给它起个新名字。",
                "  ⚠️ 其余块的类名下面至少要能站住**两件事**（引擎只把有同伴的块发给你, 所以每块都能起）;",
                "  ⚠️ 不要复述事件 —— 类的名字不是这次发生了什么。",
            ])

        if phase == PHASE_COGNIZE:
            # ⭐⭐ L2「造看法 / 写沉淀」—— 这一趟**只写正文**（关系 L1 已经判过）。
            cog_actions = self.actions(PHASE_COGNIZE)
            lines = [
                OUTPUT_DISCIPLINE,
                '    {"cognitions": [',
            ]
            for i, a in enumerate(cog_actions):
                lines.append(a.field_schema)
                if i < len(cog_actions) - 1:
                    lines.append('    , // ——或—— //')
            lines.extend([
                "    ]}",
                "",
                "cognitions 规则:",
                "  · **一行一件事**: 造一条新看法写一行 · 给一个类写沉淀写一行;",
                "  · ⭐ **没话说就不写** —— 一条都不造也完全合法（`\"cognitions\": []`）;",
                f"  · **一段最多造 {MAX_COGNITIONS} 条新看法**（写沉淀的类不算）——"
                " 造多了就是流水账;",
                "  · 右边只能引用**上方渲染列表里出现过**的 id（编造 id → **整包拒**）;",
                "  · ⛔ **别写 id / ts / event_seq**（新节点的号由**引擎发**, 你只管正文）;",
                "  · ⛔ **已有成分之间的关系不用你判** —— 上一趟已经判过了; 这一趟只写"
                "\"新造的那条跟谁相连\";",
                "  · **方向不用你操心**: 两端类型天然定了方向（经历 → 新看法 / 新看法 → 旧看法）;",
                "  · ⚠️ **看法 ≠ 经历**: 经历是\"这一次发生了什么\"（上一趟写完了）; 看法是"
                "从它里面看出来的**结论** ——",
                "    写不出一句站得住的结论, 就别造这一条;",
                "  · ⚠️ **沉淀与看法别互相复述**: 沉淀说的是**这一类事**的共同点,"
                " 看法说的是**这一条**结论;",
                "  · ⚠️ **一条证据都指不出来的看法别造**（`supports` / `evolved_from`"
                " 至少给一个）——",
                "    在图里没有任何连接的看法, 她以后再也想不起来;",
                "  · ⚠️ 沉淀是**写窄了就丢信息**: 重写时保留旧那句说对的部分。",
            ])
            lines.append("")
            for a in cog_actions:
                lines.extend([f"【{a.name} 释义】{a.role}", "语义:", a.semantics,
                              "【范例】", a.example, ""])
            return "\n".join(lines)

        raise ValueError(f"未知 digest phase: {phase!r}")
    # ------------------------------------------------------------------
    # 解析（结构校验; 引用级/图语义在引擎执行层）
    # ⚠️ **实现在 `contract.digest.parse`** —— 这里只留薄委托，让 `ROUNDS` 与测试里
    #    那几十处 `digest_registry.parse_x(...)` 的调用点不用改。
    #    （1b-2a 时这七个委托用的是**函数内 import**，为了绕开
    #     `parse → 常量 → 本模块` 的环; 1b-2b 把常量搬去 `digest_tables` 之后环没了,
    #     import 已收回模块级 —— 见模块 docstring 的"加载顺序"。）
    # ------------------------------------------------------------------

    def parse_round_a(self, raw: Any, *, seq_set: set[int] | None = None
                      ) -> tuple[list[dict], ValidationResult]:
        """实现在 `contract.digest.parse.parse_round_a`（本模块只转交）。"""
        return digest_parse.parse_round_a(raw, seq_set=seq_set)

    def parse_relations(self, raw: Any, *, episode_ids: set[str] | None = None,
                        target_ids: set[str] | None = None,
                        topics_of: dict[str, list[str]] | None = None,
                        kind_of: dict[str, str] | None = None,
                        ) -> tuple[list[dict], ValidationResult]:
        """实现在 `contract.digest.parse.parse_relations`（本模块只转交）。"""
        return digest_parse.parse_relations(raw, episode_ids=episode_ids, target_ids=target_ids, topics_of=topics_of, kind_of=kind_of)

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
                          ) -> tuple[list[dict], ValidationResult]:
        """实现在 `contract.digest.parse.parse_attribution`（本模块只转交）。"""
        return digest_parse.parse_attribution(raw, known_names=known_names)

    def parse_round_b(self, raw: Any, *, episode_ids: set[str],
                      target_ids: set[str],
                      link_ids: set[str] | None = None,
                      ) -> tuple[list[dict], ValidationResult]:
        """实现在 `contract.digest.parse.parse_round_b`（本模块只转交）。"""
        return digest_parse.parse_round_b(raw, episode_ids=episode_ids, target_ids=target_ids, link_ids=link_ids)


digest_registry = DigestRegistry()
