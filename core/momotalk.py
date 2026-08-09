"""
MomoTalk 对话引擎 — 角色聊天会话管理。

MomoTalk 与羁绊剧情的区别:
    - MomoTalk = 手机聊天界面, 无动作描写, 短消息, 对标准标点分词输出
    - 羁绊剧情 = 视觉小说, 允许动作描写 (括号), 长对白
    - 本模块中的 _strip_action_brackets() / _split_for_momotalk()
      是 MomoTalk 特化处理器; 羁绊剧情不使用它们。

用法:
    from core.momotalk import MomoTalkEngine, Session

    engine = MomoTalkEngine("config/characters", client)
    engine.start_session("igusa_haruka")
    reply = engine.send_message("你好")          # 自动处理 → MomoTalk 格式
    engine.save_session()
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

logger = logging.getLogger(__name__)

# ============================================================================
# 配置常量
# ============================================================================

MAX_HISTORY_ROUNDS = 20
SESSION_DIR = Path("data/sessions")

# MomoTalk 消息长度阈值（字符数）。超过此值认为消息过长，用标点断句
MMT_MAX_CHUNK_CHARS = 30   # 手机气泡约 30 字一行，更激进的断句
MMT_MIN_CHUNK_CHARS = 4    # 短音节词（"嗯。"、"啊..."）可独立成行

# ============================================================================
# MomoTalk 特化处理器
# ============================================================================


def _strip_action_brackets(text: str) -> str:
    """Processor 1: 去除括号内的动作描写。

    MomoTalk 是手机聊天——没有"（低头）（小声）"这种舞台指示。

    匹配中文全角括号（...）和英文半角括号(...)。
    使用非贪婪匹配正确处理嵌套括号。
    """
    # 用循环处理，因为 re.sub 无法可靠处理嵌套
    # 策略：反复去除最内层括号，直到没有括号为止
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"（[^（）]*）", "", text)
        text = re.sub(r"\([^()]*\)", "", text)
    return text.strip()


def _split_for_momotalk(text: str, max_chars: int = MMT_MAX_CHUNK_CHARS) -> list[str]:
    """Processor 2: 按标点断句，模拟手机聊天气泡。

    手机聊天的自然节奏:
        - 句号/问号/感叹号 → 强断点
        - 逗号/分号 → 弱断点（语气停顿，可合并）
        - "…"省略号不参与断句
    """
    text = text.strip()
    if not text:
        return [text]

    # 预处理: 合并连续英文句点为省略号 "…"，防止 "..." 被切碎
    # 也合并连续的中文省略号 "……" → "…"
    text = re.sub(r"[.．。]{2,}", "…", text)
    text = re.sub(r"…{2,}", "…", text)
    # 去掉没意义的纯标点碎片
    text = text.strip()

    if not text:
        return [text]

    # 在强断点（。！？!?…）处切分。标点留在句子末尾。
    strong = _strong_split(text)

    if len(strong) <= 1 and len(text) <= max_chars:
        return [text if text else strong]

    # 过滤掉纯标点碎片（"。"、"！"、"…" 单独出现不算）
    strong = [s for s in strong if _has_content(s)]
    if not strong:
        return [text]

    chunks: list[str] = []
    for segment in strong:
        if len(segment) <= max_chars:
            chunks.append(segment)
        else:
            chunks.extend(_split_at_weak_breaks(segment, max_chars))

    return _merge_short_chunks(chunks, max_chars)


def _split_at_weak_breaks(text: str, max_chars: int) -> list[str]:
    """在逗号/分号等弱标点处拆分超长句。"""
    # 去掉英文句号切分（避免 "..." 被切成碎片）
    parts = re.split(r"(?<=[，、,;；；])", text)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return [text]

    out: list[str] = []
    buf = ""
    for part in parts:
        # 极短 part 独立（"但、" "嗯……" 这种）
        if len(part) <= MMT_MIN_CHUNK_CHARS:
            if buf:
                out.append(buf.strip())
                buf = ""
            out.append(part)
            continue

        if len(buf) + len(part) <= max_chars:
            buf += part
        else:
            if buf:
                out.append(buf.strip())
            # 单 part 超长 → 硬截
            if len(part) > max_chars:
                out.append(part[:max_chars])
            else:
                buf = part
    if buf:
        out.append(buf.strip())
    return out if out else [text]


def _merge_short_chunks(chunks: list[str], max_chars: int) -> list[str]:
    """合并过短的相邻 chunk，但保留独立短音节。

    规则:
        - "嗯。" "啊..." "谢谢" 等极短句（≤4字）→ 可独立存在
        - 其他短句 → 合并到相邻 chunk
    """
    if len(chunks) <= 1:
        return chunks
    merged: list[str] = []
    buf = ""
    for c in chunks:
        # 极短句独立
        if len(c) <= MMT_MIN_CHUNK_CHARS:
            if buf:
                merged.append(buf.strip())
                buf = ""
            merged.append(c)
            continue
        if len(buf) + len(c) <= max_chars:
            buf += c
        else:
            if buf:
                merged.append(buf.strip())
            buf = c
    if buf:
        merged.append(buf.strip())
    return merged if merged else chunks


def _process_for_momotalk(text: str) -> list[str]:
    """MomoTalk 纯文本处理器。
    1. 去动作括号
    2. 按标点断句
    3. 返回聊天气泡列表 (无格式化，格式化是 UI 层的职责)
    可用于 MomoTalk 以及未来需要同样处理器的场景。
    """
    text = _strip_action_brackets(text)
    return _split_for_momotalk(text)


# ---------------------------------------------------------------------------
# 分词辅助
# ---------------------------------------------------------------------------

def _strong_split(text: str) -> list[str]:
    """在强断点（。！？!?…）处切分。"""
    parts = re.split(r"(?<=[。！？!?…])", text)
    return [p.strip() for p in parts if p.strip() and p not in (".", ":")]


def _has_content(text: str) -> bool:
    """检查片段是否有实际文字内容（非纯标点/空格）。"""
    cleaned = re.sub(r"[\s\.…。！？!?,，、;；：:（）()\"'\"\"]", "", text)
    return len(cleaned) > 0


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

        # MomoTalk 特化指令（追加到 System Prompt）
        system_prompt += (
            "\n\n【MomoTalk 规则】\n"
            "你正在通过手机即时通讯软件 MomoTalk 与 sensei 聊天。\n"
            "1. 这是文字聊天，不是面对面交流。不要使用（动作描写）或（表情描述）。\n"
            "2. 回复要简短自然，类似 LINE/微信的聊天节奏。每次最多 1-3 句话。\n"
            "3. 不要用第三人称描述自己。你就是角色本人。\n"
            "4. 可以适当使用 ~ 或 ... 等非正式语气词。"
        )

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
        """发送玩家消息，返回 MomoTalk 格式的角色回复。"""
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

        # 子类可覆盖此方法更换处理器
        processed = self._process_reply(raw_reply)

        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": processed})
        self._trim_history()

        return processed

    # ------------------------------------------------------------------
    # 钩子：输出处理（子类可覆盖）
    # ------------------------------------------------------------------

    def _process_reply(self, raw_text: str) -> str:
        """MomoTalk 格式处理：去动作括号 + 断句 + 加角色名前缀。"""
        bubbles = _process_for_momotalk(raw_text)
        name = self._current_char.display_name if self._current_char else ""

        # 去重：LLM 可能自带"角色名："前缀
        deduped: list[str] = []
        for bubble in bubbles:
            for pat in [
                rf"^{re.escape(name)}\s*[：:]\s*",
                rf"^\[{re.escape(name)}[：:\s]*\]?\s*",
                rf"^【{re.escape(name)}】\s*",
            ]:
                bubble = re.sub(pat, "", bubble)
            bubble = bubble.strip()
            if bubble:
                deduped.append(bubble)

        # 格式化：每行加 [角色名: ] 前缀
        return "\n".join(f"[{name}: ]{b}" for b in deduped) if deduped else ""

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