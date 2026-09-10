"""contract — 契约层（动作注册 / 校验 / 渲染）。

namespace package 转正式包：集中 re-export 公共 API，供 ide/ 子项目
`from contract import ...` 直接消费。

各子模块内部一律用 `contract.xxx` 完整路径互导，不依赖本 __init__ 的执行顺序。
"""

from __future__ import annotations

from contract.constants import (
    ALL_SHELL_FIELDS,
    APPROVAL_AUTO,
    APPROVAL_NEVER,
    APPROVAL_REQUIRED,
    DOMAIN_IDE,
    DOMAIN_MEMORIAL,
    DOMAIN_MMT,
    DOMAIN_STORY,
    MAX_BASIS_COUNT,
    MAX_ID_LENGTH,
    MAX_REPLY_LENGTH,
    MAX_SOURCE_COUNT,
    MAX_SUMMARY_LENGTH,
    RUNTIME_SHELL_FIELDS,
    is_valid_identifier,
)
from contract.model import AgentAction, ContractError, ValidationResult
from contract.spec import ActionSpec
from contract.registry import (
    ActionRegistry,
    IDEActionRegistry,
    MMTActionRegistry,
    MemorialActionRegistry,
    StoryActionRegistry,
    parse_action_text,
)
from contract.records import (
    CHARACTER_NARRATOR,
    CHARACTER_SENSEI,
    DEFAULT_SPEAKER_NAMES,
    KIND_CHARACTER,
    KIND_STAGE,
    MAX_SENSEI_RUN,
    SPEAKER_SENSEI_LABEL,
    STAGE_ART,
    STAGE_END,
    STAGE_EXIT,
    STAGE_MEMORIAL,
    STAGE_SWITCH,
    STAGE_VALUES,
    ParseDiag,
    ParseResult,
    VnBlock,
    VnRecord,
    check_block,
    normalize_main_character,
    parse_line,
    parse_stream,
    sensei_group_labels,
    sensei_groups,
)
from contract.schema import (
    build_schema,
    build_digest_schema,
    build_record_schema,
    export_definitions,
)

__all__ = [
    "ALL_SHELL_FIELDS",
    "APPROVAL_AUTO",
    "APPROVAL_NEVER",
    "APPROVAL_REQUIRED",
    "DOMAIN_IDE",
    "DOMAIN_MEMORIAL",
    "DOMAIN_MMT",
    "DOMAIN_STORY",
    "MAX_BASIS_COUNT",
    "MAX_ID_LENGTH",
    "MAX_REPLY_LENGTH",
    "MAX_SOURCE_COUNT",
    "MAX_SUMMARY_LENGTH",
    "RUNTIME_SHELL_FIELDS",
    "is_valid_identifier",
    "AgentAction",
    "ContractError",
    "ValidationResult",
    "ActionSpec",
    "ActionRegistry",
    "IDEActionRegistry",
    "MMTActionRegistry",
    "MemorialActionRegistry",
    "StoryActionRegistry",
    "parse_action_text",
    "build_schema",
    "build_digest_schema",
    "build_record_schema",
    "export_definitions",
    # —— VN 记录流（记录流 v2, 2026-09-10）——
    "KIND_CHARACTER",
    "KIND_STAGE",
    "CHARACTER_NARRATOR",
    "CHARACTER_SENSEI",
    "STAGE_VALUES",
    "STAGE_SWITCH",
    "STAGE_ART",
    "STAGE_MEMORIAL",
    "STAGE_END",
    "STAGE_EXIT",
    "MAX_SENSEI_RUN",
    "VnRecord",
    "VnBlock",
    "ParseDiag",
    "ParseResult",
    "parse_line",
    "parse_stream",
    "sensei_groups",
    "sensei_group_labels",
    "check_block",
    "normalize_main_character",
    "SPEAKER_SENSEI_LABEL",
    "DEFAULT_SPEAKER_NAMES",
]
