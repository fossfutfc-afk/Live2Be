# PROCEED.md — 接续用（**整篇覆盖写**；上一版见 git 历史）

> **树干净 · 本会话在 `dbac250` 之后做了 4 项任务 —— 每个的提交哈希在 §3 的表里。**
> ⚠️ 本文件每次改都会再产生一个提交 ⇒ **别在本表头抄哈希**（抄了必然落后一步）;
> 认真头用 `git log -1`。
> 现状：**全量回归 1455 passed（约 2.5 分钟）· ruff 378**。
> ⚠️ **没有 push**（`origin/master` 存在，但推不推由用户定）。
> 上一版讲的是 1a/1b/1c/1d/1e/1f/1g 七项待办 —— **1a · 1c · 1d · 1f 已做完**（见 §3），
> **1b 由用户撤下**，**1e/1g 仍在等他拍板**（见 §1）。

---

## 0. 三十秒概览

用户要的是：把这个"缝补出来的"项目改成**正常 Python 项目的样子**，然后再扩展。
四条：① 彻底改（允许改包名/import 路径）② 顶层保持分散但改名 ③ 测试随行重写
④ 文档只写 mmt/vn 输出形式 + digest + 召回三块（其余写进各包 `__init__.py`）。

工作方式（他明确要求）：
- **逐个包改，每完成一个包他会详细了解询问** → 做完整阶段就停下等他
- 每步**独立提交**；小板块配冒烟；大板块才跑全量回归
- **死代码一律先过目、先报数**，不许自行处置
- ⭐ **他离开期间只做"不需要他拍板"的活**：文档、注释、测试脚手架、信息汲取。
  凡是有两个说法都成立的岔路（归属/命名/文案口味）→ **停下来列清楚**, 不自己选。

已定下的目标形状：
```
contract/   纯契约（★现状 = 零项目内依赖）
infra/      ★新建：paths / errors / atomic / fuse / 时间 —— 为断 core↔llm 环 + 打包 exe
llm/        外部适配器（只依赖 contract + infra）
engine/     ← 现 core/ 的领域部分
tui/        ← 现 renderer/ + core/tui/
webgui/  cli/(←apps/)   tests/   docs/{design,spec,archive}/
```

---

## 1. 下一步该怎么做（按顺序，可直接执行）

### 1h · 调用层归位（**2026-10-13 用户提出；小活，但有一个岔路**）
用户原话: *"digest 里有两个 call, 我觉得有必要放入 `client.py` 中, 这工作量大吗,
函数可以不动, 但是它的位置错了"*。⛔ 两个文件**不是一类东西**（名字撞车而已）：

| 文件 | 行数 | 依赖 | 判决 |
|---|---|---|---|
| `core/digest/llm_call.py` | 85（`llm_chat` 56 + docstring） | ⭐ **零 digest 依赖**：只用 `core.common.err` · `llm.task_labels` · `llm.task_levels` | ✅ **位置错了**（就是用户说的那个）—— 真家是 `llm/`，与 `client._classify`/`_raise_transport`/`retry.call_with_feedback` 同一族 |
| `core/digest/call.py` | 164（6 函数） | `contract.digest`（**渲染产出契约**）· `core.digest.rounds.RoundSpec/budget_of` · TYPE_CHECKING `pipeline.DigestResult` | ❌ **位置是对的** —— 搬进 `llm/` = 新开 `llm → core.digest.rounds` 的反向依赖（`llm → core` 现在只剩 `task_levels` 那**一根**线，正等 `infra/paths.py` 断掉）。错的只是**名字**：看着与 `llm_call.py` 像一对。想治就改名 `round_call.py`（它自己的 docstring 就写"一轮 LLM 调用的四件套"） |

**搬 `llm_call.py` 的完整工作面（实测，AST 认 import）**：
```
搬家            core/digest/llm_call.py → llm/client.py（或 llm/robust.py, 见岔路）
改 import       core/digest/call.py:26   ← 唯一生产引用
                tests/core/test_llm_call.py:4（文件名/首行 docstring 一并改）
⛔ 必须同改     `from core.common import err` → `from contract.errors import err`
                （不改成真源, 搬完就是 `llm → core`, 把"刀 1"刚断的线又接回去）
文档指针 5 处   core/digest/__init__.py:37 · llm/task_labels.py:38,106 ·
                core/digest/pipeline.py:265 · core/digest/rounds/__init__.py:95,167
不用动          MAX_CALL_RETRIES（0 个外部引用）· digest 门面**没有**再导出 llm_chat
```
⇒ **工作量：小**（85 行搬家 + 2 处 import + 1 行改真源 + 6 行文档指针，**零行为变化**）。
冒烟 = `tests/core/test_llm_call.py` + `tests/core/test_digest_rounds.py`。

**岔路（要用户点头）**：搬进 `llm/client.py`（**他说的**，但那份已经 672 行 =
`LLMClient` 459 + 8 个模块级函数，主题是"OpenAI 协议封装"）**还是**新开 `llm/robust.py`
（主题是"怎么发得稳"：重试/deadline/档位透传/回灌）？⚠️ 我倾向**后者**：
`llm_chat` 不是协议件，它是**策略件**（它收一个鸭子类型的 `llm` 当参数，不是 `LLMClient`
的方法）。但这一条**等他定**，别自己选。

⭐ **顺带一个更值钱的发现**（同一片区域，**中活，要拍板**）：
`core/digest/call.py::_round_call`（68 行）里那个"调用 → parse → 被拒就回灌重试 1 次"
的循环，是 **`llm/retry.py::call_with_feedback` 的第三份实现** ——
`llm/retry.py` 的 docstring **自己就把 digest 那一份列在待收口的三份里**
（bond `engine.py:436-602` · mmt 三段式 · digest `call.py:99-131`）。
⇒ 真正"本该用公共契约却自己写了一份"的地方在这儿，而它的收法**不是搬文件而是改走已有实现**
（要定：重试次数 bond 3 / digest 1、错误文案带轮次、parse 怎么绑）⇒ 报给他, 没动。

### 1e · `contract/schema.py` 外移（**下一个大件；两处等他拍板**）
用户说过 *"我可能希望这个也做掉"*，并问"你有什么问题" —— 问题已报（见下），
**他还没回** ⇒ ⛔ **别自己选**，把这两条摆给他：

**待拍 ① 归属**：新 `contract/schema/` 包（对称 digest）**还是**并进已有的
`contract/records/`（它的 `grammar.py` 就是"取值表 + 记录形状"）。
我倾向**并进 `records/`** —— 理由：**另立一个包会让"取值表"有两个家**（正是要治的病）；
代价：`records/` 的名字变窄（它今天指 VN 记录，而 schema 还管 MMT 行流）。

**待拍 ② 硬规则清单的承载形式**（这条我上次漏报了，是**新发现的**）：
`_MMT_RULES`（6 条）/`_VN_RULES`（6 条）是**元组**，靠 `_numbered()` 按位置编号 ——
"加一条只管往元组里写，编号自己会跟上"（docstring 明写了这个好处）。搬进 md 之后：
  - ⓐ md 里**手写编号**（`1.` `2.` …）→ 丢掉"自动编号"，中间插一条要改后面全部
  - ⓑ md 里写 `- ` 列表，代码**解析回元组**再编号 → 保住自动编号，md 变成半结构化
  - ⓒ 只搬外壳/示例，**规则留在代码**（它们的文本里还嵌常量：
    `MAX_SENSEI_RUN` / `_VN_TURN_LINES`，见 `_VN_RULES`）
⚠️ 无论选哪个，**判据已经备好**: `.testtmp/capture_1e.py check` ——
7 个形态**逐字节不变**（含 `build_schema` 空/满注册表、行流带/不带示例、
记录流三态）。基线 = `.testtmp/schemas_1e_before.json`（**本会话已拍**）。

**实测结构**（要做的事有多大）：
```
总 292 行 · 154 个字符串字面量 · 5281 字符 · 5 个顶层函数
  _SHELL_FIELD_DESCRIPTIONS  8 行（6 条静态文案）        → 可进 md
  _APPROVAL_NOTES            5 行（3 条）                → 可进 md; 两个渲染器都用
  _numbered                 8 行（**编号唯一实现**）      → 见待拍 ②
  build_schema             35 行  ⚠️ **生产零调用者**（只有 archive/ide_editor + 再导出）
  export_definitions       18 行  ⚠️ **全死**（0 生产 0 测试, 只在 `contract/__init__` 再导出）
  _MMT_RULES 12 行 + build_line_schema 75 行（**活**: core/mmt/engine.py:710）
  _VN_TURN_LINES + _VN_RULES 16 行 + build_record_schema 71 行（**活**: bond engine:264）
```
⭐ **顺带发现**（AST 核实过，`ast.Call` 才算）：`build_schema` + `export_definitions`
+ `_SHELL_FIELD_DESCRIPTIONS` ≈ **61 行是生产死代码** ——
"A 方案数据面（给 JS/WebLLM 用）"**从来没接上**。⇒ 1e 之前值得先问他要不要**先砍这 61 行**
（砍了之后 1e 只剩两个活渲染器的搬家，小得多）。⚠️ `contract/spec.py:26` 的 docstring
与 `contract/__init__.py` 的再导出都要跟着改。

### 1d-2 · 反引号（**只差他一句话**）
槽语法已统一（1d 做完）；**"反引号只包短槽（≤20 字）"这半没做** —— 原因是"短/长"的
边界在几处说不准，而它**真的会改 prompt 正文**（他自己指出反引号会进 prompt）。
我的建议分类（**报给他, 没动**）：
  - **包**：`char` `char_id` `char_name` `group_no` `n` `key_a/b/n` `place`
    `current_place` `current_image` `note` `aliases`
  - **不包**（值是多行块）：`lexicon` `sentences` `records` `digest_schema`
    `context` `character` `character_hint` `candidates` `text`
  - 存疑（要听他判）：`note`（作者写的可能一两句）、`aliases`（`a/b/c` 拼串）、
    `character_hint`（`illustration.yml` 的简卡，可能多行）
落点：`llm/prompts/` 那 9 份（43 处槽）。

### 1g · `infra/paths.py`（**等他拍三个根**）
必要性两层：① 它是 `llm → core` 的**最后一根线**（`llm/task_levels.py:45` 只要
`paths.SETTINGS_PATH`）② **打包 exe 的硬前提**：现在 `ROOT = Path(__file__)…parent.parent`
**一个值服务三种根** —— 只读资源（config/assets/prompts）· **读写同一份**的 `settings.toml`
（GUI 设置页写它，`webgui/store.py:169`）· 运行时数据 `data/`（事件流真源）。
frozen 下三者不重合，`data/` 落临时目录 = **退出即丢**。
成本：**25 个常量 / 30 个 import 点 / ~90 处属性引用 / 32 个文件** + `tests/core/test_paths.py`。
⭐ **代码便宜，决定贵**：要他拍"三个根各放哪"。

### 然后 · 批次 2 起
纯移动：`core` → `infra/` + `engine/`；`renderer` + `core/tui` → `tui/`；`apps` → `cli/`。
⚠️ 顺带：`renderer → core.media.catalog` 3 处（表现层反向依赖引擎），`tui/` 那一步一起处理。

### ⏸ 已撤下 / 划去（**别自己捡起来**）
- ✅ **划去: 删 `examples` 字段**（原 1b）。用户 2026-10-13 裁: *"算了 examples 感觉没有
  删除的必要, 这个还可以看作扩展, 延后, 可以划去"* ⇒ **不再是待办**。
  现状照旧: 有读者（`read/pack.py` 的正文面 / `recall.py` / `render.py`）、有守卫
  （`profile.examples ≤3` 的不变量）、**零活写者**（`_apply_accrue` 随 1a 一起删了）。
  ⇒ 当它是"留着的扩展位"。
- **batch 2** 的目录改名：要他在场。

---

## 2. 必读文件

| 文件 | 为什么 |
|---|---|
| 本文件 | —— |
| `.testtmp/verify_1c.py` + `schemas_1c_before.json` | **digest 契约的逐字节判据**（15 形态）。⚠️ 本会话改过它: 加了 `EXPECTED_CHANGED`（record ×2 = profile 停产）与 `SKIP_PHASES={"understand"}`; **动契约文案就要在里面写一行为什么**, 否则它退化成"什么都拦不住" |
| `.testtmp/capture_1e.py` + `schemas_1e_before.json` | ⭐ **1e 的判据**（7 形态: 三个渲染器 × 开关组合）。1e 是"只搬不改" ⇒ 期望 `EXPECTED_CHANGED` 恒空 |
| `.testtmp/capture_prompts_1d.py` + `prompts_1d_before.json` | `llm/prompts/*.md` 的**折叠回单括号**判据（动槽/搬 prompt 文案时跑 `check`） |
| `.testtmp/scan_slots.py` · `scan_sections.py` | 不变量侦察（槽 → 填写点 / `【X】` → 出处）; 改 prompt 结构前先跑一遍看全貌 |
| `contract/digest/__init__.py` · `prompts/` · `registry.py` | 包地图 + ⭐ **契约文案真源** + 渲染 = 读 md 填槽 |
| `core/digest/rounds/__init__.py` | ⭐ **轮次真源 `ROUNDS`**（key/步序/prompt/相位/parse/料/预算一处说全; `material` 是**硬契约**, `_sections_for` 会逐字对账） |
| `tests/core/test_digest_contract_refs.py` | ⭐ **新守门**：`【X】` 必须有出处（料名/时间线标签/自造小节）|
| `tests/core/test_import_direction.py` | 分层守门 + **豁免表**（`LLM_CORE_ALLOWED` 只剩 `core.paths`） |
| `core/brain/revise.py` | 现在是**三趟执行器**（relations/cognitions/entities）—— v1 万能包执行器已删 |
| `TODO.md`（第一条） | prompt 外移那条待办 + 实测分布 |
| `CLAUDE.md` | ⚠️ 89 KB 且**多处过时**；当索引读，冲突时信代码 |

---

## 3. 已做的更改（本会话 +4，都在 master）

| # | 提交 | 做了什么 | 判据 |
|---|---|---|---|
| **1a** | `920f814` | **清残党第二刀**：删 v1 万能修订包执行器（`apply_revision_package` 96 · `_apply_action` 92 · `_apply_accrue` 34 · `_parse_create` 33 · `_build_merged` 17 · `_connection_rule_violations` 17 · `_err` · `RevisionResult`）+ store 的 4 个旧 shim（`add_link`/`remove_link`/`add_contradiction`/`remove_contradiction`，**零生产调用者**）+ 14 条测试。**-659/+67**。⛔ `classify_pair` 留下（旧档自举活路）。顺手修 5 处死指针 + `graph` docstring 里**与代码相反**的一行 | 焦点 120 passed · ruff 386→378 |
| **1c** | `8e57359` | ⭐ **`profile` 节点停产（B 案）**：契约删掉 `kind` 那一档（`record.md` 3 处 + `digest_record.md` + `digest_relate.md`）· `parse._clean_episode` 的 profile 支路改成 **`_drop`（认得出、不产条目、⛔ 不报错 ⇒ 绝不触发重写整段）** · `ROUNDS.record.writes` 摘掉 profile 一格。**留**：`KINDS`/读侧/`_PREFIX`/`_COGNITION`/`episodes` 那一支（停用不是删机器）。+2 测试删、+2 镜像断言改 | `verify_1c` 15→**相同 7·尾随空行 4·有意改动 2·计划外 0**（跳过 2）· core+llm 1330 passed |
| **1d** | `67a8dee` | ⭐ **槽语法统一**：9 份 md / **43 处** `{x}` → `{{x}}`；7 处调用方改走 `contract.slots.render_template`（漏填/多填**当场炸**）。⭐ **炸出 2 处一直静默空转的 replace**（`bond_story_rules.md` 根本没有槽 · `bond_shots.md` 没有 `{char_name}`）。⭐ `core/brain/read/modes.py::_fill` 是同一件事的**第三份**手写实现，一并收口。+守门：`llm/prompts/*.md` 不许再有单花括号槽 | `capture_prompts_1d check` 19 份全过（**折回单括号 = 逐字节原文**）· core+llm+renderer+webgui **1453 passed** |
| **1f** | `8e7fb00` | ⭐ **新守门** `tests/core/test_digest_contract_refs.py`：契约/digest 文案里每个 `【X】` 必须说得出出处（**料名 AST 取** / 时间线标签取 `renderer._LABELS` / 自造小节），**正向 + 反向**两个方向。第一次跑就抓到 **3 处真东西**（见 §5.3） | 19 份 md 全有出处 · 20 个料名全被点到 · 217 passed · `verify_1c` **计划外 0**（3 处 split 形态是**有意**改的, 已登记 —— 见坑 4.18） |

**当前层间账**（AST 实测，未变）：
```
contract  → （无）                    ← 唯一零对外依赖
llm       → contract 5 · core 1       ← 只剩 task_levels 的 core.paths（等 infra/paths.py）
core      → contract 24 · llm 34      ← 单向；core↔llm 的环**只剩那 1 处**
renderer  → core 3                    ← core.media.catalog（批次 2 的 tui/ 一起处理）
```
**测试数**（`def test_` 计）：`dbac250` 1456 → 现在 **1444**（净删 15 条死的, 净增 3 条守门）
⇒ 全量 **1455 passed**（pytest 的收集数比 `def test_` 多 ~11，参数化/嵌套）。

---

## 4. 隐形坑（踩过的，别再踩）

**4.1 `ruff check --select X --fix` 是陷阱。** `--select` 会**覆盖** pyproject 的 select，
把其他规则关掉 ⇒ "本来生效的 noqa"被判成无用批量删掉（实测：192 条带说明的 `# noqa: BLE001`
被删光）。删 noqa 只用 `.testtmp/strip_dead_noqa.py`。**同理别用 `--select` 跑 fix。**

**4.2 动 F401 前必须查"有没有人从这个模块 import 走"**（ruff 看不见再导出）。栽过 5 处。
⚠️ **`tests/**` 有 `F401/F811` 豁免**（`pyproject.toml` 的 per-file-ignores）——
测试里的未用 import **不会**被 ruff 报出来，得自己 grep（本会话在
`test_wiki_revise.py` 里清掉过两个）。

**4.3 判断"死代码"必须用 AST 认 `Call`，不能 grep 行。** 栽过：`apply_decisions` /
`_parse_create` / `_ensure_cognition` / `_rewrite` / `_link_about` 的"生产调用者"
**全是注释与文档串**。反面：`classify_pair` 看着像残党，其实是**旧档自举**的活判据。
⚠️ **同名不同物**：`digest_registry.build_schema`（方法，活）vs
`contract.schema.build_schema`（函数，**生产零调用者**）—— 按属性名找调用者会**误判**。
工具：`.testtmp/audit_calls_1e.py`。

**4.4 `.strip()` 让尾随空行不进 prompt**：digest 的 relate/cognize 三份文本从前末尾多一个
`\n`，md 化之后**少 1 字节**——**这是有意的**（文件末尾空行不该改变 prompt）。
所以"只差尾随空行"是**通过**, 不是差异。

**4.5 md 里没有"注释"这回事** —— 写进去就进 prompt。判据与说明只能住 Python 注释。
**反引号也会进 prompt。**

**4.6 `prompts/*.md` 是数据文件** —— 打包 exe 时要收进包（`contract/digest/prompts/` 与
`llm/prompts/` 两处）。`infra/paths.py` 那一步一起看。

**4.7 槽只有一种写法了（1d 起）**：`{{名字}}` + `contract.slots.render_template`。
`_SLOT` 正则只认 `\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}` ⇒ JSON 示例里的 `{` 与它无关。
⚠️ **模板的槽与给的值两个方向都必须对上**（多一个少一个都抛）——
所以"这批 md 共用一组槽"的写法**不能**再用 `.replace` 那套。

**4.8 跑测试必须带这两个参数**（`%TEMP%\pytest-of-johnf` 权限坏，在工作区**之外**，没清）：
```powershell
python -m pytest --basetemp=.testtmp/_pytemp -o cache_dir=.testtmp/_pcache
```

**4.9 解释器用 `C:\Users\johnf\miniconda3\envs\live2be\python.exe`** —— conda `base` 缺 `jieba`。
ruff 在 `…\envs\live2be\Scripts\ruff.exe`。

**4.10 PowerShell 会吃掉 `-c` 里的嵌套引号**（本会话又栽 1 次）。
一律**把脚本写成 `.testtmp/*.py` 再跑**；`git commit` 一律 `-F 消息文件`。

**4.11 行尾不统一**：337 个 .py 里 78 个纯 LF、259 个 CRLF，没有 `.gitattributes`，
`core.autocrlf=true` ⇒ 每次 commit 刷 "LF will be replaced by CRLF" 警告。**既有事实，别顺手改**。
⚠️ **按行号改文件要按字节切 `\n`**（CRLF 下空行是 `b'\r'` 不是 `b''` —— 本会话断言空行时栽过一次）。

**4.12 删顶层类/函数要连 `@decorator` 一起删**（`ast.ClassDef.lineno` **不含装饰器**）——
栽过：留下孤儿 `@dataclass(frozen=True)` → `TypeError: Cannot overwrite attribute __setattr__`。

**4.13 API 面守门**：给这 9 个模块增删模块级名字要刷 `tests/fixtures/api_surface.txt`
（`$env:SPLIT_API_UPDATE='1'`）：`webgui.bond` · `webgui.chat` · `core.bond.bond_story` ·
`contract.records` · `contract.streams` · `contract.issues` · `core.mmt.engine` ·
`apps.vn_cli` · `llm.client`。

**4.14 别把 `Measure-Object -Line` 的行数当真**（比 Python 的 `splitlines()` 少约 6%）。

**4.15 `err()` 的"勿包进中间函数"有一条有意的例外**：`contract/prompt_files.py::load_md`
故意让错误前缀是 `[prompt_files.py]`，有用例钉着这条意图。

**4.16 `_LABELS` 是 `AnnAssign`（`x: T = {…}`）** —— AST 只认 `ast.Assign` 会**静默取空集**
（本会话 1f 的用例自己栽过一次）。凡扫"带注解的模块级常量"都要 `AnnAssign` 一起认。

**4.17 一个名字在 md 里不等于它是"料名"** —— `【】` 在本项目还当
① 角色代称（`momotalk_rules.md` 的 `【你（当前角色）】`）② 序数小节
（`bond_shots.md` 的 `见上面【二】的组合拳`）③ **短形式交叉引用**（`见下方【回忆】专段`）
用。那三处**没动**（记在这儿, 等用户裁）—— 1f 的守门**故意只圈 digest 那一家**
（那里 `_sections_for` 会逐字对账, 段头是真契约）。

**4.18 改 `contract/digest/prompts/` 下**任何**一个字节，都要跑 `verify_1c.py`。**
本会话栽过：1f 只把 `parts/row_fields.md` 的一句正文从 `【哪一段】` 改成 `**哪一段**`
（`【】` 是段头不是强调号），**焦点测试 217 条全绿**，而 `verify_1c` 有 **3 个形态**
（`split|bond|1` / `split|bond|2` / `split|mmt|1`）对不上 —— 因为它进的是 **split 相位**。
⇒ 纪律两条: ① 动完**立刻**跑三个 verifier（`verify_1c` / `capture_prompts_1d check` /
`capture_1e check`）; ② **有意的**改动要写进 `EXPECTED_CHANGED` **并写为什么** ——
一条长期红着的判据 = 没人看的判据**（与它拦的东西同归于尽）**。

---

## 5. 本会话的裁决与设计注记（写给自己，别再问一遍）

### 5.1 用户已裁过的
- **A 案**（契约文案留 `contract/`、只换承载形式）——理由：*"哪些是契约文件，还是有点区别的"*。
  ⇒ `contract/digest/prompts/` 与 `llm/prompts/` **两个文案家是有意的**，
  分界线 = **"输出成什么形状"归契约，"干什么"归 llm**。
- **Round B（understand）整族删** —— *"那一族确实是过期了，只是还没来得及删掉"*。
- **`apply_revision_package` 删** ⇒ 等于放弃 `deep` 轮的预定执行器。
- **`add_link`/`remove_link` 删** —— *"现在是 akin 了，那些都是残党"*。
- **`profile` 先停产不真删**（B 案, 本会话做的）：*"a吧先"* + *"由于我们没有真删 profile，
  可以留着"* —— **真删格式要等确认没有老档依赖**（本机 0 个 profile 节点, 但 `.bak` 没扫全）。
- **测试直接删**（不是改写）—— 但"只是**调用**了要删的东西"的那几处按**同款断言**换到活 API
  （本会话 3 处: `test_edge_primitives` / `test_delete_filters_edges` / 一跳矛盾）。
- **顺手修 OK**（删了东西却没改的文案 / 断言 / docstring）。
- **`MAX_ALIAS_LEN`（revise.py:52）留着** —— 零读者, 但它是"8 字上限"那句口径的载体。
- **反引号只包 ≤20 字的短槽**（详见 §1 的 1d-2 清单, **未做**）。
- ⏸ **`entity.text` 的 digest 侧写者缺口**: 用户 2026-10-12 裁"以后再说"。

### 5.2 设计注记（我判断的，已写进代码注释）
- ⭐ **"没人跑的契约文本，就是没人会发现它过期的文本"** —— `understand.md` 的 `canon`
  烂掉一整族而没人发现, 就因为那一族**没有任何生产消费者**。1f 那条守门就是补这个。
  **1f 第一次跑就抓到 3 处**（§5.3）⇒ 这条判断是对的。
- ⭐ **静默的两种代价**（1d 实证）：`.replace` 填槽的**两个方向都静默** ——
  本会话炸出 **2 处一直在空转的替换**（填了一个模板里根本不存在的槽）。
  ⇒ "统一到会抛的原语"不只是洁癖, 它**当场变现**。
- ⭐ **"停产"与"删格式"是两件事**（1c）：停的是**生产**（契约不要 + 解析丢行），
  留的是**机器与格式**（`KINDS`/读侧/`episodes` 那一支/`_PREFIX`）。
  判据三条缺一不可：① 契约不再要 ② 她惯性还写得出 ⇒ **认得出、⛔ 不判非法**
  ③ 图上一个新节点都不会再建。⛔ ②是关键 —— 判非法会**罚她重写整段**。
- ⭐ **过期文案的三种量级**：**契约文案**（`understand.md` 的 `canon`）·
  **活代码的 docstring**（`read/recall.py` 整段 Round B；`revise.py` 的"三个入口"）·
  **死指针**（`_rewrite` / `_link_about` / `apply_decisions` 全仓 0 个 `def`）。
- ⭐ **v1 不是被"重写"顶掉的，是被拆 / 上移 / 砍三种处置取代的**：拆（万能修订包 →
  三趟执行器）· 上移（行形状解析与结构硬规则搬到**契约层**）· 砍（`update` 改写 /
  `unlink` / `resolve` / `accrue` 计数）。**机器件被留下复用**（`_create_belief` /
  `_soak` / `_add_edge` / `_find_duplicate` / `link_entity_tags`）。
- ⭐ **三层重试**（1i 起要收的是第 ③ 层）：① 传输级 `llm/client._request_with_retry`
  ② 解析级 `core/digest/llm_call.llm_chat`（不抛，返回 `(resp, err)`）③ 结构级
  `core/digest/call._round_call`（回灌重试 1 次）。**③ 是 `llm/retry.call_with_feedback`
  的第三份实现**, 而且 `llm/retry.py` 的 docstring **自己就把 digest 列在待收口的三份里**
  （bond · mmt 三段式 · digest）⇒ 这一条不是我的推断, 是那份文件自己招的。

### 5.3 1f 抓到 / 顺手改掉的三处（**这就是那条守门的价值证明**）
1. ⭐ **`digest_relate.md` 把料名写短了**：文案说 `【本次新经历】`，而引擎真正印的段头是
   **`【本次新经历（含引擎候选标注）】`**（`relate.py:81` 与 `ROUNDS.material` 逐字对账
   ⇒ 长名才是真的）。**同一个东西两个名字，而模型要在 system 里认 user 里的段头**。
   修**文案**不修段头 —— 段头带 `（…）` 注解是本项目常态（`【角色人设（锚点）】` /
   `【现有经历（候选）】` 都被完整引用），这一处是例外。
2. `parts/row_fields.md:1` 把 `【哪一段】` 当**强调号**用 ⇒ 改成 `**哪一段**`
   （`【】` 在本项目是**有语义的**，见 `marks.py` / `docs/CONTEXT_MARKS.md`）。
3. `parts/row_fields.md:2` 的 `【羁绊剧情】` 是**时间线板块标签** ⇒ 1f 的"合法出处"
   因此有**第三类**（`core/session/renderer.py::_LABELS`）。

### 5.4 还没查完 / 已报待裁的
- **`examples` 字段**（✅ **已划去**, 见 §1）: 用户 2026-10-13 裁"没有删除的必要,
  可以看作扩展, 延后"。现状 = **有读者、有守卫、零活写者**（写者 `_apply_accrue`
  随 1a 删了）—— 留着当扩展位, ⛔ 别再报"它是死代码"。
- **调用层归位**（2026-10-13 用户提出）: `core/digest/llm_call.py`（85 行, 零 digest
  依赖）**位置错了** ⇒ 搬 `llm/`（岔路: `client.py` 还是新开 `robust.py`）;
  `core/digest/call.py`（164 行, 认 `RoundSpec`+契约渲染）**位置是对的** ⇒ 只改名。
  详见 §1h。
- **`contract/schema.py` 的 61 行生产死代码**（`build_schema` + `export_definitions` +
  `_SHELL_FIELD_DESCRIPTIONS`）：AST 核实 = 无生产调用者（`build_schema` 只被
  `archive/ide_editor` 用；`export_definitions` **全死**，0 生产 0 测试，只在
  `contract/__init__.py` 再导出）。"A 方案数据面（给 JS/WebLLM）"从来没接上。
  ⇒ **报给他了, 没动**（死代码不许自行处置）。
- **`core/bond/emotion_annotate.py` 的 v1 句级标注簇**（AST: 生产 0 调用者）：
  `_try_batch` · `annotate_emotions_smart` · `annotate_emotions` · `fill_missing_emotions`
  + `llm/prompts/emotion_annotate.md`。⛔ 但**同模块的 `_extract_array` 是活的**
  （`place_annotate` 与 `emo_text` 都用它）⇒ **只能摘那一簇, 不能删模块**。
  ⇒ **报数待裁**。
- **`ctx.player_ids` 现在恒空**（1c 之后 profile 不再产）：消费面 3 处
  （`relate.py:73` / `cognize.py:50` 的 `exclude=` · `attribute.py:33` 的节点表）+
  `rounds/base.py` 的字段 + `episodes` 的第二个返回值。**留着**（B 案的"留机器"），
  但它已经是一根**没有水源的管子** —— 真删格式那一步一起收。
- **`segment.py:219/241` 的 profile 过滤**（读侧）与 `digest_relate.md` 里
  "今天只有 `belief`" 那句：都是"停产但兼容"的痕迹，等真删格式时统一清。
