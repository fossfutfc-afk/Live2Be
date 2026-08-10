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
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from llm.client import LLMClient
from parsing.dynamic_character_parser import CharacterLoader, DynamicCharacter
from core.text_processors import _process_for_momotalk

logger = logging.getLogger(__name__)

MAX_HISTORY_ROUNDS = 20
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

        on_phone = (
            "MomoTalk 是纯文字聊天——没有图片/语音/视频/文件传输能力。\n"
            "当 sensei 向你要照片/语音/视频/定位/自拍/实物时，\n"
            "不要承认你是 AI。像真人一样，描述你能看到或记得的东西即可：\n"
            "  · 照片 → 选一张相册里的旧照片，描述内容\n"
            "  · 语音 → 用文字转述你想说的话\n"
            "  · 视频通话 → 用文字描述你当前看到的画面\n"
            "  · 定位 → 描述你所在地方的环境标志物\n"
            "  · 实物/礼物 → 解释不巧不在手边，描述样子和回忆"
        )
        system_prompt += "\n\n【MomoTalk 环境说明】\n" + on_phone

        rules = (
            "简短自然，像 LINE/微信聊天，每次 1-3 句话。\n"
            "你不是 AI——你就是本人，通过手机和 sensei 聊天。"
        )
        system_prompt += "\n\n【MomoTalk 回复规则】\n" + rules

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
            raise RuntimeError("尚未开始会话")

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
        """流式模式：yield 每个完整气泡（带延迟信息）。

        用法:
            for bubble, delay in engine.send_message_stream(user_input):
                simulate_typing(bubble, delay)
        """
        if self._current_char is None:
            raise RuntimeError("尚未开始会话")

        from core.streaming import LineBuffer, TypingDelay

        messages = self.llm.format_messages(
            system_prompt=self._system_prompt,
            user_message=user_input,
            history=self._history if self._history else None,
        )

        lb = LineBuffer()
        TypingDelay.reset()
        full_text = ""
        name = self._current_char.display_name if self._current_char else ""

        for token in self.llm.chat_stream(messages, temperature=0.8, max_tokens=512):
            full_text += token
            for bubble in lb.feed(token):
                for b in _process_for_momotalk(bubble):
                    yield f"[{name}]: {b}", TypingDelay.for_bubble(b)

        # 流结束，把残留走精切 + 输入历史
        remaining = lb.flush()
        if remaining:
            for b in _process_for_momotalk(remaining):
                yield f"[{name}]: {b}", TypingDelay.for_bubble(b)

        processed = self._process_reply(full_text)
        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": processed})
        self._trim_history()

    # ------------------------------------------------------------------
    # 钩子：输出处理（子类可覆盖）
    # ------------------------------------------------------------------

    def _process_reply(self, raw_text: str) -> str:
        """MomoTalk 格式处理：去动作括号 + 断句 + 加角色名前缀。"""
        bubbles = _process_for_momotalk(raw_text)
        name = self._current_char.display_name if self._current_char else ""

        if not name:
            return "\n".join(bubbles)

        clean: list[str] = []
        for b in bubbles:
            for pat in [
                rf"^{re.escape(name)}\s*[：:]\s*",
                rf"^\[{re.escape(name)}[：:\s\]]*\]?\s*",
                rf"^【{re.escape(name)}】\s*",
            ]:
                b = re.sub(pat, "", b)
            b = b.strip()
            if b:
                clean.append(b)

        return "\n".join(f"[{name}]: {b}" for b in clean) if clean else ""

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
