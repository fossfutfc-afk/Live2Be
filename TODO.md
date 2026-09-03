# Live2Be 待办表（2026-09-03 快照）

> 此表是跨 session 的进度锚点——完成一项就勾掉。旧快照（08-23）已清理归档进 git 历史。
> 关联：CLAUDE_OPTIMIZE.md（优化方向状态清单）/ guidance/（角色卡写作指导）/
> AGENT_BRAIN.md（wiki 实施蓝图, 含开放问题 §9）/ DESIGN_BRAIN.md（记忆体系总纲）

## 进行中 / 即将

### 出厂定稿管线（brain_seed 定稿制 —— 2026-09-04 设计定稿, 本会话分阶段执行）

> 核心: 出厂经历（experience.yml）= **一次定稿**（LLM 逐条改编 + 作者 review → brain_seed.yml）,
> seed = 确定性复制; digest（运行时）只处理玩家新记忆。修正了: 出厂改编挂后台 digest 的
> 短时失忆/双轨 bug（0.1）、批量改编质量差（0.2 逐条）、改编 LLM 无人设锚（0.2 人设注入）、
> 快照回退需 yml 副本（0.4）、中途改卡语义（0.3/行为热更·记忆重灌）。

**阶段 0 设计定稿** ✅
- [x] 0.1 出厂 = 一次定稿（brain_seed.yml）; seed = 确定性复制; digest 只处理玩家新记忆
- [x] 0.2 改编工具逐条调用 + 人设锚注入（profile/personality/称谓表）
- [x] 0.3 产物 = 初稿, 作者 review 后定稿; 工具防覆盖（--force 重跑）
- [x] 0.4 世界线创建时快照定稿输入进世界线（seed_snapshot/）——回退/重建与 config 解耦
- [x] 0.5 无 brain_seed 新角色 → 原文兜底（现逻辑）——可玩性永不阻塞

**阶段 1 prompt: llm/prompts/seed_digest.md**（本会话执行中）
- [ ] 1.1 角色定位: 预设经历改编员（与 Round A 同协议: 第一人称/浓缩/不升华/verbatim 逐字）
- [ ] 1.2 人设锚段: 角色档案/性格口吻/称谓表（{{占位符}} 文档化, 工具端渲染注入）
- [ ] 1.3 单条输出规格: source_key/title/narration/verbatim/significance/author_notes
      （author_notes = 剥离的点评句, 空则省略）
- [ ] 1.4 改编规则: 不增删原文事实/不发明细节/称谓按表/点评句不混入 narration/感受句可留
- [ ] 1.5 输出纪律: 完整单条 JSON（工具端兼容 {"episodes": [...]} 数组态）, 不要代码块

**阶段 2 工具: tools/seed_digest.py**
- [ ] 2.1 读卡: CharacterLoader 取 profile/personality; experience.yml 叶子（复用 _collect_leaves）
- [ ] 2.2 称谓表渲染: knowledge.friends → 称谓行（供人设锚注入）
- [ ] 2.3 逐条 LLM 改编: temp 低/重试 ×2/单条失败记录不阻塞
- [ ] 2.4 解析校验: source_key 回填/必填非空/sig 0-1/第三人称自指软校验 → 坏条目列清单
- [ ] 2.5 写 brain_seed.yml: episodes[] + review_notes[]; 已存在拒绝（--force）
- [ ] 2.6 CLI: --char/--force/单条重跑; 进度/耗时提示

**阶段 3 引擎: seed.py**
- [ ] 3.1 brain_seed.yml 分支: episodes → make_node（title/verbatim 落库; source=experience）
- [ ] 3.2 无 brain_seed → 原文兜底（现逻辑不动）
- [ ] 3.3 世界线创建快照: brain_seed/原文 yml → worlds/{w}/characters/{c}/seed_snapshot/
- [ ] 3.4 幂等/落盘沿用（source_key 判重 + save）
- [ ] 3.5 world1 遥香重灌（删 wiki → brain_seed 重 seed）+ 渲染抽查
- [ ] 3.6 momotalk.py 131/407 行 kind=="fact" 残留清理（fact 退役死代码）

**阶段 4 测试**（设计独立, 不跑全量）
- [ ] 4.1 brain_seed 分支: 映射/immutable/幂等（test_wiki_seed 新组）
- [ ] 4.2 快照语义: seed_snapshot/ 存在; 删 wiki 用快照重建（config 改动不影响）
- [ ] 4.3 原文兜底回归; 4.4 工具单测（fake LLM）; 4.5 全量回归

**阶段 5 真实执行（遥香）**
- [ ] 5.1 seed_digest.py --char igusa_haruka → brain_seed.yml 初稿（12 条）
- [ ] 5.2 用户 review/手改（语气/自注/点评句去留）→ 定稿
- [ ] 5.3 world1 重灌 + 渲染抽查（第一人称/无点评混入）
- [ ] 5.4 review_notes → 用户写 beliefs.yml（素材已备）
- [ ] 5.5 组织视图抽查（title/verbatim 展示）

**阶段 6 文档**
- [ ] 6.1 guidance/experience.md: 写作规范（档案语义/点评句留给 beliefs/改编工具说明）
- [ ] 6.2 AGENT_BRAIN.md 出厂管线段更新（定稿制 + 快照 + brain_seed 格式）
- [ ] 6.3 TODO.md 本表勾选

### 出厂 wiki 闭环（✅ 引擎全部落地, 9558287——剩内容创作）

- [x] **seed v3: beliefs.yml 解析**——出厂认知层（guidance/beliefs.md 已定稿）：
      subject/content/links（source_key 引用校验, 孤儿引用报错并列出可用键）/significance;
      belief 出厂**不 immutable**（运行时 digest 的 touch/update 要能挂新经历——认知基线演化）;
      遥香 beliefs.yml 内容待写（用户自己写或我起草——唯一剩余项）
- [x] **渲染段位修正**：出厂 episode（source=experience）→ "久远的记忆"段 cap 5;
      运行时 episode 独占珍贵/最近段（v3 落地, 真实渲染 1151 字 vs 旧 2576 字）
- [x] **fact 退役**（用户拍板, 9558287）：knowledge.yml 不再出厂化——"我知道的事" =
      世界观知识（overview.yml common 语义）→ 世界观知识库中期项（见下）; fact 语义
      已无消费方（knowledge 注入问题随之消解, 18 fact 不再注入）
- [x] **wiki 图谱可视化工具**：tools/wiki_viz.py（networkx PNG + mermaid 双输出;
      dev 依赖进 requirements-dev, 运行时仍 dict 邻接）
- [ ] **人称转换残余**（"她/自己"指代链混用——替换"遥香"→"我"后暴露）：
      渲染层保守启发式（先"自己→我"类无歧义项; "她"消解需谨慎——可能指 sensei）
- [ ] **出厂经历优先级表达**：12 条同 sig 0.9 → cap 5 恒显示 yml 前 5 条
      （现以作者书写顺序为准; 若需新_year/main 进窗口, 待定条目级 sig 标注）

### 上个 bug 修复的验证与遗留

- [ ] **bond 黑背景遗留确认**：标注/busy/竞态修复后重启重测——若仍黑, 查 director 背景
      映射或双前端错乱（见 29a4ea9 修复清单）
- [ ] **真机完整 bond 闭环验证 digest**：wiki 出厂落盘 + episode 化后, 跑完整剧情
      → digest 产 episode/belief + 注入刷新（此前 digest 从未成功闭环过）

## 短期（体验闭环 / 明确小项）

- [x] **MMT 协议终稿（消息流 messages）**：`{"messages": [{text|action}…]}` 任意交错——
      话→图→话 微信节奏; 动作外壳 {action,payload}（summary/reply/operation 全清）;
      旧协议保序归一 ✅ 469→471 passed
- [x] **MMT 触发节奏 v2**：引擎硬闸（不足 6 轮拒 trigger）删除——玩家遇险尬聊是硬拒的
      伪正确; 建议不拦截, SUGGEST_BOND_ROUNDS=6 注记分级提示, 触发权全交 LLM
- [x] **thinking level + max_tokens 集中管理**：llm/task_levels.py 唯一真源
      （main=default / emotion=off / digest=high; 六形态 max_tokens; settings [llm.tasks] 覆盖）
- [x] **wiki 重复 append 根因修复**：seed add 不 save → wiki.jsonl 恒空 → 每次触发重 seed;
      修复后真实数据清理 + 落盘验证 ✅
- [x] **出厂 digest v2**：experience.yml → episode（与 bond digest 产物同构, 用户拍板
      "预设记忆 = 角色记得的经历"）; knowledge → fact 不变; is_seed 扩展; v1 fact 自动迁移
- [x] **bond 表情卡 default + 无限 3 点加载修复**：标注调用关 reasoning（extra_body={}）+
      max_tokens 512; 分支路径同步等标注; _generate/_pregenerate 原子抢占; 前端重试上限
- [x] **问题 1 断句权移交**：切分器（jieba 碎句合并/块保护/句界）引擎化; 契约自然段语义;
      标注层唯一真源 + robust 二分降级 + character 注入; 推进门控（情绪未到位不可推进）
- [x] **问题 2 选项失灵**：send_vn_scene max_tokens 1536→8192（high reasoning 截断根因）;
      busy 标志 finally 恒复位; 门控兜底 fill 恒可达
- [x] **问题 3 轮数机制**：rounds_since_bond 持久（worlds progress.json 语义修正）;
      vn_exit completed 清零 / 中途退出保留（v2 后降级为建议线基准）
- [x] **guidance 目录建立**：README（五问心智模型）+ beliefs.md 完整写作指导
      （字段规格/source_key 规则/范例/反面例子/LLM 自查清单）
- [ ] **背景选择逻辑加速**：Director.visual_for 每场 `set(catalog.background_scenes())`
      全量重排（620 场景 O(n log n)）→ catalog 缓存 frozenset 一次构建; 顺带查
      background_scenes_in_dir 按需扫是否可预索引
- [ ] **bond_finish 收尾等标注的 8s 同步等待** → 后台化（当前阻塞 finish 请求线程;
      标注修复后 ~1-3s, 可接受但可优化）

## 中期（蓝图 / 板块）

- [ ] **回放功能**（事件流 → 自动播放）：
      - vn_state marker 中断恢复：服务重启后重建 VN 引擎续播（webgui/bond.py 注释
        "M3 回放"——事件流在, 内存态丢, 需重建）
      - 回放模式：已存档剧情自动播放（选项锁定 picked）——DESIGN_RENDERER.md M3;
        CLI 恢复入口（list_open → resume, 旧 TODO"存档系统恢复入口"）
- [ ] **多角色扩展**（DESIGN_MULTI_CHAR.md 蓝图）：
      - 字段预留已就位：character_names 称呼注入（momotalk/bond_story 分饰多角）、
        interperson 权重表、hub channel 预留、observer 语义（reported_fact）
      - 群像本体：A 一次调用 / B 轮番调用（段落流抽象）——前置：单人模式稳定
- [ ] **RAG 召回记忆**：recall.py 三通道已实现, embed_fn 注入=RAG 升级接口已留——
      接本地 embedding（nomic + numpy 余弦, DESIGN_BRAIN §10 Phase 2）+ 原文回捞
      （滑动窗口外的按需调页）
- [ ] Virtual Brain 完整（Semantic Graph / Self-Model / Sleep 五阶段——当前 digest
      体系是其简化版; CLAUDE.md §3.2）
- [ ] 官方剧情（剧本解析器 + 播放器）
- [ ] 羁绊值系统（现用轮数制; 好感 delta 已流式累计——数值体系与行为挂钩未做）
- [ ] mmt_send_media 媒体管线（资源查库 → 生图; 当前占位回灌）
- [ ] 世界观输出侧校验（LLM 输出 vs overview.yml 规则检测矫正——config/settings/.md 未来项）
- [ ] SSE 流式推送替代轮询（chat_stream 客户端已有, 引擎/前端未接）
- [ ] 时间系统（AGENT_BRAIN §时间——单元时间标注/渲染层记忆模糊化, 待拍板）

## 已知技术债 / 文档债

- [ ] 事件流全量保留策略（YAGNI：等积累大再摘要化/归档）
- [ ] jsonl 单行 >4KB 的 append 原子性实测（长段落场景）
- [ ] DESIGN_VISUAL_PROTOCOL.md 状态行过时（"设计定稿待实现"——契约已切 emotion 内联,
      beats 已删多年）
- [ ] docs/archive 与 core/DESIGN_*.md 的部分过时描述（如 DESIGN_SAVE 已归档,
      新链路在代码 docstring——按需清理）
- [ ] llm/design.md 待定/未来扩展段核对（max_tokens/thinking 已集中到 task_levels.py）
