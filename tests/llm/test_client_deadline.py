"""`LLMClient.chat(deadline=…)` —— **预算真的能卡住重试**。

## 为什么有这一组

2026-10-18 之前 `deadline` 只活在调用方（`llm_chat`）自己的循环里: 每次尝试**之前**看一眼,
过了就不发。而"正在飞的那一次"和它内部的**传输层重试**完全不看它 —— 于是一次挂死的请求
可以把 `timeout × (max_retries + 1)` 全部跑满（真机参数: 300s × 4 ≈ 20 分钟, 而那一轮的
预算是 120s）。报错写着"撞上时间预算", 墙钟早就超了十倍。

这一组钉三件事:
  ① 单次超时被夹到 `min(timeout, 距 deadline 剩余)`（`_attempt_timeout`）;
  ② deadline 过了 ⇒ **一次新尝试都不发**（不是"再试一次看看"）;
  ③ 没有 deadline 时行为**一个字都不变**（次数上限仍由 `max_retries` 管）。

时钟是假的（`time.monotonic` / `time.sleep` 都被替换）—— 否则"预算用完"要靠真的等,
而这组用例要验的是**判定**, 不是睡眠时长。
"""
from __future__ import annotations

import time

import httpx
import pytest

from llm import client as C


class _Clock:
    """可控时钟: `tick()` 往前走，`monotonic()` 读它。"""

    def __init__(self, t0: float = 1000.0) -> None:
        self.t = t0

    def __call__(self) -> float:
        return self.t

    def tick(self, dt: float) -> None:
        self.t += dt


@pytest.fixture()
def clock(monkeypatch):
    """把 `llm.client` 看到的时间换成假时钟（`time` 是同一个模块对象, 所以是全局替换,
    monkeypatch 会在用例结束时还原; 本组用例都是同步的, 中途没有别的东西依赖真实时钟）。"""
    c = _Clock()
    monkeypatch.setattr(time, "monotonic", c)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    return c


def _client(clock, *, handler, max_retries: int = 3):
    """一个 `_http` 被换成 MockTransport 的客户端（不发真实请求）。"""
    cli = C.LLMClient(api_key="test-key", base_url="https://example.test/v1",
                      model="m", timeout=240.0, max_retries=max_retries)
    cli._http = httpx.Client(base_url="https://example.test/v1",
                             transport=httpx.MockTransport(handler))
    return cli


def _chat(cli, **kw):
    return cli.chat([{"role": "user", "content": "hi"}], response_format="text", **kw)


def test_attempt_timeout_is_clamped_to_remaining_budget(clock):
    """单次超时 = `min(timeout, 距 deadline 剩余)` —— 不是 `timeout` 说了算。"""
    cli = _client(clock, handler=lambda r: httpx.Response(200, json={}))
    deadline = clock() + 15.0
    got = cli._attempt_timeout(None, deadline)          # None = 用构造超时 240s
    assert got.read == pytest.approx(15.0), "预算 15s, 单次超时却还是 240s"
    assert cli._attempt_timeout(5.0, deadline).read == pytest.approx(5.0), \
        "显式 timeout 比剩余小 ⇒ 用它（不放大）"
    assert cli._attempt_timeout(None, None) is None, "没有 deadline ⇒ 一个字都不改"


def test_sleep_never_runs_past_deadline(clock):
    """退避不许睡过 deadline（睡过去 = 白等一次预算）。"""
    assert C.LLMClient._sleep_for(100.0, clock() + 3.0) == pytest.approx(3.0)
    assert C.LLMClient._sleep_for(1.0, clock() + 3.0) == pytest.approx(1.0)
    assert C.LLMClient._sleep_for(100.0, None) == pytest.approx(100.0)


def test_expired_deadline_sends_nothing(clock):
    """deadline 已经过去 ⇒ **0 次**请求（连第一次都不发）。"""
    hits: list[int] = []

    def handler(request):
        hits.append(1)
        return httpx.Response(200, json={})

    cli = _client(clock, handler=handler)
    with pytest.raises(httpx.TimeoutException):
        _chat(cli, deadline=clock() - 1.0)
    assert hits == [], "预算已过还发了请求"


def test_deadline_stops_retrying_a_failing_call(clock):
    """传输层重试撞上 deadline 就收手 —— 这是"20 分钟"那个病的正面判据。

    第 1 次尝试花掉 10s（假时钟前进）, 500 ⇒ 本该再退避重试; 但剩下的预算撑不住
    ⇒ 只发生 **1 次**请求。没有 deadline 时同一条路会走满 `max_retries + 1` 次。
    """
    hits: list[int] = []

    def handler(request):
        hits.append(1)
        clock.tick(10.0)                       # 这次尝试"耗时 10s"
        return httpx.Response(500, json={"error": "boom"})

    cli = _client(clock, handler=handler)
    with pytest.raises(httpx.TimeoutException):
        _chat(cli, deadline=clock() + 12.0)
    assert len(hits) == 2, f"预算 12s / 每次 10s ⇒ 只该试 2 次, 实际 {len(hits)}"

    hits.clear()
    with pytest.raises(httpx.HTTPStatusError):  # 没有 deadline ⇒ 走满 4 次后抛
        _chat(cli)
    assert len(hits) == 4, "没有 deadline 时次数上限必须仍是 max_retries + 1"


def test_success_returns_within_budget(clock):
    """健康调用不受影响（有 deadline 也照常返回）。"""
    cli = _client(clock, handler=lambda r: httpx.Response(
        200, json={"choices": [{"message": {"content": "ok"}}]}))
    assert _chat(cli, deadline=clock() + 60.0) == "ok"


def test_llm_chat_hands_deadline_to_the_client(clock):
    """`llm_chat` 的 deadline 必须**交给客户端**执行（只在自己循环里看 = 没执行）。"""
    seen: dict = {}

    class _Stub:
        def chat(self, messages, **kw):
            seen.update(kw)
            return {"ok": 1}

    deadline = clock() + 30.0
    resp, err = C.llm_chat(_Stub(), "sys", "user", deadline=deadline, timeout=3.0)
    assert (resp, err) == ({"ok": 1}, None)
    assert seen.get("deadline") == deadline
    assert seen.get("timeout") == 3.0
