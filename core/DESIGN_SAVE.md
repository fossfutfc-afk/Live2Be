# 存档系统设计（DESIGN_SAVE）— 统一互动会话 + 分层存储

> 状态：**设计定稿 2026-08-23**（待实现）
> 范围：MomoTalk 会话 + Bond Story 会话的持久化、恢复、中断容错
> 关联：DESIGN_BOND_STORY.md（VN 引擎）、3.2 Virtual Brain（远期统一记忆）

---

## 一、动机与现状痛点

### 1.1 现状（代码事实）

| 维度 | MomoTalk（core/momotalk.py Session） | Bond Story（core/bond/bond_save.py） |
|------|------|------|
| 位置 | `data/sessions/{char}_{ts}.json` | `data/saves/bond_story_{char}_{ts}.json` |
| 内容 | character_id/name + **history 全量** | **scenes[] 叙事记录**（段落/选项/视觉字段） |
| 写入 | `open(w)` 直接写（**非原子**） | 逐场 append + 原子写（temp+replace） |
| 恢复 | `resume_session`：重建 system + 塞回 history → **可继续** | `replay_bond_story`：只读回放 → **不可继续** |
| LLM 上下文 | history 在，system 可重建 ✅ | ❌ 无 history，无 VN 运行状态 |

### 1.2 痛点（用户确认）

1. **MMT / bond 记录分离**：两套 schema、两个目录、零关联——bond 存档不记"从哪个 MMT 会话进来"。断连后无法知道上次停在 MMT 还是 VN。
2. **断连要延续提示词**：MMT 勉强可（system 重建 + history 全量）；**bond 完全不能**——只存"演过什么"（回放），没存"进行到哪、上下文是什么"（继续）。
3. **中断损坏**：MMT `open(w)` 非原子（写一半断电 → 文件坏）；bond 原子写已做但**每次 append 全量重写**（O(n²) 写放大）。
4. **schema 无版本**：字段一直在变（sprite → beats/place → audio），旧档兼容靠运气。
5. **无会话状态机**：无法表达"这个会话在 VN 中暂停"。

---

## 二、设计目标

1. **一次完整互动 = 一个会话**（MMT 进 VN 再出来，全程一个会话目录，VN 记 parent 关联）
2. **断连后可继续**（不是只能回放）：存够重建 LLM 上下文 + VN 运行状态的输入
3. **中断安全**：append-only + 原子写，坏文件不阻断（宁缺勿错）
4. **schema 版本化** + v0 旧档兼容
5. **手动恢复**：列出未结束会话，玩家选择（用户决策 2026-08-23）

---

## 三、存储布局（按角色根目录，2026-08-23 升级定稿）

**原则：每角色一个根目录**——会话、AI 生成内容、远期记忆全归位（用户决策：
"按角色名分门别类"；未来 AI 生成 2D 场景的图 + 文字成对存角色 gallery 下）。

```
data/
  basic/                          # 全局（仅跨角色数据）
    player.json                   # 玩家名等
  {char_id}/                      # ★ 每角色一个根（igusa_haruka / rikuhachima_aru / …）
    progress.json                 # 聚合总轮数（所有 session 累计, 门槛判断唯一真源）
    sessions/
      {session_id}/               # 一次时间段 = 一个会话目录（MMT 进 VN 出来全程一个）
        meta.json                 # 纯索引：schema_version / type / char / created_at（无状态, §4.1）
        events.jsonl              # ★ 事件流唯一真源（内容事件 + marker 状态标记, §4.2）
        progress.json             # 该 session 内聊天轮数（agent_turn 结束 +1, 展示用）
      _archived/                  # brain 消化完的旧 session（全量保留, 延迟归档, YAGNI）
    gallery/                      # AI 生成 2D 场景（图 + 文字信息成对, §4.5）
      {scene_id}.png              # 生成图
      {scene_id}.json             # 文字信息（prompt / 场景描述 / 来源会话 / 时间戳）
    brain/                        # Virtual Brain（每角色独立, §4.6）
      wiki.json                   # LLM WIKI（成长/好感度/关系总结, brain 消化 events 的产出）
      index/                      # RAG 索引（远期）
```

| 文件 | 职责 | 写入方式 | 中断语义 |
|------|------|----------|----------|
| `meta.json` | **纯索引**（type/char/created_at, 无状态） | 原子写（创建时一次） | 原子替换，永不半写 |
| `events.jsonl` | **事件流唯一真源**（内容 + marker） | `open("a")` 每行一个事件 | 行级原子；读时行级 try/except 丢弃坏行（最多丢半事件） |
| `progress.json`（session 内） | 该会话聊天轮数 | 原子写（每轮结束） | 原子替换，永不半写 |
| `progress.json`（角色根） | 聚合总轮数 | 原子写（低频） | 原子替换，永不半写 |
| `gallery/{scene_id}.json` | 生成图元数据 | 原子写（生成一次） | 原子替换；png 先落盘再写 json 或反之（§4.5） |
| `brain/wiki.json` | WIKI 总结（brain 产出） | 原子写（每次消化更新） | 原子替换；旧 wiki 仍可读 |

---

## 四、Schema

### 4.1 meta.json（纯索引, 无状态）

**不做状态机**（用户决策 2026-08-23）——所有状态从 events 的 marker 事件推导
（§4.2/§5.1）; meta 只作索引, 创建时写一次:

```jsonc
{
  "schema_version": 1,
  "session_id": "20260823_143022_ab12",   // 角色目录内唯一: {YYYYMMDD_HHMMSS}_{rand4}（char 由目录隔离）
  "type": "mmt",                   // mmt | bond —— 会话类型 = 主导事件板块（与事件 type 统一）; 创建时确定, 列表显示用（索引缓存, 非状态）
  "character_id": "igusa_haruka",
  "character_name": "伊草 遥香",
  "created_at": "2026-08-23T14:30:22.123456"
}
```

### 4.2 events.jsonl（事件流 — 唯一真源, 2026-08-23 定稿）

**核心设计：事件流是唯一真源**——存"当时发生了什么"（结构化），LLM 消息/回放/brain 全是派生视图
（渲染器实时生成, 不落盘, 无冗余）。事件 → 消息可推导; 消息 → 事件不可（丢结构）。

每行一个事件, 共用骨架 + 板块化 payload:

```jsonl
// MMT 板块（type=mmt）—— 一轮 agent 对话的产物
{"seq":1,"ts":"2026-08-23T15:02:11.654321","type":"mmt","subtype":"mmt_chat",
 "payload":{"player":"你好呀","reply":"啊、老师…","steps":2}}

// Bond 板块（type=bond）—— 一场 VN 场景（叙事 + 意图 + 玩家裁决）
{"seq":2,"ts":"2026-08-23T15:04:12.654321","type":"bond","subtype":"story_scene",
 "payload":{"paragraphs":["…"],"choices":["…"],"picked":"…",
            "beats":[{"text":"…","emotion":"embarass"}],"place":"class_room",
            "background":"class_room","audio":null}}

// L2D 板块（type=l2d）—— 一次纪念立绘生成（引用 gallery 资产 + 来源场景）
{"seq":3,"ts":"2026-08-23T15:05:00.000000","type":"l2d","subtype":"generate",
 "payload":{"prompt":"遥香在天台…","image":"gallery/20260823_150500_cd34.png","scene_ref":2}}
```

骨架字段:
- `seq` — 会话内递增（重放/rewind 定位点）
- `ts` — 时间戳
- `type` — **板块**: `mmt` | `bond` | `l2d` | `marker`（预留 `official_story` 官方剧情）
- `subtype` — 动作名（mmt_chat / story_scene / generate / vn_state …）; 新板块只加 subtype, 骨架不变
- `payload` — 板块固定 schema（mmt: player/reply; bond: BondScene 字段 + picked;
  l2d: prompt/image/scene_ref; marker: 见下）

**marker 事件（状态标记, 2026-08-23 定稿——替代状态机）**:
```jsonl
{"seq":1, "type":"marker","subtype":"session_start"}                        // 会话开始
{"seq":12,"type":"marker","subtype":"vn_enter",
 "payload":{"parent_session_id":"20260823_140000_zz99","reason":"老师约我放学后见面"}}  // 进 VN（bond 归属）
{"seq":20,"type":"marker","subtype":"vn_exit"}                              // VN 结束回 MMT
{"seq":25,"type":"marker","subtype":"vn_state",                             // VN 恢复点（每场 VN 轮 append）
 "payload":{"round":12,"seed":"都点吧,今天我请客。","visual":{"background":"class_room"}}}
{"seq":40,"type":"marker","subtype":"session_end","payload":{"ended":true}} // 会话收尾
```
状态推导（恢复时扫描 markers, 全量加载本来就要做）:
- **会话类型**: meta.type（索引缓存; 首个非 marker 事件也可验）
- **VN 进行中**: 有 `vn_enter` 且无其后 `vn_exit`/`session_end`
- **bond 归属**: 最近 `vn_enter.payload.parent_session_id`
- **自然结束 vs 中断**: 有 `session_end` = 结束; **没有 = 中断**（崩溃时标记写不出去, 零成本表达）
- **VN 恢复点**: 最后一个 `vn_state.payload`（filter subtype=vn_state 取最后）

**派生视图（渲染器 `render_events` 实时生成, 不落盘）**:
- **喂 LLM（恢复/继续）**: 事件 → `[{role, content}]`（mmt_turn → user/assistant 对;
  bond → 段落文本; l2d → 系统注记）。**system_prompt 不落盘**——由 `char_id + type`
  重建（start_session 已是重建逻辑, 含世界观/人际/词表注入）
- **回放**: 过滤 `type=bond` 逐场渲染（原 scenes.jsonl 职责, 一解析器两用）
- **brain**: 按板块过滤 / 按 beats[].emotion 聚合 / 渲染成"叙事时间线"喂 LLM 总结（§4.6）

### 4.5 gallery / progress.json（角色目录扩展, 2026-08-23 新增）

**gallery — AI 生成 2D 场景（图 + 文字信息成对）**：
```jsonc
// data/{char_id}/gallery/{scene_id}.json  ← 与 {scene_id}.png 同名成对
{
  "scene_id": "20260823_150412_cd34",
  "character_id": "igusa_haruka",
  "prompt": "遥香在天台上, 晚风, 微笑…",     // 生图 prompt（可复现）
  "description": "（场景描述: 情感氛围/构图）",
  "source_session": "20260823_143022_ab12",  // 来源会话（可回溯 events, 过滤 type=bond）
  "created_at": "2026-08-23T15:04:12.654321"
}
```
- 写入顺序约定：**先原子写 json（元数据）再落 png**（或反之）——`list_gallery` 只认"json+png 都存在的成对"，半套视为写入中断，可重试
- 未来生图管线（Phase 4）按此格式写；本设计只定 schema，不实现生图

**progress.json（角色根）— 聚合总轮数**：
```jsonc
// data/{char_id}/progress.json —— 所有 session 总对话轮数（门槛判断唯一真源）
// 替代全局 data/basic/bond_progress.json（迁移见 §八）
{ "rounds": 84, "updated_at": "2026-08-23T15:02:11.654321" }
```

### 4.6 session progress + brain 接口（2026-08-23 定稿）

**session 内 progress.json — 该时段聊天轮数**（展示用, 记录时 +1 落盘）：
```jsonc
// data/{char_id}/sessions/{session_id}/progress.json
{ "rounds": 15, "updated_at": "2026-08-23T15:02:11.654321" }
```
- 角色根 progress.json 是**唯一真源**（门槛判断）; session 内的是该时段计数（可从 events 校验, 但显式存免扫描）

**brain/wiki.json — 每角色 LLM WIKI（brain 消化 events 的产出）**：
```jsonc
// data/{char_id}/brain/wiki.json
{
  "schema_version": 1,
  "character_id": "igusa_haruka",
  "summary": "遥香近期主线: 天台夜谈后对老师信任加深…",
  "growth": ["学会主动道歉", "不再完全否定自己"],
  "relationship": {"affection": "上升", "key_events": ["天台夜谈", "拆弹事件"]},
  "updated_at": "2026-08-23T15:30:00.000000",
  "digested_through_seq": 47        // 已消化到 events seq（增量: 下次只消化 >47 的事件）
}
```

**brain 消化流程（每次 session 结束后触发）**:
```
输入:  该 session 的 events（seq > wiki.digested_through_seq）→ 渲染器转"叙事时间线 prompt"
        （含板块标签: 【MMT对话】【羁绊剧情】【L2D生成】）
处理:  主 LLM 消化 → 输出 WIKI 增量（成长/关系/好感度变化）
产出:  更新 wiki.json（merge 增量 + 推进 digested_through_seq）
检索:  远期 RAG 从 wiki.json + 最近 events 检索 → 注入 system prompt
```

---

## 五、生命周期

### 5.1 会话生命周期（marker 事件驱动, 无状态机）

```
session_start ──► MMT 轮（append mmt 事件）
   │  mmt_trigger_bond_story → append vn_enter{parent_session_id}
   ▼
VN 轮（append bond 事件 + vn_state marker 每场）──► vn_exit ──► 回 MMT
   │
   ▼
session_end{ended:true}（自然收尾 / 程序兜底 / 玩家退出）
中断 = 崩溃/断连时 session_end 写不出去——无标记即中断（§4.2 推导）
```

### 5.2 新建 MMT 会话

```
SessionStore.create(char_id, char_name)
  → 建目录 + 写 meta.json（纯索引, 无状态）
  → append marker session_start
  → 每轮 agent_turn 结束 append type=mmt 事件 + session progress
```

### 5.3 MMT → VN 衔接

```
mmt_trigger_bond_story 执行成功时:
  SessionStore.open_vn(parent_session_id, reason)
    → 新建 bond 子会话目录
    → meta{type: bond_story, character_id, ...}（纯索引）
    → append marker session_start + vn_enter{parent_session_id, reason}
    → 子会话独立 events.jsonl（VN 的事件流; 与根会话隔离, 保持现有语义）
```

### 5.4 VN 轮

```
每场 send_vn_scene 后:
  events.jsonl append 一个 type=bond 事件（含 beats/place/视觉字段）
  events.jsonl append marker vn_state（round/seed/visual —— 恢复点, 取最后一个）
  session progress.json 原子更新（rounds+1, 若 VN 也计轮）
```

### 5.5 VN 结束（自然收尾 / 程序兜底 / b 退出）

```
wrapup_after_vn(parent_session_id):
  子会话 append marker vn_exit + session_end{ended:true}
  根会话 append marker vn_exit（回 MMT）
  后续 MMT 轮 append 回根会话 events.jsonl（VN 期间的上下文不进 MMT 根——保持现有语义）
  （brain 消化在本 session 结束后触发, 见 §4.6）
```

### 5.6 中断（崩溃/断连）

- 崩溃点在哪，哪个文件最后没写完整——但 **events.jsonl 的 marker 序列**决定恢复路径：
  - 崩溃在 MMT 轮中 → 最后 marker 是 session_start（无 vn_enter）→ resume MMT
  - 崩溃在 VN 轮中 → 最后 marker 是 vn_state（有 vn_enter 无 vn_exit）→ resume VN（取最后 vn_state）

---

## 六、恢复流程（手动选择）

```
启动 → SessionStore.list_open()          // 扫 sessions/*/meta.json, 过滤未结束
  → 玩家选择 or 选"新会话"
  → SessionStore.resume(session_id):
      meta = load meta.json（纯索引）
      events = load events.jsonl（行级容错）
      markers = [e for e in events if e.type == "marker"]
      if 有 session_end marker: 不可恢复（只读回放, filter type=bond 渲染）
      # 1) 重建 LLM 上下文（events 重放 → render 消息, 不落盘消息）
      messages = render_events(events)
      if 无 vn_enter marker（或 vn_exit 在其后）:      // 在 MMT 中
          engine.start_session(meta.character_id)      // 重建 system（含注入）
          engine._history = messages
          继续 MMT loop
      else:                                            // 在 VN 中（vn_enter 无 vn_exit）
          vn_state = 最后一个 vn_state marker.payload
          parent = vn_enter.payload.parent_session_id
          vn = BondStoryEngine(characters_root, llm, director=build_director(char))
          vn.start_session(char_id)
          vn._history = messages
          i = vn_state.round; user_input = vn_state.seed
          继续 vn_cli 主循环（remind/end 提示按恢复后的 i 继续）
      # 2) rewind（可选, 免费能力）: 重放到 seq N = render_events(events[:N])
```

**要点**：恢复 = `start_session`（system 重建，已是现有逻辑）+ **重放 events → render 消息** +
扫描 markers 定位（MMT/VN/结束）。**不需要序列化 LLM 对象、不需要状态机**——LLM 是 stateless
的，上下文从事件流派生，状态从 marker 推导。重放几十行事件毫秒级完成。

---

## 七、原子性与容错

| 机制 | 实现 |
|------|------|
| meta/vn_state/progress 原子写 | `core/session/io.atomic_write_json`（temp 同目录 + os.replace，Windows 同卷原子） |
| events append | `append_jsonl`（`open("a")` 单行 json.dumps）；读时逐行 try/except，坏行丢弃（宁缺勿错） |
| 写失败 | 不阻断主流程（现有 try 包裹模式），降级为"本轮不记录" + logger.warning |
| 并发 | **单写者假设**（单进程 CLI）；未来 web 多会话各自写自己的目录，天然隔离 |

---

## 八、兼容与迁移（v0 旧档）

- 新读路径：`data/{char_id}/sessions/{session_id}/meta.json` 存在 = v1 会话
- 旧档识别：`data/saves/bond_story_*.json`（单文件 scenes[]）→ **只读回放**（`replay_bond_story` 读路径保留），不迁移写入
- `data/sessions/{char}_{ts}.json` 旧 MMT 档 → 只读（resume 旧逻辑保留），新写走 v1
- 迁移函数 `migrate_v0(path) -> SessionStore` 仅对"确实要续玩"的旧档做（v0 MMT 档可直接升级：包成角色目录 + meta + 事件流化 events.jsonl）
- **`data/basic/bond_progress.json`（全局聚合）→ 迁移为 `data/{char_id}/progress.json`**：读路径兼容（查不到角色文件时回退全局旧档），新写按角色落盘；`BondProgress` 类改按角色路径读写

---

## 九、实现计划（审完再动手）

### 模块划分

```
core/session/
  __init__.py        # re-export
  store.py           # SessionStore: create / open_vn / append_event / append_marker /
                     #   update_session_progress / finish(session_end) / list_open / resume
                     #   所有路径参数化 data_root（默认 data/）, 内部拼 data/{char_id}/sessions/…
  events.py          # Event dataclass + 板块 payload schema（mmt/bond/l2d/marker）+ from_dict 容错
  renderer.py        # render_events(events) → [{role, content}]（喂 LLM）; filter_bond（回放）;
                     #   markers(events)（状态推导）; render_timeline（brain 叙事时间线）
  models.py          # SessionMeta（纯索引）/ VNState（vn_state marker 的 payload）dataclass
  io.py              # atomic_write_json / append_jsonl / read_jsonl（行级容错）
```

### 引擎接入点（改动最小化）

| 位置 | 改动 |
|------|------|
| `core/momotalk.py` | `save_session/resume_session` 改走 SessionStore（保留旧函数签名兼容）；agent_turn 末尾 append type=mmt 事件 + session progress |
| `core/bond/bond_save.py` | `BondStorySave` 改为写 type=bond 事件 + 子会话 meta；保留 `load_save/list_saves` 旧接口（读旧档） |
| `core/bond/bond_progress.py` | `BondProgress` 读写改按角色 `data/{char_id}/progress.json`（回退全局旧档）✅ 已落地 |
| `core/ui/vn_cli.py` | `run_bond_story_vn` 接入子会话（round/seed/visual 落 vn_state.json）；`replay_bond_story` 从 events 过滤 type=bond |
| `main.py` / `mmt_preset.py` | 恢复入口：`list_open()` → 手动选择 → resume（events 重放 → render 消息） |
| `core/media/gallery.py`（新增, Phase 4 前仅建骨架） | `list_gallery(char_id)` 只认 json+png 成对；生图管线接入时再扩展 |
| `core/brain/`（新增, 远期） | `digest(session)` 读 events → 渲染时间线 → LLM 总结 → 更新 wiki.json（§4.6） |

### 测试（tests/core/test_session.py）

- store 生命周期：create → open_vn → append_event → finish → list_open 过滤
- 中断恢复：模拟写一半的 events.jsonl（坏行丢弃）、vn_state.json 旧值恢复（回退一场）
- renderer：事件流 → 消息往返（mmt 对 / bond 段落 / l2d 注记）; rewind = 渲染 events[:N]
- brain：digest 增量（digested_through_seq 推进）→ wiki.json merge
- 兼容：v0 单文件档只读 + MMT v0 resume
- 写失败降级：只读目录 → 不阻断

---

## 十、未决事项（实现前确认）

1. **VN 期间 MMT 根会话的 events 是否记录 VN 摘要**：现在 VN 上下文与 MMT 根隔离；恢复 VN 后 wrapup 回 MMT，根会话要不要一条"（角色完成了和老师的羁绊剧情）"摘要事件？——倾向：**记一条 type=mmt 摘要事件**（wrapup 时由 MMT agent_turn record_input=False 生成，现状已支持）
2. **事件流保留策略**：**全量保留 + brain 消化后延迟归档**（用户决策 2026-08-23）——旧 session 标记 archived 不压缩；等积累真大了再摘要化（YAGNI）
3. **jsonl 行大小**：bond story 段落很长（max_tokens 1536+），单行可能 >4KB——append 原子性在 Windows 上仍是"单次 write 系统调用"，json.dumps 后单次 fh.write 写入，风险低；若实测不稳再退化为"小块写入 + 行尾校验"
