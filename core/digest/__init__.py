"""digest — **记忆消化管线**（跑在 `core/brain/` 的图与笔记之上）: 新事件 → 节点 / 边 / 看法 / 对象 / 笔记操作。

为什么单独一个包: `core/brain/` 是**数据层**（点 / 边 / 存储 / 笔记 —— 纯 stdlib、零 LLM）,
而这里是 **LLM 管线**（要契约的 schema、`llm/` 的客户端、`core.session` 的事件流）。
同包时"数据层不 import llm"只是一句注释; 分开之后它是**包边界**。

⭐ **步序 / LLM 身份 / 料 / 跳过条件 / 预算的唯一真源 = `rounds/__init__.py` 的 `ROUNDS`** ——
别在文档里、也别在 `pipeline.py` 里抄第二份表（抄一次就漂一次）。

模块分工 / 数据流 / 纪律见 `core/digest/.md`。
"""
from core.digest.pipeline import DigestResult, digest_segment

__all__ = [
    "DigestResult",
    "digest_segment",
]
