"""人际关系动作 — update_interperson（全量快照 + 角色粒度替换）。

新增关系的依据硬校验（宁缺勿错）不在此处——它需要读现有 interperson.json
对比出"新增"关系，属于执行层职责。契约层只做结构 + 不依赖文件系统的软检查。
"""

from __future__ import annotations

from typing import Any

from contract import ContractError, ValidationResult, is_valid_identifier


def parse_update_interperson(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。

    只做结构层：不访问文件系统——"哪些关系是新增"由执行层对比现有文件判断。
    """
    char_id = payload.get("character_id")
    if not is_valid_identifier(char_id):
        raise ContractError(
            f"character_id 必须匹配 [a-z0-9_]+ 且 ≤64 字符: {char_id!r}"
        )

    relations = payload.get("relations")
    if not isinstance(relations, dict):
        raise ContractError("relations 必须是对象（{关系角色id: 权重}）")
    if not relations:
        raise ContractError("relations 不能为空")

    clean: dict[str, int] = {}
    for name, weight in relations.items():
        if not is_valid_identifier(name):
            raise ContractError(f"关系角色 id 非法: {name!r}")
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise ContractError(f"权重必须是整数（不能是 bool）: {name}={weight!r}")
        clean[name] = weight

    return {
        "character_id": char_id,
        "relations": clean,
    }


def validate_update_interperson(payload: dict[str, Any]) -> ValidationResult:
    """内容软校验（不依赖文件系统）。"""
    errors: list[str] = []
    warnings: list[str] = []

    for name, weight in payload["relations"].items():
        if weight < 1 or weight > 5:
            warnings.append(
                f"关系 {name} 权重 {weight} 超出常见范围 1-5，请确认是否有意"
            )

    return ValidationResult(tuple(errors), tuple(warnings))
