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
    progress.json                 # 羁绊进度（按角色, 替代全局 bond_progress.json）
    sessions/
      {session_id}/               # 一次完整互动 = 一个会话目录
        meta.json                 # 小而稳：schema_version / type / 状态机 / 关联
        history.jsonl             # LLM 上下文消息（append-only）
        scenes.jsonl              # bond 叙事记录（逐场 append，回放/画廊源）
        vn_state.json             # VN 恢复点——仅 VN 进行中写（state==paused 时存在）
    gallery/                      # AI 生成 2D 场景（图 + 文字信息成对, §4.5）
      {scene_id}.png              # 生成图
      {scene_id}.json             # 文字信息（prompt / 场景描述 / 来源会话 / 时间戳）
    brain/                        # Virtual Brain（远期规划, 按角色隔离）
```

| 文件 | 职责 | 写入方式 | 中断语义 |
|------|------|----------|----------|
| `meta.json` | 会话元数据 + 状态机 | 原子写（temp+replace），**每次状态变化** | 状态机推进是低频小写，原子替换永不半写 |
| `history.jsonl` | LLM 上下文 | `open("a")` 每轮一行 JSON | 行级原子（单行 <4KB 安全）；读时行级 try/except 丢弃坏行 |
| `scenes.jsonl` | 叙事记录 | 同上逐场 append | 同上；丢弃最后半行（最多丢半场） |
| `vn_state.json` | VN 恢复点 | 原子写，每场 VN 轮更新 | 同上；旧 vn_state 仍可恢复（最多回退一场） |
| `progress.json` | 羁绊轮数（按角色） | 原子写（低频） | 原子替换，永不半写 |
| `gallery/{scene_id}.json` | 生成图元数据 | 原子写（生成一次） | 原子替换；png 先落盘再写 json 或反之（§4.5） |

---

## 四、Schema

### 4.1 meta.json

```jsonc
{
  "schema_version": 1,
  "session_id": "20260823_143022_ab12",   // 角色目录内唯一: {YYYYMMDD_HHMMSS}_{rand4}（char 由目录隔离）
  "type": "momotalk",              // momotalk | bond_story
  "character_id": "igusa_haruka",
  "character_name": "伊草 遥香",
  "state": "active",               // active(mmt 中) | paused(vn 中) | ended | interrupted
  "parent_session_id": null,       // bond 子会话 = 所属 MMT 会话 id; 根会话 = null
  "created_at": "2026-08-23T14:30:22.123456",
  "updated_at": "2026-08-23T15:02:11.654321",
  "trigger_reason": "老师约我放学后见面"   // bond 子会话触发原因; 根会话可空
}
```

### 4.2 history.jsonl（LLM 上下文）

每行一条消息（与 `core/momotalk.py` / `core/bond/bond_story.py` 的 `messages` 同构）：

```jsonl
{"role":"user","content":"你好呀，今天过得怎么样？"}
{"role":"assistant","content":"[mmt_chat] 啊、老师…今天也、也在认真跑腿…"}
{"role":"system","content":"（系统）剧情已推进 15 轮…"}   // system_note 也可记（若需精确复原上下文）
```

- **system_prompt 不落盘**——由 `char_id + type` 重建（momotalk/bond 的 `start_session` 已是重建逻辑，含世界观/人际/词表注入）
- 轮记：每轮结束把**该轮新增的消息**追加写入

### 4.3 scenes.jsonl（叙事记录）

每行一个场景（`BondScene.to_dict()` 同构）：

```jsonl
{"seq":1,"input":"（旁白）基于「…」……","paragraphs":["…"],"choices":["…"],"picked":"…","is_end":false,"background":"class_room","audio":null,"beats":[{"text":"…","emotion":"embarass"}],"place":"class_room"}
```

- 回放源：`replay_bond_story` 读此文件（一解析器两用，保持现状）
- **只写在 bond 子会话**；MMT 根会话无此文件

### 4.4 vn_state.json（VN 恢复点）

```jsonc
{
  "round": 12,                     // 当前第几场（vn_cli 的 i）
  "seed": "（玩家上一场的选择文本）",   // 下一场 user_input
  "completed": false,
  "force_after": 32,               // end_rounds+2（恢复后继续计数用）
  "visual": {"background": "class_room", "audio": null},  // 导演 VisualState.to_dict()
  "scenes_flushed": 12             // scenes.jsonl 已写场数（对齐校验）
}
```

### 4.5 gallery / progress.json（角色目录扩展, 2026-08-23 新增）

**gallery — AI 生成 2D 场景（图 + 文字信息成对）**：
```jsonc
// data/{char_id}/gallery/{scene_id}.json  ← 与 {scene_id}.png 同名成对
{
  "scene_id": "20260823_150412_cd34",
  "character_id": "igusa_haruka",
  "prompt": "遥香在天台上, 晚风, 微笑…",     // 生图 prompt（可复现）
  "description": "（场景描述: 情感氛围/构图）",
  "source_session": "20260823_143022_ab12",  // 来源会话（可回溯 scenes.jsonl）
  "created_at": "2026-08-23T15:04:12.654321"
}
```
- 写入顺序约定：**先原子写 json（元数据）再落 png**（或反之）——`list_gallery` 只认"json+png 都存在的成对"，半套视为写入中断，可重试
- 未来生图管线（Phase 4）按此格式写；本设计只定 schema，不实现生图

**progress.json — 羁绊进度（按角色）**：
```jsonc
// data/{char_id}/progress.json —— 替代全局 data/basic/bond_progress.json（迁移见 §八）
{ "rounds": 84, "updated_at": "2026-08-23T15:02:11.654321" }
```

---

## 五、生命周期

### 5.1 状态机

```
创建 ──► active（MMT 中）
           │  mmt_trigger_bond_story
           ▼
        paused（VN 中）─────────► vn 结束(wrapup) ──► active（回 MMT）
           │
           └─ 玩家 b 退出 VN ──► active（回 MMT, scenes 已留痕）
 ended（自然收尾）
 interrupted（崩溃/断连——下次启动时由玩家手动 resume）
```

### 5.2 新建 MMT 会话

```
SessionStore.create(char_id, char_name)
  → 建目录 + 写 meta.json{state: active}
  → start_session 后每轮 agent_turn 结束 append history.jsonl
```

### 5.3 MMT → VN 衔接

```
mmt_trigger_bond_story 执行成功时:
  SessionStore.open_vn(parent_session_id, reason)
    → 新建 bond 子会话目录
    → meta{type: bond_story, parent_session_id, state: paused, trigger_reason}
    → 子会话独立 history.jsonl（VN 的 LLM 上下文）
    → 根会话 meta.updated_at 更新（不改变根会话 state）
```

### 5.4 VN 轮

```
每场 send_vn_scene 后:
  scenes.jsonl append 一场
  vn_state.json 原子更新（round/seed/visual/completed）
  history.jsonl append 该轮消息
```

### 5.5 VN 结束（自然收尾 / 程序兜底 / b 退出）

```
wrapup_after_vn(parent_session_id):
  子会话 meta.state = ended
  根会话 meta.state = active（回到 MMT）
  后续 MMT 轮 append 回根会话 history.jsonl（VN 期间的上下文不进 MMT 根——保持现有语义）
```

### 5.6 中断（崩溃/断连）

- 崩溃点在哪，哪个文件最后没写完整——但 **meta.json 状态机在崩溃前一刻的值**决定恢复路径：
  - 崩溃在 MMT 轮中 → 根会话 state=active，history.jsonl 最后半行丢弃 → resume MMT
  - 崩溃在 VN 轮中 → 子会话 state=paused，vn_state.json 是上一场的值（最多回退一场）→ resume VN

---

## 六、恢复流程（手动选择）

```
启动 → SessionStore.list_open()          // state ∈ {active, paused} 的会话（按 updated_at 倒序）
  → 玩家选择 or 选"新会话"
  → SessionStore.resume(session_id):
      meta = load meta.json
      # 1) 重建 LLM 上下文
      if meta.type == "momotalk":
          engine.start_session(meta.character_id)        // 重建 system（含注入）
          engine._history = load history.jsonl（行级容错）
          if meta.state == "active": 继续 MMT loop
      elif meta.type == "bond_story":
          parent_meta = load meta.parent_session_id
          # 重建 VN: BondStoryEngine + director
          vn = BondStoryEngine(characters_root, llm, director=build_director(char))
          vn.start_session(char_id)
          vn._history = load 子会话 history.jsonl
          vn_state = load vn_state.json
          i = vn_state.round; user_input = vn_state.seed
          # 恢复 recorder（scenes.jsonl 已有场数 → 续记）
          # 继续 vn_cli 主循环（remind/end 提示按恢复后的 i 继续）
```

**要点**：恢复 = `start_session`（system 重建，已是现有逻辑）+ 载入 history + 载入 vn_state。**不需要序列化 LLM 对象**——LLM 是 stateless 的，上下文在 history.jsonl 里。

---

## 七、原子性与容错

| 机制 | 实现 |
|------|------|
| meta/vn_state 原子写 | 复用 `_atomic_write_json`（temp 同目录 + os.replace，Windows 同卷原子） |
| history/scenes append | `open("a", encoding="utf-8")` 单行 json.dumps；读时逐行 try/except，坏行丢弃（宁缺勿错） |
| 写失败 | 不阻断主流程（现有 try 包裹模式），降级为"本轮不记录" + logger.warning |
| 并发 | **单写者假设**（单进程 CLI）；未来 web 多会话各自写自己的目录，天然隔离 |

---

## 八、兼容与迁移（v0 旧档）

- 新读路径：`data/{char_id}/sessions/{session_id}/meta.json` 存在 = v1 会话
- 旧档识别：`data/saves/bond_story_*.json`（单文件 scenes[]）→ **只读回放**（`replay_bond_story` 读路径保留），不迁移写入
- `data/sessions/{char}_{ts}.json` 旧 MMT 档 → 只读（resume 旧逻辑保留），新写走 v1
- 迁移函数 `migrate_v0(path) -> SessionStore` 仅对"确实要续玩"的旧档做（v0 MMT 档可直接升级：包成角色目录 + meta + history.jsonl）
- **`data/basic/bond_progress.json`（全局聚合）→ 迁移为 `data/{char_id}/progress.json`**：读路径兼容（查不到角色文件时回退全局旧档），新写按角色落盘；`BondProgress` 类改按角色路径读写

---

## 九、实现计划（审完再动手）

### 模块划分

```
core/session/
  __init__.py        # re-export
  store.py           # SessionStore: create / open_vn / append_history / append_scene /
                     #   update_vn_state / finish / list_open / resume（读路径）
                     #   所有路径参数化 data_root（默认 data/）, 内部拼 data/{char_id}/sessions/…
  models.py          # SessionMeta / VNState dataclass + to_dict/from_dict（容错）
  io.py              # atomic_write_json / append_jsonl / read_jsonl（行级容错）
```

### 引擎接入点（改动最小化）

| 位置 | 改动 |
|------|------|
| `core/momotalk.py` | `save_session/resume_session` 改走 SessionStore（保留旧函数签名兼容）；agent_turn 末尾 append history |
| `core/bond/bond_save.py` | `BondStorySave` 改为写 scenes.jsonl + 子会话 meta；保留 `load_save/list_saves` 旧接口（读旧档） |
| `core/bond/bond_progress.py` | `BondProgress` 读写改按角色 `data/{char_id}/progress.json`（回退全局旧档） |
| `core/ui/vn_cli.py` | `run_bond_story_vn` 接入子会话（round/seed/visual 落 vn_state.json）；`replay_bond_story` 支持 scenes.jsonl |
| `main.py` / `mmt_preset.py` | 恢复入口：`list_open()` → 手动选择 → resume |
| `core/media/gallery.py`（新增, Phase 4 前仅建骨架） | `list_gallery(char_id)` 只认 json+png 成对；生图管线接入时再扩展 |

### 测试（tests/core/test_session.py）

- store 生命周期：create → open_vn → append → finish → list_open 过滤
- 中断恢复：模拟写一半的 history.jsonl（坏行丢弃）、vn_state.json 旧值恢复（回退一场）
- 兼容：v0 单文件档只读 + MMT v0 resume
- 写失败降级：只读目录 → 不阻断

---

## 十、未决事项（实现前确认）

1. **VN 期间 MMT 根会话的 history 是否记录 VN 摘要**：现在 VN 上下文与 MMT 根隔离；恢复 VN 后 wrapup 回 MMT，根会话要不要一条"（角色完成了和老师的羁绊剧情）"摘要？——倾向：**记一条系统摘要**（wrapup 时由 MMT agent_turn record_input=False 生成，现状已支持）
2. **history.jsonl 保留策略**：全量（现状 20 轮滑动窗口只在运行时截断，存档全量）vs 存档也滑动+摘要（协议 3.2 远期）——本轮**全量**，摘要留给 Virtual Brain
3. **jsonl 行大小**：bond story 段落很长（max_tokens 1536+），单行可能 >4KB——append 原子性在 Windows 上仍是"单次 write 系统调用"，json.dumps 后单次 fh.write 写入，风险低；若实测不稳再退化为"小块写入 + 行尾校验"
