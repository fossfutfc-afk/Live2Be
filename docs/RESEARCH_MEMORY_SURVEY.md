# RESEARCH_MEMORY_SURVEY.md — 记忆/规律/注入形态的调研结论（三份，全部带出处）

> 从 `PROCEED.md` §3 搬出（2026-09-27，用户要求 PROCEED 只做"接续用"、不堆内容）。
> 三份调研 = ① 本地深读（AgentGal / BaiShou / 我们自己的 V3）② 外部学术/框架侧 ③ 生态/产品侧。
> ⚠️ 每节末尾的"未核实 / 检索边界"是**诚实声明**，引用时别丢。

---

### 3.1 本地材料（`.testtmp/research/`，gitignore 可能被清 ⇒ 结论抄在这里）

**① AgentGal —— 最完整的一份（⭐ 真正对应我们 `habits` 的不是它的 `status.md`，而是 `understanding.jsonl`）**

> *"Stable understandings formed by the character … **durable beliefs or interaction patterns rather than single events**"*

| 面 | 它的做法 |
|---|---|
| 一条认知长什么样 | `subject`（**稳定维度**：人/关系/互动模式）+ `content`（**结论，≤200 字，不描述事件**）+ `keywords`（**未来什么情境该想起它**）+ `linked_episodes`（证据累积）+ `history`（改写轨迹） |
| 谁在什么时候更新 | ⭐ **每产生一条新记忆（EpisodeMemory）就 patch 一次**：`add` / `update`（有新角度 ⇒ 新 content **同时覆盖旧结论与新角度**；**只是再次印证 ⇒ 只回 subject，内容一字不动**） |
| 取用 | **每轮拿"玩家这一句"做 hybrid 检索** ⇒ top-N 以 `## subject / content` 注入；⭐ **认知不做 recency 衰减**（不过期，靠 update 演化） |
| `status.md` | 是**状态面板**（心境 / 在意的事 / 与玩家的关系）——**更偏物理** |
| `soul.md` 的 `<habits>` | **作者写死的**（不是学出来的） |

**② BaiShou —— 立场相反、但给了那句台词的原理**

> *"你在日记里写了十次『我爱你』，RAG 可能会去重，但白守会把它们**都留下来** —— 因为每一次的语境都不同，
> **重复的频率本身就是羁绊的厚度**。"*

⇒ "紫罗兰/洋甘菊/水仙/向日葵"的排比能成立，靠的不是总结，是**证据一条都没删**。

**③ 我们自己的 V3 §2.4/§2.5（2026-09-25 被搁置，但设计还在）**

第四轴 **`nature`（仅 belief）**：`self_image`（**不合并**）· `other`（应收敛）· **`relationship`（有时效，过期退场）** ·
**`pattern`（计数聚合 `occurrences`，"反复出现"是证据条数的属性）**。节点字段含 `occurrences` · 动作 `accrue` ·
`I7 occurrences == 支撑它的 episode 条数` · `I8 nature==self_image 不参与 merge`。
⚠️ **它被搁置的理由是"模式已有落点 = note 的 habits"** —— 而今 `habits` 被判失败 ⇒ **那条理由作废**。

### 3.2 外部学术/框架侧（9 条结论，带一手出处）

| # | 结论 | 出处 |
|---|---|---|
| 1 | ⭐ **"重复发现"没有现成实现**：GA / MemGPT / Mem0 / Zep / A-MEM / LangMem / MemoryBank **都没有 recurrence/pattern 类型**。最接近的只有 **Muscle Memory for Agents (2026)** 与 **Honcho** | [Muscle Memory](https://arxiv.org/abs/2608.08995) · [Honcho](https://hermes-agent.nousresearch.com/docs/user-guide/features/honcho) |
| 2 | ⭐ **把观察压成单一结论 = 有病理名的错**：BeliefMem 称之为 **self-reinforcing error** —— *"agent acts on the stored conclusion, **never revisits alternatives**"*，且 *"posterior support for discarded alternatives **cannot be reconstructed from memory alone**"* ⇒ ⭐ 我们的 `update`（输入=旧结论）**就是它的教科书实现** | [BeliefMem](https://arxiv.org/html/2605.05583v2) |
| 3 | **失效不删除 + 双向溯源**：Zep 双时态（`t_valid/t_invalid`），矛盾时**旧边失效不删**；episode ↔ 派生事实**双向索引** *"traced to their sources for **citation or quotation**"* | [Zep](https://arxiv.org/html/2501.13956v1) |
| 4 | **常驻要硬预算、规律走召回**：Anthropic *context rot*（*"find the **smallest possible set of high-signal tokens**"*）· Letta core block **刻意设 size limit** · GA 只用 weighted top-N。LangMem：**profile（常驻、结构化）vs collection（按需）** | [Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) · [LangMem](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/) · [Letta](https://www.letta.com/blog/memory-blocks) |
| 5 | **命名坑**：文献里 "habit" 几乎一律指**偏好** ⇒ `habits` 这个名字会误导后手。另：**Setoka** 把用户理解分四级（semantic / episodic / **behavior pattern** / **personality trait**）并报告系统**恰在后两级掉得最厉害** ⇒ **我们要的这一层学界自认未解** | [Setoka](https://arxiv.org/abs/2607.27056) |
| 6 | **更正一个常见误解**：⚠️ **别拿 BDI 类比我们的 `belief`** —— 我们的语义更接近 SEP 的 **`acceptance`**：*"more under the voluntary control of the subject"*、*"a **decision to cease inquiry**"*。**没有任何 agent 架构把 acceptance 做成一整层** | [SEP Belief](https://plato.stanford.edu/entries/belief/) |
| 7 | **形式化邻件**：Gärdenfors 的 **epistemic entrenchment** —— *"change can **raise or lower the position of a sentence … without affecting the belief set**"* ⇒ "解释会变、观察到的事实不动"有现成形式化 | [SEP Belief Revision](https://plato.stanford.edu/entries/belief-revision/) |
| 8 | **情感/态度这一整条线都只是"给记忆打情绪元数据"** —— **没有一家把"对某事的看法"做成独立对象** ⇒ 我们的方向**比文献更激进** | [2511.10652](https://arxiv.org/abs/2511.10652) · [2510.27418](https://arxiv.org/abs/2510.27418) |
| 9 | **取用侧**：主流**没有一家把"关键词触发注入"当主机制** —— 只有"常驻（有预算）"与"按需召回（检索）" ⇒ ✅ **已由第三份调研回答**（§3.3 首段 + 第 10 条） | 同上 GA/Mem0/A-MEM/Zep/MemGPT |

**未核实（诚实声明）**：`web_fetch` 拒 PDF、Wikipedia 不可达、ACM/ScienceDirect 403 ⇒ Soar/ACT-R/CLARION/OCC/BDI
原文与日本 entrainment 两篇**都没读到**；最对题但取不到的是 **Engram: Personality-Parameterized Schema Memory for NPC**
（ACM 403）。⇒ 第 1 条的"没有现成实现"是**"在读到的范围内没有"**，不是不存在。

### 3.3 生态/产品侧（26 条结论；覆盖 ST/插件/陪伴产品/开源记忆架构）

⭐ **取用侧在两边是两派**：agent 记忆派 = **常驻 vs 检索**；**内容/RP 派 = 三层**
（SillyTavern：**蓝灯 constant 常驻 / 绿灯关键词触发 / 向量检索**，**三层各有自己的 token 预算闸**，
"预算耗尽后即使关键词在场也不再激活"）。

| # | 结论（可直接用的） | 出处 |
|---|---|---|
| 10 | ⭐⭐ **常驻判据**：nacre 的 *"**是否常驻，取决于该信息能否通过检索获得。可检索的不必常驻；不可检索的必须常驻。**"* 两个**检索盲区**正好是我们的两个验收样本：**① 事件的时序/演变过程 ② 重复出现的规律**。另有两条纪律：常驻层 **每日生成一次、一天之内逐字不变**；**强制锚点**（`⤷#499 → recall → 记忆卡 → read_original`） | [nacre](https://cdn.jsdelivr.net/gh/whynene/nacre@main/README.md) |
| 11 | ⭐⭐ **"觉察重复"的现成机制 = salience 累积驱动（不是"每 N 轮"）**：HIMF 反思引擎——阈值 150，**每入库一条减去其 salience**（salience=10 的事 15 条就触发）→ LLM 生成 3 个"高层问题"→ 每个 5 条洞察 → `type="reflection"` 入库。文档原例正是我们要的那一型：*"我最近三次情绪失控了…**这跟以前的我完全不一样**"* ⚠️ **反思的 salience 要从证据节点继承**（`min(10, max(证据)*0.9)`），否则"融流时被合并掉，反思层白做" | [HIMF](https://cdn.jsdelivr.net/gh/CagierAsh123/HIMF-release@main/README.md) |
| 12 | ⭐ **"有序列举"的现成做法 = 峰终采样**：HIMF 的 **PROCESS 视图**只返回 **起点 / 终点 / 所有 `status_update` 非空节点 / salience top-K**，把 50 个节点压成 **5~6 个锚点** | 同上 |
| 13 | ⭐ **唯一有"模式级觉察"实证的产品 = Anima**（心情打卡回流进对话）：*"**that's three Sundays in a row you've logged something like this.**"* 评测原话："**That's the bit no other app pulls off.**" | [Anima 实测](https://girlfriendsai.net/anima/) |
| 14 | ⚠️ **红灯**：Kindroid 的失败模式 = **特质活着，但产生它的那段事件被压缩掉了 ⇒ 模型自信地编造出"第一次告诉你这件事"的场景**。⇒ 规律卡**必须带得回证据** | [Kindroid 实测](https://aicompanionguides.com/blog/best-ai-companions-long-term-memory-2026/) |
| 15 | ⭐ **"约定"该搬哪去的现成先例**：AgentGal 已拆分 —— **「打算 / 待触发事件」移出常驻散文 `status.md`，改存 `intents.json` / `pending_events.json` 的 typed-list 队列** | [AgentGal AGENTS.md](https://github.com/huccihuang/AgentGal/blob/main/AGENTS.md) |
| 16 | **遗忘的正确形状**：HIMF 用 FSRS 幂律，*"**遗忘是检索概率的降低，不是内容的删除**"*；**再巩固分两类** —— 解读重写追加 `reinterpretation`（旧 content 不动）· 事实重写追加 `correction_history` | 同 §11 |
| 17 | ⭐⭐ **"规律提取"已有多家上线，但机制上都不做计数**：<br>· **Claude Reflect**（官方全文，2026-07 beta）——摘要覆盖 *"**your usage patterns**"*、给 *"examples of **how you tend to collaborate**"*；**按整月统计、忽略一次性短对话**<br>· **Honcho** —— *"if a user **frequently mentions** work deadlines and **rarely mentions** hobbies, Honcho might **inductively conclude**…"* ⇒ ⭐ **两个频率的对比，而不是数次数**；且**按需检索注入**<br>· **ChatGPT "Dreaming"** —— **提及频率 + 新旧**决定前台/后台<br>· **Qwen** —— 聚类摘要 + **置信度**<br>· ⚠️ **"该用户已说过 20 次"这种显式计数展示，在已上线产品里仍未找到** ⇒ 计数当**排序**，别当准入判据 | [Claude Reflect](https://www.anthropic.com/news/reflect-with-claude) · [Honcho](https://honcho.dev/docs/v3/documentation/core-concepts/representation) · [OpenAI Dreaming](https://openai.com/index/chatgpt-memory-dreaming/)（403，媒体转述） |
| 18 | ⚠️ **纯时序召回是行业普遍弱项**：Nomi 官方 *"**Memory retrieval is often more topical than temporal**"* ⇒ 要有序列举跨天事件，**必须在引擎侧保留结构化时间锚**，**不能指望模型自己算相对时间** | [Nomi wiki](https://wiki.nomi.ai/How_does_Nomi_memory_and_knowledge_work%3F) |
| 19 | ⚠️⚠️ **反面：一个常驻块塞多种生命周期 + 淘汰规则写成提示词祈使句** = 记忆增强表格 —— 默认模板**同时装着**「任务或约定表」（短效）·「重要事件履历表」（append）·「角色特质表」（近静态），且*"注入是**全表覆盖**"*；淘汰全靠模板里手写的祈使句 ⇒ **与我们"约定 / 惯例 / 最近在想"三合一完全同构**。⭐ **教训：淘汰必须是机制，祈使句不是机制** | [记忆扩展横评](https://guide.sillytavern.one/extensions/memory-extensions/) |
| 20 | ⚠️ **反面：固定容量 + 无类型区分** = Character.AI（400 字 + pin ≤15，到顶只能用户手动挤）。⭐ 取用侧的**容量闸** = Nomi：**每次只给最相关的 2–5 条**；**每类 ≤50、合计 ≤150**；**High 永远候选 / Low 永不召回**；**不可删除、只能降级** | [MemoryLake](https://www.memorylake.ai/en/blogs/character-ai-forgets-relationship-history) · [Nomi Limits](https://wiki.nomi.ai/index.php?title=Mind_Map_Limits) |
| 21 | ⭐ **常驻层的另一条纪律：只记事实、不写指令**（nacre 原话：*"记录'**何时发生过什么**'，而非'**应当如何回应**'。后者构成角色设定，模型会照此执行；前者是证据。"*）⇒ 与 §2.2 是同一枚硬币的两面 | [nacre](https://cdn.jsdelivr.net/gh/whynene/nacre@main/README.md) |
| 22 | ⭐ **写侧"只输出变了的"**：MVU 官方 *"AI 对它**只需要更新需要更新的变量**"*；Horae 同样 change-driven。⚠️ 对照我们的**全景轮每 10 段整卡重写** = 记忆增强表格那一型 | [MVU 指南](https://cdn.jsdelivr.net/gh/echo-xianyu/worldbook-skill@main/world-book-skill/references/mvu-guide.md) · [Horae](https://cdn.jsdelivr.net/gh/SenriYuki/SillyTavern-Horae@main/README.md) |
| 23 | ⭐ **"有时效"可以不靠到期删除**：ST 的 **sticky / cooldown / delay** 三件套，*"按消息条数计、只在本聊天生效、**会话不前进则效果移除**"* ⇒ 约定用"条数窗口"比"时间戳过期"更稳。另一头是 CCM 的 *"**Durable knowledge is not silently pruned.**"* | [ST World Info](https://docs.sillytavern.app/usage/worldinfo/) · [CCM](https://ghproxy.net/https://raw.githubusercontent.com/jeremyoha450/SillyTavern-Character-Continuity-Manager/master/README.md) |
| 24 | ⭐ **可观测性的现成形状**：CharMemory 的 **Injection Viewer**（实时列出这一条消息注入了哪些记忆 + 各来源 token 估算）· ChatGPT 的**记忆来源**图标 · nacre 的常驻行 `⤷#499` | [CharMemory](https://ghproxy.net/https://raw.githubusercontent.com/bal-spec/sillytavern-character-memory/master/README.md) |
| 25 | **好感/关系展示有现成先例**（顺手回答 CLAUDE §13 那条"未立项"的 `relationship_view`）：Replika 用**两个正交量** —— **XP/等级**（连续进度）② **Relationship status 离散档位** ⇒ **"进度用连续值、关系性质用档位"** | [Replika Levels](https://help.replika.com/hc/en-us/articles/37208462290829-How-do-Replika-levels-work) |
| 26 | ⚠️ **"最近在想"没有时间锚 ⇒ 会变成"永远的最近"**：Replika 被实测"**16 个月历史全在同一深度**"，且**更正过的事实十天后会复活**。⇒ `on_mind` / 规律卡 / 态度卡都要带**写下时刻** | [thredly](https://thredly.io/replika-memory) |
| 27 | ⭐⭐ **"不做 tool call 怎么注入 graph"——收集到的七条路**（用户 2026-09-27 问）：<br>**A 常驻**（预算内全量）：ST 蓝灯 constant · MVU 变量表 · nacre L0–L3 · Horae<br>**B 关键词触发**（引擎扫最近 N 条）：ST 绿灯 · Character.AI Lorebook<br>**C 向量检索**（引擎自动，模型不参与）：ST Data Bank · CharMemory · AgentGal · TencentDB<br>**D 图扩散 / 邻居展开**：⭐ **GraphRAG local search** · ST-BME<br>**E 预计算摘要**（离线算好再检索）：⭐⭐ **GraphRAG global search（社区摘要）** · TencentDB L3 Persona<br>**F 文本标记拦截**（"穷人版 tool call"）：⭐ **paw-memory 的 `[recall]`**（模型在回复开头输出标记 → 引擎拦截执行）<br>**G 递归 / 链式激活**：⭐ **ST World Info 的 recursive scan**（条目 content 命中他条 keys ⇒ 链式激活，`Max Recursion Steps` 限深） | ST 官方文档 · [GraphRAG](https://github.com/nitin27may/ai-resources/blob/main/docs/rag/graphrag.md) |
| 28 | ⭐⭐ **GraphRAG 的两种查询模式 = "图怎么进 prompt"的两个标准答案**：**local search** = 实体向量命中 → **沿图走邻居** → 带上实体 + 关系 + 源 chunk；**global search** = **完全不做局部遍历**，而是 **map-reduce 跑预先算好的"社区摘要"**（社区由 Leiden 算法切、**每个社区一份 LLM 摘要**）。⇒ ⭐ **"群 + 摘要"不是我们发明的，是 GraphRAG 的 global 模式**；我们的 `index`（指向群的指针）与 L2 的 belief 正好对应它 | [GraphRAG 文档](https://github.com/nitin27may/ai-resources/blob/main/docs/rag/graphrag.md) · [论文 arXiv 2404.16130](https://arxiv.org/abs/2404.16130) |
| 29 | ⭐⭐⭐ **TencentDB Agent Memory —— 与我们的设计同构度最高的一家**（[仓库](https://github.com/TencentCloud/TencentDB-Agent-Memory)）：<br>· **分层** `L0 Conversation → L1 Atom → L2 Scenario → L3 Persona`，原则原话 *"**Lower layers preserve evidence; upper layers preserve structure**"*、*"The Persona layer carries day-to-day preferences; the system **drills down to Atoms only when details matter**"*<br>· ⭐ **完整下钻链**：`Persona/画布 → Scenario/jsonl → L0/refs` —— *"Compression often sacrifices traceability… avoids **irreversible compression** by maintaining a **deterministic path** from high-level abstractions back to ground-truth evidence"* ⇒ **这就是我们要的 `index → 群 → episode → events.jsonl`**<br>· ⭐ **短期用 Mermaid 符号图当常驻**（几百 token），完整 tool log offload 到 `refs/*.md`，靠 **`node_id` grep 回原文** ⇒ **"用符号换正文"的极端形态**<br>· **可直接对标的旋钮**：`recall.strategy=hybrid`（**BM25 + vector + RRF**）· `maxResults=5` · **`maxTotalRecallChars`（召回总字符预算！）** · `maxCharsPerMemory` · **`recall.timeoutMs=5000`（超时就跳过注入、不阻塞对话）** · `bm25.language=zh`（jieba）· **`pipeline.l1IdleTimeoutSeconds=600`（空闲 10 分钟触发提取）** · `enableWarmup`（新会话从第 1 轮起，间隔 **1→2→4 翻倍**）· `extraction.enableDedup`（向量去重/冲突检测）· `persona.triggerEveryN=50`<br>· **自动召回**：*"once enabled… **recall before the next turn**"* ⇒ **引擎在下一轮之前自动取好**，不是模型主动查（他们**另有** tools `tdai_memory_search` / `tdai_conversation_search` 作为补充）<br>· 指标：token −61%、成功率 +51.5%、PersonaMem 48%→76%（⚠️ 自家报告） | [TencentDB Agent Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory) |
| 30 | ⭐ **对我们的三条直接结论**：<br>① **"群 + 摘要"有权威先例**（GraphRAG global / TencentDB L3）⇒ 我们的 `index` 与 L2 belief 不是自创<br>② ⭐ **"给她一个动作"可以不用 tool call** —— **文本标记拦截**（paw-memory 的 `[recall]`）是**零 API 支持**的做法；或干脆**引擎自动召回**（TencentDB：*recall before the next turn*）⇒ **我们的"特定动作"有三个候选实现，不必等 function call**<br>③ ⭐ **必须抄的一条**：**预取要有超时兜底**（`recall.timeoutMs=5000`，"超时就跳过注入、**不阻塞对话**"）—— 正好补上我们 `DESIGN_DIGEST_LAYERS §4.1` 那两个风险（预取时机不可移动 / 冗余消失） | 同上 |

**未核实 / 检索边界（诚实声明，第三份）**：① **没有任何产品公开文档化"显式计数重复"** —— 这是行业空白；
② **以"常驻 / 触发 / 检索"命名的公开三层架构没找到**（最接近 nacre L0–L3 与 **ST 事实上的三层**，后者是归纳）；
③ **Character.AI / ChatGPT / Gemini / Kindroid 官方页** 403 或 JS 渲染 ⇒ 那几条是**明确标注的二手**；
④ **Talkie / Linky / Anima 官方无公开记忆文档**。

---

