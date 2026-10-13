# PROCEED.md — 接续用（**整篇覆盖写**；上一版见 git 历史）

> **树干净 · `ahead 38`（没 push —— 推不推由用户定）**。真实头看 `git log -1`。
> 现状：`tests/core` **1243 passed** · `tests/webgui`+`tests/llm`+`tests/renderer` **196 passed**。
> ⚠️ **这棵树里有两条线**，别混：**线 A = 记忆层重新设计（本会话主线）** ·
> **线 B = 包重组（另一个 agent 做的 1a/1c/1d/1f，1e/1h 等他拍板）**。
> 上一版（`0299e06`）只写线 B；本版把线 A 完整写进来，线 B 压成一节。

---

## 0. 三十秒概览

**线 A（本会话）**：记忆层从"写侧造容器"改成"**写侧只写地址、引擎物化、内容归 LLM**"。
已落：① brain 段那块 = **「我知道的名字」**（全体 entity、键面 + 看法）② 名字匹配 **空白不敏感**
（`entities.form_key`）③ 台账 `mmt_recall` 加 `per=`/`ms=` ④ 真机观察脚本 ⑤ **group（L2-a 分群）
退役**（整族搬 `archive/digest_group/`）。**设计已定、代码未落**：`settle` 轮 · belief collision ·
`topics` 退役 · 引用结构（写侧顺手写对象）。

**线 B（另一 agent）**：把"缝补出来的项目"改成正常 Python 项目的形状。已做 1a/1c/1d/1f；
**1e（`contract/schema.py` 外移）与 1h（调用层归位）等他拍板**（岔路见 §1B）。
目标形状（已定）：`contract/`（零项目内依赖）· **新建 `infra/`**（paths/errors/atomic/fuse/时间）·
`llm/` · `engine/`（← 现 `core/`）· `tui/`（← 现 `renderer/`+`core/tui/`）· `cli/`（← `apps/`）·
`docs/{design,spec,archive}/`。

---

## 1. 下一步该怎么做

### 1A ⭐ 记忆层改造（**设计已定稿，分四件落**；⛔ 动代码前先报形式）

**总口径**：**对象留下，容器走人**。
- **entity = 指向**（人/地方/东西）：**保留**。写侧在 ① `record` 里顺手写引用（`tag` 语义），
  引擎**物化**（查不到就建节点 + 落 `about` 边 + 把写下的写法**长进别名**）。
- **类（`experience`）= 概括**：**退役**（"概括"本来就是 `belief` 的活）。

| # | 一件 | 要点 |
|---|---|---|
| 1A-1 | **引擎寻址** | `#entity:名字`（today 存在 `tags` 里）→ 引擎 find-or-create + `about` 边 + 长别名；命中就用**她写的写法**补进 `aliases`；**miss ⇒ 建新对象 + 记一笔账**（真机看频率）。⚠️ `groups.py` 退役后 `find_group` 的寻址面比 entity 窄（title 精确、不看别名）—— 若将来还要"类"，先对齐 |
| 1A-2 | **写侧引用结构（形状待拍）** | 把 `#entity:` 从 `tags` 里搬出来，与"类/涉及谁"合成一处：`{"class": 类名, "about": [名字…]}` 或统一数组 `[{"class": …, "text": 名字, "alias": [仅新建]}]`（用户原话倾向后者）。**新建才带 `alias`**；`tags` 回到**纯检索词** |
| 1A-3 | **`settle` 轮**（新相位，名字用户已定） | **料**：① 被引用的 entity + 它当前的 `text` ② 被引用的 group（老档遗留）+ `text` ③ **本段新生引用**（= 本段新落的 `about`/`member_of` 边，引擎算）④ **重要旧生引用**（≤3，按 `significance`）—— ⚠️ ④ **不是可选项**：`record`/`cognize` 失败隔离会让某段的新引用**永久失去"新"的身份**，那是唯一的补偿 ⑤ 并群候选（老档遗留）。**产出**：统一项 `{tag, text}` 写进 `entity.text` / `experience.text`。<br>⛔ **settle 不许新建**（miss ⇒ 丢项 + 记账）—— 抄错只会"少写一次沉淀"，不会长幽灵、不会把看法写给幽灵。<br>⭐ **必须配沉淀水位**（节点上记 `text_seq`）：段级重试会把同一批引用**折两遍**（`text` 是单槽改写，不像 belief 是加法） |
| 1A-4 | **belief collision + akin 收窄** | ① `cognize` **不再写 `experience.text`**（那格搬 1A-3）；它的料改成「本段新经历 ＋ **L1 判过关系的那几条**」<br>② belief 默认**综合 ≥2 条**（相似或矛盾都行）；单点要过门槛。⭐ 判据 = **"写得出一句『所以』"**（`DESIGN_MEMORY_MODES.md:58`：簇的代表性总结是**描述**，不该住 belief）<br>③ `relate` 的 `akin` 行**退役**（"同类"交给 belief/引用）；`akin` 收窄成**她主动的弱关联**（`noticed` 的落脚点 + 召回窄门）<br>④ ⭐ **门槛换载体**：引擎算"**没被共同 belief 压住的 `akin` 簇**"⇒ 强制压住其中 **≥2** 条（"兄弟" = 共同 `supports` 同一条 belief，**可图推导**）。`ungrouped`/`build_blocks` 的切簇算法**从 archive 里捡回来复用**（只是不再建节点）<br>⑤ **软强制 + 允许一次显式 defer**（defer 记账）—— 完全强制会造垃圾 belief |
| 1A-5 | **词表收成一个** | `tags` 留（召回在用）；**`topics` 退役**（唯一读者是 `akin` 的 `on` 校验 + 挑候选，两个都在变）；挑候选改走 **`like(spec="digest")`**（那个档位**写好了却零调用** —— 顺手补上"R2 候选没接新前门"）|

**落代码的顺序建议**：1A-1（最小、可单独验）→ 1A-2（契约形状）→ 1A-5（挑候选）→ 1A-4 → 1A-3（最大）。
每件一个提交；**动契约文案要跑三份 verifier**（见 §4 坑 4.18）。

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

### ⏸ 已划去（别自己捡起来）
- **删 `examples` 字段**（用户 2026-10-13：*"算了…可以看作扩展, 延后, 划去"*）—— 现状有读者、
  有守卫、零活写者，当扩展位留着。
- **`profile` 真删格式**：1c 只做了"停产"（B 案），真删等确认没有老档依赖。

---

## 2. 必读文件

| 文件 | 为什么 |
|---|---|
| 本文件 | —— |
| **`archive/digest_group/README.md`** | ⭐ group 退役的**是什么/为什么/怎么复活**；点了名哪些读侧机器件**别删** |
| `core/digest/rounds/__init__.py` | ⭐ **轮次真源 `ROUNDS`**（key/步序/相位/parse/料/预算一处说全；`material` 是硬契约，`_sections_for` 逐字对账） |
| `core/brain/entities.py` | ⭐ `form_key` / `surface_forms` / `find_entity` / `hit_set` / `ensure_entities` —— **名字匹配的唯一归一在这** |
| `core/brain/read/modes.py` + `like.py` + `find.py` | 召回形状：形式表 / 六路打分（`SPECS["turn"]` 与 **零调用的 `SPECS["digest"]`**）/ 定向寻找 |
| `core/brain/read/render.py` | brain 段那块（`KNOWN_NAMES_HEADER` / `_known_line`）· P19 三段 · `look` 文案 |
| `contract/digest/`（`tables.py`/`docs.py`/`parse.py`/`registry.py`/`prompts/`） | ⭐ 契约五模块（值表/清单/校验/渲染/文案）—— 1A-2 要改的地方 |
| `docs/DESIGN_MEMORY_MODES.md` | ⭐ 四种模式（抽象/佐证/经验/进化）+ **`akin` 原料 → 门槛(n) → belief 产出** + "簇总结不是决定" |
| `.testtmp/verify_1c.py` · `capture_prompts_1d.py` · `capture_1e.py` | ⭐ 动契约/文案的三份**逐字节判据**（各自 `check`；`EXPECTED_CHANGED` 要写"为什么"） |
| `tests/core/test_digest_rounds.py` · `test_digest_contract_refs.py` · `test_import_direction.py` | 轮次表守门 · `【X】` 必须有出处 · 分层守门（`contract` 不许 import `core`） |
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

**线 A（本会话，都在 master）**：

| 提交 | 做了什么 |
|---|---|
| `4d978eb` | ⭐ **entity 常驻化**：brain 段那块 = **「我知道的名字」**（**全体 entity**、一行 = 主名 + 有看法才接 `:text`、**别名不上屏**、**她自己在表尾**、保留号都收）+ `entities.form_key`（去空白 + casefold）铺三处 + 台账桶 `they`/`self_stance` → `known` |
| `5a5973e` | **台账收口**：`mmt_recall` 加 `per=`（每段字数）+ `ms=`（召回+渲染耗时；同步跑在 `round_messages` 前 ⇒ 进 TTFT） |
| `593d1a1` | ⭐ **真机观察脚本** `experiments/recall_report.py`（只读、两代格式都认、`--selftest`） |
| `3ad6e71` | 两条新守门（**编号永不进她的视图** 扫整段注入文本 · **名表行形状**）+ 3 个变异靶（`form_key` 退回 casefold / 行里印 id / 行里印别名）+ 重跑旧靶 14/14、13/13 |
| `c350a3b` · `c98cbb3` | PROCEED 第四版 · 补提交链与 §2⑤ |
| `d32c8f3` | config：**作者缩短出厂立场句**（名表 1116 → 938 字；跟一条断言） |
| `c7a4ac7` | 名字归一推广到 **`hit_set` 的正文扫描**（真档实测三口径命中集相同 ⇒ 零误命中） |
| `1478121` | ⭐ **group（L2-a 分群）退役** —— 生产停 + 整族搬 `archive/digest_group/`；硬顶 720 → 600 |

**真机读数（只读探针，⛔ 全程不 save）**：haruka —— 节点 `episode 21 · belief 4 · entity 4 ·
experience 1`；边 `about 22 · supports 25 · member_of 6 · akin 5`；名表那一块 938 字。

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
**4.11 行尾不统一**（78 纯 LF / 259 CRLF，无 `.gitattributes`）—— 既有事实，**别顺手改**；
按行号改文件要按字节切 `\n`。
**4.12 删顶层类/函数要连 `@decorator` 一起删**（`ClassDef.lineno` 不含装饰器）。
**4.13 API 面守门**：给那 9 个模块增删模块级名字要刷 `tests/fixtures/api_surface.txt`
（`$env:SPLIT_API_UPDATE='1'`）—— 今天动过的 `contract/digest/*`、`core/digest/*` **不在那 9 个里**。
**4.14 别把 `Measure-Object -Line` 的行数当真**（比 `splitlines()` 少 ~6%）。
**4.15 `_LABELS` 是 `AnnAssign`** —— 扫"带注解的模块级常量"要一起认，否则静默取空集。
**4.16 一个名字在 md 里不等于它是"料名"**（`【】` 还当角色代称/序数小节/交叉引用）。
**4.17 ⭐ 改 `contract/digest/prompts/` 或 `llm/prompts/` 任何**一个字节** ⇒ 立刻跑三份 verifier**
（`verify_1c.py check` / `capture_prompts_1d.py check` / `capture_1e.py check`）；
**有意的改动写进 `EXPECTED_CHANGED` 并写为什么**（长期红的判据 = 没人看的判据）。
**4.18 真机数据只读**：探针可以读真档、可以在内存里 `store.add`，⛔ **绝不 `save()`**
（验证法：`git status data` 干净 + `wiki.jsonl` 的 mtime 不变）。
**4.19 推送必须走代理**：`git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=… push`（直连被 reset）。
**4.20 `git mv` 用显式路径**（不用通配符）；归档目录里的测试**不会**被 pytest 收集，
但它的 `parents[2]` 路径算过了 —— 要跑得先改。

---

## 5. 本会话的设计与裁决（写给自己，别再问一遍）

### 5.1 已裁的（用户 2026-10-12 / 10-13）
- ⭐ **名表四条**：「我知道的名字」= 合并（原「我眼里的他们」+「我是这样看自己的」）·
  **保留号都收** · **只写主名**（别名不上屏）· **她自己在表尾**；抬头固定
  `我知道的名字（想起谁、翻谁的事，都用这些叫法）：`（改名要同批改规则书，有守门）。
- ⭐ **名字匹配忽略空白**（`entities.form_key` = 去所有空白 + casefold，**唯一归一**）——
  铺四处：`find_entity` / `like.build_ctx` / `_materialize_stances` / `hit_set` 的正文扫描。
- ⭐ **台账格式**：`per=` 与 `modes=` 同款标签（含 `(empty)`）；`ms=` 只量召回+渲染。
- ⭐ **`settle`** = 新轮的名字（用户定的）。
- ⭐ **group 退役**："把代码整合一下搬到 archive 里面"（已落 `1478121`）。
- ⭐ **`entity` 的 text 需要重写**（用户原话）—— 那正是 `settle` 要干的。
- ⏸ **`entity.text` 的 digest 侧写者缺口**（2026-10-12 裁"以后再说"）→ 现在有答案了：`settle`。
- `mmt_send_media` 封印（`a0eb749`）：媒体管线未接 ⇒ prompt 上收；解析/执行照旧。
- ⛔ 不做 `inspect entity`（entity = 筛选轴）· `echo`/`mood`/`precious`/`recent`/`notes` 不做 ·
  `walk` **暂不接线** · 非便利屋68 的角色不维护。

### 5.2 设计判断（本会话推出来的，已写进代码注释或本文件）
- ⭐ **对象留下，容器走人**：entity = **指向**（denotation，名字从经历里顺手抄就有）;
  类 = **概括**（abstraction，得先有 ≥2 条）—— 而概括是 `belief` 的活 ⇒ 类没有独立存在的必要。
- ⭐ **门槛不废、换载体**：原设计"`akin` 原料 → `experience` 门槛(n) → belief 产出"；
  新设计 = **`akin` 簇直接对着 belief**（"兄弟" = 共同 `supports`，可图推导）。
- ⭐ **tag vs 边（二择）的判据**：**这个关系需要"一个名字"吗？** 需要 ⇒ 标签（多对一、
  可累积正文、能被 merge）；不需要 ⇒ 边（成对、无名、无正文）。补两条硬差别：**传递性**
  （归属传递、"像"不传递）· **守恒方式**（标签靠名字守恒 ⇒ 怕抄错；边不靠名字 ⇒ 但没法合并）。
- ⭐ **`akin` 与 `group_tag` 重合的是"同类"那半边用途**（`relate.md` 原文把 akin 定义成
  "同一类事"）；akin 的正身是 **"隐隐之中有什么联系"**（弱关联）—— 保留：`noticed` 的落脚点
  + 召回窄门（`like.struct` / `walk.NARROW`）；退役：`relate` 的 akin 行 + 分群依据。
- ⭐ **`topics` 的唯一读者是 akin 链**（挑候选 + 校验 `on ∈ 两端交集`）⇒ 该退役，词表收成一个。
- ⭐ **抄错灾难的机理**：不是"多一个对象"，是**那句话被写给幽灵**（真身的 `text` 停在旧版 ⇒
  记忆静默分叉）。三层防：**写侧照抄**（料里【已有的对象】放最显眼）· **引擎归一 + settle 不建**
  （miss ⇒ 丢项 + 记账）· **事后可观测**（miss 的名字与已有名互为子串且唯一 ⇒ 记"可疑抄错"账，
  ⛔ 不自动并）。
- ⭐ **正则连接（LLM 写关键词、引擎按词连）那条路否决**：没有地址（无节点 ⇒ 无沉淀/不可引用）·
  同形不同义必撞 · 与 `tags` 重复（会把检索词表当图用）· 说不出"这一类事叫什么"。
- ⭐ **"没有 X 的 Y"是个好模式**：engine 算"缺口"（没被共同 belief 压住的 akin 簇 / 有陌生名字 /
  段没消化）⇒ LLM 只在有缺口时才被叫（成本天然最小）。

### 5.3 待用户拍（**集中在这儿**）
1. **settle 能不能新建？`alias` 放哪？**（建议：settle 只认已有、miss 丢项记账；`alias` 只在
   ① `record` 的新建项上）
2. **引用结构的形状**：`{"class": …, "about": [...]}` 还是统一数组 `[{"class": …, "text": …,
   "alias": …}]`（用户原话倾向后者）；`text` 这个名字不要与 episode 的正文键混
3. **belief collision**：料是否就摆"本段新经历 + L1 判过关系的那几条"；单点门槛用 `significance`
   还是纯 prompt
4. **`topics` 退役 + 挑候选改走 `like(spec="digest")`**（同意？）
5. **废 group 的力度**：已按"停产 + 搬 archive"落；要不要"整族删"（连 `experience` kind /
   `member_of` / `meta` 里那条）—— 老档现有 1 个 `experience` + 6 条 `member_of`
6. **现在动记忆层代码，还是等 1e/批次 2**（同一片地，等一等少改一遍）
7. 线 B 那两条（1h 的岔路 · 1e 的两处待拍）—— **另一 agent 的，别替他答**
