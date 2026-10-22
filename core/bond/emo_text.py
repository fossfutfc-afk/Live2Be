"""按记录标注情绪（记录流 v2 的主链原语）—— 一板一组, 一次调用。

**一条记录一个键**: 记录内多句也只占一行（模板显式双写条数, 不是句子数）。
键的取值范围 = **情绪词表 ∪ 动作词表**（`core/bond/actions.py`）—— 两件事同构成一格,
所以只有一套解析/重试/兜底; 动作键不推进 carry, 由写回处拆成 `p["act"]`。
输入 = 本板记录文本 + 情境块（上一板原文 + 末条情绪 / 首板 seed 锚）+ 全注释词表
+ I/O 示范（示范键按实际词表挑）; 引擎负责条数硬校验与重试, 本原语负责板内延续
（上一条键 → 板首 carry）——**永不整批 None**。

提示词模板: `llm/prompts/emotion_text_annotate.md`。
"""
from __future__ import annotations

import json
import logging
import re

from contract.slots import render_template
from core.bond.actions import ACTION_NAMES, render_prompt_block
from core.bond.emotion_annotate import _extract_array
from llm.prompts import load_prompt
from llm.task_labels import EMOTION
from llm.task_levels import extra_body as _tl_extra
from llm.task_levels import max_tokens as _tl_max_tokens

logger = logging.getLogger("live2be.bond")

#: 示范优先键（词表常见情绪; 缺失则按词表顺序兜底——示范键恒 ∈ 词表）
_CANONICAL = ["nomal", "embarrassed", "smile", "surprised",
              "sad", "outburst", "expectant", "respond"]

#: 尝试上限: 空响应 / 项数错配在服务端负载期占首发 ~40%, 第二次重试能收回大部分;
#: 仍失败就走板内延续（输入小, 快失败代价低）。
_ANNO_TEXT_MAX_ATTEMPTS = 3

#: 无词表/输入为空时的板内延续默认键（engine 侧已保证词表非空; 兜底防线）
_DEFAULT_EMOTION = "nomal"


def pick_demo_keys(lexicon_keys: list[str]) -> tuple[str, str, str]:
    """I-O 示范的三个标签键（转折 a/b + 叙述 n）——全 ∈ 实际词表; 只有 1 键则同键兜底。"""
    kset = list(dict.fromkeys(k for k in lexicon_keys if isinstance(k, str)))
    n = "nomal" if "nomal" in kset else (kset[0] if kset else _DEFAULT_EMOTION)
    rest = [k for k in _CANONICAL if k in kset and k != n]
    if not rest:
        rest = [k for k in kset if k != n]
    a = rest[0] if rest else n
    b = rest[1] if len(rest) > 1 else a
    return n, a, b


_KEY_RE = re.compile(r"^[A-Za-z_]+$")


def _first_list_value(obj: dict) -> list | None:
    """对象包装取键数组（数组形态）: labels/emotion 键优先, 否则首个 list。"""
    for key in ("labels", "emotion", "keys", "emotions"):
        v = obj.get(key)
        if isinstance(v, list):
            return v
    for v in obj.values():
        if isinstance(v, list):
            return v
    return None


def _numbered_map_value(obj: dict) -> list | None:
    """编号映射形态 `{"labels": {"1": 键, …}}` → 按键升序取值（模型不必数项数）。"""
    for key in ("labels", "emotion", "keys", "emotions"):
        v = obj.get(key)
        if isinstance(v, dict):
            pairs: list[tuple[int, object]] = []
            for k, val in v.items():
                try:
                    idx = int(k)
                except (TypeError, ValueError):
                    continue
                if idx >= 1 and isinstance(val, str):
                    pairs.append((idx, val))
            if pairs:
                pairs.sort()
                return [val for _, val in pairs]
    return None


def _extract_key_array(raw: object) -> list | None:
    """标注输出 → 键数组（形态无关: 数组 | 对象数组 | 对象编号映射 | 裸键）。

    识别不出 → None; 键合法性与项数由 `_label_chain` 硬校验兜底。
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        arr = _first_list_value(raw)                # 对象数组形态
        if arr is not None:
            return arr
        return _numbered_map_value(raw)             # 对象编号映射形态
    if isinstance(raw, str):
        text = raw.strip()
        try:
            obj = json.loads(text)
        except ValueError:
            obj = None
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            arr = _first_list_value(obj)
            if arr is not None:
                return arr
            return _numbered_map_value(obj)
        arr = _extract_array(raw)                  # 旧形态: 摘引号数组
        if isinstance(arr, list):
            return arr
        m = re.search(r"\[(.*)\]", text, re.S)     # 裸键容忍（省引号输出）
        if m:
            body = m.group(1)
            if '"' not in body and "'" not in body:
                items = [x.strip() for x in body.split(",") if x.strip()]
                if items and all(_KEY_RE.fullmatch(x) for x in items):
                    return items
    return None


def _label_chain(arr: object, n: int, kset: set[str], prev: str | None,
                 acts: frozenset[str] = ACTION_NAMES,
                 ) -> tuple[list[str], int] | None:
    """数组 → 标签链: 长度恰 n → 逐项词表校验（词表外只丢该项, 走板内延续）。

    词表 = 情绪 ∪ 动作。**动作键不推进 carry**: 点动作的那一行不给表情（脸沿用上一条）,
    但键原样带回 —— 由写回处（`_annotate_text_group`）拆成 `p["act"]`。

    Returns: `(labels, missing)`; 长度 != n → None（触发重试, 不消费错位数组）。
    """
    if not isinstance(arr, list) or len(arr) != n:
        return None
    labels: list[str] = []
    # carry 起点不是真情绪键（旧数据/上板污染）→ 从默认键起
    cur = prev if prev and prev not in acts else _DEFAULT_EMOTION
    missing = 0
    for item in arr:
        key = item.strip() if isinstance(item, str) else ""
        if key and key in kset:
            if key in acts:
                labels.append(key)              # 动作键: 原样带回, 由写回处拆成 p["act"]
            else:
                cur = key
                labels.append(key)
        else:
            missing += 1                        # 词表外 → 只丢该项（板内延续）
            cur = cur or _DEFAULT_EMOTION
            labels.append(cur)
    return labels, missing


def annotate_items(
    llm,
    items: list[str],
    lexicon_keys: list[str],
    lexicon_hint: str,
    character: str,
    char_name: str,
    context: str,
    group_no: int,
    *,
    prev: str | None = None,
    max_tokens: int | None = None,
) -> tuple[list[str], dict]:
    """标注一组记录文本的情绪键 → 返回 `(labels, info)`。

    `items` = 本组记录文本（条数 N 显式双写进模板）; `context` = 情境块（上一板原文 +
    末条情绪 / 首板 seed 锚）; `prev` = 板首 carry（板内延续起点）; `group_no` 进日志与模板。

    `labels` 长度恒 == `len(items)` 且全词表内（词表 = 情绪 ∪ 动作; 动作键原样带回,
    由调用方拆）——形状/项数不符重试至多两次, 仍失败则
    板内确定性延续（前一条键 → 板首 carry → nomal）, **绝不整批 None**。
    `info` = `{attempts, retry, fallback}`（retry = 触发重试次数; fallback = 兜底条数）。
    """
    n = len(items)
    if n == 0:
        return [], {"attempts": 0, "retry": 0, "fallback": 0}
    if not lexicon_keys:                        # 无词表防线（engine 已短路; 兜底）
        labels = [prev or _DEFAULT_EMOTION] * n
        return labels, {"attempts": 0, "retry": 0, "fallback": n}
    if max_tokens is None:
        max_tokens = _tl_max_tokens("emotion")
    kset = set(lexicon_keys) | ACTION_NAMES       # 一格一个键: 情绪或动作（同构）
    key_n, key_a, key_b = pick_demo_keys(lexicon_keys)
    lexicon = lexicon_hint or "\n".join(f"  {k}" for k in lexicon_keys)
    numbered = "\n".join(f"{i + 1}: {s}" for i, s in enumerate(items))

    def _system(retry_msg: str) -> str:
        return render_template(
            load_prompt("emotion_text_annotate"),
            {"group_no": str(group_no),
             "char_name": char_name or "（角色）",
             "character_hint": character or "（角色信息未注入）",
             "context": context or "（本章开场, 无更多情境。）",
             "n": str(n),
             "records": numbered,
             "lexicon": lexicon,
             "acts": render_prompt_block(),
             "key_n": key_n, "key_a": key_a, "key_b": key_b},
            where="emotion_text_annotate.md") + retry_msg

    mismatch: str | None = None                 # 上次失败原因（"期望 N, 实得 M"）
    length_bad = False                          # 长度不符记账（重试消息 + 日志）
    for attempt in range(_ANNO_TEXT_MAX_ATTEMPTS):
        retry_msg = ""
        if attempt > 0 and mismatch:
            retry_msg = (
                "\n（上次输出无法通过校验——项数不符: 期望 "
                + str(n) + ", 实得 " + str(mismatch) + "。只重新输出 "
                '{"labels": {1..' + str(n)
                + ' 的行号 → 情绪键}}, 无任何解释。）'
            )
        try:
            raw = llm.chat(
                [
                    {"role": "system", "content": _system(retry_msg)},
                    {"role": "user",
                     "content": '请输出每一条的键（情绪键或动作键）, 包装为 {"labels": '
                     '{行号: 键}}, 行号从 1 到 ' + str(n) + '（恰 ' + str(n)
                     + ' 项）。'},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
                # json_object + thinking 显式 off（真源 = task_levels）: v4-flash 默认
                # 思考会吃光 max_tokens 留下空 content; 编号映射由引擎数项。
                response_format="json_object",
                extra_body=_tl_extra("emotion"),
                task=EMOTION,              # 调用身份（节点 5b: 桩按它分派, 不进 payload）
            )
        except Exception as e:                  # noqa: BLE001 — 失败重试/板内延续
            logger.warning("emo 按板标注调用失败(第 %d/%d 次) group=%d: %s",
                           attempt + 1, _ANNO_TEXT_MAX_ATTEMPTS, group_no, e)
            mismatch = "调用异常"
            continue
        arr = _extract_key_array(raw)
        cleaned = _label_chain(arr, n, kset, prev)
        if cleaned is not None:
            labels, missing = cleaned
            return labels, {"attempts": attempt + 1, "retry": attempt,
                            "fallback": missing}
        mismatch = f"{len(arr)} 项" if isinstance(arr, list) else "无法解析"
        if isinstance(arr, list):
            length_bad = True
    # 预算耗尽 → 板内确定性延续（前一条键 → 板首 carry; 绝不整批 None）
    if length_bad:
        logger.warning("emo 按板标注长度不符 group=%d 期望 %d 实得 %s（板内延续）",
                       group_no, n, mismatch)
    labels = []
    cur = prev or _DEFAULT_EMOTION
    for _ in items:
        labels.append(cur)
    return labels, {"attempts": _ANNO_TEXT_MAX_ATTEMPTS,
                    "retry": _ANNO_TEXT_MAX_ATTEMPTS - 1, "fallback": n}
