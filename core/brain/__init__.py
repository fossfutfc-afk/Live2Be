# -*- coding: utf-8 -*-
"""Brain — 角色记忆（**现役唯一实现 = `core/brain/wiki_v2/`**）。

⚠️ **2026-09-21: 旧版记忆（digest v1）整族删除** —— `consolidation.py`（digest_session）/
`hippocampus.py`（WikiStore v1）/ `recall.py`（build_brain_injection）三件套连同
`llm/prompts/digest.md`、`contract/schema.build_digest_schema()`、`experiments/brain_real_run.py`
一并移除（文档早已声明"保留但无运行时消费方"，见 `wiki_v2/AGENT_BRAIN.md`）。

现役记忆链（视图与边界）:

    wiki_v2/store.py      BrainNode jsonl 存储（原子整写 / id / 快照 / 水位）
    wiki_v2/digest.py     Round A 记录 + Round B 组织 + 好感结算（增量幂等）
    wiki_v2/recall.py     召回（V3-0 台账已落地）
    wiki_v2/render.py     注入视图（第一人称叙事段）

历史设计（v1 时代，含已删模块的说明）见根级 `DESIGN_BRAIN.md`（混合史，慎读）
与 `core/brain/wiki_v2/AGENT_BRAIN.md`。
"""

from __future__ import annotations

from core.brain.wiki_v2 import BrainNode, WikiStoreV2

__all__ = [
    "BrainNode",
    "WikiStoreV2",
]
