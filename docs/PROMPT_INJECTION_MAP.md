# PROMPT_INJECTION_MAP — 提示词注入地图（现网校准版）

> **状态**：2026-09-07 对照现网代码逐点校准（行号为当日实况）；**2026-09-10 盒B
> 段落已按记录流 v2 更新**（rules/输出契约/词表/舞台清单四处，见 §3；真机守形验证
> 随 P0-4b 引擎接线）。
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
| 7 | MMT 规则 | `rules_mmt` 块 = `momotalk_rules.md` | 单人模式、语气/内容示范（**风格**）、契机导向触发规则；⚠️ **形状不在这里**（⑥-2e 拆分：形状只在下一行的契约块） |
| 8 | 本轮输出契约 | `schema` 块 = **`build_line_schema(mmt_registry)`**（`contract/schema.py`）| ⚠️ **行流契约**（⑥-2e）：一行一条 JSON——`{"text": …}` 消息行 / `{"action": …, "payload": {…}}` 操作行 + 6 条硬规则 + **动作表（运行时渲染）** + 3 条示范 |

---

## 2. MMT 每轮动态尾（agent_turn，只进 context 不入历史）

`core/momotalk.py:543-600` → `round_messages`（core/promptkit/tail.py）：

```
system   = 盒A + "\n\n" + brain 注入段（_brain_injection）
messages = [system] + history + [P16 羁绊进度注记] + [P17 时间注记们]
         + [P19 你想起的事?] + [P17 system_note?]
         + [P18 随机事件?] + [task 卡] + [user 原文]
```

| # | 块 | 内容 |
|---|---|---|
| P15 | brain 段 | 拼在 system 内容**尾部、每轮现拼**：出厂背景（experience.yml 原文直注 `render_background_experience`，2026-09-05 解耦后不进 wiki）+ wiki 视图 `render_character_view`（"我记得…"第一人称，facts/beliefs/relations）。digest 后台完成后**下轮**原子替换（momotalk.py:403-453, 598-601）。⭐ **2026-09-29（N5）起 episode 行带元信息段**: `〔《事件名》｜3 周前｜9/20｜难忘〕正文（「原话」）` —— 形状与括号清单见 ⭐ **`docs/CONTEXT_MARKS.md`** |
| history | 活会话 | 40 轮 × 2 条截断 `_trim_history`（momotalk.py:953-956）；resume 恢复 = `window_messages(exclude_abandoned(events), rounds×3)`（120 单元，momotalk.py:546-549） |
| ⛔ P16 | ~~羁绊进度注记~~ **已封印**（2026-10-08 用户裁决"封印一下/删除"） | ~~`_bond_progress_note()`：`【剧情时机】距上次完整剧情 ≥6 轮→铺垫足够可发起` / `<6 → 报事实+沉淀`，每次 agent_turn 都注入~~ ⇒ **封印后 `_bond_progress_note()` 恒返回空串**（`round_messages` 跳过空串 ⇒ 注入面零字节）。**为什么删**: 那是"**依据轮次催她主动发起 VN 邀约**"的唯一路径; 触发时机从此只由规则书 §【羁绊剧情触发】的**契机判据** + LLM 判断决定（执行侧本来就零闸门）。**连带**: `momotalk_rules.md` 里那句"还是要看当前 mmt 进行了几轮"也删了（轮次依据清零）; `_bond_gap` / `BondProgress.rounds()` 计数器**留着但已无读者**（别当活旋钮）。守门 = `tests/core/test_mmt_trigger_note_sealed.py`（把 gap 拉到 6 也不许出现那两种文案; 变异验过能红） |
| P17 | 时间注记 + system_note | 时间三行（`core/worldtime`，2026-09-17 起唯一时间口径）；system_note 是引擎可选参数——现网主聊天路径恒 None，**只有收尾轮传**（wrapup 话术） |
| ⭐ **P19** | **你想起的事**（**N5a, 2026-09-29**；⭐ **2026-10-08 改走 `like(spec="turn")`，该档 `semantic` 权重 0 —— 实时路径不吃后端的全库重编码**） | `_recall_note()` → `like(RecallCtx(now, query=玩家这一句[:200]), spec="turn")` → `render_recall_block`：**每轮召回的 1~2 条旧 episode**（五路打分: 字面 / 语义 / 结构一跳 / 时间 / 重要；`turn` 档只调**不吃后端**的那四路），行 = `〔《事件名》｜5 天前｜9/26｜难忘〕正文（「原话」）`，**末尾还有一句动作提示**（N5b: `RECALL_ACTION_HINT` —— 真机实测"动作只写在规则书里会漏报"，必须贴着候选）。⚠️ **不许拼进 system**（每轮都变 ⇒ 破前缀缓存）；⚠️ 事件名**不过 `_me`**（它是地址，她要原样抄进 `{"noticed": …}`）。空/无命中 ⇒ 不注。台账两行: `mmt_recall … spec=turn titles=…`（摆了谁）+ `recall_like … top=…←why`（凭什么）。括号清单见 `docs/CONTEXT_MARKS.md` |
| P18 | 随机事件 | `want_to_speak`（12%，冷却 6 轮，core/random_events/events.py:56-63）："你现在有点想和老师说点别的…" soft 倾向。仅 store 会话触发 |
| task 卡 | 本回合任务（目标层） | `task_mmt.md`（chat，引擎默认）/ `task_mmt_wrapup.md`（收尾轮，调用方传 task_kind="wrapup"）；{char} 占位；开关 settings [promptkit].task_card（默认 true，关闭 = 无卡旧行为）；模板缺失静默跳过。**Phase 2（2026-09-07）启用**——卡 = 末位注记（约束注记之后、user 之前，离生成最近）|

**输出历史格式**（momotalk.py:849-862）：user 原文原样入历史；assistant 按
`[动作名] `前缀 + 去括号切块，仅首块带动作名前缀。

**周边异步事实（旧文档未记）**：
- digest 已**双触发**：① bond 剧情闭环后（webgui `_wrapup` completed=True）；② MMT 会话每
  N=25 轮（`_maybe_mmt_digest` momotalk.py:492-512，in_vn/in_memorial 中不触发）。
  主链 = brain `digest_segment`（digest_record.md / digest_relate.md 两轮 + 好感结算，momotalk.py:75）；
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
| 5 | 羁绊剧情规则书 | `rules_bond` 块 = `bond_story_rules.md`（**`{char_id}`/`{char_name}` 按会话替换**） | **记录流 v2（2026-09-10）**：七节结构（视角/节奏/记录写法/群与密度/换场/纪念预告/收尾）；**台词写纯文本（不包「」）**；范例说话人 = 真实 id；**不写"不要写 X 字段"式提醒**（决策 #24）。**PL2（2026-09-19）**：原 §七「收尾与收尾组合」的四种组合与 §八「范本」**搬去 `bond_shots`** —— 规则书只留硬规则, 手法归手法 |
| 6 | **`【镜头与手法】`** | `bond_shots` 块 = `bond_shots.md`（PL2, 2026-09-19; `{char_id}`/`{char_name}` 同手替换）| **把"怎么写更好看"从规则书里搬出来**：① 镜头词（星空/夜空/黄昏/黄昏云彩/蓝天白云/流星雨/繁星夜空/纯黑）② switch 组合拳（开场/换气/空镜收束/同地点不换）③ 煽情场景写法 ④ 收尾几种收法 ⑤ 范本。**都是可选手法, 不是硬要求**。⚠️ 镜头词是**刻意给 writer 的例外** —— *"这些词能让 LLM 更好的写作"*（与"零内容词表"不矛盾: 那条打的是 168 条资产菜单会框死 writer）。⚠️ 那一行镜头词**必须在层1 唯一命中**（0 调用; 层1 是"最长别名子串"匹配, 不必逐字相等——`海边夜空` 靠别名 `夜空` 命中）——`tests/core/test_bond_shots.py` 钉着（作者 2026-09-19 审稿时加了 `海边夜空`/`海边黄昏`, 两个都唯一命中 `view_sky`） |
| 7 | 本轮输出契约（VN 记录流） | `schema` 块 = **`build_record_schema(char_id=…, char_display=…)`**（contract/schema.py；bond_story.py start_session）| **v2**：标题由 `BlockContext.schema_title` 换掉「可用动作 schema」（story 域无 action 外壳）；内容 = 七种取值 + 硬规则六条 + few-shot（**随会话渲染真实角色 id**）；`end` 明示"收尾字段、不是老师的话、可留空"；不再用 `build_schema(story registry)`（memorial exit schema 仍走 registry，纪念模式注记补喂） |
| 8 | `【世界区域】` | `place_world` 块 = `regions.yml` 21 条 `zh` 主名（`core/parsing/place_regions.py`）| **2026-09-15（T16）取代 `place_palette`**：用户裁决"**主 LLM 零内容词表**"——资产 slug 菜单会**框死** writer（"为了用上拉面店而写一场拉面店"）；而**世界区域是设定不是菜单**（`overview.yml` 里一个学院名都没有, writer 会凭空发明）。判据 = "多给 writer 一个手段"还是"少给 writer 一个自由"。**"换场"这个能力由 `rules_bond` §五【换场】承担**（何时发/怎么发/同地点小动作不换场 + 三条示例）, 不需要菜单 |
| 9 | brain 段 | `brain` 块 = `load_brain_segment`（momotalk.py:129-156）：出厂背景 + wiki 视图 | webgui 每次 start/replay 都重取（webgui/bond.py:401-406, 542-548）→ **剧情内固定**不随 digest 更新（条件块） |

> **`lexicon_emotion` 已退出盒B**（2026-09-10 决策 #24⑤）：记录流 v2 里 emotion 由标注层
> **逐记录**判定（词表在标注层 prompt 里），writer 不写情绪 → 该块对创作无作用，且其
> "你不用写 emotion"式提醒属白熊效应。盒B 由 10 块降为 9 块（块实现保留在
> `blocks.BLOCKS`，供标注层/测试复用）。
> **PL2（2026-09-19）后盒B = 10 块**（加 `bond_shots`）。

**地点归属换代（2026-09-10 记录流 v2 / 2026-09-15 T16）**：主 LLM **发 `stage:switch`**
（WHEN 归它，自然语言地点），**不再有任何地点字段**；翻译成资产键是标注层的事
（WHICH；P1 待接）。旧 v2 单源切换（"换场即换段"、place lane 从正文判锚点）在
记录流里退役——history 只回显 writer 自己写的地点话，词表键永不回灌。

**盒B 至此已无任何词表块**（`lexicon_emotion` 2026-09-10 退出、`place_palette`
2026-09-15 换成世界设定块）：情绪归标注层逐记录判、地点归标注层翻译，
writer 只写自然语言。旧契约见 docs/archive/DESIGN_BOND_CONTRACT_V2.md；
新契约见 docs/DESIGN_STREAM_CONTRACT.md §5 与 docs/DESIGN_PLACE.md（三层框架）。

双 registry 分流（bond_story.py:429-435）：按**动作名归属**——story 域 spec 命中 →
story parse；否则 memorial 域。parse 失败仍留本域反馈（不能按 parse 结果分流）。
**记录流 v2 后**：story 域每场不再走 registry.parse（改 `parse_stream` 行解析，
P0-4b 落地）；registry 分流此时只剩 memorial exit 路径。

---

## 4. Bond 每场消息与"AI 到底知道什么"

`send_vn_scene`（bond_story.py:352-525）：

```
# 每场统一经 round_messages（core/promptkit/tail.py, Phase 3 起——含无注记路径,
# 与旧 llm.format_messages 布局逐字节一致）
[system(盒B)] + engine._history + [P17 system_note?（约束注记, webgui/vn_cli 拼）]
              + [场 task 卡] + [user]
```

**记录流 v2（P0-4b, 2026-09-10）对"每场"的改动**：
- **`response_format` = `text`**（记录流是 JSONL 多行多条；`json_object` 是"整回复单
  对象"且客户端会 `json.loads` 成 dict → 被误判成旧动作分支）。纪念子模式仍 `json_object`。
- 引擎把字符串输出解析成 `VnBlock` → **派生板**（换场/槽前切）→ 首板本次返回，
  其余进**待发板队列**（后续同形调用 **0 LLM** 直接发，`trace.action=record_stream/pending`）。
- `engine._history` 里每板一条 assistant 文本 = `render_bond_scene_text(板 payload)`
  （**唯一渲染源**: 未选候选不进; `switch` 按 §4 回显 writer 自己写的地点话;
  `art`/`exit` 跳过; 裁决物化为 `老师：X`）。
- 板 payload = `{records, paragraphs(派生, 带 speaker), choices(派生), is_end, place_hint?, art_hint?, memorial?}`
  —— `records` 是唯一真源，派生字段是给**尚未迁移的消费者**的过渡面（§11 P0-7）。
- **输入形态唯一**（P0-7c 定稿）: 记录流字符串——旧动作 JSON 一律打回重发;
  兼容开关与旧动作输入路径**已删除**（决策 #27）; story 域动作集模块留在库内但
  主链不可达（旧档回放由 `render_bond_scene_text` 旧分支承担, 冻结不改）。
- **换场翻译**（P0-7a）: 板带 `place_hint`（`switch` 记录文本）时，place lane 调
  `resolve_place`（prompt `place_resolve.md` + `place` 档位 = off-thinking/256）→
  `scene.place` = 词表键 → 导演查表出 `background_url`；进程内缓存（同句 0 调用），
  失败/词表外 → `[place][SWITCH] MISS(keep)`（画面保持）。
- **说话人（P0-7a 最小形态）**: payload 段落带 `speaker`（记录取值）；**API 边界**
  （`routers/bond._resolve_scene`）注入 `speaker_name`（角色 id → display_name、
  `sensei` → 老师、旁白空）→ 前端画名字行（`.bond-speaker`）；CLI 同款经
  `simulate_vn_scene(speaker_names=)`。

**本场 user_input 的五种真值**（webgui/bond.py:722-774）：

| 场景 | user_input | picked 落库 |
|---|---|---|
| 首场（fresh/prewarm seed） | `（旁白）本章：{title}——从刚才的对话与契机自然展开。`（L596） | — |
| 玩家裁决选项 | 分支内容**直接展示（零 LLM 调用）** | 选项文本（L748）|
| 分支播完点"继续" | `（继续）`（有 pregen → 提升零等待；否则正常生成）| None |
| 纯叙事场点"继续" | `（继续）`（pregen 链式消费）| None |
| 自由输入 | 玩家原文 | 原文（L771-772）|

**live/resume 分叉与 A1 回录（2026-09-07 Phase 4 修复；2026-09-10 记录流 v2 改为"物化"）**：
引擎 live 历史**生成时落库**、picked 尚不存在 → 活会话续写（输入恒为"（继续）"）
看不到裁决——与 resume/回放分叉（"AI 猜"的半边洞）。记录流 v2 的修法：
- **渲染唯一源** = `render_bond_scene_text(payload)`（`core/session/renderer.py`）：
  payload 带 `records` → `contract.records.render_records`（说话人取记录值: 角色真实 id /
  老师 / 旁白无前缀；**未选候选不出现**）；旧契约 payload（无 records）走原 paragraphs 提取。
- **裁决 = 物化**：`record_picked(picked)` 把 picked 并进 `_last_payload` 后重渲尾部 →
  群里多出一条 `老师：X`（**群首**，即老师原本开口处），不再写"（选择了: X）"；
  `BondScene.from_dict` 在显示层做同一件事（插回群首 + `speaker: "sensei"`）。
- 因渲染只看 payload、不看外部名字表 → **live 与 resume/wrapup 预灌逐字节同形**（构造性）；
  **显示名替换是 UI 层的事**（P0-7；历史/回放里角色用 id）。
- 未选候选与 `branches` 内容**不进任何视图/上下文**（A1 定稿；A2 已关闭）。
- 接线点不变：webgui 分支消费点（`_log_scene(picked=text)` 之后、`_pregenerate` 之前）；
  vn_cli 不调（其裁决文本即下一场 user_input）。

**每场动态注记 P17** = webgui `_system_note(state)` 聚合器（webgui/bond.py:1138-1179），
多条聚合一行一条（None = 不注入）：
- `round == _REMIND_ROUNDS` → 建议向结尾收束（中段提示，不匆匆）
- `round == _END_ROUNDS` → 强制本轮 story_end 收尾
- `round > _END_ROUNDS` → 每轮强制收尾

> **2026-09-13 校准（现网实况）**: 原列的四条里有三条**已不存在**——
> ① "纪念模式 → 强制 memorial_exit + exit schema 注记"（v1 动作已退役, 该注记
> 2026-09-12 删除, 理由见 webgui/bond.py 注释"会打回重发 → 反馈回环"）;
> ② "选项配额注记"（记录流 v2 退役——密度由 rules 引导; 计数侧 `choices_used`
> 字段 2026-09-21 一并删——只写不读）;
> ③ "上一场 emotion 全同 → 提醒切新单元"（2026-09-13 审计 B8 退役——emotion 由
> 标注层给, 写作者无该字段可写, 每轮白喂且会诱导碎化输出; `prev_emotions` 字段
> 一并删除）。现役只剩上面三条收尾节奏注记。

**场 task 卡（目标层, Phase 3 2026-09-07 启用）** = 约束注记之后、user 之前末位：
- **只有一种**: `task_bond.md`（scene——推进当前板块）
- ~~纪念模式中：`task_bond_memorial_exit.md`~~ **2026-09-13 已删除**（审计 B1）:
  v2 里纪念区间到块尾、边界由块边界结构性给出, 不存在"退出动作"; 该卡会把 v1
  已退役动作名喂给只吃记录流的引擎。`_scene_task_kind()` 现恒返回 `scene`。
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
| digest | bond 闭环 completed=True 后 / MMT 每 25 轮（剧情中不触发） | brain digest_segment：Round A 记录 + Round B 组织，锚点 = personality+knowledge 人设摘要，好感结算写 affection 事件（幂等键 interact_max） | `digest_record.md` / `digest_relate.md`（brain；2026-09-29 乙-2 改名, 2026-10-07 P1b-2 把 understand 换成 relate）|
| 记忆浮现 memory_flash | 仅 vn_cli bond 开场（25%，冷却无意义） | brain `random_flash_segment` 随机摘 1 段 episode | 程序话术（events.py:22-36）——⚠️ **webgui 不触发**，两入口行为不一致 |

---

## 6. 旧文档（DESIGN_WEBGUI_PROMPTS.md）勘误总表

| # | 旧表述 | 现网事实 |
|---|---|---|
| 1 | MMT 输出 `{"actions":[...]}` | **2026-09-25 起 = 行流契约**（`一行一条 JSON`：`{"text": …}` / `{"action": …, "payload": {…}}`）。中间形态 `{"messages":[{text}/{action}]}`（2026-09-02）**已退役**（⑥-2e/f）；schema 段/rules 书已同步。⚠️ 调用形态也跟着变：MMT 走 **`response_format="text"`**（裸文本）, 不再 `json_object`（那会触发行级解析前的 LLM JSON 自纠错） |
| 2 | "SIG~ 键双重出现" | 实为盒A dump 含 script.yml 全量 → tone 内容以 yaml 键值出现 + 专段再注；且 **bond_tone 也在盒A dump 出现一次**（无专段）；yaml_to_prompt 实际剥前缀显示 |
| 3 | P15 记忆注入描述 | 已解耦为出厂背景直注 + wiki 两段（2026-09-05）；MMT 每轮拼 system 尾；Bond 由调用方构造注入、剧情内固定 |
| 4 | P17 "MMT 每轮 + Bond 每场" | MMT 主聊天轮恒不传（仅收尾轮）；Bond 聚合器含选项配额/表情单调等新条目 |
| 5 | P18 仅 MMT 随机事件 | 新增 memory_flash 25%，但**只在 vn_cli**（webgui = 0）|
| 6 | P19/表情标注 | emotion 已内联 paragraphs（rules 明写"不要写 emotion，写了会被忽略"）；标注 = 批量/smart 两变体 + character_hint 判断基准 |
| 7 | P20 digest 唯一触发 = bond 闭环 | 双触发（+ MMT 25 轮）；主链 brain 两轮制；digest.md v1 退役 |
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
| `core/promptkit/box.py` | 盒装配（DOMAIN_BOXES["mmt"] **10** 块清单, 盒A v2 称呼行首段） |
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
| `core/bond/bond_story.py` | _scene_task_kind（场卡 kind——**v2 恒为 scene**; memorial_exit 分支 2026-09-13 退役） |
| `core/promptkit/box.py` | DOMAIN_BOXES（mmt **10** 块 / bond **10** 块——lexicon_emotion 已出盒, bond_shots PL2 进盒） |
| `core/promptkit/blocks.py:118-215` | Bond 域块（persona_bond/bond_tone/rules_bond/**bond_shots**=143/place_world/brain; `_lexicon_emotion` 已不在盒内） |
| `llm/prompts/task_bond.md` | Bond 场卡模板（**唯一**; task_bond_memorial_exit.md 2026-09-13 删除） |
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
