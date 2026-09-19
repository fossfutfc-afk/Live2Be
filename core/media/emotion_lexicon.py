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

place 词表（**只剩降级兜底**, PL4 2026-09-19）: 现役地点语料 =
`config/settings/world/place_entities.json`（`core/media/place_table.py`）;
本文件的 `load_place_lexicon` 读旧白名单 `assets/_director_whitelist.json` 的
`common_scenes`，**只在表读不出来时**当 `place_keys` 用（`bond_story` 的回落路径）。
（旧 `build_place_injection` 已删: 生产零调用, 且它宣传的"主 LLM 只从词表里选 place"
已被记录流 v2 + "主 LLM 零内容词表"裁决废掉。）
"""

from __future__ import annotations

import json
from pathlib import Path

from core import paths

# assets/ 默认根 + 地点白名单（`core/paths.py` 的宏）
_DEFAULT_ASSETS = paths.ASSETS_DIR
_DEFAULT_WHITELIST = paths.DIRECTOR_WHITELIST_PATH


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


def assets_root() -> Path:
    """`assets/` 根（唯一解析点）——`bond_story` 与 digest 词表注入共用。

    此前 `core/bond/bond_story.py:501` 与 `core/media/catalog.py` 各自拼过一次
    同样的三层 `parents` 路径；集中到这里，换布局只改一处。
    **值现在来自 `core/paths.py` 的宏**（2026-09-19: 路径不许再散着拼）。
    """
    return paths.ASSETS_DIR


def render_emotion_scale(lexicon: dict[str, dict], keys) -> str:
    """**只渲染给定键**的情绪标尺（digest 受众——§3.3.2）。

    与 `build_emotion_injection`（标注层受众）的分工：
        - 那个给**标注员**：全词表 + 用法 + 例句, 教它怎么标
        - 这个给 **digest Round A**：**只给本段真的出现的键**, 让 LLM 判断
          "这条 episode 的情绪摆幅多大、峰值多猛"——**不是**让它改标注

    为什么只给出现的键: 全词表（14 键 × 2~3 行）对一个只出现 5 键的段是纯噪声,
    且会诱使 LLM 拿没出现的键去"凑"强度。

    Returns:
        文本块（含标题行）; `lexicon` 或 `keys` 为空、无交集 → 空串（调用方跳过注入）。
        **键不在词表里也照样列出**（只有键名, 无注释）——保持完整, 不静默丢。
    """
    wanted = [k for k in dict.fromkeys(keys) if isinstance(k, str) and k.strip()]
    if not lexicon or not wanted:
        return ""
    lines = [
        "【本段情绪标尺】（作者为该角色手写的强度语义——**判断情绪摆幅/峰值时参考**）",
    ]
    for key in wanted:
        item = lexicon.get(key)
        if not item:
            lines.append(f"  {key}（作者未写注释）")
            continue
        line = f"  {key}: {item['comment']}" if item.get("comment") else f"  {key}"
        if item.get("eg"):
            line += f"  eg: {item['eg']}"
        lines.append(line)
    return "\n".join(lines)


# ============================================================================
# place 词表 —— **只剩降级兜底**（现役语料 = place_entities.json / place_table.py）
# ============================================================================

def load_place_lexicon(whitelist_path: str | Path | None = None) -> list[str]:
    """旧白名单 `common_scenes`（31 条裸 slug）——**表读不出来时的兜底键集**。

    唯一消费方 = `core/bond/bond_story.py` 的
    `self._place_keys = self._place_table.keys() or load_place_lexicon()`。
    正常路径（表在位）它一次都不会被调用。缺失/损坏 → []（宁缺勿错）。
    """
    p = Path(whitelist_path) if whitelist_path else _DEFAULT_WHITELIST
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    scenes = data.get("common_scenes", []) if isinstance(data, dict) else []
    return [s for s in scenes if isinstance(s, str)]
