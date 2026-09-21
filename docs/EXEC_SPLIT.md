# EXEC_SPLIT — 文件拆分与位置规划（执行计划）

> **状态**：执行中。**C0（安全网 + 工具纪律）已落地 2026-09-21**；C1 起未动。
> **怎么用**：每个节点 = **一次提交 + 全量测试 + （涉 webgui 时）B 层冒烟**；
> 节点内**只做"移动"**，任何行为改动单独开节点。行号一律不写（会漂），写 `file.py::symbol`。
> **相关**：`docs/EXEC_PIPELINE_UNIFY.md`（流水线收敛，已全部落地）· `CLAUDE.md` §2/§11/§12。

---

## 0. 一句话

把 `webgui/bond.py`（2950 行）、`core/bond/bond_story.py`（1575 行）、`contract/records.py`
（910 行）这类"什么都装"的文件拆成**职责单一的模块**，并把几处**位置放错**的包
（CLI 在 core、引擎依赖终端 UI、MMT 引擎与动作分居两处）搬回该在的地方；
拆的过程靠 **C0 的三条守门 + git 纯移动证据**保证"没丢名字、没改行为"。

---

## 1. 现状（2026-09-21 实测）

| 文件 | 行数 | 结构问题 |
|---|---|---|
| `webgui/bond.py` | **2950** | 79 个顶层符号挤在一层：`bond_start`(247) `bond_turn`(222) `_generate`(112) `bond_finish`(86) `_pregenerate`(89) `bond_status`(80)…；同时装着状态机/落库/事件流 marker/lane/预热/预生成/回放/纪念生图/收尾 |
| `core/bond/bond_story.py` | 1575 | `BondStoryEngine` **一个类 1074 行**；`BondScene` 230；`_BoardAssembler` 106 |
| `core/momotalk.py` | 1170 | 与已有的 `core/mmt/`（actions/executor/preset/ranking）**分居两处** |
| `contract/records.py` | 910 | 文法常量 + 解析 + 块/板校验 + `VnBlock` + 渲染，五件事一层 |
| `llm/client.py` | 669 | `LLMClient` **499 行**（传输 + payload + JSON 自纠错） |
| `core/ui/vn_cli.py` | 489 | CLI **应用**，但被 `webgui/bond.py` 反向依赖（`_build_director`/`_trigger_title`） |
| `tests/` | **20546** | 最大的一块：`test_bond.py` 1240 / `test_wiki_digest.py` 985 / `test_web_http.py` 822 |

**依赖半径**：`webgui.bond` ← 13 文件；`core.bond.bond_story` ← **27 文件**（含 10 个
`experiments/`+`l2d-demo/`）。⇒ 拆包必须**保持 import 路径不变**（模块→包转换 + 门面再导出）。

---

## 2. 目标布局与依赖方向

### 2.1 方向（C0 已由 `tests/core/test_import_direction.py` 固化）

```
contract/   最底层   不得依赖 core / llm / webgui / renderer / tests / experiments
llm/        传输层   不得依赖 webgui / renderer / tests / experiments;
                     对 core 只允许薄横切 core.paths / core.common
core/       引擎层   不得依赖 webgui / renderer / tests / experiments
renderer/   表现层   不得依赖 webgui / tests / experiments
webgui/     壳      不得依赖 tests / experiments
```

### 2.2 今天的既存违规（**只有 6 处**, 全部有归宿）

| 违规 | 处数 | 归宿 |
|---|---|---|
| `contract/{model,registry,spec}.py` → `core.common`（`err`） | 3 | C9 定夺：把错误原语上提（`contract` 自带 / 新 `common/`）或正式白名单为"共享内核" |
| `contract/registry.py` → `llm.json_cleaner` | 1 | C9：`json_cleaner` 是纯 JSON 修复，归 `contract/`（**位置放错**的实证） |
| `core/ui/vn_cli.py` → `renderer` | 2 | C13：`vn_cli` 是 CLI **应用** ⇒ 搬出 `core/` → `apps/` |

（`llm/task_levels.py` → `core.paths` 属薄横切豁免。**未决**：`core/paths.py` 是否上提为
顶层 `paths.py`——那会动 `test_paths.py` 守门与 20+ 消费点，先不动，记在 §5。）

### 2.3 目标树（**要搬的**）

```
webgui/bond/             ← webgui/bond.py（模块→包；13 个引用点零改动）
  __init__.py            门面: 全量再导出（含私有名）
  deps.py                ← 显式接缝（16 个 patch 点收敛到这里, §5）
  state.py               BondState / BoardLifecycle / ChoiceCandidate / _state / 注册表
  watchdog.py            看门狗阈值 + _watchdog / _lanes_idle / _gate_stalled / _force_scene_ready
  stores.py              _flow_store/_stage_store/_log_scene/_log_scene_meta/marker/prewarm/draft
  lanes.py               双路 lane + 就绪门控 + _memorial_no_visuals
  replay.py              replay_attempts/chapter_replay/_start_replay/_narrativize/标题
  pregen.py              _generate/_pregenerate/候选/丢弃/_scene_landed
  memorial.py            生图工厂 + _memorial_gen + _persisted_memorial_img
  api.py                 bond_start/turn/status/finish + wrapup（HTTP 门面）
core/bond/bond_story/    ← 模块→包（27 个引用点零改动）
  scene.py               BondScene / SceneLoopError
  boards.py              DeliveryMode / _board_spans / _BoardAssembler
  engine.py              BondStoryEngine
contract/records/        ← 模块→包
  grammar.py / parse.py / check.py / carrier.py
core/mmt/                ← core/momotalk.py 并入既有 core/mmt/（engine.py）
core/tui/                ← core/ui/{display,streaming,text_processors}
core/director/wiring.py  ← 上提 _build_director/_trigger_title（解掉 webgui→CLI）
apps/                    ← main.py + vn_cli.py（CLI 应用）
docs/                    ← core/DESIGN_*.md(7) + contract/DESIGN.md
tests/webgui/bond/       ← test_bond.py 按主题拆 + tests/stubs/ 收共享 ScriptedLLM
```

---

## 3. 节点表（每节点一提交）

| # | 节点 | 内容 | 验收 |
|---|---|---|---|
| ✅ **C0** | **安全网 + 工具纪律** | ① `tests/core/test_import_direction.py`（4 条分层规则 + 6 处白名单 + 不腐烂 + 自测）② `tests/core/test_split_safety.py`（API 面快照 367 名 / 16 个 patch 点台账）③ 本文档 | 两个守门绿 + **实测会红**（删一个名字/加一个 patch 点）；全量 **880 passed** |
| **C1** | `webgui/bond.py` → 包（**先原样**） | 全部逻辑逐字进 `webgui/bond/_impl.py`；`__init__.py` 全量再导出；**同时**把 16 个 patch 点收敛进 `webgui/deps.py` 并改测试；`test_split_safety` 白名单清空 | `git diff -M` 呈**纯移动**；13 个引用点零改动；全量 + 冒烟绿；patch 白名单 0 条 |
| **C2** | 搬 `stores.py` | 落库/事件流/marker/prewarm/draft | 绿 |
| **C3** | 搬 `lanes.py` | 双路 lane + 就绪门控 | 绿 |
| **C4** | 搬 `replay.py` | 回放/标题 | 绿（回放用例是网） |
| **C5** | 搬 `pregen.py` | 预热/预生成/候选/丢弃 | 绿（节点 4′/2″ 用例是网） |
| **C6** | 搬 `memorial.py` | 纪念生图 | 绿 |
| **C7** | 搬 `api.py`/`watchdog.py`/`state.py` | `_impl.py` 消失 | 绿；2950 行 → 9 个 100~650 行模块 |
| **C8** | `core/bond/bond_story.py` → 包 | scene/boards/engine | 27 个引用点零改动；绿 |
| **C9** | `contract/records.py` → 包 + `json_cleaner` 归位 | grammar/parse/check/carrier；**顺带消掉 4 处 contract 违规** | 分层白名单减 3 条；绿 |
| **C10** | `core/ui` 拆 + `wiring` 上提 | `core/tui/`；`_build_director/_trigger_title` → `core/director/wiring.py` | 分层白名单减 1 条（core→renderer 消失）；绿 |
| **C11** | `core/mmt` 合并 + `apps/` + `docs/` 归位 | `core/momotalk.py`→`core/mmt/engine.py`；`main.py`/`vn_cli.py`→`apps/`；`core/*.md`→`docs/` | 全仓 `compileall`；绿 |
| **C12** | 测试拆分 + 共享桩 | `tests/webgui/bond/*`；`tests/stubs/scripted_llm.py`（与 5b 的 `stub_tasks.py` 合流） | 单测文件全部 < 400 行；绿 |
| **C13** | `llm/client.py` / `llm/image_gen.py`（可选） | 按职责再分 | 绿 |
| **C14** | `core/brain/wiki_v2/*`（可选） | digest/nodes/channel 再分 | 绿 |

顺序理由：**自上层往下**（webgui 最安全、收益最快；`contract/` 是所有人依赖的地基，放后面）；
**先拆接缝再搬文件**（C1 把 16 个 patch 点收敛，之后搬块不再有静默失效风险）。

---

## 4. 工具纪律（全部在本仓库实测）

**不带新依赖**：一次性工具用 `uvx`；长期守门写成 pytest（沿用 `test_paths.py` 先例）。
`uvx` 需代理：`HTTP_PROXY=HTTPS_PROXY=http://127.0.0.1:7897`。仓库**没有任何 ruff 配置**
（`pyproject.toml`/`ruff.toml`/`setup.cfg` 都不存在）⇒ **不要 `ruff --fix` 批量改**。

| 工具 | 实测 | 用在哪 |
|---|---|---|
| **rope 1.14**（`uvx --from rope python tools/rope_move.py`） | ✅ 打开 2950 行文件 0.03s，`has_errors=False`；两次 dry-run 共 15s；`ChangeSet.get_description()` **直接给 diff**（先审后落） | **只用于 C10/C11 的"真搬家"**（跨包移动 + 全仓改 import） |
| `ruff analyze graph` | ✅ 已有 ruff 自带 | C0 依赖盘点 + 事后核对（`uvx ruff@latest analyze graph`） |
| `vulture`（仓库已在用） | ✅ | 每步搬完查"变成死引用"的名字 |
| `tach` 0.35.1 / `import-linter` 2.15 | ✅ 秒装 | **暂不用**：只有 4 条规则，自写守门更省；规则涨到十条再换 |
| `libcst` | ✅ | 暂不用（只有 16 处 patch 要改，手工更快） |

### 4.1 rope 的三次 dry-run，决定了"哪里能用它"

| 试跑 | 变更集 | 结论 |
|---|---|---|
| ① C10 型：`_trigger_title` → `core/director/director.py` | 5 文件；**tests/ 未被改** | ✅ 真搬家用它；但产出的 import 风格是全限定（`core.director.director._trigger_title(...)`）⇒ 要设 `prefer_module_from_imports`/`pull_imports_to_top` 等 prefs, 或事后人工收敛 |
| ② C2 型：`_log_scene` → 别的模块 | 2 文件；内部调用被改写成 `chat._log_scene(...)` | ❌ **拆包不能用它**：它绕过门面, 把内部调用直接指向新宿主 |
| ③ C2 型 + 被测试引用的符号（`_state`） | 6 文件, **其中 4 个是 tests/**；还**删掉测试里的 `sys.path.insert(...)`** | ❌ 同上, 且会顺手改测试的引导代码 ⇒ 与"引用点零改动"直接冲突 |

⚠️ 必设：`p.prefs.set("ignored_resources", [".testtmp", "__pycache__", ".pytest_cache"])`
——实测 rope 会去改项目根下**任何** .py（它改了我放在 `.testtmp/` 的临时探针）。

### 4.2 每节点的"纯移动"证据

```powershell
git diff -M --stat HEAD~1        # rename 识别（拆分节点应呈 rename/add, 而不是 delete+add）
git diff -M --color-moved        # 人工审"只有移动"
python -m compileall -q core webgui llm contract tests   # 全仓可编译
```

---

## 5. 陷阱清单（拆分前必读）

1. **16 个 patch 点**（`tests/core/test_split_safety.py::ALLOWED_PATCHES` 已登记）：
   `webgui.bond` 6 处（`_store`/`_choice_pregen_enabled`/`ImageGenerator`/`_image_gen`/
   `_enqueue_annotate`/2 个看门狗常量）+ `webgui.chat._store` 7 文件 8 处 + `reset_engines` 2 处
   + `llm.client._settings_toml` 1 处。
   ⇒ **C1 必须先把它们收敛到 `webgui/deps.py`**（消费方写 `deps.store()` 而非
   `from .deps import store`——**调用时属性查找** patch 才生效）, 否则模块→包之后
   patch 静默失效（测试照旧绿, 覆盖全丢）。
2. **门面 = 模块→包转换**（不是 shim 文件）: `webgui/bond.py`→`webgui/bond/`、
   `core/bond/bond_story.py`→`core/bond/bond_story/`、`contract/records.py`→`contract/records/`
   —— import 路径不变 ⇒ 13/27/其他引用点**一个字都不用改**。
3. **既有名字一个都不能丢**：`tests/fixtures/api_surface.txt`（367 个自有名字）守门。
4. **文档行号冻结**：`docs/ARCH_REVIEW_*` / `docs/AUDIT_*` 里的 `file.py:行号` 是历史记录,
   不追改; 新文档写 `file.py::symbol`。
5. **`core/paths.py` 未决**：上提为顶层会动 `tests/core/test_paths.py` 与 20+ 消费点,
   本计划**不含**; 若要做, 单开节点。
6. **`experiments/` + `l2d-demo/` 不在 CI**：它们也 import 这些模块（10 处）, rope 的
   变更集会覆盖它们 ⇒ 每步后跑 `compileall` 全仓 + 相关脚本的 import 冒烟。
7. **快照只记"class / function / data"三态**：不能用 `type(obj).__name__`——
   `core.momotalk._EMBED_REPORTED` 这类**运行期可变标志**导入时是 `None`、某用例跑完
   变 `bool`, 快照会抖（C0 落地当天就被守门抓出来, 这是"守门真的在工作"的证据）。

---

## 6. 明确不做（本计划边界）

- **不改 HTTP 契约 / JSON / JS**（前端零改动）。
- **不在拆分节点里改行为**；唯一例外是 C1 的接缝显式化（行为等价, 有全量测试 + 冒烟兜底）。
- **不重命名对外符号**（`bond_start`/`bond_turn`/`BondStoryEngine`/`check_block`…）。
- **不解决"引擎依赖终端 UI"**（`core/momotalk.py` → `core/ui/*`）与"盒B 只注入两文件"
  这类**行为级**问题——本计划只搬位置; 那些另立设计。
- 不引入新依赖 / 不改 `pytest.ini` / 不进 CI 配置。
