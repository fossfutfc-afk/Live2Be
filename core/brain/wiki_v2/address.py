# -*- coding: utf-8 -*-
"""address.py — **可见形式 → 节点**（地址解析）—— `marks.py` 的另一半。

`marks.py` : 节点 → 她看得见的形式（`〔《事件名》｜多久以前｜日期〕正文…`）—— **印**
本模块     : 她写下的形式 → 节点（`{"noticed": "…"}` / 将来的 `{"look": ["…"]}`）—— **剥**

⚠️ **印与剥必须同源**: 要剥的语法字符（书名号 / 方括号 / 引号 / 空白）与字段分隔符
都**从 `marks` 取**（`marks.STRIP_CHARS` / `marks.FIELD_SEP`）—— 此前本模块自己抄了一份
清单, 并在注释里**照名字引用**渲染侧那个函数（"`_meta_head` 用的那个"）: 那正是漂的入口。

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

from core.brain.wiki_v2 import marks

if TYPE_CHECKING:                       # 仅注解求值期可见（避免运行时循环导入）
    from core.brain.wiki_v2.nodes import BrainNode
    from core.brain.wiki_v2.store import WikiStoreV2

#: 要剥掉的**语法字符**（不是内容）与字段分隔符 —— ⚠️ **不在这里定义**:
#: 真源 = `marks.STRIP_CHARS` / `marks.FIELD_SEP`（印与剥同一份清单, 见模块 docstring）。


def normalize_title(raw: object) -> str:
    """她写下的串 → **候选名字**（只剥格式, 不做模糊匹配）。取不到 → `""`。"""
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if marks.FIELD_SEP in s:          # 把 `《名》｜5 天前｜9/26` 整段抄进来了
        s = s.split(marks.FIELD_SEP)[0]
    return s.strip(marks.STRIP_CHARS).strip()


def unique_title(store: WikiStoreV2, title: str, *, kind: str = "episode") -> str:
    """⭐ **唯一性写入时强制**（2026-09-29, `PROCEED §2 #10` 已裁的那条）——
    与既有名字冲突就**加数字**（`中秋的杂草屋` → `中秋的杂草屋 2`）。

    ⭐ **为什么它住在"地址"这一件里**（而不是写入方）: 唯一性是**地址空间的不变量**,
    不是某个写者的私事。解析（`find_episode`）与写入（本函数）必须在同一个模块里 ——
    否则"谁能被指到"这件事就散成了两处约定。

    ⭐ **判据链**（为什么值得做）: 引擎与她之间唯一的地址空间就是名字; 而 `find_episode`
    遇到同名 ≥2 **一律不猜**（丢）⇒ **重名不会出错, 只会漏**（命中率）。
    ⇒ 唯一性是**命中率的地基**, 在此之前它靠"LLM 起名恰好不撞"（真机 18/18 唯一）。

    ⚠️ **只增不重排**: 既有节点**一个都不动**（改的是**新来那条**）——
    否则她昨天抄下来的名字今天就指不到了（静默, 且只有真机看得出来）。
    ⚠️ **只管一个 kind 的命名空间**: `find_episode` 今天只在自己的 kind 里解析,
       跨 kind 唯一性**还没有消费者**（`§10` 说的"跨 kind"等 `look` 要多 kind 解析时再补）。
    ⚠️ 空名字**跳过**（`episode` 的必填只有 `text`; 没名字的节点本来就指不到,
       给它编一个"未命名 2"反而是替 LLM 创作）。
    """
    name = (title or "").strip()
    if not name:
        return name
    taken = {n.title for n in store.all() if n.kind == kind and n.title}
    if name not in taken:
        return name
    i = 2
    while f"{name} {i}" in taken:
        i += 1
    import logging
    logging.getLogger(__name__).info(
        "title_unique dedupe=%r → %r（写入时强制, 只增不重排）", name, f"{name} {i}")
    return f"{name} {i}"


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
