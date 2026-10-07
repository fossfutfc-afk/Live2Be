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
| **P1b** | 🔶 **接了一半** | ⭐ **换骨头**：`ROUNDS` 的 key `understand` → `relate` + round 接线 + prompt 改写。⚠️ **写侧已落**（`apply_relations` = P3，见下）；⛔ 旧一族**不删**（用户裁：留给 L2）| `core/digest/rounds/*` · `llm/prompts/digest_understand.md` → `digest_relate.md` · `llm/task_labels.py` | 真机那轮跑出边（不再空转）| 见下面那张"P1b-2 作战表" | P1a | 大 |
| **P2** | ⬜ | **L1 的料**：加「现有经历（候选）」+ 印 `topics` | `core/digest/material.py` · `rounds/__init__.py` 的 `material` 格 · `rounds/relate.py` | 料里真出现已有经历的 id 与其 `topics` | `_sections_for` 逐字校对（表 ↔ 调用点）· 料里没有 ⇒ 红 | **P1b** | 中 |
| **P3** | ✅ **已落地**（`2e2b75b`）| **L1 的写侧**：`apply_relations`（**只落边**，不建 belief；带 `id_map`）| `core/brain/revise.py` | 边落对（rel/src/dst）+ 幂等 | 桩 store 钉"只做两件事"· 轴留痕 · `about` 方向 | — | 中 |
| **P4** | ⬜ | **prompt 改写**（→ `digest_relate.md`：职责 + 示范 + 指针）| `llm/prompts/digest_relate.md` | prompt 不抄判据（黑名单）| 黑名单加新词 · 示范形状是 `relations` | P1b | 小 |
| **P5** | ⬜ | **桩与编排**：`stub_tasks.annotation_reply` 认新形状 · `ROUNDS` 的 `writes` 格 | `tests/stub_tasks.py` · `rounds/__init__.py` | 板块绿 | 表里的边名/字段名真实存在（已有守门）| P1b | 小 |
| **P6** | ⬜ | ⭐ **观测**（"孤立经历"的账）| `rounds/relate.py` 的日志 | 一行日志能看出：几条关系 · 几条经历**一条关系都没被连** | 日志字段在 | P2 | 小 |

### ⚠️ P1b-2 作战表（2026-10-07 **试过一次、按纪律撤回** —— 未提交，树回到 `2e2b75b` 的绿态）

**机制**（为什么一接就大面积红）: 用例里那轮的应答还是旧形状 ⇒ `parse_relations` 判错 ⇒
**反馈重试耗尽**（`digest 轮次 relate: LLM 调用重试耗尽`）⇒ **整段回滚** ⇒ 连 R0/R1 的断言
**一起红**。⇒ **84 红里大部分是连带**, 不是语义过时。

**开工顺序**（每笔都可验, 建议拆两笔）:

1. **改名全仓铺** —— `DIGEST_UNDERSTAND` → `DIGEST_RELATE` **13 处**（⚠️ 上次只铺了 4 个文件
   ⇒ **43 个 collection 错误**）+ 轮次 key 引用（`enter("understand")` → `enter("relate")`）。
   **用一条 `rglob("*.py")` 扫** `core/ llm/ contract/ webgui/ apps/ tests/`。验收: `--collect-only` **零错误**。
2. **接线** —— `ROUNDS`（key/step/parse/writes）· `git mv rounds/understand.py rounds/relate.py`（正文重写）·
   `pipeline.IMPL` 的映射 + **import 行** · `git mv llm/prompts/digest_understand.md llm/prompts/digest_relate.md`（内容重写）·
   `tests/stub_tasks.py` 那一支 → `{"relations": []}`。验收: 跑 digest 板块, 看"只剩语义过时的红"。
3. **桩适配**（约 **40 处**，散在 **12 个文件**）—— 旧形状 ⇒ 新形状。
   ⚠️ **别动** `affection_exp_delta`（那是 **R1** 的字段, M1 搬的）；`evidence` 是否留也一样看它归谁。
   文件（按命中多少排）: `test_wiki_digest.py`（最多）· `test_digest_akin` · `test_digest_gap` ·
   `test_digest_window` · `test_digest_skip` · `test_digest_rounds` · `test_round_attr` ·
   `test_round_group` · `test_round_split` · `test_title_unique` · `test_note_events` · `test_digest_registry`
   （后两个只有 1~2 处）。
4. **删语义过时的用例**（用户 2026-10-07 已授权: *"没用的测试不用改，允许删除"*）——
   真正断言"R2 建了 belief"的那一族; 它们的内容归 **L2** 的节点。
5. 把以上写进本表（本行即它）+ 一次提交。

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
