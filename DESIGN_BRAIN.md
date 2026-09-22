# Live2Be Brain 设计（合并版）

> ⚠️ **2026-09-21 状态**: 本文档里的 **digest v1（Sleep 式）算法描述已整体作废**——
> `core/brain/{consolidation,hippocampus,recall}.py`、`llm/prompts/digest.md`、
> `contract/schema.build_digest_schema()` 均已删除; 现役记忆 = `core/brain/wiki_v2/`
> （读 `core/brain/wiki_v2/AGENT_BRAIN.md`）。**本文只当历史读**。
> **2026-09-02 合并**: 由 `core/DESIGN_BRAIN.md`（digest 算法设计）+ `docs/DESIGN_MEMORY.md`
> （记忆架构/业界查证/升级路径）合并而来，放置根目录统一维护。
> **一切以代码为准**——本文档描述的是当前实现（✅）与规划（🔧）/废案（⛔）。
> 原两份文件（core/DESIGN_BRAIN.md、docs/DESIGN_MEMORY.md）已归档至 docs/archive/。
>
> 关联文档: `docs/DESIGN_SEGMENT.md`（段模型, digest 边界）· `docs/DESIGN_WORLD.md`
> （世界对齐）· `docs/archive/DESIGN_SAVE.md §4.6`（存储, 已归档）· `docs/archive/world_model_evolution.md`（已归档）
> （世界模型演进史）· ~~`llm/prompts/digest.md`（digest 规则）~~ / ~~`build_digest_schema`~~
> （两者 2026-09-21 随 digest v1 删除; 现役 = `digest_v2_round_a/b.md` +
> `contract/digest_registry.py`）。

---

## 0. 核心哲学

> **LLM ≠ 角色。Brain = 角色。LLM 只是角色的"语言中枢"。**

- **brain 是算法, 不是跨 session 实体**: 每个世界线的角色用自己的 events.jsonl
  调同一套算法, 产出各自私有的成长——**无角色级 wiki、无归并、无迁移**。
- **搭积木论证**: 纯事件流回灌 = 每次从基座重新搭积木（结果无保证）; wiki =
  "之前搭好的基础", 每次从基础上继续搭一块——这才是人的成长过程。
- **平行世界**: 每个世界（周目）是独立世界线集合, 另一个世界的成长与本世界无关。

---

## 1. 现状方案总览（2026-09-02, 以代码为准）

### 1.1 存储布局（v2 世界模型, 已实现 ✅）

```
data/worlds/
  {world_id}/                            # 世界槽位 world1..worldN（world.json active 切换）
    world.json                           # 世界 meta（created_at / active）
    characters/
      {char_id}/                         # 世界里每角色【一条连续线】（惰性创建）
        events.jsonl                     # ★ 事件流唯一真源（mmt + bond + l2d + marker + affection）
        wiki.json                        # digest 产物（brain 派生, 可删可重算）
        meta.json                        # 线状态（created_at/ended 等）
        progress.json                    # 轮数（展示用）
    snapshots/                           # 存档点（森林时点快照, 预留 🔧）
```

- `WikiStore` 路径 = `worlds/{world}/characters/{char}/wiki.json`（session_id 参数
  保留兼容, 不再参与路径）——**wiki 属于"世界线"而非"会话"**。
- 旧 `data/{char}/sessions/` 结构已被世界模型取代（store.py v2）。

### 1.2 最小单元与 digest 触发点

```
段（SEGMENT）= Trigger mmt（铺垫） + Bond story（主体） + Finish mmt（余韵）
     ↑ 最小语义完整单位——截断任何一环都破坏"一次记忆"的完整性
```

- **digest 唯一触发点 = 本段 bond 剧情闭环**（`vn_exit completed → finish →
  _wrapup → engine.async_digest()`）——仅 `completed=True`; 中断剧情不消化
  （"中断的剧情不处理", 防记忆污染）。
- **resume 只注入不消化**（`_inject_brain(digest=False)`——0 次 LLM 调用）。
- **增量**: wiki 记 `digested_seq`（上次消化到的最大事件 seq）——无新增 →
  直接返回旧 wiki（0 次 LLM 调用）。
- **消化范围**（自动成立, 无需新机制）: 上次 digest 点在上一段闭环 → 本次输入 =
  上一段 Finish mmt + 本段 Trigger mmt + 本段 Bond story（段完整性优先）。

### 1.3 数据流

```
worlds/{world}/characters/{char}/events.jsonl（本世界线真源）
      │  bond 剧情闭环后（async_digest —— 唯一触发点）
      ▼
digest（主 LLM 一次调用; llm/prompts/digest.md + build_digest_schema）
      │  输入:
      │    ① render_timeline(新增事件, seq > digested_seq)   ← 增量, 不重读全量
      │    ② 视觉记忆（新增 l2d 事件的 gallery prompts）
      │    ③ 联想: recall_related(旧 wiki tags 匹配) + 双通道随机摘段（§5）
      │    ④ 人设锚点（personality + knowledge 概要）
      │    ⑤ 已有 summary（"只提炼新增/变化"）
      ▼
worlds/{world}/characters/{char}/wiki.json（本世界线 wiki; 含 digested_seq）
      │
      ▼
注入（recall）: wiki → 【角色记忆】段（第一人称）→ system prompt
      三个注入时机:
      ① MMT resume（重进进行中会话）: 只注入已有 wiki（不消化）
      ② Bond 开场: brain_segment 注入——VN 中角色记得本世界线前面的事
      ③ async_digest 后: 新 wiki 立即注入当前引擎实例（下次对话生效）
      新世界线（新周目）零注入
```

### 1.4 平行世界语义（与世界模型的衔接）

- **世界（周目）= 顶层对齐单元**: 世界里每角色一条连续线; 同框 = 同世界对齐
  （"阿露1生病/阿露2有空" = 世界1阿露/世界2阿露——世界隔离不交叉）。
- **wiki 归属**: per 世界线（该角色在当前世界的记忆）——不是 per 会话、更不是 per 角色。
- **虚边（关联事件）**: 角色间共享事件由"视角节点对 + event_id"虚边关联——**设计中 🔧**
  （阶段 12~15, 见 docs/archive/world_model_evolution.md）; 广播落库（共享事件各角色各落一份视角）
  是虚边的地基。当前代码尚未实现广播落库（同框客串未落地）。

---

## 2. 记忆三层架构

```
┌─────────────────────────────────────────────────────┐
│ ① 滑动窗口（短期记忆）  每轮全量喂窗口内历史（顺序保持——对话连贯）  │
│ ② 原文回捞（长期记忆）  窗口外重要片段按需回捞（"回忆注入"; 未来 embedding 🔧）│
│ ③ wiki/digest（提炼）   语义层——结论/性格/关系（压缩 + 角色一致）    │
└─────────────────────────────────────────────────────┘
```

- 动机: 传统滑动窗口"呆滞"——记忆分布是**重要性**驱动的, 不是时间均匀的
  （"我不记得刚刚说了什么, 但绝对记得之前讨论时间回溯的话语"）。
- 关键区别（vs Generative Agents）: 对话式（user/assistant 顺序逻辑流）——
  回忆注入必须保持对话顺序, 不照搬"乱序检索喂入"。

---

## 3. 业界查证（2026-08-27, 设计依据）

| 方案 | 来源 | 结论 |
|---|---|---|
| 评分驱逐式 | Generative Agents (Stanford 小镇) | 每条记忆 LLM 打重要性分, 检索按 recency×importance×relevance 加权取 top-K, 满时驱逐不重要的旧——"过筛的窗口" |
| 分层 + 按需调页 | MemGPT / Letta | main context（常驻窗口）+ external context（外部索引）; memory pressure 自省（驱逐/压缩/外部化）——与我们的三层同构 |
| 语义+时间驱逐 | 研究 | 驱逐同时考虑语义重要性与时间, 优于纯时间窗口 |
| 摘要即内容 | 业界主流（Generative Agents/Mem0/SillyTavern） | 检索后直接注入提炼条目, 不回溯原文——我们的 wiki 正是此模式 |
| 原文回捞 | 唯一做的是 MemGPT | **embedding 向量检索**定位, 不是 LLM/正则——我们的初代 snippet 索引方案因此废弃（Step 3） |

---

## 4. 增量 digest（digested_seq）✅

- wiki 增加 `digested_seq: int`（上次消化到的最大事件 seq; 0 = 未消化）。
- digest_session: 读 events（便宜, ms 级）→ `new_events = seq > digested_seq`
  （marker / affection 事件不计提炼内容, 只推进水位）。
- LLM 输出**新增条目** → 引擎合并进旧 wiki（同 content 去重, significance 取高）→
  更新 digested_seq → 原子落盘。
- 收益: 省 token（只处理新增）、**旧记忆稳定**（不重写, 只在旧基础上追加——
  同一世界线的时间推进, "搭积木"）; 重复恢复零重复成本。

---

## 5. 联想 digest + 双通道回忆（v3.1/v3.2）✅

**机制**: digest 不只消化新增, 还"想起"相关旧记忆, 一起交给 LLM 综合——
新剧情 + 旧记忆的联系 = 深层信念/成长弧线（"约会" + "儿时孤独" → "从孤独走向被爱"）。

**两步联想**:
```
A. 轻量召回（零依赖, 已实现）: recall_related——旧 wiki 条目 tags 命中新增剧情文本
   → 该旧记忆"被想起"（facts/beliefs content + relations 描述, 截断 3 条）
B. 回忆摘段（双通道）:
   每次 digest 的回忆摘段:
   ┌─ 珍贵通道（30% 概率, 可调）: 从 wiki 高 significance 条目选（≥0.8 或 top-3）
   │   → **永不衰减（保底）**——初遇/告白/约定都在这里（玩家最执着）
   └─ 日常通道（70%）: 对数正态加权摘历史事件原文（遗忘曲线）
       → 近期高峰 + 长尾（偶尔想起很久以前）——日常质感, 越复杂越像人类
C. RAG 回忆（Phase 2 🔧）: embedding 检索与新增语义相关的旧事件
   （本地 nomic embedding + numpy 余弦, 见 §10）
```

**参数（per 角色可配）**: `precious_ratio` 0.3 / `significance_threshold` 0.8 /
`sigma` 1.5 / `mu` 0——通过 `digest_session(recall_opts=...)` 透出。

### 5.1 组织 pass（修订契约, 🔧 规划 2026-09-02）

纯增量只能"碰撞出新"（联想 digest 已实现）; "糅杂/矛盾/归类"必须修订旧条目——
组织 pass 与消化合并为**同一次调用**（每段闭环一次, 不新增调用点）:

```
输入（三通道召回渲染, 见 §5）:
  【本次新经历】时间线
  【相关旧记忆（供组织决策）】子图渲染——带 #id + 邻接表（links）:
    #m3 [belief, sig 0.85, links: m7 m1] 遥香开始相信自己被需要
  约束: 不得强行升华; 与【角色人设锚点】冲突的修订一律不做

输出（修订契约, 引擎校验后原子执行）:
  {"revisions": [
    {"action": "create", "entry": {...}},
    {"action": "update", "id": "m_0003", "patch": {...}},
    {"action": "merge",  "ids": ["m_0001", "m_0007"], "into": {...}},
    {"action": "link",   "from": "m_0003", "to": "m_0010"},
    {"action": "contradict", "a": "m_0003", "b": "m_0009"}]}
```

**引擎侧护栏**（代码落点）:
- **id 校验**: LLM 引用的 #id 必须存在于本次渲染的子图内（契约层 ValidationResult 同款, 防幻觉 id）
- **原子执行**: revisions 全部通过才写盘; 写 evolution_log（diff 理由, 服务 R6 回滚）
- **token 预算**: 子图渲染上限（如 15 条）, 超出按 significance 截断——全 wiki 永远不进 prompt
- **epistemic 护栏**: 见 §7（update 不得把 inferred_belief 改成 canon_fact 等）

**角色视图 vs 组织视图**（同一张图两种渲染）:
- 组织视图（喂 digest/组织 LLM）: #id + 邻接表, 供修订决策
- 角色视图（喂主剧情 LLM, 现有 build_brain_injection）: 纯第一人称叙事, 无 id 无链接
- link 的价值不在"拍平顺序", 在**召回扩展**（三通道召回 + 沿 links 一跳）与**引用决策**（邻接表）

---

## 6. digest 输出契约（单源真值）

### 6.1 LLM 输出（`contract/schema.py: build_digest_schema` 渲染进 digest.md）

```json
{
  "summary": "一句话主线（str, 整体视角, 不是只写新增）",
  "facts":    [{"content": "…", "significance": 0.8, "tags": ["老师", "杂草"]}],
  "beliefs":  [{"content": "…", "significance": 0.9}],
  "relations":[{"subject": "遥香", "object": "老师", "relation": "信任加深", "note": "…"}],
  "affection_exp_delta": 10
}
```

- `facts`: 关键事实（significance 0~1; tags 可选 1~3 关键词供检索）
- `beliefs`: 抽象信念（significance 0~1）
- `relations`: 关系变化（subject/object/relation; note 可选）
- `affection_exp_delta`: 本段互动让角色对玩家好感增加的分（int 0~100; 无变化 → 0;
  **一个分不拆分来源**——上一段余韵 + 本段铺垫 + 剧情整体综合）
- 没有值得记的内容 → 对应字段输出空数组（合法）

### 6.2 内容清洗（consolidation._clean_output）

- significance clamp 0~1（旧字段 importance 读时兼容）; tags 过滤 + 截断（≤5）;
  空 content 丢弃; 全空且无好感变化 → 视为无效（防御: 落空模板）。
- **digest 规则要点**（digest.md）: 提炼而非记录（"老师蹲下陪她看杂草" →
  "遥香第一次觉得自己被需要"）; 记角色会记住的（影响行为的 + 值得珍视的共同经历;
  初遇必记 0.9+）; **人设锚点**约束（角色对话里说的话 ≠ 她的真实过去——提炼行为与
  动机, 不提炼成事实; 与锚点冲突 → 舍弃或按锚点改写）; 禁止强行升华（谐星就是
  谐星, "约好了哦"就是约定）; 矛盾保留; 表情（emotion 标注）是难忘细节的原料。

### 6.3 增量合并（consolidation._merge_new）

- facts/beliefs: content 精确去重, significance 取 max, tags union。
- relations: (subject, object, relation) 三元组去重, note 后者覆盖。
- 同一世界线的时间推进——旧积木不动, 往上加新块。

### 6.4 好感结算（affection 双轴正交）

- **affection（好感 delta）与 significance（记忆显著性）正交**: 悲伤剧情可
  significance 高 + affection 低; 平淡日常可 affection 微增 + significance 低。
- 幂等: 好感按 `interact_max`（本段互动 max seq）作幂等键——先写 affection 事件
  （真源, append-only）, 再更新 wiki 的 `affection` 缓存（exp/level）; 重复 digest
  同区间不重复加分。

---

## 7. wiki 结构（schema_version 2）✅

> 🔧 **2026-09-02 新增设计（未实现）**: 条目加 `epistemic`（认知类型）+ `observer`（观察者）
> —— 把"角色认为的"与"世界真相"从 prompt 规则（digest.md 规则 6/7）升级为**数据结构约束**。
> 对应世界模型"广播落库/信息差"（docs/archive/world_model_evolution.md 阶段 12）。

```jsonc
// data/worlds/{world_id}/characters/{char_id}/wiki.jsonl  ← 规划: jsonl 逐条（一行一条目）
// ⚠️ 下面这份是**v1 形状的历史示例**（`layer`/`segment_id`/`source` 都已换代或删除:
//    kind 取代 layer（2026-09-02）· segment_id/source 2026-09-21 删——见 nodes.py 台账）
{"id": "m_0001", "layer": "episode", "epistemic": "observed_fact", "observer": "igusa_haruka",
 "content": "老师在杂草屋说：地砖里长出的苔藓也可以是花",
 "significance": 0.9, "tags": ["老师", "杂草屋"],
 "event_seq": [42, 58], "ts": "2026-09-01T20:00:00",
 "links": []}
{"id": "m_0002", "layer": "belief", "epistemic": "inferred_belief",
 "content": "遥香第一次觉得自己在老师眼里很特别",
 "significance": 0.85, "tags": ["自我肯定"],
 "event_seq": [42, 58], "ts": "2026-09-01T20:00:00",
 "links": ["m_0001"]}
```

**epistemic 认知类型（规划语义）**:

| 类型 | 含义 | 注入渲染前缀（示例） |
|---|---|---|
| `canon_fact` | 世界真相（作者设定——仅出厂基座条目可用, 动态 digest 不得产出） | 只作锚点, 不渲染 |
| `observed_fact` | 角色亲眼/亲身经历 | "我记得……" |
| `reported_fact` | 听说的（带 `source`） | "我听说……" |
| `inferred_belief` | 角色自己推断的认知 | "我总觉得……" |
| ~~`speculation`~~ | **已退役 2026-09-21**（零生产者/零消费者/零真机数据） | — |

**护栏**（规划）:
- 动态 digest 只能产出 `observed_fact`（本线亲历）/ `reported_fact` / `inferred_belief`;
  `canon_fact` 只来自 R3 出厂基座（experience/knowledge 种子）
- 修订契约（§5.1 组织 pass）中 update 不允许把 `inferred_belief` 改写成 `canon_fact`——认知升级只能经 digest 重新提炼
- 出厂基座条目的 update 只允许"追加注记", 不允许改原文（平行世界共享出厂设定的保护）
  ⏸ **已退役 2026-09-21**：`source`/`is_seed()`/`notes` 整族删除——出厂记忆自 2026-09-05
  起不进 wiki（`render_background_experience` 直注 yml 原文），唯一生产者已归档，
  真机 0 个 seed 节点。若将来要"作者写死、运行时不可改"的记忆，纪律落在**配置层**。

**observer 观察者（规划）**: 广播落库时每条视角记忆标 `observer`（该线角色）;
多角色同框落地后（DESIGN_MULTI_CHAR）, 以 observer + 虚边（event_id）支撑信息差
（"谁在场谁知道"; 未在场角色只有 `reported_fact, source=转述者`）。

```jsonc
// data/worlds/{world_id}/characters/{char_id}/wiki.json
{
  "schema_version": 2,
  "conversation_id": "…",              // 兼容字段（世界线语义下不再参与路径）
  "digested_seq": 87,                  // 增量: 上次消化到的事件 seq
  "summary": "天台夜谈: 老师陪遥香看杂草, 遥香开始相信自己被需要",
  "facts":    [{"content": "老师说以后常来陪她看杂草", "significance": 0.8, "tags": ["老师", "杂草"]}],
  "beliefs":  [{"content": "遥香第一次觉得自己被需要", "significance": 0.9}],
  "relations":[{"subject": "遥香", "object": "老师", "relation": "信任加深", "note": "约定常来陪她"}],
  "affection": {"exp": 120, "level": 3},   // digest 好感缓存（真源 = affection 事件）
  "updated_at": "2026-08-24T15:30:00.000000"
}
```

- 条目 = 自然语言 content + 元数据（significance 排序 / tags 检索）= 结构化可检索。
- 缺失/坏 json → 空模板（宁缺勿错, 不阻断）。

---

## 8. 注入（recall: 第一人称 + 量控）✅

- **视角包装**: wiki 条目第三人称存储（digest 稳定）→ 注入时转第一人称——
  char_name 替换为"我"（"遥香第一次觉得被需要" → "我第一次觉得被需要"）,
  summary → "我记得那段日子：…"。依据: Perspective-Bounded Memory
  （arXiv 2606.25632）+ 自我参照效应。
- **注入量控**: significance 降序截断——facts 10 / beliefs 5 / relations 5; 空 wiki → ""。
- 渲染形态:
  ```
  【角色记忆（brain）】
  我记得那段日子：…
  我记得的事：- …
  我心里渐渐觉得：- …
  我和他们的关系：- 和老师：信任加深（约定常来陪她）
  ```

---

## 9. 升级路径（来自 DESIGN_MEMORY, 状态标注）

| Step | 内容 | 状态 |
|---|---|---|
| Step 1 | 滑动窗口参数化（`history_rounds`, MMT + bond 双引擎） | ✅ 已实现 |
| Step 2 | digest 契约加 significance 分（0~1, 旧名 importance 读时兼容） | ✅ 已实现（2026-08-27） |
| Step 3 | 索引检索（初代: LLM 输出 index + 引擎逐字匹配） | ⛔ 方案废弃（2026-08-28 裁决——业界主流 = 摘要即内容; 原文回捞须向量检索） |
| Step 4 | 回忆注入（"（你突然想起…窗口外的重要片段）"） | ⛔ 不可实现点（依赖 embedding + 需与 momotalk_rules 语义协调 + 真实性需原文约束） |
| Step 5 | 重要性感知驱逐（窗口满按 significance 驱逐） | 🔧 长期（驱逐不丢的前提 = embedding 原文可回捞） |

---

## 10. 路线图

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1（当前） | 增量 digest + 轻量召回 + 双通道随机摘段 + 注入 + 接线（世界模型 v2 存储） | ✅ |
| Phase 2 | RAG 回忆法: embedding 检索相关旧事件（本地 `text-embedding-nomic-embed-text-v1.5` + numpy 余弦, 无需向量库; 前置: `lms server start && lms load …`） | 🔧 |
| 远期 | 六文件动态增长（LLM 改 profile 等核心文件） | ⛔ 废案（平行世界共享出厂设置 + digest 锚点依赖静态人设, 无前车之鉴） |
| 远期 | Virtual Brain 完整（Semantic Graph / Self-Model / Sleep 五阶段） | 🔧 规划（CLAUDE.md §3.2; 当前实现 = digest 体系） |
| 远期 | 副本时间胶囊 / 配额 | ⛔ 不做 |

---

## 11. 边界

- **events.jsonl 唯一真源**: wiki 是派生视图（可删可重算, 原子写）。
- **digest 不阻断主流程**: 异步后台线程 + 同引擎串行锁; 失败静默降级（None）。
- **平行世界**: 世界槽位隔离; 无跨世界归并/迁移/角色级 wiki; 新世界从六文件
  （五件套 + script.yml 扮演手册）重新开始。
- **频率**: digest 唯一触发点 = bond 剧情闭环（仅完整剧情 completed=True;
  中断剧情不消化）; resume 只注入不消化; 增量保证重复恢复零重复成本。
- **最小单元**: 段（Trigger mmt + Bond story + Finish mmt）——finish mmt 无独立
  结束标记, 由"下一段 trigger"隐式界定; 玩家余韵聊很久未再触发 bond → 延迟消化
  （wiki 不更新, 事件流完整, resume 重建历史不受影响）。

---

## 12. 代码锚点

> ⚠️ **2026-09-21 除锈**：下表**前三行是 v1 记忆栈（`core/brain/{hippocampus,consolidation,recall}.py`，
> 已随 v1 退休删除）**，只作考古锚点；现网记忆主链 = **`core/brain/wiki_v2/`**
> （`digest.py` 提炼 · `recall*.py` 召回 · `channels.py` 五链路 · `compose.py` 合成 · `render.py` 注入视图），
> 见 `CLAUDE.md` §7。`core/momotalk.py` 两行已改指现网真家（行号不写——会漂）。

| 位置 | 说明 |
|---|---|
| ~~`core/brain/hippocampus.py`~~（v1, 已删） | WikiStore（worlds 路径读写, schema_version 2, 空模板兜底） |
| ~~`core/brain/consolidation.py`~~（v1, 已删） | digest_session（增量 + 联想 + 双通道回忆 + 好感幂等 + 清洗合并） |
| ~~`core/brain/recall.py`~~（v1, 已删） | build_brain_injection（第一人称 + 量控 10/5/5）+ recall_related（tags 轻量召回） |
| `core/brain/wiki_v2/`（现网） | digest / recall / channels / compose / render / store / revise（记忆主链） |
| `llm/prompts/digest.md` | digest 规则（价值取向/提炼/锚点/禁止升华/significance/好感标准） |
| `contract/schema.py:107` | build_digest_schema（输出契约单源真值） |
| `core/mmt/engine.py` | `_inject_brain`（resume 只注入 / digest=True 先消化再注入） |
| `core/mmt/engine.py` | `async_digest`（bond 闭环后台线程, 唯一触发点） |
| `core/session/store.py` | SessionStore v2（worlds 槽位 / 角色线 / snapshots 预留） |
| `core/session/renderer.py` | render_timeline（digest 输入叙事化） |
| `docs/DESIGN_SEGMENT.md` | 段模型（最小单元 / digest 边界 / affection×significance 正交） |
| `docs/DESIGN_WORLD.md` | 世界对齐（世界=顶层单元, 世界线挂靠） |
| `docs/archive/world_model_evolution.md`（已归档） | 模型演进史（阶段 0~15, 虚边/快照树/共通删除等设计） |
