"""entities.py — entity 的初始化 + 第 3 轮的**输入侧**（`DESIGN_GRAPH_V4.md` §3.0 / §8.3）。

| 函数 | 谁用 | 干什么 |
|---|---|---|
| `ensure_entities` | D3 编排 | 开局把 `self` + `sensei` 建出来（保留号 + 幂等） |
| `candidate_table` | 第 3 轮 prompt | 全量候选表（§8.3 第一层）—— **只有身份**: 本地 id + 名字 + 别名 |
| `hit_set` | 第 3 轮 prompt | 命中集 —— 称呼命中本轮正文（**确定性, 不靠 LLM**） |
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

## ⭐ 名字匹配的**唯一归一** = `form_key`（2026-10-12）

匹配面永远是 `surface_forms(node)`（`name` + `aliases`）—— `form_key` 只是**归一**,
不是第二种匹配面。它做两件事：**去掉所有空白** + `casefold`。

为什么去空白（用户 2026-10-12: *"注意处理空格"*）: 卡上的主名中间就带一个空格
（`伊草 遥香` / `陆八魔 阿露` / `浅黄 睦月` / `鬼方 佳代子`），而 brain 段的
「我知道的名字」**印的就是她要照抄的键** —— 少打/多打一个空白就 `miss`（`look(entity=…)`
返回 `LOOK_EMPTY_ENTITY`、P19 的 `name` 段静默不开）是不能接受的。
⇒ `伊草遥香` ≡ `伊草 遥香` ≡ `伊草  遥香`（`str.split()` 按 Unicode 空白切, 含全角 U+3000）。

⛔ **别在调用方再 `casefold()` 一遍**（同一套归一只有这一处）;
⚠️ **四个用它的地方**（2026-10-12 起含 `hit_set`）: `find_entity`（`look` 的 `entity` 轴 +
digest 的 `#entity:` 认人）· `like.build_ctx`（P19 的 `name` 段触发面）·
`_materialize_stances` 的幂等键（否则 `伊草遥香` 与 `伊草 遥香` 会被当成两个人各建一个）·
`hit_set`/`_body_hits`（R3 的**正文扫描** —— 两边都归一, 见 `_body_hits` 的实测注）。
⚠️ **digest 侧还有一处它自己的归一**（`rounds/attribute.py` 的 `known` 集合）—— 同样走 `form_key`。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from contract import CHARACTER_SENSEI, DEFAULT_SPEAKER_NAMES
from contract.digest_registry import ENTITY_TAG_PREFIX
from core.brain import marks
from core.brain.nodes import BrainNode, format_id

if TYPE_CHECKING:                       # 仅注解求值期可见（避免运行时循环导入）
    from core.brain.store import WikiStoreV2

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
                    player_aliases=(), sensei_name: str = "", sensei_aliases=(),
                    stances=()) -> list[str]:
    """**初始化**: 没有就建 self(x0000) + sensei(x0001) + ⭐ **她认识的人**;
    返回**本次新建**的 id 列表。

    幂等（反复调用不写盘、不改数据 —— 调用方自己决定 save）:
      · self / sensei ⇒ 按**保留 id** 判;
      · 她认识的人 ⇒ 按**名字**判（`surface_forms` 撞上就算已有）, ⭐ 撞上时**只填空 text**
        —— 绝不覆盖 digest 后来长出来的立场。

    ⭐ `stances`（2026-10-08 加, 用户裁"**出厂就要有她的看法**"）:
        `(键, 主名, 别名, 立场)` 的序列 —— 来自 `interperson.yml` 的自表条目。
        ⚠️ **名字已由调用方解析好**: 本模块是 brain 层（**纯 stdlib, 不许读 config**）,
        所以"给了 `id` 的从角色档案取显示名/别名"那一步住在 `mmt/engine.py::_stances_of`。
        · 键 ∈ {`self`, `sensei`} ⇒ **不建新的**, 只把立场填进那个保留号（text 空才填）;
        · 别的键 ⇒ 建 entity（`text` = 立场）; 名字空 ⇒ **跳过 + warning**（宁可不建,
          也不建个没名字的 —— 同 `char_name` 空那条纪律）。

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

    out.extend(_materialize_stances(store, stances))
    return out


#: `stances` 里代表保留号的两个键（**不是**角色的叫法 —— 见 `ensure_entities`）
STANCE_KEYS_RESERVED = ("self", "sensei")


def _materialize_stances(store, stances) -> list[str]:
    """把**她认识的人**建出来（`stances` = `(键, 主名, 别名, 立场)` 序列）。

    ⭐ **出厂就有看法**（2026-10-08 用户裁）: `text` 不是等 digest 从记忆里长,
    而是作者在 `interperson.yml` 里写好的那句 → 建的时候一起装上。
    ⚠️ 它是 `entity.text` 的**初值**; 之后 R3 照旧可以改写（看法随经历演化）。

    幂等**按名字**（不是按 id）: `surface_forms` 撞上就算"这个人已经有了"。
    ⭐ 撞上时**只填空 `text`** —— 绝不覆盖她后来长出来的立场（那是她的东西）。

    Returns: 本次**新建**的 id 列表（调用方据此决定要不要写盘）。
    """
    by_form: dict[str, BrainNode] = {}
    for node in store.all():
        if getattr(node, "kind", "") != "entity":
            continue
        for form in surface_forms(node):
            by_form.setdefault(form_key(form), node)

    made: list[str] = []
    for key, name, aliases, text in stances:
        stance = str(text or "").strip()
        key = str(key or "").strip()
        if key in STANCE_KEYS_RESERVED:
            # 保留号: **不建新的**, 只把立场填进去（text 空才填）
            node = store.get(SELF_ID if key == "self" else SENSEI_ID)
            if node is not None and not str(node.text or "").strip() and stance:
                node.text = stance
                logger.info("entity 立场: %s ← interperson(%s)", node.id, key)
            continue
        name = str(name or "").strip()
        if not name:
            logger.warning("ensure_entities: 表里 %r 没解析出名字 → 跳过"
                           "（name 是 entity 的必填, 宁可不建）", key)
            continue
        hit = by_form.get(form_key(name))
        if hit is not None:
            if not str(hit.text or "").strip() and stance:
                hit.text = stance
                logger.info("entity 立场: %s ← interperson(%s, 名字撞上已有)",
                            hit.id, key)
            continue
        nid = store.next_id("x")
        node = _entity(nid, name, aliases, text=stance)
        store.add(node)
        for form in surface_forms(node):
            by_form.setdefault(form.casefold(), node)
        made.append(nid)
        logger.info("entity 出厂: %s %s（interperson 键 %s）", nid, name, key)
    return made


def _entity(nid: str, name: str, aliases, *, text: str = ""):
    """建一个 entity。**`text` = 立场**（出厂的印象; 不写 = 等她从记忆里长出来）。

    ⚠️ 用 `BrainNode` 直接构造 + 钉 id（**不是** `make_node`, 那条路会走 `from_dict`;
    而 `from_dict` 现在认得 entity 了, 但显式钉 id 更直白 —— 保留号不能被自动分配覆盖）。
    """
    node = BrainNode()
    node.id = nid
    node.kind = "entity"
    node.name = name.strip()
    node.text = str(text or "").strip()
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
#: 砍掉 1 字不丢真命中。
MIN_HIT_LEN = 2


def candidates(store: WikiStoreV2) -> list[BrainNode]:
    """候选对象 = 全部 entity（id 升序）。

    ⚠️ **无名的跳过**: 印一行光秃秃的 id 对第 3 轮毫无用处（它要靠名字做映射）,
    而 `validate` 本来就要求 entity 有 `name` ⇒ 这条只是防御。
    """
    return sorted((n for n in store.all()
                   if n.kind == "entity" and n.id and n.name.strip()),
                  key=lambda n: n.id)


def form_key(text: object) -> str:
    """名字匹配的**唯一归一**: **去掉所有空白** + `casefold`（2026-10-12, 见模块 docstring）。

    ⚠️ 它是**归一**，不是第二种匹配面 —— 匹配面仍是 `surface_forms`。
    ⛔ 调用方拿到结果后**不要再 `casefold()`**（同一套归一只有这一处实现）。
    """
    return "".join(str(text or "").split()).casefold()


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


def hit_set(store: WikiStoreV2, *, texts=()) -> list[str]:
    """命中集（§8.3 第二层的**确定性**规则）: 称呼命中本轮正文。

    ⚠️ **不靠 LLM**（设计写死的分工）: 引擎只负责"**这轮话里提到了谁**",
    "这条挂谁"由 R3 判。

    ⚠️ **2026-09-29 起只剩这一条通道** —— 参数 `hints=` 与 `_hint_hits` 随 R1 的
    `about_hint` 一起退役（那个字段与 R3 的"挂谁"判两次, 还可能不一致）。离线预演
    （真机 haruka 21 条 episode）: 正文通道 **22/22** 命中, 另加 tags 一条也没多救回
    ⇒ 正文就是全部（`REDUNDANCY.md` §十）。

    规则: 称呼出现在 `texts` 里（短于 `MIN_HIT_LEN` 的称呼**不扫** —— 中文没有词边界）。
    ⭐ **2026-10-12: 两边都过 `form_key`**（去空白 + casefold）—— 与 `find_entity` /
    `like.build_ctx` **同一套归一**（见模块 docstring）: 卡上的名字带一个空格
    （`伊草 遥香`）而正文多半写成 `伊草遥香` ⇒ 逐字比会把这个人整条漏掉（**静默**）。

    Args:
        texts: 本轮正文（调用方给: 新节点的 `text`, 需要时连 `title`/`verbatim`）

    Returns: 命中的 entity id（id 升序; 空 = 一个都没提到）。
    """
    texts_key = [form_key(t) for t in _strings(texts)]
    out: list[str] = []
    for n in candidates(store):
        forms = surface_forms(n)
        if any(_body_hits(f, texts_key) for f in forms):
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
    〔u0001｜《模型店》｜episode〕我把老师带到我路过很多年的那家模型店…
    〔u0002｜belief〕老师是真的记得我说过的话
    ```

    ⭐ **2026-09-29 形状变化**（原来 `u0001 [episode] 「模型店」 正文`）: 类型与名字
    **都进头**（`marks.head` —— 括号表唯一实现）。理由: 头里**第一格恒是钥匙、
    名字带书名号**, 而 `[episode]` 那个方括号按括号表另有含义（历史动作前缀）;
    旧形状把"类型"留在头外面 ⇒ **闸门漏一格**, 将来谁都能再往行首塞一段裸文本。
    ⚠️ **截断只截正文**（原来把"标题 + 正文"一起截到 120）—— 头里的名字是**地址**,
    截一半就等于把地址截坏。

    ⚠️ **只给本轮新节点**（§8 第 3 轮那栏）: R1 的 episode/画像 · R2 新建的认知。
    （⏸ 原还有"R4 物化的 promise"—— promise 2026-09-29 退图, 不再有新节点。）
    **"被改写的旧节点"不在内**（§9-12 ⑤ 那条待裁 —— 它们今天归属不了,
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
        body = node.text.strip() if node.text else ""
        if len(body) > 120:
            body = body[:120] + "…"
        lines.append(f"{marks.head(node, key=local, kind=True)}{body}".rstrip())
    return "\n".join(lines), local_of


# ⏸ `_node_tag` **2026-09-29 删** —— 类型标签的真源 = `marks.kind_tag`（**不带方括号**）。
# 它当年是"延迟 import `render._kind_tag` 再 `strip('[]')`": 同一个标签两个形状, 正是
# "散"的典型。现在 `head(kind=True)` 直接把 `marks.kind_tag` 放进头里, 不再需要它。


def find_entity(store: WikiStoreV2, raw: object) -> tuple[BrainNode | None, str]:
    """名字 → **唯一** entity（E1, 2026-10-08）—— `#entity:<名字>` 的解析走它。

    判据与 `address.find_episode` / `find_group` **同一套**: 只归一格式（首尾空白）,
    **不做近似匹配**; 命中 0 / 多条 ⇒ **不猜**（返回原因, 由调用方决定丢还是留着）。

    Returns: `(节点 | None, 原因)`, 原因 ∈
        `"ok"` 命中唯一一个 · `"empty"` 没写名字（**不是错误**）·
        `"miss"` 谁都不叫这个名字（可能是**还没建的人**）· `"ambiguous"` ≥2 个都叫

    ⚠️ 匹配面 = `surface_forms`（`name` + `aliases`）经 **`form_key` 归一**
    （去空白 + casefold, 见模块 docstring）—— 那是"她可能怎么称呼他"的唯一真源;
    ⛔ 不在这里发明第二种匹配。
    """
    name = str(raw or "").strip()
    if not name:
        return None, "empty"
    want = form_key(name)
    hits = [n for n in candidates(store)
            if want in {form_key(f) for f in surface_forms(n)}]
    if not hits:
        return None, "miss"
    if len(hits) > 1:
        return None, "ambiguous"
    return hits[0], "ok"


def normalize_entity_tags(store: WikiStoreV2, tags
                          ) -> tuple[list[str], list[str], list[str]]:
    """`tags` 里的 `#entity:<她写的叫法>` → **归一成主名**; 解析不到的**原样留着**。

    Returns: `(归一后的 tags, 能落边的对象 id, 陌生的名字)`

    ⭐ **第三个返回值就是"该建这个人"的线索**（E1 §1 的洞①）: `about` 的值必须是
    **已存在的 id** ⇒ 她本来**没有语法**表达"这条关于一个我还不知道的人"; 现在
    `#entity:小玉` 填上了它 —— 引擎**原样保留**那条 tag（不落边、不报错）, 把它报上去,
    等认人那一轮把对象建出来之后**再补边**。

    ⚠️ 本函数是**纯查**（不写边、不改库）—— 本文件是"喂给轮次看什么"的输入侧,
    写路径在 `core/digest/episodes._link_about`。
    ⚠️ 归一可能把两条并成一条（`#entity:老师` + `#entity:sensei`）⇒ 输出**去重保序**。
    """
    out: list[str] = []
    targets: list[str] = []
    strangers: list[str] = []
    for t in (tags if isinstance(tags, (list, tuple)) else []):
        s = str(t).strip()
        if not s:
            continue
        if not s.startswith(ENTITY_TAG_PREFIX):
            out.append(s)
            continue
        name = s[len(ENTITY_TAG_PREFIX):].strip()
        node, _reason = find_entity(store, name)
        if node is None:
            strangers.append(name)
            out.append(s)                       # ⭐ 原样留着（陌生人不丢）
            continue
        out.append(f"{ENTITY_TAG_PREFIX}{surface_forms(node)[0]}")   # 归一成主名
        targets.append(node.id)
    return (list(dict.fromkeys(out)), list(dict.fromkeys(targets)),
            list(dict.fromkeys(strangers)))


def strangers_block(store: WikiStoreV2, ids, names) -> str:
    """【要认的名字】—— R3（只认人）的**唯一理由**: 这些名字她写了, 但库里没有。

    每个名字下面摆**它出现在哪几条里**（`〔m0023｜《...》〕` + 那一行里含它的那句话）——
    那是她判"**这是不是一个值得记住的人/地方/东西**"的全部依据。

    ⚠️ 名字来自节点 `tags` 里的 `#entity:`（`normalize_entity_tags` 的第三个返回值,
    **引擎算出来的**, 不是 LLM 再读一遍正文猜的）⇒ 它与"她当时想指谁"是同一次判断。
    """
    out: list[str] = []
    for name in dict.fromkeys(str(n).strip() for n in names if str(n).strip()):
        out.append(f"{name}")
        for nid in ids:
            node = store.get(str(nid))
            if node is None:
                continue
            body = "\n".join(x for x in (node.title, node.text) if x)
            if name not in body:
                continue
            line = next((s.strip() for s in body.splitlines() if name in s), "")
            # ⚠️ 信息头**整条从 `marks.head` 取**（守门: 代码字面量里零手写 `《》〔〕｜`;
            # 它按 kind 自动决定"名字"那一格要不要印 —— 看法没有标题, 就不印）
            head = marks.head(node, key=str(nid))
            out.append(f"    {head}" + (f"…{line[:80]}" if line else ""))
    return "\n".join(out)


def entity_label(node) -> str:
    """⭐ **一个对象的印法**（`x0001 老师（sensei）`）—— **全仓唯一一处**。

    收它的理由（架构自检）: L1 的对象候选表与 L2 的「关于谁」两处都要印同一行,
    而"名字 + 别名"的拼法各写一份必然漂 —— 那个漂就是"同一张图在两处长得不一样"。
    ⚠️ 别名取 `surface_forms(n)[1:]`（第 0 个就是 `name`）—— 与命中判据**同源**。
    """
    aliases = surface_forms(node)[1:]
    suffix = f"（{'/'.join(aliases)}）" if aliases else ""
    return f"{node.id} {node.name.strip()}{suffix}"


def object_lines(store: WikiStoreV2, *, texts=()) -> tuple[str, list[str]]:
    """⭐ **L1（判关系）的对象候选**: 全量表（**真实 id**） + 一行字面命中提示。

    ```
    x0000 伊草 遥香（遥香）
    x0001 老师（sensei）
    → 候选: x0001（本段文本里出现了这个称呼）
    ```

    为什么与 `candidate_table`（第 3 轮的候选表）**不共用**:
      · 那边印**本地号**（`c0001` —— "防 LLM 猜真实 id", 由 `apply_attribution` 翻回来）;
      · L1 的契约印的是**真实 id**（`docs/DESIGN_DIGEST_TWO_PASSES §9.1` 的例子就是
        `{"episode": "m0014", "about": "x0001"}`）⇒ 执行侧（`apply_relations`）不需要翻译。
      ⚠️ 两套 id 混在同一次调用里才是灾难; 分开两次调用各印一套, 各自闭环。

    ⭐ **命中提示是"摆事实"不是"判归属"**（`DESIGN_DIGEST_TWO_PASSES §10.3`）:
    "本段文本里出现过这个称呼"是**字面命中**（确定性, `hit_set`）—— 挂不挂由 L1 判。

    Returns: `(text, ids)`；`ids` = 全部候选对象的真实 id（喂 parse 的 `entity_ids`）。
        一个 entity 都没有 ⇒ `("", [])`。
    """
    rows = candidates(store)
    if not rows:
        return "", []
    hits = set(hit_set(store, texts=texts))
    lines: list[str] = [entity_label(n) for n in rows]      # 印法唯一一处（`entity_label`）
    if hits:
        named = [f"{n.id}（{n.name.strip()}）" for n in rows if n.id in hits]
        lines.append(f"→ 候选: {'·'.join(named)}（本段文本里出现了这个称呼）")
    return "\n".join(lines), [n.id for n in rows]


def _body_hits(form: str, texts_key: list[str]) -> bool:
    """称呼出现在本轮正文里（`texts_key` 已 `form_key` 归一）。短称呼不扫, 见 `MIN_HIT_LEN`。

    ⚠️ **长度按归一后的算**（`len(key)`）: `阿 ` 这种"带空白的两字符"归一后是单字,
    放行就等于让一个单字去扫全文（中文没有词边界 —— `MIN_HIT_LEN` 挡的正是这个）。
    ⚠️ 正文一侧也去空白 ⇒ 理论上存在"跨空白拼出一个名字"的误命中（`并没有 月色` 里
    拼出 `无月`）。**真档实测（2026-10-12, haruka 21 条 episode × 4 个 entity）:
    逐字 / 单边归一 / 双边归一 三种口径的命中集**完全相同** ⇒ 今天零误命中;
    换来的是"名字带空格 vs 正文不带"这条整类漏检消失。要收紧就只归一 form 一侧
    （代价: 正文写成 `伊草 遥香` 时反过来漏）。
    """
    key = form_key(form)
    if len(key) < MIN_HIT_LEN:
        return False
    return any(key in t for t in texts_key)


def _strings(v) -> list[str]:
    """非空字符串的干净列表（保序; 非字符串项忽略）。"""
    out: list[str] = []
    for x in v or ():
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out
