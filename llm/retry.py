"""带反馈重试的结构化调用 —— 三个引擎共用的**那一个循环**。

## 它收的是什么

「发一次 → parse → 被拒就把模型原文 + 引擎错误**回灌** → 重试 N 次」这个骨架，
bond / mmt / digest 各写了一份：

| 谁 | 在哪 | 形态 |
|---|---|---|
| bond | `core/bond/bond_story/engine.py:436-602` | `MAX_SCENE_RETRIES = 3`，4 处 `feedback()` |
| mmt | `core/mmt/engine.py` | 三段式：行级续写 `LINE_REASK_MAX=1` + 形状级重发 `SHAPE_RETRY_MAX=2` |
| digest | `core/digest/call.py:99-131` | `DIGEST_MAX_FEEDBACK = 1` |

**回灌那一半早就收口了** —— `llm.client.feedback()` 是全仓唯一的追加实现（11 个调用点）。
没收口的是它外面的循环：什么时候重试、重试几次、被拒之后说什么。本模块只装那个循环。

## 它不做什么

不发请求、不解析、不决定措辞、不记账 —— 四件事全由调用方以参数给（见 `call_with_feedback`）。
所以它不认识 MMT、不认识 VN、也不认识 digest；`llm/` 这一层本来就不该认识它们。

## 为什么不是"兜底策略表"

像 `core/digest/rounds/ROUNDS` 那样把三段式也变成数据，看着更整齐，但 mmt 的三段
（自愈 / 行级续写 / 形状级重发）**每段的 send 与 parse 都不同**，不是同一套参数换数字。
所以这里只给一个循环原语；要不要串成几段，是各引擎自己的策略。
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from contract.model import ValidationResult
from llm.client import feedback

__all__ = ["Attempt", "CallResult", "call_with_feedback"]


@dataclass(frozen=True)
class Attempt:
    """一次尝试的回执 —— 给日志 / trace / 账用（`index` 从 1 起）。"""

    index: int
    raw: Any
    verdict: ValidationResult


@dataclass(frozen=True)
class CallResult:
    """整个循环的回执。

    `verdict` 是**最后一次**的校验结果（成功时就是那一次成功的）。
    ⚠️ 契约层的 `warnings` / `drops` **只在被接受的那一次**才有意义 —— 前面几次的输出
    整包被拒，它们的 warning 描述的是一个**不存在的产物**（收进账里会让账说谎）。
    `attempts` 留着全部回执，正是为了让调用方能只取那一次。
    """

    ok: bool
    payload: Any | None
    verdict: ValidationResult
    attempts: tuple[Attempt, ...]


def _as_message_text(raw: Any) -> str:
    """回灌时把模型原文塞进 assistant 消息 —— dict 走 JSON，str 原样。"""
    if isinstance(raw, str):
        return raw
    return json.dumps(raw, ensure_ascii=False)


def call_with_feedback(
    messages: list[dict],
    *,
    send: Callable[[list[dict]], Any],
    parse: Callable[[Any], tuple[Any, ValidationResult]],
    reason: Callable[[ValidationResult], str],
    max_feedback: int = 1,
    guidance: str = "",
    on_attempt: Callable[[Attempt], None] | None = None,
) -> CallResult:
    """发一次 → parse → 被拒就用 `feedback()` 回灌 → 重试，最多重试 `max_feedback` 次。

    Args:
        messages: 会话历史。**原地追加**（与既有三个引擎的行为一致）：被拒时依次塞进
            `{"role": "assistant", 模型原文}` 与 `feedback()` 产生的 user 反馈。
        send: 发一次并返回模型原始输出。域内决定模型 / 温度 / 上限 / `task` 标签 / 流式。
        parse: 原始输出 → `(payload, ValidationResult)`。契约层统一签名。
        reason: 被拒时构造回灌正文。⚠️ **措辞归调用方** —— 桩与用例会盯回灌消息的原文，
            不在这里统一改写（`feedback()` 的 docstring 也这么写）。
        max_feedback: **重试**次数（总尝试 = `1 + max_feedback`；0 = 只发一次）。
        guidance: 可选，由 `feedback()` 附在正文下一行。
        on_attempt: 每次尝试后回调（账 / trace / 日志）。

    Returns:
        `CallResult.ok` 为真 ⇒ `payload` 是那次成功的 parse 产物；为假 ⇒ 全部尝试都被拒，
        `verdict` 是最后一次的结果（`errors` 已填）。
    """
    attempts: list[Attempt] = []
    last = ValidationResult(errors=("未发起调用",))

    for index in range(1, max_feedback + 2):
        raw = send(messages)
        payload, verdict = parse(raw)
        attempt = Attempt(index=index, raw=raw, verdict=verdict)
        attempts.append(attempt)
        if on_attempt is not None:
            on_attempt(attempt)

        if verdict.is_valid:
            return CallResult(ok=True, payload=payload, verdict=verdict,
                              attempts=tuple(attempts))

        last = verdict
        if index > max_feedback:                       # 次数用尽 —— 不再回灌
            break
        messages.append({"role": "assistant", "content": _as_message_text(raw)})
        feedback(messages, reason(verdict), guidance)

    return CallResult(ok=False, payload=None, verdict=last, attempts=tuple(attempts))
