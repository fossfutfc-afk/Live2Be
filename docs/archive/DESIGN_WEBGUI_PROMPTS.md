# DESIGN_WEBGUI_PROMPTS — webgui 主循环总图：prompt 类型与注入时刻

> ⚠️ **已归档（2026-09-07）**：本文描写的注入结构大体仍成立，但存在多处
> 实质过期（消息流协议、digest 双触发、brain 解耦、wrapup reason 退役等——
> 完整勘误见新文档）。新基准 = **docs/PROMPT_INJECTION_MAP.md**（对照现网
> 代码逐点校准版）。本文留作历史/设计意图参考。

> 以 `igusa_haruka`（伊草 遥香）为例。总览 webgui（`webgui/`）从打开会话到
> 羁绊剧情闭环的全流程，标注**每个 prompt 的类型、来源、注入时刻**。
> 配套代码：`core/parsing/dynamic_character_parser.py` / `core/momotalk.py` /
> `core/bond/bond_story.py` / `webgui/chat.py` / `webgui/bond.py`。

---

## 0. 关键确认：盒A 与 盒B 的角色人设层数

`DynamicCharacter.build_prompt(mode)`（`core/parsing/dynamic_character_parser.py:386`）：

| 模式 | 注入的人设内容 | 层数 |
|---|---|---|
| `momotalk`（盒A） | `yaml_to_prompt(self.raw)` — **6 文件全量合并**（profile/personality/knowledge/experience/typical/script） | **全量** |
| `bond_story`（盒B） | `{**self.profile, **self.personality}` | **仅两层** |
| `trigger` | profile + brief_traits 摘要 | 最简 |

**结论：盒B 是"仅 profile+personality"两层，不是全量。** knowledge（专属知识）、
experience（预设经历）、typical（校准样本）、script（扮演手册）不进 Bond 的
角色设定段；但 script 的 `SIG~main_tone`（→【本角色剧情基调】）与
`SIG~bond_tone`（→【本角色羁绊剧情建议】）会由引擎单独注入（见盒B P4/P6）。
注意细节：MMT 的 `raw` 合并含 script.yml 的 `SIG~*` 键——它们会同时出现在
盒A 的"角色设定"全量转储里，又被 P4/P5 以专属段落再注入一次（双重出现，
属既有行为）。

---

## 1. 主循环总图

```
════════════════════════════════════════════════════════════════════════════
         Live2Be webgui 主循环总图 —— igusa_haruka（伊草 遥香）
         注: 盒A/盒B = 会话级拼装一次、每轮复用; 数字①~⑥ = LLM 调用点
════════════════════════════════════════════════════════════════════════════

【阶段0】打开会话  GET /api/mmt/session?char_id=igusa_haruka
   │
   ├─ 有进行中会话 → resume_session（重建 system + P15 注入已有 wiki + 事件流→history 40轮窗口）
   └─ 新世界线 → start_session + attach_session
         │
         ▼
   ┌─ 盒A  MMT system prompt（会话级一次, 之后每轮原样复用）────────────────┐
   │ P1  角色设定: yaml_to_prompt(六文件全量 raw) + P2 behavior_rules      │
   │ P3  【世界常識】【世界規則】: overview.yml (common+system 档)          │
   │ P4  【本角色剧情基调】: script.yml SIG~main_tone                     │
   │     （遥香: 日常向&照顾向…凝华…"这是绝对memorial的时刻"）              │
   │ P5  【本角色 MMT 风格】: script.yml SIG~mmt_tone（报答/打错字/道谢/否定）│
   │ P7  【人际层】: interperson.json 自表（便利屋68 三人权重2）            │
   │ P8  momotalk_environment.md                                        │
   │ P9  momotalk_rules.md（契机导向触发规则）                            │
   │ P10 可用动作 schema: build_schema(mmt_registry, action_list=True)  │
   └────────────────────────────────────────────────────────────────────┘
         │
【阶段1】MMT 每轮循环 ──────────────────────────────────────────────────
   玩家消息 → POST /api/mmt/chat → 输入队列 → worker（per-char 锁串行）
         │
         ▼
   messages = [system 盒A] + history(≤80条)
            + [P16 羁绊进度注记] + [P17 system_note?] + [P18 随机事件?] + [user]
         │
         ▼
   ① LLM json_object ─────────────► mmt 域契约: {"actions":[...]}
         │  mmt_chat / mmt_send_media / mmt_inspect_character(静默轮)
         │  / mmt_trigger_bond_story(独占轮)
         ▼
   结构约束(trigger 必须独占) → 全量 registry.parse(原子, 任一无效整列表回灌)
   → MmtExecutor.execute → 事件流落库(每动作一条)
         │
         ▼
   前端 pollLoop(1s) → render_chat_events 切块气泡（"正在输入…"节奏）
         │
         ▼ 触发轮: mmt_trigger_bond_story{reason:"想报答老师…"}
   粉色横幅（点击才进入）───────────────────────────────►
                                                         │
【阶段2】Bond 开场  POST /api/bond/start ◄────────────────┘
   │ reason = _trigger_reason(引擎 trace 里触发动作的 payload.reason)
   │ vn_enter marker → seed = "（旁白）基于「reason」……" → 后台 _generate
   ▼
   ┌─ 盒B  Bond system prompt（bond 会话级一次, 每场复用）────────────────┐
   │ P1' 角色设定: 仅 profile+personality（见 §0 确认）+ P2 behavior_rules│
   │ P3  世界观 + P4 剧情基调（与盒A同源, 重新注入）                       │
   │ P6  【本角色羁绊剧情建议】: script.yml SIG~bond_tone                │
   │     （遥香: 照顾杂草/吃甜品/想送东西结果搞砸, 结局老师安慰）           │
   │ P11 bond_story_rules.md                                           │
   │ P12 story 契约 schema（story_scene/story_end）                     │
   │ P13 【表情标注词表】: emotions.yml 14键+行尾 few-shot 注释           │
   │ P14 【地点标注词表】: _director_whitelist.json common_scenes        │
   │ P15 记忆段: brain wiki 第一人称注入                                  │
   └────────────────────────────────────────────────────────────────────┘
         │
【阶段3】Bond 场景循环 ─────────────────────────────────────────────────
   waitScene 轮询(700ms) GET /api/bond/status（round去重 / emo_version / memorial 同步）
         │
         ▼
   ② send_vn_scene(user_input, system_note=P17, annotate=False,
   │     on_memorial_prompt=嗅探回调)
   │  messages = [system 盒B] + history + [P17 系统注记] + [user]
   │     │                        ▲ P17 动态拼装: 纪念exit schema / 选项配额2~3
   │     │                        │    / 表情单一提醒 / 30·50轮收尾提醒
   │     ▼ chat_full 流式（token 逐块到）
   │  MemorialProbe 嗅探: "action":"memorial_enter" 确认 → "prompt" 引号闭合
   │     │ └─► 异步生图线程（图片API, 非LLM）→ gallery 落盘 ──► 前端静默淡入
   │     ▼
   │  story 域(story_scene/story_end) / memorial 域(enter/exit) 双registry
   │  → 纪念状态机约束(enter独占/至多1次) → StoryExecutor.execute
   │  → BondScene.from_action（骨架, 段落无 emotion 负担）
   │     │
   │     ├─► P19 异步标注入队 → 单worker串行: emotion_annotate.md 批量分类
   │     │      （对象身份检查写回 + emo_version++ ──► 前端补切已显示段落表情）
   │     └─► director.visual_for(scene.place) → background（place意图→背景查库）
   │     ▼
   前端渲染（背景/立绘spine/打字机/选项）→ 玩家裁决 → POST /api/bond/turn
   │   ├─ 分支消费: 选项branches 立即展示（零等待）→ 预生成下一场
   │   ├─ "（继续）"+ pregen 就绪: 提升预生成场景（零等待）→ 链式预生成
   │   └─ 正常: 补录当前场事件(带picked) → _generate 下一场
   ▼
   场景 is_end ──►【阶段4】POST /api/bond/finish
   │  补录最后一场(picked=None) + vn_exit{completed} + session_end
   │  ├─► ④ wrapup 线程: agent_turn("（自动收尾）", system_note=收尾话,
   │  │     record_input=False) → mmt 域契约（只许 mmt_chat）→ 前端拉收尾气泡
   │  │     （completed=False 中断退出: 话术明示"只进行到一半", 不 digest）
   │  └─► ⑤ async_digest 线程（仅 completed=True, digest 唯一触发点）
   │        digest_session: digest.md + build_digest_schema()
   │        输入: 新增时间线 + 视觉记忆 + 联想回忆 + 双通道随机摘段
   │              + 人设锚点 + 已有 summary
   │        └─► facts/beliefs/relations 增量合并 + affection_exp_delta 事件
   │             + wiki 落盘（digested_seq 水位）
   ▼
   回 MMT: 前端 resumePolling, 事件流自然续接（wrapup 气泡已入列）
════════════════════════════════════════════════════════════════════════════
```

---

## 2. LLM 调用点一览（①~⑥，各用哪套契约）

| 调用点 | 时刻 | 输出形式 | 契约 |
|---|---|---|---|
| ① MMT 每轮 | 玩家每条消息 | json_object 动作**列表** | **mmt 域**（mmt_chat/send_media/inspect_character/trigger_bond_story） |
| ② Bond 每场 | 每场景（含预生成） | json_object **单动作**，流式传输 | **story 域** story_scene/story_end ＋ **memorial 域** enter/exit（按动作名分流） |
| ③ 纪念生图 | ②流式中途（prompt 定稿即触发） | 图片 API（不是 LLM） | — |
| ④ wrapup 收尾 | finish 后 | json_object 动作列表 | **mmt 域**（注记强制只许 mmt_chat） |
| ⑤ digest 提炼 | 仅完整剧情闭环后 | json_object | **digest 契约**（build_digest_schema 渲染进 digest.md） |
| ⑥ 情绪标注 | 每场骨架入队后（异步） | **text 模式**纯 JSON 数组 | **无契约**——词表成员集合校验，失败延续兜底 |

---

## 3. Prompt 注入时刻总表（Haruka 实例）

| # | Prompt 类型 | 来源 | Haruka 具体内容 | 注入时刻 | 档位 |
|---|---|---|---|---|---|
| P1 | 角色卡 L1~L6 | `config/characters/igusa_haruka/{profile,personality,knowledge,experience,typical,script}.yml` | 六文件全量合并 raw（build_prompt("momotalk")） | start_session/resume | 会话级 |
| P2 | 行为规则 | `llm/prompts/behavior_rules.md` | 模块导入时加载（parser:421），随 P1 拼接 | 同上（Bond 也注） | 会话级 |
| P3 | 世界观 | `settings/world/overview.yml` common+system | 基沃托斯常识 + 恋爱合法/暴力叫停 | 同上（Bond 也注） | 会话级 |
| P4 | 剧情基调 | `script.yml SIG~main_tone` | 日常向&照顾向…凝华…memorial 时刻 | 同上（Bond 也注） | 会话级 |
| P5 | MMT 风格 | `script.yml SIG~mmt_tone` | 报答/打错字/习惯性道谢道歉/说完就否定 | 仅 MMT 会话级 | 会话级 |
| P6 | 羁绊剧情建议 | `script.yml SIG~bond_tone` | 杂草/甜品/搞砸结局→老师安慰 | 仅 Bond 会话级 | 会话级 |
| P7 | 人际层 | `interperson.json` 自表条目 | 便利屋68 权重2 | 仅 MMT 会话级 | 会话级 |
| P8 | MMT 环境 | `momotalk_environment.md` | 虚拟手机场景 | 仅 MMT 会话级 | 会话级 |
| P9 | MMT 规则 | `momotalk_rules.md` | 契机导向触发规则（偶遇/同行即展开） | 仅 MMT 会话级 | 会话级 |
| P10 | MMT 契约 schema | `contract` mmt_registry → `build_schema(action_list=True)` | 四个动作的字段约束 | 仅 MMT 会话级 | 会话级 |
| P11 | Bond 规则 | `bond_story_rules.md` | VN 行为规则（段落/收尾/选项收敛） | 仅 Bond 会话级 | 会话级 |
| P12 | Bond 契约 schema | story + memorial registry → `build_schema` | story_scene/story_end；memorial_enter/exit | Bond 会话级 + **纪念模式内每轮**经 system_note 重喂 exit schema | 会话级+每轮 |
| P13 | 表情词表 | `assets/illustration/igusa_haruka/default/emotions.yml` | 14 键 + 行尾注释 few-shot（outburst=失控灵魂表情…） | Bond 开场喂一遍；**标注调用时复用同文本作 lexicon_hint** | 会话级/异步 |
| P14 | 地点词表 | `assets/_director_whitelist.json` common_scenes | 封闭地点语义列表 | Bond 开场 | 会话级 |
| P15 | 记忆注入 | 本世界线 wiki（`data/.../brain/wiki.json`） | 第一人称"我记得…" | resume 时（只注入不消化）；Bond 开场作 brain_segment | 会话级 |
| P16 | 羁绊进度注记 | `bond_progress` 轮数 | "已累计 N 轮, ≥5 建议触发, 仅供参考" | 每轮消息尾部（不入历史） | 每轮 |
| P17 | 系统注记 | 程序动态拼装 | 纪念 exit schema / 选项配额 2~3 / 表情单一提醒 / 30·50 轮收尾提醒 / wrapup 收尾话 | MMT 每轮（可选）、Bond 每场、finish 后收尾轮 | 每轮 |
| P18 | 随机事件 | `core/random_events.py` | 低频"角色想说话"惊喜 | MMT 每轮概率触发（冷却） | 每轮 |
| P19 | 标注 prompt | `emotion_annotate.md`（`{lexicon}`/`{sentences}` 占位） | "这是独立标注任务…只选词表内键" | 每场骨架入队后异步（单 worker 串行） | 异步 |
| P20 | digest prompt | `digest.md` + `build_digest_schema()` | 提炼 facts/beliefs/relations/summary + 好感 delta | bond 闭环后后台一次（增量幂等） | 异步 |
| P21 | wrapup 注记 | 程序话术 | "以遥香身份回几句收尾…只许 mmt_chat" | finish 后独立 agent_turn 轮 | 异步 |

**三档注入时刻**：
- **会话级一次**（P1~P15）：进角色时拼死，MMT/Bond 各一个固定 system prompt 盒，每轮/每场复用
- **每轮动态**（P16~P18）：追加在 messages 尾部（system 角色），只进 LLM context 不进历史
- **异步独立调用**（P19/P20，P21 算独立一轮）：完全不占玩家等待路径——标注串行队列、digest 闭环后后台

---

## 4. 代码锚点（核对用）

| 位置 | 说明 |
|---|---|
| `core/parsing/dynamic_character_parser.py:386` | `build_prompt` 三模式（momotalk 全量 / bond 两层 / trigger 最简） |
| `core/parsing/dynamic_character_parser.py:333` | `_CHARACTER_FILES` 六文件（含 script.yml） |
| `core/parsing/dynamic_character_parser.py:421` | behavior_rules 模块级加载 |
| `core/momotalk.py:203-247` | 盒A 拼装顺序（环境/规则/schema） |
| `core/momotalk.py:378-489` | agent_turn 动作列表循环（结构约束→全量 parse→执行） |
| `core/bond/bond_story.py:269-323` | 盒B 拼装顺序（词表/地点/brain） |
| `core/bond/bond_story.py:329-491` | send_vn_scene（双 registry + 纪念状态机 + 骨架） |
| `core/bond/emotion_annotate.py:47` | annotate_emotions（text 模式标注调用） |
| `core/brain/consolidation.py:59` | digest_session（增量 + 联想 + 好感结算） |
| `webgui/chat.py:125-176` | 聊天队列 worker（MMT 后台线程） |
| `webgui/bond.py:233` / `454` / `561` / `651` / `695` | bond_start / _generate / _enqueue_annotate / _system_note / _wrapup |
| `core/bond/stream_probe.py:81` | MemorialProbe 流式嗅探 |
| `core/media/emotion_lexicon.py:39/95/130` | 词表加载 / 表情注入文本 / 地点注入文本 |
