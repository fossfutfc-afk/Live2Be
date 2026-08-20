"""羁绊剧情引擎 — 视觉小说模式对话。

与 MomoTalk 的区别:
    - 不去括号（允许动作描写）
    - 不断句（段落为单位，非气泡）
    - 不加 [名字]: 前缀（UI 层单独显示角色名）

用法:
    from core.bond_story import BondStoryEngine
"""

from __future__ import annotations

import logging
from pathlib import Path

from errors import err
from llm.client import LLMClient
from parsing.dynamic_character_parser import CharacterLoader, DynamicCharacter

logger = logging.getLogger(__name__)

MAX_HISTORY_ROUNDS = 20


class BondStoryEngine:
    """羁绊剧情对话引擎。

    与 MomoTalkEngine 共享相同的 LLMClient / CharacterLoader 模式，
    但输出策略不同：段落分割、不去括号、不加名字前缀。
    """

    def __init__(self, characters_root: str | Path, llm_client: LLMClient):
        self.char_loader = CharacterLoader(characters_root)
        self.llm = llm_client
        self._current_char: DynamicCharacter | None = None
        self._system_prompt: str = ""
        self._history: list[dict[str, str]] = []

    # ------------------------------------------------------------------
    # 会话生命周期
    # ------------------------------------------------------------------

    def start_session(self, character_id: str) -> str:
        char = self.char_loader.load(character_id)
        system_prompt = char.build_prompt("bond_story")

        rules = (
            "你正在与 sensei 进行面对面的交流。\n"
            "可以包含动作描写（用括号标注），可以有多段落的长对白。\n"
            "你不是 AI——你就是角色本人。"
        )
        system_prompt += "\n\n【羁绊剧情 回复规则】\n" + rules

        self._current_char = char
        self._system_prompt = system_prompt
        self._history = []

        logger.info("新羁绊剧情会话: %s (%s)", character_id, char.display_name)
        return char.display_name

    # ------------------------------------------------------------------
    # 对话
    # ------------------------------------------------------------------

    def send_vn_stream(self, user_input: str):
        """流式模式：yield (paragraph_text, is_last) 元组。

        与 MomoTalk 不同：不去括号、不断句、不加前缀。
        UI 层负责逐字打字动画 + Enter 推进到下一段。
        """
        if self._current_char is None:
            raise RuntimeError(err("NotInSession", "尚未开始会话"))

        from ui.display import BondStoryOutput

        messages = self.llm.format_messages(
            system_prompt=self._system_prompt,
            user_message=user_input,
            history=self._history if self._history else None,
        )

        display = BondStoryOutput()

        full_text = ""
        for token in self.llm.chat_stream(messages, temperature=0.8, max_tokens=1024):
            full_text += token
            display.feed(token)

        paragraphs = display.flush()
        for i, para in enumerate(paragraphs):
            yield para, i == len(paragraphs) - 1

        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": full_text})
        self._trim_history()

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

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _trim_history(self) -> None:
        max_messages = MAX_HISTORY_ROUNDS * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]
