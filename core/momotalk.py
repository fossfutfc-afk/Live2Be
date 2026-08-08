"""
MomoTalk 对话引擎 — 角色聊天会话管理。

职责:
    - 载入角色 → 构建 System Prompt
    - 管理对话历史（滑动窗口）
    - 调用 LLM 生成回复
    - 会话保存 / 加载 / 恢复

不负责 UI 循环 — 那在 main.py 中。

用法:
    from core.momotalk import MomoTalkEngine, Session

    engine = MomoTalkEngine("config/characters", client)

    # 新对话
    engine.start_session("igusa_haruka")
    reply = engine.send_message("你好")

    # 保存 + 下次恢复
    engine.save_session()
    # ... 程序重启 ...
    session = engine.resume_session("data/sessions/igusa_haruka_2026-08-08.json")
    reply = engine.send_message("还记得我们上次聊的吗？")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from llm.client import LLMClient
from parsing.dynamic_character_parser import CharacterLoader, DynamicCharacter

logger = logging.getLogger(__name__)

# ============================================================================
# 配置常量
# ============================================================================

MAX_HISTORY_ROUNDS = 20          # 滑动窗口：保留最近 N 轮对话
SESSION_DIR = Path("data/sessions")

# ============================================================================
# 会话数据结构
# ============================================================================


@dataclass
class Session:
    """对话会话的完整状态（可序列化）。"""
    character_id: str
    character_name: str
    history: list[dict[str, str]] = field(default_factory=list)
    created_at: str = ""

    def to_json(self, path: Path) -> None:
        """写入 JSON 文件。"""
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({
                "character_id": self.character_id,
                "character_name": self.character_name,
                "created_at": self.created_at or datetime.now().isoformat(),
                "messages": self.history,
            }, fh, ensure_ascii=False, indent=2)

    @staticmethod
    def from_json(path: Path) -> "Session":
        """从 JSON 文件读取。"""
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

    一个引擎实例可复用，start_session() 会重置状态。
    """

    def __init__(self, characters_root: str | Path, llm_client: LLMClient):
        self.char_loader = CharacterLoader(characters_root)
        self.llm = llm_client

        # 运行时状态
        self._current_char: DynamicCharacter | None = None
        self._system_prompt: str = ""
        self._history: list[dict[str, str]] = []

    # ------------------------------------------------------------------
    # 公共 API — 会话生命周期
    # ------------------------------------------------------------------

    def start_session(self, character_id: str) -> str:
        """载入角色并开始新对话。

        Returns:
            角色的显示名（给 UI 显示用）。
        """
        char = self.char_loader.load(character_id)

        system_prompt = char.build_prompt("momotalk")
        if char.is_official and char.completeness.get("ratio", 1.0) < 0.5:
            system_prompt += (
                "\n\n注意：上述角色信息较为简略。"
                "你是该角色的官方设定，你可以在自己知识库中检索该角色的完整人设信息，"
                "并以该角色的身份进行回应。请严格依据官方设定，不得编造。"
            )

        self._current_char = char
        self._system_prompt = system_prompt
        self._history = []

        logger.info("新会话: %s (%s)", character_id, char.display_name)
        return char.display_name

    def resume_session(self, session_path: str | Path) -> Session:
        """从保存文件恢复会话。

        载入角色 → 恢复历史 → 可以继续对话。
        传入的 path 是之前 save_session() 保存的 JSON 文件。
        """
        session = Session.from_json(Path(session_path))

        # 必须先载入角色以重建 System Prompt
        self.start_session(session.character_id)
        self._history = session.history

        logger.info(
            "恢复会话: %s (%d 条历史)",
            session.character_id,
            len(session.history),
        )
        return session

    def save_session(self, path: str | Path | None = None) -> Path:
        """保存当前会话到 JSON 文件。

        Returns:
            实际保存路径。
        """
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
        """重置引擎状态（不保存）。"""
        self._current_char = None
        self._system_prompt = ""
        self._history = []
        self._char_id = ""

    # ------------------------------------------------------------------
    # 公共 API — 对话
    # ------------------------------------------------------------------

    def send_message(self, user_input: str) -> str:
        """发送玩家消息，返回角色回复。

        Raises:
            RuntimeError: 尚未调用 start_session / resume_session
        """
        if self._current_char is None:
            raise RuntimeError("尚未开始会话，请先调用 start_session() 或 resume_session()")

        # 一行构建 messages（LLMClient 已有 format_messages）
        messages = self.llm.format_messages(
            system_prompt=self._system_prompt,
            user_message=user_input,
            history=self._history if self._history else None,
        )

        reply_text = self.llm.chat(messages, temperature=0.8, max_tokens=512, response_format="text")
        if not isinstance(reply_text, str):
            reply_text = str(reply_text)

        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": reply_text})
        self._trim_history()

        return reply_text

    # ------------------------------------------------------------------
    # 便捷属性 (供 UI 使用)
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
        """滑动窗口截断。"""
        max_messages = MAX_HISTORY_ROUNDS * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]
