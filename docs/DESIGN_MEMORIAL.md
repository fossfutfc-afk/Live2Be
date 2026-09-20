# DESIGN_MEMORIAL — 纪念链路（art / memorial / 黑屏缓冲 / 记录级进入）

> **状态（2026-09-20）**：**设计稿定稿，代码未动**。本文分两半——
> **§1 现状**是逐行核对代码得出的**事实**（不是设计意图，读它别读旧文档）；
> **§2 起是定稿语义与改动清单**（用户已裁决，待实施）。
>
> **为什么单独开这一页**：纪念这条链在文档里被 v1 描述污染得很重（`memorial_exit`
> 动作早已退役，但 CLAUDE.md §3.2、`chapters.py:112` 那句表格、`scene.memorial_exit`
> 的 6 处活分支都还留着"看起来有 exit"的样子）——不先钉住现状，改动一定跑偏。
>
> **相关**：`docs/DESIGN_VN_UPGRADE.md` 决策 #39/#40（纪念链路接通 + 两个真源缺口）、
> `docs/DESIGN_COLLECTION_BOOK.md`（回放侧怎么读纪念态）、`docs/DESIGN_PLACE.md`（背景系统）。

---

## 1. 现状（逐行核对代码；2026-09-20）

### 1.1 三个单位：块 / 板 / 记录

| 单位 | 定义 | 代码位置 | 真机实测 |
|---|---|---|---|
| **记录** | 一行 JSON（`character` / `stage`） | `contract/records.py` | — |
| **板** | 块内按 `switch` / 老师群切的**显示单位**（推进、选项、标注、回放都按它） | `_board_spans` → `BondScene.from_board` | 5 板（seq 14/16/18/20/23） |
| **块** | **一次 LLM 调用的全部输出**（`check_block` 校验单位、`_in_memorial` 复位单位） | `bond_story.py:786` / `:734-747` | **整章 = 1 块** |

> **"块 = 整章"的证据**：5 块板里**只有 seq 14 的首条是 `switch`**（"本章第一条必须是
> switch"），16/18/20/23 的首条都不是 ⇒ 它们同属一块。另有出图 marker 在
> seq 12、早于 `vn_enter` seq 13 ⇒ 出图那次就是入口预热那次调用，**它同时产出了
> 首板（14）和纪念板（23）**。
>
> **为什么必须记住这个**：一块可能 = 整章，所以"按块定位"等于"按章定位"，
> 而玩家感知的"一轮"= **一板**。

### 1.2 声明面：两个字段

| 字段 | 契约要求 | 可见性 | 现状消费方 |
|---|---|---|---|
| `{"stage":"art","text":"画面意向"}` | **必须块首**（`records.py:56` `STAGE_BLOCK_HEAD`，落在第 3 条及以后即 issue，`:335-336`）；同块至多 1 条（`:350-352`） | **不可见**（不进 `paragraphs`、不切板、不上屏；`records.py:554`、`:684`） | **只有生图 prompt**（缺省退化） |
| `{"stage":"memorial","text":"触发句"}` | 块内**偏后位置**；**同块至多 1 条**（`records.py:342-344`）；其后的 `switch`/`art` 被禁（`:346-348` `STAGE_FORBIDDEN_IN_MEMORIAL`） | **照常上屏**（当旁白） | ① 生图触发 ② `_in_memorial` 置位 ③ `memorial_enter` marker |

**⚠️ 没有守卫的一条**：写了 `art` 但没有 `memorial` ⇒ 只打一行 WARNING
（`bond_story.py:955-956`「声明了 art 但本回合没有 memorial（降级: 不发图）」），
**不报错、不打回**。

### 1.3 进入（现状 = **板级**）

1. **开画**：流式解析到 `memorial` 记录**那一刻** → `_feed` → `_fire_memorial_image`
   （`bond_story.py:698-703`）；非流式在整块解析后补触发（`:803-811`）。
   prompt = 块级 `art` → **缺省用 memorial 记录自己的 text**（`_memorial_image_prompt`，`:822-842`）。
2. **置位**（两处，板级）：
   - 引擎 `_finish_scene`：`if scene.memorial: self._in_memorial = True`（`:1007-1013`）；
   - webgui `_scene_landed`：`if scene.memorial: state.vn._in_memorial = True`（`bond.py:2095-2099`）
     ——给**预热缓存 / 草稿旁路 / 回放**这些绕过引擎的落地路径补一道。
3. **marker**：板落地时 `_log_scene_meta` 写 `memorial_enter`（`v2: true`）+ 紧接 `vn_state`
   （`bond.py:2653-2678`）。
4. **前端**：板载荷 `in_memorial=true` → `syncMemorial`（`bond.js:461-489`）：
   隐藏 `#bond-stage`（立绘整层）+ **清空 `#bond-bg`**（注释原文"黑屏兜底"）+
   图就绪静默淡入，**无加载 UI**。调用点：板渲染后（`:421`）、轮询每 tick（`:389`）、
   只读回放（`:317`）。

**⇒ 后果**：`memorial` 在板**中部**时，它**前面那几条记录也在黑屏上播**
（真机：seq 23 的 `records[0..3]` 四句正常对话是在黑屏上说的）。
规则书 §六 让 writer 把触发记录放"偏后位置"，**这个暗示在实现里落空了**。

### 1.4 退出（**没有退出动作，也没有退出记录**）

- 引擎复位：`_in_memorial = False`，时机 = **新一块解析成功**
  （`bond_story.py:799`；不是循环开头——预生成/重试失败不是窗口结束，决策 #40 ③）。
- marker：`_close_memorial_window` 补写 `memorial_exit`（payload `{"v2":true,"auto":true}`，
  `bond.py:2618-2650`），两条路径：
  1. 下一板落地时（`_log_scene_meta` 的 else 分支，守卫 `vn.in_memorial` 为假才算时机）；
  2. `bond_finish` 用 `force=True` 强闭合（`:1775`；玩家在纪念板读完就收尾时路径 1 永不发生，审计 B5）。
- 前端：`in_memorial=false` → 纪念层淡出 + 按**当前板**的 `background_url` 还回背景（`bond.js:474-489`）。
- **v1 的 `memorial_exit` 独占动作已于 2026-09-13 退役**（审计 B1）：`_scene_task_kind()`
  恒返回 `scene`（`bond_story.py:1344-1365`），`task_bond_memorial_exit.md` 已删，
  `vn_cli.py:261-270` 的 exit schema 注入被 `not vn._last_payload` 门住（只 v1 路径）。
  `core/bond/memorial_actions.py` 与 `stream_probe.py` 留档、主链不调用。

### 1.5 连带机制

| 机制 | 现状 | 位置 |
|---|---|---|
| **不标注** | 含 memorial 的**整板**跳过 emo/place lane（理由：立绘全隐藏、标了没人看，省 1~2 次调用 + 免门控白等） | `_memorial_no_visuals`，`bond.py:1285-1300`（决策 #39 ③） |
| **章内 ≤1** | `_memorial_used` + `_demote_repeat_memorial`：跨块第二次静默降级为普通旁白（不置位/不生图/不写 marker/不给模型反馈，只打 INFO） | `bond_story.py:856-884`（2026-09-20 补） |
| **回放板级态** | 窗口 = `memorial_enter`…其后第一条 `memorial_exit`/`vn_exit`/`session_end`；触发板 = 离 marker 最近且**带纪念标记**的板；窗口内每板带 `in_memorial: true`，触发板另带 `memorial_img` | `chapters.py::_memorial_boards:100-179` |
| **章级回落** | 图挂不上板（**预热先出图**，前面没有 `memorial_enter`）→ 挂到"带 `memorial`/`memorial_prompt` 的板" | `_attach_memorial:232-277` |
| **章末** | `end` 板 → `completed=True` → `vn_exit{completed}` → **digest 唯一触发点** | `bond.py:2101-2102`、`:2848-2850` |

### 1.6 真机样本（haruka 那一章，用作回归基准）

```
12 marker memorial_image  （预热出图：url=...b34d，prompt = memorial 的触发句原文）
13 marker vn_enter        {"chapter_title":"杂草屋的环境调研"}
14 bond   story_scene     首板（首条 = switch「杂草屋门口」）
15 marker vn_state
16/18/20 bond ×3
21 marker memorial_enter  {"v2":true}
22 marker vn_state
23 bond   story_end       ← 纪念板（records 10 条，memorial 在第 5 条、end 在第 10 条）
24 marker memorial_exit   {"v2":true,"auto":true}   ← bond_finish 强闭合写的
25 marker vn_exit         {"completed":true}
26 marker session_end
31 digest
```

- **5 块 bond 事件里 `art_hint` 一个都没有** ⇒ 生图 prompt 走的是**降级路径**（用 memorial 的 text）。
  那张图的 prompt 是「（她抬起头，眼眶有点红，却第一次把笔记稳稳递到您手里。）」——
  一句带全角括号的**舞台指示**。
- gallery 两张：`...b34d`（被 seq 12 引用）；`...0696`（14:21，**全仓 0 引用 = 孤儿**——
  上一轮尝试被丢弃，marker 随暂存一起没了，png 留在盘上；`GalleryStore` 没有任何删除/回收）。

---

## 2. 定稿语义（2026-09-20 用户裁决）

### 2.1 一句话

> **`art` 说画面（给画师看，不上屏）；`memorial` 的那句 text 说转场（给玩家看，落在黑屏上）。
> 黑屏从 `memorial` 那一句开始。**

### 2.2 逐条

| # | 条目 | 内容 |
|---|---|---|
| M1 | **`art` 不退役** | 职责收窄为两条：**画面意向**（生图 prompt）+ **提前开画**。与 `memorial` **同轮配对、缺一不可** |
| M2 | **`memorial` 不退役** | 那句 text 的价值 = ① **上屏的转场句** ② **黑屏缓冲期里唯一的内容**。位置仍在块内偏后 |
| M3 | **进入 = 记录级** | 黑屏从 `memorial` **那一句**开始（不是板首）。⇒ 那句之前的记录在**正常视觉**下播 |
| M4 | **退出 = 块边界**（不变） | 新一块解析成功即复位；章末由 `bond_finish` 强闭合 |
| M5 | **章内 ≤1**（不变） | 跨块第二次静默降级 |
| M6 | **纪念轮默认不写 `end`** | **软建议**（写进规则书，不进契约校验）：收尾默认留到下一轮——*"除非你真的认为这样很有意境"* |
| M7 | **不做"补写"** | 漏写 `art` 时**不**补调用。先改文案，用埋点**量配对命中率**，不够再议。⚠️ 原来唯一那条"art 无 memorial"WARNING 在 `_build_record_boards` 里，而**流式路径根本不走那个函数** ⇒ 生产主链上是死的；命中率改由 `check_block` 的**软问题**统计（见 A11） |
| M8 | 图未就绪 | 保持现状：进纪念即黑屏 + 文字，图就绪静默淡入，**无加载 UI** |

### 2.3 `memorial.text` 的写作要求（进规则书 §六，常驻）

1. **承上**：紧接正常视觉的最后一句出现，必须接住那个场景/动作，不能跳。
2. **定格**：它把这一刻停住——也就是 `art` 所描述的那一刻。
3. **启下**：它之后的记录都在"黑屏 → 图"上，要能自然引到那些话。
4. **扛等待**：图理论上 ~26s 才到；这句 + 其后的**纪念正文（3~6 条）**一起覆盖黑屏。
5. **不写空镜**（画面里必须有人）、**不写镜头与画风**（那是 `art` 的活）。

### 2.4 被否掉的方案（别再实现一遍）

| 方案 | 否掉的理由 |
|---|---|
| `art` 即开关（art 一出现就进纪念） | `art` 是块首，一块可能 = 整章 ⇒ **整章都在黑屏**，画面与剧情脱节 5 板 |
| 进入点 = `art` 所在**板尾** | 与 M3 冲突：`memorial` 那句（同块偏后）会在**正常视觉**下先播完，黑屏里就没有它了 |
| `memorial` 退役、只留 `art` | 丢掉那句上屏的转场句（也是"要转场"这个创作裁决本身） |
| 两者都退役 | 进入信号只能靠引擎识别文本/标注层 ⇒ 多一次调用 + 误判；且"哪一刻值得纪念"是创作裁决 |
| 漏写时**补写**小板块 | 用户裁决"现在不做"；且补出来的板必须排在 `end` 板**之前**（`end` 一落地 `completed=True`、前端即停轮询并 finish，补的板播不出来）——工程代价不小，先量再议 |

---

## 3. 改动清单（分层 / 按提交节点）

> 纪律：**每节点一提交，文档与代码同批**；人设/规则文案改动与夹具同批。

### 节点 A — 契约与规则文案（零引擎改动）　✅ **已落地 2026-09-20**

| # | 改动 | 位置 |
|---|---|---|
| A1 | 注入给 LLM 的 stage 取值清单里**摘掉 `exit`**（v1 动作已退役；解析常量 `STAGE_VALUES` **保留**，旧档回放要认） | `contract/schema.py:157` `stage_shapes` |
| A2 | `art` 的说明改成"**给画师**的画面意向（本轮最前一条）——**必须与 memorial 同轮成对出现**"；`memorial` 的说明改成"**这句会显示给玩家看**" | `schema.py` stage 取值段 |
| A3 | **统一 art / switch 的先后**——现在四处在说三种话（硬规则 4 说"首条必须 switch，art 紧跟其后成为本轮首条"；rules `:64` 说 art 是"本轮第一条"；范本是 `art → switch`；实现两种都放行）。按范本定：**art 是本轮第一条** | `schema.py:253` + `bond_story_rules.md:64` |
| A4 | 硬规则 5 保持**结构句**（`memorial` 之后到本轮结束为纪念正文）；**"本轮默认不收尾"不进硬规则**——它没有校验，放进"违反即被丢弃"就是假威胁 ⇒ 只进 §六 软建议 | `schema.py` 硬规则 5 |
| A5 | **示例改成配对形状**：`art → switch → 铺垫 → memorial → 纪念正文`（示例是"形状"的来源，`:257-266` 现在教的是**光杆 memorial**） | `schema.py:188-201` |
| A6 | §六 整段重写：分工（art 给画师 / memorial.text 给玩家）+ 配对必做 + §2.3 五条写法 + 位置 + **纪念区间内不换场**（契约已有 `STAGE_FORBIDDEN_IN_MEMORIAL`，规则书漏写） | `bond_story_rules.md:57-72` |
| A7 | **删** `:72`「没声明也可以纪念」（唯一的"可省略"许可来源） | `bond_story_rules.md:72` |
| A8 | §六 补 M6 软建议（原始措辞：*"建议不直接在 memo 结束，除非你真的认为这很有意境"*） | `bond_story_rules.md` §六 + `bond_shots.md`（收法 ④ 同步标注为"例外，不是默认"） |
| A9 | 范本加长：纪念正文从 **1 条**补到 **4 条**，并点明"纪念那一轮 / 收尾那一轮"是**两轮** | `bond_shots.md` 范本 |
| A10 | 夹具重生成 + 断言守配对：`test_build_record_schema_covers_all_values` 断言三处都说到配对、且 `exit` **不在**注入文本里 | `tests/fixtures/promptkit/*.txt`、`tests/core/test_records.py` |
| A11 | **`check_block` 新增两条软问题**（只记录/打日志，**绝不打回**）：① 有 memorial 却没 art（配对缺失）② memorial 与 end 同轮。同时在 `check_block` docstring 写明**软硬由标记串判**、加新问题串时不能撞 `HARD_BLOCK_ISSUE_MARKS`；`split_board_issues` 的日志措辞从"已切群处理"改成"不阻断"（它现在不只管群长） | `contract/records.py::check_block`、`core/bond/bond_story.py` |

### 节点 B — 记录级进入　✅ **已落地 2026-09-20**

| # | 改动 | 位置 |
|---|---|---|
| B1 | 板载荷加 **`memorial_at`**（= `memorial` 记录在 `paragraphs` 里的索引）——现在 `paragraphs` 里那句与普通旁白**长得一模一样**（没有 stage 标记），前端认不出来 | `BondScene.to_dict` / `from_board` |
| B2 | 前端 live：`syncMemorial` 改成在渲染到 `memorial_at` 那一段时切（现在 `:421` 是板渲染时就切） | `bond.js:461-489` + `:421` |
| B3 | 前端只读回放：同样按 `memorial_at` 切（现在 `:317` 板渲染即切） | `bond.js:317` |
| B4 | `_memorial_no_visuals` 改**段级**：含 memorial 那一板**只对 memorial 之后的记录**跳过标注——否则前半段（立绘正常显示）**没有表情数据、表情恒默认**（新设计引入的静默退化） | `bond.py:1285-1300`、`_want_emo/_want_place` `:2446-2475` |
| B5 | 用例：`memorial_at` 透传（引擎 + 回放）、段级标注门控；冒烟 `experiments/web_e2e/smoke.mjs` 的纪念步骤按新切换点改 | `tests/core/test_vn_records_engine.py`、`test_chapters.py`、`experiments/web_e2e/smoke.mjs` |
| B6 | 文档句更正：`chapters.py:112` 写着"触发板 = 该 marker 之前**最后一条 bond 事件**（`_log_scene` 先写板、`_log_scene_meta` 紧跟着写 marker）"——**与实现不符**（`_trigger_board` 实际认"离 marker 最近且带纪念标记的板"，真机正是 marker(21) 在前、板(23) 在后）。**代码对、文档错** | `chapters.py:112` |

**落地形态与验证**（比原计划多做了两处）：

* `memorial_at` 由 `BondScene.from_board` 算出（触发记录在 `paragraphs` 里的下标），
  经 `to_dict` 进事件流 ⇒ **回放自动拿到**（不用另存字段）；触发记录**没带 text**（空串）
  → 退回 `0`（整板即窗口，老行为）。
* **前端不是"板渲染时切"，而是把它做成"每段上屏时判一次"**：`bond.js` 里
  `syncMemorial` 只**缓存**状态（`memorialSt`），真正的判定在 `applyMemorial()` ——
  `memorialNow() = in_memorial && (at === null || typeSeg >= at)`，由 `writePara()`
  每段调用（外加轮询兜底）。这样黑屏**精确落在那一句上**。
* 冒烟新增**两半断言**（缺一即退化成板级）：逐段取样（`capturePara` 记每段的
  `memorial`/`stageHidden`）→ 「触发记录**之前**那几条是正常视觉」**且**
  「触发记录那一段进了纪念视觉」。实测输出:
  `首段="（她抬起头，指尖还沾着粉笔灰…" 立绘隐藏=false 背景清空=false 纪念层=false`
  → `段="（她抬起头，第一次直视我的眼…" 图=已淡入 立绘隐藏=true 普通背景清空=true`。
* `test_memorial_board_skips_annotation_lane` 按新语义重写（三条判据：进入点在板中 →
  **照常标注**；在板首/旧档无字段 → 跳过；窗口从上板延续 → 跳过）——原来那条
  "整板跳过"的断言正是 M3 要推翻的。

### 节点 C — 可归因埋点（量 M1 的配对命中率）　✅ **已落地 2026-09-20**

| # | 改动 |
|---|---|
| C1 | gallery json 补字段（**都可缺省, 老 json 形状不变**）：**`prompt_source`** = `art` / `memorial_text`（降级）、`refs`（喂了哪些参考图）、`model`、`elapsed_ms`。来源: 引擎在 `_fire_memorial_image` 里把"这张图的 prompt 是画面意向还是触发句"记到 `engine.memorial_prompt_source`，`_memorial_gen` 同步读走交给 `GalleryStore.write` |
| C2 | **统计口径**（三个口径互为印证）：<br>① **art 配对命中率** = gallery json 里 `prompt_source == "art"` 的比例（最权威——它记的是**真出图的那一次**）<br>② 契约软问题计数: `grep "含 memorial 但没有 art"`（`check_block` 的软问题, **流式路径也有**）<br>③ WARNING `grep "声明了 art 但本回合没有 memorial"` —— ⚠️ 这条**只覆盖批式路径**（在 `_build_record_boards` 里, 流式不走那个函数）, 别单独拿它下结论 |

### 节点 D — 图像质量（前几轮已定，与纪念链路解耦）

| # | 改动 |
|---|---|
| D1 | **性格简卡进 `character_hint`**（用户裁决：*"简卡放在 character_hint 吧，神态参考图不必了"*）。料 = `personality.yml:1` 的 `SIG~brief_traits`（"高度自卑，认为自己一无是处…"）。**同批改 `illustration.yml` 那句注释**「写形状, **不写性格**」——不改的话下一个人会照注释清掉它 |
| D2 | `llm/image_gen.py` 的 `_APIYI_TAIL` 补**构图/镜头 + 光线**（指南点名的两个缺口；现有尾段已有画幅/风格/负向，缺的就是这两样） |
| D3 | 14:21 那张**孤儿图**处置（`GalleryStore` 无删除/回收、前端也不列 gallery）——审计工具（dry-run 默认）或手删 |

### 节点 E — 文档同步（随各节点提交，不单独成节点）

| 位置 | 改什么 |
|---|---|
| `CLAUDE.md` §3.2（:100-103） | **v1 描述**："纪念域 `memorial_enter`（独占轮）/`memorial_exit`（回 bond）……槽位 `[场 task 卡 scene\|memorial_exit]`" —— 动作已退役、场卡恒 `scene`（§8 已改、§3.2 漏改）。CLAUDE.md 自称"以本文为准"，这段会带偏 |
| `CLAUDE.md` §4 纪念段 | "窗口"从板级改成**记录级**（M3） |
| `docs/DESIGN_VN_UPGRADE.md` | 追加决策记录（本页 = 设计稿，落地后补状态） |
| `docs/PROMPT_INJECTION_MAP.md` | 盒 B 块清单/描述若有 art、memorial 相关条目一并校对 |
| `TODO.md` | 纪念相关条目收敛到本页 |
| `CLAUDE.md` §13 / §4 路由 | 登记本文 |

---

## 4. 会带偏你的旧话（读代码前先看这栏）

1. **"纪念是子模式，有 enter / exit 动作"** —— v1 的事。v2 只有 `stage:memorial` **一条记录**；
   **没有退出记录也没有退出动作**，退出 = 块边界 + 引擎补 marker。
2. **`scene.memorial_exit` 在 v2 恒为 `False`**，但 webgui 里还有 **6+ 处活分支**读它
   （`bond.py:1318/1342/1362` 标注门控、`:2446/2449/2475` lane、`:2602/2664` marker 落库），
   `_log_scene_meta` 的 `elif scene.memorial_exit:` **永远走不到**。这些死分支正是
   "链路看起来有 exit 动作"的来源（审计 A2 点过"三个恒假/恒空字段的活分支"）。
3. **`art` 是"可选预告"** —— 只有 `bond_story_rules.md:72` 那一句这么说（**A7 已删，2026-09-20**）。
   契约的 stage 取值清单里它是有的，位置也有校验（必须块首）；**唯一真缺的是"配对"**。
4. **`art` 不进 LLM 历史** —— 它被从记录流剔除（`bond_story.py:960`）、只落成板上的
   `art_hint`（`:990-992`）；历史由 `render_bond_scene_text(payload)` 现算、v2 只渲染
   `payload["records"]`（`renderer.py:70-79`），而 art 不在里头（`records.py:609` 也跳过它）。
   ⇒ **下一轮的 writer 看不到上一轮写过 art**。本设计**不依赖跨轮**（M1/M2 都要求同轮配对），
   但任何"跨轮维持纪念状态"的想法都要先处理这条。
5. **"触发记录放偏后位置"** —— 现状**做不到**（板级切换），M3 之后才真正生效。
6. **`chapters.py:112` 的表格句**（见 B6）**是错的**，代码已修正过；信代码。
