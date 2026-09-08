# Live2Be 待办表（2026-09-03 快照）

> 此表是跨 session 的进度锚点——完成一项就勾掉。旧快照（08-23）已清理归档进 git 历史。
> 关联：CLAUDE_OPTIMIZE.md（优化方向状态清单）/ guidance/（角色卡写作指导）/
> AGENT_BRAIN.md（wiki 实施蓝图, 含开放问题 §9）/ DESIGN_BRAIN.md（记忆体系总纲）

## 进行中 / 即将

### 世界线语义定稿实施（core/DESIGN_WORLD.md §9, 2026-09-04 定稿——法则共享/历史固化/overlay 三层）

- [ ] **行为层现状核对**：config 单一真源实时读 = 定稿形态（无副本）——核对所有
      角色消费点是否"显式经过当前世界"（角色实例解析器: world_id+card_id → 基座+
      overlay+soul; 无 overlay 纯 config 查询零开销）; 消除隐式漂移（§9.2）
- [ ] **会话级内存快照**：会话开始时取一次基座进内存, 会话内固定——防中途改卡
      人格漂移（§9.3 哈希挂点 1）
- [ ] **世界注册表**：worlds/{w}/world.json（json）登记 roles 导入清单; 主世界默认 =
      mmt_registry 白名单; 运行时角色列表从注册表读（重开不重选, 新卡不进旧世界）;
      导入 = 显式实例化动作（§9.4）
- [ ] **哈希版本信号**：registry/overlay/出厂种子三个挂点记录基座哈希 → 变更冒泡
      （作者新版设定/记忆重整理/overlay 检查）（§9.3 哈希表）
- [ ] **overlay 承载形态**：per-world 差异文件（interperson/性格子集）——形态待用户
      （§9.6）; 出厂记忆"整理冒泡"随创建流程一起（§9.5）
- [ ] **待用户思考**: beliefs 出厂预置 vs 涌现 / 卡变体组织 / overlay 边界（§9.6）

### 出厂定稿管线 → **2026-09-05 转向: 运行时解耦**（出厂记忆不进 wiki）

> 调研定稿（Letta Memory Blocks / SillyTavern 卡 / 图记忆系）: 主流项目预置内容 =
> 直注上下文（persona 块/description）, LLM 扮演时自然内化; 图记忆只存运行时。
> experience.yml = 作者人设描述（与 personality 同性质）, 不是"待改编的记忆"。
> 改编链代码保留为可调用模块, **主进程不再使用**。

- [x] **运行时解耦已完成**（4290f3e + ece0747, 495 全过）: 主进程 seed_from_config
      调用全删（load_brain_segment/_inject_brain）——注入段 = 出厂背景
      （experience.yml 原文直注 cap 6: render_background_experience, 第三人称
      不转换——LLM 自然内化）+ 运行时 wiki（digest 产物）; world1 出厂残留已清
- [x] **预处理链归档**（5b44411, 471 全过）: seed 引擎/改编工具/prompt/brain_seed
      稿/beliefs 手册/对应测试 → archive/factory_memory/（git mv 保历史, README
      记录可复用资产: 记忆化重构规则/逐条调用模式/brain_seed 稿可作背景润色参考）
- [ ] **背景段实机效果验证**: 【背景经历】指引（"回忆过去以此为准/底色不必每轮提起"）
      在 bond/MMT 的表现——第三人称背景 LLM 自然内化是否成立（酒馆同款验证）;
      以及 cap 6 是否够（12 条只显前 6——作者可调 experience.yml 顺序）

**阶段 0 设计定稿** ✅
- [x] 0.1 出厂 = 一次定稿（brain_seed.yml）; seed = 确定性复制; digest 只处理玩家新记忆
- [x] 0.2 改编工具逐条调用 + 人设锚注入（profile/personality/称谓表）
- [x] 0.3 产物 = 初稿, 作者 review 后定稿; 工具防覆盖（--force 重跑）
- [x] 0.4 世界线创建时快照定稿输入进世界线（seed_snapshot/）——回退/重建与 config 解耦
- [x] 0.5 无 brain_seed 新角色 → 原文兜底（现逻辑）——可玩性永不阻塞

**阶段 1 prompt: llm/prompts/seed_digest.md** ✅（02460c8, 五连 commit）
- [x] 1.1 角色定位: 预设经历改编员（与 Round A 同协议: 第一人称/浓缩/不升华/verbatim 逐字）
- [x] 1.2 人设锚段: 角色档案/性格口吻/称谓表（{{占位符}} 文档化, 工具端渲染注入）
- [x] 1.3 单条输出规格: source_key/title/narration/verbatim/significance/author_notes
      （author_notes = 剥离的点评句, 空则省略）
- [x] 1.4 改编规则: 不增删原文事实/不发明细节/称谓按表/点评句不混入 narration/感受句可留
      + 示范对照（同一原文正例）
- [x] 1.5 输出纪律: 完整单条 JSON（工具端兼容 {"episodes": [...]} 数组态）, 不要代码块

**阶段 2 工具: tools/seed_digest.py** ✅（02d21e4, 七连 commit; git add -f 入库——tools/ 被 ignore）
- [x] 2.1 读卡: CharacterLoader 取 profile/personality; experience.yml 叶子（复用 _collect_leaves）
- [x] 2.2 称谓表渲染: knowledge.friends → 称谓行（供人设锚注入）
- [x] 2.3 逐条 LLM 改编: temp 低(0.3)/重试 ×2/单条失败记录不阻塞; task_levels 新增
      seed_digest 形态（medium/4096——有原文锚的转换任务, high 长考拖慢 12 条串行）
- [x] 2.4 解析校验: source_key 回填/必填非空/sig 0-1 硬错误; 第三人称残留/多余键软警告
- [x] 2.5 写 brain_seed.yml: episodes[] + review_notes[]; 已存在拒绝（--force 备份 .bak）
- [x] 2.6 CLI: --char/--dry/--only 单条重跑/--force; 进度/耗时/汇总提示

**阶段 3 引擎: seed.py** ✅（1052c56 + 1efdf05）
- [x] 3.1 brain_seed.yml 分支: episodes → make_node（narration/title/verbatim/sig
      逐条入档; source=experience 判重键与原文一致——中途补定稿不影响已有世界线）
- [x] 3.2 无 brain_seed → 原文兜底（现逻辑不动）——角色可玩性永不阻塞
- [x] 3.3 世界线创建快照: brain_seed/原文 yml + beliefs → worlds/{w}/characters/{c}/
      seed_snapshot/（首次 created 时写, 幂等不覆盖; 演练: config 模拟修改后快照保持原样）
- [x] 3.4 幂等/落盘沿用（source_key 判重 + save; created 时 save 根因修复保持）
- [x] 3.5 world1 遥香/佳代子重灌演练（原文兜底 12/4 条 + 快照写入验证）——
      **真实 brain_seed 重灌等 5.1 生成定稿后做（5.3）**
- [x] 3.6 momotalk.py 131/407 行 kind=="fact" 残留清理（恒 False 致每次 seed 空跑
      → is_seed() 判定; wiki 相关测试回归 21+26 过）

**阶段 4 测试** ✅（494 passed, +17 新增）
- [x] 4.1 brain_seed 分支: 全量映射（title/verbatim/sig/evolution 标记）/幂等/immutable/
      坏条目隔离/解析失败不回退原文（test_wiki_seed.py 追加 4 组）
- [x] 4.2 快照语义: 首建写入/原文兜底分支/不覆盖/config 改动世界线零变化/
      新世界线用新版（test_wiki_seed_snapshot.py 新文件 5 组）
- [x] 4.3 原文兜底回归: wiki 全组 108 过（haruka 真实目录 12 条原文映射不变）
- [x] 4.4 工具单测: tests/tools/test_seed_digest.py 8 组（fake LLM 注入/组装零占位符/
      校验硬软/重试跳过/写盘防覆盖 .bak——git add -f 入库, tests/tools 被 ignore）
- [x] 4.5 全量回归: 494 passed（477 + 17）

**阶段 5 真实执行（遥香）**（5.1 ✅ c10d5ae——5.2 起待用户）
- [x] 5.1 seed_digest.py --char igusa_haruka → brain_seed.yml 初稿（12/12 成功 ~4.5min;
      第一人称/title 全齐/2 verbatim/1 author_notes(regular.1 点评含"经典遥香思维"自注原样保留);
      忠实度抽查 main.1-3/valentine 与原文吻合; 原文 2281 字 → 改编 1857 字）
- [ ] 5.2 用户 review/手改（重点: 语气/自注/点评句去留; 已标 1 处措辞疑点:
      regular.1 "老师误解消息" vs "我误解"——原文主语含混, 作者定夺）→ 定稿
- [ ] 5.3 world1 重灌（删 wiki → brain_seed 重 seed）+ 渲染抽查（title 进组织视图/图谱）
- [ ] 5.4 review_notes → 用户写 beliefs.yml（素材已备: regular.1 点评句）
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

### 中止语义修正（2026-09-09 用户拍板: 中断/异常 ≠ 失败/完成）✅ 引擎侧已落地

> 历史遗留: 生成失败超限曾 closing 伪收场（is_end+completed）→ 前端 1.6s 自动
> finish → vn_exit completed=True → digest + 完整收尾话/兜底落库——大量重复
> "好好记住"兜底话 + wiki 空的来源（从未自然完成）。

- [x] N_a 失败超限 = 中止态（completed 恒 False、不落结束事件、可重试/离开重进续写）; 篇幅超限强制 closing 删除, _system_note 每轮强制 story_end 注记
- [x] N_b 前端天然支持（showTurnError 重试按钮; 无 is_end 不触发自动 finish）; 中止文案简洁化（完整异常入 diag 日志 data/diag/live2be.log——诊断不进事件流）
- [x] N_c digest 触发面注释守卫（completed 只来自场景 is_end 自然收尾）
- [ ] N_d CLI 失败收场对齐: vn_cli catch 仍落 closing story_end（伪收场残留, webgui 已改）——失败提示+重试 N 次, 超限中断且不落 story_end（vn_enter 在押可 resume）
- [ ] 放弃本章/拒绝邀约（显式退出 UI + vn_abandon——未来扩展, 用户搁置）
- [ ] replay 尾场 is_end → completed 置位口径核对（回放已完整结束剧情时的收尾/digest 语义）
- [x] 诊断日志落盘（5470f9f: data/diag/live2be.log, WARNING+ 旁路文件, 不进事件流）

## 短期（体验闭环 / 明确小项）

- [ ] **mmt 圆括号剥离误伤（未来优化）**：`_strip_action_brackets` 剥全部 （）/() 内容——
      "哼，我才不理你呢(ps: 快安慰我)" 会被肘击; 需语义判断/白名单/人设开关
      （代码注释自认边界: "喜欢在聊天里发括号的人设…等我改逻辑"; 方括号 [] 安全不剥）

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

### 选项等待减少 + 标注链路稳定（2026-09-08 立项候选, 未排期）

> 背景: SceneStream P1 真 API 实测（5 轮, experiments/p1_text_annotate_real.py）——
> 标注已收敛到「text + 编号映射 + 宽松解析 + 重试预算 3」(b12eb53); 今晚服务端
> 负载期空响应污染数据, 验收数字等空闲复测。选项等待现状: 分支直显零等待 +
> 分支播放期预生成, 剩余等待 ≈ max(0, 下一板生成 − 分支播放)。

- [x] **A. 预生成/纯推进板 low reasoning**——**用户否决（2026-09-08）**: 现网 API
       必须 high 才有正常文风（低思考 AI 味浓）, 创作档不可降; 选项等待改走
       D（P2 流式）为主 + 分支预生成已覆盖的窗口内就绪。放弃降档路线
- [ ] **B. 追赶降档**：预生成落后时先 low 出一版上屏, 后台 high 替换——双生成
       复杂度, 仅极端慢期值得, 暂缓
- [x] **C. 选项候选预生成（sibling 草稿支, 用户方案）**：已落地 master（N1 fork
       原语 + N2a spawn / N2b 消费切换 / N2c 清理观测 / N2d 开关, 489 绿）——
       板带 choices → fork 候选支（A1 按路径回录）各自预生成下一板; 裁决命中
       即端上（零等待, 未命中走老路）; 未选作废 GC（草稿纯内存零落库）。
       成本实测: 双路 prompt 近全量缓存（miss 262-1072 vs hit ~6.2k）, 增量
       ≈ 1 候选支输出; 设计/落地记录 docs/DESIGN_CHOICE_PREGEN.md; 开关
       settings.toml [bond] choice_pregen（缺省 sibling; tree 预留不做）;
       **待真机验证**: 选项命中 0 等待率 / 候选墙钟并发实测; 分歧感规则测试
       已获用户授权（临时改 rules 4 + 夹具同批, 测完回退）
- [ ] **D. P2 流式渐进（段闭合即发布）**：选项/继续等待的终态解——TTFT+首段即读;
       见 DESIGN_SCENE_STREAM §2/§10
- [ ] **E. 空闲时段复测 P1 验收**：兜底句数≈0 / 重试率 / 单段耗时 p50
       （`P1_MAX_BOARDS=6` 全量; 今晚负载噪声不可信）
- [ ] **F. client json_object 空 raw 快速失败短路**：空响应根因已除（thinking
       disabled, 见 G）——此短路变为纯防御性加固, 优先级降; 若仍要: raw 空 →
       跳过两次 LLM 自纠错直接交上层重试
- [x] **G. 档位语义修正（2026-09-08, 已落地）**：emotion/place "off" = 显式传
       `{"thinking":{"type":"disabled"}}`（此前实现"不传参数"= DeepSeek 默认
       思考开、reasoning 计入 max_tokens → 空 content, DeepSeek-V3#1610 同型;
       disabled 后标注 4/4 一次通过、单段 0.5-2.4s）——task_levels.py 注释与
       实现已更新 + 单测对齐
- [ ] **H. MMT 空 reply/直触发复现追踪**：12 轮高/低探针 0 空 0 触发、completion
       tokens 27-1126 远低于 4096 → 判为服务端偶发窗口而非档位; 复现时抓
       `llm chat ms=…` + usage + raw（探针 .testtmp/probe_mmt_effort.py 可复用）
- [ ] **I. 每板档位表拍板**（候选: low = wrapup/纯叙事续写预生成/MMT 闲聊;
       high = 选项板/自由输入/触发轮）——A 的决策前提, 待用户

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
