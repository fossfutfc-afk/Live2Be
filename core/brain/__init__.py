# -*- coding: utf-8 -*-
"""Brain 模块（角色记忆, DESIGN_BRAIN.md）——记忆生命周期: 存储/巩固/再巩固/回忆。

术语（脑科学对应）:
    hippocampus.py      海马体 — 记忆存储（WikiStore 双层级 + 归并 + 哈希）
    consolidation.py    记忆巩固 — 睡眠整合（digest_session）
    reconsolidation.py  记忆再巩固 — 记忆修订（migrate_wiki）
    recall.py           回忆 — 检索注入（build_brain_injection）
"""

from __future__ import annotations

from core.brain.hippocampus import (
    SCHEMA_VERSION,
    WikiStore,
    compute_character_hash,
)
from core.brain.consolidation import digest_session
from core.brain.reconsolidation import migrate_wiki
from core.brain.recall import build_brain_injection
