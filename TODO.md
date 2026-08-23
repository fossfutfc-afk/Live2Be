# Live2Be 待办表（2026-08-23 快照）

> 当前分支：visual-director。此表是跨 session 的进度锚点——完成一项就勾掉。

## 进行中 / 即将

- [x] **MMT 动作列表闭环**：agent_turn 解析 `{"actions":[...]}` → 逐动作 parse/execute/渲染；
      trigger 独占、inspect 不进列表、失败整列表回灌（schema/rules 已切列表）✅ 152/152
- [x] **BOND per-para sprite（架构定稿）**：paragraphs 改为 `[{text, emotion?}]`（情绪内联, **删 beats**）；
      emotion 缺省延续上一段（纯确定性, 零语义判断——AI 写文本同刻标注）; 渲染端逐段标注+查表;
      place 可选本地推断 ✅ 163/163
- [x] **端到端真实跑通**（experiments/e2e_smoke.py, DeepSeek API）：MMT 3 轮 → 强制进入 bond story → VN 8 场正常结束 → wrapup 收尾 → 对话 md 记录；
      事件流验证（root 5 事件 + bond 子会话 16 事件 vn_enter/story_scene/vn_state…）✅
- [x] **端到端抓出 2 个真 bug 并修复**：① bond_save 访问已删的 scene.beats（异常被 try 吞 → 存档静默失败）；
      ② 词表注入路径错（config/characters/{char} 无 emotions.yml → 注入空）→ 改 assets/illustration/{char_id}；
      修复后 LLM 从词表外（happy/hopeful/gentle）变为全词表内（panic/smile/embarass…）✅ 163/163
- [ ] **文档同步（beats 架构变更后）**：DESIGN_VISUAL_PROTOCOL.md §3（beats 定义已删）、
      DESIGN_SAVE.md §4.2 bond 事件示例（paragraphs 内联）待更新——用户偏好自己改文档, 或我改给 diff
- [ ] **存档系统实现**（DESIGN_SAVE.md 定稿）：
      - [x] `core/session/{io,models,events,renderer,store}.py`（IO / 模型 / 事件 / 派生视图 / 生命周期）✅ 164/164
      - [x] 引擎接入：momotalk agent_turn 落 mmt 事件 + session progress（同轮去重约定）✅
      - [x] vn_cli run_bond_story_vn 接入 store（open_vn / bond 事件 input+picked / vn_state marker / vn_exit+session_end 统一收尾）✅
      - [ ] 恢复入口（main/mmt_preset: list_open → 手动选择 → resume 重建引擎）
      - [ ] wrapup_after_vn 接子会话收尾联动（当前收尾在 run_bond_story_vn 内, wrapup 是手机收尾）
- [ ] **BOND 表情渲染**：vn_cli 渲染层接 catalog.sprite(char, emotion) 查 emotions.yml（当前只打印标签）
- [ ] **BOND 返回/渲染说明补进 bond_story_rules.md**（目前没写格式，用户确认后做）

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
