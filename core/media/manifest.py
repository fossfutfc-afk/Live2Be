# -*- coding: utf-8 -*-
"""角色差分 manifest — assets/illustration/{char}/emotions.yml（情绪词表真源）。

形态（v2 视觉意图协议, DESIGN_VISUAL_PROTOCOL.md §4/§8）:
    emotions:                 # 情绪名(id, 主 LLM 输出用) → 相对 {char} 目录的静态 png
      正常1: diff/haruka_spr_00.png   # 行尾注释 = 给主 LLM 的示范（few-shot, 本层不提取）
    spine: haruka_spr        # 可选: 优先的 spine 导出包名（= spine/ 下目录名, 兼容旧字段）

2026-08 真源由 _media.yml 改为 emotions.yml（键=情绪名id, 值=diff/ 相对路径,
行尾注释=示范）; 旧 _media.yml 不再读取。
缺失/损坏/格式不对 → 降级 {"sprites": {}, "spine": None}（宁缺勿错, 查询返回 None, 不阻断引擎）。
"""
from __future__ import annotations

from pathlib import Path

import yaml


def load_character_manifest(char_dir: Path) -> dict:
    """读取角色情绪词表 → {"sprites": {情绪: 相对路径}, "spine": 包名|None}。"""
    path = char_dir / "emotions.yml"
    empty = {"sprites": {}, "spine": None}
    if not path.is_file():
        return empty
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception:
        return empty
    if not isinstance(data, dict):
        return empty
    sprites = data.get("emotions")
    if not isinstance(sprites, dict):
        sprites = {}
    # 键转 str（防御: yaml 数值键）; 值必须是非空字符串（含 None/数字 → 丢弃）
    sprites = {
        str(k): v for k, v in sprites.items()
        if isinstance(v, str) and v.strip()
    }
    spine = data.get("spine")
    return {
        "sprites": sprites,
        "spine": str(spine) if isinstance(spine, str) and spine else None,
    }
