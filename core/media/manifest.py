# -*- coding: utf-8 -*-
"""角色差分 manifest — assets/illustration/{char}/_media.yml。

形态:
    sprites:                 # 情绪 → 相对 {char} 目录的静态 png（情绪白名单=这些键）
      smile: diff/haruka_spr_03.png
    spine: haruka_spr        # 可选: 优先的 spine 导出包名（= spine/ 下目录名）

缺失/损坏/格式不对 → 降级 {"sprites": {}, "spine": None}（宁缺勿错, 查询返回 None, 不阻断引擎）。
"""
from __future__ import annotations

from pathlib import Path

import yaml


def load_character_manifest(char_dir: Path) -> dict:
    """读取角色 manifest → {"sprites": {情绪: 相对路径}, "spine": 包名|None}。"""
    path = char_dir / "_media.yml"
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
    sprites = data.get("sprites")
    if not isinstance(sprites, dict):
        sprites = {}
    sprites = {str(k): str(v) for k, v in sprites.items() if str(v)}
    spine = data.get("spine")
    return {
        "sprites": sprites,
        "spine": str(spine) if isinstance(spine, str) and spine else None,
    }
