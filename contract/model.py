"""契约数据对象 — 跨语言 wire format 的载体。

本模块只含纯数据对象，无业务逻辑。
AgentAction.to_dict() / from_dict() 是对称的 JSON wire format，
是 Python ↔ JS 之间的数据边界（A 方案下 JS 端作为消费者）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contract.errors import Live2BeError


class ContractError(Live2BeError, ValueError):
    """契约解析失败（结构层面硬错误）。

    由 ActionSpec.parse_payload 抛出——字段类型错误、白名单之外、
    跨字段条件不满足等"无法进入 AgentAction"的结构错误走这条路径。

    多继承 ValueError：__str__ 由 Live2BeError 产出 [model.py][ContractError][info]，
    同时保留 except ValueError 的既有捕获语义。
    """


@dataclass(frozen=True)
class ValidationResult:
    """校验结果：errors 非空 = 拒绝执行；warnings 仅提示不阻断。

    errors 是硬性错误——调用方应停止，并把原因回灌给 LLM 让它修正；
    warnings 是软提示——可放行，但应记录（如"缺少 sources 依据"）。
    """

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    drops: tuple[str, ...] = ()
    """⚠️ **`warnings` 里"真的丢了东西"的那几条**（内容被丢弃 / 截断）。

    与 `warnings` 是**包含关系**（`drops ⊆ warnings`）: 这里出现的文本一定也在 `warnings`
    里 —— `warnings` 是人读的全量, `drops` 是**机器可判**的那一半。

    ⭐ **为什么要有它**（2026-09-29, D1）: 契约层写了 25 种 warning, 里面少数几种是
    "这条区间作废 / 这句原话丢了 / 那句心境丢了" —— 而 `digest` 侧**一个字都没接**
    （`call._round_call` 只看 `errors`）。要把它们接出来并**分类**, 只有两条路:
    · 按**文案**匹配（`"丢弃" in msg`）—— ⛔ 这正是本项目 2026-09-21 栽过的坑
      （`HARD_BLOCK_ISSUE_MARKS` 拿中文子串判软硬, 换个措辞就静默升级）;
    · ✅ **在源头声明**（本字段）—— 与 `ISSUE_SEVERITY` 同一个道理: 判据跟着
      **声明**走, 不跟文案走。改文案不会让它失准。
    """

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class AgentAction:
    """LLM 返回的一个可执行动作（通用外壳）。

    payload 是经过该动作 parse_payload 白名单规范化后的干净 dict——
    只含允许字段，已做类型/取值转换。
    sources/basis 仅对该动作声明了相应字段时才有值，否则恒为空 tuple。
    """

    action: str
    domain: str = ""                    # 动作域: ide / mmt / story（见 DOMAIN_* 常量）
    approval: str = ""                  # 审批策略，注册时从 ActionSpec 拷入
    summary: str = ""
    reply: str = ""                     # AI 对用户的话（完整回复/解释, 可选）
    payload: dict[str, Any] = field(default_factory=dict)
    sources: tuple[str, ...] = ()   # 事实依据（仅声明了 sources 的动作启用）
    basis: tuple[str, ...] = ()     # 决策依据（仅声明了 basis 的动作启用）

    # ------------------------------------------------------------------
    # 跨语言 wire format（JSON 对称）
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 兼容 dict（日志 / 存档 / 传给 JS 端）。"""
        return {
            "action": self.action,
            "domain": self.domain,
            "approval": self.approval,
            "summary": self.summary,
            "reply": self.reply,
            "payload": dict(self.payload),
            "sources": list(self.sources),
            "basis": list(self.basis),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AgentAction":
        """从 wire format 还原（JS 端传来的动作 JSON 等）。

        容错处理：缺失字段取默认值；sources/basis 逐项转 str。
        """
        return cls(
            action=str(raw.get("action", "")),
            domain=str(raw.get("domain", "")),
            approval=str(raw.get("approval", "")),
            summary=str(raw.get("summary", "")),
            reply=str(raw.get("reply", "")),
            payload=dict(raw.get("payload") or {}),
            sources=tuple(str(s) for s in (raw.get("sources") or [])),
            basis=tuple(str(b) for b in (raw.get("basis") or [])),
        )
