# PROCEED.md — 接续用（**整篇覆盖写**；上一版见 git 历史）

> **树干净 · `ahead 44`（没 push —— 推不推由用户定）**。真实头看 `git log -1`。
> 现状：`tests/core` **1253 passed** · `tests/webgui`+`tests/llm`+`tests/renderer` **196 passed**
> （⚠️ **按域分开跑**，理由见坑 4.25）· 三个 verifier 全 exit 0。
> ⚠️ **这棵树里有两条线**，别混：**线 A = 记忆层重新设计（本会话主线）** ·
> **线 B = 包重组（另一个 agent 做的 1a/1c/1d/1f，1e/1h 等他拍板）**。
> 上一版（`4adc7f7`）把线 A 的四件写成"设计已定、代码未落"；**现在四件里落了三件**。

---

## 0. 三十秒概览

**线 A（本会话）**：记忆层从"写侧造容器"改成"**写侧只写地址、引擎物化、内容归 LLM**"。
- 已落：① brain 段那块 = **「我知道的名字」** ② 名字匹配 **空白不敏感**（`entities.form_key`）
  ③ 台账 `mmt_recall` 的 `per=`/`ms=` ④ 真机观察脚本 ⑤ **group（L2-a）退役**（整族搬 `archive/digest_group/`）
  ⑥ **`experience` 的沉淀行停产**（认得出、丢行、⛔ 不判非法）⑦ ⭐ **`attribute` → `settle`** 改名 +
  扩职（认人 + **改名 / 写看法**）+ 执行接线 + **`text_seq` 水位** ⑧ ⭐ **引用从 `tags` 搬进独立字段 `entity`**。
- **只剩一件没落**：⭐ **akin 共 belief**（见 §1A-1，形式已定稿，等一句"开"）。
- 之后再收：`topics` 退役 · belief collision 的其余两条。

**线 B（另一 agent）**：把"缝补出来的项目"改成正常 Python 项目的形状。已做 1a/1c/1d/1f；
**1e（`contract/schema.py` 外移）与 1h（调用层归位）等他拍板**（岔路见 §1B）。
目标形状（已定）：`contract/`（零项目内依赖）· **新建 `infra/`**（paths/errors/atomic/fuse/时间）·
`llm/` · `engine/`（← 现 `core/`）· `tui/`（← 现 `renderer/`+`core/tui/`）· `cli/`（← `apps/`）·
`docs/{design,spec,archive}/`。

---

## 1. 下一步该怎么做

### 1A-1 ⭐⭐ **下一件：akin 共 belief**（形式已定稿，动代码前先报形式给用户）

**判据（用户 2026-10-13 裁）**：group 死后"一类事"没了载体 ⇒ **让 `akin` 继承它的活** ——
"akin 连的东西在 belief 创建之初就生到一起"。

- **写侧**（`revise.apply_cognitions` → `_create_belief`）：建完 belief、落完**她给的** `supports`
  之后, 把**每条已落证据的一跳 akin 邻居**并进 `supports`（零 LLM、纯图算）:
  - ⛔ 三个坑：① **先落 supports 再算邻居**（否则没有起点）② `akin` 是**对称边**
    （`add_edge` 内部 `canonical_for` 归一存储方向）⇒ **`edges_from` + `edges_to` 双向查**
    ③ **排除集**：与这条 belief 已有 `contradicts` 的、以及互相打架的证据对 —— 否则会并出
    **自相矛盾的证据面**（用户选的就是"一跳 + 排除已矛盾的"）
  - 上限 **5**（用户定的数；真机那个 akin 簇正好 5 条）; 台账加一格 `akin_joined=N`
- **料侧**（`material._l2_material`）：group 退役时撤掉的那一格【本段归类的群】**换成
  「她认过的相似簇」**（本段经历的**一跳 akin 邻域**，带轴与时间）—— 她这才写得出"覆盖这一类"
  的结论; ⭐ 顺带把**老经历重新变成可引用**（今天 `evidence_ids` 只剩本段被连过的经历,
  老经历一条都引用不了）。
  ⚠️ 簇的标签怎么算: 她写 `akin` 时的**轴词 `on` 只落在 `evolution.jsonl`、不在边上**
  （`Edge` 只有 `rel/src/dst/ts`）⇒ 要印就**现算两端 `topics` 的交集**（与 `parse_relations`
  的校验同源）。⚠️ 若先做 §1A-3（`topics` 退役）这一步就要改口径 —— **建议先做这件**。
- **记着那条副作用**（已裁"接受"）：并进去的边与"她自己认的证据"在图上**同形**，事后只有
  那一行日志分得出; 她的「被引 N」（= `supports` 入边数）会因此变大 —— ⚠️ 只影响**她的读数**,
  ⛔ 不影响引擎决策、不影响召回、不进 brain 段（`_belief_line` 不印 count）。

### 1A-2 `aliases` 的写者（**记着, 还没做**）

今天 `aliases` 只在**建对象时**写一次; `settle` 改名时会自动把**旧主名**降级成别名（已落）。
⛔ **仍冻结**的是"她主动补一个**新**别名"（`{"id": …, "aliases": [...]}`）—— 并错**不可逆**
（重复建对象还能合并, 身份并错分不开）。要做先想清判据。

### 1A-3 `topics` 退役（待拍, 与 akin 的校验耦合）

`tags` 留（召回在用）; **`topics` 退役**（唯一读者是 `akin` 链: 挑候选 + 校验 `on ∈ 两端交集`）;
挑候选改走 **`like(spec="digest")`**（那个档位**写好了却零调用**）。
⚠️ **退役它会带走 `akin` 的那道校验**（只剩"两端都得是 episode"）—— 要么接受, 要么另找载体。

### 1A-4 belief collision 的其余两条（待拍）

① belief **默认综合 ≥2 条**（相似或矛盾都行）; 单点要过门槛 —— ⭐ 判据 = **"写得出一句『所以』"**
   （`DESIGN_MEMORY_MODES.md:58`：簇的代表性总结是**描述**, 不该住 belief）
② **软强制 + 允许一次显式 defer**（defer 记账）—— 完全强制会造垃圾 belief。
⛔ **已撤回的一条**（别捡回来）：~~`relate` 的 `akin` 行退役~~ —— group 死后 `akin` 是**唯一**
还活着的"同类"判断源（`noticed` 太稀, 真机全库 5 条）⇒ 退役它 = 把 §1A-1 的继承者腿砍了。

### 1B 线 B 那两条（另一 agent 的；**别替他拍**）

- **1h 调用层归位**（用户提出）：`core/digest/llm_call.py`（85 行、零 digest 依赖）**位置错了** ⇒
  搬 `llm/`（岔路：`llm/client.py` = 用户说的 **vs** 新开 `llm/robust.py` = 那份建议，因为它是
  **策略件**不是协议件）; `core/digest/call.py`（164 行）**位置对、名字错** ⇒ 只改名 `round_call.py`。
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
- ⛔ **`ambiguous` 不加机制**（用户 2026-10-13）: 真机实测**零实例**（4 个 entity 两两不撞,
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
| **`core/brain/nodes.py`** | ⭐ 节点字段真源（`entity` 引用 / `text_seq` 水位 / `kind` 五种的必填表 / `from_dict` 的**老档一次迁移**） |
| **`core/brain/revise.py`** | ⭐ 三个执行器（`apply_relations` / `apply_cognitions` / `apply_entities` + **`apply_stances` 改名与写看法**）+ `link_entity_refs`（落边唯一实现, 含"旧名降级成别名"与撞车检查） |
| `core/brain/entities.py` | ⭐ `form_key` / `surface_forms` / `find_entity` / `normalize_entity_refs` / `hit_set` / `ensure_entities` —— **名字匹配的唯一归一在这** |
| `contract/digest/`（`tables.py`/`docs.py`/`parse.py`/`registry.py`/`prompts/`） | ⭐ 契约五模块（值表/清单/校验/渲染/文案）—— `_split_tags` 认老写法就在 `parse.py` |
| `docs/DESIGN_MEMORY_MODES.md` | ⭐ 四种模式（抽象/佐证/经验/进化）+ **`akin` 原料 → 门槛(n) → belief 产出** + "簇总结不是决定" |
| `core/brain/read/render.py` · `like.py` · `modes.py` | brain 段那块（`KNOWN_NAMES_HEADER`/`_known_line`）· 六路打分 · P19 三段（`SPECS["digest"]` **零调用**） |
| `archive/digest_group/README.md` | ⭐ group 退役的**是什么/为什么/怎么复活**；点了名哪些读侧机器件**别删** |
| `.testtmp/verify_1c.py` · `capture_prompts_1d.py` · `capture_1e.py` | ⭐ 动契约/文案的三份**逐字节判据**（各自 `check`；`EXPECTED_CHANGED` 要写"为什么"） |
| `tests/core/test_digest_rounds.py` · `test_digest_contract_refs.py` · `test_entity_tags.py` · `test_round_settle.py` | 轮次表守门 · `【X】` 必须有出处 · 引用形状/老写法兼容 · settle 的十一条行为 |
| `CLAUDE.md` | ⚠️ 89 KB 且多处过时；当索引读，冲突时**信代码** |

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
| `4d978eb` | ⭐ **entity 常驻化**：brain 段那块 = **「我知道的名字」**（全体 entity、一行 = 主名 + 有看法才接 `:text`、**别名不上屏**、她自己在表尾、保留号都收）+ `entities.form_key` 铺三处 + 台账桶 → `known` |
| `5a5973e` · `593d1a1` · `3ad6e71` | 台账 `per=`/`ms=` · 真机观察脚本 `experiments/recall_report.py` · 两条新守门 + 变异靶 |
| `c7a4ac7` · `d32c8f3` | `form_key` 推广到 `hit_set` 正文扫描 · 作者缩短出厂立场句（名表 1116 → 938 字） |
| **`1478121`** | ⭐ **group（L2-a 分群）退役** —— 生产停 + 整族搬 `archive/digest_group/`；硬顶 720 → 600 |
| `4adc7f7` | PROCEED 第五版（线 A 四件 + 线 B 一节 + 坑 4.1–4.20） |
| **`9cc3d07`** | ⭐ **`experience` 沉淀行停产**：`COGNIZE_ANCHORS` 只剩 `belief` + 新增 `COGNIZE_RETIRED`（**认得出 ⇒ 丢行 + 记账**，⛔ 不判非法）；两个文案家撤掉那一半；【本段归类的群】撤出料面（守门 `test_material_names_are_not_dead` 抓到的不一致） |
| **`a85623a`** | ⭐ **改名 `attribute` → `settle`**（纯机械、零行为）: 相位/两个 md/任务标签/轮文件/日志前缀/`CLAUDE.md` 五处活文档 —— ⚠️ `revise.py` 那条日志**不在命名守门的扫描面内**（它只扫 `core/digest/**`）得手工改 |
| **`fa8c906`** | settle 的**文案 + 料**: 契约扩成"认人 + 改名/写看法" · 新增 `material.settle_objects_block`（【这一段认下的对象】+ 两个计数提示） |
| **`457310d`** | ⭐ **settle 接线**: `parse_attribution` 两路（`id` 决定建/改）· 新增 `apply_stances` · `nodes.text_seq` 水位 · skip 放宽成"谁也没提到" · `DigestResult` 两字段 · **两条判据订正**（撤销 `allowed_names` 闭环 · 空=不改） |
| **`11682ba`** | ⭐ **引用搬进独立字段 `entity`**（从 `tags` 里的 `#entity:名字`）: 老写法**认得出并挪进来** · `from_dict` 读老档时同一次搬迁 · 三个函数/常量跟着改名（`link_entity_refs` / `normalize_entity_refs` / `ENTITY_REFS_MAX`） |

**真机读数（只读探针，⛔ 全程不 save）**：haruka —— 节点 `episode 21 · belief 4 · entity 4 ·
experience 1`；边 `about 22 · supports 25 · member_of 6 · akin 5`；名表那块 938 字。
⭐ 新增读数：**30 个节点里 0 个带老写法 `#entity:`、0 个有 `entity` 字段** ⇒ 那 22 条 `about`
边是**更早的路径**落的（不是 tag 来的）⇒ `from_dict` 那条迁移在真机上**无事可做**。

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
渲染字节与别的 prompt 不同形。按行号改文件要按字节切 `\n`。
**4.12 删顶层类/函数要连 `@decorator` 一起删**（`ClassDef.lineno` 不含装饰器）。
**4.13 API 面守门**：给那 9 个模块增删模块级名字要刷 `tests/fixtures/api_surface.txt`
（`$env:SPLIT_API_UPDATE='1'`）—— 今天动过的 `contract/digest/*`、`core/digest/*` **不在那 9 个里**。
**4.14 别把 `Measure-Object -Line` 的行数当真**（比 `splitlines()` 少 ~6%）。
**4.15 `_LABELS` 是 `AnnAssign`** —— 扫"带注解的模块级常量"要一起认，否则静默取空集。
**4.16 一个名字在 md 里不等于它是"料名"**（`【】` 还当角色代称/序数小节/交叉引用）。
**4.17 ⭐ 改 `contract/digest/prompts/` 或 `llm/prompts/` 任何**一个字节** ⇒ 立刻跑三份 verifier**
（`verify_1c.py check` / `capture_prompts_1d.py check` / `capture_1e.py check`）；
**有意的改动写进 `EXPECTED_CHANGED` 并写为什么**（长期红的判据 = 没人看的判据）。
⚠️ **前一道红会盖住后一道**：`capture_prompts_1d` 的"名单变了"先 return ⇒ **内容比对根本没跑**
（`digest_relate.md` 的一处改动因此漏登记了很久）⇒ 修名单的时候要把内容也比一遍。
⚠️ **改相位名 / 归档 md** ⇒ `verify_1c` 的基线键会认不出（`build_schema` 当场抛）⇒ 进 `SKIP_PHASES`；
`capture_prompts_1d` 有 `ARCHIVED` / `RENAMED` / `CHANGED` 三档（**改名那一档仍拿旧名基线比内容**,
这样"只是改了名"是**被证明**的）。
**4.18 真机数据只读**：探针可以读真档、可以在内存里 `store.add`，⛔ **绝不 `save()`**
（验证法：`git status data` 干净 + `wiki.jsonl` 的 mtime 不变）。
**4.19 推送必须走代理**：`git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=… push`（直连被 reset）。
**4.20 `git mv` 用显式路径**（不用通配符）；归档目录里的测试**不会**被 pytest 收集，
但它的 `parents[2]` 路径算过了 —— 要跑得先改。
**4.21 ⭐ 契约里不许有"假威胁"** —— 写了"违反即被丢弃", 引擎就**必须真丢**。
本会话抓到的实例：`【要写的名字】里没有的名字, 写了会被丢掉` 当年是**空话**（`parse_attribution`
只挡"已在库里"）。两条出路：**让引擎真拦**（加 `allowed_names`）**或改掉那句话** —— 用户选了
**第三条**：**那句话本身就不该存在**（名单只扫本段新节点, 会挡住合法的新建）⇒ 改成
"**名单是提示, 不是笼子**"。⚠️ 假威胁的代价是"模型学会无视契约里的禁令"。
**4.22 ⭐ 空值语义**: `"text": ""` = **"这一格没话可说"**（⛔ 不是"清空"）。⇒ 判"这一行改了什么"
**只看键在不在, 不看值空不空**（`parse` 收下、执行层记 `empty_skips` 后什么都不做）。
⚠️ 我第一版把"两个键都空"当成"没说改什么"丢行 —— 那会把一个**明确的 no-op** 记成"丢了东西"。
**4.23 加字段要顺着四处走**: `BrainNode` 的 dataclass 字段（`store.update` 的 `_FIELDS` 是
**动态取它的**, 漏了 ⇒ patch 报"未知字段"）· `to_dict`/`from_dict` · 照条目建节点的那两处
（`episodes._create_a_nodes` 的 profile 支 / `revise._create_belief` —— **漏搬就把内容静默吃掉**,
本会话被测试抓到两条）· `ROUNDS.writes` 与 `result_fields`。
**4.24 加 `DigestResult` 字段要同时在 `ROUNDS.result_fields` 里**（守门 `test_every_result_field_is_classified`
+ 回滚清单由表推导, 漏了就是"回滚不干净"）。
**4.25 ⚠️ 四个域塞进同一个 pytest 进程会互相干扰**: 见过一次 `test_bond_scene_error_abort_no_closing`
**超时红**（那是轮询 + 墙钟超时的用例; 单跑 ✓ · 整个 `tests/webgui` ✓ · `tests/core + test_bond.py`
合并 1287 passed ✓）⇒ **按域分开跑**（`tests/core` 一条命令, `tests/llm tests/renderer tests/webgui`
另一条）, 别图省事合成一条。
**4.26 薄委托要跟着改签名**: 契约层是"`parse.py` 实现 + `registry.py` 薄委托", 加一个 kwarg
（如 `object_ids`）要**两处都加** —— 漏了就是 `TypeError`, 而且只在真跑的轮上炸。
**4.27 守门"料还在、没人提"与"文案提到不存在的栏"是一对**: `test_material_names_are_not_dead`
（料名必须出现在某份 md 里）**反向**由 `test_every_bracket_in_prompts_has_a_home`（md 里的 `【X】`
必须说得出出处）看着 ⇒ **改段标题必须两边同改**（`ROUNDS.material` + md）。本会话那一刀就是被后者
逼出来的: 原本只想写文案, 它当场红了。

---

## 5. 本会话的设计与裁决（写给自己，别再问一遍）

### 5.1 已裁的（用户 2026-10-12 / 10-13）

**名表 / 名字匹配（更早那一批）**：⭐ 「我知道的名字」= 合并（原「我眼里的他们」+「我是这样看自己的」）·
**保留号都收** · **只写主名**（别名不上屏）· **她自己在表尾**；抬头固定（改名要同批改规则书, 有守门）·
⭐ 名字匹配**忽略空白**（`entities.form_key` = 去所有空白 + casefold, **唯一归一**）铺四处。

**2026-10-13 这一批（新的, 按时间）**：
- ⭐ **`experience`（给类写沉淀）随 group 退役一起停产** —— 判据 = **B 案第三档**（① 契约不再要
  ② 她惯性还写得出 ⇒ **认得出、丢行、⛔ 不判非法**）。⚠️ 这条修的是一个**真口子**: 停产前
  `group_ids` 恒空 ⇒ 她写一行沉淀就 **整包拒** ⇒ 那一段的看法全丢。
- ⭐ **`attribute` → `settle`**（用户原名"沉淀"）—— 命名分三截落: 改名（纯机械）→ 文案+料 → 执行。
- ⭐ **settle 的产出 = 一条数组, `id` 决定"建"还是"改"**（用户原话: *"旧的回落, 新的默认 engine
  构造"*）—— 项目自己的形状规则（`docs.py` 规则④: 有 id = 改, 无 id = 造）, ⛔ 我第一版写成
  "`entities` + `stances` 两个数组"是给同一件事造第二套形状（用户当场点出来）。
  ⭐ 它还顺手补了个洞: 新建的对象可以**在同一趟里带第一句看法**（两个数组时它没有号, 引不到）。
- ⭐ **`entity.text` ≤ 60 字, 软尺**（超了收下 + 告警）—— 判据: 那一格**每轮注入**（名表一行）,
  尺度按"一行能读完"; 新建对象的 `name` ≤ **8 字**（复用 `MAX_ALIAS_LEN` 的口径"更长的不是称呼"）。
- ⭐ **只写"不值得记"**: 契约里**不许**出现"值得记的标准 = 以后还会再出现"那类正向判据, 只留
  负向的（NPC / 店员 / 路人 / 只出现一次的相遇 / 以后多半不会再遇到的）。段标题去掉命令语气
  （【要认的名字】→ **【她写了、但库里还没有的名字】**）, 并加一句**如实**的许可
  （"**不写没有任何后果** —— 这个名字只在**这一段**问你一次"）。
- ⭐ **`id` 的门槛外化到证据上**: 改名只在"**这一段的事足以说明它本来就叫这个**"时才写
  （⛔ 不是"你觉得像"）。
- ⭐ **编造 `id` ⇒ 丢行**（⛔ **不给这个相位加"整包拒"档**: L1/L2 的一行不是独立事实, 而这里每行
  是互相独立的对象操作 ⇒ 一行坏了不连坐, 也不用白花一次反馈重试）。
  ⚠️ **代价记着**: 她若给"想建的对象"顺手编了 `id`, 那一行被丢, 而**那个名字下一段不会再被问**
  （`_strangers` 只扫本段新节点）⇒ 那个对象就建不出来。
- ⭐ **`allowed_names` 闭环撤销** —— **名单是提示, 不是笼子**（名单外的名字照样建）。
- ⭐ **空 = 不改**（见坑 4.22）。
- ⭐ **akin 共 belief**: **一跳 + 排除已矛盾的 + 上限 5**（用户给的数）。
- ⭐ **引用搬进独立字段 `entity`**（`tags` 回到纯检索词）—— 老写法**认得出并挪进来**。
- ⛔ **`ambiguous` 不加机制** · ⛔ **bond 开场不补物化** · ⏸ **`aliases` 仍冻结**（见 §1A-2）。

**更早的**：`mmt_send_media` 封印（prompt 上收, 解析/执行照旧）· ⛔ 不做 `inspect entity` ·
`echo`/`mood`/`precious`/`recent`/`notes` 不做 · `walk` **暂不接线** · 非便利屋68 的角色不维护。

### 5.2 设计判断（推出来的，已写进代码注释或本文件）

- ⭐ **对象留下，容器走人**：entity = **指向**; 类 = **概括** ⇒ 概括是 `belief` 的活。
- ⭐ **`entity.text` 与 `belief` 的分工是"粒度"** —— 而且 ⛔ **一条旧判据已作废**:
  `DESIGN_ENTITY_TAGS §6.1` / `settle.py` 从前写着"`entity.text` 那一格**今天没有读者** ⇒
  印象归 belief"。**那条理由 2026-10-12 就死了**: 名表现在每轮印 `- 主名：看法`
  （`render._known_line`）—— 读者一直在, 而且是**每轮都在**。分工: `belief` = 一条**结论**
  （有证据边、能进化/打架）; `entity.text` = 对**这一个人**的一句话总览（单槽改写 ⇒ 要防漂）。
- ⭐ **水位必须与它守的那句话同住一个原子单位**（同一个节点上）—— 于是两种失败语义都对:
  整段快照回滚 ⇒ 两者一起回滚（该重写就重写）; `own_snapshot` 只回滚自己 ⇒ 都留着（该跳过就跳过）。
- ⭐ **只有 `text` 需要水位**: **改名天然幂等**（值没变 ⇒ 不写、不留痕）, 而"整段重写"每次措辞
  都可能不同 ⇒ `text` 是这一层**唯一不幂等**的写入。
- ⭐ **撞车绝不合并**: 改名撞上别的对象 ⇒ **只丢 `name` 那一格**（`text` 照收）——"把两个人并成
  一个"**不可逆**（重复建对象还能合并, 身份并错分不开）。
- ⭐ **门槛不废、换载体**：`akin` 簇**直接对着 belief**（"兄弟" = 共同 `supports`，可图推导）。
- ⭐ **tag vs 边（二择）的判据**：这个关系**需要一个名字**吗？需要 ⇒ 标签; 不需要 ⇒ 边。
  硬差别: **传递性**（归属传递、"像"不传递）· **守恒方式**（标签靠名字守恒 ⇒ 怕抄错; 边不靠名字
  ⇒ 但没法合并）。
- ⭐ **`akin` 与 `group_tag` 重合的只是"同类"那半边**; akin 的正身是**她主动的弱关联**
  （`noticed` 的落脚点 + 召回窄门）—— ⚠️ 但 group 死后那条"退役 relate 的 akin 行"的判据
  **自动失效**（它不再与任何东西重合, 而且它是唯一来源）⇒ **撤回**。
- ⭐ **抄错灾难的机理**：不是"多一个对象"，是**那句话被写给幽灵**（真身 `text` 停在旧版 ⇒ 记忆
  静默分叉）。三层防: **写侧照抄** · **引擎归一 + 认出老写法** · **事后可观测**。
- ⭐ **"没有 X 的 Y"是个好模式**：engine 算"缺口" ⇒ LLM 只在有缺口时才被叫（成本天然最小）。
  本会话两个实例: "有解析不到的引用 ⇒ 才发 settle"; "谁也没提到 ⇒ 一次都不发"。
- ⭐ **两张计数提示的分工**（settle 的料）: 「正文里还提到过它 N 次（没标引用）」= 引擎扫正文,
  真机实测"老师" **21/21 恒真、零区分力** ⇒ **只当提示**; 「共出现 N 次（第一次在 …）」=
  **她认过的引用面**（`about` 入边）⇒ 只有这条可依据。

### 5.3 待用户拍 / 待办（**集中在这儿**）

1. ⭐ **akin 共 belief**（§1A-1）—— **形式已定稿, 等一句"开"**（下一件就是它）。
2. **`topics` 退役**（§1A-3）—— 会带走 `akin` 的 `on` 校验 ⇒ 要么接受, 要么另找载体。
3. **belief collision 的其余两条**（§1A-4）。
4. **`aliases` 的写者**（§1A-2）—— 改名带旧名已落; "她主动补新别名"仍冻结。
5. **线 B 那两条**（1h 的岔路 · 1e 的两处待拍）—— **另一 agent 的, 别替他答**。
6. ⏸ 记着不动的: `ambiguous` 不加机制 · bond 开场不补物化 · `examples` 字段当扩展位留着 ·
   `profile` 只停产不删格式。
