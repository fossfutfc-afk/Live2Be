# Live2Be 待办表（2026-08-23 快照）

> 当前分支：visual-director。此表是跨 session 的进度锚点——完成一项就勾掉。

## 进行中 / 即将

- [ ] **MMT 动作列表闭环**：agent_turn 解析 `{"actions":[...]}` → 逐动作 parse/execute/渲染；
      trigger 独占、inspect 不进列表、失败整列表回灌（schema/rules 已切列表，引擎未实现）
- [ ] **存档系统实现**（DESIGN_SAVE.md 定稿，地基已实现 `core/session/{io,models,events}`）：
      - `store.py`（SessionStore: create/open_vn/append_event/append_marker/list_open/resume）
      - `renderer.py`（render_events→LLM 消息 / filter_bond 回放 / markers 状态推导 / render_timeline brain）
      - 引擎接入（momotalk agent_turn 落事件 / bond_save 落 type=bond / vn_cli vn_state marker + wrapup）
      - 恢复入口（main/mmt_preset: list_open → 手动选择 → resume）
- [ ] **BOND 返回/渲染方法讲解**（用户待确认渲染层设计，见对话）

## 短期（体验闭环）

- [ ] **web VN 播放器**：web 加角色扮演频道（hub.channel 已预留），渲染背景+表情+选项
- [ ] **生图管线（Phase 4）**：纪念时刻判定 + SD1.5 本地生图（.env 已注释调用方式）；
      gallery 写入（图+json 成对）；L2D 板块定档（events 的 l2d payload 引用式最小已定）
- [ ] **brain digest**：session 结束后 events → 叙事时间线 → LLM 总结 → wiki.json 增量

## 中期（蓝图）

- [ ] Virtual Brain 完整（Semantic Graph / Self-Model / Sleep 整合）
- [ ] 官方剧情（剧本解析器 + 播放器）
- [ ] 羁绊值系统（现用轮数制 bond_progress）
- [ ] interperson 运行时消费（mmt_inspect_character 已接，知识问答深化）
- [ ] mmt_send_media 媒体管线（查资源库 → 生图）

## 已知技术债

- [ ] 事件流全量保留策略（YAGNI：等积累大再摘要化/归档）
- [ ] 旧档 v0 只读兼容（data/{char}/sessions 下 {char}_{ts}.json 单文件格式）
- [ ] jsonl 单行 >4KB 的 append 原子性实测（长段落场景）
