# DESIGN_CHOICE_PREGEN — 选项候选预生成（sibling 草稿支 + 按需展开, 定稿）

> ⚠️ **已归档（2026-09-10）**：本文描述**旧契约**下的选项候选预生成。
> 2026-09-10 用户拍板：VN 收敛链即终局、真分歧不立项，**sibling 候选为终态**；
> 新契约（`docs/DESIGN_STREAM_CONTRACT.md`）下"选项"被 Sensei 台词槽取代，
> 本机制整体退役。留作历史与设计意图参考，不再更新。

> **状态**: 设计定稿 2026-09-08 用户方案; **N1 + N2a-N2d 已落地 master**
> （fork 原语 + spawn/消费/清理/开关——见文末"落地记录"）。
> **背景**: 选项等待的剩余空间 = max(0, 下一板生成 − 分支播放)。降档路线（A）
> 被用户否决（创作档必须 high 才有文风）; 本方案用"候选双路预生成"把等待窗口
> 前移到**选项阅读期**, 接受 ≤2× token（+ 前缀缓存折扣）。
> **关联**: DESIGN_SCENE_STREAM §10 / DESIGN_BOND_CONTRACT_V2 §6.5/§8 /
> TODO.md（选项等待 A–I; C 由本方案受控化）。

## 落地记录（分步节点）

- **N1 引擎 fork 原语** `BondStoryEngine.fork_for_pick(picked)`: 只读面共享
  （system 同字节 → 跨支前缀缓存） + 可变面独立（历史 A1 内嵌裁决行/标注链
  carry/place 延续/para_seq）; director 克隆; `_draft` 标记;
  守卫: 未开场/无上一板/空白 picked/纪念中 → None（tests/core/test_engine_fork.py）
- **N2a spawn**: `BondState.choice_candidates` + `_spawn_candidates`（每候选
  fork + daemon 线程 `send("（继续）", annotate=True)`——不持 chat._lock /
  不占 busy, 同步标注 → 消费即视觉就绪）; worker 池身份检查（作废即丢弃）
- **N2b 消费**: `bond_turn` 分支裁决——命中就绪候选 → 切主引擎（跳过
  record_picked 防重复）+ 下一板入 pregen 通道（点继续零等待）; generating
  → 3s 短窗等待; failed/超时 → 老路（record_picked + 分支播放期单路 pregen）;
  补口: pregen 消费提升出 choices 板 → 链式 spawn
- **N2c 清理/观测**: `_discard_candidates` 统一作废; spawn 自清旧池;
  bond_status 暴露 candidates（picked+status）
- **N2d 开关**: settings.toml `[bond] choice_pregen = "off" | "sibling"`
  （tree 预留未实现; 缺省/异常 → sibling 开; off → 老路）; 全量 489 绿
- 成本实测: 双路 prompt 近全量缓存命中（miss 262-1072 vs hit ~6.2-6.4k）,
  增量 ≈ 1 个候选支输出 token（1.9-2.7k）; 候选并发生成时墙钟 ≈ 单路

## 0. 方案语义（用户 2026-09-08 口述, 校准后）

- 一个板块带 choices（2~3 个候选项）→ 板生成完成即 **fork 出候选支草稿**:
  每个候选 = 引擎克隆（历史尾部 A1 同形回录"（选择了: X）"）+ 后台生成下一板
  （输入"（继续）"）;
- 玩家裁决 → **选中支立即端上**（已生成 = 零等待; 未生成完 = 等它, 与现状同）;
  未选候选支 → **作废 GC**（零痕迹）;
- 选中支播完后继续在其上 fork 下一层候选——**宽度 = 选项数(≤3), 只沿选中路径
  展开**, 不是整树预生成; 展开总生成量 ≈ 层数 × 候选数(2~3) → 成本上限约 2-3×;
- **无 choices 的纯推进板**保持现状单链 bridge 预生成（长链, 无分叉）。

## 1. 草稿生命周期与落库边界（Q1 定稿: 不建专用运行时文件）

```
主线板(mem) ──fork──► 候选支草稿(mem) ──生成──► 就绪
                        │ 玩家裁决
                        ├─ 选中 ──► 观测/裁决点 ──► append 事件流(唯一真源)
                        └─ 未选 ──► 作废 GC(不落库, 零痕迹)
```

- 草稿 = **纯内存态**（BondState: 主线 scene_obj + 候选支池; 每条支一个 fork
  引擎）。**不新建运行时文件**: append-only events.jsonl 仍是唯一真源——
  候选支"未被玩家观测/裁决", 进任何持久层都会污染恢复语义;
- 落库时机不变 = 现有 `_log_scene`（裁决消费且前端已观测）; 事件流对候选支
  无感知 → 恢复/回放永远从主线重建;
- 进程重启丢候选支 = 自动退回"单路等待"（无一致性风险, 只是加速失效）。

## 2. 引擎 fork 原语（核心工程点）

- 只读共享: `_system_prompt`（逐字节同一构建 → 前缀缓存跨支成立的关键）、
  `_lexicon_*`、`_place_keys`、`llm`、`director` 引用;
- 深拷贝(mutable): `_history`（尾部按 picked 重渲, A1 同形）、`_carry_text/
  _carry_emo/_para_seq/_seed_anchor`（标注链分岔——预期内）、`_current_place`
  （背景/place 分岔——预期内）、`_in_memorial/_memorial_used/_last_payload`;
- 需防: 候选支生成**不写** live 引擎任何状态; 消费时主 state 切换到选中支的
  fork（引擎实例接管）;
- 候选支 annotation: fork 后各走各的 lane/链（标注链分岔在预期内, 用户确认）。

## 3. 作废/边界规则

- 候选支产出 story_end/memorial_enter 而玩家选了另一支 → 作废（不落库）;
  选中支若未到收尾, 由它自己的后续生成自然处理;
- 作废支的 LLM 调用/token = 预期开销（≤ 每层 1-2 个作废板）;
- 语义重试/整场重来只发生在所在支内部（版本 token 语义沿用 P2 设计）。

## 4. 模式参数（用户询问——分期引入）

```
settings.toml [bond]
  choice_pregen = "off" | "sibling" | "tree"   # 缺省/异常 = sibling（N2d 已落地）
```
- `off`: 现状单路（分支播放期预生成一路）;
- `sibling`: 本方案单层——每层只展开当前板候选（推荐首期落地形态）;
- `tree`: 沿路径递归展开（预判收益趋近 0——收敛链下兄弟支高度相似, 缓存与
  内容都重叠; 数据支撑前不做）。

## 5. 验收指标与先导验证

- 成本先导（probe_fork_cost, 真实 API）: 双路 cache_hit/miss、增量耗时、
  兄弟支内容相似度——数字决定 sibling 是否值得工程化;
- 就绪率: 选项点下后 0 等待率（目标 ≥ 现状 +20pp）;
- 作废 token 占比（预期 ≤50-67%）; 事件流零草稿残留（diff 审计）。

## 6. 分歧感测试授权（用户 2026-09-08）

用户授权: 为测试分支语义/缓存对比, 可临时把 bond_story_rules.md 的收敛
规则（规则 4）改出分歧感。注意: rules 进盒B（system）→ 改动须同批刷新
promptkit 夹具; 真分歧仍属契约级改动（DESIGN_BOND_CONTRACT_V2 §8 范围）。
建议正式分歧实验走"实验分支 + 夹具同批提交 + 测完回退", 不做全局默认。
