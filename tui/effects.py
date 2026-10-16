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

#: 全局默认特效表（emotion → 特效列表; 未列出 = 无特效）。
#: 覆盖 4 角色实际词表键的语义归类（2026-08-29 扩表——按情绪语义, 非精确角色）:
#:   开心系: smile/smile_2/happy/joy/giggle/laugh/tease → sparkle
#:   害羞系: embarrass/embarrass_2/embarrassed/shy      → blush + notes
#:   愤怒系: angry/rage/enraged/enraged_2/outburst      → anger（outburst 加 bang）
#:   低落系: sad/cry/depressed/depressed_2              → raindrop
#:   惊慌系: panic/panic_2/surprise/shock               → bang + sweat
#:   喊话系: shout/shout_2/strive                       → anger
#:   不安系: worry/nervous                              → sweat
#:   平静系: nomal/serious/confident/fake_confident/think/pensive/sigh/eyes_closed → 无
_GLOBAL_EFFECTS: dict[str, list[str]] = {
    "smile": ["sparkle"],              # 微笑冒星星
    "smile_2": ["sparkle"],
    "happy": ["sparkle"],
    "joy": ["sparkle"],
    "giggle": ["sparkle"],
    "laugh": ["sparkle"],              # 开怀大笑
    "tease": ["sparkle"],              # 捉弄（恶作剧得逞）
    "embarrass": ["blush", "notes"],   # 害羞: 脸红 + 音符
    "embarrass_2": ["blush", "notes"],
    "embarrassed": ["blush", "notes"],  # 遥香键名（2026-08-29 作者改词）
    "shy": ["blush", "notes"],
    "angry": ["anger"],                # 怒气符号
    "rage": ["anger"],
    "enraged": ["anger"],
    "enraged_2": ["anger"],
    "sad": ["raindrop"],               # 雨点/泪滴
    "cry": ["raindrop"],
    "depressed": ["raindrop"],         # 遥香键名（惊慌/低落）
    "depressed_2": ["raindrop"],
    "surprise": ["bang"],              # 惊叹号
    "shock": ["bang"],
    "love": ["heart"],                 # 爱心飘浮
    "panic": ["bang", "sweat"],
    "panic_2": ["bang", "sweat"],
    "outburst": ["bang", "anger"],
    "shout": ["anger"],                # 喊话
    "shout_2": ["anger"],
    "strive": ["anger"],               # 遥香键名（坚定喊话）
    "worry": ["sweat"],                # 担忧
    "nervous": ["sweat"],              # 紧张
    "serious": [],                     # 平静无特效
    "nomal": [],                       # 默认无特效
    "confident": [],                   # 自信（平静）
    "fake_confident": [],              # 强装自信（平静）
    "think": [],                       # 思考
    "pensive": [],                     # 沉思
    "sigh": [],                        # 叹气（平静）
    "eyes_closed": [],                 # 闭眼
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
