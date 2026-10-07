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
| **P0** | ✅ **已落地**（`d967ddf`）| **R1 长出 `topics`**（1~3 个具体的东西，⛔ 泛词）| `contract/digest_registry.py` 的逐字段表 · `llm/prompts/digest_record.md` | 真机每条 episode 都带 `topics` | 字段进 `RECORD_EPISODE`（⛔ 不是 R0 的 `ROW_FIELDS`）· 示例里有 · 上限 3 · `ROUNDS.writes` 有 | — | 小 |
| **P1** | ⬜ | **L1 契约形状**（`relations` + 四个动作）| `contract/digest_registry.py`（`PHASE_UNDERSTAND` 重写 + `parse_relations` 替换 `parse_round_b`）| 合法/非法行的对立用例 | id 闭集 · `on` 交集 · **文本里的 kind 名 ∈ `KINDS`**（反向）| **P0** | 中 |
| **P2** | ⬜ | **L1 的料**：加「现有经历（候选）」+ 印 `topics` | `core/digest/material.py` · `rounds/__init__.py` 的 `material` 格 · `rounds/understand.py` | 料里真出现已有经历的 id 与其 `topics` | `_sections_for` 逐字校对（表 ↔ 调用点）· 料里没有 ⇒ 红 | P1 | 中 |
| **P3** | ⬜ | **L1 的写侧**：`apply_relations`（**只落边**，不建 belief）| `core/brain/revise.py`（与 `apply_decisions` 拆开）| 边落对（rel/src/dst）+ 幂等 | 未知 id 拒 · 幂等 · **`akin` 的 `on` 缺失 ⇒ 拒** | P2 | 中 |
| **P4** | ⬜ | **prompt 改写**（`digest_understand.md`：职责 + 示范 + 指针）| `llm/prompts/digest_understand.md` | prompt 不抄判据（黑名单）| 黑名单加新词 · 示范形状是 `relations` | P1 | 小 |
| **P5** | ⬜ | **桩与编排**：`stub_tasks.annotation_reply` 认新形状 · `ROUNDS` 的 `writes` 格 | `tests/stub_tasks.py` · `rounds/__init__.py` | 板块绿 | 表里的边名/字段名真实存在（已有守门）| P1–P4 | 小 |
| **P6** | ⬜ | ⭐ **观测**（"孤立经历"的账）| `rounds/understand.py` 的日志 | 一行日志能看出：几条关系 · 几条经历**一条关系都没被连** | 日志字段在 | P3 | 小 |

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
