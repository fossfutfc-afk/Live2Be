# -*- coding: utf-8 -*-
"""address.py — **可见形式 → 节点**（地址解析）—— 与 `render.py` 对称的另一半。

`render.py`: 节点 → 她看得见的形式（`〔《事件名》｜多久以前｜日期〕正文…`）
本模块    : 她写下的形式 → 节点（`{"noticed": "…"}` / 将来的 `{"look": ["…"]}`）

⭐ **为什么单独一件**: 「名字 → 唯一节点」有两个调用者（**N5b 的 `noticed`** 与
**`look` 的三级解析第一级**）；两处各写一份必然漂——而漂了的后果是
**她指的东西与引擎找的东西不是同一个**（静默、且只有真机才看得出来）。
地址地基的裁决见 `PROCEED §2 #10/#11`：编号退回引擎内部, 标题是唯一地址空间。

## 三条纪律

1. ⚠️ **只归一格式, 不做近似匹配**（`normalize_title`）—— 剥的是**我们自己定的
   语法字符**（书名号 / 尖括号 / 引号 / 空白 / 元信息分隔符）, 不是"猜她本来想说谁"。
   近似匹配（子串 / 编辑距离 / 语义）**一律不做**: 那会把"她指错了"变成"引擎猜对了",
   而猜错的边是会进图的。
2. ⚠️ **命中 0 / 命中多条 ⇒ 不猜**（`find_episode` 返回原因, 由调用方决定丢还是回问）。
   今天标题的**唯一性还没有写入时强制**（`DESIGN_MMT_NEW_ACTION §4.6` 待做）,
   所以"歧义"是真会发生的分支, 不是防御性代码。
3. ⚠️ **空输入不是错, 是"没指"** —— 由调用方判（`reason="empty"`）。

格式归一清单（2026-09-29 用户裁决 + 实测）:
    书名号 `《》〈〉` · 尖括号 `<>` · 方括号 `【】〔〕` · 半全角引号 `"“”'‘’「」`
    · 首尾空白 · **含 `｜` 取第一段**（治"把整段元信息抄进来"）
⚠️ 归一**不改变语义**: 带不带书名号、带不带时间, 都归到同一个名字。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:                       # 仅注解求值期可见（避免运行时循环导入）
    from core.brain.wiki_v2.nodes import BrainNode
    from core.brain.wiki_v2.store import WikiStoreV2

#: 要剥掉的**语法字符**（不是内容）——见模块 docstring 的清单
_STRIP_CHARS = "《》〈〉<>【】〔〕\"“”'‘’「」 \t\r\n\u3000"

#: 元信息段的分隔符（`_meta_head` 用的那个）——她若整段抄进来, 只取第一段
_FIELD_SEP = "｜"


def normalize_title(raw: object) -> str:
    """她写下的串 → **候选名字**（只剥格式, 不做模糊匹配）。取不到 → `""`。"""
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if _FIELD_SEP in s:               # 把 `《名》｜5 天前｜9/26` 整段抄进来了
        s = s.split(_FIELD_SEP)[0]
    return s.strip(_STRIP_CHARS).strip()


def find_episode(store: WikiStoreV2, raw: object) -> tuple[BrainNode | None, str]:
    """名字 → **唯一** episode 节点。

    Returns: `(节点 | None, 原因)`, 原因 ∈

        `"ok"`         命中唯一一条
        `"empty"`      她没写（或归一后为空）—— **不是错误**
        `"miss"`       一条都不叫这个名字（编的 / 抄错字）
        `"ambiguous"`  有 ≥2 条同名 ⇒ **不猜**（今天唯一性未强制, 这是真分支）

    ⚠️ 只在 **episode** 的标题空间里解析（`DESIGN_MMT_NEW_ACTION §4.3`）:
    她指认的是"另一件**事**"; belief 是看法（全量常驻, 没有"同一件事"可言）,
    entity/group 各有各的用法 —— 都不在这里认。
    """
    name = normalize_title(raw)
    if not name:
        return None, "empty"
    hits = [n for n in store.all() if n.kind == "episode" and n.title == name]
    if not hits:
        return None, "miss"
    if len(hits) > 1:
        return None, "ambiguous"
    return hits[0], "ok"
