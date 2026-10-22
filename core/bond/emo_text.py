"""按记录标注情绪（记录流 v2 的主链原语）—— 一板一组, 一次调用。

**一条记录一个键**: 记录内多句也只占一行（模板显式双写条数, 不是句子数）。
**有动作的那一行, 键写成 `"情绪键|动作键"`**（词表 = `core/bond/actions.py`）—— 形状不多
一层（thinking-off 的廉价模型撑不住嵌套）, 动作也贴着它自己那一行; 动作段坏了只丢动作。
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
from core.bond.actions import ACTION_NAMES, MAX_ACTS_PER_BOARD, render_prompt_block
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

#: 外壳键名（同一个意思的几种写法都认——为少一次重试, 不是"教模型写几种"）
_ROWS_KEYS = ("labels", "rows", "records", "result", "emotion", "keys", "emotions")
#: 值里的分隔符: `"情绪键|动作键"` —— 动作是可选的第二段, 没有就只有一段
_ACT_SEP = "|"


def _rows_of(raw: object) -> list[object] | None:
    """标注输出 → **行值列表**（按行号升序）; 认不出容器 → None。

    每行一个值; 行数是硬校验（不符就重试, 不消费错位的表）。容器的几种写法都是
    同一个意思（真 API 观测到过）:
      · `{"labels": {行号: 值}}` —— 提示词教的形状
      · `{"rows": {...}}` / 直接 `{行号: 值}` / 数组（下标+1）—— 模型偶尔换个壳
    值 = `"情绪键"` 或 `"情绪键|动作键"`（见 `_split_value`）。
    """
    if isinstance(raw, str):
        text = raw.strip()
        starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
        lo = min(starts) if starts else -1
        hi = max(text.rfind("}"), text.rfind("]"))
        if lo >= 0 and hi > lo:
            try:
                return _rows_of(json.loads(text[lo:hi + 1]))
            except ValueError:
                pass
        m = re.search(r"\[(.*)\]", text, re.S)      # 裸键容忍（省引号输出）
        if m and '"' not in m.group(1) and "'" not in m.group(1):
            items = [x.strip() for x in m.group(1).split(",") if x.strip()]
            if items and all(_KEY_RE.fullmatch(x) for x in items):
                return items
        return None
    if isinstance(raw, list):
        return list(raw)
    if not isinstance(raw, dict):
        return None
    for key in _ROWS_KEYS:                    # 有外壳: 剥一层（壳里可能是映射或数组）
        inner = raw.get(key)
        if isinstance(inner, (dict, list)):
            return _rows_of(inner)
    pairs: list[tuple[int, object]] = []      # 无外壳: 行号映射
    for k, val in raw.items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        if idx >= 1:
            pairs.append((idx, val))
    if pairs:
        pairs.sort()
        return [val for _, val in pairs]
    return None


def _split_value(val: object, kset: set[str]) -> tuple[str, str]:
    """一行的值 → `(情绪键, 动作键)`; 认不出的给空串（生死交给调用方）。

    值语法只有两种: `"情绪键"`（绝大多数行）或 `"情绪键|动作键"`。两段来自**互斥的两个
    词表** ⇒ 顺序写反也能拆对（省一次整板重试）。对象形态（模型偶尔自己展开）是兜底,
    不是教的形状。
    """
    if isinstance(val, dict):
        emo_raw = next((v for k in ("emotion", "key", "label")
                        if isinstance(v := val.get(k), str)), "")
        act_raw = next((v for k in ("act", "action", "motion")
                        if isinstance(v := val.get(k), str)), "")
        parts = [p.strip() for p in (emo_raw, act_raw) if p.strip()]
    elif isinstance(val, str):
        parts = [p.strip() for p in val.split(_ACT_SEP) if p.strip()]
    else:
        return "", ""
    emo = next((p for p in parts if p in kset), "")
    act = next((p for p in parts if p in ACTION_NAMES and p != emo), "")
    return emo, act


def _parse_rows(raw: object, n: int, kset: set[str], prev: str | None,
                ) -> tuple[list[str], list[str], int] | None:
    """标注输出 → `(labels, acts, missing)`; 行数不符 → None（触发重试）。

    · 情绪: 词表内才认, 否则只废这一行（板内延续: 前一条键 → 板首 carry）
    · 动作: 词表内才认; 空/词表外一律当"这一行不演" —— **不算错, 也不进重试**
    · 一板最多 `MAX_ACTS_PER_BOARD` 个（按行号留前几个, 其余作废并记日志）
    """
    rows = _rows_of(raw)
    if rows is None or len(rows) != n:
        return None
    labels: list[str] = []
    acts: list[str] = []
    cur = prev
    missing = 0
    kept = 0
    dropped = 0
    for val in rows:
        emo, act = _split_value(val, kset)
        if emo and emo in kset:
            cur = emo
        else:
            missing += 1                        # 空了/词表外 → 只废这一行的情绪
        labels.append(cur or _DEFAULT_EMOTION)
        if act and act in ACTION_NAMES and kept < MAX_ACTS_PER_BOARD:
            acts.append(act)
            kept += 1
        else:
            if act:
                dropped += 1                    # 词表外或超上限: 这一行不演
            acts.append("")
    if dropped:
        logger.warning("act 丢弃 %d 个（词表外或超每板上限 %d）",
                       dropped, MAX_ACTS_PER_BOARD)
    return labels, acts, missing


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
) -> tuple[list[str], list[str], dict]:
    """标注一组记录文本 → 返回 `(labels, acts, info)`。

    `items` = 本组记录文本（条数 N 显式双写进模板）; `context` = 情境块（上一板原文 +
    末条情绪 / 首板 seed 锚）; `prev` = 板首 carry（板内延续起点）; `group_no` 进日志与模板。

    `labels` 长度恒 == `len(items)` 且全词表内（**情绪**键）——形状/项数不符重试至多两次,
    仍失败则板内确定性延续（前一条键 → 板首 carry → nomal）, **绝不整批 None**。
    `acts` 同长度, 空串 = 这一行不演（**稀疏**, 词表见 `core/bond/actions.py`）——它坏了
    **不触发重试**: 动作是可选装饰, 不该把主链（情绪）拖下水。
    `info` = `{attempts, retry, fallback}`（retry = 触发重试次数; fallback = 兜底条数）。
    """
    n = len(items)
    if n == 0:
        return [], [], {"attempts": 0, "retry": 0, "fallback": 0}
    if not lexicon_keys:                        # 无词表防线（engine 已短路; 兜底）
        labels = [prev or _DEFAULT_EMOTION] * n
        return labels, [""] * n, {"attempts": 0, "retry": 0, "fallback": n}
    if max_tokens is None:
        max_tokens = _tl_max_tokens("emotion")
    kset = set(lexicon_keys)
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
                + ' 的行号 → 键}}, 无任何解释。）'
            )
        try:
            raw = llm.chat(
                [
                    {"role": "system", "content": _system(retry_msg)},
                    {"role": "user",
                     "content": '请按行输出情绪键, 包装为 {"labels": {行号: 键}}, '
                     '行号从 1 到 ' + str(n) + '（恰 ' + str(n) + ' 项）; '
                     '这一行她还有身体动作, 就把键写成 "情绪键|动作键"。'},
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
        parsed = _parse_rows(raw, n, kset, prev)
        if parsed is not None:
            labels, acts, missing = parsed
            return labels, acts, {"attempts": attempt + 1, "retry": attempt,
                                  "fallback": missing}
        rows = _rows_of(raw)
        mismatch = f"{len(rows)} 项" if rows is not None else "无法解析"
        if rows is not None:
            length_bad = True
    # 预算耗尽 → 板内确定性延续（前一条键 → 板首 carry; 绝不整批 None）
    if length_bad:
        logger.warning("emo 按板标注长度不符 group=%d 期望 %d 实得 %s（板内延续）",
                       group_no, n, mismatch)
    labels = []
    cur = prev or _DEFAULT_EMOTION
    for _ in items:
        labels.append(cur)
    return labels, [""] * n, {"attempts": _ANNO_TEXT_MAX_ATTEMPTS,
                              "retry": _ANNO_TEXT_MAX_ATTEMPTS - 1, "fallback": n}
