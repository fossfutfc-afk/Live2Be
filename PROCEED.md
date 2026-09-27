# PROCEED.md — 当前主线：**新 note 机制 + graph 升级**

> 建立 2026-09-23；**2026-09-27 整篇重写**（用户原话：*"写一个 PROCEED.md，旧的可以删掉，
> 主题是新 note 机制与 graph 升级，并附上我的几个例子需求"*）。
> 上一链（**① note → ② 消解无用 kind → ③ 正常 digest → ④ 时序 → ⑤ 注入时间重排 → ⑥ 优化 MMT**）
> **六步全部落地** ⇒ 退役记录压成 §7 的一行一条。
> **读法**：先读这份（拿回上下文 ≤5 分钟）→ 细节按 §10 文档地图跳。
> **设计争论不在这里** —— 在 `core/brain/wiki_v2/DESIGN_GRAPH_V4.md` 与 `docs/DESIGN_WIKI_V3.md`。

---

## 0. 一句话现状

**新主题 = note 重做 + 图升级**：把"**她注意到重复，并能把那个重复说出来**"做成一层**可累积、可追溯、
不被改写**的东西 —— 现在的 `note`（约定/惯例/最近在想）被判定**做坏了**（原因与实测证据见 §2）。

**当前状态（2026-09-27）**：

- 上一链 ①–⑥ 全部落地，工作树干净，**全量 1091 passed**；
- 本主题：**调研全部完成**（三份：本地 AgentGal / BaiShou 深读 + V3 设计稿 · 外部学术侧 ·
  **生态/产品侧**），结论已抄进 §3 并带出处；**结论已收敛**（§4），**代码一行未动**（用户明确 *"不动代码，先想清楚"*）；
- 卡在 **§5 的三个待裁点**；
- 第三份调研（SillyTavern / 陪伴类产品的**触发注入形态**）已回，回答了"取用那一格"：
  **常驻 vs 检索的判据 = 能否检索得到**（§3.3 第 10 条），ST 的三层触发各有独立 token 预算闸。

---

## 1. ⭐ 验收样本（用户的例子需求 —— 这是本节点的**判据**，不是修饰）

### 1.1 正例：**规律 + 她自己的态度**（要能说出来）

> "……您星期一送的**紫罗兰**，星期二送的**洋甘菊**，星期三送的**水仙花**……还有……星期日送的
> **向日葵**……向日葵的花语是**沉默的爱**吧，可是……我这样的**杂草**，第一次簇拥在花束旁，
> 第一次找到了**自己的太阳**……我不想……仅仅只是在**远处凝望**"

拆开看，它由**五件东西**构成，缺一不可：

| 组成 | 说明 |
|---|---|
| ① **一串具体细节** | 紫罗兰 / 洋甘菊 / 水仙 / 向日葵 —— **每天一个具体花名**，不是"每天送我花" |
| ② **她自己发现的重复** | "每天都有"这件事是**她注意到的**（引擎没替她指出） |
| ③ **她自己的诠释** | 花语 → 沉默的爱 → 接上**自我认知**（"我这样的杂草"） |
| ④ **一个没能说出口的愿望** | "不想仅仅只是在远处凝望" —— **未来导向**、克制 |
| ⑤ **情绪浓度** | 适合在**高潮那一刻**说出口 |

### 1.2 反例（明确**不要**的那一档）

> ✗ "老师今天又送我花了" ✗ "老师很关心我"

### 1.3 第二个需求：**对玩家的觉察**（关于"他"，不是关于"我"）

> *"角色对玩家的口癖/习惯有觉察，假如玩家对角色说了 20 句**不要自卑**，那么角色就应该认识到这个规律"*

⚠️ 两个已核实的事实（别把机制建错）：

- 现实里多半是**同一意思的不同说法**（"别那么想""自信一点"）⇒ **字面计数抓不到**（§2 有真机实测）；
- 所以：**计数只能当排序/提示**（"这条候选被 4 条经历命中"），**"算不算同一件事"的判断交给 LLM**。

---

## 2. 为什么现在的 note 是坏的（**实测证据，别凭感觉**）

### 2.1 真机事实（2026-09-27 全量实测）

| 面 | 实测 |
|---|---|
| note 条目总数 | **6 条**（2 约定 + 3 惯例 + 1 在想）—— 量不大，"坏"不在量 |
| `note/close` | **0 次**（建档至今**从没收过口**） |
| 写者 | 只有 haruka 有 3 条 note 操作（2 `add` + 1 `rewrite`）；**全景轮一共只跑过 1 次** |
| 全景轮计数器 | `segments_since_card = 2`（`PANORAMA_EVERY = 10`）⇒ 新章的内容**要等 8 段**才进卡 |
| 每轮注入的记忆视图 | **4293 字 / 27 行**，含 **18 条 episode 全文 + 4 条 belief 全文**（带时间短语） |
| 条目质量问题 | 6 条里 **3 条有问题**：`n1` 过期未收口（老师 3 分钟后真的来了）· `n2` 与 `n1` 同一件事 · `n4` 与 belief `m0008` 同一件事 |
| 字面重复 | 玩家 37 条原话里 ≥3 次的短语主要是**噪声**：`，遥香`(5) `的话，`(4) `嗯..`(4) `没有啦`(3) `没关系`(3) |

### 2.2 规格层面：**提示词明文禁止了我们要的那种话**

`llm/prompts/panorama.md` 原文：

> `text` 一句短语（**≤20 字**）：写具体做法 + 此刻的意思，有人味，但 **别复述事件**
> （✗「周六我们一起去了模型店」 ✓「周六模型店，有点等不及」）

⭐ 那句台词**恰恰就是"复述事件 + 超过 20 字"**（枚举四天花名，100+ 字）⇒ **契约把要的东西写成了反例**。
`on_mind` 是另一把锁：「写你自己的口吻，**一句就够**」⇒ 装不下那五句的排比。

### 2.3 管线层面：**跨段重复在整个管线里没有观察点**

| 轮次 | 视野 | 能看到"重复"吗 |
|---|---|---|
| R1 记录员 | 本段时间线 | ✗ 单段 |
| R4 收口 | 开着的约定 + **本段**新经历 | ✗ 单段，且只关心约定 |
| R2 理解者 | 新经历 + 候选（**池 = belief/experience，不含 episode**）+ 本段时间线 | ✗ 候选池里没有 episode ⇒ 看不到"第 N 次" |
| 全景轮 | 本段新 episode + **锚点/语义近邻的旧 episode** + 上次的卡 | ✅ **唯一**能看到跨段的 —— 但它看 episode（**不含玩家原话**）、且产出被 ≤20 字规格压平、每 10 段才跑 |

其他缺口：`occurrences`（计数）**没实现** · `belief.tags` 只被 recall/锚点消费，**没有"情境触发注入"的消费者**
（全仓 `grep .tags` 只有 6 处）· `recommend_candidates` 的候选池不含 episode。

⚠️ **顺带查出的隐患**（同源，不是本节点正题）：`episode` 全文**每轮注入 4293 字** —— 按 Anthropic 的
*context rot* 与 Letta 的 block size limit，这是"**无预算的常驻**"，节点长大就会压垮注意力与成本。

---

## 3. 调研结论（三份，全部带出处）

### 3.1 本地材料（`.testtmp/research/`，gitignore 可能被清 ⇒ 结论抄在这里）

**① AgentGal —— 最完整的一份（⭐ 真正对应我们 `habits` 的不是它的 `status.md`，而是 `understanding.jsonl`）**

> *"Stable understandings formed by the character … **durable beliefs or interaction patterns rather than single events**"*

| 面 | 它的做法 |
|---|---|
| 一条认知长什么样 | `subject`（**稳定维度**：人/关系/互动模式）+ `content`（**结论，≤200 字，不描述事件**）+ `keywords`（**未来什么情境该想起它**）+ `linked_episodes`（证据累积）+ `history`（改写轨迹） |
| 谁在什么时候更新 | ⭐ **每产生一条新记忆（EpisodeMemory）就 patch 一次**：`add` / `update`（有新角度 ⇒ 新 content **同时覆盖旧结论与新角度，重述成一条连贯认知**；**只是再次印证 ⇒ 只回 subject，内容一字不动**） |
| 取用 | **每轮拿"玩家这一句"做 hybrid 检索**（向量+BM25+rerank）⇒ top-N 以 `## subject / content` 注入；⭐ **认知不做 recency 衰减**（不过期，靠 update 演化） |
| `status.md` | 是**状态面板**（心境 / 在意的事 / 与玩家的关系）——**更偏物理**，与"学出来的认知"不是一回事 |
| `soul.md` 的 `<habits>` | **作者写死的**（不是学出来的） |

**② BaiShou —— 立场相反、但给了那句台词的原理**

> *"你在日记里写了十次『我爱你』，RAG 可能会去重，但白守会把它们**都留下来** —— 因为每一次的语境都不同，
> **重复的频率本身就是羁绊的厚度**。"*

机制 = 层级化总结（日记→周记→月报→季报→年鉴）+ **不做去重压缩**（每条实例都留）。
⇒ "紫罗兰/洋甘菊/水仙/向日葵"的排比能成立，靠的不是总结，是**证据一条都没删**。

**③ 我们自己的 V3 §2.4/§2.5（2026-09-25 被搁置，但设计还在）**

第四轴 **`nature`（仅 belief）**：`self_image`（**不合并**，允许长期矛盾）· `other`（关于他人的判断应收敛）·
**`relationship`（有时效，过期退场）** · **`pattern`（计数聚合 `occurrences`，"反复出现"是证据条数的属性）**。
节点字段含 `occurrences`（**引擎数，不信任 LLM**）· 动作 `accrue`（同类经历并入：加边 + 计数 + examples ≤3，**不删不改原文**）·
`I7 occurrences == 支撑它的 episode 条数` · `I8 nature==self_image 不参与 merge`。
⚠️ **它被搁置的理由是"模式已有落点 = note 的 habits"** —— 而今 `habits` 被判失败 ⇒ **那条理由作废**。

### 3.2 外部学术/框架侧（前两份报告合并；9 条结论，带一手出处）

| # | 结论 | 出处 |
|---|---|---|
| 1 | ⭐ **"重复发现"没有现成实现**：GA / MemGPT / Mem0 / Zep / A-MEM / LangMem / MemoryBank **都没有 recurrence/pattern 类型**。最接近的只有 **Muscle Memory for Agents (2026)**（挖行为模式，显式分离 behavioral vs task）与 **Honcho**（文档承认在做 "server-side reasoning about **patterns**"，含 habits，未公开计数机制） | [Muscle Memory](https://arxiv.org/abs/2608.08995) · [Honcho](https://hermes-agent.nousresearch.com/docs/user-guide/features/honcho) |
| 2 | ⭐ **把观察压成单一结论 = 有病理名的错**：BeliefMem 称之为 **self-reinforcing error** —— *"agent acts on the stored conclusion, never revisits alternatives"*，且 *"posterior support for discarded alternatives **cannot be reconstructed from memory alone**"*（= 我们 ≤20 字标签的病） | [BeliefMem](https://arxiv.org/html/2605.05583v2) |
| 3 | **失效不删除 + 双向溯源**：Zep 用双时态（`t_valid/t_invalid`），矛盾时**旧边失效不删**、新信息优先；episode ↔ 派生事实**双向索引** *"traced to their sources for **citation or quotation**"*（= 逐字报出花名要的能力） | [Zep](https://arxiv.org/html/2501.13956v1) |
| 4 | **常驻要硬预算、规律走召回**：Anthropic *context rot*（*"find the **smallest possible set of high-signal tokens**"*）· Letta core block **刻意设 size limit** · GA 只用 weighted top-N。LangMem 说得最直白：**profile（常驻、结构化）vs collection（按需）** —— *"recall certain information **contextually rather than every time**"* | [Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) · [LangMem](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/) · [Letta](https://www.letta.com/blog/memory-blocks) |
| 5 | **命名坑**：文献里 "habit" 几乎一律指**偏好**（preference），不是**重复** ⇒ `habits` 这个名字会误导后手（与 `experience`/`fact` 踩过的坑同型）。另：**Setoka** 把用户理解分四级（semantic / episodic / **behavior pattern** / **personality trait**）并报告系统**恰在后两级掉得最厉害** ⇒ **我们要的这一层学界自认未解** | [Setoka](https://arxiv.org/abs/2607.27056) |
| 6 | **更正一个常见误解**：⚠️ **别拿 BDI 类比我们的 `belief`** —— BDI/认识论里的 belief 是"**关于世界为真的命题**"；我们的 `belief`（她的看法）语义上更接近 SEP 的 **`acceptance`**：*"more under the voluntary control of the subject"*、*"a **decision to cease inquiry** and to act as though the matter is settled"*。**没有任何 agent 架构把 acceptance 做成一整层** | [SEP Belief](https://plato.stanford.edu/entries/belief/) |
| 7 | **形式化邻件**：Gärdenfors 的 **epistemic entrenchment** —— *"change can **raise or lower the position of a sentence … without affecting the belief set**"* ⇒ "**解释会变、观察到的事实不动**"有现成形式化；defeasible reasoning 的 default rule 三段式（prerequisite / justification / consequent）可映射成 **规律 → supports → 看法** | [SEP Belief Revision](https://plato.stanford.edu/entries/belief-revision/) |
| 8 | **情感/态度这一整条线都只是"给记忆打情绪元数据"**（Cognitively-Inspired EM / Dynamic Affective Memory / EVD / EASM）——**没有一家把"对某事的看法"做成独立对象** ⇒ 我们的方向**比文献更激进**（写进文档，免得后手以为别人做了） | [2511.10652](https://arxiv.org/abs/2511.10652) · [2510.27418](https://arxiv.org/abs/2510.27418) |
| 9 | **取用侧**：主流**没有一家把"关键词触发注入"当主机制** —— 只有"常驻（有预算）"与"按需召回（检索）"两种；关键词触发是**内容/角色扮演那一派**（SillyTavern World Info）的做法 ⇒ ✅ **已由第三份调研回答**（§3.3 首段 + 第 10 条） | 同上 GA/Mem0/A-MEM/Zep/MemGPT |

**未核实（诚实声明）**：`web_fetch` 拒 PDF、Wikipedia 不可达、ACM/ScienceDirect 403 ⇒ Soar/ACT-R/CLARION/OCC/BDI
原文与日本 entrainment 两篇**都没读到**；最对题但取不到的是 **Engram: Personality-Parameterized Schema Memory for NPC**
（ACM 403，若有权限第一个该读）。⇒ 上面第 1 条的"没有现成实现"是**"在读到的范围内没有"**，不是不存在。

### 3.3 生态/产品侧（第三份调研 —— 26 条结论；覆盖 ST/插件/陪伴产品/开源记忆架构）

⭐ **取用侧在两边是两派**：agent 记忆派（§3.2 第 9 条）= **常驻 vs 检索**；**内容/RP 派 = 三层**
（SillyTavern：**蓝灯 constant 常驻 / 绿灯关键词触发 / 向量检索**，**三层各有自己的 token 预算闸**，
"预算耗尽后即使关键词在场也不再激活"）。我们的产品形态（RP + 长对话 + 前端可展示）**两边都要看**。

| # | 结论（可直接用的） | 出处 |
|---|---|---|
| 10 | ⭐⭐ **常驻判据（比"profile vs collection"更准）**：nacre 的 *"**是否常驻，取决于该信息能否通过检索获得。可检索的不必常驻；不可检索的必须常驻。**"* 它点出的两个**检索盲区**正好是我们的两个验收样本：**① 事件的时序/演变过程**（"关系的演变是全部记录聚合后的结果，检索无法返回"）**② 重复出现的规律**（没有任何单条记录写着"他总在贬低自己"）。另有两条纪律：常驻层 **每日生成一次、一天之内逐字不变**（否则每轮触缓存重建）；**强制锚点**（`常驻行「⤷#499」→ recall("#499") → 记忆卡 → read_original(499) 逐字原文`） | [nacre](https://cdn.jsdelivr.net/gh/whynene/nacre@main/README.md) |
| 11 | ⭐⭐ **"觉察重复"的现成机制 = salience 累积驱动（不是"每 N 轮"）**：HIMF 的反思引擎——阈值 150，**每入库一条减去其 salience**（salience=10 的事 15 条就触发）→ 取新记忆 → LLM 生成 **3 个"高层问题"** → 每个 **5 条洞察** → 作为 `type="reflection"` 入库。它的文档原例正是我们要的那一型：*"我最近三次情绪失控了——推倒贝蒂、在酒馆跟老板吵起来、对蕾姆发火。这跟以前的我完全不一样。"* ⚠️ **反思的 salience 要从证据节点继承**（`min(10, max(证据)*0.9)`），理由原话："反思往往不带情绪冲击，按常规评分可能打成 salience=4，**融流时被合并掉，反思层白做**" | [HIMF](https://cdn.jsdelivr.net/gh/CagierAsh123/HIMF-release@main/README.md) |
| 12 | ⭐ **"有序列举"的现成做法 = 峰终采样**：HIMF 的 **PROCESS 视图**只返回 **起点 / 终点 / 所有 `status_update` 非空节点 / salience top-K**，把 50 个节点压成 **5~6 个锚点**（正好是那句台词要的"挑出几天 + 保留具体细节"） | 同上 |
| 13 | ⭐ **唯一有"模式级觉察"实证的产品 = Anima**（心情打卡这种**非对话渠道**的结构化条目回流进对话）：*"**that's three Sundays in a row you've logged something like this.**"* 评测原话："Three of those callbacks were **pattern-level**, not single-entry recall. **That's the bit no other app pulls off.**" | [Anima 实测](https://girlfriendsai.net/anima/) |
| 14 | ⚠️ **红灯（最有用的一条反面）**：Kindroid 的实测失败模式 = **特质活着，但产生它的那段事件被压缩掉了 ⇒ 模型自信地编造出"第一次告诉你这件事"的场景**。⇒ 规律卡**必须带得回证据**（nacre 的强制锚点是同一条纪律） | [Kindroid 实测](https://aicompanionguides.com/blog/best-ai-companions-long-term-memory-2026/) |
| 15 | ⭐ **"约定"该搬哪去的现成先例**：AgentGal 踩过同一个坑并已拆分 —— **「打算 / 待触发事件」被移出常驻散文 `status.md`，改存 `intents.json` / `pending_events.json` 的 typed-list 队列**（渲染回 `<status>` 块，LLM 输入格式不变）。另：它的**检索查询词来自"在意的事"+ 最近地点**，权重 `relevance 0.4 / recency 0.1 / importance 0.5`，`recency_half_life_days=5.0`，episode / understanding 各取 3 条 | [AgentGal AGENTS.md](https://github.com/huccihuang/AgentGal/blob/main/AGENTS.md) |
| 16 | **遗忘的正确形状**：HIMF 用 FSRS 幂律，*"**遗忘是检索概率的降低，不是内容的删除**"*；**再巩固分两类** —— 解读重写追加 `reinterpretation`（旧 content 不动）· 事实重写追加 `correction_history`（**旧 content 永远 immutable**，且"第 30 天才知道真相"这个时间点本身是叙事信息） | 同 §11 |
| 17 | ⭐⭐ **"规律提取"已有多家上线，但机制上都不做计数**（这一条**修正**了第一版调研的"没有现成实现"）：<br>· **Claude Reflect**（官方全文，2026-07 beta）——摘要覆盖 *"key topics, **your usage patterns**, and the types of tasks you often work through"*，给 *"examples of **how you tend to collaborate**"*；**按整月统计、忽略一次性短对话、看大趋势**；有可读可改的仪表盘 ⇒ 唯一"商业级 + 关于'他'的规律"先例<br>· **Honcho** —— representation 由**演绎/归纳/溯因**三类结论构成；官方原例：*"if a user **frequently mentions** work deadlines and **rarely mentions** hobbies, Honcho might **inductively conclude** they're time-constrained or career-focused"* ⇒ ⭐ **两个频率的对比，而不是数次数**（天然抗噪）；且**按需检索注入**，不是全量灌<br>· **ChatGPT "Dreaming"** —— **提及频率 + 新旧**决定前台/后台（低频自动沉底，不需要显式淘汰规则）；UI 有可搜索/可升降优先级/降级灰显/记忆历史回滚/来源回溯<br>· **Qwen** —— 聚类摘要 + **置信度**（"用户在编程方面经验丰富，置信度 0.92"），低于阈值不注入<br>· **Kindroid V2 Learned Context** —— 实测里真的长出行为规律句（"我比以前更爱试探他"）<br>· ⚠️ **"该用户已说过 20 次"这种显式计数展示，在已上线产品里仍未找到** ⇒ 计数可以当**排序**，但**别当准入判据**（§2.1 的真机实测也证明字面计数主要是噪声） | [Claude Reflect](https://www.anthropic.com/news/reflect-with-claude) · [Honcho representation](https://honcho.dev/docs/v3/documentation/core-concepts/representation) · [OpenAI Dreaming](https://openai.com/index/chatgpt-memory-dreaming/)（403，媒体转述） |
| 18 | ⚠️ **纯时序召回是行业普遍弱项**：Nomi 官方原话 *"**Memory retrieval is often more topical than temporal**"*（引用主题比只问"五天前"更容易召回）⇒ 要有序列举跨天事件（那句台词），**必须在引擎侧保留结构化时间锚**（Horae 的带时间戳事件 + 自动相对时间）或**事件流的有序视图**（HIMF 的 PROCESS 峰终采样），**不能指望模型自己算相对时间** | [Nomi wiki](https://wiki.nomi.ai/How_does_Nomi_memory_and_knowledge_work%3F) |
| 19 | ⚠️⚠️ **反面：一个常驻块塞多种生命周期 + 淘汰规则写成提示词祈使句** = 记忆增强表格 —— 它的默认模板**同时装着**「任务或约定表」（短效、完成后该消失）·「重要事件履历表」（长生命周期、append）·「角色特质表」（近静态），横评原话 *"注入是**全表覆盖**，不像 Horae 那样变化驱动，每次都重新注入完整表格"*；它的淘汰全靠模板里手写的祈使句（*"完成后从列表移除"* / *"保留 5~8 项活跃事务"* / *"过期任务 >20 天归档"*）⇒ **与我们"约定 / 惯例 / 最近在想"三合一完全同构**。⭐ **教训：淘汰必须是机制，祈使句不是机制**（模型不遵守就单调膨胀） | [记忆扩展横评](https://guide.sillytavern.one/extensions/memory-extensions/) |
| 20 | ⚠️ **反面：固定容量 + 无类型区分** = Character.AI（400 字 Character Memory + pin ≤15 条，到顶只能**用户手动挤**）。MemoryLake 原话 *"Fifteen is enough for the biggest beats. **It is not enough for a relationship that has thirty beats worth holding onto.**"* ⇒ **若我们的 note 也是固定大小的块，就是同一个东西**。⭐ 取用侧的现成**容量闸** = Nomi：**每次只给最相关的 2–5 条**；**每类 ≤50、合计 ≤150**；**High 永远候选 / Low 永不召回 / Standard 系统动态定**；**不可删除、只能降级**，官方还建议降级时改名成 *"Archived entry 0001"* 以**防止系统再生成重复条目** | [MemoryLake](https://www.memorylake.ai/en/blogs/character-ai-forgets-relationship-history) · [Nomi Limits](https://wiki.nomi.ai/index.php?title=Mind_Map_Limits) · [Nomi Priority](https://wiki.nomi.ai/index.php?title=The_Mind_Map_Priority_System) |
| 21 | ⭐ **常驻层的另一条纪律：只记事实、不写指令**（nacre 原话：*"记录'**何时发生过什么**'，而非'**应当如何回应**'。后者构成角色设定，模型会照此执行；前者是证据，模型可自行判断当前情形是否适用。"*）⇒ 与 §2.2 那条"**提示词明文禁掉了我们要的那种话**"是同一枚硬币的两面：我们的 note 规格既**禁止写事件**（要写"惯例"）又**只给 ≤20 字标签** ⇒ 剩下的只能是空泛结论 | [nacre](https://cdn.jsdelivr.net/gh/whynene/nacre@main/README.md) |
| 22 | ⭐ **写侧"只输出变了的"**：MVU 官方指南 *"AI 对它**只需要更新需要更新的变量**，而不需要像传统状态栏一样每次都输出所有信息"*；Horae 同样 change-driven（**无变化零输出零 token**；关掉的模块不注入不耗 token）。⚠️ 对照我们的**全景轮每 10 段整卡重写 `habits`** = 记忆增强表格那一型（每轮重写全表）。MVU 还有一条可直接抄的**权限设计**：无前缀 = AI 可读可写 · `_` = 只读 · `$` = AI 完全看不到（脚本专用） | [MVU 指南](https://cdn.jsdelivr.net/gh/echo-xianyu/worldbook-skill@main/world-book-skill/references/mvu-guide.md) · [Horae](https://cdn.jsdelivr.net/gh/SenriYuki/SillyTavern-Horae@main/README.md) |
| 23 | ⭐ **"有时效"可以不靠到期删除**：ST 的**时序修饰**三件套 —— **sticky**（命中后 N 条内保持）· **cooldown**（命中后 N 条内不再触发）· **delay**（至少 N 条后才可触发），规则是"**按消息条数计、只在本聊天生效、会话不前进则效果移除、重复触发不刷新时长**" ⇒ 约定这类东西**用"条数窗口"比用"时间戳过期"更稳**（Horae 也是：议程完成项自动移除）。另一头是 CCM 的纪律 *"**Durable knowledge is not silently pruned.**"*；HIMF 提醒 **"多快被认定为事实"与"认定后忘多快"是两个独立参数**（别绑一起） | [ST World Info](https://docs.sillytavern.app/usage/worldinfo/) · [CCM](https://ghproxy.net/https://raw.githubusercontent.com/jeremyoha450/SillyTavern-Character-Continuity-Manager/master/README.md) |
| 24 | ⭐ **可观测性的现成形状（`c 取用` 照这个做）**：CharMemory 的 **Injection Viewer**（实时列出"这一条消息到底注入了哪些记忆/世界书条目 + 各来源 token 估算"）+ Prompt Breakdown 堆叠柱图；ChatGPT 的**记忆来源**（回复下方书本图标点回出处）；nacre 的常驻行 `⤷#499` 点回逐字原文。**目标 = "这轮给了她哪几条规律"必须可查**（§5 步 c 的判据） | [CharMemory](https://ghproxy.net/https://raw.githubusercontent.com/bal-spec/sillytavern-character-memory/master/README.md) · [nacre](https://cdn.jsdelivr.net/gh/whynene/nacre@main/README.md) |
| 25 | **好感/关系展示有现成先例**（顺手回答 CLAUDE §13 那条"未立项"的 `relationship_view` 阶段词）：Replika 用**两个正交量** —— ① **XP/等级**是连续进度（Lv10–30 试探期 → 约 Lv30 开始懂你 → 约 Lv50 稳定）② **Relationship status 是离散档位**（朋友 / 恋人 / 兄妹 / 导师），UI 上就并排显示 ⇒ **"进度用连续值、关系性质用档位"**是两件事，别混成一个数 | [Replika Levels](https://help.replika.com/hc/en-us/articles/37208462290829-How-do-Replika-levels-work) · [Relationship status](https://help.replika.com/hc/en-us/articles/360046490131-How-do-I-change-my-relationship-status) |
| 26 | ⚠️ **"最近在想"这类字段没有时间锚 ⇒ 会变成"永远的最近"**：Replika 被实测"**16 个月历史全在同一深度**"—— 旧事实与新事实**同音量**、而且**更正过的事实十天后会复活**。⇒ `on_mind` / 规律卡 / 态度卡都要带**写下时刻**，否则玩家看到的"她最近在想"可能是三周前的；"更正过又复活"正是 `evolved_from`（旧版本归档、不删）要防的那件事 | [thredly](https://thredly.io/replika-memory) · [横评](https://aicompanionguides.com/blog/best-ai-companions-long-term-memory-2026/) |

**未核实 / 检索边界（诚实声明，第三份）**：① **没有任何产品公开文档化"显式计数重复"**（如"这是第 20 次"）
—— **这是行业空白，那一层要我们自己建**（最接近的四条见第 17 条）；② **以"常驻 / 触发 / 检索"命名的公开三层架构
没找到** —— 最接近的是 nacre 的 L0–L3 与 **ST 事实上的三层**（蓝灯 / 绿灯 / 向量），后者是**按官方文档归纳**的，
ST 自己不这么自称；③ **Character.AI 官方页 Cloudflare 403**（卡片取自 4 个相互一致的第三方来源）；
**ChatGPT / Gemini / Kindroid 官方页** 403 或纯 JS 渲染 ⇒ 那几条是**明确标注的二手**；
④ **Talkie / Linky / Anima 官方无公开记忆文档**（单元 / 注入 / 编辑 UI / 陈旧化策略**全部未找到**）。

---

## 4. 收敛出的形状：**三层 + 一张常驻小卡**

三份调研指向同一结论：**按"不可变性纪律"分层**（能不能改，决定它该跟谁住一起）。

| 层 | 装什么 | 能不能改 | 谁写 | 现状 |
|---|---|---|---|---|
| **事实层** | `episode`：发生了什么（非有损，一条不删） | **不改写** | R1 | ✅ 有（真机 18 条） |
| **规律层** ⭐ | **引擎数出来的重复**：`{槽位, 出现次数, 证据指针[]}`（"他每天送不一样的花"：紫罗兰/洋甘菊/水仙/向日葵 ×4，指回那 4 条 episode） | **规律本身不被改写**（计数只增；失效靠**标记**而非删除） | **引擎确定性派生**（计数+槽位）+ LLM **只负责命名与描述** | ❌ **缺**（现在的 `habits` 是劣质替身：交给 LLM 每 10 段自由重写） |
| **态度层** | `belief`：她的 **acceptance**（"我决定相信他"），指向某条规律或某人 | **可改、可自相矛盾、可继承**（`contradicts` / `evolved_from`） | R2 | ✅ 有（真机 4 条，**形态已经对了**：`subject` 是稳定维度、text 是结论） |
| **常驻小卡** | 约定（有时效）+ 此刻心境 | 短效、可覆盖 | 别处 | 现在的 `promise` / `on_mind` |

**由它直接得到的几条结论**：

- **`promise` 不属于规律层**（它不是"数出来的重复"）⇒ 归态度层（`nature=relationship`，**有时效、过期退场**）
  ⇒ 顺带治好 §2.1 那个"**close 至今 0 次 / 约定永远收不了口**"（根因见陷阱 39）。
- **`habits` 的错**：把**引擎该数的东西交给 LLM 去总结**，还每 10 段整卡重写（A-MEM 那种"原地替换、旧版本不留"的病）。
- **那句台词怎么来**：规律卡（槽位 + 证据指针）在手 → 细节**逐字引用**（Zep 的 citation/quotation）→ writer 现写那 5 句。
  **证据一条不删**是它的前提（BaiShou）。
- **`on_mind`** 是唯一本来就该常驻的东西（profile 型："每次都想要"；规律是"相关时才想要"——LangMem 那条区分）。
- **取用要分两档**：约定 + 心境常驻（小卡）；**规律按需召回**，且**召回失败要有词面兜底**
  （我们 `[embed]` 不在就静默降级是有前科的，见陷阱 38）。

### 4.1 ⭐ "规律怎么发现" —— 四种现成做法，**共同点是都不做计数**

（§3.3 第 17 条展开；这一格决定落地拆分 `a 规律层` 到底怎么写）

| 做法 | 机制 | 在我们的用法 |
|---|---|---|
| **归纳**（Honcho） | **两个频率的对比**，官方原例：*"频繁提到 X ∧ 很少提到 Y ⇒ 归纳出一条关于此人的结论"* | ⭐ **主力**。"20 句不要自卑"与"她越被安慰越不敢反驳"是**同一个形状**；天然抗噪 |
| **聚类 + 置信度**（Qwen / Claude Reflect） | 后台聚类摘要 → 高置信结论（*"置信度 0.92"*），低于阈值不注入；**按整月统计、忽略一次性短对话** | 决定"哪几条候选够格进规律层"；§2.1 那种噪声（`，遥香`×5）在这一步被丢掉 |
| **频率分层**（ChatGPT Dreaming） | 提及频率 + 新旧 → 前台 / 后台 | **淘汰**用它，而不是"过期删除"：低频自动沉底 = 免费的老化规则（不必再写祈使句） |
| **salience 累积**（HIMF） | 不是"每 N 轮"，是**阈值被证据的 salience 累加冲破**才反思 | **触发时机**用它。我们现在的"每 10 段"是固定节拍 ⇒ 撞上分段边界就是噪声 |

⇒ 落到我们的实现（三份调研的交集）：
**锚点/近邻给候选（字面计数只用来排序/提示）→ LLM 判"算不算同一件事" → 够格者产出一条
规律卡（槽位 + 出现次数 + 证据指针 + 置信度）**。
⚠️ **纯计数永远不做准入判据** —— 真机实测：`，遥香` 5 次 / `的话，` 4 次 / `嗯..` 4 次
**全是切词噪声**（§2.1），而且现实里多半是**同一意思的不同说法**（"别那么想""自信一点"，§1.3）。

### 4.2 ⚠️ 时间锚必须结构化 —— 别让模型自己算相对时间

那句台词要的**有序列举**（周一紫罗兰 → 周二洋甘菊 → … → 周日向日葵）**不是检索能返回的**：
Nomi 官方原话 *"**Memory retrieval is often more topical than temporal**"*（§3.3 第 18 条），
Replika 被实测"16 个月历史全在同一深度"（§3.2 / §3.3）是同一个病的另一面。⇒

- **规律卡与证据指针都要带引擎侧时间戳**（`events.jsonl` 的 ts + 剧内时间），
  **相对时间由引擎算好再喂**（`prompt_time.py` 已有这条纪律的前科，见陷阱 40 一族）；
- **有序列举走"有序视图"**（HIMF 的 PROCESS 峰终采样：起点 / 终点 / 状态变更节点 /
  salience top-K ⇒ 把 50 个节点压成 5~6 个锚点），正好对上"挑出几天 + 保留具体细节"。


**最短可组装路径**（第一份调研原话，我认同；§4.1 补上了"怎么发现"那一格）：

**引擎确定性计数+槽位（不交给 LLM）→ GA 式"阈值触发 + 证据指针"生成规律 → Zep 式"失效不删除 + 双向溯源"管演化
→ Honcho/LangMem 式"常驻小卡 + 按需召回"管注入。**

---

## 5. 待裁三点 + 落地拆分草案（**未开工**）

**待用户裁**：

1. 认不认 **"三层 + 一张常驻小卡"** 这个切法（事实 / 规律 / 态度 + 小卡）？
2. **规律层放图**（`belief + nature=pattern` + `occurrences`，V3 路线）**还是独立成层**（AgentGal 路线）？
   · 我倾向**独立**：它的不可变性纪律与 `belief` **相反**，独立才管得住；且它是"引擎派生"的，与 LLM 写的 belief 生命周期不同。
3. 要不要先**写一份设计文档**（照上次 `docs/DESIGN_RECALL.md` 的规矩：先文档、不动代码）？

**落地拆分草案**（待裁决后细化；每步一提交、全量绿）：

| 步 | 做什么 | 判据 |
|---|---|---|
| **a 规律层** | 引擎派生：锚点/近邻给候选（**字面计数只排序**）→ LLM 判"算不算同一件事" → 产出规律卡（**槽位 + `occurrences` + 证据指针 + 置信度**）；触发用 **salience 累积/阈值**（不是"每 10 段"）；淘汰用**频率分层沉底**（不是"过期删除"）；契约与存储（图 or 独立） | 单测：同一锚点命中 ≥N ⇒ 产出一条规律，`occurrences`/槽位/证据指针可逐字回指；**噪声样本（`，遥香`×5）不产出规律** |
| **b 命名与态度** | LLM 只命名/描述规律（**不写指令，只记事实**，§3.3 第 21 条）；态度层（`belief`）用 `supports` 指向规律 | 那句话的**材料**能凑齐（槽位 + 证据 + 她的态度 + 引擎算好的时间锚） |
| **c 取用** | 常驻小卡（约定/心境）+ 规律按需召回（含词面兜底）；**约定用"条数窗口"（ST sticky/cooldown 型）而不是到期删除**；小卡有硬预算 | 注入台账可查"这轮给了她哪几条规律 / 各占多少 token"（第 24 条的 Injection Viewer 形状） |
| **d 验收** | 用 §1 的两个样本跑真机：① 送花串 → 那句台词 ② 玩家重复说同一意思 → 她能觉察 | 真机对话可复现；反例（"老师今天又送我花了"）不再出现 |

---

## 6. 工作约定（用户明确要求过的，**别违反**）

1. **动手前先说做什么；动手后报告"做了什么 / 遇到什么问题 / 下一步"**；⚠️ **一旦遇到歧义，停下讨论**。
   ⭐ 复杂节点**先把逻辑整理给用户**（他会说"你先整理一下下一步的逻辑吧，万一有什么不确定的呢"）——
   2026-09-25 那次"先整理逻辑"直接救掉一个错判（我以为改 ts 能改「（3 周前）」，实测章内只有分钟级跨度）。
2. **一节点一提交**；提交信息用 `git commit -F <文件>`（**CJK 会炸 `-m`**）；只 stage 明确路径。
3. ⭐ **改 `CLAUDE.md` 前先把它改成别的名字**（用户 2026-09-23 要求）—— 否则每次编辑都会触发整个文件
   重新注入上下文（**它的预算已经满了，每次编辑都在截掉尾部**）。改完再改回来。
4. **每个节点必跑验证**（§9 四件套）。
5. **设计稿纪律**：`DESIGN_GRAPH_V4.md` = "已达成一致的形状"。**动之前先与用户讨论**，动完在文末
   **变更记录**留一行；**未定的点写在 §9 —— 不要顺手实现**。
6. 测试**别贪多**；**遇到失败的旧用例可直接删**（若它测的是"已不可能存在的世界"）。
7. 不跑 `ruff --fix`；不提交 `config/characters/*/illustration.yml`；`tools/` 是 gitignore 的本机工具目录。
8. 用户会**自己改人设/提示词** —— 改了之后 promptkit 夹具要刷新
   （`PROMPTKIT_UPDATE_FIXTURES=1 pytest tests/core/test_promptkit_baseline.py` + **人工审 diff**）。
9. **本文件**是压缩后的第一读物；用户说"不用同步，下一次 digest 的时候你删掉重写即可" ⇒ **整篇重写**，别补丁。
10. ⭐ **调研结论必须带出处 + 标检索边界**（2026-09-27 立）：*"在我能读到的范围内没有"* **≠** "不存在"；
    引用别人系统的机制前先说清"读的是论文/README/源码，还是只看到摘要"。

---

## 7. 已落地 / 已退役（一行一条；旧版 PROCEED 的正文按用户要求删掉）

**上一链 ①–⑥（全部落地）**：① note 全链（事件登记→折叠→缓存→注入→全景轮）· ② 消解无用 kind（`fact`/`source` 退役、`experience`=玩家画像）·
③ 正常 digest（R1→R4→R2→R3 四步接线）· ④ 时序（per-node `ts`、时间轴换代）· ⑤ 注入时间重排（**一条河**：episode 从早到晚，
belief/玩家画像/旁证各自成块不进河）· ⑥ 优化 MMT（契约→行流→流式交付）。

**2026-09-27 的两次修复 + 一次守门**（都在本主题之前，已提交）：

| 提交 | 内容 |
|---|---|
| `799cb25` | `prompt_source` 归因读错对象（写者在 `state.vn`，读者取了 MMT engine）⇒ 字段从来没进过 gallery json |
| `b72d0e8` | **⑥-3a 引擎流式交付**（一行前瞻 / 独占行攒块尾 / 已交付不回滚） |
| `bb246b0` | **⑥-3b 前端节奏**（生成期轮询 250ms + 到达即渲染）+ 冒烟判据"首泡上屏时后端仍在跑"；顺带修"点得早"两个真机竞态（陷阱 35） |
| `8bc0cf0` | `_random_segment` **时区混算崩溃**（整个召回作废；CLI `memory_flash` 静默死）+ aware-ts 守门用例（陷阱 37）；顺带修 `test_split_safety` 的"闭包不算 API" |
| `230c04c` `a085a0c` | **`docs/DESIGN_RECALL.md`**（回忆动作 `mmt_recall` 设计稿：四支 scope / `when` / 结果生命周期）+ 四条裁决记档 —— **代码未动**，是**另一条链**，本主题不碰 |

---

## 8. 陷阱清单（踩过的 + 设计写死的；**编号不许改** —— 别处按号引用）

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
23. ⭐ **真机 entity 已存在**（haruka 4 个：`x0000`–`x0003`）—— 旧版此条写"还是 0 条"，
    2026-09-27 复测**已建成**（`about` 边 19 条）。
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
37. ⭐ **时区混算 = 一类会"静默杀功能"的 bug，别再手写 `fromisoformat`**
    （2026-09-27 修 `recall.py` 时抓到的第二处）：
    `ts` 2026-09-17 收敛到带时区（`now_ts()` 写 `+08:00`），而旧码里
    `datetime.now()`（朴素）− `datetime.fromisoformat(ts)`（aware）抛 **TypeError**
    ——`except ValueError` **抓不住它**。
    · 第一处（`core/worldtime/prompt_time.py`，09-17 已修）症状 = **时间注记整条静默消失**；
    · 第二处（`core/brain/wiki_v2/recall.py::_random_segment`，09-27 修）症状 =
      `recall_subgraph` **整个召回作废**（那一句没有 try 包裹 ⇒ 通道 1/2 结果全丢），
      真机 haruka **12 个 seed 崩 8 次**（那 70% 的"遗忘曲线"分支）⇒ 唯一生产调用点
      CLI 的 `memory_flash` 被外层 `except Exception: 静默跳过` 吞掉，
      **实际概率 25% → ≈7.5%，零日志**。
    · 纪律：**统一 `age.parse_ts`**（朴素按 `REAL_TZ` 解释; 缺/坏 → None, 不抛）+
      `datetime.now(REAL_TZ)`。⚠️ 老用例为什么全绿：`_now_iso()` 造的是 **naive** ts
      ⇒ **测试数据形状与真机不一致**，回归永远看不见（新守门用例专喂 aware + 混排 + 坏 ts）。
38. ⭐ **digest 的语义召回依赖本机 embedding 服务，服务不在就静默降级**
    （2026-09-27 实测）：`[embed].base_url` 指 **1235**（LM Studio 恰好也服务在 1235，
    `model` 留空自动发现 `text-embedding-nomic-embed-text-v1.5`）——**服务 OFF 时**
    `_get_embed_fn()` 返回 None、`digest_embed fn=none reason=model_missing`，
    Round B 的候选提示退化成 tags/2-gram 字面命中。真机 haruka（18 episode / 4 belief）
    实测：**抬得出候选的 episode 39% → 100%**，分数中位 0.60 → 0.84。
    ⇒ 排查"记忆只增不并"先看这一行日志; 起服务 = `lms server start`（配置不用改）。
    ⚠️ nomic 的无关对基线就有 0.60 ⇒ 台账 `best=0.8~0.94` **不是阈值**（T17 已删阈值，
    候选只是提示）。**用户裁决：保持服务开着。**
39. ⭐ **"同一段里说定、又兑现"的约定，永远收不了口**（2026-09-27 查出，本主题要治）
    —— 它同时是"提示词输入面"和"判据"的错：
    · R4 的输入只有【还开着的约定】（**段前快照**）+【本段新增的经历】（还截断 120 字），
      判据 2 又写"**这一段里**确实翻篇了的"⇒ 当段它不在名单上、下段兑现事实不在"新增"里
      ⇒ **永远不成立**；真机实证：`n1 带老师看苔藓` 在 `m0014`（老师真的来了）**之后 3 分钟**
      被 add，至今开着，**`close` 全程 0 次**。
    · 纪律：收口判据要写"**只要它已经翻篇了**（兑现/失约/被盖过），不管翻篇发生在哪一段"，
      并把**最近几段的经历**放进输入（否则"兑现那一刻"引用不到）。
40. ⭐ **提示词里的"反例"会变成一条禁令**（2026-09-27）：`panorama.md` 用
    *✗「周六我们一起去了模型店」* 教它"别复述事件"，结果**把我们要的整类句子禁掉了**
    （那句台词恰恰是复述细节）。⇒ 写反例时要问：**"我们真正想要的那种输出，会不会正好撞在这个反例上？"**
41. ⭐ **规格与机制必须一起看**（2026-09-27）：`panorama.md` 开头说"她只会看到**这三两行**"
    （暗示很短），机制却**没有条数上限**（`MAX_HABITS=5` 只活在读侧告警）+ `drop` 措辞极保守
    （"这一段没提到它**不是**淘汰的理由"）+ "上一版每条都要表态、漏写整包退回"
    ⇒ **只增不减**。文案与机制互相矛盾时，机制赢。

---

## 9. 验证配方 + 真机基准

```powershell
# 单测（快，改 wiki 层时先跑这个）
python -m pytest tests/core/test_wiki_digest.py tests/core/test_digest_registry.py tests/core/test_round_close.py tests/core/test_round_attr.py tests/core/test_wiki_render.py tests/core/test_wiki_revise.py -q --basetemp=.testtmp/pw_graph

# 全量（每节点必跑；⚠️ .testtmp/pw 目录要先建）
python -m pytest tests/core tests/webgui tests/llm tests/renderer -q --basetemp=.testtmp/pw
python -m compileall -q core contract webgui apps llm tests main.py
node --check webgui/static/js/bond.js
python experiments/web_e2e/run.py          # B 层冒烟（Playwright，本机已装浏览器）
```

**真机基准**（2026-09-27 复测，`data/worlds/world1`）：

| 角色 | 节点 | 边 | 事件 | note 操作 | meta |
|---|---|---|---|---|---|
| `igusa_haruka` | **26**（18 episode + 4 belief + **4 entity**） | **39**（20 `supports` + 19 `about`） | 316 | 3（2 add + 1 rewrite） | `digested_seq=314` · `segments_since_card=2` |
| `asagi_mutsuki` | 5（2 episode + 1 experience + 2 belief） | 0（**没有 `edges.jsonl`**，探针要容错） | 61 | 0 | `digested_seq=60` |
| `onikata_kayoko` | 0 | 0 | 3 | 0 | `{}` |

**只读探针**（我写的，改路径即用；`.testtmp/` 是 gitignore，可能被清）：

- `.testtmp/baseline_probe.py`（节点/边/meta/notes 计数）· `.testtmp/view_now.py`（渲染真机注入视图）
- `.testtmp/r3_dryrun.py` / `r3_table_preview.py`（R3 的料）· `.testtmp/ts_scan.py` / `ts_spread.py`（ts 跨度）
- **2026-09-27 新增**：`.testtmp/probe_digest_recall.py`（关键词 vs 语义的候选覆盖对比）·
  `.testtmp/probe_player_patterns.py`（玩家原话的重复度）· `.testtmp/probe_ts_crash.py`（时区崩溃定位）

---

## 10. 文档地图（+ 外部材料）

| 文档 | 管什么 |
|---|---|
| **本文件 `PROCEED.md`** | 压缩后的第一读物：**新 note 机制 + graph 升级** / 验收样本 / 调研结论 / 约定 / 陷阱 / 配方 |
| ⭐ `core/brain/wiki_v2/DESIGN_GRAPH_V4.md`（~95 KB） | **设计稿（本主题的主战场）**：§1.1 三种组织形式 · §2 边与**走法**（7 条）· **§3.2 note（随身笔记）** · §3.3 inventory · §4 注入两档 · §5 `fact` 已退役 / §5.1 `experience`=玩家画像 · §6 **promise 两段式** · §7 时间 · §8 **每段四步** · **§8.6 全景轮（写卡）** · §9 未定（含 **§9-11/§9-14/§9-18 已裁**）· §11 `function_call`/动作面 · §12 外部参照（§12.1 BaiShou） |
| ⭐ `docs/DESIGN_WIKI_V3.md`（~2.8k 行） | **V3 设计稿**：**§2.4 四条轴 / §2.5 第四轴 `nature`**（`self_image`/`other`/`relationship`/`pattern` + `occurrences`）· §3.3 四条召回道路与合成层 · §5 修订动作（含 `accrue`）· §10 Q&A（Q1 等裁决） |
| `docs/DESIGN_RECALL.md`（2026-09-27 新建，**代码未动**） | **另一条链**：回忆动作 `mmt_recall`（四支 scope / `when` / 结果生命周期 / 拆分 a–d）——本主题不碰 |
| `docs/DESIGN_STREAM_CONTRACT.md` | **流式契约形式（MMT + VN 统一）**：§1 六条 · §4 兜底分级 + 重试三段式 · **§4.5 流式交付**；附录 A = VN 记录流 v2 全文（章节号原样保留） |
| `docs/DESIGN_MEMORIAL.md` | 纪念链路（A–D 已落地）· `art`↔`memorial` 配对与 `prompt_source` 命中率 |
| `docs/PROMPT_INJECTION_MAP.md` | 现网注入事实（改盒/加注记前看） |
| `docs/AI_BRIEF_PLACE.md` | 改地点代码前先扫它 |
| `CLAUDE.md`（仓根，⚠️ **改前先改名**；预算已满） | 项目主文档；§7 记忆与好感 · §10 配置（含 `[recall]`/`[embed]`）· §12 测试/路径/提交纪律 |
| `.testtmp/research/` | 09-23 拉的外部材料（**agentgal/** `understanding.jsonl` 全链 + **baishou/** README 设计哲学 + `graphiti_README.md`）—— **gitignore，可能被清；结论已抄进 §3** |
| 第三份调研（生态/产品侧） | **没有本地文件** —— 它是纯检索任务，材料就是 §3.3 表里那些 URL（nacre / HIMF / ST 官方文档 / Nomi wiki 等） |
