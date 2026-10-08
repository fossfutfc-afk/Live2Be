# PROCEED.md — **接续用**（整篇覆盖写；上一版 2026-10-05 的 L1–L9 记录请看 git 历史）

> ## ⏭️ 接续后第一件事：**P6**（digest 观测那笔小活）
>
> **状态**（2026-10-08 21:1x）：工作树干净 · HEAD = **`00db482`** · ⚠️ **本地 ahead origin 56 笔（我没推 —— 用户自己推）**
> · 全量四件套 **1266 passed**（52s）· B 层冒烟 PASS · 用户正在 compact，之后会**自己硬刷新玩一轮**做真机验收。
>
> ⭐ 这一阶段（2026-10-07 晚 → 10-08 晚）主干是 **两条线**：
> ① **digest 两趟（L1 判关系 / L2 写正文）**：L1 全部落地（P0–P5），下一步是 **P6 观测**，再往下是 **L2（P7+）**；
> ② **羁绊剧情的一串真机报障**：背景永远兜底教室 · 气泡同帧爆开 · "对方正在输入…"乱序 · 块尾硬等 25s
> —— 全部查清并修掉（含**用户新提的"链式读前"**），顺带挖出 4 个真 bug。

---

## 1. 下一步该怎么做（按序，可直接执行）

### 1.1 **P6 = digest「孤立经历」的观测**（小活，一笔做完）
落点 `core/digest/rounds/relate.py`（已 `import logging` 但没用）：
1. 打一行 `logger.info("digest_relate rows=%d rels=%d alone=%d lone=%s cands=%d dropped=%d", …)`
   —— ⚠️ 字面量必须以 `digest_relate` 开头（守门 `test_digest_rounds_speak_their_own_name` 扫源码）。
2. 顺带：`_episode_candidates` 摆不出候选时返回**空串** ⇒ 段标题被 `_sections_for` 吞掉，
   她看不到那个抬头 ⇒ 改成 `（无）`（house style，同 `_round_b_material`）+ 同步 `test_digest_material.py`。
3. 每条守门**先验能红**；一笔提交。
⚠️ 观测的**前提**（否则数没意义）：老 episode **19 条里只有 1 条有 `topics`**（P0 字段 2026-10-07 才加）
⇒ `akin` 的 topics 相交候选**连不到历史** ⇒ 孤立率会虚高。要么接受"只测段内"，要么先写**只补 `topics`
字段**的维护脚本（正文一字不动 + `evolution.jsonl` 留痕，脚本先给用户审）。

### 1.2 **L2（P7+）开工前要用户裁 5 点**
① 那一轮的 key 名（沿用 `group` / 新名）· ② 四件事一次做完还是拆（造 belief + `evolved_from` / experience
沉淀 / `member_of` / 造改 entity）· ③ 料摆几组（**要 P6 的数**）· ④ `attribute` 轮永久删否 ·
⑤ `graph.RELS` 加不加 `continues`（6→7）。
⚠️ 顺带一处**文档自相矛盾**要改：`DESIGN_DIGEST_TWO_PASSES.md` §4 词汇表还留着 `evolve` 标记，
而 §8 已裁"**L1 不打标记**" ⇒ 那行是过期的。

### 1.3 真机验收（用户自己做；等他的反馈）
硬刷新后玩一轮，看三件：**背景跟着 switch 走**（不再永远教室）· **块尾不再等**（若还等，日志里会有
`bond_pregen_chase start … readahead=y`）· **气泡逐条 + "对方正在输入…"贴底**。
另两件**我没做、等他定**：`settings.toml [llm].reasoning_effort` 低档位对照（B 方案，一行）·
`start.ps1` 里加 `lms load`（让 embed 常驻，省掉首轮 2.2s 冷启动）。

### 1.4 用户明确**押后**的
收尾板"名字牌 + 特效"那一批（用户原话：*"我靠忘记这里做特效了，这里特效以后统一做"*）——
现状：名字牌按 `is_end` 整块隐藏，而主角台词本来就不画红字名字行 ⇒ 收尾板里她的台词**没有名字**。

---

## 2. 必读文件（路径 + 为什么）

| 文件 | 为什么必须读 |
|---|---|
| `CLAUDE.md` | 项目主文档（契约/事件流/两遍式/提示词装配/测试约定）。⚠️ 有几处已知过期：§3.3 表"MMT 每 25 轮"（真值 **40**）· §7 "R2 的动作面…`links`"（旧一族）· §3.1 槽位表里的 **P16**（已封印）。**用户自己手工同步**（编辑它会触发全文重注入） |
| `docs/TODO_TWO_PASSES.md` | 两趟的**施工顺序表**（P0–P6 状态 + L2 之前那段）；测试纪律也写在文首 |
| `docs/DESIGN_DIGEST_TWO_PASSES.md` | 两趟**规格**（§9 = L1 契约定稿；§8 = "L1 不打标记"的裁决） |
| `docs/PROMPT_INJECTION_MAP.md` | 每轮注入面现状（P15/P16/P17/P18/P19/卡）；P16 封印后**恒空串** |
| `docs/CONTEXT_MARKS.md` | 括号表（`【】〔〕《》「」`）+ 三条纪律；`【剧情时机】` 已随 P16 退役 |
| `docs/DESIGN_MEMORIAL.md` | 纪念链（含节点 F"图晚到"与新加的"图晚到由 `memorialWatch` 兜"）|
| `docs/EXEC_BOND_LATENCY.md` | 体感性能工程的账（预热/预生成/双路 lane）|
| `.testtmp/` 下的探针 | 我这一阶段写的只读探针都在这儿（`probe_*.py`）；**不是产品代码**，可删 |

---

## 3. 已做的更改（这段会话；每笔都有守门 + 变异验红）

| 提交 | 一句话 | 验证 |
|---|---|---|
| `a94a85d` | 根目录一键启动脚本 `start.ps1` + `start.cmd`（起 lms:1235 + 体检 + 前台起 web） | 实测两步都过 |
| `b3622cc` | **封印 P16「羁绊进度注记」**（按轮次催她发起 VN 的唯一路径）+ 删规则书里"看轮数"那句 | 新守门 3 例，变异红 |
| `35ac784` | 修**气泡节奏**（我上一笔把整批 `at` 恒 0 ⇒ 全同帧上屏） | 冒烟 + 变异红 |
| `63dbea4` | 修**背景永远教室**的**真因**：`_resolve_scene` ① 成功后被 ② 的兜底覆盖 + 新增"章内沿用当前地点"（含回放/回忆册）+ 前端补切 | 新守门 7 例，两处变异红 |
| `9706b43` | 修**"对方正在输入…"**：被延迟气泡挤到上方 + `running=false` 提前收摊 | 冒烟两判据，两处变异红 |
| `a48a47a` | **链式读前①地基**：`_pending_boards` 赋值 → `extend` + `send_vn_scene(readahead=True)` | 守门 3 例，两处变异红 |
| `20717ad` | **链式读前②③**：判据 `_READAHEAD_MIN_BOARDS=4`（两条路分开）· 落地不抢槽位 · 整块标注 · 丢弃清队列 · **修 `busy` 闸门卡玩家** · 未裁决选项注记 · `round` 补偿 | 守门 5 例，5 处变异红 |
| `eb99943` | 「**本章纪念已用过**」静态提示（少白写一次 art/memorial） | 守门 2 例，变异红 |
| `00db482` | **背景补切的独立守门** + 挖出**两个真 bug**（守望用 `round` 假自杀 / 陈旧快照回贴背景 + 纪念闸门） | 冒烟时间线；变异 A 红 |

**真机实测（用户授权，2026-10-08 21:0x）**：mutsuki **副本** + **真 LLM**（`.testtmp/e2e_mutsuki*`，数据根 patch 到
`.testtmp`，**真 `data/` 一字未动**）⇒ 重放备份 7 句玩家台词 → 第 4 轮触发 VN；链式 **每次推进 `src=queue` 0ms**；
背景 **教室→夏莱办公室** 补切成功；气泡间隔 3.0/2.7/1.5/1.1s；指示器 **0 帧错位**；首块真机生成 **9.4s**。

---

## 4. 隐形坑（踩过的、容易误判的）

### 4.1 测试/回归
- **`--basetemp` 必须预建目录且每次换新**（Windows）——否则**全部**用例 `PermissionError`（实测 1266 errors，看着像全崩）。
- **不许频繁跑全量**（用户硬规矩）；改到一半不跑；按板块跑。
- **改文案/规则书/prompt ⇒ 必须刷夹具**：`PROMPTKIT_UPDATE_FIXTURES=1 pytest tests/core/test_promptkit_baseline.py`，然后**人工审 diff**。

### 4.2 冒烟（B 层, `python experiments/web_e2e/run.py`）
- 桩的 `MMT_CHAT`（普通聊天轮）**整段一次喂**：分行喂会让 3 行跨两次轮询 ⇒ 节奏判据随机红绿。
- 节奏判据 = **maxGap ≥ 800ms**（不判"前两条的间隔"——引擎逐行交付本身有 ~250ms 间距）。
- 背景守门的**窗口**靠两件事同时成立：`STUB_PLACE_LAG_S=4.0s`（**> 标题屏 2.4s**）+ switch 文本
  **不命中层1 关键词**（`place_entities.json` 的 `keywords` 是 0 调用别名表；命中就当场出键 ⇒ 窗口不存在 ⇒ 假绿）。
- 背景时间线用 **MutationObserver** 记（轮询式采样**会漏**，会把"已补切"读成"没补切"）。
- `tests/webgui/conftest.py` 把**链式钉回旧节奏**（`_READAHEAD_MIN_BOARDS=1`）：桩块只有 2~4 板，
  链式会让预生成触发得勤得多，把既有用例的脚本吃光。要验链式自己 monkeypatch 成 4。
- 桩的 place lane 睡 4s ⇒ 会**推迟 `gate_place`**（推进门控），冒烟整体慢 ~4s。

### 4.3 链式读前（这一阶段最容易改错的地方）
- ⛔ **两条路必须分开**：槽位空 ⇒ 正常走一次（队列有货就**领一块进槽位**，0 LLM；队列空才真生成）;
  槽位有人但"手里不够读" ⇒ **强制再写一块**（`readahead=True`）排队尾。**一律 `readahead=True` 会丢掉"补槽位"那条 0 LLM 路**。
- ⛔ `_pending_boards` 是 **`extend`**（跨块追加），**别改回 `=`**（那会把玩家没读完的板整段丢掉）。
- ⛔ `api.py` 的 `busy` 闸门**只该拦"要领的东西还没写好"**：链式之后后台会持续写将来那块，
  无条件拦 = 每块都"点击被拒、等生成"（比不做链式更糟）。
- ⛔ 读前生成时**手里的选项还没裁决** ⇒ 必须给 `_pending_choice_note`（否则 writer 猜一个选择来承接）。
- `_READAHEAD_MIN_BOARDS` 的算术：一板 ≈ 9s 阅读 × 4 ≈ 36s > 一块生成（真机实测 **9.4s**，慢的回合 25s）;
  `min = 1` = **旧行为**（手里有货就不开工），测试要旧节奏就设 1。

### 4.4 前端（bond.js / mmt.js）
- **守望/轮询判"板还在不在"用内容指纹（`sceneKey`），⛔ 不用 `round`** —— `state.round` 在**交付之后**才 +1，
  首板必然"假推进" ⇒ 守望第一个 tick 就自杀 ⇒ 晚到的 emotion/place 全补不上。
- **纪念窗口里不许补切板级背景**（`syncBoardBg` 里 `if (memorialNow()) return;`）——否则顶掉黑屏。
- 补切只做一次**不够**：纪念退出会把 `curScene.background_url`（渲染时的陈旧快照）贴回来 ⇒
  首屏轮询也要对账 + 守望自停要等 `bgAgree`。
- "对方正在输入…"必须**永远贴末尾**（`typingToTail`），且 `running=false` 时**队列没放完不许收摊**。
- 一行 = 一个气泡（`split_reply_chunks` 已从两处摘掉）；节奏常量在 `mmt.js` 头部，CLI 端真源 `core/tui/streaming.py`。

### 4.5 环境/本机
- `lms server start` **必须显式 `--port 1235`**（不带端口会沿用上次的，而 `settings.toml [embed]` 钉的是 1235）;
  `[embed].model` 钉死 `text-embedding-qwen3-embedding-0.6b`（本机同时装着 nomic，自动发现不可靠）。
- LM Studio 空闲后第一次请求要 **~2.2s 唤醒**（之后 13~25ms）⇒ "TTFT 变慢"先看这个，不是流解析。
- 1200 之前那次 `mmt_stream_first ms=9718` 是**模型慢**（想完一口气写完），不是链路问题。
- 删东西**只指定路径、不用通配符**；只在工作目录内部删。
- 真机数据：`data/worlds/world1/characters/{igusa_haruka,asagi_mutsuki}/soul/`（haruka = 用户在玩的主线；
  **我这一阶段的实测全部在副本上跑**，真 `data/` 未动）。
