"""settle.py — ④「沉淀」: 认人（建**长期对象**）+ 改名 / 写看法（⏸ 后两件待接线）。

⭐ **2026-10-13 改名 + 扩职**（`attribute` → `settle`）—— **这一轮的活分三截落地**:
  · **命名**: 相位 / prompt 文件名 / 任务标签 / 日志前缀全跟着 key 派生（见 `tables.PHASE_SETTLE`）✅ 已落;
  · **文案与料**: 契约与 llm prompt 扩成"认人 + 改名 / 写看法", 并新增料
    【这一段认下的对象】（`material.settle_objects_block`）✅ 已落;
  · ⏸ **执行**: `_strangers` / `apply_entities` 今天**仍只认人** —— 她这一趟若写
    `{"id": …, "text" / "name": …}` 的行, 契约层会**静默丢掉**（下一半补 `allowed_names`
    闭环 + `parse_attribution` 的两路 + `revise.apply_stances` + `text_seq` 水位）。

⭐ **它为什么排在最后**: 要看到**本段全部新节点**（R1 的经历 + L2 的看法）—— 陌生名字可能
第一次出现在任何一条里; 而"写看法"同样要看到这一段**全部**提到过它的地方。
⚠️ **它只动 `entity` 与 `about` 边**, 一个字都不写进 episode / belief。
⚠️ **料里没有本地号**: `entity` 用**真身**（`x0001` —— 与 L1 的对象端同一个印法,
`object_lines` 也是真身）, ⛔ 不引第三套本地号（`payload_block` 的老 docstring 记着那个病:
同一批对象印两套 id ⇒ 同一个人的两行被当成两个人）。

⛔ **一条旧判据已作废**（别把它捡回来）: 本文件从前写着"**它不写正文**: `entity.text` 那一格
今天没有读者 ⇒ 印象归 belief"（`DESIGN_ENTITY_TAGS §6.1`）—— **那条理由 2026-10-12 就死了**:
名表现在每轮印 `- 主名：看法`（`render._known_line`）, 它是**每轮都在的**读者。
⇒ 分工改成**粒度**问题: `belief` = 一条**结论**（有 `supports` 边、能进化 / 打架）;
`entity.text` = 对**这一个人**的一句话总览（单槽改写 ⇒ 要防漂, 见契约里那三条）。
"""
from __future__ import annotations

import logging

from core.brain.entities import find_entity, object_lines, strangers_block, surface_forms
from core.brain.revise import apply_entities, apply_stances, link_entity_refs
from core.digest.material import _node_texts, settle_objects_block
from core.digest.rounds.base import Ctx, RoundOut

logger = logging.getLogger(__name__)


def _segment_ids(ctx: Ctx) -> list[str]:
    """本段**全部新节点**（R1 的经历 + L2 的看法）—— 陌生名字的搜索面。

    ⏸ 原来还并 `ctx.player_ids`（玩家画像）—— 2026-10-14 随 `profile` 删。
    """
    return [*ctx.episode_ids, *ctx.result.created_beliefs]


def _strangers(ctx: Ctx, ids: list[str]) -> list[str]:
    """本段节点 `entity` 字段里那些**解析不到**的名字（引擎算, 不是再读一遍正文猜）。

    ⚠️ **2026-10-13**: 从"扫 `tags` 里的 `#entity:` 前缀"改成**读独立字段**
    （`node.entity`, 名字就是她写的那个叫法）—— 老档的搬迁在 `nodes.BrainNode.from_dict`
    （**读一次**就把它挪进字段）。
    ⚠️ 这一格也是"名单只扫**本段新节点**"的证据: "这一段让我想记住的人"完全可能不在名单里
    （她当时没标引用）⇒ 名单是**提示**不是笼子（见 `parse_attribution` 的 docstring）。
    """
    out: list[str] = []
    for nid in ids:
        node = ctx.store.get(str(nid))
        if node is None:
            continue
        for name in (node.entity or []):
            s = str(name).strip()
            if s and find_entity(ctx.store, s)[0] is None:
                out.append(s)
    return list(dict.fromkeys(out))


def run(ctx: Ctx) -> RoundOut:
    """④ 沉淀 —— 认人（建新对象）+ 改名 / 写看法（改已有的对象）。"""
    spec = ctx.enter("settle")
    ids = _segment_ids(ctx)
    strangers = _strangers(ctx, ids)
    obj_text, obj_ids = settle_objects_block(ctx.store, ids, now=ctx.now_ts)
    if not strangers and not obj_ids:
        # 没有陌生人、也没提到任何认识的对象 ⇒ 这一趟没有活干（**跳过不是失败**）
        ctx.log_skip(spec)
        return RoundOut.skipped()
    # ⚠️ **故意还是 `casefold`**（不是 `entities.form_key`）: 这个集合要交给
    #    `contract.digest.parse.parse_attribution`, 而**契约层不许 import core**
    #    （`tests/core/test_import_direction.py`）⇒ 想两端同时换成 `form_key`,
    #    得先把那个纯字符串件**下移到 `contract/`（或 `core.common`）** —— 那是代码组织的活。
    #    今天不影响正确性: 执行层 `revise.apply_entities` 用 `find_entity`（**已经是 form_key**）
    #    再挡一道 ⇒ 这里只是"早一步、友好地"丢行, 差别只在台账那一笔。
    known = {f.casefold() for n in ctx.store.all() if n.kind == "entity"
             for f in surface_forms(n)}
    have_text, _have_ids = object_lines(ctx.store, texts=_node_texts(ctx.store, ids))
    system = ctx.system_for(spec)
    user = ctx.sections_for(spec, [
        ("这一段认下的对象", obj_text),
        ("她写了、但库里还没有的名字", strangers_block(ctx.store, ids, strangers)),
        ("已有的对象", have_text or "（还没有任何对象）"),
        ("角色人设（锚点）", ctx.character_prompt),
    ])
    rows, _resp = ctx.call(
        spec, system, user,
        parse_fn=ctx.parse_for(spec, known_names=known, object_ids=set(obj_ids)))
    if rows is None:
        return RoundOut.failed()
    # ⭐ **一行一个对象, 靠 `id` 分路**（`parse_attribution` 已经分好）
    creates = [r for r in rows if r.get("action") == "create"]
    updates = [r for r in rows if r.get("action") == "update"]
    ctx.result.created_entities = apply_entities(
        ctx.store, creates, ts=ctx.now_ts, event_seq=[ctx.interact_max])
    stances = apply_stances(ctx.store, updates, ts=ctx.now_ts,
                            event_seq=[ctx.interact_max])
    ctx.result.renamed_entities = list(stances.renamed)
    ctx.result.rewritten_entities = list(stances.rewritten)
    # ⭐ **建完补边**: 重扫本段全部节点 —— 刚才那个名字现在解析得到了 ⇒ 落 `about` + 归一
    linked = 0
    for nid in ids:
        targets, _left = link_entity_refs(ctx.store, nid, ts=ctx.now_ts)
        linked += len(targets)
    logger.info("digest_settle strangers=%d objects=%d rows=%d new=%d renamed=%d "
                "rewritten=%d clash=%d empty=%d stale=%d linked=%d",
                len(strangers), len(obj_ids), len(rows),
                len(ctx.result.created_entities), len(stances.renamed),
                len(stances.rewritten), len(stances.collisions),
                len(stances.empty_skips), len(stances.watermark_skips), linked)
    return RoundOut.done()
