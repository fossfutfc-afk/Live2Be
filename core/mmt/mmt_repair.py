"""MMT 操作行的**引擎侧自愈**（⑥-2c, 2026-09-25）。

设计: `docs/DESIGN_STREAM_CONTRACT.md` §4.2（逐动作兜底表）/ §10.3 C2。

⭐ **必须跑在 `registry.parse` 之前**（§10.2 B5 发现②）：
`send_media` 的 `media_type` / `image` 都是 registry 的**硬拒绝**——晚一步，
写歪的字段就没机会被修好，只能走回灌。

⚠️ **2026-10-08（D 笔）**: 从前还修 `mmt_inspect_character` 的 `character_id`
（角色名/别名归一成真实 id）—— 那个动作退役后, `build_candidates` /
`normalize_character_id` / `repair_inspect` 连同 `candidates` 形参一并删掉
（她今天**没有任何"按 id 查人"的动作**了）。

## 三条纪律

· **宁缺勿错**：拿不准就不猜（归一化有歧义 → 返回 `None`，让上层回灌）；
· 每一次修复都**要能说出来**（返回一句说明，进日志 / trace）；
· 本层只动"写了但写歪"的字段，**不新增语义**（不替模型补一个它没写的标题——
  那属于模型的事，修不了就回灌）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from core.mmt.mmt_lines import KIND_ACTION, MmtLine
from core.mmt.mmt_check import ACTION_TRIGGER, TITLE_MAX, TITLE_MIN

#: `media_type` 的唯一合法值（MMT 只支持图片；`mmt_actions.MMT_MEDIA_TYPES` 同源）
MEDIA_TYPE_IMAGE = "image"

#: 归一化时抹掉的装饰字符（空白 / 下划线 / 连字符 / 中点 / 点）
_DECOR_RE = re.compile(r"[\s_\-·．.,，、]+")


def _fold(text: str) -> str:
    """比对用的折叠形：小写 + 抹掉装饰字符（`igusa-haruka` / `IGUSA_HARUKA` / `伊草 遥香`）。"""
    return _DECOR_RE.sub("", (text or "").strip()).lower()


def repair_send_media(payload: Mapping) -> tuple[dict | None, str]:
    """`mmt_send_media`: `media_type` 纠回 image；未知 `library_id` 丢弃；`image` 空 → None。"""
    notes: list[str] = []
    fixed = dict(payload)

    media_type = fixed.get("media_type", MEDIA_TYPE_IMAGE)
    if media_type != MEDIA_TYPE_IMAGE:
        notes.append(f"media_type {media_type!r} → 'image'（MMT 只支持图片）")
        fixed["media_type"] = MEDIA_TYPE_IMAGE

    if "library_id" in fixed and not isinstance(fixed["library_id"], str):
        notes.append("library_id 不是字符串 → 丢弃该字段（按 image 描述走）")
        fixed.pop("library_id")

    image = fixed.get("image")
    if not isinstance(image, str) or not image.strip():
        return None, "image 是空的（图片描述必填）——这一行修不了"
    fixed["image"] = image.strip()
    return fixed, "; ".join(notes)


def repair_trigger(payload: Mapping) -> tuple[dict | None, str]:
    """`mmt_trigger_bond_story`: `chapter_title` 去空白 / 按上限截断；仍太短 → None。

    ⚠️ **不替模型起标题**（那是它的事）：短到不合规就修不了 ⇒ 回灌让它重发。
    """
    title = str(payload.get("chapter_title") or "").strip()
    notes: list[str] = []
    if len(title) > TITLE_MAX:
        notes.append(f"chapter_title 截断到 {TITLE_MAX} 字（原 {len(title)} 字）")
        title = title[:TITLE_MAX]
    if len(title) < TITLE_MIN:
        return None, (f"chapter_title 只有 {len(title)} 字（要 {TITLE_MIN}-{TITLE_MAX} 字）"
                      "——这一行修不了")
    fixed = dict(payload)
    fixed["chapter_title"] = title
    return fixed, "; ".join(notes)


#: 按动作名分派的自愈表（**只列能修的**；没列的动作原样返回，交 registry 判）
_REPAIRS = {
    "mmt_send_media": "media",
    ACTION_TRIGGER: "trigger",
}


def repair_line(line: MmtLine) -> tuple[MmtLine | None, str]:
    """一条操作行的自愈（**跑在 `registry.parse` 之前**）。

    Returns:
        `(修好的行 | None, 说明)`；`None` = 修不了（调用方按分级处理：
        `mmt.control-invalid` ⇒ 回灌 / `mmt.control-unexecuted` ⇒ 丢行 + 下一轮纠偏）。
        说明为空串 = 无需修复。
    """
    if line.kind != KIND_ACTION:                 # 内容行无副作用，没什么可修
        return line, ""
    kind = _REPAIRS.get(line.action)
    if kind is None:                             # 未知动作：交 registry.parse 报错
        return line, ""

    if kind == "media":
        fixed, note = repair_send_media(line.payload)
    else:
        fixed, note = repair_trigger(line.payload)
    if fixed is None:
        return None, note
    if not note:
        return line, ""
    return MmtLine(kind=KIND_ACTION, action=line.action, payload=fixed,
                   line_no=line.line_no), note
