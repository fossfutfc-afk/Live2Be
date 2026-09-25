"""digest.py — digest v2 两轮管线（AGENT_BRAIN.md §3 / 板块 4a）。

两轮（2026-09-02 定稿; 吸收 A-MEM 逐条对齐 + AgentGal 两轮结构 + 用户拍板）:
    Round A「记录员」: 只看新时间线 → 浓缩值得记住的经历（registry schema(record)
                      + parse_round_a → 引擎建 episode 节点, 内存暂存）
    Round B「理解者」: 新经历 + 现有认知（本地 id 渲染）→ 决策表 decisions
                      （touch=印证 / update=深化改写+history / add=新建）
                      → apply_decisions 执行 → 原子提交
（另有两轮不在本函数里: **R4 收口**在每段那一批的第 4 步; **全景轮（写卡）**是
 低频轮 —— 见下。）

编排（digest_segment）:
    1. 增量: new_events = seq > store.digested_seq（无新增 → 0 次 LLM 调用）
    2. 公共输入: 时间线(**记录级带行索引**, T14) + 视觉记忆 + 人设锚点（A 用）;
       时间线同时供 B 的 evidence quote 逐字引用
    3. Round A: llm_chat → parse_round_a → 建 episode（引擎字段归属: ts/event_seq;
       event_seq=[interact_max]; 防幻觉——LLM 不产这些字段, 4a 不做每 episode 溯源）
    4. Round B: episodes 摘要 + 认知渲染(u0001.. 本地 id) → llm_chat → parse_round_b
       （引用纪律/覆盖检查在 parse 层）→ apply_decisions（图操作 + evolution 变更审计）
    5. evidence（置信度阈值/quote 非空）→ 返回（罗盘应用后置, 无罗盘则丢弃）
    6. affection_exp_delta 返回（事件幂等写由调用方——运行时集成层）
    7. A/B 任一失败 → clone_state 快照回滚, 水位不推进（宁缺勿错, 可重算）
    8. 成功 → store.save()（原子整写）+ 推进 meta.digested_seq + save_meta

全景轮（`run_panorama`, DESIGN_GRAPH_V4 §8.6, 2026-09-25 接线）:
    **低频 · 写卡** —— 只重写 note 的 B 类两槽（`habits` / `on_mind`）。
    ⭐ 它**不碰图** ⇒ **不进事务、不拍快照**: 产出是一条 `rewrite` 操作, 由调用方
    （`mmt.engine._maybe_card_round`）append 进真源 → `save_notes` → 重建注入。
    触发 = `wiki.meta.json` 的段计数器（每消化成功一段 +1, 到 `PANORAMA_EVERY` 跑一次）,
    **没跑成不清零**（下一段再试）。

反馈回灌（2026-09-02 采纳 llm.client.feedback 语义）: 被拒轮把 LLM 自己的输出
追加为 assistant 位 + 引擎错误, 同一上下文重试 1 次——模型能看见自己错在哪
（旧实现重建 user 消息, 模型看不到被拒输出, 修正成功率低）。

失败: 静默降级（logger.warning + DigestResult(ok=False)——wiki 是派生视图,
events.jsonl 唯一真源, 可重算）。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from contract.digest_registry import (
    PHASE_CLOSE,
    PHASE_PANORAMA,
    PHASE_RECORD,
    PHASE_UNDERSTAND,
    digest_registry,
)
from core.brain.wiki_v2.llm_call import llm_chat
from core.brain.wiki_v2.nodes import PLAYER_SUBJECT, make_node
from core.brain.wiki_v2.panorama import build_input
from core.brain.wiki_v2.recall import (
    EmbedFn,
    recommend_candidates,
)
from core.brain.wiki_v2.render import render_cognition_list
from core.brain.wiki_v2.revise import apply_closures, apply_decisions, apply_panorama
from core.brain.wiki_v2.store import WikiStoreV2
from core.session.events import is_content_event
from core.session.maintenance import exclude_abandoned
from core.session.renderer import render_timeline
from llm.prompts import load_prompt
from llm.task_levels import extra_body as _tl_extra
from llm.task_levels import max_tokens as _tl_max_tokens

logger = logging.getLogger(__name__)

#: 反馈重试（parse/结构被拒 → 带 assistant 原文回灌重试 1 次）
MAX_FEEDBACK_RETRIES = 1
#: evidence 置信度阈值（低于 → 丢弃, 宁缺勿错）
EVIDENCE_THRESHOLD = 0.7
#: B 轮认知渲染上限（本地 id 数量; 排序: 珍贵档先）
COGNITION_CAP = 12
#: 好感 delta clamp 边界（**带符号: 下界 2026-09-13 由 0 放开**）。
#: 语义 = "**单段**内的好感净变化"，不是总量——上界 100 防一段暴涨,
#: 下界 -100 对称防一段暴跌; 累计地板在 `Affection` 层（MIN_EXP=0）。
#: 放开下界的理由见 docs/DESIGN_WIKI_V3.md §3.3.3: 关系能变坏是玩法语义,
#: 且同频召回需要 `aff_at_encoding` 的符号。
_AFF_MIN, _AFF_MAX = -100, 100
#: 全景轮的触发间隔（**段数**）—— 2026-09-25 用户裁决: N=10 段跑一次写卡;
#: **章闭环不插队**, 它只算那一段（触发点唯一 ⇒ 时序可预测）。
PANORAMA_EVERY = 10
#: `wiki.meta.json` 里的段计数器键（"距上次写卡消化了几段"）
PANORAMA_COUNTER_KEY = "segments_since_card"
#: 全景轮单次调用的时间预算（它比一轮 A/B 轻 —— 一次调用, 无反馈重试以外的步骤）
PANORAMA_DEADLINE = 180.0


@dataclass
class DigestResult:
    """一次 digest（两轮）的结果。"""

    ok: bool
    errors: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)     # Round A episode id
    evidence: list[dict] = field(default_factory=list)   # 成长证据（清洗后）
    affection_delta: int = 0
    llm_calls: int = 0
    #: ⭐ **归属线索**（D1, §8.2）: `[{"node": "m0005", "hint": "老师"}]` ——
    #: 第 1 轮给的自然名字, **不落库**（不是节点字段）, 由第 3 轮做 hint→id 映射。
    #: D1 只收集（`_create_a_nodes` 返回）; 消费在 D3（那时才有候选表可映射）。
    hints: list[dict] = field(default_factory=list)
    #: ⭐ **R4 收口的 note 操作**（`add` / `close`）—— ⚠️ **调用方在整批 `ok` 之后才 append**
    #: （§8: 失败 = 整批回滚 ⇒ 那条约定原样开着; 事件 append 不可撤销, 提前写就回不去了）。
    notes_ops: list[dict] = field(default_factory=list)
    #: R4 的世界校验记账（剔掉的引用 / 丢掉的 close 行…）—— 不阻断, 但要看得见
    notes_warnings: list[str] = field(default_factory=list)
    #: R4 物化的 promise 节点 id（R2/R3 要对它们写边 —— §8 的批内顺序就是为这个）
    promise_nodes: list[str] = field(default_factory=list)


@dataclass
class PanoramaRunResult:
    """一次**全景轮（写卡）**的结果（§8.6）。

    `ran=False` = **没调那次 LLM**（没有新材料 —— 重写一遍只是让措辞空转）。
    `ok=True` 时才有 `op`（调用方据此 append 事件 + `save_notes`）。
    """

    ran: bool = False
    ok: bool = False
    card: dict = field(default_factory=dict)             # 归一化的那张卡（parse 层产出）
    op: dict = field(default_factory=dict)               # note 的 `rewrite` 操作
    warnings: list[str] = field(default_factory=list)    # 世界校验的记账（剔/丢/只剩一条…）
    errors: list[str] = field(default_factory=list)
    llm_calls: int = 0
    applied: Any = None                                  # `revise.PanoramaResult`（账）


def run_panorama(
    store: WikiStoreV2,
    llm,
    note_state,
    *,
    new_ids: Any = (),
    embed_fn: EmbedFn | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    extra_body: dict | None = None,
    deadline_seconds: float = PANORAMA_DEADLINE,
    llm_timeout: float | None = None,
) -> PanoramaRunResult:
    """全景轮（写卡）: 取料 → 一次调用 → parse → 执行器 → 返回那条 `rewrite` 操作。

    ⚠️ **它不落任何盘**（不 append 事件、不 save_notes、不碰图）—— 提交顺序是
    "先真源后缓存", 而那两件事只有拿得到 `SessionStore` 的调用方能做
    （`mmt.engine._maybe_card_round`）。本函数只把**该写什么**算出来。

    ⚠️ **无新材料 ⇒ 直接不跑**（`ran=False` 且 `ok=False`, 记一行 INFO）:
    调用方据此**不清零计数器**, 下一段再试。

    Args:
        note_state: 当前笔记状态（`store.notes_state(events)`）—— 上一版那张卡就是它
        new_ids: 本轮新增的 episode id（`DigestResult.created`）
        embed_fn: 语义后端; 没给/失败 → 降级字面锚点（同 recall 的降级口径）
    """
    if max_tokens is None:                       # 真源: task_levels 形态 digest
        max_tokens = _tl_max_tokens("digest")
    if extra_body is None:                       # 真源档位: digest = high（同 A/B 轮）
        extra_body = _tl_extra("digest")
    out = PanoramaRunResult()
    inp = build_input(store, note_state, new_ids=new_ids, embed_fn=embed_fn)
    if not inp.worth_running:
        out.errors.append("没有新消化的经历（重写一遍只是措辞空转）→ 本次不跑")
        logger.info("panorama_skip 无新材料（0 次 LLM 调用）")
        return out
    system = load_prompt("panorama").replace(
        "{{digest_schema}}", digest_registry.build_schema(PHASE_PANORAMA))
    user = inp.render()
    import time as _time
    deadline = _time.monotonic() + deadline_seconds
    card, _resp = _round_call(
        llm, system, user,
        model=model, temperature=temperature, max_tokens=max_tokens,
        llm_timeout=llm_timeout, extra_body=extra_body, deadline=deadline,
        label="panorama",
        # 覆盖检查要拿"上一版卡上的编号集" —— 少了它, "沉默 = 删除"那个洞就还在
        parse_fn=lambda r: digest_registry.parse_panorama(
            r, habit_ids={it.id for it in note_state.habits if it.id}),
        result=out)
    out.ran = True
    if card is None:
        return out                               # `_round_call` 已把原因写进 errors
    applied = apply_panorama(store, card, note_state=note_state)
    out.ok = True
    out.card = card
    out.op = applied.op
    out.warnings = list(applied.warnings)
    out.applied = applied
    for w in applied.warnings:                   # 世界校验的记账: 一行一条, 可 grep
        logger.warning("panorama: %s", w)
    logger.info("panorama_card kept=%d added=%d dropped=%d on_mind=%s warn=%d mode=%s",
                len(applied.kept), len(applied.added), len(applied.dropped),
                bool(applied.op.get("on_mind")), len(applied.warnings), inp.mode)
    return out


def digest_segment(
    store: WikiStoreV2,
    llm,
    events: list,
    *,
    character_prompt: str = "",
    visuals: list[str] | None = None,
    model: str | None = None,
    embed_fn: EmbedFn | None = None,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    evidence_threshold: float = EVIDENCE_THRESHOLD,
    deadline_seconds: float = 300.0,
    llm_timeout: float | None = None,
    extra_body: dict | None = None,
    aff_at_encoding: float | None = None,
    emotion_lexicon: dict | None = None,
) -> DigestResult:
    """增量两轮 digest: 新事件 → A 记录 → B 理解 → 原子落盘 → 推进水位。

    Args:
        store: 目标世界线的图式 wiki（meta.digested_seq 是水位）
        llm: 兼容 llm.chat(messages, model=, temperature=, max_tokens=,
             response_format=, extra_body=) 的客户端
        events: 该世界线完整事件流（Event 列表; 增量由水位切）
        character_prompt: 人设锚点文本（性格+知识两层; 空 → 不注入）
        visuals: 视觉记忆 prompt 列表; None → 从事件流 l2d 事件自动收集
        model: 模型覆盖（None → 客户端默认）
        max_tokens: 输出上限（None → 真源 llm/task_levels.py 形态 "digest" = 8192,
            2026-09-02 集中管理）
        extra_body: 请求附加字段。None → 按真源形态 "digest" 注入（thinking=high——
            深度认知, 2026-09-02 拍板; 实验矩阵: low 5/5 合格但浅 / medium 1/3 死在
            规则校验 / high 2/2 认知深化与逐字校验最佳——不随 settings 全局漂移）;
            显式传（含 {}）→ 调用方覆盖
        deadline_seconds: 全程时间预算（A+B+反馈; high 档长考实测 ~2min,
                   默认 300s——撞上 → 判失败回滚, 水位不推进可重算）
        llm_timeout: per-call 超时覆盖（None = 客户端构造超时; 后台 digest
                   建议 ≥300s——high 档单次长考可超 60s 共享客户端默认）
        aff_at_encoding: 本段**开始之前**的好感标量 `Affection.to_scalar()` ∈ [−1,1]
                   （§3.3.3）——落进 episode 节点的**快照**, 写入后永不改。
                   None = 未采集 → 字段不落库（与 `0.0` 中性区分）。调用方算,
                   因为 wiki_v2 看不到事件流里的 affection 事件。
        emotion_lexicon: 角色情绪词表 `{键: {comment, eg, path}}`
                   （`core.media.load_emotion_lexicon(char_dir)`, §3.3.2）。
                   给了 → 只把**本段实际出现的键**的作者标尺注进 Round A,
                   LLM 才有依据判断"情绪摆幅多大 / 峰值多猛"。
                   None/空 → 不注入（Round A 照跑, 只是少一层依据）。
                   **为什么由调用方给**: 词表在 `assets/illustration/{char_id}/default/`,
                   brain 层不该知道资产布局——与 `aff_at_encoding` 同一分工。
    """
    if max_tokens is None:                       # 真源: task_levels 形态 digest
        max_tokens = _tl_max_tokens("digest")
    if extra_body is None:                       # 真源档位: digest = high（显式）
        extra_body = _tl_extra("digest")
    # 废弃段过滤（2026-09-07, maintenance）: 被压掉的中断段"未发生"——不进记忆
    events = exclude_abandoned(events)
    # 本窗口 = 水位之后**全部**事件（含 marker）——段类型要从 marker 派生, 见下。
    new_all = [e for e in events if e.seq > store.digested_seq]
    # 内容事件 = 非 marker 且非"账目"（affection / note）——判据收在
    # `events.is_content_event` 一处（note 落地前的 `type != "affection"` 已删）。
    new_events = [e for e in new_all if is_content_event(e)]
    if not new_events:
        return DigestResult(ok=True)                     # 无新增 → 0 次 LLM 调用
    # 段类型 + 章标题（2026-09-20）: **从 marker 派生, 不落库**。
    domain, chapters, _bond_seqs = _segment_domain(new_all)
    interact_max = max(e.seq for e in new_events)
    result = DigestResult(ok=False)
    snapshot = store.clone_state()                       # 原子性: 失败 → 回滚

    timeline = render_timeline(new_events, indexed=True)
    # 本段**可寻址事件** —— `event_seq` / `verbatim` 索引的 ⊆ 校验基准（T14）。
    # 只收种子事件（marker/affection 不渲染进时间线, LLM 指不到它们）。
    seq_set = {e.seq for e in new_events}
    by_seq = {e.seq: e for e in new_events}
    if visuals is None:
        visuals = _collect_visual_prompts(new_events)
    # 本段出现的情绪键 → 只把这些键的作者标尺注进 Round A（§3.3.2）。
    # 为什么在这里算: `char_id` 只够定位词表,**哪个键该注**必须看本段实际标注
    # ——全词表对一个只出现 5 键的段是纯噪声, 还会诱使 LLM 拿没出现的键凑强度。
    emotion_scale = ""
    if emotion_lexicon:
        from core.media.emotion_lexicon import render_emotion_scale
        emotion_scale = render_emotion_scale(emotion_lexicon,
                                             _segment_emotion_keys(new_events))
    # 段的日期 = **段内最后一条内容事件**的时刻（2026-09-17, ESSAY §10 时间轴换代）。
    # ⚠️ **不是 `datetime.now()`** —— 那是"写库时刻 / 记账时刻"，而 `ts` 要的是
    #    "这段记忆是什么时候形成的"。
    # **为什么是"最后一条"**: 羁绊剧情期间玩家无法发消息、且每次进入都从头重放
    #    → **玩完（`vn_exit`）那一刻 = 玩家过完整段** → 那一刻才是记忆形成时刻。
    # **为什么用 `new_events` 而不是全部事件**: 后者会取到 digest 自己刚写的
    #    `affection/digest`（本次调用内生成）—— 循环依赖。
    from core.worldtime.age import now_ts as _now_ts      # 写侧单一真源（带时区）
    now_ts = ((new_events[-1].ts or "").strip()
              or _now_ts())
    # （原 `segment_id = f"seg-{interact_max}"` 2026-09-21 删——段边界本来就由 marker
    #   派生（`_segment_domain`），落库的那份零读者。）

    # 时间预算: A+B 全程共享一个 deadline（宁缺勿错——水位不推进, 可重算）
    import time as _time
    deadline = _time.monotonic() + deadline_seconds

    try:
        # ── Round A: 记录员 ──
        system_a = load_prompt("digest_v2_round_a").replace(
            "{{digest_schema}}",
            digest_registry.build_schema(PHASE_RECORD, domain=domain, chapter_count=len(chapters)))
        user_a = _join_sections([
            ("本段新增互动", timeline),
            ("本章标题", " / ".join(c["title"] for c in chapters if c["title"])),  # 多章都列; 空 → 跳过
            ("画面记忆", "\n".join(f"- {v}" for v in visuals)),
            ("角色人设（锚点）", character_prompt),
            ("本段情绪标尺", emotion_scale),
        ])
        entries, resp_a = _round_call(
            llm, system_a, user_a,
            model=model, temperature=temperature, max_tokens=max_tokens,
            llm_timeout=llm_timeout,
            extra_body=extra_body, deadline=deadline, label="round_a",
            parse_fn=lambda r: digest_registry.parse_round_a(r, seq_set=seq_set),
            result=result)
        if entries is None:
            return _rollback(store, snapshot, result)
        # 索引 → 原文（T14）: parse 层拿不到事件流, 回填在这里做
        for ent in entries:
            _resolve_verbatim(ent, by_seq)
        # 一章一个 episode（2026-09-20）—— 引擎确定性收口 + 可观测告警
        entries = _collapse_bond_episodes(entries, chapters)
        # ── 时间推进：**已退役**（2026-09-17, `ESSAY_TIME_MODEL §10`）──
        # 旧实现读 Round A 的 `time_span` 推进 `WorldClock` 的**剧情游标**,
        # 再把新游标 stamp 到节点上（`story_time`）。整条链已废:
        # **唯一日期轴是现实日期**（`node.ts` —— 由下面的 `ts=now_ts` 落下），
        # 剧情内部的流逝自由但**不累积、不进账**。
        # 段的日期 = 段内最后一条内容事件的时刻（见上面 `now_ts` 的取法）。
        # ⚠️ 契约侧的 `time_span` 字段本身也已删（2026-09-17 用户裁决）—— 它当时
        #    "保留但不消费", 而**新衰减模型的输入是活跃日/会话, 不是它**;
        #    加上 parse 层从来没取过它（连落库都没有）, 留着就是白付 token。
        #    枚举定义仍留在 `core/worldtime/span.py`。详见 `contract/digest_registry.py`。
        episode_ids, player_ids, hints = _create_a_nodes(
            store, entries, ts=now_ts,
            event_seq=[interact_max], aff_at_encoding=aff_at_encoding,
            by_seq=by_seq)
        result.hints = hints
        # 台账（D1）: 归属线索与物品台账**开始有了**, 但这一版还不消费 hint。
        # 可 grep: 恒 0 说明第 1 轮没按契约写, 不是"这段没有可归属的东西"。
        logger.info("digest_hint eps=%d hint=%d items=%d（hint 待第 3 轮映射）",
                    len(episode_ids), len(hints),
                    sum(len(e.get("items") or []) for e in entries
                        if e.get("kind") != "experience"))

        # ── Round R4: 收口（promise 记账）—— §8 的批内顺序是 R1 → **R4** → R2 → R3 ──
        # 为什么必须夹在这里: `close` 会**物化 promise 节点**, 而它需要的边由后两轮写
        # （`supports`/`evolved_from` 归 R2、`about` 归 R3）⇒ 节点先就位, 否则它
        # "永远没边、永远没归属"（§9-12 ⑤ 那条"漏一批且永久补不回"的同款错误）。
        note_state = store.notes_state(events)            # 本段之前的备忘录（缓存优先）
        open_promises = [it for it in note_state.promise if not it.closed]
        if episode_ids or open_promises:
            system_c = load_prompt("digest_v2_round_close").replace(
                "{{digest_schema}}", digest_registry.build_schema(PHASE_CLOSE))
            user_c = _join_sections([
                ("还开着的约定", _open_promises_text(open_promises)),
                ("本段新增的经历", _episode_lines(store, episode_ids)),
            ])
            rows_c, resp_c = _round_call(
                llm, system_c, user_c,
                model=model, temperature=temperature, max_tokens=max_tokens,
                llm_timeout=llm_timeout, extra_body=extra_body, deadline=deadline,
                label="close", parse_fn=digest_registry.parse_close, result=result)
            if rows_c is None:
                return _rollback(store, snapshot, result)
            closures = apply_closures(store, rows_c, note_state=note_state,
                                      ts=now_ts, event_seq=[interact_max])
            result.notes_ops = list(closures.ops)          # ⚠️ 调用方等 ok 之后才 append
            result.notes_warnings = list(closures.warnings)
            result.promise_nodes = list(closures.nodes)
            for w in closures.warnings:
                logger.warning("digest_close: %s", w)
            logger.info("digest_close open=%d add=%d close=%d node=%d warn=%d",
                        len(open_promises),
                        sum(1 for o in closures.ops if o.get("action") == "add"),
                        sum(1 for o in closures.ops if o.get("action") == "close"),
                        len(closures.nodes), len(closures.warnings))
        else:
            # 没有开着的约定 **且** 本段没有新经历 ⇒ `add` 没有可引用的经历、
            # `close` 没有可翻篇的条目 ⇒ 这一轮**必然空转** ⇒ 省掉这次调用（0 次）。
            logger.info("digest_close 跳过（没有开着的约定, 本段也没有新经历）")

        # ── Round B: 理解者（引擎候选推荐 + 决策表）──
        # ⭐ `must_include` = 本轮 R4 刚物化的 promise（§9-13）: 它们必须在列表里,
        # 否则 R2 又一次"看不见刚要写边的东西"（`supports`/`evolved_from` 永远打不出来）。
        cog_text, local_of = render_cognition_list(
            store, cap=COGNITION_CAP, exclude=set(player_ids),
            must_include=result.promise_nodes)
        # ⚠️ 两个 id 空间**故意不同**: `touch`/`update` 只认看法（promise 不是看法,
        # 它的正文在固化那一刻写死）; `links` 认"看法 ∪ 承诺"。
        target_ids = {local for real, local in local_of.items()
                      if getattr(store.get(real), "kind", "") in ("belief", "experience")}
        link_ids = set(local_of.values())
        ep_text = _round_b_material(store, episode_ids, local_of,
                                    embed_fn=embed_fn,
                                    char_id=getattr(store, "char_id", ""))
        system_b = load_prompt("digest_v2_round_b").replace(
            "{{digest_schema}}", digest_registry.build_schema(PHASE_UNDERSTAND))
        user_b = _join_sections([
            ("本次新经历（含引擎候选标注）", ep_text),
            ("本段时间线（evidence 的 quote 必须逐字引用这里）", timeline),
            ("现有认知", cog_text),
            ("角色人设（锚点）", character_prompt),
        ])
        rows, resp_b = _round_call(
            llm, system_b, user_b,
            model=model, temperature=temperature, max_tokens=max_tokens,
            llm_timeout=llm_timeout,
            extra_body=extra_body, deadline=deadline, label="round_b",
            parse_fn=lambda r: digest_registry.parse_round_b(
                r, episode_ids=set(episode_ids),
                target_ids=target_ids, link_ids=link_ids),
            result=result)
        if rows is None:
            return _rollback(store, snapshot, result)
        apply_decisions(store, rows,
                        id_map={v: k for k, v in local_of.items()},   # local→real
                        ts=now_ts,
                        event_seq=[interact_max])
    except ValueError as e:                              # store 层拒绝 → 回滚
        result.errors.append(str(e))
        return _rollback(store, snapshot, result)

    # ── 成功: 提交（节点落盘 + 水位推进）──
    result.ok = True
    result.created = episode_ids
    result.evidence = _clean_evidence(resp_b.get("evidence"), evidence_threshold)
    result.affection_delta = _clamp_aff(resp_b.get("affection_exp_delta"))
    store.save()
    # 游标提交：**已退役**（2026-09-17）—— 没有剧情游标可落盘。
    store.meta["digested_seq"] = max((e.seq for e in events), default=interact_max)
    store.save_meta()
    return result


# ---------------------------------------------------------------------------
# 轮次调用（调用 + parse + 反馈回灌, feedback 语义）
# ---------------------------------------------------------------------------

def _round_call(
    llm,
    system: str,
    user: str,
    *,
    model: str | None,
    temperature: float,
    max_tokens: int,
    llm_timeout: float | None,
    extra_body: dict | None,
    deadline: float,
    label: str,
    parse_fn: Callable[[dict], tuple[Any, Any]],
    result: DigestResult | PanoramaRunResult,
) -> tuple[Any | None, dict | None]:
    """一轮 LLM 调用: 调用 → parse → 结构被拒 → assistant 原文 + 错误回灌重试 1 次。

    `result` 只用到 `errors` / `llm_calls` 两个字段 ⇒ A/B 轮（`DigestResult`）与
    全景轮（`PanoramaRunResult`）**共用这一条调用路径**（反馈回灌语义随之统一）。

    Returns:
        (parsed, last_resp): parsed None = 该轮失败（result.errors 已填, 调用方回滚）
    """
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": user}]
    for attempt in range(MAX_FEEDBACK_RETRIES + 1):
        resp, call_err = llm_chat(llm, system, "", messages=msgs, model=model,
                                  temperature=temperature, max_tokens=max_tokens,
                                  extra_body=extra_body, deadline=deadline,
                                  timeout=llm_timeout, label=label)
        if resp is None:
            result.errors.append(call_err or "LLM 调用失败")
            return None, None
        result.llm_calls += 1
        if not isinstance(resp, dict):
            result.errors.append("LLM 输出非 JSON 对象")
            return None, resp
        parsed, vr = parse_fn(resp)
        if vr.is_valid:
            return parsed, resp
        if attempt < MAX_FEEDBACK_RETRIES:
            # feedback 语义: 同一上下文——追加被拒输出 + 引擎错误
            msgs.append({"role": "assistant",
                         "content": json.dumps(resp, ensure_ascii=False)})
            msgs.append({"role": "user",
                         "content": ("【引擎校验反馈（上一轮输出被整包拒绝,"
                                     " 请修正后重新输出完整 JSON）】\n"
                                     + "\n".join(f"- {e}" for e in vr.errors))})
            continue
        result.errors.extend(vr.errors)
        return None, resp
    return None, None                                     # unreachable


# ---------------------------------------------------------------------------
# 引擎侧: 建节点 / 渲染 / 清洗
# ---------------------------------------------------------------------------

def _segment_domain(events: list) -> tuple[str, list[dict], frozenset]:
    """本段类型、**每一章的分组**、章块并集（从 marker 与事件类型派生, 不落库）。

    用户原话: *"离散的是 mmt，但 bond story 不应该连续吗"* ⇒ **粒度跟着"作者单位"走**:
    一章羁绊剧情 → **恰好 1 条**; MMT 碎聊 → 0~5 条（**需要切分的是它**）。

    ⚠️ **窗口是"混的"—— 实测真档**（2026-09-20）: haruka 的窗口里 **13 条 MMT 聊天 +
    5 块羁绊剧情**; mutsuki 是 **26 + 13**。所以不能"整段按一个契约"。

    ⚠️⚠️ **窗口里还可能有"多章"** —— 水位被清 / 重跑时**必然**如此。
    所以"一章一条"必须**按章分组**收口; 拿全窗口的 bond 块当一个章, 会把两章压成一条。

    Returns: `(domain, chapters, bond_seqs)`
        domain: `"bond"`（窗口里有 `vn_enter`）/ `"mmt"`
        chapters: `[{"title": str, "seqs": frozenset[int]}]` —— **一章一块**
            （`vn_enter` … `vn_exit` 之间的 bond 事件）; 不在任何章里的 bond 块
            自成一组（旧档/异常, 标题为空）
        bond_seqs: 全部章块的并集（"这条条目属不属于某一章"的粗判用）
    """
    from core.session.events import M_VN_ENTER, M_VN_EXIT
    chapters: list[dict] = []
    cur: dict | None = None
    orphan: set = set()
    for e in events:
        if getattr(e, "is_marker", False):
            if e.subtype == M_VN_ENTER:
                cur = {"title": str((getattr(e, "payload", None) or {})
                                    .get("chapter_title") or "").strip(),
                       "seqs": set()}
                chapters.append(cur)
            elif e.subtype == M_VN_EXIT:
                cur = None
            continue
        if getattr(e, "type", "") == "bond":
            (cur["seqs"] if cur is not None else orphan).add(e.seq)
    if orphan:
        chapters.append({"title": "", "seqs": orphan})
    chapters = [{"title": c["title"], "seqs": frozenset(c["seqs"])} for c in chapters]
    union = (frozenset().union(*[c["seqs"] for c in chapters]) if chapters
             else frozenset())
    return ("bond" if chapters else "mmt"), chapters, union


def _in_seqs(e: dict, seqs: frozenset) -> bool:
    """条目声明的 `event_seq` 是否落在给的那组块里。"""
    return any(int(s) in seqs for s in (e.get("event_seq") or [])
               if isinstance(s, (int, str)) and str(s).lstrip("-").isdigit())


def _collapse_bond_episodes(entries: list[dict], chapters: list[dict]) -> list[dict]:
    """**按章**收口: 每一章的 episode 只留 1 条 —— "一章一个 episode"的引擎侧兜底。

    契约在 `contract/digest_registry._DOMAIN_CONTRACT`（提示词侧）；这里是
    **确定性兜底**: 提示词没压住时留 `significance` 最高的那条, 其余丢弃, 并留一行
    `WARNING`（可 grep）—— 免得契约被违反是**静默**的。

    ⚠️ **逐章收口**, 不是"整段收口"（见 `_segment_domain` 的两条警告）:
    * 窗口常同时含 MomoTalk 聊天（真档实测 13 / 26 条）—— 那些条目**不属于任何章**,
      照 0~5 条留着（把整段压成 1 条会把聊天里的记忆一起丢掉）;
    * 窗口还可能有**多章**（水位清空后必然）—— **每章各留 1 条**。

    `experience`（玩家画像）不算 episode。为什么丢弃而不是合并文本: 合并是创作（要 LLM）,
    引擎只做判定; 而"一章一条"的前提是那条总结**本来就该覆盖全章**。
    """
    if not chapters:
        return entries
    dropped: set[int] = set()
    for ch in chapters:
        seqs = ch["seqs"]
        if not seqs:
            continue
        group = [e for e in entries
                 if e.get("kind") != "experience" and _in_seqs(e, seqs)]
        if len(group) <= 1:
            continue
        keep = max(group, key=lambda e: float(e.get("significance") or 0.0))
        logger.warning(
            "digest_a contract=bond chapter=%r entries=%d keep=%r（一章一条; 其余已丢。"
            "这行常出现 = 提示词没压住, 看 Round A 的【本段类型】产出契约）",
            ch["title"] or "-", len(group),
            keep.get("title") or str(keep.get("text", ""))[:12])
        dropped |= {id(e) for e in group if e is not keep}
    return [e for e in entries if id(e) not in dropped]


def _create_a_nodes(store: WikiStoreV2, entries: list[dict], *, ts: str,
                    event_seq: list[int],
                    aff_at_encoding: float | None = None,
                    by_seq: dict | None = None
                    ) -> tuple[list[str], list[str], list[dict]]:
    """Round A 条目 → 节点（引擎字段归属——确定性归引擎, 防幻觉）。

    kind=episode  → episode 节点
    kind=experience（玩家画像, MMT 专则）→ subject=player experience 节点:
        口癖/偏好/一次性个人信息——不进本轮 B（B 只组织 episode）, 下轮起参与认知层
    dedupe: (kind, event_seq, 主文本) 命中已有节点 → 复用 id（崩溃窗口重跑防双写）。

    event_seq（T14, 2026-09-15）: **条目自带就用条目自带的**（Round A 抄的行号,
    已在 parse 层校验 ⊆ 本段）, 否则回落到段级 `[interact_max]`。
    旧版**无条件覆写**成 `[interact_max]`——实测 mutsuki 全段 `[60]` 而板最大 55,
    它指向一条 MMT 消息、不指向任何一板, 于是板指针从来没存在过,
    而 `migrate_time` 的唯一排序信号也一起死掉（全部节点同键 → 退化成插入序）。

    aff_at_encoding（§3.3.3, 2026-09-13）: 本段**开始之前**的好感标量
    （`Affection.to_scalar()`, [−1,1]）——快照, 写入后永不改。
    调用方传 None = 未采集（旧档/CLI 路径）→ 字段不落库, 与 `0.0`（中性）区分。

    ⭐ D1（2026-09-22）:
      · `items`（§3.1 物品台账）**随条目自动落库** —— 它在契约层已清洗, 节点字段也已存在。
      · `about_hint`（§8.2 归属线索）**必须在这里摘掉, 不许进 `make_node`** ——
        否则它就是一个被 `from_dict` 静默忽略的未知键（这个项目最恨的静默 no-op）;
        它由第 3 轮消费, 所以随返回值交出去。

    Returns: `(episode_ids, player_ids, hints)`——episode_ids 供 B 覆盖检查;
        hints = `[{"node": id, "hint": 自然名字}]`（**去重后的条目也会记**, 它照样是一条记忆）。
    """
    from core.brain.wiki_v2.revise import _find_duplicate
    episode_ids: list[str] = []
    player_ids: list[str] = []
    hints: list[dict] = []
    for ent in entries:
        # ⚠️ 先摘 hint（不落库）; `items` 留着, 它是真字段
        hint = str(ent.pop("about_hint", "") or "").strip()
        if ent.get("kind") == "experience":
            # ⚠️ `subject` **强制**成 `player`（§5.1）: `experience` 只有一个意思
            # （"关于老师的事"），而 `subject` 是自由文本 —— 契约层已经强制过一次,
            # 这里再强制一次是因为**可见性曾经挂在它上面**（真机 haruka e0001 就是
            # 被一个自造的 subject 藏起来的）。别再让它有第二个写者。
            node = make_node("experience",
                             text=ent["text"], subject=PLAYER_SUBJECT,
                             verbatim=ent.get("verbatim", ""),
                             verbatim_seq=ent.get("verbatim_seq", []),
                             tags=ent.get("tags", []),
                             significance=ent.get("significance", 0.5))
            node.ts = ts
            node.event_seq = list(ent.get("event_seq") or event_seq)
            dup = _find_duplicate(store, node)
            if dup is not None:
                player_ids.append(dup.id)
                continue
            player_ids.append(store.add(node))
            continue
        node = make_node("episode", **{k: v for k, v in ent.items() if k != "kind"})
        node.ts = ts
        node.event_seq = list(ent.get("event_seq") or event_seq)
        # 板级情绪键序列（T15）——召回侧物化, **不进 LLM 上下文**
        if by_seq is not None:
            node.emo_shape = _emotion_shape(node.event_seq, by_seq)
            # 地点键序列（M3, 2026-09-19）——同一手物化, 同一纪律
            node.place = _place_shape(node.event_seq, by_seq)
            # 叙事轴: writer 原文（键不是地名的双射, 判"同地"只能靠语义）
            node.place_raw = _place_raw(node.event_seq, by_seq)
        node.aff_at_encoding = aff_at_encoding
        dup = _find_duplicate(store, node)
        if dup is not None:
            episode_ids.append(dup.id)
            if hint:
                hints.append({"node": dup.id, "hint": hint})
            continue
        nid = store.add(node)
        episode_ids.append(nid)
        if hint:
            hints.append({"node": nid, "hint": hint})
    return episode_ids, player_ids, hints


def _open_promises_text(items: list) -> str:
    """R4 输入之一: **还开着的约定**（带编号 —— 它要照着 `id` 写 `close`）。

    行格式复用注入块的 `notes.render_item`（`n3 周六模型店 (m0009)  ← 记于 3 天前`）——
    ⚠️ **一份行格式只有一个实现**（两个写者必然漂移）。
    """
    from core.brain.wiki_v2.notes import render_item
    return "\n".join(f"- {render_item(it)}" for it in items)


def _episode_lines(store: WikiStoreV2, episode_ids: list[str]) -> str:
    """R4 输入之二: **本段新增的经历**（真 id —— `add`/`close` 的 `refs` 只能引它们）。"""
    lines: list[str] = []
    for nid in episode_ids:
        node = store.get(nid)
        if node is None:
            continue
        head = node.text if len(node.text) <= 120 else node.text[:120] + "…"
        title = node.title or "（无题）"
        lines.append(f"- {node.id} 「{title}」 {head}")
    return "\n".join(lines)


def _round_b_material(store: WikiStoreV2, episode_ids: list[str],
                      local_of: dict[str, str],
                      embed_fn: EmbedFn | None,
                      *, char_id: str = "") -> str:
    """Round B 输入: 新经历摘要 + 每条引擎候选提示（板块 5）。

    每条 episode 用 text 走 recommend_candidates 与现有认知碰撞,
    把最像的几条**列出来给 LLM 参考**（`→ 候选(sim 0.xx): u0002 …`）。

    ⚠️ **候选只是提示, 不分档、不强制**（2026-09-15 T17）: 原先
    `≥CAND_HIGH` 会标【疑似同主题】并让 parse 层**结构强制**禁 `add`——
    而那个阈值从未标定过、实测两模型皆 6/6 全越线 → 新认知永远长不出来。
    现在排序取 top-k 无条件列出，判断全在 LLM（判 add 要在 note 里说明理由）。

    **2026-09-13 V3-0（DESIGN_WIKI_V3 §3.5）**: 末尾打一行**写路径召回台账**
    `recall_write char=… eps=… cands=… best=… mode=…`。

    Returns: episodes_text（含候选提示行）。
    """
    from core.brain.wiki_v2 import recall_ledger
    from core.brain.wiki_v2.recall import _thr, CAND_K

    thr_k = int(_thr("cand_k", CAND_K))
    acc = recall_ledger.CollisionAccount(char_id)
    modes: list[str] = []

    lines: list[str] = []
    for nid in episode_ids:
        node = store.get(nid)
        if node is None:
            continue
        head = node.text
        if len(head) > 120:
            head = head[:120] + "…"
        title = node.title or "（无题）"
        lines.append(f"{node.id} 「{title}」 {head}")
        if node.verbatim:
            lines.append(f"    原话: {node.verbatim}")
        query = f"{node.text} {node.verbatim}".strip()
        cands = recommend_candidates(store, query, embed_fn=embed_fn,
                                     mode_out=modes)
        cands = [(c, s) for c, s in cands if c.id in local_of]   # 只标已渲染的
        acc.episode(n_cand=len(cands),
                    best_sim=(cands[0][1] if cands else 0.0))
        if cands:
            ids = " ".join(local_of[c.id] for c, _ in cands)
            lines.append(
                f"    → 候选(sim {cands[0][1]:.2f}): {ids}"
                " —— 仅供参照, 同主题就 touch/update, 不同主题就 add")

    # 通道口径: 全程 semantic / 全程 keyword / 混合（部分 episode 失败降级）
    if modes and all(m == "semantic" for m in modes):
        acc.mode = "semantic"
    elif modes and all(m == "keyword" for m in modes):
        acc.mode = "keyword"
    elif modes:
        acc.mode = "mixed"
    acc.log(thr_k=thr_k)
    return "\n".join(lines) or "（无）"


def _segment_emotion_keys(events) -> list[str]:
    """本段所有 bond 板里**出现过的**情绪键（按首次出现顺序, 去重）。

    来源 = `payload.paragraphs[i].emotion`（标注层产物, 真源在事件流里）。
    只读不写——用于决定"给 Round A 注哪些键的标尺"（§3.3.2）。
    缺字段/坏结构 → 跳过, 不抛（宁缺勿错: 少注一个键, 不阻断 digest）。
    """
    keys: list[str] = []
    seen: set[str] = set()
    for e in events:
        if getattr(e, "type", None) != "bond":
            continue
        payload = getattr(e, "payload", None) or {}
        for p in payload.get("paragraphs") or []:
            if not isinstance(p, dict):
                continue
            k = p.get("emotion")
            if isinstance(k, str) and k.strip() and k.strip() not in seen:
                seen.add(k.strip())
                keys.append(k.strip())
    return keys


def _join_sections(sections: list[tuple[str, str]]) -> str:
    """输入块拼装: 非空块才注入（省 token）; 空块跳过。"""
    parts = [f"【{title}】\n{body}" for title, body in sections if body]
    return "\n\n".join(parts)


def _collect_visual_prompts(events) -> list[str]:
    """l2d 事件的 gallery png → 同名 json 的 prompt（视觉记忆）。"""
    prompts: list[str] = []
    for e in events:
        if e.type != "l2d":
            continue
        for img in e.payload.get("images", []) or []:
            if not isinstance(img, str) or not img:
                continue
            gjson = Path(img).with_suffix(".json")
            try:
                meta = json.loads(gjson.read_text(encoding="utf-8"))
                prompt = meta.get("prompt", "")
                if isinstance(prompt, str) and prompt.strip():
                    prompts.append(prompt.strip())
            except (OSError, ValueError):
                continue
    return prompts


def _resolve_verbatim(ent: dict, by_seq: dict) -> None:
    """`verbatim_seq`（行索引）→ `verbatim`（逐字原文）——**文本优先**（T14）。

    ## 两条通道（用户 2026-09-15 裁决: "保留 verbatim 可以是文本的通道"）

    ```
    LLM 只给索引  → 引擎解析出原文回填     ← 新能力, 逐字且永久可重解析
    LLM 只给文本  → 原样保留               ← 老通道, 一字不动
    LLM 两条都给  → **文本优先**（索引只留作溯源）
    索引解析不出  → 文本原样保留（没有文本就留空——**绝不编**）
    ```

    ## 为什么两条都给时是**文本**优先（这是个安全决定, 不是偏好）

    用户把"**错索引不可见**"明确**放进待办**了——错的原话一眼看得出不对, 错的索引
    解析出真文本、看起来完全正常。**在台账做出来之前, 索引不该掌握内容**:
    否则一个偏了一位的索引会把一句正确的原话**静默换掉**, 而这正是被推迟处理的那件事。

    所以索引的权威范围限定在"**它是唯一来源**"时。等台账上了（`verbatim_seq` →
    解析文本 打一行）, 再谈要不要让它顶掉文本。
    """
    seqs = ent.get("verbatim_seq") or []
    if not seqs or (ent.get("verbatim") or "").strip():
        return                                   # 无索引 / 已有文本 → 不动
    from contract.timeline_index import parse_index
    picked: list[str] = []
    for idx in seqs:
        got = parse_index(idx)
        if got is None:
            continue
        ev = by_seq.get(got[0])
        if ev is None:
            continue
        text = _text_at(ev, got[1])
        if text:
            picked.append(text)
    if picked:
        # 多条关键句拼一行（`" / "` 与时间线的记录分隔同形）——`render.py` 的
        # `（「{verbatim}」）` 是单行渲染, 换行符会把视图打断。
        ent["verbatim"] = " / ".join(picked)


def _text_at(ev, rec) -> str:
    """事件 + 记录位 → 那一条记录的**逐字原文**（取不到 → `""`, 绝不编）。"""
    from contract.timeline_index import REC_PICKED
    if rec == REC_PICKED:
        pk = ev.payload.get("picked")
        return pk.strip() if isinstance(pk, str) else ""
    if ev.type == "mmt":
        key = {0: "player", 1: "reply"}.get(rec)
        v = ev.payload.get(key) if key else None
        return v.strip() if isinstance(v, str) and v.strip() else ""
    paras = ev.payload.get("paragraphs")
    if not isinstance(paras, list) or not isinstance(rec, int):
        return ""
    if not (0 <= rec < len(paras)):
        return ""
    p = paras[rec]
    t = p.get("text", "") if isinstance(p, dict) else str(p)
    return t.strip() if isinstance(t, str) else ""


def _emotion_shape(seqs: list, by_seq: dict) -> list[str]:
    """板指针 → **板级情绪键序列**（按 seq 序拼接; 取不到 → `[]`, 绝不编）。

    只收 bond 事件: 情绪键由**标注层**产出（每条记录一个键）, MMT 事件没有键。
    空键（`""`/None）跳过——标注失败与"真的无表情"在数据里不可分,
    所以只把**有值的键**按顺序连起来（保持弧的形状, 不补位）。

    🚫 返回值只进 `node.emo_shape`（召回侧）——**绝不进 LLM 上下文**。
    """
    out: list[str] = []
    for seq in sorted(seqs or []):
        ev = by_seq.get(seq)
        if ev is None or ev.type != "bond":
            continue
        paras = ev.payload.get("paragraphs")
        if not isinstance(paras, list):
            continue
        for p in paras:
            k = p.get("emotion") if isinstance(p, dict) else None
            if isinstance(k, str) and k.strip():
                out.append(k.strip())
    return out


def _place_shape(seqs: list, by_seq: dict) -> list[str]:
    """板指针 → **地点键序列**（M3, 2026-09-19）; 取不到 → `[]`, 绝不编。

    与 `_emotion_shape` 同一手（`digest` 按 `event_seq` 从真源物化，
    因为 `Channel.gather` 只拿得到节点、翻不了板）:

    * 每板取 `payload.place`（板首 `switch` 解出的**键**）
    * 再取 `payload.paragraphs[*].place`（句级锚点, 板内后续换场）
    * **相邻去重保序** —— 结果 = "这段去过哪些地方"的变化序列;
      同地反复去会留下多个元素（`school_rooftop, classroom, school_rooftop`）

    只收 bond 事件: 地点键由**标注层**产出, MMT 事件没有键。空键跳过
    （标注失败与"这段没换场"在数据里不可分, 不补位——同 `emo_shape` 的取舍）。

    ⚠️ **带的是键不是 writer 本名**（用户 2026-09-19 的疑问）:
    C 链路比的是相等, 而「放学后的教室」/「教室里」/「回到教室」是同一张图、
    三个字符串 —— 本名做等值分组是废的。本名留在事件流里
    （`payload.place_hint` + 锚点句原文）, `event_seq` 指得到, 要重解析时回捞即可。

    🚫 返回值只进 `node.place`（召回侧）——**绝不进 LLM 上下文**。
    """
    out: list[str] = []
    for seq in sorted(seqs or []):
        ev = by_seq.get(seq)
        if ev is None or ev.type != "bond":
            continue
        keys: list[str] = []
        board = ev.payload.get("place")
        if isinstance(board, str) and board.strip():
            keys.append(board.strip())
        paras = ev.payload.get("paragraphs")
        if isinstance(paras, list):
            for p in paras:
                k = p.get("place") if isinstance(p, dict) else None
                if isinstance(k, str) and k.strip():
                    keys.append(k.strip())
        for k in keys:
            if not out or out[-1] != k:              # 相邻去重（保留"再次到访"）
                out.append(k)
    return out


def _place_raw(seqs: list, by_seq: dict) -> list[str]:
    """板指针 → **writer 原文序列**（叙事轴, 2026-09-19 用户指出后补落）。

    取每板的 `payload.place_hint` —— **writer 自己写的那个名词短语**
    （「放学后的教室」「傍晚的学校天台」），相邻去重保序。

    为什么必须有它: 键**不是地名的双射**（一键多义 / 一地多键），所以判"**同地**"
    只能靠语义, 而语义的输入就是原话 —— 见 `nodes.BrainNode.place_raw` 的两轴表。

    ⚠️ 句级锚点的原文**不在这里**（锚点只存 `{sentence, place}`）——那条句子的
    原文在 `payload.paragraphs[i].text`，与 `verbatim_seq` 同一手:
    地址永久有效，要用时按 `event_seq` 回捞。

    🚫 只进 `node.place_raw`（召回侧）——**绝不进 LLM 上下文**。
    """
    out: list[str] = []
    for seq in sorted(seqs or []):
        ev = by_seq.get(seq)
        if ev is None or ev.type != "bond":
            continue
        hint = ev.payload.get("place_hint")
        if isinstance(hint, str) and hint.strip():
            h = hint.strip()
            if not out or out[-1] != h:
                out.append(h)
    return out


def _clean_evidence(raw: Any, threshold: float) -> list[dict]:
    """evidence 清洗: function/quote 非空 str, confidence ≥ 阈值, clamp 0~1。"""
    out: list[dict] = []
    for e in raw or []:
        if not isinstance(e, dict):
            continue
        fn, quote = e.get("function", ""), e.get("quote", "")
        if not (isinstance(fn, str) and fn.strip()
                and isinstance(quote, str) and quote.strip()):
            continue
        try:
            conf = float(e.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0
        if conf < threshold:
            continue
        item = {"function": fn.strip(),
                "confidence": max(0.0, min(1.0, conf)),
                "quote": quote.strip()}
        note = e.get("note")
        if isinstance(note, str) and note.strip():
            item["note"] = note.strip()
        out.append(item)
    return out


def _clamp_aff(raw: Any) -> int:
    try:
        return max(_AFF_MIN, min(_AFF_MAX, int(raw)))
    except (TypeError, ValueError):
        return 0


def _rollback(store: WikiStoreV2, snapshot: dict,
              result: DigestResult) -> DigestResult:
    """回滚内存态（失败 → 零残留; 水位未推进, 磁盘未动）。

    2026-09-17（`ESSAY_TIME_MODEL §10`）: 原先还要还原 `WorldClock` 的**内存游标**
    （§4.11 I-a 的配套 —— 否则重试会二次推进时钟）。剧情游标整族退役后
    这一步没了, `snapshot_clock` 参数一并删除。

    ⭐ 2026-09-25: **R4 的 note 操作一并作废**（§8: 失败 = 整批回滚 ⇒ 那条约定原样开着）。
    节点面靠 `restore_state` 回去; note 面必须在这里清空 —— 事件 append **不可撤销**,
    调用方只要看到 `ok=False` 就不写, 但结果对象里留着它就是一颗雷。
    """
    store.restore_state(snapshot)
    result.notes_ops = []
    result.promise_nodes = []
    return result
