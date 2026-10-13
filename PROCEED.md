# PROCEED.md — 接续用（**整篇覆盖写**；上一版见 git 历史）

> **位置 `b451e3a` · 树干净 · 本会话 `cb9a6d7` → `b451e3a`（+8 个提交）**
> 上一版 PROCEED 讲的是"拆 digest_registry"的计划，**那批已经做完**（见 §3）。
> 现状：**全量回归 1483 passed（约 2.5 分钟）· ruff 386**。

---

## 0. 三十秒概览

用户要的是：把这个"缝补出来的"项目改成**正常 Python 项目的样子**，然后再扩展。
他定的四条：① 彻底改（允许改包名/import 路径）② 顶层保持分散但改名 ③ 测试随行重写
④ 文档只写 mmt/vn 输出形式 + digest + 召回三块（其余写进各包 `__init__.py`）。

工作方式（他明确要求）：
- **逐个包改，每完成一个包他会详细了解询问** → 做完整阶段就停下等他
- 每步**独立提交**；小板块配冒烟；大板块才跑全量回归
- **死代码一律先过目、先报数**，不许自行处置（本会话已按这条删了三批，都报过数）

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

### 1a · 清残党第二刀（**下一刀**）· `apply_revision_package` 簇
用户已确认删（*"我指的是 revision_package"*）。**296 行 + 12 条测试**：

```
core/brain/revise.py   apply_revision_package 96 · _apply_action 92 · _apply_accrue 34 ·
                       _parse_create 33 · _build_merged 17 · _connection_rule_violations 17 ·
                       _err 3 · 嵌套 fail 4   ·   还有 RevisionResult（只它用）
core/brain/__init__.py 再导出 RevisionResult / apply_revision_package
core/brain/store.py    4 个旧接口 shim（**它一死，这四个就零生产调用者**）:
                       add_link / remove_link / add_contradiction / remove_contradiction
                       （用户原话："现在是 akin 了，那些都是残党"）
tests                  test_wiki_revise 12 条 · test_wiki_store 里碰 shim 的几条
```
⛔ **`classify_pair` 不删** —— 它另一个活路是**旧档自举**：
`store._load → _load_edges → infer_edges → _emit → classify_pair`（只有点表、没有边表的老
wiki 从 `links` 还原边）。实测本机 30 行 wiki 里 0 行带旧字段、haruka 已有 `edges.jsonl`
⇒ 今天触发不了，但它是迁移网。

### 1b · 清残党第三刀 · `examples` 字段全套
第二刀做完后它**唯一写者自动消失**（`_apply_accrue`），这刀变成纯字段下线：

```
core/brain/nodes.py       字段 154 · 不变量 205-206 · normalize 218 · 字段表 92 · from_dict 310
core/brain/read/pack.py   68/79（⭐ 它是**参与语义匹配的正文面**，不只显示）
core/brain/read/recall.py 322-323 · core/brain/read/render.py 145/153
core/brain/store.py       208 的注释
tests                     test_wiki_nodes(3) · test_wiki_render(2)
```
判据：**有读者、有守卫、零活写者**；且存量数据里唯一一行带 `examples` 的是个 **belief**
（`igusa_haruka/e0001`），而所有读者都是 `profile` 门控 ⇒ **那行谁都不读**，现网行为零变化。

### 1c · `profile` 节点 kind 下线（用户裁：*"entity.text 取代了它的定位"*）
⚠️ **这是删一个节点 kind（数据格式），先报波及面再动**。已知面：
```
nodes.py    KINDS 五→四 · _REQUIRED["profile"] · examples 不变量（若 1b 已删则自然没了）
            · is_player_profile() 231-241 · docstring §3 的 kind 表
episodes.py _create_a_nodes 的 profile 分支（99-109）· 返回值 (episode_ids, player_ids)
parse.py    967/972/988（kind=profile 分支 + 错误文案）· tables.PLAYER_SUBJECT
graph.py    _COGNITION / _ABOUTABLE · store.py 的 id 前缀表（"profile": "e"）
read/       render.py 的「关于老师」标签 · recall.py 默认 kinds · channel_impl · pack.body_of
segment.py  _collapse_bond_episodes 的 profile 排除
rounds/     NODE_FACES · ("profile", (…)) 那一格
契约        record.md 的 `"kind": "profile"` 段 + llm/prompts/digest_record.md 那句
测试        触及 profile 的一批
```
⚠️ **一个必须先想清的点**（见 §5.3）：`entity.text` 今天**只有出厂物化在写**
（`interperson.yml`），digest 侧没有写者 ⇒ "取代"目前是**定位**上的取代，不是**写者**上的。

### 1d · B · 单花括号 → `{{}}` + 反引号标注（用户已批）
`llm/prompts/` 里 9 份 md 用**单花括号**（`{lexicon}` / `{char_id}` / `{sentences}`…），
填法是 `.replace("{x}", v)`（5 个模块 8 处）。**全仓没有一处对 prompt 用 `.format()`**。

- 换成 `{{x}}` + `contract.slots.render_template` ⇒ 漏填**当场炸**（`.replace` 是静默的）
- ⚠️ 安全前提已验证：那 9 份 md 里有 **88 处裸 `{`**（JSON 例子），而 `render_template`
  只认 `{{…}}` ⇒ 它根本不看那些
- ⭐ **反引号只包"短槽"**（用户裁：**20 字以下**）；长块槽（`lexicon`/`sentences`/`records`/
  `digest_schema`）**不包** —— 包了会把整块变成 code span，而且反引号**会进 prompt**
- 顺手可写守门："模板里的槽 == 填的槽"

### 1e · C · `contract/schema.py` 外移（排在 B 之后）
292 行 / 154 段字符串 / **5281 字符**。⚠️ **形态与 digest 不同**：`build_line_schema` /
`build_record_schema` 的取值清单是**运行时从动作注册表生成**的 ⇒ 混合形态：
**外壳 + 硬规则 + 示例进 md（`{{槽}}`），动作表仍由代码渲染**。所以必须先做 B（槽语法统一）。

### 1f · E · 补一条守门（约 30 行）
> 契约 md 里出现的每个 `【X】`，要么是**契约自造的小节**，要么在**料名全集**里。

料名全集**从代码自动提取、零维护**：`rounds/*.py` 里每个料是 `("本段骨架", text)` ⇒ AST
取第一项。这条能抓住"改了料名忘改契约"——正是 `understand.md` 那类过期**为什么没人发现**的机制。

### 1g · D · `infra/paths.py`（等用户拍 frozen 布局）
必要性（两层）：① 它是 `llm → core` 的**最后一根线**（`llm/task_levels.py:45` 只要
`paths.SETTINGS_PATH`）② **打包 exe 的硬前提**：现在 `ROOT = Path(__file__)…parent.parent`
**一个值服务三种根** —— 只读资源（config/assets/prompts）· **读写同一份**的 `settings.toml`
（GUI 设置页写它，`webgui/store.py:169`）· 运行时数据 `data/`（事件流真源）。frozen 下三者
不重合，`data/` 落临时目录 = **退出即丢**。
成本：**25 个常量 / 30 个 import 点 / ~90 处属性引用 / 32 个文件** + `tests/core/test_paths.py`。
⭐ **代码便宜，决定贵**：要他拍"三个根各放哪"。

### 然后 · 批次 2 起
纯移动：`core` → `infra/` + `engine/`；`renderer` + `core/tui` → `tui/`；`apps` → `cli/`。
⚠️ 顺带：`renderer → core.media.catalog` 3 处（表现层反向依赖引擎），`tui/` 那一步一起处理。

---

## 2. 必读文件

| 文件 | 为什么 |
|---|---|
| 本文件 | —— |
| `.testtmp/capture_schemas.py` · `verify_1c.py` · `schemas_1c_before.json` | **逐字节判据**（15 个形态）；改契约文案/搬渲染代码必跑 |
| `contract/digest/__init__.py` | 包地图（五个模块怎么分工、加载顺序、门面纪律） |
| `contract/digest/prompts/` | ⭐ **文案真源**（7 份相位 md + `parts/` 7 份片段）；改提示词只动这里 |
| `contract/digest/registry.py` | 渲染 = **读 md + 填槽**（`PHASE_FILES` + 8 个槽） |
| `core/digest/rounds/__init__.py` | ⭐ **轮次真源 `ROUNDS`**（key/步序/prompt/相位/parse/料/预算一处说全） |
| `core/brain/revise.py` | 现在是**三趟执行器**（relations/cognitions/entities）+ 待删的第二簇 |
| `tests/core/test_import_direction.py` | 分层守门 + **豁免表**（`LLM_CORE_ALLOWED` 已收窄到只剩 `core.paths`） |
| `TODO.md`（第一条） | prompt 外移那条待办 + 实测分布 |
| `CLAUDE.md` | ⚠️ 89 KB 且**多处过时**；当索引读，冲突时信代码 |

---

## 3. 已做的更改（按批，都在 master）

| 批次 | 提交 | 做了什么 |
|---|---|---|
| 0 · 0.5a–e | `dbb8ca2` `df8ef0d` `67f8ba8` `8cc1907` `e66e504` `4420f31` `5523fd4` `809b017` | `pyproject.toml` 成唯一工程真源 · ruff 配置诚实化 · 删 257 个 coding 头 · **修真 bug**（digest 预算预检 `>`→`>=`，Windows 时钟粒度 15.6ms）· 删 100 个 `sys.path` hack · 修 3 处注解引用未导入名 |
| 1a | `2a91e29` `b15cfdc` `6af53af` `54a61e6` `4aab6f5` | 抽三个共享原语：`llm.client._classify` · `llm.retry.call_with_feedback` · `llm.prompts.render_template` |
| 1b-1 | `a15f426` | 删假旋钮 `include_examples`；修 `record` 相位的硬编码查名 |
| 1b-2a | `0504bc3` | digest 校验实现 → `digest_parse.py`（2345 → 1145 行） |
| PROCEED | `cb9a6d7` | 上一版交接（拆 registry 的计划） |
| **1b-2b** | `2a23ba1` | 拆常量/文案 → `tables.py` + `docs.py`（1146 → 442）；解掉 `parse↔常量↔registry` 的环，7 个函数内 import 收回模块级。**逐字节不变** |
| **1b-2c** | `2850094` | 四个平铺模块 → `contract/digest/` **包 + 门面**（51 名按真家分块再导出）；引用面 8 文件按真家重写；私有名**刻意留深路径** |
| 注释清理 | `bba8afd` | 净 **-47 行**注释：墓碑（描述已不存在的东西）+ 两处**过时现状**（`PHASE_RELATE`/`PHASE_COGNIZE` 写着"没有轮在用它"，实测都在跑）+ 一处**假话**（`notes.py` 说契约层还有活着的 `PINNED_OUTCOMES`） |
| **1c** | `87b5696` | ⭐ **契约文案搬进 md**：`prompts/` 7 份相位 + 7 份片段（483 行）；`docs.py` 579→146 · `registry.py` 433→187；`render_template` 下移 `contract/slots.py`；两个 md loader 合一（`contract/prompt_files.py`）。判据 **9/15 逐字节 + 6 个只差一个尾随空行** |
| 刀 1 | `46c5acd` | `llm` 三处不再绕 `core.common`（直连 `contract.errors`）⇒ `llm → core` **4→1**；**豁免表收窄**（删掉已无人用的 `core.common`） |
| 刀 2 | `8ca6953` | 两个 md loader 合一 → `contract/prompt_files.py::load_md`；顺手统一"列哪一层的清单"与错误前缀 |
| **清残党 1** | `b451e3a` | **Round B（understand）整族下线**：`-819/+15`。`parse_round_b`+`_parse_links` 146 行 · `apply_decisions`+`_ensure_cognition` 126 行 · `understand.md` · `TOUCH/UPDATE/ADD`/`DECISIONS`/`PHASE_UNDERSTAND` · 门面 6 名 · **19 条测试** · 3 处死指针 |

**当前层间账**（AST 实测）：
```
contract  → （无）                    ← 唯一零对外依赖
llm       → contract 5 · core 1       ← 只剩 task_levels 的 core.paths（等 infra/paths.py）
core      → contract 24 · llm 34      ← 单向；core↔llm 的环**只剩那 1 处**
renderer  → core 3                    ← core.media.catalog（批次 2 的 tui/ 一起处理）
```

---

## 4. 隐形坑（踩过的，别再踩）

**4.1 `ruff check --select X --fix` 是陷阱。** `--select` 会**覆盖** pyproject 的 select，
把其他规则关掉 ⇒ "本来生效的 noqa"被判成无用批量删掉（实测：192 条带说明的 `# noqa: BLE001`
被删光）。删 noqa 只用 `.testtmp/strip_dead_noqa.py`。**同理别用 `--select` 跑 fix。**

**4.2 动 F401 前必须查"有没有人从这个模块 import 走"**（ruff 看不见再导出）。栽过 5 处。

**4.3 判断"死代码"必须用 AST 认 `Call`，不能 grep 行。** 本会话栽过：`apply_decisions` /
`_parse_create` / `_ensure_cognition` / `_rewrite` / `_link_about` 的"生产调用者"**全是注释
与文档串**。反面：`classify_pair` 看着像残党，其实是**旧档自举**的活判据。

**4.4 逐字节判据怎么跑**（改契约文案/搬渲染代码时）：
```powershell
& $envPy .testtmp\capture_schemas.py > .testtmp\schemas_after.txt
& $envPy .testtmp\verify_1c.py          # 跟 .testtmp\schemas_1c_before.json 逐个比
```
⚠️ **`.strip()` 让尾随空行不进 prompt**：relate / cognize / understand 三份文本从前末尾
多一个 `\n`，md 化之后**少 1 字节**——**这是有意的**（文件末尾空行不该改变 prompt）。

**4.5 md 里没有"注释"这回事** —— 写进去就进 prompt。判据与说明只能住 Python 注释。
**反引号也会进 prompt**：只包短槽（≤20 字），长块槽别包。

**4.6 `prompts/*.md` 是数据文件** —— 打包 exe 时要收进包（`contract/digest/prompts/` 与
`llm/prompts/` 两处）。`infra/paths.py` 那一步一起看。

**4.7 两种槽语法并存**（现状味道）：`llm/prompts/` 里 6 份 digest 用 `{{digest_schema}}`，
另 9 份用单花括号 + `.replace`。1d 就是收这个。

**4.8 跑测试必须带这两个参数**（`%TEMP%\pytest-of-johnf` 权限坏，在工作区**之外**，没清）：
```powershell
python -m pytest --basetemp=.testtmp/_pytemp -o cache_dir=.testtmp/_pcache
```

**4.9 解释器用 `C:\Users\johnf\miniconda3\envs\live2be\python.exe`** —— conda `base` 缺 `jieba`。
ruff 在 `…\envs\live2be\Scripts\ruff.exe`。

**4.10 PowerShell 会吃掉 `-c` 里的嵌套引号**（本会话栽了 5+ 次）。
一律**把脚本写成 `.testtmp/*.py` 再跑**；`git commit` 一律 `-F 消息文件`。

**4.11 API 面守门**：给这 9 个模块增删模块级名字要刷 `tests/fixtures/api_surface.txt`
（`$env:SPLIT_API_UPDATE='1'`）：`webgui.bond` · `webgui.chat` · `core.bond.bond_story` ·
`contract.records` · `contract.streams` · `contract.issues` · `core.mmt.engine` ·
`apps.vn_cli` · `llm.client`。

**4.12 别把 `Measure-Object -Line` 的行数当真**（比 Python 的 `splitlines()` 少约 6%）。

**4.13 `err()` 的"勿包进中间函数"有一条有意的例外**：`contract/prompt_files.py::load_md`
故意让错误前缀是 `[prompt_files.py]`（文件找不到就发生在加载器里），有用例钉着这条意图。

**4.14 行尾不统一**：337 个 .py 里 78 个纯 LF、259 个 CRLF，没有 `.gitattributes`，
`core.autocrlf=true` ⇒ 每次 commit 刷 "LF will be replaced by CRLF" 警告。**既有事实，别顺手改。**

**4.15 `profile` / `examples` / `entity.text` 是三个状态不同的"格子"**：
`profile` 三层写者齐备但真机 0 产出 · `examples` 结构性零写者（有读者有守卫）·
`entity.text` 只有出厂物化在写。**别把它们当同一类。**

---

## 5. 本会话的裁决与设计注记（写给自己，别再问一遍）

**5.1 用户已裁过的**
- **A 案**（契约文案留 `contract/`、只换承载形式）——理由：*"哪些是契约文件，还是有点区别的"*。
  ⇒ `contract/digest/prompts/` 与 `llm/prompts/` **两个文案家是有意的**，分界线 =
  **"输出成什么形状"归契约，"干什么"归 llm**。
- **Round B（understand）整族删** —— *"那一族确实是过期了，只是还没来得及删掉"*。
- **`apply_revision_package` 删**（他先说要留、后改口 *"我指的是 revision_package"*）⇒
  等于**放弃 `deep` 轮的预定执行器**；`store.py:315-320` 那句"不删 shim，为了已规划的
  深整理路径（V3-6）"随之作废。
- **`add_link`/`remove_link` 删** —— *"现在是 akin 了，那些都是残党"*（`add_contradiction`/
  `remove_contradiction` 同族同命运）。
- **`profile` 节点 kind 下线** —— *"entity.text 取代了它的定位"*（见 §5.3 的那点保留）。
- **反引号只包 ≤20 字的短槽**。
- **字段类改动先冻结**（后对 `examples` 单独开口子）。

**5.2 设计注记（我判断的，已写进代码注释）**
- ⭐ **"没人跑的契约文本，就是没人会发现它过期的文本"** —— `understand.md` 的 `canon`
  过期了 2026-09-21 那一整族，没人发现，因为这一族**没有任何生产消费者**。1c 的逐字节
  判据只能证明"搬得没差"，**证明不了"内容还对"**。⇒ 1f 那条守门就是补这个。
- ⭐ **过期的三种量级**（本会话各撞到一个）：**契约文案**（`understand.md` 的 `canon`）·
  **活代码的 docstring**（`read/recall.py` 整段 Round B；`revise.py` 的"三个入口"写着
  一个已死、一个名字不存在）· **死指针**（`_rewrite` / `_link_about` 全仓 0 个 `def`）。
- ⭐ **`examples` 与 `profile` 的区别**（别混）：前者**没有任何活代码路径能写它**（结构性死）；
  后者**契约+解析+执行器三层齐备、每天都在问她**，只是她一次没答（功能已接线、模型没产出）。
- ⭐ **v1 不是被"重写"顶掉的，是被拆 / 上移 / 砍三种处置取代的**：拆（一个万能修订包执行器
  → 四个窄执行器）· 上移（行形状解析与结构硬规则搬到**契约层**：`_parse_create`→`parse_*`、
  `_connection_rule_violations`→`parse_cognitions` 的"至少一条证据"、`_ensure_cognition`→
  引用域/kind 校验）· 砍（`update` 改写 belief / `unlink` / `resolve` / `accrue` 计数）。
  **机器件被留下复用**（`_create_belief` / `_soak` / `_add_edge` / `_find_duplicate` /
  `link_entity_tags`）—— 这就是 `revise.py` 没全死的理由。
- ⭐ **三层重试**（1d 的靶心）：① 传输级 `llm/client._request_with_retry` ② 解析级
  `core/digest/llm_call.llm_chat`（不抛，返回 `(resp, err)`）③ 结构级
  `core/digest/call._round_call`（回灌重试 1 次）。**层③ 与 1a 抽出的
  `llm.retry.call_with_feedback` 是同一件事的两份实现。**

**5.3 还没查完的两条**
- `profile` **为什么 0 产出**：怀疑是**结构不匹配** —— R1 的输入是"骨架（每条切片一行）"，
  而 `profile` = "关于老师的事"**不属于任何一段经历** ⇒ 她**没有写它的位置**。
  已知：R1 的覆盖检查只数 episode（`episodes.py:93` 的 `(episode_ids, player_ids)` 分开），
  所以结构上**允许**多写一行。**没验**：契约里那句话是不是弱到看不见。
- `entity.text` 的 **digest 侧写者缺口**（用户 2026-10-12 裁"以后再说"）：新看法今天落
  **belief**，`entity.text` 只有出厂物化在写 ⇒ 用户说"entity.text 取代了 profile 的定位"，
  但那是**定位**上的取代，不是**写者**上的。
