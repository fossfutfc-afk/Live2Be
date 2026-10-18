# PROMPT_SAMPLES — 每个调用点实际发出去的提示词

> **状态**：2026-10-17 对照代码逐点校准。用途：一眼看清"一次调用里 system / user 各是什么、
> 按什么顺序拼、每段来自哪个文件"。
>
> **真源永远是代码**，本文只是它的读物：
> 盒清单 = `core/promptkit/box.py` 的 `DOMAIN_BOXES` · 每轮装配 = `core/promptkit/tail.py` 的
> `round_messages` · 轮次与料 = `core/digest/rounds/__init__.py` 的 `ROUNDS`。
>
> 与相邻文档的分工：`docs/PROMPT_HOMES.md`（**住在哪**）· `docs/DESIGN_PROMPTKIT.md`（**为什么这么装**）。
> `docs/PROMPT_INJECTION_MAP.md` 停在 2026-09-07（digest 六轮没进过那张表），**注入结构以本文为准**。
>
> **本文的写法**：规则书 / 契约这类"整份文件"的东西**只给链接**，不复制正文；
> 引擎现算的料给出**形状 + 一段样例**（标注「样例」，不是真机数据）。

---

## 0. 总表

| 调用点 | 何时 | system | user | 输出 |
|---|---|---|---|---|
| **mmt** 每轮 | 同步（玩家在等） | 盒 A（10 块）+ 记忆段 | 注记们 + 任务卡 + 玩家这一句 | 行流 JSONL |
| **vn** 每场 | 同步 | 盒 B（10 块） | 注记们 + 场卡 + 选项文本 | 记录流 JSONL |
| **memo** 备忘录段 | 不单独调用 | —（随记忆段进 system） | — | — |
| **annoemo** 情绪标注 | 异步 | [`emotion_annotate.md`](../llm/prompts/emotion_annotate.md) / [`emotion_text_annotate.md`](../llm/prompts/emotion_text_annotate.md) | 逐句编号 / 逐条记录 | 标签数组 |
| **annoplace** 地点标注 | 异步 | [`place_annotate.md`](../llm/prompts/place_annotate.md) / [`place_resolve.md`](../llm/prompts/place_resolve.md) / [`place_variant.md`](../llm/prompts/place_variant.md) | 逐句编号 / 原文 / 图库候选 | 数组 / 单个键 |
| **digest** ⓪①③⑥⑦ | 异步（MMT 每 25 轮 / bond 闭环） | [`digest_<轮>.md`](../llm/prompts) + 该轮输出契约 | 若干 `【段】` | JSON / JSONL |

> ⑦ `settle` 的料里有一段**无条件**的 `【你自己】`（成长基线）⇒ 它**每段都跑**，
> 即使这一段没有新名字、也没有引用（详见 §6.6）。

---

## 1. mmt — MomoTalk 每轮（`core/mmt/engine.py::agent_turn`）

### 1.1 system = 盒 A（会话级**一次**拼死，之后逐字节复用）

| # | 块 id | 内容 | 来源 |
|---|---|---|---|
| 1 | `greeting` | 称呼行：`你好，{名字}——以下是你的行为规则，请严格遵守：` | 引擎给 `names` + `greeting_suffix` |
| 2 | `persona_mmt` | 角色设定**全量**（profile / personality / script / knowledge…）+ 行为规则 | `char.build_prompt("momotalk")` = 六文件 dump + [`behavior_rules.md`](../llm/prompts/behavior_rules.md) |
| 3 | `world` | 【世界常识】【世界规则】 | `config/settings/world/overview.yml` 的 common + system 档（`hidden` 不注入） |
| 4 | `story_tone` | 【本角色剧情基调】 | `script.yml` 的 `SIG~main_tone`（旧 `story_tone` 兜底） |
| 5 | `mmt_tone` | 【本角色 MMT 风格】（**条件**：没有就不出现） | `script.yml` 的 `SIG~mmt_tone` |
| 6 | `environment_mmt` | 虚拟手机场景说明 | [`momotalk_environment.md`](../llm/prompts/momotalk_environment.md) |
| 7 | `time_sense` | 【时间感】—— 她对时间的**世界观**（不是规则） | `core/promptkit/blocks.py::_time_sense`（引擎内联 5 行） |
| 8 | `rules_mmt` | 行为与**风格**：单人模式 / 连发节奏 / 触发契机 | [`momotalk_rules.md`](../llm/prompts/momotalk_rules.md) |
| 9 | `schema` | `可用动作 schema:` + MMT **行流契约** | [`contract/schema/prompts/line.md`](../contract/schema/prompts/line.md) + [`line_rules.md`](../contract/schema/prompts/line_rules.md) + [`line_examples.md`](../contract/schema/prompts/line_examples.md)（`build_line_schema`） |

> 记忆段（brain）不在盒里 —— 见 1.2，它挂在 `round_messages(brain=…)` 上追加到 system **尾部**。
> 从前有 `interperson` 块："她眼里的他们"读的是 `entity.text`，会随经历演化 ⇒ 搬进记忆段。

### 1.2 每轮动态尾（`round_messages`，一切都在 `history` 之后）

```
system : 盒A + "\n\n" + 记忆段(brain)
history: 最近的对话（滑动窗口；resume 时是回放出来的那截）
system : 注记们（按下面这个顺序，各是一条独立的 system 消息）
user   : 玩家这一句
```

| 落点 | 注入什么 | 为什么在这一格 |
|---|---|---|
| 注记 1 | 羁绊进度（**今天恒空**：`_bond_progress_note()` 封印） | 留了调用点，恢复只改那一个函数 |
| 注记 2 | 【手机上的日期】/【她上次见到老师是 12 天前】/【她刚刚还在和老师说话】 | 时间事实比"我想起了什么"更基础 |
| 注记 3 | 特殊日期（生日 / 节日；**只在少数日子**产注记） | 现实日历那一档，调用即记账（失败也不重复注） |
| 注记 4 | 【你想起的事…】/【你想着「X」】 —— 每轮 0~2 段记忆（见 1.3） | 查询是**玩家这一句** ⇒ 每轮不同 ⇒ 只能进动态尾（进 system 就逐轮破缓存） |
| 注记 5 | 调用方给的 `system_note`（收尾轮之类） | 最近位置最醒目 |
| 注记 6 | 随机事件（`want_to_speak`，低频惊喜） | 概率性 soft 注记 |
| 注记 7 | **任务卡**（末位）：[`task_mmt.md`](../llm/prompts/task_mmt.md) 或 [`task_mmt_wrapup.md`](../llm/prompts/task_mmt_wrapup.md) | 目标层恒定压在所有材料之后；`{{char}}` 槽 |
| 注记 8 | 上一轮**丢掉的操作行**提醒（`_take_line_notes`，自清） | 让模型别重复那个动作 |

### 1.3 召回段（**这一段是召回的入口**）

实现在 `core/mmt/engine.py::_recall_notes` → `core/brain/read/modes.py::recall`（形式表 = `modes.MODES`）。
每轮**最多两段**，顺序就是下面的顺序：

| 段 | 形式 | 触发 | 摆什么 |
|---|---|---|---|
| ① 名字段 | `"name"`（**set**，确定判据） | 老师这句话里**提到了某人的名字** | 那个对象车道上**全部**节点（新→旧），含正文里没写他名字的那些 |
| ② 兜底段 | `"turn"`（**rank**） | 每轮兜底 | 六路打分最像的 ≤ `[recall].turn_k` 条 |

规则（都在代码里，改之前先读）：

- **同一条只摆一次**：名字段先定，兜底段剔掉它的 id（`part_name` 也在加成，不剔就重复摆）。
- **保留号不算"提到了谁"**：她自己 / 老师的车道 ≈ 全部事件 ⇒ 那两行名字不触发名字段（`modes.RESERVED_TRIGGERS`）。
- **兜底段这一档的 `semantic` 权重 = 0**：语义那一路每轮要把整个库重新编码（真档 916 ms）且同步跑在装配前 ⇒ 直接进首字延迟。语义留给 digest（写路径 / 异步）。
- 一条都不像 / 空库 / 召回失败 ⇒ **不注**（少一段上下文，剧情照走）。
- 摆出来的段长这样（样例）：`【你想起的事（此刻浮上来的旧事——跟你现在要说的话有没有关系, 由你判断）】` 后面跟 `〔《周六的模型店》｜4 天前｜9/27｜难忘〕正文…` 若干条。

---

## 2. vn — 羁绊剧情每一场（`core/bond/bond_story/engine.py`）

### 2.1 system = 盒 B（10 块，顺序即注入顺序）

| # | 块 id | 内容 | 来源 |
|---|---|---|---|
| 1 | `greeting` | `你好，{名字}——以下是你的剧情行为规则，请严格遵守：` | 引擎给 `names` + `greeting_suffix` |
| 2 | `persona_bond` | 角色设定**两层**（profile + personality）+ 行为规则 | `char.build_prompt("bond_story")` |
| 3 | `world` | 【世界常识】【世界规则】 | 同盒 A |
| 4 | `story_tone` | 【本角色剧情基调】 | 同盒 A |
| 5 | `bond_tone` | 【本角色羁绊剧情建议】（条件） | `script.yml` 的 `SIG~bond_tone` |
| 6 | `rules_bond` | 规则书：单人视角 / 对白节奏 / 记录流写法（switch · 群 · memorial · end） | [`bond_story_rules.md`](../llm/prompts/bond_story_rules.md) |
| 7 | `bond_shots` | 镜头与手法（**可选写法**，不是规则）：镜头词 / switch 组合 / 煽情场景 / 收尾范本 | [`bond_shots.md`](../llm/prompts/bond_shots.md)（槽 `{{char_id}}`） |
| 8 | `schema` | `本轮输出契约（VN 记录流）:` + 记录流契约 | [`contract/schema/prompts/record.md`](../contract/schema/prompts/record.md) + [`record_rules.md`](../contract/schema/prompts/record_rules.md) + [`record_examples.md`](../contract/schema/prompts/record_examples.md)（`build_record_schema`） |
| 9 | `place_world` | 【世界区域】剧情地理主名（条件） | `regions.yml`（**世界设定不是可选空间**：overview.yml 里一个学院名都没有） |
| 10 | `brain` | 记忆段 = 出厂背景 → wiki 第一人称视图 → **【我是谁（成长基线）】** → **备忘录块**（条件） | `core/mmt/engine.py::load_brain_segment` 等 |

> 盒 B 里**没有**情绪词表（`lexicon_emotion` 已退出）：记录流 v2 里 emotion 由标注层逐条挑，
> writer 不写情绪，词表注入对创作不再起作用。

### 2.2 每场动态尾

| 落点 | 注入什么 |
|---|---|
| 注记 1 | 调用方给的 `system_note`（纪念 exit schema / 配额 / 收尾提醒） |
| 注记 2 | 「本章的纪念插画**已经用过了**」（章内至多一次；静态事实，不构成反馈回环） |
| 注记 3 | 上一轮**已交付但形状有问题**的一次性纠偏（`format_issues` 的中文串；消费即清空） |
| 注记 4 | **场卡**（末位）：[`task_bond.md`](../llm/prompts/task_bond.md)，`{{char}}` 槽 |
| user | 玩家的选项文本（VN 无自由打字通道） |

---

## 3. memo — 她自己的备忘录（**不单独调用**，随记忆段进 system）

> 紧邻它**前面**还有一段 `【我是谁（成长基线）】`（`render_character_view` 的最后一块）：
> 那是"我此刻是什么样子"（`entity.text` of `x0000`），不是备忘录的条目 —— 两者一起
> 构成记忆段的尾部（离生成点最近）。它唯一的写入口是 digest 的 `settle`（见 §6.6）。

渲染 = `core/brain/notes.py::render_note_block`（纯函数零 IO；`titles` 由调用方从图上取好传进来）。
空状态 ⇒ **一个字的块都不出现**（常驻预算）。形状（样例）：

```
【你自己记的备忘录】（你自己随手记下的, 不是别人给你的任务; 括号里是编号, 指回你记忆里的那件事）
  · 你自己记下的约定
    n3 周六模型店 (《模型店的午后》)  ← 记于 3 天前
    n1 买花 (《花店》)  ← 已结清（送出去了）
```

要点：**零结构化痕迹**（不出现 JSON / 键名 / 波括号）· `id` 必须印（她要靠它 `close`）·
开着的排在已结清前面 · **不印频次**、**不印 `due`**（防讨好 / 数值化）。

**谁写的**：真源是事件流里的 note 操作，由 digest 的 **⓪ 切分**（判）与 **① 记**（落）产出 ——
见 §6.1 / §6.2。备忘录**不进图**，是工作记忆。

---

## 4. annoemo — 情绪标注（异步，两条）

| 调用点 | system | 槽 | user |
|---|---|---|---|
| 逐句批量（`core/bond/emotion_annotate.py`） | [`emotion_annotate.md`](../llm/prompts/emotion_annotate.md) | `lexicon` · `sentences` · `character` | `请输出上述每句的情绪标签数组。` |
| 逐条记录（`core/bond/emo_text.py`） | [`emotion_text_annotate.md`](../llm/prompts/emotion_text_annotate.md) | `group_no` · `char_name` · `character_hint` · `context` · `n` · `records` · `lexicon` · `key_a` · `key_b` · `key_n` | （随 system 一起给） |

样例（`sentences` 槽的形状 —— **逐句编号**，输出是等长数组）：

```
1: 老师，今天的数学作业你写完了吗？
2: （低头）我、我不是催你……
3: 只是如果你不会的话，我可以教你。
```

约束：温度 0.2 · 输出**纯数组** · **词表外的标签逐项判 None**（不猜）· 长度不符 ⇒ 二分降级 ·
整批失败 ⇒ 调用方延续兜底（宁缺勿错，标注挂了不阻断剧情）。

---

## 5. annoplace — 地点标注 / 选图（异步，三条）

| 调用点 | 干什么 | system | 槽 |
|---|---|---|---|
| `place_annotate` | 逐句判**有没有换场**，换到哪个键 | [`place_annotate.md`](../llm/prompts/place_annotate.md) | `current_place` · `lexicon` · `sentences` |
| `place_resolve` | 把 writer 的**原话**解析成一个地点键（解析不到 ⇒ 交白卷，不编） | [`place_resolve.md`](../llm/prompts/place_resolve.md) | `current_place` · `lexicon` · `text` |
| `place_variant` | 在一堆**图库候选**里挑一张（选图，不是写文本） | [`place_variant.md`](../llm/prompts/place_variant.md) | `place` · `aliases` · `candidates` · `note` · `current_image` · `text` |

- `candidates` **不是召回**：它是 `core/media/` 查库的结果（`place_table` 的键 + 图库有哪几张），
  由引擎摆好，LLM 只做**挑选**。
- `place_resolve` 的输出会被**替回原文**（键不是给玩家看的地名），所以它只许吐出词表里的键。

---

## 6. digest — 六轮（`core/digest/rounds/__init__.py` 的 `ROUNDS`）

### 6.0 通用装配

```
system = render_template(load_prompt("digest_<轮>"), {"digest_schema": 该轮输出契约})
user   = 若干 【段标题】\n正文 块（空块跳过; 段标题由 ROUNDS.material 逐字校对, 对不上当场炸）
```

- 规则书：[`llm/prompts/digest_split.md`](../llm/prompts/digest_split.md) ·
  [`digest_record.md`](../llm/prompts/digest_record.md) ·
  [`digest_relate.md`](../llm/prompts/digest_relate.md) ·
  [`digest_cognize.md`](../llm/prompts/digest_cognize.md) ·
  [`digest_settle.md`](../llm/prompts/digest_settle.md)
- 输出契约（`{{digest_schema}}` 槽）：[`contract/digest/prompts/`](../contract/digest/prompts)
  下同名文件 + `parts/`（`domain.<域>` · `record.<域>` · `row_fields` · `scope.one|multi`），
  由 `contract/digest/registry.py::build_schema` 按相位/域/章数拼。
- 料在 `core/digest/material.py`；**只有"料的名字"写进表**，正文各函数现算。

### 6.1 ⓪ split（切分）

- 料（5 段）：`本段新增互动` · `本段的时间` · `日子` · `还开着的约定` · `本章标题`
- 输出：`{"segments": [{span, keep, abstract, state?, id?, due?}, …]}` —— **一行一件切片 + 账目**
- 说明：切多细跟着**作者单位**走（`bond` = 一章，`mmt` = 一次覆盖多轮碎聊）；
  窗口里有多章时契约要改成"每章各 1 条"（否则两章被压成一条）。

### 6.2 ① record（逐条记）

- 料（7 段）：`本段新增互动` · `本段骨架` · `本章标题` · `画面记忆` · `已有的对象` ·
  `角色人设（锚点）` · `本段情绪标尺`
- 输出：episode 条目（`title/text/verbatim/tags/entity/significance/emo_*` 等），位置取 R0 的 `seqs`
- 说明：**引擎当场按 R0 的表产 note 操作**（`add` / `update` / `close`）—— 备忘录的写者只有这一轮；
  `已有的对象` 是为了防"同一个人被起两个名"。

### 6.3 补边 akin（**零 LLM**）

不调模型、也没有 prompt：本段的 `noticed` 账 → 引擎落 `akin` 边（归属判据见 `rounds/akin.py`）。

### 6.4 ③ relate（判关系 / L1）

- 料（6 段）：`本次新经历（含引擎候选标注）` · `现有经历（候选）` · `她认过的同类印证过的看法` ·
  `本段时间线` · `现有认知` · `角色人设（锚点）`
- 输出：边表（`supports` / `akin` / `contradicts` / `evolved_from`）—— **只落边，一个字正文都不写**
- **召回在这里**：`现有经历（候选）` = `like(spec="digest")` 排出来的最像的 ≤ 6 条
  （query = 本段每条经历自己的正文，多条各问一次取并集；并把 **为什么像**（`why`）一起印出来）。
  缺 embedder ⇒ 那一路自动降级，其余照跑（台账里 `sim=` 那格解释 `cands=0`）。
- `她认过的同类印证过的看法` 是**零 LLM 统计**（同类经历印证过哪条看法）—— 补的是"看得见候选，却看不见它印证过谁"。

### 6.5 ⑥ cognize（写看法 / L2）

- 料（6 段）：`这次的事` · `这一类事` · `现有认知` · `跟这条撞上的现有看法` · `已有的对象` · `角色人设（锚点）`
- 输出：`belief`（带 `id` = 改已有的，不带 = 造新的）+ 它出生自带的边
- **召回/取料说明**：
  - `这次的事` = 本段被 L1 连过的经历（**立足点**，零 LLM 读数）；
  - `这一类事` = 那些经历**一跳 `akin`** 的邻居（她认过"是同一类事"的，额外证据）；
  - `跟这条撞上的现有看法` = **共享证据**统计（`│本段证据 ∩ 该看法的 supporters│` 降序，零 LLM）——
    治"同一个结论写第二条"。
- 这一轮**自带快照**：失败只丢"新造的那几条看法"，经历与边照旧。

### 6.6 ⑦ settle（沉淀 / R3：认人 + 写看法 + 改写她自己）

- 料（5 段）：`你自己（成长基线）` · `这一段认下的对象` · `她写了、但库里还没有的名字` ·
  `已有的对象` · `角色人设（锚点）`
- 输出：`entity`（名字 / 别名 / 第一句看法）+ 回头补 `about` 边
- **【你自己】无条件印**：`x0000` + 它现在的 `text`（`成长基线: …`）+ **本段全部新节点**
  （⛔ 不按 `about` 车道筛 —— 那条车道写的是"这条关于谁", 而一条"老师带我去吃饭"记的
  是她的日子）+ 全库 episode 的基数（`她记得的事一共 N 件`）。
  ⇒ 因此这一轮**每一段都跑**（2026-10-18 起; 从前"没陌生人、没引用"就跳过）。
- `x0000` 在**可改集合**里: 那一行的 `text` 走 `apply_stances`（水位 `text_seq` 照落）——
  这是**成长基线唯一的写入口**。它的长度尺是 `ENTITY_SELF_TEXT_MAX = 150`（不是 60:
  它已不住名字表那一行里, 读者期待的是**一段话**; 出厂值实测 116~149 字）。
- 说明：`about` **不由 LLM 写** —— 她只在写节点时留下引用，边由引擎派生；
  这一轮自带快照（失败只丢"新对象 + 这一次补边"）。

---

## 7. 改提示词的流程（照这个走，别凭手感）

1. 改 `.md` 正文或改装配顺序 ⇒ 跑 **三份逐字节判据**（`.testtmp/verify_1c.py` ·
   `capture_prompts_1d.py` · `capture_1e.py`，退出码 0 = 没有计划外差异）；有意的改动写进
   `EXPECTED_CHANGED` / `CHANGED` **并写为什么**。
2. 动到进 system 的文案 ⇒ 刷黄金夹具再**人工审 diff**：
   `$env:PROMPTKIT_UPDATE_FIXTURES='1'; python -m pytest tests/core/test_promptkit_baseline.py`，
   夹具 = `tests/fixtures/promptkit/{mmt_box,bond_box}.txt`（**字节级**的盒 A / 盒 B）。
3. 动到料 / 段标题 ⇒ 同步改 `ROUNDS.material`（对不上会当场炸，这是特性不是麻烦）。
4. 新增一块 / 新增一轮 ⇒ 先改 `DOMAIN_BOXES` / `ROUNDS`，再补判据（`test_digest_rounds.py`
   会检查 `IMPL` 与表一一对应）。
