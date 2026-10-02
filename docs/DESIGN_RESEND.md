# DESIGN_RESEND — 「重新生成 / 重发」的语义与固化线

> **状态（2026-09-21）**：**设计稿，未动代码**。
> **决策**：MMT 的提交边界 = **a. 回合提交**（用户 2026-09-21 裁决）。
> **怎么用**：本文只定义**语义与边界**；流水线侧的落地挂在 `docs/EXEC_PIPELINE_UNIFY.md`
> 的"板级 lifecycle"协议上（两者共用"未提交即丢弃"）。
> **凡本文与代码冲突，信代码**。本文只写符号不写行号（行号必漂）。
>
> **相关**：`core/session/staging.py`（B0 整章暂存 = 本文"丢弃"路线的既有实现）·
> `core/brain/revise.py` + `evolution.py`（"更正"路线的既有实现）·
> `TODO.md`（三种结局图与"中断语义修正"）· `docs/DESIGN_MEETUP.md`（邀约/拒绝）。

---

## 1. 一句话

> **append-only 不需要被破坏；需要被定义的是"什么时刻算固化"。**

你已经有两级固化线（章提交 / 记忆水位）。把它们当作"可丢弃窗口"的边界，
"重发"就永远是**丢弃**或**更正**，而不是**改写历史**。
**改写历史才是真正会破坏真源语义的那件事——而本设计一次都不需要它。**

---

## 2. 固化线（现网事实）

| 级别 | 边界 | 实现 | 越界后意味着什么 |
|---|---|---|---|
| **章** | `vn_exit` | `core/session/staging.py`：章内一切先进 `soul/staging/events.jsonl`，见到 `vn_exit` 才整段 append 进真源 | 章内的板**天然可丢**（丢弃 = 从未发生，零删除操作） |
| **记忆** | `store.meta.digested_seq` | `core/brain/digest.py`：只取 `seq > digested_seq` 的事件；**成功才推进水位** | 水位之下的内容**已经变成她的记忆/wiki 节点/好感快照** |

### 2.1 为什么不能"删真源里的行"

不是因为 append-only 是教条，而是因为 **`seq` 是三处机制的地基**：

| 消费者 | 依赖 |
|---|---|
| 前端轮询游标 | `webgui/static/js/mmt.js` 持 `_lastSeq` → 请求 `events?since=<seq>`（`webgui/routers/mmt.py`） |
| digest 水位 | `new_events = seq > store.digested_seq` |
| 恢复窗口 | `window_messages` 倒序装填、按叙事单元驱逐 |

**删一行 = 出现空洞**：三处都得学会处理空洞，且 `last_seq` 可能回退 → 前端增量拉取会漏/重。
⇒ **真源永不删行**是本设计的硬约束（不是偏好）。

---

## 3. 两个语义区（由固化线切开）

| 位置 | 那条内容的现状 | "重发"应是什么 | 机制（**全部现成**） |
|---|---|---|---|
| **水位之上**（`seq > digested_seq`）**未固化** | 只是记录，还没变成记忆 | **丢弃重来** —— 真源**零改动** | 复用 `staging.py` 的"删除变丢弃"：**让它从未提交** |
| **水位之下**（已固化） | 已进 wiki 节点 + 好感快照 | **不是"撤销那句话"，而是"记忆更正"** | **不动 `events.jsonl`**；用 `brain/revise.py::apply_revision_package` + `evolution.py::EvolutionLog`（带审计、可回滚）表达更正 |

⚠️ **板级的那一半已经落地**（2026-09-21, `EXEC_PIPELINE_UNIFY` 节点 2″）:
`webgui/bond.py::BoardLifecycle` 把"未提交/已交付/已提交"变成显式三态
（`PROVISIONAL → DELIVERED → COMMITTED`, 取代裸 bool `scene_logged`）,
`_discard_boards(state, char_id, reason=…)` 是**唯一的丢弃入口**（预生成板 +
候选支池 + 草稿旁路）——它的日志 `bond_boards_discarded` 是丢弃的**唯一痕迹**
（真源/暂存零改动）。将来做"重发/拒绝"时:
**`DELIVERED`（水位之上）→ `_discard_boards`** ; **`COMMITTED`（水位之下）→ revise**。
判据不再是注释里的约定, 而是可断言的状态。

⚠️ **"重发"是唯一会与在途生成并发的丢弃调用者**（`bond_finish` 那条被 busy 闸挡住,
`pregen-fail` 在自己的线程里）—— 所以 ○C8c（2026-09-21）先把"丢弃必须挡住在途落地"
补上了: `BondState.board_epoch` + `_board_epoch_stale` 让"丢弃那一刻之前出生的板"
全部作废（含 `_draft_save` 的写盘复核, 与丢弃同一把锁）。**做重发之前请确认这条还在**:
否则丢弃之后一个跑完的预生成线程会把板写回来, 玩家看到的还是被拒的那一块。

### 3.1 为什么"更正"是对的，而不是妥协

它与你已裁过的一条**同构**（`TODO.md`）：

> *"现状把'中断'当 `vn_abandon` ＝**宣告没发生过**；正确语义是 `vn_exit completed=False`
> ＝**发生过但没读完** —— 她**确实经历了**那半段。"*

**MMT 重发同理**：已固化的消息"她当时确实说了"——只是**记忆被更正了**。
这样整套语义自洽，而不必开"真源可改写"这个会污染全局的例外。

### 3.2 三条例行不变式全都保住

| 不变式 | 状态 |
|---|---|
| 真源可重建一切状态 | ✅ 丢弃 = 从未存在；更正 = wiki 有 evolution 审计 |
| 真源 append-only（不可改删） | ✅ 两条路线都不碰真源 |
| `seq` 单调无洞 | ✅ 不删行 |

**唯一失去的**是"重发任意历史消息"这个功能——它被降级为**记忆更正**（见 §8）。

---

## 4. MMT 的提交边界 = 回合提交（决策 a）

**定义**：`unit = 一条 user 事件 + 它触发的 assistant 回复事件`；
**下一条 user 事件到来时，提交（commit）上一个 unit**。

| 项 | 内容 |
|---|---|
| **可重发窗口** | **最后一个未提交的 unit**（= 玩家刚看到的那一轮） |
| **为什么是它** | 它尚未被任何下游消费、也尚未被玩家当作历史读 → **纯丢弃，真源零改动** |
| **越界（更早的消息）** | 走 §3 的**更正通道**（revise 包），不重发 |
| **与 VN 的关系** | VN 的提交边界是 `vn_exit`（章）；MMT 是"下一个 user"（轮）——**同一套"未提交即丢弃"，只是粒度不同** |

### 4.1 需要新增什么

| 缺口 | 现状 | 要做 |
|---|---|---|
| **MMT 没有暂存边界** | `core/momotalk.py` 直接写注入的 `store`（真源） | 给 MMT 一个**暂存式写入口**（可复用 `staging.py` 的形态，但边界是"下一个 user"而不是 `vn_exit`） |
| **前端没有重发入口** | `mmt.js` 只渲染气泡 | 重发按钮/菜单 + "替换该气泡"的渲染语义（**不需 rewind**：只替换最后一个 unit） |
| **引擎没有"重生成"语义** | `agent_turn` 只能追加 | 重发 = 丢弃未提交 unit + 用同一输入再跑一次 `agent_turn`（历史里不能残留被丢弃那一轮） |

### 4.2 开放问题（**需后续裁决**，不阻塞本次）

1. **unit 的确切事件构成**：`agent_turn` 一轮可能落**多条**事件（每动作一条，见 CLAUDE.md §3.1）
   → "提交 unit"是提交"这一轮的全部事件"还是"仅 assistant 事件"？
2. **未提交 unit 与 digest 触发点的交互**：MMT digest 每 25 轮触发，且 `interact_max`
   按 `digested_seq` 过滤（`core/momotalk.py::_interact_max`）→ 未提交的 unit
   **是否计入轮数**？（建议：不计入——否则"重发"会改变 digest 时机）
3. **重发入口的产品形态**：气泡长按 / 菜单项 / 只对最后一条显示？
4. **重发生成的成本**：是否复用候选支 fork（`webgui/bond.py::_candidate_worker` 那一套）
   做"并行生成 N 版让玩家挑"？（那是另一条产品线，别顺手塞进来）

---

## 5. 更正通道（已固化）＝ revise 包

- 入口：`core/brain/revise.py::apply_revision_package`（修订契约校验 + 执行；
  执行前深拷贝、失败回滚——`WikiStoreV2.clone_state` / `restore_state`）；
- 审计：`core/brain/evolution.py::EvolutionLog`（append-only 审计日志，也是 R6 回滚依据）；
- **不碰 `events.jsonl`**：真源保留"她说过"的事实，wiki 表达"这条记忆被更正"。

⇒ 所以"已固化重发"**不需要任何新机制**，只需要一条策略：**越界 → 发 revise 包**。

---

## 6. 下游消费面清单（一次定齐）

`staging.py` 的核心优势是"丢弃 ⇒ **没有任何地方需要记得过滤**"。所以本节的清单
**只对"更正"路线必要**（对"丢弃"路线是空的——这正是选它的理由）：

| 消费面 | 位置 | 更正时要处理什么 |
|---|---|---|
| 上下文窗口 | `core/session/renderer.py::window_messages` | 窗口里读到的应是**更正后**的视图（若更正发生在窗口内） |
| 叙事化渲染 | `renderer::render_events` / `render_timeline` | 同上 |
| **digest 水位** | `digest.py`（`seq > digested_seq`）+ `meta.digested_seq` | 更正**不能**推进水位；已消化内容靠 revise 修，不靠重消化 |
| 好感事件 | `core/affection/affection_calc.py`（按 `digested_seq` 覆盖键过滤） | 更正若改动好感，需同步 affection 的覆盖键语义 |
| 回放 | `webgui/bond.py::replay_attempts` / `chapter_replay` | 回放读 overlay（真源 + 暂存）——丢弃的章本就不在里面 ✅ |
| 回忆册 | `core/session/chapters.py` | 章级：丢弃的章不入册 ✅ |
| 前端去重 | `bond.js::sceneKey`/`seenRound`、`mmt.js::_lastSeq` | 替换气泡/板时的"不是新内容"判定 |

**结论**：**"丢弃"路线零消费面改动**；"更正"路线复用 revise 的既有审计，只需保证
上表里"更正后读到的视图"一致——建议**一次定齐后再实现**，别再走 `vn_abandon` 那种
"每个读路径都要记得 filter"的老路。

---

## 7. `vn_abandon` 族退休（附存量事实）

| 项 | 事实 |
|---|---|
| 真源里的 `vn_abandon` | **0 条**（3 个 `events.jsonl`：31 / 61 / 3 行） |
| 已有测试断言 | `tests/core/test_session_staging.py`：*"B0 之后 `vn_abandon` 不再产生 ⇒ `exclude_abandoned` 对新数据**空转**"* |
| `exclude_abandoned` 调用点 | **7 处**：`digest` ×1 · `momotalk` ×1 · `vn_cli` ×2 · `webgui/bond.py` ×3 ——**全在空转** |

**处置建议**：

1. **读路径退休**：删 `exclude_abandoned` 的调用点（它空转，且是"漏一处就污染"纪律的来源）；
2. **写路径**：本就不产生（B0 之后）；
3. **⚠️ `core/session/maintenance.py::heal` / `supersede` / `abandon_open_attempts`** 是**唯一
   能手工清理"真源里未闭合段"的冷工具** → 建议**降级为纯冷工具**（CLI，不进读路径纪律），
   而不是彻底删（手工改档/异常中断的兜底）；要不要连它一起删由用户裁决；
4. **顺序**：与 `EXEC_PIPELINE_UNIFY` 的**板级协议同一节点**做——它们是同一件事的两端
   （"未提交"成为一等状态之后，遮断标记才真正没有存在理由）；分开做中间会出现
   "没有作废机制"的窗口。

---

## 8. 明确不做

| 不做 | 理由 |
|---|---|
| **重发任意历史消息** | 降级为"记忆更正"（§3）：说过的就是说过 |
| **在真源里引入 supersede 标记** | 标记本身进真源 + 每个读路径都要 filter + digest 水位要处理"已消化又被作废"——这是 `vn_abandon` 的老路，`staging.py` 已经论证过它为何更差 |
| **改写 / 删除真源行** | 破坏 `seq` 地基（§2.1）与全部派生 |
| 邀约/拒绝的**实现** | 归 `docs/DESIGN_MEETUP.md`；本文只保证"拒绝 ⇒ 丢暂存 ⇒ 从未发生"这条不变量不被破坏 |
