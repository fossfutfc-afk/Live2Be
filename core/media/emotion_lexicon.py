# -*- coding: utf-8 -*-
"""角色情绪词表 — assets/illustration/{char}/emotions.yml 的逐行解析与注入渲染。

与 core/media/manifest.py 的分工:
    manifest  → 键:路径 映射（yaml 解析, catalog 查库用）
    lexicon   → 键 + 行尾示范注释 + eg[键] 例句 → 给主 LLM 的词表注入文本（few-shot）

emotions.yml 格式（v2 视觉意图协议, DESIGN_VISUAL_PROTOCOL.md §4/§8）:
    emotions:
      nomal: diff/haruka_spr_00.png      # 行尾注释 = 示范（何时用）
      eyes_closed: diff/haruka_spr_10.png  # ...
      # eg[eyes_closed]: 例句...           # 该键的例句示范（eg[键名] 显式标注归属）
    - 键 = 情绪名 id（主 LLM 输出用）; 值 = diff/ 相对路径
    - 行尾 # 注释 = 给主 LLM 的示范（few-shot）
    - # eg[键名]: 例句 —— eg 行是注释, eg[键名] 显式归键（不依赖位置）

逐行解析原因: yaml.safe_load 拿不到行尾注释与 eg 例句——而 few-shot 正是它们的价值。
缺失/损坏/无 emotions 键 → 空词表（宁缺勿错, 不阻断 VN）。

place 词表（per 世界, 协议 §5）: 封闭通用地点语义。当前数据源 =
assets/_director_whitelist.json 的 common_scenes（已涵盖 campus/classroom/ramen 等）。
未来可独立为 assets/_world_places.json。
"""

from __future__ import annotations

import json
from pathlib import Path

# assets/ 默认根（core/media/emotion_lexicon.py → ../../.. → 项目根/assets）
_DEFAULT_ASSETS = Path(__file__).resolve().parent.parent.parent / "assets"
_DEFAULT_WHITELIST = _DEFAULT_ASSETS / "_director_whitelist.json"


# ============================================================================
# emotion 词表（per 角色）
# ============================================================================

def load_emotion_lexicon(char_dir: str | Path) -> dict[str, dict]:
    """逐行解析角色的 emotions.yml → {情绪id: {"path", "comment", "eg"}}。

    行尾 # 注释 → comment（few-shot 示范）; `# eg[键]: 例句` → eg（该键例句）。
    空键占位（scan_diff.ps1 雏形）跳过; 解析失败 → 空（宁缺勿错）。
    """
    char_dir = Path(char_dir)
    path = char_dir / "emotions.yml"
    if not path.is_file():
        return {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    lex: dict[str, dict] = {}
    in_emotions = False
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        # eg 例句行（注释, eg[键名] 显式归键）——可在任何位置, 不依赖紧跟
        if stripped.startswith("# eg[") and "]" in stripped:
            _assign_eg(lex, stripped)
            continue
        if stripped.startswith("#"):
            continue
        if stripped == "emotions:":
            in_emotions = True
            continue
        if not in_emotions:
            continue
        if ":" not in stripped:
            continue
        key, _, rest = stripped.partition(":")
        key, rest = key.strip(), rest.strip()
        if not key or not rest:
            continue                      # 空键占位 / 空值 → 跳过
        path_part, _, comment = rest.partition("#")
        path_part, comment = path_part.strip(), comment.strip()
        if not path_part:
            continue
        lex[key] = {"path": path_part, "comment": comment, "eg": ""}
    return lex


def _assign_eg(lex: dict[str, dict], eg_line: str) -> None:
    """解析 `# eg[键]: 例句` 并归入对应键（键不存在则忽略, 宁缺勿错）。"""
    inner = eg_line[len("# eg["):]
    key, _, rest = inner.partition("]")
    eg_text = rest.lstrip(":").strip()
    key = key.strip()
    if key and eg_text and key in lex:
        lex[key]["eg"] = eg_text


def build_emotion_injection(char_dir: Path) -> str:
    """生成表情词表注入文本（标注层受众——协议 §11: 开场喂一遍 + 犯错重喂）。

    记录流 v2（2026-09-10）起**只给标注层用**（`bond_story.start_session` 的
    `_lexicon_hint`）：writer 不写 emotion，词表对创作不起作用，故已退出盒B
    （决策 #24——盒内"你不用写 emotion"式提醒属白熊效应且废 token）。

    无词表 → 空串（调用方跳过注入）。格式: 键 + 示范注释 + eg 例句（few-shot）。
    """
    lex = load_emotion_lexicon(char_dir)
    if not lex:
        return ""
    lines = [
        "【表情标注词表】（仅当前角色）",
        "给每个情绪单元标注 emotion 时，只从下面选；词表外的情绪不要标（标了会被忽略）。",
    ]
    for key, item in lex.items():          # 保持作者文件顺序（默认态在前）
        line = f"  {key}: {item['comment']}" if item["comment"] else f"  {key}"
        if item["eg"]:
            line += f"  eg: {item['eg']}"
        lines.append(line)
    return "\n".join(lines)


# ============================================================================
# place 词表（per 世界, 当前数据源 = _director_whitelist.json 的 common_scenes）
# ============================================================================

def load_place_lexicon(whitelist_path: str | Path | None = None) -> list[str]:
    """place 候选（封闭通用地点语义）。缺失/损坏 → []（宁缺勿错）。"""
    p = Path(whitelist_path) if whitelist_path else _DEFAULT_WHITELIST
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    scenes = data.get("common_scenes", []) if isinstance(data, dict) else []
    return [s for s in scenes if isinstance(s, str)]


def build_place_injection(whitelist_path: str | Path | None = None) -> str:
    """生成主 LLM 可用的地点词表注入文本（协议 §5: 封闭词表 + 不切省略）。"""
    places = load_place_lexicon(whitelist_path)
    if not places:
        return ""
    return (
        "【地点标注词表】场景切换时 place 只从下面选（同一地点不标, 省略即保持）：\n"
        + ", ".join(places)
    )
