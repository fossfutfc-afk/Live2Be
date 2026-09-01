# AGENT_BRAIN — 图式 wiki 实施蓝图（工作区: core/brain/）

> 2026-09-02 建立。**这是实施蓝图（怎么建），不是架构原则（为什么）**——架构见根目录
> `DESIGN_BRAIN.md`。本文件是给实施者（人/Agent）的执行规格：节点数据结构、构图流程、
> 渲染模板、修订契约、检索规则、里程碑。**所有"已定"项按规格实现；"开放"项在对应
> 里程碑动手前拍板（附建议）。**
>
> 来源整合：DESIGN_BRAIN.md（§5.1 组织 pass / §7 epistemic）+ neuron 草稿
> （Diary/Abstract 字段）+ 历次讨论（分层/三通道召回/罗盘成长/校验通道）。

---

## 0. 目标与验收

**目标**：把 `data/worlds/{world}/characters/{char}/wiki.json` 升级为**图式 wiki**
（jsonl 逐条 + 关联边），角色拥有：长久的日常质感记忆（不升华）、成长弧线（不 OOC）、
认知分级（epistemic）、可检索可组织（三通道 + 修订契约）、可回滚（溯源）。

**验收（M 系列全部过测试 + 遥香真实段闭环跑通）**：
- M3 后：一次真实 bond 闭环 → wiki 产生 episode 条目（narration + verbatim）+ 可选 belief
- M4 后：组织 pass 能对旧条目做 update/merge/link，id 校验拒幻觉引用
- M5 后：注入渲染按层分级（summary → 珍贵 → 最近 → belief），无 id 泄漏给主 LLM
- 遥香种子：出厂基座条目与 experience/knowledge 一一对应，epistemic 全部正确

---

## 1. 节点数据结构（已定）

### 1.1 episode 节点（对应 neuron 的 Diary；具体日常，容量大）

```jsonc
// 一行一条（wiki.jsonl）
{
  "id": "m_0003",
  "kind": "episode",
  "narration": "那天傍晚老师陪我在杂草屋看苔藓，说地砖里长出的苔藓也可以是花",  // 第一人称轻摘要（保留质感, 不升华）
  "verbatim": "「地砖里长出的苔藓也可以是花——就像遥香你。」",                 // 可选: 重要原话（R2 质感锚点）
  "tags": ["老师", "杂草屋", "自我肯定"],
  "significance": 0.8,                 // 0~1; ≥0.8 = 珍贵档（保底通道; 对应 neuron 的 memo 档）
  "epistemic": "observed_fact",        // 本线亲历
  "observer": "igusa_haruka",
  "segment_id": "s_0003",              // 溯源: 段
  "event_seq": [42, 58],               // 溯源: 事件区间（R6 回滚定位）
  "ts": "2026-09-01T20:00:00",         // 引擎分配（继承事件）
  "source": "digest",                  // digest | seed
  "links": ["m_0001"],                 // 关联（无向）; 溯源方向约定: belief→支撑它的 episode
  "contradictions": []                 // 显式矛盾对（特殊边）
}
```

**字段规则**：
- `narration` 必填（第一人称——采纳 neuron 草稿；digest 的 LLM 以本线角色视角写）
- `verbatim` 可选——LLM 判定"值得记住的原话"才填（防滥用：每段最多 2 条）
- `epistemic` 必填，取值见 DESIGN_BRAIN.md §7 表
- `source=seed` 的条目（出厂基座）**不可 update 原文**（只允许追加注记字段 `notes`）

### 1.2 belief 节点（对应 neuron 的 Abstract；抽象认知，少量）

```jsonc
{
  "id": "m_0009",
  "kind": "belief",
  "subject": "sensei",                 // 认知对象（neuron 的 name; 老师/阿露/自己…）
  "content": "老师是第一个不会嫌弃我的人",  // 抽象信念（升华）
  "growth": "从自卑到开始相信自己被需要",    // 可选: 成长弧线标注（neuron 的 growth）
  "observation": ["老师总记得我说过的话"],   // 可选: 对该对象的观察（可承载玩家口癖等 R5 素材）
  "tags": ["老师", "信任"],
  "significance": 0.9,
  "epistemic": "inferred_belief",      // belief 只能是 inferred_belief（护栏）
  "observer": "igusa_haruka",
  "segment_id": "s_0003",
  "event_seq": [42, 58],
  "ts": "2026-09-01T20:00:00",
  "source": "digest",
  "links": ["m_0003", "m_0001"],       // 溯源: 支撑它的 episode 们
  "contradictions": ["m_0012"]
}
```

**规则**：belief 的 `links` 必须至少指向 1 条 episode（升华必须有支撑——neuron 规则
"diary 要么连已有 abstract 要么新开 abstract"的结构化版；无支撑的 belief 被引擎拒绝）。

### 1.3 fact 节点（出厂基座，canon_fact）

```jsonc
{
  "id": "c_0002",
  "kind": "fact",
  "content": "遥香曾因拆炸弹事件对 sensei 建立信任",   // 第三人称（锚点用, 不渲染成角色记忆）
  "tags": ["拆炸弹", "信任"],
  "significance": 0.95,
  "epistemic": "canon_fact",
  "source": "experience",              // experience | knowledge
  "source_key": "self.regular.1",      // 溯源到 yml 的哪个字段
  "ts": "<世界线创建时间>",
  "links": [],
  "contradictions": []
}
```

**规则**：canon_fact 只由种子生成器产出；动态 digest/组织 pass 永远不产 canon_fact；
注入时只作**锚点/校验基准**，不进【角色记忆】渲染段。

### 1.4 开放问题（M1 动手前拍板）

- [ ] **significance 标度**：沿用 0~1（与现有代码一致），neuron 的"0~100 + memo 101~200"
      折叠为"0~1 + ≥0.8 珍贵档"——建议采纳折叠方案
- [ ] **contradictions 存字段还是存 link 类型**：先字段（简单）；未来边类型化时并入
- [ ] **第一人称存储的合并去重**：narration 第一人称后 content 去重键 = narration 原文
      （跨调用同句重复 → 去重仍成立）——验证即可，无需设计

---

## 2. 存储机制（已定）

```
文件: data/worlds/{world}/characters/{char}/wiki.jsonl
操作: 任何变更（create/revision/seed）→ 读全部 → 改 → 原子整写（atomic_write 同款）
     （规模 ≤ 数千行, 整写毫秒级; 快照 = 复制文件, 与事件流快照语义一致）
id:   全局递增 m_0001 / c_0001（c_ = 出厂基座）
版本: update 不产生新行——直接在原行改 content/字段, 但写 evolution_log 记录
      （{ts, action, id, before, after, reason}——审计 + R6 回滚依据）
索引: 内存 dict[id→entry] + tags 倒排; embedding 索引 = 派生（M4, numpy, 不落盘）
```

**为什么不 append-only**：事件流 append-only 是因为它是**日志**（不可变真源）；
wiki 是**派生视图**（可重算可改写）——修订后整写更简单，且快照/回滚本来就整文件处理。
（与 DESIGN_BRAIN.md §11"wiki 是派生视图"一致。）

---

## 3. 构图流程（已定, 三段闭环）

```
[段闭环] events.jsonl 新增事件
   │
   ▼ Step 1 消化+组织（同一 LLM 调用, digest.md v2 扩展）
   │   输入: 时间线 + 视觉记忆 + 三通道召回子图渲染（组织视图）+ 锚点 + 罗盘触发定义
   │   输出: {entries: [新条目…], revisions: [修订动作…], evidence: [成长证据…],
   │         affection_exp_delta: n}
   │
   ▼ Step 2 引擎执行（确定性, 全量校验通过才落盘）
   │   ① 新条目: 逐条 schema/词表/epistemic 校验 → 分配 id → 落盘
   │   ② revisions: id 存在性（仅限本次渲染子图内）→ 护栏（epistemic 不可降级/
   │      canon_fact 不可改/无支撑 belief 拒绝）→ 应用 → evolution_log
   │   ③ evidence: 置信度 ≥ 阈值 → 罗盘函数进度增量（带事件溯源）; 否则丢弃
   │   ④ affection: 幂等事件写（现有逻辑不变）
   │
   ▼ Step 3 索引更新 + 注入刷新（下一轮对话/剧情生效）
```

**组织 pass 与消化同调用**（不新增调用点）：LLM 一次拿到"新经历 + 旧子图"，同时产
新条目和修订动作——碰撞端（召回）与输出端（修订）在同一趟里闭合。

---

## 4. 渲染规格（已定）

### 4.1 组织视图（喂 digest/组织 LLM；带 id + 邻接表）

```
【本次新经历】
（render_timeline 输出…）

【相关旧记忆（供组织决策）】
#m0003 [episode, sig 0.80, links: m0001] 那天傍晚老师陪我在杂草屋看苔藓…
        〝「地砖里长出的苔藓也可以是花」〞
#m0009 [belief, sig 0.90, links: m0003 m0001] 老师是第一个不会嫌弃我的人
#c0002 [fact, canon, 只读] 遥香曾因拆炸弹事件对 sensei 建立信任

【组织动作】
- 对旧条目用 #id 引用, 不得编造不存在的 id
- 动作: create / update #id / merge #a #b / link #a→#b / contradict #a #b
- 护栏: 不得强行升华; 不得修改 canon_fact; belief 必须 links 到支撑 episode
```

### 4.2 角色注入视图（喂主剧情 LLM；无 id 无链接；分层排序）

```
【角色记忆（brain）】
我记得那段日子：{summary}

我记得的事（珍贵的）：
- {episode.narration}（verbatim 存在时: 「原话」）

最近的事：
- {narration}…

我心里渐渐觉得：
- 对{sensei}：{belief.content}（growth 非空时附: ——{growth}）

我听说的：
- {reported_fact 条目}（来源: {source}）
```

排序规则：belief 常驻（significance 降序, 上限 5）; episode 按"珍贵档优先 → 最近 ts
降序", 上限 10; reported_fact 仅当无 observed 同主题时入列。canon_fact 不进本段。

### 4.3 校验视图（异步校验 lane, M5）

```
【角色行为罗盘（当前状态）】script.yml persona_compass + wiki 函数进度
【待校验片段】（主 LLM 最近一场输出）
→ 校验 LLM: 行为与罗盘冲突? 冲突点 + 证据?（text 模式, 返回结构化标记）
```

---

## 5. 修订契约（已定, 完整 schema）

```jsonc
{"revisions": [
  {"action": "create",    "entry": {…完整条目, 无 id 无 ts（引擎分配）…}},
  {"action": "update",    "id": "m0003", "patch": {"significance": 0.85, "notes": "…"}},
  {"action": "merge",     "ids": ["m0001", "m0007"], "into": {…新条目…}},
  {"action": "link",      "from": "m0003", "to": "m0010"},
  {"action": "unlink",    "from": "m0003", "to": "m0010"},
  {"action": "contradict","a": "m0003", "b": "m0009"},
  {"action": "resolve",   "a": "m0003", "b": "m0009"}   // 矛盾消解（可选, 配合 update）
]}
```

**引擎校验规则（全量通过才落盘）**：
1. 所有 `id/from/to/a/b` ∈ 本次渲染子图 id 集（防幻觉 id）→ 违者整包 feedback 回灌
2. `update` 目标不得是 `source=seed` 的 canon_fact（只允许 `notes` 追加）
3. `update` 不得改变 `epistemic`（inferred_belief 永远是 inferred_belief）
4. `create` 的 belief 必须 `links` 非空（无支撑升华拒绝）
5. `merge` 的 `into` 继承被合并条目的 `links`/`contradictions` 并集, `event_seq` 取并
6. 原子性：任一违反 → 整包不执行（宁缺勿错）

---

## 6. 三通道召回（已定, M4 实现）

```
query 构造（组织 pass 用）: 本次新经历时间线全文（非用户输入——digest 场景）
通道1 相似度: embedding(query) × numpy 余弦 → top-k（k=5）      [M4]
通道2 珍贵保底: significance ≥ 0.8 且未被通道1命中 → 补 n=2     [M1 即可用]
通道3 随机摘段: 对数正态(seq-age) 加权抽 1 段                    [已有]
合并: 去重 → 沿 links 一跳扩展（BFS）→ significance 降序 → 截断 15 条 → 渲染组织视图
```

注入侧（角色视图）不召回——按 §4.2 规则静态分层（主剧情不需要"检索注入",
那是记忆注入的简化形态; 未来若做"回想注入"再按此三通道）。

---

## 7. 成长与不 OOC 的三层保障（已定）

```
① 静态层: 六文件 + 出厂基座(canon_fact) —— immutable, 平行世界共享出厂设定
② 动态层: episode/belief 只描述"本世界线发生了什么/角色怎么想" —— 可成长可回滚
③ 校验层: 锚点(人设) + 罗盘(八维/防御, 作者写) + epistemic 护栏
   —— 成长证据(罗盘触发)必须带原文引用 + 置信度阈值; 无证据不涨（宁缺勿错）
```

**neuron 草稿中"每次复盘必有升华"与 R2 的冲突——本蓝图裁决**：
不强制升华；升华（belief 创建）是**可选且必须带支撑 episode** 的。日常记忆以
narration+verbatim 原样保存（质感优先），只有真正认知变化才允许 belief。

---

## 8. 里程碑（每个 M 含测试, 基线 310 不动）

| M | 内容 | 依赖 | 验收 |
|---|---|---|---|
| **M1** | wiki_store v2（jsonl + 原子整写 + id + 索引）; 种子生成器（遥香: experience/knowledge → fact/episode 条目, 手写罗盘 persona_compass 骨架） | 无 | 遥香种子 100% 映射; 读写/快照/校验测试过 |
| **M2** | 组织视图渲染 + 修订契约校验（id 存在性/epistemic/支撑规则）; evolution_log | M1 | 构造修订包样例全过/全拒测试过 |
| **M3** | digest.md v2 + build_digest_schema v2（entries/revisions/evidence）; consolidation 改造（同调用输出修订） | M2 | 真实 bond 闭环 → 条目+修订落盘; 310 基线不破 |
| **M4** | 三通道召回（embedding 通道: 本地 nomic, numpy 余弦, 无 embedding 时降级 tags 匹配） | M3 | 组织视图含一跳扩展子图; 无 embedding 环境自动降级 |
| **M5** | 注入改造（§4.2 分层渲染 + 校验 lane 异步 worker 复用 emotion 队列） | M3 | 角色视图无 id 泄漏; 校验 lane 不阻塞主流程 |

**每 M 结束**: 全量 pytest + 提交（feat/two-pass-emotion）; M3 之前不动现有
consolidation/recall 的对外行为（新代码独立目录 core/brain/wiki_v2/, 最后切换）。

---

## 9. 开放问题汇总（拍板清单）

| # | 问题 | 建议 | 拍板时机 |
|---|---|---|---|
| 1 | significance 标度 | 0~1 + ≥0.8 珍贵档（折叠 neuron 的 memo） | M1 |
| 2 | contradictions 存储 | 先字段后类型化 | M1 |
| 3 | 深度整理（merge/归类）频率 | 每段轻组织（create/link/update）+ 每 N=5 段或矛盾检测触发深度整理 | M3 |
| 4 | 组织视图 id 格式 | `m0003`（无 # 前缀, 防 LLM 把它当 markdown 标题） | M2 |
| 5 | verbatim 来源 | 段落原文逐字（LLM 复制, 禁止改写）——校验: 与事件流原文模糊匹配 | M3 |
| 6 | 玩家画像（R5）落点 | wiki 顶层加 `player_profile` 段（per 世界, 与角色线平级） | M5 后 |
| 7 | 校验 lane 的冲突处理 | 记录 + 高频统计 → 提示作者改卡/改罗盘（不自动改） | M5 |
