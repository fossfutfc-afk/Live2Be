"""情绪批量标注（两遍式 C 的第二遍）—— 主 LLM 只写骨架, 情绪归这一层。

一次调用标一批句子: 角色人设 + 文本 + 词表 → 与句子等长的词表键数组。
标注是纯分类（LLM 强项）, 校验只是词表成员检查; 失败只影响表情精度（静默兜底延续）,
不阻断剧情。全量校验失败 → 二分递归重标（局部错只牺牲局部）。

用法: `tags = annotate_emotions_smart(llm, sentences, keys, hint, character)`
—— `tags[i]` 对应 `sentences[i]`; None = 该项失败, 由调用方延续兜底。
"""

from __future__ import annotations

import json
import logging
import re

from contract.slots import render_template
from llm.prompts import load_prompt
from llm.task_labels import EMOTION
from llm.task_levels import extra_body as _tl_extra
from llm.task_levels import max_tokens as _tl_max_tokens

logger = logging.getLogger("live2be.bond")

#: 标注兜底默认键（词表内没有时也用这个——宁缺勿错不阻断）
_DEFAULT_EMOTION = "nomal"


def _anno_max_tokens(explicit: int | None) -> int:
    """标注输出上限（None → 真源 task_levels 形态 "emotion"=512; 显式传值覆盖）。"""
    return _tl_max_tokens("emotion") if explicit is None else explicit


def _clean_tags(arr: list | None, n: int, lexicon: set[str]) -> list[str] | None:
    """长度恰 n 且每项都在词表里 → 数组; 否则 None（二分降级在 robust 层处理）。"""
    if arr is None or len(arr) != n:
        return None
    tags: list[str] = []
    for t in arr:
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
    """单次批量标注（一次 LLM 调用）: 成功 → 逐项词表校验后的数组; 失败 → None。"""
    lexicon = set(lexicon_keys)
    system = render_template(
        load_prompt("emotion_annotate"),
        {"lexicon": lexicon_hint or "\n".join(f"  {k}" for k in lexicon_keys),
         "sentences": "\n".join(f"{i + 1}: {s}" for i, s in enumerate(sentences)),
         "character": character or "（角色信息未注入）"},
        where="emotion_annotate.md")
    try:
        # text 模式: 输出就是纯数组, json_object 的自纠错只会拉长等待。
        # thinking / max_tokens 真源 = task_levels 形态 "emotion"。
        raw = llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": "请输出上述每句的情绪标签数组。"},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
            extra_body=_tl_extra("emotion"),
            task=EMOTION,                  # 调用身份（节点 5b: 桩按它分派）
        )
    except Exception as e:                     # noqa: BLE001 — 标注失败静默降级
        logger.warning("emotion 标注调用失败（降级）: %s", e)
        return None

    arr = _extract_array(raw)
    if arr is None:
        return None
    if len(arr) != len(sentences):
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


#: robust 标注的 LLM 调用总预算（含所有递归分支）。二分链在慢调用下会串行累积
#: （实测单场景 27.4s）; 超预算 → 整批 None, 由调用方延续兜底。
_ANNO_CALL_BUDGET = 4


# EXT: emotion-batch-v1 — 批式标注入口（主链走 emo_text; docs/EXTENSION_POINTS.md）
def annotate_emotions_smart(
    llm,
    sentences: list[str],
    lexicon_keys: list[str],
    lexicon_hint: str = "",
    character: str = "",
    *,
    max_tokens: int | None = None,
) -> list[str | None]:
    """robust 批量标注: 全量优先 → 失败二分递归 → 逐项容错。

    返回与 sentences 等长（None = 该项失败, 调用方延续）; 单句也失败 → `[None]`。
    调用总量受 `_ANNO_CALL_BUDGET` 硬顶（含所有递归分支）。
    """
    return _smart_rec(llm, sentences, lexicon_keys, lexicon_hint, character,
                      max_tokens, _ANNO_CALL_BUDGET, [0])


def _smart_rec(llm, sentences, lexicon_keys, lexicon_hint, character,
               max_tokens, budget: int, calls: list[int]) -> list[str | None]:
    """smart 递归体——calls[0] 全局计数（所有分支共享, 预算耗尽即整批 None）。"""
    if not sentences:
        return []
    if not lexicon_keys:
        return [None] * len(sentences)
    if max_tokens is None:
        max_tokens = _anno_max_tokens(None)
    if calls[0] >= budget:
        return [None] * len(sentences)          # 预算耗尽 → 兜底（不再调用）
    calls[0] += 1
    tags = _try_batch(llm, sentences, lexicon_keys, lexicon_hint, character,
                      max_tokens=max_tokens)
    if tags is not None:
        return tags
    if len(sentences) <= 1:
        return [None]
    mid = len(sentences) // 2
    left = _smart_rec(llm, sentences[:mid], lexicon_keys, lexicon_hint,
                      character, max_tokens, budget, calls)
    right = _smart_rec(llm, sentences[mid:], lexicon_keys, lexicon_hint,
                       character, max_tokens, budget, calls)
    return left + right


# EXT: emotion-batch-v1 — 单次调用版（协议单测用; docs/EXTENSION_POINTS.md）
def annotate_emotions(
    llm,
    sentences: list[str],
    lexicon_keys: list[str],
    lexicon_hint: str = "",
    character: str = "",
    *,
    max_tokens: int | None = None,
) -> list[str] | None:
    """批量标注（单次调用, 严格版）: 句子列表 → 词表内标签列表; 失败 → None。

    非 None 时长度与 sentences 一致且全词表内; 要 robust 回填请用
    `annotate_emotions_smart`。
    """
    if not sentences:
        return []
    if not lexicon_keys:
        return None
    if max_tokens is None:
        max_tokens = _anno_max_tokens(None)
    lexicon = set(lexicon_keys)
    system = render_template(
        load_prompt("emotion_annotate"),
        {"lexicon": lexicon_hint or "\n".join(f"  {k}" for k in lexicon_keys),
         "sentences": "\n".join(f"{i + 1}: {s}" for i, s in enumerate(sentences)),
         "character": character or "（角色信息未注入）"},
        where="emotion_annotate.md")
    try:
        # text 模式 + 显式关 reasoning（同 _try_batch——标注低价值, 快速失败快速兜底;
        # thinking 档位真源 = task_levels 形态 "emotion"）
        raw = llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": "请输出上述每句的情绪标签数组。"},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
            extra_body=_tl_extra("emotion"),
            task=EMOTION,                  # 调用身份（节点 5b: 桩按它分派）
        )
    except Exception as e:                     # noqa: BLE001 — 标注失败静默降级
        logger.warning("emotion 标注调用失败（兜底延续）: %s", e)
        return None

    tags = _clean_tags(_extract_array(raw), len(sentences), lexicon)
    if tags is None:
        logger.warning("emotion 标注输出非法（兜底延续）: %r", raw)
        return None
    return tags


def _extract_array(raw: object) -> list | None:
    """text 模式输出 → 数组（去 markdown 围栏/首尾杂讯）; 解析不出数组 → None。"""
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        arr = json.loads(text)
    except ValueError:
        m = re.search(r"\[[^\]]*\]", text)      # LLM 偶尔前后加解释
        if not m:
            return None
        try:
            arr = json.loads(m.group(0))
        except ValueError:
            return None
    return arr if isinstance(arr, list) else None


# EXT: emotion-batch-v1 — 批式补标入口（保留给协议单测/简单调用）; 勿删（docs/EXTENSION_POINTS.md）
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
