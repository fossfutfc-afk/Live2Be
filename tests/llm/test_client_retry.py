"""`llm.client._classify` —— 传输级重试判据的**单点**。

`_request_with_retry`（非流式）与 `_stream_collect`（流式）原先各自抄了一份
401/403 · 429 · ≥500 的阶梯，连两条错误消息都逐字重复；现在两处都只问 `_classify`。
⇒ 下面覆盖的就是**两条路径**的行为，改判据时一起生效。

顺带钉住判据的**次序**（它是有意为之，不是巧合）：
200 → 401/403 → 次数用尽 → 429 → ≥500 → 其余。
所以「403 且次数已用尽」仍然是 `auth`（消息是"认证失败"而不是"API error"）。
"""
from __future__ import annotations

import pytest

from llm.client import _classify


class _Resp:
    """只带 `_classify` 会读的两个属性。"""

    def __init__(self, status: int, retry_after: str | None = None) -> None:
        self.status_code = status
        self.headers = {} if retry_after is None else {"Retry-After": retry_after}


@pytest.mark.parametrize(("status", "attempt", "max_retries", "kind"), [
    (200, 0, 3, "ok"),
    (401, 0, 3, "auth"),      # 认证错误：还有次数也不重试
    (403, 3, 3, "auth"),      # 次数已用尽也仍是 auth（决定抛哪条消息）
    (429, 0, 3, "retry"),
    (429, 3, 3, "fatal"),     # 次数用尽
    (500, 0, 3, "retry"),
    (503, 3, 3, "fatal"),
    (400, 0, 3, "fatal"),     # 4xx 非认证：不重试
])
def test_classify_kinds(status, attempt, max_retries, kind):
    got, _wait = _classify(_Resp(status), attempt, max_retries)
    assert got == kind, f"{status} @attempt={attempt}/{max_retries} → {got}"


def test_429_retry_after_has_three_states():
    """429 的等待时间有**三态**，而且第三态与前两态不同源（实测行为）。

    · 带头且为正 → 按它等（服务端说了算）
    · 带头但 ≤ 0 → 指数退避 `2**attempt`
    · 没头 / 值非法 → **固定 5.0** —— 来自 `_parse_retry_after` 的兜底，
      不是退避公式。⚠️ 所以"没头"比"头为 0"等得更久（5.0 vs 1.0@attempt0）。
    """
    assert _classify(_Resp(429, "7"), 0, 3)[1] == 7.0
    assert _classify(_Resp(429, "0"), 2, 3)[1] == 4.0
    assert _classify(_Resp(429, "0"), 0, 3)[1] == 1.0
    assert _classify(_Resp(429), 2, 3)[1] == 5.0          # 没头 → 兜底 5.0
    assert _classify(_Resp(429, "abc"), 1, 3)[1] == 5.0   # 非法 → 兜底 5.0


def test_5xx_backs_off_exponentially():
    assert _classify(_Resp(500), 0, 3)[1] == 1.0
    assert _classify(_Resp(503), 2, 3)[1] == 4.0


def test_non_retry_kinds_carry_no_wait():
    """ok / auth / fatal 都不带等待 —— 调用方不该拿它们去 sleep。"""
    for status in (200, 401, 403, 400):
        assert _classify(_Resp(status), 0, 3)[1] == 0.0
