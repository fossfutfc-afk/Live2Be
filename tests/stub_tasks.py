# -*- coding: utf-8 -*-
"""测试桩的**任务分派**助手（节点 5b, 2026-09-21）。

桩不再按中文关键字认任务（`情绪标签` / `变更句数组` / …——那些串来自 prompt 文案,
改一次措辞就静默不命中, ARCH_REVIEW P2-8）。产品侧现在在
`llm.chat(..., task=…)` / `chat_full(..., task=…)` 上声明调用身份
（`llm/task_labels.py`）, 桩读 `kw["task"]` 分派。

## 用法

```python
from llm import task_labels as T
from tests import stub_tasks

class ScriptedLLM:
    def chat(self, messages, **kw):
        task = kw.get("task")
        self.tasks.append(task)                 # 需要按调用身份过滤时记一份
        if task == T.PLACE:                     # 本用例特别关心的那一路: 显式覆盖
            return [{"sentence": 2, "place": "school_rooftop"}]
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:                   # 其余标注/后台调用: 走标准应答
            return reply
        return self._scripts.pop(0)             # 主链（mmt / bond）: 按脚本队列
```

## 两条纪律

1. **不要**再写 `if "某中文串" in last` —— 那正是本条要根除的耦合
   （`tests/core/test_stub_dispatch_guard.py` 会扫出来）;
2. 主链之外的新任务 → 在 `llm/task_labels.py` 加标签, 并在这里给出标准应答;
   漏了会在**调用点**炸（`unknown_task` 的报错信息直接指路）。
"""
from __future__ import annotations

import re

from llm import task_labels as T

#: 情绪标注的**条数口径**: `恰 N 项`（记录级模板显式双写）——**别**用 system 的
#: `^\d+: ` 编号行（模板【示范】也带编号行, 会恒多 4 条 → 全程兜底还不报错）
_COUNT_RE = re.compile(r"恰 (\d+) 项")


def emotion_count(messages) -> int:
    """情绪标注期望的条数（取不到 → 1）。"""
    last = messages[-1]["content"] if len(messages) > 1 else ""
    m = _COUNT_RE.search(last or "")
    return int(m.group(1)) if m else 1


def annotation_reply(task: str | None, messages, *,
                     digest_b_delta: int = 0) -> object | None:
    """标注/记忆消化类调用的**标准应答**; 主链任务 → None（调用方继续走脚本队列）。

    `digest_b_delta`: Round B 的好感增量（用例需要非 0 时传, 如 webgui 的 5）。
    """
    if task == T.EMOTION:
        return ["nomal"] * emotion_count(messages)
    if task == T.PLACE:                 # 句级锚点 → 无变更
        return []
    if task == T.PLACE_BOARD:           # 板级换场翻译 → 不切背景
        return {"place": ""}
    if task == T.PLACE_VARIANT:         # 选图（第二遍）→ 保持当前图
        return {"image": ""}
    if task == T.DIGEST_RECORD:
        return {"episodes": []}
    if task in (T.DIGEST_UNDERSTAND, T.DIGEST):
        return {"decisions": [], "evidence": [], "affection_exp_delta": digest_b_delta}
    if task == T.DIGEST_CLOSE:          # R4 收口 → 没什么要记的
        return {"add": [], "close": []}
    if task == T.DIGEST_ATTRIBUTE:           # ④ 挂（attribute）→ 没有可归属的
        return {"attributions": []}
    if task == T.DIGEST_GROUP:          # L2-a 分群 → 一个类都不分（块留到下段）
        return {"attach": [], "new": [], "merge": []}
    return None


def unknown_task(task: str | None) -> AssertionError:
    """未知/缺失 task 的报错（**产品侧漏传 `task=` 或新任务没补桩**都走它）。"""
    if task is None:
        return AssertionError(
            "这次 LLM 调用没带 task= —— 产品侧调用点漏了调用身份（节点 5b）: "
            "去 `llm/task_labels.py` 挑一个标签并加到那处 `llm.chat(...)` 上。")
    return AssertionError(
        f"桩不认识 task={task!r} —— 若是新任务: 在 `llm/task_labels.py` 加标签, "
        f"并到 `tests/stub_tasks.py::annotation_reply` 给出标准应答。"
        f"合法标签: {sorted(T.ALL)}")
