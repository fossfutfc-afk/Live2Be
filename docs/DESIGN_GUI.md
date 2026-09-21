# Live2Be GUI 设计（v1: 能跑优先）

> 2026-08-25 定稿。目标: 不重写逻辑, 最大化复用现有引擎/存储/web 壳,
> 新写"后端端点 + 前端页面"。当前不需要美化, 能跑通闭环即可。

## 1. 页面流

```
登录页（LOGO + 名字输入框; 首次进入选名字, namegg.json 彩蛋）
   │
   ▼
主界面（三按钮: 设置 / 手机MMT / 回放; 换名字以后再说）
   │
   ├─ 设置 ──▶ 调 GlobalSettings（global.py 参数: API key/base_url/model 等）
   │
   ├─ 手机MMT ──▶ 选学生列表 → MMT 对话（气泡）
   │                  │ 聊到一定程度（mmt_trigger_bond_story）
   │                  ▼
   │             邀约 VN（背景 + 立绘差分 + 段落打字 + 选项 + inner 黑屏内心戏）
   │                  │ 剧情结束（story_end / b 退出）
   │                  ▼
   │             回到手机（wrapup 后角色主动发消息）
   │
   └─ 回放 ──▶ 事件流回放（历史会话 timeline 重放）
```

## 2. 适配度评估（回答: 要不要新写/重写）

| 层 | 现有形态 | GUI 适配 | 结论 |
|---|---|---|---|
| **MMT 引擎** | `momotalk.agent_turn(user_input) -> TurnResult`（函数式, 结构化） | 直接调用 | ✅ **复用, 零重写** |
| **VN 引擎** | `bond_story.send_vn_scene(user_input, system_note) -> BondScene`（函数式） | 直接调用 | ✅ **复用, 零重写** |
| **vn_cli 循环** | CLI 循环（input_fn 参数化 + print 渲染 + 纪念/gallery/事件流逻辑） | 渲染换 JS; 循环逻辑抽"VN 控制器" | ⚠️ 渲染层新写, 控制器逻辑借鉴/复用 |
| **web 壳** | FastAPI + SSE hub + runner 模式（服务 ide 域） | **同款模式**加新端点 | ✅ 复用模式, 新写端点 |
| **存储** | SessionStore / GalleryStore / events.jsonl / global.py / namegg.json | 全部直接复用 | ✅ 零改动 |
| **导演/媒体** | Director / MediaCatalog / GalleryStore | VN 渲染数据直接消费 | ✅ 零改动 |
| **前端** | web/static/index.html（vanilla JS, ide 域） | 新写 GUI 页面（登录/主界面/MMT/VN） | ⚠️ 新写（GUI 的本质工作） |

**结论: 不需要重写任何逻辑**——引擎/存储/配置全复用; 新写的是**后端端点（薄） + 前端页面（厚）**。vn_cli 的 CLI 渲染（print/打字机）由 JS 播放器替代, 但其"每场 send_vn_scene + 事件流落盘 + 纪念生图"的控制器逻辑可提取复用。

## 3. 后端架构（FastAPI, 扩展 web/）

```
web/app.py（现有壳, 加路由）:
  POST /api/gui/login          # 名字（namegg 彩蛋校验/生成）→ 会话
  GET  /api/gui/characters     # 角色列表（五件套扫描）
  POST /api/gui/mmt/start      # 选学生 → 建 engine 实例 + SessionStore 会话
  POST /api/gui/mmt/turn       # 聊天输入 → 后台 agent_turn → SSE 推送回复
  GET  /api/gui/mmt/events     # SSE: 聊天气泡流式推送
  POST /api/gui/vn/turn        # VN 输入（选项/自由输入）→ send_vn_scene → SSE 推送场景
  GET  /api/gui/vn/events      # SSE: 场景段落/差分/背景/选项/inner 推送
  GET  /api/gui/settings       # 读 GlobalSettings
  POST /api/gui/settings       # 写 GlobalSettings
  GET  /api/gui/playback       # 回放: 历史会话事件流
```

**会话管理**: per-session engine 注册表（dict: session_id → {mmt_engine, vn_engine, store}）——
并发多个会话互不干扰; 复用现有 `AgentRunner` 的"单例 runner + start_turn 锁"模式。

**SSE**: 复用 `web/hub.py` 的 channel/快照模式（`HUBS.get(channel)`）——每个 GUI 会话一个
channel, 后端推送渲染事件（气泡文本/段落/差分路径/背景 id/选项/inner）。

## 4. 关键设计点

### 4.1 渲染数据（引擎 → JSON → JS）
- MMT: TurnResult.steps → `[{type: bubble/typing, text}]` → SSE 推送, JS 渲染气泡
- VN: BondScene → `{paragraphs: [{text, emotion, inner?}], choices, visual: {sprite, background}}`
  → SSE 推送, JS 播放器渲染（背景图 + 差分 + 打字机段落 + **inner 黑屏内心戏** + 选项）
  → 玩家选项/输入 POST 回 `/api/gui/vn/turn` 继续

### 4.2 VN 触发链路（mmt → 邀约 → 回手机）
```
mmt turn 返回 bond_story=True → 前端切 VN 视图
  → POST /api/gui/vn/start（后端: vn 引擎初始化, 复用 vn_cli 的控制器逻辑:
       brain_segment 注入 + memory_flash 随机事件 + 预热生图 + vn_enter 事件流）
  → story_end / b 退出 → 后端 wrapup（复用 wrapup_after_vn 逻辑）→ 前端回手机视图
```

### 4.3 名字/彩蛋
- 首次登录: 名字输入 → namegg.json 彩蛋匹配（同名彩蛋/生成彩蛋名）
- 玩家名存 data/basic/player.json（现有）, MMT system 不注入（学生不直呼自定义名——现状保持）

### 4.4 回放
- 读历史会话 events.jsonl → timeline 渲染（复用 render_timeline）——能跑优先: 纯文本时间线即可

## 5. 前端（能跑优先: 单页 + 视图切换）

```
web/static/gui/
  index.html       # 登录视图 → 主界面 → MMT/VN/设置 视图（JS 切换）
  gui.css          # 极简样式（气泡/差分/背景定位, 不美化）
  gui.js           # 状态机 + SSE 连接 + 渲染函数
  vn_player.js     # VN 播放器（场景渲染/打字机/选项/inner 黑屏）
```

## 6. 里程碑（每步可独立验证）

| 里程碑 | 内容 | 验证 |
|---|---|---|
| **M1 登录+主界面** | LOGO/名字输入/namegg 彩蛋 + 三按钮 + 设置页（global.py 读写） | 名字彩蛋生效, 设置改 key 后生效 |
| **M2 MMT 聊天** | 角色列表 + 气泡对话（SSE 推送 + 输入） | 真实 LLM 聊 3 轮 |
| **M3 VN 播放** | 邀约触发 → VN 场景（差分/背景/段落/选项/inner 黑屏）→ 回手机 | 完整走一场剧情 |
| **M4 回放** | 历史会话事件流时间线 | 恢复旧会话查看 |

## 7. 边界/注意

- **vn_cli 不重写**: 控制器逻辑抽离或 GUI 直接调引擎 + 自己落事件流（vn_cli 的
  纪念/gallery/事件流代码是参考实现, GUI 复制其逻辑而非 import CLI 函数）
- **engine 实例生命周期**: per 会话注册表 + 空闲清理（能跑优先可暂不清理）
- **随机事件/记忆系统**: GUI 继承（memory_flash 在 VN 开场, want_to_speak 在 MMT）——
  引擎层已支持, GUI 零改动
- **能跑优先**: 不做认证/多用户/移动端适配; 单窗口单玩家
