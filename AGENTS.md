# AGENTS.md — Live2Be 项目导航

**这份文件是 agent 的唯一活入口。** 2026-10-15 起取代根目录那份 88 KB 的 `CLAUDE.md`
（它多处过时，原文归档在 `docs/archive/CLAUDE_2026-09-20.md` —— 带日期的名字是**故意的**：
harness 会按精确文件名 `AGENTS.md` / `CLAUDE.md` 自动加载指令文件，叫 `CLAUDE.md` 就会被
再注入一遍，白吃 64 KB 预算）。

这里只放**导航与纪律**：机制细节住在代码注释、各包的 `<pkg>/.md`、`docs/DESIGN_*.md` ——
因为细节会随代码变，而导航不应该。**与代码冲突时信代码**，并顺手把这里改掉。

---

## 0. 项目是什么

LLM 驱动的角色互动叙事引擎（灵感：Blue Archive）。玩家在类微信的 **MomoTalk** 里和角色
聊天，羁绊到位时由 LLM 主动触发**羁绊剧情**（视觉小说），关键时刻进**纪念模式**生成立绘。

一句话分工：**LLM 负责"演"，引擎负责"判"** —— 主 LLM 每轮只产创作文本（MMT 行流 /
Bond 记录流），情绪、地点、事件、动作名这些"判定"由引擎或廉价标注层做。

三条主线（读代码先认这三条）：

| 主线 | 一句话 |
|---|---|
| 创作 | 主 LLM 只写文本；结构与判定全在引擎（`contract/` 定义"能输出什么形状"，`core/` 判它） |
| 事实 | `soul/events.jsonl` 是 **append-only 唯一真源**；恢复 / 回放 / 记忆全从它派生 |
| 体感 | 生成发生在玩家阅读时（预热 / 预生成 / 双路标注并行 / 门控）；system 前缀逐字节稳定以吃上下文缓存 |

---

## 1. 分层与包

```
contract → infra → llm → core → tui / webgui / cli
```

| 包 | 一句话 | 细节 |
|---|---|---|
| `contract/` | 契约地基：LLM 能输出什么形状、谁来判它；两侧共用的最小原语 | [`contract/.md`](contract/.md) |
| `infra/` | 路径五个根 · settings 唯一读口 · 原子写 · 融合形状 | [`infra/.md`](infra/.md) |
| `llm/` | 传输层：客户端 / 档位 / 重试 / 生图 / 文案仓库 | [`llm/.md`](llm/.md) |
| `core/` | 领域引擎 —— 判定都在这儿 | [`core/.md`](core/.md) |
| `tui/` | 终端表现层（原名 `renderer/`），是**库**：`webgui` 也借它的 `effects` | [`tui/.md`](tui/.md) |
| `webgui/` | 网页壳 + 前端（无构建步骤）—— **唯一的产品壳** | [`webgui/.md`](webgui/.md) |
| `cli/` | 终端**调试**入口（原名 `apps/`）：不追 webgui 行为 | [`cli/.md`](cli/.md) |

另外：`tests/`（按域分 `core/ llm/ tui/ webgui/` + `fixtures/`）· `config/`（人设与世界观）·
`data/`（运行时真源，gitignore）· `assets/`（素材，gitignore）· `docs/`（设计稿与执行记录）·
`experiments/`（真 API 基准与浏览器冒烟，手工跑、烧 token）· `packaging/`（打 exe 的 spec、
素材清单与切包脚本，见 `docs/PACKAGING.md`）· `setup_tool/`（**资源配置辅助工具**，独立小 exe，见
[`setup_tool/.md`](setup_tool/.md)）· `archive/`（历史代码）· `guidance/`（角色卡写作指导）。

**三条不变量**（`tests/core/test_import_direction.py` 钉着，反向 import 一律视为 bug）：

1. `llm → core` 必须是**零**（横切件因此住在 `contract/` 与 `infra/`，不塞进 `core/`）；
2. `core → tui / webgui / cli` 不许存在（引擎要的展示数据留在 `core/{display,streaming,text}.py`
   —— 搬去 `tui/` 就会形成 `core ↔ tui` 双向依赖）；
3. 谁也不许 import `cli/`。

---

## 2. 要改什么，去哪

| 你想改 | 入口 |
|---|---|
| MMT（聊天）每轮协议 / 动作 / 兜底修复 | `core/mmt/engine.py`（行协议循环）· `core/mmt/mmt_actions.py` · `mmt_check.py` · `mmt_repair.py` |
| 羁绊剧情：记录流解析 / 板派生 / 状态机与历史 | `core/bond/bond_story/{engine,boards,scene}.py` |
| 网页侧剧情状态机（预生成 / 标注 lane / 回放 / 收尾 / 纪念） | `webgui/bond/`（模块分工见 `bond/__init__.py` 那张表） |
| 提示词装配（盒 / 动态尾 / 任务卡 / 注入报表） | `core/promptkit/`（段落实况看 `promptkit/report.py`） |
| 事件流读写 / 恢复窗口 / 认章与回放 | `core/session/{store,renderer,chapters}.py` |
| 记忆消化：**每段几轮、每轮吃什么写什么** | 真源 = `core/digest/rounds/__init__.py` 的 `ROUNDS` 表 —— **别在文档里抄轮次表**；机制见 `core/digest/.md` |
| 记忆读路径（召回 / 注入视图 / 旋钮） | `core/brain/read/`（图数据层 = `core/brain/`，纯 stdlib、零 LLM） |
| 三条标注：情绪 / 换场 / 选图 | `core/bond/{emo_text,place_annotate,variant_annotate}.py` |
| 地点表 / 背景与立绘 / 素材查库 | `config/settings/world/place_entities.json` + `core/media/` |
| LLM 客户端 / 档位 / 重试循环 | `llm/{client,retry,task_levels,task_labels}.py` |
| 生图（纪念立绘） | `llm/image_gen.py` + `webgui/bond/memorial.py` |
| HTTP 路由 / 前端 | `webgui/routers/` · `webgui/static/{js,css}/` |
| 启动 / 关停（Ctrl+C 被忽略，退出走前端「关闭服务」） | `python -m webgui.serve` · `webgui/{serve,shutdown}.py` · `webgui/routers/runtime.py` |
| 打 exe（onedir + 最小素材） | `pwsh packaging/build.ps1` · `packaging/live2be.spec` · `packaging/collect_assets.py` · `docs/PACKAGING.md` |
| 素材包（切包 / 首次运行按需下载） | `packaging/make_packs.py`（切）· `infra/packs.py`（读/下/校验/落地）· `webgui/routers/packs.py` + 前端「素材」页 |
| 资源配置 / 体检（独立小 exe） | `setup_tool/`（`python -m setup_tool --check`）· `packaging/setup_tool.spec` |

---

## 3. 契约与文案（改一个字节就要跑判据）

- 契约是"LLM 能输出什么"的**单源**：`contract/records/`（VN 记录流）· `contract/streams/`
  （域无关的行流骨架，MMT 与 VN 共用）· `contract/digest/`（消化的各轮契约：一份 spec
  同时驱动 prompt 渲染与结构校验）· `contract/schema/`（LLM 可见文本的渲染）。
- LLM 可见文案是**数据，不是代码**：`contract/{schema,digest}/prompts/*.md` ·
  `llm/prompts/*.md`。代码只负责取哪份、填什么槽、怎么拼。
- **每个调用点的 system / user 到底长什么样**（段序 + 形状样例 + 每段出处）见
  [`docs/PROMPT_SAMPLES.md`](docs/PROMPT_SAMPLES.md)；装配真源是 `core/promptkit/box.py` 的
  `DOMAIN_BOXES` 与 `tail.py` 的 `round_messages`。
- **示例才是形状的来源**：改规则书时必须同批改示例，否则模型只学会示例那个形状。
- 改完跑本机三份逐字节判据（`.testtmp/verify_1c.py` · `capture_prompts_1d.py` ·
  `capture_1e.py`，无参数即 check，退出码 0 = 没有计划外差异）。有意的改动要写进
  `EXPECTED_CHANGED`/`CHANGED` **并写为什么**。
- 改动任何进 system 的文案，还要刷夹具再人工审 diff：
  `$env:PROMPTKIT_UPDATE_FIXTURES='1'; python -m pytest tests/core/test_promptkit_baseline.py`

---

## 4. 数据与配置

真源（运行时数据都在 `data/`，gitignore）：

| 路径 | 是什么 |
|---|---|
| `data/worlds/{world}/characters/{char}/soul/events.jsonl` | 唯一真源：append-only，**不可改删**（废弃段用 marker 遮断） |
| `…/soul/wiki.jsonl` · `wiki.meta.json` | 记忆图（节点 / 边）与消化水位 |
| `…/soul/notes.json` | 随身笔记 —— **派生缓存**，真源是事件流里的 note 操作 |

**真机数据只读**：探针可以读、可以在内存里改，**绝不 `save()`**。
验证法：`git status -- data` 干净，且 `wiki.jsonl` 的 mtime 不变。

配置：`settings.toml`（gitignore，GUI 设置页读写；**唯一读入口 = `infra/settings.py`**，
不缓存、每次重读）· 角色六文件 `config/characters/{id}/` · 生图 `illustration.yml` ·
玩家档案 `config/player/profile.yml` · 人际关系 `config/settings/relation/interperson.yml` ·
世界观 `config/settings/world/overview.yml`。
优先级：构造参数 > settings.toml > `.env` > 默认。

环境开关：`LIVE2BE_IMAGE=off`（生图硬关；测试会话默认关）· `LIVE2BE_SETTINGS`（改 settings
路径，测试用）· `LIVE2BE_DIAG_LOG`（诊断日志落盘位置，`off` = 不落文件）·
`LIVE2BE_LOG=quiet|normal|verbose`（控制台详略；默认 normal = 轮询/静态请求不打印，
文件始终全量 —— 见 `infra/logsetup.py`）。

---

## 5. 开发纪律（本仓特有，别凭习惯来）

注释与文档：

1. 只写**关键点**：顶部 docstring 不许比它底下的代码还长；行内注释同理。
2. 不用 `★ ⚠ ⛔ ✅` 这类装饰符号 —— 满屏符号反而看不见重点。
3. 不写"用户拍板 / 用户裁 / 作者定的"这类表述；重要的是规则本身，不是谁说的。
4. 不写"曾经是什么"的悼词；解释放 `docs/`、提交信息、`PROCEED.md`，代码里只留结论。
   理由：长注释会随代码一起过时（本项目已踩过多次）。
5. 类型注解用 `X | None`（目标 3.12），不用 `Optional`。

测试与验收（每完成一小块就跑这一套）：

6. 跑测试必带 `--basetemp=.testtmp/_pytemp -o cache_dir=.testtmp/_pcache`（`%TEMP%` 权限坏）。
7. **两个域必须分开跑**（塞进一个进程会互相干扰）：`tests/core` 一条命令；
   `tests/llm tests/tui tests/webgui` 另一条。
8. **别用 `ruff --select … --fix`**：`--select` 会覆盖 pyproject 的配置，批量删掉有效的 `# noqa`。
   只改 import 顺序就跑 `ruff check --select I001 --fix <files>`。ruff 基线见 §7。
9. 守门测试要**双向证过会红**（造一个违规 ⇒ 红；删掉 ⇒ 绿），别只证绿。
10. 改了公共 API 面就刷快照再人工审 diff：
    `$env:SPLIT_API_UPDATE='1'; python -m pytest tests/core/test_split_safety.py`

前端（`webgui/static/`，无构建步骤）：

11. `node --check <file>` 兜底语法；纯逻辑单测 `node --test tests/webgui/js/typing.test.js`
    （**传文件，别传目录** —— Windows 上会 `Cannot find module`）。
12. 打字节奏的唯一实现是 `js/typing.js`，它必须是 `index.html` 里**第一个 classic script**。

交接：

13. `PROCEED.md`（仓根）= compact 交接：整篇覆盖写，只写四块（下一步 / 必读文件 / 已做的
    更改 / 隐形坑）。**它是共享的** —— 另一个会话（记忆层那条线）也在写它，别覆盖别人的小节。

---

## 6. 文档路由

| 文档 | 状态 |
|---|---|
| `AGENTS.md`（本文） | 唯一活入口：导航 + 纪律 |
| 各包 `<pkg>/.md` | 现行：作用 / 核心文件 / 纪律 |
| `docs/DESIGN_*.md` · `docs/EXEC_*.md` · `docs/AUDIT_*.md` | 设计稿与执行记录：**带日期、可能已漂移**；冲突信代码 |
| `docs/archive/`（含 `CLAUDE_2026-09-20.md` = 旧主文档） | 归档，只作考古 |
| `PROCEED.md` | 会话交接（滚动，会被整篇覆盖） |
| `README.md` · `TODO.md` · `CLAUDE_OPTIMIZE.md` · `DESIGN_BRAIN.md` | 尚未定稿或已过时：读前看各自状态头 |

老文档与旧注释里若见到 `CLAUDE.md §N`，那是**旧主文档的节号**（现居 `docs/archive/`）。
本文按**名字**引用规则（见下一节），不按节号 —— 节号会随重排变成死链。

**旧名对照**（老文档里见到这些，按右列读）：

| 旧 | 今 |
|---|---|
| `apps/` | `cli/` |
| `renderer/`（包） | `tui/`（`renderer/core.py` → `tui/renderer.py`） |
| `core/ui/` | `core/ui/vn_cli.py` → `cli/vn_cli.py`；其余三件 → `core/{display,streaming,text}.py` |
| `core/tui/` | 拆平进 `core/` 根：`display.py` / `streaming.py` / `text.py` |
| `core/common/` | 已解散：`errors`→`contract/errors.py`；`atomic`/`fuse`→`infra/`；`tone`→`core/parsing/tone.py` |
| `core/momotalk.py` | `core/mmt/engine.py` |
| `core/bond/bond_story.py` | `core/bond/bond_story/`（包） |
| `core/paths.py` | `infra/paths.py` |
| `contract/schema.py` · `contract/records.py` · `contract/digest_registry.py` | 同名包：`contract/schema/` · `contract/records/` · `contract/digest/registry.py` |
| `llm/json_cleaner.py` | `contract/json_cleaner.py` |
| `web/` | `webgui/` |
| `tests/renderer/` | `tests/tui/` |

---

## 7. 本机环境与已知缺口

环境：解释器 `C:\Users\johnf\miniconda3\envs\live2be\python.exe`（conda env `live2be`；
conda `base` 里没有 jieba，用 base 跑测试会挂）· `node` v24 在（前端测试用）。

当前基线（2026-10-18）：`tests/core` **1314 passed** · `tests/llm+tui+webgui` **240 passed** ·
`ruff check .` **362**。

已知缺口：

- `.testtmp/` 下的三份逐字节判据**未进 git**（gitignore）——换机器要重建；ADR 级别的判据
  长期只活在本地磁盘上。
- `llm/check/*.ps1` 里曾有**明文 API key 且进过 git**：文件已删，**key 需要轮换**（历史还在）。
- `README.md` / `TODO.md` / `CLAUDE_OPTIMIZE.md` / `DESIGN_BRAIN.md` 里的旧包名与旧结构尚未
  统一（产品未定稿，等定稿时一并重写）。

---

## 8. 产品决策（代码注释按「名字」引用它们）

老代码里写 `CLAUDE.md §N` 的地方指的都是下面这些规则；规则的历史与决策编号在归档件里。

- **VN 无自由打字通道**：玩家的"话"只经选项说出（老师的台词 = 选项文本）。CLI/API 保留
  任意文本通道，只作开发 / 实验用途。
- **不做真分歧**：收敛链即终局；分支内容永不进 LLM 上下文。
- **schema 与运行时校验同源**：能进 prompt 的形状描述，代码里必须有一份对应的校验。
  两边各写一份，漂移的表现是**静默取错 / 静默放过**，不是报错。
- **引擎里不许有内容语义**：节日名、地点风格、情绪词这类语义住配置或数据表，
  代码里不写 `if id == "christmas"`（加一条 = 加一行）。
- **软问题的文本必须进日志**：校验发现的问题要带**可 grep 的中文串**——只打数量的话，
  生产路径上永远 grep 不到（流式路径尤其）。
- **镜像防漂移**：prompt 里描述的形态必须与渲染器**同源**。
- **宁缺勿错**：异步 / 标注 / 存档失败一律静默降级，绝不阻断剧情推进或落库主链。
- **产品只有一个壳**：产品形态只有 `webgui/`；`cli/` 是调试入口，**不追 webgui 的行为**
  （预生成、标注 lane、插嘴、回放、群聊都不在 CLI 实现）。唯一例外：喂给模型的文案必须
  单源（`core/` 里那一份），壳里不许另写。
- **能不让 LLM 做的不让 LLM 做**：断句、情绪、地点、状态、动作名 —— 引擎能定的引擎定，
  LLM 只保留创作裁决。
