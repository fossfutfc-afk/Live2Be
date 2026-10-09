# PROCEED.md — **接续用**（整篇覆盖写；上一版 2026-10-05 → 2026-10-08 的会话见 git 历史）

> 头一版写在 **2026-10-08**。这一段会话干完两条线：**两趟（P6–P11）** 与 **entity（E1–E4）**，
> 两条都已收口并提交（§3）。
> ⭐ **现在停在这里**：正在讨论 **① note 的形式** 与 **② 召回策略**（§1.1/§1.2）——
> 两条都**还没动代码**，上下文压缩后从这里接着谈。

---

## 1. 下一步该怎么做

### 1.1 ✅ **已裁决：note 的形式 —— 暂缓**（2026-10-08 晚，用户原话"改的理由确实不多了"）

Node 化的收益只在"**要按对象/按类查 note**"（"关于老师的未了事"）时才兑现；代价是一个新 kind
的整套配套。这一轮把四条事实查实了，所以**不改**：

1. **省不了契约** —— `abstract` **本来就不是 note 的成本**（R0 对**每一行切片**都要写它，note 只是
   复用它：契约原文"`state=open` —— 就是她带走的那句话"）；真正属于 note 的只有 `state`/`id`/`due`
   三格（且"其余一律省略 state —— 这是绝大多数"），节点化后 `due` 还要另找家
   ⇒ **净省 ≈ 一格，甚至略长**（多一个 kind 的定义 + 两个 tag 的语义）。
2. **`refs` 是引擎推的**（`rounds/record.py::_ledger_ops`：R0 给"第几件切片" ⇒ R1 映射到本段那条
   episode ⇒ `refs=[ep]`，`src=ep` 兼作 add 的**幂等键** `notes.ALREADY_PINNED`）—— ⛔ **不是 LLM 写的**
   ⇒ "按 `refs` 召回"的地基可靠。
3. **出生时 `refs` 为空：不可能** —— 唯一调用点被 `if not (text and ep)` 挡住，挡住时**进 `lost_kept`
   账 + warning**（`digest_record 'state=open' 有 N 条没长成 note（约定丢了）`）；下游还有三道闸
   （`_apply_add` 跳过 + warning · `note_event` 严格读报错 · `check()` 不变量①告警）。
4. **结清不丢痕迹** —— 事件流两条 op（append-only）+ **图里两条经历**（出生那条 + 结清那一刻那条；
   "没有那一刻"的经历其 `abstract` **就是结局正文**）；只有常驻视图消失（设计意图"本子=当前抽屉"）。
   ⚠️ 唯一"只剩事件流、没有查询入口"的边角 = `refs` 悬空/为空的旧档（`check()` 告警，**不是静默**）。

⚠️ **留档**：我曾提"约定 = 一条 belief + `#note` 标记" —— **被用户否**
（note 是"**更精确、更具体的 episode**"，belief 是模式句/结论、**承载不了时间性**）。
将来若真要做"按对象查未了事"，用户的意向是 **专属节点 + 两个 tag**（"是不是 note" / "是否 active"
—— 两个 tag 比合并成一个好：正交的两件事）。

### 1.2 ⭐⭐ **主攻：召回**（形状已定；第一笔未开工）

#### 两个类（用户 2026-10-08 裁："一个包、正好分为两个类"）

| | **定向寻找 `find`** | **相似召回 `like`** |
|---|---|---|
| 输入 | 一个**锚**（名字 / 对象 / 类 / 时间 / 轴 / 关系）| 一段**情境**（玩家那句 / 本段经历）|
| 输出 | **全部**符合的（漏一条即错）⇒ ⛔ **不 top-k** | **最像的 k 条**（顺序即答案）|
| 找不到 | 必须**明说"没有"** | **正常**（没想起来）|
| 分数 | 只是展示顺序 | **就是答案** |
| 后端 | ⛔ **不需要**（确定性）| 需要，**但必须有降级** |
| 对应动作 | ⭐ **`look`**（规格已存在，见 §2）| P19 · 常驻装填 · digest 各轮 |

#### 先做 `like`（用户裁）。落法 = **不复用资源，可适当移动**

- ⛔ **不 import `compose` / `recall`**（旧件保持**零调用**，将来整体删）；它们就是病根
  （`compose.recall_now` 在 digest 场景**四链路降级三条**；`recommend_candidates(embed_fn=None)`
  **四个查询全空**）
- ⭐ **搬**三块算法进新模块：`compose` 的"证据轴归一 + **名次门槛**" · 两轴分派（**先验轴原样不归一**）
  · `channel_impl` 的**时间衰减**（half_life + floor）
- ✅ `core/common/fuse.py` 是**通用工具**（不是旧召回资源）⇒ 照用
- 新件：`core/brain/read/pack.py`（`Candidate` 协议 + `render_candidates` + `ledger_line`）·
  `core/brain/read/like.py`（`like()` + `_lexical`/`_temporal`/`_prior` + `_normalize`）；
  将来 `read/find.py` 接 `look` 的执行器
- 旋钮进 `recall_config.py`（真源）：`like_k` · `w_lex`/`w_time`/`w_prior` · `half_life`/`floor` ·
  `w_sem`（先留 0）

**第一笔** = `pack.py` + `like.py` 的 **M1 字面 / M5 时间 / M6 先验**（三条**都不依赖后端**）
+ 5 条守门 + 5 变异 + 只读探针 `.testtmp/probe_like_r0.py`（真机四查询：`like` vs
`recommend_candidates` **并排** —— 这次不会再是空）。
**第二笔** = M3 结构一跳 + M4 轴（接 digest L1 的料）· **第三笔** = 接 **P19**（替换
`recommend_candidates`，**同句旧 vs 新**对照）+ 台账接 `mmt_recall`。

⭐ **5 条守门要点**（都要先验能红）：
① **无 embedder 也必须出结果**（打"返回空"那个病根）② 字面三路（tags / title / **别名**）
③ 时间衰减 + **floor 不归零** ④ ⭐ **先验只做加成**（造"高 sig 但毫不相关"的节点 ⇒ **不许压过字面命中**）
⑤ **import 黑名单**（`like.py` 不许 import `compose`/`recall` —— 把"不复用"落成可执行约束）。

#### 实测底数（R0 只读探针 `.testtmp/probe_recall_r0.py`，真机 haruka）

```
常驻全量 = 5204 字符 / 30 行（episode 21 条 3218 字 · belief 4 条 418 字 · player/reported 0）
  cap= 8 → 全文 ≈1739 + 标题 ≈124 ⇒ 约 1863 字（−64%）
  cap=12 → 全文 ≈2178 + 标题 ≈ 86 ⇒ 约 2264 字（−56%）   ← 建议起点
  ⭐ 「标题清单」极便宜: 9~13 条只花 86~124 字（≈全文的 1/20）
sig 无区分度: episode 珍贵档(≥0.8) 8/21 = 38%（光 0.85 一档占 7 条）· belief 3/4
  按 sig 截断 ⇒ **最近的 m0024 出局**（"新的低 sig 记忆永远进不来"被证实）
```

**用户已裁三条**：常驻**要 cap** · 超出部分**只出标题** · 上限**别太小**（有 LLM 主动查询兜底，
但要防上下文过长）。
⭐ **配对关系**：**cap + 标题清单 + 主动查询（`look`）是一套三件** —— 没有主动查询，cap 就成了
"看得见标题、摸不着内容"。

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
| `docs/DESIGN_MMT_NEW_ACTION.md` | ⭐ **`look`（主动查询）的完整规格**: §2 `when` 语法（只留 `back`）· §3 三级解析 / 权限 / 返回形状 / **空结果两种说法** · §7 裁决（与 `inspect` **合并**、`chapters`/`note` 并入、一轮预算 2）。⚠️ 它的解析半边**已落地**（`address.normalize_title`/`find_episode` + `entities.find_entity`）|
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
| `865497b` | **E1b** `#entity:` 判据补全（新认识的角色必须写 · 跨时间段反复出现 · 不写抽象/司空见惯 · >5 不建议再加）+ ⭐ **防 alias**（【已有的对象】进 **R1/L2 的料**）+ `#` 开头的检索词**记 warning**（不再静默丢）|

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
