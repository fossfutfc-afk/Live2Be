# -*- coding: utf-8 -*-
"""entities.py — entity 的初始化与（后续）消解辅助（`DESIGN_GRAPH_V4.md` §3.0）。

**本文件只有一件事现在能跑**: `ensure_entities` —— 开局把两个 entity 建出来。

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

⚠️ 名字读取目前散在 3~4 处（`_name_aliases` 私有在 mmt 引擎、"id→显示名, sensei→老师"
在 bond router / vn_cli / bond engine 各一份）—— **"上升为统一接口"已记为一个独立节点**
（多人模式的显示名也要用），届时本文件的调用方换成那个接口即可, 本文件不变。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 保留号（见模块 docstring）
SELF_ID = "x0000"
SENSEI_ID = "x0001"

#: sensei 的默认识别名（角色视角怎么称呼玩家）
SENSEI_NAMES = ("老师", "sensei")


def ensure_entities(store, *, char_name: str = "", aliases=(), player_name: str = "",
                    player_aliases=()) -> list[str]:
    """**初始化**: 没有就建 self(x0000) + sensei(x0001); 返回**本次新建**的 id 列表。

    幂等: 按 id 判存在, 已有则跳过 —— 反复调用不写盘、不改数据（调用方自己决定 save）。
    名字全空也能建（`name` 是唯一必填, 但 `validate` 只认"非空白字符串"——
    所以这里兜一个 `char_id`/占位名, 免得整条被拒）。

    Args:
        char_name: 角色自己的显示名（`REQ~most_called_name`）; 空 → 不建 self 的 name?
            ⚠️ 不 —— `name` 是 entity 的**必填**, 空名字的 entity 会被 `store.add` 拒。
            所以 char_name 为空时**跳过建 self**（宁缺勿错: 宁可不建, 不建一个没名字的）。
        aliases: 角色别名（`other_names`/`jp_name`/`en_name` 切分后的; 由调用方给）
        player_name: 玩家自己的名字（GUI 可配; 会进 sensei 的 aliases）
        player_aliases: 玩家名的其它说法
    """
    out: list[str] = []
    if SELF_ID not in store and char_name.strip():
        out.append(store.add(_entity(SELF_ID, char_name, aliases)))
    elif SELF_ID not in store:
        logger.warning("ensure_entities: 没给 char_name → **跳过**建 self（%s）——"
                       "name 是 entity 的必填, 宁可不建也不建个没名字的", SELF_ID)

    if SENSEI_ID not in store:
        aliases_s = list(SENSEI_NAMES[1:])                  # "sensei"（"老师"当主名）
        for extra in (*player_aliases, player_name):
            if extra and extra.strip() and extra.strip() not in (SENSEI_NAMES[0], *aliases_s):
                aliases_s.append(extra.strip())
        out.append(store.add(_entity(SENSEI_ID, SENSEI_NAMES[0], aliases_s)))
    return out


def _entity(nid: str, name: str, aliases):
    """建一个只有身份的 entity（`text`/`state` 留空 —— 立场由第 3 轮从记忆里长出来）。

    ⚠️ 用 `BrainNode` 直接构造 + 钉 id（**不是** `make_node`, 那条路会走 `from_dict`;
    而 `from_dict` 现在认得 entity 了, 但显式钉 id 更直白 —— 保留号不能被自动分配覆盖）。
    """
    from core.brain.wiki_v2.nodes import BrainNode
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
