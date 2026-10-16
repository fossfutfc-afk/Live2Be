"""core/bond — 羁绊剧情（Bond Story）域: 引擎 + 标注层。

    bond_story/          引擎包（记录流 v2）: BondStoryEngine / BondScene / SceneLoopError
    bond_progress.py     羁绊进度（对话轮数）
    emo_text.py          标注层: 情绪词表键（按记录, 一板一次调用）
    place_annotate.py    标注层: 换场锚点（事件型稀疏）
    place_cues.py        换场线索词（预筛, 0 调用）
    variant_annotate.py  第二遍选图（时刻 / 天气 / 差分）
    emotion_annotate.py  批式标注入口（协议单测用, 见 `# EXT: emotion-batch-v1`）

v1 的动作契约整族（bond_actions / bond_executor / memorial_actions / sentence_splitter /
stream_probe）已删: 现役唯一形态 = **记录流 v2**, 收到动作 dict 一律打回重发。
"""

from __future__ import annotations

from core.bond.bond_progress import BondProgress
from core.bond.bond_story import BondScene, BondStoryEngine, SceneLoopError

__all__ = [
    "BondScene",
    "BondStoryEngine",
    "SceneLoopError",
    "BondProgress",
]
