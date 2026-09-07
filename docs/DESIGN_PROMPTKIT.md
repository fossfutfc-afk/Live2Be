# DESIGN_PROMPTKIT — 提示词组装层 + 本回合任务卡 + 选项回录（定稿）

> **状态**：设计定稿 2026-09-07（用户拍板三项：① 先定稿再开 Phase 0；
> ② task 卡默认开、settings 可关；③ 方案A 选项回录并入本批）。
> **前置事实**：docs/PROMPT_INJECTION_MAP.md（现网注入地图——本设计的唯一事实基线；
> 旧 DESIGN_WEBGUI_PROMPTS.md 已归档）。窗口语义：docs/DESIGN_CONTEXT_WINDOW.md。
> **本批不碰**：reasoning knob（用户裁决项）、SSE、choice 场全量预生成（InfiPlot 式）、
> digest/标注 prompt 内容、好感可视化。

---

## 1. 要治的病（地图 §7 实证）

| # | 病 | 现网证据 |
|---|---|---|
| 1 | 无任务层 | 所有域只有长期规则书；每轮/每场无"本回合目标"（引擎 `agent_turn`/`send_vn_scene` 无卡片概念） |
| 2 | 装配散装两份拷贝 | 盒A（momotalk.py:303-348）与盒B（bond_story.py:290-346）各自手拼 world/tone/greeting/rules/schema；顺序只活在代码里 |
| 3 | 注记层错位 | Bond P17 聚合器是 **webgui 层**概念（webgui/bond.py:1138）；vn_cli 自己又抄了一份同款注记（vn_cli.py:206-242）——同类提醒只会越加越多、各层分叉 |
| 4 | live 与回放行为分叉 | 引擎 live 历史生成时落库 → **永远看不到 picked**；resume/replay 走事件流（payload 带 picked）→ 看得到（renderer.py:98-100）——同一剧情 AI 知道的不同 |
| 5 | 防漂移无工具 | 地图文档今天校准明天漂，行号已证明 |

目标形态：装配有**声明式清单**、每回合有**任务卡**、live=回放**同一条叙事化函数**、
实际注入可被 **report 工具复述**。

## 2. 装配协议（红线，本批任何改动不得破坏）

```
【会话级】system = 盒[域]（一次拼死, 逐字节稳定）
【每轮】  messages = [system] + history + [约束注记们…] + [Task 卡] + [user]
【异步】  标注 / digest / 收尾轮 = 独立 prompt 体系（本批不动内容）
```

1. **前缀稳定**：system + history 逐字节不变（DeepSeek 上下文缓存基本盘）；
   一切动态只发生在 history 之后。
2. **卡最近位**：Task 卡 = history 之后、所有约束注记之后、user 之前
   （momotalk.py:616 前 / `_system_note` 同槽）——离生成最近最醒目（两处既有注释
   已表达此意图）。
3. **卡不抄规则**：卡片只点目标，不复制规则书/schema/注记内容（那些已在 system 内）；
   预算 ≤ 100 token。
4. **一处装配**：CLI / vn_cli / webgui / 预生成 / bench 走同一装配代码。
5. **一函数叙事**：live 历史、事件渲染、回放视图、收尾预灌，同一个叙事化函数。

## 3. 架构：core/promptkit/（引擎层模块）

```
core/promptkit/
├── __init__.py      # 导出: build_box / round_messages / task_card / describe
├── config.py        # task_card_enabled(): 读 settings.toml [promptkit].task_card
│                    #   （默认 True; 引擎构造参数 task_card: bool|None 覆盖——测试注入用）
├── blocks.py        # 命名块注册表: Block(id, source, section, role) 
│                    #   块 = 有稳定身份的注入段（character/world/tone_mmt/tone_bond/
│                    #   interperson/environment/rules_mmt/rules_bond/schema_mmt/
│                    #   schema_story/lexicon_emotion/lexicon_place/brain/…）
├── box.py           # build_box(域) → str: 盒A/盒B = 两份声明式块清单, 取代手拼
├── tail.py          # round_messages(box, history, notes, task, user) → messages
│                    #   唯一每轮装配入口（brain 段并入 box 尾部刷新——语义同现网）
├── task.py          # task_card(域, kind, *, char=…) → str|None
│                    #   模板 = llm/prompts/task_*.md（人可改, {char} 占位 replace）
└── report.py        # describe(域) → md: 从 box/task 清单渲染"实际注入报表"
                     #   （与 PROMPT_INJECTION_MAP §1/§2 同构——文档代码化的落点）
```

引擎改造形态（语义等价优先）：
- `MomoTalkEngine.agent_turn(user_input, *, task_kind="chat", ...)`：
  system = box("mmt") + brain 段 → history → 注记（现有 P16/P17/P18 顺序不动）
  → `task_card("mmt", task_kind)` → user。
- `BondStoryEngine.send_vn_scene(user_input, *, task_kind=None, ...)`：
  task_kind 默认由引擎自推——`in_memorial` → `memorial_exit`，否则 `scene`；
  调用方（收尾轮等）可显式传。
- 收尾轮（wrapup / vn_cli 收尾）传 `task_kind="wrapup"`。

## 4. Task 卡文案终稿（模板文件 = llm/prompts/task_*.md）

职责切分：**卡 = 目标层**（这回合达成什么）；现网 P17/系统注记 = **约束层**
（配额/提醒/边界）——两者互补不重叠，卡内不重复约束内容。

| 文件 | kind | 文案（定稿草案） | 触发 |
|---|---|---|---|
| task_mmt.md | chat | `本回合任务：以{char}身份回应老师刚发来的消息。若此刻已形成共处契机或老师正需要你出面——直接发起 mmt_trigger_bond_story（独占轮，规则见前）；否则按 MomoTalk 规则正常消息流聊天，不要无端转剧情。` | MMT 每轮（引擎默认） |
| task_mmt.md | wrapup | `本回合任务：以{char}身份就刚结束的羁绊剧情给老师回几条手机消息收尾（具体话术见系统注记）——只许 mmt_chat，不要再次触发剧情。` | 收尾轮（调用方显式传）|
| task_bond.md | scene | `本场任务：作为{char}推进当前板块——输出 story_scene 骨架：正文自然段 + 一组 2~3 选项 + 键一致的 branches；若剧情已到约定达成/道别/夜色收场的自然段落 → 直接输出 story_end 收尾。` | Bond 每场（引擎默认；含预生成"（继续）"场）|
| task_bond.md | memorial_exit | `本场任务：纪念时刻已落幕——输出 memorial_exit 回到 bond（可带一句过渡文字）。` | 纪念模式中每场（引擎自推）|

- 卡只在 `task_card_enabled()` 为真时注入；模板缺失 → 不注入（宁缺勿错）。
- 收尾强制（_END_ROUNDS 之类）仍是约束注记职责，不进卡（不重复）。

## 5. 方案A：选项回录（live 与回放对齐 + 分支叙事化）

### 5.1 现状三岔（地图 §4 实证）

| 路径 | picked | 选中分支内容 | 实现 |
|---|---|---|---|
| 引擎 live 历史（生成时落） | ❌ 永远没有 | ❌ | bond_story.py:503-507 `render_bond_scene_text(payload)`（payload 无 picked）|
| resume / wrapup 预灌（事件流） | ✅ | ❌（设计决定"branches 不写记忆，只记 picked"，renderer.py:60, 98-100）| render_events → window_messages |
| 回放视图（webgui 渲染） | ✅ | ✅（自实现合并）| webgui/bond.py:353 `_narrativize`（**与 renderer 重复的实现**）|

→ 同一场戏，AI live 续写不知道选择、恢复知道选择但不知道分支、回放视图两者都知道。
**续写靠猜 = live 路径缺 picked**；分支内容缺失是 2026-09-05 的有意决定，但它直接导致
"（继续）"续写不记得分支里刚说过/做过什么——本批**推翻该决定**（见 5.4 决策）。

### 5.2 目标形态：一函数 + 一 API

1. **叙事化唯一化**：`render_bond_scene_text(payload, *, include_branch=False)` 增加
   `include_branch`——payload 有 picked 且 branches[picked] 存在时，选中分支段落
   以续行并入叙事文本（行首无标注即可，与正文同格；未选分支永不进上下文不变）。
   webgui `_narrativize`（bond.py:353-384）删除，回放渲染改走本函数（include_branch=True），
   消除重复实现——**回放视图与 LLM 上下文从此一致**。
2. **引擎回录 API**：`BondStoryEngine` 记录最近一次动作 payload（`self._last_payload`），
   新方法 `record_picked(picked: str)`：把 `_history` 尾部该场 assistant 条目重渲为
   `render_bond_scene_text(payload, include_branch=True)` 并把 picked 写进 payload
   副本 → live 历史 = 事件流将来重放的样子（append-only 事件流不动——picked 已由
   `_log_scene` 落库，无新事件）。
3. **接线点**（裁决即回录，随后任何 LLM 调用都看到）：
   - webgui：分支消费（bond.py:748 `_log_scene(picked=text)` 后、:765 `_pregenerate`
     前）调 `state.vn.record_picked(text)`——预生成/正常续写都发生在裁决之后，顺序天然正确。
   - 自由输入轮：玩家原文即下轮 user，无需回录（现网已等价）。
   - vn_cli：裁决点同款接线（实施时核对 CLI 消费循环的裁决分支）。
   - 演示模式（demo）无引擎，跳过。
4. **边界**：choice 场本体不做裁决前预生成（InfiPlot 式全预生成仍为邻接项）——
   回录只保证"裁决之后发起的生成看到选择与分支"。

### 5.3 文档联动

- docs/DESIGN_CONTEXT_WINDOW.md："branches 不写记忆（只记 picked）"一条作废 →
  新语义：**picked 必记（live/恢复同源）+ 选中分支叙事化进上下文**；未选分支仍永不入。
- digest 输入若经叙事化文本（wiki_v2/digest.py 摘取源实施时核对）将同步获得分支
  叙事——无新增代码，只观察 token 涨幅。

### 5.4 待拍板（两选项，二选一）

- **A2（推荐）**：picked + 选中分支都进上下文（5.2 全量）。续写真正不猜；代价：
  每场上下文 +1 段分支文本（数十字~百余字），前缀稳定不变。
- **A1（保守）**：只回录 picked（不改 renderer include_branch，不删 _narrativize）。
  续写知道选择、仍不知道分支说了什么——猜的洞补一半。改动最小。

## 6. 配置

```toml
# settings.toml（运行时, gitignore）
[promptkit]
task_card = true      # 本回合任务卡开关（默认 true; false = 现网行为逐字节不变）
```

- 读取：`core/promptkit/config.py::task_card_enabled()`（settings.toml 缺失/损坏 → True）；
  引擎构造参数 `task_card: bool | None`（None=读配置）——测试与 bench 可固定。
- webgui 设置页白名单（webgui/store.py:77 只存已知分组）后续按需加 [promptkit] 字段，
  本批不做 UI。

## 7. 迁移步骤与验收

### Phase 0 — 基线脚手架（零行为改动）
- 写探针测试：构造真实引擎捕获 `_system_prompt` 全文与一次典型轮 messages
  （MMT 轮 / Bond 场各一）→ 存为**黄金夹具**（断言按结构段列表比对，不锁全文——换行
  敏感）。夹具即本批"语义等价"的裁判。
- 产出：`tests/core/test_promptkit_baseline.py`。

### Phase 1 — promptkit 骨架 + MMT 装配抽盒（语义等价重构）
- 建 core/promptkit/（config/blocks/box/tail/task/report）+ task 模板 md（先空置不注）。
- momotalk `start_session`/`agent_turn` 换 `build_box("mmt")` + `round_messages`；
  顺序与文案逐字节不变（report.describe("mmt") 输出 == 黄金夹具段表）。
- 验收：全量测试绿；describe 报表与 PROMPT_INJECTION_MAP §1/§2 段结构一致。

### Phase 2 — Task 卡启用（MMT）
- task.py + task_mmt.md（chat/wrapup 两 kind）；`agent_turn(task_kind=...)`；
  引擎默认 chat；webgui wrapup（bond.py:1240）与 vn_cli 收尾传 wrapup。
- settings [promptkit].task_card 接线（默认 true; false 时夹具路径逐字节复现现网）。
- 顺手：llm client usage 日志加 `prompt_cache_hit_tokens`（DeepSeek 缓存命中字段）
  → 完成 EXEC_BOND_LATENCY P2 #4（前缀缓存验证）的数据面。
- 验收：卡出现在 user 前最后一位；开/关两态测试；wrapup 轮卡在 P16 注记之后。

### Phase 3 — Bond 盒装配抽盒 + 场卡
- bond_story `start_session`/`send_vn_scene` 换盒/尾；scene/memorial_exit 两 kind 卡
  （send_vn_scene 引擎自推默认 kind）；CLI/vn_cli/webgui/预生成同源。
- 验收：describe("bond") == 地图 §3 段结构；纪念模式轮 = memorial_exit 卡且无 scene 卡。

### Phase 4 — 方案A（选项回录；按 5.4 拍板结果）
- A2：renderer include_branch + 删 webgui _narrativize + record_picked + 接线
  （webgui 分支消费点 / vn_cli）；A1：仅 record_picked（picked 行）。
- 验收：分支消费后 `（继续）` 生成请求的历史尾部含选择与（A2）分支叙事；resume/
  wrapup 预灌与 live 逐字节同形；replay 视图与 LLM 上下文一致（_narrativize 删除后
  无行为差异——有对比测试）。

## 8. 测试计划（新增/改动摘要）

| 测试 | 要点 |
|---|---|
| test_promptkit_baseline | Phase 0 黄金夹具（段表对比） |
| test_boxes | build_box("mmt"/"bond") 段顺序 == 地图顺序；条件块（无 mmt_tone/词表/brain）缺省降级 |
| test_round_messages | 前缀逐字节稳定（同盒两轮 system 相等）；卡=最后一位；notes 顺序 |
| test_task_cards | 各 kind 文案/占位；模板缺失 → 不注入；开关 false → 无卡且全文=现网夹具 |
| test_record_picked | record_picked 重渲尾部；picked 未消费不破坏历史；连续两场正确性 |
| test_narrativize_unified | render include_branch=True == 旧 _narrativize 输出（删除前先对拍） |
| 回归 | 现有全量（尤其 test_context_window / test_bond* / webgui turn/分支/回放用例） |

## 9. 邻接与明确不做

- choice 场裁决前全预生成（InfiPlot 式）——独立立项（收敛链安全后另议）。
- `_system_note` webgui 聚合器**本批保留原位**（约束注记层），"注记体系引擎化"
  （vn_cli 同款合并）降级为后续可选优化——卡片层先行，避免本批动约束层文案。
- reasoning knob / SSE / 好感可视化 / digest 内容——不动。
