# EXPERIMENT_CONTRACT_SHAPE — L2 写入契约的两种形状（A/B，2026-10-14）

> **问题**: "看法可改"这件事，契约写成 **甲**（单数组 + `id` 在场/不在场决定改/造）
> 还是 **乙**（`new` / `cur` 两个容器）？
> **做法**: 离线重放，**只调 `cognize` 那一轮**，自变量只有 system 里那段契约。
> **结论**: ⭐ **打平 ⇒ 选甲**（改动最小 · 与 `settle` 现形同构 · 不推翻既有裁决）。
> **产物**: `.testtmp/ab_contract_shape.py`（台子）· `.testtmp/ab/contract_{jia,yi}.txt`（两版全文）
> · `.testtmp/ab/out/*`（36 份原始输出）· `.testtmp/ab/result.tsv`（记分表）。

---

## 0. 结论先行

| | 甲（单数组 + `id`） | 乙（`new` / `cur`） |
|---|---|---|
| **形状一次过** | **18/18** | **18/18** |
| 丢行 / 整包拒 / 判别键误用 | 0 / 0 / 0 | 0 / 0 / 0 |
| 真覆写正文（带 id + 写 text） | 1 | 1 |
| 只挂证据（带 id、text 留空） | 11 | 18 |
| 新造看法 | 18 | 18 |
| 新造那条 vs 已有看法的最大 2-gram Jaccard | ≤ 0.06 | ≤ 0.09 |

⭐ **两条比形状更值钱的读数**：

1. **"覆写正文"两条路两边都几乎没走**（各 1 次，35/36 次是"只挂证据 + 造新的"）——
   原因不是契约不允许，而是**这 6 个真实片段里几乎不存在"同一结论 + 补细节"的情形**
   （她每次带来的都是**新角度**）⇒ 决定成败的是"撞上"那一格的**判据质量**，不是容器形状。
2. **没有出现"同一个结论写第二条"**（词面重合 ≤ 0.09）—— 原先担心"乙会把正文改动
   推到 `new` 从而造重复"，**数据不支持**。

⚠️ **局限（读结论前先读这一段）**：

- 样本 **M=6 × K=3** 太小 ⇒ "乙用改的次数多"（11/18 vs 16/18）**不当判据**（p≈0.11）；
- **覆写判据本身没被测到**（触发太少）—— 要测它得**人工构造"同一结论 + 新细节"的样本**
  （真机历史里几乎没有）；台子是现成的，加样本即可复用；
- 只测了一个模型（`deepseek-flash` · digest 档 `thinking=high` · `temperature=0.3`）;
- 料里的【跟这条撞上的现有看法】是**手搓草案**（那时代码还没写）—— 两臂逐字相同
  ⇒ 比较仍成立，但它不是生产渲染。

---

## 1. 自变量与钉死的量

| 项 | 值 |
|---|---|
| **自变量** | system 里 `{{digest_schema}}` 那一段（**只有它**两臂不同） |
| 料 | 真机 haruka 真档（**只读**加载）现渲染的同一份文本，两臂逐字共用（`material_<样本>.txt`） |
| 模型 / 参数 | `LLMClient()`（root `settings.toml` + `.env`）· `temperature=0.3` · `max_tokens`/`extra_body` = `llm.task_levels` 的 **digest 档**（= 生产值） |
| 图起点 | **每臂各自**从同一份真档重新加载（谁也不会跑在被谁写过的图上）· 全程 ⛔ 不 `save` |
| 样本 | `m0022`（3 条同类 + 3 条撞上）· `m0004` · `m0016` · `m0023` · `m0014`（无同类）· `m0006`（最小） |
| 规模 | 6 样本 × 3 次 × 2 臂 = **36 次真调用** |

**预注册判据**（写在跑之前，免得看完数据再找理由）：先比 ①形状合法率，再比 ②误用形态；
**打平选甲**。

⭐ **记分口径的一个坑（值得记）**：shipped 的 `parse_cognitions` **按设计会丢掉所有带 `id`
的行**（"这一趟只造"）—— 拿它记分两臂都会被误判。所以记分用的是**提议语义**的校验器
（带 id ⇒ 改 · `text` 可空 · 空转行丢 · 只数新建 · 带 id 又写 `evolved_from` 丢那一格 ·
编造 id ⇒ 整包拒），六种误用先做过烟测（`.testtmp/ab_validator_smoke.py`）。

---

## 2. 结果（每次调用一行；完整表见 `.testtmp/ab/result.tsv`）

```
arm sample k 一次过 行数 改行数 耗时s
jia m0022  0   1     2    1     34.7
jia m0022  1   1     1    0     46.8
…
yi  m0006  2   1     1    0      7.7
```
36/36 全部 `一次过=1`，`drops` / `errors` 列**全空**，`notes`（结构误用）列**全空**。
⇒ **两版契约在形状上都没有把她难住**。

**id 形式**（我额外查的一项，因为 AgentGal 专门为 `u1`/`u0001` 做了前缀容错）：
36 次输出里 62 处 `"id"` **全部是 4 位**（`u0001`×40 · `u0003`×14 · `u0002`×4 · `u0004`×4），
**零个短号** ⇒ 在这套料上她**照抄了看到的写法**。⚠️ 只说明"照抄"，不等于"永远照抄"
（⇒ 落地时仍加了容错，见 §4）。

---

## 3. 外部对照：别人的 digest 契约长什么样

> 这一段是同期做的资料调研（AgentGal 用**本机源码** `D:\MYCODE\github\AgentGal`；其余六家走公开源码/论文）。

| 系统 | 操作词汇 | 输出形状 | "改哪一条"怎么指 | 删除/失效 |
|---|---|---|---|---|
| **Mem0**（旧 `DEFAULT_UPDATE_MEMORY_PROMPT`） | `ADD`/`UPDATE`/`DELETE`/`NONE` | 单数组, **每行一个 `"event"`** | 回传输入里的原 id | 契约上真删; 实现=向量库真删 + history 表 `is_deleted=1` 墓碑 |
| **Mem0**（main 现役 V3） | **只有 `ADD`**（"Your sole operation is ADD"） | 单数组, **无动作字段** | 不指; 引擎 hash 去重 + `linked_memory_ids` 挂链 | 无删除 |
| **A-MEM**（arXiv 2502.12110） | `should_evolve` + `actions:["strengthen","update_neighbor"]` | 两次独立调用、两套 schema | 邻居用 **`memory index:{i}`** 局部序号 | 契约里无删除 |
| **AgentGal** ⭐ | `add` / `update` | **一个数组 + 一个以 id 为键的对象**: `{"add":[…],"update":{"u1":{…}}}` | 现有认知渲染成局部号 `[u1]`, `update` 的**键**就是它; 未知 id **跳过** | 契约里**无 delete**; `Understanding.history` 每次正文变化追加快照 |
| **Zep / Graphiti** | 无动作词（语义由字段承担） | 两个 **idx 数组**（`duplicate_facts` / `contradicted_facts`） | idx 整数（两段输入连续编号） | ⭐ **标记失效, 从不删**: `invalid_at` + `expired_at` |
| **LangMem** | `create`/`update`/`delete`（工具参数） | **tool_call**（不是 JSON 数组） | ⭐ **id 在场=改 / 不在场=造**（引擎从元数据反推）；工具边界**硬校验** | 真删（`adelete`, 无墓碑；`enable_deletes` 默认 **False**） |
| **Letta / MemGPT** | `create`/`str_replace`/`insert`/`delete`/`rename`（工具名即动作） | tool_call | 块 `label` + **逐字文本匹配**（0 处报错、>1 处列出冲突行） | 文本级删除 / 整块删; 工具层无历史 |

**三个直答**：

- **A. 有没有人用"id 在场=改 / 不在场=造"？** **只有 LangMem 一家**是真隐式的
  （`"updated" if rmeta.get("json_doc_id") else …"inserted"`），且它在工具边界硬校验
  （create 带 id 报错 / update 不带 id 报错）。其余全是**显式动作**; Mem0 现役 V3 干脆**只剩 ADD**。
- **B. 有没有人用"两个数组"？** **AgentGal 最接近但不是**（= 数组 + **以 id 为键的对象**）;
  Graphiti 是真两个数组但元素是 **idx**; 字面 `{"new":[],"existing":[]}` **六家都没有**。
- **C. 撤回一条已落地的边, 删还是标记？** 分界线很干净：**边/图 = 标记失效（从不删）**;
  **行/条目 = 真删**（Mem0 留墓碑、LangMem 硬删且默认关）。A-MEM / AgentGal / Letta 的契约里
  根本没有撤回。

**出处**: [mem0/configs/prompts.py](https://github.com/mem0ai/mem0/blob/main/mem0/configs/prompts.py) ·
[A-MEM arXiv:2502.12110](https://arxiv.org/abs/2502.12110) ·
[AgentGal](https://github.com/huccihuang/AgentGal)（本机源码: `prompts/consolidation_prompts.py`
的 `UNDERSTANDING_PATCH` · `app/llm_schema.py` 的 `LLMUnderstandingPatch` ·
`app/consolidation/flow.py` 的 `_apply_understanding_patch`）·
[Graphiti](https://github.com/getzep/graphiti)（`graphiti_core/prompts/dedupe_edges.py` ·
`utils/maintenance/edge_operations.py`）·
[LangMem](https://github.com/langchain-ai/langmem)（`knowledge/tools.py` · `knowledge/extraction.py`）·
[Letta](https://github.com/letta-ai/letta)（`letta/functions/function_sets/base.py`）。

---

## 4. 对落地的直接影响

1. **契约选甲**（单数组 + `id`）—— 与 `settle` 同形，这就是"两套形状"那条裁决的延续。
2. ⭐ **吸收 AgentGal 的 id 容错**, 但**不能照抄它的实现**: 它做的是**纯前缀**
   （真号 `abc123`、她写 `abc`）—— 而我们的号是**零填充**（`"u0002".startswith("u2")` 是**假**）。
   ⇒ 落地补的是 **数字等价**（`u2` ≡ `u0002`）+ 唯一前缀两条, 且**只在唯一命中时救**,
   救到了记一行 warning（⛔ 契约里不教她偷懒）。
3. ⛔ **不抄 AgentGal 的"必须至少输出一条"**：它需要那句是因为**它的证据靠那次 update
   自动挂载**（引擎机械注入 `linked_episodes`）; 我们的证据是 **L1 显式写 `supports`**
   ⇒ 允许空输出是自洽的。两句规矩各自服务各自的架构。
4. **撤回不做**（用户裁"只为删边没必要"）—— ⚠️ 诚实记一句：业界对**边**的撤回也是
   **标记失效**（Graphiti `invalid_at`/`expired_at`, 从不 delete），不是删除;
   我们缺的正是这一层 ⇒ **已知缺口**: 判错的 `akin` 会继续被 `_join_akin` 当立足点。
   将来若要做, 正确形状是"**给边补一个结束时间**", ⛔ 不是 `remove_edge`。

---

## 5. 复现

```powershell
# 料 + 两版契约（零 API）
python .testtmp/ab_step0.py          # 真档只读 + 现网契约原文 + 候选样本
python .testtmp/ab_dry.py            # 两版契约与六个样本的料都渲染一遍
python .testtmp/ab_validator_smoke.py # 记分校验器（六种误用）
# 真调用（36 次 · digest 档）
python .testtmp/ab_contract_shape.py
# 内容侧读数（覆写 / 只挂证据 / 新造 + 与新造那条的重复度）
python .testtmp/ab_id_stats.py
```
⚠️ 真机数据**只读**：全程 `WikiStoreV2(path=…)` 加载, ⛔ 不 `save`。
