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

from core.brain.wiki_v2 import marks
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
        # ⭐ 2026-09-29: 「亲历 / 听说」的判据从 `epistemic` 搬到 **`observer` 空不空**
        # （字段退役, `REDUNDANCY.md` #3）—— 分桶结果逐条相同: 非空 observer ⟺ 听说的。
        "episode": lambda n: (n.kind == "episode"
                              and not n.observer.strip()),
        "belief": lambda n: n.kind == "belief",
        # ⚠️ 2026-09-25（§5.1）: 按 **kind** 收，**不再看 `subject`** —— 那是自由文本,
        # 拿它当路由会让"subject 被写坏"变成"这条记忆静默消失"（真机 haruka e0001 就是）。
        "player": lambda n: n.kind == "experience",
        "reported": lambda n: (n.kind == "episode"
                               and bool(n.observer.strip())),
    }
    # ⭐ 经历 = **一条河（旧→新）**（2026-09-25, 链路 ⑤）: 从前按 `(珍贵, ts)` 降序,
    # 于是"同一个时刻的事"被 `is_precious` 劈到两段里 ⇒ 河的时间轴断掉。
    # 「难忘」现在只是**行内标记**（见 `_memory_line`）, 不再参与排序。
    # ⚠️ 无 `ts` 的（旧档/未采集）排在**河首**: `marks.relative` 对它们**不印短语**
    # （哨兵纪律: 不编"很久以前"）⇒ 放在"现在"那一端会被读成"刚发生的事",
    # 放在开头的误读代价更小。
    episodes = sorted((n for n in all_nodes if bucket["episode"](n)),
                      key=lambda n: (bool(n.ts), n.ts or "", n.id))
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
        - 我记得的事（**一条河, 从早到晚**）: episode 全量按 `ts` 升序（2026-09-25 链路 ⑤）
        - 我心里渐渐觉得（belief）: 按 sig
        - 老师的事（player experience 口癖）: count 降序
        - 我听说的（reported）: 兜底 —— ⚠️ **不进河**: 那是"听说的事"不是她经历的
          （用户 2026-09-25 裁决: 当前值/旁证各自成块, 河只管 episode）
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
    # ⭐ **一条河**（2026-09-25, 链路 ⑤）: 经历不再按"珍贵的/最近的"切成两块 ——
    # 那会把**同一个时刻的事劈到两段里**, 读不出先后（真机: 3 天前既在「珍贵的」里
    # 又在「最近的事」里 = 两条并行的时间线）。现在按时间**从早到晚**排成一条,
    # 「难忘」降级为**行内标记**（`（3 天前·难忘）`）。
    # ⚠️ 方向是 **旧→新**（用户 2026-09-25 裁决）: 河尾紧挨着下面的笔记块与对话历史
    # ⇒ "过去 → 现在"一路流到此刻, 接缝连续; 而且最新的事落在**离生成点最近的那一端**
    # （`Lost in the Middle`: 上下文两头的信息利用率最高）; 新条目追加在河尾
    # ⇒ 河的前段逐字节稳定（前缀缓存友好）。
    if episodes:
        blocks.append("我记得的事（从早到晚）：\n" + "\n".join(
            _memory_line(n, char_name, char_aliases, now) for n in episodes))
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


#: 「你想起的事」段头（N5）。
#: ⚠️ **段头自己带边界**（"跟你现在要说的话有没有关系, 由你判断"）: 它是**候选**
#: 不是**待办** —— 少了这句, "引擎每轮都摆"会被读成"每轮都该提一件旧事"
#: （同 `look` 那条"回忆是动作, 不是习惯"）。
RECALL_HEADER = (
    "【你想起的事（此刻浮上来的旧事——跟你现在要说的话有没有关系, 由你判断）】")

#: ⭐ 候选旁的**动作提示**（N5b）——拼在候选**之后**（离她要做决定的地方最近）。
#: 为什么不只写在规则书里（**2026-09-29 真机 A/B 实测**）:
#: 只写在规则书 ⇒ 4 轮里 2 轮该写没写, 而且**最该写的那一轮**（召回段正摆着两条
#: 苔藓相关, 她话里也提到了）照样没写; 挪到候选旁边 ⇒ 3/4 轮写了、最该写那轮写了。
#: **她认得出、也说得出, 就是不记** —— 所以这一句必须贴着候选。
#: ⚠️ 实测口径: 两组的**抄写形态**都零变形（`{"noticed": "名字"}` 全部原样命中）,
#: 只有"写不写"有差别 ⇒ 缺的是**触发**, 不是**格式**。
RECALL_ACTION_HINT = (
    '（认出其中哪一条正是老师说的这件事——或者你想拿它来说事——就照抄'
    f'{marks.NAME_OPEN}{marks.NAME_CLOSE}里那几个字，'
    '单独写一行 {"noticed": "名字"}；认不出就不用写。）')

#: 该段的字符预算（`[recall].turn_budget` 的回落值）。真闸门是它, 不是条数
#: （一条 episode 长短不均; 设计原话 = "召回预算按 token（不是条数）"）。
RECALL_BUDGET = 700


def _recall_budget(override: int | None) -> int:
    """取字符预算（显式 > `[recall].turn_budget` > 模块常量）。读配置失败不阻断。"""
    if override is not None:
        return int(override)
    try:
        from core.brain.wiki_v2.recall_config import get
        return int(get("turn_budget"))
    except Exception:                            # noqa: BLE001 — 配置层不阻断注入
        return RECALL_BUDGET


def render_recall_block(nodes: Iterable[BrainNode], *,
                        char_name: str = "",
                        char_aliases: tuple[str, ...] = (),
                        now=None,
                        budget: int | None = None) -> str:
    """⭐ **N5** · 「你想起的事」—— 引擎每轮摆的 1~2 条旧 episode（空 → 不注入）。

    与 `render_character_view` 的**三条差别**（所以是**两个函数**, 别合并）:

    | | 角色视图（常驻） | 本段（每轮） |
    |---|---|---|
    | 选面 | **全部**记得的事（一条河） | **按当下这句话召回的 1~2 条** |
    | 落点 | `system`（盒 + brain） | **动态尾**（history 之后） |
    | 变化节奏 | digest 之后才变（前缀缓存友好） | **每轮都变** |

    ⚠️ **它进动态尾是硬要求, 不是排版偏好**: 这一段的输入里有**玩家这一句**
    （`recall_episodes(query=…)`）⇒ 它每轮必然不同 ⇒ 一旦拼进 `system` 就**逐轮
    破前缀缓存**（`core/promptkit/tail.py` 的不变式: "动态一切发生在 history 之后"）。

    ⚠️ **一次调用只渲染一次**: `agent_turn` 在拼 messages 之前调它一次, 这一轮内
    的重试/续写**复用同一份 messages**——召回不会在轮中途换内容（换了就等于
    "她刚才想起的"与"她现在想起的"不是同一件事）。

    `budget` 那一条是**按行累积**的（不是先算总长再砍）: 宁可少摆一条, 也不把
    一条 episode 截半——半条记忆比没有更坏（截断处正好是细节, 而"引用细节"正是
    这一段存在的理由）。
    """
    picked = [n for n in nodes if n.kind == "episode"]
    if not picked:
        return ""
    limit = _recall_budget(budget)
    lines: list[str] = []
    used = 0
    for n in picked:
        line = _memory_line(n, char_name, char_aliases, now)
        if lines and used + len(line) > limit:   # 第一条永远留（预算是闸门不是否决）
            break
        lines.append(line)
        used += len(line)
    return RECALL_HEADER + "\n" + "\n".join(lines) + "\n" + RECALL_ACTION_HINT


def _reported_line(node: BrainNode, char_name: str,
                   aliases: tuple[str, ...] = ()) -> str:
    line = f"- {_me(node.text, char_name, aliases)}"
    if node.observer:
        line += f"（听{node.observer}说的）"
    return line


def _memory_line(node: BrainNode, char_name: str,
                 aliases: tuple[str, ...] = (),
                 now=None) -> str:
    """一条 episode 的记忆行 —— **元信息在最前**（§3.8 / §4.11）。

    形态: `- 〔《中秋的杂草屋》｜4 天前｜9/27｜难忘〕中秋节晚上，社团的大家…（「月亮，真的很圆。」）`

    ⭐ **标题从 N5（2026-09-29）起印出来**（`《…》`, 元信息第一段）——
    在此之前 `title` **从来没进过任何注入面**（`PROCEED §1` 事实 #1: 契约要求 8-16 字、
    真机 18 条都唯一且都含具体名词, 但一个读者都没有）。

    **为什么它必须可见**（地址地基, `PROCEED §2` #10/#11）:
    引擎与她的**唯一地址空间就是标题**——编号（`m0014`）退回引擎内部。而她要用标题
    做的那件事是**指认**: `{"noticed": "苔藓的约定"}`（"这不就是同一件事吗"）。
    标题不可见 ⇒ 那个动作**无从说起**（她无法指一个看不见的名字）。
    ⇒ ⚠️ **标题一律原样（不过 `_me`）**: 它是**地址**, 她抄下来的串必须与库里的
    `node.title` 逐字相同; 做了第一人称转换（"遥香的秘密"→"我的秘密"）就会
    让每一次指认都落空, 且**静默**。

    **为什么元信息在最前而不是最后**（2026-09-13, N5 起扩成整段）:
    这是**防失忆注记**——LLM 需要先看到"这是多久以前的事"再读内容, 才好判断
    "这件事讲过了/该不该重提"。放最后等于读完才知道远近。
    ⭐ **名字是第一格**（"哪一条"先立住, 再读时间与正文）—— 且用**书名号**标出;
    摘抄的判据是**书名号**不是位置（见 `marks.head` / `marks.name`）。

    **为什么挂短语不影响 Q24 的"只给标题"**：Q24 砍的是**正文体积**
    （episode 内容进 writer 视图要压缩）; 元信息是**几到十几个字**, 不在被砍之列,
    而它恰好补上 Q24 留下的洞——干标题没有任何时间线索, 措辞会漂。

    ⚠️ **相对短语绝不出现精确值**（I-c）: `render_relative` 只给
    "今天/昨天/N 天前/N 周前/上个月/N 个月前/去年/N 年前/很久以前"。
    破了会让角色"数日子", 且诱导 LLM 做算术。
    ⚠️ **绝对日期是引擎坐标, 不是她的口吻**（`PROCEED §2 #16`）: 两个都要 ——
    但只有相对短语是"她会说出口的话"; 日期不许进她的台词（I-c 窄破那条仍在待裁）。

    `now=None`（调用方未给）→ **只有标题**（不给"现在"就不知道是哪一年 ⇒ 不猜）。
    节点无 `ts`（空串/坏值）→ 同理不出现时间段——**不编一个"很久以前"**,
    那会让"未采集"与"真的很旧"混为一谈。
    """
    body = _me(node.text, char_name, aliases)
    if node.verbatim:
        body += f"（「{node.verbatim}」）"
    # ⭐ 头由 `marks.head` 出（**唯一实现**）: `〔《名》｜4 天前｜9/27｜难忘〕`。
    # 珍贵档那一格的**说法随读者变**（她读作 `难忘`, L2 读作 `sig 0.90`）⇒ 由读者给。
    extra = ["难忘"] if node.is_precious else []
    return f"- {marks.head(node, now=now, extra=extra)}{body}"


# ⏸ `_meta_head` / `_time_phrase` / `_abs_date` **2026-09-29 搬进 `marks.py`** ——
# 信息头（括号 · 名字 · 类型 · 时间 · 格序）从此只有一份实现（那个模块的 docstring
# 就是原来的三张表）; 当年写在 `_meta_head` 里的三条纪律一并搬过去了:
# `｜` 不是 `·` · 书名号在名字才在（按括号找不按位置找）· 一个字段都没有 ⇒ 整段不出现。
# 搬家的理由 = **写侧五份、读侧一份**（`address.normalize_title`）: 任一处漂了,
# 她抄回来的名字就静默命中 0。


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
                          exclude: set[str] | None = None,
                          must_include: Iterable[str] = ()
                          ) -> tuple[str, dict[str, str]]:
    """Round B 输入: 现有稳定认知渲染（本地 id u0001..; 排序: significance 降序）。

    只挑 belief/experience/**promise**（episode 是流水不参与组织 —— 它是"支撑"的**起点**
    而不是被 touch 的对象）; 渲染层守 `_ensure_cognition` 语义, 引擎不给 LLM 不可选之物。

    ⭐ **promise 2026-09-25 加进来**（§9-13 的洞）: 固化后的承诺也是"稳定下来的东西",
    而 R2 要写 `supports(promise → belief)`（"这条承诺长出了看法"）与
    `evolved_from(promise → 旧 promise)`（"新的盖过旧的"）—— **看不见就写不出**,
    那两条边就永远打不出来。⚠️ 但它**不能被 `touch`/`update``（不是看法）⇒
    `digest` 那边把可 touch 的集与可 link 的集分开传（`parse_round_b` 的
    `target_ids` / `link_ids`）。

    `exclude`: 本轮 A 刚建的 id 集（player 画像条目——本段产物不进本轮认知列表,
    B 只组织 episode, 画像留待后续轮次参与组织）。
    `must_include`: **本轮 R4 物化的 promise 节点** —— 它们必须出现在列表里
    （不受 `cap` 截断）, 否则 R2 又一次"看不见刚要写边的东西"。

    Returns:
        (text, local_of): local_of = 真实 id → 本地 id（候选标注/执行器解析用;
        parse 层只认本地 id——防 LLM 猜真实 id）
    """
    exclude = exclude or set()
    nodes = [n for n in store.all()
             if n.kind in ("belief", "experience", "promise")
             and n.id not in exclude]
    nodes.sort(key=lambda n: (-n.significance, n.id))
    picked = nodes[:cap]
    have = {n.id for n in picked}
    for nid in must_include:                     # 必进的（本轮新物化的承诺）
        node = store.get(nid)
        if node is not None and node.id not in have:
            picked.append(node)
            have.add(node.id)
    graph = store.graph()                       # experience 的次数 = supports 入边数
    # ⭐ **N2（2026-09-29）: 元信息进 `〔〕`，被引与边都印出来** ——
    #   形态: `〔u0001｜belief｜被引 3〕关于 sensei: 老师是第一个不会嫌弃我的人`
    #         + 缩进续行 `        edges: supports←m0004 contradicts→u0003`
    #   为什么（`PROCEED §1` 那条"看不见两端的 LLM 写不出那条边"）:
    #   R2 要写 `supports`/`contradicts`/`evolved_from`，**它必须先看得见边**;
    #   而"被引 N"是它判"这条看法成熟了没有"的唯一依据（今天只有 experience 印次数）。
    local_of: dict[str, str] = {}
    for i, n in enumerate(picked, start=1):
        local_of[n.id] = f"u{i:04d}"
    lines: list[str] = []
    for n in picked:
        lines.extend(render_cognition_line(store, n, graph, local_of))
    if not lines:
        return "（尚无稳定认知——这是第一次理解, 直接 add）", local_of
    return "\n".join(lines), local_of


def render_cognition_line(store: WikiStoreV2, node: BrainNode, graph,
                          local_of: dict[str, str], *,
                          max_body: int = 100, indent: str = "") -> list[str]:
    """**一条认知的渲染行**（主行 + 边续行）—— 两个调用者共用同一份。

    `render_cognition_list`（认知列表, `max_body=100`）与
    `digest._round_b_material`（候选提示, `max_body=60` + 缩进）——
    ⚠️ **两处各写一份必然漂**, 而漂了就是"同一张图在两处长得不一样"。
    """
    extra = [f"被引 {_count_of(node, graph)}"]
    if node.is_precious:
        extra.append(f"sig {node.significance:.2f}")
    # ⚠️ `subject` **原样**印 + 全角冒号 —— 不前置"关于":
    # 它是 R2 的自由文本，真机里本来就写成「关于 我道歉的习惯」，
    # 前置就变成「关于 关于 我道歉的习惯:」（老形态的老毛病，顺手修）。
    subject = f"{node.subject}：" if node.subject else ""
    body = node.text if len(node.text) <= max_body else node.text[:max_body] + "…"
    out = [f"{indent}{marks.head(node, key=local_of[node.id], kind=True, extra=extra)}"
           f"{subject}{body}"]
    edge_line = _cognition_edges(store, node, graph, local_of)
    if edge_line:
        out.append(f"{indent}{_INDENT}{edge_line}")
    return out


#: 一条认知最多印几条边（超出的只计数）——被引 20 条时印 20 行没人读得下去,
#: 而"有几条"已经写在 `被引 N` 里了（**少花 ≠ 少信息**）。
_COGNITION_EDGES_MAX = 6


def _cognition_edges(store: WikiStoreV2, node: BrainNode, graph,
                     local_of: dict[str, str]) -> str:
    """一条认知的边（`supports←m0004 contradicts→u0003`）—— 空串 = 不印。

    ⚠️ **只印"能指认的"两端**（这是本地 id 纪律的延伸）:
      · 认知 → **本地号**（`u0003`; 只它在列表里时才有 —— 不在列表里就是"看不见"）；
      · episode → **真实 id**（`m0004`: R2 的 decisions 本来就用真实 id 指 episode）；
      · 其余（entity/group…）→ 只计数（`（另有 N 条边指向列表外）`），
        **绝不编一个它看不到正文的号**。
    """
    rels = [(e.rel, e.dst, "→") for e in graph.edges_from(node.id)]
    rels += [(e.rel, e.src, "←") for e in graph.edges_to(node.id)]
    shown: list[str] = []
    outside = 0
    for rel, other, arrow in rels:
        if other in local_of:
            shown.append(f"{rel}{arrow}{local_of[other]}")
            continue
        dst = store.get(other)
        if dst is not None and dst.kind == "episode":
            shown.append(f"{rel}{arrow}{other}")
            continue
        outside += 1
    if not shown and not outside:
        return ""
    head = " ".join(shown[:_COGNITION_EDGES_MAX])
    if len(shown) > _COGNITION_EDGES_MAX:
        head += f" …（另有 {len(shown) - _COGNITION_EDGES_MAX} 条）"
    if outside:
        tail = f"（另有 {outside} 条边指向列表外）"
        head = f"{head} {tail}" if head else tail.strip()
    return f"edges: {head}"


# ⏸ `_kind_tag` **2026-09-29 搬进 `marks.kind_tag`**（不带方括号的唯一版本）。
# 它当年有两个形状（这里 `[belief]`、`entities` 里 `strip("[]")` 成 `belief`）——
# 同一个类型标签两种印法, 正是"散"的典型; 现在只有一处。
