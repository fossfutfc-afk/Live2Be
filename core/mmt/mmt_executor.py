"""MMT 执行层 — 按 approval=auto 执行动作，reply 承载对白。

契约层只解析动作（纯结构校验, 不碰文件系统/运行时）；执行层负责动作的
实际执行——读角色资料、模拟媒体发送、羁绊触发判定。每个动作成功返回
ExecResult(ok=True, message=回灌给 LLM 的内容)；不可执行抛 MmtExecError
（message 同样回灌给 LLM 修正, 而不是崩溃）。

动作执行（对应 core/mmt/mmt_actions.py 的动作集）:
    mmt_chat                 对白已在 action.reply——执行仅确认, 正常回复核心路径
    mmt_inspect_character    深挖后备: 按 interperson 权重分级读目标资料
                             （自检拒绝 / 无记录拒绝 / 1=profile 2=+personality 3=+experience）
    mmt_send_media           图片发送占位——媒体管线未接入, 仅回灌确认
    mmt_trigger_bond_story   触发放行——**引擎不拦节奏**（2026-09-02 v2 用户拍板:
                             轮数只是建议, 由 momotalk 每轮注记提示时机; 紧急剧情
                             sensei 遇险等 LLM 自行裁决随时触发）; 放行即切剧情模式

信息架构（v2 五层认知, 与 mmt_actions 一致）:
    L0 自我层 / L1 人际层（自表条目注入, self_entry_to_prompt）/ L2 硬知识 / L3 深挖层。
    inspect 是 L3 的门控入口: 无记录=素不相识 → 拒绝, LLM 用知识回答公开信息。

设计决策:
    - 执行器持有会话当前角色（set_current_character）, inspect/trigger 依赖它。
    - 自检防护（双重）: 本文件抛 MmtExecError 代码级报错 + mmt_actions schema 提示。
    - 无记录≠不认识: 无记录=素不相识（可耳闻）, inspect 拒绝但可凭知识回答。
    - 自表条目注入: self_entry_to_prompt 生成 L1 注入文本, 由 momotalk 拼进 system prompt。
    - 触发 bool: 引擎建议不拦截（v1 曾硬拒不足 6 轮——2026-09-02 v2 用户复盘
      否决: 玩家遇险时角色尬聊是硬闸的伪正确; 时机建议由 momotalk._bond_progress_note
      每轮注入, 触发与否全权交给 LLM 的剧情判断）。
    - 人际层工具（load_interperson / resolve_access_level / self_entry_to_prompt）
      当前内联在本文件, 待 core/parsing/relation_parser.py 落地后移入。
    - 错误统一走 MmtExecError（Live2BeError 子类）, 由调用方捕获回灌。

TODO（后续 session）:
    - core/parsing/relation_parser.py: 移入人际层工具
    - 媒体管线（存储/查库/LLM 生成）落地后替换 _execute_mmt_send_media 的占位
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.common import Live2BeError
from contract import AgentAction, DOMAIN_MMT
from core.parsing.dynamic_character_parser import (
    CharacterLoader,
    DynamicCharacter,
    yaml_to_prompt,
)

# interperson.json 默认路径（项目根绝对, cwd 无关——uvicorn/IDE 从任意目录启动）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_INTERPERSON_PATH = _PROJECT_ROOT / "config" / "settings" / "relation" / "interperson.json"


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
# 人际层工具（待 relation_parser.py 落地后移入）
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
        1 = 萍水相逢（见过几次/交手/共事）→ 只见 profile
        2 = 社团/队友                      → + personality
        3 = 故知/青梅竹马                  → + experience
    无记录 / 权重非法 → 0（素不相识: 可耳闻但无私人交集, inspect 拒绝）。
    """
    weight = interperson.get(self_id, {}).get(target_id)
    if isinstance(weight, int) and 1 <= weight <= 3:
        return weight
    return 0


def self_entry_to_prompt(interperson: dict, self_id: str) -> str:
    """L1 人际层注入: 提取 self 的 interperson 条目, 渲染为 prompt 文本。

    解决两个问题: 键值映射（LLM 用准确 id 查资料, 无需猜）+ 关系感知
    （权重即关系信息, 回答「认不认识」问题时直接可用）。

    Returns:
        注入文本; self 无条目 → 空串（调用方跳过注入）。
    """
    entry = interperson.get(self_id)
    if not isinstance(entry, dict) or not entry:
        return ""
    items = ", ".join(f"{k}: {w}" for k, w in sorted(entry.items()))
    return (
        "你的关系记录: {" + items + "}\n"
        "含义: 键=角色id（查资料时用）, 值=熟悉程度（1=萍水相逢 2=社团/队友 3=故知）; "
        "未列出的角色=素不相识, 但你可能听说过其公开信息"
    )


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
        """设置会话当前角色（inspect/trigger 依赖它）。"""
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
    # mmt_inspect_character — 深挖后备: 查角色私密资料（权重分级）
    # ==================================================================

    def _execute_mmt_inspect_character(self, action: AgentAction) -> ExecResult:
        if self.current_char is None:
            raise MmtExecError("尚未进入会话, 无法查角色资料")

        target_id = action.payload["character_id"]
        self_id = self.current_char.character_id

        # 自检防护（代码级报错, 配合 mmt_actions schema 提示双重防线）
        if target_id == self_id:
            raise MmtExecError(
                "目标角色是你自己——你完全了解自己, 完整资料已在你的角色设定中, 不要查自己"
            )

        try:
            char = self.char_loader.load(target_id)
        except FileNotFoundError:
            raise MmtExecError(
                f"角色不存在: {target_id}——请使用已建档角色, 不要查玩家或胡编的名字"
            ) from None

        interperson = load_interperson(self.interperson_path)
        level = resolve_access_level(interperson, self_id, target_id)

        # 无记录≠不认识: 素不相识 → 拒绝查私密资料, 用知识回答公开信息
        if level == 0:
            raise MmtExecError(
                f"{char.display_name} 与你素不相识（无关系记录）——基于公开信息和你的知识"
                "回答其基本信息即可, 无法查其私密资料"
            )

        merged = dict(char.profile)
        if level >= 2:
            merged.update(char.personality)
        if level >= 3:
            merged.update(char.experience)

        data = yaml_to_prompt(merged, f"角色 {char.display_name} 资料")
        return ExecResult(
            ok=True,
            message=f"[已查阅 {target_id} 资料, 访问层级 {level}/3]\n{data}",
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
    # mmt_trigger_bond_story — bool 触发判定（好感度门槛 + LLM 决策）
    # ==================================================================

    def _execute_mmt_trigger_bond_story(self, action: AgentAction) -> ExecResult:
        if self.current_char is None:
            raise MmtExecError("尚未进入会话, 无法触发羁绊剧情")

        # 2026-09-02 v2（用户复盘拍板）: **引擎不拦节奏**——轮数不再是闸门
        # （玩家遇险时角色尬聊 6 轮是硬拒的伪正确）。时机由 momotalk 每轮注记
        # 建议（_bond_progress_note: 未满建议线报事实+沉淀, 达标主动提示）;
        # 触发与否全权交给 LLM 的剧情判断——紧急/危险场面随时可触发。
        # 2026-09-05: reason 退役——payload 带 chapter_title（本章标题, 触发即命题）;
        # 起因由上下文窗口承载（触发前对话在窗口里, bond 首场自带）
        title = str(action.payload.get("chapter_title") or "").strip()
        suffix = f"（本章: {title}）" if title else ""
        return ExecResult(
            ok=True,
            message=f"羁绊剧情触发成功{suffix}——切换到羁绊剧情模式",
        )

    # ==================================================================
    # 内部
    # ==================================================================
