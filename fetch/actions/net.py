"""网络与收尾动作 — fetch_url / done。

都是 APPROVAL_NEVER（只读/收尾），契约层只校验请求结构；
抓取（httpx + html.parser）与结果回灌是执行层职责。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from contract import ContractError

from fetch.actions.common import MAX_FETCH_CHARS


def _is_http_url(url: str) -> bool:
    """校验 http/https 完整 URL（有 netloc）。"""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


# ============================================================================
# fetch_url — 抓取网页（只读工具, 结果回灌 LLM）
# ============================================================================

def parse_fetch_url(payload: dict[str, Any]) -> dict[str, Any]:
    """结构校验（硬错误, 抛 ContractError）。"""
    url = payload.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ContractError("url 必须是非空字符串")
    url = url.strip()
    if not _is_http_url(url):
        raise ContractError(f"url 必须是合法的 http/https 地址: {url!r}")

    clean: dict[str, Any] = {"url": url}

    max_chars = payload.get("max_chars")
    if max_chars is not None:
        if isinstance(max_chars, bool) or not isinstance(max_chars, int):
            raise ContractError("max_chars 必须是正整数")
        if not 1 <= max_chars <= MAX_FETCH_CHARS:
            raise ContractError(f"max_chars 必须在 1-{MAX_FETCH_CHARS} 之间")
        clean["max_chars"] = max_chars

    return clean


# ============================================================================
# done — 收尾（LLM 声明本轮结束 / 等待用户）
# ============================================================================

def parse_done(payload: dict[str, Any]) -> dict[str, Any]:
    """收尾动作：几乎无 payload, 允许可选 message 补充说明。"""
    clean: dict[str, Any] = {}
    msg = payload.get("message")
    if msg is not None:
        if not isinstance(msg, str) or not msg.strip():
            raise ContractError("message 必须是非空字符串")
        clean["message"] = msg.strip()
    return clean
