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
    mmt_trigger_bond_story   触发判定——软门槛（轮数参考注入 LLM, AI 有裁决权）,
                             程序只兜底首条消息; true 切换羁绊剧情模式

信息架构（v2 五层认知, 与 mmt_actions 一致）:
    L0 自我层 / L1 人际层（自表条目注入, self_entry_to_prompt）/ L2 硬知识 / L3 深挖层。
    inspect 是 L3 的门控入口: 无记录=素不相识 → 拒绝, LLM 用知识回答公开信息。

设计决策:
    - 执行器持有会话当前角色（set_current_character）, inspect/trigger 依赖它。
    - 自检防护（双重）: 本文件抛 MmtExecError 代码级报错 + mmt_actions schema 提示。
    - 无记录≠不认识: 无记录=素不相识（可耳闻）, inspect 拒绝但可凭知识回答。
    - 自表条目注入: self_entry_to_prompt 生成 L1 注入文本, 由 momotalk 拼进 system prompt。
    - 触发 bool: 轮数参考（_affection_score, 已接入 bond_progress）+ LLM 决策;
      软门槛——AI 可提前触发（老师有急事等剧情需要）, 程序只兜底首条消息（0 轮）。
    - 人际层工具（load_interperson / resolve_access_level / self_entry_to_prompt）
      当前内联在本文件, 待 core/parsing/relation_parser.py 落地后移入。
    - 错误统一走 MmtExecError（Live2BeError 子类）, 由调用方捕获回灌。

TODO（后续 session）:
    - core/parsing/relation_parser.py: 移入人际层工具
    - 媒体管线（存储/查库/LLM 生成）落地后替换 _execute_mmt_send_media 的占位
      （羁绊触发门槛已接入 core/bond/bond_progress.py 轮数, 2026-08-21）
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.common import Live2BeError
from contract import AgentAction, DOMAIN_MMT
from core.bond.bond_progress import BondProgress
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
        affection_threshold: int = 6,
        bond_progress: BondProgress | None = None,
    ):
        self.char_loader = CharacterLoader(characters_root)
        self.interperson_path = (
            Path(interperson_path) if interperson_path
            else Path(DEFAULT_INTERPERSON_PATH)
        )
        # 羁绊触发参考轮数（默认 5）——软门槛: 注入 LLM 作参考建议, 不硬拦截;
        # 程序只在首条消息（0 轮）兜底拒绝。见 core/bond/bond_progress.py。
        self.affection_threshold = affection_threshold
        self.bond_progress = bond_progress or BondProgress()
        self.current_char: DynamicCharacter | None = None
        # 本段会话轮数（2026-09-02: 触发节奏按"本段相处"而非全局累计——
        # 全局累计几百轮后 LLM 会在新会话第 3 轮就贸然触发; momotalk 每轮同步）
        self.session_rounds: int = 0

    # ------------------------------------------------------------------
    # 会话上下文
    # ------------------------------------------------------------------

    def set_current_character(self, char: DynamicCharacter | None) -> None:
        """设置会话当前角色（inspect/trigger 依赖它）。"""
        self.current_char = char

    def set_session_rounds(self, rounds: int) -> None:
        """同步本段会话轮数（momotalk 每轮落盘后调用——触发门槛判定用）。"""
        self.session_rounds = max(0, int(rounds))

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

        # 2026-09-02 定稿（用户拍板）: 触发节奏归程序——距上次**完整** bond 剧情
        # 的 MMT 轮数（_bond_gap, 持久化, 由 momotalk 每轮同步）≥ threshold 才
        # 放行; 不足 → 硬拒（拒消息回灌, LLM 自然转聊天——不靠话术自觉）。
        # 刚演完剧情清零 → 冷却 = 门槛本身（防连发/防"演完立刻又主动"）。
        # 全局累计轮数不再参与判定（只作偏好统计/注记事实）。
        score = self._affection_score()
        if self.affection_threshold > 0 and score < self.affection_threshold:
            raise MmtExecError(
                f"羁绊剧情暂不触发——距上次剧情才聊 {score} 轮, 系统要求至少 "
                f"{self.affection_threshold} 轮; 先自然聊几句, 让故事继续发展"
            )

        reason = action.payload["reason"]
        suffix = f"（理由: {reason}）" if reason else ""
        return ExecResult(
            ok=True,
            message=f"羁绊剧情触发成功{suffix}——切换到羁绊剧情模式",
        )

    # ==================================================================
    # 内部
    # ==================================================================

    def _affection_score(self) -> int:
        """触发门槛计数 = 距上次完整 bond 剧情的 MMT 轮数（2026-09-02 定稿）。

        momotalk 每轮同步（set_session_rounds）: 持久 progress.json 的
        rounds_since_bond（断线/重启继续累计）; 完整剧情结束清零。
        方法名保留历史命名; 无当前角色 → 0。门槛校验读它真实生效。
        """
        if self.current_char is None:
            return 0
        return self.session_rounds
