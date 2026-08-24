# -*- coding: utf-8 -*-
"""记忆再巩固（reconsolidation）— 记忆修订（Brain 模块, DESIGN_BRAIN.md §1.4）。

对应脑科学: 记忆再巩固（memory reconsolidation）——记忆被唤起/重新整合时会按
新现实修订。本项目即: 检测到人设卡被修改（config 哈希 ≠ 角色级 wiki.
character_hash）→ 让主 LLM 按新设定**保守修订**旧记忆（只改冲突项, 保留其余）。

失败处理: 重试 MAX_WIKI_RETRIES 次, 仍失败 → 返回 None（调用方降级: 旧 wiki 标
stale 不注入, 不阻塞新会话——wiki 是派生视图可重算）。

用法（调用方 = 变更检测, 见 DESIGN_BRAIN.md §1.3/§1.4）:
    from core.brain.reconsolidation import migrate_wiki
    new_wiki = migrate_wiki(llm, data_root, char_id, character_prompt, new_hash)
    if new_wiki is not None:
        ws.save_char_wiki(char_id, new_wiki)        # 已含新 character_hash
    else:
        # 降级: 旧 wiki 标 stale 不注入（下次会话再试）
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from core.brain.consolidation import _clean_entries, _clean_relations
from core.brain.hippocampus import WikiStore, _empty_char_wiki
from llm.prompts import load_prompt

logger = logging.getLogger(__name__)

#: 迁移重试上限（耗尽 → 降级 stale）
MAX_WIKI_RETRIES = 3


def migrate_wiki(
    llm,
    data_root: str | Path,
    char_id: str,
    character_prompt: str,
    new_character_hash: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 1536,
) -> dict | None:
    """记忆再巩固: 人设变更 → 主 LLM 保守修订旧记忆（DESIGN_BRAIN.md §1.4）。

    Args:
        character_prompt: 新人设的完整渲染（char.build_prompt 输出）——LLM 判断
           哪些旧记忆与新设定冲突。
        new_character_hash: 新 config 哈希（修订后写入, 下次检测即一致）。

    Returns:
        修订后的**角色级 wiki**（含新 character_hash, 可直接 save_char_wiki）;
        重试耗尽/输出无效 → None（调用方降级 stale）。
    """
    ws = WikiStore(data_root)
    old = ws.load_char_wiki(char_id)
    if not old.get("facts") and not old.get("beliefs") and not old.get("relations"):
        # 无旧记忆可修订 → 直接返回新空模板（含新 hash）
        wiki = _empty_char_wiki(char_id, character_hash=new_character_hash)
        wiki["updated_at"] = datetime.now().isoformat()
        return wiki

    user_msg = _build_user_message(character_prompt, old)
    system = load_prompt("wiki_migrate")
    last_err: Exception | None = None
    for attempt in range(MAX_WIKI_RETRIES):
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
        except Exception as e:                           # noqa: BLE001
            last_err = e
            logger.warning("migrate LLM 调用失败（第 %d/%d 次）: %s",
                           attempt + 1, MAX_WIKI_RETRIES, e)
            continue

        cleaned = _clean_output(resp)
        if cleaned is None:
            last_err = RuntimeError("迁移输出无效")
            logger.warning("migrate 输出无效（第 %d/%d 次）", attempt + 1, MAX_WIKI_RETRIES)
            continue
        return _assemble(ws, char_id, cleaned, new_character_hash)

    logger.warning("migrate 重试耗尽, 旧记忆将标 stale: %s", last_err)
    return None


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------

def _build_user_message(character_prompt: str, old_wiki: dict) -> str:
    old_text = _wiki_to_text(old_wiki)
    return (f"【新设定】\n{character_prompt}\n\n"
            f"【旧记忆】\n{old_text}")


def _wiki_to_text(wiki: dict) -> str:
    lines = [f"- summary: {wiki.get('summary', '') or '（无）'}"]
    for label, key in (("facts", "facts"), ("beliefs", "beliefs"), ("relations", "relations")):
        items = wiki.get(key, []) or []
        if not items:
            continue
        lines.append(f"- {label}:")
        for it in items:
            imp = it.get("importance", "?")
            tags = it.get("tags", [])
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            if label == "relations":
                lines.append(f"    · {it.get('subject')}→{it.get('object')}: "
                             f"{it.get('relation')}（{it.get('note', '')}）")
            else:
                lines.append(f"    · {it.get('content', '')}（imp={imp}{tag_str}）")
    return "\n".join(lines)


def _clean_output(resp) -> dict | None:
    """校验/清洗迁移输出（复用 consolidation 清洗; 非 dict/全空 → None）。"""
    if not isinstance(resp, dict):
        return None
    summary = resp.get("summary", "")
    facts = _clean_entries(resp.get("facts"))
    beliefs = _clean_entries(resp.get("beliefs"))
    relations = _clean_relations(resp.get("relations"))
    if not (facts or beliefs or relations):
        return None                       # 全删光了 → 无效（保守修订不该清空全部）
    out: dict = {"facts": facts, "beliefs": beliefs, "relations": relations}
    if isinstance(summary, str) and summary.strip():
        out["summary"] = summary.strip()
    return out


def _assemble(ws: WikiStore, char_id: str, cleaned: dict, new_hash: str) -> dict:
    """组装修订后角色级 wiki: 保留结构字段 + 新 character_hash + 旧 digested_through_ts。"""
    old = ws.load_char_wiki(char_id)
    wiki = _empty_char_wiki(char_id, character_hash=new_hash)
    wiki.update(cleaned)
    wiki["digested_through_ts"] = old.get("digested_through_ts")
    wiki["updated_at"] = datetime.now().isoformat()
    return wiki
