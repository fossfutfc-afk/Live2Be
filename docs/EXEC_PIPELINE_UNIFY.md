# EXEC_PIPELINE_UNIFY — 单一记录流流水线（c′）执行计划

> **状态（2026-09-21）**：**计划稿，未动代码**。Decision 0 已由用户裁决为 **c′**（见 §1）。
> **怎么用**：按 §4 节点表逐节点实施，**每节点一提交 + 全量测试**（`pytest tests/{core,webgui,llm,renderer} -q --basetemp=.testtmp/pw`）；
> 节点 0 由本文档 + `docs/DESIGN_RESEND.md` 承担（已写）。
> **凡本文与代码冲突，信代码**，并顺手把这段改掉。
>
> **⚠️ 本文只写"文件 + 符号"，不写行号**——行号必漂（`DESIGN_MEMORIAL.md` 引的
> `bond_story.py:786` 在 2026-09-21 已经指到无关代码）。要定位就 `grep -n "<符号>"`。
>
> **相关**：`docs/ARCH_REVIEW_2026-09-20.md`（本文要解决的 P0-2/P0-3 出处）·
> `docs/DESIGN_MEMORIAL.md`（块/板/记录三层定义）· `docs/DESIGN_RESEND.md`（重发语义，
> 与本计划的"未提交"协议同源）· `docs/EXTENSION_POINTS.md`（哪类接口可以留）。

---

## 1. 决策记录（Decision 0）

**问题**：同一块 LLM 输出有**两条流水线**，走哪条取决于"调用方传没传 `on_board`"与
"LLM 客户端有没有 `chat_full`"——**隐式分派**。而"校验/兜底"只在其中一条上。

| 选项 | 板派生 | 交付 | 板级硬闸 | 块级硬闸 | 代价 |
|---|---|---|---|---|---|
| a 共享派生 + 双模式显式 | 一份 | 两种模式 | batch 有 / stream 无（现状） | batch 有 / stream 无 | "两种模式"仍在（只是变显式） |
| b 只留批式 | 一份 | 整块 | 有 | 有 | **丢 §9 的首屏优化**（产品退步） |
| c 裸只留流式 | 一份 | 增量 | 无 | 无 | 硬闸全面失守 |
| **c′ 只留流式 + 板级闸（裁决）** | **一份** | **增量** | **有（新写）** | 仅 art 配对降级为 advisory | 需实现板级闸 + 首板违规时退回等待 |

**裁决 = c′**（用户 2026-09-21）。**为什么 c′ 成立**：

> 流式与硬闸**并不根本冲突**——冲突的是**校验单位（块）与交付单位（板）错配**。
> 逐条看规则落在哪一层：
>
> | 规则 | 最小可判单位 | 交付前能判吗 |
> |---|---|---|
> | 空块 / 首条不是 switch / 必须块尾 / 坏行丢行 / 超长 sensei 群 / 单板记录数 | **板**（或"行"） | **能**——板闭合即判，判过再交付 |
> | 章内第二次 memorial | **板**（`_demote_repeat_memorial` 已在板级跑） | **能** |
> | memorial 与 end 同块 | **板**（end 一出现即知该块该结束） | **能**（近似） |
> | **art 写了但整块没有 memorial** | **块**（memorial 可能在本块后段才出现） | **不能** → 天生 advisory |
>
> ⇒ 真正只能块级的只剩 **art↔memorial 配对**（外加"整块空"）。也就是说：**写了板级闸之后，
> 硬闸比今天生产上的更强**（今天板级也没执法，见 §2.1 的注释原文）。

**被否的理由**：b 拿产品行为换代码整洁；a 把"隐式分叉"永固化；c 让"引擎判"的硬闸全线失守。

---

## 2. 现状事实（逐条核对代码；2026-09-21）

### 2.1 分派点

`core/bond/bond_story.py::BondStoryEngine.send_vn_scene` 里：

- `stream = BlockStreamParser(...) if on_board is not None else None` —— **只有调用方传 `on_board` 才有流式解析器**；
- `chat_full = getattr(self.llm, "chat_full", None)` —— 客户端没有 `chat_full` 就回退 `chat()`，此时 `stream` 收不到任何 chunk；
- `if delivered:` → **流式分支**：只把 `check_block` 的结果记进 trace + 打一行 `issues=%d`（**只打数量，不打文本**），**不反馈、不打回**；
- `else:` → **批式分支** `_build_record_boards`：硬违规 → `feedback()` 打回重发，软违规 → 日志。

流式分支的注释原文（**这就是"硬闸在生产上今天就没执法"的证据**）：

> *"流式已交付（on_board 给过板）: **不再重复解析/交付**——校验只做记账。
> 注: 流式下'硬违规'无法回滚（板已在玩家屏上）, 故只 trace/日志, 不打回重发
> （真机守形 0 违规; 反馈留给上层下一轮注记）。"*

### 2.2 两条流水线的差异（**节点 2′ 已统一** ✅）

改动前的分叉逐条列在下面（本表 = 历史 + 现状对照）:

| 守卫 / 行为 | 改动前（批式 / 流式） | 现状（节点 2′ 之后） |
|---|---|---|
| 板装配 | 各写一份（`_build_record_boards` / `_scene_from_records`） | ✅ **`_BoardAssembler` 单源**（两条路同一个类） |
| `check_block` 硬违规 → 打回重发 | 有 / **无（仅记账）** | ✅ 批式仍拦；流式改由**板级闸 `check_board`** 拦（仅首板交付前） |
| 软/硬问题**文本**进日志 | 有 / 无（只有 `issues=%d`） | ✅ **节点 1 已补**（`issues_txt=`） |
| 纯 `switch` 空板 | `spare` 并入下一板 / **交付空板** | ✅ 两侧都**向前合并** |
| 块尾纯 `switch` | 向后并入末板 / 单独成板 | ✅ 两侧都**末板自成一板**（不引入前瞻, 保首屏） |
| `MAX_BOARDS_PER_TURN` 上限 | 有 / **无** | ✅ 两侧都有 |
| `art` 挂载目标 | "含 memorial 的板" / "首个交付板" | ✅ 两侧都挂**首个板** |
| `art` 写了但整块无 memorial | WARNING / 无 | ✅ 两侧都进 `check_block` 软问题（流式经 `issues_txt` 可 grep） |
| `_demote_repeat_memorial`（章内 ≤1） | 有 / 有 | 不变 |
| `_memorial_used` 置位 | 有 / 有 | 不变（现由装配器统一置位） |

**仅存的差异 = 两类, 且都是有意**（由 `DeliveryMode` 表达）:

1. **交付时机**: 流式增量交付 / 批式整块交付;
2. **已交付之后的校验是 advisory**: 流式拦不住已上屏的板——"打回重发"产出的是**另一段
   文本**, 玩家侧表现为"同一段戏讲两遍"（`docs/DESIGN_RESEND.md` §3）。

**改动前的玩家可见分叉（已消除）**：相邻两条 `switch` → `BlockStreamParser._close()` 把
`[switch A]` 单独成板 → `BondScene.from_board` 跳过 switch → **交付一个空板**。
**同一段内容，走哪条路取决于"这次是玩家点击生成的、还是预生成拿的"** —— 现在不再如此。

### 2.3 调用方矩阵

| 调用方 | 传 `on_board`？ | 实际流水线 |
|---|---|---|
| `webgui/bond.py::_generate`（玩家点击、真机 LLM 有 `chat_full`） | **传** | **流式** |
| `webgui/bond.py::_pregenerate`（零等待预生成；§9 说这是主路径） | 不传 | **批式** |
| `webgui/bond.py::_candidate_worker`（候选支预生成） | 不传 | **批式** |
| `core/ui/vn_cli.py`（CLI） | 不传 | 批式 |

### 2.4 测试站在分界的错误一侧

| 测试文件 | `def chat_full` 个数 | 后果 |
|---|---|---|
| `tests/webgui/test_web_http.py` | **0** | 全程批式 |
| `tests/webgui/test_bond.py` | 1（仅个别用例） | 绝大多数用例走批式 |
| `tests/core/test_vn_records_engine.py` | 4 | 少数核心用例覆盖流式 |

⇒ **webgui 状态机测试套件系统性验证的是生产不跑的那条解析路径**。

### 2.5 现有"等价性"测试只覆盖一半

`tests/core/test_records.py::test_board_split_batch_stream_equivalence` 只钉了**切板边界**
（`_board_spans` vs `BlockStreamParser`，7 种边界）。**§2.2 表里那些守卫的差异没有任何测试覆盖。**

### 2.6 为什么"交付后不能回滚"（回滚半径清单）

流式每一板落地都走 `webgui/bond.py::_scene_landed`，一次交付**同时触发 8 个有副作用的消费者**：

`state.scene_obj/scene/scene_input` 覆盖 · `vn._in_memorial` 置位 · `_ensure_memorial_img`
（可能写 marker） · `if scene.is_end: state.completed = True`（触发 wrapup/digest 链） ·
`_log_board_deliver` 台账 · **`_log_scene_meta` 写 marker（落事件流）** ·
**`_enqueue_annotate`（emotion/place lane 开始花钱）** · `_spawn_candidates` · `fail_count` 复位。

⇒ "打回重发"要撤销的不是一个字符串，而是一整套已启动的连锁；其中 **marker 落库不可撤销**
（append-only；章级只能 `vn_abandon` 遮断，粒度是章不是板）。

---

## 3. 目标形态（**节点 2′ 已落地** ✅）

**三个"只有一份"**：

1. **`records → boards` 派生** ✅：`_BoardAssembler`（`core/bond/bond_story.py`）单源——
   不可见板向前合并、`MAX_BOARDS_PER_TURN`、`art` 挂首个板、章内二次 memorial 降级，
   两条路都调。切板仍由两条切板器负责（`_board_spans` / `BlockStreamParser`，
   两者的边界等价早已有测试：`tests/core/test_records.py::test_board_split_batch_stream_equivalence`）。
2. **守卫与闸** ✅：`check_block`（块级，`contract/records.py`）与 `check_board`
   （板级，同文件）各一份实现，由 **`DeliveryMode`** 决定"违规时是拦还是记"。
3. **板级 lifecycle**（**节点 2″ 已落地** ✅）：`webgui/bond.py::BoardLifecycle`
   （`PROVISIONAL → DELIVERED → COMMITTED`）+ 唯一丢弃入口 `_discard_boards`；
   它是 c′ 的板级闸、也是 `docs/DESIGN_RESEND.md` 的"重发/拒绝"共用的底座。

**一个显式枚举**：

| 交付模式 | 增量交付 | 板级闸（`check_board`） | 块级校验（`check_block`） |
|---|---|---|---|
| `DeliveryMode.STREAM`（live、真机 `chat_full`、**预生成**——节点 4′ 起） | ✅ | **拦**（不交付 + feedback） | **advisory**（记账 + 日志 + 下一轮注记） |
| `DeliveryMode.BLOCK`（CLI / 无流式客户端） | ✗（整块） | 拦 | **拦**（打回重发） |

⚠️ **预生成必须与 live 同一格**（节点 4′）: 预测"玩家点继续时会看到什么"的东西,
不能比 live 更严——否则同一份输出在两侧给出不同的板（历史: 预生成走批式, 对
"首板之后的形状违规"直接打回 3 次 ⇒ 预生成失败, 而 live 是 advisory 照常交付）。

**不变量**：**真源里永不出现"未提交"的板**——章级已由 `core/session/staging.py` 保证
（章内一切先进 `soul/staging/events.jsonl`，见 `vn_exit` 才整段 append），**板级由本计划保证**。

### 3.1 板级 lifecycle（**节点 2″ 已落地** ✅）

```
PROVISIONAL ──交付上屏──► DELIVERED ──裁决/推进/收尾──► COMMITTED（旧 scene_logged=True）
     │                        │
     └──丢弃──►（无痕）        └──重发/被 supersede──► 丢弃（同"无痕"语义）
```

- **落地形态**：`webgui/bond.py::BoardLifecycle`（`str` 枚举 + `committed` 属性）取值于
  `BondState.scene_state`; `PROVISIONAL` 那一态由**预生成板**占据（`state.pregen_obj`,
  不进 `scene_obj`）; 状态也随 `bond_status` 出（`scene_state=delivered|committed`）;
- **唯一丢弃入口**：`_discard_boards(state, char_id, reason=…)`——清预生成板 + 候选支池
  + 草稿旁路（"已生成未播放"的持久化落点）, 并打一行 `bond_boards_discarded reason=…`
  作为**唯一痕迹**。⚠️ 它**不动当前板**（`DELIVERED` 已在玩家屏上, 丢它是产品决策）,
  也**不动 `_prewarm_cache`**（那是章节入口的暂存首场, 新鲜度判据 `staged_seq`）;
- **丢弃必须挡住"在途落地"**（**○C8c 补的洞**, 2026-09-21 —— 见 `EXEC_SPLIT` §5 陷阱 16）:
  只清引用是不够的, 一个已经飞出去的后台线程（预生成 / live 流式 / 候选支）跑完后会把
  刚清掉的东西写回来（`pregen_scene` 甚至草稿文件复活 ⇒ "唯一痕迹"白打）。补法 =
  `BondState.board_epoch`: `_discard_boards` 每次 **+1**（= 这一刻之前出生的板全部作废）,
  后台产者**出生时记世代、落地前复核**（`_board_epoch_stale` → 一行 `bond_board_stale`）;
  写盘的复核与删除在**同一把 `state._lock`** 里 ⇒ 丢弃与落地互斥。副产品: 这条把
  "板级生命周期的丢弃"从"清内存"升级成**一个可断言的状态机不变量**;
- **三类"丢弃"的关系**：① 违规板不交付（c′ 的闸——引擎侧根本不交付, 无内存可清）
  ② 玩家重发（`DESIGN_RESEND.md`, 用 `_discard_boards`——**唯一会与在途生成并发的调用者**,
  所以 ○C8c 的世代复核正是它的前置条件）③ 邀约被拒（整章丢暂存,
  `staging.py` 已实现, 生命周期属"章"不属"板"）;
- **不变量断言**：*任何"丢弃"都不需要写任何标记到真源*（这正是 `staging.py` 相对
  `vn_abandon` 的核心优势——"漏一处就污染"变成"零过滤"）。节点 2″ 的用例
  `test_discard_boards_is_traceless` 直接比对丢弃前后 overlay 的事件 seq 列表;
  ○C8c 再加两条: `test_stale_pregen_landing_is_dropped`（在途落地被拦 + 新一代照常落地）与
  `test_discard_inside_pregen_landing_window`（"板已可见、草稿未落"的窗口里丢弃）。

---

## 4. 节点表（每节点一提交 + 全量测试）

| # | 节点 | 目标 / 改动 | 验收（可自动判定） | 风险 |
|---|---|---|---|---|
| ✅ **0** | **协议与设计**（本文 + `DESIGN_RESEND.md`） | 钉住现状、Decision 0、板级 lifecycle、forward-compat 约束 | 两份文档落地 + CLAUDE.md 路由登记（提交 `0393796`） | 无（未动代码） |
| ✅ **1** | **特征化测试网 + 生产可观测** | ① `tests/core/test_pipeline_parity.py`（7 例）把 §2.2 的差异**显式写成期望值** ② 流式分支的问题**文本**进日志（`issues_txt=`）③ `tests/webgui/test_bond.py::test_scene_logged_is_provisional_until_pick` 钉住 provisional 状态 **+ 章级暂存两层边界** | 全量 **861 passed**（853 → +8）；**零行为改动** | 0 |
| ✅ **2′** | **单一 `records → boards` + 板级闸 + 交付模式** | ① `_BoardAssembler`（不可见板向前合并 / 板上限 / `art` 挂首板 / 章内二次 memorial）两条路共用 ② `contract/records.py::check_board`（板级闸: `end` 后还有记录 / 同板多条 memorial / 纪念区间内换场）③ `DeliveryMode` 枚举（`STREAM`/`BLOCK`）写进 trace ④ 流式**首板交付前**拦、已交付后 advisory | 8 例 parity 全绿（差异集合 = **仅剩交付时机 + 有意的模式差异**）；全量 **862 passed** + **B 层 e2e 冒烟 PASS** | 中（已过: 批式行为变更无回归 + 全量绿） |
| ✅ **2″** | **板级 lifecycle 显式化** | ① `webgui/bond.py::BoardLifecycle`（`PROVISIONAL`/`DELIVERED`/`COMMITTED` + `committed` 属性）取代裸 bool `scene_logged`（9 处迁移）② `_discard_boards(state, char_id, reason=…)` = **唯一丢弃入口**（预生成板 + 候选支池 + 草稿旁路; 打 `bond_boards_discarded` 一行 = 唯一痕迹; 不动当前板/预热缓存）③ 接进 `_pregenerate` 失败降级与 `bond_finish` 收尾 ④ `bond_status` 出 `scene_state` + `pregen_ready` | `test_bond.py`：`test_scene_logged_is_provisional_until_pick` 改成断言 `DELIVERED → COMMITTED`（原节点 1 的锚点）+ 新增 `test_discard_boards_is_traceless`（丢弃前后 overlay 事件 seq **一条不多一条不少**, 三处引用全清而当前板不动）；全量 **869 passed** | 小-中（已过） |
| — | *为什么 2″ 单列*: 它是 `DESIGN_RESEND`（重发/拒绝）与"板级 lifecycle"的**地基**, 但**不是**流水线统一所必需——节点 2′（闸+交付模式）已经独立成立且可验收。拆开做可以避免"为将来的功能拖住当下的收敛"。 | | | |
| ✅ **5** | **测试桩对齐生产** | 给 `test_web_http.py`（原 **0 个** `chat_full`）与 `test_bond.py` 的桩补 `chat_full`——**按行喂 `on_chunk`**（= 真机 `LLMClient.chat_full` 语义, 板一闭合即交付）; 新增 `test_webgui_runs_on_streaming_production_path` 断言 trace 是 `record_stream/streamed` 且 `delivery_mode=stream` | **webgui 37 例全绿**（切到生产路径**零失败** = 节点 2′ 统一为真的最强证据）+ 全量 **863 passed** | 小改动、**大暴露面**（已过: 零回归） |
| ✅ **5b** | **桩的结构化分派**（ARCH_REVIEW P2-8） | ① `llm/task_labels.py` = **调用身份词表**（`emotion` / `place` / `place_board` / `place_variant` / `digest.round_a|b` / `mmt` / `bond` + `ALL`/`MAIN`/`PROFILE_OF`）② `llm/client.py` 的 `chat`/`chat_full` 加 keyword-only **`task`**——**不进 messages/payload**（前缀缓存与夹具零影响）, 进日志（`llm chat task=…`, 顺手补上生产侧"这次调用是谁"）③ 产品侧 **10 个物理调用点**全带上（`emo_text` · `emotion_annotate`×2 · `place_annotate`×2 · `variant_annotate` · `wiki_v2/llm_call`（透传既有 `label`）· `momotalk` · `bond_story` 的 `chat`+`chat_full`）④ 桩改按 `kw["task"]` 分派（**~16 个测试文件** + B 层冒烟的 `stub_world.py` + 2 个真机探针 + 2 个封闭签名桩补 `**kw`）, 共享应答助手 `tests/stub_tasks.py`（含 `emotion_count` 的 `恰 N 项` 口径与 `unknown_task` 指路报错） | **旧的多余半层已删**（`test_stub_keyword_guard.py` 整文件删除）; 新守门 `tests/core/test_stub_dispatch_guard.py`（产品调用点必须带 `task=` / 标签必须在词表且形态必须在 `task_levels.PROFILES` / 测试里不许再有中文串分派 / 桩助手对缺失或未知 task 会报错指路）；**实测删掉一处 `task=` → 立刻红**；全量 **874 passed** + B 层冒烟 PASS | 中（已过: 动公共签名, 零行为改动） |
| ✅ **3** | **守卫分层显式 + 下一轮纠偏** | ① `BondStoryEngine._pending_feedback`：**已交付**后发现的形状问题（流式 advisory 的硬问题 + 批式软问题）记账 ② 下一轮拼进 notes（场卡**之前**、注入后**自清**）——"（系统）上一轮输出的**形状**有这些问题: …" ③ `DeliveryMode` 下硬/软的语义写进注释（板级 ⊆ 块级 ⇒ 板级闸不新增拒绝） | 新用例 2 例：`test_vn_records_engine.py::test_soft_issues_become_next_round_note`（软问题 → 下一轮 notes 出现纠偏文本 + 自清）、`test_pipeline_parity.py::test_stream_late_violation_pends_feedback_for_next_round`（流式已交付后违规 → 记账 not 只打日志）；全量 **865 passed** | 低（已过） |
| ✅ **4′** | **预生成与 live 同路径** | `webgui/bond.py::_pregenerate` 补 `on_board=_on_pregen_board` ⇒ 预生成也走 `DeliveryMode.STREAM`（此前不传 ⇒ 退回批式, 同一份输出两条路给出**不同的板**）。回调**只记账不落库** = 预生成 **provisional**（真源/暂存的 `bond` 事件等玩家消费时 `_log_scene` 才写; "丢弃"不需要清任何东西）。新增台账 `bond_pregen_board board=N recs=N dur=ms`（预生成**首板**到达时刻, 与 `bond_pregen src=gen dur=` 的"整块写完"对照）。⚠️ 显式 lifecycle 枚举（provisional→delivered→committed）仍归节点 2″ | 新用例 2 例（`tests/webgui/test_bond.py`）：`test_pregen_uses_live_delivery_path`（同一记录流 live/pregen **板载荷逐字节一致** + 预生成 trace 是 `record_stream/streamed`/`delivery_mode=stream`; **去掉 `on_board` 即红**——已实测）、`test_pregen_board_is_provisional_until_adopted`（预生成不落库/在草稿旁路 → adopt 只是提升 → 再推进才写暂存, 真源仍无） | 中（已过: 全量 **868 passed** + B 层冒烟） |
| ✅ **6** | **`Issue(code, severity)` 结构化** | ① `contract/records.py`: `IssueCode`（`block.*`/`board.*`）+ `IssueSeverity` + **`ISSUE_SEVERITY: IssueCode → IssueSeverity` 唯一真源** + `Issue(code, message)`（`severity` 是派生属性）+ `format_issues`/`split_issues` ② `check_block`/`check_board` 返回 `list[Issue]`；`bond_story.HARD_BLOCK_ISSUE_MARKS` 与 `split_board_issues` **删除** ③ trace 里问题分两份：人读文本 `issues` + 机器码 `issue_codes` ④ 测试断言改成看 `IssueCode` | **守门用例** `test_records.py::test_issue_severity_is_declared_by_code_not_message`（软问题文案**塞满硬关键词**也不改分级 / 每个码必须声明严重度 / 源码不许复活子串分级）；全量 **866 passed** | 低（已过） |

**顺序 = 0 → 1 → 2′ → 5 → 3 → 6 → 4′ → 2″ → 5b**（**全部落地**；唯一没做的是用户
2026-09-21 说"之后再做"的 `webgui/bond.py` 文件拆分），理由：

- **1 必须先做**：现在没有任何测试证明两条路等价（§2.5），动刀前先建网；
- **5 放在 2′ 之后、3/4′ 之前**：此时两条路已等价，不会一次爆几十个红；而它一旦生效，
  3/4′ 每一步都有**生产路径**的网；
- **6 在 3 之后**：它动 contract 层公共返回形状，等 3 把分层语义定死再结构化最省事
  （节点 3 引入的 `_pending_feedback` 正好是第一个"软硬都要走同一条路"的消费者）；
- **4′ 放最后**：它动性能主路径（预热/预生成链），单独验收更容易定位回归；
  且它的验收方式就是"与 live 逐字节一致"——前面的节点没落地时这条根本没意义。
- **2″ 收尾**：它是三个"可选地基"里唯一被未来需求（重发 / 拒绝 / 多人）**反复踩到**的
  那块——放在最后做, 正好把前面所有节点的状态语义一次性收进一个枚举。
- **5b 最后**：它动 `llm.chat` 的公共签名 + 每个 test double, 是纯"测试/可观测基础设施"
  （不阻塞任何产品功能）; 放在所有语义节点定稿之后做, 才不会边改边返工。
  ⚠️ 它替换掉了 2″ 之后那个**廉价前置**（关键字 ↔ 源 的守门表）——那张表可以整体删了,
  因为"桩不再看文案"比"保证文案还在"强一档。

---

## 5. forward-compat 约束（**不实现，但计划里写明"不许写死"**）

来源：用户 2026-09-21 说明的四项未来需求。这里只记**对本次改动的要求**，
重发的完整语义见 `docs/DESIGN_RESEND.md`。

| 未来需求 | 不许写死的假设 | 现在留的最小口子 |
|---|---|---|
| **多人模式** | ① `records → boards` 不得假设"一个主说话人"（现在是 `contract.is_main_speaker` + 别名归一）② 板载荷不得假设"一板一立绘/一背景"（`DESIGN_VN_UPGRADE` §14：**站位是持久状态**，需 cast/站位快照）③ engine/state 不得假设 `(char, session)` 一对一（`webgui/bond.py::_bonds`、`BondStoryEngine.fork_for_pick`） | 载荷加**可选** `cast` 槽位（空着不填）；说话人归一改成"查 cast 表"的函数签名（默认单元素 cast）。纯签名级，零行为改动 |
| **重发 / 重新生成** | supersede 的**消费面必须一次定齐**（否则又是"漏一处就污染"） | 见 `DESIGN_RESEND.md` §6 的清单；"丢弃"路径**不需要**任何消费面改动 |
| **邀约 / 拒绝** | 入口意图不得与 VN 生命周期耦合；"拒绝"必须**不写 VN 事件** | 邀请做成一等事件（pending/accepted/declined/expired）；`staging.py` 的"丢缓存=从未发生"已就位 |
| **本计划自身** | 板级闸不得变成"卡死" | 复用 `MAX_SCENE_RETRIES`（现定义在 `bond_story.py`，值 3），**超限放行**（宁可显示别卡死，符合"宁缺勿错"） |

---

## 6. 明确不在本计划内

| 项 | 为什么不在 | 归属 |
|---|---|---|
| 拆 `webgui/bond.py`（ARCH_REVIEW P1-4） | **必须在流水线收敛之后**做，否则会把分叉复制成"两份都叫 landing 的模块" | 本计划之后独立立项 |
| 真分歧 / A2 分支叙事化 | 2026-09-10 已定稿关闭（收敛链即终局） | `docs/archive/DESIGN_BOND_CONTRACT_V2.md` |
| 候选支预生成（DESIGN_CHOICE_PREGEN）是否退役 | 独立裁决：v2 下唯一调用点被 `if not scene.records:` 挡住，只剩"v1 旧档回放"这条冻结路径能到达 | 独立节点 |
| 测试侧 16 处 F841 + 1 处 F811 | 与流水线无关；且**不能**批量跑 `ruff --unsafe-fixes`（会把 `r = st.resume(...)` 这类带副作用的调用一起删） | 独立小节点 |
| MMT 重发 / 邀约 / 多人 **实现** | 只做 §5 的口子，不做功能 | `docs/DESIGN_RESEND.md` / `docs/DESIGN_MEETUP.md` / `docs/DESIGN_MULTI_CHAR.md` |

---

## 7. 风险与回退

| 风险 | 对策 |
|---|---|
| 板级闸引入"反馈回环"（LLM 反复产违规板） | `MAX_SCENE_RETRIES` 上限 + **超限放行**；违规只记日志不抛 |
| 交付时机变化（`spare` 挂起）导致玩家少一次点击/多一次等待 | B 层 e2e 冒烟（`experiments/web_e2e/run.py`）+ 节点 1 的特征化测试；逐段取样断言（"某段上屏那一刻"必须逐段取样，见 CLAUDE.md §12） |
| 节点 5 打开生产路径后一次性暴露大量红 | 它排在 2′ 之后（此时两路已等价）；红即"2′ 没做干净"的信号，属于**收益**不是损失 |
| 中途放弃 | **每节点一提交**，任意节点可单独回退；本文档的节点表就是回退粒度 |
