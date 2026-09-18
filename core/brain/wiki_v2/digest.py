"""digest.py — digest v2 两轮管线（AGENT_BRAIN.md §3 / 板块 4a）。

两轮（2026-09-02 定稿; 吸收 A-MEM 逐条对齐 + AgentGal 两轮结构 + 用户拍板）:
    Round A「记录员」: 只看新时间线 → 浓缩值得记住的经历（registry schema(record)
                      + parse_round_a → 引擎建 episode 节点, 内存暂存）
    Round B「理解者」: 新经历 + 现有认知（本地 id 渲染）→ 决策表 decisions
                      （touch=印证 / update=深化改写+history / add=新建）
                      → apply_decisions 执行 → 原子提交

编排（digest_segment）:
    1. 增量: new_events = seq > store.digested_seq（无新增 → 0 次 LLM 调用）
    2. 公共输入: 时间线(**记录级带行索引**, T14) + 视觉记忆 + 人设锚点（A 用）;
       时间线同时供 B 的 evidence quote 逐字引用
    3. Round A: llm_chat → parse_round_a → 建 episode（引擎字段归属: ts/segment_id/
       event_seq=[interact_max]; 防幻觉——LLM 不产这些字段, 4a 不做每 episode 溯源）
    4. Round B: episodes 摘要 + 认知渲染(u0001.. 本地 id) → llm_chat → parse_round_b
       （引用纪律/覆盖检查在 parse 层）→ apply_decisions（图操作 + history 溯源）
    5. evidence（置信度阈值/quote 非空）→ 返回（罗盘应用后置, 无罗盘则丢弃）
    6. affection_exp_delta 返回（事件幂等写由调用方——运行时集成层）
    7. A/B 任一失败 → clone_state 快照回滚, 水位不推进（宁缺勿错, 可重算）
    8. 成功 → store.save()（原子整写）+ 推进 meta.digested_seq + save_meta

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
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from contract.digest_registry import (
    PHASE_RECORD,
    PHASE_UNDERSTAND,
    digest_registry,
)
from core.brain.wiki_v2.llm_call import llm_chat
from core.brain.wiki_v2.nodes import make_node
from core.brain.wiki_v2.recall import (
    EmbedFn,
    recommend_candidates,
)
from core.brain.wiki_v2.render import render_cognition_list
from core.brain.wiki_v2.revise import apply_decisions
from core.brain.wiki_v2.store import WikiStoreV2
from core.session.maintenance import exclude_abandoned
from core.session.renderer import render_timeline
from core.worldtime.span import parse_span
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


@dataclass
class DigestResult:
    """一次 digest（两轮）的结果。"""

    ok: bool
    errors: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)     # Round A episode id
    evidence: list[dict] = field(default_factory=list)   # 成长证据（清洗后）
    affection_delta: int = 0
    llm_calls: int = 0


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
    new_events = [e for e in events
                  if e.seq > store.digested_seq
                  and not e.is_marker and e.type != "affection"]
    if not new_events:
        return DigestResult(ok=True)                     # 无新增 → 0 次 LLM 调用
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
    segment_id = f"seg-{interact_max}"

    # 时间预算: A+B 全程共享一个 deadline（宁缺勿错——水位不推进, 可重算）
    import time as _time
    deadline = _time.monotonic() + deadline_seconds

    try:
        # ── Round A: 记录员 ──
        system_a = load_prompt("digest_v2_round_a").replace(
            "{{digest_schema}}", digest_registry.build_schema(PHASE_RECORD))
        user_a = _join_sections([
            ("本段新增互动", timeline),
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
        # ── 时间推进：**已退役**（2026-09-17, `ESSAY_TIME_MODEL §10`）──
        # 旧实现读 Round A 的 `time_span` 推进 `WorldClock` 的**剧情游标**,
        # 再把新游标 stamp 到节点上（`story_time`）。整条链已废:
        # **唯一日期轴是现实日期**（`node.ts` —— 由下面的 `ts=now_ts` 落下），
        # 剧情内部的流逝自由但**不累积、不进账**。
        # 段的日期 = 段内最后一条内容事件的时刻（见上面 `now_ts` 的取法）。
        # ⚠️ Round A 的 `time_span` **仍由契约输出但不消费**（用户 2026-09-17 裁决 = 选项 c）:
        #    **它是为将来的衰减新模型预留的** —— 玩家的游玩时间是**密集成块的离散**
        #    （一口气玩 3 小时 → 隔一周 → 又 3 小时），而记忆曲线假设时间连续均匀,
        #    **不匹配**。故现在**保留契约字段**, 等新模型落地时改它的计算方式。
        #    详见 `TODO.md`「记忆衰减」。**不要顺手删它。**
        episode_ids, player_ids = _create_a_nodes(
            store, entries, ts=now_ts, segment_id=segment_id,
            event_seq=[interact_max], aff_at_encoding=aff_at_encoding,
            by_seq=by_seq)

        # ── Round B: 理解者（引擎候选推荐 + 决策表）──
        cog_text, local_of = render_cognition_list(
            store, cap=COGNITION_CAP, exclude=set(player_ids))   # 本轮画像条目不进认知列表
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
                target_ids=set(local_of.values())),      # local_of: real→local, 取 values
            result=result)
        if rows is None:
            return _rollback(store, snapshot, result)
        apply_decisions(store, rows,
                        id_map={v: k for k, v in local_of.items()},   # local→real
                        ts=now_ts, segment_id=segment_id,
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
    result: DigestResult,
) -> tuple[Any | None, dict | None]:
    """一轮 LLM 调用: 调用 → parse → 结构被拒 → assistant 原文 + 错误回灌重试 1 次。

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

def _create_a_nodes(store: WikiStoreV2, entries: list[dict], *, ts: str,
                    segment_id: str, event_seq: list[int],
                    aff_at_encoding: float | None = None,
                    story_time: dict | None = None,
                    by_seq: dict | None = None
                    ) -> tuple[list[str], list[str]]:
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

    story_time（§4.11, 2026-09-13）: 本段**结束时刻**的剧情时间点
    （`StoryTime.to_dict()`）——同样是**快照, 写入后永不改**。
    ⚠️ **只在这里写**（I-b）: `apply_decisions`（Round B）不许碰它,
    与 `id`/`ts`/`event_seq` 同级保护——否则时间会倒流。

    Returns: (episode_ids, player_ids)——episode_ids 供 B 覆盖检查。
    """
    from core.brain.wiki_v2.revise import _find_duplicate
    episode_ids: list[str] = []
    player_ids: list[str] = []
    for ent in entries:
        if ent.get("kind") == "experience":
            node = make_node("experience",
                             pattern=ent["pattern"], subject=ent.get("subject", "player"),
                             verbatim=ent.get("verbatim", ""),
                             verbatim_seq=ent.get("verbatim_seq", []),
                             tags=ent.get("tags", []),
                             significance=ent.get("significance", 0.5))
            node.ts = ts
            node.segment_id = segment_id
            node.event_seq = list(ent.get("event_seq") or event_seq)
            dup = _find_duplicate(store, node)
            if dup is not None:
                player_ids.append(dup.id)
                continue
            player_ids.append(store.add(node))
            continue
        node = make_node("episode", **{k: v for k, v in ent.items() if k != "kind"})
        node.ts = ts
        node.segment_id = segment_id
        node.event_seq = list(ent.get("event_seq") or event_seq)
        # 板级情绪键序列（T15）——召回侧物化, **不进 LLM 上下文**
        if by_seq is not None:
            node.emo_shape = _emotion_shape(node.event_seq, by_seq)
        node.aff_at_encoding = aff_at_encoding
        node.story_time = story_time
        dup = _find_duplicate(store, node)
        if dup is not None:
            episode_ids.append(dup.id)
            continue
        episode_ids.append(store.add(node))
    return episode_ids, player_ids


def _round_b_material(store: WikiStoreV2, episode_ids: list[str],
                      local_of: dict[str, str],
                      embed_fn: EmbedFn | None,
                      *, char_id: str = "") -> str:
    """Round B 输入: 新经历摘要 + 每条引擎候选提示（板块 5）。

    每条 episode 用 main_text 走 recommend_candidates 与现有认知碰撞,
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
        head = node.narration
        if len(head) > 120:
            head = head[:120] + "…"
        title = node.title or "（无题）"
        lines.append(f"{node.id} 「{title}」 {head}")
        if node.verbatim:
            lines.append(f"    原话: {node.verbatim}")
        query = f"{node.narration} {node.verbatim}".strip()
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
    """
    store.restore_state(snapshot)
    return result
