"""digest 域注册表 — 记忆整理 LLM 输出的动作 spec 单源（AGENT_BRAIN.md §3 重构 / 板块 2）。

背景: digest 曾是"数据产出"风格——build_digest_schema_v2 手写 schema（LLM 可见面）
与 revise.py 手写校验（runtime 接受面）双写, 漂移源。重构为动作注册表:
每个动作 spec 一份, 驱动两层——
    ① build_schema(phase)  → prompt 内嵌的输出格式文本（字段旁内联约束注释,
                              A-MEM Ps1 模板同款: 规则贴字段, 不散散文）
    ② parse_round_a/b      → 结构校验（宁缺勿错, 逐条报错; 内容质量用 warning
                              不阻断, 引擎执行层再叠加引用级/图语义校验）

分轮（两轮 digest, 2026-09-02 定稿 + 深度整理占位）:
    phase=record     Round A 记录员: record_episode——只产 episode, 不看旧记忆
    phase=understand Round B 理解者: touch / update / add——决策表（逐 episode 一行,
                     结构保证不漏不编 id; 输出对齐输入 = A-MEM 列表对齐的升级）
    phase=deep       深度整理（merge/contradict/…: 后续板块注册, 每 N=5 段触发）
包级字段（B 轮）: evidence（罗盘成长证据）/ affection_exp_delta（引擎消费）。

引擎执行层在 core/brain/wiki_v2/（digest.py 两轮编排 + revise.py 执行器, 板块 4）;
本文件只管"LLM 契约层": 结构/类型/边界/字段约束。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contract.model import ValidationResult

PHASE_RECORD = "record"
PHASE_UNDERSTAND = "understand"
PHASE_DEEP = "deep"

#: B 轮决策类型
DECISIONS = ("touch", "update", "add")

#: 玩家画像条目的 subject 固定值（与 nodes.PLAYER_SUBJECT 对齐, 契约层不依赖 core）
PLAYER_SUBJECT = "player"

#: 边界（parse 级）
MAX_EPISODES = 5        # A 轮单包最多 episode 数
MAX_NARRATION = 300     # narration 单行上限（汉字）
MAX_CONTENT = 200       # belief content 上限（AgentGal write_rules 同款）
MAX_TAGS = 4            # tags 检索词上限
MAX_EXAMPLES = 3        # experience.examples 上限
MAX_EVIDENCE = 5        # B 轮 evidence 上限


@dataclass(frozen=True)
class DigestAction:
    """digest 动作 spec（单源真值）。

    渲染与校验共用: schema_text 的每个字段约束同时是 parse 的检查依据——
    改字段约束只改这一处。
    """

    name: str                       # record_episode / touch / update / add
    phase: str                      # PHASE_*
    role: str                       # 一句释义（LLM 可见）
    semantics: str                  # 何时用/怎么改/禁什么（三段式规则文案）
    field_schema: str               # 字段块（// 内联约束注释, A-MEM Ps1 式）
    example: str = ""               # 范例 JSON 片段（正例）


# ============================================================================
# 动作定义
# ============================================================================

RECORD_EPISODE = DigestAction(
    name="record_episode",
    phase=PHASE_RECORD,
    role="把本段新增互动浓缩为值得记住的经历条目（一条一对象）。",
    semantics=(
        "何时用: 时间线里形成了完整经历（有起有落/有情感细节/值得以后想起）;\n"
        "怎么改: 第一人称浓缩——起点→关键推进→落点, 保留角色当时的感受与反应;"
        " 印象最深的一句原话进 verbatim（逐字, 禁改写）;\n"
        "禁什么: 不升华成人生感悟; 不记寒暄流水账; 不写旧记忆里已有的事;"
        " 情绪词堆砌但无情节支撑 → 舍弃。"
    ),
    field_schema=(
        '    {  // 一条记录, 最多一次输出 5 条; kind=episode 默认 //\n'
        '      "kind": "episode",    // "episode"=经历 | "experience"=玩家画像专用\n'
        '                            //（玩家口癖/偏好/一次性个人信息——pattern 必填,\n'
        '                            //  subject 不用填, 引擎固定为 player）//\n'
        '      "narration": "…",  // kind=episode 必填; 单行 ≤300 字; 浓缩不流水账 //\n'
        '      "pattern": "…",    // kind=experience 必填; 玩家画像句, 如"玩家的生日是\n'
        '                          // 5 月 20 日""玩家总说摸鱼" //\n'
        '      "title": "…",      // kind=episode 必填; 8-16 字短标题; 拿不准也给朴素标题 //\n'
        '      "verbatim": "…",   // 可选; 原话逐字复制（角色或玩家均可）, 禁止改写 //\n'
        '      "tags": ["…"],     // 必填 1-4 个; 检索导向——未来玩家输入/叙事可能出现的词\n'
        '                          //（人名/地点/物品/动作/话题）; 不含时间词; 从最重要排起 //\n'
        '      "significance": 0~1,  // 行为锚点: 0.9+ 改变认知/极深刻（初遇/告白）;\n'
        '                          // 0.7~0.9 重要约定/特别难忘的日常; <0.7 普通但角色在意的细节;\n'
        '                          // 拿不准往低给 //\n'
        '      "epistemic": "observed_fact",  // observed_fact 默认;\n'
        '                          // 若是"听别人说的"→ reported_fact 且必须填 observer=转述者 //\n'
        '      "observer": "…"     // reported_fact 时必填（转述者）; observed 不填 //\n'
        '    }'
    ),
    example=(
        '{"narration": "老师约我去公园散步, 我紧张但努力答应了; 在长椅上一起喝热茶时,'
        ' 一只流浪猫来蹭老师的裤脚, 我鼓起勇气摸了摸它, 回家路上嘴角一直藏着笑。",'
        ' "title": "和老师的公园散步",'
        ' "verbatim": "它想认识你。",'
        ' "tags": ["公园", "流浪猫", "热茶"],'
        ' "significance": 0.8}'
    ),
)

TOUCH = DigestAction(
    name="touch",
    phase=PHASE_UNDERSTAND,
    role="episode 只是再次印证了某条已有认知——连一条边即可。",
    semantics=(
        "何时用: 引擎候选标注'疑似印证'或你判断新经历只是重复已知相处模式;\n"
        "怎么改: 什么都不改——引擎自动把 episode 链到 target 认知;\n"
        "禁什么: 禁止带 patch/content——印证不动原文（改动只发生在 update）。"
    ),
    field_schema=(
        '    {  // 每个 episode 恰好一行; decisions 覆盖全部 episode（引擎结构检查）//\n'
        '      "episode": "m0001",   // 本行处理的 episode id（Round A 产物, 真实 id）//\n'
        '      "decision": "touch",  // touch=印证, 只连边 //\n'
        '      "target": "u0002",    // 必填: 目标认知 id（只能来自下方渲染列表 u0001..）//\n'
        '      "note": "…"           // 可选: 一句印证理由（不进记忆, 仅供审计）//\n'
        '    }'
    ),
    example=(
        '{"episode": "m0001", "decision": "touch", "target": "u0002",'
        ' "note": "又是老师带猫粮来喂, 印证了猫粮约定"}'
    ),
)

UPDATE = DigestAction(
    name="update",
    phase=PHASE_UNDERSTAND,
    role="新经历带来新角度/修正/深化——改写既有认知并连接。",
    semantics=(
        "何时用: 找到同主题认知, 新经历改变/丰富了它;\n"
        "怎么改: patch 部分字段合并改写——只写要变的字段, 空=保留旧值;"
        " 新认知是已有认知的子/超集 → 改宽已有 subject, 不新建;\n"
        " 新 content 应覆盖新旧理解, 重新表述为连贯结论;\n"
        "禁什么: 不复制原文进 content; 不改 epistemic; 不碰出厂基座(canon 只读)。"
    ),
    field_schema=(
        '    {  // 每个 episode 恰好一行 //\n'
        '      "episode": "m0001",   // 真实 id //\n'
        '      "decision": "update",\n'
        '      "target": "u0002",    // 必填: 目标认知 id //\n'
        '      "patch": {            // 部分字段, 空=保留; 至少一个非空 //\n'
        '        "subject": "…",     // 可选; 认知主体, 不按情境命名（太窄→并入更宽维度）//\n'
        '        "content": "…",     // 可选; 结论式 ≤200 字, 不描述事件 //\n'
        '        "significance": 0~1,// 可选; 行为锚点同 A 轮 //\n'
        '        "tags": ["…"],      // 可选; 检索导向 //\n'
        '        "growth": "…"       // 可选; 认知的成长方向（一句）//\n'
        '      }\n'
        '    }'
    ),
    example=(
        '{"episode": "m0002", "decision": "update", "target": "u0001",'
        ' "patch": {"content": "和老师在一起可以安静相处, 沉默也是自然的——现在连'
        ' 带猫粮喂猫这种小事, 我都敢主动约老师一起做了。"}}'
    ),
)

ADD = DigestAction(
    name="add",
    phase=PHASE_UNDERSTAND,
    role="无同主题认知——新建一条（belief 或 experience）并连回 episode。",
    semantics=(
        "何时用: 候选里没有同主题认知, 且新经历形成了稳定结论或可复用模式;\n"
        "怎么改: subject 用稳定维度命名（人/关系/互动模式/性格特征）;"
        " content 写结论不写事件; 反复出现的模式 → kind=experience（pattern 句 + 首个 example）;\n"
        "禁什么: 与已有认知同抽象层或更窄 → 应 update 已有而非 add;"
        " 只印证不新增 → 应 touch; 引擎标注'疑似重复'仍 add → 整包拒。"
    ),
    field_schema=(
        '    {  // 每个 episode 恰好一行 //\n'
        '      "episode": "m0001",   // 真实 id //\n'
        '      "decision": "add",\n'
        '      "kind": "belief",     // belief=认知结论 | experience=重复模式 //\n'
        '      "subject": "…",       // 必填; 稳定维度命名, 不按情境 //\n'
        '      "content": "…",       // belief 必填: 结论式 ≤200 字 //\n'
        '      "pattern": "…",       // experience 必填: 模式句 //\n'
        '      "example": "…",       // experience 可选: 本次的具体例子一句 //\n'
        '      "tags": ["…"],        // 可选; 检索导向 //\n'
        '      "significance": 0~1,  // 可选; 行为锚点 //\n'
        '      "growth": "…"         // belief 可选; 成长方向 //\n'
        '    }'
    ),
    example=(
        '{"episode": "m0003", "decision": "add", "kind": "belief",'
        ' "subject": "我对老师的信任",'
        ' "content": "老师是第一个不嫌弃我的人——把猫抱到我腿边这种小事, 都让我'
        ' 觉得自己也被放在心上。", "significance": 0.9}'
    ),
)

DEFAULT_ACTIONS = (RECORD_EPISODE, TOUCH, UPDATE, ADD)


# ============================================================================
# 注册表
# ============================================================================

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

    def build_schema(self, phase: str, *, include_examples: bool = True) -> str:
        """渲染某一轮的输出格式文本。

        record:     {"episodes": [...]}
        understand: {"decisions": [...], "evidence": [...], "affection_exp_delta": n}
        """
        if phase == PHASE_RECORD:
            lines = [
                "输出 JSON（不要任何解释文字, 不要 ```json 代码块）:",
                '    {"episodes": [',
            ]
            a = self.spec("record_episode")
            lines.append(a.field_schema)
            lines.extend(["    ]}",
                          "",
                          f"【record_episode 释义】{a.role}",
                          "语义:", a.semantics])
            if include_examples and a.example:
                lines.extend(["", "【范例】", a.example])
            return "\n".join(lines)

        if phase == PHASE_UNDERSTAND:
            actions = self.actions(PHASE_UNDERSTAND)
            lines = [
                "输出 JSON（不要任何解释文字, 不要 ```json 代码块）:",
                '    {"decisions": [',
            ]
            for i, a in enumerate(actions):
                lines.append(a.field_schema)
                if i < len(actions) - 1:
                    lines.append("    , // ——或—— //")
            lines.extend([
                "    ],",
                '     "evidence": [ // 可选; 成长证据——只输出有明确原文支撑的;',
                '                    // confidence < 0.7 会被引擎丢弃; quote 必须逐字来自时间线 //',
                '        {"function": "fe", "confidence": 0.8, "quote": "…原文…", "note": "…"}',
                "     ],",
                '     "affection_exp_delta": 0  // 本段好感净变化 -100~100（int）; 无变化 → 0;',
                '                                // **负值 = 关系恶化**（被伤到/失望/决裂）//',
                "    }",
                "",
                "decisions 规则: 每个 episode 恰好一行; 必须覆盖全部 episode;",
                "id 只能引用上方渲染列表里出现的 id（编造 id → 整包拒）;",
                "引擎候选标注'疑似印证/疑似重复'时必须遵守（印证→touch, 重复→update）。",
            ])
            if include_examples:
                lines.append("")
                for a in actions:
                    lines.extend([f"【{a.name} 释义】{a.role}", "语义:", a.semantics,
                                  "【范例】", a.example, ""])
            return "\n".join(lines)

        raise ValueError(f"未知 digest phase: {phase!r}")

    # ------------------------------------------------------------------
    # 解析（结构校验; 引用级/图语义在引擎执行层）
    # ------------------------------------------------------------------

    def parse_round_a(self, raw: Any) -> tuple[list[dict], ValidationResult]:
        """Round A: {"episodes": [...]} → 规范化条目列表。"""
        errors: list[str] = []
        warnings: list[str] = []
        if not isinstance(raw, dict):
            return [], ValidationResult(errors=("Round A 输出必须是 JSON 对象",))
        raw_eps = raw.get("episodes")
        if not isinstance(raw_eps, list):
            return [], ValidationResult(errors=("episodes 必须是数组",))
        if len(raw_eps) > MAX_EPISODES:
            errors.append(f"episodes 超过 {MAX_EPISODES} 条（超出的丢弃）")
            raw_eps = raw_eps[:MAX_EPISODES]
        out: list[dict] = []
        for i, e in enumerate(raw_eps):
            item, item_errs, item_warns = _clean_episode(e, i)
            errors.extend(item_errs)
            warnings.extend(item_warns)
            if item is not None:
                out.append(item)
        return out, ValidationResult(tuple(errors), tuple(warnings))

    def parse_round_b(self, raw: Any, *, episode_ids: set[str],
                      target_ids: set[str],
                      must_touch: dict[str, str] | None = None,
                      ) -> tuple[list[dict], ValidationResult]:
        """Round B: {"decisions": [...], "evidence": [...], "affection_exp_delta": n}。

        episode_ids: 本轮 Round A 产出的真实 episode id 集（引用检查）。
        target_ids: 渲染给 LLM 的认知本地 id 集（u0001..; 引用检查）。
        must_touch: 引擎候选标注（板块 5）: {episode_id: 疑似同主题候选的本地 id}——
        这些 episode 的 decision 只能是 touch/update（禁 add 重复, 结构强制）。
        """
        errors: list[str] = []
        warnings: list[str] = []
        if not isinstance(raw, dict):
            return [], ValidationResult(errors=("Round B 输出必须是 JSON 对象",))
        rows = raw.get("decisions")
        if not isinstance(rows, list):
            return [], ValidationResult(errors=("decisions 必须是数组",))
        seen: set[str] = set()
        out: list[dict] = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"decisions[{i}] 必须是对象")
                continue
            ep = str(row.get("episode", "")).strip()
            if ep not in episode_ids:
                errors.append(f"decisions[{i}].episode 不在本轮 episode 集内: {ep!r}")
                continue
            decision = str(row.get("decision", "")).strip()
            if decision not in DECISIONS:
                errors.append(f"decisions[{i}].decision 非法: {decision!r}（touch|update|add）")
                continue
            seen.add(ep)
            item: dict = {"episode": ep, "decision": decision}
            forced = (must_touch or {}).get(ep)
            if forced and decision == "add":
                errors.append(
                    f"decisions[{i}]: episode {ep} 存在疑似同主题候选"
                    f"（{forced}）——decision 只能是 touch/update（禁 add 同主题重复）")
                continue
            if decision in ("touch", "update"):
                target = str(row.get("target", "")).strip()
                if not target:
                    errors.append(f"decisions[{i}]: {decision} 必须填 target")
                    continue
                if target not in target_ids:
                    errors.append(f"decisions[{i}].target 不在渲染列表内: {target!r}")
                    continue
                item["target"] = target
                if decision == "touch":
                    note = row.get("note")
                    if isinstance(note, str) and note.strip():
                        item["note"] = note.strip()
                else:  # update
                    patch = row.get("patch")
                    if not isinstance(patch, dict) or not patch:
                        errors.append(f"decisions[{i}]: update 必须带非空 patch 对象")
                        continue
                    if not any(isinstance(v, (str, int, float, list))
                               and v not in (None, "", [], 0)
                               for v in patch.values()):
                        errors.append(f"decisions[{i}]: update.patch 至少一个非空字段")
                        continue
                    if "epistemic" in patch:
                        errors.append(f"decisions[{i}]: patch 不得含 epistemic")
                        continue
                    item["patch"] = patch
            else:  # add
                kind = str(row.get("kind", "belief")).strip()
                if kind not in ("belief", "experience"):
                    errors.append(f"decisions[{i}].kind 非法: {kind!r}（belief|experience）")
                    continue
                item["kind"] = kind
                for f in ("subject", "content", "pattern", "example", "tags",
                          "significance", "growth"):
                    v = row.get(f)
                    if v not in (None, "", []):
                        item[f] = v
                if kind == "belief" and not _nonempty_str(item.get("content")):
                    errors.append(f"decisions[{i}]: add(belief) 必须填 content")
                    continue
                if kind == "experience" and not _nonempty_str(item.get("pattern")):
                    errors.append(f"decisions[{i}]: add(experience) 必须填 pattern")
                    continue
                if not _nonempty_str(item.get("subject")):
                    warnings.append(f"decisions[{i}]: add 缺 subject（建议稳定维度命名）")
            out.append(item)
        # 包级: 覆盖检查（结构保证——漏 episode 直接报错, 引擎不补）
        missing = sorted(episode_ids - seen)
        if missing:
            errors.append(f"decisions 未覆盖全部 episode: 漏 {', '.join(missing)}")
        return out, ValidationResult(tuple(errors), tuple(warnings))


# ============================================================================
# 内部清洗（宁缺勿错: 坏项丢弃 + 报错; 质量项 warning 不阻断）
# ============================================================================

def _clean_episode(e: Any, i: int) -> tuple[dict | None, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(e, dict):
        return None, [f"episodes[{i}] 必须是对象"], []
    # 引擎字段一律不收（id/ts/event_seq/segment_id——LLM 塞了也丢弃）
    for f in ("id", "ts", "event_seq", "segment_id"):
        if f in e:
            warnings.append(f"episodes[{i}] 含引擎字段 {f}——已忽略")
    kind = str(e.get("kind", "episode")).strip()
    if kind == "episode":
        item, errors, warnings = _clean_episode_item(e, i, errors, warnings)
        if item is not None:
            item["kind"] = "episode"
        return item, errors, warnings
    if kind == "experience":
        # 玩家画像条目（MMT 专则, 2026-09-02）: pattern 必填, subject 引擎固定 player
        pattern = e.get("pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            return None, [f"episodes[{i}]: kind=experience（玩家画像）必须填 pattern"], []
        item: dict = {"kind": "experience", "pattern": pattern.strip(),
                      "subject": PLAYER_SUBJECT}
        verbatim = e.get("verbatim")
        if isinstance(verbatim, str) and verbatim.strip():
            item["verbatim"] = verbatim.strip()     # 画像条目无 episode 载体——原话直接存
        tags = [t for t in e.get("tags", []) if isinstance(t, str) and t.strip()][:MAX_TAGS]
        if tags:
            item["tags"] = tags
        sig = e.get("significance")
        try:
            sig_f = float(sig) if sig is not None else 0.5
        except (TypeError, ValueError):
            sig_f = 0.5
        item["significance"] = max(0.0, min(1.0, sig_f))
        return item, errors, warnings
    return None, [f"episodes[{i}].kind 非法: {kind!r}（episode|experience）"], []


def _clean_episode_item(e: dict, i: int, errors: list[str], warnings: list[str]
                        ) -> tuple[dict | None, list[str], list[str]]:
    """kind=episode 条目的字段清洗（缺 narration 整条丢弃, 宁缺勿错）。"""
    narration = e.get("narration")
    if not isinstance(narration, str) or not narration.strip():
        return None, errors + [f"episodes[{i}] 缺 narration"], warnings
    narration = narration.strip()
    if len(narration) > MAX_NARRATION:
        # 宁缺勿错: 整条丢弃（包已无效 → 反馈重试会让 LLM 重写整包, 截断反而静默改内容）
        return None, errors + [f"episodes[{i}].narration 超过 {MAX_NARRATION} 字——整条丢弃"], warnings
    item: dict = {"narration": narration}
    title = e.get("title")
    if isinstance(title, str) and title.strip():
        item["title"] = title.strip()
    else:
        warnings.append(f"episodes[{i}] 缺 title（建议 8-16 字短标题）")
    verbatim = e.get("verbatim")
    if isinstance(verbatim, str) and verbatim.strip():
        item["verbatim"] = verbatim.strip()
    tags = [t for t in e.get("tags", []) if isinstance(t, str) and t.strip()][:MAX_TAGS]
    if tags:
        item["tags"] = tags
    else:
        warnings.append(f"episodes[{i}] 缺 tags（检索导向 1-4 个）")
    sig = e.get("significance")
    try:
        sig_f = float(sig) if sig is not None else 0.5
    except (TypeError, ValueError):
        warnings.append(f"episodes[{i}].significance 非数字——取 0.5")
        sig_f = 0.5
    item["significance"] = max(0.0, min(1.0, sig_f))
    epi = str(e.get("epistemic", "observed_fact")).strip()
    if epi == "reported_fact":
        obs = e.get("observer")
        if not (isinstance(obs, str) and obs.strip()):
            return None, errors + [f"episodes[{i}]: reported_fact 必须带 observer（转述者）"], warnings
        item["epistemic"] = "reported_fact"
        item["observer"] = obs.strip()
    else:
        item["epistemic"] = "observed_fact"
    return item, errors, warnings


def _nonempty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


#: 默认注册表实例（板块 4 引擎编排消费）
digest_registry = DigestRegistry()
