# -*- coding: utf-8 -*-
"""entities.py — entity 的初始化 + 第 3 轮的**输入侧**（`DESIGN_GRAPH_V4.md` §3.0 / §8.3）。

| 函数 | 谁用 | 干什么 |
|---|---|---|
| `ensure_entities` | D3 编排 | 开局把 `self` + `sensei` 建出来（保留号 + 幂等） |
| `candidate_table` | 第 3 轮 prompt | 全量候选表（§8.3 第一层）—— **只有身份**: 本地 id + 名字 + 别名 |
| `hit_set` | 第 3 轮 prompt | 命中集 —— `about_hint` ∪ 称呼命中本轮正文（**确定性, 不靠 LLM**） |
| `payload_block` | 第 3 轮 prompt | 命中集的**当前载荷**（`text` 立场 + `state` 物理状况） |

⚠️ 第 3 轮的**执行器**（写 `about` 边 / 建新 entity / 重写载荷）**不在这里** ——
它是 `revise.apply_attribution`（D2b）。本文件只管"**喂给第 3 轮看什么**"。

## 为什么 self 与 sensei 是**保留号**

```
x0000 = self     （v3 §2.8 定的"我"）
x0001 = sensei   （老师/玩家）
```

- **幂等判定 = 查 id**，不用靠名字匹配（"老师"会被玩家改名、sensei/老师 混用）。
- 日志里一眼可辨（同 `x0000` 那条理由）。
- `store.next_id("x")` 因此从 **x0002** 起。
- ⚠️ 所以 `ensure_entities` **必须在任何"自动建 entity"之前跑**（它是"初始化"的含义）；
  第 3 轮建新 entity 走 `next_id`，天然不会撞。

## 名字从哪来（**参数化传入, 不读 config**）

与 `character_prompt` / `emotion_lexicon` / `aff_at_encoding` 同一条分工: `core/brain/`
是纯 stdlib 叶子, **不知道**角色配置（yml）与资产布局 —— 名字由调用方取好传进来
（`CharacterLoader` 的 `char.display_name` + 别名助手）。

**两个 entity 各读各的档案**（2026-09-23 用户裁决 —— 玩家也走 config, 与角色对称）:

| | 主名 / 别名来源 |
|---|---|
| `self` | `config/characters/{id}/profile.yml`（经 `names.names_of(char)`） |
| `sensei` | `config/player/profile.yml`（经 `player_profile.player_names()`） + `data/basic/player.json` 的玩家自取名（**运行时数据, 只作别名**） |

⇒ "老师"这个字面量本文件**不再持有**（原 `SENSEI_NAMES` 已删），只剩
`contract.DEFAULT_SPEAKER_NAMES` 那一份兜底。

⚠️ 名字读取**已于 2026-09-23 归一**（N1 → `core/parsing/names.py` 的 `char_names(profile)`
/ `names_of(char)`）—— 本文件的调用方直接把那个接口的结果当参数传进来即可,
**本文件仍然只收参数**（`core/brain/` 是纯 stdlib 叶子, 不反向读 `config/`）。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from contract import CHARACTER_SENSEI, DEFAULT_SPEAKER_NAMES
from core.brain.wiki_v2.nodes import BrainNode, format_id

if TYPE_CHECKING:                       # 仅注解求值期可见（避免运行时循环导入）
    from core.brain.wiki_v2.store import WikiStoreV2

logger = logging.getLogger(__name__)

#: 保留号（见模块 docstring）
SELF_ID = "x0000"
SENSEI_ID = "x0001"

#: sensei 的**兜底**名/别名 —— 真源 = `contract.DEFAULT_SPEAKER_NAMES`（"老师"全项目只此一份;
#: 原 `SENSEI_NAMES = ("老师", "sensei")` 是第二份字面量, 2026-09-23 删）。
#: ⚠️ 现网的名字**不从这里来**: 由 `config/player/profile.yml` 经
#: `core/parsing/player_profile.player_names()` 当参数传进来（玩家也走 config, 与角色档案
#: 同一套前缀约定）。这两个常量只服务"调用方没给"的场合（如本模块的单测）—— 引擎侧不许靠它。
SENSEI_FALLBACK_NAME = DEFAULT_SPEAKER_NAMES[CHARACTER_SENSEI]
SENSEI_FALLBACK_ALIASES = (CHARACTER_SENSEI,)


def ensure_entities(store, *, char_name: str = "", aliases=(), player_name: str = "",
                    player_aliases=(), sensei_name: str = "", sensei_aliases=()) -> list[str]:
    """**初始化**: 没有就建 self(x0000) + sensei(x0001); 返回**本次新建**的 id 列表。

    幂等: 按 id 判存在, 已有则跳过 —— 反复调用不写盘、不改数据（调用方自己决定 save）。

    Args:
        char_name: 角色自己的**主名**（= `config/characters/{id}/profile.yml` 的
            `REQ~most_called_name`, 由调用方经 `names.names_of(char).display` 给）。
            ⚠️ 空 → **跳过建 self**: `name` 是 entity 的必填, 空名字的 entity 会被
            `store.add` 拒 —— 宁可不建, 也不建一个没名字的。
        aliases: 角色的别名（同档案的 `other_names`/`jp_name`/`en_name` 切分后）
        player_name: 玩家**自己取的名字**（GUI/CLI 可改）—— 追加成 sensei 的一条别名
        player_aliases: 玩家名的其它说法
        sensei_name: sensei 的**主名**（= `config/player/profile.yml` 的
            `REQ~most_called_name`, 经 `player_profile.player_names()` 给）。
            空 → 退回 `SENSEI_FALLBACK_NAME`（= contract 的 "老师"）
        sensei_aliases: 作者给 sensei 的别名（同档案的 `other_names` 等）
    """
    out: list[str] = []
    if SELF_ID not in store and char_name.strip():
        out.append(store.add(_entity(SELF_ID, char_name, aliases)))
    elif SELF_ID not in store:
        logger.warning("ensure_entities: 没给 char_name → **跳过**建 self（%s）——"
                       "name 是 entity 的必填, 宁可不建也不建个没名字的", SELF_ID)

    if SENSEI_ID not in store:
        name_s = sensei_name.strip() or SENSEI_FALLBACK_NAME
        aliases_s: list[str] = []
        # 顺序 = 作者别名（config）→ contract 兜底 → 玩家自取名/别名; 先到先得（去重）
        for extra in (*sensei_aliases, *SENSEI_FALLBACK_ALIASES,
                      *player_aliases, player_name):
            extra = str(extra or "").strip()
            if extra and extra != name_s and extra not in aliases_s:
                aliases_s.append(extra)
        out.append(store.add(_entity(SENSEI_ID, name_s, aliases_s)))
    return out


def _entity(nid: str, name: str, aliases):
    """建一个只有身份的 entity（`text`/`state` 留空 —— 立场由第 3 轮从记忆里长出来）。

    ⚠️ 用 `BrainNode` 直接构造 + 钉 id（**不是** `make_node`, 那条路会走 `from_dict`;
    而 `from_dict` 现在认得 entity 了, 但显式钉 id 更直白 —— 保留号不能被自动分配覆盖）。
    """
    node = BrainNode()
    node.id = nid
    node.kind = "entity"
    node.name = name.strip()
    seen: list[str] = []
    for a in aliases or ():
        a = str(a).strip()
        if a and a != node.name and a not in seen:
            seen.append(a)
    node.aliases = seen
    return node


# ---------------------------------------------------------------------------
# 第 3 轮的输入侧（D2a —— §8.3 的两层注入: 候选表 + 命中集载荷）
# ---------------------------------------------------------------------------

#: 候选表的**本地 id** 前缀 —— 真 entity id 是 `x`（`x0000`/`x0001` 还是保留号）,
#: 本地号必须换个前缀, 否则第 3 轮分不清"它复述的"和"我们真有的"。
LOCAL_PREFIX = "c"
#: **本轮新节点**的本地 id 前缀（`new_nodes_block`）—— ⚠️ 与 `LOCAL_PREFIX` **必须分开**:
#: 同一次调用里有两套本地号（对象 `c0001` / 节点 `u0001`）, 混用就等于让模型
#: 把"挂谁"和"挂在谁身上"写反, 而那种错**看起来完全正常**。
NODE_PREFIX = "u"
#: 字面匹配的**最小长度**。⚠️ 中文没有词边界: 单字称呼（"他"/"她"/"它"）**会命中
#: 每一段正文**; 而别名无论初始化还是"顺手写回"给的都是**名字**（"sensei"/"遥香"）,
#: 砍掉 1 字不丢真命中。hint 走精确相等, **不受此限**。
MIN_HIT_LEN = 2


def candidates(store: WikiStoreV2) -> list[BrainNode]:
    """候选对象 = 全部 entity（id 升序）。

    ⚠️ **无名的跳过**: 印一行光秃秃的 id 对第 3 轮毫无用处（它要靠名字做映射）,
    而 `validate` 本来就要求 entity 有 `name` ⇒ 这条只是防御。
    """
    return sorted((n for n in store.all()
                   if n.kind == "entity" and n.id and n.name.strip()),
                  key=lambda n: n.id)


def surface_forms(node: BrainNode) -> list[str]:
    """一个 entity 的**全部字面称呼** = `name` + `aliases`（去空、去重、保序）。

    `name` 在首位 —— 调用方靠这个约定取"除主名之外的别名"（`[1:]`）。
    """
    out: list[str] = []
    for f in (node.name, *node.aliases):
        f = str(f or "").strip()
        if f and f not in out:
            out.append(f)
    return out


def candidate_table(store: WikiStoreV2) -> tuple[str, dict[str, str]]:
    """候选表（§8.3 第一层）: `c0001 老师（sensei/阿宅）`。

    **只有身份** —— 名字 + 别名。载荷在 `payload_block`（两层分开是 §3.1 的量化结论:
    身份表便宜、载荷贵, 而膨胀命中的是载荷）。

    ⚠️ **不印类别**（2026-09-23 用户裁决）: `etype` 已裁决不做（§3.0）⇒ 那个"（人）"
    没有字段来源, 印了就是编。
    ⚠️ **本地 id**（同 Round B 的 `u0001`）: 真 id 不外泄, LLM 猜不出一个"像真的" id;
    `local_of`（真实 id → 本地 id）交给执行器解析 —— 与 `apply_decisions(id_map=…)` 同款。
    ⚠️ **不裁剪**（§8.5）: 几十条不构成注意力问题; 会膨胀的是载荷, 不是这张表。

    Returns:
        `(text, local_of)`；无 entity → `("", {})`（空态怎么呈现由调用方定）。
    """
    lines: list[str] = []
    local_of: dict[str, str] = {}
    for i, n in enumerate(candidates(store), start=1):
        local = format_id(LOCAL_PREFIX, i)
        local_of[n.id] = local
        aliases = surface_forms(n)[1:]                     # [0] 是 name
        suffix = f"（{'/'.join(aliases)}）" if aliases else ""
        lines.append(f"{local} {n.name.strip()}{suffix}")
    return "\n".join(lines), local_of


def hit_set(store: WikiStoreV2, *, hints=(), texts=()) -> list[str]:
    """命中集（§8.3 第二层的**确定性**规则）: `about_hint` ∪ 称呼命中本轮正文。

    ⚠️ **不靠 LLM**（设计写死的分工）: 第 1 轮说"我在写谁"（hint）、第 3 轮说"那对应
    表里的哪一个"（映射）; 引擎只负责"**这轮话里提到了谁**"。

    两条规则:
        · **hint**: 与某个称呼精确相等（忽略大小写）, 或 ≥2 字的包含（双向）。
          hint 是模型自己写的称呼 ⇒ 单字 hint 只可能是它真的这么称呼, **不受下限**。
        · **正文**: 称呼出现在 `texts` 里（短于 `MIN_HIT_LEN` 的称呼**不扫**）。

    Args:
        hints: 第 1 轮产出的 `about_hint`（`DigestResult.hints` —— **不落库**）
        texts: 本轮正文（调用方给: 新节点的 `text`, 需要时连 `title`/`verbatim`）

    Returns: 命中的 entity id（id 升序; 空 = 一个都没提到）。
    """
    hs = _strings(hints)
    texts_cf = [t.casefold() for t in _strings(texts)]
    out: list[str] = []
    for n in candidates(store):
        forms = surface_forms(n)
        if any(_hint_hits(h, forms) for h in hs) \
                or any(_body_hits(f, texts_cf) for f in forms):
            out.append(n.id)
    return out


def payload_block(store: WikiStoreV2, ids, local_of: dict[str, str]) -> str:
    """命中集的**当前载荷**（§8.3 第二层）: `立场`（`text`）+ `现状`（`state`）逐行。

    ```
    c0001 老师
      立场: 他是第一个不会嫌弃我的人
      现状:
        - 今天戴了眼镜
        - 手腕上贴着创可贴
    ```

    ⚠️ **只给命中集**: 全量载荷就是 §3.1 算出来的那个膨胀源（100 条 ≈ 1~2 万字/轮,
    而载荷是**每轮注入**的）。
    ⚠️ **`local_of` 必给, 且必须是 `candidate_table` 那一份**: 同一批对象印两套 id,
    第 3 轮会把同一个人的两行当成两个人。
    ⚠️ **不在 `local_of` 里的 id 跳过** —— 没在候选表里露过面的对象不许出现在载荷区
    （否则第 3 轮收到一个它无法引用的载荷）。
    ⚠️ **只有一行头 = 还没有载荷**（`text`/`state` 皆空）。这本身就是信息: "这条进了
    命中集, 但立场还没长出来, 该本轮写"（§8.3 的基线改写触发就看命中集）。
    ⚠️ `state` **一句一行**（不是拼成一段）: §3 的写纪律是"只改变化的那一行, 其余原样
    复制" —— 逐行才让重写是行对齐的。
    """
    blocks: list[str] = []
    for nid in ids:
        local = local_of.get(nid)
        node = store.get(nid) if local else None
        if node is None or node.kind != "entity":
            continue
        block = [f"{local} {node.name.strip()}"]
        if node.text.strip():
            block.append(f"  立场: {node.text.strip()}")
        states = [s for s in (str(x).strip() for x in node.state) if s]
        if states:
            block.append("  现状:")
            block += [f"    - {s}" for s in states]
        blocks.append("\n".join(block))
    return "\n".join(blocks)


def new_nodes_block(store: WikiStoreV2, ids) -> tuple[str, dict[str, str]]:
    """第 3 轮的第三块料: **本轮新节点**（本地 id `u0001..`）—— 归属的对象。

    ```
    u0001 [episode] 「模型店」 我把老师带到我路过很多年的那家模型店…
    u0002 [promise·kept] 周六模型店，有点等不及 —— 周六真的去了
    ```

    ⚠️ **只给本轮新节点**（§8 第 3 轮那栏）: R1 的 episode/画像 · R4 物化的 promise ·
    R2 新建的认知。**"被改写的旧节点"不在内**（§9-12 ⑤ 那条待裁 —— 它们今天归属不了,
    这是已知的洞, 不是遗漏）。
    ⚠️ 本地 id 前缀 `u`（与 R2 的认知列表**同款但不同一次调用**, 不会撞）——
    `local_of` 交给执行器解析（`apply_attribution(id_map=…)`）。
    ⚠️ 没有可归属的节点 → `("", {})`（调用方据此**不发**这次调用）。

    Returns: `(text, local_of)` —— `local_of` = 真实 id → 本地 id。
    """
    lines: list[str] = []
    local_of: dict[str, str] = {}
    i = 0
    for nid in ids:
        node = store.get(str(nid))
        if node is None or node.id in local_of:
            continue
        i += 1
        local = format_id(NODE_PREFIX, i)
        local_of[node.id] = local
        head = node.text.strip() if node.text else ""
        if node.title:
            head = f"「{node.title}」 {head}"
        if len(head) > 120:
            head = head[:120] + "…"
        lines.append(f"{local} {_node_tag(node)} {head}".rstrip())
    return "\n".join(lines), local_of


def _node_tag(node: BrainNode) -> str:
    """`[episode]` / `[belief]` / `[promise·已兑现]` —— 与 `render._kind_tag` 同形（一份口径）。"""
    from core.brain.wiki_v2.render import _kind_tag
    return _kind_tag(node)


def _hint_hits(hint: str, forms: list[str]) -> bool:
    """hint 命中某称呼: 精确相等（忽略大小写）或 ≥2 字包含（双向）。"""
    h = hint.casefold()
    for f in forms:
        fc = f.casefold()
        if h == fc or (len(hint) >= MIN_HIT_LEN and (h in fc or fc in h)):
            return True
    return False


def _body_hits(form: str, texts_cf: list[str]) -> bool:
    """称呼出现在本轮正文里（`texts_cf` 已 casefold）。短称呼不扫, 见 `MIN_HIT_LEN`。"""
    if len(form) < MIN_HIT_LEN:
        return False
    f = form.casefold()
    return any(f in t for t in texts_cf)


def _strings(v) -> list[str]:
    """非空字符串的干净列表（保序; 非字符串项忽略）。"""
    out: list[str] = []
    for x in v or ():
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out
