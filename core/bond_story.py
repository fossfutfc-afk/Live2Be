"""羁绊剧情引擎 — 视觉小说模式对话。

与 MomoTalk 的区别:
    - 不去括号（允许动作描写）
    - 不断句（段落为单位，非气泡）
    - 不加 [名字]: 前缀（UI 层单独显示角色名）

VN 场景结构（收敛多分支, 2026-08-21 用户确认）:
    每场景 = 叙事段落 + 可选的【选择】选项块 + 可选的【完】收尾。
    选项收敛到同一主线——无论玩家选哪个, 剧情走向同一结局, 只影响
    紧接着的对白语气/细节（减轻 LLM 维护发散状态的负担）。
    bond_story_rules.md 约束 LLM 按此格式输出; _parse_scene 解析。

用法:
    from core.bond_story import BondStoryEngine
    vn = BondStoryEngine(characters_root, llm_client)
    vn.start_session("igusa_haruka")
    scene = vn.send_vn_scene("（开场）")
    for para in scene.paragraphs: ...
    if scene.choices: ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from core.common import err
from llm.client import LLMClient
from llm.prompts import load_prompt
from core.parsing.dynamic_character_parser import CharacterLoader, DynamicCharacter
from core.parsing.world_parser import DEFAULT_WORLD_PATH, load_world, world_to_prompt

logger = logging.getLogger(__name__)

MAX_HISTORY_ROUNDS = 20


@dataclass
class BondScene:
    """一个羁绊剧情场景的解析产物。

    paragraphs — 叙事段落（不含【选择】/【完】标记段）
    choices    — 选项列表（空 = 无选项; 有选项时玩家选一个, 喂回下一场景）
    is_end     — 是否剧情结束（出现【完】）
    """

    paragraphs: list[str] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)
    is_end: bool = False


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

        # 世界观（common + system 档）注入——角色理应知道的世界常识 + 安全边界
        world_chunk = world_to_prompt(load_world(DEFAULT_WORLD_PATH))
        if world_chunk:
            system_prompt += "\n\n" + world_chunk

        system_prompt += "\n\n" + load_prompt("bond_story_rules")

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

        from core.ui.display import BondStoryOutput

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

    def send_vn_scene(self, user_input: str) -> BondScene:
        """结构化场景 API：单次 LLM 调用 → BondScene（段落 + 选项 + 是否结束）。

        与 send_vn_stream 的区别: 解析【选择】选项块与【完】收尾标记,
        返回可驱动的结构（VN CLI 靠它出选项、判定剧情结束）。
        """
        if self._current_char is None:
            raise RuntimeError(err("NotInSession", "尚未开始会话"))

        from core.ui.display import BondStoryOutput

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

        scene = self._parse_scene(full_text)

        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": full_text})
        self._trim_history()
        return scene

    # ------------------------------------------------------------------
    # 场景解析
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_scene(text: str) -> BondScene:
        """纯函数: 流式文本 → BondScene。

        按双换行切段; 段为【完】→ is_end; 段以【选择】开头 → 后续非空行
        剥「数字.」前缀为选项; 其余 → paragraphs。无匹配标记的段照常进段落。
        """
        scene = BondScene()
        for raw_para in text.split("\n\n"):
            para = raw_para.strip()
            if not para:
                continue
            if para == "【完】":
                scene.is_end = True
                continue
            if para.startswith("【选择】"):
                for line in para.split("\n")[1:]:
                    line = line.strip()
                    if not line:
                        continue
                    # 剥「1. xxx」编号前缀, 保留选项文本
                    cleaned = line
                    if len(line) > 1 and line[0].isdigit() and line[1] in "。.、":
                        cleaned = line[2:].strip()
                    if cleaned:
                        scene.choices.append(cleaned)
                continue
            scene.paragraphs.append(para)
        return scene

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
