"""人际关系动作 — update_interperson（全量快照 + 角色粒度替换）。

权重语义（熟悉程度 = 访问层级; knowledge 基本不被学生间共享）:
    1  萍水相逢      profile
    2  社团/队友     profile + personality          ← 社团成员默认
    3  故知/青梅竹马  profile + personality + experience   ← 很难达到,
                                                           AI 可基于资料推断加码到 3
    超出 1-3 无定义语义 → 硬错误（宁缺勿错）。

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
        if weight < 1 or weight > 3:
            errors.append(
                f"关系 {name} 权重 {weight} 超出语义范围 1-3"
                "(1=萍水相逢/只见profile 2=社团成员/加personality "
                "3=故知/再加experience)，无定义语义"
            )
        elif weight == 3:
            warnings.append(
                f"关系 {name} 熟悉度 3（故知）程度很高，"
                "请确认有资料/用户依据（宁缺勿错）"
            )

    return ValidationResult(tuple(errors), tuple(warnings))


def parse_view_interperson(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。只读, 结果回灌 LLM。

    character_id 可选——缺省列出全部有关系的角色, 带则只看该角色的完整关系。
    """
    clean: dict[str, Any] = {}
    char_id = payload.get("character_id")
    if char_id is not None:
        if not is_valid_identifier(char_id):
            raise ContractError(
                f"character_id 必须匹配 [a-z0-9_]+ 且 ≤64 字符: {char_id!r}"
            )
        clean["character_id"] = char_id
    return clean
