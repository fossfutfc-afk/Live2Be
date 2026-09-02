"""render.py — 渲染视图（AGENT_BRAIN.md §4 / M2）。

同一张图, 两种渲染（视图分工）:
    组织视图  render_organize_view   —— 喂 digest/组织 LLM
             带 id + 邻接表 + 层/显著性/矛盾标记, 供修订决策（LLM 按 id 引用）
    角色视图  render_character_view  —— 喂主剧情 LLM
             纯第一人称叙事, 无 id 无链接, 分层排序（§4.2 + 排序规则）

格式约定（决策 #7）: id 无 # 无下划线（m0003）——组织视图行首即 id, 防 markdown 标题歧义。
player experience（§4.4）: 组织视图带 [关于老师] 标记; 角色视图独立【老师的事】段。
fact（出厂记忆, 2026-09-02 修正）: 角色视图渲染为 久远的记忆/我知道的事 两段。
"""
from __future__ import annotations

from typing import Iterable

from core.brain.wiki_v2.nodes import BrainNode

#: 组织视图行首缩进（verbatim/example 续行）
_INDENT = "        "


# ---------------------------------------------------------------------------
# 组织视图（digest/组织 LLM 消费）
# ---------------------------------------------------------------------------

def render_organize_view(nodes: Iterable[BrainNode], *, timeline: str = "") -> str:
    """组织视图: 【本次新经历】时间线 + 【相关旧记忆】子图（id + 邻接表）。

    节点顺序 = 传入顺序（引擎已按显著性/召回排序）。
    """
    blocks: list[str] = []
    if timeline:
        blocks.append(f"【本次新经历】\n{timeline.strip()}")
    lines = [_organize_line(n) for n in nodes if n.id]
    if lines:
        blocks.append("【相关旧记忆（供组织决策）】\n" + "\n".join(lines))
    return "\n\n".join(blocks)


def _organize_line(node: BrainNode) -> str:
    """一行: `m0003 [episode, sig 0.80, links: m0009, c: m0005] 内容`。

    player experience 的 kind 标签带 [关于老师]; fact 带只读标记。
    """
    meta = [node.kind]
    if node.is_player_experience:
        meta[0] = "experience·关于老师"
    meta.append(f"sig {node.significance:.2f}")
    if node.kind == "experience":
        meta.append(f"count {node.count}")
    if node.links:
        meta.append("links: " + " ".join(node.links))
    if node.contradictions:
        meta.append("c: " + " ".join(node.contradictions))
    if node.kind == "fact":
        meta.append("canon 只读")
    head = f"{node.id} [{', '.join(meta)}] {_organize_text(node)}"
    extra = _organize_extra(node)
    return head + extra


def _organize_text(node: BrainNode) -> str:
    """主文本（按 kind）: narration / pattern / content。"""
    if node.kind == "episode":
        return node.narration
    if node.kind == "experience":
        return node.pattern
    return node.content


def _organize_extra(node: BrainNode) -> str:
    """续行（缩进引文）: episode 的 verbatim / experience 的 examples（最多 2 条）。

    原文已带「」时不重复包裹（防双重引号）。
    """
    quotes: list[str] = []
    if node.kind == "episode" and node.verbatim:
        quotes.append(node.verbatim)
    elif node.kind == "experience":
        quotes.extend(node.examples[:2])
    if not quotes:
        return ""
    return "\n" + "\n".join(
        f"{_INDENT}〝{q if q.startswith('「') and q.endswith('」') else f'「{q}」'}〞"
        for q in quotes)


# ---------------------------------------------------------------------------
# 角色视图（主剧情 LLM 消费, 第一人称无 id）
# ---------------------------------------------------------------------------

def render_character_view(
    nodes: Iterable[BrainNode],
    *,
    char_name: str = "",
    summary: str = "",
    cap_beliefs: int = 5,
    cap_episodes: int = 10,
    cap_player: int = 5,
    cap_facts: int = 5,
    cap_reported: int = 3,
) -> str:
    """角色注入视图: 分层排序渲染（§4.2 + 排序规则）, 空段省略。

    排序: belief 常驻（sig 降序）; episode 珍贵档优先 → ts 降序（总量 cap_episodes）;
    player experience count 降序; fact 分 experience/knowledge 两段; reported 仅无同主题时。
    fact/belief 内容做第一人称转换（char_name → 我）。
    """
    # 角色视图不依赖 id（渲染中从不出现 id）——直接按 kind/排序处理
    # observed 的 episode 进 珍贵/最近 段; reported_fact 进 我听说的 段（§4.2 排序规则）
    episodes = sorted(
        (n for n in nodes if n.kind == "episode" and n.epistemic == "observed_fact"),
        key=lambda n: (n.is_precious, n.ts or ""), reverse=True)
    episodes = episodes[:cap_episodes]
    beliefs = sorted((n for n in nodes if n.kind == "belief"),
                     key=lambda n: n.significance, reverse=True)[:cap_beliefs]
    players = sorted((n for n in nodes if n.is_player_experience),
                     key=lambda n: n.count, reverse=True)[:cap_player]
    facts_exp = sorted((n for n in nodes if n.kind == "fact"
                        and n.source == "experience"),
                       key=lambda n: n.significance, reverse=True)[:cap_facts]
    facts_know = sorted((n for n in nodes if n.kind == "fact"
                         and n.source == "knowledge"),
                        key=lambda n: n.significance, reverse=True)[:cap_facts]
    reported = [n for n in nodes if n.kind == "episode"
                and n.epistemic == "reported_fact"][:cap_reported]

    blocks: list[str] = ["【角色记忆（brain）】"]
    if summary:
        blocks.append(f"我记得那段日子：{_me(summary, char_name)}")
    precious = [n for n in episodes if n.is_precious]
    recent = [n for n in episodes if not n.is_precious]
    if precious:
        blocks.append("我记得的事（珍贵的）：\n" + "\n".join(
            _memory_line(n, char_name) for n in precious))
    if recent:
        blocks.append("最近的事：\n" + "\n".join(
            _memory_line(n, char_name) for n in recent))
    if beliefs:
        blocks.append("我心里渐渐觉得：\n" + "\n".join(
            _belief_line(n, char_name) for n in beliefs))
    if players:
        blocks.append("老师的事：\n" + "\n".join(
            f"- {_me(n.pattern, char_name)}（count {n.count}）" for n in players))
    if reported:
        blocks.append("我听说的：\n" + "\n".join(
            _reported_line(n, char_name) for n in reported))
    if facts_exp:
        blocks.append("久远的记忆：\n" + "\n".join(
            f"- {_me(n.content, char_name)}" for n in facts_exp))
    if facts_know:
        blocks.append("我知道的事：\n" + "\n".join(
            f"- {_me(n.content, char_name)}" for n in facts_know))
    return "\n\n".join(blocks)


def _reported_line(node: BrainNode, char_name: str) -> str:
    line = f"- {_me(node.narration, char_name)}"
    if node.observer:
        line += f"（听{node.observer}说的）"
    return line


def _memory_line(node: BrainNode, char_name: str) -> str:
    line = f"- {_me(node.narration, char_name)}"
    if node.verbatim:
        line += f"（「{node.verbatim}」）"
    return line


def _belief_line(node: BrainNode, char_name: str) -> str:
    content = _me(node.content, char_name)
    line = f"- 对{_me(node.subject, char_name)}：{content}" if node.subject else f"- {content}"
    if node.growth:
        line += f"（——{_me(node.growth, char_name)}）"
    return line


def _me(text: str, char_name: str) -> str:
    """第三人称 → 第一人称（同现有 recall._me: 条目里出现的 char_name → 我）。"""
    if not char_name or not text:
        return text
    return text.replace(char_name, "我")
