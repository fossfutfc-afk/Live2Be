# CLAUDE.md — Live2Be 项目主文档（2026-09-07 大重构版）

> 灵感：Blue Archive 式角色互动叙事引擎。玩家经 **MomoTalk**（类微信聊天）与
> 角色互动，氛围到位时由 LLM 主动触发 **羁绊剧情**（视觉小说），关键瞬间进入
> **纪念模式** 生成立绘。LLM 负责"演"，引擎负责"判"——本文把两者边界讲清楚。
>
> 本版重构动机：旧版停留在历史结构（Sleep 式记忆规划、`core/bond_story.py`、
> `web/`），且对事件流/两遍式/提示词装配等关键机制零覆盖。**以本文为准**；
> 冲突时代码为最终事实，设计意图见文末文档路由表。

---

## 0. 三条主线（读项目先读这里）

1. **创作主线**：主 LLM 每轮只产出"创作"（MMT 消息流 / Bond 自然段文本），
   结构与判定全在引擎——见 §3 契约与 §4 判定层。
2. **事实主线**：`events.jsonl` **append-only 唯一真源**——对话/场景/裁决/标记
   全部落事件流；恢复、回放、记忆消化都从它派生，任何状态都能重建。见 §5。
3. **体感主线**：一切等待优化都围绕"生成发生在玩家阅读时"（预热/预生成/双路
   标注并行/门控），prompt 前缀稳定以吃上下文缓存。见 §9。

**核心哲学（贯穿全项目）**
- **内容与判定分离**：文本承载创作；情绪/地点等"判定"由廉价标注层做（两遍式 C，
  2026-08-31 教训：让主 LLM 逐句内联情绪 → 注意力分散、重试爆炸）。
- **能不让 LLM 做的不让 LLM 做**：断句、情绪、地点、事件/状态、动作名语境隐含……
  引擎能定的引擎定；LLM 只保留创作裁决（正文、选项、收尾时刻、纪念时刻）。
- **宁缺勿错**：所有异步/标注/存档失败静默降级，绝不阻断剧情推进或落库主链。
- **稳定前缀**：system + history 前缀逐字节稳定 → DeepSeek 上下文缓存命中
  （日志 `cache_hit=` 可观测）。

---

## 1. 术语表（文档与代码共用语）

| 词 | 含义 |
|---|---|
| 域（domain） | 契约命名空间：mmt / story / memorial / digest / ide……动作注册表（contract/）按域隔离 |
| 盒（box） | 会话级 system prompt 的装配单元（promptkit `DOMAIN_BOXES`）：盒A=MMT、盒B=Bond；一次拼死、逐字节稳定 |
| 板（board） | Bond 一次 LLM 回合产出的一"板块"（记录流 v2: 一次调用 = 一块 → 派生多板）——玩家**点画面/选选项**推进一次, = 标注/提交/回放单位 |
| 记录（record） | **v2 的显示/判定最小单元**: 一行 JSON = 一个 `paragraphs` 项（角色 id / narrator / sensei / switch / art / memorial / end / exit）; 引擎**不切句** |
| 段（text/自然段） | **v1 遗留词**（主 LLM 写段 → parse 切句）; v2 已被"记录"取代, 文档/代码里的"段"凡指标注单元一律读作"板/记录" |
| 句（sentence） | **v1 遗留词**: 曾为显示/判定最小单元（打字机/emotion/place 挂在句上）; v2 = 记录级, 一条记录可能含多句但只给一个键 |
| 事件（event）/ 标记（marker） | events.jsonl 两类行：普通事件（type/subtype/payload）与状态标记（vn_enter 等）；marker 驱动 session_status 推导 |
| 两遍式 C | 主 LLM 写骨架 → 标注层异步回填视觉键（emotion 按板全覆盖、一条记录一个键；place 事件型锚点） |
| task 卡 | 每回合"目标层"注记（见 §8），= 对"AI 只有规则书没有任务"的修复 |
| 回录（record_picked） | 裁决后把"（选择了: X）"写回引擎历史尾部，live 与 resume 同形（A1） |
| 玩家话语（**只体现为选项**） | 选项居中显示; 选项时刻正文停在上一句角色台词/旁白, 名字牌不动; **裁决后选项组留在屏上转只读态**（压暗 + 高亮所选; live 侧禁用, 只读回放侧可点=只推进）——玩家那句永不当正文上屏（决策 #37/#41）; 事件 payload 的 `picked` 与引擎历史的 `老师：X` 物化照旧（AI/回放锚点） |
| 推进（**点画面**） | **没有"▼ 继续"按钮**（决策 #41 删除）: 点画面/点右下 ▾ 三角 = 板内下一段 → 板读完进下一板 → `is_end` 收尾; 板上有**未裁决**选项时点画面不推进（等玩家点选项）; 三角带 `.ready` = "整板读完"（自动化据它判定） |
| 回忆册 / 角色页 / 章节条目 | **P0 已落地**（docs/DESIGN_COLLECTION_BOOK.md）: 书页 UI（两半页 × 3行4列, **一格 = 一角色**, `collection.png` 封面, 空格留白）→ 点格子进**角色页**（该角色**已结束**章节的标题列表）→ **章节条目**旁的按钮进回放 |
| 只读回放 | 回忆册里的回放（`BondVN.enterReadonly`）: 播完即停、**0 LLM**、不碰 `BondState`/不写事件流——与现网"中断重进 → 回放前缀 → LLM 续写"的 resume 型 replay 是两件事 |

---

## 2. 全局架构分层

```
浏览器 (webgui/static/js: bond.js / mmt.js / gui.js)
   │  REST + 轮询（无 SSE——未立项）
webgui/        FastAPI 壳 + 会话状态机（bond.py BondState / chat.py 输入队列 worker）
   ├ routers/  路由层: 请求→驱动层; _resolve_scene 给场景附前端渲染信息(bg/fx/place_bg)
   └ store.py  运行时配置读写(settings.toml)
core/          引擎层（无 web 依赖, CLI/实验同源复用）
   ├ momotalk.py             MMT 引擎（消息流动作循环）
   ├ bond/bond_story.py      Bond 引擎（双 registry + 状态机 + 骨架 + 历史）
   ├ bond/*_annotate.py      标注层两路: emotion(按板一组, 一条记录一个键) / place(换场锚点)
   ├ session/                事件流: store(events.jsonl)/renderer(叙事化)/maintenance(废弃段)
   ├ brain/wiki_v2/          digest 记忆（RoundA/B 提炼 + 好感结算 + 注入视图）
   ├ promptkit/              提示词装配: box/tail/task/report（见 §8）
   ├ parsing/ director/ media/ mmt/ ui/ random_events/ affection/ rag/
contract/       契约地基: ActionSpec/Registry/parse/schema（LLM 可见 schema 与运行时校验同源）
llm/            client(超时/流式/usage 日志) · task_levels(档位真源) · prompts/文案仓库
config/         人设六文件(REQ~/SIG~) · settings/world(overview.yml) · settings/relation
data/           运行时数据(gitignore): worlds/*/characters/*/{events.jsonl,soul/,progress.json…}
tests/ core/ webgui/ llm/ 分别对应域; experiments/ 真 API 基准与探索脚本
```

注：`core/bond_story.py`/`web/` 是历史名，**不存在**；现为 `core/bond/bond_story.py`
与 `webgui/`。`core/brain/{consolidation,hippocampus,recall}.py` = 旧版记忆
（digest v1）**仅实验/参考用**；运行主链 = `core/brain/wiki_v2/`。根级
`DESIGN_BRAIN.md` 为记忆体系总设计（历史+现网混合，读前看文首状态）。

---

## 3. 契约与 LLM 调用点总表（各注入什么、输出什么、谁判）

### 3.1 MMT（MomoTalkEngine, `agent_turn`）
- **每轮输出**：单个 JSON 消息流 `{"messages":[{"text":…},{"action","payload"}]}`
  （2026-09-02 协议；text 单元=说话隐含 mmt_chat；action 单元=引擎介入操作）。
- **可用动作**：`mmt_chat`(隐含) / `mmt_send_media` / `mmt_inspect_character`
  （静默推理轮, 按 interperson 权重访问他人人设）/ `mmt_trigger_bond_story`
  （**唯一模式切换动作**, 独占轮, 必须带 chapter_title 3-16 字）。
- **messages 槽位**（`promptkit.round_messages` 唯一入口）：
  `[system=盒A(+brain 记忆段尾拼)] + history + [P16 羁绊进度注记] + [P17 系统注记?]
   + [P18 随机 want_to_speak?] + [task 卡 chat/wrapup] + [user 原文]`
- 引擎判定：消息流解析/独占约束/全量 parse 原子回灌/事件落库（每动作一条）。

### 3.2 Bond（BondStoryEngine, `send_vn_scene`）
- **每场输出**：单动作 JSON `story_scene`（正文段数组+一组选项+branches）或
  `story_end`（收尾, 无选项）或纪念域 `memorial_enter`（prompt+煽情段, 独占轮）/
  `memorial_exit`（回 bond）。**收尾/纪念是创作裁决 → 显式动作；engine 校验频率与独占。**
- **messages 槽位**：`[system=盒B] + engine._history + [P17 约束注记?] + [场 task 卡
  scene|memorial_exit] + [user]`。
- 引擎判定：切句/骨架化/情绪与地点标注（两遍式）/导演视觉（place→背景）/
  选项配额(≤3)/收尾提醒/失败重试(feedback ≤3)→closing。
- **选项目前语义**（详见 §6）：每板 1 组 2~3 候选项 + 键一致的 branches（选中即显,
  零 LLM）；选项收敛同主线（"假选择/收敛链"）；A1 回录后 AI 只见选择行不见分支文本。

### 3.3 标注两路与异步调用（不进玩家等待主链或并行进行）
| 调用 | 时机 | 输出 | 档位(task_levels) |
|---|---|---|---|
| emotion 标注 | 每板交付后（webgui 异步 lane / CLI 同步） | 词表键数组（长度 = 板内**记录数**, 一条记录一个键; 主角+旁白, NPC 不送） | emotion: off / 512 |
| place 标注 | 同上, **与 emotion 双路并行** | 换场锚点 `[{sentence, place}]`（稀疏；keep=空） | place: off / 256 |
| digest | bond 完整闭环后 / MMT 每 25 轮（剧情中不触发） | wiki RoundA/B 增量 + 好感 delta | digest: high / 8192 |
| wrapup 收尾轮 | finish 后 agent_turn（mmt 域, task_kind=wrapup） | 手机消息收尾话 | mmt（default） |
| 生图 | 板上出现 `stage:memorial` 时（v2: prompt = 块级 `art` 画面意向 → 缺省触发句; 只在真出现纪念时开画） | 图片（**非 LLM** 主链外；总开关见 §10） | — |

档位真源 = `llm/task_levels.py`（main=跟随 settings `[llm].reasoning_effort`, 用户裁决项）。

---

## 4. 视觉与判定层（两遍式 C 全貌——本项目最独特的机制）

**切句权移交（2026-09-02 定稿；v2 已被记录流取代）**：v1 主 LLM 只写"自然段"、
契约 parse 层 `split_paragraph` 切句；**记录流 v2 起一行 = 一条记录 = 一个显示/
判定单元, 引擎不再切句**（docs/DESIGN_VN_UPGRADE.md §6）。

**emotion（按板一次, 一条记录一个键 —— 2026-09-11 口径修正）**
- 标注层 prompt：`emotion_text_annotate.md`（词表键+示范+人设摘要防"逞强笑"误判）
  + 原语 `core/bond/emo_text.py:annotate_items` + engine
  `fill_scene_emotions_text`（取代整场批标 `emotion_annotate.md`，后者仅存于
  单测/存档路径）。
- **单元 = 记录, 分组 = 一板一组一次调用**（真机板 3~12 条; `scene.segments` 在 v2
  恒为 None——`_seg_ends` 只由旧动作契约 parse 产生）。**一条记录一个键**：记录内
  多句也只占一行（模板显式写明"行数是记录条数, 不是句子数"——旧模板自称"每行
  一句", 会诱使模型按句拆项 → 长度不符 → 整板兜底）。
- **只有主角记录 + 旁白进标注**：其他角色（客串/NPC）台词不送——无差分可切
  （只有 default 一张）, 由引擎确定性继承"上一条已生效键"（立绘不变, 零 LLM
  决策）; 判据 `contract.is_main_speaker` 与别名归一**同源**。注意批式 parse 会把
  **未知说话人归一到主角**（决策 #21 单人模式兜底）, 流式路径保留原值。
- 情境块 = 上一板记录原文 + 末条情绪 carry / 首板 = 本章 seed 锚（禁后文）;
  示范键由 engine 按实际词表挑; 条数显式双写; 长度不符重试一次带"期望 N 实得 M"。
- 输出 = 与**记录条数**等长的词表键数组；逐项容错 + 板内延续兜底（前一条键 →
  carry; **永不整批 None**）。
- 消费：立绘**按记录**切（每条记录一个表情键）、typing 节奏; 前端 emo_version
  感知补切已显示段。真机一章 6 板 = 6 次调用（875/922/1031ms, `retry=0`）。
- 质量日志: `scene_anno group= n= npc= retry= fallback_items= carry=→out=`。
- **测试桩口径**：桩从 user 消息 `恰 N 项` 取条数（**别**用 `^\d+: ` 数 system 行
  ——模板【示范】也带编号行, 会恒多 4 条, 让用例全程走兜底路径还不报错）。

**place（事件型稀疏锚点, v2 单源切换 2026-09-07）**
- **主 LLM 不写地点**（schema/rules 已删；写作约定 = "换场即换段"）。
- 标注层 prompt：`place_annotate.md`（判据与编剧 rules 镜像：从…走进/推开…门→换场；
  转身/坐下/同地点动作→keep；时间流逝/回忆/拿不准→keep）。输出锚点数组,
  引擎写回**变更句**句项 `place` 键（稀有）。
- 消费：导演按锚点句切背景；前端段首切 + 晚到即切。**词表 = `config/settings/
  world/place_entities.json`**（168 条语义键表, `core/media/place_table.py` 加载;
  层1 `keywords` 别名 0 调用 → 层2 整表含 `note` 就近推测）。旧
  `_director_whitelist.json`（31 条裸 slug）**只剩降级兜底**。
  ⚠️ **表键 ≠ 资产 scene_id**（`classroom`↔`class_room`），翻译走 `files` 文件名。
  缺素材 → **黑屏 `black` + 报"素材未找到"**（不静默换别的图）。
  速查/防坑见 `docs/AI_BRIEF_PLACE.md`。
- **视觉键隔离**：`render_bond_scene_text` 只读 text/emotion/inner —— place 不进
  LLM 上下文（resume 窗口不被视觉键污染）；但进 payload/事件流供回放时间轴。

**双路 lane（webgui）**：Q_emo/W_emo 与 Q_place/W_place 独立队列消费者并行；
推进门控 = **双路齐**（emotion 内容判完成 / place 靠 scene._place_done 标记, 含 keep）。
分支反应段/回放场景/无词表/**纪念窗口**（立绘隐藏+背景清空, 标了没人看）= 视为就绪
不占 lane（`_memorial_no_visuals`）。CLI/测试同步路径在引擎内串行。

**纪念（memorial, v2 2026-09-12 接通）**：板含 `stage:memorial` → 引擎 `in_memorial`
置位（**新一块解析成功**时复位 = 区间到块尾）→ 前端隐藏立绘 + 清空普通背景 + 纪念图淡入；
生图由引擎在**一行 memorial 解析出来时**触发（prompt = 块级 `art` 意向, 缺省触发句）;
v1 的 `MemorialProbe`/`memorial_exit` 动作已退役。**图是异步的 → 回执单开一条
`memorial_image` marker 落真源**（append-only 不可补写原事件）, 回放/重启按"其后没有
`vn_exit`/`vn_abandon`/`session_end`"恢复——**不是**按 `vn_enter` 划范围
（**预热会在 `vn_enter` 之前就出图**, 决策 #40）; v2 板落 `memorial_enter`, 窗口结束
自动补 `memorial_exit`（跨重启也成立: 创建 state 时从事件流初始化记账）。

---

## 5. 事件流与恢复语义（事实主线）

- **存储**：`data/worlds/{world}/characters/{char}/events.jsonl`（每角色一条世界线,
  session_id 来自 meta.json；append-only, 事件不可改删——**废弃段用 marker 遮断**）。
- **事件**：`{type, subtype, payload}`。type: mmt / bond / l2d / affection；marker 是
  is_marker 的状态行（session_start/end、vn_enter/vn_exit、vn_abandon、vn_state、
  memorial_enter/exit、**memorial_image**＝纪念图异步落盘回执 {url,prompt,w,h}）。
- **推导**：`session_status` 从 marker 栈推导 ended / in_vn / in_memorial / 当前章。
- **恢复窗口**：`window_messages(events, max_units=120)`（叙事单元计, 倒序装填整条
  驱逐）+ `exclude_abandoned`（vn_abandon 段不进上下文）→ resume / wrapup /
  Bond 预灌同构。
- **回放/中断（2026-09-07 语义）**：中断后重进 → `replay_attempts` 按 vn_enter 分段,
  逐场回放"已记录前缀"（0 LLM, 分支视图合并 picked）→ 队列尽交棒 live 预生成续写
  （LLM 后补）。**开场/恢复即预生成链**, 读屏期间生成下一场。
- **维护工具**：`core/session/maintenance.py`（CLI: heal/supersede/audit, dry-run
  默认）——把废弃段用 vn_abandon 闭合, 新章自然接管；用法见该文件 docstring。
- **选项回录（A1）**：引擎历史在生成时落库（picked 尚不存在）——裁决后
  `record_picked(picked)` 用同一渲染函数重渲尾部 → live 与事件渲染**逐字节同形**；
  分支内容仍不进 LLM 上下文（A2 留档）。CLI 不需回录（裁决文本即下轮 user）。

---

## 6. 选项与分支：现网精确语义（容易被误解的一块）

1. 契约层：`choices` = 选项文本数组(1~3)；`branches` = dict, **键即选项原文**, 值 =
   同 paragraphs 格式的反应段（1~3 句, 无嵌套选项）。每个中段板 1 组选项。
2. 点击选项 X（记录流 v2）：**玩家那句不上屏**——选项组**留在屏上**转只读态（压暗 +
   高亮所选; live 侧禁用, 只读回放侧可点=只推进）, 正文停在
   上一句; 同时落库(整板 payload+picked=X) → A1 回录 → 立即预生成下一板（输入"（继续）",
   历史已含物化裁决行）。v1 旧档仍是"分支内容当屏直显（零 LLM）"（冻结不改, 决策 #37/#41）。
3. ~~自由输入~~（2026-09-10 锁死）: **产品内 VN 没有自由打字通道**——纯叙事板
   点画面推进（固定输入"（继续）", 2026-08-30 起已替代输入框; 按钮本身已于 #41 删除）; 玩家的"话"只经
   选项说出——**老师的台词 = 选项文本**（给了选项 = 老师在开口）。CLI/API 层
   保留任意文本通道仅作开发/实验用途, 非产品语义; 自由对话类体验移交邀约扩展
   （docs/DESIGN_MEETUP.md）。
4. **AI 视角**：正文 + `（选项: A/B）` + `（选择了: X）`；**看不到分支内容**（有意
   决定）。resume/回放视图(人看) = 板正文序列（**玩家那句不在其中**——要显示"当时选了哪句"应做成选项态 UI, 决策 #37; v1 旧档仍含所选分支, 冻结）。
5. 收敛链：规则强制选项同主线——分支只影响当下语气/细节。**真分歧 = 契约级改动**
   （事件流分叉/回放分支语义/A1 演进/选项预生成成本）, 见 docs/archive/DESIGN_BOND_CONTRACT_V2 §8。
   **（2026-09-10 拍板定稿: VN 不做真分歧, 收敛链即终局——玩家自由度整体移交
   邀约扩展 DESIGN_MEETUP.md; A2 分支叙事化一并关闭, 分支继续不进 LLM 上下文）**。
6. 配额：契约上限 1~3 / 板; 规则层整章 0~3 次、常单个直白（2026-09-09 形式定稿:
   多数板无 choices, 需要表态才给）; webgui 机械兜底（≥3 次后注记省略）仍在。

---

## 7. 记忆与好感（digest / affection）

- 出厂背景（experience.yml）**不进 wiki**——每会话直注；wiki 只存玩家参与后的事。
- `digest_segment`（wiki_v2, RoundA 记录 + RoundB 组织 + 好感结算）触发点：
  ① bond 完整闭环（vn_exit completed）后 ② MMT 每 N=25 轮（in_vn/in_memorial 中
  不触发）。增量幂等（digested_seq 水位）；失败零损失。
- 结算 delta → `affection|digest` 事件（events.jsonl 为真源）+ wiki 好感快照；
  数值**不直接喂 LLM**（无数字概念, 防讨好/数值化）——未来 relationship_view
  （阶段词）是规划方向。`core/affection/affection_calc.py` 数值层。
- 注入形态：MMT 每轮拼 system 尾（digest 后**下轮**生效）；Bond 开场构造注入（剧情内
  固定）。resume 只注入不消化。

---

## 8. 提示词装配（promptkit）——改文案/加任务前必读

- 代码：`core/promptkit/{box,tail,task,config,report}.py`；盒清单 = `DOMAIN_BOXES`：
  盒A(mmt) 9 块：greeting → persona_mmt → world → story_tone → mmt_tone →
  interperson → environment → rules_mmt → schema。
  盒B(bond) **9 块**：greeting → persona_bond → world → story_tone → bond_tone →
  rules_bond → schema → **place_world（世界区域·剧情地理）** → brain。
  **盒B 至此已无任何词表块**：`lexicon_emotion` 2026-09-10 退出（emotion 归标注层
  逐记录判）、`place_palette` 2026-09-15 换成 `place_world`（用户裁决"**主 LLM 零
  内容词表**"——资产 slug 菜单会**框死** writer；而世界区域是**设定不是菜单**，
  `overview.yml` 里一个学院名都没有、writer 会凭空发明）。判据 = "多给 writer 一个
  手段"还是"少给 writer 一个自由"；"换场"这个能力由 `rules_bond` §五【换场】承担。
  地点/背景系统见 docs/DESIGN_PLACE.md（三层框架）。
- 每轮动态尾唯一入口 `round_messages`：注记们（P16/P17/P18/…）→ task 卡 → user。
- task 卡模板（目标层, 不重复规则书）：`llm/prompts/task_<domain>.md` =
  默认 kind（mmt→chat, bond→scene）；`task_<domain>_<kind>.md` = 其余
  （现存唯一非默认 = task_mmt_wrapup；**task_bond_memorial_exit 已于 2026-09-13
  随 v1 `memorial_exit` 动作退役删除**——`_scene_task_kind()` 恒返回 `scene`）。
  开关 `settings.toml [promptkit] task_card`（默认 true；引擎构造参数可覆盖——
  A/B 对照与回归用）。注：实测 `task_bond.md` = 311 字符（非"≤100 token"量级）。
- 文案仓库 = `llm/prompts/*.md`（rules/environment/task/标注 prompt/digest 模板）——
  **人可改**, 代码只加载。改动任意进 system 的内容后：**夹具必须刷新**
  （`PROMPTKIT_UPDATE_FIXTURES=1 pytest tests/core/test_promptkit_baseline.py`,
  生成后人工审 git diff——只允许有意的内容变更）。
- 注入现状报表：`core/promptkit/report.py describe("mmt"|"bond", ctx)` 与
  `docs/PROMPT_INJECTION_MAP.md`（现网校准版；旧版归档 docs/archive/）。

---

## 9. 体感性能工程（主线项目, 记录于 docs/EXEC_BOND_LATENCY.md）

| 机制 | 说明 | 状态 |
|---|---|---|
| 入口预热 prewarm | 触发轮结束即后台生成首场（staged/adopt/新鲜度校验） | ✅ P1 |
| bridge 预生成 | 纯叙事板读完点画面零等待；链式预生成 | ✅ |
| 分支/预生成竞态 | 裁决后 A1 回录 → 预生成请求带裁决行 | ✅ |
| 双路标注并行 | emotion/place lane, gate 双路齐（不增等待） | ✅ |
| 超时与重试语义 | LLM client 默认 240s；场级语义重试 ≤3 后 closing；前端 busy 轮询 status | ✅ |
| 前缀缓存 | system 逐字节稳定 + 日志 `cache_hit/cache_miss`（usage） | ✅ 数据面 |
| task 卡降低瞎猜重试 | 每轮目标显式化（实测: 最坏 10s 有结果而非 4min 三连败） | ✅ |
| reasoning 档位 | `settings.toml [llm].reasoning_effort`——**用户裁决项**（low≈9s/场 vs high≈23s） | 待用户定 |
| SSE 流式渐进渲染 | 首段 TTFT 即显 | 未立项（P3 候选） |
| choice 板裁决前全预生成 | InfiPlot 式（收敛链下可行, 成本×N） | 关闭（2026-09-10: 收敛终局, sibling 候选为终态） |

---

## 10. 配置体系

- **角色六文件**（config/characters/{char_id}/）：profile(REQ 必填层)/personality/
  knowledge/experience/typical/script.yml——REQ~/SIG~ 前缀 = 必填/重要标记,
  **yaml_to_prompt 渲染时剥前缀**；script.yml 的 SIG~main_tone/mmt_tone/bond_tone
  分域注入（盒内 tone 专段与 dump 会二次出现 = 既有行为）。
- **世界观** overview.yml：common+system 注入（【世界常识】【世界规则】）, hidden 不注入。
- **人际关系** settings/relation/interperson.json 扁平权重表：自表条目会话级注入 +
  `mmt_inspect_character` 静默轮按权重访问他人人设（1=profile/2=+personality/
  3=+experience——runtime 现网消费）。
- **运行时配置** settings.toml（gitignore, GUI 设置页读写）：`[llm]`(api/base/model/
  reasoning_effort) · `[llm.tasks.*]`(按形态覆盖档位/max_tokens, 真源 llm/task_levels.py)
  · `[image]`(api/model/screen_size/**enabled 生图总开关**) · `[promptkit]`(task_card)。
  优先级 构造参数 > settings.toml > .env > 默认。
  **生图总开关**：`[image].enabled=false`（GUI 复选框）或环境变量 `LIVE2BE_IMAGE=off`
  （优先, 进程级）→ `llm.image_gen.image_enabled()` False → 纪念场景降级纯文字
  （webgui 不开生图线程 / vn_cli 当没注入 / 直接 `generate()` 明确报错）。
  **测试默认硬关**（tests/conftest.py 会话级 autouse 设 `LIVE2BE_IMAGE=off`）——
  本机配着真 key 时跑测试也不会出图烧钱、不写 gallery。
- **资产** assets/(gitignore)：illustration/{char}/{outfit}/emotions.yml + diff/spine、
  background/、`_director_whitelist.json`（**旧 place 白名单, 只剩降级兜底** ——
  现役词表 = `config/settings/world/place_entities.json`, 见 §3.3/§4）。
  **标准外观格式（2026-09-12 定稿）= `emotions.yml` + `portrait/` + `spine/` 三项必有,
  `diff/` 可选**（OC 不好做 spine 动画）; `spine/` 播差分, `portrait/` = 其他界面渲染资产。
  **MMT 列表头像 = 每个角色各取自己的** `portrait/*.png`（首选 `collection.png`）,
  缺 portrait/ 才回落 `diff/*Idle*.png`（`webgui/routers/mmt.py:_find_avatar`）。
  **`mmt/` 目录已退役删除**（代码不再读; 遥香那张待机帧迁到 `diff/haruka_spr_Idle_01.png`）。
  （历史: 一度改成"全角色共用遥香那一张", 属过度解读, 已回退。）
  **portrait/ 五件套补齐工具**（本地, tools/ 被 gitignore）: `python tools/sync_portrait.py`
  干跑 → `--apply` 拷贝 → `--verify` 查标准 → `--audit` 与官方源逐字节比对; 源 =
  `D:\myStuff\tools\Blue-Archive-Asset-Downloader\JP_Android_Extracted\Bundle\Texture2D`
  （或 `LIVE2BE_BA_DUMP`; 官方名 `Student_Portrait_{Name}_Collection.png` 等 → 本地标准名,
  尺寸固定 404x456/252x204/182x144/304x240/172x136; 外观 = 名字中缀 `_Newyear`）。

---

## 11. WebGUI 运行与前端

- 启动：`python -m uvicorn webgui.app:app --host 127.0.0.1 --port 8000`（见 entrance/）。
- 结构：`webgui/bond.py`（BondState 状态机: busy/round/pregen/staged/replay/lanes…）、
  `webgui/chat.py`（每角色输入队列 worker + 预热挂钩）、`webgui/routers/*`（HTTP 壳,
  `_resolve_scene` 附 background_url/fx/place_bg）、`webgui/static/js/{bond,mmt,gui}.js`。
- 关键交互语义：进入/回放零等待；turn 被拒 = busy（前端 waitTurnIdle 轮询 status,
  **绝不重发已消费的 submit**）；gate_busy = 双路标注未齐；emo/place 补切经版本号。
- 测试桩约定（**改引擎标注行为必读**）：各测试文件 ScriptedLLM 按 **user 尾部关键字**
  应答异步调用——emotion 标注（user 含 `情绪标签`）→ 全 nomal 数组, **条数从
  `恰 N 项` 取**（别用 `^\d+: ` 数 system 行: 模板【示范】也带编号行, 会恒多 4）;
  place 标注("变更句数组")→ []；digest("记录员/整理者")→ 空包。新增标注任务 → 同步给
  tests/webgui/test_bond.py、tests/core/test_vn_cli.py、test_memorial_mode.py、
  test_director.py 等桩补分支, 否则吞场景脚本。

---

## 12. 测试/实验/维护约定

- 测试：`pytest tests/{core,webgui,llm} -q --basetemp=.testtmp/pw`——**Windows 下
  basetemp 需预建目录**（New-Item -ItemType Directory .testtmp/pw）, 否则 tmp 用例
  全挂；默认 tmp 清理有权限错。JS：`node --check webgui/static/js/*.js`。
- 夹具：promptkit 基线夹具 tests/fixtures/promptkit/*.txt 刷新纪律见 §8。
- **固定路径一律写进 `core/paths.py`**（2026-09-19 用户裁决：*"写成 macro 的形式
  放在最上面……最后改成你用 grep 能直接全量定位的方法"*）：消费方
  `from core import paths` → `paths.XXX_PATH`（**写全 `paths.`**）。全量定位两条 grep:
  `grep -n "^[A-Z][A-Z_]* = " core/paths.py`（清单）/ `grep -rn "paths\.[A-Z]"`（消费点）。
  **不许在函数体里现拼项目根路径**——`tests/core/test_paths.py` 扫 `core/ webgui/
  llm/ contract/` 守门（现拼 `Path(__file__) / "assets"` 之类会直接红）。
  包内相对资源（模块找自己目录下的文件）不在此列。
- **web 端到端两层**（2026-09-11, 见 experiments/web_e2e/README.md）: ① **A 层 HTTP** =
  `tests/webgui/test_web_http.py`（httpx + ASGITransport 打真实 app, 桩 LLM/临时
  store 注入, ~1s, 随全量跑）——路由/状态码/响应头/静态挂载/JSON 契约/settings 往返;
  ② **B 层浏览器** = `python experiments/web_e2e/run.py`（Playwright 驱动**本机已装**
  Chrome/Edge, 不需下载浏览器; 桩世界 = 真 app + 桩 LLM + 临时世界线）——真点击
  登录→MMT→羁绊入口→VN 首板/裁决/收尾全链, 产物 = 逐步截图 + 逐段文字 + console
  错误/失败请求（`.testtmp/webtest/<ts>/`）。**VN 是点击推进制 + 逐段替换渲染**:
  一次只显示一段, 段末等左键（继续三角带无限 bob 动画 → 脚本别点它, 点 `#bond-text`;
  **板读完的机器可读信号 = `#bond-continue.ready`**（按钮已删, 决策 #41）;
  点选项后**选项组留在屏上转只读态**——别等它清空, 直接点画面推进）。注: harness 放
  `experiments/`（tracked）而非 `tools/`（.gitignore 忽略的本机工具目录）。
- **生图默认硬关**（tests/conftest.py 会话级 autouse 置 `LIVE2BE_IMAGE=off`, §10）：
  用例天然不出图、不写 gallery——**不再依赖"本机没配 key"这种偶然保护**。需要真走
  生图分支的用例显式 `monkeypatch.setenv("LIVE2BE_IMAGE", "on")` 并给
  `bond._image_generator` 替身（老例见 tests/archive/test_bond_retired_v1.py）。
  **测试进程硬闸**（2026-09-11 误触计费事故后加）: 闸门在唯一 HTTP 出口
  `ImageGenerator._post_api` 上——pytest 进程里一律拒绝（`PYTEST_CURRENT_TEST` /
  `sys.modules['pytest']` 判定），要真调必须显式 `LIVE2BE_IMAGE_ALLOW_REAL=1`;
  用例请 monkeypatch `_post_api`；**探针/实验请用干跑** `LIVE2BE_IMAGE=dry`
  （构造完整请求 + 打日志, 不发 HTTP, 返回占位 GeneratedImage 不落盘）。
- **可归因性埋点**（2026-09-11, 回答"这内容从哪来"）:
  ① `bond_board_deliver src=stream|gen|queue|prewarm|draft|replay board=N recs=N
  call=xxxx dur=ms`——**每板一行**, 标明这一板是怎么到玩家眼前的（0 LLM 路径的
  call 为 `-`, 队列板带"当初写它的那次调用" id）; `bond_pregen src=queue|gen call=…`
  区分"领队列"与"真调用";
  ② `llm chat/chat_full` 日志补 `out=/in=`（completion/prompt tokens）——此前只看得到
  prompt 侧 cache 命中, 判断"单块还能写多长"只能靠记录条数估。
  用途: 真机"玩家几乎零卡顿"里有多少是生成、多少是缓存/回放, 一眼可查。
- 镜像防漂移测试：判据类文案（rules ↔ place_annotate）用共 token 断言兜底。
- experiments/：真 API 基准（bond_bench_thinking / e2e_bs_bench / promptkit_card_ab /
  two_pass_real …）与 smoke；用 conda env python 运行, 先确认 settings.toml。
- 提交纪律：**每节点一提交**；文档与代码同节点更新；人设/rules 内容改动与夹具同批。
- 错误格式：`[file.py][ErrType][信息]`（core/common/errors.py）；失败静默降级打
  WARNING 单行可 grep（计时/缓存等 INFO 埋点按 §6.1 约定）。
- 开发哲学：宁缺勿错 > 完美兜底；append-only 不可补 → 门控保证落库前视觉键就绪。

---

## 13. 演进中 / 未决（先读文档再动）

| 项 | 状态/位置 |
|---|---|
| Bond contract v2（段/换场/背景标注分层; 反应段外置; end 形态; 语法 A/B） | docs/archive/DESIGN_BOND_CONTRACT_V2.md §8/§9（**已归档 2026-09-10**） |
| **VN 契约形式换代（记录流 v2）** | docs/DESIGN_VN_UPGRADE.md（**P0–P2 已落地, 真机在跑**; P3/P4 未做; **§14 渲染层 = 多人同框站位/动作, 设计稿未实现（决策 #36, 暂缓）**） |
| 真分歧 vs 收敛链（分支/事件流分叉） | **已定稿（2026-09-10）: VN 收敛链即终局, 真分歧不立项**——玩家自由度移交邀约扩展（DESIGN_MEETUP.md）; A2 分支叙事化关闭 |
| reasoning 档位 / SSE / choice 板全预生成（已关闭 2026-09-10, sibling 为终态） | §9 表与 v2 §5.4 |
| 好感可视化（relationship_view 阶段词） | §7; 未立项 |
| 官方固定剧情（XML/剧本管线） | 未动工（与动态契约并列的另一条线） |
| 见面式对话扩展（邀约/扯皮窗, 玩家显式发起/纯对话/中断打终止） | docs/DESIGN_MEETUP.md; 预期未立项 |
| **回忆册（书页 UI: 一格一角色 → 角色页 → 只读回放）** | docs/DESIGN_COLLECTION_BOOK.md（**P0 已落地 2026-09-12**; 口径: 只渲染 `vn_exit completed` 的章、不建索引表（事件流派生）、0 LLM）; P1 未做（图挂 memorial 板/3D 翻页/书签） |
| **记忆图 v3（实体中心节点 + 混合召回 + 时间架构 + 组合重组）** | docs/DESIGN_WIKI_V3.md（**设计稿**; **V3-0 召回台账已落地 2026-09-13**; V3-1a 起未实现。**§4 时间 = 三层时钟**：剧情时间（角色口径）· 现实日历（只做生日/节日触发器）· 壁钟（只做审计）——**两钟不试图同步**，冲突走单向**目标日吸附**。Q14–Q22 见 §10） |
| **第四面墙 / creepiness / OS（Orwell'S 操作系统）** | docs/DESIGN_FOURTH_WALL.md（**立项稿 2026-09-13, 只留接口不实现**; 地基 = `archive/world_model_evolution.md` 阶段 15「单体倒流=局部熵减=他人眼中失忆」; 理论核心 = **只有玩家跨世界线**; creepiness 可关闭/达阈值**不惩罚**只开门）; 唯一已落接口 = `real_clock.rewind_count`（随 V3-4） |
| promptkit 注记体系引擎化（vn_cli 同款合并） | DESIGN_PROMPTKIT §9 后续可选项 |

**文档路由表（读前看文首"状态"栏, 旧档已归档 docs/archive/）**：
- 注入地图（现网事实）：docs/PROMPT_INJECTION_MAP.md
- 提示词装配 + task 卡：docs/DESIGN_PROMPTKIT.md
- Bond 契约 v2（段/换场/place 标注层, **已归档 2026-09-10**）：docs/archive/DESIGN_BOND_CONTRACT_V2.md
- **VN 契约形式换代（记录流 v2, 当前主线设计）**：docs/DESIGN_VN_UPGRADE.md
- **背景/地点系统（三层框架: 资产层 → 语义键层 → 契约查询层）**：docs/DESIGN_PLACE.md
  （2026-09-05 定稿; **2026-09-15 补了状态头**——原先漏在本路由表外被绕读多轮。
  §1③/§5 的"主 LLM 写 place 字段 + 注入活跃键表"**已被记录流 v2 与
  "主 LLM 零内容词表"裁决取代**; §1② 语义键层与解析链仍有效）
- **地点系统速查（⚠️ 给 AI 看的防坑版, 改地点代码前先读它）**：docs/AI_BRIEF_PLACE.md
  （2026-09-19 用户要求建: *"把文档中误导你的重写成你理解的语言……这个是给你看的"*。
  内含"会带偏你的旧话"逐条清单）
- **回忆册（书页 + 角色页 + 只读回放, P0 已落地）**：docs/DESIGN_COLLECTION_BOOK.md
- **记忆图 v3（实体中心 + 混合召回 + 时间架构 + 组合, 设计稿, V3-0 已落地）**：docs/DESIGN_WIKI_V3.md
- **第四面墙 / creepiness / OS(Orwell'S)（立项稿, 只留接口不实现）**：docs/DESIGN_FOURTH_WALL.md
- 召回阈值实验（nomic vs Qwen3 实测数据）：docs/EXPERIMENT_CAND_HIGH.md
- 全量审计（分级 + 未决项台账）：docs/AUDIT_2026-09-13_FULL.md
- 上下文窗口（120 单元语义）：docs/DESIGN_CONTEXT_WINDOW.md
- 体感延迟工程：docs/EXEC_BOND_LATENCY.md
- 记忆体系总设计：根级 DESIGN_BRAIN.md（混合史, 慎读）；视觉协议：core/DESIGN_VISUAL_PROTOCOL.md
- 模块级设计：core/DESIGN_{MMT_CHAT,GUI,SEGMENT,WORLD,MULTI_CHAR}.md（BOND_STORY 已归档）
  与 docs/archive/DESIGN_BOND_STORY.md（旧 VN 运行时）
- 其他根级说明：README.md / CLAUDE_OPTIMIZE.md / TODO.md / ASKYOURSELF.yml / guidance/
