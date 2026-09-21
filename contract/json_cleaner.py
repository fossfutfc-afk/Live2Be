"""JSON 清洗管道 — 从 LLM 返回文本中提取并解析 JSON。

⚠️ **位置**（C10, `docs/EXEC_SPLIT.md`）: 纯 JSON 修复、无传输/无网络 ⇒ 归 `contract/`
（此前住在 `llm/`，害得 `contract/registry.py` 反向依赖 `llm`）。

LLM 不听话的常见表现:
    - markdown 包裹  (```json ... ```)
    - 前后废话       ("好的，这是你要的JSON：{...}")
    - 尾部多余逗号   ({"a": 1,})
    - 单行 // 注释
    - 嵌套字符串引号  (极少数情况)

本模块的 extract_json() 用分层管道处理上述情况。

用法:
    from contract.json_cleaner import extract_json
    data = extract_json(llm_response_text)
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from contract.errors import err


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

    # LLM 偶发输出 Python dict 字面量（单引号键/值、True/False/None）——json.loads 只认双引号。
    # ast.literal_eval 只解析字面量、不执行代码（安全）。Python 单引号串不能含裸换行,
    # 所以对每个候选再试一次"把字符串内裸换行转义为 \n"的版本。
    candidates = []
    for c in (cleaned, repaired):
        candidates.append(c)
        escaped = _escape_newlines_in_strings(c)
        if escaped != c:
            candidates.append(escaped)
    for candidate in dict.fromkeys(candidates):  # 去重保序
        try:
            value = ast.literal_eval(candidate)
        except (SyntaxError, ValueError) as e:
            errors.append(f"literal_eval: {e}")
            continue
        if isinstance(value, dict):
            return value
        errors.append(f"literal_eval: 顶层非 dict ({type(value).__name__})")

    raise ValueError(err(
        "JsonExtract",
        f"JSON extraction failed after {len(errors)} attempts.\n"
        f"--- raw response (first 500 chars) ---\n"
        f"{original[:500]}\n"
        f"--- cleaned (first 500 chars) ---\n"
        f"{cleaned[:500]}\n"
        f"--- errors ---\n"
        f"{chr(10).join(errors)}",
    ))


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


def _escape_newlines_in_strings(text: str) -> str:
    """把字符串字面量内部的裸换行转义为 \\n（Python 单引号/双引号串不允许裸换行）。

    LLM 输出 Python dict 时可能把多行内容直接写在 '...' 里（如 experience.yml 的多段文本），
    ast.literal_eval 会报 unterminated string literal。本函数用引号状态机定位字符串内部,
    只转义字符串内的换行, 不碰结构空白（如逗号/冒号后的换行）。
    """
    out: list[str] = []
    quote: str | None = None     # "'" / '"' / None
    escaped = False
    for ch in text:
        if quote:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                out.append(ch)
                escaped = True
            elif ch == quote:
                out.append(ch)
                quote = None
            elif ch == "\n":
                out.append("\\n")          # 裸换行 → 转义
            else:
                out.append(ch)
        else:
            if ch in ("'", '"'):
                quote = ch
            out.append(ch)
    return "".join(out)
