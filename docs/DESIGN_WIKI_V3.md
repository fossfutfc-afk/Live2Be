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
| **节点** | 4 个 kind 混用（`episode`/`experience`/`belief` + `source=experience`），一词四义 | **3 kind**：`episode`（发生的事）/ `belief`（持久认知）/ `possession`（持有物）；**观察到的规律降为 belief 的子形态** |
| **时间** | **零游戏内时间**，只有壁钟 `ts` | 双层：壁钟（审计）+ **剧情时间游标**（锚点 + 累积流逝）；渲染模糊成"三周前" |
| **召回** | 静态分桶按 `significance` 取前 N（**无 query**）；三通道召回零生产调用方 | **混合召回**：向量 + 词面 + 线索 → 融合 → 时间/重要性加权 → 跳转扩展；**且可观测** |
| **LLM 动作** | Round A 记录 + Round B 三选一（add/touch/update） | **多步**：记录 → 元数据 → 组织决策（含**链接/矛盾/组合**）→ 时间推进；动作集扩到 8 |
| **组合** | `merge`/`accrue` 代码全套 ✅ 但**零生产调用** | 两档：**无损聚合**（digest 内）与**深度重组**（独立阶段，带溯源与撤销） |

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
| 新增 `possession` | **同上全部**（新 kind 要过每一道闸） |
| 组合重组 | `revise` 规则引擎 · `store` 不变量 · 新增阶段编排 · `digest_registry` 新动作 |
| 时间架构 | 每个节点的字段 · `render` 文案 · `recall` 衰减 · `store` 需要时间游标 |

打四次补丁 = 把同一片代码动四遍，且中间态是"半新半旧 schema"（新旧 kind 共存、
时间字段半有无）。**重构一次 = 动一遍 + 带 `schema_version` 迁移**。

**代价现在最低**：全库 13 个节点，迁移脚本几十行；等真跑几百条就不是这个量级。

### 1.5 v3 明确**不**重写的东西（保住已建成的资产）

| 保留 | 理由 |
|---|---|
| `events.jsonl` append-only 真源 | 事实主线，v3 不碰 |
| `digested_seq` 水位 / 原子提交 / 快照回滚 | 增量与幂等已正确 |
| `history` 版本化字段 ✅ | 正是 A-Mem 那条"必须版本化"纪律的落地物——v3 要**用它**，不是重塑它 |
| `apply_revision_package` 规则引擎与测试 ✅ | merge/contradict/accrue 逻辑与校验已写好，v3 只补**入口 + 溯源** |
| 上两轮加的观测/降级埋点 | 不动 |

---

## 2. 节点新概念（kinds / 字段 / 前缀 / 不变量）

### 2.1 两个正交的轴（v2 把它们压在一起了）

```
轴一 kind      —— 节点的"形状"（要不要时间区间、要不要证据链、怎么渲染）
轴二 epistemic —— 认知的"来源性质"（亲历 / 听说 / 推断 / 猜测）
```

v2 的问题是：**用 kind 兼职表达了"关于谁"与"来源"**。v3 把"关于谁"交给 `subject`，
"来源性质"交给 `epistemic`，kind 只管形状。

### 2.2 v3 的 kind 集合（3 个）

#### (1) `episode` — 发生的事（一次性，有起有落）

```jsonc
{
  "id": "m0001", "kind": "episode",
  "title": "老师拜托我调查杂草",          // 8-16 字
  "narration": "第一人称浓缩……",          // ≤300 字，质感优先不升华
  "verbatim": "老、老师千万不要这么说！",   // 可选，逐字
  "tags": ["杂草调查", "报告"],             // ≤4，检索导向
  "significance": 0.7,                     // 0~1 行为锚点
  "epistemic": "observed_fact",            // observed_fact | reported_fact
  "observer": "",                          // reported_fact 时= 转述者（"老师"）
  "subject": "",                           // v3 新增可选：事件主体（他人事件时填）
  "story_time": { ... },                   // §4 时间游标
  "segment_id": "seg-30", "event_seq": [30],
  "origin": "digest",                      // digest | seed（原 source）
  "links": ["m0005"]                       // 它支撑的认知
}
```

**v3 相对 v2 的变化**：新增可选 `subject`（把"关于谁"从 narrator 文风里解放出来）、
`source`→`origin` 改名（消除与 `experience` 的拼写冲突）。

#### (2) `belief` — 持久认知（结论，非事件）

```jsonc
{
  "id": "m0005", "kind": "belief",
  "subject": "被老师求助时的反应",          // 稳定维度命名（人/关系/互动模式）
  "content": "老师一开口请我帮忙，我会先……",  // ≤200 字，结论式
  "growth": "学着在自我怀疑之前先承认……",   // 可选，成长方向
  "pattern": "",                            // v3：反复出现时填"模式句"（见下）
  "occurrences": 3,                         // 引擎字段，= 支撑 episode 条数（不信任 LLM）
  "keywords": ["老师", "自我怀疑"],          // v3 新增：与 tags 分开，供检索
  "significance": 0.6,
  "epistemic": "inferred_belief",           // 引擎强制
  "history": [ { "episode_id": "m0001", "content": "…", "ts": "…" } ],  // ✅ 已有
  "superseded_by": "",                      // v3 新增：被更新的认知取代时填写
  "story_time": { ... },
  "origin": "digest",
  "links": ["m0001"]                        // ≥1 条支撑，含 episode 与 belief
}
```

**`experience` 的去向（v3 的核心裁决）**

| v2 | v3 |
|---|---|
| kind `experience` = 重复模式 | **降为 belief 的形态**：`pattern` 非空 + `occurrences ≥ 2` 即"规律型认知"，渲染成 `【模式】` 前缀 |
| `subject="player"` = 玩家画像 | **仍是 belief**，`subject` 填 `player`（渲染进独立的【老师的事】段） |
| 护栏"player experience 永不被内容去重/合并掉" | 改为**按 subject 的护栏**：`subject == "player"` 的 belief 不被 merge 入其他 subject |

理由：一个字符对老师的稳定认知（"老师总靠浓缩咖啡硬撑"）**本来就是 belief**；
"反复出现"是 `occurrences` 的事。保留独立 kind 的唯一实际收益是"决策表里多一个选项"，
而代价是**每一道 kind 闸都要多写一个分支**（`_REQUIRED`/`_PREFIX`/`normalize`/
`render` 分桶/`recall` 过滤/`revise` 目标/契约枚举 7 处），并且制造了 §1.2 那三处自相矛盾。

> 宁可少一个 kind、多一个字段：kind 是**编译期**概念（每处消费者都要枚举），
> 字段是**运行期**概念（不关心的消费者直接忽略）。

#### (3) `possession` — 持有的物品（v3 新增）

```jsonc
{
  "id": "p0001", "kind": "possession",
  "item": "写着杂草名字的卡片",              // 物品名（稳定标识）
  "state": "held",                          // held | lost | given_away | consumed
  "holder": "igusa_haruka",                 // 当前持有者（角色 id 或 player）
  "obtained": { "episode": "m0001", "story_time": { ... } },   // 获得出处
  "lost": null,                             // 失去/转手的出处（同构）
  "keywords": ["卡片", "杂草"],
  "significance": 0.4,
  "story_time": { ... },
  "origin": "digest",
  "links": ["m0001"]                        // 获得/失去它的 episode
}
```

**为什么必须是独立 kind（而不是 belief 的一种）**

| 判据 | 说明 |
|---|---|
| 有**身份** | 一个具体物品（"那张卡片"）可以被反复提起、被指认；belief 是一次性结论 |
| 有**状态机** | held → given_away / lost / consumed；belief 没有状态迁移（只有改写） |
| 有**时间区间** | "持有"是**区间**而非时刻；§4 的时间游标正好表达 |
| 有**资产锚点** | `assets/illustration/{char}/{outfit}/possession/` **已在文档里预留**（`EMOTIONS_CONFIG.md §28/49` 明写"角色级物品图"），只是尚无实体目录。节点化后可与图一一对应 |

**关键设计点：转手用边表达，不用字段覆盖**

"我把发夹送给她了"之后，**双方都不应显示为持有**。所以 `holder` + `state` 是**当前快照**，
而**历史在 `links` + `lost.episode`**。v3 不做"拥有边"的图结构（那会让每次转手写成两条边），
而是**快照 + 溯源**：谁改的、哪条 episode 改的，都能追。

**清单类物品的归并**：`keywords` 用于"她还记得自己有哪些东西"这类召回；
同一 `item` 的重复出现**不新建节点**，而是追加 `links`（与 belief 的 `occurrences` 同构）。

### 2.3 字段总表（v3 定稿）

| 字段 | 适用 kind | 性质 | 说明 |
|---|---|---|---|
| `id` / `kind` / `significance` / `epistemic` / `tags` / `links` | 全部 | 引擎/LLM 混合 | `links` 方向 = "支撑/相关"无向语义，渲染时按 kind 解释 |
| `story_time` | 全部 | 引擎写、LLM 提议 | §4 |
| `origin` | 全部 | 引擎 | `digest` / `seed`（原 `source`） |
| `segment_id` / `event_seq` / `ts` | 全部 | 引擎 | 溯源，LLM 不可写 |
| `title` / `narration` / `verbatim` / `observer` / `subject` | episode | LLM | `subject` 可选（他人事件） |
| `subject` / `content` / `growth` / `pattern` / `keywords` / `history` | belief | LLM（`history` 引擎） | `occurrences` 引擎数 |
| `item` / `state` / `holder` / `obtained` / `lost` | possession | LLM 提议、引擎校验 | |
| `contradictions` / `superseded_by` | belief/episode | 引擎 + 深度阶段 | §5 |
| `notes` | 全部 | 引擎 | 只允许追加（出厂基座纪律保留） |

### 2.4 id 前缀与 `_PREFIX` 表

v2 实测（`store.py:25`）：`{"experience": "e", "episode": "m", "belief": "m"}`
—— **episode 与 belief 共用 `m`**（因为两者都是"动态产出"）。

v3 变为：

```python
_PREFIX = {"episode": "m", "belief": "m", "possession": "p"}
```

- `e` 前缀**退役**（随 `experience` kind 归并）—— 迁移时 `e0001` → `m00xx`，
  **id 会变**，因此迁移脚本必须**同步改写所有指向它的 links/contradictions**
  （`store.audit` 的悬空引用检查会兜住遗漏，见 §7.2）。
- `p` 前缀给 `possession`；与 `m` 分开的理由：物品有**状态机**与**当前快照**语义，
  在日志与调试里一眼能区分"这是事件/认知"还是"这是物品"。
- `c` 前缀（出厂基座）已于 2026-09-02 随 `fact` 退役，v3 不恢复
  （出厂 episode 改用 `origin="seed"` 表达，见 §2.2）。

### 2.5 不变量（引擎强制，入仓时校验）

```
I1  belief.epistemic == "inferred_belief"（认知不伪装成事实）          ✅ v2 已有
I2  belief.links ≥ 1 条支撑（episode 或 belief）——无支撑不升华          ✅ v2 已有
I3  possession.state ∈ {held,lost,given_away,consumed}；given_away 必须有 holder
I4  belief.occurrences == 支撑它的 episode 条数（引擎数，不信任 LLM）    ⚠️ v2 的 count 只对 experience 生效
I5  subject == "player" 的 belief 不被 merge（只可 update）
I6  story_time 单调不减（同一条世界线的节点按 event_seq 排序，story_time 不得倒退）
I7  superseded_by 指向存在的节点；被取代者**保留在图里**（不回 GC）
I8  history 只增不改（改写溯源，v2 已有）
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

### 3.2 v3 召回管线（引擎侧确定性，不进 LLM）

```
query（本轮情境文本）
  │
  ├─ 通道1 语义：embedding(query) × 节点向量 → top-k_sim          [embed_fn 可缺]
  ├─ 通道2 词面：BM25 / tags∩ / subject 命中 → top-k_lex          [零依赖兜底]
  ├─ 通道3 线索：本轮提到的具名实体（人名/物品/地点）→ 命中其节点     [v3 新增]
  ├─ 通道4 珍贵保底：significance ≥ 0.8 且未命中 → 补 n_precious     ✅ 设计已有
  └─ 通道5 随机摘段：30% 珍贵加权 / 70% 对数正态(剧情年龄)加权       ✅ 设计已有
        │
        ▼  合并去重(id)
  融合打分 = w_rel·relevance + w_time·recency + w_imp·importance      ← v3 核心
        │   relevance = w_vec·cos + w_lex·bm25_norm                   （AgentGal 同构）
        │   recency   = 双信号：剧情年龄衰减 × 上次被想起的年龄衰减
        ▼
  一跳扩展（沿 links ∪ contradictions）                               ✅ 设计已有
        │
        ▼
  按 kind 配额截断（防单一 kind 挤占）→ 渲染
        │
        ▼
  写召回台账（§3.5）+ 回写 last_recalled（剧情时间）
```

**关键改动 vs v2 设计**：
1. **`recency` 用剧情时间，不用壁钟**（§4 落地后才有意义）
2. **`last_recalled_at`（剧情时间）** —— 刚念过的自然下沉，解掉"每轮重复念同一件事"
3. **双信号 recency**（事件年龄 + 上次被想起的年龄）—— 对齐 AgentGal
4. **kind 配额** —— 防 episode 洪泛把 belief 挤出去（v2 靠固定 cap，v3 靠配额）

### 3.3 两套视图，两种召回（v2 只有一套）

| 视图 | 消费者 | 召回方式 |
|---|---|---|
| **角色视图** ✅ 已有 | 主剧情 LLM（MMT 每轮 / Bond 开场） | 上述管线，第一人称、无 id |
| **组织视图** ✅ 已实现零调用 | digest Round B / 深度阶段 | 子图 + 邻接表 + id + 矛盾标记 |

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

### 5.3 重档：深度重组（独立阶段，可撤销）

| 动作 | 语义 | v3 新增纪律 |
|---|---|---|
| `merge` | 多条认知合成一条更宽的 | **产物记 `superseded_by`；源节点保留**（I7）；产物 `history` 合并源的历史 |
| `contradict` | 标注两条认知互斥 | 双向边；渲染时并列显示，**不自动选边**（让 LLM 在剧情里处理张力） |
| `generalize` | 由 N 条 episode 提升出**新** belief | 必须 ≥2 条支撑（对齐 I2） |

**触发时机**（v2 的 `PHASE_DEEP` 声明了但没注册动作）：
- 同 `subject` 的 belief 数超阈值（如 ≥4）→ 提议 merge
- 语义碰撞持续判"同主题"但内容分歧（用 §3.2 的 relevance 分数分布触发）
- 每 N 次 digest 兜底一次

**成本控制**：对齐 AgentGal 的 step3 —— **只在超过阈值时才跑**，
而不是每次 digest 都做一遍全局重组。

### 5.4 撤销与审计

- `history` ✅ 已有：update 时追加 `{episode_id, content, ts}`
- v3 补：`superseded_by` + `evolution.jsonl` 记录 `merge` 的**源 id 列表**
- **不做 GC**：被取代的节点留在图里（可回放、可审计、可回滚），只是不再参与常规召回
  （`superseded_by` 非空的节点权重 ×0.3，或直接从角色视图剔除、仅组织视图可见）

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

> 存在的理由：关键词质量对 §3.2 通道2/3 影响很大，而"写叙事"与"抽检索词"
> 是两种不同的注意力模式。省掉也能跑——**这是可选的加档**。

#### Step 2 — 认知整理者（原 Round B，拆分）

| | |
|---|---|
| 输入 | Step 1 产物（真实 id）+ **候选标注**（§6.3）+ 现有认知列表（本地 id `u0001..`）+ 人设锚 |
| 输出 | `{"decisions": [...]}` — 见 §6.3 的 v3 动作集 |
| 引擎校验 | id 引用合法；覆盖检查；`must_link` 检查；subject/kind 约束 |
| 失败 | 整包回滚（快照），水位不推进 |

#### Step 3 — 物品登记（**新**，仅当 Step 1 出现物品线索时跑）

| | |
|---|---|
| 输入 | Step 1 的 episode + **现有 possession 清单** + 线索 |
| 输出 | `{"possessions": [{"item","state","holder","episode_ref"}]}` |
| 引擎校验 | `item` 去重（同名追加 links 不新建）；state 合法性（I3）；holder 必须是已知角色或 player |
| 失败 | 跳过（物品是**锦上添花**，绝不阻断剧情消化） |

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

| v2 | v3 | 说明 |
|---|---|---|
| `add`(belief) | ✅ `add` | |
| `add`(experience) | → `add`(belief, 带 `pattern`) | §2.2 的归并 |
| `touch` | ✅ `touch` | |
| `update` | ✅ `update` | |
| — | 🔧 `link` | **连 belief↔belief**；补 `kind` 字段说清关系（`same_theme`/`caused_by`/`elaborates`） |
| — | 🔧 `contradict` | 标互斥（双向边） |
| — | 🔧 `accrue` | 无损聚合（`occurrences`/`examples`） |
| — | 🔧 `add_possession` / `update_possession` | 物品登记与状态迁移 |
| — | 🔧 `merge` | 深度重组档（独立阶段） |

**`must_touch` 的口径变更**：v2 是**结构强制**（出 `add` → 整行作废，见
`parse_round_b`），v3 改为**强提示**：仍标注"疑似同主题 + sim 分数"，但允许 LLM
`add` 并在 `note` 里说明理由。理由：v2 的强制把一个**未标定的阈值**变成了硬闸门
（实测两个模型下 6/6 全部越线 → 会禁止一切 add）。

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

### 7.2 迁移映射（基于线上 13 条真实数据）

| v2 形态 | 数量 | → v3 |
|---|---|---|
| `kind=episode`, `source=digest` | 6 | `kind=episode`, `origin=digest` |
| `kind=belief` | 6 | `kind=belief`, `occurrences=len(links)`, `keywords=tags` |
| `kind=experience`, `subject=player`（`e0001`） | 1 | **拆两条**：① `episode`（老师说了那句话，`reported_fact`, `observer=老师`）② `belief`（`subject=player`, `pattern` 非空, `occurrences=1`）；② links 指① |
| `epistemic=reported_fact` + `subject`（`m0002`） | 1 | `episode` 保留；`subject` 保留（v3 新字段正好容纳） |
| `source=experience`（出厂 episode） | **0（线上无）** | 迁移规则保留：`origin=seed` |
| 所有节点 | 13 | 补 `story_time`：按 `event_seq` 单调外插，或置 `null`（渲染退化"很久以前"） |

**迁移脚本必须**：① 幂等（可重跑）② 先备份 `wiki.jsonl.bak.v2`
③ 干跑模式先输出 diff 供人工审 ④ 失败整文件回滚（复用 `atomic_write_lines`）。

### 7.3 旧档兼容

对齐决策 #4（旧档冻结）：**v3 读 v2（迁移后）**；读**未迁移**的 v2 档 →
按 §7.2 在内存里即时映射（不写盘），保证老世界线可玩。

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
| **V3-1** | **节点层换代**：3 kind + 字段表 + 不变量（I1~I8）+ `origin` 改名 | 单测：validate/normalize/渲染分桶/契约枚举全绿 |
| **V3-2** | **迁移脚本** + `schema_version`（13 节点，干跑 diff 人工审） | 旧档迁移后逐字节可回放 |
| **V3-3** | **读路径接上混合召回**（§3.2 + 模糊时间渲染 §3.4） | 台账显示双通道命中；belief 不再"取前 5" |
| **V3-4** | **时间架构**（§4）：游标 + Step 0 + 模糊渲染 + 衰减接进召回 | 剧情跨段后"三周前"正确出现 |
| **V3-5** | **LLM 动作扩展**：`link`/`contradict`/`accrue` + Step 3 物品 + 动作集表落地 | 真机一章后 `evolution.jsonl` 出现 touch/link（不再是清一色 add） |
| **V3-6** | **深度重组阶段**（§5.3）+ `superseded_by` 溯源 | 阈值触发的 merge 可审计、可回滚 |
| **V3-7** | **Bond 章内重召回**（§6.4 选项 C） | 长章后半段的记忆不再陈旧 |

**依赖**：V3-0 ✅ 独立完成；V3-1 必须先于 V3-3/4/5；V3-2 依赖 V3-1；V3-6 依赖 V3-5。

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

## 10. 待拍板（阻塞项，按需要你回答的顺序）

| # | 问题 | 我的倾向 | 影响 |
|---|---|---|---|
| **Q1** | `experience` kind 是否按 §2.2 **归并进 belief**（`pattern` 字段 + `occurrences`）？ | 归并（理由是 §1.2 那三处自相矛盾） | 决定 V3-1 的 kind 数量与全部消费者 |
| **Q2** | 剧情时间**锚点**谁定？间隔谁给？ | LLM 提议 + 引擎校验夹取（§4.3） | 决定 V3-4 |
| **Q3** | `possession` 的"转手"用**快照 + 溯源**（我倾向）还是**时间区间边**？ | 快照 + 溯源（§2.2） | 决定 possession 的数据形态 |
| **Q4** | merge 后源节点：**保留 + `superseded_by`**（我倾向）还是删除？ | 保留（对齐 A-Mem 版本化纪律，I7） | 决定 V3-6 与存储增长 |
| **Q5** | Bond 章内召回：A 开场固定 / B 每板刷新 / **C 关键点重召回**（我倾向） | C | 决定 V6-7 与盒机制是否破 |
| **Q6** | `evidence` 直接删除还是保留待用？ | 删除（§8-4） | 决定 Step 4 契约 |
| **Q7** | Step 1.5（关键词抽出）做不做？ | 做（对通道2/3 有价值，且可降级） | 决定 V3-5 的调用数 +1 |
| **Q8** | 旧节点没有 `story_time` 时：外插（我倾向）还是 `null` 退化？ | 外插（按 event_seq 单调） | 决定 V3-2 迁移质量 |

---

## 11. 边界（v3 不做的事）

- **不做**跨世界线/跨角色的记忆合并（世界线隔离是硬语义，`DESIGN_BRAIN §1.4`）
- **不做**GC / 物理删除节点（append-only 精神；被取代者保留）
- **不做**在节点里存"情感数值"（好感仍是事件流派生，数值不进节点）
- **不让**主 LLM 写 `id`/`story_time`/`occurrences`/`history`（引擎字段，防幻觉）
- **不引入**向量数据库依赖（当前是 JSONL + 进程内向量；要换后端只换 `embed_fn`，
  与 v2 预留接口一致）
- **不做**多角色的 NPC 记忆网络（那是 `core/DESIGN_MULTI_CHAR.md` 的线，v3 不碰）
