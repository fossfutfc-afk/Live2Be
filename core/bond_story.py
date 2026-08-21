"""羁绊剧情引擎 — 视觉小说模式对话。

与 MomoTalk 的区别:
    - 不去括号（允许动作描写）
    - 不断句（段落为单位，非气泡）
    - 不加 [名字]: 前缀（UI 层单独显示角色名）

场景契约（2026-08-22 JSON 契约化 + 双核升级, 用户拍板）:
    每场景 = 单个 story 动作 JSON: 中段 story_scene {paragraphs: [str], choices: [str]}
    或收尾 story_end {paragraphs: [str]}。is_end 由动作类型推导——story_scene 隐含
    False, story_end 隐含 True; 收尾成为一等动作, 结构上保证「收尾必无选项」。
    LLM 直接输出场景 JSON——contract.py 既规范输出也规范处理; 选项收敛到同一主线
    （无论选哪个, 剧情走向同一结局, 只影响紧接着的对白语气/细节）。
    双核（镜像 momotalk）: contract 层 core/story_actions.py（build_story_registry）
    + 执行层 core/story_executor.py（StoryExecutor/StoryExecError）, 引擎记 trace。
    BondScene 是契约解析后的程序侧结构; to_dict/from_dict 是序列化唯一路径——
    **一解析器两用**: 运行时 from_action（动作类型推导 is_end）+ 读存档 json[] 回放
    from_dict（存档显式 is_end）（DESIGN_BOND_STORY.md）。
    双空格/【选择】/【完】等自由文本标记解析已删除——结构由 JSON 字段强制。
    行为规则在 llm/prompts/bond_story_rules.md; 契约 schema 由 build_schema 注入。

用法:
    from core.bond_story import BondStoryEngine
    vn = BondStoryEngine(characters_root, llm_client)
    vn.start_session("igusa_haruka")
    scene = vn.send_vn_scene("（开场）")
    for para in scene.paragraphs: ...
    if scene.choices: ...
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from contract import AgentAction, build_schema
from core.common import Live2BeError, err
from core.story_actions import MAX_SCENE_RETRIES, build_story_registry
from core.story_executor import StoryExecError, StoryExecutor
from llm.client import LLMClient
from llm.feedback import feedback
from llm.prompts import load_prompt
from core.parsing.dynamic_character_parser import CharacterLoader, DynamicCharacter
from core.parsing.world_parser import DEFAULT_WORLD_PATH, load_world, world_to_prompt

logger = logging.getLogger(__name__)

MAX_HISTORY_ROUNDS = 20


class SceneLoopError(Live2BeError):
    """单场景解析或执行任一失败超过 MAX_SCENE_RETRIES 仍未通过（循环必须终结, 宁缺勿错）。"""


@dataclass
class BondScene:
    """一个羁绊剧情场景（story_scene 契约解析后的程序侧结构）。

    paragraphs — 叙事段落（数组一项一段）
    choices    — 选项列表（空 = 无选项; 有选项时玩家选一个, 喂回下一场景）
    is_end     — 是否剧情结束（契约 is_end=true）
    """

    paragraphs: list[str] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)
    is_end: bool = False

    def to_dict(self) -> dict:
        """序列化为存档/契约同构 dict（回放读档的反向）。"""
        return {
            "paragraphs": list(self.paragraphs),
            "choices": list(self.choices),
            "is_end": bool(self.is_end),
        }

    @classmethod
    def from_dict(cls, raw: dict | None) -> "BondScene":
        """宽松解析 dict → BondScene（运行时契约解析与回放读档同一条路径）。

        逐字段 .get 容错 + 过滤非 str 项 + is_end 缺省 False——宁缺勿错,
        坏数据不 raise, 只降级为空场景。
        """
        if not isinstance(raw, dict):
            return cls()
        paras = [p for p in raw.get("paragraphs", []) if isinstance(p, str)]
        choices = [c for c in raw.get("choices", []) if isinstance(c, str)]
        return cls(paragraphs=paras, choices=choices, is_end=bool(raw.get("is_end", False)))

    @classmethod
    def from_action(cls, action: "AgentAction") -> "BondScene":
        """运行时契约解析: AgentAction → BondScene, is_end 由动作类型推导。

        story_scene 隐含 is_end=False; story_end 隐含 is_end=True。payload 已过
        parse 白名单（干净字段）, 仍逐字段容错（宁缺勿错）——坏数据降级为空场景。
        """
        payload = action.payload
        return cls(
            paragraphs=[p for p in payload.get("paragraphs", []) if isinstance(p, str)],
            choices=[c for c in payload.get("choices", []) if isinstance(c, str)],
            is_end=(action.action == "story_end"),
        )


class BondStoryEngine:
    """羁绊剧情对话引擎。

    与 MomoTalkEngine 共享相同的 LLMClient / CharacterLoader 模式，
    但输出策略不同：段落分割、不去括号、不加名字前缀。
    """

    def __init__(self, characters_root: str | Path, llm_client: LLMClient):
        self.char_loader = CharacterLoader(characters_root)
        self.llm = llm_client
        self.registry = build_story_registry()
        self.executor = StoryExecutor()
        self._current_char: DynamicCharacter | None = None
        self._system_prompt: str = ""
        self._history: list[dict[str, str]] = []
        self._trace: list[dict] = []      # 最近一次 send_vn_scene 的动作轨迹（追溯/调试）

    # ------------------------------------------------------------------
    # 会话生命周期
    # ------------------------------------------------------------------

    def start_session(self, character_id: str) -> str:
        char = self.char_loader.load(character_id)
        system_prompt = char.build_prompt("bond_story")

        # 世界观（common + system 档）注入——角色理应知道的世界常识 + 安全边界
        world_chunk = world_to_prompt(load_world(DEFAULT_WORLD_PATH))
        if world_chunk:
            system_prompt += "\n\n" + world_chunk

        system_prompt += "\n\n" + load_prompt("bond_story_rules")
        # 场景契约 schema（story_scene 动作）——momotalk 同款注入, LLM 看到字段约束
        system_prompt += "\n\n可用动作 schema:\n" + build_schema(self.registry)

        self._current_char = char
        self._system_prompt = system_prompt
        self._history = []
        self._trace = []

        logger.info("新羁绊剧情会话: %s (%s)", character_id, char.display_name)
        return char.display_name

    # ------------------------------------------------------------------
    # 对话
    # ------------------------------------------------------------------

    def send_vn_scene(
        self,
        user_input: str,
        max_tokens: int = 1536,
        system_note: str | None = None,
    ) -> BondScene:
        """结构化场景 API：单次 LLM 调用 → BondScene（段落 + 选项 + 是否结束）。

        LLM 直接输出 story_scene/story_end 契约 JSON（json_object 模式, 内部已有
        3 次语法自纠错）; 外层再做解析/执行重试（双核: registry.parse + executor.
        execute, 任一失败 → feedback 回灌, 最多 MAX_SCENE_RETRIES 次）, 耗尽抛
        SceneLoopError（宁缺勿错: 循环必须终结）。每轮成功/失败都记入 trace。

        system_note: 本轮系统注记（只进 context 不入历史, 最近位置最醒目）——
        双层收尾机制用: 轮数提醒 / 达上限建议收尾。None = 不注入。
        """
        if self._current_char is None:
            raise RuntimeError(err("NotInSession", "尚未开始会话"))

        self._trace = []

        if system_note:
            # 手动组装: system + history + system_note(最近) + user
            messages = [{"role": "system", "content": self._system_prompt}]
            if self._history:
                messages.extend(self._history)
            messages.append({"role": "system", "content": system_note})
            messages.append({"role": "user", "content": user_input})
        else:
            messages = self.llm.format_messages(
                system_prompt=self._system_prompt,
                user_message=user_input,
                history=self._history if self._history else None,
            )

        for attempt in range(MAX_SCENE_RETRIES):
            try:
                response = self.llm.chat(
                    messages, temperature=0.8, max_tokens=max_tokens,
                    response_format="json_object",
                )
            except Exception as e:
                logger.warning("LLM 调用失败（第 %d 次）: %s", attempt, e)
                feedback(messages, f"LLM 调用失败: {e}\n请重试。")
                continue
            messages.append({"role": "assistant", "content": str(response)})

            # 1) 契约解析（动作无效 → 回灌修正）
            action, result = self.registry.parse(response)
            self._trace.append({
                "attempt": attempt,
                "action": action.action if action else None,
                "summary": action.summary if action else "",
                "reply": action.reply if action else "",
                "payload": action.payload if action else None,
                "parse_valid": result.is_valid,
                "parse_errors": list(result.errors),
            })
            if not result.is_valid:
                feedback(
                    messages,
                    f"动作无效: {'; '.join(result.errors)}",
                    "请严格按 schema 重新输出单个 story_scene 或 story_end 动作 JSON。",
                )
                continue

            # 2) 执行确认（不可执行 → 回灌修正）
            try:
                exec_result = self.executor.execute(action)
            except StoryExecError as e:
                self._trace[-1]["exec_message"] = str(e)
                feedback(messages, str(e))
                continue
            self._trace[-1]["exec_ok"] = exec_result.ok
            self._trace[-1]["exec_message"] = exec_result.message
            break
        else:
            raise SceneLoopError(
                f"单场景解析或执行超过 {MAX_SCENE_RETRIES} 次仍未通过"
            )

        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": json.dumps(
            action.payload, ensure_ascii=False, separators=(",", ":"))})
        self._trim_history()
        return BondScene.from_action(action)

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def current_character(self) -> DynamicCharacter | None:
        return self._current_char

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._history)

    @property
    def history_length(self) -> int:
        return len(self._history)

    @property
    def trace(self) -> list[dict]:
        """最近一次 send_vn_scene 的动作轨迹（attempt/action/payload/解析/执行结果）。"""
        return list(self._trace)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _trim_history(self) -> None:
        max_messages = MAX_HISTORY_ROUNDS * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]
