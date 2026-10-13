"""digest — **记忆消化管线**（跑在 `core/brain/` 那套图与笔记之上）。

⭐ 2026-09-29 从 `core/brain/digest.py` 抬出来（代码管理节点 B 的第一步）。为什么单独一个包:
`core/brain/` 是**数据层**（点 / 边 / 存储 / 笔记 —— 纯 stdlib、零 LLM），而 digest 是
**LLM 管线**（要 contract 的 schema、要 `llm/` 的客户端、要 `core.session` 的事件流）。
两者同包时"数据层不 import llm"只是一句注释；分开之后它才是**包边界**。

一眼看清它跑什么（⭐ **步序的真源 = `rounds/` 包里的 `ROUNDS`**, 这里只是同一件事的人读版）::

    ⓪ 切分 split   digest.split     时间线 + 时间/日子/还开着的约定 → **切片骨架 + 账目**（五行）
    ① 记 record    digest.record    时间线 + 骨架 + 人设 + 视觉记忆 → episode / 玩家画像
                                   ⭐ **并当场按 R0 的表产 note 操作**（add / update / close）
    补边 akin    （0 LLM）          本段的 `noticed` 账 → `akin` 边
    ② 接 relate    digest.relate    本段经历 + 认知列表 → **关系表**（只落边; 一个字正文都不写）
    ③ 挂 settle    digest.settle     候选表 + 命中集载荷 + 新节点 → `about` 边 + entity 载荷
    ④ 分群 group   digest.group      块 + 已有类 → 群节点 + `member_of`（自带快照）

⏸ **收口 close（`digest.close`）2026-10-05（L8）删** —— 账目由 ⓪ 判（它手里是本段原文）、
由 ① 落（`_ledger_ops`）; 那一轮读的只是 120 字转述。

⚠️ **每步的定义已收进 `rounds/` 一张表**（2026-09-29 节点 C; 乙-1 起按轮拆成包）:
步序 / LLM 身份 / prompt / 契约相位 / parse / 料 / 写什么 / 跳过条件 / 每轮预算 / 是否自带快照。
`pipeline.py` 是执行体（`for spec in ROUNDS: IMPL[spec.key](ctx)`, 每轮进门先
`ctx.enter(key)` 拿 spec —— 越序当场炸）;
`_rollback` 的清空清单也由表推导 —— 别再往 `pipeline` 里加第二份轮次清单。

## 包内分工（拆包 S1/S2 + 乙-1, 2026-09-29 —— `pipeline.py` 1431 → 666 → 约 260 行）

| 模块 | 装什么 |
|---|---|
| **`rounds/`** | ⭐ **按轮切的包**（乙-1）: `__init__.py` = **轮次表**（步序/身份/prompt/相位/parse/料/写什么/跳过/预算/快照）· `base.py` = `Ctx` + `RoundOut` · 六个轮文件 `split/record/akin/relate/settle/group.py`（每个 `def run(ctx) -> RoundOut`） |
| **`pipeline.py`** | **编排与事务**：`for spec in ROUNDS: IMPL[spec.key](ctx)`（顺序只由表说）· `DigestResult` · 回滚/自吞/计数/放弃 |
| **`call.py`** | **一轮 LLM 调用**：prompt+契约装配 · 调用+回灌重试 · 本轮截止 · 带轮次的失败文案 |
| **`material.py`** | **各轮的料**（引擎侧零 LLM）：段标题校对/拼装 · 视觉记忆 · 情绪标尺 · 约定行 · 新经历 · L1 候选 · R3 对象正文 |
| **`segment.py`** | **这一段是什么**：段类型/章分组 · `span` 区间展开 · 一章一条收口 |
| **`episodes.py`** | **L1 落节点**：字段归属 + 去重 · 自己的时刻 · 逐字原话 · 情绪/地点/叙事轴物化 |
| **`llm_call.py`** | LLM 鲁棒层（重试 / deadline / 档位透传） |

⇒ 三层（L1 本段 / L2 跨段 / L3 实体）要改的刀各有落点:
L1 落 `rounds/record.py`（+ `episodes.py` / `segment.py`）· L2 落 `rounds/relate.py` /
`rounds/group.py` · L3 落 `rounds/settle.py` —— 不用再全挤在 `pipeline.py` 里。
⚠️ 这里的 **L1/L2/L3 是"三段层次"**（本段/跨段/实体, `DESIGN_DIGEST_LAYERS`）,
与**两趟**那套 L1/L2（判关系 / 写正文, `DESIGN_DIGEST_TWO_PASSES`）**同名不同物**。
"""
from core.digest.pipeline import DigestResult, digest_segment

__all__ = [
    "DigestResult",
    "digest_segment",
]
