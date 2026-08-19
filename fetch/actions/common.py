"""动作域共享层 — 常量 + per-file 校验器 + files 白名单。

被 actions/ 下各动作模块（character / interperson / net）引用。
本文件不含任何具体动作——只有跨动作复用的"零件"。
"""

from __future__ import annotations

from typing import Any

import yaml

from contract import RUNTIME_SHELL_FIELDS, ContractError, ValidationResult

from fetch.conflicts import find_top_level_conflicts, format_conflicts

# 角色五件套（与主项目 parsing.dynamic_character_parser._CHARACTER_FILES 对齐）
CHARACTER_FILES = (
    "profile.yml",
    "personality.yml",
    "knowledge.yml",
    "experience.yml",
    "typical.yml",
)
CHARACTER_FILE_SET = frozenset(CHARACTER_FILES)

# update 模式
MODE_MERGE = "merge"
MODE_OVERWRITE = "overwrite"
UPDATE_MODES = frozenset({MODE_MERGE, MODE_OVERWRITE})

# 抓取文本长度上限（防超长响应撑爆上下文）
MAX_FETCH_CHARS = 50000

# IDE 只读/收尾动作的外壳字段：运行时最小集 + reply（AI 对用户的话）
IDE_RUNTIME_FIELDS = RUNTIME_SHELL_FIELDS | frozenset({"reply"})


# ============================================================================
# 文件类型校验器（per-file validator）
# ============================================================================

def _validate_profile(yml: dict, payload: dict, errors: list[str], warnings: list[str], require_complete: bool) -> None:
    """profile.yml 内容校验 + 提取显示名。

    require_complete=True（create / overwrite）时:
        - 强制 REQ~most_called_name——它是主项目 get_display_name 的
          **代码级依赖**（列表/会话名显示必需），故比其他 REQ~ 字段严格。
          其余 REQ~ 字段无法在此检测缺失：约定驱动下没有固定字段清单
          （加字段 = 改 YAML 零代码），"没写的字段"不在 dict 里、无法枚举。
        - 提取显示名写回 payload（单一真源在 profile.yml）。
    require_complete=False（merge 补丁）时:
        只验证提交的字段本身——完整性由执行层合并后检查。
    """
    if not require_complete:
        return

    name = yml.get("REQ~most_called_name", "")
    if not isinstance(name, str) or not name.strip():
        errors.append(
            "profile.yml 必须包含非空 REQ~most_called_name（界面显示名）——"
            "REQ~ 是必填键的前缀字面量，直接写 `REQ~most_called_name: 名字` 到 profile.yml；"
            "该键是主项目显示名（get_display_name）的代码级依赖，缺失会致角色加载失败"
        )
    else:
        payload["display_name"] = name.strip()


def _validate_pending(yml: dict, payload: dict, errors: list[str], warnings: list[str], require_complete: bool) -> None:
    """未实现的文件类型校验器占位（personality/knowledge/experience/typical）。

    TODO(后续): 各文件类型的结构校验——行为逻辑层、独有知识库、预设经历、
    校准样本。当前只覆盖 profile。
    """
    # 占位：显式忽略参数，保持与分派表签名一致
    del yml, payload, errors, warnings, require_complete


# 文件类型 → 校验器分派表
_FILE_VALIDATORS = {
    "profile.yml": _validate_profile,
    "personality.yml": _validate_pending,
    "knowledge.yml": _validate_pending,
    "experience.yml": _validate_pending,
    "typical.yml": _validate_pending,
}


# ============================================================================
# 共享：files 结构白名单
# ============================================================================

def _parse_files(files: Any, *, require_nonempty: bool) -> dict[str, str]:
    """files 结构白名单校验（硬错误）。返回 {文件名: YAML 文本}。"""
    if not isinstance(files, dict):
        raise ContractError("files 必须是对象（{文件名: YAML 文本}）")
    if require_nonempty and not files:
        raise ContractError("至少需要提供一个文件")

    clean: dict[str, str] = {}
    for name, content in files.items():
        if name not in CHARACTER_FILE_SET:
            raise ContractError(
                f"未知文件: {name!r}（允许: {', '.join(CHARACTER_FILES)}）"
            )
        if not isinstance(content, str) or not content.strip():
            raise ContractError(f"{name} 必须是非空 YAML 文本")
        clean[name] = content
    return clean


def _validate_files_content(payload: dict, require_complete: bool) -> ValidationResult:
    """共享内容校验：解析每个文件的 YAML → 跨文件键冲突检测 → per-file 校验。"""
    errors: list[str] = []
    warnings: list[str] = []

    # 1. 解析全部文件（同时收集顶层 key 供跨文件检测）
    parsed: dict[str, dict] = {}
    for name, content in payload["files"].items():
        try:
            yml = yaml.safe_load(content)
        except yaml.YAMLError as e:
            errors.append(f"{name} YAML 解析失败: {e}")
            continue

        if not isinstance(yml, dict):
            errors.append(f"{name} 必须解析为对象（dict），不能是 null/空/列表")
            continue
        parsed[name] = yml

    # 2. 跨文件键冲突检测（A3）：主项目先加载优先（profile 赢）, 重复 → warning
    warnings.extend(format_conflicts(find_top_level_conflicts(parsed)))

    # 3. per-file 校验器
    for name, yml in parsed.items():
        _FILE_VALIDATORS[name](yml, payload, errors, warnings, require_complete)

    return ValidationResult(tuple(errors), tuple(warnings))
