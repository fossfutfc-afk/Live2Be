"""render.py — 渲染视图（AGENT_BRAIN.md §4 / M2 + 板块5）。

同一张图, 多种渲染（视图分工）:
    组织视图    render_organize_view    —— 喂 digest/组织 LLM
               带 id + 邻接表 + 层/显著性/矛盾标记, 供修订决策（LLM 按 id 引用）
    角色视图    render_character_view   —— 喂主剧情 LLM
               纯第一人称叙事, 无 id 无链接, 分层排序（§4.2 + 排序规则）
    认知列表    render_cognition_list   —— Round B 输入（板块5）
               本地 id u0001.. 渲染（belief/experience, sig 降序）——引擎防 LLM 猜真实 id

格式约定（决策 #7）: id 无 # 无下划线（m0003）——组织视图行首即 id, 防 markdown 标题歧义。
player experience（§4.4）: 组织视图带 [关于老师] 标记; 角色视图独立【老师的事】段。
出厂 episode（2026-09-02 v3）: 角色视图渲染为独立【久远的记忆】段（cap 5 低配常驻）;
运行时 episode 独占 珍贵/最近 段（玩家羁绊主窗口）——出厂不挤占玩家记忆。
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

    player experience 的 kind 标签带 [关于老师]; 出厂 episode 带只读标记。
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
    if node.is_seed():
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
    char_aliases: tuple[str, ...] = (),
    summary: str = "",
    cap_seed_episodes: int = 5,
    cap_beliefs: int = 5,
    cap_player: int = 5,
    cap_recent: int = 6,
    cap_reported: int = 3,
) -> str:
    """角色注入视图: 分层排序渲染（2026-09-02 v3: fact 退役 + 出厂/运行时分层）。

    分层（出厂记忆低配常驻, 运行时玩家羁绊主窗口——注入预算竞争矛盾定稿）:
        - 久远的记忆（出厂 episode, source=experience）: cap_seed_episodes 按 sig——
          角色底色, 少而精; 出厂经历是"游戏开始前的过去", 不该挤占玩家记忆窗口
        - 我记得的事（珍贵的/最近）: **运行时独占**（玩家羁绊主窗口: 珍贵档 +
          ts 降序）; 出厂 episode 永不进此段
        - 我心里渐渐觉得（belief）: 出厂 belief（种子）+ 运行时 digest 产物混排
          （按 sig; 被玩家剧情 touch/update 的出厂认知自然带着玩家印记演化）
        - 老师的事（player experience 口癖）: count 降序
        - 我听说的（reported）: 兜底
        - knowledge 不再出厂化（世界观知识 = config 档案, system prompt 注入）
    第一人称转换: char_name + char_aliases（yml 原文多用简称, 如"遥香"）→ 我。
    """
    # 角色视图不依赖 id（渲染中从不出现 id）——直接按 kind/排序处理
    seed_eps = sorted(
        (n for n in nodes if n.kind == "episode" and n.source == "experience"),
        key=lambda n: n.significance, reverse=True)[:cap_seed_episodes]
    episodes = sorted(
        (n for n in nodes if n.kind == "episode"
         and n.epistemic == "observed_fact" and n.source != "experience"),
        key=lambda n: (n.is_precious, n.ts or ""), reverse=True)
    episodes = episodes[:cap_recent]
    beliefs = sorted((n for n in nodes if n.kind == "belief"),
                     key=lambda n: n.significance, reverse=True)[:cap_beliefs]
    players = sorted((n for n in nodes if n.is_player_experience),
                     key=lambda n: n.count, reverse=True)[:cap_player]
    reported = [n for n in nodes if n.kind == "episode"
                and n.epistemic == "reported_fact"][:cap_reported]

    blocks: list[str] = ["【角色记忆（brain）】"]
    if summary:
        blocks.append(f"我记得那段日子：{_me(summary, char_name, char_aliases)}")
    precious = [n for n in episodes if n.is_precious]
    recent = [n for n in episodes if not n.is_precious]
    if precious:
        blocks.append("我记得的事（珍贵的）：\n" + "\n".join(
            _memory_line(n, char_name, char_aliases) for n in precious))
    if recent:
        blocks.append("最近的事：\n" + "\n".join(
            _memory_line(n, char_name, char_aliases) for n in recent))
    if beliefs:
        blocks.append("我心里渐渐觉得：\n" + "\n".join(
            _belief_line(n, char_name, char_aliases) for n in beliefs))
    if players:
        blocks.append("老师的事：\n" + "\n".join(
            f"- {_me(n.pattern, char_name, char_aliases)}（count {n.count}）"
            for n in players))
    if reported:
        blocks.append("我听说的：\n" + "\n".join(
            _reported_line(n, char_name, char_aliases) for n in reported))
    if seed_eps:
        blocks.append("久远的记忆：\n" + "\n".join(
            _memory_line(n, char_name, char_aliases) for n in seed_eps))
    return "\n\n".join(blocks)


def render_background_experience(data: dict, *, cap: int = 6) -> str:
    """出厂背景段（2026-09-05 解耦定稿: 出厂记忆**不进 wiki**）。

    experience.yml 原文直注——与 personality 同为"作者人设描述", LLM 扮演时
    自然内化（社区主流做法: 预置内容 = 直注上下文, 不做节点化/改编/第一人称
    转换——回忆是 LLM 基本能力）。cap 按作者书写顺序截断（预算保护;
    想调展示集 → 改 experience.yml 条目顺序/拆段）。

    返回 "" = 无经历素材（零注入不阻断）。头段指引 LLM: 这些是她游戏开始前
    的人生, 回忆过去以此为准（运行时 wiki 的记忆只含玩家参与后的事）。
    """
    from core.brain.wiki_v2.seed import _collect_leaves
    leaves = _collect_leaves(data)
    if not leaves:
        return ""
    body = "\n".join(f"- {text}" for _, text in leaves[:cap])
    return ("【背景经历（游戏开始前她的人生——她回忆这段过去时以此为准; "
            "这是她的底色, 不必每轮提起）】\n" + body)


def _reported_line(node: BrainNode, char_name: str,
                   aliases: tuple[str, ...] = ()) -> str:
    line = f"- {_me(node.narration, char_name, aliases)}"
    if node.observer:
        line += f"（听{node.observer}说的）"
    return line


def _memory_line(node: BrainNode, char_name: str,
                 aliases: tuple[str, ...] = ()) -> str:
    line = f"- {_me(node.narration, char_name, aliases)}"
    if node.verbatim:
        line += f"（「{node.verbatim}」）"
    return line


def _belief_line(node: BrainNode, char_name: str,
                 aliases: tuple[str, ...] = ()) -> str:
    content = _me(node.content, char_name, aliases)
    line = f"- 对{_me(node.subject, char_name, aliases)}：{content}" \
        if node.subject else f"- {content}"
    if node.growth:
        line += f"（——{_me(node.growth, char_name, aliases)}）"
    return line


def _me(text: str, char_name: str, aliases: tuple[str, ...] = ()) -> str:
    """第三人称 → 第一人称（同现有 recall._me: 条目里出现的 char_name → 我）。

    2026-09-02: 支持简称别名——yml 原文多用简称（"遥香"而非"伊草 遥香"）;
    先替换长名后替换短名（防子串部分替换）; "她/他"不替换（可能指其他角色）。
    """
    if not text:
        return text
    names = [n for n in (char_name, *aliases) if n and n.strip()]
    # 长名优先（短名可能是长名子串）
    for n in sorted(set(names), key=len, reverse=True):
        text = text.replace(n, "我")
    return text


# ---------------------------------------------------------------------------
# Round B 输入渲染（板块 5: 认知列表 + episode 摘要）
# ---------------------------------------------------------------------------

def render_cognition_list(store: WikiStoreV2, cap: int = 12,
                          exclude: set[str] | None = None
                          ) -> tuple[str, dict[str, str]]:
    """Round B 输入: 现有稳定认知渲染（本地 id u0001..; 排序: significance 降序）。

    只挑 belief/experience（episode 是流水不参与组织, fact 是出厂基座不可
    touch/update）; 渲染层守 _ensure_cognition 语义, 引擎不给 LLM 不可选之物。
    exclude: 本轮 A 刚建的 id 集（player 画像条目——本段产物不进本轮认知列表,
    B 只组织 episode, 画像留待后续轮次参与组织）。

    Returns:
        (text, local_of): local_of = 真实 id → 本地 id（候选标注/执行器解析用;
        parse 层只认本地 id——防 LLM 猜真实 id）
    """
    exclude = exclude or set()
    nodes = [n for n in store.all()
             if n.kind in ("belief", "experience") and n.id not in exclude]
    nodes.sort(key=lambda n: (-n.significance, n.id))
    lines: list[str] = []
    local_of: dict[str, str] = {}
    for i, n in enumerate(nodes[:cap], start=1):
        local = f"u{i:04d}"
        local_of[n.id] = local
        body = n.content if n.kind == "belief" else (
            f"{n.pattern}（次数 {n.count}）" if n.count > 1 else n.pattern)
        if len(body) > 100:
            body = body[:100] + "…"
        sig = f", sig {n.significance:.2f}" if n.is_precious else ""
        subject = f" 关于 {n.subject}:" if n.subject else ""
        lines.append(f"{local} {_kind_tag(n)}{subject} {body}{sig}")
    if not lines:
        return "（尚无稳定认知——这是第一次理解, 直接 add）", local_of
    return "\n".join(lines), local_of


def _kind_tag(node: BrainNode) -> str:
    return f"[{node.kind}]"
