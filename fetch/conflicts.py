"""跨文件键冲突检测（A3）— 纯函数, 无 I/O。

主项目合并语义（parsing/dynamic_character_parser.py）:
    按 _CHARACTER_FILES 顺序遍历 5 个文件, `if k not in merged` 才写入
    → **先加载优先（profile 赢）**, 后出现的同名顶层 key 被静默忽略。

A3 提前发现这种"被静默覆盖"的顶层 key, 输出警告:
    - 提示哪个文件赢了、哪个被忽略（不是错误——主项目语义明确, 只是提醒
      是否是有意覆盖）
    - 逐文件报告, 方便 LLM/用户决定是否删除重复

用法:
    conflicts = find_top_level_conflicts({"profile.yml": {...}, "knowledge.yml": {...}})
    # conflicts 是 (winner_file, ignored_file, key) 元组列表
"""

from __future__ import annotations

from typing import Any, Iterable

# 合并优先级顺序（与主项目 dynamic_character_parser._CHARACTER_FILES 一致）:
# 前面的赢。独立定义在本模块——作为"冲突检测语义"的唯一真源, 避免循环导入。
MERGE_ORDER = (
    "profile.yml",
    "personality.yml",
    "knowledge.yml",
    "experience.yml",
    "typical.yml",
)


def find_top_level_conflicts(files: dict[str, dict[str, Any]]) -> list[tuple[str, str, str]]:
    """检测顶层 key 跨文件重复。

    files: {文件名: 已解析的 YAML dict}。只接受五件套文件名。
    返回 [(赢者文件, 被忽略文件, key), ...]，按 key 顺序排序。

    语义: 顺序靠前的文件赢（profile 最前 → 覆盖一切）。重复 key 报一次:
    赢者是顺序最靠前出现该 key 的文件, 被忽略者是其后的第一个。
    """
    seen: dict[str, str] = {}   # key → 赢者文件
    conflicts: list[tuple[str, str, str]] = []
    reported: set[str] = set()  # 已报过的 key（只报第一次冲突）

    for name in MERGE_ORDER:
        data = files.get(name)
        if data is None:
            continue
        for key in data:
            if key not in seen:
                seen[key] = name
            elif key not in reported:
                conflicts.append((seen[key], name, key))
                reported.add(key)
    return conflicts


def format_conflicts(conflicts: Iterable[tuple[str, str, str]]) -> list[str]:
    """把冲突元组渲染成人类可读的警告行（给 LLM/用户看）。"""
    return [
        f"⚠️ 顶层 key「{key}」跨文件重复: {ignored} 的定义会被 {winner} 覆盖"
        f"（主项目先加载优先）。如非有意, 请删除其中一个"
        for winner, ignored, key in conflicts
    ]
