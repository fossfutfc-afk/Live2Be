# MMT 聊天核心——完成指南（GUI 版，2026-08-25）

> 状态: **设计定稿, 待用户审阅后动手**。
> 目标: 在 webgui（FastAPI）上实现 MMT 聊天闭环——选学生 → 会话管理 → 真实引擎
> 对话 → 气泡渲染 → 触发 VN 标记。基于此前全部讨论（平行世界/并行多角色/单人
> 模式/好感/保存系统）整合, 衔接已有接口, 妥善处理边界。

## 1. 目标与范围

| 做 | 不做（后续里程碑） |
|---|---|
| 对话模式: 选学生 → 聊（真实 LLM 引擎） | VN 播放器（触发后仅标记/占位） |
| 会话管理: 新开世界线 / 恢复进行中会话 | SSE 流式（M1 轮询, M4 升级） |
| 事件流保存（已有）+ 好感联动（已有） | 论坛模式（左侧栏位已留） |
| 多角色并行 + 未读补全 | 表情包/图片气泡（send_media 渲染 M4） |

## 2. 架构总览（数据流）

```
前端(聊天窗) ──POST /api/mmt/chat──▶ 后端(mmt_chat 路由)
   ▲                                    │ 后台线程(每 char 一个任务)
   │ 轮询 GET /api/mmt/events(新seq)     ▼
   │                            引擎(MomoTalkEngine, 每 char 独立实例)
   │                               start/resume_session + agent_turn
   │                                    │ 真实 LLM（动作契约循环/重试/随机事件）
   │                                    ▼
   └────────── 事件流 events.jsonl（append, 唯一真源）◀─ 引擎落库
                   （bond 闭环后 digest 提炼 → wiki + 好感 affection 事件）
```

## 3. 已有资产（复用, 不重造）

| 资产 | 位置 | 用法 |
|---|---|---|
| 引擎 | `core/momotalk.py` `MomoTalkEngine` | `MomoTalkEngine(char_root, llm, store=SessionStore)` |
| 会话创建 | `store.create(char_id)` → meta | 新世界线 |
| 会话恢复 | `engine.resume_session(char_id, sid)` | 含 brain 记忆注入（resume 只注入不消化, 平行世界——digest 只在 bond 闭环, 见 core/DESIGN_BRAIN.md） |
| 进行中列表 | `store.list_open()` → [SessionMeta] | 判断"恢复 or 新开" |
| 一轮对话 | `engine.agent_turn(text)` → TurnResult | `steps/reply/actions/bond_story` |
| 事件流 | `store.events(char_id, sid)` | 渲染历史 + 轮询新回复 |
| 好感 | `load_affection_from_events` | 列表已接（digest 后自动更新） |
| 玩家名 | `load_player_name()`（mmt_preset） | 注入/显示 |
| 单人模式 | 已写进 momotalk_rules.md | LLM 不扮多角 ✅ |

## 4. 核心流程（一轮对话）

```
玩家在聊天窗输入 → 发送:
  1. 前端: 输入禁用(等待中) + 玩家气泡上屏 + POST /api/mmt/chat
       {char_id, session_id, text}
  2. 后端: 校验(会话存在/非VN/非空文本) → 起后台任务(该 char 的任务队列, 串行)
  3. 任务: engine.agent_turn(text)
       - TurnResult.bond_story=True → VN 触发（vn_enter marker 已落）→ 返回标记
       - 正常 → 事件流已有新 mmt 事件（引擎落库）
  4. 前端: 轮询 GET /api/mmt/events?since=lastSeq（1s 间隔）
       → 新事件(角色回复, 可多动作/多气泡) → 上屏 → 清等待态
  5. 异常(LLM 失败/循环超限): 后端捕获 → 返回错误气泡 + 前端恢复输入
```

## 5. 会话管理（新开 / 恢复 / 世界线）

**决策（平行世界语义）**:

```
点学生(对话模式) → 后端查 store.list_open() 里该 char 的进行中会话:
  - 有 → 自动恢复（resume_session: brain 记忆注入 + 重建历史——注入不消化,
       digest 只在 bond 剧情闭环后）→ 继续
  - 无 → 新开世界线（store.create + engine.start_session + attach_session）
  - 聊天窗顶部「新世界线」按钮 → 显式开新线（旧世界线保留, 可在回放里看到——未来）
```

- 恢复 = 玩家预期（点开继续上次）; 新世界线 = 显式操作（平行世界语义）
- 已结束（ended）会话不恢复（`resume_session` 已拒绝）

## 6. 后端设计（webgui/routers/mmt.py 扩展 + 新文件）

```
webgui/routers/mmt.py        # 列表（已有）+ 以下新增
webgui/chat.py               # 聊天域: 引擎管理 + 后台任务 + 轮询接口（新文件, 不堆路由）
```

### 6.1 引擎管理（并行多角色——之前讨论的方案2: 每角色独立上下文）

```python
# webgui/chat.py
_engines: dict[str, MomoTalkEngine] = {}     # char_id → 引擎实例（内存, 单用户本机）
_locks: dict[str, threading.Lock] = {}       # char_id → 串行锁（同角色轮询串行）
```
- 每 char 独立引擎实例（`_history`/`_system_prompt` 内存状态互不干扰）
- 同 char 串行（锁）; 不同 char 并行（各自线程跑 agent_turn——真实 LLM 并发 OK）
- **切换角色不取消后台任务**（回复继续跑, 完成后落库）——落库靠事件流, 前端切回拉取

### 6.2 接口

```
POST /api/mmt/chat          {char_id, session_id, text}
   → 202 {accepted} 或错误; 后台线程跑 agent_turn
GET  /api/mmt/session?char_id={cid}
   → {session_id, history: [事件渲染], in_vn: bool, display_name}
   （进入聊天窗时: 确定恢复/新开 + 拉历史）
POST /api/mmt/new_world     {char_id} → 新世界线（store.create + 绑引擎）
GET  /api/mmt/events?char_id&session_id&since={seq}
   → {events: [seq>since 的 mmt 事件], last_seq, in_vn}
   （轮询用; 回复完成 = 出现新 assistant 侧 mmt 事件）
```

### 6.3 事件渲染（历史气泡）

`render_events`（已有, core/session/renderer.py）输出 LLM 消息格式——前端气泡用
**事件流原始 mmt 事件**（`payload.player` / `payload.reply`）渲染更直接:
```python
# 渲染器: mmt 事件 → [{side: player|char, text, seq}]（send_media 事件 M4 再渲染图片）
```

## 7. 前端设计（mmt.js 扩展）

```
聊天窗(#mmt-chat-window):
  顶部: 学生名 + 「新世界线」按钮 + ❤好感
  中部: 气泡滚动区（玩家右粉 / 角色左白）——打字指示(等待中)
  底部: 输入框 + 发送按钮（等待中禁用; 空文本禁发）
```
- 进入聊天窗: GET session（恢复 or 新开）→ 渲染历史气泡 → 轮询开始
- 未读: 切换走时记录该 char 最后已读 seq → 切回时补拉 + 列表条目未读红点
  （对话模式列表条目右上角小红点——"遥香有新消息"）
- VN 触发（bond_story=True）: 聊天窗显示全屏占位"进入羁绊剧情——VN 播放器建设中",
  输入禁用（VN 独占）; 事件流已有 vn_enter——未来 VN 播放器从这里 resume

## 8. 边界情况处理表（核心）

| # | 边界 | 处理 |
|---|---|---|
| 1 | **等待回复时切其他角色** | 每 char 独立引擎 + 后台继续跑; 回复落库; 切回拉取补全 + 未读红点 |
| 2 | **等待中重复发送** | 前端输入禁用直到回复完成（同 char 串行锁兜底） |
| 3 | **空消息/纯空白** | 前端 trim 禁发 + 后端 400 |
| 4 | **LLM 失败/循环超限** | 引擎内部重试耗尽抛 MmtLoopError → 后端捕获 → 错误气泡 + 恢复输入（允许重发） |
| 5 | **刷新/断线（SSE 未接, 轮询天然恢复）** | 事件流持久化 → 重新进聊天窗 GET session 拉全量 → 恢复渲染 |
| 6 | **进行中会话 vs 新开** | §5 决策（自动恢复 + 显式新世界线按钮） |
| 7 | **VN 中** | 聊天窗禁用 + 占位; vn_enter 已落库（未来 VN 播放器 resume; ended 拒绝恢复已有） |
| 8 | **同 char 双标签页同时发** | 后端 char 锁串行（第二个排队或 409 提示）——单用户本机, 锁够用 |
| 9 | **digest 触发时机** | 唯一触发点 = bond 剧情闭环（async_digest, 引擎已做）; resume 只注入不消化; 聊天进行中/中断剧情不 digest（控成本 + 防记忆污染） |
| 10 | **好感刷新** | digest 后 affection 事件落库 → 列表接口实时算（已有）→ 聊天窗顶部❤切回时刷新 |
| 11 | **随机事件（want_to_speak）** | 引擎 agent_turn 已内置钩子（store 注入后自动）→ GUI 零额外 |
| 12 | **触发 VN 后玩家想回 MMT** | M3 阶段: VN 播放器未做 → 触发后该会话 in_vn 状态; 列表/聊天窗显示
     状态标识; 回 MMT 由未来 VN 播放器 vn_exit 后恢复（事件流标记已有, 不丢数据） |

## 9. 保存系统（衔接现状, 不加新东西）

```
events.jsonl（唯一真源, append-only）: mmt 事件 + marker + affection 事件 —— 已有
wiki.json（派生缓存）: digest 提炼 + 好感缓存 —— 已有
player.json（玩家名）: 已有
会话元数据 meta.json: created_at/ended —— 已有（list_open 用它判"进行中"）
```
- **聊天核心不引入新存储格式**——一切落事件流（引擎已做）
- 会话结束（bond 剧情闭环: vn_exit completed → finish）→ digest 触发点（async_digest, 已实现）→ 好感更新

## 10. 分步实施（一步一步, 每步可验证）

**M1: 最小闭环（一个学生聊起来）**
1. `webgui/chat.py`: 引擎管理（_engines/_locks）+ `open_session(char_id)`（恢复/新开）
2. 路由: `POST /api/mmt/chat`（后台线程 agent_turn + 异常捕获）+ `GET /api/mmt/events`
3. 前端: 聊天窗渲染（历史气泡 + 输入 + 发送 + 轮询 + 等待态）
4. 验证: 真实 LLM 和遥香聊一轮（事件流落库 + 气泡上屏 + 刷新后历史完整）

**M2: 会话完整性**
1. 「新世界线」按钮 + 恢复优先逻辑（list_open）
2. 未读红点（切走记录 last_seq + 列表标记）
3. 验证: 恢复会话（brain 注入生效——角色记得世界线的事）+ 新世界线从零开始

**M3: VN 触发标记**
1. bond_story=True → 聊天窗占位 + 输入禁用 + 事件流 vn_enter 确认
2. 验证: 聊到触发 bond → 占位提示 + 列表状态标识（in_vn）

**M4: 打磨（后续）**
1. SSE 推送（借鉴 web/ 的 hub runner 模式）替代轮询
2. send_media 图片气泡渲染
3. VN 播放器（独立里程碑——GUI 版 vn_cli）

## 11. 待你确认的点

1. **恢复策略**: 自动恢复进行中会话 + 显式「新世界线」按钮（§5）——OK?
2. **轮询起步**: M1 用 1s 轮询（简单可靠）, M4 再上 SSE——OK?
3. **VN 触发后**: M3 只做占位标记（VN 播放器独立里程碑）——OK?
4. **引擎实例**: 内存 map（每 char 一个引擎）——重启服务丢内存状态但事件流在
   （重新进聊天窗 = resume 重建）——可接受?

---

确认后按 M1 → M2 → M3 实施, 每步跑全量 + 真机验证。
