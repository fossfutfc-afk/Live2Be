# -*- coding: utf-8 -*-
"""角色搜索别名索引 — 从 config/characters/*/profile.yml 自动构建。

解决"搜不到角色"：AI 常以别名/繁体/日文名/昵称搜索，而萌娘百科 opensearch
只做标题前缀匹配，别名大多不命中（实测: "遥香"→[], "ハルカ"→[], "ムツキ"→[]）。
索引把 别名 → 规范标题（most_called_name 去空格, 实测=萌娘百科标题；
含"鬼方佳代子"→命中"鬼方佳世子"这类译名差异），search 执行时命中即追加规范标题重试。

宁缺勿错: 只收 profile 里已有的名字字段（显示名/en_name/jp_name/other_names），
不臆造昵称；同一别名命中多个角色 → 映射到集合，调用方都试。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from parsing.dynamic_character_parser import get_display_name

# 别名切分符: 中英文逗号 / 顿号 / 分号 / 斜杠
_NAME_SPLIT_RE = re.compile(r"[,，、;；/｜|]")

# 去所有空白（含全角空格）
_WS_RE = re.compile(r"[\s　]+")

# 括号块（如 "（日文名）"）剔除——别名规范化时括号内容不参与匹配
_PAREN_RE = re.compile(r"[（(\[【［][^）)\]】］]*[）)\]】］]")


def normalize_query(s: str) -> str:
    """别名/查询规范化: 小写 + 去空白 + 剔除括号块。"""
    s = _WS_RE.sub("", s.strip())
    s = _PAREN_RE.sub("", s).strip()
    return s.lower()


def _name_pieces(field_value: str) -> list[str]:
    """一个名字字段 → 别名片段列表（先按标点切, 再按空白拆出子 token）。

    例: "浅黄无月，无月，睦月，Mukki，地雷妹，大头"
        → [浅黄无月, 无月, 睦月, Mukki, 地雷妹, 大头]
    "Igusa Haruka" → [Igusa Haruka, igusa, haruka]（子 token 供单名搜索）
    """
    pieces: list[str] = []
    for part in _NAME_SPLIT_RE.split(field_value):
        part = part.strip()
        if not part:
            continue
        pieces.append(part)
        if len(part.split()) > 1:
            pieces.extend(part.split())
    return pieces


def _field_pieces(field_value: object) -> list[str]:
    """名字字段 → 别名片段列表。兼容两种写法:
        - 字符串（逗号/顿号分隔, 老 profile 风格）: "遥香，瑶香"
        - 字符串列表（AI 写入风格）: ['空崎阳奈', '大可爱', ...]
    其他类型（int/None/嵌套）→ 空列表, 宁缺勿错。
    """
    if isinstance(field_value, str):
        return _name_pieces(field_value)
    if isinstance(field_value, list):
        pieces: list[str] = []
        for item in field_value:
            if isinstance(item, str) and item.strip():
                pieces.extend(_name_pieces(item))
        return pieces
    return []


def _load_yaml_dict(path: Path) -> dict[str, Any] | None:
    """读 profile YAML, 缺失/解析失败/非对象 → None（宁缺勿错）。"""
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 索引是尽力而为, 坏文件跳过即可
        return None
    return data if isinstance(data, dict) else None


def build_alias_index(root: str | Path) -> dict[str, set[str]]:
    """构建 别名(规范化) → {规范标题} 索引。

    规范标题 = most_called_name 去空格。别名集合 = 各名字字段切分后的每一项
    （含子 token，如 "Haruka" / "ハルカ"）。遍历所有角色目录。
    """
    index: dict[str, set[str]] = {}
    base = Path(root) / "config" / "characters"
    if not base.is_dir():
        return index

    for char_dir in sorted(base.iterdir()):
        if not char_dir.is_dir():
            continue
        profile_path = char_dir / "profile.yml"
        if not profile_path.exists():
            continue
        data = _load_yaml_dict(profile_path)
        if data is None:
            continue
        display = get_display_name(data)
        if not display:
            continue
        canonical = normalize_query(display)
        if not canonical:
            continue

        # 名字字段 → 每个片段都是该角色的别名
        for field in (display, data.get("en_name"), data.get("jp_name"),
                      data.get("other_names")):
            for piece in _field_pieces(field):
                key = normalize_query(piece)
                if key:
                    index.setdefault(key, set()).add(canonical)
    return index


def canonical_titles_for(query: str, root: str | Path) -> list[str]:
    """查询命中的规范标题列表（去重排序）。未命中 → []。"""
    hits = build_alias_index(root).get(normalize_query(query))
    return sorted(hits) if hits else []
