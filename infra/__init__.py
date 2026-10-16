"""基础设施层：与领域无关的横切件。只依赖 stdlib 与 contract/。

    paths.py     固定路径清单（五个根：RESOURCE / CONFIG / ASSETS / APP / DATA）
    settings.py  settings.toml 的唯一读入口（不缓存，每次重读）
    atomic.py    原子替换的 Windows 占用重试
    fuse.py      两轴融合的三个形状

放这儿的理由：`llm/` 要读 settings.toml，这两个件若留在 `core/` 下就成了反向依赖。
不许 import core / llm / webgui / tui / cli（test_import_direction.py 钉着）。
"""
from __future__ import annotations

__all__: list[str] = []
