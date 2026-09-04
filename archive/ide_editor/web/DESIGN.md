# Live2Be IDE Agent Web GUI — 设计文档

> 状态：**已实现**（2026-08-20）。本文档保留为实现期的唯一设计依据；
> 回归见 `web/_server_test.py`（mock 模式全链路：批准/拒绝/中止/409/auto-approve）。

## 1. 背景与目标

ide/ 子项目的 IDE 角色撰写 agent（`IDEAgent`）目前是纯 CLI：阻塞 `input()` 审批、`print()` 输出、一轮跑到底。目标是给 IDE agent 配一个 Web GUI（fastapi + SSE + 纯 vanilla JS 单页）。

**范围硬约束**：
- 只做 IDE agent 的 GUI；主项目 MomoTalk / Bond Story 不动。
- GUI 只是壳——**契约层 contract/、执行层 ide/ide_executor、agent 循环一行不改**。
- 不引入前端构建链（无 npm/vite，纯原生 JS）。

**Phase 2 已完成的前置**：`IDEAgent` 已改为 emit/ask 回调驱动（[ide/ide_agent.py](../ide/ide_agent.py)），CLI 默认回调逐字节复刻历史输出。GUI 只需要注入**队列实现的回调**，事件模型 `ide/ide_events.py` 已定义好全部 `AgentEventKind`。

## 2. 决策记录（讨论结论）

| # | 决策点 | 结论 |
|---|---|---|
| 1 | 自动审批 | **加入，带取消窗口**：auto_approve 开启时，提议发出 2s 内无人操作 → 自动 approve；期间点 [拒绝]/[中止] 优先。纯注入回调层实现，引擎零改动 |
| 2 | 会话隔离 | **不做**。多标签页共享单 agent 实例 + 全局事件流（天然一致）。但**服务级隔离必须做**——hub 从第一天按 channel 分频道，IDE 与未来角色扮演互不串流 |
| 3 | reconnect 语义 | 新订阅从当前时刻开始，**不重放历史**。IDE 对话量小，未来需要再扩展 session 保存（参照主项目 `data/sessions/`） |
| 4 | 输入阻塞 | turn 运行期间禁用输入框 + 发送按钮（"AI 思考中…"），DONE/ABORTED 后恢复；服务端再兜 409 |
| 5 | mock 模式 | **加入**：`IDE_MOCK=1` 启动 → 注入 StubLLM，固定走"提议→审批→执行"脚本，不烧 API 即可试 UI。本质是"关键字→动作"的胶水，未来可演化为指令系统 |
| 6 | 素材预览 | IDE GUI 不做差分渲染（素材是 Bond Story 侧的事，手动维护） |
| 7 | abort 语义 | 中止只在决策点/步骤间隙生效；LLM 阻塞调用不可线程取消。前端如实展示"中止请求已发，将在下个决策点生效" |

## 3. 目录结构

```
web/
  __init__.py
  DESIGN.md        # 本文档
  hub.py           # EventHub：线程安全事件缓冲 + 订阅者游标 + channel
  runner.py        # AgentRunner：单 IDEAgent + turn 串行化 + ask 桥 + auto-approve
  app.py           # FastAPI：路由 + lifespan + mock 开关
  mock.py          # StubLLM（IDE_MOCK=1 时的 mock 模式）
  _server_test.py  # 回归测试（mock 模式全链路）
  __main__.py      # python -m web → uvicorn.run(app)
  static/
    index.html
    app.js
    style.css
```

依赖：live2be env 安装 `fastapi` + `uvicorn`（不加 `[standard]`，纯 asyncio 即可）。

## 4. 并发模型

```
浏览器                     FastAPI (asyncio)              工作线程 (daemon)
  │ POST /api/turn              │                              │
  │ ──────────────────────────▶ │ lock.acquire(blocking=False) │
  │                             │   ✗ 忙 → 409                 │
  │                             │   ✓ 成功 → Thread(...).start()│─▶ agent_turn()
  │                             │                              │    emit(evt)
  │ GET /api/events (SSE)       │◀──── hub.publish(ch, evt) ────┤
  │ ◀── data: {json}\n\n ───────│   (轮询 cursor, 50ms)          │
  │                             │                              │    ask(aid, prompt)
  │ POST /api/approve           │                              │ ◀── decision_q.get(timeout=1s)
  │ ───────{aid, decision}─────▶│──── decision_q.put ──────────▶│     └ 超时→auto_approve / abort
  └─────────────────────────────┘                              └ 锁释放 → busy=False
```

三个关键设计，均已被 CourSelection 项目验证或简化：

### 4.1 事件桥 — 轮询游标，不做 to_thread

参考 CourSelection 的 `SseQueue`（[app.py `api_advise_stream`](D:/CODE/CourSelection.fin/server/app.py#L525)）：worker 线程 `put` 进线程安全缓冲，async 消费端 **`asyncio.sleep(0.05)` 轮询**。agent 事件是离散的（非逐 token），50ms 轮询足够，**不需要 `asyncio.to_thread(q.get)`**——省掉非主线程碰 asyncio 的问题。

为支持多标签页，用**共享缓冲 + 每连接游标**取代每请求一个队列：

```python
class EventHub:
    def __init__(self):
        self._events: list[dict] = []
        self._lock = threading.Lock()
    def publish(self, evt: dict) -> None:      # 线程安全; worker 线程调用
        with self._lock:
            self._events.append(evt)
    def snapshot(self, cursor: int) -> tuple[list[dict], int]:
        with self._lock:                        # SSE 生成器轮询调用
            return list(self._events[cursor:]), len(self._events)
```

**没有订阅/退订对象**——SSE 连接只持有一个本地游标，断开即生成器结束，无全局残留可泄漏。这比"订阅者队列 + finally unsubscribe"更简单（Cursor 模式自带生命周期管理）。

- channel：`HUBS.get(channel)` 惰性创建 `EventHub` 实例。IDE 用 `"ide"`，未来角色扮演用别的频道，互不串流。
- 缓冲无上限（IDE 事件量小）。若未来长期运行可加封顶丢旧——但注意会让未消费游标失效，v1 不做。

### 4.2 ask 桥 — 轮询 decision_q + 超时护栏

worker 线程阻塞在 `decision_q.get(timeout=1.0)`，每秒醒来检查一次超时/auto-approve：

```python
def _ask(self, approval_id: str, prompt: str) -> ApprovalDecision:
    started = time.monotonic()
    while True:
        elapsed = time.monotonic() - started
        try:
            aid, decision = self._decisions.get(timeout=1.0)
        except queue.Empty:
            if self._auto_approve and elapsed >= self._auto_delay:
                return "approve"
            if elapsed >= ASK_TIMEOUT:          # 默认 300s
                return "abort"                  # ★ 防 worker 死锁, 见风险
            continue
        if aid == approval_id:                  # 只认当前审批实例的决策
            return decision
        # 过期/其他审批实例的决策 → 忽略
```

- **auto-approve 取消窗口**：elapsed >= auto_delay（默认 2s）且无人决策 → 自动 approve。窗口内用户点击 → 优先。
- **ASK_TIMEOUT → abort**：页面被关/无人响应时，worker 不会永久占锁导致后续 turn 全部 409。这是最关键的一条护栏。
- 决策校验放 app 层：`decision ∈ {approve, reject, abort}`，`approval_id` 必填。

### 4.3 turn 串行化

`threading.Lock` 非阻塞 `acquire(blocking=False)`，失败 → 409。单 agent 实例，turn 天然串行。锁在 `finally` 释放 + `busy=False`。

### 4.4 SSE 响应

```python
StreamingResponse(event_stream(), media_type="text/event-stream", headers={
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
})
```
- 每 50ms 轮询 cursor，有新事件 → `data: {json.dumps(evt, ensure_ascii=False)}\n\n`
- 每 15s 发 `: ping\n\n` 保活（中间件/代理断开兜底）
- 无 done 哨兵——连接保持到客户端关闭（reconnect 由 EventSource 自动重连）

## 5. 端点契约

| 方法/路径 | 请求体 | 响应 | 用途 |
|---|---|---|---|
| `GET /` | — | index.html | 单页 |
| `GET /api/events?channel=ide` | — | SSE 流 | 事件流（含 PENDING_APPROVAL） |
| `POST /api/turn` | `{"message": str}` | 200 / 409 | 提交一轮 agent 对话 |
| `POST /api/approve` | `{"approval_id": str, "decision": "approve\|reject\|abort"}` | 200 / 400 | 审批决策 → ask 队列 |
| `POST /api/auto_approve` | `{"enabled": bool, "delay_s": float?}` | 200 | 自动审批开关 + 窗口时长 |
| `GET /api/status` | — | `{"busy", "auto_approve", "auto_delay"}` | 前端初始化/轮询同步 |

- 409 语义：已有 turn 在跑。前端收到 409 应提示"上一轮还没结束"。
- `POST /api/turn` 的 message 为空 → 400。

## 6. 事件 → UI 映射

`AgentEventKind`（[ide/ide_events.py](../ide/ide_events.py)）→ 前端渲染：

| kind | UI 元素 |
|---|---|
| `THINKING` | 顶部转圈"思考中…" |
| `AI_MESSAGE` | 聊天气泡 `[AI] …` |
| `PENDING_APPROVAL` | **提议卡片**：summary + diff(`<pre>` 等宽) + [✓批准][✗拒绝][■中止]；记录 `approval_id`；auto_approve 开时显示"N 秒后自动批准" |
| `EXEC_RESULT` | 状态行 `[已执行]/[执行失败] …` |
| `DECISION` | 状态行 `[已拒绝]`/`[已中止本轮]` |
| `ABORTED` | 状态行 + **恢复输入** |
| `DONE` | 聊天气泡 `[AI] …` + **恢复输入** |
| `TOOL_START/RESULT/ERROR` | 状态行 `[search 关键词] 已获取 N 字符` |
| `INVALID_ACTION` / `LLM_ERROR` / `PLAN_ERROR` | 低调状态行（错误回灌给 LLM 自行修正） |

`DONE`/`ABORTED` 是唯一两个"恢复输入"的信号。

## 7. 前端（vanilla JS）

布局（单页三区）：

```
┌────────────────────────────────────────────┐
│ 任务输入: [用自然语言描述需求…] [发送]  [⚙自动] │  ← busy 时禁用
├────────────────────────────────────────────┤
│  事件流（滚动日志）                          │
│    🤔 思考中…                              │  ← THINKING
│    [AI] 已根据你的需求创建了 profile.yml…    │  ← AI_MESSAGE
│    ┌ 提议卡片 ──────────────────┐           │
│    │ 创建测试酱的 profile.yml    │  [✓批准]  │  ← PENDING_APPROVAL
│    │ - a                       │  [✗拒绝]  │      (auto: 倒计时)
│    │ + b                       │  [■中止]  │
│    └────────────────────────────┘           │
│    [已执行] 已创建角色 real_oc_test          │  ← EXEC_RESULT
│    [AI] 五件套已写入                         │  ← DONE (恢复输入)
├────────────────────────────────────────────┤
│  状态栏: 运行中 / 等待审批 / 空闲             │
└────────────────────────────────────────────┘
```

- **EventSource** 收事件，按 `data.kind` 分发（映射表见 §6）；`data.approval_id` 存进卡片。
- **busy 状态**：发送 turn 后立即置 busy（禁用输入）；`DONE`/`ABORTED` 事件或 `/api/status` 同步恢复。加载页面时先 `GET /api/status` 对齐。
- **审批**：点按钮 → `POST /api/approve` → 卡片置灰；auto_approve 倒计时用 `setInterval` 更新，按钮点击时清除。
- 无构建链：`EventSource` + `fetch` + DOM 操作。

## 8. mock 模式

`IDE_MOCK=1` 环境变量启动时，`app.py` 用 StubLLM（复用 tests/ide/test_events.py 的脚本模式）替代 `LLMClient`，固定产出：
`THINKING → AI_MESSAGE → PENDING_APPROVAL → (审批) → EXEC_RESULT → THINKING → AI_MESSAGE → DONE`。

前端对 mock 无感知。便于无 API 成本验证 UI 全部交互路径（批准/拒绝/中止/409/auto-approve/重连）。

## 9. 风险与已知边界

1. **ask 超时必须 abort**：否则 worker 永久占锁 → 后续全部 409。已由 ASK_TIMEOUT 护栏覆盖。
2. **LLM 调用不可取消**：abort 只在决策点/步骤间隙生效；LLM 阻塞期间前端只能展示"中止将在下个决策点生效"。
3. **多标签页 = 同一流**：一个标签页操作，其他标签页实时看到相同事件（含审批）。这是特性不是 bug。
4. **SSE 轮询开销**：每连接每 50ms 一次 `snapshot()`（锁 + 切片）。连接数小，可接受。
5. **API 逆向风险**：仅影响 `tools/fetch_kivo.py`（已 gitignore），IDE GUI 不依赖 kivo API。

## 10. 未来扩展（现在不做）

- **session 保存/恢复**：IDE 对话持久化，参照主项目 `data/sessions/`（MMT 的 Session to_json/from_json）。
- **历史回放 reconnect**：SSE 重连带最近 N 条回放。
- **关键字指令系统**：mock 模式（StubLLM + 关键字→动作）演化为真正的本地指令层，无需 LLM 即可驱动 agent。
- **角色扮演频道**：`channel=roleplay` + 独立 runner（core/momotalk 引擎），与 IDE 频道隔离。
- **素材/差分渲染**：Bond Story 侧的事，独立于本 GUI。

## 11. 实现顺序

1. [x] `hub.py`（纯线程安全缓冲，可单测）
2. [x] `runner.py`（AgentRunner：turn 串行化 + ask 桥 + auto-approve）
3. [x] `app.py` + `__main__.py`（FastAPI 路由 + mock 开关）
4. [x] `static/`（index.html / app.js / style.css）
5. [x] 全链路验证：mock 模式走通 批准/拒绝/中止/409/auto-approve/重连（`_server_test.py`）
6. [~] 真实 LLM 冒烟（一次简单 OC 创建）——IDE_CLI 已冒烟，GUI 侧随 IDE 使用验证
