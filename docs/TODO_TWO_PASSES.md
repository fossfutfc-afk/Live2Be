# TODO_TWO_PASSES — 两趟（L1 判关系 · L2 写正文）**施工顺序表**

> 建立 **2026-10-07**。规格 = `docs/DESIGN_DIGEST_TWO_PASSES.md`（§9 = **L1 契约正文，已定稿**）。
> 语义地基 = `DESIGN_MEMORY_MODES.md`。**一行一个节点、一个提交。**
> 判据写死；**每条守门都要先验"能红"**才算数。
>
> ⚠️ **测试纪律**（同 `TODO_DIGEST_LEDGER` / `TODO_SPLIT_AXES`）：**禁止频繁跑全量**；**按板块跑**；
> **改到一半的树不跑回归**。
> ⚠️ **动代码之前先报"关键信息的形式"给用户审**；**除用户明确说"继续"，不许自己往下做**。

---

## 0. 一条硬依赖 + 一条顺序原则

| # | 事 | 为什么 |
|---|---|---|
| **D1** | ⭐ **`topics` 必须先在 R1（`record`）落地** | `akin` 的 `on` 要按**两端 `topics` 交集**校验 ⇒ **没有 `topics` 就没有轴**。它是 M3 的第 0 步（= **P0** 节点）|
| **D2** | 顺序 = **契约 → 料 → 执行器 → 观测** | 同 `TODO_DIGEST_LEDGER §1`：形状定死、守门能红，后面才敢动 |

---

## 1. 节点表（L1 这一段）

| 步 | 状态 | 一句话 | 落点 | 验收 | 守门（能红）| 依赖 | 体量 |
|---|---|---|---|---|---|---|---|
| **P0** | ✅ **已落地**（`11ad209`）| **R1 长出 `topics`**（1~3 个具体的东西，⛔ 泛词）| `contract/digest_registry.py` 的逐字段表 · `llm/prompts/digest_record.md` | 真机每条 episode 都带 `topics` | 字段进 `RECORD_EPISODE`（⛔ 不是 R0 的 `ROW_FIELDS`）· 示例里有 · 上限 3 · `ROUNDS.writes` 有 | — | 小 |
| **P1a** | ✅ **已落地**（`b09136f`）| ⭐ **新增并立**：新相位 `relate` + 四个关系动作 + `parse_relations`（旧路径**一字不动**）| `contract/digest_registry.py` | 合法/丢行/整包拒三档分得开 | 动作名 ⊆ `graph.RELS` · 锚点类型 == `nodes.KINDS` · 契约里没有正文键 | **P0** | 中 |
| **P1b** | ✅ **已落地**（P1b-2, 2026-10-07）| ⭐ **换骨头**：`ROUNDS` 的 key `understand` → `relate` + round 接线 + prompt 改写。⚠️ **写侧已落**（`apply_relations` = P3，见下）；⛔ 旧一族**不删**（用户裁：留给 L2）| `core/digest/rounds/*` · `llm/prompts/digest_understand.md` → `digest_relate.md` · `llm/task_labels.py` | 真机那轮跑出边（不再空转）| 见下面那张"P1b-2 作战表" | P1a | 大 |
| **P2** | ✅ **已落地**（P2, 2026-10-07）| **L1 的料**（**一笔三件**）：「现有经历（候选）」（按 `topics` 相交摆 + 印交集轴 + 印旧事的时间）+ 新经历印 `topics` + 对象候选（≤5 个真 id + 字面命中提示, `entity_ids` 换真集）· ⭐ 顺带补上 **`akin`/`contradicts` 两端类型检查**（`kind_of`）| `core/digest/material.py` · `core/brain/entities.py`（`object_lines`）· `rounds/__init__.py` 的 `material` 格 · `rounds/relate.py` · `contract/digest_registry.py` | 料里真出现已有经历的 id 与其 `topics`; `akin` 连得上旧经历; `about` 落得下来 | `test_l1_akin_reaches_an_older_episode` · `test_l1_about_lands_with_object_candidates` · `test_l1_type_mismatch_is_dropped` · `test_digest_material.py`（挑法/上限/印法）· 四条都验过**能红** | **P1b** | 中 |
| **P3** | ✅ **已落地**（`2e2b75b`）| **L1 的写侧**：`apply_relations`（**只落边**，不建 belief；带 `id_map`）| `core/brain/revise.py` | 边落对（rel/src/dst）+ 幂等 | 桩 store 钉"只做两件事"· 轴留痕 · `about` 方向 | — | 中 |
| **P4** | ✅ **随 P1b-2 落地** | **prompt 改写**（→ `digest_relate.md`：职责 + 候选解释 + 指针）| `llm/prompts/digest_relate.md` | prompt 不抄判据（黑名单）| `test_relate_prompt_points_at_the_contract`（旧词汇零命中 + 指针对准契约真标题）| P1b | 小 |
| **P5** | ✅ **随 P1b-2 落地** | **桩与编排**：`stub_tasks.annotation_reply` 认新形状 · `ROUNDS` 的 `writes` 格 | `tests/stub_tasks.py` · `rounds/__init__.py` | 板块绿 | `test_l1_writes_edges_only`（`writes` 只有边面）| P1b | 小 |
| **P6** | ✅ **已落地**（P6, 2026-10-08）| ⭐ **观测**（"孤立经历"的账）| `core/digest/rounds/relate.py` 的日志 · `core/digest/material.py`（摆不出候选时**不再连段标题一起被吞**）| 一行日志能看出：几条关系 · 几条经历**一条关系都没被连**（`alone=` / `lone=`）· 前提读数 `pool=` | `tests/core/test_round_relate.py`（7 例）· 5 个变异全红（`.testtmp/verify_p6_red.py`）| P2 ✅ | 小 |

| **P7** | ✅ **两笔已落地**（`d54e55c` L2 契约 · `466b641` L1 第五个动作, 2026-10-08）| ⭐ **L2 的契约**（新相位 `cognize`）+ 顺带补上 **L1 的第五个动作 `evolved_from`** | `contract/digest_registry.py` · `llm/prompts/digest_relate.md` | 三种行渲得出来 · 三档分得开 · 上限 5 · "旧看法 → 更旧"有主 | `tests/core/test_digest_registry.py`（+5 例）· 6 个变异全红（`.testtmp/verify_p7_red.py`）| P6 ✅ | 中 |
| **P8** | ✅ **已落地**（P8, 2026-10-08）| **L2 的料**: 【本段归类的群】（**每类一块** · 挑"本段新归入最多"的那组 · 现状沉淀 · 已有成员**上限 4**）·【被连过的经历】（**读 L1 那五条边**取两端 · 行头 + 正文 · `↳ 关于:` 只随 `about` 边出现）| `core/digest/material.py` · `core/brain/entities.py`（`entity_label` 抽公共）| 真机样张**逐条对齐**（`.testtmp/verify_p8_material.py`）| `test_digest_material.py`（+5 例）· 6 个变异全红 | P7 ✅ | 中 |
| **P9** | ✅ **已落地**（P9, 2026-10-08）| **L2 的执行器** `apply_cognitions`: 造 belief（**幂等走 `_find_duplicate`** —— 与 R1 的 episode 同一判据同一实现）+ 出生自带三条边 + 覆写 `experience.text`（**留痕照 `apply_decisions` 的 update 行**）| `core/brain/revise.py` | 真机**副本**上真跑: 新节点 + 两条边 + 沉淀覆写 + 四条账 · **重跑不双写**（`.testtmp/verify_p9_executor.py` 12/12）| `test_wiki_revise.py`（+4 例）· 8 个变异全红 | P8 ✅ | 中 |
| **P10** | ⬜ | **接线**: `ROUNDS` 加一行（**排在 `group` 之后**）+ `digest_cognize.md` + 桩（`stub_tasks` / `task_labels`）| `rounds/__init__.py` · `llm/prompts/` · `tests/stub_tasks.py` | 真机跑出 `digest_cognize` 那行日志 | naming guard 绿 | P9 | 中 |
| **P11** | ⬜ | **观测**: `digest_cognize beliefs= evolved= contradicted= soaked= groups= rows= dropped=` | `rounds/cognize.py` | 一行看清这一趟干了什么 | 先验能红 | P10 | 小 |

> ⚠️ **P8 的形状是用户逐轮审出来的**（三稿）: 成员 8 → **4** · 「被连过的经历」里的
> `↳ 印证` / `↳ 同类` **全删**（用户: *"要么给全, 要么不给…现有的关系不需要知道它的印证什么的"*
> —— 那是"已有成分之间的关系", 而契约明写着"上一趟已经判过了"）· ⭐ **`↳ 关于:` 留着**
> （用户: *"还是保留吧, 保障扩展"* —— entity 那条链在 L2 视野里的唯一把手）。
> ⛔ **不做【相似候选】**（用户: *"以后得统一写一个节点召回包, 现在先直接分桶"* ⇒ §1.5）·
> ⛔ **不给【本段时间线】**（经历正文已经说全）。
> ⚠️ **`ROUNDS` 那一行必须与 `rounds/cognize.py` 同笔**：命名守门
> （`test_round_files_speak_their_own_name`）要求"表里的 key ↔ 有轮文件"**一一对应**,
> 只加表行不加文件 ⇒ 当场红。⇒ 段标题与 `material` 格随 **P10** 落地。

> ⚠️ **P6 那个前提**（读 `cands=` 之前先看它）: 真机老档 **19 条 episode 只有 1 条有 `topics`**
> （字段是 P0 才加的）⇒ `cands` 会长期是 0、`alone` 虚高。`pool=` 就是给这个用的解释器。
> 用户 2026-10-08 裁: *"反正以后也要测试新的 digest，之后就删掉数据重来了，现在不急"*
> ⇒ **只观测**, 不写补 `topics` 的维护脚本。

### ⚠️ P1b-2 作战表（2026-10-07 **已落地** —— 试做一次按纪律撤回, 第二次一次做完）

**机制**（为什么一接就大面积红）: 用例里那轮的应答还是旧形状 ⇒ `parse_relations` 判错 ⇒
**反馈重试耗尽**（`digest 轮次 relate: LLM 调用重试耗尽`）⇒ **整段回滚** ⇒ 连 R0/R1 的断言
**一起红**。⇒ **第一遍那 84 红里大部分是连带**, 不是语义过时。

**实际怎么做的**（五步, 一笔提交 —— ⚠️ **"拆两笔"不成立**: key / 常量值 / 桩分派
是一根绳, 而且"R2 建 belief"那一族用例必须同笔删掉才可能是绿的）:

1. **改名全仓铺** —— `DIGEST_UNDERSTAND` → `DIGEST_RELATE` **20 处 / 12 文件**
   （⚠️ 表里原先写的"13 处"是错的; 上一遍只铺了 4 个文件 ⇒ 43 个 collection 错误）+
   常量值 + 轮次 key 引用 + prompt 文件名。验收: `--collect-only` **1235 collected, 零错误**。
2. **接线** —— `ROUNDS` 那格（key/step/parse/`writes`）· `git mv rounds/understand.py relate.py`
   （正文重写）· `pipeline.IMPL` + import 行 · `git mv llm/prompts/digest_understand.md digest_relate.md`
   （按 §9.6 重写）· `tests/stub_tasks.py` 那一支 → `{"relations": []}`。
3. **桩适配** —— 旧 `{"decisions": …}` 那一族按文件批量替换（脚本, 锚点唯一才写盘）:
   `test_wiki_digest` / `test_round_split` / `test_round_group` / `test_round_attr` /
   `test_digest_{akin,gap,skip,window,rounds}` / `test_title_unique` / `test_note_events` /
   `tests/webgui/test_bond` / `experiments/web_e2e/stub_world`。
   ⚠️ **`affection_exp_delta` 没动**（它是 R1 的字段, M1 搬的）—— 只把"第二支那份没人读的"
   删了。
4. **删语义过时的用例**（用户 2026-10-07 授权）—— 真正断言"R2 建 belief / 改正文"的那一族:
   `test_touch_decision_links_only` · `test_high_candidate_no_longer_forces_touch_update` ·
   `test_no_candidate_when_unrelated` · `test_cold_start_add_belief` ·
   `test_b_rejected_twice_fails_atomically`（并成下面两条新的）。
   **新写两条**: `test_l1_writes_edges_and_enforces_the_axis`（本地号翻译 / 轴交集 /
   `on` 留痕 / `about` 无候选 · 端到端）· `test_l1_invented_id_rejects_the_whole_package`
   （编造 id ⇒ 整包拒 ⇒ 整段原子回滚）· 另加一条 `test_candidate_hint_is_only_a_hint`
   （料里不许再出现旧动作名 —— 那是**她照抄就会变坏行**的东西）。
5. 把以上写进本表（本行即它）+ 一次提交。

**⭐ 这一遍逼出来的两处真问题**（都不是笔误, 已修 + 已补守门）:

| 问题 | 判据 | 处置 |
|---|---|---|
| `parse_relations` 的 **`about` 档位与它自己的 docstring 不一致**（代码走"整包拒", 文档写"丢行"）| 对象候选是引擎摆出来的 **≤5 个**, 挑错了是**失手**; 而整包拒会把**这一段记忆整个回滚** —— 代价与"归错一次人"不成比例 | 按文档改成**丢行 + 记账**（硬档只留给"左端 / 非 about 的右端"）；P1a 那条松散断言（`res6.errors or res6.drops`）收紧成 `drops and not errors` |
| `relate` 传给 parse 的 `target_ids` **只含认知**（本地号）⇒ "本段两条经历之间"的 `akin` 被当成**编造 id** ⇒ 整包拒 | 右边能引用的 = **渲染列表里的全部**（认知用本地号 · 本段新经历用真身）| `target_ids = 本地认知号 ∪ 本段 episode 真 id`（端到端用例逼出来的）|

**⛔ 明确不做**: 删旧一族（`TOUCH`/`UPDATE`/`ADD` · `parse_round_b` · `apply_decisions`）——
用户裁: *"有些可能会留给 L2，你觉得有用的不用着急删"*。

### 之后（**L2 那一段** —— 用户 2026-10-08 定稿五点，P7 已落地）

- **P7–P11**（见上表）：契约 → 料 → 执行器 → 接线 → 观测，**一笔一验**。
- ⭐ **L2 = `cognize` 一趟干两件事**: **造看法**（`belief`, 出生自带 `supports` /
  `evolved_from` / `contradicts`）+ **给已有的类写沉淀**（`experience.text`, **整段重写**）。
  用户原话: *"experience 本质是群 belief"* ⇒ 正文归 L2, **而"哪些事件属于这一类 + 类名"是结构**
  ⇒ 建类 / 成员仍归 `group`（**L2 不建类** —— `experience` 那一行**必须带 `id`**）。
- ⭐ **L2 的料 = 「L1 圈出来的素材」**（接力，不是并列 —— 用户 2026-10-07）：
  被 L1 连过的那些经历（**读边取两端**，纯计算）+ 本段归类的群（类名 + 现状沉淀 + 成员正文）
  + L1 指向的认知 + 少量引擎候选。
  ⚠️ **孤立经历（L1 一条边都没连的）不进 L2** —— 那不是漏洞，是**天然的归纳门槛**（规格 §3）。
- ⏸ **`attribute` 轮押后到 L2 落地后再裁**（用户 2026-10-08）：L2 到底吃掉 entity 的哪一半,
  决定它还剩什么 —— 现在删/留都可能白做。
- ⛔ **`graph.RELS` 不加 `continues`**（保 6 条，理由见规格 §4）。
- **L1 的第五个动作 `evolved_from`** 已落地（`466b641`）：判据 = 谁手里有两端。

---

## 1.5 读路径 / 召回（**待裁** —— 用户 2026-10-08 的两条判断, 不在这条链上）

用户原话：*"我觉得（单独）桶分的最大问题是**容易被占满, 导致新的记忆永远无法扩展**；
我觉得**给到 digest 的素材需要用到混合打分**, 不然那个混合打分到底用在哪啊"*。

⭐ **第三条（同日, P8 样张审完后）**：*"相似候选…我觉得**以后得统一写一个节点召回包**,
现在先直接分桶"* ⇒ **P8 不做【相似候选】那一段** —— L2 的右端就是【现有认知】这一份桶
（`sig` 前 N + `u…` 编号）。**"节点召回包"列为将来那件大事**（它其实就是下面 B/C 的统一形状）。
⚠️ **已知代价**（记着, 别以后当 bug 查）: 不在桶里的旧看法, L2 写不出指向它的 `evolved_from`
—— **前 12 之外 = 进化边够不着**; 同理 L1 的 `contradicts` 也只在桶内可见。

**查证到的事实**（我逐处读代码核过, 供以后裁）：

| 事 | 现状 |
|---|---|
| 常驻 brain 段 | **不是召回, 是全量注入**（台账 `mode=off`）: 经历 = 一条河（`ts` 升序）· belief = **sig 降序** · profile = 被引次数 · reported 原序; **cap 已删**（2026-09-25 有意）|
| MMT 每轮「你想起的事」(P19) | **唯一真召回**: `recall_episodes` 语义 top-2; embed 不可用 → tags∩这句话 + 2-gram Dice>0.35（台账 `mmt_recall … mode=`）|
| 四链路混合打分（`compose.recall_now`）| ⚠️ **零生产调用** —— 只有 `experiments/recall_compose_probe.py` 与测试在跑。设计上它是**读路径注入视图**的合成层, 而那个位置被"静态分桶的全量注入"占了 |
| `recall_subgraph`（三通道 + sig 降序）| 只被 `core/rag/brain.py` 包了一层, 而**那个包装零调用**（`recall_with_rag` 无调用方）|
| digest 的料 | 走**写路径**的候选碰撞（`recommend_candidates`, 单通道语义）+「现有认知」的 **sig 前 12** |

⭐ **用户那句话与"sig 前 12"是同一个病根**：高 sig 的老看法永远占着那 12 个位置,
**新看法永远没机会被连接 / 进化**。
⏭ **下一步（未开工）**: 先跑一次只读探针（`experiments/recall_compose_probe.py`, 跑前先核它不写盘）
把"四链路在真档上会选谁 / TIME 把排序改了多少"量出来, 再在
**A 时间桶 / B 接 `compose` / C 二维配额（类型 × 时间）** 三条里裁 —— 用户 2026-10-08 裁:
**先不动**, 收完 P7 再说（P7 已收）。

---

## 2. P1 的验收细目（这一笔最容易出错，写死）

**形状**（合法行的全集）：

```
{"episode": "m0014", "about": "x0001"}                    ✅
{"episode": "m0017", "akin": "m0014", "on": "苔藓"}        ✅
{"episode": "m0017", "supports": "u0003"}                 ✅
{"episode": "m0015", "contradicts": "m0009"}              ✅
{"belief": "u0007", "supports": "u0002"}                  ✅ 候选对（两端都已有）
{"episode": "m0014", "akin": "m0017"}                     ❌ 缺 `on` ⇒ 丢行 + 记账
{"episode": "m0014", "akin": "m0017", "on": "老师"}        ❌ `on` 不在交集 ⇒ 丢行 + 记账
{"episode": "m0014", "supports": "u9999"}                 ❌ id 不在列表 ⇒ **整包拒**
{"episode": "m0014", "text": "…"}                         ❌ 本趟禁正文键 ⇒ 丢行
```

**为什么"缺 `on`"是丢行而不是拒整包**：轴是**逐行**的性质，一行坏不该毁掉整段记忆
（与"编造 id"不同 —— 那个说明她**没在引用真实世界**，整包不可信）。

⚠️ **`on` 的交集判据要用"两端 `topics` 的原样字符串"**（大小写/标点都不归一 ——
归一就变成引擎在替她判"这两个词是一回事"）。

---

## 3. 不做（这一段）

| ❌ | 为什么 |
|---|---|
| 加 `ends` 格 | 方向**由类型对定死**，多一格是重复记账（用户 2026-10-07 裁决）|
| `continues` | 用户裁"暂时不提"（要动 `graph.RELS` 6 → 7；启用时再加）|
| L1 打"该长出一条看法"的标记 | 踩"同一件事想两遍"（`DESIGN_DIGEST_TWO_PASSES §8`）|
| L1 造虚节点 | 同上 |
| L1 要求"覆盖每条经历" | 没话说就不写（"这条跟谁都没关系"也是结论）|
