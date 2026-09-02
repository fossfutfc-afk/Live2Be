"""digest.py — digest v2 两轮管线（AGENT_BRAIN.md §3 / 板块 4a）。

两轮（2026-09-02 定稿; 吸收 A-MEM 逐条对齐 + AgentGal 两轮结构 + 用户拍板）:
    Round A「记录员」: 只看新时间线 → 浓缩值得记住的经历（registry schema(record)
                      + parse_round_a → 引擎建 episode 节点, 内存暂存）
    Round B「理解者」: 新经历 + 现有认知（本地 id 渲染）→ 决策表 decisions
                      （touch=印证 / update=深化改写+history / add=新建）
                      → apply_decisions 执行 → 原子提交

编排（digest_segment）:
    1. 增量: new_events = seq > store.digested_seq（无新增 → 0 次 LLM 调用）
    2. 公共输入: 时间线(带 seq) + 视觉记忆 + 人设锚点（A 用）; 时间线同时供 B 的
       evidence quote 逐字引用
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
from core.brain.wiki_v2.revise import apply_decisions
from core.brain.wiki_v2.store import WikiStoreV2
from core.session.renderer import render_timeline
from llm.prompts import load_prompt

logger = logging.getLogger(__name__)

#: 反馈重试（parse/结构被拒 → 带 assistant 原文回灌重试 1 次）
MAX_FEEDBACK_RETRIES = 1
#: evidence 置信度阈值（低于 → 丢弃, 宁缺勿错）
EVIDENCE_THRESHOLD = 0.7
#: B 轮认知渲染上限（本地 id 数量; 排序: 珍贵档先）
COGNITION_CAP = 12
#: 好感 delta clamp 边界
_AFF_MIN, _AFF_MAX = 0, 100


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
    temperature: float = 0.3,
    max_tokens: int = 8192,
    evidence_threshold: float = EVIDENCE_THRESHOLD,
    deadline_seconds: float = 150.0,
    extra_body: dict | None = None,
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
        extra_body: 请求附加字段。None → {"reasoning_effort": "low"}——
                   推理模型（v4-flash 类）默认长考失控（reasoning 吃光输出预算 →
                   空输出/截断; 实验 2026-09-02 N=5×2: low 档 5/5 合格、推理降 10×、
                   62s→17s, 质量保留; medium 档 1/3 死在规则校验）
        deadline_seconds: 全程时间预算（A+B+反馈）; 撞上 → 判失败回滚
    """
    new_events = [e for e in events
                  if e.seq > store.digested_seq
                  and not e.is_marker and e.type != "affection"]
    if not new_events:
        return DigestResult(ok=True)                     # 无新增 → 0 次 LLM 调用
    interact_max = max(e.seq for e in new_events)
    result = DigestResult(ok=False)
    snapshot = store.clone_state()                       # 原子性: 失败 → 回滚

    timeline = render_timeline(new_events, include_seq=True)
    if visuals is None:
        visuals = _collect_visual_prompts(new_events)
    now_ts = datetime.now().isoformat(timespec="seconds")
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
        ])
        entries, resp_a = _round_call(
            llm, system_a, user_a,
            model=model, temperature=temperature, max_tokens=max_tokens,
            extra_body=extra_body, deadline=deadline, label="round_a",
            parse_fn=digest_registry.parse_round_a, result=result)
        if entries is None:
            return _rollback(store, snapshot, result)
        episode_ids = _create_episodes(
            store, entries, ts=now_ts, segment_id=segment_id,
            event_seq=[interact_max])

        # ── Round B: 理解者 ──
        cognitions, id_map = _render_cognitions(store, cap=COGNITION_CAP)
        system_b = load_prompt("digest_v2_round_b").replace(
            "{{digest_schema}}", digest_registry.build_schema(PHASE_UNDERSTAND))
        user_b = _join_sections([
            ("本次新经历", _render_episodes(store, episode_ids)),
            ("本段时间线（evidence 的 quote 必须逐字引用这里）", timeline),
            ("现有认知", cognitions),
            ("角色人设（锚点）", character_prompt),
        ])
        rows, resp_b = _round_call(
            llm, system_b, user_b,
            model=model, temperature=temperature, max_tokens=max_tokens,
            extra_body=extra_body, deadline=deadline, label="round_b",
            parse_fn=lambda r: digest_registry.parse_round_b(
                r, episode_ids=set(episode_ids), target_ids=set(id_map)),
            result=result)
        if rows is None:
            return _rollback(store, snapshot, result)
        apply_decisions(store, rows, id_map=id_map, ts=now_ts,
                        segment_id=segment_id, event_seq=[interact_max])
    except ValueError as e:                              # store 层拒绝 → 回滚
        result.errors.append(str(e))
        return _rollback(store, snapshot, result)

    # ── 成功: 提交（节点落盘 + 水位推进）──
    result.ok = True
    result.created = episode_ids
    result.evidence = _clean_evidence(resp_b.get("evidence"), evidence_threshold)
    result.affection_delta = _clamp_aff(resp_b.get("affection_exp_delta"))
    store.save()
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
                                  label=label)
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

def _create_episodes(store: WikiStoreV2, entries: list[dict], *, ts: str,
                     segment_id: str, event_seq: list[int]) -> list[str]:
    """Round A 条目 → episode 节点（引擎字段归属——确定性归引擎, 防幻觉）。

    4a: 本段 episode 的 event_seq 统一 [interact_max]（段级溯源）; 每段内的
    逐事件溯源留给时间系统（蓝图 §9 计划）。
    dedupe: (kind, event_seq, 主文本) 命中已有节点 → 复用 id（崩溃窗口重跑防双写）。
    """
    from core.brain.wiki_v2.revise import _find_duplicate
    ids: list[str] = []
    for ent in entries:
        node = make_node("episode", **ent)
        node.ts = ts
        node.segment_id = segment_id
        node.event_seq = list(event_seq)
        dup = _find_duplicate(store, node)
        if dup is not None:
            ids.append(dup.id)
            continue
        ids.append(store.add(node))
    return ids


def _render_episodes(store: WikiStoreV2, ids: list[str]) -> str:
    """Round B 输入: 新经历摘要（真实 id; title + 正文截断 + 原话）。"""
    lines: list[str] = []
    for nid in ids:
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
    return "\n".join(lines) or "（无）"


def _render_cognitions(store: WikiStoreV2, cap: int) -> tuple[str, dict[str, str]]:
    """Round B 输入: 现有认知渲染（本地 id u0001..; 排序: significance 降序）。

    渲染层只挑稳定认知（belief/experience）; episode 是流水不参与组织（B 不修细节）。
    id_map: 本地 id → 真实 id（执行器解析用; parse 层只认本地 id——防 LLM 猜真实 id）。
    """
    nodes = [n for n in store.all() if n.kind in ("belief", "experience")]
    nodes.sort(key=lambda n: (-n.significance, n.id))
    lines: list[str] = []
    id_map: dict[str, str] = {}
    for i, n in enumerate(nodes[:cap], start=1):
        local = f"u{i:04d}"
        id_map[local] = n.id
        kind_tag = f"[{n.kind}]"
        body = n.content if n.kind == "belief" else (
            f"{n.pattern}（次数 {n.count}）" if n.count > 1 else n.pattern)
        if len(body) > 100:
            body = body[:100] + "…"
        sig = f", sig {n.significance:.2f}" if n.is_precious else ""
        subject = f" 关于 {n.subject}:" if n.subject else ""
        lines.append(f"{local} {kind_tag}{subject} {body}{sig}")
    if not lines:
        return "（尚无稳定认知——这是第一次理解, 直接 add）", id_map
    return "\n".join(lines), id_map


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


def _rollback(store: WikiStoreV2, snapshot: dict, result: DigestResult) -> DigestResult:
    """回滚内存态（失败 → 零残留; 水位未推进, 磁盘未动）。"""
    store.restore_state(snapshot)
    return result
