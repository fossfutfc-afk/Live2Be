"""选图标注（**第二遍**: 地点已定 → 用这个地点的哪一张图）。

## 为什么有这一步（2026-09-19, 用户推动）

第一遍（`resolve_place`）只回答"**哪个地点**"。但同一个地点在资源库里常有好几张图:

| 轴 | 例子 | 现在的状态 |
|---|---|---|
| **时刻/天气** | `BG_ClassRoom_Night.jpg` / `_Sunset` / `_Rain` | 从文件名后缀派生（`MOMENT_VARIANTS`）。实测 **153 张夜 + 35 张夕**，此前**谁都选不了**（`catalog.background(sid, variant=None)` 永远第一条） |
| **差分** | `BG_SchoolRooftop.jpg` vs `BG_SchoolRooftop2.jpg`（"普通差分天台为主, 差分2天空为主"） | **45 个键各有 ≥2 张无变体图**, 引擎永远取第一张; 作者在 `note` 里写的偏好（`fishing_village`: *"请使用差分2"*、`lighthousepier`: *"建议使用差分2"*）**没有任何消费方** |

用户原话: *"好消息是我的部分 note 里面本身就会教 LLM 某些特殊常用的夜景以及差分的
区别"* ⇒ **note 就是这个资源的说明书**, 所以这一步把作者说明原样摆给标注 LLM,
让它挑**文件**（不是挑一个抽象的"时刻 token"）。

## 为什么不走关键词表（用户当场否掉）

时刻词在文本里**根本不等于**时刻: 「从早到晚，我都想一直陪在老师身边」（范围成语）、
「这些灯光，感觉像在白天一样呢~」（比喻 + 否定 ⇒ 其实是夜）、「我一定要将老师的善良
公布在光天化日之下！」（成语）、「私は夜の散歩が一番好きです」（外语 + 意愿句）。
这四句都是**判据示范写进了 prompt**; 关键词表会把 3 句判反、1 句判错, 而且**漏判是
静默的**（画面停在旧图, 没人报错）。⇒ 这是语义判定, 归标注层, 不归正则。

## 调用纪律（宁缺勿错）

* **只有一张图 → 根本不调用**（168 个键里 22 个单图; 其余才发这一步）
* 输出**必须是该键候选之一**（文件名精确匹配）, 否则丢弃 → 保持当前画面
* 失败/服务不可用/文本为空 → `""`（保持）, 绝不阻断主链
* 档位 = `place`（off-thinking / 256 tokens）——与第一遍同档, 都是廉价判定
"""
from __future__ import annotations

import json
import logging
import re

from contract.slots import render_template
from llm.prompts import load_prompt
from llm.task_labels import PLACE_VARIANT
from llm.task_levels import extra_body as _tl_extra
from llm.task_levels import max_tokens as _tl_max_tokens

logger = logging.getLogger("live2be.bond")


def _extract_image(raw: object) -> str | None:
    """从模型输出里抠出 `{"image": "<文件名>"}`。形状不对 → None。"""
    text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    img = obj.get("image")
    return img.strip() if isinstance(img, str) else ""


def pick_image(
    llm,
    text: str,
    entry,
    *,
    current_image: str = "",
    max_tokens: int | None = None,
    retries: int = 1,
) -> str:
    """地点键的**候选图**里挑一张（相对路径）; `""` = 不动（保持当前画面）。

    Args:
        llm: LLM 客户端（`chat` 文本模式）
        text: 编剧写的那句话（switch 原文）——也是这一遍唯一的语境
        entry: `PlaceEntry`（候选与 note 都从它来）
        current_image: 当前画面用的那张（相对路径; 让模型有"保持"这个概念）
        retries: 解析失败重试次数

    Returns: `entry` 的 `files` 里的相对路径; `""` = 保持 / 判不出 / 失败。
    """
    text = (text or "").strip()
    if not text or entry is None:
        return ""
    candidates = entry.image_candidates()
    if len(candidates) <= 1:
        return ""                                     # 只有一张图 → 不用问（0 调用）
    allowed = {rel for rel, _ in candidates}
    by_name = {rel.rsplit("/", 1)[-1]: rel for rel, _ in candidates}
    if max_tokens is None:
        max_tokens = _tl_max_tokens("place")
    system = render_template(
        load_prompt("place_variant"),
        {"place": entry.place,
         "aliases": "/".join(entry.keywords) or "（无别名）",
         "candidates": entry.image_candidate_lines(),
         "note": entry.note or "（作者没写说明——那就只看文本）",
         "current_image":
             current_image.rsplit("/", 1)[-1] if current_image else "（还没定）",
         "text": text},
        where="place_variant.md")
    user = "请输出选中的文件名 JSON。"
    for attempt in range(retries + 1):
        try:
            raw = llm.chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user}],
                temperature=0.2,
                max_tokens=max_tokens,
                extra_body=_tl_extra("place"),
                task=PLACE_VARIANT,        # 选图（节点 5b: 桩按它分派）
            )
        except Exception as e:                        # noqa: BLE001 — 失败静默降级
            logger.warning("选图调用失败（保持当前画面）: %s", e)
            continue
        picked = _extract_image(raw)
        if picked is None:                            # 解析失败 → 重试一次
            continue
        if not picked:                                # 显式空 = 保持
            return ""
        picked = picked.strip().strip('"').strip("'")
        if picked in allowed:                         # 精确路径
            return picked
        if picked in by_name:                         # 只给了文件名（常态）
            return by_name[picked]
        logger.warning("[place][PICK] 模型给了候选外的图（丢弃）: %r", picked)
        return ""
    return ""
