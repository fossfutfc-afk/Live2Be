# -*- coding: utf-8 -*-
"""测试夹具: 把"场景意图"写成**记录流**（记录流 v2 后引擎唯一输入形态, P0-7b）。

背景: 旧测试用 `{"action": "story_scene", "payload": {...}}` dict 喂 `send_vn_scene`;
记录流 v2 起 dict 一律被拒（过渡缝已删, 决策 #22）——这里给出统一的写法。

用法::

    from tests.vn_fixtures import scene, rec, CHARACTER

    SCENE_A = scene(switch_to="教室", lines=["段落一。"], sensei=["选A", "选B"])
    END = scene(end="（收尾。）")

    block = scene(lines=["……老师。"], sensei=["我在听。"], after=["……嗯。"])
    # after = 群之后的角色反应 —— 板切分: 槽挂板尾、反应在**下一板**

约定: 一段 record = 一个显示/判定单元（对应旧契约的一个 paragraph）。
"""
from __future__ import annotations

import json

#: 测试角色 id（与 config/characters 下真实目录一致）
CHARACTER = "igusa_haruka"
#: 角色显示名（人设 display_name）
DISPLAY = "伊草 遥香"


def rec(kind: str, value: str, text: str = "") -> str:
    """一条记录行（wire 形状）。"""
    return json.dumps({kind: value, "text": text}, ensure_ascii=False)


def line(text: str, speaker: str = CHARACTER) -> str:
    """角色/老师/旁白台词记录（speaker 给 narrator 即旁白）。"""
    return rec("character", speaker, text)


def switch(text: str) -> str:
    return rec("stage", "switch", text)


def art(text: str) -> str:
    return rec("stage", "art", text)


def memorial(text: str) -> str:
    return rec("stage", "memorial", text)


def end(text: str = "") -> str:
    return rec("stage", "end", text)


def scene(*, switch_to: str = "", art_hint: str = "", lines=(), sensei=(),
          after=(), memorial_text: str = "", end_text: str | None = None,
          narrator=()) -> str:
    """拼一块记录流。

    Args:
        switch_to: 换场地点话（`stage:switch`; 空 = 不换场）
        art_hint: 画面意向（`stage:art`, 块首声明）
        lines: 角色台词（str, 或 (speaker, text) 元组——后者可给 narrator/自定义）
        sensei: 老师的话（连续 = 一个群 = 一个交互槽; 板在群尾收）
        after: 群之后的角色反应（同块内 = **下一板**）
        memorial_text: 纪念触发（其后到块尾 = 纪念正文）
        end_text: 收尾（None = 不写; "" = 黑屏收尾）
        narrator: 旁白（`character:narrator`）
    """
    out: list[str] = []
    if art_hint:
        out.append(art(art_hint))
    if switch_to:
        out.append(switch(switch_to))
    for item in lines:
        if isinstance(item, (tuple, list)) and len(item) == 2:
            out.append(line(str(item[1]), str(item[0])))
        else:
            out.append(line(str(item)))
    for item in narrator:
        out.append(line(str(item), "narrator"))
    out.extend(rec("character", "sensei", str(t)) for t in sensei)
    for item in after:
        if isinstance(item, (tuple, list)) and len(item) == 2:
            out.append(line(str(item[1]), str(item[0])))
        else:
            out.append(line(str(item)))
    if memorial_text:
        out.append(memorial(memorial_text))
    if end_text is not None:
        out.append(end(end_text))
    return "\n".join(out)


def from_v1_scene(raw) -> str:
    """**v1 桩 → 记录流**（P0-7c 迁移期适配器, 只给存量测试桩用）。

    存量测试写的是 `{"action": "story_scene", "payload": {...}}` dict; 引擎现在只吃
    记录流。这里做一次等价翻译, 让那些**仍在测活行为**的用例改一行就能继续跑:

        paragraphs    → 角色记录（以（）开头的整段 → narrator 记录）
        choices       → 群（连续 sensei 记录, 挂块尾 = 交互槽）
        branches[第一个] → 群之后的**下一板**（收敛链语义: 反应在同块内后续）
        is_end/story_end → stage=end 收尾记录

    注意: 这是**测试侧**适配——产品侧没有这条通道（dict 一律被引擎拒）。
    新写的用例请直接用 `scene(...)`; 本函数只为存量桩兜底, 迁完即可删。
    """
    payload = raw
    if isinstance(raw, dict) and "action" in raw:
        payload = raw.get("payload") or {}
    if isinstance(raw, str) or not isinstance(payload, dict):
        return str(raw)
    paras = payload.get("paragraphs") or []
    lines: list[str] = []
    for p in paras:
        text = (p.get("text") if isinstance(p, dict) else p) or ""
        text = str(text)
        if not text:
            continue
        speaker = "narrator" if text.startswith("（") else CHARACTER
        lines.append(line(text, speaker))
    sensei_texts = [str(c) for c in (payload.get("choices") or []) if str(c).strip()]
    branches = payload.get("branches") or {}
    reaction: list[str] = []
    if sensei_texts and isinstance(branches, dict):
        first = branches.get(sensei_texts[0]) or []
        for p in first:
            text = str((p.get("text") if isinstance(p, dict) else p) or "")
            if text:
                reaction.append(line(text, "narrator" if text.startswith("（") else CHARACTER))
    is_end = bool(payload.get("is_end")) or (
        isinstance(raw, dict) and raw.get("action") == "story_end")
    out = list(lines)
    out += [rec("character", "sensei", t) for t in sensei_texts]
    out += reaction
    if is_end:
        out.append(end(""))
    return "\n".join(out)

