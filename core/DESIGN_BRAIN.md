# Live2Be Brain 板块设计（digest → LLM WIKI + 检索注入 + 记忆生命周期）

> 2026-08-24 定稿 v2（基于主流方案研究 + 三轮设计细化）。
> 定位: Virtual Brain（CLAUDE.md §3.2 蓝图）的 **Phase 1 落地**——semantic 层
> （LLM WIKI）+ 记忆一致性机制; RAG/self-model/图结构分阶段后置。

## 0. 设计依据（研究结论 → 本项目决策）

| 研究结论（主流共识） | 本项目决策 |
|---|---|
| 分层是标配（episodic/semantic/procedural） | events.jsonl = episodic（已有 ✅）; wiki = semantic（新增）; 五层卡 = procedural（已有） |
| 整合 = 提炼 + 抽象（Smallville 反思）, 不是压缩 | digest 输出 facts/beliefs/relations（"老师蹲下看杂草" → 信念"遥香第一次觉得被需要"） |
| 文件式记忆有效（Claude Code / ST Lorebook） | LLM WIKI = json 文件双层级, 可读可维护 |
| 整理频率: 每段互动结束（非每轮, 控成本） | 触发 = 会话退出（/exit /back Ctrl-D）; **不按 VN 结束**（session_end 语义是 VN 结束, wrapup 后还有 MMT 事件） |
| 检索 = 关键词 + 语义混合 | Phase 1 全量注入（importance 截断）; Phase 2 RAG |
| 记忆管理: 离线批处理（Smallville） | digest 离线批处理, 不侵入主 LLM 执行 |

## 1. 记忆生命周期（v2 核心: 时间胶囊 + 哈希 + 迁移 + RP 演出）

```
config 五层卡（author 静态源）
  │  start_session（新会话）:
  │    ① 复制副本 → sessions/{id}/cards/（五层全量, 时间胶囊）
  │    ② 对比: 当前 config 哈希 vs 角色级 wiki.character_hash
  │
  ├─ 一致 ──▶ 正常: 五层卡（副本）+ brain 段（记忆有效）注入
  │
  └─ 不一致（author 改卡 / 用户改 wiki）
       ├─▶ LLM 保守迁移 wiki（只改冲突项, 保留非冲突; 重试 3 次, 耗尽降级 stale）
       ├─▶ 更新 character_hash
       └─▶ RP 注记: 新会话第一轮 system_note（"头脑剧痛, 记忆不对劲"）
                │
                ▼
          对话进行中（用副本, 中途改卡无效）
                │
                ▼
        digest（会话退出, 基于副本人设）→ wiki 双层级落盘
```

### 1.1 副本机制（会话内冻结 + 恢复一致）

- **start_session（新会话）**: engine 复制 config 五层卡 → `sessions/{id}/cards/*.yml`
- **对话期间**: engine 用副本（author 中途改 config 不影响当前对话——当前对话记忆一致）
- **resume（恢复）**: 从该会话副本加载（**不是最新 config**）——存档 = 时间胶囊（这个存档就是那个时间点的角色）
- 代价: 每会话几 KB × 配额上限（§1.2）, 量级可控

### 1.2 存档配额（防爆盘）

- **每角色至多 3 个会话存档**（`MAX_SESSIONS_PER_CHAR = 3`, store.py 常量, 可配）
- create 时检查: 超限 → **优先删最旧已结束会话**（已 digest, 可重建）→ 全未结束则删最旧 + warning
- "全局 100 总配额 + 用户分配"留 GUI/命令管理（远期）

### 1.3 变更检测（哈希）

- `compute_character_hash(files)`: 五层卡（存在的文件）内容哈希
- 角色级 wiki 存 `character_hash`（= 上次 digest 时的 config 哈希）; 会话级 wiki 存 `character_hash`（副本哈希）
- wiki 文件本身存 `self_hash`（篡改检测: 手动改 wiki → 哈希不符 → 视为"记忆被外部植入"）

### 1.4 保守迁移（LLM 修订记忆）

- 检测到变更 → LLM 读新人设概要 + 旧 wiki → 输出修订后 wiki
- **迁移规则（wiki_migrate.md）**: 只改写与新人设【冲突】的条目; 保留不冲突的旧记忆;
  新人设新增设定由后续 digest 自然积累
- **失败处理: 重试 3 次（MAX_WIKI_RETRIES）, 耗尽降级**（旧 wiki 标 stale 不注入 + warning——不阻塞新会话）

### 1.5 RP 演出（记忆篡改玩法）

- **Phase 1**: 变更检测 → 新会话第一轮 `system_note`
  （"你感觉头脑一阵剧痛……有些记忆变得模糊/不太对劲。请以角色的方式自然表达异样感"）
- **未来**: bond-story **热更改检测**（运行时轮询哈希）→ LLM 假装头痛 → **强制结束当前对话**——把"篡改"做成剧情玩法

### 1.6 experience 定位（v2 确认）

- **experience.yml = raw material 直接给 AI 读**（build_prompt 静态注入, 不进 wiki）
- 理由: experience 是 author 静态设定（权威）; wiki 是运行时动态派生——混来源污染 author 控制边界
- 防重复: digest prompt 注明"预设经历你已知晓, 只提炼新发生且人设里没有的"

### 1.7 视觉记忆（v2.1: 生图 prompt 即视觉记忆）

- **洞察**: memorial 生图时主 LLM 亲笔写的 prompt 就是**画面文字化**——视觉记忆
  无需视觉 LLM 转述（"看图说话"反而脱离剧情上下文）
- **存储**: gallery/{scene_id}.json 是视觉记忆底层（prompt + 时间 + 来源会话, 已有）
- **digest 收录**: 输入附本会话 gallery prompts, LLM 提炼值得记住的画面 → facts/beliefs
- **不重复存储**: wiki 不复制 prompt（gallery 是家）, 只引用提炼

## 2. 分层架构与数据流

```
events.jsonl ── episodic（唯一真源, 已有 ✅）
      │  会话退出触发
      ▼
digest（主 LLM 一次调用, temperature 0.3, json_object; llm/prompts/digest.md）
      │  输入: render_timeline(events)（带板块标签）
      │        + 本会话 gallery 的 prompts（**视觉记忆素材**——生图 prompt 即
      │          画面文字化, 主 LLM 亲笔, 无需视觉 LLM; gallery 是底层存储）
      ▼
wiki ── semantic 层（双层级）
      ├─ sessions/{id}/brain/wiki.json   会话级（本对话消化产物）
      └─ brain/wiki.json                 角色级（跨会话汇总 + character_hash）
      │
      ▼
注入（start_session / bond_story.start_session）
      ├─ 五层卡（副本）build_prompt 注入（已有）
      └─ brain 段: build_brain_injection(角色级 wiki, 哈希匹配才注入)
```

## 3. 数据层：wiki 结构（schema_version 2）

**层级 1 — 会话级**:
```jsonc
// data/{char_id}/sessions/{conversation_id}/brain/wiki.json
{
  "schema_version": 2,
  "conversation_id": "20260824_143022_ab12",
  "character_hash": "a1b2c3...",          // 本会话副本哈希（digest 基准）
  "summary": "天台夜谈: 老师陪遥香看杂草…",
  "facts": [{"content": "老师说以后常来陪她看杂草", "importance": 0.8, "tags": ["老师", "杂草", "约定"]}],
  "beliefs": [{"content": "遥香第一次觉得'被需要'", "importance": 0.9}],
  "relations": [{"subject": "遥香", "object": "老师", "relation": "信任加深", "note": "约定常来陪她"}],
  "updated_at": "2026-08-24T15:30:00.000000"
}
```

**层级 2 — 角色级**:
```jsonc
// data/{char_id}/brain/wiki.json
{
  "schema_version": 2,
  "character_id": "igusa_haruka",
  "character_hash": "a1b2c3...",          // 上次 digest 的副本哈希（变更检测基准）
  "self_hash": "d4e5f6...",                // 本文件哈希（篡改检测）
  "summary": "遥香近期主线: 天台夜谈后开始相信被需要…",
  "facts": [/* 归并: 同 content 去重, importance 取 max, tags union */],
  "beliefs": [/* 归并; 矛盾保留 */],
  "relations": [/* 归并; (subject,object,relation) 去重, note 取最近 */],
  "digested_through_ts": "2026-08-24T15:30:00.000000",
  "updated_at": "2026-08-24T15:30:00.000000"
}
```

## 4. 目录架构（v2 定稿: 什么存在哪里）

**新增代码**:
```
core/brain/
  __init__.py           # 导出 WikiStore / digest_session / migrate_wiki / build_brain_injection
  hippocampus.py        # 海马体 — 记忆存储: WikiStore 双层级读写 + 归并 + 哈希
  consolidation.py      # 巩固 — 睡眠整合: digest_session（timeline → LLM → 落盘）
  reconsolidation.py    # 再巩固 — 记忆修订: migrate_wiki（保守迁移, 重试 3 次）
  recall.py             # 回忆 — 检索注入: build_brain_injection（importance 排序截断）
llm/prompts/
  digest.md             # digest 规则（提炼 facts/beliefs/relations + importance/tags; 对应 consolidation）
  wiki_migrate.md       # 保守迁移规则（只改冲突项; 对应 reconsolidation）
```

**新增数据**:
```
data/{char_id}/
  sessions/{conversation_id}/
    cards/                    # ★ 五层卡副本（时间胶囊, 对话期/恢复用）
      profile.yml / personality.yml / knowledge.yml / experience.yml / typical.yml
    brain/
      wiki.json               # 会话级消化产物
  brain/
    wiki.json                 # 角色级汇总（character_hash / self_hash）
```

**改动现有文件**:
```
core/session/store.py      # 配额: MAX_SESSIONS_PER_CHAR, create 时检查 + 删最旧
core/momotalk.py           # snapshot_cards(副本) + brain 段注入 + resume 从副本加载
core/bond/bond_story.py    # brain 段注入（哈希匹配才注入）
core/parsing/dynamic_character_parser.py  # CharacterLoader.load_from_directory（副本恢复用）
core/mmt/mmt_preset.py     # 会话退出触发 digest; 配额提示
main.py                    # 会话退出触发 digest; snapshot_cards 调用
```

## 5. 分阶段路线图

| 阶段 | 内容 |
|---|---|
| **Phase 1（本次）** | wiki 双层级 + digest + 保守迁移 + 副本时间胶囊 + 配额 + 注入 + RP 注记（新会话第一轮）+ 触发钩子 |
| Phase 2 | RAG 语义检索（embedding episodic + wiki）→ 检索式注入 |
| Phase 3 | self-model（人设 delta）+ 关系图（时间演化）+ bond-story 热更改强制结束玩法 |

## 6. 关键边界（防回归）

- **events.jsonl 唯一真源**: wiki/cards 全是派生视图（可删可重算）
- **digest 不阻断主流程**: 失败静默/降级; 重试仅限迁移（3 次）
- **不写回五层卡**: 记忆不覆盖 author 静态设定; experience 保持 raw 注入
- **测试兼容**: 触发在 main 退出路径（不测）; run_bond_story_vn 不触发 digest; 无 store 零注入——现有测试零改动预期
