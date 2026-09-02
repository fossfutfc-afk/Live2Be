# AGENT_BRAIN — 图式 wiki 实施蓝图（工作区: core/brain/）

> 2026-09-02 建立。**这是实施蓝图（怎么建），不是架构原则（为什么）**——架构见根目录
> `DESIGN_BRAIN.md`。本文件是给实施者（人/Agent）的执行规格：节点数据结构、构图流程、
> 渲染模板、修订契约、检索规则、里程碑。**所有"已定"项按规格实现；"开放"项在对应
> 里程碑动手前拍板（附建议）。**
>
> 来源整合：DESIGN_BRAIN.md（§5.1 组织 pass / §7 epistemic）+ neuron 草稿
> （Diary/Abstract 字段）+ 历次讨论（分层/三通道召回/罗盘成长/校验通道）。

---

## 0.1 模块文件布局（多文件分工, 2026-09-02）

```
core/brain/wiki_v2/                # 独立模块——不动现有 brain/*.py 直到 M 系列切换
├── AGENT_BRAIN.md                 # 本蓝图
├── __init__.py                    # 公共导出
├── nodes.py                       # ✅ 板块1 节点数据结构（4 kind; title/history/main_text; relation 已砍）
├── store.py                       # ✅ M1b 存储（jsonl/原子整写/id 分配/索引/快照/去重检查）
├── seed.py                        # ✅ M1c 出厂 digest pass（experience/knowledge → fact 条目, 确定性映射 v1, 幂等）
├── render.py                      # ✅ M2 渲染（组织视图带 id 邻接表 + 角色注入视图分层）
├── revise.py                      # ✅ 板块4 修订执行器（apply_decisions 决策表 + apply_revision_package 深度整理）
├── evolution.py                   # ✅ M2 审计日志（append-only, R6 回滚依据）
├── recall.py                      # ✅ M4 三通道召回 + 一跳扩展（embed_fn 注入, tags 降级）
├── llm_call.py                    # ✅ 板块3 LLM 调用鲁棒层（重试/deadline/reasoning_effort, digest 唯一 LLM 触面）
└── digest.py                      # ✅ 板块4 digest v2 两轮管线（A 记录员 + B 理解者决策表, 原子/水位/幂等）
contract/digest_registry.py        # ✅ 板块2 digest 动作注册表（spec 单源: schema 渲染 + parse 校验）
llm/prompts/digest_v2_round_a.md   # ✅ Round A prompt（记录员）
llm/prompts/digest_v2_round_b.md   # ✅ Round B prompt（理解者）
```

分工原则: 每文件单一职责, 依赖方向单向（nodes ← store ← revise ← render/recall ← digest）;
契约层在 contract/digest_registry.py（LLM 可见面与 runtime 校验双写合一）;
引擎侧流程在 digest.py 编排（两轮） + revise.py 执行（store 只提供原语, 不做修订决策）。

```
dev 工具（不进运行时依赖, M3 后有真实数据再做）:
tools/wiki_viz.py  读 wiki.jsonl → mermaid 导出（零依赖, webgui/markdown 渲染）
                   可选 networkx+matplotlib（requirements-dev）: 度中心性/连通分量
运行时图操作 = dict 邻接（千级节点 O(1)）——不引入 networkx（双真源风险, 2026-09-02 决策）
```

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
  "id": "m0003",
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
  "links": ["m0001"],                 // 关联（无向）; 溯源方向约定: belief→支撑它的 episode
  "contradictions": []                 // 显式矛盾对（特殊边）
}
```

**字段规则**：
- `narration` 必填（第一人称——采纳 neuron 草稿；digest 的 LLM 以本线角色视角写）
- `verbatim` 可选——LLM 判定"值得记住的原话"才填（防滥用：每段最多 2 条）
- `epistemic` 必填，取值见 DESIGN_BRAIN.md §7 表
- `source=seed` 的条目（出厂基座）**不可 update 原文**（只允许追加注记字段 `notes`）

### 1.2 experience 节点（重复模式层, 🔧 新增 2026-09-02）

**定位**：相同/同类的事情多次发生 → 聚合为**模式事实**（不是一次性 episode，不是抽象 belief）。
心理学对应：习惯/统计学习记忆（habit memory）。一石四鸟：聚合重复防节点爆炸 /
反升华闸门（重复先落事实模式, 拦错误跳升）/ 玩家口癖载体（R5: subject=player）/
significance 强化（被引用记忆升值）。

```jsonc
{
  "id": "e0002",
  "kind": "experience",
  "pattern": "sensei 提到工作繁忙",          // 模式概括（事实性, 不升华）
  "subject": "sensei",                       // 模式主体（玩家口癖时 = player）
  "count": 4,                                // ★ 引擎数 links 得出, LLM 不数数（防幻觉计数）
  "examples": ["「这周又忙成狗了」", "「今天加班, 晚点回你」"],   // verbatim 摘录, 最多 3
  "tags": ["sensei", "工作"],
  "significance": 0.7,                       // 随 count 强化: min(0.9, base + 0.05×(count-1))
  "epistemic": "observed_fact",
  "observer": "igusa_haruka",
  "segment_id": null,                        // 跨段聚合, 无单一来源段
  "event_seq": [61, 78, 92],                 // 全部 occurrence 的溯源（R6 定位）
  "ts": "<last_ts>",
  "source": "digest",
  "links": ["m_0011", "m_0015", "m_0020"],   // 指向支撑它的 episodes; count = len(links)（引擎保证）
  "contradictions": []
}
```

**规则**：
- 同类判定 = LLM（组织 pass 输出 `accrue` 动作）; count/event_seq/significance 强化 = 引擎
- **去重键 = event_seq**（同事件重复消化 → 去重; 不同事件同类 → accrue, 永不因内容重复被删）
- 玩家口癖 = subject=player 的 experience 节点（R5 载体, 合并去重不得触碰——老规矩机制化）

### 1.3 belief 节点（对应 neuron 的 Abstract；抽象认知，少量）

```jsonc
{
  "id": "m0009",
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

**规则**：belief 的 `links` 必须至少指向 1 条（episode | experience）——升华必须有支撑。
**episode 连接裁定（2026-09-02 用户澄清）**：每条新 episode 必须在
"链接到已有 belief/experience" 与 "新建 belief/experience（并链接它）" 之间
**至少选择其一**——强制的是连接决策, 不是内容升华。

### 1.4 fact 节点（出厂基座, canon_fact）

```jsonc
{
  "id": "c0002",
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

**规则**：canon_fact 只由**出厂 digest pass** 产出（世界线创建时, experience/knowledge
渲染为预设时间线走一次消化——2026-09-02 用户决策: 种子生成器替换为出厂 digest, 与动态
digest 同一套机制）; 动态 digest/组织 pass 永远不产 canon_fact;
注入时**渲染为出厂记忆段**（§4.2 久远的记忆/我知道的事——2026-09-02 修正: fact 是
角色的出厂经历/出厂认知, 她本来就记得/知道, 不是"世界真相"; 世界观另有 overview.yml）;
同时作**锚点/校验基准**（digest 防脑补）。
**双注入待处理**（开放项, M5）: MMT 盒A 静态注入已含 experience/knowledge → 与出厂记忆段
重复; 方案 = 统一注入源（experience/knowledge 不再静态注入, 一律从 wiki 渲染; 静态文件
保留为作者真源 + 出厂 digest 输入）。

### 1.5 节点类型总表（2026-09-02: 砍 relation——两参考系统(A-MEM/AgentGal)均无此层,
信息落 tags/subject; 无生产数据窗口期移除）

| kind | 语义 | epistemic | 谁产 | 支撑规则 |
|---|---|---|---|---|
| `fact` | 出厂经历/出厂认知（作者设定, 角色本来就记得/知道） | canon_fact | 出厂 digest（experience/knowledge） | immutable; 渲染为出厂记忆段 |
| `episode` | 一次性经历（质感: narration+verbatim; title 可选短标题） | observed_fact | 动态 digest | 必连 belief 或 experience（连接裁定） |
| `experience` | 重复模式（count 聚合） | observed_fact | 动态 digest（accrue） | 引擎计数; 口癖 = subject=player |
| `belief` | 抽象认知（升华; history 记录改写溯源 {episode_id, content, ts}） | inferred_belief | 动态 digest | links ≥1（episode\|experience） |

**图边 vs 节点（2026-09-02 澄清）**——两个维度, 不冲突:

```
图边（虚边, 引擎图结构, 存于节点字段）:   links / contradictions
   = 节点之间的结构关系（溯源/关联/矛盾）: m0003 links: m0009（episode 支撑 belief）
节点内容（被图边引用的实体）:              episode / experience / belief / fact
```

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
id:   全局递增 m0001 / c0001 / e0001（前缀: m=动态(episode/belief/relation), c=出厂基座, e=experience）
版本: update 不产生新行——直接在原行改 content/字段, 但写 evolution_log 记录
      （{ts, action, id, before, after, reason}——审计 + R6 回滚依据）
索引: 内存 dict[id→entry] + tags 倒排; embedding 索引 = 派生（M4, numpy, 不落盘）
```

**为什么不 append-only**：事件流 append-only 是因为它是**日志**（不可变真源）；
wiki 是**派生视图**（可重算可改写）——修订后整写更简单，且快照/回滚本来就整文件处理。
（与 DESIGN_BRAIN.md §11"wiki 是派生视图"一致。）

---

## 3. 构图流程（已定, 出厂消化 + 两轮闭环——2026-09-02 板块4 重构）

```
[Step 0 出厂消化] 世界线创建时（2026-09-02 决策: 种子生成器 → 出厂 digest pass）
   experience/knowledge → 渲染为"预设时间线" → 走一次消化（无修订/无情感）
   → 产出 canon_fact 条目（source=experience/knowledge, 带 source_key 溯源到 yml 字段）

[段闭环] events.jsonl 新增事件 → digest_segment（digest.py, 两轮 + 反馈重试 + 原子）
   │
   ▼ Round A「记录员」（只看新时间线——不注入旧记忆, 防"组织污染记录"）
   │   输入: 时间线 + 画面记忆 + 人设锚点（性格+知识两层）
   │   契约: digest_registry.build_schema(record) ← digest_v2_round_a.md
   │   输出: {episodes: [新经历…]}（parse_round_a 结构校验）
   │   引擎: 建 episode 节点（内存暂存; 引擎字段归属: ts/segment_id/event_seq;
   │         dedupe 幂等; 不落盘）
   │
   ▼ Round B「理解者」（新经历 ↔ 现有稳定认知, 决策表）
   │   输入: 新经历摘要 + 认知渲染（本地 id u0001.., 引擎防猜真实 id）
   │         + 时间线（evidence quote 逐字引用用）+ 锚点
   │   契约: digest_registry.build_schema(understand) ← digest_v2_round_b.md
   │   输出: {decisions: [逐 episode 一行 touch|update|add], evidence, affection_exp_delta}
   │        parse_round_b: 引用纪律（id 必须 ∈ 渲染列表）+ 覆盖检查（漏 episode 整包拒）
   │   引擎: apply_decisions（revise.py）——touch=add_link / update=白名单 patch +
   │         history 溯源 / add=新建+先链后入仓; epistemic 引擎归属
   │
   ▼ 提交（确定性, 全量通过才落盘）
   │   ① evidence: 置信度 ≥ 阈值/quote 非空 → 返回（罗盘应用后置, 无罗盘丢弃）
   │   ② affection_exp_delta → 幂等事件写（调用方）
   │   ③ store.save() + 推进 meta.digested_seq + save_meta
   │   失败（parse/执行/撞 deadline）→ clone_state 快照回滚, 水位不推进 → 可重算
   │
   ▼ Step 3 索引更新 + 注入刷新（下一轮对话/剧情生效）
```

**反馈回灌（feedback 语义, 2026-09-02 采纳 llm.client.feedback）**: 被拒轮把 LLM 自己
输出追加为 assistant 位 + 引擎错误, 同一上下文重试 1 次——模型能看见自己错在哪。

**深度整理（板块6 预留）**: 每 N=5 段或矛盾检测 → phase=deep 轮（merge/contradict,
apply_revision_package 复用, digest_registry 注册 deep 动作集）。

**两轮拆分动机**（板块4 复盘）: 旧单轮"记录+组织一包"让 LLM 同时干两类活——组织决策
依赖的旧记忆子图会污染记录（看到旧 belief 就忍不住升华）; 且 revision 契约的
"新 episode 必须连接裁定"与"可能确实没值得组织"相互拉扯。拆轮后 A 只记录（质感
优先不升华）, B 只看认知层（episode 摘要 + belief/experience 列表）做逐条决策——
结构保证不漏不编（A-MEM 逐条对齐升级 + AgentGal 两轮同构）。

---

### 3.1 mmt 会话 digest 策略（2026-09-02 拍板, 用户场景: 长聊不触发剧情/未来纯聊天模式）

**背景**: digest 原唯一触发点 = bond 剧情闭环（story_end 为段边界）——纯 mmt 长聊
永不消化, 三层损失: ① 约定/玩家分享/角色表露不进 wiki（跨 session 不记得）;
② **玩家画像 R5 断供**（subject=player 的口癖只在 mmt 出现）; ③ 好感冻结
（affection 事件只由 digest 写, 纯 mmt 好感不涨）。

**拍板（2026-09-02）**:
1. **mmt 窗口 digest**: 每 N=25 轮 mmt → 后台 digest（节流而非精确窗口——digest
   消化触发时刻全部未消化事件, 增量幂等, 撞车 0 新增短路; 锁串行 _digest_lock）
2. **触发保护**: 剧情中不切段——session_status in_vn / in_memorial → 不触发;
   bond 剧情中本就有 marker 段边界, mmt 窗口只作用于纯对话区
3. **空闲超时 T**: 暂缓（无常驻调度器; N 已覆盖长聊主场景; 触发器签名留
   idle_minutes 位, webgui 常驻 tick 再挂）
4. **不新增节点 kind**（4 kind 收敛形态; 玩家话语是内容维度不是结构维度）:
   - 约定/共同互动 → episode（narration 角色视角 + verbatim 玩家原话）
   - 玩家口癖/偏好/一次性个人信息 → experience subject=player（R5 主通道,
     蓝图 #9 拍板落点; pattern=画像句, 无需真重复）
   - **verbatim 语义扩展**: 原话双侧（角色或玩家）, 逐字; 说话者由 narration
     语境交代——渲染零改动
5. **约定必记（用户强调）**: MMT 专则第一条——与玩家的约定/共同计划必须进记忆
   （episode + tags 含"约定"）; 约定重复出现成模式 → experience subject=sensei
6. **好感结算开放**: mmt digest 同 bond 机制——affection_exp_delta → affection
   事件（幂等键 interact_max, 真源 events.jsonl）
7. **注入刷新**: digest 后台完成后**动态拼装注入段**（_brain_injection 字段原子替换,
   chat 每轮组装 system 时拼接）——不追加防重复注入, 跨线程零锁

**A 轮 MMT 专则**（digest_v2_round_a.md）: mmt 段素材只有对话本身——值得记的 =
约定/玩家透露/角色内心表露; 寒暄表情不记; 单轮无实质不硬凑。玩家说的话第一人称
只写角色感受与回应, 玩家原话放 verbatim。

**实现时机**: "digest 接入运行时"板块（async_digest 切 wiki_v2 digest_segment +
触发器 should_digest_mmt 纯函数 + seed 挂载 + affection 幂等写）——2026-09-02 动工。

**运行时切换状态（2026-09-02 ✅ 完成）**:
- momotalk `_inject_brain` 重写（legacy digest_session/WikiStore/build_brain_injection
  退役）: per-char 单库 WikiStoreV2 + 出厂 seed 挂载（0 LLM, source_key 幂等）+
  digest_segment 两轮 + render_character_view 注入段（`_brain_injection` 原子替换,
  chat 动态拼装——不追加防重复注入, 跨线程零锁）
- async_digest 双触发点: bond 剧情闭环（story_end 收尾）+ mmt 每 N=25 轮
  （`_maybe_mmt_digest`: 轮数判定 + in_vn/in_memorial 保护内聚, 纯函数可单测）
- 好感结算: digest 返回 affection_delta → 运行时幂等写 affection 事件
  （幂等键 interact_max, `_interact_max` 助手——真源 events.jsonl）
- bond/vn_cli 剧情注入 + random_events memory_flash 同步切 wiki_v2
  （`load_brain_segment` 公共 helper / `random_flash_segment` 双通道随机摘段）
- legacy core/brain/{consolidation,hippocampus,recall} 保留但**无运行时消费方**
  （仅 experiments/测试/导出引用——最后清理轮次删除）

**reasoning_effort 生产档（2026-09-02 拍板: high）**——digest 质量实验矩阵
（deepseek-v4-flash thinking, smoke 两最小 unit）:
| 档 | 结果 | 单 unit 耗时 |
|---|---|---|
| low | 5/5 合格——规则全过但组织偏浅 | ~17s（早期 62s 含长考失控） |
| medium | 1/3——2/3 死在规则校验（引擎防护拦截, 无污染） | 3~6min |
| high | 2/2——认知深化（unit2 update 而非 add）、evidence 逐字自检、growth 演化细腻 | 118s + 32s |

适配（high 档参数）: **thinking level 参数化**——settings.toml [llm] `reasoning_effort`
（low|medium|high, 默认 high; 空/缺失 → 不注入=模型默认）——单一配置源:
LLMClient 构造解析 → default_extra_body（extra_body=None 注入, 显式 {} 关闭,
chat/chat_full/chat_stream 三入口一致）; digest deadline_seconds 默认 300s;
LLMClient per-call timeout 覆盖（momotalk digest 传 300——共享客户端 60s
主对话超时会掐 high 长考, 主对话快速失败语义不变）。

---

---

## 4. 渲染规格（已定）

### 4.1 组织视图（喂 digest/组织 LLM；带 id + 邻接表）

```
【本次新经历】
（render_timeline 输出…）

【相关旧记忆（供组织决策）】
#m0003 [episode, sig 0.80, links: m0009] 那天傍晚老师陪我在杂草屋看苔藓…
        〝「地砖里长出的苔藓也可以是花」〞
#e0002 [experience, sig 0.70, count 4, links: m0011 m0015 m0020] sensei 提到工作繁忙
        〝「这周又忙成狗了」〞
#e0007 [experience·关于老师, sig 0.75, count 5, links: m0030 m0033 …] 老师总说「摸鱼」
        〝「今天也摸鱼」〞      ← player experience: 带【关于老师】标记, 同类判定优先,
                                  accrue 敏感（口癖必须捕捉, 不被去重/合并掉）
#m0009 [belief, sig 0.90, links: m0003 m0001] 老师是第一个不会嫌弃我的人
#c0002 [fact, canon, 只读] 遥香曾因拆炸弹事件对 sensei 建立信任

【组织动作】
- 对旧条目用 #id 引用, 不得编造不存在的 id
- 动作: create / update #id / merge #a #b / link #a→#b / contradict #a #b / accrue #id
- 每条新 episode 必须: 链接到已有 belief/experience, 或新建 belief/experience 并链接（连接裁定）
- 护栏: 不得强行升华; 不得修改 canon_fact; belief 必须 links 到支撑 (episode|experience)
- 【关于老师】的 experience 是重点观察对象——玩家口癖/习惯必须被捕捉（见 §4.4）
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

老师的事（player experience 强调段, 2026-09-02 用户强调）：
- 老师总说「摸鱼」（count 5）
- 老师最近很忙（count 4）

我听说的：
- {reported_fact 条目}（来源: {source}）

久远的记忆（出厂经历, fact, experience 派生）：
- 和老师拆炸弹的那次，第一次有人这样对我

我知道的事（出厂认知, fact, knowledge 派生）：
- 阿露大人是便利屋68的社长，曾带我逃出霸凌
```

排序规则：belief 常驻（significance 降序, 上限 5）; episode 按"珍贵档优先 → 最近 ts
降序", 上限 10; reported_fact 仅当无 observed 同主题时入列; **fact 渲染为出厂记忆段**
（experience 派生 → 久远的记忆, 上限 5; knowledge 派生 → 我知道的事, 上限 5——
2026-09-02 修正: fact 是角色的出厂记忆, 她本来就记得/知道）。
**【老师的事】段 = subject=player 的 experience 节点（上限 5, count 降序）**——
它是角色对老师的观察积累（R5 强调点: 口癖/习惯的沉淀）, 独立成段不被普通 episode 淹没,
md 序列化时固定渲染在 beliefs 之后。

### 4.3 校验视图（异步校验 lane, M5）

```
【角色行为罗盘（当前状态）】script.yml persona_compass + wiki 函数进度
【待校验片段】（主 LLM 最近一场输出）
→ 校验 LLM: 行为与罗盘冲突? 冲突点 + 证据?（text 模式, 返回结构化标记）
```

### 4.4 player experience 强调规则（2026-09-02 用户强调, 贯穿整理与序列化）

1. **LLM 整理侧（组织 pass）**: 时间线中玩家话语行是口癖候选——渲染时高亮
   （`【玩家原话】`前缀）; subject=player 的 experience 在组织视图带
   `[关于老师]` 标记; accrue 同类判定对 player subject 更敏感（口癖优先捕捉）
2. **序列化侧（md/注入）**: 【老师的事】独立段（§4.2）, 固定渲染位置, count 降序
3. **去重豁免**: subject=player 的 experience 及其 occurrence **永不被内容去重/合并掉**
   （去重键 = event_seq 的机制保证）; 深度整理（merge）不得合并两个不同 pattern 的
   player experience
4. **承载**: 玩家口癖 = experience(pattern="摸鱼", subject="player", examples=[原文…])

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
  {"action": "resolve",   "a": "m0003", "b": "m0009"},   // 矛盾消解（可选, 配合 update）
  {"action": "accrue",    "id": "e0002",                 // 同类事件并入 experience（2026-09-02）
   "occurrence": {"event_seq": [61], "example": "「忙得脚不沾地」"}}
]}
```

**引擎校验规则（全量通过才落盘）**：
1. 所有 `id/from/to/a/b` ∈ 本次渲染子图 id 集（防幻觉 id）→ 违者整包 feedback 回灌
2. `update` 目标不得是 `source=seed` 的 canon_fact（只允许 `notes` 追加）
3. `update` 不得改变 `epistemic`（inferred_belief 永远是 inferred_belief）
4. `create` 的 belief 必须 `links` 非空（无支撑升华拒绝）
5. `merge` 的 `into` 继承被合并条目的 `links`/`contradictions` 并集, `event_seq` 取并
6. `accrue`: 同类判定信任 LLM, 但 `count`/`event_seq`/significance 强化由引擎计算
   （count = len(links), sig = min(0.9, base + 0.05×(count-1))）
7. **连接裁定**: 本包若无新 episode 满足"links 含 belief/experience 或 新建并链接"→ 整包回灌
8. 原子性：任一违反 → 整包不执行（宁缺勿错）

---

## 6. 三通道召回（已定, M4 实现）——2026-09-02 决策修订

```
query 构造（组织 pass 用）: 本次新经历时间线全文（非用户输入——digest 场景）
通道1 相似度: embed_fn 注入（批式; 无 embed_fn → 降级 tags 词面匹配）→ top-k（k=5）
通道2 珍贵保底: significance ≥ 0.8 且未被通道1命中 → 补 n=2
通道3 随机摘段: 30% 珍贵（sig 加权）/ 70% 对数正态(ts 年龄)加权抽 1 段
              （数学照搬 legacy random_recall_segment, age = ts 差——wiki_v2 无全局 seq）
合并: 去重(id) → 沿 links ∪ contradictions 一跳扩展 → significance 降序（暂定）→ 截断 15
```

**决策（2026-09-02 拍板）**：
- **D1 fact 进召回**——不排除任何 kind。用户预设经历 = 作者明示"角色必须记住的"，
  出厂基座同权参与三通道（sig 0.9 自然进珍贵保底; 组织视图里 canon 只读标记已支持）
- **D5 一跳扩展含 contradictions 目标**——否则组织视图的 c: 标记悬空, LLM 无法决策 resolve
- **RAG 后路 = 接口层**：`embed_fn` 批式注入槽即后路（v2 换 ChromaDB/FAISS 只换后端,
  调用方零改动）; **embedding 派生不落盘**（修订改内容零漂移, 落盘 = 双真源风险,
  jsonl 不膨胀; 代价 = digest 异步路径毫秒级重算, 可接受）
- **D2/D3** 确认; **D4** 排序 significance 降序（暂定, 混合打分 α·sim+β·sig+γ·recency 备选）

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

## 时间系统（计划, 2026-09-02——先写进蓝图, 待拍板后实现, 不入里程碑）

> 决策状态: 已达成一致 = ① 每个单元（mmt→bond→mmt）可标注时间; ② 记忆模糊化在渲染层派生。
> 待拍板 = P1 具体机制 / 桶表粒度 / time_skip 是否后置。
> **时间表述一律用英文**（跨语言安全, 同词表键名原则）——渲染输出如 "a month ago",
> 本地化展示是前端/作者的事, 与 LLM 交互只认英文。

### 背景与动机

wiki_v2 节点目前只有 `ts`（digest 创建时间）——不是事件发生时的**世界内时间**:
"最近的事"排序用的是 digest 时间; 角色/组织视图无从表达"这是多久前的事"。
单元时间系统补上这个"何时"维度。

### P1 单元时间标注（三个候选, 推荐 c）

| 方案 | 机制 | 问题 |
|---|---|---|
| a. 强制每单元=一天 | 每单元 +1 天 | 同一天聊多次 → 世界内时间飞走; 久别重逢感丢失 |
| b. LLM 推断 | 从上个单元结束时间推断 | 无锚必漂移; 双轨状态复杂 |
| **c. 偏移锚定（推荐）** | 世界内日期 = 真实日期 + 固定偏移; 偏移在世界线创建时锚定（作者配世界内基准日, 如 2050-07-01） | 零状态/零 LLM/零 schema 变更 |

**c 的理由**: `narrative_date(node) = date(node.ts) + offset` 随时可算; BA 本体就是真实日历同步
（活动按现实日期开）; 同一天聊五次 = 世界内同一天, 两周没玩 = 角色觉得好久不见。
**LLM 时间控制留后路（P1b, 后置）**: 显式 `time_skip` 动作（封闭词表 + 引擎 clamp）解决
"约定一个月后相见"类剧情——双轨对齐问题等真需要时再解。

### P2 记忆模糊化（渲染层派生, 引擎日期减法）

**原则**: 存储永远精确（narrative_date 派生自 ts）; 表达永远模糊（渲染时算）。
存模糊值必过期（"一个月前"一个月后还是"一个月前"）——派生渲染永远正确。
**LLM 零日期运算**（跨年/跨月必错）——减法、分桶全部引擎做, LLM 只消费结果文本。

**桶表（英文表述, 阈值按天, 可调）**:

| bucket (EN) | age range (days) |
|---|---|
| today | 0 |
| yesterday | 1 |
| the day before yesterday | 2 |
| a few days ago | 3–6 |
| last week | 7–13 |
| two weeks ago | 14–20 |
| last month | 21–60 |
| a few months ago | 61–180 |
| half a year ago | 181–365 |
| a year ago | 366–730 |
| long ago | > 730 |

边界: 未来日期 → clamp "today"; 缺失日期 → 不渲染时间; 未来 time_skip 解耦后模糊化仍正确
（只依赖存储日期）。

### 消费点

| 消费点 | 用法 |
|---|---|
| 角色视图 | 条目带 `（a month ago）` 相对时间——角色说话有时代感 |
| 组织视图 | 时间线事件带相对时间——digest 判断新旧/accrue 合理性 |
| digest 输入 | 给当前世界日期 + 相对时间; 禁止 LLM 输出绝对日期做运算 |
| 通道3 随机摘段 | age 改用叙事年龄（语义正确） |
| time_skip（后置） | 跳变后模糊化不受影响 |

### 待拍板

1. P1 机制选 (c) 偏移锚定?（推荐）
2. 桶表粒度（11 桶）OK?
3. time_skip 后置为增强功能, v1 不做?（推荐）

---

## 8. 里程碑（每个 M 含测试, 基线 310 不动; 板块 1~4 已于 2026-09-02 吸收 M1~M3 并重构为两轮 digest——下表 M3 描述已被 §3 两轮图取代, 保留作演进历史）

| M | 内容 | 依赖 | 验收 |
|---|---|---|---|
| **M1** | wiki_store v2（jsonl + 原子整写 + id + 索引）; **出厂 digest pass**（遥香: experience/knowledge → 预设时间线 → 消化 → canon_fact 条目; 手写罗盘 persona_compass 骨架） | 无 | 遥香出厂条目 100% 映射（source_key 可溯源）; 读写/快照/校验测试过 |
| **M2** | 组织视图渲染 + 修订契约校验（id 存在性/epistemic/支撑规则）; evolution_log | M1 | 构造修订包样例全过/全拒测试过 |
| ~~M3~~ | ~~digest.md v2 + revisions 契约（单轮输出修订）~~ → **板块 4 已重构为两轮**（Round A 记录员 + Round B 理解者决策表, digest_registry 契约, 原子快照, feedback 语义回灌） | M2 | 假 LLM 全链 + 失败矩阵测试过; 真 LLM 冒烟两轮闭环 |
| **M4** | 三通道召回（embedding 通道: 本地 nomic, numpy 余弦, 无 embedding 时降级 tags 匹配） | M3 | 组织视图含一跳扩展子图; 无 embedding 环境自动降级 |
| **M5** | 注入改造（§4.2 分层渲染 + 校验 lane 异步 worker 复用 emotion 队列） | M3 | 角色视图无 id 泄漏; 校验 lane 不阻塞主流程 |

**板块进度（2026-09-02 重构）**:
- 板块1 nodes ✅（relation 砍 / title+history / main_text 收敛）  板块2 digest_registry ✅
- 板块3 llm_call ✅（传输/策略分层）  板块4 两轮 digest ✅（骨架+执行器护栏+原子+幂等）
- 板块5 recall 候选推荐 ✅（recommend_candidates: embed_fn 注入=RAG 升级接口,
  关键词降级保守兜底; B 轮标注 疑似同主题(≥0.5, 禁 add 结构强制)/可能相关(≥0.25);
  render_cognition_list 本地 id 渲染迁入 render.py）
- 板块6 深度整理轮（phase=deep: merge/contradict, 每 N=5 段）——预留

**每 M 结束**: 全量 pytest + 提交（feat/two-pass-emotion）; M3 之前不动现有
consolidation/recall 的对外行为（新代码独立目录 core/brain/wiki_v2/, 最后切换）。

---

## 9. 开放问题汇总（拍板清单）

| # | 问题 | 状态 | 拍板时机 |
|---|---|---|---|
| 1 | significance 标度 | ✅ 已拍板 2026-09-02: decimal 0~1 + ≥0.8 珍贵档 | M1 |
| 2 | contradictions 存储 | ✅ 已拍板: 存字段（`contradictions` 数组） | M1 |
| 3 | experience 出厂基座 | ✅ 已拍板: 出厂 digest pass（预设时间线消化, 非独立生成器） | M1 |
| 4 | 升华/连接裁定 | ✅ 已拍板: 每条新 episode 必须连已有 belief/experience 或新建并链接 | M2 |
| 5 | 去重规则 | ✅ 已拍板: 去重键 = event_seq（同事件去重/不同事件同类 accrue）; 玩家口癖/习惯永不被内容去重 | M3 |
| 6 | 深度整理（merge/归类）频率 | ✅ 已拍板: 每段轻组织（create/link/update/accrue）+ 每 N=5 段或矛盾检测触发深度整理 | M3 |
| 7 | 组织视图 id 格式 | ✅ 已拍板: `m0003`（无 # 无下划线, 防 LLM 当 markdown 标题） | M2 |
| 8 | verbatim 来源 | ✅ 已拍板: 段落原文逐字（LLM 复制, 禁止改写）——校验: 与事件流原文模糊匹配 | M3 |
| 9 | 玩家画像（R5）落点 | ✅ 已拍板: subject=player 的 experience 节点集合（与角色线同构）; **强调规则见 §4.4** | M5 后 |
| 10 | 校验 lane 的冲突处理 | ⏸ 暂定（记录 + 高频统计 → 提示作者, 不自动改） | M5 |
