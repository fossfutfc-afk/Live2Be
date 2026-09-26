# PROCEED.md —— 接续指南（给压缩后的我）

> 建立 2026-09-23，**取代 `core/brain/wiki_v2/DIGEST_HANDBOOK.md`（已删，别去找）**。
> 2026-09-25 **整篇重写**（链路 ①–⑤ 已落地，位置搬到 ⑥）。
> **读法**：先读这份（拿回上下文 ≤5 分钟）→ 需要细节时按 §6 的文档地图跳进去。
> **设计争论不在这里** —— 全部在 `core/brain/wiki_v2/DESIGN_GRAPH_V4.md`。

---

## 0. 一句话现状

Live2Be = Blue Archive 式叙事引擎（MMT 聊天 + Bond 视觉小说 + digest 记忆）。

**当前主线 = 记忆图 v4 落地**（`core/brain/wiki_v2/`）。用户定的链路
**① note → ② 消解无用 kind → ③ 正常 digest → ④ 时序 → ⑤ 注入时间重排 → ⑥ 优化 MMT**
里，**①–⑤ 全部落地**（每步一提交、全量 + B 冒烟），**现在站在 ⑥ 的门口**。

**最新提交**：`86c5de6`(⑤ 一条河) · `97a8ce6`(④-① per-node ts) · `f2432e0`(③-3 R3 接线) ·
`9a372f1`(③-2 R2 视野+动作面) · `2c08827`(③-1 R4 编排) · `63b6a1b`(②-2 experience 落地) ·
`ad0e038`(②-1 消解死引用) · `e04a998`(① 收尾 全景轮调用侧) · `c3a9762`(① 全景轮执行器) ·
`99d2b5b`(① 全景轮契约) · `b206b1e`(reason→afterwards) …
**工作树干净，全量 1047 passed。**

⭐ **每段 digest 现在是四步 `R1 → R4 → R2 → R3`，全部接线**（契约 / 提示词 / 编排 / 执行器 / 桩 / 用例）。
⭐ **note（随身笔记）整条链已通**：事件登记 → `notes.py` 折叠 → `soul/notes.json` 缓存 →
注入块 → 全景轮（写卡，每 10 段一次）→ R4 收口（promise 记账 + 固化）。
⭐ **契约形式已定稿**（2026-09-25）：MMT 与 VN 合成**一条流式契约**，全文落进
`docs/DESIGN_STREAM_CONTRACT.md`（旧三份设计稿已删并改指）。
⭐ **⑥-2 全部落地**（2026-09-25/26，a₀–f 七步）：共用层 = **`contract/streams/`**；
MMT 已换**行协议**（一行一条 JSON、逐行交付/落库、四阶段办理 + 三段式兜底）；
**旧 messages 路径整段删除**（−296 行）。
⭐ **⑥-3a 已落地**（2026-09-27）：引擎接 `chat_full(on_chunk=…)` + `MmtStream`，
**内容行一行前瞻即时交付 / 独占行攒块尾 / 已交付不回滚**（设计稿 §4.5）。
⭐ **⑥-3b 已落地**（2026-09-27）：前端生成期轮询 250ms + **到达即渲染**（人为打字
延迟退场），冒烟有了"首泡上屏时后端仍在跑"的硬判据。—— **⑥（优化 MMT）三步全部落地**。
⚠️ 提速暴露两个真机竞态（点击落在 staged 预热**构造中**：标题屏兜底"羁绊剧情" /
整章缺 `vn_enter` ⇒ 回忆册"0 章"），同节点修掉（PROCEED 陷阱 35）。

---

## 1. 工作约定（用户明确要求过的，别违反）

1. **动手前先说做什么；动手后报告"做了什么 / 遇到什么问题 / 下一步"**；⚠️ **一旦遇到歧义，停下讨论**。
   ⭐ 复杂节点**先把逻辑整理给用户**（他会说"你先整理一下下一步的逻辑吧，万一有什么不确定的呢"）——
   2026-09-25 那次"先整理逻辑"直接救掉一个错判（我以为改 ts 能改「（3 周前）」，实测章内只有分钟级跨度）。
2. **一节点一提交**；提交信息用 `git commit -F <文件>`（**CJK 会炸 `-m`**）；只 stage 明确路径。
3. ⭐ **改 `CLAUDE.md` 前先把它改成别的名字**（用户 2026-09-23 要求）—— 否则每次编辑都会触发整个文件
   重新注入上下文（**它的预算已经满了，每次编辑都在截掉尾部**）。改完再改回来。
4. **每个节点必跑验证**（§5 四件套）。
5. **设计稿纪律**：`DESIGN_GRAPH_V4.md` = "已达成一致的形状"。**动之前先与用户讨论**，动完在文末
   **变更记录**留一行；**未定的点写在 §9 —— 不要顺手实现**。
6. 测试**别贪多**；**遇到失败的旧用例可直接删**（若它测的是"已不可能存在的世界"）。
7. 不跑 `ruff --fix`；不提交 `config/characters/*/illustration.yml`；`tools/` 是 gitignore 的本机工具目录。
8. 用户会**自己改人设/提示词** —— 改了之后 promptkit 夹具要刷新
   （`PROMPTKIT_UPDATE_FIXTURES=1 pytest tests/core/test_promptkit_baseline.py` + **人工审 diff**）。
9. **本文件**是压缩后的第一读物；用户说"不用同步，下一次 digest 的时候你删掉重写即可" ⇒ **整篇重写**，别补丁。

---

## 2. 现在在哪 / 下一步（⑥ 的已裁方案）

**用户 2026-09-25 就 ⑥ 的第一件拍了板**：*"换真 jsonl 开流吧……MMT 的契约和 vn 其实就一样了，
只是字段不同，先不要考虑其他的，考虑能否复用以及契约形式吧"*。

| 裁决 | 内容 |
|---|---|
| **MMT 输出格式** | **换真 JSONL（一行一条）+ 开流式**（现在是 `{"messages":[…]}` + `json_object` + 整轮原子） |
| **复用方式** | ⭐ **抽取共用层**（动 VN 那条已上线的流式链），不另写一份（本仓明文：两份实现必然漂移） |
| **判别键** | MMT 的内容行**保持 `{"text": …}`**（不新增 `say` 之类）; VN 保持 `character`/`stage` |
| **交割单元** | ⭐ **一行 = 一个气泡**（屏幕 / 事件流 / 历史**三处同粒度**），行到达即可上屏 |
| **切句接口** | `_process_for_momotalk`/`_split_for_momotalk`/`split_reply_chunks` **函数与单测原样保留**，从气泡主路径摘除，**不留开关**（用户：*"不确定 LLM 能不能正确断句…这个接口未来并不完全没用"*） |
| **旧协议** | ⭐ **统统改掉**：删 `engine.py` 的 `reply`/`actions` 兼容分支 + 所有注入文本/示范/文档同步（清单见设计稿 §5） |
| **失败兜底** | ⭐ **内容行可丢；控制行永不静默丢弃** + **重试三段式**（① 引擎自愈零回灌 → ② 行级续写（**只收控制行**）→ ③ 整轮失败）；预算 = **行级 1 次 + 形状级 2 次**（现状 `MAX_STEPS=6` 全量重发） |
| **落库时机** | ⭐ **行交付即 append 事件**（前端 `events_after` 轮询天然拿增量 ⇒ **不需要 SSE**）；语义 = "话已经发出去了"（半轮产物入真源） |
| **智能矫正** | 落点 = **`core/mmt/mmt_repair.py`**（`character_id` 归一化：关系记录键 + 角色 id/显示名，**唯一命中才用**）；contract 层只做纯校验 |
| **形状单源** | `momotalk_rules.md` 的示范**兼作语言风格指导** ⇒ **拆开**：风格样本留 rules（去掉 JSON 外壳）、**完整形状只在契约块存一份** |

**落地细节全表见设计稿 §10**（A1–A7 解析层切法 · B1–B6 契约层 · C1–C4 三个注入点 · D1–D3）。

### 契约形式六条（**已写进设计稿 §1**，这里只留速查）

1. **一行一个 JSON 对象**，不包外层数组；
2. 行内**判别键**决定这是哪一类行（VN: `character`\|`stage`；MMT: `text`\|`action`）；
3. **内容行 / 控制行**二分 —— 内容行**无副作用**（可即时交付），控制行**有副作用**（过校验才执行）；
4. 坏行**丢行 + 记账**（`ParseDiag`），不抛、不毁别的行；
5. **交付与提交分离**（显示即时 / 事件在边界提交）；
6. 校验问题分**硬/软**（`Issue(code,severity)`，硬度跟 `code` 走、不看文案）。

### 下一步（三小步，每步一提交）

| 步 | 做什么 | 判据 |
|---|---|---|
| **⑥-1 抽取** ✅ | **已落地**：通用件 → `contract/streams/`（`lines.py` 行骨架 + `classify`/`known_keys`/`rescue` 注入 + `ParseDiag`/`tail_repair`；`stream.py` 增量缓冲基类 `LineStreamBase`）；`records/` 只留 VN 判别 / 转义救援 / **切板规则**（交付单元 = 板），3 个通用件改**再导出**（对外面不变） | ⭐ **纯搬家、零行为变化** ✅：全量 + B 冒烟；快照刷新（2 处真家 + 新段 5 名）+ 新守门 `test_streams_layer_stays_domain_free`（变异验证） |
| ⑥-2 MMT 契约 | 契约 / 规则书 / 示例改 JSONL + 行级解析（**先不流式**）；"整轮原子"收窄成"**action 行必须全有效才执行**、text 行可部分交付" | 桩要按 `task` 补；`test_mmt_*` 跟着改 |
| ⑥-3 流式交付 | 接 `chat_full(on_chunk=…)` + 气泡逐条上屏（`webgui/chat.py` 的 `events_after` 轮询链要动） | B 层冒烟要能测到"第一个气泡早于整轮完成" |

### ⑥-3 的两小步（2026-09-27 用户拍板"折中方案 A + 前端 250ms"）

| 步 | 做什么 | 状态 |
|---|---|---|
| **a 引擎流式交付** | `_turn_lines` 接 `chat_full(on_chunk=…)` + `MmtStream`：**内容行一行前瞻**（下一行到达时交付；见到 `inspect` 就把手里那行丢掉 ⇒ "没查到就先答"原样保住）· **独占行（`WHOLE_TURN_ACTIONS`）攒块尾**判/执行 · `_plan_line` 单行办理 + `_run_lines(check_rows=…)`（**校验面=整轮 / 执行面=剩余行**）· **已交付后的硬问题不回滚、不抛**（记账 + 下一轮注记）· 埋点 `mmt_stream_first` / `mmt_turn` | ✅ **已落地**（全量 1090 + B 冒烟 + 4 条流式守门用例；设计稿 §4.5） |
| **b 前端节奏 + 冒烟判据** | `mmt.js`：`POLL_MS` 生成期 1000→250ms · 行间人为 `chunkTypingTime` 延迟**退场**（到达即渲染，真节奏 = LLM 的节奏）· 删 `BUBBLE_GAP_MS` + `renderBubbles(stream:true)` 死代码 · 冒烟桩补 `chat_full`（逐行喂 + 行间 sleep）+ 新断言"第一个气泡早于整轮完成" | ✅ **已落地**（冒烟 3/3 PASS：首泡 t≈620-670ms 且 `running=true`，整轮 t≈1450-1550ms） |

### ⑥-2 的七小步（用户要求"**保证每一步都可调试**"，故拆细；**每步全量绿、产品在每步边界都可用**）

| 步 | 做什么 | 主要文件 | 状态 |
|---|---|---|---|
| **a₀ 共用校验原语** | `IssueSeverity`/`Issue`/`format_issues`/`split_issues` → `contract/issues.py`；每域 `declare_severity(自己的表)` 登记（未声明→KeyError 带指路；同码两种严重度→ValueError） | `contract/issues.py`（新）· `records/check.py`（再导出）· 快照 · `test_issues.py`（新） | ✅ 已落地 |
| **a 契约渲染器** | `build_line_schema(registry, *, with_examples=True)`：行文法 + 判别键 + 内容/控制二分 + 动作表（运行时生成）+ 一条交错示范 | `contract/schema.py` · `tests/core/test_line_schema.py`（新） | ✅ 已落地 |
| **b MMT 行解析** | `MmtLine` + `classify` + `MmtStream(LineStreamBase)`（**行即交付单元**）+ `to_action_raw()` | `core/mmt/mmt_lines.py`（新）· `test_mmt_lines.py`（新） | ✅ 已落地 |
| **c 校验 + 自愈** | 5 个 `mmt.*` 码 + 软硬表 · `character_id` 归一化（**唯一命中才用**）· ⚠️ **自愈必须在 `registry.parse` 之前**（inspect 的 id / send_media 的 media_type 都是 registry 硬拒绝）· ⚠️ **`chapter_title` 的必填 3-16 要自己加**（registry 只管类型、空标题放行——b 实测） | `core/mmt/mmt_check.py`、`mmt_repair.py`（新）+ 单测 | ✅ 已落地 |
| **d 引擎接线（双读）** | 行路径**旁挂**：JSONL 段走行解析 → 逐行 parse/执行 → **逐行 append 事件**；三段式兜底 + 预算（行级 1 / 形状级 2）；history 一行一条；**旧 `{"messages"}` 分支原样留着** | `core/mmt/engine.py` · `test_mmt_lines_protocol.py`（新） | ✅ 已落地 |
| **e 翻转契约** ⭐ | `engine.py:490` 换新渲染器 · `response_format` **json_object → text** · `momotalk_rules.md` **拆风格/形状** · ⚠️ **顺带修 `mmt_actions.py` 两处旧协议残句**（"附带的话写在轮级 reply 字段" · "邀约的话写 text 单元"——它们会一起注入）· 夹具刷新（人工审）· `PROMPT_INJECTION_MAP.md` | `core/mmt/engine.py` · `llm/prompts/momotalk_rules.md` · `core/mmt/mmt_actions.py` · `tests/fixtures/promptkit/*` | ✅ 已落地 ⚠️ **等真机验** |
| **f 清旧协议** | 删 `reply`/`actions` 归一分支 + 旧循环 + `_finish_turn_list`/`_record_events` + `line_protocol` 开关 + `build_schema(action_list=…)` 分支；`CLAUDE.md` §3.1 改前**先改名** | `core/mmt/engine.py` · `contract/schema.py` · `CLAUDE.md` | ✅ 已落地（−296 行） |

⚠️ **顺序是正确性**：a–d 期间真机仍走旧路径（双读）⇒ 产品不坏；**e 才是换代**；f 删的是"已无人走"的分支。

### 复用判定表（我拆过一遍的结论）

| 件 | 位置 | 复用性 |
|---|---|---|
| `ParseDiag` / `ParseResult` | `records/grammar.py` | ⭐ 通用（只是命名带 records） |
| `_tail_repair`（补 `"}`） | `records/parse.py` | ⭐ 通用 |
| 行骨架（strip→跳空行/围栏→`json.loads`→数组行拍平→坏行记账） | `records/parse.py::_parse_line_multi` | ⭐ 通用（中间只调一次记录判别） |
| 增量缓冲 `feed`/`finish`/`pop_ready` | `BlockStreamParser` | ⭐ 骨架通用；**切板规则 VN 专用** |
| `Issue(code,severity)` + `split_issues`/`format_issues` | `records/check.py` | ⭐ 机制通用（码表各自声明） |
| action 契约（`registry.parse` + `spec.py`） | `contract/registry.py` | ⭐ **MMT 已有**，吃 dict ⇒ 行解析出来直接喂 |
| `_record_from_obj`（character/stage 判别） | `records/parse.py` | ❌ VN 专用 |
| `_rescape_repair`（辅助转义） | `records/parse.py` | ❌ 靠"`text` 恒为最后字段"这条记录文法；MMT 的 `payload` 在后 ⇒ 前提不成立 |
| `check_block`/`check_board` | `records/check.py` | ❌ VN 专用 |

### ⏳ ⑥ 里还开着、用户没圈的（别顺手做）

- **读路径召回 + `mmt_recall{scope}`**（设计稿 §11 的正题）——⭐ 它同时是 **`retire` 的许可证**
  （R4 现在**只发 `close` 不发 `retire`**，就是在等这条读路径接通）。连带 §9-11（recall 返回什么形状）
  与 §9-14（`self` 要不要无条件进命中集）。
- **note 的"顺手记一笔"**（主 LLM 当场 add 约定，配合 R4 兜底）。

---

## 3. 未决账（**动手前必须问用户**）

**A. §9-12 的 ①-⑧**（⑦ 已结案；其余仍待裁）：① `evidence` 删 · ② `affection_delta` 收窄输入 ·
③ R2 加 `detach` · ④ R3 加 `merge_entity` · ⑤ ⭐ **R3 也看"本轮被改写的旧节点"**
（**这是 ③-3 留下的唯一残留洞**：R3 只看本轮新节点 ⇒ 被 R2 改写的旧节点这一轮归属不了、且**不会再回来**）·
⑥ 复查队列不做 · ⑧ **D4：把 belief 的产出从 R2 搬到 R1**（§8 的 R2"禁止"栏写着"R2 不建节点"，
现状不符；搬到 R1 后 `about_hint` 才齐、`links` 的两端限制也自然消失）。

**B. §9 其余未定**（读原文再答，别凭记忆）：1 常驻层的界 · 4 `state` 清理 · 5 place 归位 ·
6 `about_state`/复查队列 · 7 玩家改名回填 · 8 用户档案/用户提示词（**已裁"暂时先不做"**）·
11 `recall` 返回形态 · 14 `self` 无条件进命中集 · 15 R4 是否独立调用 · 16 第三方承诺的 `from`/`to` ·
18 **`retire` 的开关**（等读路径召回）。

**C. 待清的死件**（我查出来的，都很小，但都是"看起来生效"的假旋钮）：
`core/worldtime/age.py::render_relative(age, significance)` 的 **`significance` 从未被使用**；
`age.is_precious` + `_SIG_PRECIOUS` **零消费者**；`graph.REL_UNKNOWN` 之外的旧 `entry`……

⭐ **`experiments/engine_smoke.py` 整篇烂了**（2026-09-25 实测 **0 PASS / 8 FAIL**）：它是对着
**2026-09-02 之前**的 `{reply, actions}` 旧协议写的，之后没人维护 ⇒ 要么重写、要么删
（它不在全量套件里，所以一直没人发现）。⚠️ 别拿它的断言当现状依据（⑥-2d 差点被它误导）。

⭐ **AUDIT §B9**（`mmt_inspect_character` 读到的资料被丢弃）：**行协议里已接上**（⑥-2d，
`_run_lines` 执行 inspect → `feedback` 资料 → 继续这一轮）；旧路径**按用户口径不动**，
随 ⑥-2e/f 一起退役。

**D. 文档引用纠正**：设计稿 §12.1 说 BaiShou"注入时按日期排序拼成一整段共同回忆" —— 查过它的
README 与 v3.0.0 更新日志，**都没写注入顺序**（它是"工具派"：摘要走 `summary_read` 工具 + RAG 检索）。
那句**来源存疑，别当依据**（已在 §12.1 标掉）。

---

## 4. 陷阱清单（踩过的 + 设计写死的）

1. **新事件类型不登记进 `EVENT_TYPES` = 静默丢失**（`Event.from_dict` 对白名单外的 type 返回 `None`）。
2. **"非剧情事件"的判据只有一处** = `core/session/events.py::is_content_event`（静态守门在
   `test_note_events.py::test_content_filter_is_not_reimplemented_elsewhere`）。
3. **契约层改字段要三处同改**：取值清单 + 硬规则 + **示例**。⚠️ **示例才是形状的来源**。
4. **给 LLM 的示例全仓只能有一种形状**；JSON 换行只放成员之间（字符串里折行 = 示范本身非法）。
5. **note 的提交顺序 = 先真源（`note/*` 事件 append）后缓存（`notes.json`）**；反过来会出现
   "本子上有、事件流没有"（没人能重建它）。唯一实现 = `mmt.engine._write_note_ops`。
6. ⭐ **R4 的 note 操作不在 `digest_segment` 里 append** —— 它拿不到 `SessionStore`；挂在
   `DigestResult.notes_ops` 上，**调用方在整批 `ok` 之后**才写（`_rollback` 会清空它）。
7. ⭐ **全景轮的计数器不清零**（没跑成 / 没料 ⇒ 下一段再试）；**第一次直接到点**（`wiki.meta.json`
   里还没有那个键 = 从没写过卡）；**写卡后要重读事件流**（注入块才看得到新卡）。
8. **`experience` = 玩家画像专用**（写者只有 R1；R2 的 `add kind=experience` **被拒**）；
   读侧**按 kind 收、不看 `subject`**（旧口径拿自由文本路由 ⇒ 真机 haruka `e0001` 静默不可见）。
9. ⭐ **两个 id 空间不许混**：R2 的 `target_ids`（可 touch/update，**只有看法**）vs `link_ids`
   （可 `links` 两端，**含承诺**）；R3 的 `c0001`（对象）vs `u0001`（节点）。
   混用会让模型把"挂谁"与"挂在谁身上"写反，而那种错**看起来完全正常**。
10. **每段四步的批内顺序 `R1 → R4 → R2 → R3` 是正确性**：R4 物化的 promise 节点要先就位，
    R2/R3 才有边可写（否则它"永远没边、永远没归属"）。
11. **第 1 轮节点的 `ts` = 它自己 `event_seq` 里最后一条事件的时刻**；第 2/4 轮仍是段 ts
    （"什么时候想明白的 = 消化那一刻"）。`event_seq` 空/指不到 ⇒ 回落段 ts。
12. **注入视图是"一条河"，从早到晚**（旧→新）：「难忘」只是行内标记 `（3 天前·难忘）`；
    无 `ts` 的排河首；belief / 玩家画像 / reported **不进河**（当前值与旁证各自成块）。
13. **`about_hint` 必须显式摘掉**再进 `make_node`（否则被 `from_dict` 静默忽略）。
14. **Round B 有"覆盖全部 episode"的结构检查** ⇒ 桩里 `decisions: []` 而 episode 非空 ⇒ 反馈重试、
    把桩耗尽。给每个 episode 一条决策。
15. **桩必须按 `task` 分派**（`llm/task_labels.py`）；**新任务要补四处**：`tests/stub_tasks.py` ·
    `tests/core/test_wiki_digest.py::FakeLLM` · `tests/core/test_round_*.py` 的桩 ·
    `experiments/web_e2e/stub_world.py`。`tests/core/test_stub_dispatch_guard.py` 会扫源码守门。
16. **`llm_call.llm_chat` 有 feedback 语义**：被拒 → 追加 assistant 位 + 引擎错误，同上下文重试 1 次。
17. **水位是单一整数 `digested_seq`**；任一轮失败 ⇒ **整体回滚**（含 R4 的判定与 R3 的新 entity）。
18. **`_find_duplicate`** = (同 kind, `event_seq` 有交集, 主文本相同) → 复用 id（崩溃窗口幂等）。
19. **改 digest prompt 必跑** `test_wiki_digest.py` + `test_digest_registry.py`；
    **digest 的 prompt 不在 promptkit 盒里 ⇒ 没有夹具**。
20. **`hit_set` 扫正文的称呼要求 ≥2 字**；hint 走精确相等不受此限。候选表与载荷区**必须共用同一份
    `local_of`**。
21. **`config/player/profile.yml` 坏了 → 本轮 digest 直接中止**（**不兜底**，用户裁决）。
22. ⭐ **空表时 `next_id("x")` 返回 `x0001`** = sensei 的保留号 ⇒ `ensure_entities` 必须在任何
    "自动建 entity"**之前**跑（现接在 `_inject_brain(digest=True)` 最前面）。
23. ⭐ **真机存档里 `entity` 现在还是 0 条** —— 下一次 digest 才会建 `x0000`/`x0001`
    （R3 的候选表到那时才是 `c0001 伊草 遥香（…遥香…）` + `c0002 老师（sensei）`）。
24. ⭐ **别拿"真机数据频率"论证价值**（用户原话：*"真机数据我都是完全顺着 AI"*）—— 没压过的地方就是 0。
25. ⭐ **不要把图当列表用**：`about`/`supports` 有数据但消费者极少 ⇒ 没有 traverse 者时图 ≈ 带 id 的列表。
26. **`emo_shape` 是逐记录的情绪数组**（真机最长 129 键），空键跳过、不补位。
27. ⚠️ **编辑坑（我自己踩了三次）**：用 `.Replace()` 时若把行尾换行也吃掉，`def` 会与 docstring
    挤成一行（`IndentationError` 立刻红）；**优先用 edit 工具而不是脚本替换**。
28. ⚠️ **测试里的 id 顺序别赌**：预置节点会占号（`_store` 先建 `x0000/x0001`、
    `make_node("belief")` 也吃 `m` 前缀）⇒ 断言按**文本**查 id，别写死 `m0001`。
29. ⚠️ **搬家时"诊断文案"也是行为**：`ParseDiag.error` 的中文串被用例逐字钉住
    （⑥-1 我把"数组行内无合法记录"改成"…行对象"→ 当场面红）⇒ 通用层照抄 VN 原文案，
    **不为措辞漂亮去动它**。
30. ⚠️ **`tests/fixtures/api_surface.txt` 第四列 = "真家"**：搬件后必须
    `SPLIT_API_UPDATE=1 pytest tests/core/test_split_safety.py` 刷新 + **人工审 diff**
    （刷新快照 ≠ 行为变化，提交信息要写明）。`contract.streams` 已进 `TARGETS` 与 `SPLIT_PKGS`。
31. ⭐ **通用层不许认识域**：`contract/streams/` 只 import stdlib 与自身——判别 / 已知字段 /
    救援**全部靠注入**；守门 `test_import_direction.py::test_streams_layer_stays_domain_free`
    （已变异验证：塞一条 `from contract.records import …` 立刻红）。
32. ⚠️ **桩的 `chat_full` 必须喂"它返回的那段文本"**（⑥-3a 实测）：`on_chunk(json.dumps(resp))`
    在 `resp` 已是 str 时 = **双重编码** ⇒ 行协议一行都解析不出来，一路跑到 `MAX_STEPS`
    才报"单轮超过 6 步仍未产出可见回复"（三个 promptkit 基线用例当场红）。真客户端的
    `on_chunk` 就是内容增量 ⇒ 桩照它写。
33. ⭐ **流式下"校验面"与"执行面"不是一个东西**（⑥-3a）：块尾只剩独占行没办，但
    **组合校验必须看整轮**（独占性是"同一轮还有没有别的行"）⇒ `_run_lines(check_rows=…)`。
    另：`inspect` 单独一轮**本来就不产出可见内容**，"没有可交付的行"那条 fatal 必须把
    `need_more` 排除在外（否则静默轮被当成失败）。
34. ⭐ **已交付 ⇒ 只记账，不抛 `MmtLoopError`**（用户裁决"折中方案 A"）：玩家已经看见气泡时
    把整轮标成失败，前端会把**玩家的**消息画成感叹号（"发送失败"），而角色明明回了话。
35. ⭐ **"点得早"会踩到预热构造中**（⑥-3b 提速暴露，`bond_start` 的"并发 init skip"分支）：
    玩家点粉泡时 worker 的 **staged 预热可能正在构造**（`state.vn` 刚被建出来）⇒ 走那条
    提前返回的分支，它漏了两件 adopt 该做的事——
    ① 漏 `chapter_title`（标题屏兜底"羁绊剧情"）；
    ② **不落 `vn_enter`**（staged 预热故意不落，等点击 adopt 补）⇒ **整章没有 enter**，
       `chapter_index` 认不出 ⇒ 回忆册"已结束的故事 **0 章**"（真机事件流实测
       `vn_exit`=1 / `vn_enter`=0）。
    ⇒ 任何"预热后的提前返回分支"都要问一句：**玩家已经点了吗？adopt 的记账做了吗？**
36. ⭐ **冒烟断言要判"谎"，不要判"出现"**（⑥-3b）：轮询提速后，"对方正在输入…"会在
    **这一轮真在跑**时短暂出现（诚实状态）——旧断言"3.5s 内出现过就失败"会误报。
    正确判据 = "**后端说 `running=false` 却还在跳 >0.8s**"（直读 `/api/mmt/events`）。
    同一条纪律：断言超时时要**留证真身**（回忆册那次补了"列表原文"⇒ 一次就分清
    "加载中 / 空的 / 读不到"）。

---

## 5. 验证配方 + 真机基准

```powershell
# 单测（快，改 wiki 层时先跑这个）
python -m pytest tests/core/test_wiki_digest.py tests/core/test_digest_registry.py tests/core/test_round_close.py tests/core/test_round_attr.py tests/core/test_wiki_render.py tests/core/test_wiki_revise.py -q --basetemp=.testtmp/pw_graph

# 全量（每节点必跑；⚠️ .testtmp/pw 目录要先建）
python -m pytest tests/core tests/webgui tests/llm tests/renderer -q --basetemp=.testtmp/pw
python -m compileall -q core contract webgui apps llm tests main.py
node --check webgui/static/js/bond.js
python experiments/web_e2e/run.py          # B 层冒烟（Playwright，本机已装浏览器）
```

**真机基准**（2026-09-25 量，`data/worlds/world1`）：

| 角色 | 节点 | 边 | meta | notes | 事件 |
|---|---|---|---|---|---|
| `igusa_haruka` | **14**（11 episode + 3 belief，含迁移过来的 `e0001`） | 11（全 `supports`） | `digested_seq=206` | 无 | 207 |
| `asagi_mutsuki` | 5（2 episode + 1 experience + 2 belief） | 0（**没有 `edges.jsonl`**，探针要容错） | `digested_seq=60` | 无 | 61 |
| `onikata_kayoko` | 0 | 0 | `{}` | 无 | 3 |

⚠️ **两边都还没有 `notes.json`、没有任何 `entity`、没有 `source` 之外的边** ⇒ 全量 1047 是**唯一**的回归面；
真机验证要等下一次真实互动（R4 的第一次 `add`、R3 的第一次 `attach`）。

**只读探针**（我写的，改路径即用）：`.testtmp/baseline_probe.py`（节点/边/meta/notes 计数）·
`.testtmp/view_now.py`（渲染真机注入视图，带 `now`）· `.testtmp/r3_dryrun.py` / `r3_table_preview.py`
（R3 的料）· `.testtmp/ts_scan.py` / `ts_spread.py`（各批的 ts 跨度）。

---

## 6. 文档地图（+ 外部材料）

| 文档 | 管什么 |
|---|---|
| **本文件 `PROCEED.md`** | 压缩后的第一读物：现状 / 约定 / 未决 / 陷阱 / 配方 |
| ⭐ `docs/DESIGN_STREAM_CONTRACT.md`（2026-09-25 新建） | **流式契约形式（MMT + VN 统一）**：§1 六条 · §2 两域对照 · §3 内容/控制二分 · **§4 兜底分级 + 重试三段式** · §5 MMT 旧协议退役清单 · §6 切句接口处置 · §7 复用判定表 · §8 ⑥ 三小步；**附录 A = VN 记录流 v2 全文（原 `DESIGN_VN_UPGRADE.md`，章节号原样保留 ⇒ 文中的 §N 都指附录 A）**。⚠️ **本文取代并删除了 `DESIGN_VN_UPGRADE.md` / `DESIGN_MMT_CHAT.md` / `DESIGN_CONTRACT.md`**（28 处引用已改指） |
| `core/brain/wiki_v2/DESIGN_GRAPH_V4.md`（~95 KB） | **设计稿**：§1.1 三种组织形式 · §2 边与**走法**（**7 条**，`source` 已删） · §3 entity/**note**/inventory · §3/§5.1 **`experience` = 玩家画像** · §4 注入两档 · §5 **fact 已退役** · §6 **promise 两段式** · §7 时间（**per-node ts**）· §8 **每段四步 + R2 视野与动作面 + R3 归属** · **§8.6 全景轮（写卡）** · §9 未定 · §11 `function_call` 与动作面 · §12 外部参照（§12.1 BaiShou，⚠️ 其中"按日期排序"一句已标存疑） |
| `CLAUDE.md`（仓根，⚠️ **改前先改名**；预算已满） | 项目主文档；§7 记忆与好感 · §12 测试/路径/提交纪律 |
| `docs/PROMPT_INJECTION_MAP.md` | 现网注入事实（改盒/加注记前看） |
| `docs/AI_BRIEF_PLACE.md` | 改地点代码前先扫它 |
| `docs/DESIGN_MEMORIAL.md` | 纪念链路（A–D 已落地） |
| `.testtmp/research/` | 09-23 的外部调研材料（AgentGal / BaiShou 源码）—— **gitignore，可能被清** |
