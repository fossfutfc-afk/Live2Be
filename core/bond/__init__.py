"""core/bond — 羁绊剧情（Bond Story）域。

引擎与契约的统一归属（对齐 core/mmt 的 mmt_ 前缀模式，2026 重构自 core/ 平铺）:

    bond_story/       引擎包（C9 起）: BondStoryEngine / BondScene / SceneLoopError（记录流文法消费）
    bond_progress.py  羁绊进度: BondProgress（对话轮数）
    emo_text.py       标注层: 情绪词表键（按记录, 一轮一次调用）
    place_annotate.py 标注层: 换场锚点（事件型稀疏）
    place_cues.py     换场线索词（PL3 预筛）
    variant_annotate.py 第二遍选图（时刻/天气/差分）
    emotion_annotate.py 批式标注入口（**协议单测/简单调用**——见 `# EXT: emotion-batch-v1`）

⚠️ **2026-09-21: v1 动作契约整族退役删除** —— `bond_actions.py`（story_scene/story_end/
memorial_enter 三动作 registry）、`bond_executor.py`（StoryExecutor）、`memorial_actions.py`
（memorial 域 exit 动作）、`sentence_splitter.py`（v1 切句）、`stream_probe.py`（v1 流式嗅探）
与 `BondScene.from_action` 一并移除。现役唯一形态 = **记录流 v2**（一行一条 JSON，
见 `bond_story/engine.py` 模块 docstring）；收到动作 dict 一律打回重发。
考古读 git 历史与 `docs/ARCH_REVIEW_2026-09-20.md` P0-2。
"""

from __future__ import annotations

from core.bond.bond_story import BondScene, BondStoryEngine, SceneLoopError
from core.bond.bond_progress import BondProgress

__all__ = [
    "BondScene",
    "BondStoryEngine",
    "SceneLoopError",
    "BondProgress",
]
