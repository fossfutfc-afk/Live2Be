"""背景资源查库 — assets/background/ 命名派生（纯数据, 零 manifest）。

命名规则（已核实 1089 张 jpg 全带 BG_ 前缀）:
    BG_{Scene}_{Variant?}.jpg
    - 末尾 _X 只有命中变体白名单才算变体, 否则属于场景名
      （BG_GehennaCampus_Night → scene=gehenna_campus, variant=night）
      （BG_WildhuntStreet     → scene=wildhunt_street, 无变体）
    - 场景 id 统一 snake_case（camelCase → class_room_2）, 磁盘文件名不动

变体白名单是数据驱动的（新后缀非场景名 → 加进 VARIANT_TOKENS）;
非 BG_ 前缀/异常命名 → 防御性原样 snake（宁缺勿错, 不崩）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# 变体白名单（小写, 命中才从场景名切分; 大小写变体经 .lower() 归一）
# 2026-08-22 从 1089 张 jpg 后缀统计得到: 高频真实变体是 night/sunset/ruin/erode/blur/dark/off 等
VARIANT_TOKENS = frozenset({
    "night", "sunset", "ruin", "erode", "blur", "dark", "off",
    "fineday", "cloudy", "rain", "fog", "dawn", "day", "fire",
    "tent", "sky", "fake", "party", "alert",
})

_CAMEL_SPLIT = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])"          # ClassCorridor → Class_Corridor
    r"|(?<=[A-Z])(?=[A-Z][a-z])"       # CSAbydos → CS_Abydos（缩略词边界）
    r"|(?<=[a-zA-Z])(?=[0-9])"         # ClassRoom2 → Class_Room_2（数字边界）
)


@dataclass(frozen=True)
class BackgroundMedia:
    """一条背景资源。scene_id 是语义场景 id, variant 是时刻/状态变体。"""
    scene_id: str
    path: Path
    variant: str | None = None


def _snake(name: str) -> str:
    """camelCase → snake_case（数字边界也切: ClassRoom2 → class_room_2）。"""
    return _CAMEL_SPLIT.sub("_", name).lower()


def derive_background(stem: str) -> tuple[str, str | None]:
    """解析一个背景文件名（不含扩展名）→ (scene_id, variant)。

    变体后缀只认白名单（否则是场景名一部分）; 非 BG_ 前缀防御性原样 snake。
    """
    base = stem[3:] if stem.startswith("BG_") else stem
    if "_" in base:
        head, _, tail = base.rpartition("_")
        if tail.lower() in VARIANT_TOKENS:
            return _snake(head), tail.lower()
    return _snake(base), None
