"""
LLM API Client — OpenAI-compatible Chat Completions 封装。

职责：
  - HTTP 通信 + 指数退避重试
  - JSON 响应清洗（处理 AI 不听话的各种情况）
  - 剩下的一切（人设拼装、记忆检索、Prompt 构造）都是调用方的责任

用法:
    from llm.client import LLMClient

    client = LLMClient()                        # 自动读取 .env
    msgs = client.format_messages(sys_prompt, user_input, history)
    reply = client.chat(msgs)                   # 自然语言 → str
    data  = client.chat(msgs, response_format="json_object")  # JSON → dict
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

# Windows + conda SSL 证书路径修复
# conda 环境的 SSL_CERT_FILE 有时指向不存在的路径，
# 用 certifi 提供的 CA bundle 覆盖
import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()

# ---------------------------------------------------------------------------
# 自动加载 .env（从项目根目录）
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parents[1]
_load_dotenv_result = load_dotenv(_project_root / ".env")


# ---------------------------------------------------------------------------
# JSON 清洗管道
# ---------------------------------------------------------------------------

def _strip_markdown_fence(text: str) -> str:
    """Layer 1: 移除 ```json ... ``` 包裹。"""
    text = text.strip()
    # 精确匹配：```json\n...\n```
    if text.startswith("```") and text.endswith("```"):
        # 去掉开头的 ``` 及可能的语言标记
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        else:
            text = text[3:]  # 没有换行？直接去掉 ```
        text = text[: text.rfind("```")].strip()
    return text


def _extract_json_substring(text: str) -> str:
    """Layer 2: 找到第一个 { 到最后一个 } 的区间。"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return text  # 找不到花括号，原样返回让 json.loads 报错
    return text[start:end + 1]


def _repair_common_json_errors(text: str) -> str:
    """Layer 4: 修复常见 JSON 语法错误。

    这里的每一项修复都是"宁可错杀不可放过"的安全操作——
    只处理高置信度的模式。
    """
    # 移除尾部逗号（"key": "value",} → "key": "value"}）
    text = re.sub(r",\s*(\}|\])", r"\1", text)

    # 单行 // 注释 → 移除
    text = re.sub(r"//[^\n]*", "", text)

    # 行尾逗号后无下一项（"\n]" 前多余逗号也由第一条覆盖）
    return text


def extract_json(response_text: str) -> dict[str, Any]:
    """完整的 JSON 提取管道。

    Args:
        response_text: LLM 返回的原始文本，可能包含 markdown 包裹、前后废话等。

    Returns:
        解析成功的 dict。

    Raises:
        ValueError: 所有清洗手段用尽后仍无法解析。
    """
    errors: list[str] = []
    original = response_text

    # Layer 1: 去 markdown 代码块
    cleaned = _strip_markdown_fence(response_text)

    # Layer 2: 提取 JSON 子串
    cleaned = _extract_json_substring(cleaned)

    # Layer 3: 直接解析
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        errors.append(f"clean parse: {e}")

    # Layer 4: 修复常见错误后重试
    repaired = _repair_common_json_errors(cleaned)
    if repaired != cleaned:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e:
            errors.append(f"repaired parse: {e}")

    # 全部失败 → 抛出诊断信息
    raise ValueError(
        f"JSON extraction failed after {len(errors)} attempts.\n"
        f"--- raw response (first 500 chars) ---\n"
        f"{original[:500]}\n"
        f"--- cleaned (first 500 chars) ---\n"
        f"{cleaned[:500]}\n"
        f"--- errors ---\n"
        f"{chr(10).join(errors)}"
    )


# ---------------------------------------------------------------------------
# 主客户端
# ---------------------------------------------------------------------------

class LLMClient:
    """OpenAI-compatible Chat Completions 客户端。

    自动从 .env 读取配置：
        LLM_API_KEY  — API 密钥（必需）
        LLM_BASE_URL — API 地址（默认 https://api.deepseek.com/v1）
        LLM_MODEL    — 模型名（默认 deepseek-chat）

    也可在构造时覆盖：
        client = LLMClient(api_key="sk-...", base_url="...", model="...")
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
        self.model = model or os.getenv("LLM_MODEL", "deepseek-chat")
        self.timeout = timeout
        self.max_retries = max_retries

        if not self.api_key:
            raise ValueError(
                "LLM_API_KEY not set. 请在 .env 文件中设置 LLM_API_KEY=sk-xxx "
                "或通过 LLMClient(api_key=...) 传入"
            )

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
        """发送 chat completion 请求。

        Args:
            messages:        标准 messages 列表
            model:           模型名（默认使用构造时指定的模型）
            temperature:     生成温度 (0.0-2.0)
            max_tokens:      最大输出 token 数
            response_format: "text" → 返回 str；"json_object" → 返回 dict
            extra_body:      额外请求体字段

        Returns:
            response_format="text" → str（角色回复文本）
            response_format="json_object" → dict（解析后的 JSON）

        Raises:
            httpx.HTTPError: 网络错误（含重试耗尽）
            ValueError:      JSON 解析失败（含 LLM 修正重试耗尽）
        """
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

    # ------------------------------------------------------------------
    # 辅助
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
        """尝试解析 JSON；失败时把错误喂回 LLM 请求修正，最多 N-1 次重试。

        流程:
            attempt 0: 解析第一次 LLM 响应
            attempt 1: 失败 → 追加"JSON格式错误，请修正"→ 重新请求 → 解析
            attempt 2: 再失败 → 同上
            attempt 3 (max): 最后一次失败 → 抛出 ValueError

        每次修正时，LLM 会看到它之前的错误输出和解析器给出的具体错误信息。
        """
        raw_text = first_attempt

        for attempt in range(max_json_retries):
            try:
                return extract_json(raw_text)
            except ValueError as e:
                if attempt == max_json_retries - 1:
                    raise  # 修正重试耗尽，向上抛出

                # 将失败的输出 + 修正指令追加到 messages
                # 截断过长内容，防止 token 爆炸
                truncated = raw_text[:2000] if len(raw_text) > 2000 else raw_text
                messages.append({"role": "assistant", "content": truncated})
                messages.append({
                    "role": "user",
                    "content": (
                        f"你上一轮的回复无法解析为合法JSON。\n"
                        f"解析错误详情：{e}\n\n"
                        f"请修正以上错误，严格以纯JSON格式重新输出。"
                        f"不要用 ```json``` 代码块包裹，不要添加任何解释文字。"
                        f"只输出JSON对象，以 {{ 开头、以 }} 结尾。"
                    ),
                })

                # 用更新后的 messages 重新请求
                payload = _build_payload(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format="json_object",
                    extra_body=extra_body,
                )
                raw_text = self._request_with_retry(payload)

        # 不应到达此处
        raise ValueError(
            f"JSON correction failed after {max_json_retries} total attempts"
        )

    # ------------------------------------------------------------------
    # 公共辅助
    # ------------------------------------------------------------------

    @staticmethod
    def format_messages(
        system_prompt: str,
        user_message: str,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """将 system prompt + 历史 + 当前输入 组装为标准 messages 列表。

        Args:
            system_prompt: 角色人设 / 行为指令
            user_message:  玩家当前输入
            history:       可选，历史消息列表 [{"role": "user", "content": "..."},
                                               {"role": "assistant", "content": "..."}]

        Returns:
            标准 OpenAI messages 格式
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def close(self) -> None:
        """关闭 HTTP 连接。"""
        self._http.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 内部：HTTP + 重试
    # ------------------------------------------------------------------

    def _request_with_retry(self, payload: dict[str, Any]) -> str:
        """发送请求，带指数退避重试。

        - 网络错误 / 5xx → 重试
        - 429 (限流) → 读取 Retry-After，等待后重试
        - 4xx (非429) → 不重试，直接抛
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = self._http.post("/chat/completions", json=payload)
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = 2 ** attempt
                    time.sleep(delay)
                    continue
                raise

            # 成功
            if resp.status_code == 200:
                return _parse_chat_response(resp.json())

            # 限流
            if resp.status_code == 429:
                retry_after = _parse_retry_after(resp)
                if attempt < self.max_retries:
                    time.sleep(retry_after if retry_after > 0 else 2 ** attempt)
                    continue

            # 服务端错误 → 可重试
            if resp.status_code >= 500 and attempt < self.max_retries:
                delay = 2 ** attempt
                time.sleep(delay)
                continue

            # 不可重试的错误
            raise httpx.HTTPStatusError(
                f"LLM API error {resp.status_code}: {resp.text[:500]}",
                request=resp.request,
                response=resp,
            )

        # 重试耗尽
        assert last_error is not None
        raise last_error


# ---------------------------------------------------------------------------
# 内部：请求/响应处理
# ---------------------------------------------------------------------------

def _build_payload(
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
    response_format: str,
    extra_body: dict[str, Any] | None,
) -> dict[str, Any]:
    """构造 HTTP 请求体。"""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    # JSON 模式：在 payload 中声明 + 不传 response_format 参数给不支持的服务
    if response_format == "json_object":
        payload["response_format"] = {"type": "json_object"}
        # 确保 system/user prompt 中明确提到 JSON（API 要求）
        _ensure_json_instruction(messages)

    if extra_body:
        payload["extra_body"] = extra_body

    return payload


def _ensure_json_instruction(messages: list[dict[str, str]]) -> None:
    """确保 messages 中至少有一条提到了 'JSON'。

    OpenAI-compatible API 要求：使用 json_object 模式时，
    system 或 user 消息中必须出现 'JSON' 字样。
    """
    all_text = " ".join(m["content"] for m in messages if "content" in m)
    if "json" not in all_text.lower() and "JSON" not in all_text:
        # 在最后一条 user 消息末尾追加
        if messages and messages[-1]["role"] == "user":
            messages[-1]["content"] += "\n\n请以纯JSON格式回复，不要包含markdown代码块。"
        else:
            messages.append({
                "role": "user",
                "content": "请以纯JSON格式回复，不要包含markdown代码块。",
            })


def _parse_chat_response(body: dict[str, Any]) -> str:
    """从 Chat Completion 响应体中提取文本。"""
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(
            f"Failed to parse response body. "
            f"Expected choices[0].message.content. Got keys: {list(body.keys())}"
        ) from e


def _parse_retry_after(response: httpx.Response) -> float:
    """读取 Retry-After 头（秒）。"""
    raw = response.headers.get("Retry-After", "")
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 5.0  # 默认等 5 秒
