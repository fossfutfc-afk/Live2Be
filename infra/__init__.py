"""`infra/` — **基础设施层**（最底层之一, 只依赖 stdlib 与 `contract/`）。

装的是"与领域无关、与产品无关"的横切件 —— 谁都能用, 谁都不许往里加业务:

    paths.py    固定路径的唯一清单（**五个根**: RESOURCE / CONFIG / ASSETS / APP / DATA）
    atomic.py   原子替换的 Windows 健壮性包装（`os.replace` + 占用重试）
    fuse.py     两轴融合的三个形状（纯算术, 唯一实现）

## 为什么单独一层（而不是塞进 `core/common/`）

1. **`llm/` 需要它**：`llm/task_levels.py` 读 `settings.toml` ⇒ 要 `paths`。
   放在 `core/` 下的话, `llm → core` 就是一条**反向依赖**（现在那条依赖**归零**了,
   见 `tests/core/test_import_direction.py` 的 `LLM_CORE_ALLOWED`）。
2. **它没有领域语义**：路径、原子写、融合形状——换成别的产品也照样这么写。
   `core/` 是引擎（领域）, `core/common/` 那个"抽屉"（errors/atomic/fuse/tone/
   mmt_registry 混在一处）2026-10-15 已就地解散: `atomic`/`fuse` 来这儿,
   `errors` 归 `contract/`, `tone` 归 `core/parsing/`, `mmt_registry` 归 `core/mmt/`。
3. **打包 exe 的接缝**：五个根的区分（只读资源 vs 可写数据 vs 用户内容）只在本层表达。

## 依赖纪律

⛔ 本层**不许** import `core` / `llm` / `webgui` / `renderer` / `apps` / `tests`
（`test_import_direction.py` 的 `RULES` 钉着）。`contract` 可以（它更底）。
"""
from __future__ import annotations

__all__: list[str] = []
