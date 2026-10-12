# PROCEED.md — **接续用**（整篇覆盖写；上一版见 git 历史）

> 位置（2026-10-12 夜 / 第三版）：**树干净 · 最新 `a7d79c8` · ahead 2（未推）**。
> 这一段做完了四件事：① **"她怎么认识人"整条线**（换写法 → 出厂物化 → brain 段注入 →
> `inspect` 退役 → 规则书【回忆】专段）；② ⭐ **召回的"形式表 + 唯一前门"**
> （`core/brain/read/modes.py`）；③ ⭐ **P19 变三段**（「你想着「名字」」/「你想着「时间」那阵子」/
> 「你想起的事」）+ **钥匙与空手**；④ **走法接口**（`walk.bfs` 找同类 / `walk.chain` 深挖,
> ⛔ **未接线**）+ `mmt_send_media` **封印** + `look` 的 **`entity` 筛选轴**。
> ⏭ **下一步 = entity 常驻 + entity 名表**（见 §2①，会改她看到的东西 ⇒ 先报形式）。

---

## 0. ⭐ 召回与 `look` 的 API（2026-10-12 定；用户: "字符串/参数格式随你定, 定完了告诉我"）

```python
from core.brain.read.modes import recall, recall_with_keys, render_section, mode_of, MODES

cands      = recall(store, ctx, *, mode="turn", k=None, weights=None)
cands, keys = recall_with_keys(store, ctx, *, mode="name")     # ⭐ 带"钥匙"
seg        = render_section(cands, *, mode="name", key="阿露", empty_ok=True, **渲染参数)
```

| 参数 | 规矩 |
|---|---|
| `mode` | **形式名**（`MODES` 的键）。今天三个：`name`（set,「你想着「X」」）· `when`（set, 时间窗）· `turn`（rank, 六路兜底） |
| `k` / `weights` | ⚠️ **只有 rank 型认识**；给 set 型传 ⇒ `ValueError` |
| `key` | ⭐ **这一段的"钥匙"** = 触发它的那个词（老师用的写法 / 扫到的时间词）—— 填进 `{key}` 槽; ⛔ 带槽没值 ⇒ **当场炸** |
| `empty_ok` | `False` = **这次的"空"是被别的段去重拿走了**（不是想不起来）⇒ ⛔ 一个字都不印（印了是假话） |
| `cap` / `budget` | 渲染层的"摆几条 / 多长"（互斥, `cap` 优先）—— ⛔ 不是召回层旋钮。P19 **每段**各自读 `[recall].turn_budget`（1000） |
| 未知名 | `KeyError` + 可用清单（⛔ 不静默回落缺省） |

⭐ **加一个形式 = `MODES` 表里加一行**（⛔ 别在执行器里写 `if mode == …`）：
```python
"when": Mode(shape=SHAPE_SET, anchors=("when",), payload_from=PAYLOAD_WHEN,
             header="【你想着「{key}」那阵子——浮上来的是这些（用不用由你判断）】",
             empty="【你想着「{key}」那阵子——那几天的事，一时没想起来】"),
```
`Mode` 字段: `shape / spec / anchors / payload_from / skip_ids / kinds / order / header / hint / empty`。
⛔ **没接线的形式不许先写进表**（空行 = 假承诺）—— 所以 `near`/`echo` **不在表里**（它们的走法
接口在 `walk.py`，见 §1）。

**`mmt_look` 的三格筛选轴（AND, 2026-10-12 加 `entity`）**：
`{"action": "mmt_look", "payload": {"entity": "阿露", "clue": "便利屋 && 苔藓", "when": "上个月"}}`
· `entity` → `entities.find_entity`（**只归一格式, 不做近似匹配**; miss/ambiguous 不猜 ⇒
`LOOK_EMPTY_ENTITY` 且**不计数**）⇒ `find` 的 entity 锚 = **他车道上全部**
· ⛔ **不印 `entity.text`**（"我眼里的他们"已常驻 brain 段, 再印一遍是同一份内容两次进上下文）
· 三格**至少给一个**; 三格都空 ⇒ `ContractError`。

**设计依据**（为什么分形式、不混分; 六类范式 + 出处）= `docs/DESIGN_RECALL_MODES.md`。

---

## 1. 召回与走法的地图（`core/brain/read/` · 12 文件 · ~3600 行）

```
写侧                                  读侧 core/brain/read/
digest/material.py ─┐
rag/brain.py ───────┴→ recall.py::recommend_candidates / recall_subgraph   现役（R2 的料 + rag）
                      → render.py::render_cognition_list                   现役（relate / cognize 的料）

MMT 引擎 ─┬→ modes.recall_with_keys(mode="name"/"when") → find.find(…)
          │                                            → render.render_section ⭐ P19 前两段
          ├→ modes.recall(mode="turn") → like.like(spec="turn") → render.render_section ⭐ 第三段
          ├→ render.render_character_view                                        ⭐ brain 段
          └→ recall_ledger.log_read · recall_config（台账 + 旋钮）

`mmt_look` ─→ find.find({entity|title|text|when} = AND) → render.render_candidates（她主动翻）
⛔ 未接线: walk.py（BFS 找同类 / DFS 深挖 —— 接口 + 13 条守门 + 13 变异靶都在, **没有调用方**）
⛔ 未接线: channels.py + channel_impl.py + compose.py（五链路 A–E + 合成层; 只有 experiments 在跑）
⛔ legacy: recall.py::recall_episodes（P19 已改用 like/modes; 只剩测试在调）
```

| 文件 | 行 | 干什么 | 现役 |
|---|---|---|---|
| `modes.py` | ~300 | ⭐ **形式表 + 唯一前门**（`recall` / `recall_with_keys` / `render_section` / `describe`） | ✅ engine（P19 三段） |
| `like.py` | 718 | 相似召回：`PARTS`（六路）+ `SPECS`（档位）+ `like()` + `build_ctx` | ✅ engine |
| `find.py` | 425 | 定向寻找：五锚 `title/entity/group/when/text` **AND** ⇒ 全部（不漏即正确） | ✅ engine（`look`） |
| `walk.py` | ~300 | ⭐ **走法接口**：`bfs`（找同类: 纵向参数/广度闸 `width`）+ `chain`（深挖: 来路+方向, 防环） | ⛔ **未接线** |
| `pack.py` | 136 | 候选形状 `Candidate` + 共用命中面 `body_of` + 台账行 | ✅ 包内共用 |
| `render.py` | ~830 | 一切注入视图（brain 段 / 召回段 / `look` 结果 / 认知料 / 三档空手 + 名字空手） | ✅ engine + digest |
| `recall_config.py` | 142 | `[recall]` 旋钮（`like_k`/`sim_k`/`turn_budget`/`half_life`…） | ✅ |
| `recall_ledger.py` | 174 | 读路径台账（`log_read`）+ 合成台账（`log_compose`, 那层没接线） | 半 |
| `recall.py` | 396 | 旧三通道 + 一跳（`recommend_candidates` / `recall_subgraph` 仍现役） | 半 |
| `channels.py`+`channel_impl.py` | 747 | 五链路（A 强度先验 / B 情绪 RAG / C 地点 / D 既视感 / E 认知碎片） | ⛔ 未接线 |
| `compose.py` | 345 | 五链路合成（归一 + noisy-or + 名次门槛）· `recall_now()` | ⛔ 未接线 |

⚠️ 四条事实别踩：`turn` 档 `semantic` 权重 = **0**（**召回不靠语义**）· `find` 的 `entity` 锚是
**set 语义**而 `like` 的 `name` 路**只加成不作准入**（所以两段会撞同一条 ⇒ engine 跨段去重必需）·
「提到了谁」是**字面子串**命中（`cf in query`）⇒ 保留号会把整条河捞出来（`RESERVED_TRIGGERS`）·
`walk.bfs` 的**渲染预算不是广度闸**（见 §4）。

---

## 2. 下一步（每件一个提交 + 用户审一关；动代码前**先报形式**）

### ⏭ ① entity 常驻 + entity 名表（下一件；会改她看到的东西）
用户 2026-10-12: *"接下来就是你说的那些加 entity 常驻以及 entity 名表了"*。
今天的状态与要定的三件事：
- ⚠️ **只有 `text` 非空的 entity 才进「我眼里的他们」** ⇒ 真机 `x0002 杂草屋` / `x0003 夏莱`
  （没人给它们写过看法）**根本不出现**; 而"地方/组织"混在"他们"里措辞也不对。
- 要定 **谁常驻**（全部 entity / 只有车道的 / 只有 text 的）· **印什么**（主名 / 别名 / 有没有一行说明）·
  **放哪**（拆出「我知道的地方」还是并进「我眼里的他们」）。
- **名表**的作用 = 给她一张"她认识的名字"清单（她的 `look(entity=…)`、`noticed`、提人时都靠它
  对齐地址）; 要定**印不印别名**（别名 = "她可能怎么写他"的唯一真源，见 §6）· 与 ② 是否重复。

### ⏭ ② `walk` 接线（用户: *"这两个先都不接"* ⇒ **等她说**）
接线的三缺（`walk.py` 文件头也写着）：① `set` 形状的执行器（今天只有 `find`; 要么给它加
"按 id 集合"的锚, 要么 `Mode.executor` 表驱动）② `near`/`echo` 两行形式 + `Mode.order` 加取值
`"near"` ③ **`chain` 的用户还没定**（最自然是 `look` 的第三种形态"我为什么这么想"）。

### ⏭ ③ 五链路 A–E：**改造**（各自成段）还是**归档** —— ⛔ 要用户拍。
### ⏭ ④ 扫尾（低价值）：`emo_span`/`emo_int` 退契约 · `entities.candidate_table` 死代码 ·
`graph.py:76` 那句"`contradicts`/`evolved_from` 零写者"**已过时**（P7-2 起有写者）。
### ⏭ ⑤ 台账收口（真机前）：`mmt_recall` 只有总 `chars=` ⇒ 想加**每段字数**与**召回耗时 ms**
（它同步跑在 `round_messages` 之前, 直接进 TTFT）。

### 押后（不做, 除非用户点名）
P19 的 cap + 标题清单 · `specificity` 加权 · `part_axis` · BFS 对照台 · `noticed` 带想法 ·
`emotion`/`place`/`mood` 进图（= `mood` 形式的前置）· `entities.candidate_table` ·
interperson 渲染要不要印档案显示名 · `look` 的"标题候选台"。

### ⭐ 真机观察清单（用户说"等完全弄完我会从头跑真机"）
| 看什么 | 判据（预设） |
|---|---|
| 三段实际长度 | 撞满 3000 字符 ⇒ 该分预算; 平均 < 600 ⇒ 预算给多了 |
| 空手占比（`grep 'when(empty)\|name(empty)'`） | 每轮都空 ⇒ 触发面太宽 |
| 她会不会**过度汇报**"想不起来" | 多 ⇒ 措辞要收（那就不是信息, 是噪声） |
| `noticed` 写不写 / 抄得对不对 | 沿用 N5b 口径 |
| `look` 用了几次 | 三段摆得多 ⇒ 她**该少翻**才对（P19 与 `look` 互补） |
| `ms=`（④ 做完后） | 召回耗时有没有随库长线性恶化 |

---

## 3. 已裁（2026-10-12，用户）—— 别再翻案

- ⭐ **P19 三段的六条口径**：**每段各自** 1000 字符 · 段序 `name → when → turn` ·
  **保留号不触发**名字段 · 名字段**不挂** `noticed` 提示 · `when` **只查 exact 不放宽**
  （*"可以让 LLM 干脆自己多开区间搜"*）· 段头**印钥匙**、**空手也说话**（措辞限定在钥匙上、
  瞬时; ⛔ 不写"一片空白/良久"）。
- ⭐ **`mmt_send_media` 封印**（`a0eb749`）：媒体管线未接、端到端 no-op ⇒ prompt 上收掉
  （`ActionSpec.in_prompt=False`）; **解析/执行照旧**。恢复 = 那一格改回 `True` + 同批改回
  规则书 3 处 / 环境 2 处 / 示例 + 刷夹具。
- ⭐ **不做 `inspect entity`**：`entity.text` 以后常驻 ⇒ "看档案"这个动作没有信息增量;
  `entity` 的正确定位是**筛选轴**（`look(entity=…)`, 已落 `a7d79c8`）。
- **`echo` / `mood` 不做**：`echo` 的实时语义路与"P19 不吃后端"冲突（`akin` 边是它的离线版）;
  `mood` **无料**（情绪不在图里）。`precious`/`recent`/`notes`/`person_near` 也都**不做**
  （与常驻注入或既有形式重复）。
- **`一行前瞻`：撤了**（`30fe6b6`）⇒ 内容行**到达即交付**。
- **`self` 出厂值：写了**（`9379a91`）。⚠️ 引擎仍是"只填空 text" ⇒ 真档 `x0000` 已有 R3 那份,
  **新世界线才生效**（用户: "先不管"）。
- **非便利屋68 的角色：不维护**（用户: *"以后除了便利屋68相关的都不打算维护, 那几位 sprite 都没"*）。
- **`entity.text` 的演化通道**（digest 侧没有写者）= **以后再说**。

---

## 4. ⚠️ 会**静默**出错的那几处（改召回/契约时必看）

- **契约 / 规则书 / 示例三处必须同批改**（漂过两次）。守门 = `test_mmt_look_action.py::
  test_rulebook_section_and_the_contract_say_the_same_thing`。改完任意进 system 的内容 ⇒
  **刷 promptkit 夹具**（`PROMPTKIT_UPDATE_FIXTURES=1 pytest tests/core/test_promptkit_baseline.py`）+ 人审 diff。
- **封印位只收 prompt, 不收解析**：`in_prompt=False` 的动作**仍在注册表**（`action_names()`）——
  ⛔ 别把 `prompt_action_names()` 与 `action_names()` 合并（合并后她万一写了就认不出）。
- **位置实参串位**：`look_header(entity, clue, when, …)` / `look_fn(entity, clue, when)` 全是字符串,
  一律**关键字实参**（`test_wiki_render` 那次红就是这么来的）。
- **`names._pick` 的列表**：作者三种写法都在用——只认一种会**静默**切出垃圾别名（**已修**, 别回退）。
- **YAML 折行**：`text` 用 **`|`**; `>` 会把换行变空格（汉字之间由 `_fold_layout` 兜, 拉丁旁边兜不掉）。
- **直接调 `_look_result` / `_recall_notes` 的测试必须钉 `eng._turn_now`**（否则 `上周` 随真实日期漂）。
- **⛔ 假旋钮**: 加配置格之前先问"有没有第二个取值"。
- **⛔ 带槽不填 ⇒ 当场炸**（`render_section` 的 `{key}`; 用 `str.replace` 不用 `format` —— 文案里有 JSON）。
- **⛔ 去重掏空 ≠ 空手**：跨段去重会把后一段掏空, 那时印"一时没想起来"是**假话** ⇒ `empty_ok=False`。
- **测试夹具别借保留号**（`x0000`/`x0001`）：借了会被 `skip_ids`/`RESERVED_TRIGGERS` 整条剔掉,
  用例**红得莫名其妙**; 想验保留号就得自己按 `entities.SELF_ID/SENSEI_ID` 建 + **自验前提**。
- **时间词扫句子要最长优先**（「上上周」不许被「上周」截走）, 且**未过完的窗口不算旧事**
  （今天/本周/本月/今年）—— 两条都有变异靶。
- **渲染预算不是广度闸**：一个类 30 个成员时, 1000 字符挡得住她看到的长度, 挡不住
  **两跳的扇出平方放大**与**台账那一行** ⇒ `walk.bfs(width=…)`（缺省不裁, 由形式给值）。
- **`walk.chain` 的已访问集是安全件**：`contradicts` 对称 ⇒ 环在真图里可能, 少了它**不是慢, 是停不下来**
  （标记要在 **push** 时做; 验证脚本给子进程加了 `timeout`, 卡住也算抓住）。
- **变异靶子要选对**：`check_turn` 那层用例**管不到**流式暂存; 靶子选错 ⇒ 变异"绿"其实是没验到。

## 5. 流程纪律与环境（踩过的都在这儿）

- 每件一个提交 + **用户审一关**; CJK commit 用 `git commit -F .testtmp/<file>.txt`;
  **stage 显式路径**; ⛔ 不用 `ruff --fix`; ⛔ 不 commit `illustration.yml`; 真机数据**只读**。
- **PROCEED.md 统一最后写**（用户 2026-10-12 裁）—— 不再夹在每件里单独开提交。
- 测试: `python -m pytest … -q --basetemp=.testtmp/<名字>` —— ⚠️ **目录必须预建**,
  否则上千个 `PermissionError`（看着像代码全炸, 其实是 tmp 根建不出来）。
- **git 推送必须走代理**（直连被 reset）:
  `git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin master`。
- 改 `core/mmt/engine.py` 的 import ⇒ `SPLIT_API_UPDATE=1 pytest tests/core/test_split_safety.py` + 人审快照 diff。
- LM Studio（`lms server start`, 端口 1235）只在 **digest 语义召回**时要; 不在就静默降级
  （`digest_embed fn=none`）。

## 6. 口径（用户裁过, 不许悄悄推翻）

- 召回**分形式、不混分**（要总序就混名次 RRF）; 形式名按**意图**, 不按编号。
- `interperson` 的**键 = 她的叫法**; `self` / `sensei` 是**保留键**（按 id 认, ⛔ 不搜 profile）。
- **不设硬上限**（entity 不裁; 计数只做建议）; `look` 展示 cap 5。
- **她只知道自己眼里的他们**（⛔ 不读别人的客观档案 —— D 笔退役 inspect 的理由）。
- `find` = 不漏即正确; 线索 = **字面**布尔式（**零正则**）; 时间两族（`last`/`back`）;
  时间轴 = **现实日/现实年**。
- **独占口径**: `look` / `trigger` = **唯一操作行**（话可前置）。
- **别名（`aliases`）是"她可能怎么写他"的唯一真源**，三条路共用同一张面
  （`entities.surface_forms`）：`look(entity=)` **精确等价** · P19 的 `name` 段**子串** ·
  digest 认人（`#entity:`）**精确等价**。⚠️ 短别名会在 P19 那条路上**误触发**;
  而 `look` 那条路**认不出别名的变体**（⛔ 不猜）—— 想让某条路认得出, 就把那个写法写进 `aliases`。

---

## 7. 这一段提交链（`569a9d8` 之后 · 全部已验证）

| 提交 | 一句话 |
|---|---|
| `cbdbe3e` | ⭐ **召回形式表 + 唯一前门** `modes.recall(mode=…)` |
| `569a9d8` | PROCEED 第二版 + `docs/DESIGN_RECALL_MODES.md` |
| `fe61c15` | **`name` 接线** ⇒ P19 两段（跨段去重 · 保留号不触发 · 每段 1000） |
| `0090a8a` | PROCEED 第二版收口 |
| `78b85e9` | ⭐ **钥匙 + 空手**（`recall_with_keys` / `Mode.empty` / `{key}` 槽 / `empty_ok`） |
| `c0aa9f8` | ⭐ **`when` 形式**（`scan_when` 句子扫时间词 · 只 exact 不放宽 · 三段） |
| `7152ede` | **`walk.bfs`** 接口（找同类; ⛔ 未接线）+ 8 条守门 + 6 变异靶 |
| `b8d5289` | `walk.bfs` 补**广度闸 `width`**（大群不许灌爆段/台账） |
| `43a84cc` | **`walk.chain`** 接口（深挖/DFS: `evolved_from` + `contradicts`; 来路+方向+防环） |
| `a0eb749` | **封印 `mmt_send_media`** 的 prompt 注入（`ActionSpec.in_prompt`） |
| `a7d79c8` | **`look` 的 `entity` 筛选轴**（三格 AND; ⛔ 不印 `entity.text`） |
