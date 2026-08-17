"""角色动作 — create_character / update_character。

结构白名单在 parse（硬错误, 抛 ContractError）；内容校验委托给共享的
_validate_files_content（软拒绝, ValidationResult）。
"""

from __future__ import annotations

from typing import Any

from contract import ContractError, ValidationResult, is_valid_identifier

from fetch.actions.common import (
    MODE_MERGE,
    MODE_OVERWRITE,
    UPDATE_MODES,
    _parse_files,
    _validate_files_content,
)


# ============================================================================
# create_character — 新建角色目录
# ============================================================================

def parse_create_character(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。

    只做结构层：不解析 YAML、不访问文件系统。
    """
    char_id = payload.get("character_id")
    if not is_valid_identifier(char_id):
        raise ContractError(
            f"character_id 必须匹配 [a-z0-9_]+ 且 ≤64 字符: {char_id!r}"
        )

    files = _parse_files(payload.get("files"), require_nonempty=True)
    if "profile.yml" not in files:
        raise ContractError("create_character 至少需要 profile.yml")

    return {
        "character_id": char_id,
        "files": files,
    }


def validate_create_character(payload: dict[str, Any]) -> ValidationResult:
    """内容软校验：新文件即最终形态 → require_complete=True。"""
    return _validate_files_content(payload, require_complete=True)


# ============================================================================
# update_character — 改已有角色
# ============================================================================

def parse_update_character(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。"""
    char_id = payload.get("character_id")
    if not is_valid_identifier(char_id):
        raise ContractError(
            f"character_id 必须匹配 [a-z0-9_]+ 且 ≤64 字符: {char_id!r}"
        )

    mode = payload.get("mode", MODE_OVERWRITE)
    if mode not in UPDATE_MODES:
        raise ContractError(f"mode 必须是 {MODE_MERGE} 或 {MODE_OVERWRITE}: {mode!r}")

    files = _parse_files(payload.get("files"), require_nonempty=True)

    return {
        "character_id": char_id,
        "mode": mode,
        "files": files,
    }


def validate_update_character(payload: dict[str, Any]) -> ValidationResult:
    """内容软校验。

    overwrite → 提交的是完整文件, 完整检查（require_complete=True）；
    merge     → 提交的是补丁, 只验证提交的字段（require_complete=False），
                最终完整性由执行层合并现有文件后检查。
    """
    require_complete = payload["mode"] == MODE_OVERWRITE
    return _validate_files_content(payload, require_complete=require_complete)
