"""
Config 解析层 — 角色五层文件的加载与 System Prompt 构建。

五个接口：
    Profile        ← profile.yml        外貌/基础信息
    Personality    ← personality.yml    性格/行为逻辑
    Knowledge      ← knowledge.yml      独有知识库
    Experience     ← experience.yml     预设经历（初始化 Virtual Brain 用）
    Typical        ← typical.yml        校准样本 / 高频口癖

未来扩展：
    Static         ← .static/           游戏内实际对话数据（训练用，暂为声明）

用法:
    from parsing.character_parser import CharacterLoader

    loader = CharacterLoader("config/characters")
    haruka = loader.load("igusa_haruka")

    # 按场景构建不同强度的 System Prompt
    prompt = haruka.build_system_prompt(mode="momotalk")
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# ============================================================================
# 自定义异常
# ============================================================================


class ConfigValidationError(ValueError):
    """配置文件缺失必填字段或格式严重错误时抛出。"""

    def __init__(self, character_id: str, file_name: str, detail: str):
        self.character_id = character_id
        self.file_name = file_name
        self.detail = detail
        super().__init__(
            f"[{character_id}] {file_name}: {detail}"
        )


# ============================================================================
# 五个数据接口
# ============================================================================


@dataclass
class Profile:
    """L1 — 角色外貌与基础信息（任何萍水相逢之人都能看到）。

    必填字段：
        - most_called_name: 角色最常用的称呼
        - introduction: 角色简介
        - is_official_character: 是否为官方角色（影响 LLM 是否自行补充信息）
    """

    is_official: bool = True
    most_called_name: str = ""
    en_name: str = ""
    jp_name: str = ""
    other_names: list[str] = field(default_factory=list)
    gender: str = ""
    age: int = 0
    birthday: str = ""
    height: int = 0
    weight: str = ""
    position: str = ""
    gun_type: str = ""
    gun_name: str = ""
    interest: str = ""
    school: str = ""
    club: str = ""
    introduction: str = ""
    appearance: dict[str, Any] = field(default_factory=dict)

    def to_prompt_lines(self, use_llm_fallback: bool = False) -> list[str]:
        """转换为 Prompt 注入用的文本行。

        Args:
            use_llm_fallback: 如果为 True，则在信息不足时追加 LLM 自行查询的指令。
                              (仅在用户只填写了少量字段且 is_official=True 时使用)
        """
        lines: list[str] = []

        if self.most_called_name:
            parts = [f"你叫{self.most_called_name}"]
            if self.en_name:
                parts.append(f"（{self.en_name}）")
            if self.gender:
                parts.append(f"，{self.gender}")
            if self.age:
                parts.append(f"，{self.age}岁")
            if self.birthday:
                parts.append(f"，生日{self.birthday}")
            if self.height:
                parts.append(f"，身高{self.height}cm")
            parts.append("。")
            lines.append("".join(parts))

        if self.school or self.club:
            school_part = f"学校：{self.school}" if self.school else ""
            club_part = f"社团：{self.club}" if self.club else ""
            lines.append("。".join(p for p in [school_part, club_part] if p) + "。")

        if self.position or self.gun_name:
            pos_part = f"定位：{self.position}" if self.position else ""
            gun_part = f"武器：{self.gun_name}（{self.gun_type}）" if self.gun_name else ""
            lines.append("。".join(p for p in [pos_part, gun_part] if p) + "。")

        if self.interest:
            lines.append(f"爱好：{self.interest}。")

        if self.introduction:
            lines.append(f"简介：{self.introduction}")

        if use_llm_fallback:
            lines.append("")
            lines.append(
                "注意：上述角色信息较为简略。你是该角色的官方设定，"
                "你可以在自己知识库中检索该角色的完整人设信息，"
                "并以该角色的身份进行回应。请严格依据官方设定，不得编造。"
            )

        return lines


@dataclass
class Personality:
    """L2 — 性格与行为逻辑（角色扮演的最大参考源）。"""

    brief_traits: list[str] = field(default_factory=list)
    detailed_personality: list[str] = field(default_factory=list)

    def to_prompt_lines(self) -> list[str]:
        """转换为 Prompt 注入用的文本行。"""
        lines = ["【性格特征】"]
        for t in self.brief_traits:
            lines.append(f"- {t}")
        if self.detailed_personality:
            lines.append("")
            lines.append("【性格详述】")
            for p in self.detailed_personality:
                lines.append(p.strip())
        return lines


@dataclass
class Knowledge:
    """L3 — 角色独有知识库（人际关系 / 技能 / 物品 / 敌人 / 地点）。"""

    friends: dict[str, str] = field(default_factory=dict)
    techniques: list[str] = field(default_factory=list)
    possessions: dict[str, str] = field(default_factory=dict)
    enemies: dict[str, str] = field(default_factory=dict)
    places: dict[str, str] = field(default_factory=dict)

    def to_prompt_lines(self) -> list[str]:
        """转换为 Prompt 注入用的文本行。"""
        lines: list[str] = []

        if self.friends:
            lines.append("【你认识的人】")
            for name, desc in self.friends.items():
                lines.append(f"- {name}：{_safe_strip(desc)}")

        if self.places:
            lines.append("")
            lines.append("【你知道的地方】")
            for name, desc in self.places.items():
                lines.append(f"- {name}：{_safe_strip(desc)}")

        if self.techniques:
            lines.append("")
            lines.append("【你的技能】")
            for t in self.techniques:
                lines.append(f"- {t}")

        if self.possessions:
            lines.append("")
            lines.append("【你珍视的物品】")
            for name, desc in self.possessions.items():
                lines.append(f"- {name}：{_safe_strip(desc)}")

        if self.enemies:
            lines.append("")
            lines.append("【你的敌人】")
            for name, desc in self.enemies.items():
                lines.append(f"- {name}：{_safe_strip(desc)}")

        return lines


@dataclass
class Experience:
    """L4 — 与玩家的预设经历（静态初始值，运行时由 Virtual Brain 接管）。"""

    self_stories: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    main_stories: list[dict[str, str]] = field(default_factory=list)
    valentine: str = ""

    def to_prompt_lines(self) -> list[str]:
        """MVP 阶段：将经历摘要注入 Prompt。以后由 VB 替代。"""
        lines: list[str] = ["【你和sensei的过往经历】"]

        for category, episodes in self.self_stories.items():
            for ep in episodes:
                for label, text in ep.items():
                    lines.append(f"[{category}-{label}] {_safe_strip(text)}")

        for ep in self.main_stories:
            for label, text in ep.items():
                lines.append(f"[主线-{label}] {_safe_strip(text)}")

        if self.valentine:
            lines.append(f"[情人节] {self.valentine.strip()}")

        return lines


@dataclass
class Typical:
    """L5 — 校准样本：高频口癖 + Q&A 对。"""

    frequent_phrases: list[str] = field(default_factory=list)
    q_and_a: list[dict[str, str]] = field(default_factory=list)

    def to_prompt_lines(self) -> list[str]:
        """转换为 Prompt 注入用的文本行。"""
        lines: list[str] = []
        if self.frequent_phrases:
            lines.append("【你的常用口癖/表达方式】")
            for p in self.frequent_phrases:
                lines.append(f"- {p}")
        return lines


# ============================================================================
# 未来扩展：Static
# ============================================================================


class Static:
    """.static/ — 游戏内实际对话数据，用于模型训练。
    此接口为未来扩展预留，当前仅为声明。
    """

    def __init__(self, static_dir: Path):
        self._dir = static_dir
        self._available = static_dir.exists()

    @property
    def available(self) -> bool:
        return self._available

    def __repr__(self) -> str:
        st = "available" if self._available else "not found"
        return f"Static({st}, path={self._dir})"


# ============================================================================
# 聚合接口
# ============================================================================


@dataclass
class CharacterConfig:
    """一个角色的完整配置聚合。"""

    character_id: str
    profile: Profile
    personality: Personality
    knowledge: Knowledge
    experience: Experience
    typical: Typical
    static: Static

    # 加载后由 CharacterLoader 计算
    _info_level: str = "full"          # "full" | "minimal" | "bare"
    _missing_fields: list[str] = field(default_factory=list)

    @property
    def info_level(self) -> str:
        """信息完整度：full / minimal / bare。"""
        return self._info_level

    @property
    def missing_fields(self) -> list[str]:
        """缺失的关键字段列表。"""
        return self._missing_fields

    @property
    def needs_llm_fallback(self) -> bool:
        """是否需要 LLM 自行补充信息。"""
        return self._info_level in ("minimal", "bare") and self.profile.is_official

    def build_system_prompt(self, mode: str = "momotalk") -> str:
        """根据使用场景构建 System Prompt。

        Args:
            mode: "momotalk" / "bond_story" / "trigger"
        """
        sections: list[list[str]] = []

        if mode == "momotalk":
            use_fallback = self.needs_llm_fallback and self.profile.is_official
            sections.append(self.profile.to_prompt_lines(use_llm_fallback=use_fallback))
            sections.append(self.personality.to_prompt_lines())
            sections.append(self.knowledge.to_prompt_lines())
            sections.append(self.typical.to_prompt_lines())
            sections.append(self.experience.to_prompt_lines())
            sections.append(self._get_behavior_rules())

        elif mode == "bond_story":
            use_fallback = self.needs_llm_fallback and self.profile.is_official
            sections.append(self.profile.to_prompt_lines(use_llm_fallback=use_fallback))
            sections.append(self.personality.to_prompt_lines())
            sections.append(self._get_behavior_rules())

        elif mode == "trigger":
            use_fallback = self.needs_llm_fallback and self.profile.is_official
            sections.append(self.profile.to_prompt_lines(use_llm_fallback=use_fallback))
            if self.personality.brief_traits:
                sections.append(
                    ["【性格标签】"]
                    + [f"- {t}" for t in self.personality.brief_traits]
                )

        else:
            raise ValueError(f"Unknown mode: {mode}")

        prompt = "\n\n".join(
            "\n".join(sec) if isinstance(sec, list) else sec
            for sec in sections
        )
        return prompt.strip()

    @staticmethod
    def _get_behavior_rules() -> list[str]:
        return [
            "【回复要求】",
            "1. 你必须严格按照上述角色设定进行回复，不得脱离人设（OOC）。",
            "2. 用角色的口癖和说话方式。你是角色本人，不是旁白，不要用第三人称描述自己。",
            "3. 可以适当使用括号描述动作或表情，例如（低头）（小声）。",
            "4. 回复长度控制在2-4句话，不要一次说太多。保持自然聊天节奏。",
            "5. 对话对象是 sensei（老师），你对 sensei 的称呼是 sensei 或 老师。",
        ]


# ============================================================================
# 加载器
# ============================================================================


class CharacterLoader:
    """从 config/characters/ 加载角色配置。"""

    # ── 必填的 profile 字段 ──
    REQUIRED_PROFILE_KEYS = {
        "is_official_character",
        "most_called_name",
        "introduction",
    }

    # ── 判定信息等级的阈值 ──
    MINIMAL_THRESHOLD = 5   # 有意义的 profile 字段数 < 此值 → "bare"
    FULL_THRESHOLD = 10     # 有意义的 profile 字段数 < 此值 → "minimal", >= → "full"

    def __init__(self, characters_root: str | Path):
        self.root = Path(characters_root)

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def list_characters(self) -> dict[str, str]:
        """列出所有可用角色。

        扫描 config/characters/ 下所有包含 profile.yml 或 profile.yaml 的子目录，
        读取各角色的 IMP_most_called_name 作为显示名。

        Returns:
            {目录名: 显示名} 映射，如 {"igusa_haruka": "伊草 遥香"}
        """
        result: dict[str, str] = {}
        if not self.root.exists():
            return result

        for p in sorted(self.root.iterdir()):
            if not p.is_dir() or p.name.startswith("."):
                continue
            profile_path = self._find_profile_file(p)
            if profile_path is None:
                continue
            raw = self._read_yaml(p, profile_path.name)
            display_name = self._extract_display_name(raw, p.name)
            result[p.name] = display_name

        return result

    def load(
        self,
        character_id: str,
        *,
        strict: bool = True,
    ) -> CharacterConfig:
        """加载一个角色的完整配置。

        Args:
            character_id: 角色目录名，如 "igusa_haruka"
            strict: True  → 必填字段缺失时抛出 ConfigValidationError
                    False → 必填字段缺失时仅发 warning，仍可加载

        Returns:
            CharacterConfig 聚合对象

        Raises:
            FileNotFoundError:      角色目录不存在
            ConfigValidationError:  strict 模式下必填字段缺失
            yaml.YAMLError:         YAML 语法错误
        """
        char_dir = self.root / character_id
        if not char_dir.is_dir():
            avail = self.list_characters()
            raise FileNotFoundError(
                f"角色目录不存在: {char_dir}\n"
                f"可用角色: {list(avail.keys())}"
            )

        profile = self._load_profile(char_dir)
        personality = self._load_personality(char_dir)
        knowledge = self._load_knowledge(char_dir)
        experience = self._load_experience(char_dir)
        typical = self._load_typical(char_dir)

        # 校验必填字段
        missing = self._validate_profile(profile, character_id, strict)

        # 评估信息完整度
        info_level = self._assess_info_level(profile, personality)

        if info_level != "full":
            self._warn_low_info(character_id, info_level, missing, profile.is_official)

        return CharacterConfig(
            character_id=character_id,
            profile=profile,
            personality=personality,
            knowledge=knowledge,
            experience=experience,
            typical=typical,
            static=Static(char_dir / ".static"),
            _info_level=info_level,
            _missing_fields=missing,
        )

    # ------------------------------------------------------------------
    # 必填字段校验
    # ------------------------------------------------------------------

    def _validate_profile(
        self, profile: Profile, character_id: str, strict: bool
    ) -> list[str]:
        """校验 Profile 必填字段。

        必填:
            - most_called_name (映射自 IMP_most_called_name)
            - introduction
            - is_official_character

        Returns:
            缺失字段名列表。
        """
        missing: list[str] = []

        if not profile.most_called_name:
            missing.append("name.IMP_most_called_name")
        if not profile.introduction:
            missing.append("introduction")

        if missing and strict:
            raise ConfigValidationError(
                character_id=character_id,
                file_name="profile.yml",
                detail=(
                    f"缺少必填字段: {', '.join(missing)}。"
                    f"请在 profile.yml 中填写这些字段。"
                    f"如果角色信息不完整，可以使用 load(..., strict=False) 跳过此检查，"
                    f"LLM 将自动从其知识库中补充角色信息。"
                ),
            )

        if missing:
            logger.warning(
                "[%s] profile.yml 缺少必填字段: %s。将启用 LLM fallback 模式。",
                character_id,
                ", ".join(missing),
            )

        return missing

    # ------------------------------------------------------------------
    # 信息完整度评估
    # ------------------------------------------------------------------

    def _assess_info_level(self, profile: Profile, personality: Personality) -> str:
        """评估角色信息的完整度。

        统计规则:
            - profile 中每个非空字段 +1 分（appearance/other_names 除外）
            - personality 有 brief_traits +1，有 detailed +1

        Returns:
            "full" | "minimal" | "bare"
        """
        score = 0

        # profile 有意义字段计数
        meaningful = [
            profile.most_called_name,
            profile.en_name,
            profile.gender,
            profile.age,
            profile.birthday,
            profile.height,
            profile.position,
            profile.interest,
            profile.school,
            profile.club,
            profile.introduction,
        ]
        score += sum(1 for v in meaningful if v)

        # personality
        if personality.brief_traits:
            score += 1
        if personality.detailed_personality:
            score += 1

        if score >= self.FULL_THRESHOLD:
            return "full"
        elif score >= self.MINIMAL_THRESHOLD:
            return "minimal"
        else:
            return "bare"

    def _warn_low_info(
        self,
        character_id: str,
        level: str,
        missing: list[str],
        is_official: bool,
    ) -> None:
        """信息不足时发出警告。"""
        messages: list[str] = []

        if missing:
            messages.append(f"缺失必填字段: {', '.join(missing)}")

        if is_official:
            messages.append(
                "该角色标记为官方角色(is_official_character=true)，"
                "LLM 将在对话中自行检索知识库补充角色信息。"
            )
        else:
            messages.append(
                "该角色并非官方角色，LLM 无法自行补充信息。"
                "建议补充更多角色设定以获得更好的对话体验。"
            )

        full_msg = (
            f"\n{'=' * 60}\n"
            f"⚠️  角色 [{character_id}] 信息完整度: {level.upper()}\n"
            f"{'=' * 60}\n"
            + "\n".join(f"  • {m}" for m in messages)
            + f"\n{'=' * 60}\n"
        )
        warnings.warn(full_msg, stacklevel=3)
        logger.warning(full_msg)

    # ------------------------------------------------------------------
    # 五个解析器
    # ------------------------------------------------------------------

    def _load_profile(self, char_dir: Path) -> Profile:
        raw = self._read_yaml(char_dir, "profile.yml")

        # 解析 name 字段
        most_called = ""
        en_name = ""
        jp_name = ""
        other_names: list[str] = []
        name_list = raw.get("name", [])
        if isinstance(name_list, list):
            for entry in name_list:
                if isinstance(entry, dict):
                    if "IMP_most_called_name" in entry:
                        most_called = entry["IMP_most_called_name"] or ""
                    if "en_name" in entry:
                        en_name = entry["en_name"] or ""
                    if "jp_name" in entry:
                        jp_name = entry["jp_name"] or ""
                    if "other_name" in entry:
                        other_names = (
                            entry["other_name"]
                            if isinstance(entry["other_name"], list)
                            else [entry["other_name"]]
                        )

        # 解析 appearance（list-of-dict → 扁平 dict）
        appearance: dict[str, Any] = {}
        app_list = raw.get("appearance", [])
        if isinstance(app_list, list):
            for entry in app_list:
                if isinstance(entry, dict):
                    appearance.update(entry)

        return Profile(
            is_official=raw.get("is_official_character", raw.get("is_official-character", True)),
            most_called_name=most_called,
            en_name=en_name,
            jp_name=jp_name,
            other_names=other_names,
            gender=raw.get("gender") or "",
            age=raw.get("age") or 0,
            birthday=raw.get("birthday") or "",
            height=raw.get("height") or 0,
            weight=_safe_str(raw.get("weight")),
            position=raw.get("position") or "",
            gun_type=raw.get("gun_type") or "",
            gun_name=raw.get("gun_name") or "",
            interest=raw.get("interest") or "",
            school=raw.get("school") or "",
            club=raw.get("club") or "",
            introduction=_safe_strip(raw.get("introduction")),
            appearance=appearance,
        )

    def _load_personality(self, char_dir: Path) -> Personality:
        raw = self._read_yaml(char_dir, "personality.yml")
        brief = raw.get("brief_traits") or []
        detailed = raw.get("detailed_personality") or []

        if isinstance(brief, str):
            brief = [brief]
        if isinstance(detailed, str):
            detailed = [detailed]

        return Personality(
            brief_traits=[_safe_strip(b) for b in brief] if isinstance(brief, list) else [],
            detailed_personality=(
                [_safe_strip(d) for d in detailed]
                if isinstance(detailed, list)
                else []
            ),
        )

    def _load_knowledge(self, char_dir: Path) -> Knowledge:
        raw = self._read_yaml(char_dir, "knowledge.yml")
        return Knowledge(
            friends=raw.get("friends") if isinstance(raw.get("friends"), dict) else {},
            techniques=raw.get("technique") if isinstance(raw.get("technique"), list) else [],
            possessions=raw.get("possession") if isinstance(raw.get("possession"), dict) else {},
            enemies=raw.get("enemy") if isinstance(raw.get("enemy"), dict) else {},
            places=raw.get("places") if isinstance(raw.get("places"), dict) else {},
        )

    def _load_experience(self, char_dir: Path) -> Experience:
        raw = self._read_yaml(char_dir, "experience.yml")

        self_stories: dict[str, list[dict[str, str]]] = {}
        raw_self = raw.get("self")
        if isinstance(raw_self, list):
            for category_entry in raw_self:
                if isinstance(category_entry, dict):
                    for category, episodes in category_entry.items():
                        if isinstance(episodes, list):
                            self_stories[category] = [
                                ep for ep in episodes if isinstance(ep, dict)
                            ]

        main_stories: list[dict[str, str]] = []
        raw_main = raw.get("main")
        if isinstance(raw_main, list):
            main_stories = [ep for ep in raw_main if isinstance(ep, dict)]

        valentine_raw = raw.get("valentine", "")
        valentine = _safe_strip(valentine_raw) if valentine_raw else ""

        return Experience(
            self_stories=self_stories,
            main_stories=main_stories,
            valentine=valentine,
        )

    def _load_typical(self, char_dir: Path) -> Typical:
        raw = self._read_yaml(char_dir, "typical.yml")
        phrases = raw.get("frequent_phrases")
        q_and_a = raw.get("q_and_a")

        if phrases is None:
            phrases = []
        if q_and_a is None:
            q_and_a = []

        return Typical(
            frequent_phrases=phrases if isinstance(phrases, list) else [],
            q_and_a=q_and_a if isinstance(q_and_a, list) else [],
        )

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    def _find_profile_file(self, char_dir: Path) -> Path | None:
        """在角色目录中查找 profile.yml 或 profile.yaml。"""
        for name in ("profile.yml", "profile.yaml"):
            p = char_dir / name
            if p.exists():
                return p
        return None

    @staticmethod
    def _extract_display_name(raw: dict[str, Any], fallback: str) -> str:
        """从 raw profile 数据中提取 IMP_most_called_name 作为显示名。

        查找路径: name → list → IMP_most_called_name
        找不到时 fallback 到目录名。
        """
        name_list = raw.get("name", [])
        if isinstance(name_list, list):
            for entry in name_list:
                if isinstance(entry, dict) and "IMP_most_called_name" in entry:
                    return entry["IMP_most_called_name"] or fallback
        return fallback

    def _read_yaml(self, char_dir: Path, filename: str) -> dict[str, Any]:
        """读取 YAML 文件，带错误处理。

        - 文件不存在 → 返回 {}
        - YAML 语法错误 → 抛出 ConfigValidationError（带清晰定位）
        - 编码错误 → 抛出 ConfigValidationError
        - 文件内容不是 dict → 返回 {}
        """
        path = char_dir / filename

        if not path.exists():
            logger.info("[%s] 文件不存在: %s", char_dir.name, filename)
            return {}

        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except UnicodeDecodeError as e:
            raise ConfigValidationError(
                character_id=char_dir.name,
                file_name=filename,
                detail=(
                    f"文件编码错误，请确保文件以 UTF-8 编码保存。\n"
                    f"技术细节: {e}"
                ),
            ) from e
        except yaml.YAMLError as e:
            raise ConfigValidationError(
                character_id=char_dir.name,
                file_name=filename,
                detail=(
                    f"YAML 语法错误，请检查缩进（只能用空格）、引号配对等。\n"
                    f"技术细节:\n{e}"
                ),
            ) from e

        if not isinstance(data, dict):
            logger.warning(
                "[%s] %s 内容不是 dict (类型=%s)，将视为空配置。",
                char_dir.name,
                filename,
                type(data).__name__,
            )
            return {}

        return data


# ============================================================================
# 共享工具函数
# ============================================================================


def _safe_strip(value: Any) -> str:
    """安全 strip：None → ""，非 str → str(value).strip()。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _safe_str(value: Any) -> str:
    """安全转字符串，None → ""。"""
    if value is None:
        return ""
    return str(value)
