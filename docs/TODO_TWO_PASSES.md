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
| **P6** | ⬜ | ⭐ **观测**（"孤立经历"的账）| `rounds/relate.py` 的日志 | 一行日志能看出：几条关系 · 几条经历**一条关系都没被连** | 日志字段在 | P2 ✅ | 小 |

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

### 之后（**L2 那一段，等 L1 落地后再排**）

- **P7+**：L2 = 「造新认知 + 接图」（`belief` / `evolved_from` / `experience` 的沉淀 / `member_of` / 造改 entity）
- ⭐ **L2 的料 = 「L1 圈出来的素材」**（接力，不是并列 —— 用户 2026-10-07）：
  被 L1 连过的那些经历（**读边取两端**，纯计算）+ L1 指向的认知/群 + 少量引擎候选 + 那些成群经历的正文。
  ⚠️ **孤立经历（L1 一条边都没连的）不进 L2** —— 那不是漏洞，是**天然的归纳门槛**（规格 §3）。
- ⏸ 顺带：**`attribute` 轮永久删**（两件活被两趟吸收）· `graph.RELS` 若加 `continues` 则 6 → 7

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
