# EXEC_SPLIT — 文件拆分与位置规划（执行计划）

> **状态**：执行中。**C0–C10 已落地 2026-09-21 —— 三个"什么都装"的文件都拆完了**:
> C0 安全网 · C1a 接缝 · C1b 模块→包 · C2 `state.py` · C3 `stores.py` ·
> C4 `lanes.py`+`util.py` · C5 `replay.py` · C6 `memorial.py` · C7 `pregen.py` ·
> C8 `api.py`+`watchdog.py`（`webgui/bond.py` 的 `_impl.py` 消失）·
> C9 `core/bond/bond_story/`（scene/boards/engine）·
> C10 `contract/records/`（grammar/parse/check/carrier）+ 错误原语下沉 + `json_cleaner` 归位。
> **下一步 = C11（`core/tui/` + `_build_director` 上提）**。
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
| ✅ `contract/{model,registry,spec}.py` → `core.common`（`err`） | 3 | **C10 已消**：错误原语下沉 `contract/errors.py`（`core/common/errors.py` 只剩薄再导出壳） |
| ✅ `contract/registry.py` → `llm.json_cleaner` | 1 | **C10 已消**：`json_cleaner` 搬到 `contract/json_cleaner.py`（**位置放错**的实证） |
| `core/ui/vn_cli.py` → `renderer` | 2 | C11：`_build_director`/`_trigger_title` 上提到 `core/director/wiring.py`（C12 再把 `vn_cli` 搬 `apps/`） |

（`llm/task_levels.py` → `core.paths` 属薄横切豁免。**未决**：`core/paths.py` 是否上提为
顶层 `paths.py`——那会动 `test_paths.py` 守门与 20+ 消费点，先不动，记在 §5。）

### 2.3 目标树（**要搬的**）

```
webgui/deps.py           ← 显式接缝（C1a 已落地: store / 生图器 / 看门狗阈值 / choice 开关 /
                           `enqueue_annotate` 钩子）。⚠️ **放包外**（`webgui/deps.py`）不放
                           `webgui/bond/deps.py`: `chat.py` 也要用 store 接缝, 而
                           `chat → bond` 会成环（现在只有 `bond → chat` 单向）。
webgui/bond/             ← webgui/bond.py（模块→包；13 个引用点零改动）—— **C1b–C8 全部落地**
  __init__.py            门面: 117 名按"真家"分块再导出（含私有名; 不定义 `__all__`）
  state.py               BondState / BoardLifecycle / ChoiceCandidate / _state / 注册表
                         （**C2 已落地** —— 见 §5 陷阱 10: 它必须**最先**拆）
  stores.py              落库层（**事件流读写唯一出口**）: _flow_store/_stage_store/
                         _log_scene/_log_scene_meta/marker/prewarm/draft（**C3 已落地**）
  lanes.py               双路 lane + 就绪门控 + _memorial_no_visuals（**C4 已落地**）
  util.py                `_ms_since` —— **跨模块纯小工具**（C4 新开；不放 state: 那是
                         状态模型; 不放 lanes: 别的模块凭什么从 lane 借计时器）
  replay.py              resume 型回放 / 只读回放 / 认章定位 / _narrativize（**C5 已落地**）
  memorial.py            生图工厂 + _memorial_gen + _persisted_memorial_img
                         （**C6 已落地**；⚠️ 与原计划 C6/C7 对调: 它是叶子, 而 pregen
                         的 `_generate`/`_pregenerate` 要用它的 `_make_memorial_cb`）
  pregen.py              _generate/_pregenerate/候选/丢弃/_scene_landed（**C7 已落地**；
                         含 `_system_note` 与收尾/重试常量）
  watchdog.py            忙态/视觉门/预生成消费门的兜底放行 + _watchdog（**C8 已落地**；
                         阈值常量在 `deps.py`——测试要改它们）
  api.py                 bond_start/turn/status/finish + _start_replay + wrapup（**C8 已落地**；
                         1051 行 —— 若嫌大, 见 §3 的 ○C8b 可选节点）
core/bond/bond_story/    ← 模块→包（27 个引用点零改动）—— **C9 已落地**
  __init__.py            门面: 54 名按"真家"分块再导出（含私有名; 不定义 `__all__`）
  scene.py               BondScene / SceneLoopError（**C9**；264 行）
  boards.py              DeliveryMode / _board_spans / _BoardAssembler + 板级闸（**C9**；184 行）
  engine.py              BondStoryEngine / _personality_summary / MAX_SCENE_RETRIES /
                         DEFAULT_HISTORY_ROUNDS / logger（**C9**；1195 行）
contract/records/        ← 模块→包（28 个引用点零改动）—— **C10 已落地**
  __init__.py            门面: 52 名按"真家"分块再导出 + 原模块 docstring（115 行; 含私有名;
                         不定义 `__all__`）；**全是本包自有名**, 无"路过"的借用名
  grammar.py             取值表（kind/stage/speaker/上限 + 正则）+ VnRecord/ParseDiag/
                         ParseResult（**C10**；134 行, 叶子）
  parse.py               行 → 记录（五条容错纪律）+ parse_line/parse_stream +
                         BlockStreamParser（**C10**；276 行）
  check.py               sensei_groups/group_labels + Issue 软硬分级 +
                         check_block/check_board（**C10**；284 行）
  carrier.py             VnBlock + 说话人身份 + render_records/materialize_pick/
                         pick_insert_index（**C10**；308 行）
contract/errors.py       ← 错误原语真家（C10 从 core/common 下沉; 只 import stdlib）
contract/json_cleaner.py ← 纯 JSON 修复（C10 从 llm/ 归位）
core/common/errors.py    → 薄再导出壳（保 20+ 处旧 import 路径; **C10**）
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
| ✅ **C1a** | **接缝收敛（`webgui/deps.py`）** | 新建 `webgui/deps.py`（store / 生图器 / 看门狗阈值 / choice 开关 / `enqueue_annotate` 钩子）; `bond.py`/`chat.py`/`routers/collection.py` 全部改读 `deps.xxx`（**调用时**属性查找）; **16 个 patch 点全部改打 `deps.*`**; `ALLOWED_PATCHES` 清空 + 新增 `SAFE_PATCHES`（3 条: 调用点在包外的 patch）; 快照加盯 `webgui.deps`（`SNAPSHOT = TARGETS + ("webgui.deps",)`——`deps` **不能**进 `TARGETS`, 否则"patch 接缝"会被守门当成违规）; owner 列归一（`_owner_of` 去掉私有段, 免得换解释器抖 + C1b 要求快照零 diff） | 全量 **880 passed**; 冒烟 **PASS**（含纪念生图链路）; patch 白名单 0 条; 快照 diff = 只此 10 个名字搬家 |
| ✅ **C1b** | **`webgui/bond.py` → 包（原样）** | `git mv webgui/bond.py webgui/bond/_impl.py`（**逐字未改**）+ 新 `webgui/bond/__init__.py`：**逐个显式**再导出 117 个名字（含私有名, 列表**从 API 面快照生成**, 见 §5 陷阱 8）; 13 个引用点**一个字未改** | `git diff -M` = **rename 100%** + 只有门面新增; `tests/fixtures/api_surface.txt` **零 diff**; 全量 **880 passed**; 冒烟 **PASS** |
| ✅ **C2** | **搬 `state.py`（叶子优先 —— 原计划排在 C7, 实测必须提前）** | `ChoiceCandidate` / `BoardLifecycle` / `BondState` / `_bonds` / `_state` / `_memorial_open_in_events` 逐字搬进 `webgui/bond/state.py`（唯一改动: `_store()` → `deps.store()`）; `_impl.py` 只留一行 import; 门面**零改动** | 全量 **880 passed**; 冒烟 **PASS**; 门面/夹具**零 diff**; 身份自检（`webgui.bond.X is webgui.bond.state.X` / `_bonds` 同一个 dict）|
| ✅ **C3** | **搬 `stores.py`（落库层）** | 22 个符号逐字搬进 `webgui/bond/stores.py`: `_store`/`_flow_store`/`_stage_store` · `_last_bond_seq`/`_last_mmt_seq`/`_open_vn_seq` · `_draft_*` · `_prewarm_cache_*` · `_log_scene`/`_log_scene_meta`/`_close_memorial_window`。**新纪律**: 门面改从 `stores` 收这 22 个名字（`_impl` 只收它自己还在调用的 15 个）; 顺手清掉 `_impl` 里早已无人用的 3 个事件常量与 `image_enabled`（门面继续给, 指向真家 `core.session.events` / `llm.image_gen`） | 全量 **880 passed**; 冒烟 **PASS**; 门面 117 名 + 夹具**零 diff**; 身份自检（`webgui.bond.X is webgui.bond.stores.X`）|
| ✅ **C4** | **搬 `lanes.py` + `util.py`** | 13 个符号逐字搬进 `webgui/bond/lanes.py`（就绪门控 `_memorial_no_visuals`/`_scene_*_ready`/`_scene_ready_or_busy`/`_wait_annotated` + 双路 lane `_ensure_lane`/`_enqueue_annotate`/`_enqueue_place_annotate`/`_anno_worker`/`_place_worker`/`_fallback_fill`）; **新开 `util.py`** 放 `_ms_since`（4 个模块要用的纯小工具 —— 塞 state 属位置放错）; `deps.enqueue_annotate` 的懒转发目标改指 `webgui.bond.lanes`（C1a 就预留了这句话） | 全量 **880 passed**; 冒烟 **PASS**; 门面 117 名 + 夹具**零 diff**; 身份自检 |
| ✅ **C5** | **搬 `replay.py`（回放层）** | 8 个符号逐字搬进 `webgui/bond/replay.py`: `_narrativize` · `replay_attempts` · `_interrupted_replay_queue` · `chapter_replay`（**只读回放**, 与 resume 型回放是两件事）· `_pending_in_vn` · `_title_from_events` · `_enter_title` · `_prev_chapter_quit`。`_start_replay` **不搬**（同时抓 pregen/memorial/payload/draft, 属编排 → C8 `api.py`）; 顺手把 `NON_PICKS`/`abandoned_ranges`/`replayable_chapters` 从 `_impl` 的清成"门面直指真家" | 全量 **880 passed**; 冒烟 **PASS**; 门面 117 名 + 夹具**零 diff**; 8 个名字身份自检 |
| ✅ **C6** | **搬 `memorial.py`（纪念生图）** | 4 个符号逐字搬进 `webgui/bond/memorial.py`: `_persisted_memorial_img`（从事件流/overlay 捡回异步落盘的图）· `_memorial_gen`（真开画, 生图器走 `deps`）· `_make_memorial_cb` · `_ensure_memorial_img`。**注意 C6/C7 对调了**（见下）; 顺手把 `GalleryStore`/`collect_ref_images`/`M_MEMORIAL_IMAGE` 清成"门面直指真家" | 全量 **880 passed**; 冒烟 **PASS**; 门面 117 名 + 夹具**零 diff**; 4 个名字身份自检 |
| ✅ **C7** | **搬 `pregen.py`（生成 / 预生成 / 候选 / 丢弃）** | 15 个符号逐字搬进 `webgui/bond/pregen.py`: 常量 `_CLOSING_TEXT`/`_CLOSING_PARA`/`MAX_GEN_FAILURES`/`_REMIND_ROUNDS`/`_END_ROUNDS` + `_generate`/`_pregenerate`/`_scene_landed`/`_log_board_deliver` + 候选支 `_choice_pregen_enabled`/`_spawn_candidates`/`_candidate_worker` + 丢弃入口 `_discard_boards`/`_discard_candidates` + `_system_note`（产品侧只有生成两处调用, 故住这里）。顺手把 `ChoiceCandidate`/`staging_store`/`M_SESSION_END`/`M_VN_ABANDON` 清成"门面直指真家" | 全量 **880 passed**; 冒烟 **PASS**; 门面 117 名 + 夹具**零 diff**; 15 个名字身份自检; `_impl.py` 1204 行 |
| ✅ **C8** | **搬 `api.py` + `watchdog.py`；`_impl.py` 消失** | `watchdog.py`（144 行）= `_watchdog`/`_lanes_idle`/`_lane_writer_alive`/`_gate_stalled`/`_force_scene_ready`/`_thread_alive`（单向: 只依赖 lanes/deps/util）; `api.py` = `bond_start/turn/status/finish` + `bond_start_demo` + `_start_replay` + `_ready_scene_payload`/`_role_info` + `_entry_already_done` + `_note_reject`/`_clear_rejects` + `_wrapup`/`_wrapup_inner` + `DEMO_SCRIPT`（原 `bond.py` 的模块说明逐字搬进来当"对外契约"一节）。**门面按"名字的真家"整体重建**（117 名 → 9 个包内模块 + 11 个核心/契约/llm 真家, 分块列出）; `_impl.py` 删除 | 全量 **880 passed**; 冒烟 **PASS**; **快照刷新后 diff = 只有 owner 列**（模块+名字+种类零变化, 已逐列核对）; `import webgui.bond._impl` → ModuleNotFoundError |
| ○ **C8b**（可选） | `api.py` 再分 | `api.py` 实测 **1051 行**（比计划里的 ≤460 大一倍多）—— 可选切成 `entry.py`（`bond_start`/`_start_replay`/负载/演示）+ `api.py`（`bond_turn`/`status`/`finish`/`_wrapup*`）, 方向 api → entry | 绿 |
| ✅ **C9** | **`core/bond/bond_story.py` → 包** | `git mv` 模块成 `core/bond/bond_story/{scene,boards,engine}.py`（逐字搬, 只改 import 行: 无相对导入, 故 `from core.bond.bond_story.{scene,boards} import …` 需补全限定名）+ 门面 `__init__.py` **逐个显式**再导出 54 名（含私有名; 列表**从 API 面夹具的该段生成**, **不定义 `__all__`**）。门面按"真家"分块: 3 个包内模块 + 43 个 core/contract/llm 真家（后者**整体重建**, 因为原模块是一次性 import 了一大票外部名）; `max_tokens as task_levels_max_tokens` 是本次唯一的重名别名（真家里叫 `max_tokens`）。**27 个引用点一个字未改** | 全量 **880 passed**; 冒烟 **PASS**; **快照刷新后 diff = 只有 owner 列 13 行**（模块+名字+种类零变化, 已逐列核对）; `python -m compileall` 全仓绿; 4 个名字身份自检 |
| ✅ **C10** | **`contract/records.py` → 包 + 错误原语下沉 + `json_cleaner` 归位** | ① **拆包**: 原文件七个 `# ---` 分区**逐字**切成四块（36–153 → `grammar.py` · 154–295 + 816–910 → `parse.py` · 296–545 → `check.py` · 548–815 → `carrier.py`, `git rename` 锚点 = 最大片段）; 门面 `__init__.py` = **原模块 docstring 逐字** + 52 名按"真家"分块再导出（**全是本包自有名**, 无借用名）。② **违规定夺（用户裁决 A）**: `core/common/errors.py` `git mv` → `contract/errors.py`（真家; `core/common/errors.py` 留薄再导出壳, 20+ 处旧路径零改动）, `contract/{model,registry,spec}.py` 改指真家; ③ `llm/json_cleaner.py` → `contract/json_cleaner.py`（3 个调用点改指）; ④ `test_import_direction.py` 白名单 **5 → 1 条** | 全量 **880 passed**; 冒烟 **PASS**; 快照刷新后 diff **只有 owner 列 44 行**（前 3 列 374 行逐行比对零变化）; `compileall` 全仓绿; 分层守门"白名单没过期"用例逼着删掉 4 条（**红的正是它该红的地方**） |
| **C11** | `core/ui` 拆 + `wiring` 上提 | `core/tui/`；`_build_director/_trigger_title` → `core/director/wiring.py` | 分层白名单减 1 条（core→renderer 消失）；绿 |
| **C12** | `core/mmt` 合并 + `apps/` + `docs/` 归位 | `core/momotalk.py`→`core/mmt/engine.py`；`main.py`/`vn_cli.py`→`apps/`；`core/*.md`→`docs/` | 全仓 `compileall`；绿 |
| **C13** | 测试拆分 + 共享桩 | `tests/webgui/bond/*`；`tests/stubs/scripted_llm.py`（与 5b 的 `stub_tasks.py` 合流） | 单测文件全部 < 400 行；绿 |
| **C14** | `llm/client.py` / `llm/image_gen.py`（可选） | 按职责再分 | 绿 |
| **C15** | `core/brain/wiki_v2/*`（可选） | digest/nodes/channel 再分 | 绿 |

顺序理由：**自上层往下**（webgui 最安全、收益最快；`contract/` 是所有人依赖的地基，放后面）；
**先拆接缝再搬文件**（C1a 已把 16 个 patch 点收敛, 之后搬块不再有静默失效风险）。

---

## 4. 工具纪律（全部在本仓库实测）

**不带新依赖**：一次性工具用 `uvx`；长期守门写成 pytest（沿用 `test_paths.py` 先例）。
`uvx` 需代理：`HTTP_PROXY=HTTPS_PROXY=http://127.0.0.1:7897`。仓库**没有任何 ruff 配置**
（`pyproject.toml`/`ruff.toml`/`setup.cfg` 都不存在）⇒ **不要 `ruff --fix` 批量改**。

| 工具 | 实测 | 用在哪 |
|---|---|---|
| **rope 1.14**（`uvx --from rope python tools/rope_move.py`） | ✅ 打开 2950 行文件 0.03s，`has_errors=False`；两次 dry-run 共 15s；`ChangeSet.get_description()` **直接给 diff**（先审后落） | **只用于 C11/C12 的"真搬家"**（跨包移动 + 全仓改 import） |
| `ruff analyze graph` | ✅ 已有 ruff 自带 | C0 依赖盘点 + 事后核对（`uvx ruff@latest analyze graph`） |
| `vulture`（仓库已在用） | ✅ | 每步搬完查"变成死引用"的名字 |
| `tach` 0.35.1 / `import-linter` 2.15 | ✅ 秒装 | **暂不用**：只有 4 条规则，自写守门更省；规则涨到十条再换 |
| `libcst` | ✅ | 暂不用（只有 16 处 patch 要改，手工更快） |

### 4.1 rope 的三次 dry-run，决定了"哪里能用它"

| 试跑 | 变更集 | 结论 |
|---|---|---|
| ① C11 型：`_trigger_title` → `core/director/director.py` | 5 文件；**tests/ 未被改** | ✅ 真搬家用它；但产出的 import 风格是全限定（`core.director.director._trigger_title(...)`）⇒ 要设 `prefer_module_from_imports`/`pull_imports_to_top` 等 prefs, 或事后人工收敛 |
| ② C3 型：`_log_scene` → 别的模块 | 2 文件；内部调用被改写成 `chat._log_scene(...)` | ❌ **拆包不能用它**：它绕过门面, 把内部调用直接指向新宿主 |
| ③ C3 型 + 被测试引用的符号（`_state`） | 6 文件, **其中 4 个是 tests/**；还**删掉测试里的 `sys.path.insert(...)`** | ❌ 同上, 且会顺手改测试的引导代码 ⇒ 与"引用点零改动"直接冲突 |

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

1. **16 个 patch 点**（C1a 已全部收敛; `tests/core/test_split_safety.py` 的
   `ALLOWED_PATCHES` 现在**是空表**——它就是"收敛完了"的机器证据）：
   `webgui.bond` 6 处（`_store`/`_choice_pregen_enabled`/`ImageGenerator`/`_image_gen`/
   `_enqueue_annotate`/2 个看门狗常量）+ `webgui.chat._store` 7 文件 8 处 + `reset_engines` 2 处
   + `llm.client._settings_toml` 1 处。
   ⇒ 收敛到 `webgui/deps.py`（消费方写 `deps.store()` 而非 `from .deps import store`
   ——**调用时属性查找** patch 才生效）, 否则模块→包之后 patch 静默失效（测试照旧绿,
   覆盖全丢）。
   ⚠️ **接缝外还有"非测试"的 patch 点**（不在守门扫描范围: 它只扫 `tests/`）:
   `experiments/web_e2e/stub_world.py` 的 `chat._store = st` 与
   `bond_mod._image_generator = …`、`l2d-demo/{async_time,ab_branch}.py` 的 `chat._store = st`
   ——C1a 一并改成 `deps.set_store()` / `deps.image_generator = …`
   （**不改成静默 no-op**: 前者的后果是冒烟写真实 data/, 后者是纪念生图链路在冒烟里
   假装跑通）。以后新增桩/脚本请照这两条改。
2. **门面 = 模块→包转换**（不是 shim 文件）: `webgui/bond.py`→`webgui/bond/`、
   `core/bond/bond_story.py`→`core/bond/bond_story/`、`contract/records.py`→`contract/records/`
   —— import 路径不变 ⇒ 13/27/其他引用点**一个字都不用改**。
3. **既有名字一个都不能丢**：`tests/fixtures/api_surface.txt`（7 拆分目标 + 接缝
   `webgui.deps` 的自有名字）守门。owner 列由 `_owner_of` **去掉私有段**
   （`pathlib._local`→`pathlib`, `webgui.bond._impl`→`webgui.bond`）⇒ 与解释器版本、
   与"包内实现文件怎么分"解耦, C1b 的验收是**夹具零 diff**。
   ⚠️ **C8 之后 owner 列本来就该变**（实现文件不再是私有的 `_impl.py`, 而是
   `webgui.bond.api` / `.state` / …）—— 判据始终是**模块 + 名字 + 种类**三列;
   C8 就是拿这一点做的验收: 刷新快照后 diff 只有 owner 列, 前两列逐行比对零变化。
   ⚠️ 快照的**名字列**永远取自门面（`__init__.py` 的显式 import 列表）——
   所以"门面 = 对外面的唯一真源"这条纪律是守门成立的前提。
4. **文档行号冻结**：`docs/ARCH_REVIEW_*` / `docs/AUDIT_*` 里的 `file.py:行号` 是历史记录,
   不追改; 新文档写 `file.py::symbol`。
5. **`core/paths.py` 未决**：上提为顶层会动 `tests/core/test_paths.py` 与 20+ 消费点,
   本计划**不含**; 若要做, 单开节点。
6. **`experiments/` + `l2d-demo/` 不在 CI**：它们也 import 这些模块（10 处）, rope 的
   变更集会覆盖它们 ⇒ 每步后跑 `compileall` 全仓 + 相关脚本的 import 冒烟。
7. **快照只记"class / function / data"三态**：不能用 `type(obj).__name__`——
   `core.momotalk._EMBED_REPORTED` 这类**运行期可变标志**导入时是 `None`、某用例跑完
   变 `bool`, 快照会抖（C0 落地当天就被守门抓出来, 这是"守门真的在工作"的证据）。
8. **门面（`__init__.py`）必须"逐个显式再导出"**（C1b 实测三条理由）：
   ① `from ._impl import *` **不带下划线名**, 而外部真在用私有名
   （`webgui/deps.py` 懒转发 `_enqueue_annotate`、测试 `from webgui.bond import _state`);
   ② 守门按**字面名字**扫, `import *` 只会被读到一个 `*` ⇒ API 面快照误报"全丢 117 个";
   ③ **不要在门面里定义 `__all__`** —— 它本身会被快照记成一个名字
   （`webgui.bond __all__`）, 而 C1b 的验收是**夹具零 diff**; 那块显式 import 列表
   就是白名单。生成办法：直接拿 `api_surface.txt` 里该段的名字当 import 列表
   （判据即来源, 逐名对齐; 生成脚本是一次性的, 不入库）。
9. **门面里绝不能放"可替换依赖"**：包内子模块读的是**自己的全局**, 打**包属性**
   （`monkeypatch.setattr(webgui.bond, "X", …)`）会**静默失效**。那类东西一律走
   `webgui/deps.py`（C1a 已收敛 16 个点, `ALLOWED_PATCHES` 空表即证据）。
10. **拆包顺序必须"叶子优先"**（C2 实测把计划改了一处）：模块之间**只能往下看**,
    否则成环。这次的具体教训是 `BoardLifecycle` —— `BondState.scene_state`（状态模型）
    与 `_log_scene`（落库, 原以为属 C2 `stores.py`）**运行期**都要用它, 谁先谁后都别扭
    ⇒ 把 `state.py` 从原来的 C7 **提前到 C2**（它是纯叶子: 只依赖 core/contract/deps）,
    后面每个模块直接 `from webgui.bond.state import BondState, BoardLifecycle`,
    环形依赖在源头消失。**做法**: 动手前先跑一次顶层依赖图（`ast` 扫 `_impl.py` 的
    顶层符号 + 名字加载, 只看"跨子集边"）, 选一个**对外边为空**的子集。
    ⚠️ 判据要看**运行期**引用: `from __future__ import annotations` 之后, 只出现在
    注解里的名字（`state: BondState`）不构成运行期依赖, 可以在类型模块里 `TYPE_CHECKING`
    或干脆不导入 —— 别把"注解里出现"误判成"必须同模块"。
11. **"名字的搬运"与"门面的来源"要一起想**（C3 定下的做法）：搬走一块之后,
    1) 新模块只 import **它自己用得到的**东西; 2) `_impl.py` 只从新模块收**它自己还在
    调用的**名字; 3) **门面（`__init__.py`）直接指向新家** —— 于是 `_impl.py` 不会
    攒下一堆"只为再导出而 import"的死名字（C8 它消失时也就没有额外迁移成本）。
    ⚠️ 对外面**一个名字都不能少**: 搬完后立刻用 `dir()`/API 面夹具核对
    （本项目 117 名 = `_impl` 收 N 个 + 门面从新模块收 M 个）;
    ⚠️ 也顺手清掉"当年为再导出而留、如今全仓无人用"的名字（C3 清了 `_impl` 里
    3 个事件常量 + `image_enabled`）—— 但**门面继续给**（它是对外面的一部分）。
12. **"这是个单文件"是测试里的隐含假设**（C9 实测踩到, "拆包"独有的坑）: 动手前先
    grep 一遍**测试里现拼模块路径**的地方。`tests/core/test_records.py` 的软硬分级守门
    原来写死 `root / "contract" / "records.py"` 与 `core/bond/bond_story.py` ——
    C9 把后者变成包的那一刻它就 `FileNotFoundError`（**红在"文件不存在", 而不是
    "规则被违反"**, 看报错容易误判成拆坏了）。做法: 扫源码的守门一律走
    "模块 → `[自己]` / 包 → 包内 `*.py`"的小助手（现役范例 = 该文件里的 `_sources`）;
    ⚠️ **取不到必须 assert**（返回空列表 = 静默不再检查任何文件 = 守门失明, 比红更危险）。
    同一条规矩对 C10 的 `contract/records.py` 已经预置好了（C10 落地时它直接生效:
    守门自动改扫 `contract/records/*.py`）。定位命令:
    `grep -rn "<模块名>\.py" tests/ core/ webgui/` —— 文档/注释里的历史提及不必改,
    但**指路用的路径**要顺手改成新家（C9 就地更新了 `core/bond/__init__.py` ·
    `core/media/emotion_lexicon.py` · `webgui/bond/replay.py` 三处）。
13. **搬 docstring 时引号必须成对闭合**（两次实际踩到, 都表现为"编译期
    `SyntaxError: invalid character '（'`"——**报错行是中文注释那行, 真因在几十行之前**）:
    ① C5: 给新模块写的头部 docstring 少一个结尾 `"""` ⇒ 后面的 import 全被吞进字符串;
    ② C10: 门面模板写成 `"""...{orig}\n## 包结构..."""`, 而 `{orig}` **本身就是一整段
    带开闭引号的 docstring** ⇒ 第一个 `"""` 提前收尾, `## 包结构` 变成代码, 末尾那个
    `"""` 反而**开了**一个吞掉全部 import 的字符串。做法: 插入前 `strip()` 掉源 docstring
    的开闭引号（`orig[3:-3]`）, 并在写盘后**立刻** `python -m compileall <新文件>`——
    这个错不会在生成脚本里报, 只在新文件被 import 时才炸。

---

## 6. 明确不做（本计划边界）

- **不改 HTTP 契约 / JSON / JS**（前端零改动）。
- **不在拆分节点里改行为**；唯一例外是 C1a 的接缝显式化（行为等价, 有全量测试 + 冒烟兜底）。
- **不重命名对外符号**（`bond_start`/`bond_turn`/`BondStoryEngine`/`check_block`…）。
- **不解决"引擎依赖终端 UI"**（`core/momotalk.py` → `core/ui/*`）与"盒B 只注入两文件"
  这类**行为级**问题——本计划只搬位置; 那些另立设计。
- 不引入新依赖 / 不改 `pytest.ini` / 不进 CI 配置。
