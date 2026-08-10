"""JSON 清洗管道 — 从 LLM 返回文本中提取并解析 JSON。

LLM 不听话的常见表现:
    - markdown 包裹  (```json ... ```)
    - 前后废话       ("好的，这是你要的JSON：{...}")
    - 尾部多余逗号   ({"a": 1,})
    - 单行 // 注释
    - 嵌套字符串引号  (极少数情况)

本模块的 extract_json() 用分层管道处理上述情况。

用法:
    from llm.json_cleaner import extract_json
    data = extract_json(llm_response_text)
"""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json(response_text: str) -> dict[str, Any]:
    """完整的 JSON 提取管道。

    Args:
        response_text: LLM 返回的原始文本。

    Returns:
        解析成功的 dict。

    Raises:
        ValueError: 所有清洗手段用尽后仍无法解析。
    """
    errors: list[str] = []
    original = response_text

    cleaned = _strip_markdown_fence(response_text)
    cleaned = _extract_json_substring(cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        errors.append(f"clean parse: {e}")

    repaired = _repair_common_json_errors(cleaned)
    if repaired != cleaned:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e:
            errors.append(f"repaired parse: {e}")

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
# 内部
# ---------------------------------------------------------------------------

def _strip_markdown_fence(text: str) -> str:
    """移除 ```json ... ``` 包裹。"""
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        else:
            text = text[3:]
        text = text[: text.rfind("```")].strip()
    return text


def _extract_json_substring(text: str) -> str:
    """找到第一个 { 到最后一个 } 的区间。"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return text
    return text[start:end + 1]


def _repair_common_json_errors(text: str) -> str:
    """修复常见 JSON 语法错误。"""
    text = re.sub(r",\s*(\}|\])", r"\1", text)   # 尾部逗号
    text = re.sub(r"//[^\n]*", "", text)         # 单行注释
    return text
