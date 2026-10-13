# PROCEED.md — 接续用（**整篇覆盖写**；上一版见 git 历史）

> **树干净 · `ahead 49`（没 push —— 推不推由用户定）**。真实头看 `git log -1`。
> 现状：`tests/core` **1260 passed** · `tests/webgui`+`tests/llm`+`tests/renderer` **196 passed**
> （⚠️ **按域分开跑**，理由见坑 4.25）· 三个 verifier 全 exit 0。
> ⚠️ **这棵树里有两条线**，别混：**线 A = 记忆层重新设计（本会话主线）** ·
> **线 B = 包重组（另一个 agent 做的 1a/1c/1d/1f，1e/1h 等他拍板）**。
> v7（`62a4dac`）时线 A 的四件全落；**本版又落了第五件 = `topics` 退役**（`080460b`，一个提交）。
> ⚠️ **编号变过**：本版 `1A-2` = ✅ `topics` 退役（已落）；`1A-3` = `aliases` 的写者 ·
> `1A-4` = belief collision 的其余两条 —— ⛔ **别拿旧编号对新文件**。

---

## 0. 三十秒概览

**线 A（本会话）**：记忆层从"写侧造容器"改成"**写侧只写地址、引擎物化、内容归 LLM**"。
- 已落：① brain 段那块 = **「我知道的名字」** ② 名字匹配 **空白不敏感**（`entities.form_key`）
  ③ 台账 `mmt_recall` 的 `per=`/`ms=` ④ 真机观察脚本 ⑤ **group（L2-a）退役**（整族搬 `archive/digest_group/`）
  ⑥ **`experience` 的沉淀行停产** ⑦ ⭐ **`attribute` → `settle`** 改名 + 扩职 + 执行接线 + **`text_seq` 水位**
  ⑧ ⭐ **引用从 `tags` 搬进独立字段 `entity`** ⑨ ⭐ **akin 共 belief**（一跳邻域并进证据 + 料侧相似簇）
  ⑩ ⭐ **`topics` 退役**（`on` 的判据随载体一起走；L1 候选**换源**走 `like(spec="digest")`）。
- **下一件**：待你挑（见 §1A-3 / §1A-4 / §5.3）—— 我倾向 **belief collision 那两条**
  （`akin` 并边已把"多条"喂厚了，正好接着收"单点要不要拦"）。
- ⚠️ **真机提醒**（这一刀探到的）：`like(spec="digest")` 的 `semantic` 权重是 1.00，
  **embedder 不在时排序会被 `tags[老师]` 这类泛词主导** ⇒ 真机跑 digest 前先确认
  `[embed]` 服务在（`lms server start`）并 grep `digest_embed` / `recall_like … skip=`。

**线 B（另一 agent）**：把"缝补出来的项目"改成正常 Python 项目的形状。已做 1a/1c/1d/1f；
**1e（`contract/schema.py` 外移）与 1h（调用层归位）等他拍板**（岔路见 §1B）。
目标形状（已定）：`contract/`（零项目内依赖）· **新建 `infra/`**（paths/errors/atomic/fuse/时间）·
`llm/` · `engine/`（← 现 `core/`）· `tui/`（← 现 `renderer/`+`core/tui/`）· `cli/`（← `apps/`）·
`docs/{design,spec,archive}/`。

---

## 1. 下一步该怎么做

### 1A-1 ✅ **akin 共 belief —— 已落**（`6cf1151` 写侧 + `794add5` 料侧）

落定的形式记在这儿（**改它之前先读这段**）：

- **写侧**（`revise._join_akin`）：她给的 `supports` 落完之后，把**每条证据的一跳 `akin` 邻居**
  并进 `supports`；额度 `AKIN_JOIN_MAX = 5`；台账 `digest_cognize … akin=N` + 每条看法一行
  `akin_joined=N belief=… evidence=…`。
- **四条纪律**：① 起点**只有她写的那几条**（⛔ 不拿上一趟并进来的当起点 ⇒ 重跑不滚雪球）
  ② **先落 `supports` 再算邻居**，而**排除集要在落 `contradicts` 之前算**（那两条边在循环里
  落得比它晚 —— "跟这条看法打架的不算证据"这条规则不能等它们落完）③ **打架的不共撑一个结论**
  （跟看法打架的 / 跟她点的证据打架的 / 两条候选互相打架的 —— 一条规则全管住）④ 额度超了就
  少并几条（⛔ 不报错、不重试）。
- **料侧**（`material._akin_block`）：【被连过的经历】每条下面一行 `↳ 她认过跟它像的` ——
  **A 案 = 挂在经历下面**（用户裁的，⛔ 不是独立的一格）；每条 anchor 最多印
  `DIGEST_L2_AKIN = 3` 条 + **明说还有几条没印**；**本段的邻居只出信息头**（正文归它自己那一行）；
  与 anchor 打架的邻居**不摆**。⏸ `轴 …` 那一格**2026-10-14 随 `topics` 撤了**（见 §1A-2）。
- ⭐ **老经历回到 `evidence_ids`**（料里印出来的都算引用面）—— 不认它，她就引不了自己早先
  认过的同类，而引擎偏偏会把它们并进证据 ⇒ 两边对不上。
- ⚠️ **已知副作用**（用户裁"接受"）：并进来的边与她亲手点的**在图里同形**，事后只有
  `evolution.jsonl` 里那一条多带的 `"via": "akin"` 分得出；她的「被引 N」会变大（只影响读数）。
- **删掉的机器**（用户裁"删掉"）：`DIGEST_L2_GROUPS` / `DIGEST_L2_MEMBERS` / `_groups_for_l2` /
  `_group_block` / `_members_by_precious` —— 它们由 `member_of` 喂，而那条边**已无写者**；
  ⛔ **读侧的"同类兄弟"没动**（`find.py` 的类成员 / `walk.py` 的窄门 —— 旧档还走得到）。
- **文案分工**（这一刀立的规矩）：`llm/prompts/digest_cognize.md` 提一句（它们也算证据 ⇒
  该写"总是 / 每次"就别只写"这一次"）；**契约（`contract/digest/prompts/`）不提** ——
  引擎行为**不是她要遵守的形状**。

### 1A-2 ✅ **`topics` 退役 —— 已落**（`080460b`，一个提交）

> ⚠️ **为什么是一个提交而不是两个**：这一刀跨"契约/解析"与"料"两层，而两层互相咬合
> （契约不再要 `topics` ⇒ 料里的 `轴` 无来源；料的候选换了源 ⇒ 判据跟着换）——
> **改一半树是红的**。⇒ 判据：**同一件事的两半如果不能各自站住，就写成一个提交**。

**落定的形式**：

- **`on` 随载体一起退役**（用户裁 A2）：契约里的 `"on": "苔藓"` 与"必须是两端 `topics`
  交集里的词"那句都删了；`parse_relations` 不再收 `on`、不再要 `topics_of`
  （她惯性还写着 ⇒ **静默忽略**，同 `about_hint`/`items` 的先例：⛔ 不丢行、不告警）；
  `apply_relations` 的变更史也不再写 `on` 格。
- **`topics` 字段只停产、不删格式**（用户裁 B1）：`BrainNode.topics` 与 `to_dict`/`from_dict`
  留着（老档那几格还读得回来），注释写明**零写者**；`parse._clean_episode_item` 的清洗块删掉、
  `tables.TOPICS_MAX` 删、`ROUNDS.writes` 摘掉那一格。
- **料（用户裁 C1：`轴` 那一格全消失）**：`_axes_field` / `_likeness_axis` 与三处 `轴 …`
  （L1 新经历行 / 候选行 / 相似簇行）全撤。⛔ **没拿 `tags` 顶替**（真机实测那些词大半是
  泛词 —— "约定 / 笔记"让一条经历跟 **9 条**相连 ⇒ 零区分力）。
- ⭐ **L1 的候选换源**（`material._episode_candidates`）：老的判据是"两端 `topics` 有交集"，
  今天走 **`like(spec="digest")`**（读路径那条**写好了却零调用**的档位）：
  query = 本段每条经历自己的正文（多条**取并集按分降序去重**）；
  每行印 `候选 0.46` + 一行 `→ 为什么: 覆盖 1.00 · 6 天前 · 重要 0.85`（`like` 的 `why` 原样）。
  ⚠️ **多要 `len(mine)` 个名额** —— 召回池里有本段自己那几条（见坑 4.31）。
- **L1 的观测账换一格**：`pool=`（库里标了轴的条数 —— 真机上恒 3/21，解释不了任何事）
  → **`sim=<1|0>`**（语义那一路在不在 = "cands=0 是真没有还是没起来"）。

### 1A-3 `aliases` 的写者（**记着, 还没做**）

今天 `aliases` 只在**建对象时**写一次；`settle` 改名时会自动把**旧主名**降级成别名（已落）。
⛔ **仍冻结**的是"她主动补一个**新**别名"（`{"id": …, "aliases": [...]}`）—— 并错**不可逆**
（重复建对象还能合并，身份并错分不开）。要做先想清判据。

### 1A-4 belief collision 的其余两条（待拍；⭐ 我建议下一件做这个）

① belief **默认综合 ≥2 条**（相似或矛盾都行）；单点要过门槛 —— ⭐ 判据 = **"写得出一句『所以』"**
   （`DESIGN_MEMORY_MODES.md:58`：簇的代表性总结是**描述**，不该住 belief）
② **软强制 + 允许一次显式 defer**（defer 记账）—— 完全强制会造垃圾 belief。
   ⭐ 与 §1A-1 的关系：`akin` 并边**已经把"多条"喂厚了**（她点 1 条 ⇒ 图上可能 4 条），
   所以这两条今天更多是"**要不要拦单点**"的问题，不是"她写不写得出来"的问题。
⛔ **已撤回的一条**（别捡回来）：~~`relate` 的 `akin` 行退役~~ —— group 死后 `akin` 是**唯一**
还活着的"同类"判断源（`noticed` 太稀，真机全库 5 条）⇒ 退役它 = 把 §1A-1 的继承者腿砍了。

### 1B 线 B 那两条（另一 agent 的；**别替他拍**）

- **1h 调用层归位**（用户提出）：`core/digest/llm_call.py`（85 行、零 digest 依赖）**位置错了** ⇒
  搬 `llm/`（岔路：`llm/client.py` = 用户说的 **vs** 新开 `llm/robust.py` = 那份建议，因为它是
  **策略件**不是协议件）；`core/digest/call.py`（164 行）**位置对、名字错** ⇒ 只改名 `round_call.py`。
  ⭐ 同一片区域还有个更值钱的发现：`call.py::_round_call` 的"调用→parse→回灌重试"是
  **`llm/retry.py::call_with_feedback` 的第三份实现**（那份 docstring 自己就把 digest 列在待收口里）。
- **1e `contract/schema.py` 外移**：待拍 ① 归属（新 `contract/schema/` 包 **vs** 并进 `contract/records/`；
  倾向后者）② 硬规则清单承载形式（md 手写编号 / md 列表回解析 / 只搬外壳）。
  ⭐ 顺带：`build_schema` + `export_definitions` + `_SHELL_FIELD_DESCRIPTIONS` ≈ **61 行生产死代码**
  （AST 核实），**先问他砍不砍**。判据已备：`.testtmp/capture_1e.py check`（基线 `schemas_1e_before.json`）。
- 批次 2（`core → infra/engine`、`renderer+tui → tui/`、`apps → cli/`）：**要他在场**。

### ⏸ 已划去 / 已裁"不做"（别自己捡起来）

- **删 `examples` 字段**（用户 2026-10-13：*"算了…可以看作扩展, 延后, 划去"*）—— 现状有读者、
  有守卫、零活写者，当扩展位留着。
- **`profile` 真删格式**：1c 只做了"停产"（B 案），真删等确认没有老档依赖。
- ⛔ **`ambiguous` 不加机制**（用户 2026-10-13）: 真机实测**零实例**（4 个 entity 两两不撞，
  而"社长/室长/课长/普通职员"这类头衔**都不在匹配面上**）⇒ 分档、单列栏、台账**一律不做**。
- ⛔ **bond 开场不补 entity 物化**（用户裁"不用了"）: 出厂物化只有 MMT 开会话那一个入口
  （`_engine._ensure_char_entities`）—— 理论缺口（只走剧情的新档名表会是空的）**记着, 不动**。

---

## 2. 必读文件

| 文件 | 为什么 |
|---|---|
| 本文件 | —— |
| **`core/digest/rounds/__init__.py`** | ⭐ **轮次真源 `ROUNDS`**（key/步序/相位/parse/**料**/**写什么**/预算/快照一处说全；`material` 是硬契约，`_sections_for` 逐字对账） |
| **`core/digest/rounds/settle.py`** + `contract/digest/prompts/settle.md` + `llm/prompts/digest_settle.md` | ⭐ **最新那一轮的完整形状**（`id` 决定"建/改"· 空=不改 · 名字 ≤8 · 看法 ≤60 软尺 · 改名要有依据）—— 也是"文案与形状怎么分工"的范本 |
| **`core/digest/material.py`** | ⭐ L1 的候选（`_episode_candidates`：`like(spec="digest")` + 分 + 为什么）· L2 的料（`_l2_material` / `_akin_block`）· settle 的对象块 |
| **`core/digest/rounds/relate.py`** | ⭐ L1 全貌：料（候选 + 认知表）· 三个 id 空间 · 观测账 `digest_relate … cands= sim=` |
| **`core/brain/graph.py`** | ⭐ 边词汇表（6 条 · `SYMMETRIC_RELS` · `canonical_for`）+ **`related` / `conflicting`**（对称 rel 的**唯一**实现处）；`store` 上有同名薄封装 |
| **`core/brain/revise.py`** | ⭐ 三个执行器（`apply_relations` / `apply_cognitions` **+ `_join_akin`** / `apply_entities` + **`apply_stances`**）+ `link_entity_refs`（落边唯一实现） |
| **`core/brain/nodes.py`** | ⭐ 节点字段真源（`entity` 引用 / `text_seq` 水位 / **`topics` 已停产但留着** / `kind` 五种的必填表 / `from_dict` 的老档兼容） |
| **`core/brain/read/like.py`** | ⭐ 六路打分 + 档位表 `SPECS`（**`digest` 那一档现在有调用方了**）+ `RecallCtx` 的输入契约 |
| `contract/digest/`（`tables.py`/`docs.py`/`parse.py`/`registry.py`/`prompts/`） | ⭐ 契约五模块（值表/清单/校验/渲染/文案）—— `parse_relations` 的两档校验（丢行 vs 整包拒）就在 `parse.py` |
| `docs/DESIGN_MEMORY_MODES.md` | ⭐ 四种模式（抽象/佐证/经验/进化）+ **`akin` 原料 → 门槛(n) → belief 产出** + "簇总结不是决定" |
| `archive/digest_group/README.md` | ⭐ group 退役的**是什么/为什么/怎么复活**；点了名哪些读侧机器件**别删** |
| `.testtmp/verify_1c.py` · `capture_prompts_1d.py` · `capture_1e.py` | ⭐ 动契约/文案的三份**逐字节判据**（各自 `check`；`EXPECTED_CHANGED` / `CHANGED` 要写"为什么"） |
| `.testtmp/probe_akin_block.py` · `probe_topics_vs_like.py` · `probe_candidates_after_topics.py` | ⭐ 真机（haruka）的**只读**探针：相似簇的渲染 · `topics` 路 vs `like` 路 · 新候选料长什么样 |
| `tests/core/test_digest_rounds.py` · `test_digest_contract_refs.py` · `test_round_relate.py` · `test_wiki_revise.py` | 轮次表守门 · `【X】` 必须有出处 · L1 的观测账与候选 · **`akin` 并边的六条** |
| `CLAUDE.md` | ⚠️ 89 KB 且多处过时（`topics` 那一行现在已经作废）；当索引读，冲突时**信代码** |

---

## 3. 已做的更改

**线 B（另一 agent，`dbac250` 之后 4 项）**：

| # | 提交 | 做了什么 |
|---|---|---|
| 1a | `920f814` | 清残党第二刀：删 v1 万能修订包执行器 + store 4 个旧 shim + 14 条测试（-659/+67） |
| 1c | `8e57359` | ⭐ **`profile` 节点停产**（契约不要 + parse 丢行不报错 + `writes` 摘掉；机器留着） |
| 1d | `67a8dee` | ⭐ **槽语法统一**：9 份 md / 43 处 `{x}` → `{{x}}`；7 处调用方走 `contract.slots.render_template`（漏填/多填当场炸）；炸出 2 处一直空转的 `.replace` |
| 1f | `8e7fb00` | ⭐ 新守门 `test_digest_contract_refs.py`：每个 `【X】` 说得出出处；第一次跑抓到 3 处真东西 |

**线 A（本会话，都在 master；越往下越新）**：

| 提交 | 做了什么 |
|---|---|
| `4d978eb` | ⭐ **entity 常驻化**：brain 段那块 = **「我知道的名字」** + `entities.form_key` 铺三处 + 台账桶 → `known` |
| `5a5973e` · `593d1a1` · `3ad6e71` | 台账 `per=`/`ms=` · 真机观察脚本 `experiments/recall_report.py` · 两条新守门 + 变异靶 |
| `c7a4ac7` · `d32c8f3` | `form_key` 推广到 `hit_set` 正文扫描 · 作者缩短出厂立场句（名表 1116 → 938 字） |
| **`1478121`** | ⭐ **group（L2-a 分群）退役** —— 生产停 + 整族搬 `archive/digest_group/`；硬顶 720 → 600 |
| `4adc7f7` | PROCEED 第五版（线 A 四件 + 线 B 一节 + 坑 4.1–4.20） |
| **`9cc3d07`** | ⭐ **`experience` 沉淀行停产**：`COGNIZE_ANCHORS` 只剩 `belief` + 新增 `COGNIZE_RETIRED`（认得出 ⇒ 丢行 + 记账，⛔ 不判非法）；【本段归类的群】撤出料面 |
| **`a85623a`** | ⭐ **改名 `attribute` → `settle`**（纯机械、零行为）—— ⚠️ `revise.py` 那条日志**不在命名守门的扫描面内**（它只扫 `core/digest/**`）得手工改 |
| **`fa8c906`** | settle 的**文案 + 料**: 契约扩成"认人 + 改名/写看法" · 新增 `material.settle_objects_block` |
| **`457310d`** | ⭐ **settle 接线**: `parse_attribution` 两路（`id` 决定建/改）· 新增 `apply_stances` · `nodes.text_seq` 水位 · skip 放宽 · **两条判据订正**（撤销 `allowed_names` 闭环 · 空=不改） |
| **`11682ba`** | ⭐ **引用搬进独立字段 `entity`**：老写法**认得出并挪进来** · `from_dict` 读老档时同一次搬迁 · 三个函数/常量跟着改名 |
| `74668ef` | PROCEED 第六版（线 A 四件落三件 + 坑 4.21–4.27） |
| **`6cf1151`** | ⭐ **akin 共 belief（写侧）**: `_join_akin`（一跳邻域 → `supports`，额度 5）· `graph.related`/`conflicting` · `"via": "akin"` 留痕 · 台账 `akin=` |
| **`794add5`** | ⭐ **akin 共 belief（料侧）**: `_akin_block`（`↳ 她认过跟它像的`）· 老经历回到 `evidence_ids` · **删掉五个停产件 + 三条用例** |
| `62a4dac` | PROCEED 第七版 |
| **`080460b`** | ⭐ **`topics` 退役**：`on` 的判据随载体走 · 字段只停产 · `轴` 那一格全撤 · **L1 候选换源 `like(spec="digest")`**（分 + 为什么）· 台账 `pool=` → `sim=` |

**真机读数（只读探针，⛔ 全程不 save）**：haruka —— 节点 30 · 边 58 · `episode 21 · belief 4 ·
entity 4 · experience 1`；边 `about 22 · supports 25 · member_of 6 · akin 5`；名表那块 938 字。
- `akin` **5 条全在一个 6 条的簇里**（`m0021`/`m0022`/`m0004`/`m0023`/`m0013`/`m0016`）——
  一个 anchor 的一跳邻域 **≤ 3 条** ⇒ 两个额度（印 3 / 并 5）在生产上**都截不到**；
  全图 `contradicts` = **0** ⇒ 并边那三条"排除打架的"在真机上是**防御, 不是日常**。
- 21 条经历里 **只有 3 条有 `topics`**，那 3 条**互相不共轴** ⇒ 老的候选路（`topics` 交集）
  **恒 0 条**；`tags` 则是 21/21 全有 —— 但它当轴会退化（`m0006` 与 **9 条**相连）。
- 换源后（`probe_candidates_after_topics.py`，探针里 embedder=None）：候选摆得出，
  带分与理由；`m0022` 的第三名 `m0004` 的理由正是 **`认过的相似 1.00`**（结构窄门那条 `akin`）⇒
  两条路真的接上了。⚠️ **没有 embedder 时排序被 `tags[老师]` 这类泛词主导** ⇒ 真机跑 digest
  前先确认 `[embed]` 服务在。
- 30 个节点里 0 个带老写法 `#entity:`、0 个有 `entity` 字段 ⇒ 那 22 条 `about` 边是**更早的路径**
  落的 ⇒ `from_dict` 那条迁移在真机上**无事可做**。

---

## 4. 隐形坑（踩过的，别再踩）

**4.1 `ruff check --select X --fix` 是陷阱**（`--select` 覆盖 pyproject 的 select ⇒ 把有效的
`# noqa` 批量删掉）。删 noqa 只用 `.testtmp/strip_dead_noqa.py`。**别用 `--select` 跑 fix。**
**4.2 动 F401 前先查"有没有人从这个模块 import 走"**（ruff 看不见再导出）；`tests/**` 有
F401/F811 豁免 ⇒ 测试里的未用 import 得自己 grep。
**4.3 判"死代码"必须用 AST 认 `Call`**（栽过 5 处：调用者全是注释/文档串）。工具
`.testtmp/audit_calls_1e.py`。⚠️ **同名不同物**：`digest_registry.build_schema`（方法, 活）
vs `contract.schema.build_schema`（函数, 生产零调用）。
**4.4 `.strip()` 让尾随空行不进 prompt** ⇒ "只差尾随空行"是**通过**不是差异。
**4.5 md 里没有"注释"** —— 写进去就进 prompt；**反引号也会进 prompt**。
**4.6 `prompts/*.md` 是数据文件**（打包要收进包：`contract/digest/prompts/` 与 `llm/prompts/`）。
**4.7 槽只有一种写法**：`{{名字}}` + `contract.slots.render_template`（两方向都对不上就抛）。
**4.8 跑测试必须带**：`--basetemp=.testtmp/_pytemp -o cache_dir=.testtmp/_pcache`（`%TEMP%` 权限坏）。
**4.9 解释器** `C:\Users\johnf\miniconda3\envs\live2be\python.exe`（conda base 缺 jieba）；ruff 在
`…\envs\live2be\Scripts\ruff.exe`。
**4.10 PowerShell 会吃掉 `-c` 里的嵌套引号** ⇒ 脚本一律写成 `.testtmp/*.py` 再跑；
`git commit` 一律 `-F 消息文件`。
**4.11 行尾混杂**（无 `.gitattributes`）—— ⚠️ **`write` 工具写出来的 md 是 LF**, 而全仓 prompt 是
**CRLF** ⇒ 每次重写 md 之后**拉一次 CRLF**（脚本：读文本 → `\r\n` → `write_bytes`）；否则她看到的
渲染字节与别的 prompt 不同形。按行号改文件要按字节切 `\n`。⭐ **`edit` 工具不会把行尾改混**
（本会话核过 8 个文件: 改完 CRLF/LF 计数与改前一致），`write` 与 `Set-Content` 要**改完核一次**
（`.testtmp/check_eol.py`）。
**4.12 删顶层类/函数要连 `@decorator` 一起删**（`ClassDef.lineno` 不含装饰器）。
**4.13 API 面守门**：给那 9 个模块增删模块级名字要刷 `tests/fixtures/api_surface.txt`
（`$env:SPLIT_API_UPDATE='1'`）—— 今天动过的 `contract/digest/*`、`core/digest/*` **不在那 9 个里**。
**4.14 别把 `Measure-Object -Line` 的行数当真**（比 `splitlines()` 少 ~6%）。
**4.15 `_LABELS` 是 `AnnAssign`** —— 扫"带注解的模块级常量"要一起认，否则静默取空集。
**4.16 一个名字在 md 里不等于它是"料名"**（`【】` 还当角色代称/序数小节/交叉引用）。
**4.17 ⭐ 改 `contract/digest/prompts/` 或 `llm/prompts/` 任何**一个字节** ⇒ 立刻跑三份 verifier**
（`verify_1c.py check` / `capture_prompts_1d.py check` / `capture_1e.py check`）；
**有意的改动写进 `EXPECTED_CHANGED` / `CHANGED` 并写为什么**（长期红的判据 = 没人看的判据）。
⚠️ **前一道红会盖住后一道**：`capture_prompts_1d` 的"名单变了"先 return ⇒ **内容比对根本没跑**
（`digest_relate.md` 的一处改动因此漏登记了很久）⇒ 修名单的时候要把内容也比一遍。
⚠️ **改相位名 / 归档 md** ⇒ `verify_1c` 的基线键会认不出（`build_schema` 当场抛）⇒ 进 `SKIP_PHASES`；
`capture_prompts_1d` 有 `ARCHIVED` / `RENAMED` / `CHANGED` 三档（**改名那一档仍拿旧名基线比内容**,
这样"只是改了名"是**被证明**的）。
**4.18 真机数据只读**：探针可以读真档、可以在内存里 `store.add`，⛔ **绝不 `save()`**
（验证法：`git status data` 干净 + `wiki.jsonl` 的 mtime 不变）。⚠️ 加载真档要 `WikiStoreV2(path=
…/soul/wiki.jsonl, …)` —— 第一个位置参数是 **data_root 不是 soul 目录**，传错了会静默得到 0 个节点。
**4.19 推送必须走代理**：`git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=… push`（直连被 reset）。
**4.20 `git mv` 用显式路径**（不用通配符）；归档目录里的测试**不会**被 pytest 收集，
但它的 `parents[2]` 路径算过了 —— 要跑得先改。
**4.21 ⭐ 契约里不许有"假威胁"** —— 写了"违反即被丢弃", 引擎就**必须真丢**；
反过来, **判据的载体死了, 那句判据也要跟着死**（见 §5.2"判据随载体走"）——
留一个没有判据的必填格只会教她写空话。
**4.22 ⭐ 空值语义**: `"text": ""` = **"这一格没话可说"**（⛔ 不是"清空"）。⇒ 判"这一行改了什么"
**只看键在不在, 不看值空不空**（`parse` 收下、执行层记 `empty_skips` 后什么都不做）。
**4.23 加字段要顺着四处走**: `BrainNode` 的 dataclass 字段（`store.update` 的 `_FIELDS` 是
**动态取它的**, 漏了 ⇒ patch 报"未知字段"）· `to_dict`/`from_dict` · 照条目建节点的那两处
（`episodes._create_a_nodes` 的 profile 支 / `revise._create_belief` —— **漏搬就把内容静默吃掉**）·
`ROUNDS.writes` 与 `result_fields`。
**4.24 加 `DigestResult` 字段要同时在 `ROUNDS.result_fields` 里**（守门 `test_every_result_field_is_classified`
+ 回滚清单由表推导, 漏了就是"回滚不干净"）。
**4.25 ⚠️ 四个域塞进同一个 pytest 进程会互相干扰**: 见过一次 `test_bond_scene_error_abort_no_closing`
**超时红**（那是轮询 + 墙钟超时的用例; 单跑 ✓ · 整个 `tests/webgui` ✓）⇒ **按域分开跑**
（`tests/core` 一条命令, `tests/llm tests/renderer tests/webgui` 另一条）, 别图省事合成一条。
**4.26 薄委托要跟着改签名**: 契约层是"`parse.py` 实现 + `registry.py` 薄委托", 加/删一个 kwarg
（如 `object_ids`、`topics_of`）要**两处都改** —— 漏了就是 `TypeError`, 而且只在真跑的轮上炸。
**4.27 守门"料还在、没人提"与"文案提到不存在的栏"是一对**: `test_material_names_are_not_dead`
（料名必须出现在某份 md 里）**反向**由 `test_every_bracket_in_prompts_has_a_home`（md 里的 `【X】`
必须说得出出处）看着 ⇒ **改段标题必须两边同改**（`ROUNDS.material` + md）。
**4.28 ⭐ "一份料里同一段正文只印一次"的正确实现**: 簇里对**本段**的邻居**只出信息头**
（正文归它自己那一行）。⚠️ 我第一版把"只出信息头"也算进"正文已印" ⇒ 轮到它自己那一行时走
"（正文见上）"分支 ⇒ **那一条的正文在整份料里一个字都不剩**（自审抓到）。判据: `printed`/`shown`
这类集合**只收真的印过正文的那些**; 主列表**永远印自己那一条的正文**（⛔ 不看那个集合）。
**4.29 ⭐ 对称 rel 只查一个方向必然漏一半**（`akin` / `contradicts`）: 存进去时被 `canonical_for`
归一到"id 小的当 `src`" ⇒ 漏掉的是哪一半**取决于两个 id 的字典序, 不是语义**。唯一实现 =
`graph.related(edges, nid, rel)` / `graph.conflicting(edges, a, b)`（`store` 上是薄封装），
⛔ 别在调用点手写 `edges_from` + 条件。
**4.30 删一个停产件要连带清掉"注释里提到它"的地方**: 删 `_groups_for_l2` 之后,
`contract/digest/parse.py` 与 `tables.py` 的 docstring 还在讲"`_groups_for_l2` 恒空"
（grep 死符号名才找得到 —— 编译器/测试都不会报）。做法: 删完**按名字 grep 全仓**,
把解释**改写**成"没有写者"而不是"某个已删的函数恒空"。
**4.31 ⭐ `like()` 会把"本段自己那几条"排在第一名**（query 就是它们的正文 ⇒ `覆盖 1.00` 自匹配）——
调它要**补名额**（`k=int(k) + len(mine)`）并**过滤掉 `mine` 与非目标 kind**，否则
"要 6 条"实际只摆得出 5 条（我第一版就是这么红的）。
**4.32 "退役一整行"与"退役行内一格"是两条先例**, 别混:
· **整行死了**（`profile` / `experience` 锚点）⇒ **认得出 + 丢那一行 + 记账**（B 案: ⛔ 不判非法）;
· **只是行内一格死了**（`about_hint` / `items` / `topics` / `on`）⇒ **白名单外的键静默不落库**
  （⛔ 不丢行、不告警 —— 那一行本身没毛病）。
判据 = **那一格没了以后, 这一行还成不成立**。
**4.33 大段替换之后立刻 `git diff` 核对**: 一次 `edit` 的 `old_string` 横跨十几行、报成功,
而实际结果与预期不完全对得上（我用 `git diff` 逐行核过才确认只删了该删的那些）。
做法: 改完**看增删行数对不对得上**（`git diff --stat` + 只看 `^[+-]`），别信"工具说成功"。

---

## 5. 本会话的设计与裁决（写给自己，别再问一遍）

### 5.1 已裁的（用户 2026-10-12 / 10-13 / 10-14）

**名表 / 名字匹配（更早那一批）**：⭐ 「我知道的名字」= 合并（原「我眼里的他们」+「我是这样看自己的」）·
**保留号都收** · **只写主名**（别名不上屏）· **她自己在表尾**；抬头固定（改名要同批改规则书, 有守门）·
⭐ 名字匹配**忽略空白**（`entities.form_key` = 去所有空白 + casefold, **唯一归一**）铺四处。

**2026-10-13 那一批**：
- ⭐ **`experience`（给类写沉淀）随 group 退役一起停产** —— 判据 = **B 案第三档**（① 契约不再要
  ② 她惯性还写得出 ⇒ **认得出、丢行、⛔ 不判非法**）。
- ⭐ **`attribute` → `settle`**（用户原名"沉淀"）—— 命名分三截落: 改名（纯机械）→ 文案+料 → 执行。
- ⭐ **settle 的产出 = 一条数组, `id` 决定"建"还是"改"**（⛔ 两数组版被否: 同一件事两套形状）。
- ⭐ **`entity.text` ≤ 60 字软尺** · **新建对象的 `name` ≤ 8 字**。
- ⭐ **只写"不值得记"**（契约里不许有正向判据）· **`id` 的门槛外化到证据上** ·
  **编造 `id` ⇒ 丢行**（⛔ 不给这一相位"整包拒"档）。
- ⭐ **`allowed_names` 闭环撤销** —— **名单是提示, 不是笼子**。
- ⭐ **空 = 不改**（见坑 4.22）。
- ⭐ **akin 共 belief**：**一跳 + 排除已矛盾的 + 上限 5**；**料侧 A 案**（挂在经历下面）；
  **`group` 留下的五个停产件：删**。

**2026-10-14 那一批（本版）**：
- ⭐ **`topics` 退役**（用户原话 *"先把 topics 退役掉吧"*）：契约不再要它、`parse` 不再登记、
  `ROUNDS.writes` 摘掉; ⭐ **字段只停产不删格式**（用户裁 **B1** —— 老档那几格还读得回来）。
- ⭐ **`akin` 的 `on` 一起退役**（用户裁 **A2**）：判据的载体死了 ⇒ 不留"没有判据的必填格"。
- ⭐ **`轴 …` 那一格全消失**（用户裁 **C1**），⛔ **不拿 `tags` 顶替**（真机泛词让一条经历跟
  9 条相连）。
- ⭐ **候选换源 = `like(spec="digest")`**（那条"写好了却零调用"的档位），印**分 + 为什么**。
- ⭐ **一个提交**（不是两个）：同一件事的两半**各自站不住**（改一半树是红的）⇒ 合成一笔。

**更早的**：`mmt_send_media` 封印（prompt 上收, 解析/执行照旧）· ⛔ 不做 `inspect entity` ·
`echo`/`mood`/`precious`/`recent`/`notes` 不做 · `walk` **暂不接线** · 非便利屋68 的角色不维护。

### 5.2 设计判断（推出来的，已写进代码注释或本文件）

- ⭐ **对象留下，容器走人**：entity = **指向**; 类 = **概括** ⇒ 概括是 `belief` 的活。
- ⭐ **"一类事"那个门槛不废、换载体**：从前"一群同类经历 → 一条沉淀"，今天"一群同类经历 →
  一条看法"，而"一群"由**她自己认过的 `akin`** 说了算（一跳；两跳会串到别的簇）。
  ⭐ 配套: **写侧并的是"证据"、料侧摆的是"立足点"** —— 两边同一口径（一跳 + 同一排除 + 同一排序）。
- ⭐ **判据随载体走**（2026-10-14 立）：一个字段退役时，**挂在它上面的判据要一起走** ——
  `topics` 死 ⇒ `akin` 的 `on ∈ 两端交集` 也死（⛔ 别留"没有判据的必填格": 那是"假威胁"的镜像）。
  同时 **判据的替换要换到能力相当的东西上**（这里是 `like` 的语义/字面打分，不是"随便找个字段顶"）。
- ⭐ **"像不像"从"共同轴词"换成"引擎给的理由"**：老路是纯集合运算（交集非空才能用，
  真机上恒空）; 新路是打分 + `why`（**分数不是闸门** —— 同一个人的经历天然都像，
  判"是不是同一类事"永远是她的活）。
- ⭐ **`entity.text` 与 `belief` 的分工是"粒度"**（旧判据"那一格没有读者"2026-10-12 已作废）。
- ⭐ **水位必须与它守的那句话同住一个原子单位**（同一个节点上）—— 两种失败语义都对。
- ⭐ **只有 `text` 需要水位**: **改名天然幂等**（值没变 ⇒ 不写、不留痕）。
- ⭐ **撞车绝不合并**: 改名撞上别的对象 ⇒ **只丢 `name` 那一格**（并错不可逆）。
- ⭐ **"引擎的手"要在变更史里留指纹**: 边表分不出"她点的"与"引擎并的"（用户裁"接受"）;
  但 `evolution.jsonl` 里那格 `"via": "akin"` 必须分得出 —— **审计与图是两件事**。
- ⭐ **tag vs 边（二择）的判据**：这个关系**需要一个名字**吗？需要 ⇒ 标签; 不需要 ⇒ 边。
- ⭐ **抄错灾难的机理**：不是"多一个对象"，是**那句话被写给幽灵**。三层防: 写侧照抄 ·
  引擎归一 + 认出老写法 · 事后可观测。
- ⭐ **"没有 X 的 Y"是个好模式**：engine 算"缺口" ⇒ LLM 只在有缺口时才被叫（成本天然最小）。
- ⭐ **两张计数提示的分工**（settle 的料）: 「正文里还提到过它 N 次（没标引用）」= 引擎扫正文,
  真机实测"老师" **21/21 恒真、零区分力** ⇒ **只当提示**; 「共出现 N 次（第一次在 …）」=
  **她认过的引用面**（`about` 入边）⇒ 只有这条可依据。

### 5.3 待用户拍 / 待办（**集中在这儿**）

1. ⭐ **belief collision 的其余两条**（§1A-4）—— 我建议下一件做它（`akin` 并边已把"多条"喂厚）。
2. **`aliases` 的写者**（§1A-3）—— 改名带旧名已落; "她主动补新别名"仍冻结。
3. **线 B 那两条**（1h 的岔路 · 1e 的两处待拍）—— **另一 agent 的, 别替他答**。
4. ⏸ 记着不动的: `ambiguous` 不加机制 · bond 开场不补物化 · `examples` 字段当扩展位留着 ·
   `profile` 只停产不删格式 · `topics` 只停产不删格式。
5. **收口类**（不是设计, 是欠的活）: `form_key` 下移 `contract/`（统一 `parse_attribution` 两端）·
   **真机跑一次端到端**（uvicorn + `experiments/recall_report.py`; ⚠️ 先确认 `[embed]` 服务在,
   否则 L1 的候选只看得到字面那几路）· `ahead 49` 未 push ·
   `noticed` 那条路落的 `akin` 边**不写变更史**（只有一行日志 —— 要不要补留痕, 记着）。
