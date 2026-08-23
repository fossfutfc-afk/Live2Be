"""STORY + MEMORIAL 执行层 — 校验 + trace, 无副作用（历史/存档由引擎与 UI 负责）。

契约层只解析动作（纯结构校验）; 执行层做域校验与动作名分派。story 域动作是
纯输出契约——VN 每场景就是一条 story_scene/story_end, 程序不执行媒体/立绘等
副作用, 执行器只确认「场景已就绪」供引擎记 trace 留痕。memorial 域（memorial_
exit）同理——纯状态确认, 立绘生成由引擎/UI 负责（§4.7）。

存档分工（用户拍板, 2026-08-22; 2026-08-24 单流修订）:
    executor 只管校验 + trace; 落盘由 core/ui/vn_cli.py 统一 append 进事件流
    （type=bond 事件含 input/picked）——picked=玩家选择在场景渲染后才得知,
    只有 vn_cli 掌握。历史记录由 core/bond_story.BondStoryEngine 负责。

设计决策:
    - 守卫极简（宁缺勿错、不过度拒绝）: 空 paragraphs 已在 parse 层 ContractError
      兜底; 段落数上限不做（max_tokens 天然约束 + 拒绝只烧 token）。genuine
      拒绝仅域校验 + 未知动作。
    - ExecResult 复用 MMT 域（core/mmt/mmt_executor.ExecResult）——单一 canonical
      形状, 无循环依赖（mmt_executor 不引用本模块）。
    - 无构造函数, 动作自包含——story/memorial 域动作不依赖会话上下文（不像 MMT
      的 inspect/trigger 需要当前角色）。状态机约束（纪念模式内只许 exit 等）
      在引擎层 send_vn_scene 做（§4.7）, 执行层不管状态。
"""

from __future__ import annotations

from core.common import Live2BeError
from contract import AgentAction, DOMAIN_MEMORIAL, DOMAIN_STORY
from core.mmt.mmt_executor import ExecResult


class StoryExecError(Live2BeError):
    """STORY 执行层拒绝/失败。message 供调用方回灌给 LLM 修正。

    __str__ 自动产出 [story_executor.py][StoryExecError][message]。
    """


class StoryExecutor:
    """STORY/MEMORIAL 动作执行器。无构造函数——动作自包含, 不依赖会话上下文。"""

    def execute(self, action: AgentAction) -> ExecResult:
        """执行一个已通过契约校验的 VN 动作（story 域 + memorial 域）。

        抛 StoryExecError 表示不可执行。统一入口: 按动作名分派到
        _execute_{action}。调用方捕获 StoryExecError 并把 message 回灌给 LLM
        （见 core/bond_story.send_vn_scene）。
        """
        if action.domain not in (DOMAIN_STORY, DOMAIN_MEMORIAL):
            raise StoryExecError(f"非 VN 域动作: {action.domain}:{action.action}")
        handler = getattr(self, f"_execute_{action.action}", None)
        if handler is None:
            raise StoryExecError(f"未知执行动作: {action.action}")
        return handler(action)

    # ==================================================================
    # story_scene — 中段场景（is_end 隐含 False）
    # ==================================================================

    def _execute_story_scene(self, action: AgentAction) -> ExecResult:
        """中段场景确认——段落/选项已就绪, 渲染与存档由引擎与 UI 负责。"""
        return ExecResult(ok=True, message="中段场景已就绪")

    # ==================================================================
    # story_end — 收尾场景（is_end 隐含 True）
    # ==================================================================

    def _execute_story_end(self, action: AgentAction) -> ExecResult:
        """收尾场景确认——输出后剧情结束。渲染与存档由引擎与 UI 负责。"""
        return ExecResult(ok=True, message="收尾场景已就绪, 剧情将结束")

    # ==================================================================
    # memorial_enter — 进入纪念子模式（story 域, §4.7）
    # ==================================================================

    def _execute_memorial_enter(self, action: AgentAction) -> ExecResult:
        """纪念进入确认——生图/渲染/事件由引擎与 UI 负责（含 l2d 事件 + marker）。"""
        return ExecResult(ok=True, message="纪念进入已就绪")

    # ==================================================================
    # memorial_exit — 纪念模式收尾（memorial 域, §4.7）
    # ==================================================================

    def _execute_memorial_exit(self, action: AgentAction) -> ExecResult:
        """纪念收尾确认——marker memorial_exit 由 UI 落盘, 执行层无副作用。"""
        return ExecResult(ok=True, message="纪念收尾已就绪, 回到 bond")
