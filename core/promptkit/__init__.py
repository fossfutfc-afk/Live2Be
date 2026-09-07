# -*- coding: utf-8 -*-
"""promptkit — 提示词组装层（docs/DESIGN_PROMPTKIT.md）。

职责边界:
    box.py    盒 = 会话级 system prompt（命名块清单装配, 一次拼死, 逐字节稳定）
    tail.py   每轮动态尾 = history 之后、user 之前（注记们 → task 卡）
    task.py   本回合任务卡（Phase 2 启用; 现占位返回 None）
    config.py 开关（settings.toml [promptkit].task_card, 默认 true）
    report.py describe() = 实际注入报表（文档代码化, 防漂移）

红线（DESIGN_PROMPTKIT §2）:
    ① system+history 前缀逐字节稳定（上下文缓存基本盘）
    ② 一切动态只发生在 history 之后
    ③ task 卡 ≤100 token, 不抄规则书
    ④ 一处装配: CLI / vn_cli / webgui / 预生成 / bench 同源
"""

from core.promptkit.box import DOMAIN_BOXES, BlockContext, box_chunks, build_box
from core.promptkit.config import task_card_enabled
from core.promptkit.report import describe
from core.promptkit.tail import round_messages
from core.promptkit.task import task_card

__all__ = [
    "DOMAIN_BOXES",
    "BlockContext",
    "box_chunks",
    "build_box",
    "describe",
    "round_messages",
    "task_card",
    "task_card_enabled",
]
