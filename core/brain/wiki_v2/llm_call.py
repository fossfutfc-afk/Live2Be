"""llm_call.py — digest 的 LLM 调用鲁棒层（板块 3 抽取, 原 digest.py 内联实现搬家）。

digest 唯一的 LLM 触面——所有传输级失败模式收敛一处:
    - 调用重试: 偶发空响应/坏 JSON → 重试 N 次（JsonExtract 等异常）
    - deadline: 撞上时间预算立即放弃（重试放大曾拖垮一次 digest 到近半小时, 2026-09-02）
    - reasoning_effort: None → {"reasoning_effort": "high"}（生产默认, 2026-09-02 拍板——
      实验矩阵 low 5/5(17s/次, 合格但浅) / medium 1/3(规则校验失败) / high 2/2
      (118s+32s, 认知深化与逐字校验质量最佳) → 默认提档 high; 显式传 {} 可关闭）
    - timeout: per-call 超时覆盖透传（后台长考; None → 客户端构造超时）

返回 (resp, err): resp 为 dict（json_object 已解析）或 None; err 非 None = 失败原因
（调用方决定降级/反馈, 本层不抛——失败静默降级语义在编排层）。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from core.common import err

logger = logging.getLogger(__name__)

#: 调用重试上限（偶发空响应/坏 JSON; 耗尽 → 降级; deadline 优先于次数）
MAX_CALL_RETRIES = 3
#: 默认请求附加字段（None → 此默认; 显式传 {} 关闭）——生产默认 high 档
DEFAULT_EXTRA_BODY: dict[str, str] = {"reasoning_effort": "high"}


def llm_chat(
    llm,
    system: str,
    user_msg: str,
    *,
    messages: list[dict] | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 8192,
    extra_body: dict | None = None,
    deadline: float | None = None,
    max_retries: int = MAX_CALL_RETRIES,
    timeout: float | None = None,
    label: str = "digest",
) -> tuple[dict | None, str | None]:
    """单次结构化调用（json_object）: 重试 N 次或撞 deadline。

    Args:
        messages: 完整消息列表（反馈回灌用——同一上下文续调: 编排层追加
                  assistant 被拒输出 + 引擎错误后传入; None → 由 system+user 组装）
        llm: 兼容 llm.chat(messages, model=, temperature=, max_tokens=,
             response_format=, extra_body=) 的客户端
        deadline: time.monotonic() 绝对截止时刻; None = 不限
        timeout: per-call 超时覆盖（后台长考放宽; None = 客户端构造超时）
        label: 日志上下文（digest / round_a / round_b …）

    Returns:
        (resp, None): 成功, resp = 解析后的 dict
        (None, err_str): 重试耗尽 / 撞 deadline
    """
    body = DEFAULT_EXTRA_BODY if extra_body is None else extra_body
    if messages is None:
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user_msg}]
    last_err: Exception | None = None
    for attempt in range(max_retries):
        if deadline is not None and time.monotonic() > deadline:
            return None, "LLM 调用撞上时间预算"
        try:
            resp = llm.chat(
                list(messages),
                model=model, temperature=temperature, max_tokens=max_tokens,
                response_format="json_object", extra_body=body, timeout=timeout)
            return resp, None
        except Exception as e:                       # noqa: BLE001
            last_err = e
            logger.warning(err("DigestFailed",
                               f"{label} LLM 调用失败（第 {attempt + 1}/{max_retries} 次）: {e}"))
    return None, f"LLM 调用重试耗尽: {last_err}"
