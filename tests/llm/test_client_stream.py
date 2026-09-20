# -*- coding: utf-8 -*-
"""LLMClient 流式路径测试（chat_full / chat_stream, mock httpx stream——不打网络）。

Step 1（方案 A 流式嗅探基座）: chat_stream 支持 response_format; chat_full
收集完整文本（等价 chat）+ on_chunk 每块增量回调 + json_object 自纠错复用。
"""
import json

import pytest
from unittest.mock import MagicMock

from llm.client import LLMClient


def _client_with_stream(lines: list[str], status: int = 200) -> LLMClient:
    """构造 mock 流式客户端: _http.stream 返回 (status, iter_lines)。"""
    client = LLMClient(api_key="test-key", base_url="https://example.test/v1")
    resp = MagicMock()
    resp.status_code = status
    resp.iter_lines.return_value = lines
    cm = MagicMock()
    cm.__enter__.return_value = resp
    client._http = MagicMock()              # 整体替换（httpx.Client 方法不可赋值）
    client._http.stream.return_value = cm
    return client


def _sse(chunks: list[str], reasoning: list[str] | None = None) -> list[str]:
    """SSE 行构造: 每块 content（可选 reasoning_content 交错）。"""
    out: list[str] = []
    for i, c in enumerate(chunks):
        delta: dict = {"content": c}
        if reasoning is not None and i < len(reasoning):
            delta["reasoning_content"] = reasoning[i]
        out.append("data: " + json.dumps({"choices": [{"delta": delta}]}))
    out.append("data: [DONE]")
    return out


def test_chat_full_collects_text_and_chunks():
    chunks = ["你", "好，", "老师！"]
    client = _client_with_stream(_sse(chunks))

    received: list[str] = []
    text = client.chat_full([{"role": "user", "content": "hi"}],
                            on_chunk=received.append)

    assert text == "你好，老师！"
    assert received == chunks


def test_chat_full_json_object_returns_dict():
    raw = '{"action": "story_scene", "payload": {"paragraphs": [{"text": "你好"}]}}'
    client = _client_with_stream(_sse([raw]))

    out = client.chat_full([{"role": "user", "content": "hi"}],
                           response_format="json_object")

    assert isinstance(out, dict)
    assert out["action"] == "story_scene"


def test_chat_full_payload_has_stream_and_json_format():
    client = _client_with_stream(_sse(["{}"]))
    client.chat_full([{"role": "user", "content": "hi"}],
                     response_format="json_object", max_tokens=999)

    payload = client._http.stream.call_args.kwargs["json"]
    assert payload["stream"] is True
    assert payload["max_tokens"] == 999
    assert payload["response_format"] == {"type": "json_object"}


def test_chat_stream_yields_chunks():
    chunks = ["一", "二", "三"]
    client = _client_with_stream(_sse(chunks))

    got = list(client.chat_stream([{"role": "user", "content": "hi"}]))

    assert got == chunks


def test_chat_full_stream_429_retry_then_ok():
    """429 退避重试（对齐 _request_with_retry）: 第一次 429, 第二次 200。"""
    client = LLMClient(api_key="test-key", base_url="https://example.test/v1")
    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.headers = {"Retry-After": "0"}
    cm_429 = MagicMock()
    cm_429.__enter__.return_value = resp_429

    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.iter_lines.return_value = _sse(["好了"])
    cm_ok = MagicMock()
    cm_ok.__enter__.return_value = resp_ok

    client._http = MagicMock()
    client._http.stream.side_effect = [cm_429, cm_ok]
    client.max_retries = 1

    text = client.chat_full([{"role": "user", "content": "hi"}])

    assert text == "好了"
    assert client._http.stream.call_count == 2


def test_chat_full_stream_401_raises_immediately():
    """401/403 立即抛（配置错误, 不重试）。"""
    client = LLMClient(api_key="test-key", base_url="https://example.test/v1")
    resp_401 = MagicMock()
    resp_401.status_code = 401
    resp_401.text = "bad key"
    resp_401.request = None
    resp_401.response = None
    cm_401 = MagicMock()
    cm_401.__enter__.return_value = resp_401
    client._http = MagicMock()
    client._http.stream.return_value = cm_401
    client.max_retries = 2

    import httpx
    with pytest.raises(httpx.HTTPStatusError):
        client.chat_full([{"role": "user", "content": "hi"}])
    assert client._http.stream.call_count == 1


# ---------------------------------------------------------------------------
# thinking level（settings.toml [llm] reasoning_effort, 2026-09-02）
# ---------------------------------------------------------------------------

def _client_with_effort(monkeypatch, effort: str) -> LLMClient:
    import llm.client as client_mod
    monkeypatch.setattr(client_mod, "_settings_toml",
                        lambda: {"llm": {"reasoning_effort": effort}})
    return LLMClient(api_key="test-key", base_url="https://example.test/v1")


def test_effort_parsed_from_settings(monkeypatch):
    c = _client_with_effort(monkeypatch, "high")
    assert c.default_extra_body == {"reasoning_effort": "high"}
    c2 = _client_with_effort(monkeypatch, "")
    assert c2.default_extra_body == {}                # 空/缺失 → 不注入


def test_effort_invalid_ignored(monkeypatch):
    c = _client_with_effort(monkeypatch, "turbo")
    assert c.default_extra_body == {}                 # 非法档位忽略（logger 警告）


def test_effort_injected_on_chat(monkeypatch):
    """extra_body=None → settings 默认档注入 payload; 显式 {} 关闭。"""
    c = _client_with_effort(monkeypatch, "medium")
    sent: list[dict] = []

    def fake_request(payload, timeout=None):
        sent.append(payload)
        return json.dumps({"ok": 1})

    monkeypatch.setattr(c, "_request_with_retry", fake_request)
    c.chat([{"role": "user", "content": "hi"}], response_format="text")
    assert sent[0].get("reasoning_effort") == "medium"

    c.chat([{"role": "user", "content": "hi"}], response_format="text",
           extra_body={})                              # 显式 {} → 关闭默认
    assert "reasoning_effort" not in sent[1]
