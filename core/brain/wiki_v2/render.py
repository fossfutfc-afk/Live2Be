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
⚠️ **出厂 episode / seed 桶 2026-09-21 删**（"出厂基座"机制退役）: 2026-09-05 解耦后
出厂记忆**不进 wiki**（主进程注入走 `render_background_experience` 直注 yml 原文）,
真机 0 个 seed 节点 ⇒ 本文件那条 `source == "experience"` 的分支（含【久远的记忆】段
与组织视图的"canon 只读"标记）一直在空转。**将来若真要"手动出厂库"**, 请以
`config/characters/*/experience.yml` 为准扩那一条注入链, 不要回 wiki 造第二真源。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from core.brain.wiki_v2.nodes import BrainNode

if TYPE_CHECKING:                       # 仅注解求值期可见（避免运行时循环导入）
    from core.brain.wiki_v2.store import WikiStoreV2

#: 组织视图行首缩进（verbatim/example 续行）
_INDENT = "        "

# ---------------------------------------------------------------------------
# yml → 叶子（source_key, 文本）收集（原 seed.py, 2026-09-05 解耦后内迁——
# render_background_experience 唯一活动消费者; seed.py 本体随出厂链归档）
# ---------------------------------------------------------------------------

_PREFIXES = ("SIG~", "REQ~")
_SKIP_LEAF = {"true", "false", "null", "none", "~", ""}


def _collect_yml_leaves(data: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    """递归拍平 yml 树 → [(source_key, 文本), …]。

    规则:
        - dict: 键路径拼接（剥离 SIG~/REQ~ 前缀; null 值跳过）
        - list: 单键 dict 项 → 用其键作路径段（numbered 条目, 如 {1: text}）;
                纯值项 → 1-based 序号（technique.1）
        - 叶子: 非空文本（bool/None 类占位跳过）
    """
    out: list[tuple[str, str]] = []
    _walk(data, prefix, out)
    return out


def _walk(node: Any, path: str, out: list[tuple[str, str]]) -> None:
    if node is None:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            if not isinstance(k, str):
                continue
            _walk(v, _join(path, _strip_prefix(k)), out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, dict) and len(v) == 1:
                (k, vv), = v.items()                      # numbered 条目 {1: text}
                _walk(vv, _join(path, str(k)), out)
            else:
                _walk(v, _join(path, str(i + 1)), out)    # 纯值项 1-based
    else:
        text = str(node).strip()
        if text.lower() not in _SKIP_LEAF and path:
            out.append((path, text))


def _join(path: str, seg: str) -> str:
    return f"{path}.{seg}" if path else seg


def _strip_prefix(key: str) -> str:
    for p in _PREFIXES:
        if key.startswith(p):
            return key[len(p):]
    return key


# ---------------------------------------------------------------------------
# 组织视图（digest/组织 LLM 消费）
# ---------------------------------------------------------------------------

def render_organize_view(nodes: Iterable[BrainNode], *, timeline: str = "",
                         graph=None) -> str:
    """组织视图: 【本次新经历】时间线 + 【相关旧记忆】子图（id + 邻接表）。

    节点顺序 = 传入顺序（引擎已按显著性/召回排序）。

    `graph`: 边视图（`core.brain.wiki_v2.graph.Graph`）。**G3 起边不在节点里**
    （`links`/`contradictions` 只作旧档读入、不再被写出）⇒ 不给 graph 就**不印边**
    （这是有意的空: 印一个恒空的 `links:` 会让人以为"这条记忆没有邻居"）。
    """
    blocks: list[str] = []
    if timeline:
        blocks.append(f"【本次新经历】\n{timeline.strip()}")
    lines = [_organize_line(n, graph) for n in nodes if n.id]
    if lines:
        blocks.append("【相关旧记忆（供组织决策）】\n" + "\n".join(lines))
    return "\n\n".join(blocks)


def _organize_line(node: BrainNode, graph=None) -> str:
    """一行: `m0003 [episode, sig 0.80, edges: supports→m0009 contradicts→m0005] 内容`。

    player experience 的 kind 标签带 [关于老师]。
    ⚠️ 边的**类型印出来**（G3）—— 旧版印的是无类型的 `links: m0009` + `c: m0005`,
    "谁支撑谁"读不出来; 现在 `supports→m0009` 一眼可判方向。
    """
    meta = [node.kind]
    if node.is_player_experience:
        meta[0] = "experience·关于老师"
    meta.append(f"sig {node.significance:.2f}")
    if node.kind == "experience":
        meta.append(f"count {_count_of(node, graph)}")
    if graph is not None:
        # 出边（我指向谁）+ 入边（谁指向我）——无向边的时代两边都有, 这里都印
        rels = [f"{e.rel}→{e.dst}" for e in graph.edges_from(node.id)]
        rels += [f"{e.rel}←{e.src}" for e in graph.edges_to(node.id)]
        if rels:
            meta.append("edges: " + " ".join(rels))
    head = f"{node.id} [{', '.join(meta)}] {node.text}"
    extra = _organize_extra(node)
    return head + extra


# ⏸ `_organize_text()` 2026-09-21 删——它按 kind 从 narration/pattern/content 里挑正文;
# 三槽合流成 `text` 后挑选这步没了（调用点直接用 `node.text`）。


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

#: 最近一次 `render_character_view` 的台账（V3-0）。调用方取走后应清空，
#: 用列表而非全局标量: 渲染函数可能在多处被调（bond 开场 / MMT 每轮 / CLI），
#: 由调用方决定"这次渲染属于谁"，渲染层自己不猜 char_id。
_last_view_account: list[dict] = []


def take_last_view_account() -> dict | None:
    """取走最近一次角色视图的台账（无 → None）。取走即清空（消费语义）。"""
    return _last_view_account.pop() if _last_view_account else None


def _count_of(node: BrainNode, graph) -> int:
    """experience 的出现次数 = **`supports` 入边数**（G3 起不再读节点字段）。

    语义: experience 是"重复模式", 每被印证一次就多一条 `supports` 入边
    （digest 的 add/accrue/touch 各加一条 —— `revise` 里都是 `add_edge(REL_SUPPORTS,…)`）。

    `graph=None`（调用方没给边表）→ **0**, 不去读那个已停止写入的旧 `links` 字段:
    读了会得到一个"看起来很真"的假计数（0 至少一眼看得出是没接线）。
    """
    return len(graph.supporters(node.id)) if graph is not None else 0


def _bucket_view(nodes: Iterable[BrainNode], graph=None) -> dict:
    """**唯一**分桶实现（2026-09-13 **cap 全删**）。

    抽出来是为了让台账（V3-0）与渲染共用同一份分桶结果——否则两条路径会漂移,
    而台账的全部价值就在于"如实反映 LLM 看到了什么"。

    **cap 为什么删**（用户裁决 2026-09-13, DESIGN_WIKI_V3 §3.1/§3.7）:
    分桶的 `[:cap]` 截断**就是** v2 的召回机制——它按绝对 `significance` 取前 N,
    后果是"第 6 条以后的 belief 永不出现 → 永远不可能被 touch/update"（写路径
    依赖读路径把它喂进去）。v3 的召回由**实体车道 + 混合打分**接管（A-Mem 式），
    判据是"与当下相关"而不是"绝对重要"——**两者是替代关系, 不是叠加**。
    留 cap = 在召回之前先无理由砍一刀 → 召回再准也捞不到被砍掉的。

    规模实测（真机 world1）: 一条世界线全部记忆 ≈1.6k~3.1k 字（≈800~1600 token），
    且**当前无一条世界线触到任何 cap**（haruka 4 belief / 4 episode）——
    删 cap 在今天**行为零变化**, 只是拆掉将来的玻璃天花板。

    桶内**排序保留**（它决定注入顺序, 不是截断判据）。
    """
    all_nodes = list(nodes)
    bucket = {
        # ⚠️ 原 "seed" 桶（`source == "experience"`）2026-09-21 删——出厂记忆不进 wiki,
        # 真机零节点, 见模块 docstring。
        "episode": lambda n: (n.kind == "episode"
                              and n.epistemic == "observed_fact"),
        "belief": lambda n: n.kind == "belief",
        # ⚠️ 2026-09-25（§5.1）: 按 **kind** 收，**不再看 `subject`** —— 那是自由文本,
        # 拿它当路由会让"subject 被写坏"变成"这条记忆静默消失"（真机 haruka e0001 就是）。
        "player": lambda n: n.kind == "experience",
        "reported": lambda n: (n.kind == "episode"
                               and n.epistemic == "reported_fact"),
    }
    episodes = sorted((n for n in all_nodes if bucket["episode"](n)),
                      key=lambda n: (n.is_precious, n.ts or ""), reverse=True)
    beliefs = sorted((n for n in all_nodes if bucket["belief"](n)),
                     key=lambda n: n.significance, reverse=True)
    players = sorted((n for n in all_nodes if bucket["player"](n)),
                     key=lambda n: _count_of(n, graph), reverse=True)
    reported = [n for n in all_nodes if bucket["reported"](n)]
    return {
        "total": len(all_nodes),
        "episodes": episodes,
        "beliefs": beliefs,
        "players": players,
        "reported": reported,
        # 台账口径: 桶名 → 注入条数（cap 已删 → 桶内全量, 无"选中/候选"之分）
        "buckets": {
            "episode": len(episodes),
            "belief": len(beliefs),
            "player": len(players),
            "reported": len(reported),
        },
    }


def render_character_view(
    nodes: Iterable[BrainNode],
    *,
    char_name: str = "",
    char_aliases: tuple[str, ...] = (),
    summary: str = "",
    now=None,
    graph=None,
) -> str:
    """角色注入视图: 分层排序渲染（2026-09-13: **cap 全删**, 见 `_bucket_view`）。

    分层（运行时分区, 决定**注入顺序**而非截断）:
        - 我记得的事（珍贵的/最近）: 珍贵档 + ts 降序
        - 我心里渐渐觉得（belief）: 按 sig
        - 老师的事（player experience 口癖）: count 降序
        - 我听说的（reported）: 兜底
        - knowledge 不再出厂化（世界观知识 = config 档案, system prompt 注入）
        （原"久远的记忆"段 2026-09-21 删——出厂 episode 不进 wiki, 见模块 docstring）
    第一人称转换: char_name + char_aliases（yml 原文多用简称, 如"遥香"）→ 我。
    （**v3 将废弃该转换**——见 DESIGN_WIKI_V3 §2.11; 本节暂不动。）

    2026-09-13（V3-0）: 分桶抽到 `_bucket_view`（台账与渲染共用），并把这次
    的桶统计**记进 `_last_view_account`** 供调用方打台账（渲染函数本身不打日志——
    它不知道自己在为哪个角色/哪条 surface 渲染）。

    2026-09-13（T3）**防失忆注记**: `now` 给了 → 每条 episode 前置
    **虚化时间短语**（"（3 周前）…"）。这是 Q24 留下的洞的补丁:
    episode 只给标题后, LLM 没有任何时间线索, 不知道是上周还是三年前的事。
    短语**不落数据**（§3.8: 只在渲染层做, 阈值可随时重算）; 不给 `now`
    则完全不出现（旧档/未接线时与本改动前逐字节相同）。

    2026-09-17（`ESSAY_TIME_MODEL §10` 时间轴换代）: 年龄改由**现实日期**算
    （`node.ts`），不再读 `node.story_time` / 剧情游标。`now` 传的是当前
    **时刻**（`datetime` 或 `ts` 串）—— 形状没变, 语义从"剧情时间槽"变成"今天"。
    """
    b = _bucket_view(nodes, graph)
    episodes, beliefs, players, reported = (
        b["episodes"], b["beliefs"], b["players"], b["reported"])
    _last_view_account.append(b)

    blocks: list[str] = ["【角色记忆（brain）】"]
    if summary:
        blocks.append(f"我记得那段日子：{_me(summary, char_name, char_aliases)}")
    precious = [n for n in episodes if n.is_precious]
    recent = [n for n in episodes if not n.is_precious]
    if precious:
        blocks.append("我记得的事（珍贵的）：\n" + "\n".join(
            _memory_line(n, char_name, char_aliases, now)
            for n in precious))
    if recent:
        blocks.append("最近的事：\n" + "\n".join(
            _memory_line(n, char_name, char_aliases, now)
            for n in recent))
    if beliefs:
        blocks.append("我心里渐渐觉得：\n" + "\n".join(
            _belief_line(n, char_name, char_aliases) for n in beliefs))
    if players:
        blocks.append("老师的事：\n" + "\n".join(
            f"- {_me(n.text, char_name, char_aliases)}（count {_count_of(n, graph)}）"
            for n in players))
    if reported:
        blocks.append("我听说的：\n" + "\n".join(
            _reported_line(n, char_name, char_aliases) for n in reported))
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
    leaves = _collect_yml_leaves(data)
    if not leaves:
        return ""
    body = "\n".join(f"- {text}" for _, text in leaves[:cap])
    return ("【背景经历（游戏开始前她的人生——她回忆这段过去时以此为准; "
            "这是她的底色, 不必每轮提起）】\n" + body)


def _reported_line(node: BrainNode, char_name: str,
                   aliases: tuple[str, ...] = ()) -> str:
    line = f"- {_me(node.text, char_name, aliases)}"
    if node.observer:
        line += f"（听{node.observer}说的）"
    return line


def _memory_line(node: BrainNode, char_name: str,
                 aliases: tuple[str, ...] = (),
                 now=None) -> str:
    """一条 episode 的记忆行 —— **时间短语挂在最前**（§3.8 / §4.11）。

    形态: `- （3 周前）她拉着我在杂草屋蹲了一下午。（「原话」）`

    **为什么短语在最前而不是最后**（2026-09-13）: 这是**防失忆注记**——
    LLM 需要先看到"这是多久以前的事"再读内容, 才好判断"这件事讲过了/该不该重提"。
    放最后等于读完才知道远近。

    **为什么挂短语不影响 Q24 的"只给标题"**：Q24 砍的是**正文体积**
    （episode 内容进 writer 视图要压缩）; 短语是**几到十个字**, 不在被砍之列,
    而它恰好补上 Q24 留下的洞——干标题没有任何时间线索, 措辞会漂。

    ⚠️ **短语绝不出现精确值**（I-c）: `render_relative` 只给
    "今天/昨天/N 天前/N 周前/上个月/N 个月前/去年/N 年前/很久以前"。
    破了会让角色"数日子", 且诱导 LLM 做算术。

    `now=None`（调用方未给）→ **不加短语**（旧档/未接线时保持原形态）。
    节点无 `ts`（空串/坏值）→ 同样不加——**不编一个"很久以前"**,
    那会让"未采集"与"真的很旧"混为一谈。
    """
    line = f"- {_me(node.text, char_name, aliases)}"
    phrase = _time_phrase(node, now)
    if phrase:
        line = f"- （{phrase}）" + line[2:]
    if node.verbatim:
        line += f"（「{node.verbatim}」）"
    return line


def _time_phrase(node: BrainNode, now) -> str:
    """节点的时间短语（`""` = 不加）。**只读, 不改节点**（§3.8「不落数据」）。

    2026-09-17（`ESSAY_TIME_MODEL §10`）: 年龄 = `今天 − date(node.ts)`（**现实日**），
    不再读 `node.story_time`。`now=None` 或 `node.ts` 缺失 → `""`
    （哨兵纪律: **不编一个"很久以前"**，那会让"未采集"与"真的很旧"混为一谈）。
    """
    if now is None or not node.ts:
        return ""
    try:
        from core.worldtime.age import age_days, render_relative
        age = age_days(node.ts, now=now)
        if age is None:
            return ""
        return render_relative(age, node.significance)
    except Exception:                            # noqa: BLE001 — 渲染绝不因时间炸
        return ""


def _belief_line(node: BrainNode, char_name: str,
                 aliases: tuple[str, ...] = ()) -> str:
    body = _me(node.text, char_name, aliases)
    line = f"- 对{_me(node.subject, char_name, aliases)}：{body}" \
        if node.subject else f"- {body}"
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
    graph = store.graph()                       # experience 的次数 = supports 入边数
    lines: list[str] = []
    local_of: dict[str, str] = {}
    for i, n in enumerate(nodes[:cap], start=1):
        local = f"u{i:04d}"
        local_of[n.id] = local
        cnt = _count_of(n, graph)
        body = n.text if n.kind == "belief" else (
            f"{n.text}（次数 {cnt}）" if cnt > 1 else n.text)
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
