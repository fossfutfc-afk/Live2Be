# Live2Be 优化总览（CLAUDE_OPTIMIZE）

> 2026-08-27 建立。目的：把散落在各设计文档里的优化方向**按板块分门别类**，
> 一眼看清"已实现 / 已设计待实施 / 规划中 / 被否决"。每个方向标注状态：
> - ✅ 已实现　- 🔧 已设计（有方案, 待实施）　- 📋 规划中（有蓝图, 未细化）
> - ⛔ 被否决（及原因）
>
> 关联文档: CLAUDE.md（总纲）/ TODO.md（旧待办）/ docs/DESIGN_*.md / docs/DESIGN_*.md

---

## 一、MMT 聊天域（core/momotalk.py + webgui/chat.py + mmt.js）

**现状**: 动作列表闭环（chat/send_media/inspect/trigger_bond）✅ · 排队 + 插嘴提示 ✅ ·
气泡切块复用 CLI ✅ · 微信式失败重发/删除 ✅ · bond 入口粉色横幅 + 触发轮完整渲染 ✅ ·
输入锁定（in_vn）✅ · 轮询（1s）✅ · 每 char 独立引擎 + 并行后台任务 ✅

| 方向 | 状态 | 说明 |
|---|---|---|
| SSE 流式推送替代轮询 | 🔧 | DESIGN_MMT_CHAT.md M4——轮询 1s 延迟与重复轮询开销 |
| send_media 图片气泡渲染 | 🔧 | 设计有（MMT 只支持图片）——资源查库 → 生图管线未接 |
| 未读红点（切走记录 last_seq） | 🔧 | DESIGN_MMT_CHAT.md M2——切回补拉 |
| regenerate 单轮（"从第 N 轮重说"） | 🔧 | 已设计（撤销式: 删 history + 事件流 → 重生成）——引擎层函数未写 |
| 随机事件 want_to_speak 参数化 | 🔧 | 引擎已有钩子, 频率/内容可配置化 |
| 称呼 list 注入 rules | ✅ | character_names 参数（分饰多角预留） |

## 二、Bond Story 域（core/bond/bond_story.py + 契约）

**现状**: story_scene/story_end 双动作 + 双核 loop ✅ · 视觉意图协议（emotion/place）✅ ·
memorial 状态机（enter/exit + 生图）✅ · 双层收尾兜底 ✅ · async_digest（闭环后消化）✅

| 方向 | 状态 | 说明 |
|---|---|---|
| **渲染器 renderer/（M1-M4）** | 🔧 | docs/DESIGN_RENDERER.md——背景/差分意图/特效/音频/回放; CLI 输出迁移 |
| regenerate 剧情粒度（整段撤销 + wiki 回滚） | 🔧 | 已设计（vn_enter 后全删 + 阶段 14 回滚）——待 bond 播放器配套 |
| VN 播放器（GUI） | 📋 | DESIGN_GUI.md M3 + DESIGN_MMT_CHAT.md M4——渲染器 M2 的前端消费方 |
| 回放模式（事件流 → 自动播放, 选项锁定 picked） | 🔧 | DESIGN_RENDERER.md M3 + 回放源支持快照（回溯场景） |
| 特效算法落地（smile→星星等, 角色表+全局表） | 🔧 | DESIGN_RENDERER.md §5——查表确定性, 待 M1 后 |
| 音频接口（bgm/sfx/voice） | 📋 | DESIGN_RENDERER.md §6——占位设计, 未来播放器 |

## 三、记忆 / Brain 域（core/brain/ + 滑动窗口 + digest）

**现状**: digest 唯一触发点 = bond 闭环（async_digest）✅ · resume 只注入 ✅ ·
增量 digest（digested_seq）✅ · 好感 delta（0~100）事件流幂等 ✅ · 滑动窗口 40 + 参数化 ✅ ·
wiki 注入（第一人称 recall）✅ · 中断剧情不消化 ✅

| 方向 | 状态 | 说明 |
|---|---|---|
| 好感度分层打分（MMT 0~10 / bond 30~100） | 🔧 | 防 MMT 闲聊刷好感——统一 0~100 的细化 |
| digest significance 分（0~1）消费（检索/驱逐排序） | 🔧 | 根目录 DESIGN_BRAIN.md §9 Step 2——分已实现（旧名 importance）, 消费未写 |
| 回忆注入（"你突然想起…"） | 🔧 | 根目录 DESIGN_BRAIN.md §9 Step 4——对话顺序保持, 依赖 embedding 回捞 |
| 重要性驱逐（Generative Agents 式） | 🔧 | 根目录 DESIGN_BRAIN.md §9 Step 5——依赖 embedding（驱逐不丢的前提是原文可回捞） |
| 联想 digest（新旧碰撞出成长） | 🔧 | 根目录 DESIGN_BRAIN.md §5——双通道回忆（珍贵保底 + 遗忘曲线） |
| RAG 回忆（embedding 检索旧事件） | 📋 | 根目录 DESIGN_BRAIN.md §10 Phase 2——本地 nomic embedding, numpy 余弦即可 |
| 并行/并发 digest（多角色 + 玩家输入优先） | 🔧 | 已讨论（LLM 串行锁 + 可让路/放弃） |
| 好感动画延迟结算（UI: ??? → EXP 动画） | 🔧 | 已讨论——GUI 侧 |
| 事件流全量保留策略（长积累摘要化/归档） | 🔧 | TODO 技术债——YAGNI 当前可延后 |

## 四、世界 / 存档域（worlds v2 + 快照 + 回退）

**现状**: data/worlds/{world1..3} 平行世界 ✅ · 每角色单线（sessions/events.jsonl）✅ ·
marker 状态推导（无状态机）✅ · 中断 = 无 session_end ✅ · 快照树/虚边/森林模型定稿（文档）✅

| 方向 | 状态 | 说明 |
|---|---|---|
| 快照系统实现（世界时点复制 + 恢复） | 📋 | docs/archive/world_model_evolution.md 阶段 8——世界顶层存档单元, 未实现 |
| 单体回溯 / 集体倒退 / 平行世界切换器 | 📋 | 阶段 15.3（scope 参数）——组件化, 引擎层未写 |
| 快照回放源（原线剧情回放） | 🔧 | DESIGN_RENDERER.md §7.3——snapshot: s_xxx 源 |
| 世界树 UI（快照浏览/回放入口） | 📋 | 阶段 15——GUI 侧, 依赖快照实现 |
| wiki 有损回滚（LLM 重写, IDE 模式复用） | 🔧 | 阶段 14——regenerate 剧情粒度的配套 |
| 旧档 v0 只读兼容 | ⛔ | 用户拍板: 开发期旧档直接删除, 不迁移不兼容 |

## 五、渲染器域（renderer/ 规划——见二）

## 六、视觉 / 媒体域（core/director/ + catalog + 生图）

**现状**: 视觉意图协议（emotion/place 封闭词表）✅ · Director.visual_for ✅ ·
MediaCatalog 背景/差分查库 ✅ · 情绪词表 per 角色（emotions.yml）✅ · 生图接口
ImageGenerator（SD1.5）✅ · memorial 生图 ✅ · 差分配置（diff/ 静态 + spine 扫描）✅

| 方向 | 状态 | 说明 |
|---|---|---|
| sprite_player 独立模块（play_diff / play_spine 双 API） | 🔧 | DESIGN_RENDERER.md §4——renderer 只出意图, 播放外包 |
| spine 动画播放（骨骼动画, 呼吸/眨眼） | 📋 | assets/illustration/{char}/spine/ 已有扫描——播放器未来 |
| 生图管线剩余（纪念判定已接, 日常发图未接） | 🔧 | mmt_send_media 媒体管线（TODO 中期） |
| L2D 动画参数（静态图 + 呼吸/眨眼） | 📋 | CLAUDE.md 板块 3——前端展示层 |

## 七、好感度域（core/affection/）

**现状**: Level-EXPgap 查表 ✅ · AI 回 0~100 delta ✅ · 事件流累计 + rewind ✅ ·
MMT 列表显示 + 排序（好感/活跃/白名单）✅ · None = 初始 1 ✅

| 方向 | 状态 | 说明 |
|---|---|---|
| 好感动画（聊天中实时涨跌提示） | 🔧 | GUI 侧——已讨论 |
| 好感影响行为（高好感触发特殊对话/解锁） | 📋 | CLAUDE.md §3.5——现仅显示/排序, 未进规则 |
| 分层打分 | 🔧 | 见三（MMT/bond 额度分离） |

## 八、GUI 域（webgui/）

**现状**: 登录（namegg 彩蛋）✅ · 主界面三入口 ✅ · 设置页（settings.toml 真源 +
优先级 构造>toml>env）✅ · MMT 三栏（横幅/模式切换/资料/对话）✅ · 微信式失败 UX ✅ ·
API key 打码/密码框 ✅ · 静态资源 no-cache ✅ · bond 入口横幅 ✅ · 输入锁定 ✅

| 方向 | 状态 | 说明 |
|---|---|---|
| VN 播放器（view-vn） | 📋 | 渲染器 M2 的消费方——最重要的大块 |
| 回放页（时间线 → 渲染器回放） | 📋 | DESIGN_GUI.md M4 |
| 设置页暴露窗口数值/好感参数 | 🔧 | DESIGN_MEMORY.md Step 1 优化空间 |
| 角色资料模式完善（生日/bio 已有, 好感曲线/历史） | 📋 | 已有基础, 扩展 |
| 未读红点 / SSE | 🔧 | 见一 |

## 九、引擎基础设施（llm/ + core/common/）

**现状**: OpenAI 兼容 httpx 封装 ✅ · 401/403 快速失败 ✅ · 思维链捕获
（last_reasoning）✅ · ReasoningProbe 可插拔 ✅ · 统一错误格式 ✅ · 滑窗参数化 ✅

| 方向 | 状态 | 说明 |
|---|---|---|
| 流式（chat_stream）接入 MMT | 📋 | client 已有 chat_stream——引擎/前端未接（SSE 配套） |
| 本地小模型（意图分类/实体提取/Sleep Encoding） | 📋 | CLAUDE.md §3.3——Phase 6 |
| 多 LLM 负载/降级（主+备 key） | 📋 | 未讨论细节 |

## 十、远期板块（📋 规划中）

| 板块 | 蓝图 | 前置 |
|---|---|---|
| 多角色同框（A 一次调用 / B 轮番调用） | DESIGN_MULTI_CHAR.md（段落流抽象） | 单人模式解锁后 |
| 官方剧情（剧本解析器 + 播放器） | CLAUDE.md 板块 4 | 渲染器就绪后 |
| Virtual Brain 完整（Semantic Graph / Self-Model / Sleep 五阶段） | CLAUDE.md §3.2 | digest 体系稳定后 |
| 羁绊触发算法（LLM+规则混合打分） | CLAUDE.md §3.5 | 轮数门槛升级 |
| 匿名论坛（角色间自发互动） | CLAUDE.md §1.2 | 多角色后 |
| 语音（ASR/TTS） | CLAUDE.md 技术栈 | 音频接口落地后 |

---

## 快速启动建议（按性价比排序）

```
1. 好感度分层打分（三/七）          —— 小改, digest.md 规则微调, 防刷好感
2. digest importance 分（三）        —— 零前置, 记忆体系地基（Step 2）
3. renderer/ M1（二/五）             —— 骨架 + 三 Resolver + CLI 迁移（设计已定稿）
4. regenerate 单轮（一）             —— 引擎层函数, GUI 未来接
5. SSE 替代轮询（一）                —— 体验提升, 模式现成（hub runner）
```

> 状态会随实施更新——完成一项就改 ✅ 并勾掉 TODO.md 对应项。
