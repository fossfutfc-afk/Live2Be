# -*- coding: utf-8 -*-
"""EffectResolver — 特效解算（DESIGN_RENDERER.md §五）。

设计原则:
    - 纯查表算法（非 LLM）: emotion（封闭词表）→ 特效类型——确定性、可测试
    - 特效是情绪的外化——与差分同源（emotion），但独立输出（差分是"图"，特效是"动效"）
    - 分层配置: 多数角色用全局表; 个别角色可自定义覆盖（per 角色表优先, 全局兜底）

全局默认表: 代码内置（M1 快速; 未来可迁 config/settings/effects.toml 供作者改, §十三 开放问题 6）。
per 角色覆盖: assets/illustration/{char}/effects.yml（可选, 未写条目回落到全局表）——
    yaml 顶层 {emotion: [特效...]}, 值兼容列表或逗号分隔字符串（宽容, 宁缺勿错）。

CLI 降级: [✨] 符号标注（文本流不破坏）——特效符号由平台定义, 本模块只出特效名。
"""
from __future__ import annotations

from pathlib import Path

import yaml

#: 全局默认特效表（emotion → 特效列表; 未列出 = 无特效）
_GLOBAL_EFFECTS: dict[str, list[str]] = {
    "smile": ["sparkle"],              # 微笑冒星星
    "happy": ["sparkle"],
    "joy": ["sparkle"],
    "giggle": ["sparkle"],
    "embarrass": ["blush", "notes"],   # 害羞: 脸红 + 音符
    "shy": ["blush", "notes"],
    "angry": ["anger"],                # 怒气符号
    "rage": ["anger"],
    "sad": ["raindrop"],               # 雨点/泪滴
    "cry": ["raindrop"],
    "surprise": ["bang"],              # 惊叹号
    "shock": ["bang"],
    "love": ["heart"],                 # 爱心飘浮
    "panic": ["bang", "sweat"],
    "panic_2": ["bang", "sweat"],
    "outburst": ["bang", "anger"],
    "serious": [],                     # 平静无特效
    "nomal": [],                       # 默认无特效
}


def load_character_effects(char_dir: str | Path) -> dict[str, list[str]]:
    """读角色可选特效覆盖表 assets/illustration/{char}/effects.yml。

    格式: 顶层 {emotion: [特效...]}; 值兼容 列表 或 逗号分隔字符串。
    缺失/损坏 → {}（宁缺勿错, 全局表兜底）。
    """
    path = Path(char_dir) / "effects.yml"
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception:                                  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in data.items():
        if not isinstance(k, str) or not k.strip():
            continue
        if isinstance(v, list):
            fx = [str(x).strip() for x in v if str(x).strip()]
        elif isinstance(v, str):
            fx = [x.strip() for x in v.replace("，", ",").split(",") if x.strip()]
        else:
            continue
        if fx:
            out[k.strip()] = fx
    return out


class EffectResolver:
    """特效解算: 分层查表（角色表 → 全局表 → 空）——确定性。"""

    def __init__(self, char_dir: str | Path | None = None):
        """char_dir=None → 仅全局表（测试/无角色资产时）。"""
        self._table = dict(_GLOBAL_EFFECTS)
        if char_dir is not None:
            self._table.update(load_character_effects(char_dir))

    def resolve(self, emotions: list[str | None]) -> list[list[str]]:
        """emotion 序列 → 逐段特效序列（未列出/None → 空列表 = 无特效）。"""
        return [list(self._table.get(e, [])) if e else [] for e in emotions]

    def effects_for(self, emotion: str | None) -> list[str]:
        """单条查询（供未来特效音/单段渲染用）。"""
        return list(self._table.get(emotion, [])) if emotion else []
