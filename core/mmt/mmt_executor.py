"""MMT 执行层 — 按 approval=auto 执行动作，reply 承载对白。

契约层只解析动作（纯结构校验, 不碰文件系统/运行时）；执行层负责动作的
实际执行——读角色资料、模拟媒体发送、剧情触发。每个动作成功返回
ExecResult(ok=True, message=回灌给 LLM 的内容)；不可执行抛 MmtExecError
（message 同样回灌给 LLM 修正, 而不是崩溃）。

动作执行:
    mmt_chat                 对白已在 action.reply——执行仅确认, 正常回复核心路径
    mmt_inspect_character    读目标角色资料, 按 interperson 权重限制访问层级
                             （1=只见 profile, 2=+personality, 3=+experience）
    mmt_send_media           图片发送占位——媒体存储/查库/生成管线未接入,
                             仅回灌确认信息（用户已确认后续细化, 先保证回复流程）
    mmt_trigger_bond_story   羁绊剧情内容系统未实现 → 拒绝触发, 回灌纠正 LLM

设计决策:
    - 执行器持有会话当前角色（set_current_character）, inspect 用它查
      interperson 里 self→target 的权重决定访问层级。
    - 访问层级逻辑（load_interperson / resolve_access_level）当前内联在
      本文件——待 core/parsing/relation_parser.py 落地后移入。
    - 错误统一走 MmtExecError（Live2BeError 子类, __str__ 自动产出
      [mmt_executor.py][MmtExecError][message]）, 由调用方捕获回灌。
    - 与 IDE 执行器同一范式: 成功返回 ExecResult, 失败抛域异常。

TODO（后续 session）:
    - core/parsing/relation_parser.py: 移入 load_interperson / resolve_access_level
    - 媒体管线（存储/查库/LLM 生成）落地后替换 _execute_mmt_send_media 的占位
    - 羁绊剧情内容系统（story_parser）落地后实现 _execute_mmt_trigger_bond_story
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from errors import Live2BeError
from contract import AgentAction, DOMAIN_MMT
from core.parsing.dynamic_character_parser import (
    CharacterLoader,
    DynamicCharacter,
    yaml_to_prompt,
)

# interperson.json 默认路径（相对项目根, 与 fetch/executor.py 一致）
DEFAULT_INTERPERSON_PATH = "config/settings/relation/interperson.json"


class MmtExecError(Live2BeError):
    """MMT 执行层拒绝/失败。message 供调用方回灌给 LLM 修正。

    __str__ 自动产出 [mmt_executor.py][MmtExecError][message]。
    """


@dataclass
class ExecResult:
    """执行结果。message 回灌给 LLM（或展示给用户）。"""

    ok: bool
    message: str


# ============================================================================
# 访问层级（待 relation_parser.py 落地后移入）
# ============================================================================

def load_interperson(path: str | Path) -> dict:
    """读取 interperson.json（缺失 → {}；损坏 → MmtExecError）。

    Returns:
        {char_id: {rel_char_id: 权重 int}} 扁平权重表。
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise MmtExecError(f"interperson.json 读取失败: {e}") from e
    if not isinstance(data, dict):
        raise MmtExecError(f"interperson.json 内容不是对象: {path}")
    return data


def resolve_access_level(interperson: dict, self_id: str, target_id: str) -> int:
    """interperson 权重 → 访问层级。

    权重语义（与 IDE 文档一致）:
        1 = 萍水相逢      → 只见 profile
        2 = 社团/队友     → + personality
        3 = 故知/青梅竹马 → + experience
    无记录 / 权重非法 → 1（默认只可见 profile, "查不到的角色视为不认识"）。
    """
    weight = interperson.get(self_id, {}).get(target_id)
    if isinstance(weight, int) and 1 <= weight <= 3:
        return weight
    return 1


# ============================================================================
# 执行器
# ============================================================================

class MmtExecutor:
    """MMT 动作执行器。characters_root = config/characters 目录。"""

    def __init__(
        self,
        characters_root: str | Path,
        interperson_path: str | Path | None = None,
    ):
        self.char_loader = CharacterLoader(characters_root)
        self.interperson_path = (
            Path(interperson_path) if interperson_path
            else Path(DEFAULT_INTERPERSON_PATH)
        )
        self.current_char: DynamicCharacter | None = None

    # ------------------------------------------------------------------
    # 会话上下文
    # ------------------------------------------------------------------

    def set_current_character(self, char: DynamicCharacter | None) -> None:
        """设置会话当前角色（inspect 用它查 self→target 的权重）。"""
        self.current_char = char

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def execute(self, action: AgentAction) -> ExecResult:
        """执行一个已通过契约校验的 MMT 动作。抛 MmtExecError 表示不可执行。

        统一入口: 按动作名分派到 _execute_{action}。调用方捕获 MmtExecError
        并把 message 回灌给 LLM。
        """
        if action.domain != DOMAIN_MMT:
            raise MmtExecError(f"非 MMT 域动作: {action.domain}:{action.action}")
        handler = getattr(self, f"_execute_{action.action}", None)
        if handler is None:
            raise MmtExecError(f"未知执行动作: {action.action}")
        return handler(action)

    # ==================================================================
    # mmt_chat — 说一句话（正常回复核心路径）
    # ==================================================================

    def _execute_mmt_chat(self, action: AgentAction) -> ExecResult:
        """对白已在 action.reply——执行即确认。

        模拟手机操作（operation）是展示层元数据, 由调用方渲染, 无需执行。
        """
        return ExecResult(ok=True, message="已回复")

    # ==================================================================
    # mmt_inspect_character — 查角色资料（访问层级限制）
    # ==================================================================

    def _execute_mmt_inspect_character(self, action: AgentAction) -> ExecResult:
        if self.current_char is None:
            raise MmtExecError("尚未进入会话, 无法查角色资料")

        target_id = action.payload["character_id"]
        try:
            char = self.char_loader.load(target_id)
        except FileNotFoundError:
            raise MmtExecError(
                f"角色不存在: {target_id}——请使用已建档角色"
            ) from None

        interperson = load_interperson(self.interperson_path)
        level = resolve_access_level(
            interperson, self.current_char.character_id, target_id
        )

        merged = dict(char.profile)
        if level >= 2:
            merged.update(char.personality)
        if level >= 3:
            merged.update(char.experience)

        data = yaml_to_prompt(merged, f"角色 {char.display_name} 资料")
        return ExecResult(
            ok=True,
            message=(
                f"[已查阅 {target_id} 资料, 访问层级 {level}/3]\n"
                f"{data}"
            ),
        )

    # ==================================================================
    # mmt_send_media — 发图片（占位, 媒体管线后续接入）
    # ==================================================================

    def _execute_mmt_send_media(self, action: AgentAction) -> ExecResult:
        """图片发送占位——存储/查库/LLM 生成管线未接入, 仅回灌确认。

        用户已确认: 媒体方案先不细化, 保证回复流程正常即可。
        不伪造图片, 明说占位让 LLM 知道媒体尚未真实落地。
        """
        desc = action.payload["image"]
        library_id = action.payload["library_id"]
        if library_id:
            message = (
                f"[图片占位] 引用资源库 {library_id}（{desc}）——"
                "媒体管线未接入, 后续落地查库/生成"
            )
        else:
            message = (
                f"[图片占位] {desc}——媒体管线未接入, 后续落地查库/生成"
            )
        return ExecResult(ok=True, message=message)

    # ==================================================================
    # mmt_trigger_bond_story — 触发羁绊剧情（剧情系统未实现）
    # ==================================================================

    def _execute_mmt_trigger_bond_story(self, action: AgentAction) -> ExecResult:
        story_id = action.payload["story_id"]
        raise MmtExecError(
            f"羁绊剧情 {story_id} 无法触发——剧情内容系统尚未实现, "
            "请勿触发; 正常对话即可"
        )
