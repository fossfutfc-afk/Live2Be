"""LLM → 程序动作 契约外壳（通用层）。

设计目标:
    LLM 返回结构化 JSON（动作）→ 本模块解析 + 校验 → 程序执行。
    主项目（运行时表情/背景切换）与辅助项目（角色配置写入）共用同一套机制，
    各自通过 ActionRegistry 注册自己的动作。本文件只含外壳，不含任何具体动作。

动作域（domain）:
    动作按域分门别类，域之间完全隔离，便于修改/扩展/调用/阅读:
        IDEActionRegistry   "ide"   辅助项目（写配置文件）
        MMTActionRegistry   "mmt"   MomoTalk 运行时（未来 agent：模拟手机操作）
        StoryActionRegistry "story" 羁绊剧情运行时（表情/背景切换）
    域标签烙进 AgentAction.domain，动作名无需前缀、在域内保持简短。

审批策略（决定动作如何被处理）:
    APPROVAL_REQUIRED  写动作，用户批准后才执行（辅助项目写配置文件）
    APPROVAL_AUTO      规则校验通过即执行（主项目运行时切换表情/背景）
    APPROVAL_NEVER     只读/抓取，直接执行（fetch_url 等）

用法（以辅助项目为例）:
    from llm.contract import IDEActionRegistry, ActionSpec, APPROVAL_REQUIRED

    def parse_create_character(payload: dict) -> dict:
        # 白名单规范化：只保留允许字段并转换类型；结构错误抛 ContractError
        ...  # 见 fetch/ 项目实际实现
        return clean_payload

    registry = IDEActionRegistry()   # 辅助项目动作域
    registry.register(ActionSpec("create_character", parse_create_character,
                                 APPROVAL_REQUIRED, evidence=True))  # 写动作需证据

    action, result = parse_action_text(registry, llm_response_text)
    if result.is_valid:
        if action.approval == APPROVAL_REQUIRED:
            ...  # 展示 diff，等用户批准
        else:
            ...  # 直接执行
    else:
        ...  # 把 result.errors 回灌给 LLM 让它修正

约定:
    - 解析分两层：结构错误抛 ContractError（硬错误）；校验错误进 ValidationResult（软拒绝）。
    - payload 一律经过动作自身的 parse_payload 白名单规范化——丢弃未知字段，
      防止 LLM 往 payload 塞任意内容。
    - sources/basis 仅对 evidence=True 的动作启用并强制来源非空；非 evidence 动作
      （主项目运行时等）LLM schema 不含这两个字段，违规返回也会被丢弃。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

# ============================================================================
# 审批策略
# ============================================================================

APPROVAL_REQUIRED = "required"   # 写动作：用户批准后才执行
APPROVAL_AUTO     = "auto"       # 规则校验通过即执行（主项目运行时）
APPROVAL_NEVER    = "never"      # 只读/抓取：直接执行

# ============================================================================
# 动作域（domain）— 分门别类，域之间隔离
# ============================================================================

# ide   辅助项目（配置写入）
# mmt   MomoTalk 运行时（未来 agent：模拟发图/打电话/定位等手机操作）
# story 羁绊剧情运行时（表情/背景切换）
DOMAIN_IDE = "ide"
DOMAIN_MMT = "mmt"
DOMAIN_STORY = "story"

# ============================================================================
# 通用约束
# ============================================================================

# 通用标识符（角色 id / 关系名等）：小写字母、数字、下划线
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9_]+$")
MAX_ID_LENGTH = 64

# 外壳字段上限
MAX_SUMMARY_LENGTH = 500
MAX_SOURCE_COUNT   = 20
MAX_BASIS_COUNT    = 20


def is_valid_identifier(name: Any) -> bool:
    """通用 id 校验（角色 id / 关系名共用）。"""
    return (
        isinstance(name, str)
        and len(name) <= MAX_ID_LENGTH
        and bool(IDENTIFIER_PATTERN.fullmatch(name))
    )


# ============================================================================
# 校验结果
# ============================================================================

class ContractError(ValueError):
    """契约解析失败（结构层面硬错误）。由 parse_payload 抛出。"""


@dataclass(frozen=True)
class ValidationResult:
    """校验结果：errors 非空 = 拒绝执行；warnings 仅提示不阻断。"""

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def require_valid(self) -> None:
        if not self.is_valid:
            raise ContractError("\n".join(self.errors))


# ============================================================================
# 动作
# ============================================================================

@dataclass(frozen=True)
class AgentAction:
    """LLM 返回的一个可执行动作（通用外壳）。

    payload 是经过该动作 parse_payload 白名单规范化后的干净 dict——
    只含允许字段，已做类型/取值转换。
    """

    action: str
    domain: str = ""                    # 动作域: ide / mmt / story（见 DOMAIN_* 常量）
    approval: str = ""                  # 审批策略，注册时从 ActionSpec 拷入
    summary: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    sources: tuple[str, ...] = ()   # 事实依据（仅 evidence 动作启用，否则恒为空）
    basis: tuple[str, ...] = ()     # 决策依据（仅 evidence 动作启用，否则恒为空）

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "domain": self.domain,
            "approval": self.approval,
            "summary": self.summary,
            "payload": dict(self.payload),
            "sources": list(self.sources),
            "basis": list(self.basis),
        }


class ActionSpec:
    """单个动作类型的注册规格。

    evidence 开关决定该动作是否需要证据字段（sources/basis）:
        - True  写动作（辅助项目）：LLM schema 含 sources/basis，sources 强制非空
        - False 运行时动作（主项目剧情）：LLM schema 不含这两个字段，
                AI 即便违规返回也会被解析时静默丢弃——避免 AI 为填依据而编造内容
    """

    __slots__ = ("name", "parse_payload", "approval", "validate", "evidence")

    def __init__(
        self,
        name: str,
        parse_payload: Callable[[dict[str, Any]], dict[str, Any]],
        approval: str,
        validate: Callable[[dict[str, Any]], ValidationResult] | None = None,
        *,
        evidence: bool = False,
    ):
        """
        Args:
            name: 动作名（LLM 的 action 字段必须精确匹配）
            parse_payload: 白名单规范化 + 结构转换；结构错误抛 ContractError
            approval: APPROVAL_REQUIRED / AUTO / NEVER 之一
            validate: 可选软校验；返回 ValidationResult，错误即拒绝
            evidence: 是否需要 sources/basis 证据字段（默认 False）
        """
        self.name = name
        self.parse_payload = parse_payload
        self.approval = approval
        self.validate = validate
        self.evidence = evidence


class ActionRegistry:
    """动作注册表：LLM 输出（dict）→ (AgentAction, ValidationResult)。

    纯外壳，不包含任何具体动作——由各项目注册自己的动作集。
    每个注册表实例属于一个域（domain），parse 出的 AgentAction 烙上该域标签。
    """

    def __init__(self, domain: str = ""):
        if not isinstance(domain, str) or not domain.strip():
            raise ValueError("domain 必须是非空字符串")
        self.domain = domain
        self._specs: dict[str, ActionSpec] = {}

    def register(self, spec: ActionSpec) -> None:
        """注册一个动作类型。同名重复注册抛错。"""
        if spec.name in self._specs:
            raise ValueError(f"动作已注册: {spec.name}")
        self._specs[spec.name] = spec

    def spec(self, name: str) -> ActionSpec | None:
        return self._specs.get(name)

    def action_names(self) -> list[str]:
        return sorted(self._specs)

    def parse(self, raw: Any) -> tuple[AgentAction | None, ValidationResult]:
        """解析 LLM 返回的原始对象（已由 json 解析成 dict）。

        Returns:
            (AgentAction, ValidationResult): 校验失败时 AgentAction 为 None。
        """
        if not isinstance(raw, dict):
            return None, ValidationResult(errors=("动作必须是 JSON 对象",))

        name = raw.get("action", "")
        spec = self._specs.get(name)
        if spec is None:
            return None, ValidationResult(
                errors=(f"未知动作: {name!r}（已注册: {self.action_names()}）",)
            )

        errors: list[str] = []
        warnings: list[str] = []

        # ---- 外壳字段 ----
        summary = raw.get("summary", "")
        if not isinstance(summary, str):
            errors.append("summary 必须是字符串")
            summary = ""
        elif len(summary) > MAX_SUMMARY_LENGTH:
            errors.append(f"summary 超过 {MAX_SUMMARY_LENGTH} 字符")

        # ---- 证据字段（仅 evidence 动作启用）----
        if spec.evidence:
            sources = _normalize_str_list(raw.get("sources", []), "sources", MAX_SOURCE_COUNT, errors)
            basis = _normalize_str_list(raw.get("basis", []), "basis", MAX_BASIS_COUNT, errors)
            if not sources:
                errors.append("该动作需要 sources（事实依据，宁缺勿错）")
        else:
            # 非 evidence 动作：忽略并丢弃 AI 返回的证据字段，防止编造
            sources = ()
            basis = ()

        # ---- payload 解析（结构错误 → 异常 → 收集为错误）----
        payload_raw = raw.get("payload")
        if not isinstance(payload_raw, dict):
            errors.append("payload 必须是对象")
            payload: dict[str, Any] = {}
        else:
            try:
                payload = spec.parse_payload(payload_raw)
            except ContractError as e:
                errors.append(str(e))
                payload = {}

        # ---- 动作专属软校验（仅在结构无误后执行）----
        if spec.validate is not None and not errors:
            extra = spec.validate(payload)
            errors.extend(extra.errors)
            warnings.extend(extra.warnings)

        result = ValidationResult(tuple(errors), tuple(warnings))
        if not result.is_valid:
            return None, result

        return AgentAction(
            action=name,
            domain=self.domain,
            approval=spec.approval,
            summary=summary,
            payload=payload,
            sources=sources,
            basis=basis,
        ), result


# ============================================================================
# 三个具名动作域 — 分门别类，各自独立注册/扩展
# ============================================================================

class IDEActionRegistry(ActionRegistry):
    """辅助项目动作域：写配置文件，写动作默认需证据 + 用户审批。"""

    def __init__(self) -> None:
        super().__init__(DOMAIN_IDE)


class MMTActionRegistry(ActionRegistry):
    """MomoTalk 动作域：运行时模拟手机操作（未来 agent 板块）。"""

    def __init__(self) -> None:
        super().__init__(DOMAIN_MMT)


class StoryActionRegistry(ActionRegistry):
    """羁绊剧情动作域：运行时表情/背景切换。"""

    def __init__(self) -> None:
        super().__init__(DOMAIN_STORY)


# ============================================================================
# 便捷入口
# ============================================================================

def parse_action_text(registry: ActionRegistry, response_text: str) -> tuple[AgentAction | None, ValidationResult]:
    """从 LLM 原始响应文本直接解析动作（内部走 json_cleaner 清洗管道）。

    用法:
        action, result = parse_action_text(registry, llm_raw_text)
    """
    from llm.json_cleaner import extract_json

    try:
        raw = extract_json(response_text)
    except ValueError as e:
        return None, ValidationResult(errors=(f"JSON 解析失败: {e}",))
    return registry.parse(raw)


# ============================================================================
# 内部工具
# ============================================================================

def _normalize_str_list(
    raw: Any, label: str, limit: int, errors: list[str]
) -> tuple[str, ...]:
    """规范化字符串列表字段（sources/basis）。非法的项被丢弃并记录错误。"""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errors.append(f"{label} 必须是列表")
        return ()

    result: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label} 项必须是非空字符串")
            continue
        result.append(item.strip())

    if len(result) > limit:
        errors.append(f"{label} 超过 {limit} 项")
    return tuple(result)
