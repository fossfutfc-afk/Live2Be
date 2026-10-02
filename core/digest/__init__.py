# -*- coding: utf-8 -*-
"""digest — **记忆消化管线**（跑在 `core/brain/` 那套图与笔记之上）。

⭐ 2026-09-29 从 `core/brain/digest.py` 抬出来（代码管理节点 B 的第一步）。为什么单独一个包:
`core/brain/` 是**数据层**（点 / 边 / 存储 / 笔记 —— 纯 stdlib、零 LLM），而 digest 是
**LLM 管线**（要 contract 的 schema、要 `llm/` 的客户端、要 `core.session` 的事件流）。
两者同包时"数据层不 import llm"只是一句注释；分开之后它才是**包边界**。

一眼看清它跑什么（⭐ **步序的真源 = `rounds.py` 的 `ROUNDS`**, 这里只是同一件事的人读版）::

    ① R1 记     digest.round_a    时间线 + 人设 + 视觉记忆 → episode / 玩家画像
      akin 补边 （0 LLM）          本段的 `noticed` 账 → `akin` 边
    ② R4 记账   digest.close      开着的约定 + 本段经历 → note 操作（不建节点）
    ③ R2 接     digest.round_b    本段经历 + 时间线 + 认知列表 → 决策表 + `links`
    ④ R3 挂     digest.attr       候选表 + 命中集载荷 + 新节点 → `about` 边 + entity 载荷
    ⑤ L2-a 分群 digest.group      块 + 已有类 → 群节点 + `member_of`（自带快照）

⚠️ **每步的定义已收进 `rounds.py` 一张表**（2026-09-29 节点 C）: 步序 / LLM 身份 /
prompt / 契约相位 / parse / 料 / 写什么 / 跳过条件 / 是否自带快照。
`pipeline.py` 是执行体（每步先 `cur.enter(key)` 拿 spec, 越序当场炸）;
`_rollback` 的清空清单也由表推导 —— 别再往 `pipeline` 里加第二份轮次清单。
"""
from core.digest.pipeline import DigestResult, digest_segment

__all__ = [
    "DigestResult",
    "digest_segment",
]
