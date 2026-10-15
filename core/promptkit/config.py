"""promptkit 配置 — settings.toml [promptkit] 分组（运行时用户配置, gitignore）。

缺失/损坏 → 默认, 不阻塞。引擎构造参数可覆盖（task_card: bool | None——None = 读配置;
测试/bench 固定用）。
"""
from __future__ import annotations

from infra import settings


def _read_settings() -> dict:
    """settings.toml 全量（缺失/损坏 → {}）。"""
    return settings.raw()


def task_card_enabled() -> bool:
    """本回合任务卡开关（DESIGN_PROMPTKIT §6）: [promptkit].task_card, 默认 true。

    false = 现网行为逐字节不变（无任务卡, 供 A/B 对照与回归）。
    """
    try:
        v = (_read_settings().get("promptkit") or {}).get("task_card", True)
    except Exception:                          # noqa: BLE001 — 非法形态回退默认
        return True
    return bool(v) if isinstance(v, bool) else True
