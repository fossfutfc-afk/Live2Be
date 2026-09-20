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

### 2.2 两条流水线的差异（"守卫只长在一条路上"）

| 守卫 / 行为 | 批式 `_build_record_boards` | 流式 `_scene_from_records` |
|---|---|---|
| `check_block` 硬违规 → 打回重发 | **有** | **无**（仅记账） |
| 软问题**文本**进日志 | **有** | ✅ **节点 1 已补**（此前只有 `issues=%d`） |
| 纯 `switch` 空板 → `spare` 并入下一板 | **有** | **无** |
| `MAX_BOARDS_PER_TURN` 上限 | **有** | **无** |
| `art` 挂载目标 = "含 memorial 的板" | **有** | 挂"首个交付板"（另一条规则） |
| `art` 写了但整块无 memorial → WARNING | **有** | **无** |
| `_demote_repeat_memorial`（章内 ≤1） | 有 | 有 |
| `_memorial_used` 置位 | 有 | 有 |

**玩家可见的具体分叉**：相邻两条 `switch` → `BlockStreamParser._close()` 把 `[switch A]`
单独成板 → `BondScene.from_board` 跳过 switch → **交付一个空板**；批式的 `spare` 合并
正是为这个场景写的。**同一段内容，走哪条路取决于"这次是玩家点击生成的、还是预生成拿的"。**

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

## 3. 目标形态

**三个"只有一份"**：

1. **`records → boards` 派生**：切板边界、`spare` 合并、`MAX_BOARDS_PER_TURN`、`art` 挂载规则，
   收进**一个**函数，两条路都调；`BlockStreamParser` 退化为纯"逐行解析 + 板闭合通知"。
2. **守卫与闸**：`check_block`（块级）与新增的 `check_board`（板级）各一份实现，
   由**交付模式**决定"违规时是拦还是记"。
3. **板级 lifecycle（未提交/已交付/已提交）**：见 §3.1，它是 c′ 的板级闸、
   也是 `docs/DESIGN_RESEND.md` 的"重发/拒绝"共用的底座。

**一个显式枚举**：

| 交付模式 | 增量交付 | 板级闸（`check_board`） | 块级校验（`check_block`） |
|---|---|---|---|
| `DeliveryMode.STREAM`（live、真机 `chat_full`） | ✅ | **拦**（不交付 + feedback） | **advisory**（记账 + 日志 + 下一轮注记） |
| `DeliveryMode.BLOCK`（CLI / 无流式客户端） | ✗（整块） | 拦 | **拦**（打回重发） |

**不变量**：**真源里永不出现"未提交"的板**——章级已由 `core/session/staging.py` 保证
（章内一切先进 `soul/staging/events.jsonl`，见 `vn_exit` 才整段 append），**板级由本计划保证**。

### 3.1 板级 lifecycle（协议草案）

```
provisional ──校验通过──► delivered ──裁决/推进──► committed（≈ 现在 scene_logged=True）
     │                        │
     └──校验不过──► 丢弃       └──玩家重发/被 supersede──► 作废（同"丢弃"语义）
```

- **挂点**：已有的写入口 `webgui/bond.py::_stage_store` / `_flow_store`（注释已写明"只用于写"）；
- **三类"丢弃"共用一条路**：① 违规板不交付（c′ 的闸）② 玩家重发（见 `DESIGN_RESEND.md`）
  ③ 邀约被拒（整章丢暂存，`staging.py` 已实现）；
- **不变量断言**：*任何"丢弃"都不需要写任何标记到真源*（这正是 `staging.py` 相对
  `vn_abandon` 的核心优势——"漏一处就污染"变成"零过滤"）。

---

## 4. 节点表（每节点一提交 + 全量测试）

| # | 节点 | 目标 / 改动 | 验收（可自动判定） | 风险 |
|---|---|---|---|---|
| ✅ **0** | **协议与设计**（本文 + `DESIGN_RESEND.md`） | 钉住现状、Decision 0、板级 lifecycle、forward-compat 约束 | 两份文档落地 + CLAUDE.md 路由登记（提交 `0393796`） | 无（未动代码） |
| ✅ **1** | **特征化测试网 + 生产可观测** | ① `tests/core/test_pipeline_parity.py`（7 例）把 §2.2 的差异**显式写成期望值** ② 流式分支的问题**文本**进日志（`issues_txt=`）③ `tests/webgui/test_bond.py::test_scene_logged_is_provisional_until_pick` 钉住 provisional 状态 **+ 章级暂存两层边界** | 全量 **861 passed**（853 → +8）；**零行为改动** | 0 |
| **2′** | **单一 `records → boards` + 板级闸 + 板级 lifecycle** | ① 抽出共用派生函数（含 `spare` 合并、上限、`art` 挂载规则）② 流式的纯 switch 板改为"挂起到下一板闭合" ③ 新增 `check_board`（板级闸）④ 引入 `DeliveryMode` 枚举并把 §3 的表写进代码注释 | 节点 1 的差异集合**缩小到只剩"交付时机"**；空板分叉消失；闸有正/反用例 | 中（动交付时机 → 需 B 层 e2e 冒烟 `experiments/web_e2e/run.py`） |
| **5** | **测试桩对齐生产** | 给 `test_web_http.py`（0 个）与 `test_bond.py` 的桩补 `chat_full`；顺手把桩的"按自然语言关键字应答"换成**结构化标记分派**（ARCH_REVIEW P2-8） | webgui 用例**跑在生产路径上**（可断言 `engine.trace` 里是 `record_stream/streamed`）+ 全量绿 | 小改动、**大暴露面**（这是本计划最强的验收放大器） |
| **3** | **守卫分层显式 + 生产可观测** | 把硬/软在两种交付模式下的语义写成**显式策略**（枚举 + 注释 + 契约文案同步）；流式硬违规 → 日志 + trace + **下一轮 feedback**；软问题文本可 grep（CLAUDE.md §12 现在让 grep 一个生产不打的串） | 新用例：流式硬违规有日志/trace、玩家不受影响；文档口径同步 | 低 |
| **4′** | **预生成与 live 同路径** | `_pregenerate` 走同一交付模式（把"增量交付"与"落库/门控"解耦）；语义升级为 **预生成 = provisional（未 adopt 即丢弃）**，与"拒绝/重发"共用 §3.1 协议 | 新用例：**同一记录流，live 与 pregen 的板载荷逐字节一致** | 中（预生成是 §9 主路径） |
| **6** | **`Issue(code, severity)` 结构化** | `check_block` 返回结构化 Issue；`split_board_issues` 不再按中文子串判硬软；测试断言同步 | 新守门用例："加问题串不会静默变成硬违规"；全量绿 | 低 |

**顺序 = 0 → 1 → 2′ → 5 → 3 → 4′ → 6**，理由：

- **1 必须先做**：现在没有任何测试证明两条路等价（§2.5），动刀前先建网；
- **5 放在 2′ 之后、3/4′ 之前**：此时两条路已等价，不会一次爆几十个红；而它一旦生效，
  3/4′ 每一步都有**生产路径**的网；
- **6 放最后**：它动 contract 层公共返回形状，等 3 把分层语义定死再结构化最省事。

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
| MMT 重发 / 邀约 / 多人 **实现** | 只做 §5 的口子，不做功能 | `docs/DESIGN_RESEND.md` / `docs/DESIGN_MEETUP.md` / `core/DESIGN_MULTI_CHAR.md` |

---

## 7. 风险与回退

| 风险 | 对策 |
|---|---|
| 板级闸引入"反馈回环"（LLM 反复产违规板） | `MAX_SCENE_RETRIES` 上限 + **超限放行**；违规只记日志不抛 |
| 交付时机变化（`spare` 挂起）导致玩家少一次点击/多一次等待 | B 层 e2e 冒烟（`experiments/web_e2e/run.py`）+ 节点 1 的特征化测试；逐段取样断言（"某段上屏那一刻"必须逐段取样，见 CLAUDE.md §12） |
| 节点 5 打开生产路径后一次性暴露大量红 | 它排在 2′ 之后（此时两路已等价）；红即"2′ 没做干净"的信号，属于**收益**不是损失 |
| 中途放弃 | **每节点一提交**，任意节点可单独回退；本文档的节点表就是回退粒度 |
