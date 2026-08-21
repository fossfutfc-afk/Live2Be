"""
LLM API Client — OpenAI-compatible Chat Completions 封装。

职责:
  - HTTP 通信 + 指数退避重试
  - JSON 响应解析（委托给 json_cleaner）
  - 格式化成标准 messages 列表

用法:
    from llm.client import LLMClient
    client = LLMClient()
    reply = client.chat(messages)
    data  = client.chat(messages, response_format="json_object")
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import certifi
import httpx
from dotenv import load_dotenv

from core.common import err
from llm.json_cleaner import extract_json

# Windows + conda SSL 证书修复
os.environ["SSL_CERT_FILE"] = certifi.where()

# 加载 .env
_project_root = Path(__file__).resolve().parents[1]
_load_dotenv_result = load_dotenv(_project_root / ".env")


class LLMClient:
    """OpenAI-compatible Chat Completions 客户端。

    从 .env 读取 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL，
    构造时可逐一覆盖。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL", "deepseek-v4-flash")
        self.timeout = timeout
        self.max_retries = max_retries

        if not self.api_key:
            raise ValueError(err(
                "ConfigError",
                "LLM_API_KEY not set. 请在 .env 中设置或通过 LLMClient(api_key=...) 传入",
            ))

        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(self.timeout),
        )

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.8,
        max_tokens: int = 1024,
        response_format: str = "text",
        extra_body: dict[str, Any] | None = None,
    ) -> str | dict[str, Any]:
        """发送 chat completion 请求（批次模式）。"""
        effective_model = model or self.model

        payload = _build_payload(
            messages=messages,
            model=effective_model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            extra_body=extra_body,
        )

        raw_text = self._request_with_retry(payload)

        if response_format == "json_object":
            return self._extract_json_with_llm_correction(
                first_attempt=raw_text,
                messages=messages,
                model=effective_model,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra_body,
            )
        return raw_text

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.8,
        max_tokens: int = 512,
    ):
        """流式 chat completion — yield 每个 token 的文本增量。

        用法:
            for chunk in client.chat_stream(messages):
                print(chunk, end="", flush=True)
        """
        effective_model = model or self.model

        payload = {
            "model": effective_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        with self._http.stream("POST", "/chat/completions", json=payload) as resp:
            if resp.status_code != 200:
                raise httpx.HTTPStatusError(
                    err("LLMAPI", f"LLM API error {resp.status_code}: {resp.text[:500]}"),
                    request=resp.request,
                    response=resp,
                )
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    @staticmethod
    def format_messages(
        system_prompt: str,
        user_message: str,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """组装标准 messages 列表: system + history + user。"""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 内部: JSON 修正
    # ------------------------------------------------------------------

    def _extract_json_with_llm_correction(
        self,
        first_attempt: str,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        extra_body: dict[str, Any] | None,
        max_json_retries: int = 3,
    ) -> dict[str, Any]:
        """尝试解析 JSON；失败时把错误喂回 LLM，最多 N-1 次重试。"""
        raw_text = first_attempt

        for attempt in range(max_json_retries):
            try:
                return extract_json(raw_text)
            except ValueError as e:
                if attempt == max_json_retries - 1:
                    raise

                truncated = raw_text[:2000] if len(raw_text) > 2000 else raw_text
                messages.append({"role": "assistant", "content": truncated})
                messages.append({
                    "role": "user",
                    "content": (
                        f"你上一轮的回复无法解析为合法JSON。\n"
                        f"解析错误详情：{e}\n\n"
                        f"请修正以上错误，严格以纯JSON格式重新输出。"
                        f"键和字符串必须用双引号(\")包裹，禁止用单引号，"
                        f"布尔用 true/false，空值用 null。"
                        f"不要用 ```json``` 代码块包裹，不要添加任何解释文字。"
                        f"只输出JSON对象，以 {{ 开头、以 }} 结尾。"
                    ),
                })

                payload = _build_payload(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format="json_object",
                    extra_body=extra_body,
                )
                raw_text = self._request_with_retry(payload)

        raise ValueError(err("JsonCorrection", f"JSON correction failed after {max_json_retries} total attempts"))

    # ------------------------------------------------------------------
    # 内部: HTTP
    # ------------------------------------------------------------------

    def _request_with_retry(self, payload: dict[str, Any]) -> str:
        """发送请求，带指数退避重试。"""
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = self._http.post("/chat/completions", json=payload)
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise

            if resp.status_code == 200:
                return _parse_chat_response(resp.json())

            if resp.status_code == 429:
                retry_after = _parse_retry_after(resp)
                if attempt < self.max_retries:
                    time.sleep(retry_after if retry_after > 0 else 2 ** attempt)
                    continue

            if resp.status_code >= 500 and attempt < self.max_retries:
                time.sleep(2 ** attempt)
                continue

            raise httpx.HTTPStatusError(
                err("LLMAPI", f"LLM API error {resp.status_code}: {resp.text[:500]}"),
                request=resp.request,
                response=resp,
            )

        assert last_error is not None
        raise last_error


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------

def _build_payload(
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
    response_format: str,
    extra_body: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    if response_format == "json_object":
        payload["response_format"] = {"type": "json_object"}
        _ensure_json_instruction(messages)

    if extra_body:
        payload["extra_body"] = extra_body

    return payload


def _ensure_json_instruction(messages: list[dict[str, str]]) -> None:
    """确保 messages 中有 'JSON' 字样（API 要求）。"""
    all_text = " ".join(m["content"] for m in messages if "content" in m)
    if "json" not in all_text.lower() and "JSON" not in all_text:
        if messages and messages[-1]["role"] == "user":
            messages[-1]["content"] += "\n\n请以纯JSON格式回复，不要包含markdown代码块。"
        else:
            messages.append({
                "role": "user",
                "content": "请以纯JSON格式回复，不要包含markdown代码块。",
            })


def _parse_chat_response(body: dict[str, Any]) -> str:
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(err(
            "BadResponse",
            f"Failed to parse response body. "
            f"Expected choices[0].message.content. Got keys: {list(body.keys())}",
        )) from e


def _parse_retry_after(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After", "")
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 5.0
