# PROCEED.md — 接续用（**整篇覆盖写**；上一版见 git 历史）

> ⚠️ **本文件不记 `ahead` 数**（写死过两次、两次都对不上）—— 真源 = `git status -sb` 与 `git log -1`。
> ⚠️ **`git status` 里常年挂着几份"作者手改未提交"的文件**（2026-10-17 时是
> `config/settings/relation/interperson.yml` · `infra/fuse.py`）——
> 那是**作者的改动, ⛔ 不是脏改动**, 别 `checkout` 掉、也别卷进提交（`git add` 一律写显式路径）。
> 现状：`tests/core` **1295 passed** · `tests/llm+tui+webgui` **208 passed**（⚠️ **按域分开跑**, 见 §5 坑 4）·
> 三份 verifier 全 exit 0 · ruff **366**（基线，`AGENTS.md` §7 同步）· 真机数据未动。
> ⚠️ **两域里各有几个轮询式 flaky**（靠 `_wait(cond, timeout=10)` 等异步状态的那类）: 机器一忙就超时,
> 单跑常绿 ⇒ 别急着怀疑自己刚改的代码, 见 §5b 第 17 条。
> ⚠️ **测试目录 `tests/renderer/` 已改名 `tests/tui/`**（2026-10-15，跟着 `renderer/`→`tui/`）。
> 📄 **活入口 = 仓根 `AGENTS.md`**（2026-10-15 起取代 88 KB 的 `CLAUDE.md`；旧文归档在
> `docs/archive/CLAUDE_2026-09-20.md`）—— 读项目先读它；本文只记"接续要做的事 + 坑"。
> 🎯 **下一步等作者定**: 可能做**首次使用向导（前端）** / **打包 exe** / **架构优化** —— 见 §6 末尾。

---

## 0. 写法约定（2026-10-15 作者要求，代码注释一律照此）

- 只写**关键点**：顶部 docstring 不许比它底下的代码还长；函数内注释同理。
- 不用 `★ ⚠ ⛔ ✅` 这类装饰符号（满屏符号反而看不见重点）。
- 不写"用户拍板 / 用户裁 / 作者定的"这类表述 —— 重要的是规则本身，不是谁说的。
- 理由：长注释会随代码一起过时（本项目已经踩过多次）；解释放 PROCEED 与提交信息，代码里只留结论。
- 历史文件里那种写法很多，**读的时候别照抄**。

---

## 1. 现状：记忆层（线 A）走到哪了

**一句话**：写侧只写地址、引擎物化、内容归 LLM；**一段 6 轮**（`ROUNDS` 是唯一真源 ——
`group` 退役后从 7 掉到 6, 其中 5 轮发 LLM、`akin` 零 LLM）：
`split ⓪切 → record ①记 → akin 补边(0 LLM) → relate ③接 → cognize ⑥想 → settle ⑦沉淀`
（`understand`/`group`/`close` 已退役, 编号留空档）。

| 轮 | 今天的活 | 料（段名） | 产出 |
|---|---|---|---|
| `relate`（**判关系**） | 判这一段的新经历跟谁有关系, **一个字的正文都不写** | 本次新经历 · 现有经历（候选）· ⭐**她认过的同类印证过的看法** · 本段时间线 · 现有认知 · 人设 | 四种边：`akin` / `supports` / `contradicts` / `evolved_from` |
| `cognize`（**写正文**） | 造新看法 **或** 改已有的看法, 不判已有成分之间的关系 | ⭐**这次的事** · ⭐**这一类事** · 现有认知 · ⭐**跟这条撞上的现有看法** · 已有的对象 · 人设 | `belief` 节点 + 出生自带边 |

⭐ **今天刚落地的那一刀（`2597737`）：看法可改** ——
`{"belief": {"id": "u0003", "text": …}, "supports": […]}`
- **带 `id` = 改那条已有的**（只改写出来的格子; `text` 留空 = 正文不动, 只加边）
- **不带 `id` = 造一条新的**（`text` 必填, 至少一条立足点, 只数新建 ≤5）
- **边只增不减**（⛔ 没有"删证据"这个动作）· `evolved_from` **只在造新的那条上写**（改口 ≠ 取代）
- 三档分开：**锚点 `id` 没命中 ⇒ 丢这一行**（不连坐）· **证据 id 没命中 ⇒ 整包拒**
- **`text_seq` 水位**：同一段重跑不许把同一条正文再改写一遍（防措辞漂移）· ⛔ 改那一路**不并 `akin`**
- ⭐ 两个新料格都走同一条纪律：**看见就得能引用**（cap 之外的看法补发本地号并进引用面）

⭐ **`f6541b0`：L2 的料区域化** —— 【被连过的经历】拆成 **`【这次的事】`**（本段被 L1 连过的,
立足点）与 **`【这一类事】`**（它们一跳 `akin` 的邻居, 额外的证据）。**判据一个字没改**
（一跳 · 打架的不摆 · 边建立序 · 先到先得）, 换的只是摆放 —— 从前簇散在每条 anchor 底下,
她数不出"这一类一共几条 / 跨多长时间"。
- **正文互斥**（不是条目互斥）：本段的条目在第二区只出**信息头** + `（正文见上面【这次的事】）`,
  且**不占额度**（否则本段三条就把 5 格吃光, 老经历反而看不见）
- 额度：`DIGEST_L2_AKIN` **3/每条 anchor → 5/整区**（与 `AKIN_JOIN_MAX` / 撞上那格同量级）
- 空区 ⇒ 空串 ⇒ `_join_sections` **连段头一起不印** · `evidence_ids` 的集合与改前逐条相同
- "这些也算作证据"那句从**料的抬头**搬进契约【belief 释义】（抬头撤了, 留着就是假描述）

**其余已落的**（细节看提交信息, 不在这儿复述）：
`kind` 只剩四种（`episode/experience/belief/entity`; **`profile` 2026-10-14 删格式**）·
`topics` 退役（字段只停产, 判据随载体走）· `entity` 留空 ⇒ **默认归属**（读侧口径, ⛔ 不落边）·
`evolved_from` 图上方向 = **旧 → 新** · akin 共 belief（一跳邻域并进证据, 额度 5）。

**真机读数**（只读探针, haruka）：节点 30 · 边 58（`about 22 · supports 25 · member_of 6 · akin 5`）·
`entity` 字段 **0/30** · 全图 `contradicts`/`evolved_from` **= 0** · akin 5 条全在一个 6 条簇里 ·
⚠️ 认知列表里 `e0001` 是一条 **belief**（id 带老前缀, 历史遗留, 不影响功能）。

**线 B（包重组，另一个 agent 负责）**：`contract/` 与 `llm/` 那一层已经理到位 ——
1a / 1c / 1d / 1f / 1e / 1h 全部落地（见 §4 提交表），并**新建 `infra/` 层**
（`paths` 五个根 · `atomic` · `fuse`）、**解散 `core/common/`**（那个"抽屉"里 6 个模块 4 种性质各归各家）。

- `llm → core` 现在**零依赖**：`test_import_direction.py` 的 `LLM_CORE_ALLOWED` 是空表。
- `infra/paths.py` 的五个根：`RESOURCE`（只读，随包）· `CONFIG` / `ASSETS`（用户内容，
  以后可能由首次向导指定）· `APP`（settings.toml）· `DATA`（事件流真源）。源码树里
  `RESOURCE`/`APP` = 仓根、其余三个 = 仓根下同名目录，所以**老常量值一个字没变**。
- `infra/settings.py` 已是 settings.toml 的**唯一读入口**（9 个读者收成 1）。**不缓存、每次重读**
  （mtime+size 那个缓存在 2026-10-15 被自测抓出会读到旧值，已去掉）。
  `[paths]` 那一节也通了（首次向导写它，保存后要重启才能生效——`paths` 是 import 期常量）。
- **批次 2 目录改名：收工**。计划 = `docs/EXEC_RENAME.md`。
  **第 1 步 `apps/`→`cli/`、第 2 步 `renderer/`→`tui/`（含 `core/tui` 三件拆平进 `core/`、
  `renderer/core.py`→`tui/renderer.py`、`tests/renderer/`→`tests/tui/`）都已落地**。
  **第 3 步（`core`→`engine`）作者裁决不做**（收益纯语义、代价 ≈1400 处；理由与实测在计划文档 §8）
  ⇒ `core/` 保留原名，靠 `core/.md` 说明"它是领域引擎，底座在 contract/infra"。
  改名脚本 = `.testtmp/rename_pkg.py <old> <new> [--dry]`（先干跑逐处打印；⚠️ 默认**不开**
  "裸点名 `X.y`"那条规则——本仓有同名陷阱：`core/session/renderer.py`、`cli/vn_cli.py` 里的
  局部变量 `renderer`、以及 pixi 的 `app.renderer`；另外它抓不到散文里列举的包名，
  应用后要再 grep 一遍裸词）。
- 另有两条可选：`webgui/store.DEFAULTS` 与各领域默认值**两处写**（设置项清单的归属）·
  文档那一趟（`CLAUDE.md` 等里的 `core/common/`、`contract/schema.py`、以及**本轮改名的旧名**）。

---

## 2. 下一步该干什么（按顺序）

### 2.1 ⭐ 真机端到端跑一次（唯一能看出"改完长什么样"的一步）
```powershell
# ① 先确认 embedder 在（不在 ⇒ L1 候选 + 撞上的语义那一路都只剩字面）
lms server start                      # 本机 LM Studio, base_url 指 1235
# ② 起服务 + 跑观察脚本
python -m uvicorn webgui.app:app --host 127.0.0.1 --port 8000
python experiments/recall_report.py
```
看三行：`digest_relate … cands= sim=`（`sim=0` = 语义没起来）· `digest_cognize … patched= empty= watermark=`
· `digest_embed fn=`（`none` = 降级）。⚠️ 真机数据只读之外, 这一次**会写**（真要跑 digest 才写）——
先想清是不是要在真档上跑。

### 2.2 ⏸ 已知缺口（记着, 不是现在做）
- **撞上的"语义那一路"暂缺**：那一刻她还没写出新看法, query 只能拿本段经历顶 ⇒ 等 `[embed]` 在位再补。
- **判错的 `akin` 无法撤回**（你裁"只为删边没必要"）。⚠️ 业界对**边**的撤回是**标记失效**
  （Graphiti `invalid_at`/`expired_at`, 从不 delete）—— 我们缺的正是这一层。
  将来要做, 形状是"**给边补一个结束时间**", ⛔ 不是 `remove_edge`。
- **召回折叠演化链**（"以后再说"）· **`aliases` 的写者**（"她主动补新别名"仍冻结: 并错不可逆）。
- `noticed` 那条路落的 `akin` 边**不写变更史**（只有一行日志）。

### 2.3 收口类（欠的活, 都不阻塞）
⭐ **代码里 19 处 `PROCEED §2 #10/#11/#16` 这类交叉引用指向的是"旧版 PROCEED 的结构"**
（第十二版重排后那些节号已经不存在 ⇒ 全是死链, 但**裁决本身都还在**）。两条出路, 二选一:
给 PROCEED 加一节「旧编号 → 今天在哪」, 或者把那些注释改成不依赖节号的写法（`akin.py` 那处
今天顺手改了, 其余 19 处没动）。
`form_key` 下移 `contract/`（统一 `parse_attribution` 两端）·
四份契约的**文风/结构统一**（向 `settle` 看齐 —— 值表 → 判据 → 【释义】→【范例】的固定顺序）。

---

## 3. 必读文件（只列真会打开的那些）

| 文件 | 为什么 |
|---|---|
| `core/digest/rounds/__init__.py` | ⭐ **轮次真源 `ROUNDS`**：key/步序/相位/prompt/**料**/**写什么**/预算一处说全；`material` 是硬契约（改了必须与 md 两边同改） |
| `core/digest/material.py` | 各轮的料（L2 那两个区在这儿：`_l2_material` / `_akin_region_rows`；两个新格：`akin_supported_beliefs_block` / `collided_beliefs_block`） |
| `contract/digest/prompts/cognize.md` | ⭐ **今天刚改的契约**（带 id = 改 / 不带 = 造；边只增；撞上四条出路）—— 改它先读 `docs/EXPERIMENT_CONTRACT_SHAPE.md` |
| `contract/digest/parse.py` | 两档校验（丢行 vs 整包拒）与 **id 容错**都在 `parse_cognitions` / `_clean_belief` |
| `core/brain/revise.py` | 三个执行器 + `_join_akin` + **`_apply_belief_patch`**（覆写/水位/留痕） |
| `core/brain/graph.py` | 边词汇表 + `DEFAULT_FACES` / `default_faces` / `lane`（**默认是读侧口径**） |
| `docs/EXPERIMENT_CONTRACT_SHAPE.md` | ⭐ 契约形状的 A/B 记录 + **别人的 digest 契约对照**（Mem0/AgentGal/Graphiti/LangMem/Letta） |
| `docs/DESIGN_MEMORY_MODES.md` | 四种模式的语义地基 —— ⚠️ **§0/§1 还在教已退役的"经验=门槛"模型**（读它要带这层判断） |
| `.testtmp/verify_1c.py` · `capture_prompts_1d.py` · `capture_1e.py` | ⭐ 动契约/文案的三份逐字节判据（各自 `check`；`EXPECTED_CHANGED`/`CHANGED` 要写"为什么"） |
| `CLAUDE.md` | ⚠️ 89 KB 且多处过时（`topics`/`profile` 那几行已作废）；当索引读, 冲突时**信代码** |

---

## 4. 这一段的提交（越往下越新）

| 提交 | 做了什么 |
|---|---|
| `080460b` | `topics` 退役：`on` 的判据随载体走 · 字段只停产 · `轴` 那格全撤 · L1 候选换源 `like(spec="digest")` |
| `7697b72` | `entity` 留空 ⇒ **默认归属**（R1: 你+老师）—— 读侧兜底, ⛔ 不落边 |
| `99b9271` | `evolved_from` 图上方向翻成 **旧 → 新**（名字不动） |
| `f7a280a` | PROCEED 修三处会误导的（`supports` 出边 · 去掉写死的 `ahead` · "树干净"那句） |
| `f738ea5` | **删掉 `profile` kind 与 `examples` 字段**（真机零依赖; `subject` 留着 —— belief 的活读者） |
| `2597737` | ⭐ **L2 碰撞那一刀**：看法可改（`id` 决定建/改）+ 两趟各补一格 + `DEFAULT_FACES["belief"]` |
| `f6541b0` | ⭐ **L2 料区域化**：【这次的事】/【这一类事】两区 + 正文互斥（信息头不占额度）+ 额度 3/条 → 5/区 |
| `3f34874` | `contract/schema.py` → **`contract/schema/` 包**，2.6 KB 文案搬进 `prompts/*.md`（5 个形态逐字节不变；顺带砍掉 3 个生产死件 67 行） |
| `3070a25` | `contract/schema/` 的**文案守门**：动作名必须在注册表里 · 取值表与 `records` 文法对账 · 规则 md 是干净列表 |
| `d83bb04` | **新建 `infra/` 层**：`paths.py`（五个根）· `atomic.py` · `fuse.py`；31 处 `core.paths` → `infra.paths`；顺手治 6 个"自己现拼根"的文件 |
| `21a4df0` | **解散 `core/common/`**：`errors` 壳删（20 处直连 `contract.errors`）· `mmt_registry`→`core/mmt/` · `tone`→`core/parsing/` |
| `4a8e39b` | **注释瘦身**：按作者要求改掉我自己写的那几个文件（去掉装饰符号、"只写关键点"；写法约定进了 §0） |
| `dd40344` | **`infra/settings.py`**：settings.toml 的**唯一读入口**（9 个读者收成 1）· `[paths]` 覆盖通了 · 坏文件有声音 |
| `b013fbe` | `infra/settings` **去掉读盘缓存**：mtime+size 的键有洞（同长度改写会读到旧值，我自己的测试抓到的）⇒ 每次重读；`settings.reset`/`recall_config.reload` 跟着消失 |
| `fcea64a` | 前端契约守门：`bond.js` 的 `FX_SYMBOLS` ↔ `renderer/effects.py` 特效名两边对齐（两个方向都证过会红） |
| `efa7093` | **视觉门"等多久"收成后端一处**：`GATE_DISPLAY_WAIT_MS`（纯显示，到点 `gate_busy` 转 false，数据不改）与 `GATE_WATCHDOG_MS`（管线安全，会写真源）分开；前端不再自己数 8 秒 |
| `83a399e` | `/err404` → **经典 XP 蓝屏**（namegg `FT~` 落地页）：自带 CSS/JS（零 `/static/` 引用）· 确定 ⇒ 30 秒假转储 → alert → 回主页面 · 全屏尽力而为 + 点击兜底 |
| `697d65c` | 前端节奏收成一处：新建 `js/typing.js`（纯计算 + 顺序揭示队列）· `bond.js` 只动两处 · **前端第一次有了自动化守门**（`node --test` 9 条 + pytest 包装） |
| `6fa30f7` | `docs/EXEC_RENAME.md`：顶层包改名计划（三步 · 四条已定决策 · 每步引用面与判据） |
| `4adf7e1` | **EXEC_RENAME 第 1 步**：`apps/` → `cli/`（24 文件 / 42 处引用；含 `start.ps1` 的用户命令与 4 个 `experiments/` 脚本）· 新增 `cli/.md` |
| `d485e9b` | **EXEC_RENAME 第 2 步**：`renderer/` → `tui/`（+ `core/tui` 三件拆平进 `core/{display,streaming,text}.py`、门面删、`renderer/core.py`→`tui/renderer.py`、`tests/renderer/`→`tests/tui/`）· 干跑抓到三处同名陷阱 |
| `d90024c` | **EXEC_RENAME 收工**：第 3 步（`core`→`engine`）作者裁决不做（≈1400 处 / 收益纯语义）· 新增 `core/.md` 把"名字会误导"用文档补掉 · 计划文档 §8 记下实测与替代做法 |
| `92059f49` | 补 `webgui/.md`（约定里最后一个没写的包）+ `test_paths._SCAN_DIRS` 从五包扩到七包（`cli`/`tui` 上一轮改名后没被扫过）；守门双向证过会红 |
| `bb03fecb` | ⭐ **`AGENTS.md`（12 KB）取代 `CLAUDE.md`（88 KB）**：harness 的候选表是 `["AGENTS.md","CLAUDE.md"]` 且**两份都加载** ⇒ 旧文归档成带日期的 `docs/archive/CLAUDE_2026-09-20.md`（叫 `CLAUDE.md` 会被再注入一遍）· 新增 `infra/.md`（约定里唯一缺的）· `contract/.md` 的"七轮"改指真源（实为 6 轮） |
| `eb96f365` | 10 处 `CLAUDE.md §N` 引用改成**按名字**引用（`AGENTS.md` §8「产品决策」八条）；两处不指 AGENTS 而指真家（`tests/stub_tasks.py` 的 `_COUNT_RE`、`recall.py` 自己的 MU/SIGMA）；顺手修 `recall_config` docstring 里已被删的 mtime 缓存说法 |
| `c1c090f2` | **逐包导览第 1 站 `core/affection/`**：自拼根路径收进 `paths.DATA_DIR` · 补上守门盲区（老判据够不着"赋值换行续写"，改成**逻辑行**判；真违规当场红）· 注释 224→156 行 |
| `d899a6b6` | **第 2 站 `core/bond/`**：清注释（净 −252 行；顶部 docstring 砍 30~60%、清全部装饰符号与"用户裁"）· 修两个注解类型错（`_extract_array -> object` 与 `int(it.get(...))`） |
| `6c475f8e` | **第 3 站 `core/brain/` 顶层十个文件**：剥约 390 处装饰符号 · 10 个顶部 docstring 重写（337→185 行）· 去 23 处"用户裁/拍板" · 顺手修两处**内容已错**（模块表里列着已删的 `groups.py`/`seed.py`；`graph.py` 说"还没有 entity"） |
| `f41ed19d` | **`core/brain/read/` 第二刀**：新工具（`tokenize`+`ast`，只动注释/docstring，真字符串不碰）剥 374 行 · 去 51 处"用户"表述 · ⭐ **修四个 Pylance 报错**——根因全是 dataclass 字段写成 `object`（`Candidate.node` / `Composed.node` / `embed_fn` / `float(h.raw)`） |
| `f0ac5dbe` | **第三刀**：新写 `core/brain/.md`（机制说明）· **删** `AGENT_BRAIN.md` `DESIGN_GRAPH_V4.md` `REDUNDANCY.md` · 清 **59 处**指向它们的引用（`archive/` 里 5 处故意留） |
| `6736ea6f` | PROCEED 定点更新（不动线 A 的 §1–§3） |
| `2f9d2a93` | **第 4 站 `core/creep/`**：三个顶部 docstring 29/35/24 → 16/19/17 行 · 去装饰符号与"用户裁决" · 新增 `core/creep/.md`（作用/核心文件/现状"只留接口"/五条纪律/措辞纪律） |
| `3b298f6d` | brain 五处 Pylance 报错（`all(isinstance)` 窄化不了 · `nodes: tuple` · `-h.raw` · `extra: object` · `add_edge` 的 src/dst） |
| `65bf18e1` | ⭐ **修复 `bond_progress.py` 整份缩进塌陷**（粘贴/渲染事故: 每行前导空白被压成一个空格 ⇒ `IndentationError` ⇒ 全仓 1047 例收集失败）。做法: 以 HEAD 为基准, 去掉空白后逐行比对 + **非 docstring 字符串字面量全量核对**, 只摘掉那 11 行 docstring |
| `e4102db6` | **`core/brain/read/` 去重**：`scale.py`（`cosine` / `pool_minmax` / `SCALE_*`）与 `context.py`（输入契约）两件**中性件** —— 因为 `like/pack/find` 不许 import 旧族（守门⑤）; 两处 cosine、两处 min-max、「两套 ctx」各收成一份; 新增守门（共用算术只有一处, 双向证过） |
| `ee70286f` | **第 5 站 `core/digest/`**：七处类型错（`_parse_for` 的 parse 可为 None / `_create_a_nodes` 返回注解是假的 / `store.get(...)` 直接 deref ×2 / 元组解包 / `Snapshot` 别名）· `__init__` 的 48 行**过时** docstring 压成 6 行（还写着已退役的 `group` 轮）· 新增 `core/digest/.md` |
| `7571b693` | **第 6 站 `core/media/`**：`files = v.get("files") if isinstance(v.get("files"), dict)` —— **两次 `.get`** ⇒ 改成取一次再判; 新增 `core/media/.md` |
| `22629909` | **第 7 站 `core/mmt/`**：七处类型错（`emb` 的 None / `plan` 的字符串标签联合 ⇒ 统一成 `AgentAction` + `_text_action` / 两处 `display_name`）· `parse_lines` 的 ruff-unused 与 API 面快照打架 ⇒ 保留 + `noqa` 写明, 刷快照 · 新增 `core/mmt/.md`（**主循环讲清楚**） |
| `ce18cfcb` | **第 8 站 `core/promptkit/`**：`_greeting` 返回注解 · `promptkit/.md` · ⭐ 新增 **`docs/PROMPT_SAMPLES.md`**（每个调用点 system/user 长什么样: 段序 + 出处 + 形状样例; 规则书只给链接, 召回用文字讲清） |
| `f4f9f232` | **第 9 站 `core/rag/`**：`_ensure_vectors` 从 `-> bool` 改成**交回向量表**（窄化 + 三种"没有语义层"仍记缓存） |
| `288b127f` | **第 10 站 `core/random_events/` + `core/session/`**：`cooldowns` 的地板判 · `per_board.get(item.get("seq"))` · `has_picked` 这种**中间 bool 窄化不了** · 新增 `core/session/.md`（事件流数据流 / 六条纪律） |
| `cffd5a2a` | **第 11 站 `core/worldtime/` + `core/text.py`**：`occ.year_fixed`（property 不能窄化）⇒ 直接判 `occ.year is not None` · `_parse_spec` 两支倒过来各自窄化 · `text.py` 那个把 `list` 塞进 `list[str]` 的**死分支** · 新增 `core/worldtime/.md` |
| `81e19474` | **webgui**：`app.py` 的 `settings` **名字遮蔽**（router 覆盖了 `infra.settings`, ruff F811 早就在报）⇒ `settings_router` · `_table_bg_url` 的两次 `.get` |
| `7cccf763` | `webgui/bond/state.py` 三处 `object` 注解（`store` / 两个线程）——§5b 第 12 条那笔欠账清掉 |
| `23210a18` | **`webgui/bond/` 第一刀**：`_place_done` 是**动态属性**（6 处赋值 / 12 处 `getattr` 读）⇒ 在 `BondScene` 上按 `_streamed` 的先例声明 · `state.scene_obj`/`vn` 的"先赋值再读"窄化失效 ⇒ 局部变量接住 · lanes 两个 worker 的队列与 vn 取一次局部 |
| `fbb59708` | **`webgui/bond/` 第二刀**：又两个动态属性（`_call_id` / `_from_draft`）· `_generate` 声明 `-> bool` 却**漏 return True**（调用方把"启动了"读成"没启动"）· `replay.open_attempt` 改成**交回新段**（闭包 `nonlocal` 窄化不了） |
| `a4282426` | ⭐ **MMT 静默行 `{"text": ""}`**：她可以这一轮完全不发消息（玩家把话拆几条发、还没说完时"等下一句"）。空串是**唯一**合法写法（`null`/空白串仍按坏行丢, 文案教它写空串）· 不算空轮/不算失败 · 轮数照算 · **玩家那句话补进历史**（不补这功能就没意义）· `TurnResult.silent` |
| `4e16e3ed` | **CLI 的 VN 分支不落事件流**（`cli/main.py` 调 `run_bond_story_vn` 没传 `store` ⇒ `vn_enter`/每场 bond/`commit_staging`/`finish` 全被跳过, 跑起来一切正常）。补 `store=engine._store` + AST 守门（漏参数 / 传 None 两个方向都证过会红） |
| `d4e07363` | ⭐ **收束注记单源化**：CLI 那两句还在教 v1 的 `story_end` 动作（v2 记录流里没有它）⇒ 新建 `core/bond/bond_story/closing.py`（`REMIND_ROUNDS`/`END_ROUNDS` + `closing_notes`）, 两壳都调它; 顺带补上 CLI 缺的"余量 2 场每场强制" · 守门钉住"这三句只许在一处" |
| `638609d5` | 给 `cli/` 定性: 产品只有一个壳 = `webgui/`, CLI 是调试入口**不追 webgui 行为**（`AGENTS.md` §8 新增同名决策 + §1 表格三行; `cli/.md` 重写） |
| 本轮 | **控制台日志收口**: 新建 `infra/logsetup.py`（控制台短/文件全）——轮询与静态请求的 2xx 不打印 · 短域名前缀（`digest`/`bond`/`mmt`/`llm`/`http`）· 超 110 字截断 · `LIVE2BE_LOG=quiet/normal/verbose` · `akin` 逐条边降 debug。文件日志仍全量（软问题文本可 grep） |
| 本轮 | **digest 关停韧性**: 新建 `infra/runtime.py`（关停信号 + 在途登记）· `digest_segment` 在**每轮之间**与**提交前**查闸 ⇒ `_abort`（回滚内存、**不写盘、不计 `digest_retry`** —— 否则三次 Ctrl+C 就永久放弃一段）· `WikiStoreV2._heal_watermark` 加载时按图上 `event_seq` 补齐水位（修"图新水位旧"⇒ 重喂 ⇒ 重复记忆）· `webgui/app.py` lifespan 关停时置信号并等 3 秒 |
| 本轮 | ⭐ **两阶段提交**（`WikiStoreV2.commit`）: 点 + 边 + 水位先一次性原子写进 `wiki.txn.json`, 再逐份应用, 最后删日志; **加载时残留就照它补完**（幂等）。`save()` 同款 ⇒ **写路径只有一条且都有保护**。digest 的提交从 `save()+save_meta()` 改成 `meta 赋值 + commit()`（此前中间被杀就是"图新水位旧"） |

---

## 5. 隐形坑（一行一条；细节在代码注释与 git 历史里）

**环境 / 工具**
1. 跑测试必须带 `--basetemp=.testtmp/_pytemp -o cache_dir=.testtmp/_pcache`（`%TEMP%` 权限坏）。
2. 解释器 `C:\Users\johnf\miniconda3\envs\live2be\python.exe`；ruff 在 `…\envs\live2be\Scripts\ruff.exe`。
3. ⛔ **别用 `ruff --select … --fix`**（`--select` 覆盖 pyproject ⇒ 批量删掉有效的 `# noqa`）。
4. **四个域塞进一个 pytest 进程会互相干扰** ⇒ `tests/core` 一条命令、`tests/llm tests/tui tests/webgui` 另一条
   （`tests/renderer/` 2026-10-15 已改名 `tests/tui/`）。
5. ⚠️ **`git show HEAD:<file>` 是 LF、工作区是 CRLF**（autocrlf）—— 验行尾**只看工作区文件**;
   `write`/`Set-Content` 之后必须 `check_eol.py`（`edit` 工具不会改混）。
6. PowerShell 会吃掉 `-c` 里的嵌套引号 ⇒ 脚本一律写成 `.testtmp/*.py`；`git commit` 一律 `-F 消息文件`。

**契约 / 文案（改一个字节就要跑三份 verifier）**
7. ⭐ **改 `contract/digest/prompts/**` 或 `llm/prompts/**` ⇒ 立刻跑三份 verifier**，有意的改动写进
   `EXPECTED_CHANGED`/`CHANGED` **并写为什么**（长期红的判据 = 没人看的判据）。
8. ⭐ **`【】` 是段头不是强调号**：契约 md 里写 `【X】` = 对她宣布"下面这段叫 X"⇒ 必须有出处
   （料名 / 契约自己行首定义 / 渲染器标签），由 `test_digest_contract_refs.py` 钉住。
9. ⭐ **守门是一对**：`test_material_names_are_not_dead`（料名必须出现在某份 md）↔ `test_every_bracket_in_prompts_has_a_home`
   ⇒ **改段标题必须 `ROUNDS.material` 与 md 两边同改**。
10. ⭐ **模板槽只有一种写法** `{{名字}}` + `contract.slots.render_template`（**两个方向都对不上就当场炸**
    —— 我把 `{{max_cognitions}}` 写成字面量 5, 当场红）。
11. **契约里不许有"假威胁"**：写了"违反即丢弃", 引擎就必须真丢；**判据的载体死了, 那句判据也要跟着死**。
12. **空值语义有两种, 别混**：`settle`/`cognize` 的**空格子 = 不改** · `entity` 留空 = **取默认**。
13. **退役分两种**（先例）：**整行死了**（`profile`/`experience`）⇒ 认得出 + 丢行 + 记账；
    **只是行内一格死了**（`about_hint`/`items`/`topics`/`on`）⇒ 白名单外**静默不落库**。
14. 删停产件后**按名字 grep 全仓**（注释里还在讲"某个已删函数恒空"—— 编译器/测试都不会报）。

**方向 / 图**
15. ⭐⭐ **"方向只看一端"这类错犯了四次**：`related` / `conflicting` / `lane` 兜底 / **交接文档**。
    写法：**先把方向写成一句话**（`X → Y`）再写代码。`about` 是"节点 → entity"⇒ 判"这条属于谁"查
    **出**边（`targets`）; `supports` 是"经历 → 看法"⇒ 查经历的 `supports` 要 `targets`（写 `sources` **恒空且不报错**）。
16. **对称 rel 只查一个方向必然漏一半**（`akin`/`contradicts` 存进去被 `canonical_for` 归一）——
    唯一实现 = `graph.related` / `graph.conflicting`（`store` 上是薄封装）。
17. **加了"读侧默认面"这类口径之后, 老 fixture 会静默换一支**（不是红, 是**测的东西变了**）——
    给它们**明确写一个别的归属**, ⛔ 别改判据。
18. **`like()` 会把"本段自己那几条"排第一**（自匹配 1.00）⇒ 调它要 **`k + len(mine)`** 并过滤 `mine`。
19. **一份料里同一段正文只印一次**：`printed/shown` 只收**真印过正文**的; 主列表**永远印自己那一条**
    （我第一版把"只出信息头"也算进"已印"⇒ 那一条正文一个字都不剩）。
20. **`kind` 认不出会静默降级成 `episode`**（`from_dict` 的兜底）⇒ 删一个 kind 时,
    **"照条目建节点"的那一支必须删干净**, 不能只停产（否则埋一条"画像被写成经历"的路）。

**真机数据**
21. ⭐ **真机数据只读**：探针可以读、可以在内存里改, ⛔ **绝不 `save()`**
    （验证法: `git status -- data` 干净 + `wiki.jsonl` 的 mtime 不变）。
22. 加载真档要 `WikiStoreV2(path=…/soul/wiki.jsonl, …)` —— 第一个位置参数是 **data_root 不是 soul 目录**
    （传错会静默得到 0 个节点）。
23. ⚠️ **`[embed]` 服务不在 = 语义召回静默降级**（`digest_embed fn=none`）⇒ 排查"记忆只增不并"先 grep 这一行。
24. ⭐ **探针不许手搓判据**：我在对照探针里自己写了"本段的条目整个剔出第二区"⇒ 跑出"整区空",
    看着像数据的事, 其实是**我编的规则**（真实现是**正文互斥**）。改判据的活儿要**照抄现役
    实现**, 或者干脆**调真函数**（`.testtmp/probe_l2_region_final.py` 那一版）。

---

## 5b. 线 B（包重组）这一轮的坑 —— 换我来做的时候先读这段

**顶层已定（改名收工）**：`cli` · `contract` · `core` · `infra` · `llm` · `tui` · `webgui`（+ `tests/`）。
层次 `contract → infra → llm → core → tui/webgui/cli`。⛔ **`core` 不改名**（裁决见 `docs/EXEC_RENAME.md` §8）；
⛔ **`core → tui` 必须保持不存在**（决策 ②：引擎要的展示数据留在 `core/{display,streaming,text}.py`）。

1. ⭐ **改名代价要按"出现次数"数，不是按"import 行数"数** —— 同一个包两个口径差 2.5 倍
   （`core`→`engine`：556 行 vs ≈1400 处）。第 1 步也是（计划 4 处 / 实际 42 处）。
   数的时候别忘：**logger 名字符串** · `ROOT / "core" / …` 路径构造 · 守卫表里的字面量 ·
   `start.ps1` 这类**启动脚本里的命令** · `experiments/` 与 `l2d-demo/`（常规 survey 会把它们排除）。
2. ⭐ **通用改名脚本的"裸点名 `X.y`"规则默认关**（`.testtmp/rename_pkg.py`，要加 `--dot`）。
   本仓有三个同名陷阱：`core/session/renderer.py`（与 `renderer/` 包同名）· `cli/vn_cli.py` 里的
   **局部变量** `renderer` · pixi 的 `app.renderer`。开之前先 grep 一遍同名物。
3. **散文里列举的包名脚本抓不到**（`core / llm / webgui / renderer` 这种斜杠分隔、没有 `.`/`/`
   紧贴的写法）⇒ 应用后必须再 grep 一遍**裸词**，逐条判。箭头写法（`core→renderer`）同理。
4. **删包/删门面时目录也要删干净**（连 `__pycache__`）：只删 `__init__.py` 的话 Python 会把那个
   目录当**命名空间包**，`import core.tui` 照样成功 —— "名字消失"是假的。
5. **`infra/settings.raw()` 不缓存、每次重读**（⛔ 别再加 mtime+size 缓存：同长度的改写落在同一个
   mtime 刻度里会读到旧值，这个洞是我自己的测试抓出来的）。`settings.reset()` 与 `recall_config.reload()`
   已随之删除。
6. **前端能测**：`node` 在（v24）。`node --check <file>` 可当语法兜底；纯逻辑单测走
   `tests/webgui/js/*.test.js`（`node --test`），外层包一层 `tests/webgui/test_typing_js.py`
   （没 node 就 skip）。前端契约守门 = `tests/webgui/test_frontend_contract.py`（fx 名两边对齐）。
7. **每个包有一份 `.md`**：常规约定 = 作用 + 核心文件 + 纪律（≤1 页），七个包齐了
   （`contract/` `infra/` `llm/` `tui/` `cli/` `core/` `webgui/`）。⚠️ **`core/brain/.md` 是有意的例外**
   —— 作者要的是"比较详细的机制说明"（数据在哪 / 四种 kind / 六条 rel 的方向 / 归属 / 笔记 /
   写路径 ↔ `ROUNDS` / 读路径三条注入视图 + 五条链路 → 合成 → 两种形式 / 纪律与坑）。
8. **每步验收固定**：`ruff check .` 对齐 **372**（改 import 顺序用 `ruff check --select I001 --fix`，
   它只动 import 块）· 两域测试 · 三份 verifier · `.testtmp/layers.py` 的层间账 · `api_surface.txt`
   刷新（改名是"净中性"）· 一个提交（`git add` 写显式路径）。
9. ⭐ **验证被作者的手改挡住时：开一个 worktree 独立验**。`git worktree add .testtmp/_verify HEAD`
   → 在**那里**跑（`workdir` 要真的切过去，否则还是主树）；两个坑：① `data/basic/*` 是 gitignore 的，
   从主树拷一份过去（`Copy-Item -Recurse data\basic .testtmp\_verify\data\`）② 用
   `$env:PYTHONPATH='.'` 逼它走 worktree 的包。剩下的失败会集中在 `assets/`（worktree 里是**空目录**）
   —— 认得出就不必管；验完 `git worktree remove .testtmp/_verify --force`。
10. ⭐ **剥注释要用 token 级工具**（`.testtmp/strip_marks.py`）：`tokenize` 找注释、`ast` 找 docstring，
    **只在它们的范围里剥**，真字符串（含 f-string）一个字节不碰。本仓有符号落在字符串里的实例
    （`notes.py` 台账文案、`recall_ledger` 的 `" ⚠no_candidate"`）—— 台账那个是**机器可读标记**
    （`test_wiki_recall_ledger.py` 断言它、靠它 grep）⇒ **留**。符号表也别漏 `⏳ ⏸ 🚫`。
11. ⛔ **批处理文本的脚本，三次翻车的教训**（都靠"逐处打印"当场看见、都用显式路径回退）：
    ① 清尾规则**不能无条件套在每个文件上**（我折叠双空格 ⇒ 动了 250 个无关文件）；
    ② 括号正则**不能允许跨行**（`[^（）]` 含换行 ⇒ 把整段吞了）；
    ③ 把子正则 `.pattern` 拼进外层时**必须用 `(?:…)` 包住** —— 它顶层有 `|`，否则整个正则被劈成
    两个分支（会从词中间开始匹配、还塞回一个 `（`）。规矩：**先小样本验证、逐处打印、回退只碰显式路径**。
12. ⭐ **`object` 注解是 IDE 报错的大户**（这一轮修了 6 处，根因都是它）：`Candidate.node` ·
    `Composed.node` · `RecallCtx.embed_fn` / `RecallContext.embed_fn` —— 收紧成 `BrainNode` /
    `Callable[[list[str]], list[list[float]]] | None` 之后，`render` / `modes` / `like` 的报错一起消。
    ⚠️ **还剩几处同类**（`now: object`）：`core/brain/read/{channels,like}.py` 各 1 ·
    `core/worldtime/realtime.py` 1 · **`webgui/bond/state.py` 3**（那边若报"属性未知"就是它）。
    另：修一层注解可能露出下一层 —— Pylance 在类型不明时经常闭嘴。
13. ⭐ **跑测试先确认文件选对了**：我跑了 `test_emotion_text.py`，而覆盖 `_clean_tags` 的是
    `test_emotion_annotate.py` ⇒ **47 绿是假象**，真 bug（F821）最后是 ruff 抓到的。
14. ⭐ **Pylance 报错的四类根因**（2026-10-17 一遍扫下来约 35 处，修法都是"让窄化成立"，不是加 `cast`）：
    ① **两次 `.get`**（`x = d.get(k) if isinstance(d.get(k), dict) else {}`、`t.get(k).asset() if t.get(k)`）
    ⇒ 取一次再判；② **`all(isinstance(x, …) for x in (a, b, c))` 窄化不了单个变量** ⇒ 逐个 `isinstance` 合取；
    ③ **中间 bool / property 当判据**（`has_picked = …`、`occ.year_fixed`）⇒ 直接判那个变量本身；
    ④ **先赋值再读**（`state.scene_obj = …; state.scene_obj.x`）⇒ 用局部变量接住。
    ⚠️ 反过来:**声明 `-> bool` 却漏 return**、**注解写成 `tuple[list, list]` 早就不返回第二项**
    这类"注解在撒谎"更贵 —— 它们不报错的时候是在静默骗调用方。
15. ⭐ **"运行时标记"要显式声明在 dataclass 上**（`BondScene._streamed/_place_done/_call_id/_from_draft`）：
    它们**不进序列化**（`to_dict` 是手写的, 不认这几格）, 但**必须声明**, 否则 6 处赋值全报"属性未知",
    而 12 处 `getattr(scene, "_place_done", False)` 又把真相藏起来。
16. ⚠️ **`.testtmp/` 里的判据不进 git**：`capture_1e.py` 的 `EXPECTED_CHANGED`、`verify_1c.py` 的
    `CHANGED` 都只活在本机 ⇒ 换机器要重建, 而且"有意改动"的记录**不会跟着提交走**。
    改系统提示词时的正确姿势：改 md → 跑三份 verifier → 把差异连同"为什么"写进本机那份清单 → 刷夹具。
17. ⚠️ **轮询式 flaky**：`tests/webgui/test_bond_chain_readahead.py` 与 `test_bond.py` 里几个用例靠
    `_wait(cond, timeout=10)` 等异步状态, 而**标注 lane 的 LLM 调用会落在"采样之后、断言之前"**
    （用例自己的注释就写着"单独跑绿、两域同跑红"）。判据: **同一条命令连跑 3 次, 过/挂/过 = flaky**,
    别改自己的代码去迁就它。
18. ⚠️ **给 `DigestResult` 加字段必须同时归类**：删/加字段后 `tests/core/test_digest_rounds.py::test_every_result_field_is_classified`
    会红 —— 要么写进某一轮的 `result_fields`（回滚清它）, 要么加进 `rounds.COMMIT_ONLY`（回滚不碰它）。
    `aborted` 属于后者（它描述"这次尝试怎么结束的", 不是哪一轮的产出）。
19. ⚠️ **"被杀"与"失败"是两种结局, 别共用一个出口**：失败要计 `digest_retry`（满 3 次**永久放弃**那段）,
    而关停是外部事件。混在一起写 ⇒ 用户按三次 Ctrl+C 就等于亲手丢一段记忆。

---

## 6. 等你拍 / 已裁"不做"（别自己捡回来）

- **拍**：要不要先跑真机端到端（§2.1）· 要不要现在推 push（§2.3）。
- **已裁不做**：`ambiguous` 不加机制 · bond 开场不补 entity 物化 · `examples` 字段已删（⛔ 别加回来）·
  `profile` 已删格式 · `topics` 只停产不删格式 · 撤回边不做（缺口见 §2.2）· 撤回/删证据不做 ·
  召回折叠演化链"以后再说" · ⛔ **belief 正文不原地改**这条**已被推翻**（今天起: 差不多就覆写,
  旧的那句不再成立才 `evolved_from`）。
- **线 B 已裁不做**：`core`→`engine` 改名（§5b 第 1 条有代价）· `contract/` 那 11 个平铺件分族 ·
  `tests/` 归属重划 · `bond.js` 拆分（作者：那坨山暂时不拆）· `err404.html` 的 CSS 抽出（页面已被蓝屏取代）。
  ⛔ **`CLAUDE.md` 不再当活入口**（已归档到 `docs/archive/`，别再往仓根写它）。
- ⭐ **`cli/` 定位（2026-10-17 定）**：**产品只有一个壳 = `webgui/`**；`cli/` 是调试入口,
  **不追 webgui 的行为**（预生成 / 标注 lane / 插嘴 / 回放 / 群聊都不在 CLI 实现, 落后不算 bug）。
  评估过并否决的两个方案: ① `tui/` + `cli/` 合并改名 `clitui/`（约 168 处引用 / 半天,
  只买名字; 且会让 `webgui → tui.effects` 变成"壳借壳", 除非先把 `effects.py` 下沉到 `core/`）
  ② 抽一层 `ChapterSession` 给两壳共用（那 471 行编排是提前抽象, 真要做等群聊带来第二个消费者）。
  **唯一保留的双份义务 = 喂给模型的文案必须单源**（先例 `core/bond/bond_story/closing.py`）。
  细节见 `cli/.md`; 这两条已写进 `AGENTS.md` §8「产品只有一个壳」。
- **线 B 逐包导览：已收官（2026-10-17）**。字母序走完 `affection` ✓ `bond` ✓ `brain`（顶层 + `read/`）✓
  `creep` ✓ `digest` ✓ `media` ✓ `mmt` ✓ `promptkit` ✓ `rag` ✓ `random_events` ✓ `session` ✓
  `worldtime` ✓ —— 只剩 **`core` 根下 `display.py` / `streaming.py`**（作者看过了: 两个都没 bug）。
  每包做法固定：① 剥装饰符号 ② 顶部 docstring 重写 ③ 去"用户裁/拍板" ④ 顺手修同类类型错
  ⑤ 值得的写 `<pkg>/.md` ⑥ 两域测试 + ruff + 一个提交。
  有两处**按作者要求收窄了范围**：`digest` / `media` / `mmt` / `promptkit` 只修类型 + 顶部 docstring
  （包内注释清理**没做**）· `webgui/bond/` 只修类型（注释与结构不动）。
- **线 B 还没做**（都可选）：`digest` / `media` / `mmt` / `promptkit` / `webgui/bond/` 的**注释清理**
  （这几包只动了 docstring 与类型）· `webgui/bond/` 剩下的 Pylance 报错（作者会按文件贴过来，我只修类型）·
  文档那一趟（`README.md` / `TODO.md` / `CLAUDE_OPTIMIZE.md` / `DESIGN_BRAIN.md` / `docs/*` 里的**旧包名**
  —— 作者的话是"产品没定稿，README 等最后定稿"）· `webgui/store.DEFAULTS` 与各领域默认值"两处写" ·
  上面 §5b 第 17 条那批 flaky 用例（改成"等队列排空"而不是 `sleep(0.2)`）· `core/brain/read/{channels,like}.py`
  与 `realtime.py` 剩下的 `now: object`（要根治得先给 `age.py` 一个 `TsLike`，作者说往后放）。

## 7. 作者口述的下一步方向（2026-10-17；与 §2 那张"记忆层的活"不是一回事）

1. **前向导**（首次使用向导，前端）—— 把"填 API key / 选角色 / 选世界 / 试跑一句"收成一条龙；
   注意 `settings.toml` 的唯一读入口是 `infra/settings.py`，向导要写配置就得走它（别自己 open 文件）。
2. **打包 exe** —— 主要待解：`assets/` 与 `config/` 的体积与只读根（`paths.RESOURCE_ROOT` vs `APP_ROOT`）、
   Python 运行时与 `node`（前端无构建步骤，但 `tests/webgui/js/*.test.js` 只在开发期用）、
   `LM Studio / embedding 服务` 这类外部依赖在别人机器上没有时怎么降级（今天已经全链路可降级）。
3. **架构优化** —— 已知的可动点：`webgui/bond/`（3550 行, 11 文件）的模块边界 · `digest/material.py`（877 行）
   的料函数分组 · `core/mmt/engine.py`（2069 行）的循环与状态 · `contract/` 那 11 个平铺件
   （曾裁"不分族", 若重开要先读 `docs/EXEC_RENAME.md` §8 的口径）。
