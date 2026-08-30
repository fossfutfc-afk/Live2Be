# -*- coding: utf-8 -*-
"""情绪批量标注服务（两遍式策略 C 的第二遍）— 生成与情绪解耦。

背景（2026-08-31, branch feat/two-pass-emotion）:
    主分支契约强制 emotion 内联（LLM 生成时逐句标注）——长输出注意力分散
    → 缺漏率高 → 全量解析校验失败 → 整个板块重生成（失败成本 O(板块)）。
    两遍式把"叙事生成"与"情绪标注"拆开:
        第一遍: LLM 输出骨架（纯文本, 无 emotion 负担）→ 快、遵守率高
        第二遍: 本模块批量标注（文本+词表 → 标签, 分类任务, 输出 ~每句一词）
    ——标注是纯分类（LLM 强项）, 校验 = 词表集合成员检查（零成本）,
    标注失败只影响表情精度（静默兜底延续）, 不阻断剧情（失败成本 O(0)）。

标注调用与生成并行（生成显示期间后台标注, 前端读到后续句时表情已就绪）;
预生成链（纯叙事场提前生成）天然掩盖标注延迟。

用法:
    tags = annotate_emotions(llm, sentences, lexicon_keys, lexicon_hint=...)
    # tags[i] 对应 sentences[i]; 失败/非法 → 兜底（延续/默认）
"""

from __future__ import annotations

import logging

from llm.prompts import load_prompt

logger = logging.getLogger("live2be.bond")

#: 标注兜底默认键（词表内没有时也用这个——宁缺勿错不阻断）
_DEFAULT_EMOTION = "nomal"


def _clean_tags(raw: object, n: int, lexicon: set[str]) -> list[str] | None:
    """标注输出清洗: 必须是长度 n 的数组且每项在词表内 → 否则 None（兜底）。"""
    if not isinstance(raw, list) or len(raw) != n:
        return None
    tags: list[str] = []
    for t in raw:
        if not isinstance(t, str) or t not in lexicon:
            return None
        tags.append(t)
    return tags


def annotate_emotions(
    llm,
    sentences: list[str],
    lexicon_keys: list[str],
    lexicon_hint: str = "",
    *,
    max_tokens: int = 256,
) -> list[str]:
    """批量标注: 句子列表 → 情绪标签列表（词表内）。

    失败（LLM 异常 / 输出非法）→ 全兜底（延续语义由调用方处理——本函数返回
    None 由调用方决定回退; 此处返回 None 表示"无法标注"）。
    返回 None = 标注不可用（调用方兜底延续）; 非 None = 长度与 sentences 一致。
    """
    if not sentences:
        return []
    if not lexicon_keys:
        return None

    lexicon = set(lexicon_keys)
    system = load_prompt("emotion_annotate").replace(
        "{lexicon}",
        lexicon_hint or "\n".join(f"  {k}" for k in lexicon_keys),
    ).replace(
        "{sentences}",
        "\n".join(f"{i + 1}: {s}" for i, s in enumerate(sentences)),
    )
    try:
        resp = llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": "请输出上述每句的情绪标签数组。"},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
            response_format="json_object",
        )
    except Exception as e:                     # noqa: BLE001 — 标注失败静默降级
        logger.warning("emotion 标注调用失败（兜底延续）: %s", e)
        return None

    if isinstance(resp, dict) and isinstance(resp.get("tags"), list):
        raw = resp["tags"]
    elif isinstance(resp, dict) and len(resp) == 1:
        raw = next(iter(resp.values()))        # 兼容 {"labels": [...]} 等单键包装
    elif isinstance(resp, list):
        raw = resp
    else:
        raw = None
    tags = _clean_tags(raw, len(sentences), lexicon)
    if tags is None:
        logger.warning("emotion 标注输出非法（兜底延续）: %r", raw)
        return None
    return tags


def fill_missing_emotions(
    paragraphs: list[dict],
    annotator,
    lexicon_keys: list[str],
    lexicon_hint: str = "",
) -> list[dict]:
    """骨架段落补标: 缺 emotion 的段落批量标注并回填（延续兜底）。

    annotator = callable(sentences, lexicon_keys, lexicon_hint) -> tags|None
    （依赖注入, 便于测试; 默认 = annotate_emotions 的偏应用）
    回填规则: 标注可用 → 逐句回填; 不可用/缺漏 → 延续前一句（首句 → 默认）。
    """
    missing = [i for i, p in enumerate(paragraphs) if not p.get("emotion")]
    if not missing:
        return paragraphs

    sentences = [paragraphs[i]["text"] for i in missing]
    tags = annotator(sentences, lexicon_keys, lexicon_hint) if annotator else None

    prev = ""
    for seq, (pos, sent) in enumerate(zip(missing, sentences)):
        tag = ""
        if tags and seq < len(tags) and tags[seq] in set(lexicon_keys):
            tag = tags[seq]
        paragraphs[pos]["emotion"] = tag or prev or _DEFAULT_EMOTION
        prev = tag or prev or _DEFAULT_EMOTION
    return paragraphs
