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

import json
import logging
import re

from core.bond.emotion_annotate import _extract_array  # 共享文本模式数组提取
from llm.prompts import load_prompt
from llm.task_labels import PLACE, PLACE_BOARD
from llm.task_levels import extra_body as _tl_extra
from llm.task_levels import max_tokens as _tl_max_tokens

logger = logging.getLogger("live2be.bond")

#: switch 文本 → 词表键的进程内缓存（P0-7 最小换场翻译; 文件级缓存 places_resolved.jsonl
#: 是 P1-3 的事——这里先给"同一地点话不再重复调用"的收益）
_RESOLVE_CACHE: dict[str, str] = {}
_RESOLVE_CACHE_MAX = 256


#: 层2 的显式"不换场"标记（prompt 里唯一的合法出口）——语义 = "编剧说的就是当前这个地方"。
#: ⚠️ 与"给空串"分开（2026-09-23）: 空串曾是模型偷懒的出口（真机 '夜晚的模型店橱窗前'
#: 三块板都空 ⇒ 画面卡在上一张）。标记化之后"确实是同一处"与"判不出来"在数据里分家。
_SAME_TOKEN = "same"


def _layer1(text: str, table, current: str, key_set: set[str]) -> str | None:
    """**层1: 别名精确命中（0 调用）** —— 命中就返回键; 不命中/歧义 → `None`（下沉层2）。

    判据（`core/media/place_table.py:resolve_exact`）:
    * 唯一命中且 ≠ 当前 → 直接用
    * 唯一命中 == 当前 → `""`（画面不用动, 也省一次调用）
    * **歧义（≥2 条）**→ 若 `current` 在里面也算"已经在那一带"→ `""`;
      否则 `None`（交层2 读 `note` 判——层1 不猜）

    ⚠️ **结果必须落在 `key_set` 里**（2026-09-19）: `place_keys` 才是"这次允许
    用哪些键"的真源（webgui 门控 + 调用方可以收窄），表只是**语料**。
    两者可能不一致（测试/子集场景）——此时以 `key_set` 为准，别让两个真源打架。
    """
    if table is None or not table:
        return None
    hits = [p for p in table.resolve_exact(text) if p in key_set]
    if not hits:
        return None
    if len(hits) == 1:
        return "" if hits[0] == current else hits[0]
    return "" if (current and current in hits) else None


def _lexicon_hint(place_keys: list[str], table) -> str:
    """层2 的词表文本: 有表 → 整表（含 `note`）; 无表 → 旧口径（裸 id 列表）。

    ⚠️ `note` 是**表外地点也能落位**的唯一依据（用户 2026-09-19）——没它模型
    只能对着裸 slug 瞎猜, 真机 `杂草屋 → school_rooftop` 就是这么来的。
    """
    if table is not None and table:
        return table.lexicon_text()
    return "\n".join(f"  {k}" for k in place_keys)


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
    table=None,
    max_tokens: int | None = None,
    retries: int = 1,
) -> list[dict]:
    """地点变更标注（单次调用 + 至多重试）: 返回清洗后锚点列表; 失败 → []（keep）。

    Args:
        sentences: 本场句子列表（引擎已切句, 1-based 输出对应其序号）
        place_keys: 地点词表（closed 键集; 有 `table` 时只用于校验输出合法性）
        current_place: 上一画面地点（空 = 初始/未知——首次出现的变更句即起始背景）
        table: `PlaceTable`（C2, 2026-09-19）——有它则词表文本换成**整表含 note**;
            None → 旧口径（裸 id 列表, 只为兼容/降级）
        max_tokens: None → task_levels 形态 "place"=256; 显式传值覆盖
        retries: 解析失败重试次数（每次附带"只输出 JSON 数组"提醒）; 0 = 不重试
    """
    if not sentences or not place_keys:
        return []
    if max_tokens is None:
        max_tokens = _tl_max_tokens("place")
    key_set = set(place_keys)
    lexicon_hint = _lexicon_hint(place_keys, table)
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
                task=PLACE,               # 句级锚点（节点 5b: 与板级翻译区分）
            )
        except Exception as e:                    # noqa: BLE001 — 失败静默降级
            logger.warning("place 标注调用失败（keep 兜底）: %s", e)
            continue                              # 重试机会耗尽 → 落到 finally [] 
        arr = _extract_array(raw)
        if arr is not None:                       # 形状可解析 → 逐项容错完成
            return _clean_anchors(arr, len(sentences), key_set, current)
    return []                                     # 全部失败 → keep（画面保持）


def _extract_place_obj(raw: object) -> str | None:
    """从模型输出里抠出 {"place": "<id>"} 的 id；形状不对 → None。"""
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
    place = obj.get("place")
    return place.strip() if isinstance(place, str) else None


def resolve_place(
    llm,
    text: str,
    place_keys: list[str],
    current_place: str = "",
    *,
    table=None,
    max_tokens: int | None = None,
    retries: int = 1,
) -> str:
    """`switch` 地点话 → 背景词表键（**层1 别名 0 调用 → 层2 LLM 就近推测**）。

    记录流 v2 的换场由 writer 发 `stage:switch`（自然语言地点），WHICH 归标注层:
    这一步就是那一次翻译。

    ## 两层（C3, 2026-09-19）

    * **层1**（`_layer1`）: 表里的 `keywords` 别名整串/最长别名命中 → **0 调用**。
      真机实测: `教室`→`classroom`、`街角的咖啡馆，靠窗的位子`→`moderncafe`
      （这两条在"31 条裸 slug"时代全是 MISS）。
    * **层2**: 吃**整张表**（含 `note`）。**"词表里没有能对上"不是失败**——
      writer 自由写（用户: *"writer 的自由不受限制……annotation-llm 只要看到 note
      就能大致推测出地点"*），层2 的活就是**读 note 选语义最近的一张**。
      ⚠️ 旧口径"宁可空着，不要硬凑"是**第一版为了让程序跑起来的遗老**（用户
      2026-09-19 定性），已随 prompt 一并改掉。

    `""` = 这次不切背景（keep）。命中进程内缓存 → 不再调用。

    Returns: 词表键; `""` = 这次不切背景。
    """
    text = (text or "").strip()
    current = (current_place or "").strip()
    if not text or not place_keys:
        return ""
    cache_key = f"{current}|{text}|{len(place_keys)}"
    if cache_key in _RESOLVE_CACHE:
        return _RESOLVE_CACHE[cache_key]
    key_set = set(place_keys)
    # 层1: 纯字符串, 命中即返回（0 调用）; None = 下沉层2
    hit = _layer1(text, table, current, key_set)
    if hit is not None:
        if len(_RESOLVE_CACHE) < _RESOLVE_CACHE_MAX:
            _RESOLVE_CACHE[cache_key] = hit
        return hit
    layer1_hit = False
    reason = "failed"                             # 默认: 调用异常/解析失败耗尽
    result = ""
    if max_tokens is None:
        max_tokens = _tl_max_tokens("place")
    lexicon_hint = _lexicon_hint(place_keys, table)
    system = (load_prompt("place_resolve")
              .replace("{lexicon}", lexicon_hint)
              .replace("{current_place}", current or "（还没定）")
              .replace("{text}", text))
    user = "请输出地点 id JSON。"
    for attempt in range(retries + 1):
        try:
            raw = llm.chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user}],
                temperature=0.2,
                max_tokens=max_tokens,
                extra_body=_tl_extra("place"),
                task=PLACE_BOARD,         # 板级换场翻译（节点 5b: 与句级锚点区分）
            )
        except Exception as e:                    # noqa: BLE001 — 失败静默降级（keep）
            logger.warning("place 翻译调用失败（keep 兜底）: %s", e)
            continue
        place = _extract_place_obj(raw)
        if place is None:                         # 解析失败 → 重试一次
            if not isinstance(raw, str):
                logger.info("place_resolve 解析失败（第 %d 次）: %r",
                            attempt + 1, str(raw)[:80])
            continue
        if place == _SAME_TOKEN:                  # "就是当前这个地方" → 显式不换
            reason = "same"
            break
        if place and place in key_set and place != current:
            result = place
            reason = "ok"
        elif place and place in key_set:
            reason = "same"                       # 与当前相同 → 画面不用动
        elif place:
            reason = f"bad_key={place}"           # ⭐ 表外键: **记下来**（模型想说什么）
        else:
            reason = "empty"                      # 模型给了空串（prompt 已不许, 兜底可见）
        break
    # ⚠️ **只缓存成功的结果**（2026-09-23）: 空/表外键/调用失败都**不缓存**——
    # 原先连 `""` 一起缓存, 一次偷懒就把同一句话整章钉死（真机 '夜晚的模型店橱窗前'
    # 三块板全是 MISS, 再没有第二次机会）。
    if result and len(_RESOLVE_CACHE) < _RESOLVE_CACHE_MAX:
        _RESOLVE_CACHE[cache_key] = result
    if reason != "ok":
        logger.info("place_resolve reason=%s text=%r current=%r duration=%s",
                    reason, text[:40], current or "-",
                    "（层1 命中, 未调用 LLM）" if layer1_hit else "LLM")
    return result

