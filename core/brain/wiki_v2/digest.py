"""digest.py — digest v2 管线（AGENT_BRAIN.md §3 Step 1-3 / M3）。

编排（与 legacy consolidation 对等的新实现; legacy 不动, 最后切换）:
    digest_segment(store, llm, events, ...)
      1. 增量: new_events = seq > store.digested_seq（无新增 → 0 次 LLM 调用）
      2. 输入: 时间线(带 seq 标签) + 视觉记忆 + 三通道召回子图(组织视图) + 锚点
      3. LLM 调用: digest_v2.md + build_digest_schema_v2（json_object）
      4. 引擎执行: **新经历统一走 revisions 的 create**（entries 数组废案——ref 机制
         让新 episode 链接新 belief 成为可能）→ apply_revision_package 原子执行;
         **校验失败 → 反馈回灌重试 1 次**（修订契约的闭环）
      5. evidence 校验（置信度阈值/quote 逐字）→ 返回（罗盘应用后置, 无罗盘则丢弃）
      6. affection delta 返回（事件幂等写由调用方——运行时集成层, M5）
      7. 成功 → 推进 store.meta.digested_seq + save_meta（失败不推进 → 可重算）

失败: 静默降级（logger.warning + DigestResult(ok=False)——wiki 是派生视图,
events.jsonl 唯一真源, 可重算）。
"""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from contract import build_digest_schema_v2
from core.brain.wiki_v2.recall import EmbedFn, recall_subgraph
from core.brain.wiki_v2.render import render_organize_view
from core.brain.wiki_v2.revise import RevisionResult, apply_revision_package
from core.brain.wiki_v2.store import WikiStoreV2
from core.common import err
from core.session.renderer import render_timeline
from llm.prompts import load_prompt

logger = logging.getLogger(__name__)

#: LLM 调用重试（偶发空响应/坏 JSON; 耗尽 → 降级 None）
MAX_CALL_RETRIES = 3
#: 校验反馈重试（修订被拒 → 带错误回灌重试 1 次）
MAX_FEEDBACK_RETRIES = 1
#: evidence 置信度阈值（低于 → 丢弃, 宁缺勿错）
EVIDENCE_THRESHOLD = 0.7
#: 好感 delta clamp 边界
_AFF_MIN, _AFF_MAX = 0, 100


@dataclass
class DigestResult:
    """一次 digest 的结果。"""

    ok: bool
    errors: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)     # 新条目 id
    revision: RevisionResult | None = None
    evidence: list[dict] = field(default_factory=list)
    affection_delta: int = 0
    llm_calls: int = 0


def digest_segment(
    store: WikiStoreV2,
    llm,
    events: list,
    *,
    character_prompt: str = "",
    visuals: list[str] | None = None,
    k_sim: int = 5,
    n_precious: int = 2,
    n_random: int = 1,
    embed_fn: EmbedFn | None = None,
    rng: random.Random | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    evidence_threshold: float = EVIDENCE_THRESHOLD,
) -> DigestResult:
    """增量 digest: 新事件 → LLM 提炼+组织 → 原子落盘（条目+修订）→ 推进水位。

    Args:
        store: 目标世界线的图式 wiki（meta.digested_seq 是水位）
        llm: 兼容 llm.chat(messages, temperature=, max_tokens=, response_format=) 的客户端
        events: 该世界线完整事件流（Event 列表; 增量由水位切）
        character_prompt: 人设锚点文本（空 → 不注入该段）
        visuals: 视觉记忆 prompt 列表; None → 从事件流 l2d 事件自动收集
    """
    new_events = [e for e in events
                  if e.seq > store.digested_seq
                  and not e.is_marker and e.type != "affection"]
    if not new_events:
        return DigestResult(ok=True)                     # 无新增 → 0 次 LLM 调用
    interact_max = max(e.seq for e in new_events)
    all_seq = {e.seq for e in new_events}
    result = DigestResult(ok=False)

    timeline = render_timeline(new_events, include_seq=True)
    if visuals is None:
        visuals = _collect_visual_prompts(new_events)
    subgraph = recall_subgraph(
        store, query=timeline, k_sim=k_sim, n_precious=n_precious,
        n_random=n_random, embed_fn=embed_fn, rng=rng)
    scope = {n.id for n in subgraph}
    organize = render_organize_view(subgraph, timeline=timeline)

    system = load_prompt("digest_v2").replace(
        "{{output_schema}}", build_digest_schema_v2())

    feedback = ""
    for round_i in range(MAX_FEEDBACK_RETRIES + 1):
        user_msg = _build_user_message(timeline, visuals, organize,
                                       character_prompt, feedback)
        resp = _call_llm(llm, system, user_msg, temperature, max_tokens, result)
        if resp is None:
            return result                               # 调用重试耗尽 → 降级
        result.llm_calls += 1
        if not isinstance(resp, dict):
            result.errors.append("LLM 输出非 JSON 对象")
            return result
        prepared = _prepare_revisions(resp.get("revisions"), interact_max, all_seq)
        rev = apply_revision_package(store, prepared, subgraph_ids=scope)
        if rev.ok:
            break
        if round_i < MAX_FEEDBACK_RETRIES:
            feedback = ("【引擎校验反馈（上一轮输出被整包拒绝, 请修正后重新输出完整 JSON）】\n"
                        + "\n".join(f"- {e}" for e in rev.errors))
            continue
        result.errors.extend(rev.errors)
        return result

    # ── 成功: 收集产物 → 推进水位 ──
    result.ok = True
    result.created = list(rev.created.values())
    result.revision = rev
    result.evidence = _clean_evidence(resp.get("evidence"), evidence_threshold)
    result.affection_delta = _clamp_aff(resp.get("affection_exp_delta"))
    store.meta["digested_seq"] = max((e.seq for e in events), default=interact_max)
    store.save_meta()
    return result


# ---------------------------------------------------------------------------
# 输入拼装 / LLM 调用
# ---------------------------------------------------------------------------

def _build_user_message(timeline: str, visuals: list[str], organize: str,
                        character_prompt: str, feedback: str) -> str:
    parts = [f"【本段新增互动】\n{timeline}"]
    if visuals:
        parts.append("【本段生成的画面描述（视觉记忆）】\n"
                     + "\n".join(f"- {v}" for v in visuals))
    if organize:
        parts.append(f"【当前记忆子图（供组织决策）】\n{organize}")
    if character_prompt:
        parts.append(f"【角色人设（锚点）】\n{character_prompt}")
    if feedback:
        parts.append(feedback)
    return "\n\n".join(parts)


def _call_llm(llm, system: str, user_msg: str, temperature: float,
              max_tokens: int, result: DigestResult):
    """调用 + 重试（异常 → 3 次; 耗尽 → None 降级）。"""
    last_err: Exception | None = None
    for attempt in range(MAX_CALL_RETRIES):
        try:
            return llm.chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user_msg}],
                temperature=temperature, max_tokens=max_tokens,
                response_format="json_object")
        except Exception as e:                           # noqa: BLE001
            last_err = e
            logger.warning(err("DigestFailed",
                               f"LLM 调用失败（第 {attempt + 1}/{MAX_CALL_RETRIES} 次）: {e}"))
    result.errors.append(f"LLM 调用重试耗尽: {last_err}")
    return None


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


# ---------------------------------------------------------------------------
# 引擎侧准备 / 清洗
# ---------------------------------------------------------------------------

def _prepare_revisions(raw: Any, interact_max: int, all_seq: set[int]) -> list:
    """LLM revisions → 引擎可执行形态:

    - create 的 event_seq/ts/segment_id 由引擎分配（LLM 可复制时间线 seq 溯源,
      但必须 ⊆ 本段 seq 集——否则落回 [interact_max], 防幻觉）
    """
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        r = dict(r)
        if r.get("action") == "create" and isinstance(r.get("entry"), dict):
            entry = dict(r["entry"])
            seqs = [s for s in entry.get("event_seq", [])
                    if isinstance(s, int) and s in all_seq]
            entry["event_seq"] = seqs or [interact_max]
            entry["ts"] = datetime.now().isoformat(timespec="seconds")
            entry["segment_id"] = f"seg-{interact_max}"
            r["entry"] = entry
        out.append(r)
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
