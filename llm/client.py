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
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import certifi
import httpx
from dotenv import load_dotenv

from contract.errors import err
from contract.json_cleaner import extract_json
from llm.task_labels import digest_label

logger = logging.getLogger(__name__)

#: reasoning_effort 合法档位（thinking level 参数, settings.toml [llm]）
_EFFORT_LEVELS = ("low", "medium", "high")

# Windows + conda SSL 证书修复
os.environ["SSL_CERT_FILE"] = certifi.where()

# 加载 .env
_project_root = Path(__file__).resolve().parents[1]
# 返回值不用（要的是 `load_dotenv` 把 .env 灌进 os.environ 这个**副作用**）; 名字保留是因为
# 它在 API 面快照里（`tests/fixtures/api_surface.txt`）——顺手可当"有没有找到 .env"的探针。
_load_dotenv_result = load_dotenv(_project_root / ".env")

#: settings.toml 位置（项目根——GUI 设置页存档; 非空字段优先于 .env）
_SETTINGS_PATH = _project_root / "settings.toml"


def _settings_toml() -> dict:
    """读项目根 settings.toml → dict（缺失/损坏 → {}, 不阻塞）。

    GUI 设置页保存的运行时配置（webgui/store.py 同源）。结构:
        [llm]   {api_key, base_url, model}
        [image] {api_key, base_url, model}
    """
    if not _SETTINGS_PATH.is_file():
        return {}
    try:
        import tomllib
        data = tomllib.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, ImportError):
        return {}


class LLMClient:
    """OpenAI-compatible Chat Completions 客户端。

    配置优先级: 构造参数 > settings.toml（GUI 设置页, 非空字段）> .env > 默认。
    从 settings.toml [llm] 读 api_key/base_url/model（空字段跳过 → .env 兜底）。

    思维链: self.last_reasoning = 最近一次 chat() 的 reasoning_content
    （DeepSeek reasoner/v4 系列返回; deepseek-chat 不返回 → None）。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 240.0,
        max_retries: int = 3,
    ):
        """OpenAI-compatible 客户端。

        默认 timeout 2026-09-07: 60 → 240s——reasoning(high) 生成长思考可 >60s,
        旧 60s 总超时会把正常慢调用砍掉 → ×3 重试 → 观感"卡死几分钟"。
        长任务（digest）可继续用 per-call timeout 覆盖（如 300s）。
        """
        cfg = _settings_toml().get("llm", {}) or {}
        self.api_key = (
            api_key or str(cfg.get("api_key") or "").strip()
            or os.getenv("LLM_API_KEY", "")
        )
        self.base_url = (
            base_url or str(cfg.get("base_url") or "").strip()
            or os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
        ).rstrip("/")
        self.model = (
            model or str(cfg.get("model") or "").strip()
            or os.getenv("LLM_MODEL", "deepseek-v4-flash")
        )
        self.timeout = timeout
        self.max_retries = max_retries
        self.last_reasoning: str | None = None   # 最近一次 chat 的思维链（无 → None）

        # thinking level（settings.toml [llm] reasoning_effort）: 全局默认档位——
        # extra_body=None 时注入; 显式传 {} 关闭（调用方局部覆盖）。非法值忽略+警告
        self.default_extra_body: dict[str, Any] = {}
        effort = str(cfg.get("reasoning_effort") or "").strip().lower()
        if effort in _EFFORT_LEVELS:
            self.default_extra_body = {"reasoning_effort": effort}
        elif effort:
            logger.warning("settings [llm] reasoning_effort 非法: %r（low|medium|high, 忽略）",
                           effort)

        if not self.api_key:
            raise ValueError(err(
                "ConfigError",
                "LLM_API_KEY not set. 请在 .env 中设置或通过 LLMClient(api_key=...) 传入",
            ))

        # 代理（2026-09-09 事故加固）: 默认 **不信任环境代理**（trust_env=False,
        # httpx 默认走 HTTP_PROXY/HTTPS_PROXY——本机曾因代理变量指向未监听的
        # 127.0.0.1:7897 → 全部请求 WinError 10061 连接拒绝, "之前从没出过"）。
        # 本项目 API 均为官方直连（实测可达）; 确需系统代理时 settings.toml
        # [llm] use_proxy = true 显式开启。
        use_proxy = str(cfg.get("use_proxy") or "").strip().lower() == "true"
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(self.timeout),
            trust_env=use_proxy,
        )

    def _resolve_extra(self, extra_body: dict[str, Any] | None) -> dict[str, Any]:
        """extra_body 解析: None → settings 默认档（default_extra_body）;
        显式 dict（含 {}）→ 原样（调用方局部覆盖/关闭）。"""
        return dict(self.default_extra_body) if extra_body is None else extra_body

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
        timeout: float | None = None,
        task: str | None = None,
    ) -> str | dict[str, Any]:
        """发送 chat completion 请求（批次模式）。

        思维链捕获（DeepSeek reasoner/v4 系列返回 reasoning_content）: 每次调用后
        self.last_reasoning = 最近一次响应的思考过程（无 → None）。模型无关——
        deepseek-chat 不返回则为 None。调用方（引擎 trace / CLI debug）可读。

        timeout: per-call 超时覆盖（None = 构造时的 self.timeout）。后台长任务
        （digest high 档长考可达 ~2min）用它放宽, 主对话快速失败语义不受影响。

        task: **调用身份**（`llm/task_labels.py` 的常量）——**不进 messages/payload**
        （前缀缓存零影响）, 只进日志 + 供测试桩分派（节点 5b, 2026-09-21）。
        """
        extra_body = self._resolve_extra(extra_body)   # None → settings 默认档
        effective_model = model or self.model

        payload = _build_payload(
            messages=messages,
            model=effective_model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            extra_body=extra_body,
        )
        # 计时埋点（EXEC_BOND_LATENCY §6.1）: 非流式 json 档记耗时（info 控噪）
        global _LAST_USAGE
        _LAST_USAGE = None
        _t0 = time.monotonic()
        raw_text = self._request_with_retry(payload, timeout=timeout)
        if response_format == "json_object":
            # 前缀缓存命中（DeepSeek usage.prompt_cache_hit_tokens; 无 → -1）
            # 2026-09-11 补 **输出侧** 用量: 此前只记 prompt 侧缓存指标, 判断
            # "一次调用写了多少字/单块还能加多长"只能靠记录条数间接估（记录流
            # 一章 ≈ 52 条 / ~1000 字, 但 completion_tokens 一直不可见）。
            _u = _LAST_USAGE or {}
            logger.info(
                "llm chat task=%s ms=%d json=y cache_hit=%d cache_miss=%d out=%d in=%d",
                task or "-",
                int((time.monotonic() - _t0) * 1000),
                int(_u.get("prompt_cache_hit_tokens") or -1),
                int(_u.get("prompt_cache_miss_tokens") or -1),
                int(_u.get("completion_tokens") or -1),
                int(_u.get("prompt_tokens") or -1))
        self.last_reasoning = _LAST_REASONING    # 模块级捕获 → 实例可读

        if response_format == "json_object":
            return self._extract_json_with_llm_correction(
                first_attempt=raw_text,
                messages=messages,
                model=effective_model,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra_body,
                timeout=timeout,
            )
        return raw_text

    def chat_full(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.8,
        max_tokens: int = 1024,
        response_format: str = "text",
        extra_body: dict[str, Any] | None = None,
        on_chunk: Callable[[str], None] | None = None,
        task: str | None = None,
    ) -> str | dict[str, Any]:
        """流式 chat completion — 收集完整文本, 返回与 chat 完全一致。

        与 chat 的区别只在传输: SSE 流式（token 逐块到达, on_chunk 每块增量
        回调——观察者/流式嗅探用）。json_object 时同样走 LLM 自纠错
        （_extract_json_with_llm_correction, 纠错阶段为非流式请求）。

        task: 调用身份, 同 `chat`（不进 payload, 只进日志/测试桩分派）。
        """
        extra_body = self._resolve_extra(extra_body)   # None → settings 默认档
        effective_model = model or self.model

        payload = _build_payload(
            messages=messages,
            model=effective_model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            extra_body=extra_body,
            stream=True,
            include_usage=True,     # 流式 usage（末 chunk）——前缀缓存命中统计用
        )
        # 计时埋点（EXEC_BOND_LATENCY §6.1）: 总耗时 + TTFT（首个 content chunk）
        global _LAST_USAGE
        _LAST_USAGE = None
        _t0 = time.monotonic()
        _ttft: list[float | None] = [None]
        _user_obs = on_chunk

        def _obs(c: str) -> None:
            if _ttft[0] is None:
                _ttft[0] = time.monotonic() - _t0
            if _user_obs is not None:
                _user_obs(c)

        raw_text = self._stream_collect(payload, on_chunk=_obs)
        _u = _LAST_USAGE or {}
        # out/in = 输出/输入 token（2026-09-11 补: 记录流一章 ≈ 52 条, 有了它才能
        # 量化"单块还能写多长 / 章长该不该拆"）
        logger.info(
            "llm chat_full task=%s ms=%d ttft=%dms json=%s cache_hit=%d cache_miss=%d out=%d in=%d",
            task or "-",
            int((time.monotonic() - _t0) * 1000),
            int(_ttft[0] * 1000) if _ttft[0] is not None else -1,
            "y" if response_format == "json_object" else "n",
            int(_u.get("prompt_cache_hit_tokens") or -1),
            int(_u.get("prompt_cache_miss_tokens") or -1),
            int(_u.get("completion_tokens") or -1),
            int(_u.get("prompt_tokens") or -1))
        self.last_reasoning = _LAST_REASONING    # 模块级捕获 → 实例可读

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
        response_format: str = "text",
    ):
        """流式 chat completion — yield 每个 token 的文本增量。

        用法:
            for chunk in client.chat_stream(messages):
                print(chunk, end="", flush=True)

        response_format: "text"（默认）/ "json_object"（同 chat——payload 带
        response_format, messages 自动补 JSON 指令）。
        """
        effective_model = model or self.model

        payload = _build_payload(
            messages=messages,
            model=effective_model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            extra_body=self.default_extra_body or None,   # 全局默认档
            stream=True,
        )

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

    def __enter__(self) -> LLMClient:
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
        timeout: float | None = None,
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
                raw_text = self._request_with_retry(payload, timeout=timeout)

        raise ValueError(err("JsonCorrection", f"JSON correction failed after {max_json_retries} total attempts"))

    # ------------------------------------------------------------------
    # 内部: HTTP
    # ------------------------------------------------------------------

    def _request_with_retry(self, payload: dict[str, Any],
                            timeout: float | None = None) -> str:
        """发送请求，带指数退避重试。

        timeout: per-call 覆盖（None = 构造超时 self.timeout）——后台长任务
        （digest）放宽; httpx per-request timeout 用 send(timeout=...) 覆盖。
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                # 2026-09-09 修复: httpx 0.28 的 Client.send 已无 timeout 参数
                # （旧 send(req, timeout=...) 抛 unexpected kwarg → digest 长期
                # 失败, wiki 永不产出）; per-request 超时统一走 post(timeout=)
                resp = self._http.post(
                    "/chat/completions", json=payload,
                    timeout=None if timeout is None
                    else httpx.Timeout(timeout))
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise

            kind, wait = _classify(resp, attempt, self.max_retries)
            if kind == "ok":
                return _parse_chat_response(resp.json())
            if kind == "retry":
                time.sleep(wait)
                continue
            _raise_transport(resp, auth=kind == "auth")

        assert last_error is not None
        raise last_error

    def _stream_collect(
        self,
        payload: dict[str, Any],
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        """流式请求（SSE）— 收集完整文本, 重试语义对齐 _request_with_retry。

        401/403 立即抛（配置错误, 重试无意义）; 429/5xx 指数退避; 超时退避。
        流式响应顺带捕获 reasoning_content（DeepSeek reasoner/v4 系列）。
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                with self._http.stream("POST", "/chat/completions", json=payload) as resp:
                    kind, wait = _classify(resp, attempt, self.max_retries)
                    if kind == "ok":
                        return self._drain_stream(resp, on_chunk)
                    if kind == "retry":
                        time.sleep(wait)
                        continue
                    _raise_transport(resp, auth=kind == "auth")
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise

        assert last_error is not None
        raise last_error

    @staticmethod
    def _drain_stream(
        resp: httpx.Response,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        """SSE 流式响应 → 完整文本（内容增量 + reasoning 增量 + usage 捕获）。"""
        global _LAST_REASONING, _LAST_USAGE
        buf: list[str] = []
        reasoning: list[str] = []
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue
            # usage（stream_options.include_usage 末 chunk; 无 choices 也读）
            usage = parsed.get("usage")
            if isinstance(usage, dict):
                _LAST_USAGE = usage
            try:
                delta = parsed["choices"][0].get("delta", {})
            except (KeyError, IndexError, TypeError):
                continue
            content = delta.get("content", "")
            if content:
                buf.append(content)
                if on_chunk is not None:
                    on_chunk(content)
            rc = delta.get("reasoning_content") or delta.get("reasoning")
            if rc:
                reasoning.append(rc)
        if reasoning:
            _LAST_REASONING = "".join(reasoning)
        return "".join(buf)


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
    stream: bool = False,
    include_usage: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }

    if response_format == "json_object":
        payload["response_format"] = {"type": "json_object"}
        _ensure_json_instruction(messages)

    if stream and include_usage:
        payload["stream_options"] = {"include_usage": True}

    if extra_body:
        payload.update(extra_body)   # 展开成顶层字段（此前误嵌套, 无调用点未暴露）

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


#: 最近一次响应的思维链（模块级——_parse_chat_response 设置, chat() 同步到实例）
_LAST_REASONING: str | None = None
#: 最近一次响应的 usage（DeepSeek: prompt_cache_hit_tokens/miss; None = 未返回）
_LAST_USAGE: dict | None = None


def _parse_chat_response(body: dict[str, Any]) -> str:
    global _LAST_REASONING, _LAST_USAGE
    try:
        _LAST_USAGE = body.get("usage") or None     # 前缀缓存命中统计用
        msg = body["choices"][0]["message"]
        # 思维链捕获: DeepSeek reasoner/v4 系列返回 reasoning_content（chat 无 → 清空）
        _LAST_REASONING = msg.get("reasoning_content") or None
        return msg.get("content", "")
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


def _classify(resp: httpx.Response, attempt: int, max_retries: int) -> tuple[str, float]:
    """传输级重试的**唯一判据** → `(kind, wait_seconds)`。

    kind ∈ `ok`（200, 直接消费）/ `auth`（401·403, 配置错误, 重试无意义）/
    `retry`（429 或 ≥500, 等 wait 秒再来）/ `fatal`（其余, 抛 API 错误）。

    `_request_with_retry` 与 `_stream_collect` 原先各抄了一份同样的阶梯（连两条
    错误消息都逐字重复），这里收成一处。⚠️ 超时是**异常**路径, 不在此列 ——
    两边各自 `2 ** attempt` 退避（只有一行, 不值得为它绕一圈）。
    """
    if resp.status_code == 200:
        return "ok", 0.0
    if resp.status_code in (401, 403):
        # 假 key / key 失效时玩家该秒得感叹号, 不该 6 步 × 指数退避转圈 1~2 分钟
        return "auth", 0.0
    if attempt >= max_retries:
        return "fatal", 0.0
    if resp.status_code == 429:
        wait = _parse_retry_after(resp)
        return "retry", wait if wait > 0 else 2 ** attempt
    if resp.status_code >= 500:
        return "retry", 2 ** attempt
    return "fatal", 0.0


def _raise_transport(resp: httpx.Response, *, auth: bool) -> NoReturn:
    """两条传输错误消息的唯一出处（401/403 = 配置错误, 其余 = API 错误）。"""
    if auth:
        raise httpx.HTTPStatusError(
            err("LLMAuth", f"API 认证失败 {resp.status_code}: {resp.text[:200]}"),
            request=resp.request,
            response=resp,
        )
    raise httpx.HTTPStatusError(
        err("LLMAPI", f"LLM API error {resp.status_code}: {resp.text[:500]}"),
        request=resp.request,
        response=resp,
    )


def feedback(
    messages: list[dict],
    reason: str | Exception,
    guidance: str = "",
) -> None:
    """错误/结果回灌给 LLM 的公共助手 — 追加一条 user 修正指令。

    fetch IDE loop 与 MMT/Story loop 共用。所有域的回灌统一走这一个函数:
    消息体由调用方构造（带域内措辞/指引）, 本函数只负责把它作为 user 角色
    追加进 messages, 并留出 guidance 附言约定——避免每个域手写
    messages.append({"role": "user", "content": ...}) 的三四行样板。

    注意 web/mock.py 依赖部分回灌消息的原文（如 "动作已执行" 前缀、
    "用户拒绝" 子串）——调用方必须保留既有措辞, 别在这里统一改写。

    Args:
        messages: OpenAI 风格历史 [{role, content}, ...], 原地追加。
        reason:   回灌正文。Exception（str() 后得到 [file][Class][msg]）、
                  '; '.join(errors)（parse 级）或任意提示文本——调用方自带
                  域内措辞前缀（如 '无法执行: '）。
        guidance: 可选, 追加在正文下一行的修正提示（schema 要点 / 建议）。
    """
    content = str(reason)
    if guidance:
        content = f"{content}\n{guidance}"
    messages.append({"role": "user", "content": content})


# ---------------------------------------------------------------------------
# 结构化调用（一次调用发得稳）—— 2026-10-13 从 `core/digest/llm_call.py` 搬到这儿
# ---------------------------------------------------------------------------

#: 调用重试上限（偶发空响应/坏 JSON; 耗尽 → 降级; deadline 优先于次数）
MAX_CALL_RETRIES = 3


def llm_chat(
    llm,
    system: str,
    user_msg: str,
    *,
    messages: list[dict] | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    extra_body: dict | None = None,
    deadline: float | None = None,
    max_retries: int = MAX_CALL_RETRIES,
    timeout: float | None = None,
    label: str = "digest",
) -> tuple[dict | None, str | None]:
    """单次结构化调用（json_object）: 重试 N 次或撞 deadline。

    ⚠️ **它是"策略件", 不是 `LLMClient` 的方法**（2026-10-13 用户裁"搬进 client.py"时
    一并议定）: `llm` 是**鸭子类型**的（任何有 `.chat()` 的东西）——
    digest 那一族的测试桩只实现 `.chat()`（80 个桩 / 41 个文件里绝大多数如此），
    而"重试几次 / deadline 怎么算 / 档位怎么透传"是**引擎策略**:
    挂到具体类上, 桩就得**复刻策略**, 那 130 处用例就不再验真策略了。
    同形状的还有 `llm/retry.py::call_with_feedback`（也是模块级 + 鸭子类型）。

    Args:
        messages: 完整消息列表（反馈回灌用——同一上下文续调: 编排层追加
                  assistant 被拒输出 + 引擎错误后传入; None → 由 system+user 组装）
        llm: 兼容 llm.chat(messages, model=, temperature=, max_tokens=,
             response_format=, extra_body=) 的客户端
        deadline: time.monotonic() 绝对截止时刻; None = 不限
        timeout: per-call 超时覆盖（后台长考放宽; None = 客户端构造超时）
        label: 日志上下文（digest / record / understand … 即轮次 key）

    Returns:
        (resp, None): 成功, resp = 解析后的 dict
        (None, err_str): 重试耗尽 / 撞 deadline
    """
    if messages is None:
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user_msg}]
    if max_tokens is None:                       # 真源: task_levels 形态 digest
        from llm.task_levels import max_tokens as _tl_mt
        max_tokens = _tl_mt("digest")
    last_err: Exception | None = None
    for attempt in range(max_retries):
        if deadline is not None and time.monotonic() >= deadline:
            # `>=` 而非 `>`: Windows 的 monotonic() 粒度约 15.6ms，deadline 恰好落在
            # 当前 tick 时 `>` 恒为 False ⇒ 0 秒预算等于没有预检，调用照发。
            return None, "LLM 调用撞上时间预算"
        try:
            resp = llm.chat(
                list(messages),
                model=model, temperature=temperature, max_tokens=max_tokens,
                response_format="json_object", extra_body=extra_body, timeout=timeout,
                # 调用身份（节点 5b）: label 已有（digest / record / understand …）,
                # 直接映射成 task 标签——测试桩据此分 A/B 轮, 不再认中文关键字
                task=digest_label(label))
            return resp, None
        except Exception as e:                       # noqa: BLE001
            last_err = e
            logger.warning(err("DigestFailed",
                               f"{label} LLM 调用失败（第 {attempt + 1}/{max_retries} 次）: {e}"))
    return None, f"LLM 调用重试耗尽: {last_err}"
