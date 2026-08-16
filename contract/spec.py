"""动作规格 — 单个动作的注册声明。

ActionSpec 描述一个动作的全部契约:
    - 外壳字段声明（prompt_fields）：单一真源，驱动三层行为
    - payload 结构解析（parse_payload）：白名单规范化
    - 审批策略（approval）
    - 软校验钩子（validate）

依赖: constants（外壳字段全集）、model（ValidationResult）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from contract.constants import ALL_SHELL_FIELDS
from contract.model import ValidationResult


class ActionSpec:
    """单个动作类型的注册规格。

    prompt_fields 是单一真源（single source of truth），同时驱动三层行为:
        1. 输入层  build_schema() 只输出集合内的字段 → LLM 只看到这些字段
        2. 输出层  AgentAction 按集合取字段，未声明的一律为空
        3. 校验层  parse() 按集合处理——声明了 sources 强制非空（宁缺勿错）;
                   未声明则丢弃违规返回（不污染数据）
    """

    __slots__ = (
        "name", "parse_payload", "approval", "validate",
        "prompt_fields", "payload_schema",
    )

    def __init__(
        self,
        name: str,
        parse_payload: Callable[[dict[str, Any]], dict[str, Any]],
        approval: str,
        validate: Callable[[dict[str, Any]], ValidationResult] | None = None,
        *,
        prompt_fields: frozenset[str] | None = None,
        payload_schema: str = "",
    ):
        """
        Args:
            name: 动作名（LLM 的 action 字段必须精确匹配）
            parse_payload: 白名单规范化 + 结构转换；结构错误抛 ContractError
            approval: APPROVAL_REQUIRED / AUTO / NEVER 之一
            validate: 可选软校验；返回 ValidationResult，错误即拒绝
            prompt_fields: 该动作需要的外壳字段子集（⊆ ALL_SHELL_FIELDS）。
                默认 = 全集（写动作需要 sources/basis 追溯）。
                运行时动作应传 RUNTIME_SHELL_FIELDS。
            payload_schema: 给 LLM 看的 payload 字段描述（build_schema 输出用）
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("动作名必须是非空字符串")
        self.name = name
        self.parse_payload = parse_payload
        self.approval = approval
        self.validate = validate
        self.prompt_fields = (
            ALL_SHELL_FIELDS if prompt_fields is None else frozenset(prompt_fields)
        )
        invalid = self.prompt_fields - ALL_SHELL_FIELDS
        if invalid:
            raise ValueError(f"未知外壳字段: {sorted(invalid)}")
        if "action" not in self.prompt_fields:
            raise ValueError("prompt_fields 必须包含 action")
        self.payload_schema = payload_schema

    @property
    def requires_sources(self) -> bool:
        """是否要求 sources 证据（由 prompt_fields 声明派生）。"""
        return "sources" in self.prompt_fields
