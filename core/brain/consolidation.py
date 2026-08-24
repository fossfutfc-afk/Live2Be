# -*- coding: utf-8 -*-
"""记忆巩固（consolidation）— 睡眠整合（Brain 算法, DESIGN_BRAIN.md v3.1）。

对应脑科学: 记忆巩固（memory consolidation）——睡眠中把新经历整合进长期记忆。
本项目即: **brain 是算法**——加载/恢复 session 时, 把该 session 新增的事件
（seq > digested_seq, 增量）+ 视觉记忆 + 联想旧记忆（轻量召回 + 随机摘段）喂给
主 LLM 一次调用, 提炼出 facts/beliefs/relations, 增量合并进**该 session 自己的
wiki**（平行世界, 无跨 session 归并/迁移）。

增量（v3.1）: wiki 记 digested_seq——无新增事件 → 0 次 LLM 调用直接返回旧 wiki;
只有新增才提炼, 输出新增条目 → 引擎合并（同 content 去重, importance 取高）。
联想（v3.1）: 新旧碰撞出成长——"今天约会 + 想起儿时孤独 → 从孤独走向被爱"。

触发: 加载/恢复 session 时（resume 注入用）——不是每轮, 控成本。
失败: 静默降级（logger.warning + return None, 不阻断主流程——wiki 是派生视图,
       events.jsonl 唯一真源, 可重算）。

用法:
    from core.brain.consolidation import digest_session
    wiki = digest_session(llm, data_root, "igusa_haruka", session_id)
    # 成功 → 本 session 的 wiki dict（已落盘）; 空会话/失败 → None
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from pathlib import Path

from core.session import SessionStore
from core.session.renderer import render_timeline
from core.brain.hippocampus import WikiStore
from core.brain.recall import recall_related
from core.common.errors import err
from contract import build_digest_schema
from llm.prompts import load_prompt

logger = logging.getLogger(__name__)

#: 条目重要性 clamp 边界
_IMP_MIN, _IMP_MAX = 0.0, 1.0
#: tags 上限（防膨胀）
_MAX_TAGS = 5
#: digest LLM 调用重试上限（防偶发空响应/坏 JSON; 耗尽 → 降级 None）
MAX_DIGEST_RETRIES = 3


def digest_session(
    llm,
    data_root: str | Path,
    char_id: str,
    session_id: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    use_random_recall: bool = True,
    character_prompt: str = "",
) -> dict | None:
    """增量 + 联想 digest: 本 session 新增事件 → 主 LLM 提炼 → 合并进本 session 的 wiki。

    brain 是算法: 输入本 session 的 events.jsonl, 输出该 session 自己的 wiki
    （平行世界, 无跨 session 归并）。加载/恢复 session 时调用（resume 注入用）。

    增量: wiki.digested_seq 记录上次消化到的 seq——无新增 → 0 次 LLM 调用;
    联想: 新增剧情 + 回想起来的旧记忆（轻量召回 + 随机摘段）→ 综合出深层成长。

    Returns:
        本 session 的 wiki dict（已落盘 sessions/{id}/brain/wiki.json）;
        无事件 / LLM 失败 / 输出无效 → None（宁缺勿错, 不阻断）。
    """
    store = SessionStore(data_root)
    ws = WikiStore(data_root)

    events = store.events(char_id, session_id)
    if not events:
        logger.info("digest 跳过: 会话 %s 无事件", session_id)
        return None

    wiki = ws.load(char_id, session_id)
    digested_seq = int(wiki.get("digested_seq", 0) or 0)

    # 增量: 只提炼 seq > digested_seq 的新增内容事件（marker 不算新增, 但 seq 推进）
    new_events = [e for e in events if e.seq > digested_seq and not e.is_marker]
    if not new_events:
        return wiki                       # 无新增 → 旧 wiki（0 次 LLM 调用）

    # 输入: 新增时间线 + 视觉记忆 + 联想（轻量召回 + 双通道回忆）+ 人设锚点 + 已有记忆概要
    timeline = render_timeline(new_events)
    visuals = _collect_visual_prompts(new_events)
    recalled = recall_related(wiki, timeline)
    random_seg = _random_segment(events, digested_seq, wiki) if use_random_recall else None
    user_msg = _build_user_message(timeline, visuals, recalled, random_seg,
                                   wiki, character_prompt)

    # 契约渲染: digest.md 的 {{output_schema}} 占位 ← build_digest_schema（单源真值）
    system = load_prompt("digest").replace("{{output_schema}}", build_digest_schema())
    resp = None
    last_err: Exception | None = None
    for attempt in range(MAX_DIGEST_RETRIES):
        try:
            resp = llm.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format="json_object",
            )
            break
        except Exception as e:                       # noqa: BLE001 — 重试, 耗尽后降级
            last_err = e
            logger.warning(err("DigestFailed",
                               f"LLM 调用失败（第 {attempt + 1}/{MAX_DIGEST_RETRIES} 次）: {e}"))
    if resp is None:
        logger.warning(err("DigestFailed", f"重试耗尽, 跳过本会话: {last_err}"))
        return None

    cleaned = _clean_output(resp)
    if cleaned is None:
        logger.warning(err("DigestFailed",
                           f"输出无效（非 dict/无有效条目）, 跳过本会话: {session_id}"))
        return None

    # 增量合并: 旧条目保留 + 新条目（同 content 去重, importance 取高）
    merged = _merge_new(wiki, cleaned)
    merged["digested_seq"] = max(e.seq for e in events)   # 推进到最新 seq（含 marker）
    merged["updated_at"] = datetime.now().isoformat()
    try:
        ws.save(char_id, session_id, merged)
    except Exception as e:                           # noqa: BLE001 — 落盘失败降级（err 格式）
        logger.warning(err("DigestFailed", f"落盘失败: {e}"))
        return None
    return merged


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------

def _collect_visual_prompts(events) -> list[str]:
    """本会话视觉记忆: l2d 事件的 gallery png → 同名 json 的 prompt（DESIGN_BRAIN §1.7）。"""
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


def _build_user_message(timeline: str, visuals: list[str],
                        recalled: list[str], random_seg: str | None,
                        wiki: dict, character_prompt: str = "") -> str:
    """组装 digest 输入（v3.2: 新增 + 视觉记忆 + 联想 + 人设锚点 + 已有记忆概要）。"""
    parts = [f"【本段新增互动（上次整理之后的部分）】\n{timeline}"]
    if visuals:
        parts.append("【本段生成的画面描述（视觉记忆）】\n" +
                     "\n".join(f"- {v}" for v in visuals))
    if recalled:
        parts.append("【回想起来的旧记忆（可能相关, 供联想）】\n" +
                     "\n".join(f"- {r}" for r in recalled))
    if random_seg:
        parts.append(f"【偶然想起的旧日片段】\n{random_seg}")
    if character_prompt:
        parts.append(f"【角色人设（锚点）】\n{character_prompt}")
    summary = wiki.get("summary", "")
    parts.append("【你已有的记忆（summary）】\n" +
                 (summary if isinstance(summary, str) and summary.strip()
                  else "（暂无——本 session 第一次消化）"))
    return "\n\n".join(parts)


def _random_segment(events, digested_seq: int, wiki: dict | None = None,
                    rng=None) -> str | None:
    """双通道回忆摘段（DESIGN_BRAIN.md §3.1）: 情感保底 + 遗忘曲线。

    回忆概率 = 时间衰减 × 情感/重要性:
    - 珍贵通道（30%）: wiki 高 importance 条目——**永不衰减（保底）**,
      初遇/告白/约定都在这里（玩家执着的记忆永存）; wiki 无高 importance → None
    - 日常通道（70%）: 历史事件按对数正态(年龄)加权摘原文——遗忘曲线
      （近期高峰 + 长尾, 偶尔想起很久以前）; "越复杂越像人类"

    参数（per 角色可配, 呼应 CLAUDE.md §3.2.3 衰减系数设计）:
        precious_ratio=0.3      珍贵通道概率（情感重的角色调高）
        importance_threshold=0.8 importance 门槛
        mu=0.0 / sigma=1.5      对数正态位置/尺度（衰减快慢; 天然呆角色 σ 大）
    """
    precious_ratio = 0.3
    importance_threshold = 0.8
    mu, sigma = 0.0, 1.5
    if (rng or random).random() < precious_ratio:
        return _precious_recall(wiki, importance_threshold)
    return _daily_recall(events, digested_seq, mu, sigma, rng)


def _precious_recall(wiki: dict | None, threshold: float) -> str | None:
    """珍贵通道: importance ≥ 阈值的条目, importance 加权选 1 条（情感保底）。"""
    if not wiki:
        return None
    precious = [
        e for e in wiki.get("facts", []) + wiki.get("beliefs", [])
        if isinstance(e, dict)
        and float(e.get("importance", 0) or 0) >= threshold
        and isinstance(e.get("content", ""), str) and e["content"]
    ]
    if not precious:
        return None
    weights = [max(float(e.get("importance", 0.5) or 0.5), 0.1) for e in precious]
    e = random.choices(precious, weights=weights, k=1)[0]
    return f"（重要回忆）{e['content']}"


def _daily_recall(events, digested_seq: int, mu: float, sigma: float,
                  rng=None) -> str | None:
    """日常通道: 历史事件按对数正态(年龄)加权摘 1 段原文（遗忘曲线）。"""
    import math
    hist = [e for e in events
            if e.seq <= digested_seq and not e.is_marker and e.type in ("mmt", "bond")]
    if not hist:
        return None
    weights = []
    for e in hist:
        age = max(digested_seq - e.seq, 0)           # 0 = 最新
        x = math.log(age + 1)                        # 对数年龄（避免 log 0）
        w = math.exp(-((x - mu) ** 2) / (2 * sigma * sigma)) / (age + 1)
        weights.append(max(w, 1e-9))
    e = (rng or random).choices(hist, weights=weights, k=1)[0]
    if e.type == "mmt":
        return (f"（旧日片段）玩家: {e.payload.get('player', '')}"
                f"｜角色: {e.payload.get('reply', '')}")
    paras = e.payload.get("paragraphs", []) or []
    texts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in paras]
    text = " ".join(t for t in texts if t)
    return f"（旧日片段）{text[:150]}" if text else None


def _merge_new(old: dict, cleaned: dict) -> dict:
    """增量合并: 旧条目保留 + 新条目（同 content 去重, importance 取高, tags union）。

    同一世界线的时间推进——旧积木不动, 往上加新块（"搭积木"）。
    """
    merged = dict(old)
    merged["facts"] = _merge_entries(old.get("facts", []), cleaned.get("facts", []))
    merged["beliefs"] = _merge_entries(old.get("beliefs", []), cleaned.get("beliefs", []))
    merged["relations"] = _merge_relations(old.get("relations", []), cleaned.get("relations", []))
    s = cleaned.get("summary", "")
    if isinstance(s, str) and s.strip():
        merged["summary"] = s.strip()
    return merged


def _merge_entries(existing: list, new: list) -> list:
    """facts/beliefs 合并: content 精确去重, importance 取 max, tags union。"""
    by_content: dict[str, dict] = {}
    for e in list(existing) + list(new):
        if not isinstance(e, dict):
            continue
        content = e.get("content", "")
        if not isinstance(content, str) or not content:
            continue
        cur = by_content.get(content)
        if cur is None:
            by_content[content] = dict(e)
        else:
            cur["importance"] = max(
                float(cur.get("importance", 0) or 0), float(e.get("importance", 0) or 0))
            tags = set(cur.get("tags", []) or []) | set(e.get("tags", []) or [])
            if tags:
                cur["tags"] = sorted(t for t in tags if isinstance(t, str))
    return list(by_content.values())


def _merge_relations(existing: list, new: list) -> list:
    """relations 合并: (subject,object,relation) 去重, note 取新（后者覆盖）。"""
    by_key: dict[tuple, dict] = {}
    for r in list(existing) + list(new):
        if not isinstance(r, dict):
            continue
        key = (r.get("subject", ""), r.get("object", ""), r.get("relation", ""))
        if not any(key):
            continue
        by_key[key] = dict(r)             # 后者（新会话）覆盖 note
    return list(by_key.values())


def _clean_output(resp) -> dict | None:
    """校验/清洗 LLM 输出（坏字段丢弃, 宁缺勿错）。非 dict → None。

    结构边界对齐契约 build_digest_schema（contract/schema.py, 单源真值）;
    本函数是内容净化（importance clamp / tags 过滤 / 空 content 丢弃）。
    """
    if not isinstance(resp, dict):
        return None
    summary = resp.get("summary", "")
    facts = _clean_entries(resp.get("facts"))
    beliefs = _clean_entries(resp.get("beliefs"))
    relations = _clean_relations(resp.get("relations"))
    if not (facts or beliefs or relations) and not (isinstance(summary, str) and summary.strip()):
        return None                       # 全空 → 视为无效（或合法空？——防御: 落空模板）
    out: dict = {"facts": facts, "beliefs": beliefs, "relations": relations}
    if isinstance(summary, str) and summary.strip():
        out["summary"] = summary.strip()
    return out


def _clean_entries(raw) -> list[dict]:
    """facts/beliefs 清洗: content 非空 str, importance clamp 0~1, tags 过滤截断。"""
    out: list[dict] = []
    for e in raw or []:
        if not isinstance(e, dict):
            continue
        content = e.get("content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        item: dict = {"content": content.strip()}
        try:
            item["importance"] = max(_IMP_MIN, min(_IMP_MAX, float(e.get("importance", 0.5))))
        except (TypeError, ValueError):
            item["importance"] = 0.5
        tags = [t.strip() for t in e.get("tags", []) if isinstance(t, str) and t.strip()]
        if tags:
            item["tags"] = tags[:_MAX_TAGS]
        out.append(item)
    return out


def _clean_relations(raw) -> list[dict]:
    """relations 清洗: subject/object/relation 非空 str; note 可选。"""
    out: list[dict] = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        subj, obj, rel = r.get("subject", ""), r.get("object", ""), r.get("relation", "")
        if not (isinstance(subj, str) and isinstance(obj, str) and isinstance(rel, str)):
            continue
        if not (subj.strip() and obj.strip() and rel.strip()):
            continue
        item = {"subject": subj.strip(), "object": obj.strip(), "relation": rel.strip()}
        note = r.get("note", "")
        if isinstance(note, str) and note.strip():
            item["note"] = note.strip()
        out.append(item)
    return out
