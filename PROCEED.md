# PROCEED.md — **接续用**

> ⭐ **这份文件的唯一用途**：compact / 换会话之后，**5 分钟拿回上下文**。
> **关键内容不在这里** —— 在 §5 文档地图那几份里。
> ⭐ **规则：不往这里堆内容。** 一次讨论结束后，**只更新三处**：**§0 下一步 · §2 已裁 · §3 待裁**。
> （2026-09-27 按用户要求瘦身：陷阱 → `docs/TRAPS.md` · 三份调研 → `docs/RESEARCH_MEMORY_SURVEY.md`）

---

## 0. 状态 + ⏭️ 下一步

| | |
|---|---|
| **主线** | **新 note 机制 + graph 升级**（digest 按视野三层重排） |
| **代码** | ⭐ **一行未动**（用户明确"不动代码，先想清楚"） |
| **设计** | 一轮讨论已收口：**9 条已裁**（§2）· **3 条待裁**（§3）· 5 份设计文档（§5） |
| ⏭️ **下一步（compact 后从这里继续）** | ⭐ **讨论「wiki 的注入形式」** —— 进而得到 **MMT action 的设计** |

---

## 1. ⏭️ 接续点：为什么"注入形式"是下一个要讨论的

### 要讨论的问题

> **wiki（brain 注入）以什么形式进 prompt？**
> 而它**直接决定 MMT action 的设计** —— 因为 **"手边有什么"决定了"她还需要伸手要什么"**：
> **手边宽 ⇒ 不需要 action；手边窄 ⇒ action 变成必需品。**

### 今天的形态（真机实测，2026-09-27）

```
system 尾 = 【角色记忆（brain）】  … 4205 字符
              ├─ 我记得的事（从早到晚）：18 条 episode 【全文】（含「逐字原话」）
              └─ 我心里渐渐觉得：4 条 belief 全文（带 ——growth）
system 尾 += 【你自己记的备忘录】note（promise + on_mind）
history  = window_messages(max_units=120) → 真机 70 单元 … 5287 字符
────────────────────────────────────────────────────────
合计 ≈ 9500 字符（不含盒A 10 块 / 人设 / task 卡 / 玩家输入）
```

### 问题在哪

- **今天放得下**（18 条）—— 所以**五个玩家问题里四个她今天能答**（见下表）
- ⚠️ **wiki 变大就放不下**：100 天 ≈ 270 条 ⇒ **≈ 63000 字符**
- ⇒ **真正的问题是：变大之后，怎么保住"她能答那几个问题"？**
- **候选方向**：**骨架（title + 时间 + 难忘）常驻 + 按需正文**（refs 走法 / 引擎每轮摆 / `inspect`）
  · 今天 18 条全文 4205 字 vs 骨架 ~270 字（**≈ 1/15**）

### ⭐ 讨论时要带上的已知事实

| # | 事实 | 出处 |
|---|---|---|
| **1** | ⭐⭐ **`episode.title` 早就有了**（契约要求 8-16 字；真机 18 条**都唯一、都含具体名词**）—— ⚠️ **但从来没印出来** | `render._memory_line` **不印 title** |
| **2** | ⭐ 时间短语**故意虚化**（I-c 纪律："绝不出现小时/分钟/精确日期"）⇒ 真机全是 `（1 周前）`/`（7 天前）` ⇒ **"上周"筛不出**（**是纪律，不是 bug**） | `render._time_phrase` |
| **3** | ⭐⭐⭐ `_memory_line` 的设计理由里**已经写着**：*"LLM 需要先看到'这是多久以前的事'再读内容，才好判断'**这件事讲过了 / 该不该重提**'"* —— **判断的种子在提示词里，出口不存在** | 同上 |
| **4** | ⭐ **`inspect` 真机 0 次（157 轮）= 规模没到**，不是它没用（陷阱 **24** 的印证：*"没压过的地方就是 0"*） | 探针 |
| **5** | 五个玩家问题（上周干了什么 / 杂草屋发生过什么 / 你怎么看 X / 最珍贵 / 餐厅那次）⇒ ⭐ **四个她今天能答**（全文在手）；**只有"第三人"不能**（没预装、没注入） | 探针 dump |
| **6** | 两条链路**零调用者**：`render_organize_view`（边渲染）· `recall_subgraph`（整条召回链） | grep |

---

## 2. ✅ 已裁（9 条，一行一条）

| # | 裁决 | 详见 |
|---|---|---|
| **1** | **digest 按「视野」分三层**：`L-M` 对话轮 / `L1` 本段 / `L2` 跨段 / `L3` 实体；**不按轮**（`R5` 消掉、全景轮退役） | `DESIGN_DIGEST_LAYERS` §0 |
| **2** | **规律不落地成节点，落在边属性上**（`same_kind{aspect, conf}`）；**群的身份 = `aspect` 的值** ⇒ `group_by(aspect)`，零算法 | 同上 §5 |
| **3** | **`add` 只归 L2**（`groups[].belief`）；`decisions` 只许 `touch`/`update` | 同上 §3.6 |
| **4** | **note = `promise` + `on_mind` + ⭐ `index`**（指向群的指针）；**`habits` 槽取消** | `DESIGN_NOTE` |
| **5** | **L3 = entity 摘要**（动态人设基线）—— 异步 · 派生缓存 · **不进事务** | `DESIGN_DIGEST_LAYERS` §4 |
| **6** | ⭐ **`refs` 要有走法（两条都要）**：引擎按 refs 展开（**注入时预取**）+ **给她一个动作**；**展开可选 link 连环**（默认 1 跳 + 预算） | `DESIGN_NOTE` §5.2 |
| **7** | **`index` = 纯派生缓存**（从边表重建，不落真源） | 同上 |
| **8** | **段边界** =「一个来访单位结束」= **空闲 ≥1h 或 章闭环（先到者）** | `DESIGN_DIGEST_LAYERS` §4.6(g) |
| **9** | ⭐⭐ **Link 移交 MMT**（本主题最重要的一次结构裁决）：**link 由 MMT 每轮发现 / collision 由 L2 离线派生**；一石五鸟 + 打破"先分组才能派生"的循环 | `DESIGN_DIGEST_LAYERS` **§0.1** · `MMT_DESIGN` §3 |

---

## 3. ⬜ 待裁（3 条）

| # | 项 | 我的倾向 |
|---|---|---|
| **1** | **L3 的注入位置**：**替代**一部分 episode 全量注入，还是并列？ | ⭐ **"换一种读法" + 分两步走**（步 1 只加 L3 + 骨架不砍正文；步 2 验证预取命中率后再砍）—— `DESIGN_DIGEST_LAYERS` §4.1 |
| **2** | **`refs` 预取的命中率阈值**（步 2 能不能开的门槛） | 需真机标定 |
| **3** | **MMT 侧"她引用的当下"怎么落** —— 我给的方案是 ⭐ **边先落 `event_seq → episode`，L1 后引擎二分提升** | 待确认（`DESIGN_DIGEST_LAYERS` §0.1(i) · `MMT_DESIGN` §3.5） |

⚠️ **第 4 条会自动出现**：§1 的"wiki 注入形式"讨论完，会产生新的裁决。

---

## 4. 立刻要用的真机数字（`data/worlds/world1`）

```
haruka : 26 节点（18 episode + 4 belief + 4 entity）· 39 边（20 supports + 19 about）
         316 事件 · digested_seq=314 · note 6 条（note/close 0 次）
注入   : brain 4205 字 + history 5287 字（70 单元）≈ 9500 字符
5 个真组: 苔藓 · 夏莱 · 笔记 · 道歉 · 团子
致命三数: 4 条 belief 全部诞生自 1 条 episode · episode↔episode 边 0 条 · links 只写过 2 次
embed  : text-embedding-qwen3-embedding-0.6b（nomic 已换，见 TRAPS 38）
```

**四条实测结论**（讨论注入形式时都要用）：

| 结论 | 数值 |
|---|---|
| dense 相似度**判不了同类** | 组内最低 < 组外最高，最差 **0.425**（任何 k / 任何阈值下 4 个真组 **0/4 干净**） |
| 字面（`tags`）**精确度 1.00** | 归一化能把召回 0.67 → **1.00** |
| `inspect` 使用率 | **0 / 157 轮** |
| `contradicts` | **0 条**（机制齐全、零数据） |

---

## 5. 文档地图（**关键内容在哪**）

| 文档 | 管什么 |
|---|---|
| ⭐ **`docs/MMT_DESIGN.md`** | **主对话轮的设计**：三种行（消息/操作/记录）· `inspect` 慢路 · **link 记录行 + 锚 + 区间** · 手边六格 · 情形表 · **相对其他项目解了什么** |
| ⭐ **`docs/DESIGN_DIGEST_LAYERS.md`** | **digest 三层重排（动工文档）**：§0.1 根因与最终分工 · L1/L2/L3 规格 · 边与图 · 候选池"窄而深" · L3 注入详解 · 节点拆分 |
| ⭐ **`docs/DESIGN_NOTE.md`** | **note 的真正定位**：人的三类 note · LLM 的三条差别 · 三条合一的存在判据 · **第三槽 `index`** |
| ⭐ **`docs/TODO.md`** | **施工顺序表（15 步）** + 每步细化 + 判据 + 三条纪律 |
| ⭐ **`docs/TRAPS.md`** | **陷阱 1–47**（编号全局，**不许改**） |
| ⭐ **`docs/RESEARCH_MEMORY_SURVEY.md`** | **三份调研结论**（本地深读 / 学术侧 9 条 / 生态侧 26 条，带出处与检索边界） |
| `core/brain/wiki_v2/DESIGN_GRAPH_V4.md` | 图的设计稿：走法（7 条）· promise 两段式 · 每段四步 · 全景轮 |
| `docs/DESIGN_WIKI_V3.md` | V3 设计稿：四轴 · `nature`（含 `pattern`+`occurrences`）· 四条召回道路 |
| `docs/DESIGN_RECALL.md` | **另一条链（读路径）**：`mmt_recall` 四支 scope / `when` / 结果生命周期 |
| `docs/EXPERIMENT_CAND_HIGH.md` | Q11 阈值实验（**nomic vs Qwen3 实测**——换模型的依据） |
| `CLAUDE.md`（仓根） | 项目主文档（⚠️ **改前先改名**）；§7 记忆 · §10 配置 · §12 测试/提交纪律 |

---

## 6. 施工顺序

⭐ **在 `docs/TODO.md`**（15 步，`N1` 边加属性 → … → `N15` 验收）。
**顺序原则**：输入面先修 → 免费的先做（含 **MMT 的发现**）→ 花钱的放最后。
**硬约束**：`N1` 起手；`N3`（L1 区间化）不做完，后面每步的输入都是脏的。

---

## 7. 纪律（**别违反**）

1. **动手前先说做什么；动手后报告"做了什么 / 遇到什么问题 / 下一步"**；⚠️ **歧义就停下讨论**
2. ⭐ **复杂节点先把逻辑整理给用户**（2026-09-25 那条救掉一个错判）
3. **一节点一提交**；`git commit -F <文件>`（**CJK 会炸 `-m`**）；只 stage 明确路径
4. ⭐ **改 `CLAUDE.md` 前先改名**（`git mv CLAUDE.md CLAUDE_EDIT.md` → 改 → 改回）；它的预算已满
5. 不跑 `ruff --fix`；不提交 `config/characters/*/illustration.yml`；`tools/` 是 gitignore
6. ⭐⭐ **别拿"真机数据频率"论证价值**（陷阱 **24**）—— **没压过的地方就是 0**（`inspect` 0 次 / `contradicts` 0 条都是这一类）
7. ⭐ **改契约必须同批改示例**（陷阱 **3/46**）—— **示例才是形状的来源**
8. ⭐ **调研结论要带出处 + 标检索边界**（*"在能读到的范围内没有"* **≠** "不存在"）
9. ⭐ **答复用户要具体**（他两次说"没咋听懂"）：**不堆比喻**，直接说问题在哪 / 能不能解决 / 代价是什么；**用真机数字说话**

---

## 8. 验证配方（每节点必跑）

```powershell
New-Item -ItemType Directory -Force .testtmp/pw | Out-Null   # ⚠️ Windows 下要先建

# 小回归（改 wiki 层时先跑）
python -m pytest tests/core/test_wiki_digest.py tests/core/test_digest_registry.py `
  tests/core/test_round_close.py tests/core/test_round_attr.py tests/core/test_wiki_render.py `
  tests/core/test_wiki_revise.py -q --basetemp=.testtmp/pw_graph

# 全量四件套
python -m pytest tests/core tests/webgui tests/llm tests/renderer -q --basetemp=.testtmp/pw
python -m compileall -q core contract webgui apps llm tests main.py
node --check webgui/static/js/bond.js
python experiments/web_e2e/run.py
```

**最近一次已知绿**：全量 **1091 passed**（`8bc0cf0` 之后；其后都是文档提交）。

**只读探针**（`.testtmp/` 是 gitignore，可能被清 ⇒ 结论已抄进各文档）：
`probe_mmt_view.py`（**真机注入 dump**）· `probe_bfs_purity.py`（dense 判不了同类的决定性证据）·
`probe_literal_dims.py`（tags 精确 1.00）· `probe_embed_ab.py`（nomic vs qwen3）·
`probe_belief_birth.py`（4 条 belief 全诞生自 1 条）· `probe_abstraction.py`（抽象句占比）·
另有 `probe_graph_shape` / `probe_time_axis` / `probe_turn_grain` / `probe_group_keys` /
`probe_chapter_scope` / `probe_mmt_grain` / `probe_pure_mmt` / `probe_mmt_entropy` / `probe_sessionize` /
`probe_belief_redundancy` / `probe_llm_load` / `probe_reabstract` / `probe_bfs_components` / `probe_ts_crash`

---

## 9. 提交记档（最近）
| 提交 | 内容 |
|---|---|
| `d0e4fe9` | embedding 换模型：**nomic → Qwen3-Embedding-0.6B**（并排实测 + 钉死配置） |
| `ca604d5` | PROCEED 第二次整篇重写（§4 推理链 + 三层） |
| `eaa1b63` | §4.4b belief 会不会膨胀（实测 + 三条准入） |
| `d055616` | **动工文档 `DESIGN_DIGEST_LAYERS` + `DESIGN_NOTE`** |
| `53f02db` | 落四条裁决（refs 走法 / index 派生 / 段边界 / L3 详解） |
| `41fa193` | §3.3 补"不做 tool call 怎么注入 graph"的七条路 |
| `02dab87` | L2 规格落五动作 + 新建 `TODO.md` |
| `ec5c0fc` · `c037e33` | **Link 移交 MMT**（§0.1 根因与最终分工） |
| `fbcf654` | **新建 `MMT_DESIGN.md`**（三种行 / inspect / link） |
| （本次） | ⭐ **PROCEED 瘦身成"接续用"**（1135 → ~200 行）：陷阱 → `docs/TRAPS.md` · 调研 → `docs/RESEARCH_MEMORY_SURVEY.md` · **§1/§2/§4 → `docs/REASONING_LOG.md`** |

---

## 10. ⚠️ 章节对照（**旧编号 → 新家**）

> 2026-09-27 瘦身时重排了编号。**别处写 `PROCEED §N` 的引用，按这张表找。**

| 旧编号（被别处引用过） | 现在在哪 |
|---|---|
| §1 验收样本（送花台词 + 反例 + 玩家觉察） | ⭐ `docs/REASONING_LOG.md` **§1** |
| §2 为什么现在的是坏的（真机证据 + 提示词 + 管线） | ⭐ `docs/REASONING_LOG.md` **§2** |
| §3 调研结论（三份，带出处） | ⭐ `docs/RESEARCH_MEMORY_SURVEY.md` |
| §4 本轮推理链（4.1–4.7b） | ⭐ `docs/REASONING_LOG.md` **§4**（**子编号原样**：`§4.4b` / `§4.6(g)` / `§4.7` 都在） |
| §5 拆分 + 待裁 | ✅ 仍在本文 **§2/§3**（裁决拆成"已裁 / 待裁"两张表） |
| §6 工作约定 | ✅ 仍在本文 **§7 纪律** |
| §7 已落地 / 已退役 | ✅ 并入本文 **§9 提交记档** |
| §8 陷阱清单 1–47 | ⭐ `docs/TRAPS.md`（**编号不变**） |
| §9 验证配方 + 真机基准 | ✅ 仍在本文 **§4 + §8** |
| §10 文档地图 | ✅ 仍在本文 **§5** |

⚠️ **新增/追加的规则**（搬家时验过：`TRAPS.md` 1–47 连续、`RESEARCH` 三节齐全、`REASONING_LOG` 各小节齐全）：
- **陷阱只许追加**，不许插入/重排（编号是全局引用键）
- **本文只更新三处**：§0 下一步 · §2 已裁 · §3 待裁；**新内容一律进设计文档**
