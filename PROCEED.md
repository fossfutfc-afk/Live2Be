# PROCEED.md — **接续用**（整篇覆盖写；上一版见 git 历史 `28f07b6`）

> 这一段会话（2026-10-08）干完一条线：**召回 `like` 从零到接上 P19**（6 笔提交，§3），
> 并把 **embed 从实时注入里停掉**（用户裁）。
> ⭐ **现在停在这里**：下一步是**把两条线接上** —— ① MMT 主动查询 `look` ② digest 的候选换新件。
> §1.1/§1.2 是这两条线的**施工表**（差距已摸清，可直接开工）。

---

## 1. 下一步该怎么做

### 1.1 ⭐⭐ 主攻：把 `look`（MMT 主动查询）接上 —— 四笔，按序

`look` 的**规格已存在**（`docs/DESIGN_MMT_NEW_ACTION.md`；§7 裁决：与 `mmt_inspect_character`
**合并**、`chapters`/`note` 折进去、一轮预算 2、`type="tool"`）；**解析半边已落地**
（`address.find_episode` / `entities.find_entity`）。差的是执行链。

| 笔 | 内容 | 关键点 |
|---|---|---|
| **①** | `pack.render_candidates` —— 把 `render._memory_line` 搬进 `core/brain/read/pack.py`；P19 的 `_recall_note` 改用它（现在经 `render_recall_block` 转一手） | ⚠️ render 是最敏感的一层（`test_marks_guard` 钉着"代码字面量零手写 `《》〔〕｜`"、**她的视图永不印编号**）；搬完让 `render.render_recall_block` 留成薄适配器 ⇒ 旧调用点零改动 |
| **②** | `core/brain/read/find.py` —— **定向寻找原语** | 锚 → **全部**符合的（⛔ 不 top-k、⛔ 不需要后端）；五类锚（名字 / 对象 / 类 / 时间 / 轴 / 关系）；**两种"空"**（"没这条" ≠ "没记过"）；返回 `pack.Candidate`（分只作展示顺序）。⚠️ 半个已经落地，别重写：`address.find_episode`（标题→episode）· `entities.find_entity`（名字/别名→对象）· `graph.lane`（按对象取**全部**，方向是"节点 → entity"）· `age_days`（时间过滤）⇒ `find` 是**调度**，不是新检索引擎 |
| **③** | `look` 四件套：parse（`core/mmt/mmt_actions.py` 注册 + `payload_schema` 文案）· 校验（`mmt_check.py` 的 `WHOLE_TURN_ACTIONS` 加 `look` + 预算）· 执行器（`mmt_executor._execute_look`，照 `_execute_mmt_inspect_character` 的样板：静默轮 + 结果回灌）· 规则书一句（"**回忆是动作，不是习惯**"） | `when` 只留 `back` 前缀；`scope` 归一；`RECALL_MAX_PER_TURN = 2`；落 `type="tool"` 事件 + 台账 |
| **④** | digest 一处接线 | 见 §1.2 |

⚠️ **顺序上的坑**：`look` 与 **cap + 标题清单是三件套**（现在常驻注入是**全量**：真档 5204 字 /
30 行）。三件套可以晚一步，但 **`look` 返回的标题必须与"标题清单"是同一个地址**
⇒ 第①笔就把两边统一到同一套 marks 渲染。

### 1.2 digest 接口 —— 一处接线 + 一个待拍的决定

| # | 件 | 现状 | 缺什么 |
|---|---|---|---|
| 1 | **候选碰撞换 `like`** | 唯一生产调用点 = `core/digest/material.py:800`（在 `_round_b_material` 里，被 `rounds/relate.py:75` 用） | 换成 `like(store, RecallCtx(now=…, query=…, embed_fn=embed_fn), spec="digest")`；`c.id in local_of` 过滤改 `c.node.id`；写路径台账 `recall_write … mode=` → `spec=digest` + `skip=` |
| 2 | ⚠️ **`SPECS["digest"]` 的 `kinds` 写错了**（**待用户拍**） | 我写的是 `("episode","belief","experience")` | 旧件候选池是 **`("belief","profile")`**，设计原话"**稳定认知**才参与组织，episode 是流水" ⇒ 要么改成 `("belief","profile")`，要么拆两个档（R2 与 L2 若问法不同） |
| 3 | `part_axis`（topics 相交） | ⭐ 已有先例：`material._episode_candidates` 用**纯集合运算**做同一件事（零后端、P2 落地） | `like` 里加一条 `part_axis` ⇒ 两处候选一个口径；料只 **3/21**（`topics` 是 P0 才加的字段，老段落已裁"不补"）⇒ 可押后 |

⭐ **digest 那边已经有一条"零后端结构化召回"的成功样本**（`_episode_candidates`）——
所以 digest 的语义那一路是**只剩一处**的历史遗留。

### 1.3 押后的（用户明确"以后再说"）

| 事 | 现成结论 |
|---|---|
| **BFS 扩散对照台**（用户提的法子：正则/字面命中 → **sig 最高者当种子** → **BFS** → 注入事件集） | 我的 `part_struct` = **多命中都是种子 + 只走两条窄门的一跳**；他的版本更激进（单一种子 + 多跳全边型）⇒ **必须先量**：真档「老师」车道 **10/21 = 48%**，`docs/REASONING_LOG.md:179` 早记过"世界一长会退化到 **100%**"；我这边"放开两跳"的变异当初就是红的 |
| **specificity 加权**（HippoRAG 的 `1/|Pᵢ|`，零后端、有先例） | 治「老师」那道天花板：老师 0.10 / 杂草屋 0.33 ⇒ 同样命中，杂草屋重 3.3 倍 |
| **离线 synonymy 边**（写入期算一次、在线只走图） | Zep/HippoRAG 的正解；能把"模糊相似"从"每轮 embed 全库"变成零 TTFT |
| **`noticed` 更出彩**：带一句"当下的想法" ⇒ 下一段 digest 长成节点 + 边 | 现在是 `{title, hit}` 只记账（非内容事件）。用户说的"把两件事联系并产生当下心理想法进图"**已经有一条路**：她说的话 → 下一段 digest → L2 造 belief + R2 判边 |
| **cap + 标题清单** | 与 `look` 一套三件 |
| `part_axis` / `emotion` / `place` / `mood`（好感同频） | 都缺 **query 侧输入**或料（`emo_shape` 8/21 且分层 +0.020 ≈ 噪声；`place` 8/21 是硬信号；好感极性连标量都没有，且真档 delta 全正） |

---

## 2. 必读文件（路径 + 为什么）

| 文件 | 为什么必须读 |
|---|---|
| `core/brain/read/like.py` | ⭐ **本轮主角**。**三张表 + 一个契约**：`PARTS`（注册表：函数 / `axis` / `scale` / `needs` / `seeds` / `material`）· `SPECS`（档位：`kinds` + 哪几路 + 权重）· `RecallCtx`（输入契约；`sim`/`degraded` 是派生字段）。合成 = **三趟**（原始分 → 按 scale 归一 → 准入 + 加权平均）。改召回先读它 |
| `core/brain/read/pack.py` | `Candidate`（node/score/**why**）+ `ledger_line`（`spec=`/`skip=`/`w=` 三格）。**`why` 由打分函数顺手写下，绝不事后重算** |
| `tests/core/test_read_like.py` | 33 条守门：三张表的形状 / 权重 0 的语义 / 缺输入记账 / 窄门 / 池内归一 + 名次门槛 / GATE / import 黑名单。**改 `like` 必跑** |
| `.testtmp/verify_like_red.py` | **22 支变异**（把一处行为退回旧态 ⇒ 对应守门必须红）。⚠️ 锚点会随代码漂：输出里"跳过（锚点 0 次）"= **没验到**，不是通过 |
| `core/mmt/engine.py::_recall_note` | P19 的接线点（`like(spec="turn")` + `render_recall_block`）；台账 `mmt_recall … spec=turn titles=` |
| `docs/DESIGN_MMT_NEW_ACTION.md` | ⭐ **`look` 的完整规格**（§2 `when` 只留 `back`；§3 三级解析 / 权限 / 返回形状 / **空结果的两种说法**；§7 裁决） |
| `core/brain/address.py` · `core/brain/entities.py` | `look` 的解析半边：`normalize_title` / `find_episode`（按标题找）· `find_entity`（名字+别名，**绝不猜**）· `hit_set` |
| `core/digest/rounds/__init__.py`（`ROUNDS` 表） | digest 的**唯一真源表**（轮次 / 步序 / LLM 身份 / prompt / 相位 / parse / 料 / 写什么 / 跳过 / 预算 / 快照）—— 改 digest 先读它 |
| `core/digest/material.py`（`_round_b_material` 750+ / `_episode_candidates` 448+） | 两处候选的现状：前者走旧件 `recommend_candidates`（**要换的那一处**），后者是 topics 相交（**零后端先例**） |
| `docs/TRAPS.md` §38 | embed 服务的坑（模型 id 必须钉死 `text-embedding-qwen3-embedding-0.6b`）；⭐ **用户裁"保持服务开着"** —— 那条是给 **digest** 的 |
| `docs/DESIGN_ENTITY_TAGS.md` · `docs/DESIGN_DIGEST_TWO_PASSES.md` | entity 线（E1–E4 已落地）· 两趟规格（L1 契约） |
| `.testtmp/probe_like_r0.py` · `.testtmp/probe_recall_cost.py` | 这一段写的**只读探针**（真档五查询并排 / 召回开销）。`.testtmp/` 全是 scratch，可删 |

---

## 3. 已做的更改（这一段 6 笔，全部已验证）

| 提交 | 一句话 |
|---|---|
| `3f6cf2d` | **like 第一笔** `pack.py` + `like.py`（字面 / 时间 / 先验；加权平均 + **准入只认内容轴** + **名字只加成**） |
| `428a2d2` | **like 第二笔** `part_struct` 结构一跳（**窄门准入**：`akin` 1.0 / 同类兄弟 0.8，⛔ `about` 不进；**种子不吃结构分**；只一跳） |
| `db1feb9` | 先验轴从 `det` **拆成 `sig` 一个参量**（时间/情绪各只算一次；实测 `pearson(sig, span·int) = 0.879`、前 8 名 8/8 重合） |
| `95023b7` | 收口成 **三张表 + 一个契约**（照 promptkit 的 `BLOCKS` + `DOMAIN_BOXES`）；`Part` 带 `axis/scale/needs/seeds/material`；`GATE` 语义位留着但**配了权重就当场炸** |
| `905d840` | **like 第三笔** 语义轴（`COSINE` **池内 min-max** + **名次门槛** `[recall].sim_k`）—— 补平"旧件有语义、新件没有"那处倒退 |
| `07253b7` | **第四笔** P19 接 `like(spec="turn")`，并把 **embed 从实时注入里停掉**（`semantic` 权重 **0**，**留行写 0** ⇒ 台账印 `skip=semantic(权重0)`） |

**验证口径**：`tests/core` **1162 passed** · 变异 **22/22 全红** · 真档只读探针（五查询并排 / 开销）

**关键实测（`.testtmp/probe_*.py` 可复现）**

```
召回开销（haruka 21 条 episode）: 旧件每轮 737ms · like 带语义 916ms · like 无后端 2ms
  embedding 斜率 26ms/条 **线性** ⇒ 21 条 0.6s / 105 条 2.8s / 420 条 11.2s；冷启动另加 2.2s
真档字段: ts 21/21 · tags 21/21 · title 21/21 · **topics 只 3/21** · emo 21/21
车道规模: 遥香 4/21 · **老师 10/21（48%）** · 杂草屋 3/21 · 夏莱 2/21
五查询（新件无后端 vs 旧件）: 苔藓 3 条 vs 1 条 · 本段新经历 2 条 vs 空 · 寒暄 1 条 vs 空 · 对象名 0 条 vs 空
⭐ 6 条簇（`akin` 5 条 + `member_of` 6 条指向同一簇）: 「咖啡厅甜点」→ 种子稳稳第一 + 5 条邻居
```

**文档同步**：`docs/PROMPT_INJECTION_MAP.md`（P19 行）· `docs/TODO_TWO_PASSES.md`（P19 现状行）·
`tests/fixtures/api_surface.txt`（`SPLIT_API_UPDATE=1` 刷新 + 人审）· `core/brain/read/__init__.py` 包地图

**用户这一段的裁决**（不许悄悄推翻）

1. **embed 留接口、停实时**："把 MMT embed 那一块的实时注入先暂停"；接口留着（digest / 将来 look 用）
2. **准入 = 内容轴 + 窄门结构**；名字 / 时间 / 重要**只加成**（真机「老师」10/21 会淹）
3. **一个包、两个类**：`find`（定向，要全部）vs `like`（相似，要 top-k）
4. **函数以 `part` 开头**；**加权平均**（"不费脑子"）；权重 **0 = 不在意**
5. ⛔ **不复用旧件**（`compose`/`recall`/`channels`/`channel_impl` 一个都不 import，AST 黑名单钉着）；**可搬**
6. `docs/TRAPS.md` §38：**digest 的 embedding 服务保持开着**

---

## 4. 隐形坑（这一段新踩的 + 仍然有效的）

### 4.1 ⭐ 这一段新踩的

- ⛔ **消融会被污染**：结构一跳的"种子"只能从 `Part.seeds=True` 的路出，且**只在它这次真调时**才取
  —— 否则 `lexical=0` 时结构路还偷偷吃着字面证据，那个消融是**假的**（变异逼出来的）。
- ⛔ **假绿两例**（都靠变异抓出来）：
  ① 断言只落在**原始分**上（`part_semantic` 的输出）⇒ 测不出"池内归一失效"（归一在合成层第二趟做）
     ⇒ **断言要落在最终分上**；
  ② 只断言"引擎没调后端"⇒ 抓不住"档位里把权重写回 1.00"（引擎不传后端时怎么都不调）
     ⇒ 必须**同时钉住 `SPECS["turn"].parts["semantic"] == 0.0`**。
- ⛔ **变异脚本的锚点会随代码漂**：改 `SPECS` 的行 ⇒ 以 `("lexical", 1.00), …` 为锚的变异变成
  "跳过（锚点 0 次）" —— **那是没验到，不是通过**。跑完必须看有没有"跳过"。
- ⛔ **PowerShell `-replace` 会把 `\r\n` 字面写进 Python 源码**（`__all__` 那次 SyntaxError）。
  **优先用 `edit` 工具**；用脚本改完先 `python -c "import ast; ast.parse(…)"` 自检。
- ⛔ **动 `core/mmt/engine.py` 的 import / 新增顶层函数 ⇒ 要刷 API 快照**：
  `SPLIT_API_UPDATE=1 pytest tests/core/test_split_safety.py` + **人工审 diff**（TRAPS 30）。
- ⚠️ **`mmt_recall` 是两义**：`logger.info("mmt_recall …")` 是**引擎摆给她看**的台账行；
  `DESIGN_RECALL.md` 里的 `mmt_recall` **动作**已并入 `look`（她主动查）。别混。
- ⚠️ **`m0018` 是 belief 不是 episode** —— 旧件默认 `kinds=("belief","profile")` 才命中它；
  这就是"苔藓那句旧件 1 条、新件 3 条"的原因（不是新件漏了）。
- ⚠️ **测试 `--basetemp` 要预建**：这一段用 `.testtmp/pw_like`（已存在，可复用）。
- ⚠️ **记账**：`emo_span`/`emo_int` **没有活着的读者了**（唯一读者是待删的
  `channel_impl.IntensityPrior`）；要么承认它是给将来情绪通道留的料，要么从 digest 契约里退掉。

### 4.2 仍然有效的（压缩）

- 跑测试：`python -m pytest tests/core -q --basetemp=.testtmp/pw_like`（**Windows 必须预建目录**）
- **不许频繁跑全量**（用户硬规矩）；按板块跑；改到一半的树不跑回归
- **每新增一条判据都要跑变异验红**（假绿比没测更糟）
- 改**进 system 的内容**（盒A/盒B）⇒ 刷夹具：`PROMPTKIT_UPDATE_FIXTURES=1 pytest tests/core/test_promptkit_baseline.py` + 人审 diff
  （⚠️ digest 的 prompt/契约**不在**盒里；`like` 的改动**不进** system ⇒ 都不触发）
- 契约文案改一处要**同批改示例**（示例才是形状的来源）
- `pipeline.IMPL` 的键序被守门钉住（与 `ROUNDS` 同序同集）
- 代码字面量里零手写 `《》〔〕｜`（`tests/core/test_marks_guard.py`）
- 桩不认识 `task` 就炸：新增一轮要同时补 `tests/stub_tasks.annotation_reply` + 各处自造桩
- `entities.py` 是"输入侧"不写边；`brain` 不许 import `digest`（分层）
- 写 Python 补丁脚本：`print("…"…"…")` 里嵌引号会让整个脚本 SyntaxError —— 用「」或先 `ast.parse` 自检

### 4.3 环境/本机

- LM Studio：`lms server start --port 1235`；`[embed].model` **钉死** `text-embedding-qwen3-embedding-0.6b`
  （本机装着两个 embedder，自动发现取"排前面的"，不可靠）
- 空闲后第一次请求 **~2.2s 唤醒**（之后 13~62ms）—— "TTFT 变慢"先看这个
- 删东西**只指定路径、不用通配符**；只在工作目录内部删
- 真机数据：`data/worlds/world1/characters/{igusa_haruka,asagi_mutsuki}/soul/`
  —— **这一段所有写操作都在副本/临时目录**，真 `data/` 未动
- 提交链**未推送**（ahead **24**）；推送要 `git -c http.proxy= -c https.proxy= push origin master`
  （代理 127.0.0.1:7897 已死；git config 未动）
- CJK 提交信息走 `git commit -F .testtmp/commit_*.txt`；**stage 显式路径**
