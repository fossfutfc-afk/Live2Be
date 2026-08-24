# -*- coding: utf-8 -*-
"""回忆（recall）— 检索注入（Brain 算法, DESIGN_BRAIN.md）。

对应脑科学: 回忆/提取（recall）——把存储的记忆在需要时"想起来"并表达出来。
本项目即: 把**本 session 的 wiki**（digest 产物）渲染成 prompt 的【角色记忆】段,
加载/恢复 session 时注入——角色记得"这个世界线"前面的事。

**视角包装（v2.1 决策）**: wiki 条目是第三人称（中性事实, digest 输出稳定）;
**注入时转第一人称**——char_name 出现在条目里就替换成"我"（"遥香第一次觉得被
需要" → "我第一次觉得被需要"）, summary → "我记得那段日子…"。依据:
Perspective-Bounded Memory（arXiv 2606.25632）+ 自我参照效应——角色视角的记忆
注入比旁观者视角更贴角色认同。

注入量控: importance 降序 → 截断（facts/beliefs/relations 各自上限）; 空 wiki → ""。

用法:
    from core.brain.recall import build_brain_injection
    wiki = WikiStore().load("igusa_haruka", session_id)
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


def recall_related(wiki: dict, new_text: str, limit: int = 3) -> list[str]:
    """轻量召回（联想 digest 用, DESIGN_BRAIN.md §3）: 从旧 wiki 条目按 tags 匹配新增剧情。

    新增剧情文本里出现某条旧记忆的 tags 关键词 → 该旧记忆"被想起"（相关联想）。
    人倾向于想起和当前事情紧密相连的东西——tags 命中即轻量相关性（零依赖,
    RAG embedding 是 Phase 2 的升级）。

    Returns: 被想起的旧记忆文本列表（facts/beliefs content + relations 描述）, 截断 limit。
    """
    recalled: list[str] = []
    for e in wiki.get("facts", []) + wiki.get("beliefs", []):
        if not isinstance(e, dict):
            continue
        tags = e.get("tags", []) or []
        content = e.get("content", "")
        hit = any(isinstance(t, str) and t and t in new_text for t in tags)
        if hit and isinstance(content, str) and content:
            recalled.append(content)
    for r in wiki.get("relations", []):
        if not isinstance(r, dict):
            continue
        obj = r.get("object", "")
        if isinstance(obj, str) and obj and obj in new_text:
            recalled.append(f"和{obj}的关系: {r.get('relation', '')}")
    return recalled[:limit]
