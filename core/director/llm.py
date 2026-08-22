# -*- coding: utf-8 -*-
"""导演 LLM 薄封装 — 本地小模型（Qwen2.5-7B 等, LM Studio localhost:1234/v1）。

职责:
    - 构造 OpenAI-compatible 客户端（本地 endpoint, 覆盖 .env 的远端默认）
    - suggest(prompt) → DirectorSuggestion{sprite?, background?}
    - 任何失败（网络 / 非法输出）→ 抛 DirectorLLMError（上层宁缺勿错降级）

与主 LLM 的区别: 导演是封闭词表分类式输出, 输入数百 token, 本地跑便宜,
失败绝不进主 LLM retry 循环（DESIGN_VISUAL §4）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.common import Live2BeError
from llm.client import LLMClient

logger = logging.getLogger(__name__)

# 本地导演 LLM 默认（与 .env 注释里的本地信息一致; 构造可覆盖）
_DEFAULT_BASE_URL = "http://localhost:1234/v1"
_DEFAULT_API_KEY = "lm-studio"
_DEFAULT_MODEL = "qwen2.5-7b-instruct"


class DirectorLLMError(Live2BeError):
    """导演 LLM 不可用或输出非法（上层捕获 → 降级正则/保持/默认, 不阻断 VN）。"""


@dataclass(frozen=True)
class DirectorSuggestion:
    """导演输出建议（闭包词表, 可省略字段 = None 表示"未给/保持"）。

    sprite    — 表情（合法值由上层用 catalog 白名单校验）
    background — scene_id / 目录名 / keep / null（语义校验在上层）
    """

    sprite: str | None = None
    background: str | None = None


class DirectorLLM:
    """导演 LLM 薄封装（本地 Qwen2.5-7B）。"""

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        api_key: str = _DEFAULT_API_KEY,
        model: str = _DEFAULT_MODEL,
        timeout: float = 15.0,
        max_retries: int = 1,
    ) -> None:
        self.model = model
        self._client = LLMClient(
            api_key=api_key, base_url=base_url, model=model,
            timeout=timeout, max_retries=max_retries,
        )

    def suggest(self, prompt: str) -> DirectorSuggestion:
        """单次导演调用: prompt → {sprite?, background?}。

        Raises:
            DirectorLLMError: 网络/API 失败或输出无法解析为合法 JSON（上层降级）。
        """
        messages = [
            {"role": "system", "content": "你是羁绊剧情视觉导演，严格按指令输出纯 JSON。"},
            {"role": "user", "content": prompt},
        ]
        try:
            raw = self._client.chat(
                messages,
                temperature=0.3,
                max_tokens=128,
                response_format="json_object",
            )
        except Exception as e:  # 网络 / 解析修正失败 → 统一降级
            raise DirectorLLMError(f"导演 LLM 调用失败: {e}") from e

        if not isinstance(raw, dict):
            raise DirectorLLMError(f"导演输出非对象: {type(raw).__name__}")

        sprite = raw.get("sprite")
        background = raw.get("background")
        # 宁缺勿错: 非 str 字段 → None（上层走保持/降级）
        return DirectorSuggestion(
            sprite=sprite if isinstance(sprite, str) else None,
            background=background if isinstance(background, str) else None,
        )

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # 关闭失败不影响调用方
            pass
