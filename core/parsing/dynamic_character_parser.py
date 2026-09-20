"""
动态角色解析器 — 约定驱动，零硬编码。

约定章程（以 profile.yml 头部注释为准）:
    REQ~  = 必填（Required）  — 缺失则警告/拒绝
    SIG~  = 重要（Significant）— 计入信息完整度
    无前缀 = 普通字段         — 透传，可选，不校检
    null   = 合法占位符       — 跳过，不报错

核心行为:
    1. 读取 YAML → 保留原始嵌套结构
    2. 扫描所有 key → 按前缀分类（REQ~/SIG~/普通）
    3. 透传渲染为 LLM Prompt 文本 → 不逐字段映射
    4. null 值 → 跳过
    5. 支持多文件合并 (profile + personality + knowledge + experience + typical)
    6. 加字段 = 改 YAML，零代码改动

已知问题（暂不修复）:
    ① Python bool 值渲染为 "True"/"False" 而非 YAML 的 true/false。
       LLM 能理解，但格式与源文件不一致。如需修复，在 _render_node 叶子分支加 isinstance(value, bool) 特判。
    ② 嵌套 list-of-dict 会产生双重路径（如 dress 本身 + dress[0].regular），
       classify_fields 的 info 列表中会有重复条目。不影响 Prompt 最终输出。
    ③ SIG~ 前缀标在 list/dict 节点上时，语义为"整个容器重要"，其子节点不再继承 SIG~。
       如需标记容器内某子项重要，应在子项的 key 上加 SIG~（但目前不建议，保持前两层前缀干净即可）。
    ④ yaml_to_prompt 对 deep-nested 的 YAML（如 experience.yml）展示效果一般——
       三层以上的嵌套在 Prompt 中缩进过深。建议此类内容保持 ≤2 层嵌套。

用法:
    from core.parsing.dynamic_character_parser import CharacterLoader

    loader = CharacterLoader("config/characters")
    chars = loader.list_characters()          # {"igusa_haruka": "伊草 遥香"}
    char = loader.load("igusa_haruka")        # 合并全部 5 个 yml
    prompt = char.build_prompt()              # LLM System Prompt
    prompt = char.build_prompt("bond_story")  # 简化版 (profile + personality)
    prompt = char.build_prompt("trigger")     # 极简版 (profile only)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.common import err
from llm.prompts import load_prompt

logger = logging.getLogger(__name__)

# ============================================================================
# 前缀常量
# ============================================================================

PREFIX_REQ = "REQ~"
PREFIX_SIG = "SIG~"

# ============================================================================
# 载入
# ============================================================================


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """读取单个 YAML 文件，返回原始 dict。

    Raises:
        FileNotFoundError: 文件不存在
        yaml.YAMLError: YAML 语法错误
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(err("NotFound", f"档案不存在: {path}"))

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise ValueError(err("InvalidYaml", f"{path.name} 内容不是有效 YAML dict"))

    return data


# ===========================================================================
# 字段分类
# ===========================================================================


def classify_fields(data: dict[str, Any]) -> dict[str, Any]:
    """遍历 YAML dict（递归），按前缀分类所有叶子字段。

    Returns:
        {
            "req":  {"字段名": 值, ...},    # REQ~ 前缀
            "sig":  {"字段名": 值, ...},    # SIG~ 前缀
            "info": {"字段名": 值, ...},    # 无前缀
            "all":  {"字段名": 值, ...},    # 全部（含前缀剥离后的干净键名）
        }
    """
    result: dict[str, dict[str, Any]] = {
        "req": {},
        "sig": {},
        "info": {},
        "all": {},
    }
    _walk(data, result, prefix="")
    return result


def _walk(node: Any, result: dict, prefix: str) -> None:
    """递归遍历 YAML 树。"""
    if isinstance(node, dict):
        for raw_key, value in node.items():
            if value is None:
                continue

            # raw_key 必须是字符串——int 键无意义，跳过
            if not isinstance(raw_key, str):
                continue

            clean_key, tag = _strip_prefix(raw_key)
            full_key = f"{prefix}.{clean_key}" if prefix else clean_key

            if tag and isinstance(value, (str, int, float, bool)):
                # 有前缀的标量叶子 → 归类
                result["all"][full_key] = value
                if tag == "req":
                    result["req"][full_key] = value
                elif tag == "sig":
                    result["sig"][full_key] = value
            elif tag and isinstance(value, (list, dict)):
                # 有前缀的嵌套 → 前缀作用于本节点，递归子节点
                result["all"][full_key] = value
                if tag == "req":
                    result["req"][full_key] = value
                elif tag == "sig":
                    result["sig"][full_key] = value
                _walk(value, result, full_key)
            elif isinstance(value, (str, int, float, bool)):
                # 无前缀叶子
                result["all"][full_key] = value
                result["info"][full_key] = value
            else:
                # 无前缀嵌套 → 继续递归
                result["all"][full_key] = value
                _walk(value, result, full_key)

    elif isinstance(node, list):
        for i, item in enumerate(node):
            if isinstance(item, dict):
                _walk(item, result, f"{prefix}[{i}]")
            # 跳过 list 中的非 dict 元素（标量不需要递归）


def _strip_prefix(raw_key: str) -> tuple[str, str]:
    """剥离 REQ~ / SIG~ 前缀。

    Returns:
        (clean_key, tag)  其中 tag 为 "req" / "sig" / ""
    """
    if raw_key.startswith(PREFIX_REQ):
        return raw_key[len(PREFIX_REQ):], "req"
    if raw_key.startswith(PREFIX_SIG):
        return raw_key[len(PREFIX_SIG):], "sig"
    return raw_key, ""


# ===========================================================================
# 校检 — 针对单个 YAML 文件
# ===========================================================================


def check_required(data: dict[str, Any]) -> list[str]:
    """检查所有 REQ~ 前缀字段是否非空。

    Returns:
        缺失/为空的字段名列表。空列表 = 全部通过。
    """
    classified = classify_fields(data)
    missing = []
    for name, value in classified["req"].items():
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(name)
    return missing


def get_completeness(data: dict[str, Any]) -> dict[str, Any]:
    """计算信息完整度。

    Returns:
        {
            "score": int,             # 非空 SIG~ 字段数
            "total_sig": int,         # SIG~ 字段总数
            "ratio": float,           # 比例
            "missing_sig": [str],     # 空值的 SIG 字段
            "missing_req": [str],     # 空值的 REQ 字段
        }
    """
    classified = classify_fields(data)

    total_sig = len(classified["sig"])
    filled = sum(
        1 for v in classified["sig"].values()
        if v is not None and (not isinstance(v, str) or v.strip())
    )
    missing_sig = [
        k for k, v in classified["sig"].items()
        if v is None or (isinstance(v, str) and not v.strip())
    ]
    missing_req = [
        k for k, v in classified["req"].items()
        if v is None or (isinstance(v, str) and not v.strip())
    ]

    return {
        "score": filled,
        "total_sig": total_sig,
        "ratio": filled / total_sig if total_sig > 0 else 1.0,
        "missing_sig": missing_sig,
        "missing_req": missing_req,
    }


# ===========================================================================
# 元数据提取
# ===========================================================================


#: CJK（含中日韩标点/全角）——折行合并时用于去掉汉字之间的空格噪声
_CJK = r"[\u3000-\u303f\u3040-\u30ff\u4e00-\u9fff\uff00-\uffef]"


def _fold_prompt_text(text: str) -> str:
    """YAML 块标量折行 → 单行提示文本: 压缩空白, 再去掉 CJK 之间的空格。"""
    folded = " ".join(text.split())
    previous = None
    while previous != folded:
        previous = folded
        folded = re.sub(f"({_CJK}) ({_CJK})", r"\1\2", folded)
    return folded


def get_display_name(data: dict[str, Any]) -> str:
    """提取角色显示名。

    优先级: REQ~most_called_name > 第一个 REQ~ 值 > "未知角色"
    """
    # 不用 classify_fields，直接从顶层取（O(1)）
    name = data.get(f"{PREFIX_REQ}most_called_name", "")
    if name:
        return str(name)
    # fallback: 扫描第一个 REQ 字段
    for key, value in data.items():
        if key.startswith(PREFIX_REQ) and isinstance(value, str) and value.strip():
            return value
    return "未知角色"


def is_official(data: dict[str, Any]) -> bool:
    """是否为官方角色（is_official_character）。"""
    val = data.get(f"{PREFIX_REQ}is_official_character", True)
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("true", "1", "yes")


# ===========================================================================
# 透传渲染 → LLM Prompt
# ===========================================================================


def yaml_to_prompt(data: dict[str, Any], title: str = "角色设定") -> str:
    """将 YAML dict 渲染为 LLM 可读的结构化 Markdown 文本。

    规则:
        - 剥离 REQ~ / SIG~ 前缀后显示
        - null → 跳过
        - 嵌套 dict → 缩进展开
        - 列表 → - 展开
        - 多行字符串 → 保留换行
        - 保留 YAML key 的顺序（Python 3.7+ dict 有序）
    """
    lines = [f"# {title}", ""]
    _render_node(data, lines, indent=0)
    return "\n".join(lines)


def _render_node(node: Any, lines: list[str], indent: int) -> None:
    """递归渲染节点。"""
    pfx = "  " * indent

    if isinstance(node, dict):
        for raw_key, value in node.items():
            if value is None:
                continue
            if not isinstance(raw_key, str):
                continue
            clean_key, _tag = _strip_prefix(raw_key)
            display_key = clean_key.replace("_", " ")

            if isinstance(value, (str, int, float, bool)):
                text = str(value).strip()
                if text:
                    text_lines = text.split("\n")
                    if len(text_lines) > 1:
                        lines.append(f"{pfx}**{display_key}**:")
                        for tl in text_lines:
                            lines.append(f"{pfx}  {tl.strip()}")
                    else:
                        lines.append(f"{pfx}- **{display_key}**: {text_lines[0]}")
            elif isinstance(value, list):
                lines.append(f"{pfx}- **{display_key}**:")
                for item in value:
                    if isinstance(item, dict):
                        _render_node(item, lines, indent + 1)
                    elif isinstance(item, str):
                        item_text = item.strip()
                        if item_text:
                            lines.append(f"{pfx}  - {item_text}")
                    elif item is not None:
                        lines.append(f"{pfx}  - {item}")
            elif isinstance(value, dict):
                lines.append(f"{pfx}- **{display_key}**:")
                _render_node(value, lines, indent + 1)

    elif isinstance(node, list):
        for item in node:
            if isinstance(item, dict):
                _render_node(item, lines, indent)
            elif isinstance(item, str) and item.strip():
                lines.append(f"{pfx}- {item.strip()}")
            elif item is not None:
                lines.append(f"{pfx}- {item}")

    elif isinstance(node, str):
        text = node.strip()
        if text:
            lines.append(f"{pfx}{text}")


# ===========================================================================
# 多文件合并 + 角色加载器
# ===========================================================================

# 角色目录下的 6 个文件（profile 必需，其余可选; script.yml = 扮演手册 2026-09-01）
_CHARACTER_FILES = [
    "profile.yml",
    "personality.yml",
    "knowledge.yml",
    "experience.yml",
    "typical.yml",
    "script.yml",
]


def _first_str(data: dict, key: str) -> str:
    """键值 → 文本（str 原样; list 逐项换行拼接——手册的 mmt_tone/bond_tone 常为列表）;
    dict 项（作者写了 `key: value` 格式）→ 值拼接（容错）; 缺失/坏值 → 空。"""
    v = data.get(key, "")
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        parts: list[str] = []
        for x in v:
            if isinstance(x, dict):                 # 容错: 项被 YAML 解析成映射
                x = " ".join(str(t).strip() for t in x.values())
            t = str(x).strip().lstrip("- ").strip()
            if t:
                parts.append(t)
        return "\n".join(parts) if parts else ""
    return ""


@dataclass
class DynamicCharacter:
    """一个角色的完整配置（多文件合并后的聚合）。"""

    character_id: str
    raw: dict[str, Any] = field(default_factory=dict)  # 合并后的完整数据
    profile: dict[str, Any] = field(default_factory=dict)
    personality: dict[str, Any] = field(default_factory=dict)
    knowledge: dict[str, Any] = field(default_factory=dict)
    experience: dict[str, Any] = field(default_factory=dict)
    typical: dict[str, Any] = field(default_factory=dict)
    script: dict[str, Any] = field(default_factory=dict)  # 扮演手册（可选, 2026-09-01）

    # 元数据（加载时计算）
    display_name: str = ""
    is_official: bool = True
    completeness: dict[str, Any] = field(default_factory=dict)
    missing_req: list[str] = field(default_factory=list)
    # 剧情基调（扮演手册 script.yml 的 SIG~main_tone 优先 → 兼容 personality
    # 的 SIG~story_tone → 空; 对话生成层注入——"最一开始告诉 AI"）
    story_tone: str = ""
    # 扮演手册分域注入（script.yml 的 SIG~mmt_tone / SIG~bond_tone; 缺失 → 空）
    mmt_tone: str = ""
    bond_tone: str = ""

    def image_persona_brief(self, limit: int = 4) -> str:
        """生图用的**性格简卡**（2026-09-20, docs/DESIGN_MEMORIAL.md 节点 D1）。

        为什么需要: 生图模型**不知道她是谁**——只喂外观参考图, 它画得出服装发型,
        画不出"自卑/惶恐/不敢对视"那层神态（真机那张纪念图被画成了明亮的笑,
        用户: *"图不像人不是 VN 的问题，更像是生图 LLM 没把握住神态"*）。

        料 = `personality.yml` 的 `SIG~brief_traits`（人设里本来就有的短句清单）。
        **只给性格, 不给外貌**——外貌有参考图, 描述细节反而会跟参考图打架。
        `illustration.yml` 的 `character_hint` 非空时优先用它（作者手写版）。
        """
        traits = self.personality.get(f"{PREFIX_SIG}brief_traits", [])
        if not isinstance(traits, list):
            return ""
        lines = [str(t).strip() for t in traits if str(t).strip()][:max(0, limit)]
        return "\n".join(f"- {t}" for t in lines)

    def build_prompt(self, mode: str = "momotalk") -> str:
        """根据模式构建 System Prompt。

        Args:
            mode: "momotalk" → 完整人设 + 行为约束
                  "bond_story" → 简化（profile + personality + 行为约束）
                  "trigger" → 最简（profile + brief_traits）
        """
        sections: list[str] = []

        if mode == "momotalk":
            sections.append(yaml_to_prompt(self.raw, "角色设定"))
            sections.append(_BEHAVIOR_RULES)

        elif mode == "bond_story":
            merged = {**self.profile, **self.personality}
            sections.append(yaml_to_prompt(merged, "角色设定"))
            sections.append(_BEHAVIOR_RULES)

        elif mode == "trigger":
            # 极简：只要 profile + 性格标签
            merged = dict(self.profile)
            if self.personality:
                brief = self.personality.get(f"{PREFIX_SIG}brief_traits", [])
                if brief:
                    merged["_brief_traits"] = brief
            sections.append(yaml_to_prompt(merged, "角色概要"))

        else:
            raise ValueError(err("UnknownMode", f"Unknown mode: {mode}"))

        return "\n\n".join(s.strip() for s in sections if s.strip())


#: 行为规则（长篇 prompt → llm/prompts/behavior_rules.md）
_BEHAVIOR_RULES = load_prompt("behavior_rules")


class CharacterLoader:
    """从 config/characters/ 加载角色配置（多文件合并）。

    用法:
        loader = CharacterLoader("config/characters")
        chars = loader.list_characters()       # {"igusa_haruka": "伊草 遥香"}
        haruka = loader.load("igusa_haruka")   # DynamicCharacter
    """

    def __init__(self, characters_root: str | Path):
        self.root = Path(characters_root)

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def list_characters(self) -> dict[str, str]:
        """列出所有可用角色（显示名 = IMP_most_called_name）。

        Returns:
            {目录名: 显示名} 映射
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
            try:
                data = load_yaml_file(profile_path)
                result[p.name] = get_display_name(data)
            except Exception:
                result[p.name] = p.name  # fallback

        return result

    def load(self, character_id: str, strict: bool = True) -> DynamicCharacter:
        """加载一个角色的全部 5 个 yml 文件。

        Args:
            character_id: 角色目录名
            strict: True → REQ 字段缺失时打印 warning 但仍返回

        Returns:
            DynamicCharacter 聚合对象
        """
        char_dir = self.root / character_id
        if not char_dir.is_dir():
            raise FileNotFoundError(err(
                "NotFound",
                f"角色目录不存在: {char_dir}\n"
                f"可用角色: {list(self.list_characters().keys())}",
            ))

        # 加载 5 个文件（profile 必需，其余可选）
        loaded: dict[str, dict[str, Any]] = {}
        for filename in _CHARACTER_FILES:
            path = char_dir / filename
            if path.exists():
                try:
                    loaded[filename.replace(".yml", "")] = load_yaml_file(path)
                except Exception as e:
                    logger.warning("[%s] %s 加载失败: %s", character_id, filename, e)
                    loaded[filename.replace(".yml", "")] = {}
            else:
                loaded[filename.replace(".yml", "")] = {}

        profile = loaded.get("profile", {})
        if not profile:
            raise FileNotFoundError(err(
                "NotFound",
                f"[{character_id}] profile.yml 不存在，无法加载角色",
            ))

        # 合并全部数据（profile 优先，避免 key 冲突时的覆盖）
        merged: dict[str, Any] = {}
        for filename in _CHARACTER_FILES:
            name = filename.replace(".yml", "")
            data = loaded.get(name, {})
            for k, v in data.items():
                if k not in merged:
                    merged[k] = v

        # 元数据
        display_name = get_display_name(profile)
        official = is_official(profile)
        missing_req = check_required(profile) if strict else []

        # strict 模式下的警告
        if strict and missing_req:
            logger.warning(
                "[%s] 缺失必填字段 (REQ~): %s",
                character_id,
                ", ".join(missing_req),
            )

        completeness_full = get_completeness(merged)

        # 剧情基调（扮演手册 script.yml 的 SIG~main_tone 优先 → 兼容 personality
        # 的 SIG~story_tone → 空; 调用方用默认兜底）
        personality_data = loaded.get("personality", {})
        script_data = loaded.get("script", {})
        tone = (script_data.get("SIG~main_tone", "")
                or personality_data.get("SIG~story_tone", ""))
        story_tone = tone.strip() if isinstance(tone, str) else ""
        # 扮演手册分域注入（mmt_tone → 聊天; bond_tone → 羁绊剧情）
        mmt_tone = _first_str(script_data, "SIG~mmt_tone")
        bond_tone = _first_str(script_data, "SIG~bond_tone")

        return DynamicCharacter(
            character_id=character_id,
            raw=merged,
            profile=profile,
            personality=personality_data,
            knowledge=loaded.get("knowledge", {}),
            experience=loaded.get("experience", {}),
            typical=loaded.get("typical", {}),
            script=script_data,
            display_name=display_name,
            is_official=official,
            completeness=completeness_full,
            missing_req=missing_req,
            story_tone=story_tone,
            mmt_tone=mmt_tone,
            bond_tone=bond_tone,
        )

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _find_profile_file(char_dir: Path) -> Path | None:
        for name in ("profile.yml", "profile.yaml"):
            p = char_dir / name
            if p.exists():
                return p
        return None

    def load_illustration(self, character_id: str) -> dict[str, str]:
        """读角色**可选生图配置** {char_dir}/illustration.yml（缺失/损坏 → {}）。

        与 profile.yml 的 halo 字段**刻意分开**: 后者是给其他角色/扮演查阅的设定,
        这里专供生图（模型没见过的非典型形状——如遥香的非闭合三角光环——靠它讲清）。
        支持字段（都可选; 非字符串/空 → 忽略）:
            halo_hint:      光环形状描述（替换引擎默认光环提示）
            character_hint: 外观要点/性格等, 追加到【角色本体】标签
        """
        path = self.root / character_id / "illustration.yml"
        if not path.is_file():
            return {}
        try:
            data = load_yaml_file(path)
        except Exception as e:                       # noqa: BLE001 — 读不了就空（不阻断）
            logger.warning("[%s] illustration.yml 加载失败: %s", character_id, e)
            return {}
        if not isinstance(data, dict):
            return {}
        out: dict[str, str] = {}
        for key in ("halo_hint", "character_hint"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                out[key] = _fold_prompt_text(val)     # 折行 → 单行（prompt 里更稳）
        return out

