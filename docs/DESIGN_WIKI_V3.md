# DESIGN_WIKI_V3.md — 记忆图 v3 设计稿（节点 / 召回 / LLM 动作 / 时间 / 组合）

> **状态（2026-09-13）: 设计稿，未实现。** 本文**不是现状描述**——凡标 ✅ 的才是代码已
> 有之物；标 🔧 的是待落地；标 ⚠️ 的是**从线上真实数据里查出来的**问题（不是推测）。
>
> 前置阅读：
> - `core/brain/wiki_v2/AGENT_BRAIN.md`（v2 蓝图，本文取代其节点/召回章节，§9 开放问题在此收口）
> - `DESIGN_BRAIN.md`（记忆体系合并史，文首有状态栏，慎读）
> - `docs/AUDIT_2026-09-13_FULL.md`（§9 未修清单 / §10 embedding 实测）
> - 外部参照：A-Mem（note + link generation + memory evolution）、AgentGal（多步整理 +
>   混合召回 + 游戏内时间衰减）、BaiShou（层级总结 + 拥抱冗余 + 时间感）
>
> **v3 的动机一句话**：v2 是赶工产物，它在**节点分类轴**、**时间语义**、**读路径**三处
> 留了结构性欠账；这三处互相纠缠，打补丁会来回抵消（本文 §1.4 给出证据）。

---

## 0. 一页纸（给赶时间的人）

| 轴 | v2 现状 | v3 目标 |
|---|---|---|
| **图的中心** | **以非 belief 节点为中心**：episode 是主体，belief 挂在它下面、彼此无边（利于 agent-memory，**不利于 RP**） | **实体中心的两层图**：`entity`（谁/什么/哪里/哪条知识）为持久参照物，episode/belief 都指向它 |
| **节点** | 4 个 kind 混用（`episode`/`experience`/`belief` + `source=experience`），一词四义 | **2 kind**：`entity` + `episode`/`belief`（同为经验层）；**`experience` kind 归并**（规律 = belief + `nature=pattern`，物品 = `entity(etype=item)` + 边状态） |
| **归属** | `subject` 是自由字符串 → 同一实体裂成多种写法（真机：老师 ×4 种） | `about`（引擎管，指向 entity，保证归堆）+ `aspect`（LLM 写，保留侧面区分度） |
| **认知分层** | 无 | 第四轴 `nature`：`self_image`（内核，**不合并**）/ `other`（合并）/ `relationship`（有时效）/ `pattern`（计数聚合） |
| **时间** | **零游戏内时间**，只有壁钟 `ts` | 双层：壁钟（审计）+ **剧情时间游标**（锚点 + 累积流逝）；渲染模糊成"三周前" |
| **召回** | 静态分桶按 `significance` 取前 N（**无 query**）；三通道召回零生产调用方 | **实体为召回车道**：向量 + 词面 + 线索 → 实体级打分 → 车道内取 belief → 融合/时间加权 → 跳转扩展；**且可观测** |
| **LLM 动作** | Round A 记录 + Round B 三选一（add/touch/update） | **多步**：时间推进 → 记录 → 实体消解/登记 → 组织决策（含**链接/矛盾/组合**）→ 好感；动作集扩到 9 |
| **组合** | `merge`/`accrue` 代码全套 ✅ 但**零生产调用** | 两档：**无损聚合**（digest 内）与**深度重组**（独立阶段，带溯源与撤销）；合并策略**按 `nature` 分派** |

---

## 1. 为什么 v3 必须换节点层

### 1.1 ⚠️ `experience` 一词在代码里承担四套语义

| 出现位置 | 实际含义 | 归属层 |
|---|---|---|
| `nodes.KINDS` 的 `kind="experience"` | 重复模式 / 口癖 | **图节点** |
| `nodes.is_seed()` 判据 `source="experience"`（挂在 **episode** 上） | 出厂预设经历 | **图节点的来源字段** |
| `render_background_experience(ch.experience)` | `experience.yml` 角色档案 | **配置文件**（不进 wiki） |
| `mmt_inspect_character` 的 L3 `+experience` | 故知层人设资料 | **检视深度** |

同一拼写横跨四层。**后果不是"难读"，而是规则写不对**：`accrue`（同类事件并入 experience）、
`_ensure_cognition` 的目标校验、`render` 的分桶、`recall` 的 kind 过滤——每一处的"experience"
指的是哪一套，只能靠上下文猜。

### 1.2 ⚠️ 线上真实数据证明 `experience` 节点名不副实（决定性证据）

线上全库 **13 个节点**（haruka 8 / mutsuki 5 / kayoko 0）。其中唯一的 experience 节点：

```json
{"id": "e0001", "kind": "experience", "subject": "player", "significance": 0.5,
 "epistemic": "observed_fact", "links": null, "event_seq": [60], "segment_id": "seg-60",
 "pattern": "老师总靠喝浓缩咖啡硬撑工作, 自称到了需要它才有精力的程度",
 "verbatim": "我已经到了需要喝浓缩咖啡才能有精力工作的程度了呢",
 "tags": ["浓缩咖啡", "工作", "老师"]}
```

它有**三处自相矛盾**，每一处都指向同一个诊断：

1. **`subject="player"` 但 kind 叫 experience** —— 它记的是**关于玩家（老师）的知识**，
   不是角色的经历。它是"对老师的认知"，语义上就是 belief。
2. **`epistemic="observed_fact"` 但内容是一句转述** —— "自称到了……的程度"是**老师说的**。
   按 v2 自己的护栏，这该是 `reported_fact`（episode 才有此取值），而 belief 又强制
   `inferred_belief`。**它落在一个两种 kind 都不认的语义夹缝里**。
3. **`links=null`** —— 而 v2 的规则是"belief 必须 links ≥1 支撑（无支撑升华拒绝）"。
   它作为 cognition 参与 Round B 组织（`render_cognition_list` 只挑 belief/experience），
   却**没有任何支撑证据**。规则在 kind 之间不一致。

**结论**：`experience` 作为一个 **kind** 没有独立语义载荷。它实际想表达的是
"**反复出现的规律**"，而"反复"是**证据条数**的属性，不是节点的类型属性。

### 1.3 另一条被记错的节点（同一批数据）

```json
{"id": "m0002", "kind": "episode", "epistemic": "reported_fact", "observer": "老师",
 "narration": "聊天时老师说起阿露酱居然认真跑去问他怎么帅气地喝苦咖啡……",
 "verbatim": "库呼呼～老师你可千万别告诉她哦", "subject": "阿露", "tags": ["阿露","苦咖啡","牛奶","恶作剧"]}
```

`observer="老师"` 意味着"这是老师说的事"，但 `narration` 写的是**阿露的行为**，
`verbatim` 是**睦月自己**说的话。**"谁经历的 / 谁说的 / 关于谁"三个轴被压进了一条记录**，
而渲染时（`render.py` 的 `_reported_line`）只会加一句"（听老师说的）"——**主体是谁读不出来**。

这是 `subject`（关于谁）与 `observer`（谁说的）在 v2 里**职责重叠**的直接后果。

### 1.4 为什么"打补丁"会来回抵消（四个诉求改的是同一片）

你要的四件事，落点文件**完全重叠**：

| 诉求 | 要动的地方 |
|---|---|
| 澄清 `experience` | `nodes.KINDS/_REQUIRED/validate/normalize` · `store._PREFIX` · `render` 五个分桶 · `recall` 的 kind 过滤 · `digest_registry` 决策表与 parse · `revise` 目标校验 |
| **实体中心化 + 物品/地点/知识** | **同上全部**（新 kind 要过每一道闸）+ `recall` 两级结构 + `render` 分组 + Round B 组织视图 + **新增 Step 1.8** |
| 组合重组 | `revise` 规则引擎 · `store` 不变量 · 新增阶段编排 · `digest_registry` 新动作 · **合并策略按 `nature` 分派** |
| 时间架构 | 每个节点的字段 · `render` 文案 · `recall` 衰减 · `store` 需要时间游标 |

打四次补丁 = 把同一片代码动四遍，且中间态是"半新半旧 schema"（新旧 kind 共存、
时间字段半有无）。**重构一次 = 动一遍 + 带 `schema_version` 迁移**。

**代价现在最低**：全库 13 个节点，迁移脚本几十行；等真跑几百条就不是这个量级。

**而且这四件事互为前提**（不是四件独立的事）：
- 没有实体层，"组合重组"就只能在**自由字符串 subject** 上做比较 → 判不出该不该合并
- 没有 `nature`，"合并策略"就没有判据 → 会把角色内核（`self_image`）当重复项合并掉
- 没有时间，`relationship`（约定）就无法过期 → 只能一直堆着
- 没有实体层，物品/地点的"状态"就要各自造一套 → 就是 v3 初稿那个 `possession` kind

### 1.5 v3 明确**不**重写的东西（保住已建成的资产）

| 保留 | 理由 |
|---|---|
| `events.jsonl` append-only 真源 | 事实主线，v3 不碰 |
| `digested_seq` 水位 / 原子提交 / 快照回滚 | 增量与幂等已正确 |
| `history` 版本化字段 ✅ | 正是 A-Mem 那条"必须版本化"纪律的落地物——v3 要**用它**，不是重塑它 |
| `apply_revision_package` 规则引擎与测试 ✅ | merge/contradict/accrue 逻辑与校验已写好，v3 只补**入口 + 溯源** |
| 上两轮加的观测/降级埋点 | 不动 |

---

## 2. 节点新概念（实体层 + 经验层 + 四条轴）

### 2.0 为什么引入实体层（诊断 + 用户裁决 2026-09-13）

**v2 的图是"以非 belief 节点为中心"的**：`episode` 是绝对主体，belief 挂在它下面，
彼此之间没有任何边。作为 agent-memory 这没问题；**但对 RP 不对** —— 角色扮演里
最有价值的查询是"老师在她心里是什么样"，而 v2 的结构回答不了。

真实数据（线上 13 节点）给出三条证据：

**(1) `subject` 是自由字符串 → 同一实体裂成多种写法**

```
igusa_haruka  [belief] subject='被老师求助时的反应'
              [belief] subject='向老师敞开秘密基地'
              [belief] subject='对老师肯定的感受'
              [belief] subject='对老师的承诺方式'
asagi_mutsuki [belief] subject='我对老师的心意'
              [belief] subject='我对阿露的看法'
```
同一个"老师"，haruka 用 4 种**侧面描述**当 subject，mutsuki 用"我对X的看法"当 subject。
不是 LLM 不听话——**是引擎没给它一个稳定引用点**，每次都是现场编。
后果：这 4 条 belief 语义上属于同一个实体，结构上却彼此无关，召回时无法一起捞。

**(2) 实体信息其实已经在图里，只是散在 `tags`**

真机 episode 的 tags：`阿露 / 春余×2 / 杂草屋 / 咖啡厅 / 俄罗斯轮盘巧克力 / 联邦理事会 / …`
——**人名、地点、物品全在，但没有节点承载**。换场翻译、物品查表都只能靠字符串匹配。

**(3) `interperson.json` 已经是一张角色实体表**（8 条，带权重 1/2/3）
——实体中心化不是引入新概念，是**把已有的表接进图**。

**(4) 顺带**：线上 `source=experience` 的节点 **0 条** —— 出厂 episode 从未进过 wiki。
所以"出厂基座"目前纯属设计概念，迁移几乎没有历史包袱。

**用户裁决（2026-09-13）**：需要 `self`（自我认知）/ `item`（物品）/
`place`（地点）/ `knowledge`（特定知识）四类实体；**belief 保持多条并存**
（不做"合成一条总结"——理由见 §2.5）。

### 2.1 两层，不是三种东西

```
┌─ 实体层（entity）── 世界里的"持久参照物"：谁 / 什么 / 哪里 / 哪条知识
│     稳定 · 引擎管身份 · 可被引用 · 不承载情感内容
│
└─ 经验层 ────────── 角色视角的"我经历过/我认为"
      episode（发生的事，亲历/听说）
      belief （持久认知，含自我认知/对他人/关系/模式）
```

**关键澄清（用户问题的直接回答）**：

> 引入实体层解决的是**归属与召回**，**不是**内容粒度。

`entity` 节点**不是"把对它的看法装进它"**，而是"给它一个家"——
entity 只存身份与索引（名字/别名/类型/关系阶段），**关于它的看法仍是多个 belief 节点**。

所以**不做**方案 B（把"对老师的看法"合成一条）：
- "对老师的看法"会变成一段**单调增长**的长文本，而 `content ≤200 字`——
  第 20 条经历时要么丢细节、要么写不下
- 每次 update 都要**重生成整段** → 成本高 + **漂移**（A-Mem 的警告正是针对这个：
  "rewriting older notes … without hard versioning is hard to debug and can be unsafe"）
- **矛盾无法表达**：一个人对另一个人的看法**本来就是矛盾的**
  （"依赖他" + "怕成为负担"）——合成一条会把张力抹平，而 **RP 里张力就是戏**

### 2.2 实体层：`entity`

```jsonc
{
  "id": "x0001",
  "kind": "entity",
  "name": "老师",                        // 显示名（中文主名）
  "etype": ["person"],                   // ★ 数组，不是单值（见 §2.4 改进①）
  "aliases": ["sensei", "老师", "他"],    // 归一化用（每角色视角不同）
  "ref": "player",                       // 关联既有 id：interperson / registry / 角色 id（可空）
  "stage": "",                           // 关系阶段词（未来 relationship_view 接这里；引擎裁决）
  "origin": "digest",                    // digest | seed | author
  "story_time": { ... }                  // 首次确立时间（§4）
}
```

**`etype` 取值（用户定，4 + 1）**：

| etype | 指什么 | 真机例子 | 特殊之处 |
|---|---|---|---|
| `self` | **角色本人**（自我认知的归属点） | 唯一一个，id 固定 `x0000` | 必存在：开局自动建，别名 = 角色名 + 自称 |
| `person` | 他人（学生/老师/其他） | 老师、阿露、春余 | 可与 `interperson.json` 对齐 |
| `place` | 地点 | 杂草屋、咖啡厅、联邦理事会 | 与 §10 背景词表/换场翻译天然对接 |
| `item` | 物品 | 俄罗斯轮盘巧克力、写满杂草名字的卡片 | 有生命周期 → 见 §2.6 边状态 |
| `knowledge` | 特定知识（事实/秘密/规则） | "联邦理事会让他做环境调研报告" | **与 `knowledge.yml`（世界观知识库）刻意同名**——把"我知道的事"接进图 |

**为什么 `self` 必须有**：真实 belief 里 **最多的是关于自己的**——
"我这种人配不上老师的帮助"、"对老师肯定的感受"。若只建"他人"实体，
**角色内核将无家可归**（现在它们的 subject 是"被老师求助时的反应"，挂在老师名下，
语义上是错的）。

### 2.3 经验层：`episode` / `belief`

**episode**（形状同 §2.2 旧版，仅新增/改名两个字段）：
```jsonc
{ "id": "m0001", "kind": "episode",
  "title": "老师拜托我调查杂草", "narration": "……", "verbatim": "……",
  "tags": ["杂草调查", "报告"], "significance": 0.7,
  "epistemic": "observed_fact", "observer": "",
  "about": ["x0001"],              // ★ v2 的单一 subject → 实体引用列表（可多人同场）
  "story_time": { ... }, "origin": "digest", "event_seq": [30], "links": ["m0005"] }
```

**belief**（⚠️ 相对 v3 初稿有实质变化——`subject` 拆成 `about` + `aspect`）：
```jsonc
{ "id": "m0005", "kind": "belief",
  "about": "x0000",                // ★ 归堆键：指向实体（引擎保证存在、唯一）
  "aspect": "被求助时的反应",        // ★ v2 的 subject 语义降到这里（LLM 自由写）
  "nature": "self_image",          // ★ 第四轴，见 §2.5
  "content": "老师一开口请我帮忙，我会先……",   // ≤200 字，结论式
  "growth": "……", "pattern": "", "keywords": ["老师", "自我怀疑"],
  "occurrences": 3,                // 引擎数（= 支撑 episode 条数）
  "significance": 0.6, "epistemic": "inferred_belief",
  "history": [ { "episode_id": "m0001", "content": "…", "ts": "…" } ],
  "superseded_by": "", "story_time": { ... }, "origin": "digest",
  "links": ["m0001"] }
```

**`about` + `aspect` 的拆分是这一版的核心**：

| 字段 | 谁管 | 作用 |
|---|---|---|
| `about` | **引擎**（LLM 只能从已渲染的实体列表里选，或显式提议新建） | **保证归堆**——同一实体下的 belief 天然成为一组，"四种写法"从根上消失，**不靠提示词劝** |
| `aspect` | LLM | **保留区分度**——每条看法讲的是哪个侧面，自由命名 |

这两者缺一不可：只有 `about` → 丢侧面（"对老师的看法"含糊）；只有 `aspect` → 就是现在这样裂开。

**替换 `player` 特例**：v2 用硬编码 `subject == "player"` 表达"玩家画像"
（`is_player_experience`/`PLAYER_SUBJECT`，7 处消费）。v3 改为
`about == 玩家实体 id` + `nature == "pattern"` —— **同一套词汇，取消特例**。

### 2.4 四条轴（v2 只有两条，且被压在一起）

```
轴一 kind      —— 节点的"形状"      : entity | episode | belief
轴二 epistemic —— "我怎么知道的"    : observed_fact | reported_fact | inferred_belief | speculation
轴三 etype     —— 实体是"哪种东西"  : self | person | place | item | knowledge   （仅 entity）
轴四 nature    —— 认知"是哪一类"    : self_image | other | relationship | pattern （仅 belief）
```

### 2.5 改进②：第四轴 `nature`（为什么必须加）

真实那 4 条 belief 混着**四种性质不同的知识**，而它们的**合并规则完全不同**：

| nature | 例子 | 合并规则 | 为什么 |
|---|---|---|---|
| `self_image` | "我这种人配不上老师的帮助" | **不合并**——允许长期并存甚至互相矛盾 | 这是**角色内核**；合并等于抹掉人设张力 |
| `other` | "老师总靠浓缩咖啡硬撑" | **同类合并**（同一 about+aspect 的多条经历 → update/accrue） | 关于他人的判断会被反复观察到，该收敛 |
| `relationship` | "约定一起去看杂草" | **有时效，过期退场** | 约定会履行或失效；现在没有这个机制（§4 时间架构支撑） |
| `pattern` | "老师总说摸鱼"（= v2 的 experience 本义） | **计数聚合**（`occurrences`） | "反复出现"是证据条数的属性 |

**只按 `about` 归堆的缺陷**：会把 `self_image`（自我认知）与 `pattern`（他人习惯）
放进同一个桶里，而前者**不该被计数合并**、后者**应该**。
所以 `nature` 是**合并策略的判据**，不是标签——它决定这条 belief 在 V3-6
深度重组阶段**能不能被 merge**。

**默认值**：LLM 未填 → 按 `about` 推断（`about == self` → `self_image`；
有关键词线索"约定/答应/一起" → `relationship`；`pattern` 非空 → `pattern`；
否则 `other`）。引擎可覆盖，且**判错不致命**（最坏是合并策略取默认）。

### 2.6 改进③：边状态 —— 通用化 v3 初稿的 `possession`

v3 初稿给 `possession` 设计了独立 kind + `state`/`holder` 字段。**引入实体层后
这套变得多余，而且不通用**：

| 情况 | 用 possession kind | 用边状态 |
|---|---|---|
| 物品转手 | `state=given_away` | ✅ 同 |
| 地点变得不可去（毕业了/封锁） | ❌ 无表达 | ✅ `state=lost` |
| 知道了某个秘密 | ❌ 无表达 | ✅ `state=held`（knowledge 也"持有"） |
| 忘记了 | ❌ 无表达 | ✅ `state=forgotten` |

**推荐形态（待确认，但必须现在定形状）**：把"角色与实体的当前关系"表达为
**角色 → 实体的边状态**，而不是物品专属字段：

```jsonc
// 每角色一份（与 wiki.jsonl 并列，不改 entity 节点本身）
// soul/bonds.jsonl 或 wiki.meta.json 的 relations 段
{ "entity": "x0003", "state": "held",       // held | lost | given_away | consumed | forgotten
  "obtained": { "episode": "m0001", "story_time": {...} },
  "lost":     null,                          // 同构
  "updated_at": "壁钟（审计）" }
```

**为什么不能把状态放 entity 节点上**：entity 是**世界级**的（一个物品只有一件），
而"持有"是**角色级**的（换角色视角完全不同）。放错层会让多角色共享世界时互相污染。

**与 §2.2 初稿的 `possession` kind 的取舍**：v3 初稿把 `possession` 立为 kind 的
四条理由（有身份/有状态机/有时间区间/有资产锚点）**全部由
`entity(etype=item)` + 边状态满足**，且少一个 kind。资产锚点
（`assets/illustration/{char}/{outfit}/possession/`）改为与 `entity.id` 对应。

### 2.7 改进①+④：`etype` 用数组 + 别名软合并

**改进①：`etype: list[str]` 而非单值。** 一个实体天然可属多类，
单值会强制 LLM 二选一：`白守`既是 person 又是 group；`圣园未花`是 person，
但作为学生会长出现在 belief 里也带 group 语义。而 `etype` 是**滤镜**不是**身份**——
`["person", "group"]` 同时满足两种检索。渲染取首元素当主标签。

**改进④：实体合并用"别名软合并"，不做硬删。**
v3 初稿让 merge 保留源节点（I7）。实体合并同理且更严格：

```
LLM 提议 merge(x0007 → x0001)
  → 只做两件事: ① x0001.aliases ∪= x0007.aliases ∪ {x0007.name}
                ② x0007.merged_into = "x0001"（**节点保留**）
  → 此后 LLM 看到的是 x0001（含全部别名, 归一命中率上升）
  → 旧的 about=x0007 的 belief **不改写**（append-only 精神）;
    召回时经 merged_into 一跳重定向到 x0001
```

**为什么硬删是坑**：实体是**被引用的**——删掉它，指向它的 belief 全变悬空
（`store.audit` 能查出来，但已经丢了解释信息）。而软合并**只增不改**，
可回滚、可审计，与项目既有哲学一致。

### 2.8 id 前缀

```python
_PREFIX = {"entity": "x", "episode": "m", "belief": "m"}
```

- `x` 给实体（`x0000` 固定为 `self` —— 保留 0 号，让"我自己"在日志里一眼可辨）
- `m` 仍给 episode/belief（两者都是"动态产出"，序号共享便于按创建序读日志）
- `e` 前缀**退役**（随 v2 `experience` kind 归并）
- `p` 前缀**不再需要**（possession 不再是 kind，见 §2.6）
- `c` 前缀已于 2026-09-02 随 `fact` 退役，v3 不恢复

### 2.9 不变量（引擎强制，入仓时校验）

```
I1  belief.epistemic == "inferred_belief"（认知不伪装成事实）              ✅ v2 已有
I2  belief.links ≥ 1 条支撑（episode 或 belief）——无支撑不升华              ✅ v2 已有
I3  belief.about 指向存在的 entity（**悬空引用一律拒收**）                  ★ v3 新增
I4  entity.id 唯一；`x0000` 恒为 self；每个角色开局必有一个 self 实体        ★ v3 新增
I5  entity.etype ⊆ {self,person,place,item,knowledge} 且非空                ★ v3 新增
I6  belief.nature ∈ {self_image,other,relationship,pattern}（缺省按 §2.5 推断）★ v3 新增
I7  belief.occurrences == 支撑它的 episode 条数（引擎数，不信任 LLM）        ⚠️ v2 count 只对 experience 生效
I8  nature == self_image 的 belief **不参与 merge**（只可 update/accrue）    ★ v3 新增
I9  entity 合并只走"别名软合并"：`merged_into` 单向、目标必须存在、不得成环    ★ v3 新增
I10 story_time 单调不减（同世界线按 event_seq 排序不得倒退）                 ★ v3 新增
I11 superseded_by / merged_into 指向存在的节点；被取代者**保留在图里**       ✅ v3 初稿
I12 history 只增不改（改写溯源）                                            ✅ v2 已有
```

---
## 3. 混合召回策略（读路径重建）

### 3.1 现状：读路径根本不是召回

`render_character_view` ✅ 是唯一被主链消费的视图，形态是**静态分桶 + cap 截断**：

| 桶 | 排序键 | cap |
|---|---|---|
| 久远的记忆（seed episode） | significance 降序 | 5 |
| 我记得的事（运行时 episode） | `(is_precious, ts)` 降序 | 6 |
| 我心里渐渐觉得（belief） | **significance 降序** | 5 |
| 老师的事（player belief） | count 降序 | 5 |
| 我听说的（reported） | 原序 | 3 |

**无 query、无 embedding、无权值**。后果：**第 6 条以后的 belief 永远不出现在任何提示词里**，
因此永远不可能被 touch/update（写路径依赖读路径把它喂进去）。

而设计好的三通道召回 `recall_subgraph`（相似度 + 珍贵保底 + 随机摘段 + 一跳扩展）✅
**零生产调用方**（我逐处核过：只有 `def`、`core/rag/brain.py` 的 wrapper、和
`tests/core/test_wiki_recall.py`）。

### 3.2 v3 召回管线（实体为"车道"）

引入实体层后，召回从"在一个扁平池子里打分"变成**两级 + 车道配额**：

```
query（本轮情境文本）
  │
  ├─ ① 实体级召回（先决定"这轮关于谁/什么"）
  │     通道E1 具名线索：query 里出现的实体名/别名（含 merged_into 重定向）★ 最强信号
  │     通道E2 语义：embedding(query) × **实体**向量（name+aliases 合成的代表向量）
  │     通道E3 在场保底：本场 episode 的 about 里的实体（剧情正在讲谁，必进）
  │        ▼  合并去重 → 实体打分 = w_cue·线索 + w_sem·cos + w_imp·该实体下最高 sig
  │        ▼  取 top-k_entity（建议 3~5）——**这就是"召回车道"**
  │
  ├─ ② 车道内召回（在每个实体内部取具体的认知/经历）
  │     通道B1 语义：embedding(query) × 该实体下 belief/episode 向量 → top-k
  │     通道B2 词面：BM25 / tags∩ / aspect 命中
  │     通道B3 珍贵保底：该实体下 significance ≥ 0.8 且未命中 → 补 n_precious  ✅ 设计已有
  │     通道B4 随机摘段：30% 珍贵加权 / 70% 对数正态(剧情年龄)加权              ✅ 设计已有
  │        ▼  融合打分 = w_rel·relevance + w_time·recency + w_imp·importance
  │             relevance = w_vec·cos + w_lex·bm25_norm            （AgentGal 同构）
  │             recency   = 双信号：剧情年龄衰减 × 上次被想起的年龄衰减
  │        ▼  **每实体配额**（每车道最多 n_per_entity，防一个实体洪泛）
  │
  ├─ ③ 跨实体补充（保证"没被 query 提到但对角色重要"的东西不饿死）
  │     通道C1 珍贵保底：全库 significance ≥ 0.8 的 belief（跨实体，补 n_precious）
  │     通道C2 时间锚：最近的 episode（保持"最近发生了什么"的连续性）
  │
  ▼
  一跳扩展（沿 links ∪ contradictions ∪ about 反向）
  ▼
  按 kind 配额截断（防 episode 洪泛把 belief 挤出去）→ 渲染
  ▼
  写召回台账（§3.5, 增记 entity 命中）+ 回写 last_recalled（剧情时间）
```

**为什么"实体为车道"是这一版的关键**：v2 是在**扁平池**里按 significance 取前 N，
于是"关于老师的 4 条 belief"里只有排前面的进得来，其余永久读不出（§3.1）。
实体车道把"该给谁"和"给多少"解耦：**先按 query 选人，再在这个人内部按 query 选事**。
`COGNITION_CAP=12` 那个全局漏斗随之退役（见 §8-5）。

**防扇出（必须做，否则新结构会比旧的更糟）**：
若"老师"下挂 20 条 belief，无配额的一跳扩展会把它们全拉进上下文。
三道闸：① `k_entity` 限制车道数 ② `n_per_entity` 限制单车道条数
③ 全库上限 `cap`。三个值都进 `settings.toml [recall]`（V3-0 已建好旋钮面）。

**关键改动 vs v2 设计**：
1. **两级结构**（实体级 → 车道内）+ 车道配额（v3 新增）
2. **`recency` 用剧情时间，不用壁钟**（§4 落地后才有意义）
3. **`last_recalled_at`（剧情时间）** —— 刚念过的自然下沉，解掉"每轮重复念同一件事"
4. **双信号 recency**（事件年龄 + 上次被想起的年龄）—— 对齐 AgentGal
5. **kind 配额** —— 防 episode 洪泛（v2 靠固定 cap，v3 靠配额）

### 3.3 两套视图，两种召回（v2 只有一套）

| 视图 | 消费者 | 召回方式 |
|---|---|---|
| **角色视图** ✅ 已有 | 主剧情 LLM（MMT 每轮 / Bond 开场） | 上述管线，第一人称、无 id |
| **组织视图** ✅ 已实现零调用 | digest Round B / 深度阶段 | **实体清单 + 该实体下的认知子图**（id + 邻接表 + 矛盾标记） |

**组织视图随实体层升级**（这是 Round B 能写出正确 `about` 的前提）：
v2 渲染的是"本地 id `u0001..` 的扁平认知列表"；v3 必须额外渲染**实体清单**，
让 LLM 能引用既有实体（而不是每次现场编 subject）：

```
【已知实体】（引用时只能从这里选；确需新建 → 走 new_entity）
  x0000 [self] 我
  x0001 [person] 老师（别名: sensei）
  x0002 [person] 阿露
  x0003 [place] 杂草屋
  x0004 [item] 俄罗斯轮盘巧克力   ← 当前: 已吃掉
```
这**正是 v2 那 7 处 `player` 硬编码特例的通用化**——玩家只是 `etype=person` 的
一个普通实体。

v3 要求：**两个视图都必须有 query**。Bond 的"开场注入后整章不变"（盒是逐字节稳定的）
需要重新设计——见 §6.4 的待拍板项。

### 3.4 渲染的模糊时间（你要的"x 周前"）

```
story_age = now_story_time − node.story_time
   < 1 天        → "今天" / "刚才"
   1~6 天        → "昨天" / "N 天前"
   1~4 周        → "上周" / "N 周前"
   1~11 月       → "上个月" / "N 个月前"
   ≥ 1 年        → "去年" / "N 年前" / "很久以前"（按 significance 调节措辞）
```
- **只在渲染层做**，不落数据（节点存精确游标，文案可随阈值调整而重算）
- 措辞带**情绪权重**：高 significance 的旧事可以说"我一直记得那天"而不是"三年前"
- 对齐 BaiShou 的"时间感"与 AgentGal 的"游戏内日"取向

### 3.5 召回台账（可观测性 —— 先做这个）

对齐 AgentGal 的 `log_retrieval_results`。每轮一行可 grep：

```
recall_view=chara char=igusa_haruka q_len=42
  cand_sem=18 cand_lex=6 cand_cue=2 precious=2 random=1 hop=3
  picked=11 emo=… belief=[m0005:0.72 m0007:0.68] ep=[m0003:0.81 …]
  dropped=7 (cap) embed=ok|keyword_fallback
```

**为什么这条要排在最前**：没有它，后面每一步（阈值标定、时间衰减、组合效果）
都无法验收。这与当初为 VN 加 `bond_board_deliver` 是同一个理由。

---

## 4. 时间架构（v3 新增的第二条主线）

### 4.1 双层时间，绝不混用

| 层 | 用途 | 载体 |
|---|---|---|
| **壁钟** `ts` ✅ 已有 | 审计/排序/调试 | ISO 字符串（**实测格式正常**：`2026-09-07T03:37:20.037943`） |
| **剧情时间** 🔧 v3 新增 | 一切**面向角色**的时间表达 | `story_time` 游标 |

**红线**：任何进 LLM 上下文、任何影响召回排序的时间，**必须用剧情时间**。
壁钟只用于"这段是几点跑出来的"这类工程问题。

### 4.2 游标模型

```jsonc
// world 级：worlds/{world}/story_clock.json
{
  "schema_version": 3,
  "anchor": { "label": "春", "year": 1, "day": 12 },   // 起点（LLM 提议 + 玩家/作者确认）
  "elapsed_days": 47,                                   // 引擎累加（唯一真源）
  "updated_at": "…壁钟…"                                 // 审计
}

// 节点级
"story_time": { "day": 59, "label": "第 1 年 春 第 59 天" }   // = anchor + 偏移
```

### 4.3 谁决定什么（三权分立，与项目既有哲学一致）

| 主体 | 决定 |
|---|---|
| **LLM** | ① 开场锚点提议（"这是春天，开学第 12 天"）② 每段剧情的**间隔**（"这次隔了一周"） |
| **引擎** | ① 累加与**单调性校验**（I6）② **合理性夹取**（一次跳过 ≤ 1 年；负数/0 的非法值 → 走默认）③ 写入游标与节点 |
| **作者/玩家** | 首次锚点可覆盖（settings 或世界创建时填） |

**为什么间隔交给 LLM**：只有它知道"这段戏是紧接着上一场，还是过了一个暑假"。
**为什么引擎必须夹取**：LLM 会写出"过了十年"这种毁掉全部既有记忆相对位置的数字，
而单调性与量级是**可判定的**，不该交给概率模型。

### 4.4 与现有字段的关系

- `segment_id` / `event_seq` ✅ 保留（工程溯源，游标是**语义**时间，两者并存）
- 现有节点的 `ts` 保留；v3 新增 `story_time`。**没有 story_time 的旧节点**：
  迁移时按 `event_seq` 顺序**外插**到游标（单调分配），或标 `story_time: null`
  并在渲染时退化为"很久以前"（§7 迁移策略里二选一）

---

## 5. 组合重组策略（两档，别一次全上）

### 5.1 现状：机制齐全，零调用，且溯源有缺陷

`revise.py` 的 `merge`/`contradict`/`accrue`/`create`/`link`/`unlink`/`resolve` ✅ 全实现，
测试全覆盖，**但零生产调用**（`apply_revision_package` 只出现在测试里）。
真机 `evolution.jsonl`：**6 条，全是 `add`**（haruka 4 + mutsuki 2）。

而 `_build_merged`（`revise.py:421`）的做法有一个**设计缺陷**：
merge 是**造新节点 + 删源节点**，`links/contradictions/event_seq` 取并集，
但**不记录"我从哪几条合并来"** —— 恰好违反 A-Mem 那条纪律
（"without versioned history this is hard to debug and can be unsafe"）。
### 5.2 轻档：无损聚合（放进 digest 常态）

| 动作 | 语义 | 引擎保证 |
|---|---|---|
| `accrue` ✅ 已有 | 同类经历并入既有认知 | 加边 + `occurrences` 计数 + `examples` 追加（≤3）；**不删不改原文** |
| `touch` ✅ 已有 | 纯印证 | 只加边 |

特点：**信息零损失**，可随时重建。这档没有争议，v3 直接启用（v2 只是没接入口）。

### 5.3 重档：深度重组（独立阶段，可撤销）—— **合并策略按 `nature` 分派**

这是 §2.5 第四轴的**用途所在**：`nature` 不是标签，而是**能不能合并的判据**。

| `nature` | 允不允许 merge | 理由 |
|---|---|---|
| `self_image` | **禁止 merge**（I8） | 角色内核。合并 = 抹掉人设张力（"依赖他" + "怕成为负担"必须能并存） |
| `other` | ✅ 允许 | 关于他人的判断会被反复观察，该收敛 |
| `relationship` | ✅ 允许，但**优先"过期退场"而非合并** | 约定会被履行/失效，是**时效**问题不是重复问题 |
| `pattern` | ✅ 优先 `accrue`（计数聚合） | "反复出现"本就该累积，不需要合成新句 |

| 动作 | 语义 | v3 新增纪律 |
|---|---|---|
| `merge` | 多条同 `nature`、同 `about` 的认知合成一条更宽的 | **产物记 `superseded_by`；源节点保留**（I11）；产物 `history` 合并源的历史；**`self_image` 一律拒绝** |
| `contradict` | 标注两条认知互斥 | 双向边；渲染时并列显示，**不自动选边**（让 LLM 在剧情里处理张力） |
| `generalize` | 由 N 条 episode 提升出**新** belief | 必须 ≥2 条支撑（对齐 I2） |
| `merge_entity` | 两个实体实为同一个 | **只做别名软合并**（§2.7 改进④）：别名并入 + `merged_into` 单向标记，**节点保留**、**不改写指向它的 belief** |

**触发时机**（v2 的 `PHASE_DEEP` 声明了但没注册动作）：
- **同 `about` + 同 `nature=other`** 的 belief 数超阈值（如 ≥4）→ 提议 merge
- **同 `about` 的实体重复**（LLM 提议新建时发现别名高度重合）→ 提议 `merge_entity`
- 语义碰撞持续判"同主题"但内容分歧（用 §6.3 的 relevance 分数分布触发）
- 每 N 次 digest 兜底一次

**成本控制**：对齐 AgentGal 的 step3 —— **只在超过阈值时才跑**，
而不是每次 digest 都做一遍全局重组。

### 5.4 撤销与审计

- `history` ✅ 已有：update 时追加 `{episode_id, content, ts}`
- v3 补：`superseded_by`（认知被取代）+ `merged_into`（实体被归并）
  + `evolution.jsonl` 记录 `merge`/`merge_entity` 的**源 id 列表**
- **不做 GC**：被取代的节点留在图里（可回放、可审计、可回滚），只是不再参与常规召回
  （`superseded_by` / `merged_into` 非空的节点权重 ×0.3，或直接从角色视图剔除、
  仅组织视图可见）

---

## 6. LLM 每一步动作（全链路重排）

### 6.1 v2 现状：两步挤在一轮里、动作只有三选一

| 步骤 | v2 实际做什么 | 问题 |
|---|---|---|
| Round A | 时间线 → episodes（`kind` 可出 episode/experience） | 缺时间/地点/在场；两种素材共用一段【MMT 专则】 |
| Round B | 逐条决策（add/touch/update）+ subject 纪律 + content 改写 + experience 判定 + 好感 + evidence | **一轮干六件事**；动作集缺链接/矛盾/组合 |

### 6.2 v3 动作表（每步：输入 / 输出 / 引擎校验 / 失败口径）

#### Step 0 — 时间推进（**新**，极轻）

| | |
|---|---|
| 触发 | 每次 digest 之前 |
| 输入 | 上一游标 + 本段事件流（压缩）+ 上一段末尾 |
| 输出 | `{"elapsed_days": 7, "reason": "暑假过去"}` |
| 引擎校验 | 整数、`0 ≤ x ≤ 365`、超出夹取并记 NOTE |
| 失败 | 默认 `elapsed_days=0`（视为紧接上一场） |

#### Step 1 — 经历记录员（原 Round A，改造）

| | |
|---|---|
| 输入 | 时间线（**放宽到 800~1200 字**，见 §8）+ 画面记忆 + 人设锚 + **当前剧情时间** |
| 输出 | `{"episodes": [{title, narration, verbatim?, tags, significance, epistemic, observer?, subject?}]}` |
| 引擎校验 | 必填字段齐全（**结构完整性逐条校验**，对齐 AgentGal）；`epistemic` 与 `observer` 配对；≤5 条 |
| 失败 | 整步跳过、水位不推进（宁缺勿错） |

**素材分区**（解 v2 的"两种素材共用一个提示词"）：MMT 会话 / Bond 场景
**各自一套 prompt 文件**，靠流程编排选择，而不是在同一段里写【专则】。

#### Step 1.5 — 元数据（**新**，可省）

| | |
|---|---|
| 输入 | Step 1 产物 |
| 输出 | 每条 episode 的 `keywords`（本次可含**物品/地点**线索） |
| 失败 | 退化为 Step 1 自带的 tags（对齐 AgentGal 的 `_apply_default_chunk_metadata`） |

> 存在的理由：关键词质量对召回通道影响很大，而"写叙事"与"抽检索词"
> 是两种不同的注意力模式。省掉也能跑——**这是可选的加档**。

#### Step 1.8 — 实体消解与登记（**新，实体层的入口**）

这是引入实体层后**新增的关键一步**，也是"四种写法"问题的根治点。

| | |
|---|---|
| 触发 | Step 1 之后（与 Step 1.5 可合并成一次调用） |
| 输入 | Step 1 的 episode（含 tags/narration）+ **已知实体清单**（渲染成 `x0001 [person] 老师（别名: sensei）`）+ 关系表（`interperson.json`） |
| 输出 | `{"entities": [{"ref": "x0001"} \| {"new": {"name": "春余", "etype": ["item"], "aliases": []}}], "links": [{"episode": "m0001", "about": ["x0001", "x0004"]}]}` |
| 引擎校验 | ① `ref` 必须存在于清单（**引用幻觉 → 该条作废**，与 Round B 的 id 纪律同源）② `new` 必须过 `etype ⊆ 词表`（I5）③ `new` 与既有实体**别名重合度超阈值 → 引擎改判为 `ref` 并建议 `merge_entity`**（防重复实体）④ 每条 episode 的 `about` 至少 1 个实体 |
| 失败 | 跳过本步 → `about` 留空（该 episode 不进实体车道，仍可被语义/词面通道召回到；**绝不阻断消化**） |

**为什么必须有这一步（而不是让 Round B 顺手写）**：
- **`about` 是归堆键，必须可信**。若交给 Round B（它同时在忙决策/改写/好感），
  就会重演 v2 的 `subject` 自由发挥。
- **实体创建要防重复**。引擎做别名重合度检查、强制走 `ref`，这是**构造性**防重；
  靠提示词"请复用已有实体"是劝不住的（v2 的实证）。
- **代价可控**：可与 Step 1.5 合并为一次调用，不额外增加轮次。

**`self` 与 `player` 不进 LLM 决策**：`x0000`（self）开局自动建、
`about=self` 由引擎按"这是角色自己的反应"判定；玩家实体开局自动建
（`ref=player`，`etype=[person]`，别名取玩家当前名字 + "老师"/"sensei"）。
LLM 只需要在清单里引用它们。

#### Step 2 — 认知整理者（原 Round B，拆分）

| | |
|---|---|
| 输入 | Step 1 产物（真实 id）+ **候选标注**（§6.3）+ **实体清单**（含每实体下的既有认知）+ 人设锚 |
| 输出 | `{"decisions": [...]}` — 见 §6.3 的 v3 动作集 |
| 引擎校验 | id 引用合法；`about` 指向存在的实体（I3）；覆盖检查；`must_link` 检查；`nature` 取值合法（缺省按 §2.5 推断） |
| 失败 | 整包回滚（快照），水位不推进 |

> **与 v2 的关键差别**：v2 给的是"扁平认知列表 `u0001..`"，LLM 得自己猜
> 这条新经历该挂到哪个 subject；v3 给的是**按实体分组的视图**
> （`x0001 老师` 下面列出它已有的 4 条认知），挂靠从"猜"变成"选"。

#### Step 3 — 边状态维护（**新**，仅当本段出现状态变化线索时跑）

> v3 初稿这里叫"物品登记"。引入实体层后**不再是物品专属**——
> 它维护的是"**角色 ↔ 实体**的当前关系状态"（§2.6），物品只是其中一个 `etype`。

| | |
|---|---|
| 触发 | 本段出现 获得/失去/送出/吃掉/遗忘/得知 这类变化线索 |
| 输入 | Step 1 的 episode + **该角色当前的边状态表**（`x0004 俄罗斯轮盘巧克力 → held`）+ 线索 |
| 输出 | `{"edges": [{"entity": "x0004", "state": "consumed", "episode": "m0009"}]}` |
| 引擎校验 | ① `entity` 必须存在且 `etype` 匹配语义 ② `state ∈ {held,lost,given_away,consumed,forgotten}` ③ 目标实体必须是 entity（不是 belief/episode） ④ 同段内同一实体只允许一次转移 |
| 失败 | 跳过（边状态是**锦上添花**，绝不阻断剧情消化） |

**与 Step 1.8 的关系**：Step 1.8 负责"新实体登记 + episode 归到哪些实体"，
Step 3 负责"已有实体的状态迁移"。两者都可省——省了只会丢精度，不会丢内容。

#### Step 4 — 好感与成长（原 Round B 里的一部分，**拆出来**）

| | |
|---|---|
| 输入 | 本段时间线 |
| 输出 | `{"affection_exp_delta": 0~100}` |
| 引擎 | clamp + 幂等事件（**注意 §8 的丢失窗口**） |

> `evidence`：**v3 建议删除**（当前 schema 每轮要 ≤5 条、不校验 quote ∈ 时间线、
> 结果零消费者）。若将来要做"罗盘"，再作为独立步骤回归。

#### Step 9（可选）— 深度重组

见 §5.3。**独立触发、独立预算**，不在每次 digest 里跑。

### 6.3 v2 → v3 动作集对照

**三张动作表**（分属不同步骤，别混）：

**(a) 实体动作（Step 1.8）**
| v2 | v3 | 说明 |
|---|---|---|
| — | 🔧 `ref_entity` | 引用既有实体（**默认路径**——清单里能对上就绝不该新建） |
| — | 🔧 `new_entity` | 新建实体（引擎做别名重合检查；重合 → 改判 `ref` 并建议 `merge_entity`） |
| — | 🔧 `merge_entity` | 别名软合并（§2.7 改进④；节点保留 + `merged_into` 单向） |

**(b) 认知动作（Step 2）**
| v2 | v3 | 说明 |
|---|---|---|
| `add`(belief) | ✅ `add` | 需带 `about`（指向实体）+ 可选 `aspect`/`nature` |
| `add`(experience) | → `add`(belief, `nature=pattern`) | §2.2 的归并（`experience` kind 退役） |
| `touch` | ✅ `touch` | |
| `update` | ✅ `update` | |
| — | 🔧 `link` | **连 belief↔belief**；补关系类型（`same_theme`/`caused_by`/`elaborates`） |
| — | 🔧 `contradict` | 标互斥（双向边） |
| — | 🔧 `accrue` | 无损聚合（`occurrences`/`examples`） |

**(c) 边状态动作（Step 3）**
| v2 | v3 | 说明 |
|---|---|---|
| — | 🔧 `set_edge_state` | 角色 ↔ 实体的当前关系（`held`/`lost`/`given_away`/`consumed`/`forgotten`）——**取代** v3 初稿的 `add_possession`/`update_possession` |

**(d) 深度重组（Step 9，独立阶段）**：`merge` / `generalize`（见 §5.3）

**`must_touch` 的口径变更**：v2 是**结构强制**（出 `add` → 整行作废，见
`parse_round_b`），v3 改为**强提示**：仍标注"疑似同主题 + sim 分数"，但允许 LLM
`add` 并在 `note` 里说明理由。理由：v2 的强制把一个**未标定的阈值**变成了硬闸门
（实测: 真机 4/4 episode 全越线、`best sim 0.92` → 会禁止一切 add；见 §9.1 首次读数）。

**另外**：`must_touch` 的判定范围也应随实体层收窄——**只在同一 `about` 内部比较**
（"这条新经历是否印证了关于老师的某条既有认知"），而不是和全库认知比。
这样"阈值把同关系的不同侧面判成同一件事"就从根上消失了（§11 的实证）。

### 6.4 提示词装配的约束（与盒机制冲突的地方）

`render_character_view` ✅ 目前是 **Bond 开场一次注入、整章不变**（盒B"一次拼死、
逐字节稳定"）。召回一旦变成 query 驱动，就与这个约束冲突。三个选项（**待你拍板**）：

| 选项 | 做法 | 代价 |
|---|---|---|
| A | Bond 仍开场注入，但**开章 query 用触发语料**（chapter_title + 触发 reason + 首场 switch） | 章内不刷新，长章仍然陈旧；但零改动盒机制 |
| B | Bond **每板**刷新召回段，放在**盒外**的动态尾（注记位） | 破"盒逐字节稳定"的前缀缓存收益（§9 缓存会退化） |
| C | 折中：**开场注入 + 关键节点重召回**（换场 / 纪念 / 每 N 板） | 复杂度中等，缓存影响可控 |

我倾向 **C**（换场是天然的记忆检索时机，而且 Bond 已有 `switch` 记录作为触发点）。

---

## 7. 兼容、迁移与回退

### 7.1 schema 版本

`wiki.meta.json` 补 `schema_version`（当前实测只有 `{"digested_seq": 30}`，
**v2 完全没有版本机制**），v3 写 `3`。

### 7.2 迁移映射（基于线上 13 条真实数据，**实体中心版**）

迁移分两段：**先建实体，再把节点挂上去**。

**(a) 实体层生成**（7 条 belief/experience 的 subject → 实体）

| v2 subject | 数量 | → entity | `about` 归属 |
|---|---|---|---|
| `player`（e0001） | 1 | `x_p` [person] 老师（`ref=player`，别名 sensei/老师） | 引擎预建 |
| `我对老师的心意`（mutsuki m0003） | 1 | 同上 `x_p` | `about=x_p`, `aspect="我对他的心意"` |
| `我对阿露的看法`（mutsuki m0004） | 1 | `x_a` [person] 阿露 | `about=x_a`, `aspect="我对她的看法"` |
| `被老师求助时的反应`（haruka m0005） | 1 | `x_s` [self] 我（`x0000`） | `about=x_s`, `aspect="被求助时的反应"` |
| `向老师敞开秘密基地`（m0006） | 1 | `x_p`（关系） | `about=x_p`, `aspect="敞开秘密基地"`, `nature=relationship` |
| `对老师肯定的感受`（m0007） | 1 | `x_s`（自我价值） | `about=x_s`, `aspect="被肯定时的感受"` |
| `对老师的承诺方式`（m0008） | 1 | `x_p`（关系） | `about=x_p`, `aspect="我们的承诺方式"`, `nature=relationship` |

**这张表就是迁移脚本的规则来源**，但脚本**不硬编码这些字符串**——它按
"**subject 文本 → 是否含自身指代/关系词 → 归 self 还是 person**"的启发式来判，
并把**无法判定的打进人工审清单**（干跑 diff 里高亮）。判定启发式：

```
subject 含 我/自己/我的 + 心理词（反应/感受/价值/怀疑） → about=self
subject 含 约定/一起/敞开/承诺/关系词                  → about=person, nature=relationship
subject 形如 "我对X的看法/心意"                        → about=X（先解析 X 是否既有实体）
其余                                                  → about=person, 保持原 subject 为 aspect
```

**(b) 节点迁移**

| v2 形态 | 数量 | → v3 |
|---|---|---|
| `kind=episode`, `source=digest` | 6 | `kind=episode`, `origin=digest`, 补 `about`（由 tags 线索 + 人工审） |
| `kind=belief` | 6 | `kind=belief`, `about`+`aspect`（见上表）, `occurrences=len(links)`, `keywords=tags`, `nature` 推断 |
| `kind=experience`, `subject=player`（`e0001`） | 1 | **拆两条**：① `episode`（老师说了那句话，`reported_fact`, `observer=老师`）② `belief`（`about=x_p`, `nature=pattern`, `pattern` 非空, `occurrences=1`）；② links 指① |
| `epistemic=reported_fact`（`m0002`） | 1 | `episode` 保留；其 narration 讲的是**阿露**的事 → `about=[x_a]`（这正是 §1.3 说的"主体读不出来"，迁移时人工定） |
| `source=experience`（出厂 episode） | **0（线上无）** | 规则保留：`origin=seed` |
| 所有节点 | 13 | 补 `story_time`：按 `event_seq` 单调外插（§10 Q8 建议） |

**迁移脚本必须**：① 幂等（可重跑）② 先备份 `wiki.jsonl.bak.v2`
③ **干跑模式输出 diff + 人工审清单**（实体归属无法判定的条目）供人工过
④ 失败整文件回滚（复用 `atomic_write_lines`）⑤ 迁移后跑 `store.audit()` 断言无悬空引用。

### 7.3 旧档兼容

对齐决策 #4（旧档冻结）：**v3 读 v2（迁移后）**；读**未迁移**的 v2 档 →
按 §7.2 在内存里即时映射（不写盘），保证老世界线可玩。

**⚠️ 一个必须处理的兼容点**：v2 档的 `subject` 在 v3 里语义变了
（从"归属键"降为 `aspect`）。即时映射时必须**为每条旧 belief 现造一个临时实体**
（`about` 指向它，`aspect=原 subject`），否则旧档的 belief 会因 `about` 缺失被 I3 拒收。

---

## 8. 顺带解掉的既有缺陷（与 v3 同批处理更省）

| # | 缺陷 | v3 归属 |
|---|---|---|
| 1 | ⚠️ `render_timeline` 默认 `max_paragraph_chars=120` → 一个 bond 板砍到 120 字，**verbatim/evidence 的"逐字"物理不可能** | §6.2 Step 1 输入放宽到 800~1200（或按记录渲染） |
| 2 | ⚠️ `save()` + 推进水位 + `save_meta()` **三次独立写** → meta 失败则水位回退重跑，而重跑去重键只认 `main_text` 全等 → **重复节点** | v3 把"节点写入 + 水位推进"收成**一次原子提交** |
| 3 | ⚠️ 好感 delta 丢失窗口（wiki+水位先提交、`affection` 事件后写 → 中间崩则数字不存在） | §6.2 Step 4 与提交同临界区 |
| 4 | ⚠️ `evidence` 白花钱且无消费者 | §6.2 建议删除 |
| 5 | ⚠️ 认知窗口 `COGNITION_CAP=12` 饱和后低 sig 认知永不可见 | §3.2 改成 query top-k，天然解掉 |
| 6 | ⚠️ 三通道召回零调用 / `render_organize_view` 零调用 / `apply_revision_package` 零调用 | §3 / §5 接线 |
| 7 | ⚠️ `CAND_HIGH=0.50` 未标定、且 embedding 降级静默 | §6.3 改强提示 + **按模型标定**（§10 已有实测分数） |
| 8 | ⚠️ 无 `last_recalled_at` → 每轮重复念同一件事 | §3.2 通道回写 |

---

## 9. 实施路线（分阶段、可回退，每阶段一提交）

> 纪律沿用项目既有：**每节点一提交**；文档与代码同阶段更新；改 prompt 必刷夹具。

| 阶段 | 内容 | 完成标志 |
|---|---|---|
| **V3-0** ✅ **已落地（2026-09-13）** | **召回台账**（§3.5）+ 阈值可配置化 | ✅ 真机一行日志能看出"这轮给了 LLM 哪几条"——见 §9.1 |
| **V3-1a** | **实体层地基**：`entity` kind + `etype`（5 类）+ `about`/`aspect`/`nature` 字段 + 不变量 I1~I12 + `_PREFIX`（x 入、e/p 出）+ `origin` 改名 | 单测：validate/normalize/实体引用校验/软合并/渲染分组全绿 |
| **V3-1b** | **`experience` kind 归并** + `player` 特例通用化（`is_player_experience` 7 处消费点改走 `about`+`nature`） | 单测：旧 experience 语义可表达；无 `PLAYER_SUBJECT` 残留 |
| **V3-2** | **迁移脚本** + `schema_version`（13 节点 + 7 条 subject→实体映射，干跑 diff + 人工审清单） | 旧档迁移后 `store.audit()` 无悬空引用、逐字节可回放 |
| **V3-3** | **读路径接上实体车道召回**（§3.2 两级 + 模糊时间渲染 §3.4） | 台账显示 entity 命中与车道配额；belief 不再"取前 5" |
| **V3-4** | **时间架构**（§4）：游标 + Step 0 + 模糊渲染 + 衰减接进召回 | 剧情跨段后"三周前"正确出现 |
| **V3-5** | **LLM 动作扩展**：Step 1.8 实体消解 + `link`/`contradict`/`accrue` + Step 3 边状态 + 动作集三表落地 + **`must_touch` 收窄到同一 `about`（Q11）** | 真机一章后 `evolution.jsonl` 不再清一色 add；台账 `forced=` 显著下降 |
| **V3-6** | **深度重组阶段**（§5.3）+ `superseded_by`/`merged_into` 溯源 + 按 `nature` 分派 | 阈值触发的 merge 可审计、可回滚；`self_image` 拒合并有测试 |
| **V3-7** | **Bond 章内重召回**（§6.4 选项 C） | 长章后半段的记忆不再陈旧 |

**依赖**：
- V3-0 ✅ 独立完成
- **V3-1a 是一切的前提**（V3-1b/2/3/4/5 都依赖它）
- V3-2 依赖 V3-1b；V3-3 依赖 V3-1a；V3-5 依赖 V3-2（迁移完才有干净的 `about`）
- V3-6 依赖 V3-5；V3-7 依赖 V3-3
- **V3-4 与 V3-3 可并行**（都只依赖 V3-1a）

### 9.1 V3-0 落地记录（2026-09-13）

| 交付 | 位置 |
|---|---|
| 召回旋钮（`[recall]` 分组，默认 = v2 常量） | `core/brain/wiki_v2/recall_config.py` · `settings.toml [recall]` |
| 召回台账（写路径 + 读路径） | `core/brain/wiki_v2/recall_ledger.py` |
| 写路径打点（候选碰撞汇总） | `core/brain/wiki_v2/digest.py::_round_b_material` |
| 读路径打点（注入视图桶统计） | `core/brain/wiki_v2/render.py::_bucket_view`（分桶抽成单一实现）+ `core/momotalk.py::_log_read_ledger` |
| 契约测试 11 例 | `tests/core/test_wiki_recall_ledger.py` |

**行为零变化**（这是 V3-0 的承诺，已实测）：
- 渲染文本逐字节不变（真机 8 节点 = 999 字，sha256 前 16 位 `e8eff9dc55f99b5d`）
- `recommend_candidates` 默认 `k` 与显式 `k=CAND_K` 结果相同
- 不配 `[recall]` 时全部走默认；配坏值/TOML 损坏 → 回落默认、不抛

**真机首次读数（就是 v3 要解的那个病）**：

```
recall_read  surface=chara char=igusa_haruka total=8 picked=8 dropped=0 mode=off
             buckets=seed:0/0 episode:4/4 belief:4/4 player:0/0 reported:0/0
recall_write char=igusa_haruka eps=4 collide=12 forced=100% med_only=0 none=0
             cands=12 best=0.92 mode=semantic thr=0.50/0.25 ⚠forced_high
```

两条读数各自钉住一个 v3 要解的问题：
- **读路径 `dropped=0`** 是**假阴性**——库里只有 8 条、低于全部 cap，所以"看不出来"。
  等节点数超过 cap（belief > 5）才会出现 `dropped>0`；这正是 §3.1 说的"第 6 条
  以后的 belief 永远读不出来"，台账现在会**提前**把它显示出来。
- **写路径 `forced=100% mode=semantic`** 是**真问题当场暴露**：真实 4 条 episode
  在**语义模式**（非降级）下全部被判【疑似同主题】→ `parse_round_b` 结构强制
  touch/update → **新 belief 永远长不出来**。这条链此前在日志里完全不可见。

回归：**605 passed**（594 + 11）。


---

## 10. 待拍板

### 10.1 ✅ 已裁决（2026-09-13 用户拍板）

| # | 问题 | 裁决 |
|---|---|---|
| **Q1** | `experience` kind 是否归并？ | ✅ **归并**——`pattern` 字段 + `occurrences`；`experience` kind 退役（依据 §1.2 三处自相矛盾） |
| **Q1b** | 实体层要哪些 `etype`？ | ✅ **`self` / `item` / `place` / `knowledge`**（+ 必然存在的 `person`，共 5 类） |
| **Q1c** | belief 粒度：多条并存 vs 合成一条 | ✅ **多条并存**——不做"对 X 的看法"单条总结（理由 §2.1：200 字上限 + 重写漂移 + 矛盾无法表达） |
| **Q3** | 物品"转手"的数据形态 | ✅ 演化为**通用边状态**（§2.6）——不再是物品专属字段；`possession` kind 取消 |
| **Q4** | merge 后源节点 | ✅ **保留 + `superseded_by`**（I11）；实体合并同理走**别名软合并**（§2.7 改进④） |

### 10.2 ⏳ 仍待你拍板

| # | 问题 | 我的倾向 | 影响 |
|---|---|---|---|
| **Q2** | 剧情时间**锚点**谁定？间隔谁给？ | LLM 提议 + 引擎校验夹取（§4.3） | 决定 V3-4 |
| **Q5** | Bond 章内召回：A 开场固定 / B 每板刷新 / **C 关键点重召回** | C（换场是天然检索时机，Bond 已有 `switch` 触发点） | 决定 V3-7 与盒机制是否破 |
| **Q6** | `evidence` 直接删除还是保留待用？ | 删除（§8-4：零消费者 + 不校验逐字） | 决定 Step 4 契约 |
| **Q7** | Step 1.5（关键词抽出）做不做？ | 做（对召回通道有价值，且可降级） | 决定调用数 +1 |
| **Q8** | 旧节点没有 `story_time` 时：外插还是 `null` 退化？ | 外插（按 event_seq 单调） | 决定 V3-2 迁移质量 |
| **Q9**（新） | 边状态存哪：`soul/bonds.jsonl` 独立文件 vs `wiki.meta.json` 的 relations 段？ | 独立文件（与 wiki.jsonl 并列，便于 diff 与备份） | 决定 V3-5 存储形态 |
| **Q10**（新） | Step 1.8 与 Step 1.5 **是否合并成一次调用**？ | 合并（省一轮；两者都是"从 episode 抽结构化信息"，注意力模式相同） | 决定调用数与 V3-5 编排 |
| **Q11**（新） | `must_touch` 是否**收窄到同一 `about` 内**比较？ | 收窄（§6.3 末——从根上消除"同关系不同侧面被误判同主题"，真机 4/4 越线正是这个病） | 决定 V3-5 判定范围，**建议优先级最高** |

---

## 11. 边界（v3 不做的事）

- **不做**跨世界线/跨角色的记忆合并（世界线隔离是硬语义，`DESIGN_BRAIN §1.4`）
- **不做**GC / 物理删除节点（append-only 精神；被取代者保留）
- **不做**在节点里存"情感数值"（好感仍是事件流派生，数值不进节点）
- **不让**主 LLM 写 `id`/`story_time`/`occurrences`/`history`（引擎字段，防幻觉）
- **不引入**向量数据库依赖（当前是 JSONL + 进程内向量；要换后端只换 `embed_fn`，
  与 v2 预留接口一致）
- **不做**多角色的 NPC 记忆网络（那是 `core/DESIGN_MULTI_CHAR.md` 的线，v3 不碰）
