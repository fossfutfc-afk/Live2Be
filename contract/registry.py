"""动作注册表 — 动作集管理与解析（校验层）。

每个注册表实例属于一个域（domain），parse 出的 AgentAction 烙上域标签。
动作的执行在此之后由调用方按 approval 策略处理。

依赖: constants / model / spec。
"""

from __future__ import annotations

from typing import Any

from contract.constants import (
    DOMAIN_IDE,
    DOMAIN_MMT,
    MAX_BASIS_COUNT,
    MAX_REPLY_LENGTH,
    MAX_SOURCE_COUNT,
    MAX_SUMMARY_LENGTH,
)
from contract.errors import err
from contract.model import AgentAction, ContractError, ValidationResult
from contract.spec import ActionSpec


class ActionRegistry:
    """动作注册表：LLM 输出（dict）→ (AgentAction, ValidationResult)。

    纯外壳，不包含任何具体动作——由各项目注册自己的动作集。
    每个注册表实例属于一个域（domain），parse 出的 AgentAction 烙上域标签。
    """
    domain: str                   # 类型域
    _specs: dict[str, ActionSpec] # json转为的dict

    def __init__(self, domain: str = ""):
        if not isinstance(domain, str) or not domain.strip():
            raise ValueError(err("BadDomain", "domain 必须是非空字符串"))
        self.domain = domain
        self._specs: dict[str, ActionSpec] = {}

    # ------------------------------------------------------------------
    # 注册与查询
    # ------------------------------------------------------------------

    def register(self, spec: ActionSpec) -> None:
        """注册一个动作类型。同名重复注册抛错。"""
        if spec.name in self._specs:
            raise ValueError(err("DuplicateAction", f"动作已注册: {spec.name}"))
        self._specs[spec.name] = spec

    def spec(self, name: str) -> ActionSpec | None:
        """按动作名取规格（schema 渲染用）。"""
        return self._specs.get(name)

    def action_names(self) -> list[str]:
        """已注册动作名（排序）—— **包括封印的**（解析/执行照旧认得它们）。"""
        return sorted(self._specs)

    def prompt_action_names(self) -> list[str]:
        """⭐ **进 prompt 的动作名**（排序）—— `in_prompt=False` 的封印动作**不在内**。

        ⚠️ 与 `action_names()` 的差别就是**封印位**（`ActionSpec.in_prompt`）:
        渲染"本轮输出契约"用这一个; 解析/执行用那一个。⛔ 别把两者合并
        （合并 = 封印的动作连"她万一写了"都认不出）。
        """
        return sorted(n for n, s in self._specs.items() if getattr(s, "in_prompt", True))

    # ------------------------------------------------------------------
    # 校验层：解析 LLM 输出
    # ------------------------------------------------------------------

    def parse(self, raw: Any) -> tuple[AgentAction | None, ValidationResult]:
        """解析 LLM 返回的原始对象（已由 json 解析成 dict）。

        按动作的 prompt_fields 裁剪外壳字段：
            声明了 sources → 校验其内容；空则 warning 提示（宁缺勿错，硬性依据
            要求由动作的 validate 钩子决定，如 interperson 不得凭空添加）；
            未声明 → 违规返回一律丢弃，不污染 AgentAction。

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

        # ---- 外壳字段（按 prompt_fields 声明裁剪）----
        summary = ""
        if "summary" in spec.prompt_fields:
            summary = raw.get("summary", "")
            if not isinstance(summary, str):
                errors.append("summary 必须是字符串")
                summary = ""
            elif len(summary) > MAX_SUMMARY_LENGTH:
                errors.append(f"summary 超过 {MAX_SUMMARY_LENGTH} 字符")

        reply = ""
        if "reply" in spec.prompt_fields:
            reply = raw.get("reply", "")
            if not isinstance(reply, str):
                errors.append("reply 必须是字符串")
                reply = ""
            elif len(reply) > MAX_REPLY_LENGTH:
                errors.append(f"reply 超过 {MAX_REPLY_LENGTH} 字符")

        if "sources" in spec.prompt_fields:
            sources = _normalize_str_list(
                raw.get("sources", []), "sources", MAX_SOURCE_COUNT, errors
            )
            if not sources:
                # 宁缺勿错：缺来源不阻断（依据可为 basis，如 OC 角色的用户需求），
                # 但不得编造。硬性依据要求（如 interperson 不得凭空添加关系）
                # 由该动作的 validate 钩子保证——强制与否属于动作声明。
                warnings.append("该动作缺少 sources；宁缺勿错，请勿编造依据")
        else:
            sources = ()  # 未声明 → 丢弃违规返回

        if "basis" in spec.prompt_fields:
            basis = _normalize_str_list(
                raw.get("basis", []), "basis", MAX_BASIS_COUNT, errors
            )
        else:
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
            reply=reply,
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


# ============================================================================
# 便捷入口
# ============================================================================

def parse_action_text(
    registry: ActionRegistry, response_text: str
) -> tuple[AgentAction | None, ValidationResult]:
    """从 LLM 原始响应文本直接解析动作（内部走 `contract.json_cleaner` 清洗管道）。

    用法:
        action, result = parse_action_text(registry, llm_raw_text)
    """
    from contract.json_cleaner import extract_json

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
    """规范化字符串列表字段（sources/basis）。非法的项被丢弃并记录错误。

    机器侧容错（与 schema 提示的『列表』类型约定配套）：
    LLM 偶发把单值写成裸字符串（如 basis: "用户要求整理"），语义无损，
    自动包成单元素列表再走常规校验——宁缺勿错但不过度拒绝。
    """
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [raw]
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
