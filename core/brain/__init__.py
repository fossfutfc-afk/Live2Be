# -*- coding: utf-8 -*-
"""Brain 算法（角色记忆, DESIGN_BRAIN.md）——**算法不是跨 session 实体**。

每个 session 是平行世界: 各自的 events.jsonl（真源）→ brain 算法 → 各自唯一的
wiki（sessions/{id}/brain/wiki.json）。另一个世界线的成长与本 session 无关——
无角色级 wiki、无归并、无迁移。

术语（脑科学对应）:
    hippocampus.py      海马体 — session wiki 读写
    consolidation.py    记忆巩固 — digest（events.jsonl → 本 session 的 wiki）
    recall.py           回忆 — 注入（本 session 的 wiki → prompt 段）
"""

from __future__ import annotations

from core.brain.hippocampus import SCHEMA_VERSION, WikiStore
from core.brain.consolidation import digest_session
from core.brain.recall import build_brain_injection
