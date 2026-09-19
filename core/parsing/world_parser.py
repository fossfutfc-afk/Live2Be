"""世界观解析 — overview.yml → 可注入的世界知识。

约定（config/settings/world/overview.yml 的三档结构）:
    common  全员皆知的事实   → 注入每个角色的 System Prompt（角色理应知道）
    hidden  多数角色不知道   → 默认不注入（secret; 仅 knowledge.yml 授予的角色知道）
    system  元规则/安全边界  → 注入（恋爱合法、暴力血腥需求直接叫停）

用法:
    from core.parsing.world_parser import load_world, world_to_prompt

    world = load_world("config/settings/world/overview.yml")
    chunk = world_to_prompt(world)        # common + system
    if chunk:
        system_prompt += "\\n\\n" + chunk
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from core import paths
from core.common import err

#: 项目根（`core/paths.py` 的宏——绝对路径, uvicorn/IDE 从任意 CWD 启动都能找到）
_PROJECT_ROOT = paths.ROOT

#: 默认路径（项目根绝对, cwd 无关）
DEFAULT_WORLD_PATH = paths.WORLD_OVERVIEW_PATH

#: 三档（顺序即渲染顺序）
_TIERS = ("common", "hidden", "system")


@dataclass
class WorldConfig:
    """解析后的世界观（按档分类的规则列表）。"""

    common: list[str] = field(default_factory=list)
    hidden: list[str] = field(default_factory=list)
    system: list[str] = field(default_factory=list)


def load_world(path: str | Path) -> WorldConfig:
    """读取 overview.yml → WorldConfig。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 顶层不是有效 dict / 某档不是 list。
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(err("NotFound", f"世界观文件不存在: {path}"))

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(err("InvalidYaml", f"{path.name} 内容不是有效 YAML dict"))

    world = WorldConfig()
    for tier in _TIERS:
        rules = data.get(tier) or []
        if not isinstance(rules, list):
            raise ValueError(err("InvalidTier", f"{path.name} 的 {tier} 档必须是列表"))
        setattr(world, tier, [str(r) for r in rules if str(r).strip()])
    return world


def world_to_prompt(world: WorldConfig, include_hidden: bool = False) -> str:
    """渲染为可注入的 System Prompt 块（默认 common + system 档）。

    Args:
        world: load_world 的产物。
        include_hidden: True 时把 hidden 档也注入——默认不注入，它是 secret，
            仅当调用方有明确理由（如角色 knowledge.yml 授予）才开启。

    Returns:
        空串 = 无内容（调用方可跳过拼装）。
    """
    sections: list[tuple[str, list[str]]] = [("世界常识", world.common)]
    if include_hidden:
        sections.append(("隐秘知识", world.hidden))
    sections.append(("世界规则", world.system))

    lines: list[str] = []
    for title, rules in sections:
        if rules:
            lines.append(f"【{title}】")
            lines.extend(f"- {r}" for r in rules)
    return "\n".join(lines)
