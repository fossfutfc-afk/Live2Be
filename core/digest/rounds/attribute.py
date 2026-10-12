"""attribute.py — ④ R3「认人」: 她写下的**陌生名字** ⇒ 建一个新的 `entity`。

⭐ **2026-10-08（E4）重定义**: 这一轮从"归属 + 载荷维护"（`attach`/`new_entity`/`rewrite`
三动作）缩成**只认人**。判据 = `docs/DESIGN_ENTITY_TAGS.md`:
  · 她只在**写节点时**在 `tags` 里带 `#entity:名字`（R1 写经历 · L2 写看法）;
  · 引擎按那个标记落 `about` 边（`revise.link_entity_tags`）—— **解析不到的**原样留着;
  · 那些"解析不到的"就是这一轮的**全部输入** ⇒ **没有陌生人 ⇒ 一次调用都不发**;
  · 建完对象**回头补边**: 本段那些 `#entity:<新名字>` 现在解析得到了 ⇒ 落边 + 归一
    （同一段内闭合, 零 LLM）。

⛔ **它不写正文**: entity 的"印象 / 现状"归 **belief**（`DESIGN_ENTITY_TAGS §6.1` ——
`entity.text` 那一格今天没有读者, 而 note 那条路已被 `on_mind`/`habits` 的退役判据封死）。

⚠️ **为什么它排在最后**: 它要看到**本段全部新节点**（R1 的经历/画像 + L2 的看法）——
陌生名字可能第一次出现在任何一条里。
⚠️ **料里没有本地号**: 她只写名字（`reason` 是准入门槛）—— 旧的 `c0001`/`u0001` 两套本地号
随 `attach`/载荷一起退休（"挂谁"这件事已经归 `tags` 了）。
"""
from __future__ import annotations

import logging

from core.brain.entities import (find_entity, object_lines, strangers_block,
                                 surface_forms)
from core.brain.revise import apply_entities, link_entity_tags
from core.digest.material import _node_texts
from core.digest.rounds.base import Ctx, RoundOut

logger = logging.getLogger(__name__)


def _segment_ids(ctx: Ctx) -> list[str]:
    """本段**全部新节点**（R1 的经历/画像 + L2 的看法）—— 陌生名字的搜索面。"""
    return [*ctx.episode_ids, *ctx.player_ids, *ctx.result.created_beliefs]


def _strangers(ctx: Ctx, ids: list[str]) -> list[str]:
    """本段节点 `tags` 里那些 `#entity:` **解析不到**的名字（引擎算, 不是再读一遍正文猜）。"""
    out: list[str] = []
    for nid in ids:
        node = ctx.store.get(str(nid))
        if node is None:
            continue
        for t in (node.tags or []):
            s = str(t).strip()
            if not s.startswith("#entity:"):
                continue
            name = s[len("#entity:"):].strip()
            if name and find_entity(ctx.store, name)[0] is None:
                out.append(name)
    return list(dict.fromkeys(out))


def run(ctx: Ctx) -> RoundOut:
    """④ 认人 —— 本段那些"她写了、但库里没有"的名字 ⇒ 建对象 + **回头补边**。"""
    spec = ctx.enter("attribute")
    ids = _segment_ids(ctx)
    strangers = _strangers(ctx, ids)
    if not strangers:
        # ⭐ **事件驱动**: 没有陌生人 ⇒ 一次调用都不发（这是 E4 的成本判据）
        ctx.log_skip(spec)
        return RoundOut.skipped()
    # ⚠️ **故意还是 `casefold`**（不是 `entities.form_key`）: 这个集合要交给
    #    `contract/digest_registry.parse_attribution`, 而**契约层不许 import core**
    #    （`tests/core/test_import_direction.py`）⇒ 想两端同时换成 `form_key`,
    #    得先把那个纯字符串件**下移到 `contract/`（或 `core.common`）** —— 那是代码组织的活。
    #    今天不影响正确性: 执行层 `revise.apply_entities` 用 `find_entity`（**已经是 form_key**）
    #    再挡一道 ⇒ 这里只是"早一步、友好地"丢行, 差别只在台账那一笔。
    known = {f.casefold() for n in ctx.store.all() if n.kind == "entity"
             for f in surface_forms(n)}
    obj_text, _obj_ids = object_lines(ctx.store, texts=_node_texts(ctx.store, ids))
    system = ctx.system_for(spec)
    user = ctx.sections_for(spec, [
        ("要认的名字", strangers_block(ctx.store, ids, strangers)),
        ("已有的对象", obj_text or "（还没有任何对象）"),
        ("角色人设（锚点）", ctx.character_prompt),
    ])
    rows, _resp = ctx.call(spec, system, user,
                           parse_fn=ctx.parse_for(spec, known_names=known))
    if rows is None:
        return RoundOut.failed()
    ctx.result.created_entities = apply_entities(
        ctx.store, rows, ts=ctx.now_ts, event_seq=[ctx.interact_max])
    # ⭐ **建完补边**: 重扫本段全部节点 —— 刚才那个名字现在解析得到了 ⇒ 落 `about` + 归一 tag
    linked = 0
    for nid in ids:
        targets, _left = link_entity_tags(ctx.store, nid, ts=ctx.now_ts)
        linked += len(targets)
    logger.info("digest_attribute strangers=%d rows=%d new=%d linked=%d",
                len(strangers), len(rows), len(ctx.result.created_entities), linked)
    return RoundOut.done()
