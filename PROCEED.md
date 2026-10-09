# PROCEED.md — **接续用**（整篇覆盖写；上一版 2026-10-05 → 2026-10-08 的会话见 git 历史）

> 头一版写在 **2026-10-08**。这一段会话干完两条线：**两趟（P6–P11）** 与 **entity（E1–E4）**，
> 两条都已收口并提交（§3）。
> ⭐ **现在停在这里**：正在讨论 **① note 的形式** 与 **② 召回策略**（§1.1/§1.2）——
> 两条都**还没动代码**，上下文压缩后从这里接着谈。

---

## 1. 下一步该怎么做

### 1.1 ⭐⭐ **正在讨论：note 的形式**（未决，最重要）

**用户 2026-10-08 的定性（这是判据，别再搞错）**：

> **note 本质上是"更精确、更具体的 episode"**（例：*"星期天的时候记得一定要来找我"*）
> ⇒ ⛔ **不能并进 `belief`**（belief 是"简短但描述性的**模式句/结论**"、**没有时间性**；
> 约定是**一件有期限的具体的事**）。

**用户的方向**：**note 打 `#note` 标记** · **在 episode 上按一个 `active`** ·
**R0 不更新 note，只指定"这一笔要不要更新/结清"，细节交给 R1**。

**我在这条上错过一次（留档免得重犯）**：我提过"约定 = 一条 belief + `#note` 标记，
`notes.py` 整族退休" —— **被用户否掉**（理由见上：belief 承载不了时间性/具体性）。

**已经查清的事实（可省一轮读码）**：

| 项 | 现状 |
|---|---|
| 真源 | **事件流的 note 操作**（`add` / `close` / `update`）；`soul/notes.json` 是**派生缓存** |
| 一槽 | `pinned`（"她随身带着的事"= 誓约/重大约定；2026-09-29 由 `promise` 改名并**收紧判据**）|
| 条目 | `NoteItem(id="n1", text, refs, since, due)` —— ⚠️ `id` 是 note **内部**计数器，**图里不存在** |
| 谁写 | **R0 判账目**（一行五键合一的表：`span`/`abstract`/`state`/`id`/`due`）⇒ **R1 照抄成 op**（`_ledger_ops`）|
| ⭐ 正文 | `state="open"` 那一行的 **`abstract` 就是 note 的正文**（契约原文：*"就是她带走的那句话"*）⇒ **"交给 R1 填写"今天是重复写** |
| `state` 稀有度 | 契约原文：*"其余**一律省略** `state` —— 这是绝大多数"* ⇒ **账目是稀有事件**（别把它当主流程）|
| `open` 兼两件事 | ① 新开一笔 ② **更正**（"日期后来才知道"⇒ 同一行 `open` + `id` + 新 `due`）|
| `close` 两形态 | 有那一刻（`span` 指那一刻）/ 没有那一刻（`span: null` + `abstract` = 那条回忆的正文）|
| `#pinned` | **已经由 R0 的 `state=open` 派生**（`record.py::_tag_pinned` 打在**出生那条** episode 上，幂等）⇒ "标记驱动"**今天已经是一半** |
| `close` 的语义 | 2026-10-05 裁决：**"本子 = 当前抽屉，不是账簿"**（划掉即移除；两段式合并成一步）|
| 注入面 | 常驻 `【你自己记的备忘录】`（bond 开场 / MMT system 尾，**0 LLM**）+ refs 印名字 |
| 历史裁决 | ⚠️ `promise` **节点 2026-09-29 退图**（原话：*"承诺太轻, 不足以长期记录"*，连 `from`/`to`/`formed_by` 三条边一起删）· ⚠️ "**备忘录不进图**"（`notes.py` 明文）|
| `notes.py` | **756 行**（槽/上限/`fold`/`PINNED_TAG`/`_LEGACY_SLOT`/派生缓存/事件流 op）|

**要用户裁的（我的下一问，别自己先动手）**：

1. **note = 一条 episode**（它出生时就是 R1 造的那条 ✓ 今天 `refs` 就指它）⇒ 那么 `active` 落在**那条 episode 上**？
2. **`active` 的载体**：episode 上加**可选布尔字段**（新字段，`nodes.py` 的 `_REQUIRED` 不必动）还是用**标记**（`#note` 在 = 开着）？
3. **`due` 放哪**（今天在 note 上 ⇒ 若 note = episode，则要 episode 上一格）
4. **注入面**：仍单独分小节（按 `#note` 过滤）还是并进 episode 河（按时间排）？
5. **真源**：note 操作继续住事件流，还是落 episode 的字段（⇒ 图上）?
6. **`notes.py` 整族**：退休还是留一槽？（这是"契约简化"的真身 —— 不退休就只是"多一个形态"）
7. ⚠️ **两条既有裁决要签字**：`promise` 退图（当年嫌"太轻"，今天要的是"可指认/可召回"——**理由变了**）· "备忘录不进图"

**另外两条我上一轮提过、被别的话题盖过去的**（都还没做）：
- ⭐ **note 接召回**（今天笔记只有常驻注入一条路；note 有 `refs` ⇒ 可按相关度进【你想起的事】）—— 这条**与 note 是否节点化无关**，可以先做
- ⚠️ **`#entity:` 契约还缺三条**（E1 的尾巴，未补）：① **禁令**："检索词**不要**以 `#` 开头"（否则检索侧 `startswith("#")` **静默跳过**）② "`#entity:` 只能是**人/地方/东西**（不是心情、不是话题）" ③ **反例**："只是顺口提到、或一群人里露了一下 ⇒ 不写"（L2 的 `belief.tags` 那格同补）

### 1.2 ⭐ **正在讨论：召回策略**（R0 已跑，R1 待做）

**用户已经裁的三条**：**常驻注入要 cap** · **超出的 episode 以「标题」形式呈现** ·
**上限别太小**（还有 LLM 主动查询兜底，但防上下文过长）。

**R0 只读探针的实测（真机 haruka；`.testtmp/probe_recall_r0.py`，不写盘、不调网络）**：

```
常驻全量 = 5204 字符 / 30 行   （episode 21 条 3218 字 · belief 4 条 418 字 · player/reported 0）
  cap= 8 → 全文 ≈1739 + 标题清单 ≈124  ⇒ 约 1863 字（−64%）
  cap=12 → 全文 ≈2178 + 标题清单 ≈ 86  ⇒ 约 2264 字（−56%）  ← 建议起点
  cap=20 → 全文 ≈3626 + 标题清单 ≈ 11  ⇒ 约 3637 字（−30%）
⭐ 「标题清单」极便宜（9~13 条只花 86~124 字 ≈ 全文的 1/20）

sig 的区分度（用户的判断被证实）:
  episode 21 条 [0.9, 0.9, 0.85×7, 0.75, 0.72, 0.7×2, 0.62, 0.6×3, 0.55×4, 0.5]
          ≥0.8（珍贵档）8/21 = 38% · 极差只有 0.40  ← 光 0.85 一档就占 7 条
  belief  4 条 [0.97, 0.95, 0.92, 0.75] ⇒ 珍贵档 3/4
  ⚠️ 按 sig 截断时**最近的 m0024 出局**（cap=8/12 都出局）⇒ "新的低 sig 记忆永远进不来"被证实

⚠️ 两套召回在 digest 场景下都几乎不可用:
  compose.recall_now: 四条链路**降级三条**（无 emo_now / 无 place_now / 无 embed_fn; E 未立项）
                      ⇒ 四个查询只有 1 个出了 1 条
  recommend_candidates(embed_fn=None): **四个查询全空**（不是"退化成字面", 是空）
```

**R1 的清单（我提的，待用户点头）**：
1. **cap + 标题清单**（cap=12 起步；超出的 `《标题》` 一行一条）
2. **排序换混合分**：证据轴（新鲜度 + 字面/语义 + 结构：被引/边）+ 先验轴（**sig 只做加成**）⇒ sig 不再决定谁进来
3. **豁免**："她明确在意的东西"（**未结清的账** / 被引高 / 约定）不参与置换
4. ⭐ **降级要能用**：无 embedder 时用字面 + 新鲜度 + 结构出分（**⛔ 不能是空**）
5. **台账一行**：这次注入了哪 12 条全文 / 哪几条只出标题 / 各自的分（可 grep）
6. **note 接召回**（见 §1.1 末）

**方案骨架（用户原则："统一写一个节点召回包"）**：
```
recall(store, query) -> RecallPack        # 一个入口, 四种查询 + 融合分
query = { text, anchors, time, want }     # want ∈ 想起的事 / 同类的事 / 关于某人的 / 默认(无 query)
消费者: MMT P19(2 条) · 常驻装填(默认查询) · L1 的认知/经历候选 · L2 的群候选(可选) · note
⛔ 不做: 向量库/索引 · 每轮全库重算 · 动 fuse.MODES(那是代码选项)
```

### 1.3 真机验收（用户自己做；**E1–E4 之后这一环还没有过**）

跑一段（或玩一章）⇒ 看这几行（可 grep）：
```
digest_record strangers=N（还没建的人）
digest_relate rows= rels= alone= lone= cands= pool= dropped=
digest_cognize rows= beliefs= reused= edges= soaked= dropped= strangers=
digest_attribute strangers= rows= new= linked=      ← 稀有（只在有陌生名字时）
```
**E1 的只读验证已经过了**（`.testtmp/probe_entity_names.py`）：真机 4 个 entity、
**22/22 种叫法解析回自己**、口径差 **48% → 100%**。缺的是"跑一段真数据"。

### 1.4 用户明确**押后**的

收尾板**名字牌 + 特效** · `[llm].reasoning_effort` 低档对照 · `start.ps1` 加 `lms load`。

---

## 2. 必读文件（路径 + 为什么）

| 文件 | 为什么必须读 |
|---|---|
| `CLAUDE.md` | 项目主文档。⚠️ 已知过期几处（§3.3 "MMT 每 25 轮"真值 **40** · §7 "R2 的动作面…`links`" · §3.1 槽位表的 **P16**）—— **用户自己手工同步**（编辑它会触发全文重注入） |
| `docs/DESIGN_ENTITY_TAGS.md` | ⭐ **entity 线的规格（E1–E4 已全落地）**：`tag 是输入 · 边是派生 · entity 只存身份 · 印象是 belief`；§7 = 红账；§9 = 施工表 |
| `docs/DESIGN_DIGEST_TWO_PASSES.md` | 两趟规格（§9 = L1 契约；⚠️ 其中 `about` 那一节 **E3 起标成历史**）|
| `docs/TODO_TWO_PASSES.md` | 两趟施工表（P0–P11 状态）+ 测试纪律；§4 指向 entity 那条线 |
| `core/digest/rounds/__init__.py` | ⭐ **轮次表 = 步序/LLM 身份/prompt/相位/parse/料/写什么/跳过/预算/快照 的唯一真源**（改 digest 先读它）|
| `core/brain/notes.py` | note 的全链（槽/纪律/派生/注入面）—— 讨论 note 形式时的第一手材料 |
| `core/brain/read/{channels,compose,recall}.py` | 召回：四链路 + 两轴 + 融合（`compose`）+ P19 在用的 `recommend_candidates` |
| `.testtmp/probe_*.py` | 我这一段写的**只读探针**（`probe_entity_names` / `probe_recall_r0` / `probe_belief_subject` / `probe_l2_material` …）；**不是产品代码**，可删 |

---

## 3. 已做的更改（这段会话；每笔都有守门 + 变异验红）

**两趟（P6–P11，`docs/TODO_TWO_PASSES.md`）**

| 提交 | 一句话 |
|---|---|
| `360b303` | **P6** L1 的观测账（`rows/rels/alone/lone/cands/pool/dropped`）—— 探针抓到真 bug（校验写进了只认 `akin/contradicts` 的 if）|
| `d0775af` | render 的 docstring 改对（认知列表收 belief/profile；`experience` 不进它）|
| `d54e55c` `466b641` `daff2f8` | **P7** L2 契约（三档 + 九条硬规则）· L1 第五个动作 `evolved_from` · 文档同步 |
| `8c814ef` | 召回第三条判断记档（`TODO_TWO_PASSES §1.5`）|
| `fa0c3cb` | **P8** L2 的料（群块 + 被连块；真机样张 9/9 对齐；自测抓到"`member_of` 让归了类的经历不再孤立"的假判据）|
| `fa19e03` | **P9** L2 的执行器 `apply_cognitions`（幂等走 `_find_duplicate`；留痕照 `apply_decisions` 的 update 行）|
| `d9a2f1b` | **P10** 接线：`ROUNDS` 加 `cognize`（**与轮文件同笔**）+ prompt + 标签 + 桩；硬顶 600→720 |
| `3e76157` | L2 摆 3 组 + **挑组时"没写过沉淀的先"** + `digest_cognize` 补 `dropped=` |

**entity（E1–E4，`docs/DESIGN_ENTITY_TAGS.md`）**

| 提交 | 一句话 |
|---|---|
| `dbce099` | 规格大纲（tag 是输入 · 边是派生）|
| `e1c9722` | **E1** `#entity:<名字>`：契约分栏（不占检索词额度）· 引擎落 `about` 边 + 归一 + **陌生保留** · `entities.find_entity` |
| `f3fd7a1` | **E2** 看法也能带地址（belief 加可选 `tags`）—— 真机依据：`subject` 已漂成"主题句"（4/4 解析不到 entity）|
| `09ef18c` | **E3** 删 L1 的 `about`（5→4）+ 修 `writes` 漏印 `evolved_from` 的红账；连带删 L1 料的【候选对象】栏 |
| `f11883a` | **E4** R3 恢复成**只认人**（`apply_entities`）+ **建完补边**（`link_entity_tags` = 落边的唯一实现）+ skip="有陌生 tag"（**没有新人 ⇒ 0 调用**）|

**验证口径**：`tests/core`+`llm`+`webgui` **1288 passed** · 每个节点的变异**全红** ·
E1 的真机只读探针 22/22。

---

## 4. 隐形坑（踩过的、容易误判的）

### 4.1 ⭐ 这一阶段新踩的（digest/契约）

- ⛔ **改契约文案必须同批改"示例"** —— 示例才是形状的来源；`digest_*` 的 prompt 与契约**两处同批**改。
- ⛔ **`pipeline.IMPL` 的键序被守门钉住**（"与表同序同集"）—— 动了 `ROUNDS` 的顺序要**同步动 IMPL 的字面顺序**
  （E4 就是被这条当场抓住的）。
- ⛔ **代码字面量里零手写 `《》〔〕｜`**（`tests/core/test_marks_guard.py`）—— 用 `marks.head/name/FIELD_SEP`。
- ⛔ **L2 的"被连过的经历"取自 `RELATION_ACTIONS`**（L1 的动作面）⇒ **动 L1 的动作面会改 L2 的行为**
  （E3 删 `about` 之后，只带 `#entity:` 标记的经历重新算"孤立"⇒ 那一段 L2 跳过）。
- ⛔ **桩不认识 `task` 就炸**：新增一轮要同时补 `tests/stub_tasks.annotation_reply` + **各处自造桩**
  （P10 补了 5 处；⛔ 别靠"这次恰好跳过"）。
- ⛔ **`entities.py` 是"输入侧"，不写边**（写路径在 `revise` / `digest.episodes`）；`brain` **不许 import `digest`**（分层）。
- ⚠️ **`sig` 在真机上没有区分度**（见 §1.2 的数字）⇒ 任何"按 sig 排序/截断"的设计都要先量化。
- ⚠️ **写 Python 补丁脚本时：`print("…"…"…")` 里嵌引号会让整个脚本 SyntaxError**（本会话连踩三次）——
  中文引号用「」，或先 `ast.parse` 自检。

### 4.2 测试/回归
- **`--basetemp` 必须预建目录**（Windows；本会话用 `.testtmp/pw_p10`，可复用）——否则全部用例 `PermissionError`。
- **不许频繁跑全量**（用户硬规矩）；按板块跑；**改到一半的树不跑回归**。
- **每新增一条判据都要跑变异验红**（`python .testtmp/verify_*_red.py`）；⛔ 假绿比没测更糟
  （本会话 3 条假绿被变异逼出来）。
- 改**进 system 的内容**（盒A/盒B 相关）⇒ 必须刷夹具：`PROMPTKIT_UPDATE_FIXTURES=1 pytest tests/core/test_promptkit_baseline.py` + 人工审 diff。
  （digest 的 prompt 与契约**不在**盒A/盒B 里 ⇒ 不触发夹具。）

### 4.3 冒烟（B 层, `python experiments/web_e2e/run.py`）
- 桩的 `MMT_CHAT` **整段一次喂**（分行喂会让节奏判据随机红绿）；节奏判据 = **maxGap ≥ 800ms**。
- 背景守门的窗口靠 `STUB_PLACE_LAG_S=4.0s`（> 标题屏 2.4s）+ switch 文本**不命中层1 关键词**。
- 背景时间线用 **MutationObserver**（轮询采样会漏）。
- `tests/webgui/conftest.py` 把链式钉回旧节奏（`_READAHEAD_MIN_BOARDS=1`）；验链式自己 monkeypatch 成 4。

### 4.4 前端（bond.js / mmt.js）
- 守望/轮询判"板还在不在"用**内容指纹**（`sceneKey`），⛔ 不用 `round`（交付后才 +1 ⇒ 首板必然假推进）。
- 纪念窗口里**不许补切板级背景**；补切只做一次不够（退纪念会把陈旧快照贴回来）。
- "对方正在输入…"**永远贴末尾**；`running=false` 时队列没放完**不许收摊**。
- 一行 = 一个气泡；节奏常量在 `mmt.js` 头部，CLI 真源 = `core/tui/streaming.py`。

### 4.5 环境/本机
- `lms server start --port 1235`（**必须显式端口**；`[embed].model` 钉死 `text-embedding-qwen3-embedding-0.6b`）。
- LM Studio 空闲后第一次请求 **~2.2s 唤醒**（之后 13~25ms）⇒ "TTFT 变慢"先看这个。
- 删东西**只指定路径、不用通配符**；只在工作目录内部删。
- 真机数据：`data/worlds/world1/characters/{igusa_haruka,asagi_mutsuki}/soul/`
  —— **本会话所有写操作都在副本上**（`.testtmp/`），真 `data/` 未动；`git status` 一直干净。
