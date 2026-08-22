"""core/bond — 羁绊剧情（Bond Story）域。

引擎与契约的统一归属（对齐 core/mmt 的 mmt_ 前缀模式，2026 重构自 core/ 平铺）:

    bond_story.py     引擎: BondStoryEngine / BondScene / SceneLoopError
    bond_actions.py   契约: build_story_registry（story_scene / story_end 双动作）
    bond_executor.py  执行层: StoryExecutor / StoryExecError
    bond_progress.py  羁绊进度: BondProgress（对话轮数）
    bond_save.py      存档: BondStorySave / load_save / list_saves

契约层的域名为 story（DOMAIN_STORY, 动作 story_scene/story_end）——文件名用 bond_
前缀统一, 与引擎概念一致; LLM 契约仍叫 story_*。
"""

from __future__ import annotations

from core.bond.bond_story import BondScene, BondStoryEngine, SceneLoopError
from core.bond.bond_progress import BondProgress
from core.bond.bond_save import BondStorySave, load_save, list_saves
from core.bond.bond_executor import StoryExecError, StoryExecutor
from core.bond.bond_actions import build_story_registry

__all__ = [
    "BondScene",
    "BondStoryEngine",
    "SceneLoopError",
    "BondProgress",
    "BondStorySave",
    "load_save",
    "list_saves",
    "StoryExecError",
    "StoryExecutor",
    "build_story_registry",
]
