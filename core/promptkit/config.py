# -*- coding: utf-8 -*-
"""promptkit 配置 — settings.toml [promptkit] 分组（运行时用户配置, gitignore）。

与 llm/client.py 读取模式一致（tomllib）; 缺失/损坏 → 默认, 不阻塞。
引擎构造参数可覆盖（task_card: bool | None——None = 读配置; 测试/bench 固定用）。
"""
from __future__ import annotations

import logging
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "settings.toml"


def _read_settings() -> dict:
    """读项目根 settings.toml → dict（缺失/损坏 → {}, 不阻塞）。"""
    try:
        with open(_SETTINGS_PATH, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:                    # noqa: BLE001 — 损坏配置不阻塞
        logger.warning("promptkit settings.toml 读取失败, 用默认: %s", e)
        return {}


def task_card_enabled() -> bool:
    """本回合任务卡开关（DESIGN_PROMPTKIT §6）: [promptkit].task_card, 默认 true。

    false = 现网行为逐字节不变（无任务卡, 供 A/B 对照与回归）。
    """
    try:
        v = (_read_settings().get("promptkit") or {}).get("task_card", True)
    except Exception:                          # noqa: BLE001 — 非法形态回退默认
        return True
    return bool(v) if isinstance(v, bool) else True
