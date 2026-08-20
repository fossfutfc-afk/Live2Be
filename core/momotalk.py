"""
MomoTalk 对话引擎 — 角色聊天会话管理。

MomoTalk 与羁绊剧情的区别:
    - MomoTalk = 手机聊天界面, 无动作描写, 短消息, 标点分词输出
    - 羁绊剧情 = 视觉小说, 允许动作描写 (括号), 长对白

用法:
    from core.momotalk import MomoTalkEngine, Session
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from errors import err
from llm.client import LLMClient
from llm.prompts import load_prompt
from parsing.dynamic_character_parser import CharacterLoader, DynamicCharacter
from parsing.world_parser import DEFAULT_WORLD_PATH, load_world, world_to_prompt
from ui.text_processors import _process_for_momotalk, format_momotalk_reply

logger = logging.getLogger(__name__)

MAX_HISTORY_ROUNDS = 20
SESSION_DIR = Path("data/sessions")


# ============================================================================
# 会话数据结构辅助类，反正就堆在一起了
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


# ============================================================================
# 引擎
# ============================================================================


class MomoTalkEngine:
    """MomoTalk 对话引擎。

    可在子类中覆盖 _process_reply() 更换输出处理器（羁绊剧情等）。
    """

    def __init__(self, characters_root: str | Path, llm_client: LLMClient):
        self.char_loader = CharacterLoader(characters_root)
        self.llm = llm_client

        self._current_char: DynamicCharacter | None = None
        self._system_prompt: str = ""
        self._history: list[dict[str, str]] = []

    # ------------------------------------------------------------------
    # 公共 API — 会话生命周期
    # ------------------------------------------------------------------

    def start_session(self, character_id: str) -> str:
        char = self.char_loader.load(character_id)
        system_prompt = char.build_prompt("momotalk")

        # 世界观（common + system 档）注入——角色理应知道的世界常识 + 安全边界
        world_chunk = world_to_prompt(load_world(DEFAULT_WORLD_PATH))
        if world_chunk:
            system_prompt += "\n\n" + world_chunk

        system_prompt += "\n\n" + load_prompt("momotalk_environment")
        system_prompt += "\n\n" + load_prompt("momotalk_rules")

        self._current_char = char
        self._system_prompt = system_prompt
        self._history = []

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
        self._char_id = ""

    # ------------------------------------------------------------------
    # 公共 API — 对话
    # ------------------------------------------------------------------

    def send_message(self, user_input: str) -> str:
        """批次模式：等 LLM 完整回复后一次性返回。"""
        if self._current_char is None:
            raise RuntimeError(err("NotInSession", "尚未开始会话"))

        messages = self.llm.format_messages(
            system_prompt=self._system_prompt,
            user_message=user_input,
            history=self._history if self._history else None,
        )

        raw_reply = self.llm.chat(messages, temperature=0.8, max_tokens=512, response_format="text")
        if not isinstance(raw_reply, str):
            raw_reply = str(raw_reply)

        processed = self._process_reply(raw_reply)

        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": processed})
        self._trim_history()

        return processed

    def send_message_stream(self, user_input: str):
        """流式模式（MomoTalk）：yield 格式化气泡 + 延迟。

        用法:
            for bubble, delay in engine.send_message_stream(user_input):
                simulate_typing(bubble, delay)
        """
        if self._current_char is None:
            raise RuntimeError(err("NotInSession", "尚未开始会话"))

        from ui.display import MomoTalkOutput

        messages = self.llm.format_messages(
            system_prompt=self._system_prompt,
            user_message=user_input,
            history=self._history if self._history else None,
        )

        name = self._current_char.display_name if self._current_char else ""
        display = MomoTalkOutput(_process_for_momotalk, name)

        full_text = ""
        for token in self.llm.chat_stream(messages, temperature=0.8, max_tokens=512):
            full_text += token
            yield from display.feed(token)

        yield from display.flush()

        processed = self._process_reply(full_text)
        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": processed})
        self._trim_history()

    # ------------------------------------------------------------------
    # 钩子：输出处理（子类可覆盖）
    # ------------------------------------------------------------------

    def _process_reply(self, raw_text: str) -> str:
        """委托给 text_processors.format_momotalk_reply。"""
        name = self._current_char.display_name if self._current_char else ""
        return format_momotalk_reply(raw_text, name)

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def current_character(self) -> DynamicCharacter | None:
        return self._current_char

    @property
    def _char_id(self) -> str:
        return self._current_char.character_id if self._current_char else ""

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._history)

    @property
    def history_length(self) -> int:
        return len(self._history)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _trim_history(self) -> None:
        max_messages = MAX_HISTORY_ROUNDS * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]
