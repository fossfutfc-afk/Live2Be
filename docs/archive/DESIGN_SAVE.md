# 存档系统设计（DESIGN_SAVE）— 统一互动会话 + 分层存储

> 状态：**设计定稿 2026-08-23，整合修订 2026-08-24**（单事件流 + l2d 动作）
> 范围：MomoTalk + Bond Story + L2D 纪念立绘的持久化、恢复、中断容错
> 关联：DESIGN_BOND_STORY.md（VN 引擎）、3.2 Virtual Brain（远期统一记忆）

---

## 一、动机与现状痛点

### 1.1 历史现状（v0 单文件，已废弃）

| 维度 | MomoTalk（core/momotalk.py Session） | Bond Story（core/bond/bond_save.py） |
|------|------|------|
| 位置 | `data/sessions/{char}_{ts}.json` | `data/saves/bond_story_{char}_{ts}.json` |
| 内容 | character_id/name + **history 全量** | **scenes[] 叙事记录**（段落/选项/视觉字段） |
| 写入 | `open(w)` 直接写（**非原子**） | 逐场 append + 原子写（temp+replace） |
| 恢复 | `resume_session`：重建 system + 塞回 history → **可继续** | `replay_bond_story`：只读回放 → **不可继续** |

### 1.2 痛点（2026-08-24 用户决策：开发期，v0 旧档 + 已落盘双目录会话**直接删除**，不迁移不兼容）

1. **MMT / bond 记录分离**：两套 schema、两个目录、零关联——bond 存档不记"从哪个 MMT 会话进来"。
2. **断连要延续提示词**：MMT 勉强可（system 重建 + history 全量）；bond 只存"演过什么"，没存"进行到哪"。
3. **中断损坏**：MMT `open(w)` 非原子；bond 每次 append 全量重写（O(n²) 写放大）。
4. **schema 无版本**：字段一直在变（sprite → beats → 内联 emotion），旧档兼容靠运气。
5. **无会话状态机**：无法表达"这个会话在 VN 中暂停"。
6. **MMT 根 + bond 子会话分两个目录**（2026-08-24 整合修订的动因）：同一对话跨目录、靠 marker 跨目录关联——应整合为**一个对话一个目录**。

---

## 二、设计目标

1. **一次完整互动 = 一个会话目录**：MMT 进 VN、VN 中出 l2d，全程一个目录、一条 events.jsonl
2. **断连后可继续**：存够重建 LLM 上下文 + VN 运行状态的输入
3. **中断安全**：append-only + 原子写，坏文件不阻断（宁缺勿错）
4. **schema 版本化**；旧档开发期直接删除（用户决策 2026-08-24）
5. **手动恢复**：列出未结束会话，玩家选择

---

## 三、存储布局（2026-08-24 整合修订）

**原则：每角色一个根目录 + 一个对话一个会话目录**（用户决策："按角色名分门别类"、
"jsonl 就应该同一个文件记载 mmt+bond+l2d"）。

```
data/
  basic/                          # 全局（仅跨角色数据）
    player.json                   # 玩家名等
  {char_id}/                      # ★ 每角色一个根（igusa_haruka / rikuhachima_aru / …）
    progress.json                 # 聚合总轮数（所有 session 累计, 门槛判断唯一真源）
    sessions/
      {conversation_id}/          # ★ 一次完整互动 = 一个会话目录（MMT+VN+L2D 全程一个）
        meta.json                 # 纯索引：schema_version / type / char / created_at（§4.1）
        events.jsonl              # ★ 事件流唯一真源：mmt + bond + l2d + marker 同一文件, seq 统一递增（§4.2）
        progress.json             # 该会话内聊天轮数（展示用）
        brain/                    # 该会话的消化产物（digest 产出, 已实现; §4.6）
          wiki.json               # 本会话记忆总结（facts/beliefs/relations + affection）
          index.jsonl             # （已废弃: 初代 snippet 索引 2026-08-28 裁决删除——
                                  #   原文回捞未来走 embedding, 见 docs/DESIGN_MEMORY.md Step 3）
    gallery/                      # AI 生成 2D 场景（图 + 文字信息成对, §4.5）
      {scene_id}.png              # 生成图
      {scene_id}.json             # 文字信息（prompt / 场景描述 / 来源会话 / 时间戳）
    brain/                        # （废弃: 早期"角色级归并"设计——平行世界语义下
                                  #   无角色级 wiki, 见 §4.6 修订注记; 目录不再创建）
      wiki.json                   # 跨会话 LLM WIKI（digest 归并各会话产物）※ 已废弃
      index/                      # RAG 索引（远期——embedding 向量回捞, 非初代 snippet 方案）
```

| 文件 | 职责 | 写入方式 | 中断语义 |
|------|------|----------|----------|
| `meta.json` | **纯索引**（type/char/created_at, 无状态） | 原子写（创建时一次） | 原子替换，永不半写 |
| `events.jsonl` | **事件流唯一真源**（mmt+bond+l2d+marker） | `open("a")` 每行一个事件 | 行级原子；读时行级 try/except 丢弃坏行 |
| `progress.json`（session 内） | 该会话聊天轮数 | 原子写（每轮结束） | 原子替换，永不半写 |
| `progress.json`（角色根） | 聚合总轮数 | 原子写（低频） | 原子替换，永不半写 |
| `gallery/{scene_id}.json` | 生成图元数据 | 原子写（生成一次） | 原子替换；png 与 json 成对（§4.5） |
| `sessions/{id}/brain/wiki.json` | 会话消化产物 | 原子写（消化一次） | 原子替换；旧值仍可读 |
| `brain/wiki.json`（角色根） | 角色级汇总 ※ 已废弃（平行世界, 无归并——DESIGN_BRAIN.md v3.1） | — | — |

---

## 四、Schema

### 4.1 meta.json（纯索引, 无状态）

**不做状态机**——所有状态从 events 的 marker 事件推导（§4.2/§5.1）; meta 只作索引, 创建时写一次:

```jsonc
{
  "schema_version": 2,
  "session_id": "20260824_143022_ab12",   // 角色目录内唯一: {YYYYMMDD_HHMMSS}_{rand4}
  "type": "conversation",          // ★ 2026-08-24: 一个对话含 mmt+bond+l2d 多板块, 不再用 mmt|bond
  "character_id": "igusa_haruka",
  "character_name": "伊草 遥香",
  "created_at": "2026-08-24T14:30:22.123456"
}
```

### 4.2 events.jsonl（统一事件流 — 唯一真源, 2026-08-24 整合）

**核心设计：事件流是唯一真源**——存"当时发生了什么"（结构化），LLM 消息/回放/brain 全是派生视图
（渲染器实时生成, 不落盘, 无冗余）。**mmt + bond + l2d + marker 全部写入同一文件**，
`seq` 全局统一递增（不再分文件、不再有子会话 seq）。

```jsonl
// MMT 板块（type=mmt）—— 一轮 agent 对话的产物
{"seq":1,"ts":"2026-08-24T15:02:11.654321","type":"mmt","subtype":"mmt_chat",
 "payload":{"operation":"","player":"你好呀","reply":"啊、老师…"}}

// Bond 板块（type=bond）—— 一场 VN 场景（叙事 + 意图 + 玩家裁决）
{"seq":2,"ts":"2026-08-24T15:04:12.654321","type":"bond","subtype":"story_scene",
 "payload":{"paragraphs":[{"text":"…","emotion":"embarrass"}],"choices":["…"],"is_end":false,
            "background":"class_room","input":"…","picked":"…"}}

// L2D 板块（type=l2d）—— 纪念立绘（memorial_enter 进入子模式时的产物, §4.7）
{"seq":3,"ts":"2026-08-24T15:05:00.000000","type":"l2d","subtype":"memorial_enter",
 "payload":{"paragraphs":["（煽情文字…）"],"choices":["…"],"images":["gallery/xxx.png"]}}
```

骨架字段:
- `seq` — 会话内全局递增（重放/rewind 定位点）
- `ts` — 时间戳
- `type` — **板块**: `mmt` | `bond` | `l2d` | `marker`（预留 `official_story`）
- `subtype` — 动作名（mmt_chat / story_scene / memorial_enter / memorial_exit / vn_state …）; 新板块只加 subtype
- `payload` — 板块固定 schema（mmt: operation/player/reply; bond: BondScene + input/picked;
  l2d: paragraphs/choices/images; marker: 见下）

**marker 事件（状态标记——替代状态机）**:
```jsonl
{"seq":1, "type":"marker","subtype":"session_start"}                        // 会话开始
{"seq":12,"type":"marker","subtype":"vn_enter",
 "payload":{"reason":"老师约我放学后见面"}}                                 // ★ 进 VN（同一事件流, 无 parent_session_id）
{"seq":20,"type":"marker","subtype":"vn_exit"}                              // VN 结束回 MMT
{"seq":25,"type":"marker","subtype":"vn_state",                             // VN 恢复点（每场 VN 轮 append）
 "payload":{"round":12,"seed":"都点吧,今天我请客。","visual":{"background":"class_room"}}}
{"seq":30,"type":"marker","subtype":"memorial_enter",                       // ★ 进入纪念子模式（§4.7）
 "payload":{"reason":"湖边告白"}}
{"seq":33,"type":"marker","subtype":"memorial_exit"}                        // ★ 退出纪念, 回 bond
{"seq":40,"type":"marker","subtype":"session_end","payload":{"ended":true}} // 会话收尾
```
状态推导（恢复时扫描 markers）:
- **VN 进行中**: 有 `vn_enter` 且无其后 `vn_exit`/`session_end`（同一文件内, 天然成立）
- **纪念子模式中**: 有 `memorial_enter` 且无其后 `memorial_exit`/`session_end`（§4.7）
- **自然结束 vs 中断**: 有 `session_end` = 结束; **没有 = 中断**（崩溃时标记写不出去）
- **VN 恢复点**: 最后一个 `vn_state.payload`
- **纪念恢复点**: 最后 marker 是 `memorial_enter` → resume 到纪念场景
- **对话含 L2D**: 有 `type=l2d` 事件（列表/画廊标记用）

**派生视图（渲染器实时生成, 不落盘）**:
- **喂 LLM（恢复/继续）**: `render_events` 按板块渲染——mmt → user/assistant 对;
  bond → input + 紧凑 JSON; l2d/marker → 跳过（资产引用与状态标记不进对话上下文）
- **回放**: 过滤 `type=bond` 逐场渲染（`filter_bond`）; l2d 画廊 = 过滤 `type=l2d`
- **brain**: `render_timeline` 带板块标签（【MMT对话】【羁绊剧情】【L2D生成】）喂 LLM 总结

### 4.5 gallery / progress.json（角色目录扩展）

**gallery — AI 生成 2D 场景（图 + 文字信息成对）**：
```jsonc
// data/{char_id}/gallery/{scene_id}.json  ← 与 {scene_id}.png 同名成对
{
  "scene_id": "20260824_150412_cd34",
  "character_id": "igusa_haruka",
  "prompt": "遥香在天台上, 晚风, 微笑…",     // 生图 prompt（可复现）
  "description": "（场景描述: 情感氛围/构图）",
  "source_session": "20260824_143022_ab12",  // 来源会话（可回溯 events, 过滤 type=l2d）
  "created_at": "2026-08-24T15:04:12.654321"
}
```
- 写入顺序约定：**先原子写 json（元数据）再落 png**（或反之）——`list_gallery` 只认"json+png 都存在的成对"，半套视为写入中断
- l2d 动作（§4.7）执行时按此格式写入

**progress.json（角色根）— 聚合总轮数**：
```jsonc
// data/{char_id}/progress.json —— 所有 session 总对话轮数（门槛判断唯一真源）
{ "rounds": 84, "updated_at": "2026-08-24T15:02:11.654321" }
```

### 4.6 brain（2026-09-02 修订: 以代码为准——单层级 per-session wiki, 平行世界）

> ⚠️ **早期"双层级"设计（会话级 + 角色级归并）已废弃**——DESIGN_BRAIN.md v3.1 定稿:
> brain 是**算法**, 不是跨 session 实体; 每个 session 是独立世界线, **无角色级 wiki、
> 无归并、无迁移**。本小节只保留当前实现。

**当前实现（core/brain/, 单层级 per-session wiki）**：
```jsonc
// data/{char_id}/sessions/{conversation_id}/brain/wiki.json
{
  "schema_version": 2,
  "conversation_id": "20260824_143022_ab12",
  "digested_seq": 87,                    // 增量: 上次消化到的事件 seq（v3.1）
  "summary": "天台夜谈: 遥香对老师信任加深…",
  "facts":    [{"content": "老师说以后常来陪她看杂草", "significance": 0.8, "tags": ["老师", "杂草"]}],
  "beliefs":  [{"content": "遥香第一次觉得自己被需要", "significance": 0.9}],
  "relations":[{"subject": "遥香", "object": "老师", "relation": "信任加深", "note": "约定常来陪她"}],
  "affection": {"exp": 120, "level": 3},  // digest 好感结算缓存（真源 = affection 事件）
  "updated_at": "2026-08-24T15:30:00.000000"
}
```

**digest 流程（bond 剧情闭环后触发——async_digest, 唯一触发点）**:
```
触发:  本段 bond 闭环（vn_exit completed → finish → _wrapup → engine.async_digest）
输入:  seq > digested_seq 的全部事件（增量; 天然含本段 trigger mmt + 本段 bond
       + 上一段 finish 余韵——见 core/DESIGN_SEGMENT.md §3）;
       marker/affection 事件不计提炼内容（只推进水位）
处理:  主 LLM 提炼 → facts/beliefs/relations 增量合并（同 content 去重,
       significance 取高）→ affection_exp_delta 幂等写 affection 事件
       → 更新 digested_seq 水位
产出:  sessions/{id}/brain/wiki.json（本世界线私有——无角色级归并）
中断:  无闭环（无 story_end）→ 不消化（"中断的剧情不处理"）; 失败静默降级
       （wiki 是派生视图, events.jsonl 唯一真源, 可重算）
检索:  远期 RAG 从本 session wiki 检索 → 注入 system prompt（DESIGN_BRAIN.md §8）

### 4.7 纪念子模式（memorial, 2026-08-24 定稿: 状态机 enter/exit）

**定位**：memorial 是 bond 剧情中的**子模式**（状态），不是字段、不是单动作——
有明确的进入/退出（begin/end），架构与 mmt→bond 同构：

```
mmt ──mmt_trigger_bond_story──▶ bond ──memorial_enter──▶ memorial ──memorial_exit──▶ bond
```

**示范（遥香）**：老师邀请遥香去高级餐厅 →（trigger bond）遥香因紧张毁掉浪漫夜晚，
哭着跑出去 →（memorial_enter）湖边，sensei 说"接受这样的她正是自己该做的" →
（memorial_exit）遥香和老师蹲路边吃路边摊 →（回 MMT）遥香表示感谢。

**为什么是状态机而非可选字段**（2026-08-24 复盘）:
- 字段可填可不填 → LLM 必然偷懒（emotion 可选已实证）；独占动作逼 LLM **谨慎决策**
- memorial 是一段有 begin/end 的子剧情——字段表达不了状态边界
  （恢复/渲染/频率控制全依赖"当前是否在纪念模式"）

**动作**（memorial 域, 独立 registry `build_memorial_registry()`）:

`memorial_enter`（独占一轮, 谨慎决策进入纪念时刻）:
```jsonc
{"action": "memorial_enter", "payload": {
  "prompt": "她在湖边微笑，眼角带着一滴泪，黄昏暖光，晚风吹起鬓发，中景半身",  // 必填: 中文场景指令（场景/光线/情感/构图）
  "paragraphs": ["（纪念场景的煽情文字=本场剧情内容）", "…"],  // 必填
  "choices": ["…"]                                           // 可选
}}
```
- 执行: APIYI 生图（见下「生图后端」）→ gallery 落盘 → append l2d 事件
  {paragraphs, choices, images} + marker memorial_enter → 渲染纪念场景（文字 + 立绘 + 选项）

`memorial_exit`（独占一轮, 回到 bond）:
```jsonc
{"action": "memorial_exit", "payload": {
  "paragraphs": ["（从纪念时刻回到日常的过渡文字, 可空）"]    // 可选
}}
```
- 执行: append marker memorial_exit → 之后 LLM 继续 story_scene/story_end（bond 模式）

**marker 状态**（对齐 vn_enter/vn_exit）:
- `memorial_enter` / `memorial_exit` marker → `session_status` 推导 `in_memorial`
- 中断恢复: 最后 marker 是 memorial_enter → resume 到纪念场景

**l2d 事件**（进统一事件流, subtype=memorial_enter）:
```jsonl
{"seq":N,"ts":"...","type":"l2d","subtype":"memorial_enter",
 "payload":{"paragraphs":["（煽情文字…）"],"choices":["…"],"images":["gallery/xxx.png"]}}
```
- `images` 数组: 一场可多张（每张一个 gallery 文件对, 各自 prompt 可复现）; 单张也数组
- prompt 不落事件（在 gallery json）; 无 description/scene_ref

**生图后端（2026-08-24: APIYI Gemini 图像为主, 本地 diffusers 兜底）**:
- **APIYI**（推荐）: .env 配 `IMAGE_API_KEY` → `ImageGenerator` 走
  `generateContent`（Google GenAI SDK 协议, `{base}/{api_version}/models/{model}:generateContent`）,
  多图 ref + 中文指令, 秒级出图（对比本地 SD 20 分钟）。
- **ref 命名约定**（`assets/illustration/{char_id}/ref/`, 喂图顺序固定）:
  ```
  sprite_*.png    角色本体（可多张）
  style_*.png     画风示例（可多张）
  其余 png        配饰（光环/随身物品, 物品名即可, 如 halo.png）
  ```
  `collect_ref_images(char_id)` 按 **角色→画风→配饰** 分组排序返回。
- **提示词三段式**: 固定框架（引擎拼接: 图1角色锚定 / 图2画风锚定 / 图3配饰锚定 /
  质量要求——不依赖 LLM 每次写）+ 变化部分 = `memorial_enter.prompt`（**中文场景指令**,
  只写场景/光线/情感/构图; 角色外观由 ref 图锚定, 写了反而冲突）。
- 本地 diffusers（SD1.5/SDXL + IP-Adapter）: 未配 `IMAGE_API_KEY` 时兜底
  （中文 prompt 是噪声、无画风参考、8G 显存极慢——不建议日常用）。

**频率约束**: **一段 bond 剧情至多 1 次 memorial**（2026-08-24 用户拍板, 后续
  memorial_enter 被引擎静默拒绝 + 下轮注记）——情感高潮通常一次, 防刷屏

**单向**: 生图结果不回灌 LLM 历史（防"揣摩生图"自我强化, 与 place 同理）

**approval**: `APPROVAL_AUTO`（APIYI 按次计费 $0.025/次（Nano Banana 2 Lite）, 无需审批）

**已知限制 / 未来项**:
- **立绘竖版**: 当前输出为竖版（APIYI 默认比例）——横屏展示适配（aspectRatio 参数,
  如 16:9）**留到 web 前端阶段**（2026-08-24 用户拍板, CLI 阶段不处理）
- **光环 ref 有效**: 遥香的光环（断裂三角结构）需配饰图锚定——其余角色不传光环
  参数也能出, 但遥香必须传（2026-08-24 实测验证）

---

## 五、生命周期（marker 事件驱动, 无状态机, 2026-08-24 单流修订）

### 5.1 会话生命周期

```
session_start ──► MMT 轮（append mmt 事件）
   │  mmt_trigger_bond_story → append marker vn_enter{reason}
   ▼
VN 轮（append bond 事件 + vn_state marker 每场）
   │  VN 中 LLM 输出 memorial_enter → append l2d 事件（立绘+煽情文字）
   │    + marker memorial_enter（进入纪念子模式）──► 纪念场景（渲染文字+图+选项）
   │  memorial_exit → append marker memorial_exit ──► 回 bond（story_scene 继续）
   ▼
vn_exit ──► 回 MMT
   ▼
session_end{ended:true}（自然收尾 / 程序兜底 / 玩家退出）
中断 = 崩溃/断连时 session_end 写不出去——无标记即中断（§4.2 推导）
```

### 5.2 新建会话

```
SessionStore.create(char_id, char_name)
  → 建目录 + 写 meta.json（type=conversation, 纯索引）
  → append marker session_start
  → 每轮 agent_turn 结束 append type=mmt 事件 + session progress
```

### 5.3 MMT → VN 衔接（★ 2026-08-24: 无子会话）

```
mmt_trigger_bond_story 执行成功时:
  SessionStore.enter_vn(reason)
    → 当前会话 append marker vn_enter{reason}（不建新目录、无 parent 关联）
    → 后续 bond 事件 / vn_state / vn_exit 全部 append 到同一 events.jsonl
```

### 5.4 VN 轮

```
每场 send_vn_scene 后:
  events.jsonl append 一个 type=bond 事件（paragraphs 内联 emotion + input/picked）
  events.jsonl append marker vn_state（round/seed/visual —— 恢复点, 取最后一个）
  若该场 LLM 输出 memorial_enter: append l2d 事件（立绘+煽情文字）+ marker memorial_enter（进入子模式, §4.7）
  若该场 LLM 输出 memorial_exit: append marker memorial_exit（回 bond, 后续继续 story_scene）
```

### 5.5 VN 结束（自然收尾 / 程序兜底 / b 退出）

```
wrapup_after_vn:
  同一 events.jsonl append marker vn_exit（回 MMT）
  后续 MMT 轮 append 回同一 events.jsonl
  （VN 期间的上下文不进 MMT 注入段——上下文隔离由渲染器按板块分段, 存储不分家）
  （bond 剧情闭环后触发 brain 消化, 见 §4.6）
```

### 5.6 中断（崩溃/断连）

- 最后 marker 决定恢复路径（同一文件内）：
  - 最后是 session_start（无 vn_enter）→ resume MMT
  - 最后是 vn_state（有 vn_enter 无 vn_exit）→ resume VN（取最后 vn_state）

---

## 六、恢复流程（手动选择, 2026-08-24 简化: 读一个目录）

```
启动 → SessionStore.list_open()          // 扫 sessions/*/meta.json, 过滤未结束
  → 玩家选择 or 选"新会话"
  → SessionStore.resume(session_id):
      meta = load meta.json（纯索引）
      events = load events.jsonl（行级容错）
      if 有 session_end marker: 不可恢复（只读回放: filter type=bond 渲染 / type=l2d 画廊）
      # 1) 重建 LLM 上下文（events 重放 → render_events, 不落盘消息）
      messages = render_events(events)
      if 无 vn_enter marker（或 vn_exit 在其后）:      // 在 MMT 中
          engine.start_session(meta.character_id)      // 重建 system（含注入）
          engine._history = messages
          继续 MMT loop
      else:                                            // 在 VN 中（vn_enter 无 vn_exit）
          vn_state = 最后一个 vn_state marker.payload
          vn = BondStoryEngine(characters_root, llm, director=build_director(char))
          vn.start_session(char_id)
          vn._history = messages
          i = vn_state.round; user_input = vn_state.seed
          继续 vn_cli 主循环
      # 2) rewind（可选）: 重放到 seq N = render_events(events[:N])
```

**要点**：恢复 = `start_session`（system 重建）+ **重放 events → render 消息** +
扫描 markers 定位（MMT/VN/结束）。**无跨目录 parent 关联、无需状态机**——
LLM 是 stateless 的，上下文从事件流派生，状态从 marker 推导。

---

## 七、原子性与容错

| 机制 | 实现 |
|------|------|
| meta/vn_state/progress 原子写 | `core/session/io.atomic_write_json`（temp 同目录 + os.replace，Windows 同卷原子） |
| events append | `append_jsonl`（`open("a")` 单行 json.dumps）；读时逐行 try/except，坏行丢弃（宁缺勿错） |
| l2d 生图失败 | 降级不阻断：不落 l2d 事件，该轮按"无副作用"收场（§4.7） |
| 写失败 | 不阻断主流程（try 包裹），降级为"本轮不记录" + logger.warning |
| 并发 | **单写者假设**（单进程 CLI）；未来 web 多会话各自写自己的目录，天然隔离 |

---

## 八、兼容与迁移（2026-08-24 修订: 开发期旧档删除）

- **新读路径**：`data/{char_id}/sessions/{conversation_id}/meta.json` 存在 = v2 会话（type=conversation, 单事件流）
- **旧档删除**（用户决策 2026-08-24，开发期）：以下直接删除，不做迁移、不做只读兼容：
  - v0 单文件档：`data/{char}/sessions/{char}_{date}.json`、`bond_story_{char}_{date}.json`
  - v1 双目录会话：MMT 根会话 + bond 子会话（`vn_enter.parent_session_id` 关联的旧结构）
  - 全局旧档：`data/basic/bond_progress.legacy.json`、`data/basic/playeranalysis.yml` 等
- 删除后：`BondStorySave`（core/bond/bond_save.py 单文件 recorder）**退役**（读路径随之删除）；
  `resume_session` 旧逻辑删除；`replay_bond_story` 改为从事件流 `filter_bond` 渲染
- 数据迁移豁免：开发期数据无长期价值，删了重玩（用户拍板）

---

## 九、实现计划（整合落地, 待 l2d 设计确认后动手）

### 模块改动

| 位置 | 改动 |
|------|------|
| `core/session/store.py` | `open_vn` → `enter_vn(reason)`（只 append vn_enter marker, 不建目录）; 删除 parent 关联; meta.type=conversation |
| `core/session/models.py` | `SessionMeta.type` 默认 `conversation`; `VNState` 保留（vn_state payload） |
| `core/session/renderer.py` | `session_status` 去掉 parent_session_id; `render_events` 跳过 l2d（已支持）; `filter_l2d` 新增（画廊源） |
| `core/ui/vn_cli.py` | `run_bond_story_vn` 去掉 `store.open_vn` 子会话逻辑 → 统一 append 到当前会话; `replay_bond_story` 改从事件流过滤 |
| `core/bond/memorial_actions.py`（新增） | `build_memorial_registry()`（memorial 域独立 registry, §4.7） |
| `core/bond/memorial_executor.py`（新增） | memorial 执行（生图 + gallery + l2d 事件; 失败降级, 每场 1 张上限） |
| `core/bond/bond_save.py` | `BondStorySave` 退役（旧档删除后, 读路径一并删） |
| `core/media/gallery.py`（新增骨架） | `list_gallery(char_id)` 只认 json+png 成对; l2d 执行时写入 |
| `core/brain/`（已实现） | `digest_session` → 本 session 的 wiki（§4.6 修订版; 无角色级归并） |
| `core/session/io.py` | 保留（原子写/append 原样） |

### 删除动作

- v0/v1 旧档数据文件 + `data/basic/*` 残留（§八）
- `core/bond/bond_save.py` 的 BondStorySave 类 + `replay_bond_story` 旧读路径
- `core/momotalk.py` 的 v0 `resume_session` 旧逻辑（保留 `SessionStore.resume`）

### 测试（tests/core/test_session.py 等）

- store: create → enter_vn → append mmt/bond/l2d 事件 → finish → list_open 过滤
- 单流: mmt + bond + l2d + marker 同一 events.jsonl, seq 全局递增
- 中断恢复: 坏行丢弃、vn_state 恢复（回退一场）
- renderer: render_events 板块混排、filter_bond / filter_l2d、rewind
- memorial: memorial_enter/exit 状态机（parse/执行/mock ImageGenerator）/失败降级/一段至多 1 次 enter
- 旧档删除后: 无兼容路径, 相关测试删除

---

## 十、未决事项（实现前确认）

1. ~~memorial 每场上限~~ → **已定（2026-08-24）**：一段 bond 剧情至多 1 次 memorial（后续 enter 拒绝 + 注记）
2. ~~预判式 / 独占动作 / 内联字段~~ → **已定（2026-08-24）**：子模式状态机 `memorial_enter` / `memorial_exit`
   （显式独占动作逼 LLM 谨慎决策 + begin/end 状态边界; 预判式废弃——预判不知剧情, prompt 与剧情脱节）
3. **事件流保留策略**：全量保留 + brain 消化后延迟归档（既有决策, 保留）
4. **jsonl 行大小**：bond 段落很长（max_tokens 1536+），单行可能 >4KB——append 原子性
   在 Windows 上仍"单次 write 系统调用"，风险低；若实测不稳再退化"小块写入 + 行尾校验"
