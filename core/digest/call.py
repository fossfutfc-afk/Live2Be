"""call.py — **一轮 LLM 调用的四件套**（2026-09-29 从 `pipeline.py` 拆出）。

装的是"怎么发这一轮、发失败怎么说"——**不装任何业务**（哪一轮吃什么、写什么在图/表里）：

| 函数 | 干什么 |
|---|---|
| `_system_for` | 这一轮的 system = prompt 文件 + 该轮的产出契约（`{{digest_schema}}`） |
| `_parse_for` | 把表里那个 parse 绑上这一轮的上下文（`seq_set` / `episode_ids`…） |
| `_round_call` | 调用 → parse → 结构被拒 ⇒ assistant 原文 + 错误**回灌重试 1 次** |
| `_round_deadline` / `_call_failed` | 本轮截止 = `min(整段硬顶, 现在 + 预算)`；失败文案**带轮次** |
| `_log_skip` | 跳过这一轮（文案来自轮次表的 `skip` 格） |

⚠️ **为什么是"一轮"而不是"某一轮"**: 五轮共用这一套（prompt/相位/预算/parse 都从
`rounds.ROUNDS` 的 spec 取）—— 所以这里一行轮次名都不该出现。
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from contract.digest import digest_registry
from contract.slots import render_template
from core.digest.rounds import RoundSpec, budget_of
from llm.client import feedback, llm_chat
from llm.prompts import load_prompt

if TYPE_CHECKING:                       # 仅注解求值期（避免与编排层循环 import）
    from core.digest.pipeline import DigestResult

logger = logging.getLogger(__name__)

#: 反馈重试（parse/结构被拒 → 带 assistant 原文回灌重试 1 次）
DIGEST_MAX_FEEDBACK = 1


def _system_for(spec: RoundSpec, *, domain: str = "mmt", chapter_count: int = 1) -> str:
    """这一轮的 system = 对应 prompt 文件 + 该轮的**产出契约**（`{{digest_schema}}`）。

    `domain` / `chapter_count` 是 `build_schema` 的分域参数（R0 与 R1 都要 ——
    "这一段该切成几件事"的说明跟着"作者单位"走）。⚠️ 原先这里是 `**schema_kw`,
    名单藏在 kwargs 里; 写死成具名参数之后,**谁要传什么一眼看得见**, 传错当场 TypeError。
    """
    return render_template(
        load_prompt(spec.prompt),
        {"digest_schema": digest_registry.build_schema(
            spec.phase, domain=domain, chapter_count=chapter_count)},
        where=f"{spec.prompt}.md")


def _parse_for(spec: RoundSpec, **ctx) -> Callable[[dict], tuple[Any, Any]]:
    """把表里那个 parse 函数绑上**这一轮的上下文**（`seq_set` / `episode_ids` / `block_ids`…）。

    契约层的 parse 签名统一是 `(raw, **ctx)` ⇒ 表里存函数、调用点给上下文, 两不相欠。
    """
    return lambda raw: spec.parse(raw, **ctx)


def _log_skip(spec: RoundSpec) -> None:
    """跳过这一轮 —— 那句日志的文案来自表（`skip` 是唯一真源）, 前缀来自 `spec.name`。"""
    logger.info("%s 跳过（%s）", spec.name, spec.skip)


def _round_call(
    llm,
    system: str,
    user: str,
    *,
    spec: RoundSpec,
    model: str | None,
    temperature: float,
    max_tokens: int,
    llm_timeout: float | None,
    extra_body: dict | None,
    hard_deadline: float,
    parse_fn: Callable[[dict], tuple[Any, Any]],
    result: DigestResult,
) -> tuple[Any | None, dict | None]:
    """一轮 LLM 调用: 调用 → parse → 结构被拒 → assistant 原文 + 错误回灌重试 1 次。

    ⭐ **本轮的截止在这里算**: `min(整段硬顶, 现在 + 本轮预算)`（预算取自轮次表）。
    从前全段共享一个 deadline ⇒ 前几轮一慢, 后面几轮**集体被饿死**, 而报错还看不出
    是哪一轮。现在单轮慢只影响它自己, 失败文案也带轮次。

    ⭐ 回灌走 `llm.client.feedback`（**唯一实现** —— 同 bond/mmt 的形状:
    "assistant 手写被拒原文 + user 走 helper"）; 措辞与从前逐字相同。

    `result` 只用到 `errors` / `llm_calls` 两个字段 ⇒ A/B 轮（`DigestResult`）与
    （全景轮退役前曾与它共用这条路径 —— N4a 起只剩 digest。）

    Returns:
        (parsed, last_resp): parsed None = 该轮失败（result.errors 已填, 调用方回滚）
    """
    round_deadline = _round_deadline(hard_deadline, budget_of(spec))
    label = spec.label
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": user}]
    for attempt in range(DIGEST_MAX_FEEDBACK + 1):
        resp, call_err = llm_chat(llm, system, "", messages=msgs, model=model,
                                  temperature=temperature, max_tokens=max_tokens,
                                  extra_body=extra_body, deadline=round_deadline,
                                  timeout=llm_timeout, label=label)
        if resp is None:
            result.errors.append(
                _call_failed(label, call_err, round_deadline, hard_deadline))
            return None, None
        result.llm_calls += 1
        if not isinstance(resp, dict):
            result.errors.append(f"digest 轮次 {label}: LLM 输出非 JSON 对象")
            return None, resp
        parsed, vr = parse_fn(resp)
        if vr.is_valid:
            # ⭐ D1（2026-09-29）: 契约层"说过的话"要接出来 —— 从前 `vr.warnings` 一个字
            # 都没落（本函数只看 `is_valid` / `errors`）, 于是"这条区间作废 ⇒ 内容没主"
            # 这种**当场才知道**的事实永久消失。
            # ⚠️ **只收被接受那一次尝试的**: 前面几次的输出整包被拒, 它们的 warning
            # 描述的是一个**不存在的产物**（收进来会让账说谎）。
            result.contract_warnings.extend(f"{label}: {w}" for w in vr.warnings)
            result.contract_drops.extend(f"{label}: {d}" for d in vr.drops)
            return parsed, resp
        if attempt < DIGEST_MAX_FEEDBACK:
            # feedback 语义: 同一上下文——追加被拒输出 + 引擎错误（见 `llm.client.feedback`）
            msgs.append({"role": "assistant",
                         "content": json.dumps(resp, ensure_ascii=False)})
            feedback(msgs, "【引擎校验反馈（上一轮输出被整包拒绝,"
                           " 请修正后重新输出完整 JSON）】\n"
                           + "\n".join(f"- {e}" for e in vr.errors))
            continue
        result.errors.extend(vr.errors)
        return None, resp
    return None, None                                     # unreachable


def _round_deadline(hard_deadline: float | None, budget: float) -> float | None:
    """本轮的截止时刻 = `min(整段硬顶, 现在 + 本轮预算)` —— **判据在这一行**。

    两个都要: 只看本轮预算 ⇒ 段可以无限长（半小时那次事故）; 只看整段硬顶 ⇒
    前几轮一慢就把后面的轮饿死（刀 1 要修的那个病）。
    """
    if budget <= 0:
        return hard_deadline
    soft = time.monotonic() + budget
    if hard_deadline is None:
        return soft
    return min(hard_deadline, soft)


def _call_failed(label: str, call_err: str | None, round_deadline: float | None,
                 hard_deadline: float | None) -> str:
    """一轮调用失败的记账 —— **带上轮次**, 并说清是"本轮预算用完"还是"整段硬顶到了"。

    从前这句是裸的 `LLM 调用撞上时间预算`（`llm_chat` 的原文）, grep 出来分不出
    是哪一轮、也分不出是哪种预算 ⇒ 事后无法定位"谁把时间吃掉了"。
    """
    msg = call_err or "LLM 调用失败"
    if round_deadline is None:
        return f"digest 轮次 {label}: {msg}"
    left = round_deadline - time.monotonic()
    hit_cap = hard_deadline is not None and round_deadline >= hard_deadline
    which = "整段硬顶到了" if hit_cap else "本轮预算用完"
    return f"digest 轮次 {label}: {msg}（{which}, 离本轮截止还剩 {max(left, 0.0):.0f}s）"
