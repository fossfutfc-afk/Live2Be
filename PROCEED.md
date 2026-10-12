# PROCEED.md — **接续用**（整篇覆盖写；上一版见 git 历史）

> 位置（2026-10-12 夜 / 第二版）：**树干净 · 最新 `fe61c15`**（推送状态见文末）。
> 这一段做完了三件事：① **"她怎么认识人"整条线**（换写法 → 出厂物化 → brain 段注入 →
> `inspect` 退役 → 规则书【回忆】专段 → 文档收口 + 全量 1403 passed）；
> ② ⭐ **召回的"形式表 + 唯一前门"**（`core/brain/read/modes.py` —— 六路加权从唯一外部 API
> 降级为"`rank` 形状里的一行"）；
> ③ ⭐ **`name` 形式接线到 P19** ⇒ **P19 现在是两段**（「关于他们的」（确定命中）+
> 「你想起的事」（六路兜底）），每段各自吃 1000 字符预算。
> ⏭ **下一步 = 下一批召回形式**（见 §2）。

---

## 0. ⭐ 召回 API 的格式（2026-10-12 定；用户: "字符串/参数格式随你定, 定完了告诉我"）

```python
from core.brain.read.modes import recall, render_section, mode_of, MODES, DEFAULT_MODE

cands = recall(store, ctx, *, mode="turn", k=None, weights=None) -> list[Candidate]
seg   = render_section(cands, *, mode="turn", cap=None, budget=None,
                       char_name="", char_aliases=(), now=None) -> str
```

| 参数 | 规矩 |
|---|---|
| `mode` | **形式名**（`MODES` 的键）。今天两个：`"name"`（set, 「关于他们的」——⭐ **已接线到 P19 第一段**）· `"turn"`（rank, 「你想起的事」= 从前的 `like(spec="turn")`, **逐条同**, P19 第二段） |
| `k` / `weights` | ⚠️ **只有 rank 型认识**；给 set 型传 ⇒ `ValueError`（⛔ 不静默忽略） |
| `cap` / `budget` | **渲染层**的"摆几条 / 多长"（互斥, `cap` 优先）—— ⛔ 不是召回层的旋钮。⭐ P19 两段**各自**读 `[recall].turn_budget`（1000） |
| 返回 | 两种形状**同一个类型**：rank 型 ≤ k 条（降序）；set 型 = 命中**全部**（新→旧, **不裁**） |
| 未知名 | `KeyError` + 可用清单（⛔ 不静默回落缺省） |

⭐ **加一个形式 = `MODES` 表里加一行**（⛔ 别在执行器里写 `if mode == …`）：
```python
"when": Mode(shape=SHAPE_SET, anchors=("when",), payload_from=…, header="【那阵子的】")
```
`Mode` 字段: `shape / spec / anchors / payload_from / skip_ids / kinds / order / header / hint`。
⛔ **故意没加** `admit` / `cap` 两格（今天每种形状只有一种准入规则; 截断归渲染层）——
加格子要等真有第二种规则, 否则是配了没人读的**假旋钮**。
⭐ **加了的只有 `skip_ids`**（`name` 行用它剔保留号）—— 它不是旋钮, 是**一行形式的固有
属性**（"谁的叫法能触发这一段"），而且真有第二取值。
⛔ **没接线的形式不许先写进表**（空行 = 假承诺）。

**设计依据**（为什么分形式、不混分; 别人怎么做的六类范式 + 出处）= `docs/DESIGN_RECALL_MODES.md`。

---

## 1. 召回包地图（`core/brain/read/` · 11 文件 · ~3200 行）—— 回召回的起点

```
写侧                                  读侧 core/brain/read/
digest/material.py ─┐
rag/brain.py ───────┴→ recall.py::recommend_candidates / recall_subgraph   现役（R2 的料 + rag）
                      → render.py::render_cognition_list                   现役（relate / cognize 的料）

MMT 引擎 ─┬→ modes.recall(mode="name") → find.find({"entity":…})  → render.render_section  ⭐ P19 第一段
          │   （⛔ 保留号 x0000/x0001 不触发 —— `Mode.skip_ids`）
          ├→ modes.recall(mode="turn") → like.like(spec="turn") → pack.Candidate
          │                                                   → render.render_section   ⭐ P19 第二段
          ├→ render.render_character_view                                                ⭐ brain 段
          └→ recall_ledger.log_read · recall_config（台账 + 旋钮）

⛔ 未接线: channels.py + channel_impl.py + compose.py（五链路 A–E + 合成层; 只有 experiments 在跑）
⛔ legacy: recall.py::recall_episodes（P19 已改用 like/modes; 只剩测试在调）
⚠️ `render.render_recall_block`（= turn 档文案的老门面）**留着**（render 的公开函数 + 测试在用），
   但 **engine 不再 import 它**（两段统一走 `render_section`）—— api 快照那一行已换。
```

| 文件 | 行 | 干什么 | 现役 |
|---|---|---|---|
| `modes.py` | 215 | ⭐ **形式表 + 唯一前门**（`recall` / `render_section` / `describe`） | ✅ engine（P19 两段） |
| `like.py` | 718 | 相似召回：`PARTS`（六路）+ `SPECS`（档位）+ `like()` + `build_ctx` | ✅ engine |
| `find.py` | 425 | 定向寻找：五锚 `title/entity/group/when/text` **AND** ⇒ 全部（不漏即正确）+ `compile_clue` | ✅ engine（`look`） |
| `pack.py` | 136 | 候选形状 `Candidate` + **共用命中面** `body_of` + 台账行 | ✅ 包内共用 |
| `render.py` | 803 | 一切注入视图（brain 段 / 召回段 / look 结果 / 认知料 / 三档空手文案） | ✅ engine + digest |
| `recall_config.py` | 142 | `[recall]` 旋钮（`like_k`/`sim_k`/`turn_budget`/`half_life`/`freshness_floor`…） | ✅ |
| `recall_ledger.py` | 174 | 读路径台账（`log_read`）+ 合成台账（`log_compose`, 那层没接线） | 半 |
| `recall.py` | 396 | 旧三通道 + 一跳（`recommend_candidates` / `recall_subgraph` 仍现役） | 半 |
| `channels.py`+`channel_impl.py` | 747 | 五链路（A 强度先验 / B 情绪 RAG / C 地点 / D 既视感 / E 认知碎片） | ⛔ 未接线 |
| `compose.py` | 345 | 五链路合成（归一 + noisy-or + 名次门槛）· `recall_now()` | ⛔ 未接线 |

⚠️ 三条事实别踩：`turn` 档 `semantic` 权重 = **0**（真机 916ms → 2ms 的取舍 ⇒ **召回不靠语义**）；
`find` 的 `entity` 锚是 **set 语义**（车道上全部），而 `like` 的 `name` 路**只加成、不作准入**
⇒ 所以两段**会撞同一条**（engine 层跨段去重是必需的，不是优化）；
⭐ 「提到了谁」是**字面子串**命中（`cf in query`）⇒ 保留号（她自己/老师）会把整条河捞出来
（`RESERVED_TRIGGERS` 就是为它设的）。

---

## 2. 下一步（每件一个提交 + 用户审一关）

### ⏭ ① 下一批形式（落一个加一行）
`when`（时间窗, set）· `echo`（既视感, rank）· `mood`（情绪, rank）· `near`（图上相邻, set）。
清单与判据见 `docs/DESIGN_RECALL_MODES.md §4`。
⚠️ **每落一个之前先报"判据 + 触发时机 + 抬头 + 预算"**（会改她看到的东西 ⇒ 先审后动）。
⚠️ **触发时机要单独拍**: 今天 `name` 是"**玩家这句**提到了名字"; 而 `echo` / `mood` 那类
更该由"她上一句 / 当前情境"触发 —— 但引擎现成的料只有玩家这一句（`RecallCtx.query`）。
⚠️ P19 两段已经能撞满 **2×1000** 字符 —— **加第三段之前先定"谁有保底名额"**。

### ⏸ 已裁（2026-10-12，用户）—— 别再翻案
- ⭐ **P19 两段的四条口径**（`fe61c15`）: **每段各自** 1000 字符（`[recall].turn_budget`）·
  段序「关于他们的」在前 · **保留号不触发**名字段（她自己/老师）· 名字段**不挂**
  `{"noticed": …}` 提示（两段同屏不重复一句话; 兜底段挂着）。
- **`一行前瞻`：撤了**（`30fe6b6`）⇒ 内容行**到达即交付**。
- **`self` 出厂值：写了**（`9379a91`）。⚠️ 引擎仍是"只填空 text" ⇒ 真档 `x0000` 已有 R3 那份,
  **新世界线才生效**（用户: "先不管"）。
- **非便利屋68 的角色：不维护**（用户: *"以后除了便利屋68相关的都不打算维护, 那几位 sprite 都没"*）
  ⇒ 含 `hinomiya_chinatsu` 那一行、含没卡的几位（`火宫千夏`/`小鸟游星野`/`龙华妃咲`/`羽沼真琴`）。
- **`entity.text` 的演化通道**（digest 侧没有写者）= **以后再说**。

### 押后（不做, 除非用户点名）
P19 的 cap + 标题清单 · `look` 给 `entity` 锚（"关于阿露的全部"）· `specificity` 加权 ·
`part_axis` · BFS 对照台 · `noticed` 带想法 · `emotion`/`place`/`mood` 进图 ·
`emo_span`/`emo_int` 退契约 · `entities.candidate_table` 死代码 · interperson 渲染要不要印档案显示名 ·
五链路 A–E 是**改造**（各自成段）还是**归档**。

---

## 3. 已落地的链（这一段 18 笔, 全部已验证 · 远端同步）

| 提交 | 一句话 |
|---|---|
| `365a0df` `eace2ab` `9f0a7af` | **A/A2 笔**：`interperson` 换写法（值 = 她的看法）· 换 YAML · 作者改写立场 + **折行语义**（换行=排版, 空格=内容） |
| `ed4d48d` | **B 笔**：出厂物化 —— `ensure_entities(stances=…)` 把表里的立场装进 `entity.text` |
| `e6e11c5` `a432ee8` | **C 笔**：brain 段添「我眼里的他们」+「我是这样看自己的」；盒A 撤 `interperson` 块（10→9）；物化**提前到开会话** |
| `cb6907d` `3330809` | **C2 笔**：修 `other_names` 列表 bug · 6 个角色的 `SIG~friends` 逐字搬进表 + 删副本 |
| `90af157` | **D 笔**：`mmt_inspect_character` 退役（注册/执行器/门控/自愈/`void` 分支/契约重编号） |
| `4013cd9` | **规则书**：【回忆】专段 + 删 `关键边界` 4 行 + 守门"规则书与契约不许漂" |
| `19e598b` | **E 笔**：文档收口 + **全量 1403 passed** + 修两条跨文件 flake |
| `30fe6b6` `9379a91` | 撤前瞻 · 作者写上的 `self` |
| `7cfcda2` `4d93258` | PROCEED 推送命令改代理 · CLAUDE.md §7/§2 校正 digest **7 轮** |
| `cbdbe3e` | ⭐ **召回形式表 + 唯一前门** `modes.recall(mode=…)` |
| `fe61c15` | ⭐ **`name` 接线到 P19** —— 两段（名字段在前 + 兜底段在后）· 跨段去重 · 保留号不触发 · 每段 1000 字符 · 变异 5 靶全红 |

---

## 4. ⚠️ 会**静默**出错的那几处（改召回时必看）

- **契约 / 规则书 / 示例三处必须同批改**（今天漂过两次）。守门 =
  `test_mmt_look_action.py::test_rulebook_section_and_the_contract_say_the_same_thing`。
- **`names._pick` 的列表**：作者三种写法都在用（逗号串 / 行内 list / 块 list）——
  只认一种会**静默**切出垃圾别名（名字车道 + `find_entity` 一起失灵）。**已修**, 别再回退。
- **YAML 折行**：`text` 用 **`|`**（换行无痕）; `>` 会在解析时把换行变空格（汉字之间由
  `_fold_layout` 兜, 拉丁旁边兜不掉）。**行内空格是内容, 不许动**。
- **直接调 `_look_result` 的测试必须钉 `eng._turn_now`**（否则回落 `datetime.now()`,
  `上周` 随真实日期漂 —— 踩过一次时间炸弹）。
- **⛔ 假旋钮**: 加配置格之前先问"有没有第二个取值"; 没有就别加（`test_no_threshold_knobs_left`）。
- **变异靶子要选对**: `check_turn` 那层用例**管不到**流式暂存（`WHOLE_TURN_ACTIONS`）——
  它有专门的流式用例; 靶子选错 ⇒ 变异"绿"其实是没验到。
- **测试夹具别借保留号**（`fe61c15` 踩到）: 测试里造 entity 若不写死 id, `next_id("x")`
  会把 `x0001`（= 老师）分给它 ⇒ 名字段被 `skip_ids` 整条剔掉, 用例**红得莫名其妙**;
  反过来, 想验"保留号不触发"就必须**自己按 `entities.SELF_ID/SENSEI_ID` 建**那两行
  （测试档里引擎不一定物化过它们 —— 那一步在脑注入那次）+ **自验前提**（`named` 真命中了）。

## 5. 流程纪律与环境（踩过的都在这儿）

- 每件一个提交 + **用户审一关**; CJK commit 用 `git commit -F .testtmp/<file>.txt`;
  **stage 显式路径**; ⛔ 不用 `ruff --fix`; ⛔ 不 commit `illustration.yml`; 真机数据**只读**。
- 测试: `python -m pytest … -q --basetemp=.testtmp/<名字>` —— ⚠️ **目录必须预建**,
  否则 **1403 个 `PermissionError`**（看着像代码全炸, 其实是 tmp 根建不出来）。
- **git 推送必须走代理**（直连被 reset）:
  `git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin master`。
- 改进 system 的内容 ⇒ **刷夹具 + 人审 diff**; 改 `core/mmt/engine.py` 的 import ⇒
  `SPLIT_API_UPDATE=1 pytest tests/core/test_split_safety.py` + 人审。
- LM Studio（`lms server start`, 端口 1235）只在 **digest 语义召回**时要; 不在就静默降级
  （`digest_embed fn=none`, 候选退化成字面命中 —— grep 这行能分辨）。

## 6. 口径（用户裁过, 不许悄悄推翻）

- 召回**分形式、不混分**（要总序就混名次 RRF）; 形式名按**意图**, 不按编号。
- `interperson` 的**键 = 她的叫法**; `self` / `sensei` 是**保留键**（按 id 认, ⛔ 不搜 profile）。
- **不设硬上限**（entity 不裁; 计数只做建议）; `look` 展示 cap 5。
- **她只知道自己眼里的他们**（⛔ 不读别人的客观档案 —— D 笔退役 inspect 的理由）。
- `find` = 不漏即正确; 线索 = **字面**布尔式（零正则）; 时间两族（`last`/`back`）;
  时间轴 = **现实日/现实年**。
- 独占口径: `look` / `trigger` = **唯一操作行**（话可前置）。
