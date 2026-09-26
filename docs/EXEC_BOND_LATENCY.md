# 执行文档：VN 入口预热 + 读写交错（消灭"点击进羁绊剧情 5s+ 空屏"）

> **⚠️ 记录流 v2 后（2026-09-10）**：本文的"一场 = 一板 = 一次 LLM 调用"前提变了——
> 现在一次调用产出一整块（~40 条记录, 可派生 ~10 板）, 板间靠引擎**待发队列** 0 LLM,
> 预生成/桥的语义更新见 `docs/DESIGN_STREAM_CONTRACT.md` §10.4 与 §13 决策 #28:
> · **入口预热 / 跨重启缓存**（`prewarm.json`）不变（存 `scene.to_dict()`）;
> · **会话内桥** = 无槽板预生成 + 预生成链 + **裁决后立即预生成**（有槽板不预生成）;
> · 候选 fork（sibling 预生成）对记录流板已退役（后继板本来就在手）;
> · **草稿旁路**（决策 #28b, `soul/bond_draft.json`）: "已生成未播放"的板（当前
>   未落库板 + 待发队列 + 预生成板）落盘 → 重进 **0 LLM 续播**, 且续播板正常落库;
>   新鲜判据 = 同一在押段 + 其后无新 bond 事件;
> · **渐进渲染已落地**（2026-09-10, 记录流 v2 顺带解锁; **不需要 SSE**——chunk 本来
>   就在客户端侧）: chunk → 逐行解析 → **板一闭合就交付前端**。真机: 首板提前
>   3.3s 可读（= 内容段的 81%）; 剩余等待主要是**思考段**（10~23s, 占 60~90%）——
>   那里的杠杆是 reasoning 档位（用户裁决项）与预热/缓存/草稿三条 0 LLM 路径。


> 状态：P1 已实施（2026-09-07）——入口预热（staged/adopt/守卫）+ 单 POST +
> busy 语义 + 细粒度首场轮询全部落地, webgui 测试 20/20 通过（含新增预热与
> 渲染预热用例）。P2：#1（细粒度轮询）#2（enter 并行/单 POST）随 P1 落地,
> #3（MediaCatalog/EffectResolver 预热）2026-09-07 落地; #4（前缀缓存验证）
> 数据面已加（2026-09-07: llm chat/chat_full 日志输出 usage cache_hit/cache_miss,
> 流式请求带 stream_options.include_usage）, 验证报告待跑; SSE（#5）待执行。相关讨论：会话归因结论（首场=一次主 LLM
> 整包生成 + thinking=high 抬高 TTFT）见本档 §1；Storyloom 对照结论见 §8。
> 已拍板约束：reasoning 档位留给用户（最后优化点，本期不动）；bond.js 等待卡
> 的 `reason` 变量为历史遗留，不修；演示模式（demo）不预热。

---

## 0. 一句话目标

玩家点击粉泡进入羁绊剧情时，首场场景应**已生成或正在生成**（触发轮阅读期预热），
进入后读前场文本期间，下一场/分支/情绪/纪念图在后台与阅读交错完成——
从"点击后空等 5s+"变成"点击即有（≤0.5s 拾取）"。

## 1. 现状归因（为什么现在 5s+）

```
点击 → 2×POST start(幂等,~ms) → bond_start 同步段(<100ms, 0 LLM)
     → [后台线程] send_vn_scene：1 次主 LLM 整包生成
         · thinking=high（settings.toml [llm].reasoning_effort, main 类跟随全局）→ TTFT 含思考
         · 整场 JSON（段落+选项+place）→ 流式仅用于传输收集 + memorial 嗅探,
           展示等全量闭合 + 契约校验（MAX_SCENE_RETRIES=3）
     → 前端 700ms 轮询拾取 → status 里 MediaCatalog 首次构造 ~百 ms（纯本地）
```

- 背景查库**不在**首帧关键路径（发生在 scene 生成后的 status 轮询里，全本地）。
- emo 标注是"骨架发布后异步"，已不挡首帧——但没有让首帧更早。

## 2. 术语

| 词 | 义 |
|---|---|
| 入口预热（staged 首场） | 触发轮结束即后台生成首场，暂存内存态；点击时直接采用 |
| 读写交错 | 展示/阅读（读）与 LLM 生成/标注/生图（写）在时间上重叠的流水线 |
| staged | BondState 的"已预热未正式进入"状态（未落 vn_enter 等事件流标记） |
| adopt | 点击时把 staged 态转为正式态（补落 vn_enter marker） |

---

## 3. 机制 A：入口预热（staged first scene）

### 3.1 时序（目标态）

```
触发轮(agent_turn)内: LLM 输出 mmt_trigger_bond_story(带 chapter_title)
        │ 引擎落事件流: player/reply/trigger 事件（agent_turn 期间完成）
        ▼
worker 置 _tasks[key].bond_story ──► 同步调用 bond_start(staged=True)  ← 预热点
        │        （构造引擎+灌窗口 0 LLM → 起生成线程 → 立即返回）
        ▼
玩家阅读触发对白 + 犹豫（~1-8s）   ←── 首场 LLM 生成重叠在此窗口（3~8s）
        │
        ▼ 点击粉泡
POST /api/bond/start ──► vn 已存在 & staged → adopt（补 vn_enter marker, 校验 seq）
        │ busy=False 且 scene 就绪 → 返回
        ▼
前端 waitScene 首轮即取到场景 → 渲染（无等待卡或一闪而过）
```

### 3.2 状态与生命周期

BondState 新增字段：

```python
staged_seq: int | None = None   # 非 None = 预热态; 值 = 预热时最大事件 seq（一致性守卫）
vn_enter_written: bool = False  # vn_enter marker 是否已落（staged 不落, adopt 补落一次）
```

生命周期状态机（点击进入路径 `bond_start` 分支顺序）：

| 状态 | 点击时行为 |
|---|---|
| completed | 不变：拒绝（本档不改变"已完成再触发"语义，见 §3.4 开放问题） |
| busy | **改为 accepted:True,busy:True**（预热在途=常态；前端走 waitScene 轮询）——现状 busy 返回 accepted:False 会让单 POST 时代点击报错 |
| vn 存在（staged_seq 非 None） | 新鲜度校验通过 → adopt：`enter_vn()`（若未写）+ `staged_seq=None` → resumed 返回；校验失败 → 丢弃重建 |
| vn 存在（非 staged） | 原 resumed 路径（中断续玩），不变 |
| 空 | 原首进路径（现场生成），不变 |

adopt 的 vn_enter 时序：vn_enter 必须出现在事件流中触发事件**之后**、首场 bond
事件之前——staged 期间不写任何事件流 marker；adopt 时补写，时序天然正确。

### 3.3 文件级改动

**A. `webgui/chat.py`**（预热触发点，~6 行）
`_worker` 里置任务标志处（现 line ~166-169）追加：

```python
result = engine.agent_turn(text)
if result.bond_story:                 # 触发轮结束、事件流已终态
    from webgui import bond as _bond  # 延迟 import 破环 chat↔bond
    try:
        _bond.bond_start(char_id, session_id, staged=True)
    except Exception as e2:
        logger.warning("bond 预热失败（点击时现场生成）: %s", e2)
_tasks[key] = {"running": False, "error": "", "bond_story": bool(result.bond_story)}
```

- 同步调用即可：bond_start 同步段无 LLM、立即返回；生成线程拿 `chat._lock(char_id)`
  在 worker 释放后（本轮结束即刻）开始，无死锁（worker 不等待生成线程）。
- 守卫（`bond_start` staged 分支内）：completed/busy/vn-demo 已存在 → 直接返回不预热；
  staged 已存在且 seq 落后于本次触发 → 丢弃重建（防"旧预热被新触发复用"）。

**B. `webgui/bond.py`**
- `bond_start(..., staged: bool = False)`：
  - 同步段同现状（引擎构造/窗口灌入/brain/标题取自 engine.trace）——**唯一差异**：
    `staged=True` 时不调 `_store().enter_vn(...)`，记录 `staged_seq = 事件流最后一条
    **mmt 事件** seq（基准只数 mmt——玩家对白/触发；预热自身后续写入的 vn_state 等
    marker/bond 事件不参与判定，否则自生成标记会把预热误判过期而丢弃重建）。
  - 幂等/复入分支：见 §3.2；adopt 需要 `state.chapter_title`（已在字段中）。
  - busy 分支返回值改 accepted:True（见上表），error 字段可带 "正在生成首场"。
  - 新增小工具 `_last_mmt_seq()`（扫事件流取最后一条 mmt 事件的 seq，见上）。
- 丢弃重建：`_bonds.pop((char_id, session_id), None)` 后走全新首进路径（staged 生成
  线程是 daemon，其写回经对象身份检查 `_anno_worker` 风格防竞态——场景生成线程
  结束会写回旧 state 对象，不影响新 state，因键已 pop）。

**C. `webgui/routers/bond.py`**：无需改（start 直接透传）。

**D. `webgui/static/js/bond.js`** `enter()`
- 目前 `await initSpine()` 先于 POST start（spine 元数据网络请求串在生成之前）→
  改为：POST start 先行发出并 await 结果，`initSpine()` 在其后 await——两次网络
  请求时间重叠，spine 耗时被生成期覆盖。
- 点击即 busy（预热在途）时：start 返回 accepted:True,busy:True → `showEnterWait`
  照旧显示等待卡，waitScene 轮询到场景即收卡（现状逻辑已支持 busy）。
- waitScene：去掉每轮开头固定 700ms sleep——立即 fetch；busy 时尾部睡眠
  `gotScene ? 700ms : 250ms`（首场等待细粒度，拿到首场后回粗粒度）。

**E. `webgui/static/js/mmt.js`** `enterBond()`
- 现状：enterBond POST#1 → BondVN.enter 内 POST#2（幂等双发）。清理为单 POST：
  enterBond 只 `lockChat()` + `BondVN.enter()`（enter 内部 POST + waitScene）；
  错误处理由 enter 内 catch 承担（exit() 会 unlockChat + resumePolling）。

### 3.4 守卫矩阵与开放问题

| 场景 | 行为 |
|---|---|
| 预热后玩家不点，继续 MMT 聊天 | 事件 seq 前进 → adopt 时新鲜度校验失败 → 丢弃重建（新上下文生成） |
| 预热后不点也不聊，直接关页面 | 内存残留一个 vn（无事件流痕迹）；下次 openChat `in_vn=False` 正常；同角色新触发 → 预热守卫丢弃重建 |
| 预热在途点击 | busy → accepted:True → waitScene 等剩余时间（已省大半） |
| 预热 LLM 失败（3 次内） | 与现首进失败一致：state.error + 前端重试按钮（同路径，无回归） |
| 预热生成期间玩家点 demo | demo 独立（不预热），无冲突 |
| 服务重启 | 内存态全丢 = 现状；事件流无 vn_enter（staged 未写）→ 不会误判 in_vn ✓ |
| **已完成剧情后再次触发** | 现状 completed 拒绝点击（可能已是问题）——**开放问题**：若确认要支持二周目重触发，新触发轮时若 state.completed 应 pop 重建（预热与点击路径同改）；需与作者确认 |

---

## 4. 机制 B：读写交错（把"写"藏进"读"里）

### 4.1 现状覆盖矩阵（逐路径逐环节）

| 环节 | 现状 | 等待点 |
|---|---|---|
| 首场（入口） | 点击后才生成 | **5s+（机制 A 解决）** |
| 选项场→分支 | branches 同响应预写，选完零等待 | 无 |
| 分支读完→下一场 | 分支消费时即链式 `_pregenerate` | 极端：分支读完瞬间 pregen 未完成（≤ 一次生成时长，罕见） |
| 纯叙事场→下一场 | 渲染完成即 pregen，点"继续"零等待 | 同上有 pregen 失败降级窗口 |
| emotion 标注 | 展示不等标注（骨架先出）；推进门控等当前场景标注完 | 读速>标注速时短暂 busy（标注单 worker FIFO，当前场景先入队先标） |
| memorial 立绘 | 流式嗅探 prompt 定稿即开生图线程，图就绪静默淡入 | 无（APIYI 实测 **26s**/张；本地 SD ~2s 时代已于 2026-09-10 终止——后端只保留 APIYI） |
| digest/wrapup | finish 后异步 | 无 |

结论：**读写交错的主体已存在**（pregen 链 = Storyloom 的桥接预取；branches =
post-bridge 分支）。缺口 = 入口段（A）+ 少量语义修正（B）+ 可选轮询粒度（§5）。

### 4.2 流水线深度与锁语义（定稿，勿打破）

每 (char, session) 同时在途的上限：

```
1 × 场景生成（主/pregen 二选一：同持 chat._lock(char_id)，天然互斥串行）
+ 1 × emotion 标注（_anno_worker 不持 chat 锁，可与生成并发调 API）
+ 1 × memorial 生图（独立线程）
= 同会话 API 并发深度 ≤ 3（不同 char 互不干扰）
```

- pregen 触发点在主生成 `finally`（busy 清零后）与分支消费路径（§现状），保持。
- 标注队列 FIFO + 对象身份检查（scene_obj/pregen_obj 已换 → 丢弃）已防竞态；维持。
  pregen 场景标注若在玩家改选后作废 = 接受浪费（token 小，别加复杂度）。
- 推进门控 `_scene_ready_or_busy` 保留（情绪不到位不推进 = 落库质量底线）。

### 4.3 残余等待点决策表（本期全部"接受"，记录在案）

| 残余等待 | 出现条件 | 决策 |
|---|---|---|
| pregen 未完成点"继续" | 分支/纯叙事读完瞬间，pregen 偶发失败或超长 | 已有降级路径（busy + 正常生成）；读速 >> 生成速，实际命中率低；后续若要消灭 → 生成提前到"场次渲染完成"即可（现状已如此），只剩失败分支 |
| 标注 gate 短等 | 玩家连点跳过文本 | 2~5s 上限内，前端 busy 提示自动放行；接受 |
| 每场首个文本前 | TTFT（thinking=high） | 已被 pregen 藏进阅读期（除入口，A 解决）；用户要更快 → reasoning 档位旋钮（用户自选，§5 不做默认改动） |

---

## 5. 微优化清单（P2 顺手项）

| # | 项 | 收益 | 改动 |
|---|---|---|---|
| 1 | 首场等待期轮询 700→250ms（拿到首场后回粗粒度） | 平均 ~0.4s | bond.js waitScene 首场分支 |
| 2 | enter() 并行 initSpine + start POST；mmt.js 单 POST（§3.3 D/E） | ~0.1-0.5s + 清冗余 | 前端两文件 |
| 3 | MediaCatalog/EffectResolver 预热进预热线程（首场就绪后 status 不再现构造） | ~百 ms（首帧轮询更稳） | bond 预热路径 touch 一次 |
| 4 | 前缀缓存验证：system prompt 跨场稳定（start_session 构造一次）——DeepSeek 上下文缓存应已使后续场次 TTFT/成本降低 | 后续场次 | 只做埋点验证，无代码 |
| 5 | SSE 推送替代轮询（chat_stream 客户端已有，引擎/前端未接） | 轮询粒度→0 | 架构项，独立立项，不在本期 |
| — | reasoning 档位旋钮（settings [llm.tasks.bond] thinking=low/off） | 大 | **不做默认改动**：用户选择权，最后优化点；文档记录用法即可 |
| — | 等待卡 `reason` 变量 | — | **历史遗留，不修**（用户拍板） |

---

## 6. 埋点与验收

### 6.1 计时埋点（✅ 已实施 2026-09-07, logging INFO, 单行可 grep）

| 计量 | 日志标记 | 位置 |
|---|---|---|
| trigger→预热完成（staged scene 就绪） | `bond_prewarm_start`（起点, 含 title）/ `bond_prewarm_ready … lat=`（就绪时点; 丢弃/adopt 后不误报——registry 身份守卫） | bond.py staged 分支 / _generate run |
| 点击→首场（adopt 就绪? busy? / fresh 现场生成 / 内存续玩 / 中断回放） | `bond_click adopt … lat= ready=` / `bond_click prewarm\|fresh` / `bond_click resumed` / `bond_click replay scenes=` / `bond_click busy_wait` | bond_start 各分支 |
| 场景生成 / pregen 耗时 | `bond_gen ok … round= dur=`（失败带 dur）/ `bond_pregen ok dur=` | _generate / _pregenerate run |
| 标注耗时 | `bond_anno dur= fallback=` | _anno_worker |
| LLM 调用总耗时 + TTFT（首个 content chunk） | `llm chat_full ms= ttft= json=` / `llm chat ms= json=y`（非流式 json 档） | llm/client.py chat/chat_full |

中断行为注意点（实施约定）: `t_staged` 只随预热态存活——丢弃重建（pop 新对象）
/ 回放 / 普通首进 = 0, 无脏值; 预热就绪日志带 registry 身份守卫（state 已被
丢弃则不报）; busy 在途点击记 `adopt ready=n` 与 `busy_wait`, 语义各自独立。

### 6.2 手动验收脚本

1. MMT 聊到触发 → 观察日志：触发轮结束即出现"预热开始"；不等点击。
2. 立即点粉泡（<2s）：等待卡一闪或直接进场景，总等待 < 1s（原 5s+）。
3. 等 10s 再点：直接进场景，无等待卡（预热已就绪）。
4. 预热后先发一条新 MMT 消息再点：事件 seq 变化 → 丢弃重建，首场反映新上下文。
5. 纯叙事场连点"继续"：每场零等待（pregen 命中，回归确认）。
6. 选项→分支→继续：全程无 LLM 等待感（回归）。
7. 完成整段 → finish → wrapup 正常；事件流含恰一个 vn_enter（adopt 写入）且
   位于触发事件之后。
8. 回归：中断重进（resumed 续玩）、已完成拒绝、demo 路径、多角色并行。

---

## 7. 阶段划分

| 阶段 | 内容 | 涉及文件 | 风险/回滚 |
|---|---|---|---|
| P1 | 机制 A（预热+adopt+守卫+busy 语义）+ 埋点 | webgui/chat.py, webgui/bond.py, js/bond.js, js/mmt.js | 仅 webgui；预热失败走原路径（try/except 包裹）；可关开关（环境变量/常量预留在 chat.py 预热点） |
| P2 | §5 微优化 1-3 + §6 验收脚本执行 | 同上 + 预热线程 touch catalog | 纯增量 |
| P3 | 前缀缓存验证报告 + （可选）SSE 立项 / 展示先行立项 | — | 评估后另立 |

开关建议：`webgui/chat.py` 顶部 `PREWARM_ENABLED = True`（作者可关），P1 交付后默认开。

## 8. 参考对照（Storyloom, D:\MYCODE\github\Storyloom）

| Storyloom | 本项目对应 | 启示 |
|---|---|---|
| Phase5 `</story>` 即发下一轮 API（game_loop.py:1018-1054） | pregen 链（渲染完成即预生成） | 已有同构；保持 |
| `<bridge/>` + post-bridge 纯叙事缓冲覆盖 TTFT | branches/纯叙事预生成 | 同构；无新增 |
| 选项流中途暂停（`</choice>` → yield → send） | 选项需等整场 JSON（无中途交互） | 展示先行立项时的参考协议 |
| 行级自包含 XML + 行级宽容错误（format_errors → 下轮反馈） | 整包 JSON + MAX_SCENE_RETRIES=3 + closing | 失败哲学可借鉴：普通错误下轮反馈、严重错误交给用户重试（本项目已近似；可把"连续失败→closing"改为"失败留按钮"） |
| 严重错误永不自动重试（API/超时 → UI 用户决策） | 自动重试 3 次后 closing | 可选改进点（需作者拍板） |
| 首轮 TTFT 也硬等（无入口预热，10-30s） | 本项目有 MMT 触发窗口 → **预热是超越点** | 机制 A 依据 |

## 9. 关联文档

- 本问题归因链：webgui/bond.py `_generate`/send_vn_scene 调用、core/bond/bond_story.py
  `send_vn_scene`（406-449）、llm/client.py `chat_full`（181-222）、llm/task_levels.py、
  settings.toml `reasoning_effort=high`、archive/maXEmo-miNDelay.md（已归档）（流式 vs 退火取舍）、
  docs/archive/DESIGN_BOND_STORY.md（两遍式 C 背景）、CLAUDE.md §4（两遍式 C 现网口径）。
