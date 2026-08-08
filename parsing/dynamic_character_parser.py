"""
动态角色解析器 — 约定驱动，零硬编码。

约定章程（profile.yml 头部注释）:
    REQ~  = 必填（Required）  — 缺失则警告/拒绝
    SIG~  = 重要（Significant）— 计入信息完整度
    无前缀 = 普通字段         — 透传，可选，不校检

核心行为:
    1. 读取 YAML → 保留原始嵌套结构
    2. 扫描所有 key → 按前缀分类（REQ~/SIG~/普通）
    3. 透传渲染为 LLM Prompt 文本 → 不逐字段映射
    4. null 值 = 合法占位符 → 跳过

用法:
    from parsing.dynamic_character_parser import load_character, yaml_to_prompt

    char_data = load_character("config/characters/igusa_haruka/profile.yml")
    prompt = yaml_to_prompt(char_data)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ============================================================================
# 前缀常量
# ============================================================================

PREFIX_REQ = "REQ~"
PREFIX_SIG = "SIG~"

# ============================================================================
# 载入
# ============================================================================


def load_character(profile_path: str | Path) -> dict[str, Any]:
    """读取角色 profile.yml，返回原始 dict（保留嵌套结构）。

    Raises:
        FileNotFoundError: 文件不存在
        yaml.YAMLError: YAML 语法错误
    """
    path = Path(profile_path)
    if not path.exists():
        raise FileNotFoundError(f"角色档案不存在: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise ValueError(f"{path.name} 内容不是有效 YAML dict")

    return data


# ===========================================================================
# 字段分类
# ===========================================================================


def classify_fields(data: dict[str, Any]) -> dict[str, Any]:
    """遍历 YAML dict（递归），按前缀分类所有叶子字段。

    Returns:
        {
            "req":  {"字段名": 值, ...},    # REQ~ 前缀
            "sig":  {"字段名": 值, ...},    # SIG~ 前缀
            "info": {"字段名": 值, ...},    # 无前缀
            "all":  {"字段名": 值, ...},    # 全部（含前缀剥离后的干净键名）
        }
    """
    result: dict[str, dict[str, Any]] = {
        "req": {},
        "sig": {},
        "info": {},
        "all": {},
    }
    _walk(data, result, prefix="")
    return result


def _walk(node: Any, result: dict, prefix: str) -> None:
    """递归遍历 YAML 树。"""
    if isinstance(node, dict):
        for raw_key, value in node.items():
            # 跳过 null 值
            if value is None:
                continue

            # 剥离前缀
            clean_key, tag = _strip_prefix(raw_key)

            # 全路径键名
            full_key = f"{prefix}.{clean_key}" if prefix else clean_key

            if tag and isinstance(value, (str, int, float, bool)):
                # 叶子节点：有前缀的标量 → 直接归类
                result["all"][full_key] = value
                if tag == "req":
                    result["req"][full_key] = value
                elif tag == "sig":
                    result["sig"][full_key] = value
            elif tag and isinstance(value, (list, dict)):
                # 有前缀的嵌套 → 前缀只作用于本节点，归类后继续递归
                result["all"][full_key] = value
                if tag == "req":
                    result["req"][full_key] = value
                elif tag == "sig":
                    result["sig"][full_key] = value
                _walk(value, result, full_key)
            elif isinstance(value, (str, int, float, bool)):
                # 无前缀的叶子
                result["all"][full_key] = value
                result["info"][full_key] = value
            else:
                # 无前缀的嵌套 → 继续递归
                result["all"][full_key] = value
                _walk(value, result, full_key)

    elif isinstance(node, list):
        for i, item in enumerate(node):
            child_prefix = f"{prefix}[{i}]"
            _walk(item, result, child_prefix)


def _strip_prefix(raw_key: str) -> tuple[str, str]:
    """剥离 REQ~ / SIG~ 前缀。

    Returns:
        (clean_key, tag)  其中 tag 为 "req" / "sig" / ""
    """
    if raw_key.startswith(PREFIX_REQ):
        return raw_key[len(PREFIX_REQ):], "req"
    if raw_key.startswith(PREFIX_SIG):
        return raw_key[len(PREFIX_SIG):], "sig"
    return raw_key, ""


# ===========================================================================
# 校检
# ===========================================================================


def check_required(data: dict[str, Any]) -> list[str]:
    """检查所有 REQ~ 前缀字段是否非空。

    Returns:
        缺失/为空的字段名列表。空列表 = 全部通过。
    """
    classified = classify_fields(data)
    missing = []
    for name, value in classified["req"].items():
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(name)
    return missing


def get_completeness(data: dict[str, Any]) -> dict[str, Any]:
    """计算信息完整度。

    Returns:
        {
            "score": int,             # 非空 SIG~ 字段数
            "total_sig": int,         # SIG~ 字段总数
            "ratio": float,           # 比例
            "missing_sig": [str],     # 空值的 SIG 字段
            "missing_req": [str],     # 空值的 REQ 字段
        }
    """
    classified = classify_fields(data)

    total_sig = len(classified["sig"])
    filled = sum(
        1 for v in classified["sig"].values()
        if v is not None and (not isinstance(v, str) or v.strip())
    )
    missing_sig = [
        k for k, v in classified["sig"].items()
        if v is None or (isinstance(v, str) and not v.strip())
    ]
    missing_req = [
        k for k, v in classified["req"].items()
        if v is None or (isinstance(v, str) and not v.strip())
    ]

    return {
        "score": filled,
        "total_sig": total_sig,
        "ratio": filled / total_sig if total_sig > 0 else 1.0,
        "missing_sig": missing_sig,
        "missing_req": missing_req,
    }


# ===========================================================================
# 透传渲染 → LLM Prompt
# ===========================================================================


def yaml_to_prompt(data: dict[str, Any], title: str = "角色设定") -> str:
    """将 YAML dict 渲染为 LLM 可读的结构化文本。

    规则:
        - 剥离 REQ~ / SIG~ 前缀后显示
        - null → 跳过
        - 嵌套 dict → 缩进展开
        - 列表 → 用 - 展开
        - 多行字符串 → 保留换行

    Args:
        data: YAML 原始 dict
        title: 顶层标题

    Returns:
        可直接注入 System Prompt 的 Markdown 文本
    """
    lines = [f"# {title}", ""]
    _render_node(data, lines, indent=0)
    return "\n".join(lines)


def _render_node(node: Any, lines: list[str], indent: int) -> None:
    """递归渲染节点。"""
    prefix_space = "  " * indent

    if isinstance(node, dict):
        for raw_key, value in node.items():
            if value is None:
                continue

            clean_key, _tag = _strip_prefix(raw_key)
            display_key = clean_key.replace("_", " ")

            if isinstance(value, (str, int, float, bool)):
                # 叶子 → 单行
                text = str(value).strip()
                if text:
                    # 多行文本按换行展开
                    text_lines = text.split("\n")
                    if len(text_lines) > 1:
                        lines.append(f"{prefix_space}**{display_key}**:")
                        for tl in text_lines:
                            lines.append(f"{prefix_space}  {tl.strip()}")
                    else:
                        lines.append(
                            f"{prefix_space}- **{display_key}**: {text_lines[0]}"
                        )
            elif isinstance(value, list):
                # 列表 → 展开子项
                lines.append(f"{prefix_space}- **{display_key}**:")
                for item in value:
                    if isinstance(item, dict):
                        _render_node(item, lines, indent + 1)
                    elif isinstance(item, str):
                        item_text = item.strip()
                        if item_text:
                            lines.append(f"{prefix_space}  - {item_text}")
                    elif item is not None:
                        lines.append(f"{prefix_space}  - {item}")
            elif isinstance(value, dict):
                # 嵌套 dict → 递归
                lines.append(f"{prefix_space}- **{display_key}**:")
                _render_node(value, lines, indent + 1)

    elif isinstance(node, list):
        for item in node:
            if isinstance(item, dict):
                _render_node(item, lines, indent)
            elif isinstance(item, str) and item.strip():
                lines.append(f"{prefix_space}- {item.strip()}")
            elif item is not None:
                lines.append(f"{prefix_space}- {item}")

    elif isinstance(node, str):
        text = node.strip()
        if text:
            lines.append(f"{prefix_space}{text}")
