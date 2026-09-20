# CLAUDE.md — Live2Be 项目主文档（2026-09-07 大重构版；**2026-09-20 全量校正**）

> 灵感：Blue Archive 式角色互动叙事引擎。玩家经 **MomoTalk**（类微信聊天）与
> 角色互动，氛围到位时由 LLM 主动触发 **羁绊剧情**（视觉小说），关键瞬间进入
> **纪念模式** 生成立绘。LLM 负责"演"，引擎负责"判"——本文把两者边界讲清楚。
>
> 本版重构动机：旧版停留在历史结构（Sleep 式记忆规划、`core/bond_story.py`、
> `web/`），且对事件流/两遍式/提示词装配等关键机制零覆盖。**以本文为准**；
> 冲突时代码为最终事实，设计意图见文末文档路由表。
>
> ⚠️ **2026-09-20 校正说明**：本次逐节核对代码，改掉了三处**v1 遗留描述**
> （§3.2 Bond 的旧动作契约、§4 纪念的板级进入、§13 回忆册余项），补齐了
> **块/板/记录三层**（§1 原来只有后两层）、§2 分层图漏掉的两个包、§11 列到的
> 已归档测试文件，以及本次新落的**纪念链路四节点**（docs/DESIGN_MEMORIAL.md）。
> 凡本文与代码冲突，**信代码**，并顺手把这段改掉。

---

## 0. 三条主线（读项目先读这里）

1. **创作主线**：主 LLM 每轮只产出"创作"（MMT 消息流 / Bond 记录流文本），
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
| **块（block）** | **一次 LLM 调用的全部输出**——`check_block` 的校验单位、`_in_memorial` 复位的单位、`check_block` 软硬问题的判定单位。⚠️ **一块可能 = 整章**（真机实测：5 板同属一块，只有 seq 14 首条是 `switch`） |
| 板（board） | 块内按 `switch`/老师群切出的**显示单位**——玩家**点画面/选选项**推进一次, = 标注/提交/回放单位 |
| 记录（record） | **v2 的显示/判定最小单元**: 一行 JSON = 一个 `paragraphs` 项（角色 id / narrator / sensei / switch / art / memorial / end）; 引擎**不切句**。⚠️ `exit` 是**解析层遗留值**（旧档回放要认, 2026-09-20 起**不再注入**给 LLM） |
| 段（text/自然段） | **v1 遗留词**（主 LLM 写段 → parse 切句）; v2 已被"记录"取代。⚠️ **规则书里的"段/这一轮"= 一次回复 = 一块**（`bond_story_rules.md` §三 定义），不是"章"也不是"板"——这是最容易读错的一个词 |
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
   ├ bond/bond_story.py      Bond 引擎（记录流解析 + 板派生 + 状态机 + 历史 + 生图钩子）
   ├ bond/                   标注层与契约件: emo_text（情绪按记录）、
   │                         place_annotate/place_cues（换场锚点）、variant_annotate（选图）。
   │                         ⚠️ bond_actions/bond_executor/memorial_actions/stream_probe/
   │                         sentence_splitter（v1 契约与执行）已于 2026-09-21 删除
   ├ session/                事件流: store(events.jsonl)/renderer(叙事化)/chapters(认章+回放)/maintenance
   ├ brain/wiki_v2/          digest 记忆（RoundA/B 提炼 + 好感结算 + 注入视图）
   ├ promptkit/              提示词装配: box/tail/task/report（见 §8）
   ├ worldtime/              时间：三层时钟（剧情/现实日历/壁钟, DESIGN_WIKI_V3 §4）
   ├ common/                 横切: errors（`[file][ErrType][信息]`）/ fuse（形状唯一实现）
   └ parsing/ director/ media/ mmt/ ui/ random_events/ affection/ rag/
contract/       契约地基: records(记录文法+块校验) · schema(LLM 可见文本) · spec/registry/model(动作契约)
                · digest_registry · timeline_index · constants
llm/            client(超时/流式/usage 日志) · image_gen(生图) · task_levels(档位真源) · prompts/文案仓库
config/         人设六文件(REQ~/SIG~) + illustration.yml · settings/world(overview.yml) · settings/relation
data/           运行时数据(gitignore): worlds/*/characters/*/{progress.json…} +
                **soul/**（记忆层: events.jsonl + wiki.jsonl + wiki.meta.json + 变更史）
tests/ core/ webgui/ llm/ renderer/ 分别对应域; experiments/ 真 API 基准与探索脚本
```

注：`core/bond_story.py`/`web/` 是历史名，**不存在**；现为 `core/bond/bond_story.py`
与 `webgui/`。⚠️ `core/brain/{consolidation,hippocampus,recall}.py`（旧版记忆 digest v1）
与 **v1 动作契约整族已于 2026-09-21 删除**；记忆主链 = `core/brain/wiki_v2/`。根级
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
- **每场输出**：**记录流**——一行一条 JSON，从上往下读就是这一段的完整演出
  （文法与约束见契约 `contract/schema.py::build_record_schema` 注入的"本轮输出契约"，
  设计见 docs/DESIGN_VN_UPGRADE.md）。
  ⚠️ **v1 的动作 JSON 已整族退役**：`story_scene`/`story_end`/`memorial_enter`/
  `memorial_exit` 收到 dict 一律**打回重发**（`bond_story.py` 的 legacy_action_rejected）；
  契约/执行四模块（`bond_actions`/`bond_executor`/`memorial_actions`/`sentence_splitter`）、
  `BondScene.from_action`、`stream_probe` **已于 2026-09-21 删除**（考古读 git 历史）。
  收尾 = `stage:end`；纪念 = **`stage:art` + `stage:memorial` 成对**（见 §4 纪念段）。
- **messages 槽位**：`[system=盒B] + engine._history + [P17 约束注记?] + [下一轮纠偏注记?]
  + [场 task 卡 scene] + [user]`
  （task kind **恒 `scene`**；`task_bond_memorial_exit.md` 随 v1 动作于 2026-09-13 删除）。
- 引擎判定：记录流解析（含坏行修复/丢行记账）→ 板派生 → 两遍式标注（emotion/place）
  → 导演视觉（place→背景）→ 契约校验（**硬违规打回重发 / 软违规只记录**，见 §12）
  → 失败重试（feedback ≤3）。**引擎不切句**（v2 一行一条记录）。
- **两种交付模式**（`DeliveryMode`，2026-09-21 节点 2′）：批式 = `BLOCK`（整块先判后交，
  **块级 + 板级**双闸都能拦）；流式 = `STREAM`（生产默认，板一闭合即上屏 ——
  **只有首板交付前**能拦，其后**一律 advisory**）。⚠️ 板级规则 ⊆ 块级规则 ⇒
  板级闸**不新增拒绝**（`art`↔`memorial` 配对等"只有块级能判"的规则在流式下天然是软问题）。
- **下一轮纠偏（节点 3）**：advisory 不等于算了 —— 已交付后发现的形状问题记进
  `BondStoryEngine._pending_feedback`，**下一轮**拼进 notes（场卡**之前**）念一次
  "上一轮输出的**形状**有这些问题: …"，随即**自清**（下一轮仍脏才会重新置上）。
  改动前那些问题只进日志/trace（注释写着"留给上层下一轮注记"，而那条注记从未实现）⇒
  同一类形状错误会在整章每块重演。
- **选项目前语义**（详见 §6）：每板 1 组 2~3 候选项 + 键一致的 branches（选中即显,
  零 LLM）；选项收敛同主线（"假选择/收敛链"）；A1 回录后 AI 只见选择行不见分支文本。

### 3.3 标注两路与异步调用（不进玩家等待主链或并行进行）
| 调用 | 时机 | 输出 | 档位(task_levels) |
|---|---|---|---|
| emotion 标注 | 每板交付后（webgui 异步 lane / CLI 同步） | 词表键数组（长度 = 板内**记录数**, 一条记录一个键; 主角+旁白, NPC 不送） | emotion: off / 512 |
| place 标注 | 同上, **与 emotion 双路并行** | 换场锚点 `[{sentence, place}]`（稀疏；keep=空） | place: off / 256 |
| **选图（第二遍）** | 板首 `switch` 定键之后, **该键不止一张图时**（168 键里 146 个） | `{"image": "<表 files 里的文件名>"}`（空=保持） | place: off / 256 |
| digest | bond 完整闭环后 / MMT 每 25 轮（剧情中不触发） | wiki RoundA/B 增量 + 好感 delta | digest: high / 8192 |
| wrapup 收尾轮 | finish 后 agent_turn（mmt 域, task_kind=wrapup） | 手机消息收尾话 | mmt（default） |
| 生图 | 板上出现 `stage:memorial` 时（prompt = 块级 `art` 画面意向 → 缺省触发句; **只在真出现纪念时开画**） | 图片（**非 LLM** 主链外；总开关见 §10） | — |

**选图（`core/bond/variant_annotate.py` + `llm/prompts/place_variant.md`, 2026-09-19）**：
第一遍（`resolve_place`）只回答"**哪个地点**"；同一地点在资源库里常有好几张图 ——
**时刻/天气**（`_Night` 153 张 / `_Sunset` 35 张）与**作者差分**（45 个键各有 ≥2 张
无变体图，区别写在 `note` 里：*"请使用差分2"*、*"2则有圣诞树"*）。此前引擎走
`catalog.background(sid, variant=None)` = **永远第一条**，两条轴都选不了。
现在：候选 = 该键 `files` 的每一张（标签机器派生：`夜` / `默认·差分2`），
**作者 `note` 原样进 prompt**（用户：*"我的部分 note 里面本身就会教 LLM 某些特殊
常用的夜景以及差分的区别"*），输出必须是候选之一（否则丢弃 = 保持）。
⚠️ **不走关键词表**（用户当场否掉）：时刻词在文本里 ≠ 时刻
（「这些灯光，感觉像在白天一样呢~」其实是夜；「私は夜の散歩が一番好きです」是意愿句）
——那四句反例写进了 prompt。选中的文件落 `payload.place_asset`（旧事件没有 → 默认图,
回放安全）；取图**优先走表的路径**（catalog 的 scene_id 派生会漏 6 张）。

**生图三条（2026-09-20 节点 C/D, docs/DESIGN_MEMORIAL.md）**：
① **画面意向 = `art`**（块首条、**不上屏**、一章至多一次）；缺 `art` → 降级用
`memorial` 的转场句当 prompt（`prompt_source=memorial_text`）；
② **性格简卡进 `character_hint`**——生图模型不知道人设就画不出神态（真机那张图被画成
明亮的笑）；`illustration.yml` 手写优先, 空则 `DynamicCharacter.image_persona_brief()`
从 `personality.yml` 的 `SIG~brief_traits` 兜底；
③ 提示词尾段（`llm/image_gen.py::_APIYI_TAIL`）含**画幅 + 构图 + 光线 + 负向**——
"忘写构图"是 Gemini 图像模型的常见失误, 别把它改丢。
可归因：gallery json 记 `prompt_source`/`refs`/`model`/`elapsed_ms`（缺省不写）。

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
- **视觉键隔离**：`render_bond_scene_text` 只读 text/emotion/inner —— place / place_asset
  不进 LLM 上下文（resume 窗口不被视觉键污染）；但进 payload/事件流供回放时间轴。
- **选图（第二遍, 2026-09-19）**：定键之后若该键 `files` 不止一张图 → 选图调用
  （`variant_annotate.pick_image` + `place_variant.md`，详见 §3.3）。**板首 `switch`
  与句级锚点都发**（两处都是换场）：板首 → `payload.place_asset`；锚点 → 那一句的
  `paragraphs[i].place_asset`（锚点用**锚点那一句**当文本）。前端取图**优先走表**。

**双路 lane（webgui）**：Q_emo/W_emo 与 Q_place/W_place 独立队列消费者并行；
推进门控 = **双路齐**（emotion 内容判完成 / place 靠 scene._place_done 标记, 含 keep）。
分支反应段/回放场景/无词表/**整板都在纪念里**（立绘隐藏+背景清空, 标了没人看）=
视为就绪不占 lane（`_memorial_no_visuals`）。
⚠️ **"整板"的判据 2026-09-20 改过**（见下面纪念段 M3）：含 `memorial` 的板**不再一律跳过**
——只有进入点落在**板首**（`memorial_at` 为 0/缺字段）或窗口从上一板延续时才跳过；
否则触发记录**之前**那几条是在正常视觉下播的，**必须标**（不标就立绘恒默认表情）。
CLI/测试同步路径在引擎内串行。

**纪念（memorial；v2 2026-09-12 接通，2026-09-20 定稿语义 —— 详见 docs/DESIGN_MEMORIAL.md）**

> ⚠️ **v1 的"纪念子模式 + enter/exit 动作"已退役**：现在**只有一条进入记录，没有退出
> 记录、没有退出动作**（`memorial_exit` marker 仍在，但由**引擎补写**）。任何"让模型
> 输出 memorial_exit"的想法都会打回重发（反馈回环）。

- **两个字段分工（M1/M2）**：`{"stage":"art"}` = **给画师**的画面意向（块首条、
  **不上屏**、一章至多一次）；`{"stage":"memorial"}` = **给玩家**的转场句（上屏，
  **并且它就落在黑屏上**）。二者**必须同轮成对**——契约硬规则与规则书 §六都写死了，
  示例也是配对形状（原来示例是"光杆 memorial"，真机 writer 照抄 ⇒ art 命中率 0/5）。
- **进入点是记录级（M3, 2026-09-20 用户裁决："从 memorial 那一句开始"）**：
  板载荷带 **`memorial_at`**（= 触发记录在 `paragraphs` 里的下标），前端 `bond.js`
  播到**那一段**才：隐藏立绘 + 清空普通背景（黑屏兜底）+ 图就绪静默淡入。
  它**之前**的记录仍以正常视觉播出。`memorial_at` 为 None（旧档/普通板）→ 退回板级。
- **退出 = 块边界（M4）**：引擎 `_in_memorial = False` 发生在**新一块解析成功**时
  （不是尝试循环开头——预生成/重试失败不算收窗, 决策 #40 ③）；章在窗口内结束时由
  `bond_finish` 用 `force=True` 强闭合 marker。前端退出时按**当前板**的
  `background_url` 把普通背景还回来。
- **章内至多一次（M5）**：第二次 `memorial` → `_demote_repeat_memorial` 静默拒绝
  （降级为标准旁白、文字照常显示, 不生图/不置位/不写 marker/**不给模型反馈**）。
- **默认不在纪念轮收尾（M6）**：软建议（规则书 §六 原文 *"除非你真的认为就在插画上
  收尾更有意境"*）——**没有契约校验**（放进"违反即被丢弃"就是假威胁）；真机那种
  "memorial 与 end 同块"只打一条**软问题**（见 §12）。
- **不做"补写"（M7）**：漏写 art 时**不**补一次调用；先靠文案 + 埋点量命中率
  （`gallery json` 的 `prompt_source` / 软问题 grep）。真机唯一那一章是 0/5 块写过 art。
- 生图由引擎在**一行 memorial 解析出来时**触发（流式即时 / 非流式整块后补触发）。
- **图是异步的 → 回执单开一条 `memorial_image` marker 落真源**（append-only 不可补写
  原事件）, 回放/重启按"其后没有 `vn_exit`/`vn_abandon`/`session_end`"恢复——**不是**
  按 `vn_enter` 划范围（**预热会在 `vn_enter` 之前就出图**, 决策 #40）；v2 板落
  `memorial_enter`, 窗口结束自动补 `memorial_exit`（跨重启也成立: 创建 state 时从
  事件流初始化记账）。

---

## 5. 事件流与恢复语义（事实主线）

- **存储**：`data/worlds/{world}/characters/{char}/**soul**/events.jsonl`
  （每角色一条世界线, session_id 来自 meta.json；append-only, 事件不可改删——
  **废弃段用 marker 遮断**）。⚠️ **路径在 `soul/` 下**（2026-09-04 拍板"记忆层自包含":
  events 原材料 + wiki 成品 + meta 同居）——真源 `core/session/store.py:112`；
  旧文档写的 `characters/{char}/events.jsonl` **是错的**（2026-09-20 更正）。
- **事件**：`{type, subtype, payload}`。type: mmt / bond / l2d / affection；marker 是
  is_marker 的状态行（session_start/end、vn_enter/vn_exit、vn_abandon、vn_state、
  memorial_enter/exit、**memorial_image**＝纪念图异步落盘回执 {url,prompt,w,h}）。
  ⚠️ **v2 的 `memorial_exit` 是引擎补写的**（payload `{"v2":true,"auto":true}`），
  不是模型输出——别去规则书里找"怎么写 exit"。
- **推导**：`session_status` 从 marker 栈推导 ended / in_vn / in_memorial / 当前章。
- **恢复窗口**：`window_messages(events, max_units=120)`（叙事单元计, 倒序装填整条
  驱逐）+ `exclude_abandoned`（vn_abandon 段不进上下文）→ resume / wrapup /
  Bond 预灌同构。
- **回放/中断（2026-09-07 语义）**：中断后重进 → `replay_attempts` 按 vn_enter 分段,
  逐场回放"已记录前缀"（0 LLM, 分支视图合并 picked）→ 队列尽交棒 live 预生成续写
  （LLM 后补）。**开场/恢复即预生成链**, 读屏期间生成下一场。
  ⚠️ **回放读的是 overlay（真源 + 章内暂存）**: B0 整章暂存后进行中的章**不在真源**
  ⇒ 只读真源会让"章进行中重进"看不到任何段（2026-09-20 修 `replay_attempts` /
  `_interrupted_replay_queue`; `_pending_in_vn` 当时改对了）。
- **维护工具**：`core/session/maintenance.py`（CLI: heal/supersede/audit, dry-run
  默认）——把废弃段用 vn_abandon 闭合, 新章自然接管；用法见该文件 docstring。
  **地点改名** = `python -m core.media.place_rename --from X --to Y [--apply]`
  （PL6, dry-run 默认）: 扫引用面（事件流 + 暂存 + `_place_review.json`）→ 改表那一行
  → 给 `data/worlds/{world}/place_renames.jsonl` 留痕。**事件流不动**（append-only）;
  台账的消费方 = `_place_bg()` 把"素材未找到"解释成 *"key 'X' 已改名为 'Y'"*
  （`core/media/place_renames.py`）。⚠️ 表是 **tempo → repo** 单向同步, 就地改 repo
  的表只对本机有效。
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
6. 配额：**契约**上限 1~3 / 板。
   ⚠️ **旧口径"规则层整章 0~3 次、多数板无 choices"已作废（v1 的）**——
   记录流 v2 起交互密度**由 rules 引导**（*"一段戏里老师开口 3~5 次"*），
   引擎不再逐轮念配额（P0-7c 退役那条注记）。
   真机实测（2026-09-19 量 9/11–9/12 的档）：**5/6 与 13/14 的板都带 choices**
   —— 因为 `sensei` 群结束就切板（`records.py`），**板主要是选项点切的, 不是 switch**。
   一段戏 30~45 条记录 ÷ 3~5 个选项点 ≈ **每板 3~9 条**（真机均 5.1~8.7）。
   ⇒ **板数 ≈ 交互密度, 是产品参数, 不是 bug**；每板固定开销 = emotion 一次 + place 一次
   （都廉价且在异步 lane, 不挡玩家）。

---

## 7. 记忆与好感（digest / affection）

- 出厂背景（experience.yml）**不进 wiki**——每会话直注；wiki 只存玩家参与后的事。
- **两层写法与粒度（2026-09-20 用户裁决；改 digest prompt/契约前必读）**：
  **`episode` = informative but single**（信息量足，但只讲一件事）、
  **`belief`/`experience` = brief but descriptive**（简短，但描述性——写模式/结论，不复述事件）。
  **粒度跟着"作者单位"走**：**一章羁绊剧情（`vn_enter`…`vn_exit`）= 1 条 episode**
  （正文就是这一章的总结，`title` 用 `chapter_title`；**边界是引擎已知的**，不需要 LLM 猜），
  **MMT 那种一次覆盖多轮的碎聊 = 0~5 条**（需要切分的是它）。段类型由
  `digest._segment_domain` 从 marker **派生**（不落库，与 `session/chapters.py` 认章同一套）；
  ⚠️ **窗口是混的**（真档实测 haruka = 13 条聊天 + 5 块剧情，mutsuki = 26 + 13）——
  "一章一条"**只收口属于这一章**的条目（`event_seq` 与 bond 块相交），聊天那些照 0~5 条留着；
  提示词没压住时 `_collapse_bond_episodes` 留 `significance` 最高的那条 +
  打一行 `digest_a contract=bond` 告警（可 grep）。用户原话：
  *"离散的是 mmt，但 bond story 不应该连续吗"*。
- `digest_segment`（wiki_v2, RoundA 记录 + RoundB 组织 + 好感结算）触发点：
  ① bond 完整闭环（vn_exit completed）后 ② MMT 每 N=25 轮（in_vn/in_memorial 中
  不触发）。增量幂等（digested_seq 水位）；失败零损失。
  ⚠️ **digest 的唯一触发点是 `if completed:`**（webgui `_wrapup_inner`）——而
  `completed` 只可能来自 `stage:end`（`is_end`）⇒ **没有 end 的章永远不进记忆**。
- 结算 delta → `affection|digest` 事件（events.jsonl 为真源）+ wiki 好感快照；
  数值**不直接喂 LLM**（无数字概念, 防讨好/数值化）——未来 relationship_view
  （阶段词）是规划方向。`core/affection/affection_calc.py` 数值层。
- 注入形态：MMT 每轮拼 system 尾（digest 后**下轮**生效）；Bond 开场构造注入（剧情内
  固定）。resume 只注入不消化。

---

## 8. 提示词装配（promptkit）——改文案/加任务前必读

- 代码：`core/promptkit/{box,tail,task,config,report}.py`；盒清单 = `DOMAIN_BOXES`：
  盒A(mmt) **10 块**：greeting → persona_mmt → world → story_tone → mmt_tone →
  interperson → environment → **time_sense（2026-09-17 加）** → rules_mmt → schema。
  盒B(bond) **10 块**：greeting → persona_bond → world → story_tone → bond_tone →
  rules_bond → **bond_shots（镜头与手法, 2026-09-19 PL2）** → schema →
  **place_world（世界区域·剧情地理）** → brain。
  **盒B 的词表纪律（别读错）**：`lexicon_emotion` 2026-09-10 退出（emotion 归标注层
  逐记录判）、`place_palette` 2026-09-15 换成 `place_world`（用户裁决"**主 LLM 零
  内容词表**"——资产 slug 菜单会**框死** writer；而世界区域是**设定不是菜单**，
  `overview.yml` 里一个学院名都没有、writer 会凭空发明）。判据 = "多给 writer 一个
  手段"还是"少给 writer 一个自由"；"换场"这个能力由 `rules_bond` §五【换场】承担。
  ⚠️ **`bond_shots` 是有意的例外**：它给的是**镜头词**（星空/夜空/黄昏/纯黑…）与
  **手法**（switch 组合拳/煽情写法/收尾收法/范本）——用户原话 *"这些词能让 LLM 更好
  的写作"*。与"零内容词表"不矛盾（那条打的是**从 168 条资产菜单里挑**）。
  地点/背景系统见 docs/DESIGN_PLACE.md + docs/AI_BRIEF_PLACE.md。
- 每轮动态尾唯一入口 `round_messages`（实测签名是 `system/user/history/notes/brain`，
  **没有 task 槽**——场卡由**调用方**作 `notes` 末位追加，`bond_story.py` / `momotalk.py`
  各一处；审计 C4 记过这个文档与实现的差）。
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
- **契约文案单源**：`contract/schema.py::build_record_schema` 渲染"本轮输出契约"
  （取值清单 + 硬规则 + **示例**）。⚠️ **示例才是"形状"的来源**——2026-09-20 真机
  art 命中率 0/5 的根因就是**示例里 memorial 是光杆出现的**（取值清单/硬规则/规则书
  三处说法强度不一）。改规则书时**必须同批改示例**，否则模型只学会示例那个形状。
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
  ⚠️ **盒B 只注入 `{profile + personality}` 两层**（`build_prompt("bond_story")`）——
  VN 里的 writer **看不到** typical/knowledge/experience（MMT 才是六文件全量）。
  这是"人设把握不完全"的一个已知来源，改它要连带考虑 system 变长与缓存重建。
- **`illustration.yml`（第 7 个可选文件，专供生图）**：`halo_hint`（非典型光环形状）
  + `character_hint`（**外观要点 + 性格简卡**）。⚠️ 2026-09-20 起性格那一半是必需的；
  为空时引擎用 `DynamicCharacter.image_persona_brief()`（`SIG~brief_traits`）兜底。
  ⚠️ 该文件的文本会被 `_fold_prompt_text` **折成单行**——写 `>` 折行整段，别写 `- ` 列表。
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
  角色的 `ref/` 目录（`sprite_*` 外观 / `style_*` 画风基准 / `halo.png`）是**生图参考图**,
  由 `llm/image_gen.collect_ref_images` 按名字约定收集。
  **portrait/ 五件套补齐工具**（本地, tools/ 被 gitignore）: `python tools/sync_portrait.py`
  干跑 → `--apply` 拷贝 → `--verify` 查标准 → `--audit` 与官方源逐字节比对; 源 =
  `D:\myStuff\tools\Blue-Archive-Asset-Downloader\JP_Android_Extracted\Bundle\Texture2D`
  （或 `LIVE2BE_BA_DUMP`; 官方名 `Student_Portrait_{Name}_Collection.png` 等 → 本地标准名,
  尺寸固定 404x456/252x204/182x144/304x240/172x136; 外观 = 名字中缀 `_Newyear`）。

---

## 11. WebGUI 运行与前端

- 启动：`python -m uvicorn webgui.app:app --host 127.0.0.1 --port 8000`（见 entrance/）。
- 结构：`webgui/bond.py`（BondState 状态机: busy/round/pregen/staged/replay/lanes/memorial…）、
  `webgui/chat.py`（每角色输入队列 worker + 预热挂钩）、`webgui/routers/*`（HTTP 壳,
  `_resolve_scene` 附 background_url/fx/place_bg）、`webgui/static/js/{bond,mmt,gui}.js`。
- **预生成 = provisional（节点 4′, 2026-09-21）**：`_pregenerate` 与 live **同一条交付
  路径**（也传 `on_board` ⇒ `DeliveryMode.STREAM`——此前不传 ⇒ 批式, 同一份输出两条路
  给出**不同的板**）。它的 `on_board` 回调**只记账不落库**：板进 `state.pregen_scene`
  与**草稿旁路**, 事件的 `bond` 正文要等玩家消费后**再推进一次**才写（`_log_scene`）。
  ⇒ "丢弃一个预生成"不需要清任何东西（`docs/EXEC_PIPELINE_UNIFY.md` §3.1 不变量）。
- **纪念视觉在前端的三件事都由 `applyMemorial()` 做**（`bond.js`）：隐藏立绘层 +
  清空 `#bond-bg`（黑屏兜底）+ 图就绪淡入。判定 `memorialNow() = in_memorial &&
  (memorial_at === null || typeSeg >= memorial_at)`——**每段上屏都调一次**
  （`writePara` 开头），所以黑屏精确落在 `stage:memorial` **那一句**上（见 §4 M3）。
  `syncMemorial(st)` 只负责**缓存**状态（`memorialSt`），两个来源都吃：状态对象的
  `scene.memorial_at` / 场景 dict 自身的 `memorial_at`。
- 关键交互语义：进入/回放零等待；turn 被拒 = busy（前端 waitTurnIdle 轮询 status,
  **绝不重发已消费的 submit**）；gate_busy = 双路标注未齐；emo/place 补切经版本号。
  ⚠️ **裁决后自动进下一板**（2026-09-20 用户: *"点了选项应该直接推进"*）:
  点选项 → 选项组留屏转只读 + 高亮所选（决策 #41）,**但不再等第二次点击** ——
  `PICK_ADVANCE_MS`（450ms, 只为让高亮可见）后自动 `goNext()`; 手动点画面/点选项
  走同一函数（`busy` 防重复提交）。两条历史坑都钉在冒烟 `裁决后自动推进` 那一步:
  ① `pendingChoice`（"本板还有未裁决选项"的门闩）**必须在裁决分支复位**, 否则
  `advanceOrFinish` 见它即 return、点画面/点三角全被吞;
  ② 裁决后的选项按钮**不许 `disabled`**（disabled 吞点击 + `onClick` 又排除
  `.bond-choice` ⇒ 点黄着那句毫无反应）；绑定是 `goNext()`, **不回填、不重提交原文本**。
  ⚠️ **结局后粉泡的"手快重进"窗口**（同日报障: *"有足够时间重进，后果不堪设想"*）:
  完成翻转本来靠轮询（`applyBondDone`）→ 有窗口。两道闸: 前端 `finish(completed=true)`
  **立刻**调 `window.mmtLockBondEntries()` 去掉点击；后端 `_entry_already_done()`
  （**只看事件流**, 内存态重启即丢）拒绝重进已完成入口。
  **中途退出（`completed=false`）两道闸都不生效** —— 那种要能再进（静默续章）。
  ⚠️ **好感自动刷新**（同日）: `mmt.js` 每 10s 拉一次 `/api/mmt/characters`,
  **只在 MMT 可见 + 不在 VN 里 + 页面未切走**时; 值没变**不碰 DOM**（不闪）。
  为什么轮询而不是事件: 好感由 **digest** 后台写, 客户端不知道它何时落地。
- 测试桩约定（**改引擎标注行为必读**）：各测试文件 ScriptedLLM 按 **user 尾部关键字**
  应答异步调用——emotion 标注（user 含 `情绪标签`）→ 全 nomal 数组, **条数从
  `恰 N 项` 取**（别用 `^\d+: ` 数 system 行: 模板【示范】也带编号行, 会恒多 4）;
  place 标注("变更句数组")→ []；换场翻译("地点 id JSON")→ `{"place": ""}`；
  **选图("选中的文件名")→ `{"image": ""}`**（2026-09-19 第二遍）; digest
  ("记录员/整理者")→ 空包。新增标注任务 → 同步给 tests/webgui/test_bond.py、
  tests/core/test_vn_cli.py、tests/core/test_director.py 等桩补分支, 否则吞场景脚本
  （v1 存量用例连同 `tests/archive/` 已于 2026-09-21 整目录删除）。

---

## 12. 测试/实验/维护约定

- 测试：`pytest tests/{core,webgui,llm,renderer} -q --basetemp=.testtmp/pw`——**Windows
  下 basetemp 需预建目录**（New-Item -ItemType Directory .testtmp/pw）, 否则 tmp 用例
  全挂；默认 tmp 清理有权限错。JS：`node --check webgui/static/js/*.js`。
- 夹具：promptkit 基线夹具 tests/fixtures/promptkit/*.txt 刷新纪律见 §8。
- **契约问题的软硬分级（改 `check_block` 前必读）**：`contract/records.py` 返回结构化
  **`Issue(code, message)`**；**严重度只跟 `code` 走**（`ISSUE_SEVERITY: IssueCode →
  IssueSeverity` 的显式声明），跟 `message` 中文文案**毫无关系**。
  · **硬**（`打回重发整轮`）：`block.empty` · `block.tail` · `block.head` ·
  `block.head-not-switch` · `block.memorial-repeat` · `block.memorial-forbidden-stage` ·
  `block.art-repeat`；
  · **软**（只记录/打日志）：`block.sensei-run-too-long`（切群处理）·
  `block.art-pair-missing`（**含 memorial 但没有 art**）· `block.memorial-with-end`
  （后两条是"art 配对命中率"的统计口径）；
  · **板级** `board.*`（`check_board`）**全部硬**——板级闸"非空即拦"，但只在**首板
  交付前**生效（流式已交付 ⇒ 一律 advisory，见 §3.2）。
  新增规则 = 加 `IssueCode` + 在 `ISSUE_SEVERITY` 声明一行（忘了声明会被
  `tests/core/test_records.py::test_issue_severity_is_declared_by_code_not_message`
  拦下——那条用例还钉住"文案塞满硬关键词也不改分级"）。
  ⚠️ **历史**：2026-09-21 之前硬/软靠 `HARD_BLOCK_ISSUE_MARKS` **中文子串匹配**，
  给软问题换个措辞就会**静默**升级成"整轮重发"（ARCH_REVIEW P0-3 ⇒ 节点 6 修）。
  ⚠️ **"打回"只在整块未交付时可能**（流式已上屏 ⇒ advisory）——但**不是"算了"**：
  软问题（批式）与 advisory 问题（流式）都进 `_pending_feedback`，下一轮注记纠偏
  （节点 3，见 §3.2）。判"硬/软"只管**本回合**要不要重发。
  ⚠️ 拼问题文本一律用 `contract.records.format_issues(...)`（`Issue` 不是 `str`，
  直接 `"; ".join(issues)` 会 TypeError）。
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
  点选项后**选项组留在屏上转只读态**——别等它清空, 直接点画面推进）。
  ⚠️ **要断言"某一段上屏那一刻"的视觉状态, 必须逐段取样**（`capturePara` 每次
  `_tick` 前读一次）——"板读完再查"已经晚了, 那一刻本来就该是终态（2026-09-20
  纪念 M3 的冒烟就是这么改的）。注: harness 放 `experiments/`（tracked）而非
  `tools/`（.gitignore 忽略的本机工具目录）。
- **生图默认硬关**（tests/conftest.py 会话级 autouse 置 `LIVE2BE_IMAGE=off`, §10）：
  用例天然不出图、不写 gallery——**不再依赖"本机没配 key"这种偶然保护**。需要真走
  生图分支的用例显式 `monkeypatch.setenv("LIVE2BE_IMAGE", "on")` 并给
  `bond._image_generator` 替身（v1 老例 `tests/archive/test_bond_retired_v1.py` 已删;
  现役例子看 `tests/webgui/test_bond.py`）。
  **测试进程硬闸**（2026-09-11 误触计费事故后加）: 闸门在唯一 HTTP 出口
  `ImageGenerator._post_api` 上——pytest 进程里一律拒绝（`PYTEST_CURRENT_TEST` /
  `sys.modules['pytest']` 判定），要真调必须显式 `LIVE2BE_IMAGE_ALLOW_REAL=1`;
  用例请 monkeypatch `_post_api`；**探针/实验请用干跑** `LIVE2BE_IMAGE=dry`
  （构造完整请求 + 打日志, 不发 HTTP, 返回占位 GeneratedImage 不落盘）。
- **可归因性埋点**（2026-09-11, 回答"这内容从哪来"）:
  ① `bond_board_deliver src=stream|gen|queue|prewarm|draft|replay board=N recs=N
  call=xxxx dur=ms`——**每板一行**, 标明这一板是怎么到玩家眼前的（0 LLM 路径的
  call 为 `-`, 队列板带"当初写它的那次调用" id）; `bond_pregen src=queue|gen call=…`
  区分"领队列"与"真调用"; **`bond_pregen_board board=N recs=N dur=ms`**（节点 4′）
  = 预生成**首板**到达时刻——与 `bond_pregen src=gen dur=ms`（**整块**写完）一比,
  就知道预生成的收益有多少来自"增量交付"而不是"整体更快";
  ② `llm chat/chat_full` 日志补 `out=/in=`（completion/prompt tokens）——此前只看得到
  prompt 侧 cache 命中, 判断"单块还能写多长"只能靠记录条数估;
  ③ **图像侧**（2026-09-20）: gallery json 的 `prompt_source`（`art` / `memorial_text`）
  = **art 配对命中率**; `[vn][memorial] 开画 prompt=… src=…` 一行日志同源。
  用途: 真机"玩家几乎零卡顿"里有多少是生成、多少是缓存/回放, 一眼可查。
- 镜像防漂移测试：判据类文案（rules ↔ place_annotate ↔ 契约示例）用共 token 断言兜底。
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
| **纪念链路（art↔memorial 配对 / 记录级进入 / 埋点 / 生图质量）** | docs/DESIGN_MEMORIAL.md（**节点 A–D 已落地 2026-09-20**）。**剩两件**：① **量 art 配对命中率**——改文案后要真机跑一章才知道有没有用（历史基准 **0/5 块**），看 gallery `prompt_source` 或 `grep "含 memorial 但没有 art"`；② **漏写 art 的"补写"方案**——用户裁决"现在不做"，设计稿 §2.4 记了否掉的理由（补出来的板必须排在 `end` 板**之前**，`end` 一落地 `completed=True`、前端即停轮询并 finish，补的板播不出来） |
| 真分歧 vs 收敛链（分支/事件流分叉） | **已定稿（2026-09-10）: VN 收敛链即终局, 真分歧不立项**——玩家自由度移交邀约扩展（DESIGN_MEETUP.md）; A2 分支叙事化关闭 |
| reasoning 档位 / SSE / choice 板全预生成（已关闭 2026-09-10, sibling 为终态） | §9 表与 v2 §5.4 |
| 好感可视化（relationship_view 阶段词） | §7; 未立项 |
| 官方固定剧情（XML/剧本管线） | 未动工（与动态契约并列的另一条线） |
| 见面式对话扩展（邀约/扯皮窗, 玩家显式发起/纯对话/中断打终止） | docs/DESIGN_MEETUP.md; 预期未立项 |
| **回忆册（书页 UI: 一格一角色 → 角色页 → 只读回放）** | docs/DESIGN_COLLECTION_BOOK.md（**P0 已落地 2026-09-12**; **P1① 已落地 2026-09-20**——纪念态落到板）；P1 余项: CSS 3D 翻页 / 缩略图收尾（一章多图时章级缩略图取的是**最后**一张, 未必最动人）；**书签/续读位置不做**（用户裁决） |
| **记忆图 v3（实体中心节点 + 混合召回 + 时间架构 + 组合重组）** | docs/DESIGN_WIKI_V3.md（**设计稿**; **V3-0 召回台账已落地 2026-09-13**; **合成层（四条道路 → 最终分, 调和平均）已落地 2026-09-20**, 见该文 §3.3.4; V3-1a 起未实现。**§4 时间 = 三层时钟**：剧情时间（角色口径）· 现实日历（只做生日/节日触发器）· 壁钟（只做审计）——**两钟不试图同步**，冲突走单向**目标日吸附**。Q14–Q22 见 §10） |
| **第四面墙 / creepiness / OS（Orwell'S 操作系统）** | docs/DESIGN_FOURTH_WALL.md（**立项稿 2026-09-13, 只留接口不实现**; 地基 = `archive/world_model_evolution.md` 阶段 15「单体倒流=局部熵减=他人眼中失忆」; 理论核心 = **只有玩家跨世界线**; creepiness 可关闭/达阈值**不惩罚**只开门）; 唯一已落接口 = `real_clock.rewind_count`（随 V3-4） |
| promptkit 注记体系引擎化（vn_cli 同款合并） | DESIGN_PROMPTKIT §9 后续可选项 |

**文档路由表（读前看文首"状态"栏, 旧档已归档 docs/archive/）**：
- 注入地图（现网事实）：docs/PROMPT_INJECTION_MAP.md
- 提示词装配 + task 卡：docs/DESIGN_PROMPTKIT.md
- Bond 契约 v2（段/换场/place 标注层, **已归档 2026-09-10**）：docs/archive/DESIGN_BOND_CONTRACT_V2.md
- **VN 契约形式换代（记录流 v2, 当前主线设计）**：docs/DESIGN_VN_UPGRADE.md
- **地点 / 背景系统（资产层 → 语义键层 → 两遍判定 → 取图）**：docs/DESIGN_PLACE.md
  （**2026-09-20 重写**: 旧稿是"09-05 定稿 + 两次状态头 + 三次补丁"的千层饼, 已删。
  新稿只写现网事实: 表/两遍判定（层1 别名 0 调用 → 层2 整表 → **第二遍选图**）/
  缺素材与改名 / 三档分流 / 语义检索 / 作者侧工作流 + **§10 会带偏你的旧话**）
- **地点系统速查（⚠️ 给 AI 看的一页纸, 改地点代码前先扫它）**：docs/AI_BRIEF_PLACE.md
  （2026-09-19 用户要求建: *"把文档中误导你的重写成你理解的语言……这个是给你看的"*。
  只放"最容易搞错的事 + 旧话清单 + 用户原话", **机制细节不重复**——重复就会漂）
- **回忆册（书页 + 角色页 + 只读回放, P0 已落地）**：docs/DESIGN_COLLECTION_BOOK.md
- **纪念链路（art / memorial / 黑屏缓冲 / 记录级进入 / 生图质量; 节点 A–D 已落地）**：docs/DESIGN_MEMORIAL.md
- **记忆图 v3（实体中心 + 混合召回 + 时间架构 + 组合, 设计稿, V3-0 已落地）**：docs/DESIGN_WIKI_V3.md
- **第四面墙 / creepiness / OS(Orwell'S)（立项稿, 只留接口不实现）**：docs/DESIGN_FOURTH_WALL.md
- 召回阈值实验（nomic vs Qwen3 实测数据）：docs/EXPERIMENT_CAND_HIGH.md
- 全量审计（分级 + 未决项台账）：docs/AUDIT_2026-09-13_FULL.md
- 上下文窗口（120 单元语义）：docs/DESIGN_CONTEXT_WINDOW.md
- 体感延迟工程：docs/EXEC_BOND_LATENCY.md
- **单一记录流流水线（c′）执行计划**：docs/EXEC_PIPELINE_UNIFY.md（**执行中**。
  Decision 0 = c′（用户 2026-09-21）: 一份 `records → boards` 派生 + **板级闸** + 显式
  交付模式; 节点 0–6, 每节点一提交。**主链已全部落地: 0（协议）· 1（parity 测试网）·
  2′（`_BoardAssembler` + `check_board` + `DeliveryMode`）· 5（桩对齐生产路径）·
  3（下一轮纠偏）· 6（`Issue(code, severity)` 结构化）· 4′（预生成与 live 同路径）**;
  待做（可选地基）: 2″（板级 lifecycle 显式枚举）· 5b（桩结构化分派）; 另: `webgui/bond.py`
  文件拆分（用户 2026-09-21 说"之后再做"）。来源 = ARCH_REVIEW P0-2/P0-3 的根治）
- **重新生成 / 重发 的语义与固化线**：docs/DESIGN_RESEND.md（**设计稿, 未动代码**。
  决策: MMT 提交边界 = **回合提交**; 两区 = 水位之上**丢弃** / 水位之下走
  `wiki_v2/revise` **更正**; 含 `vn_abandon` 族退休方案——存量真源 0 条, 读路径空转）
- 记忆体系总设计：根级 DESIGN_BRAIN.md（混合史, 慎读）；视觉协议：core/DESIGN_VISUAL_PROTOCOL.md
- 模块级设计：core/DESIGN_{MMT_CHAT,GUI,SEGMENT,WORLD,MULTI_CHAR}.md（BOND_STORY 已归档）
  与 docs/archive/DESIGN_BOND_STORY.md（旧 VN 运行时）
- 未来扩展和预留未调用函数 docs/EXTENSION_POINTS.md
- 其他根级说明：README.md / CLAUDE_OPTIMIZE.md / TODO.md / ASKYOURSELF.yml / guidance/
