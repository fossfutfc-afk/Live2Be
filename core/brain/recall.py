# -*- coding: utf-8 -*-
"""回忆（recall）— 检索注入（Brain 模块, DESIGN_BRAIN.md §4）。

对应脑科学: 回忆/提取（recall）——把存储的记忆在需要时"想起来"并表达出来。
本项目即: 把角色级 wiki 渲染成 system prompt 的【角色记忆】段, 随五层卡一起注入。

**视角包装（v2.1 决策）**: 存储是第三人称（wiki 条目中性事实, 归并/检索靠 content
精确匹配, 人称统一才稳定）; **注入时转第一人称**——char_name 出现在条目里就替换
成"我"（"遥香第一次觉得被需要" → "我第一次觉得被需要"）, summary → "我记得那段
日子…"。依据: Perspective-Bounded Memory（arXiv 2606.25632）+ SillyTavern 实践 +
自我参照效应——角色视角的记忆注入比旁观者视角更贴角色认同。

注入量控: importance 降序 → 截断（facts/beliefs/relations 各自上限）; 空 wiki → ""。

用法:
    from core.brain.recall import build_brain_injection
    wiki = WikiStore().load_char_wiki("igusa_haruka")
    seg = build_brain_injection(wiki, char_name="遥香")   # 非空才追加进 system prompt
"""

from __future__ import annotations

#: 注入上限（importance 降序截断——token 控量）
_MAX_FACTS = 10
_MAX_BELIEFS = 5
_MAX_RELATIONS = 5


def build_brain_injection(
    wiki: dict,
    char_name: str = "",
    *,
    max_facts: int = _MAX_FACTS,
    max_beliefs: int = _MAX_BELIEFS,
    max_relations: int = _MAX_RELATIONS,
) -> str:
    """角色级 wiki → 第一人称记忆段（空 wiki → ""，零注入）。

    char_name: 条目里出现的角色叫法（display_name 或其常用简称）——替换为"我"。
    条目顺序: importance 降序后截断。
    """
    summary = wiki.get("summary", "")
    facts = _top(wiki.get("facts", []), max_facts)
    beliefs = _top(wiki.get("beliefs", []), max_beliefs)
    relations = _top(wiki.get("relations", []), max_relations)
    if not (summary or facts or beliefs or relations):
        return ""

    lines = ["【角色记忆（brain）】"]
    if isinstance(summary, str) and summary.strip():
        lines.append(f"我记得那段日子：{_me(summary, char_name)}")

    if facts:
        lines.append("\n我记得的事：")
        for f in facts:
            lines.append(f"- {_me(f.get('content', ''), char_name)}")
    if beliefs:
        lines.append("\n我心里渐渐觉得：")
        for b in beliefs:
            lines.append(f"- {_me(b.get('content', ''), char_name)}")
    if relations:
        lines.append("\n我和他们的关系：")
        for r in relations:
            obj = _me(r.get("object", ""), char_name)
            rel = r.get("relation", "")
            note = r.get("note", "")
            line = f"- 和{obj}：{rel}" if obj else f"- {rel}"
            if isinstance(note, str) and note.strip():
                line += f"（{_me(note, char_name)}）"
            lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------

def _top(entries, limit: int):
    """importance 降序截断（importance 缺失按 0 排末尾）。"""
    scored = sorted(
        (e for e in entries if isinstance(e, dict)),
        key=lambda e: float(e.get("importance", 0) or 0),
        reverse=True,
    )
    return scored[:limit]


def _me(text: str, char_name: str) -> str:
    """第三人称 → 第一人称: 条目里出现的 char_name 替换为"我"（角色记忆视角）。

    wiki 条目是"角色的记忆", 提到 char_name 基本都指角色自己——替换后
    "遥香第一次觉得被需要" → "我第一次觉得被需要"; 其他角色名（老师等）保留。
    """
    if not char_name or not text:
        return text
    return text.replace(char_name, "我")
