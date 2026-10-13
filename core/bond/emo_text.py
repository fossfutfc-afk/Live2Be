"""按记录情绪标注原语 — 记录流 v2（一板一组一次调用; docs/DESIGN_STREAM_CONTRACT.md 附录 A §6）。

形态: 单板一次请求——【本板】= 本组要标的**记录**文本列表（真机 3~12 条;
一条记录 = 一个显示/判定单元, 内部可能含两三句）+ 【情境】（engine 按已生效链
记账: 非首板 = 上一板记录原文 + 末条情绪; 首板 = 本章 seed 锚; 禁后文）+ 全注释
词表 + I/O 示范（示范键由 engine 按实际词表动态挑选, 保证词表内合法）。engine
职责外置: 记录条数显式双写、长度=N 硬校验、每条必填、长度不符重试一次（消息带
"期望 N, 实得 M"）、词表外单项只丢该项——残余由本原语做板内延续
（上一条键 → 板首 carry）——**永不整批 None**。

**一条记录一个键**（2026-09-11 口径修正）: 记录内多句也只占一行——旧模板自称
"每行一句", 与 v2"一行 = 一条记录"的实际输入不符, 会诱使模型按句拆项
（长度不符 → 整板走延续兜底）。

提示词模板: llm/prompts/emotion_text_annotate.md（2026-09-11 口径修正）。
"""
from __future__ import annotations

import json
import logging
import re

from contract.slots import render_template
from core.bond.emotion_annotate import _extract_array
from llm.prompts import load_prompt
from llm.task_labels import EMOTION
from llm.task_levels import extra_body as _tl_extra
from llm.task_levels import max_tokens as _tl_max_tokens

logger = logging.getLogger("live2be.bond")

#: 示范优先键（词表常见情绪; 缺失则按词表顺序兜底——示范键恒 ∈ 词表）
_CANONICAL = ["nomal", "embarrassed", "smile", "surprised",
              "sad", "outburst", "expectant", "respond"]

#: 预算（2026-09-08 真 API 修正: 1 → 2 次重试）——空响应/项数错配在
#: 服务端负载期占首发 ~40%; 第 2 次重试显著回收; 仍失败走板内延续
#: （小输入快失败, 代价小; DESIGN_SCENE_STREAM §4.3/§10 注）
_ANNO_TEXT_MAX_ATTEMPTS = 3

#: 无词表/输入为空时的板内延续默认键（engine 侧已保证词表非空; 兜底防线）
_DEFAULT_EMOTION = "nomal"


def pick_demo_keys(lexicon_keys: list[str]) -> tuple[str, str, str]:
    """I-O 示范标签键: (转折示范 key_a, 转折示范 key_b, 叙述示范 key_n)。

    全 ∈ 实际词表——模板示范的标签键由 engine 动态挑选（DESIGN_SCENE_STREAM
    §0.7/§4.1 注: 示范永远词表内合法）。词表仅 1 键 → 同键兜底（格式仍示范）。
    """
    kset = list(dict.fromkeys(k for k in lexicon_keys if isinstance(k, str)))
    n = "nomal" if "nomal" in kset else (kset[0] if kset else _DEFAULT_EMOTION)
    rest = [k for k in _CANONICAL if k in kset and k != n]
    if not rest:
        rest = [k for k in kset if k != n]
    a = rest[0] if rest else n
    b = rest[1] if len(rest) > 1 else a
    return n, a, b


_KEY_RE = re.compile(r"^[A-Za-z_]+$")


def _first_list_value(obj: dict) -> object:
    """对象包装取键数组（数组形态）: labels/emotion 键优先, 否则首个 list。"""
    for key in ("labels", "emotion", "keys", "emotions"):
        v = obj.get(key)
        if isinstance(v, list):
            return v
    for v in obj.values():
        if isinstance(v, list):
            return v
    return None


def _numbered_map_value(obj: dict) -> object:
    """对象包装取键数组（编号映射形态, 2026-09-08 真 API 二修）。

    数组形态（text/json）下模型数不对项（n≥3 常合并/漏行 → 重试后整板兜底）。
    编号映射 `{"labels": {"1": 键, "2": 键}}` 让**引擎数项**（行号键集合）,
    模型只需逐行标——键(≥1)排序取值; 漏行/错位仍由项数硬校验兜底（重试）。
    """
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


def _extract_key_array(raw: object) -> object:
    """标注输出 → 键数组（形态无关: 数组 | 对象数组 | 对象编号映射）。

    2026-09-08 真 API 修正（DESIGN_SCENE_STREAM §4.1 注）: 文本模式实测
    deepseek-v4-flash 频发空响应/裸键数组（重试/整板兜底率飙升）→ 输出契约
    改 json_object 对象包装, 二修为**编号映射** {"labels": {"1":键,…}}
    （模型不再数项数——引擎按行号键集合数项）。本函数兜底兼容旧形态
    （dict/list/裸键容忍——测试桩与旧客户端路径用）。
    键合法性仍由词表成员校验兜底（丢非法项）, 项数仍由 _label_chain 硬校验
    （不符 → 重试一次, 消息带"期望 N, 实得 M"）。无法识别 → None。
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
                 ) -> tuple[list[str], int] | None:
    """数组 → 标签链: 长度恰 n → 逐项词表校验（词表外只丢该项 → 板内延续）。

    Returns:
        (labels, missing): 成功——labels 全 ∈ kset 且长度 n; missing = 兜底项数;
        None: 长度 != n（触发重试——不逐项消费错位数组）。
    """
    if not isinstance(arr, list) or len(arr) != n:
        return None
    labels: list[str] = []
    cur = prev
    missing = 0
    for item in arr:
        if isinstance(item, str) and item.strip() in kset:
            cur = item.strip()
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
    """标注一组记录文本的情绪键（记录流 v2: 一板一组的记录, 一条一个键）。

    Args:
        llm: LLM 客户端（标注走 emotion 档位——reasoning off / max_tokens 真源）。
        items: 本组要标的**记录文本**（engine 已知条数 N, 显式双写进模板）。
        lexicon_keys / lexicon_hint: 角色情绪词表（全注释注入, §0.5）。
        character / char_name: 人设卡（现网 _character_hint 形态, §0.2）与角色名。
        context: 情境块（engine 记账: 上一板记录原文+末条情绪 / 首板 seed 锚）。
        group_no: 组号（= 第几板; 日志/metrics/模板标题用）。
        prev: 板首 carry——上一板末条已生效情绪（词表内; 板内延续起点）。
        max_tokens: 输出上限（None → 真源 task_levels 形态 "emotion"=512）。

    Returns:
        (labels, info): labels 长度恒 == len(items) 且全词表内——
        形状/项数不符 → 重试至多两次; 仍失败/调用异常 → 板内确定性延续
        （前一条键 → 板首 carry → nomal）, **绝不整批 None**。
        info = {attempts, retry, fallback}: 质量记账（DESIGN_SCENE_STREAM §8:
        retry = 触发重试次数; fallback = 兜底条数——目标 ≈0）。
    """
    n = len(items)
    if n == 0:
        return [], {"attempts": 0, "retry": 0, "fallback": 0}
    if not lexicon_keys:                        # 无词表防线（engine 已短路; 兜底）
        labels = [prev or _DEFAULT_EMOTION] * n
        return labels, {"attempts": 0, "retry": 0, "fallback": n}
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
                     "content": '请输出情绪标签, 包装为 {"labels": {行号: '
                     '情绪键}}, 行号从 1 到 ' + str(n) + '（恰 ' + str(n)
                     + ' 项）。'},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
                # 2026-09-08 终局: json_object + **thinking 显式 disabled**
                # （task_levels off 语义; DeepSeek v4-flash 默认思考吃光
                # max_tokens → 空 content, DeepSeek-V3#1610 同型——disabled 后
                # 无空响应 + 引号/结构双保证, 单板 0.5-2.4s 实测）; 编号映射
                # 由引擎数项, 自纠错风暴不再触发
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
