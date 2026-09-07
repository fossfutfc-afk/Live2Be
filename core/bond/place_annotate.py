# -*- coding: utf-8 -*-
"""地点变更标注（bond v2 视觉意图第二路, DESIGN_BOND_CONTRACT_V2 §5）——判定型任务。

背景（2026-09-07 定稿, text 半成功论）: 主 LLM 只按"换场即换段"写作约定分段,
**不写地点字段**; 地点语义由本标注层从句子文本里读出——与 emotion 同族:
    情绪   = 逐句全覆盖（词表键）
    place  = 事件型稀疏（仅在空间实体变更句产出锚点 {sentence, place}）

与 emotion 的差异（因此独立模块、独立 prompt, 但共享文本模式工具）:
    · 依赖"当前地点"状态（上一画面在哪——continuity 判定基础）
    · 输出 = 索引表 [{sentence, place}]（非等长标签数组）→ robust 二分不适用,
      失败语义 = 整批 keep（画面保持, 宁缺勿错, 不进主 LLM 重试）
    · 词表外/与当前相同/越界/重复 → 逐项丢弃（keep）

用法:
    anchors = annotate_places(llm, sentences, place_keys, current_place)
    # anchors: [{sentence: int(1-based), place: str}] 按句升序去重; 失败 → []
    # P3 接线: 引擎在锚点句应用背景切换（payload 句项写 place 键, 稀有种）
"""

from __future__ import annotations

import logging

from core.bond.emotion_annotate import _extract_array  # 共享文本模式数组提取
from llm.prompts import load_prompt
from llm.task_levels import extra_body as _tl_extra
from llm.task_levels import max_tokens as _tl_max_tokens

logger = logging.getLogger("live2be.bond")


def _clean_anchors(
    raw: object,
    n_sentences: int,
    place_keys: set[str],
    current_place: str,
) -> list[dict]:
    """锚点清洗（逐项容错）: 类型/序号越界/词表外/与当前相同 → 丢弃;
    同句多条目 → 保留最后一个; 按句号升序。"""
    if not isinstance(raw, list):
        return []
    by_sentence: dict[int, str] = {}
    for it in raw:
        if not isinstance(it, dict):
            continue
        try:
            s = int(it.get("sentence"))
        except (TypeError, ValueError):
            continue
        p = it.get("place")
        if not isinstance(p, str):
            continue
        p = p.strip()
        if not (1 <= s <= n_sentences and p in place_keys):
            continue
        if p == current_place:
            continue                          # 与当前相同 → keep（无变化）
        by_sentence[s] = p
    return [{"sentence": s, "place": by_sentence[s]}
            for s in sorted(by_sentence)]


def annotate_places(
    llm,
    sentences: list[str],
    place_keys: list[str],
    current_place: str = "",
    *,
    max_tokens: int | None = None,
    retries: int = 1,
) -> list[dict]:
    """地点变更标注（单次调用 + 至多重试）: 返回清洗后锚点列表; 失败 → []（keep）。

    Args:
        sentences: 本场句子列表（引擎已切句, 1-based 输出对应其序号）
        place_keys: 地点词表（closed, 如 _director_whitelist common_scenes）
        current_place: 上一画面地点（空 = 初始/未知——首次出现的变更句即起始背景）
        max_tokens: None → task_levels 形态 "place"=256; 显式传值覆盖
        retries: 解析失败重试次数（每次附带"只输出 JSON 数组"提醒）; 0 = 不重试
    """
    if not sentences or not place_keys:
        return []
    if max_tokens is None:
        max_tokens = _tl_max_tokens("place")
    key_set = set(place_keys)
    lexicon_hint = "\n".join(f"  {k}" for k in place_keys)
    current = (current_place or "").strip()

    for attempt in range(retries + 1):
        system = load_prompt("place_annotate").replace(
            "{lexicon}", lexicon_hint,
        ).replace(
            "{current_place}",
            current or "（初始/未知——出现首次变更即起始地点）",
        ).replace(
            "{sentences}",
            "\n".join(f"{i + 1}: {s}" for i, s in enumerate(sentences)),
        )
        user = "请输出变更句数组 JSON。" + (
            "（上一次输出无法解析——请只输出 JSON 数组, 无变更输出 []）"
            if attempt > 0 else "")
        try:
            # text 模式 + off-thinking（真源 task_levels 形态 "place"——低价值快失败）
            raw = llm.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
                extra_body=_tl_extra("place"),
            )
        except Exception as e:                    # noqa: BLE001 — 失败静默降级
            logger.warning("place 标注调用失败（keep 兜底）: %s", e)
            continue                              # 重试机会耗尽 → 落到 finally [] 
        arr = _extract_array(raw)
        if arr is not None:                       # 形状可解析 → 逐项容错完成
            return _clean_anchors(arr, len(sentences), key_set, current)
    return []                                     # 全部失败 → keep（画面保持）

