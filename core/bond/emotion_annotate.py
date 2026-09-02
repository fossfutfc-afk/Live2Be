# -*- coding: utf-8 -*-
"""情绪批量标注服务（两遍式策略 C 的第二遍）— 生成与情绪解耦。

背景（2026-08-31, branch feat/two-pass-emotion; 2026-09-02 切分权移交定稿）:
    主分支契约强制 emotion 内联（LLM 生成时逐句标注）——长输出注意力分散
    → 缺漏率高 → 全量解析校验失败 → 整个板块重生成（失败成本 O(板块)）。
    两遍式把"叙事生成"与"情绪标注"拆开:
        第一遍: LLM 输出骨架（自然段文本, 无 emotion 负担）→ 快、遵守率高
                （2026-09-02: 骨架 emotion 一律丢弃——标注层唯一真源）
        第二遍: 本模块批量标注（角色人设 + 文本 + 词表 → 标签, 分类任务,
                输出 ~每句一词）
    ——标注是纯分类（LLM 强项）, 校验 = 词表集合成员检查（零成本）,
    标注失败只影响表情精度（静默兜底延续）, 不阻断剧情（失败成本 O(0)）。

标注调用与生成并行（生成显示期间后台标注, 前端读到后续句时表情已就绪）;
预生成链（纯叙事场提前生成）天然掩盖标注延迟。
2026-09-02 robust 化（句子数随切分器上升, 全量失败成本变大）:
    - 二分降级: 全量输出校验失败 → 对半递归重标（局部错只牺牲局部）
    - 逐项容错: 长度对齐但个别词表外 → 该项 None, 其余保留（不再整批弃）
    - 人物注入: {character}（角色身份 + 性格要点——人设化情绪判断基准）,
      无人物知识时标注 LLM 会把"逞强笑着说没事"误判为 smile

用法:
    tags = annotate_emotions(llm, sentences, lexicon_keys, lexicon_hint, character)
    # tags[i] 对应 sentences[i]（str | None; None = 该项失败, 调用方延续兜底）
"""

from __future__ import annotations

import json
import logging
import re

from llm.prompts import load_prompt

logger = logging.getLogger("live2be.bond")

#: 标注兜底默认键（词表内没有时也用这个——宁缺勿错不阻断）
_DEFAULT_EMOTION = "nomal"


def _clean_tags(raw: object, n: int, lexicon: set[str]) -> list[str] | None:
    """标注输出清洗（严格版, 向后兼容）: 长度 n + 每项词表内 → 数组; 否则 None。

    二分降级在 robust 层处理; 这里是"整批可用性"判定。
    """
    if not isinstance(raw, list) or len(raw) != n:
        return None
    tags: list[str] = []
    for t in raw:
        if not isinstance(t, str) or t not in lexicon:
            return None
        tags.append(t)
    return tags


def _try_batch(
    llm,
    sentences: list[str],
    lexicon_keys: list[str],
    lexicon_hint: str,
    character: str,
    *,
    max_tokens: int,
) -> list[str | None] | None:
    """单次批量标注（一次 LLM 调用）。

    Returns:
        list[str|None]: 调用成功且长度对齐——逐项词表校验, 非法项 None;
        None: 调用异常 / 输出无法解析 / 长度不对齐（触发二分降级）。
    """
    lexicon = set(lexicon_keys)
    system = load_prompt("emotion_annotate").replace(
        "{lexicon}",
        lexicon_hint or "\n".join(f"  {k}" for k in lexicon_keys),
    ).replace(
        "{sentences}",
        "\n".join(f"{i + 1}: {s}" for i, s in enumerate(sentences)),
    ).replace("{character}", character or "（角色信息未注入）")
    try:
        # text 模式（非 json_object）: 输出是纯数组, json_object 的自纠错会
        # 拉长等待——标注是低价值重试（失败只影响表情精度）, 快速失败快速降级
        # extra_body={}（2026-09-02 修复）: 显式关闭全局 high reasoning——
        # 256 max_tokens 下 thinking 会吃满预算截断, robust 链爆炸成分钟级
        raw = llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": "请输出上述每句的情绪标签数组。"},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
            extra_body={},
        )
    except Exception as e:                     # noqa: BLE001 — 标注失败静默降级
        logger.warning("emotion 标注调用失败（降级）: %s", e)
        return None

    arr = _extract_array(raw)
    if not isinstance(arr, list) or len(arr) != len(sentences):
        if arr is not None:
            logger.warning("emotion 标注长度不符 %d != %d（二分降级）",
                           len(arr), len(sentences))
        return None
    tags: list[str | None] = []
    for t in arr:
        if isinstance(t, str) and t in lexicon:
            tags.append(t)
        else:                                   # 词表外 → 该项 None（逐项容错）
            tags.append(None)
    return tags


def annotate_emotions_smart(
    llm,
    sentences: list[str],
    lexicon_keys: list[str],
    lexicon_hint: str = "",
    character: str = "",
    *,
    max_tokens: int = 512,
) -> list[str | None]:
    """robust 批量标注: 全量优先 → 失败二分递归 → 逐项容错。

    返回与 sentences 同长的 list（str = 词表内标签; None = 该项标注失败,
    调用方延续兜底）。单句也失败 → [None]（不无限递归）。
    max_tokens 默认 512（2026-09-02: 256 在推理模型上截断风险高——
    标注调用已显式关 reasoning, 512 给长批数组留足余量）。
    """
    if not sentences:
        return []
    if not lexicon_keys:
        return [None] * len(sentences)

    tags = _try_batch(llm, sentences, lexicon_keys, lexicon_hint, character,
                      max_tokens=max_tokens)
    if tags is not None:
        return tags
    if len(sentences) <= 1:
        return [None]
    mid = len(sentences) // 2
    left = annotate_emotions_smart(
        llm, sentences[:mid], lexicon_keys, lexicon_hint, character,
        max_tokens=max_tokens)
    right = annotate_emotions_smart(
        llm, sentences[mid:], lexicon_keys, lexicon_hint, character,
        max_tokens=max_tokens)
    return left + right


def annotate_emotions(
    llm,
    sentences: list[str],
    lexicon_keys: list[str],
    lexicon_hint: str = "",
    character: str = "",
    *,
    max_tokens: int = 512,
) -> list[str] | None:
    """批量标注（严格兼容版, 单次调用）: 句子列表 → 情绪标签列表（词表内）。

    失败（LLM 异常 / 输出非法）→ None（调用方决定兜底——robust 全量回填请用
    annotate_emotions_smart; 本函数保留给协议单测/简单调用）。
    返回 None = 标注不可用; 非 None = 长度与 sentences 一致且全词表内。
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
    ).replace("{character}", character or "（角色信息未注入）")
    try:
        # text 模式 + 显式关 reasoning（同 _try_batch——标注低价值, 快速失败快速兜底）
        raw = llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": "请输出上述每句的情绪标签数组。"},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
            extra_body={},
        )
    except Exception as e:                     # noqa: BLE001 — 标注失败静默降级
        logger.warning("emotion 标注调用失败（兜底延续）: %s", e)
        return None

    tags = _clean_tags(_extract_array(raw), len(sentences), lexicon)
    if tags is None:
        logger.warning("emotion 标注输出非法（兜底延续）: %r", raw)
        return None
    return tags


def _extract_array(raw: object) -> object:
    """text 模式输出 → 数组（去 markdown 围栏/首尾杂讯）; 无法解析 → None。"""
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except ValueError:
        # 提取第一个 [...] 段（LLM 偶尔前后加解释）
        m = re.search(r"\[[^\]]*\]", text)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                return None
        return None


def fill_missing_emotions(
    paragraphs: list[dict],
    annotator,
    lexicon_keys: list[str],
    lexicon_hint: str = "",
    character: str = "",
) -> list[dict]:
    """骨架段落补标: 缺 emotion 的段落批量标注并回填（延续兜底）。

    annotator = callable(sentences, lexicon_keys, lexicon_hint, character)
        -> list[str | None]（robust: 逐项可用; 依赖注入, 便于测试）
    回填规则: 可用标签 → 该项; None/缺漏 → 延续前一句（首句 → 默认）。
    """
    missing = [i for i, p in enumerate(paragraphs) if not p.get("emotion")]
    if not missing:
        return paragraphs

    sentences = [paragraphs[i]["text"] for i in missing]
    tags = (annotator(sentences, lexicon_keys, lexicon_hint, character)
            if annotator else None)

    prev = ""
    for seq, pos in enumerate(missing):
        tag = ""
        if tags and seq < len(tags) and isinstance(tags[seq], str) \
                and tags[seq]:
            tag = tags[seq]
        paragraphs[pos]["emotion"] = tag or prev or _DEFAULT_EMOTION
        prev = tag or prev or _DEFAULT_EMOTION
    return paragraphs
