# 记忆系统设计（业界查证 + 升级路径）

> 2026-08-27 定稿方向。动机：传统滑动窗口"呆滞"——记忆不按时间均匀分布
> （"不记得刚才说的，但记得很久前的重要讨论"）。本档记录业界查证、
> 我们的三层记忆架构、分步升级路径——每一步标注：✅ 已实现 / 🔧 优化空间 /
> ⛔ 当前不可实现点（及原因）。

---

## 一、动机与问题

```
传统滑动窗口（最近 N 轮全量喂）的缺陷:
  · 按【时间】截取——"呆滞": 重要的旧内容随窗口滑走, 不重要的新内容占窗口
  · 窗口外记忆彻底丢失（除非外部记忆兜底）
  · 用户洞察: "我不记得刚刚说了什么, 但绝对记得之前讨论时间回溯的话语"
    ——记忆的分布是【重要性】驱动的, 不是时间均匀的
```

## 二、业界查证（2026-08-27 web 检索）

### 2.1 评分驱逐式（Generative Agents, Stanford 小镇）

- [generative-agents-2 memory_stream](https://github.com/apollohuang1/generative-agents-2/blob/main/memory_stream.py)
- [三组件评分实现（codex-memory）](https://docs.rs/codex-memory/0.1.64/codex_memory/memory/three_component_scoring/index.html)
- [评分 issue 讨论](https://github.com/stratalab/strata-core/issues/1637)

```
机制: 记忆流（memory stream）——每条记忆 digest 时由 LLM 打【重要性分】(0-10);
检索时按  recency × importance × relevance  加权取 top-K;
记忆库满时驱逐"不重要的旧", 保留"重要的旧"。
→ 正是"过筛的窗口"——重要性感知
```

### 2.2 分层 + 按需调页式（MemGPT / Letta）

- [MemGPT: Adaptive Retention and Context Summarization](https://informationmatters.org/2025/10/memgpt-engineering-semantic-memory-through-adaptive-retention-and-context-summarization/)

```
机制: main context（常驻窗口）+ external context（外部记忆, 索引）——不全量喂;
"memory pressure"（窗口快满）→ 自省: 驱逐不重要 / 压缩摘要 / 外部化。
→ 与我们的三层架构同构: 滑动窗口（常驻）+ 原文回捞（未来 embedding 按需调页）+ wiki（压缩）
```

### 2.3 语义 + 时间感知驱逐（研究）

- [Focusing Memory in LLMs: Semantic and Temporal Aware Eviction](https://soe.lau.edu.lb/research/undergraduate/focusing-memory-in-llms-semantic-and-temporal-aware-eviction-for.php)

```
驱逐（eviction）同时考虑【语义重要性 + 时间】——驱逐"语义上不重要的旧内容"
优于纯时间驱逐（传统滑动窗口）
```

### 2.4 记忆层框架 / 教程

- [Mem0 vs Zep（记忆层对比）](https://mem0.ai/blog/mem0-vs-zep)
- [NirDiamant/Agent_Memory_Techniques（工作记忆/上下文窗口教程）](https://github.com/NirDiamant/Agent_Memory_Techniques/blob/main/all_techniques/12_working_memory_context_window/README.md)

---

## 三、我们的记忆架构（三层）

```
┌─────────────────────────────────────────────────────┐
│ ① 滑动窗口（短期记忆）  每轮全量喂窗口内历史（顺序保持——对话连贯）  │
│ ② 原文回捞（长期记忆）  窗口外重要片段按需回捞（"回忆注入"; 未来 embedding） │
│ ③ wiki/digest（提炼）   语义层——结论/性格/关系（压缩 + 角色一致）    │
└─────────────────────────────────────────────────────┘
关键区别（vs Generative Agents）:
  我们是对话式（user/assistant 顺序逻辑流）——不能照搬"乱序检索喂入"
  回忆注入必须保持对话顺序（以"（你突然想起…）"形式插入, 不破坏逻辑流）
```

## 四、升级路径（分步 + 状态标注）

### Step 1: 滑动窗口参数化（✅ 本轮已实现）

```
DEFAULT_HISTORY_ROUNDS = 40（原 20）
引擎构造参数 history_rounds（MMT + bond 双引擎）——玩家可配（设置页未来接入）
_trim_history / resume 重建统一用 self._history_rounds
```

- 🔧 优化空间：设置页（settings.toml）暴露数值——per 角色覆盖（[characters.xxx] 分组预留）
- ⛔ 不可实现点：无

### Step 2: digest 契约加 significance 分（✅ 已实现——2026-08-27）

```
digest 输出加 significance 字段（0~1, LLM 打分——几乎零增量成本; 旧名 importance, 读时兼容）
用途: ① 检索排序（重要的先回捞）② 驱逐决策（窗口满时保留重要旧内容）
```

- 🔧 优化空间：检索/驱逐的消费（见 Step 3/5——目前仅回忆通道按 significance 加权）

### Step 3: 索引检索（⛔ 方案废弃——2026-08-28 调研裁决, 原文回捞改为 embedding）

```
初代方案（2026-08-27 尝试, 已删除）:
  LLM 输出 index: [{snippet, significance, topic}] → 引擎逐字匹配定位 → wiki.index
  问题（四轮修正仍走不通——用户裁决"没想好实现, 先看业界怎么做"）:
    - LLM 输出位置（seq/position）→ LLM 看不到真实 seq, 定位是引擎的活
    - snippet + 引擎正则匹配 → 两层错误层; 单事件定位丢集群; 重复台词歧义
  业界查证结论（2026-08-28）:
    - 主流（Generative Agents / Mem0 / SillyTavern）: 摘要即内容——检索后直接
      注入提炼条目, 不回溯原文
    - 唯一做原文回捞的 MemGPT: 用 **embedding 向量检索**定位, 不是 LLM/正则
    - 我们的 wiki（facts/beliefs/relations）= 主流模式, 已够用 → 删除整个 index
```

- ✅ 已删除：`index` 字段（契约 build_digest_schema / digest.md 规则 12 / consolidation
  `_clean_index`/`_merge_index`/`_match_index_seq` 函数族 / 旧 wiki 数据的 index 残留）
- 🔧 未来（Phase 2 已有计划——nomic embedding + numpy 余弦, MemGPT 同款）：
  **原文回捞 = 向量检索**——语义相近都命中（无字面歧义）、一段对话天然聚簇、
  重复内容取最近——初代方案的三个坑在向量方案下天然不存在
- 🔧 触发机制（若做回忆注入）三选一（未定——见下）：
  - a) LLM 每轮自主判断（输出"回忆"动作——类似 mmt_inspect_character 机制）
  - b) 规则/关键词触发（确定性, 死板）
  - c) 混合（b 兜底 + a 补充——主 LLM 意图 + 规则, 同视觉协议模式）

### Step 4: 回忆注入（⛔ 当前不可实现点）

```
"（你突然想起…窗口外的重要片段）"——对话顺序保持, 回忆以系统注记插入
```

- ⛔ 不可实现点及原因：
  1. 依赖 embedding 回捞（Step 3 废弃后未实现——见上）
  2. 注入位置/时机需与 momotalk_rules 的"单人模式/插嘴"语义协调
  3. 回忆内容的真实性（LLM 可能脑补——需原文约束, 见 digest.md 规则 6/7 锚点）

### Step 5: 重要性感知驱逐（🔧 优化空间——长期）

```
窗口满时按 significance 驱逐（保留重要的旧, 逐出不重要的新）——Generative Agents 式
对话式变体: 保持顺序, 驱逐后以未来 embedding 回捞保证可回捞（不是丢失, 是"降级到外部"）
```

- ⛔ 当前不可实现点：依赖 Step 2（significance 分, 已实现）——但驱逐不丢的前提是
  原文可回捞（embedding 未实现）——直接驱逐会丢失（违背"重要旧内容保留"的目标）

---

## 五、当前不可实现点汇总（现状约束）

| 项 | 原因 | 前置 |
|---|---|---|
| Step 3 原文回捞（embedding） | 初代索引方案已废弃（业界主流=摘要即内容; 回捞须向量检索） | Phase 2 embedding（DESIGN_BRAIN 已有计划） |
| Step 4 回忆注入 | 依赖 embedding 回捞 + 需与规则语义协调 | embedding |
| Step 5 重要性驱逐 | 依赖 embedding（驱逐不丢的前提是原文可回捞） | embedding |

## 六、查证结论

```
业界共识: 记忆管理 = 重要性感知（评分/分层/语义驱逐）——不是"更大的窗口"
我们的定位: 对话式变体（顺序保持）——吸收 Generative Agents 的评分概念
           + MemGPT 的分层结构——分步落地（见升级路径）
```
