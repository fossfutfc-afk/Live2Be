# ARCH_REVIEW — 组织形式与可扩展性问题（2026-09-20）

> **状态**：评审稿。
> **2026-09-21 更新**：**P0-2（退役只删调用点、不删能力）已解决**——v1 动作契约整族
> （`bond_actions`/`bond_executor`/`memorial_actions`/`sentence_splitter`/`stream_probe`
> + `BondScene.from_action` + webgui 的 8 处 `memorial_exit` 恒假分支）与旧版记忆三件套
> 已删除; 其余逐条处置（A/B 打 `# EXT:` 保留、C/D/E 删除）见 `docs/EXTENSION_POINTS.md`。
> **P0-3（严重度靠中文串判）也已解决**（节点 6, 见该条的状态行）。
> 单流水线收敛（P0-1 的根治方向 c′）进度见 `docs/EXEC_PIPELINE_UNIFY.md`。
> **来源**：2026-09-20 那次纪念链路改动（docs/DESIGN_MEMORIAL.md 节点 A–D）
> 亲历的摩擦——每一条都有这次的具体证据，不是泛泛而谈。
> **怎么用**：新开一个对话解决时，把本文丢给它；下面的"方向"是**候选**，不是结论。

---

## 一、组织形式（现状，一句话版）

```
浏览器  webgui/static/js/{bond,mmt,gui}.js
  ↕ REST + 轮询（无 SSE）
webgui/    FastAPI 壳 + 会话状态机（bond.py BondState / chat.py worker / routers/）
core/      引擎（无 web 依赖）: momotalk · bond(引擎+标注) · session(事件流) ·
           brain/wiki_v2(记忆) · promptkit(装配) · media/director(视觉) ·
           parsing · mmt · ui · affection · rag · worldtime · common
contract/  契约地基: records(记录文法+块校验) · schema(LLM 可见文本) · registry/spec/model
llm/       客户端 + 档位真源 + image_gen + prompts/文案仓库（人可改）
config/    人设(六文件 + illustration.yml) · 世界观 · 人际
data/      真源 events.jsonl + wiki（都在 characters/*/soul/ 下）
tests/     分域（core/webgui/llm/renderer）+ experiments/ 真 API 探针
```

**数据流**：LLM 创作 → `contract` 解析/校验 → 引擎（板派生 / 两遍式标注 / 导演视觉）
→ **事件流（唯一真源）** → 派生（回放 / 回忆册 / digest 记忆 / 提示词注入）→ 前端渲染。

**四条立得住的骨架**（先说好的，改的时候别拆掉）：

1. **事实主线稳**：append-only + 一切派生。这次四轮改动全靠"从事件流重放"验证，
   没有一次需要改历史数据。
2. **判定/创作分离**：加"纪念从哪开始"这种语义不需要动 prompt。
3. **埋点纪律**：`bond_board_deliver src=… board=N recs=N call=…` 每板一行——
   这次能一眼说清"这一板从哪来、0 LLM 还是真调用"。
4. **两层 e2e**（A 层 HTTP + B 层真浏览器）：抓到了我两次"断言放晚了"的错误
   （见 §3.3 第 3 条）。

---

## 二、结构性问题（按"这次的实际代价"排序）

### P0-1 一个语义散落在五层，靠注释对齐

**证据**：加 `memorial_at`（"黑屏从哪一段开始"）要同时改

| 层 | 改什么 |
|---|---|
| `core/bond/bond_story.py` | `BondScene` 字段 + `from_board` 算下标 + `to_dict`/`from_dict` 往返 |
| `webgui/static/js/bond.js` | `memorialSt` 缓存 + `memorialNow()` 判定 + 每段上屏调用 |
| `webgui/bond.py` | `_memorial_no_visuals` 的段级判据 |
| `core/session/chapters.py` | （这次**免改**——因为字段随 `to_dict` 进了 payload，回放自动拿到） |
| `webgui/routers/bond.py` | （免改，`_resolve_scene` 原样透传） |

更早的例子是 `in_memorial`：引擎布尔、webgui marker 记账、前端 `syncMemorial`、
`chapters` 板级派生——**四处四种粒度**。

**根因**：板载荷（scene payload）是**隐式契约**。字段全靠 `.get()` 约定，
没有字段表、没有消费者清单、没有"谁写谁读"的记录。

**方向**：`contract/board.py` 声明板载荷字段表（名/类型/默认/谁写/谁读），
由它生成前端的字段名常量，并加一条测试：「payload 里出现的键都在表里，表里的键都有读点」。
投入小、回报直接。

### P0-2 退役只删调用点，不删能力 ⇒ 地里埋着看起来能用的死路

**证据**（这次全部撞到）：

- `scene.memorial_exit` 在 v2 **恒为 False**，但 webgui 里还有 **6+ 处活分支**读它
  （标注门控 / lane / marker 落库），`_log_scene_meta` 的 `elif scene.memorial_exit:`
  永远走不到；
- `STAGE_EXIT` 是解析层常量、**却一直出现在注入给 LLM 的取值清单里**（我这次才摘掉）；
- `core/bond/memorial_actions.py` / `stream_probe.py`：v1 的 registry 与探针仍在；
- `core/bond/bond_story.py:955` 那条"声明了 art 但本回合没有 memorial"的 WARNING
  **只覆盖批式路径**（流式根本不走那个函数）⇒ 生产主链上是死的（我这次才发现）。

**代价**：为了确认"纪念到底有没有 exit"，我读了 6 个文件；你也在它上面绕了两轮。

**方向**：**退役 = 三处同时摘**（① 注入面 ② registry/契约 ③ 消费面），
并加测试：「注入文本里不得出现解析层遗留常量」「恒假字段没有活分支（否则删字段）」。

### P0-3 契约的"严重度"语义放错了层

> **已解决（2026-09-21, `docs/EXEC_PIPELINE_UNIFY.md` 节点 6）**：`contract/records.py`
> 现在返回结构化 `Issue(code, message)`，严重度 = `ISSUE_SEVERITY[code]` 的显式声明；
> `split_issues` 只读 `Issue.severity`，`HARD_BLOCK_ISSUE_MARKS` 已删。守门用例
> `tests/core/test_records.py::test_issue_severity_is_declared_by_code_not_message`
> 钉住三件事：文案塞满硬关键词也不改分级 / 每个 `IssueCode` 必须声明严重度 /
> 源码里不许复活子串分级。

**证据**：`check_block` 在 `contract/records.py` 产出**中文问题串**，而"硬/软"
由 `core/bond/bond_story.py::split_board_issues` 按**字符串匹配**
（`HARD_BLOCK_ISSUE_MARKS`）判。两个后果：

- `VnBlock.is_valid` 在 contract 里只能表示"无任何问题"，语义不完整
  （软问题也会让它 False）；
- **加一个问题串若撞了硬标记串，会静默变成"整轮重发"** —— 这次我加两条软问题时
  只能靠人肉避开 "条 memorial" / "条 art" 这类子串。

**方向**：改成结构化 `Issue(code, severity)`，严重度跟问题一起定义
（顺手解掉"判定靠中文串"的脆弱性）。同一条也适用于测试断言。

### P1-4 `webgui/bond.py`（2852 行）是全局耦合点

一个文件里同时装着：`BondState` 定义、落库（`_log_scene`/`_log_scene_meta`）、
marker 记账、B0 暂存、标注 lane、双路门控、预热/草稿、回放、纪念态、收尾链、
wrapup、settings 读取。

**代价**：改纪念要动 4 个相隔很远的段落；文档里的行号引用**立刻失效**
（CLAUDE.md 原来引的 `webgui/bond.py:2611` 这次就漂了）。

**方向**：按职责切（landing / logging+markers / lanes / memorial / replay / finish），
`bond.py` 只留状态与门面。

### P1-5 "块/板/记录"三层没有类型隔离，命名也不统一

**证据**：真机实测 **一块 = 整章**（5 板同属一块），而规则书里的"段"= 一次回复 = 一块。
文档里"段/轮/块/板"混用 —— 这次为对齐这个词花了整整两轮对话。

**方向**：代码里用不可混用的命名/类型（`block_id` / `board_seq` / `record_idx`）；
文档术语表强制；**对 LLM 说话的文案统一成"这一轮（= 你这次回复）"**。

### P1-6 B0 章内暂存 ⇒ "读路径必须读 overlay"是隐性纪律

**证据**：这次踩了两次（`_persisted_memorial_img` 只读真源 → 纪念"没见过"；
`replay_attempts` 只读真源 → 章进行中重进看不到内容）。

**方向**：把"章内读"收敛成**一个入口**（如 `soul_view(char, session)` 返回 overlay），
禁止业务代码直接 `store.events(...)`——做法可以照搬 `core/paths.py` 那次
（单点定义 + 一条测试扫消费面）。

### P1-7 文档 ⨯ 代码没有防漂机制

**证据**：这一轮抓到三处——`CLAUDE.md` §3.2（v1 动作描述）、
`core/session/chapters.py:112` 的表格句（"触发板 = marker 之前最后一条 bond 事件"，
实现早就改过）、以及"契约示例里 memorial 是光杆的"这条**语义漂移**。

**方向**：把文档里**可机器验证**的事实变成断言（注入面清单 / 字段表 / marker 清单 /
三层术语在代码中的命名），其余在文首标"最后核对日期"。另：CLAUDE.md 已 506 行、
13 节，建议拆成"给 AI 的一页纸"（照 `docs/AI_BRIEF_PLACE.md` 的样子）+ 各域设计稿。

### P2-8 测试桩按自然语言关键字应答

`ScriptedLLM` 按 user 尾部关键字（"user 含 `情绪标签`"、"恰 N 项"…）分派。
**改文案会静默让桩不命中**（CLAUDE.md 自己记着这个坑），加一条标注任务要同步 5 个文件。

**方向**：桩改按**结构化标记**分派——引擎已经在 messages 里放了 task 卡，
加一个机器可读的 header（task kind / 契约域）即可。

### P2-9 提示词质量没有回归手段（只能快照）

夹具守的是"文本没变"，守不住"模型有没有照做"。这次的 **art 命中率 0/5**
就是"文案写了但没人量"的典型（已补 `prompt_source` 埋点）。

**方向**：再加一行**每章摘要日志**（板数 / 有无 art / 纪念数 / 重试次数 / 时长），
让质量趋势可见；必要时做 A/B 探针（`experiments/` 已有先例）。

### P2-10 `data/` 与 `config/` 的边界重叠（次要，影响上手）

角色目录下同时有 `meta.json`/`progress.json`（运行时）与 `soul/`（记忆层），
而作者面在 `config/characters/<id>/`。这次为找 gallery 我先 glob 了一遍才定位。
影响的是"新人/AI 第一次找东西"的成本，不急。

---

## 三、这次顺手记下的三条"操作纪律"（不属于架构，但值得保留）

1. **改文案必须同批改"示例"**——契约示例才是形状的来源
   （取值清单/硬规则/规则书写得再清楚，示例是光杆的，模型就学光杆）。
2. **要断言"某一段上屏那一刻"的状态，必须逐段取样**——"板读完再查"已经晚了
   （我第一版冒烟就是这么错的，被 B 层 e2e 抓到）。
3. **软/硬问题靠中文子串判** ⇒ 加问题串前先 grep `HARD_BLOCK_ISSUE_MARKS`。

---

## 四、如果要排优先级

| 优先级 | 做什么 | 为什么先做 |
|---|---|---|
| **P0** | 板载荷字段表（P0-1）+ 契约严重度结构化（P0-3） | 这两条是"改一处要动五处""笔误变整轮重发"的**根因** |
| **P0** | 退役纪律 + 死分支清理（P0-2） | 直接降低**误读成本**——这次为此多花了至少两轮 |
| **P1** | 拆 `webgui/bond.py`（P1-4）+ overlay 单一读入口（P1-5/6） | 改动半径最大、最容易出静默 bug |
| **P1** | 文档防漂 + 术语/命名统一（P1-7、P1-5） | 影响的是**每一次**协作的起步成本 |
| **P2** | 桩结构化（P2-8）+ 质量趋势日志（P2-9） | 提升的是长期迭代速度，不阻塞当前功能 |
