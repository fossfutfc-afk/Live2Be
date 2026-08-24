# -*- coding: utf-8 -*-
"""记忆巩固（consolidation）— 睡眠整合（Brain 算法, DESIGN_BRAIN.md）。

对应脑科学: 记忆巩固（memory consolidation）——睡眠中把新经历整合进长期记忆。
本项目即: **brain 是算法**——加载 session 时, 把该 session 的 events.jsonl
（episodic）+ 视觉记忆（gallery prompts）喂给主 LLM 一次调用, 提炼出
facts/beliefs/relations, 生成**该 session 自己的 wiki**（平行世界, 无跨 session
归并/迁移）。

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
from datetime import datetime
from pathlib import Path

from core.session import SessionStore
from core.session.renderer import render_timeline
from core.brain.hippocampus import WikiStore, _empty_wiki
from llm.prompts import load_prompt

logger = logging.getLogger(__name__)

#: 条目重要性 clamp 边界
_IMP_MIN, _IMP_MAX = 0.0, 1.0
#: tags 上限（防膨胀）
_MAX_TAGS = 5


def digest_session(
    llm,
    data_root: str | Path,
    char_id: str,
    session_id: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> dict | None:
    """记忆巩固: 本 session 事件流 + 视觉记忆 → 主 LLM 提炼 → 本 session 的 wiki。

    brain 是算法: 输入本 session 的 events.jsonl, 输出该 session 自己的 wiki
    （平行世界, 无跨 session 归并）。加载 session 时调用（resume 注入用）。

    Returns:
        本 session 的 wiki dict（已落盘 sessions/{id}/brain/wiki.json）;
        空会话（无内容事件）/ LLM 失败 / 输出无效 → None（宁缺勿错, 不阻断）。
    """
    store = SessionStore(data_root)
    ws = WikiStore(data_root)

    events = store.events(char_id, session_id)
    content_events = [e for e in events if not e.is_marker]
    if not content_events:
        logger.info("digest 跳过: 会话 %s 无内容事件", session_id)
        return None

    # 输入: 叙事时间线 + 视觉记忆（本会话 l2d 事件的 gallery prompts）
    timeline = render_timeline(events)
    visuals = _collect_visual_prompts(events)
    user_msg = _build_user_message(timeline, visuals)

    system = load_prompt("digest")
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
    except Exception as e:                           # noqa: BLE001 — 失败降级
        logger.warning("digest LLM 调用失败, 跳过本会话: %s", e)
        return None

    cleaned = _clean_output(resp)
    if cleaned is None:
        logger.warning("digest 输出无效（非 dict/无有效条目）, 跳过本会话: %s", session_id)
        return None

    # 本 session 的 wiki 落盘
    wiki = _empty_wiki(session_id)
    wiki.update(cleaned)
    wiki["updated_at"] = datetime.now().isoformat()
    try:
        ws.save(char_id, session_id, wiki)
    except Exception as e:                           # noqa: BLE001 — 落盘失败降级
        logger.warning("digest 落盘失败: %s", e)
        return None
    return wiki


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


def _build_user_message(timeline: str, visuals: list[str]) -> str:
    parts = [f"【本段互动时间线】\n{timeline}"]
    if visuals:
        parts.append("【本段生成的画面描述（视觉记忆）】\n" +
                     "\n".join(f"- {v}" for v in visuals))
    return "\n\n".join(parts)


def _clean_output(resp) -> dict | None:
    """校验/清洗 LLM 输出（坏字段丢弃, 宁缺勿错）。非 dict → None。"""
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
