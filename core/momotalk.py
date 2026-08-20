"""
MomoTalk 对话引擎 — 全 JSON 动作 agent loop。

每轮对话（agent_turn）:
    用户输入 → LLM 输出单个动作 JSON（mmt_ 前缀）→ registry.parse 契约解析
    → 执行器执行（MmtExecError 回灌修正）→ 静默动作（inspect）结果回灌 LLM
    继续推理, 直到产生用户可见输出（mmt_chat / mmt_send_media）或触发羁绊
    剧情（mmt_trigger_bond_story）才结束本轮。

历史格式（每轮至少记动作名 + reply, 可追溯 agent 干了什么）:
    user:      用户说的话
    assistant: "[mmt_chat] 今天谢谢你！" / "[mmt_send_media] 你看这张！"

五层认知（与 mmt_actions / mmt_executor 一致）:
    L0 自我层   build_prompt("momotalk") + 世界观（common+system 档）→ 常驻
    L1 人际层   interperson 自表条目注入（self_entry_to_prompt）→ 常驻
    L2 硬知识   LLM 世界知识 + 知识库（规划中）
    L3 深挖层   mmt_inspect_character（静默推理轮, 权重分级）→ 仅此入口

MomoTalk 与羁绊剧情的区别:
    - MomoTalk = 手机聊天, 无动作描写, 短消息, 逐块输出（…打字指示 + 气泡）
    - 羁绊剧情 = 视觉小说, 允许动作描写（括号）, 长对白（BondStoryEngine）

用法:
    engine = MomoTalkEngine("config/characters", llm_client)
    engine.start_session("haruka")
    result = engine.agent_turn("我们去天台吧？")
    for step in result.steps:   # …打字指示 + 气泡, 依序渲染
        ...
    engine.save_session()
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from errors import Live2BeError, err
from llm.client import LLMClient
from llm.prompts import load_prompt
from llm.feedback import feedback
from contract import AgentAction, build_schema
from core.mmt.mmt_actions import build_mmt_registry
from core.mmt.mmt_executor import (
    ExecResult,
    MmtExecError,
    MmtExecutor,
    load_interperson,
    self_entry_to_prompt,
)
from core.parsing.dynamic_character_parser import CharacterLoader, DynamicCharacter
from core.parsing.world_parser import DEFAULT_WORLD_PATH, load_world, world_to_prompt
from core.ui.display import MomoTalkOutput
from core.ui.streaming import DisplayStep
from core.ui.text_processors import _process_for_momotalk

logger = logging.getLogger(__name__)

MAX_HISTORY_ROUNDS = 20
SESSION_DIR = Path("data/sessions")

# agent loop 参数
MAX_STEPS = 6          # 单轮动作步数上限（含 inspect 静默轮）
TEMP = 0.8             # 与旧 send_message 一致
MMT_MAX_TOKENS = 4096  # 动作 JSON + 对白（推理模型需大 max_tokens, 勿改小）


class MmtLoopError(Live2BeError):
    """MomoTalk agent loop 错误（步数耗尽等）。message 供调用方展示/重试。

    __str__ 自动产出 [momotalk.py][MmtLoopError][message]。
    """


# ============================================================================
# 会话数据结构辅助类
# ============================================================================


@dataclass
class Session:
    """对话会话的完整状态（可序列化）。"""
    character_id: str
    character_name: str
    history: list[dict[str, str]] = field(default_factory=list)
    created_at: str = ""

    def to_json(self, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({
                "character_id": self.character_id,
                "character_name": self.character_name,
                "created_at": self.created_at or datetime.now().isoformat(),
                "messages": self.history,
            }, fh, ensure_ascii=False, indent=2)

    @staticmethod
    def from_json(path: Path) -> "Session":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return Session(
            character_id=data.get("character_id", ""),
            character_name=data.get("character_name", ""),
            history=data.get("messages", []),
            created_at=data.get("created_at", ""),
        )


@dataclass
class TurnResult:
    """一轮 agent 对话的结果。

    steps      — 显示步骤序列（…打字指示 + 气泡）, 由 UI 依序渲染
    reply      — 完整对白（不含名字前缀, 历史存档用; 可能为空）
    action     — 终止动作名（mmt_chat / mmt_send_media / mmt_trigger_bond_story）
    payload    — 终止动作的干净 payload（GUI 可渲染媒体等）
    bond_story — True = 触发羁绊剧情成功, 调用方应切换到羁绊剧情模式
    error      — ok=False 时的原因（预留; 当前异常走 MmtLoopError）
    """
    ok: bool = True
    steps: list[DisplayStep] = field(default_factory=list)
    reply: str = ""
    action: str = ""
    payload: dict = field(default_factory=dict)
    bond_story: bool = False
    error: str = ""


# ============================================================================
# 引擎
# ============================================================================


class MomoTalkEngine:
    """MomoTalk 对话引擎 — 会话生命周期 + 全 JSON 动作 agent loop。"""

    def __init__(
        self,
        characters_root: str | Path,
        llm_client: LLMClient,
        interperson_path: str | Path | None = None,
        player_name: str | None = None,
    ):
        self.char_loader = CharacterLoader(characters_root)
        self.llm = llm_client
        self.registry = build_mmt_registry()
        self.executor = MmtExecutor(characters_root, interperson_path)

        self._player_name = (player_name or "").strip()   # 玩家称呼（可选, 注入 system prompt）
        self._current_char: DynamicCharacter | None = None
        self._system_prompt: str = ""
        self._history: list[dict[str, str]] = []
        self._trace: list[dict] = []      # 最近一轮的完整动作轨迹（追溯/调试）

    # ------------------------------------------------------------------
    # 公共 API — 会话生命周期
    # ------------------------------------------------------------------

    def start_session(self, character_id: str) -> str:
        char = self.char_loader.load(character_id)

        sp = char.build_prompt("momotalk")          # L0 自我层: 完整人设 + 行为约束

        world_chunk = world_to_prompt(load_world(DEFAULT_WORLD_PATH))
        if world_chunk:                              # 世界观（common + system 档）
            sp += "\n\n" + world_chunk

        try:                                         # L1 人际层: 自表条目注入（键值+权重）
            interperson = load_interperson(self.executor.interperson_path)
        except MmtExecError as e:                    # 文件损坏 → 跳过注入, 不挡会话启动
            logger.warning("interperson 读取失败, 跳过 L1 注入: %s", e)
            interperson = {}
        entry = self_entry_to_prompt(interperson, char.character_id)
        if entry:
            sp += "\n\n" + entry

        if self._player_name:                        # 玩家称呼: 角色该知道怎么叫玩家
            sp += f"\n\n玩家称呼（你的对话对象）: {self._player_name}"

        sp += "\n\n" + load_prompt("momotalk_environment")
        sp += "\n\n" + load_prompt("momotalk_rules")
        sp += "\n\n可用动作 schema:\n" + build_schema(self.registry)

        self._current_char = char
        self._system_prompt = sp
        self._history = []
        self._trace = []
        self.executor.set_current_character(char)   # inspect/trigger 依赖会话角色

        logger.info("新会话: %s (%s)", character_id, char.display_name)
        return char.display_name

    def resume_session(self, session_path: str | Path) -> Session:
        session = Session.from_json(Path(session_path))
        self.start_session(session.character_id)
        self._history = session.history
        logger.info("恢复会话: %s (%d 条历史)", session.character_id, len(session.history))
        return session

    def save_session(self, path: str | Path | None = None) -> Path:
        if path is None:
            SESSION_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            path = SESSION_DIR / f"{self._char_id}_{ts}.json"
        Session(
            character_id=self._char_id,
            character_name=self._current_char.display_name if self._current_char else "",
            history=list(self._history),
            created_at=datetime.now().isoformat(),
        ).to_json(Path(path))
        logger.info("会话已保存: %s (%d 条消息)", path, len(self._history))
        return Path(path)

    def clear(self) -> None:
        self._current_char = None
        self._system_prompt = ""
        self._history = []
        self._trace = []
        self.executor.set_current_character(None)

    # ------------------------------------------------------------------
    # 公共 API — 对话（全 JSON 动作 loop）
    # ------------------------------------------------------------------

    def agent_turn(self, user_input: str) -> TurnResult:
        """一轮 agent 对话：LLM 动作循环, 直到用户可见输出 / 羁绊触发。

        循环内:
            LLM 决策（json_object）→ registry.parse 契约解析
            → 解析无效 / 执行不可行（MmtExecError）→ feedback 回灌修正, 重试
            → mmt_inspect_character 结果回灌 LLM 继续推理（静默, 玩家不可见）
            → mmt_chat / mmt_send_media / mmt_trigger_bond_story 结束本轮

        步数耗尽仍未产出可见回复 → 抛 MmtLoopError（调用方展示/重试）。
        """
        if self._current_char is None:
            raise RuntimeError(err("NotInSession", "尚未开始会话"))

        self._trace = []
        messages = [{"role": "system", "content": self._system_prompt}]
        messages.extend(self._history)
        messages.append({"role": "user", "content": user_input})

        for step in range(MAX_STEPS):
            # 1) LLM 决策（json_object 已内置 JSON 清洗与修正重试, 返回 dict）
            try:
                response = self.llm.chat(
                    messages, temperature=TEMP, max_tokens=MMT_MAX_TOKENS,
                    response_format="json_object",
                )
            except Exception as e:
                logger.warning("LLM 调用失败（step %d）: %s", step, e)
                feedback(messages, f"LLM 调用失败: {e}\n请重试。")
                continue
            messages.append({"role": "assistant", "content": str(response)})

            # 2) 契约解析
            action, result = self.registry.parse(response)
            self._trace.append({
                "step": step,
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
                    "请严格按 schema 重新输出单个 mmt 动作 JSON。",
                )
                continue

            # 3) 执行（不可执行 → 回灌修正）
            try:
                exec_result = self.executor.execute(action)
            except MmtExecError as e:
                self._trace[-1]["exec_message"] = str(e)
                feedback(messages, str(e))
                continue
            self._trace[-1]["exec_ok"] = exec_result.ok
            self._trace[-1]["exec_message"] = exec_result.message

            # 4) 静默动作: inspect 结果回灌 LLM, 玩家不可见, 继续推理
            if action.action == "mmt_inspect_character":
                messages.append({"role": "user", "content": exec_result.message})
                continue

            # 5) 用户可见输出 → 结束本轮
            return self._finish_turn(action, exec_result, user_input)

        raise MmtLoopError(f"单轮动作循环超过 {MAX_STEPS} 步仍未产出可见回复")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _finish_turn(
        self, action: AgentAction, exec_result: ExecResult, user_input: str
    ) -> TurnResult:
        """终结动作 → 渲染显示步骤 + 存档历史 + 组装 TurnResult。"""
        reply = (action.reply or "").strip()

        # 显示步骤: …打字指示 + 气泡（对白逐块; 无对白 → 空, 媒体由 GUI 用 payload 渲染）
        display = MomoTalkOutput(_process_for_momotalk, self._current_char.display_name)
        steps = display.publish_reply(reply)

        # 历史: 每轮至少记动作名 + reply（可追溯 agent 干了什么）
        self._history.append({"role": "user", "content": user_input})
        self._history.append({
            "role": "assistant",
            "content": f"[{action.action}] {reply}" if reply else f"[{action.action}]",
        })
        self._trim_history()

        return TurnResult(
            ok=True,
            steps=steps,
            reply=reply,
            action=action.action,
            payload=action.payload,
            bond_story=(action.action == "mmt_trigger_bond_story"),
        )

    def _trim_history(self) -> None:
        max_messages = MAX_HISTORY_ROUNDS * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def current_character(self) -> DynamicCharacter | None:
        return self._current_char

    @property
    def player_name(self) -> str:
        """玩家称呼（注入 system prompt; 会话开始前设置才生效）。"""
        return self._player_name

    @player_name.setter
    def player_name(self, value: str | None) -> None:
        self._player_name = (value or "").strip()

    @property
    def _char_id(self) -> str:
        return self._current_char.character_id if self._current_char else ""

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._history)

    @property
    def history_length(self) -> int:
        return len(self._history)

    @property
    def trace(self) -> list[dict]:
        """最近一轮的完整动作轨迹（每步: action/summary/reply/payload/执行结果）。"""
        return list(self._trace)
