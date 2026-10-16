# EXEC_RENAME — 顶层包改名（`core`→`engine` · `renderer`+`core/tui`→`tui` · `apps`→`cli`）

接在 `EXEC_SPLIT.md`（C0–C12b 那轮拆分）与 `PROCEED.md` §1「线 B」之后。这一轮**只改名**，
不重排任何包内部结构、不合并测试归属。

## 1. 目标树与层次

```
浏览器 / 终端
   ↑
webgui/      FastAPI 壳（24 个 .py）           不动
cli/         ← apps/（3 个 .py）              面向人的入口
tui/         ← renderer/（9 个 .py）          终端表现层
engine/      ← core/（121 个 .py）            领域引擎
   ↑
llm/         传输层（7 个 .py + prompts/）
infra/       基础设施（paths/settings/atomic/fuse）
   ↑
contract/    契约地基（4 子包 + 11 平铺件）     零项目内依赖

tests/       engine/ ← tests/core/ · tui/ ← tests/renderer/ · llm/ · webgui/ · fixtures/
```

import 方向：`contract → infra → llm → engine → tui / webgui / cli`（只能往下）。现有守门
`tests/core/test_import_direction.py` 钉着，每步都要把新包名加进它的 `RULES`。

## 2. 已定的四条（作者 2026-10-15）

| # | 决定 | 理由 |
|---|---|---|
| ① | `contract/` 那 11 个平铺件**不分族** | 一共 1149 行，一屏看得完；新增件按 `contract/__init__.py` 归类 |
| ② | `core/tui/` 的三件**平铺在 engine 根**（第 2 步时那个包还叫 `core` ⇒ 先落到 `core/` 根，
第 3 步改名后自然成为 `engine/` 根）：`engine/display.py`（`MomoTalkOutput`）· `engine/streaming.py`（`DisplayStep`/打字节奏）· `engine/text.py`（纯文本件） | `engine/mmt/engine.py` 与 `engine/session/renderer.py` 直接 import 它们 ⇒ 它们**不能进顶层 `tui/`**，否则 `engine ↔ tui` 成环（`tui` 侧已有 3 处 `→ core.media.catalog`） |
| ③ | `tui/core.py` → **`tui/renderer.py`** | 它是 `Renderer`/`RenderOutput` 那台管线；`tui/core.py` 这个名字读不出信息 |
| ④ | `tests/` **只跟着改名**（`tests/core/`→`tests/engine/`、`tests/renderer/`→`tests/tui/`） | 归属重划要逐个读约 10 个跨包守门测试判它测谁，单开一刀 |

## 3. 三步（顺序：最小 → 最大，先验证流程）

### 第 1 步 `apps/` → `cli/`（3 文件 / 624 行）

外部引用面只有 4 处（实测）：`main.py:15` · `apps/main.py:14`（包内）· `tests/core/test_vn_cli.py:18,353`
· `l2d-demo/smoke_shiraishi.py:27`。
用户可见变化一个：`python -m apps.main` → `python -m cli.main`（`python main.py` 不变）。

### 第 2 步 `renderer/` → `tui/`（9 文件 / 743 行）+ 决策 ②③

引用面（实测）：`apps/vn_cli.py:41-42` · `tests/renderer/test_renderer.py:17,27,280`
· `webgui/routers/bond.py:28` · 包内 15 行。同时做：`core/tui/` 三件搬进 `engine/`、
`renderer/core.py` → `tui/renderer.py`。

### 第 3 步 `core/` → `engine/`（121 文件 / 30099 行）

引用面**最大**：**125 个外部文件 / 556 行 import**（`from core.brain import …` 这种深路径占绝大多数；
`from core import X` 门面用法 0 处）。纯前缀替换，子包名一个不动。
用户可见变化：`python -m core.media.place_rename …` → `python -m engine.media.place_rename …`
（那条命令写在 `core/media/place_rename.py` 自己的 docstring 里，同批改）。

## 4. 每一步都要跟着改的"写死名字"（漏一个就红/瞎）

| 位置 | 改什么 |
|---|---|
| `pyproject.toml` | `known-first-party` 列表 |
| `tests/<域>/test_import_direction.py` | `RULES` 的键 + 每个包的禁用表（新增 `tui` / `cli` 后，`core`/`renderer` 那两条要换成新名） |
| `tests/<域>/test_paths.py` | `_SCAN_DIRS`（扫"现拼项目根路径"的范围） |
| `tests/<域>/test_split_safety.py` | 9 个守卫模块名（含 `apps.vn_cli` · `core.bond.bond_story` · `core.mmt.engine`） |
| `tests/fixtures/api_surface.txt` | 快照里的模块名前缀（`SPLIT_API_UPDATE=1` 刷新 + 人工审 diff） |
| `tests/<域>/test_worldtime.py` | `WORLDTIME_ALLOWED`（含 `core.worldtime`） |
| `.testtmp/layers.py` | 它的 `TOP` 元组（**我的层间账判据**——不同步改就整个瞎掉） |
| `llm/.md` · `contract/.md` | 正文里提到的包名 |
| 各包 `.md` | 每个包补一份说明（照 `llm/.md` 的约定，每份不超过一页） |

⚠️ 时机：**测试目录跟着它测的包走** —— `tests/core/` 要到第 3 步才变 `tests/engine/`，
而 `tests/renderer/` 在第 2 步就跟着变成 `tests/tui/`。所以上表里的 `tests/<域>/…`：
第 1 步只碰 `tests/core/test_vn_cli.py`，第 3 步才动 `tests/core/` 整个目录名。

## 5. 坑（改名特有）

1. **字符串里的模块名**：`monkeypatch.setattr(core.x, ...)` / `setattr(ig.paths, ...)` 这类
   在测试里到处都是——改名后它们**不会**自动跟着变，要 grep `"core.` / `'core.` 逐个看。
2. **`test_split_safety` 的守卫模块名是字符串表**，改名后不刷新 = 守门静默失效（比红更糟）。
3. **不要用 `ruff --fix` 处理 import 顺序**（`--select` 会覆盖 pyproject ⇒ 批量删掉有效的 `# noqa`）；
   改名后顺序错乱用 `ruff check --select I001 --fix`，它只动 import 块。
4. **`l2d-demo/`、`experiments/`、`archive/`** 里的引用：`l2d-demo/smoke_shiraishi.py` 改；
   `experiments/` 一并改（它们是能跑的脚本）；`archive/` **不动**（已经不可运行，留给文档那一趟）。
5. **文档里的旧路径**（`CLAUDE.md` 26 处 · `DESIGN_BRAIN.md` 14 处 · `docs/*` 数百处）留到
   **文档那一趟**统一处理；本轮只改**活代码/测试/命令**里的名字。
6. **别名常量**：`CHAR_ROOT = paths.CHARACTERS_DIR` 这类是"值"的别名，改名不影响；
   但 `from core.x import y` 换包后，测试里 patch 旧路径会**静默 no-op**（第 1 条同源）。

## 6. 每步的验收（固定）

- 先干跑：一个可复用脚本 `.testtmp/rename_pkg.py <old> <new> [--dry]`，**逐处打印**再应用
- `ruff check .` 对齐基线（本轮基线 **373**）
- `tests/<域>` 全绿 + 全量两域（`tests/core`+`llm`+`renderer` / `tests/webgui`）
- 三份逐字节 verifier 全 exit 0（`capture_1e.py` / `verify_1c.py` / `capture_prompts_1d.py`）
- `.testtmp/layers.py` 的层间账：`llm → core` 仍为 **0**、`contract` 无对外依赖
- `api_surface.txt` 刷新，diff 只含预期改名
- **每步一个提交**，提交信息写清引用面数字与判据

## 7. 本轮不做

- 不重排任何包的内部结构（`engine/brain`、`engine/digest` 等一个不动）
- 不动 `webgui/`、不动 `config/`/`data/`/`assets/`
- 不合并测试归属（决策 ④）
- 不改文档里的历史路径（留到文档那一趟）
- 不顺手重构 `llm/client.py`（736 行）之类——那是另一件事
