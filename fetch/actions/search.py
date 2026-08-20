"""搜索动作 — search（只读工具, 结果回灌 LLM）。

与 fetch_url 互补: fetch_url 需要**已知 URL**, search 从关键词出发**找 URL**。
AI 查资料流程: search 定位资料页 → fetch_url 抓取正文。

后端: MediaWiki opensearch API（`/api.php?action=opensearch`）, 无 key、稳定。
默认搜萌娘百科; `source` 也可传任意 MediaWiki 站点 base URL（如 kivo/fandom）。
"""

from __future__ import annotations

from typing import Any

from contract import ContractError

from fetch.actions.net import _is_http_url

# 已知资料站别名 → MediaWiki base URL（单一真源, 执行层也引用）。
# kivo / fandom 的稳定 URL 待确认后再补别名; 现在可直接传完整 base URL 作 source。
WIKI_ALIASES = {
    "moegirl": "https://zh.moegirl.org.cn",
}

DEFAULT_MAX_RESULTS = 5
MAX_RESULTS_LIMIT = 10

# AI 一次 search 最多提交的候选词数（新角色自动索引覆盖不到时用）
MAX_ALIASES = 5


def parse_search(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。"""
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ContractError("query 必须是非空字符串")
    query = query.strip()

    clean: dict[str, Any] = {"query": query}

    source = payload.get("source", "moegirl")
    if not isinstance(source, str) or not source.strip():
        raise ContractError("source 必须是非空字符串")
    source = source.strip()
    if source not in WIKI_ALIASES and not _is_http_url(source):
        raise ContractError(
            f"source 必须是已知别名 {sorted(WIKI_ALIASES)} "
            f"或合法的 http(s) MediaWiki base URL: {source!r}"
        )
    clean["source"] = source

    aliases = payload.get("aliases")
    if aliases:
        if not isinstance(aliases, list) or not all(
            isinstance(a, str) and a.strip() for a in aliases
        ):
            raise ContractError("aliases 必须是字符串数组, 每一项非空")
        cleaned_aliases = [a.strip() for a in aliases]
        if len(cleaned_aliases) > MAX_ALIASES:
            raise ContractError(f"aliases 最多 {MAX_ALIASES} 个候选词")
        clean["aliases"] = cleaned_aliases

    max_results = payload.get("max_results", DEFAULT_MAX_RESULTS)
    if isinstance(max_results, bool) or not isinstance(max_results, int):
        raise ContractError("max_results 必须是正整数")
    if not 1 <= max_results <= MAX_RESULTS_LIMIT:
        raise ContractError(f"max_results 必须在 1-{MAX_RESULTS_LIMIT} 之间")
    clean["max_results"] = max_results

    return clean
