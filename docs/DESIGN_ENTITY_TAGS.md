# entity 的归属与身份 —— **tag 是输入 · 边是派生**

> 2026-10-08 用户裁决（对话里叫 B0 / B0' / B0.5 / B1，本文件用 **E1–E4**）。
> ⚠️ 本文件**取代** `DESIGN_GRAPH_V4.md` §10 的三条：`attach`（归属由 LLM 边写边判）、
> `new_entity` 的载荷（`text`/`state` 由归属轮写）、"归属轮每段跑一次"。
> 状态：**大纲**（未落码）。施工表见 §9。

---

## 0. 一句话

**她写 tag（`#entity:老师`）· 引擎落边（`about`）· entity 只存身份 · "看法/印象"是 belief。**

---

## 1. 这一版治的三个洞

| # | 洞 | 现状（真机可核） |
|---|---|---|
| ① | **认不了新人** | `about` 的值必须是**已存在的 id**（`parse_relations` 拿 `entity_ids` 校验）⇒ 她**没有语法**表达"这条关于一个我还不知道的人" |
| ② | **"印象"无处放、且没有读者** | `entity.text` 计划由归属轮写，而那一轮**暂停**（2026-10-05）；且 entity 在注入面里**零读者** |
| ③ | **归属判两遍** | L1 判 `about`（真机覆盖 **48%**、10/21 条），归属轮又判一次 `attach` ⇒ 同一件事两个写者 |

---

## 2. 四条结论（答案先写）

1. **`about` 边要留** —— 它是 `graph.lane(E)` / `beliefs_of(E)` / `unattributed()` 的载体
   （"X 的故事"、"她对 X 的看法"、"还没归属的清单"三条查询），但**由引擎从 tag 派生**，
   不是 LLM 在另一轮再判一遍。
2. **entity 不背正文** —— 印象 = **belief**（见 §6.1），entity 只存**身份**（`name` + `aliases`）。
3. **归属只判一次** —— 在"写这条东西"的那一轮顺手声明（R1 写 episode 的 tag、L2 写 belief 的 tag）。
4. **新人走三步**：tag 先写（指不到）→ R3 **建人** → 引擎**回头补边**（纯计算，同段闭合）。

---

## 3. 数据模型

```
她写的（输入, 弱引用 —— 可以指向还没建的人）
    episode/belief 的 tags:  [..., "#entity:老师"]
                    ↓ 引擎: 解析 → 落边 → 归一
引擎落的（派生, 强引用 —— 一定指向真实 id）
    about:  m0025 ──about──▶ x0001
    tag 归一: "#entity:sensei" → "#entity:老师"（主名）
    解析不到 ⇒ tag **原样留着** + 账上记 strangers=<名字, …>

entity 节点 = 身份:  name（主名）+ aliases（别称）
                    ⛔ text/state 字段留着但**没人写**（等它有读者）

"她对某人的看法" = belief（+ 它的 #entity: tag）
                    ✅ 注入（认知列表已经在注入 belief）
                    ✅ 进化（evolved_from: 新看法 → 旧看法）
                    ✅ 召回（belief 本来就在召回候选里）
```

**为什么这样切**：`about` 的语义是"**这条涉及谁**"（tag 口径，一条最多 2 个 ⇒ 她必须挑），
而"**X 的故事**"要的正是这个口径（提到过他的那些时刻），**不是**"主要内容是关于他"。

---

## 4. 语法：`#entity:<名字>`

| 项 | 定法 |
|---|---|
| 形状 | `#entity:` + 名字（名字 = 她认识的任何叫法：`老师` / `sensei` / `tama`）|
| 写在哪 | `episode.tags`（R1）· `belief.tags`（L2，**新增一个可选字段**）|
| 额度 | **不占** tags 的 1~4 个检索词额度；`#entity:` 自己**上限 2 个** |
| 形状坏 | `#entity:` 后面空名字 ⇒ **丢那一项** + `drops` 记账（parse 层，纯字符串）|
| 解析 | **执行层**（有 store）：命中 ⇒ 归一成**主名**；未命中 ⇒ **原样保留**（那就是陌生人线索）|
| 旧档兼容 | 没有 `#entity:` 的节点照旧（tag 缺席 ≠ 错误）|

---

## 5. 谁在什么时候做什么

| 步 | 谁 | 动作 | 备注 |
|---|---|---|---|
| R1 `record` | LLM | 写 `episode.tags`（可含 0~2 个 `#entity:`）| 判**一次** |
| — | 引擎 | 解析 tags ⇒ 落 `about` 边 + 归一 tag | 零 LLM |
| L2 `cognize` | LLM | 写 `belief`（可含 `#entity:` tag）| 印象就在这里 |
| L1 `relate` | LLM | ⛔ **删掉 `about` 动作**（5 → 4）| 见 §7 红账 |
| R3 `attribute` | LLM | **只认人**：`new_entity {name, aliases, reason}` | 零正文 |
| — | 引擎 | R3 建完 ⇒ **回头补边**：重扫本段 tags，现在能解析的落 `about` | 零 LLM，同段闭合 |
| R3 的 skip | 引擎 | **有解析不到的 `#entity:` tag 才跑** | ⇒ 没有新人 ⇒ **0 次调用** |

---

## 6. 被否掉的三条路（判据 + 出处）

### 6.1 ⛔ 印象放 `entity.text`（本文件取代的旧设计）
- 没有读者（注入四桶里没有 entity）；每段重写要防漂（要 `reason` 门槛、要观测"每段改几个"）；
- 而 belief 三件事**全都现成**（注入 / `evolved_from` / 召回）⇒ 零新增机制。

### 6.2 ⛔ 印象放 note
`core/brain/notes.py` 的退役判据原文（两槽各一条）：
> **`on_mind`**：判据不是"零读者"而是**时间尺度**……一旦写下来, 引擎就会在每一轮把它重新念给她听
> （常驻注入）,**情绪因此被冻在过去**。
> ⚠️ 将来若真需要"她此刻在想什么", 该走的是 **`belief`（有图、有边、能被召回、会随新经历更新）**,
> 不是在 note 里再养一个形状特殊的槽。

> **`habits`**：它是"规律"的**劣质替身**……**与 belief 重复** ⇒ 内容归 **L2 的 belief（模式句）**。

⇒ 印象是**活的东西** + note 是**常驻注入**的 ⇒ 放进去就是"把印象冻在过去"（同 `on_mind` 的病）。

### 6.3 ⛔ 不挂边、只靠字面命中（正则兜底）
真机实测字面命中 **21/21 恒真**（"老师"遍地）⇒ **零区分力**，只能当"扩大候选"的信号。
⇒ 边要有，但要**由声明派生**（§3），不要 LLM 再判一遍。

---

## 7. 旧数据与顺带修的红账

- **旧的 22 条 `about` 边留着、不回填**（它们是历史；把边反写成 tag 才是"把派生当真源"）。
- **entity 的 `text`/`state` 字段留着**（不删、不写）。
- ⚠️ **红账（P7-2 的漏印）**：`ROUNDS` 里 `relate` 的 `writes` 只列了
  `("supports","akin","contradicts","about")` —— **漏了 `evolved_from`**（P7-2 加的动作），
  而守门 `test_l1_writes_edges_only` 把这个漏印**固化成了判据**（断言恰好那 4 条）。
  ⇒ 随 E3 一起修：删 `about` 之后改成 `("supports","akin","contradicts","evolved_from")`，
  守门同步改判据（**先验能红**：改前把 `evolved_from` 拿掉 ⇒ 守门必须红）。

---

## 8. 不做的事（⛔ 都写了判据）

| ⛔ | 判据 |
|---|---|
| **不强制归属** | 契约从来没有覆盖要求；`about_state` 三态**已退回未定**（"判不出就别建边, 也不追踪"）。tag 也是 0~2 个，拿不准就不写 |
| **不给 entity 写正文** | 没有读者；写了就是"只增不并"那条老路的翻版 |
| **不让 R3 写看法/印象** | 印象归 belief（§6.1）⇒ R3 只有一个动作 |
| **不做 NER** | 引擎算不出"陌生称呼"⇒ 那是 LLM 的活（R3 读正文 + tag 线索） |
| **不建"人物关系图"** | 多人模式的那一页（"她与 X 的往事"）等**真有读者**时再做，用 `lane()` 现成查询 |
| **不删 `parse_attribution` 的老代码** | 它里面的 `new_entity` + `reason` 门槛 + `MAX_ALIASES` 直接复用（E4）|

---

## 9. 施工表

| 节点 | 内容 | 落点 | 验收 | 依赖 |
|---|---|---|---|---|
| **E1** | ✅ **已落地**（2026-10-08）| `#entity:` 语法：parse 形状（空名字丢项）· 执行层**落 `about` 边** + 归一 + 陌生保留 + 账 `strangers=` · R1 的契约/prompt（翻掉"别写关于谁"那条裁决）| `contract/digest_registry.py` · `core/brain/entities.py`（`find_entity` / `normalize_entity_tags`）· `core/digest/episodes.py`（`_link_about`）· `llm/prompts/digest_record.md` | 真机只读: **22/22 种叫法解析回自己** · 口径差 48%→100% · `test_entity_tags.py` 11 例 · **7 变异全红** · 三板块 1290 passed | — |
| **E2** | ✅ **已落地**（2026-10-08）| L2 的 belief 行加**可选 `tags`**（同一套 `#entity:` 语法）⇒ 引擎归一并落 `about(belief → 对象)`；`_split_tags` 的记账文案参数化（`where=`）| 同上契约 + `_clean_belief` · `core/brain/revise.py`（`_create_belief` + `CognitionResult.strangers`）| 真机依据: belief 的 `subject` 已漂成"主题句"（**4/4 条解析不到 entity**）⇒ 看法确实缺地址槽 · 6 例守门 · **5 变异全红** | E1 |
| **E3** | ✅ **已落地**（2026-10-08）| **删 L1 的 `about` 动作**（5 → 4）+ 修 §7 那笔红账 + prompt/守门同步；连带收干净同一个死因: `parse_relations` 的 `entity_ids` 参数与 about 那一档 · L1 料的【候选对象】栏 · `RELATION_ANCHORS` 的 `"entity"` | `contract/digest_registry.py` · `rounds/__init__.py` · `rounds/relate.py` · `material.py` · `digest_relate.md` | L1 的 `writes` = 4 条边（含 `evolved_from`）· **5 变异全红**（含变异逼出的一条真缺口: "编造 id 整包拒"原来只测了锚点那一端）· 三板块 1295 passed | E1 |
| **E4** | 恢复 R3 = **只认人**（`new_entity`）+ **建完补边** + skip="有解析不到的 tag" + 观测一行 | `rounds/attribute.py` · `rounds/__init__.py` · `revise.apply_attribution` | 先验能红：新人建得出 · 补边落得上 · 老对象不重复建 · 无陌生人时 **0 调用** · 变异 5 条 | E3 |

**观测行**（E4）：`digest_attribute cands= strangers= new= edges= skipped=`（可 grep）。

---

## 10. 风险与代价（都不藏）

1. **口径变宽**：`about` 从"主要内容是关于他"变成"她声明过涉及他" ⇒ `lane()` 查出来的东西更杂。
   换来的是覆盖率 **48% → ~100%**，而"X 的故事"要的就是宽口径。
2. **tag 与边可能暂时不一致**：她在同一段先写 tag、R3 补边 —— 中间那一刻"tag 有、边没有"
   （那是**预期**：边是派生，进度落后于声明）。**读侧要认这个窗口**（查询以边为准 = 保守）。
3. **她可能滥用 `#entity:`**（在正文里写、或给不相干的东西挂人）⇒ 契约写死额度与判据 + 账可查。
4. **`tags` 里混进结构**：检索词那一栏与 `#entity:` 一栏必须**分开计数**（parse 层），
   否则 4 个额度会被结构挤掉（检索质量下降）。
5. **E4 之后 R3 是"偶发轮"**（几十段才跑一次）⇒ 它的失败自吞（`own_snapshot=True`）与
   真机可见性要靠那行观测账确认。
