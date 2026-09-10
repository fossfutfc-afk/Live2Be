# PROMPT_INJECTION_MAP — 提示词注入地图（现网校准版）

> **状态**：2026-09-07 对照现网代码逐点校准（行号为当日实况）。
> **取代**：`docs/DESIGN_WEBGUI_PROMPTS.md`（已归档至 `docs/archive/`，历史参考）。
> **用途**：提示词组装重构（promptkit / task 卡片）的事实基线；LLM 各调用点
> "到底注入了什么"的唯一现网答案。代码改动后本节可能再漂——行号以代码为准，
> 结构争议以本文为准（未来由 promptkit report 工具生成同款报表，见设计尾注）。
> 以 `igusa_haruka`（伊草 遥香）为例。

---

## 0. 总纲：三档注入时刻

| 档 | 内容 | 特征 |
|---|---|---|
| 会话级一次 | 盒A（MMT system）/ 盒B（Bond system） | 进会话/进剧情时拼死，之后每轮/每场原样复用 |
| 每轮动态 | 追加在 messages 尾部（system role 或 user 前） | 只进 LLM context 不入历史 |
| 异步独立调用 | 情绪标注 / digest / 收尾轮 | 不占玩家等待主路径（标注入队、digest 后台） |

两条铁律（贯穿现网实现）：
1. **玩家名不注入** system prompt（momotalk.py:330——学生不直呼自定义名）。
2. **system + history 前缀每轮稳定**，动态内容只在尾部追加——DeepSeek 上下文缓存的
   基本盘（promptkit 重构不得破坏）。

---

## 1. 盒A — MMT system prompt（会话级一次）

`core/momotalk.py:299-322` `start_session()` → `core/promptkit/` 盒装配
（box.py DOMAIN_BOXES["mmt"] 声明式清单; 2026-09-07 Phase 1 抽盒完成——
**盒A v2: 称呼行归位盒顶**, 其余顺序/文案逐字不变, 黄金夹具锁定）:

| # | 块 | 来源/装配点 | 备注 |
|---|---|---|---|
| 0 | 称呼行 | `greeting` 块（blocks.py）: `你好，{display_name}——以下是你的行为规则，请严格遵守：`（名单可多人, 一人分饰多角预留） | **v2 首段（身份先行）**——此前夹在 environment 与 rules 之间（位置不伦不类, 用户拍板 2026-09-07）|
| 1 | `# 角色设定` + 行为规则 | `persona_mmt` 块 = `build_prompt("momotalk")`（parser:396-398）= 六文件 merged raw → `yaml_to_prompt` + `_BEHAVIOR_RULES`（behavior_rules.md，parser:421 模块级加载） | yaml_to_prompt **剥 REQ~/SIG~ 前缀**（parser:285）、下划线转空格。raw = 六文件全量合并（parser:502-509）→ **script.yml 三个 tone 键内容也以 yaml 键值形态出现一次** |
| 2 | `【世界常识】【世界规则】` | `world` 块 = `world_to_prompt(load_world(...))`（world_parser:70-89），overview.yml common+system 档 | hidden 不注入 |
| 3 | `【本角色剧情基调】` | `story_tone` 块 = `load_story_tone(char)`（core/common/tone.py）：script.yml `SIG~main_tone` 优先，personality `SIG~story_tone` 兜底（parser:531-533） | 与块1 dump 里的 main tone 键值**二次出现**（既有行为） |
| 4 | `【本角色 MMT 风格】` | `mmt_tone` 块 = script.yml `SIG~mmt_tone`（char.mmt_tone）| 缺失 → 不注入（条件块） |
| 5 | 人际层自表 | `interperson` 块 = interperson.json self 条目（load_interperson + self_entry_to_prompt）| 便利屋68 权重 2；损坏 → 跳过不挡启动 |
| 6 | MMT 环境 | `environment_mmt` 块 = `momotalk_environment.md` | 虚拟手机场景 |
| 7 | MMT 规则 | `rules_mmt` 块 = `momotalk_rules.md` | rules 内含消息流协议、单人模式、契机导向触发规则、触发 JSON 示范 1~4 |
| 8 | 可用动作 schema | `schema` 块 = `build_schema(mmt_registry, action_list=True)`（contract/schema.py:34-92）| ⚠️ **消息流协议渲染**：`{"messages":[{text}|{action,payload}]}`（2026-09-02 协议），非旧 `{"actions":[...]}` |

---

## 2. MMT 每轮动态尾（agent_turn，只进 context 不入历史）

`core/momotalk.py:543-600` → `round_messages`（core/promptkit/tail.py）：

```
system   = 盒A + "\n\n" + brain 注入段（_brain_injection）
messages = [system] + history + [P16 羁绊进度注记] + [P17 system_note?]
         + [P18 随机事件?] + [task 卡] + [user 原文]
```

| # | 块 | 内容 |
|---|---|---|
| P15 | brain 段 | 拼在 system 内容**尾部、每轮现拼**：出厂背景（experience.yml 原文直注 `render_background_experience`，2026-09-05 解耦后不进 wiki）+ wiki 视图 `render_character_view`（"我记得…"第一人称，facts/beliefs/relations）。digest 后台完成后**下轮**原子替换（momotalk.py:403-453, 598-601） |
| history | 活会话 | 40 轮 × 2 条截断 `_trim_history`（momotalk.py:953-956）；resume 恢复 = `window_messages(exclude_abandoned(events), rounds×3)`（120 单元，momotalk.py:546-549） |
| P16 | 羁绊进度注记 | `_bond_progress_note()`（momotalk.py:930-951）：`【剧情时机】距上次完整剧情 ≥6 轮→铺垫足够可发起` / `<6 → 报事实+沉淀`。**每次 agent_turn 都注入**（含 wrapup 收尾轮） |
| P17 | system_note | 引擎可选参数。现网主聊天路径恒 None（webgui/chat.py:172 不传）；**只有收尾轮传**（wrapup 话术 webgui/bond.py:1240） |
| P18 | 随机事件 | `want_to_speak`（12%，冷却 6 轮，core/random_events/events.py:56-63）："你现在有点想和老师说点别的…" soft 倾向。仅 store 会话触发 |
| task 卡 | 本回合任务（目标层） | `task_mmt.md`（chat，引擎默认）/ `task_mmt_wrapup.md`（收尾轮，调用方传 task_kind="wrapup"）；{char} 占位；开关 settings [promptkit].task_card（默认 true，关闭 = 无卡旧行为）；模板缺失静默跳过。**Phase 2（2026-09-07）启用**——卡 = 末位注记（约束注记之后、user 之前，离生成最近）|

**输出历史格式**（momotalk.py:849-862）：user 原文原样入历史；assistant 按
`[动作名] `前缀 + 去括号切块，仅首块带动作名前缀。

**周边异步事实（旧文档未记）**：
- digest 已**双触发**：① bond 剧情闭环后（webgui `_wrapup` completed=True）；② MMT 会话每
  N=25 轮（`_maybe_mmt_digest` momotalk.py:492-512，in_vn/in_memorial 中不触发）。
  主链 = wiki_v2 `digest_segment`（digest_v2_round_a/b.md 两轮 + 好感结算，momotalk.py:75）；
  `digest.md` / `consolidation.digest_session`（v1）仅剩 experiments/archive 使用。
- `build_prompt("trigger")`（profile + brief_traits 最简模式）只用于 IDE mmt_preset 侧
  （dynamic_character_parser.py:36），不在 webgui 主链。

---

## 3. 盒B — Bond system prompt（进剧情一次）

`core/bond/bond_story.py:290-335` `start_session()` → `core/promptkit/` 盒装配
（box.py DOMAIN_BOXES["bond"] 声明式清单; 2026-09-07 Phase 3 抽盒完成——
**盒B v2: 称呼行归位盒顶**, 其余顺序/文案逐字不变, 黄金夹具锁定）:

| # | 块 | 来源 | 备注 |
|---|---|---|---|
| 0 | 称呼行 | `greeting` 块: `你好，{display_name}——以下是你的剧情行为规则，请严格遵守：` | **v2 首段（身份先行）**——此前夹在 bond_tone 与 rules 之间 |
| 1 | `# 角色设定` + 行为规则 | `persona_bond` 块 = `build_prompt("bond_story")`（parser:400-403）= **仅 {profile+personality} 两层** merged + behavior_rules | script.yml **不进** dump；tone 全靠下面专段 |
| 2 | `【世界常识】【世界规则】` | `world` 块（world_parser:70-89）| 同源重新注入 |
| 3 | `【本角色剧情基调】` | `story_tone` 块 = load_story_tone（core/common/tone.py）| 与盒A同源 |
| 4 | `【本角色羁绊剧情建议】` | `bond_tone` 块 = script.yml `SIG~bond_tone`（char.bond_tone）| 缺失 → 不注入（条件块） |
| 5 | 羁绊剧情规则书 | `rules_bond` 块 = `bond_story_rules.md` | rules 内含：单人模式/3~5 板块+收尾/每板块 1 个选项（2~3 候选项）**branches 必须且键一致**/选项收敛同主线/宁可及早收尾/story_scene 与 story_end JSON 范本/**memorial_enter JSON 范本行内教形状**（rules L66-80：prompt=中文场景指令勿写外观） |
| 6 | 可用动作 schema | `schema` 块 = `build_schema(story registry)`（bond_story.py）单动作 | ⚠️ **只有 story_scene/story_end**；memorial 双动作不在盒里——enter 形状靠 rules 范本教，exit schema 在纪念模式每场由注记补喂 |
| 7 | `【表情标注词表】` | `lexicon_emotion` 块 = `build_emotion_injection`（emotion_lexicon.py:95-112）= emotions.yml 键 + 行尾示范注释 + `eg[键]` 例句 | 词表路径 `assets/illustration/{char}/default/`（2026-08-31 修过 default 段缺失）；缺失 → 不注入（条件块） |
| 8 | `【可去的地方】` | `place_palette` 块 = whitelist common_scenes（**与标注层同源**）| 舞台清单（v2 2026-09-07）：**词表可见性 ≠ 写权限**——主 LLM 不写地点字段（单源判定在标注层），但必须知道舞台范围才不会把剧情困在"肯定有"的场景；措辞明示不输出字段 |
| 9 | brain 段 | `brain` 块 = `load_brain_segment`（momotalk.py:129-156）：出厂背景 + wiki 视图 | webgui 每次 start/replay 都重取（webgui/bond.py:401-406, 542-548）→ **剧情内固定**不随 digest 更新（条件块） |

**地点单源切换（2026-09-07 v2, P3b-2 完成）**：主 LLM **不写 place**（schema/rules
地点说明已删）——换场语义靠"换场即换段"写作约定（rules【段落规划与换场】）；
地点判定移交标注层 place lane（place_annotate.md 持有词表），锚点写回句项 `place`
键（稀有，只进 payload/事件流，render 忽略——不进 LLM 上下文），导演/前端在锚点
句切背景（routers `_resolve_scene` 注入 place_bg；晚到锚点即切）。**词表可见性以
`place_palette` 舞台清单保留**（同源, 防背景单调）。详细设计：docs/archive/DESIGN_BOND_CONTRACT_V2.md
（旧契约, 已归档）；新契约的换场/词表归属见 docs/DESIGN_VN_UPGRADE.md §5。

双 registry 分流（bond_story.py:429-435）：按**动作名归属**——story 域 spec 命中 →
story parse；否则 memorial 域。parse 失败仍留本域反馈（不能按 parse 结果分流）。

---

## 4. Bond 每场消息与"AI 到底知道什么"

`send_vn_scene`（bond_story.py:352-525）：

```
# 每场统一经 round_messages（core/promptkit/tail.py, Phase 3 起——含无注记路径,
# 与旧 llm.format_messages 布局逐字节一致）
[system(盒B)] + engine._history + [P17 system_note?（约束注记, webgui/vn_cli 拼）]
              + [场 task 卡] + [user]
```

**本场 user_input 的五种真值**（webgui/bond.py:722-774）：

| 场景 | user_input | picked 落库 |
|---|---|---|
| 首场（fresh/prewarm seed） | `（旁白）本章：{title}——从刚才的对话与契机自然展开。`（L596） | — |
| 玩家裁决选项 | 分支内容**直接展示（零 LLM 调用）** | 选项文本（L748）|
| 分支播完点"继续" | `（继续）`（有 pregen → 提升零等待；否则正常生成）| None |
| 纯叙事场点"继续" | `（继续）`（pregen 链式消费）| None |
| 自由输入 | 玩家原文 | 原文（L771-772）|

**live/resume 分叉与 A1 回录（2026-09-07 Phase 4 修复）**：事件流渲染
（renderer.py:98-100）在 payload 带 picked 时输出 `（选择了: X）`；但引擎 live
历史**生成时落库**、picked 尚不存在 → 活会话续写（输入恒为"（继续）"）看不到
选择——与 resume/回放分叉（"AI 猜"的半边洞）。修复：
- `BondStoryEngine.record_picked(picked)`：引擎留存 `_last_payload`（本场动作
  payload），裁决后以 `render_bond_scene_text`（同一函数）重渲历史尾部 → live
  与 resume/wrapup 预灌**逐字节同形**（构造性成立）；
- webgui 接线：分支消费点（`_log_scene(picked=text)` 之后、`_pregenerate` 之前）；
- vn_cli 无需回录——其裁决文本（choice）即下一场 user_input，LLM 直接可见。
**branches 内容仍不进上下文**（A1 定稿；A2 叙事化留档，见 DESIGN_PROMPTKIT §5.4）。

**每场动态注记 P17** = webgui `_system_note(state)` 聚合器（webgui/bond.py:1138-1179），
多条聚合一行一条（None = 不注入）：
- 纪念模式中：强制只许 `memorial_exit` + 补喂 exit 域 schema（L1142-1147）
- 选项配额：已用 ≥3 → 后续一律省略 choices；已用 1~2 → 提醒少给、报剩余
- 上一场 ≥3 单元且 emotion 全同 → 提醒情绪变化、切新单元
- `round == _REMIND_ROUNDS` → 建议向结尾收束（中段提示，不匆匆）
- `round == _END_ROUNDS` → 强制本轮 story_end 收尾

**场 task 卡（目标层, Phase 3 2026-09-07 启用）** = 约束注记之后、user 之前末位：
- 常规场：`task_bond.md`（scene——推进当前板块, 引擎默认）
- 纪念模式中：`task_bond_memorial_exit.md`（memorial_exit——引擎 `_scene_task_kind()`
  自推, 与 P17 的 exit schema 注记互补不重复）
- 开关与 MMT 同源（settings [promptkit].task_card）; vn_cli/webgui/预生成同源（引擎级）。

**失败路径**：引擎内 feedback 回灌自纠错 ×3（MAX_SCENE_RETRIES）→ 仍败抛
SceneLoopError；webgui 侧连续 3 次失败（MAX_GEN_FAILURES）→ closing 强制收场。
**两遍式标注**：webgui 生成时 annotate=False（骨架先显示），标注 worker 异步补
emotion → emo_version++（引擎同步标注仅 CLI/测试用）。**导演层**：骨架返回前
`director.visual_for(place)` 定 background（L519-524）。

---

## 5. 异步/周边调用点

| 调用 | 时刻 | 输入 | prompt 源 |
|---|---|---|---|
| 情绪标注 | 每场骨架入队后（webgui 单 worker 串行） | 段落文本 + 词表 + 人设摘要 | `emotion_annotate.md` 两变体（emotion_annotate.py:80 批量 / :183 smart），`{lexicon}`/`{sentences}` 占位替换，注入 `_character_hint`（personality 摘要 = 人设化判断基准，逞强笑 ≠ smile）|
| 收尾轮 wrapup | finish 后（完整/中断两文案） | 事件流窗口预灌 `engine._history`（exclude_abandoned + window_messages）+ system_note 话术 | 程序话术（webgui/bond.py:1182-1256）：completed 话术 / 中断话术明示"只进行到一半、不总结未发生剧情"；兜底话术本地预设；`record_input=False` 不落假 player 事件 |
| digest | bond 闭环 completed=True 后 / MMT 每 25 轮（剧情中不触发） | wiki_v2 digest_segment：Round A 记录 + Round B 组织，锚点 = personality+knowledge 人设摘要，好感结算写 affection 事件（幂等键 interact_max） | `digest_v2_round_a.md` / `digest_v2_round_b.md`（wiki_v2）|
| 记忆浮现 memory_flash | 仅 vn_cli bond 开场（25%，冷却无意义） | wiki_v2 `random_flash_segment` 随机摘 1 段 episode | 程序话术（events.py:22-36）——⚠️ **webgui 不触发**，两入口行为不一致 |

---

## 6. 旧文档（DESIGN_WEBGUI_PROMPTS.md）勘误总表

| # | 旧表述 | 现网事实 |
|---|---|---|
| 1 | MMT 输出 `{"actions":[...]}` | 2026-09-02 **消息流协议** `{"messages":[{text}/{action}]}`；schema 段/rules 书已同步 |
| 2 | "SIG~ 键双重出现" | 实为盒A dump 含 script.yml 全量 → tone 内容以 yaml 键值出现 + 专段再注；且 **bond_tone 也在盒A dump 出现一次**（无专段）；yaml_to_prompt 实际剥前缀显示 |
| 3 | P15 记忆注入描述 | 已解耦为出厂背景直注 + wiki 两段（2026-09-05）；MMT 每轮拼 system 尾；Bond 由调用方构造注入、剧情内固定 |
| 4 | P17 "MMT 每轮 + Bond 每场" | MMT 主聊天轮恒不传（仅收尾轮）；Bond 聚合器含选项配额/表情单调等新条目 |
| 5 | P18 仅 MMT 随机事件 | 新增 memory_flash 25%，但**只在 vn_cli**（webgui = 0）|
| 6 | P19/表情标注 | emotion 已内联 paragraphs（rules 明写"不要写 emotion，写了会被忽略"）；标注 = 批量/smart 两变体 + character_hint 判断基准 |
| 7 | P20 digest 唯一触发 = bond 闭环 | 双触发（+ MMT 25 轮）；主链 wiki_v2 两轮制；digest.md v1 退役 |
| 8 | wrapup 注入起因便签 | reason 便签退役（2026-09-05），改事件流窗口预灌 + title 兜底；中断分支"不脑补 + 不 digest" |
| 9 | 行号锚点 / webgui 结构 | 行号全漂；webgui 已拆 `routers/`；bond.py 现 1256 行 |

---

## 7. 对 task 卡片（"本回合任务"）的推论——现网装配落点

审计结论：**所有域确实"只有规则书、无本回合任务"**——LLM 每轮只知道长期规则，
不知道"这一回合我的目标是什么"。

插入槽位（两处代码注释已暗示"最近位置最醒目"的设计意图）：
- **MMT**：P16/P17/P18 之后、user 之前（momotalk.py:616 前）。
- **Bond**：与 `_system_note` 同一槽位（history 之后、user 之前）。

装配原则（promptkit 重构必须守住）：
1. system + history 前缀**逐字节稳定**（DeepSeek 上下文缓存）；
2. 卡片 ≤ ~60-100 token，只点目标不重复规则（规则书已在 system 内）；
3. **放引擎层**（CLI / vn_cli / 预生成 / bench 与 webgui 同源），webgui `_system_note`
   归并为引擎注记体系中的一类——当前它是 webgui 层概念，引擎层无卡片。

---

## 8. 代码锚点（2026-09-07 实况）

| 位置 | 说明 |
|---|---|
| `core/promptkit/box.py` | 盒装配（DOMAIN_BOXES["mmt"] 9 块清单, 盒A v2 称呼行首段） |
| `core/promptkit/blocks.py` | 命名块实现（文案单一装配源） |
| `core/promptkit/tail.py` | round_messages（每轮动态尾唯一入口） |
| `core/momotalk.py:299-322` | start_session → build_box("mmt")（盒A v2） |
| `core/momotalk.py:543-595` | agent_turn（每轮尾 → round_messages: brain/P16/P17/P18/user） |
| `core/momotalk.py:403-453` | _inject_brain（出厂背景 + wiki 注入段） |
| `core/momotalk.py:492-512` | _maybe_mmt_digest（25 轮窗口） |
| `core/momotalk.py:930-951` | _bond_progress_note（P16 文案） |
| `core/momotalk.py:129-156` | load_brain_segment（Bond 开场注入段共用） |
| `core/bond/bond_story.py:298-339` | start_session → build_box("bond")（盒B v2） |
| `core/bond/bond_story.py:341-537` | send_vn_scene（每场尾 → round_messages; 双 registry + 状态机 + 骨架 + 历史） |
| `core/bond/bond_story.py:564-569` | _scene_task_kind（场卡 kind 自推: memorial_exit/scene） |
| `core/promptkit/box.py` | DOMAIN_BOXES（mmt 9 块 / bond 10 块） |
| `core/promptkit/blocks.py:110-141` | Bond 域块（persona_bond/bond_tone/rules_bond/lexicon_*/brain） |
| `llm/prompts/task_bond.md` / `task_bond_memorial_exit.md` | Bond 场卡模板（scene / memorial_exit） |
| `core/bond/bond_story.py:429-435` | 双 registry 按动作名分流 |
| `core/parsing/dynamic_character_parser.py:386-417` | build_prompt 三模式 |
| `core/parsing/dynamic_character_parser.py:259-326` | yaml_to_prompt（剥前缀渲染） |
| `core/parsing/world_parser.py:70-89` | world_to_prompt（【世界常识】【世界规则】） |
| `contract/schema.py:34-92` | build_schema（消息流/单动作两形态） |
| `core/media/emotion_lexicon.py:95-135` | 表情/地点词表注入文本 |
| `core/random_events/events.py` | want_to_speak / memory_flash 定义 |
| `webgui/bond.py:401-406, 542-548` | Bond 引擎构造（brain_segment） |
| `webgui/bond.py:722-774` | turn 消费（分支直显 / 继续 / pregen 提升） |
| `webgui/bond.py:1138-1179` | _system_note 聚合器（P17 内容源） |
| `webgui/bond.py:1182-1256` | _wrapup（收尾话术 + digest 触发） |
| `webgui/chat.py:148-189` | MMT worker（agent_turn + prewarm 挂钩） |
