# Live2Be Brain 板块设计（digest → LLM WIKI + 检索注入）

> 2026-08-24 定稿（基于主流方案研究, 见会话记录"角色连贯记忆/人设一致性研究"）。
> 定位: Virtual Brain（CLAUDE.md §3.2 蓝图）的 **Phase 1 落地**——先做
> **semantic 层（LLM WIKI）**, RAG/self-model 分阶段后置。

## 0. 设计依据（研究结论 → 本项目决策）

| 研究结论（主流共识） | 本项目决策 |
|---|---|
| 分层是标配（episodic/semantic/procedural） | events.jsonl = **episodic 层（已有 ✅）**; wiki = **semantic 层（本次新增）**; 人设卡 = procedural 层（已有） |
| 整合 = **提炼 + 抽象**（Smallville 反思把事件抽象成信念）, 不是压缩 | digest 输出 **facts/beliefs/relations**（"遥香觉得被需要是第一次"——信念, 不是"第 3 场她说了 X"） |
| 文件式记忆有效（Claude Code CLAUDE.md / ST Lorebook） | **LLM WIKI = markdown/json 文件**, 可读可维护 |
| 整理频率: **每段互动结束**（非每轮, 控成本） | 触发点 = **session_end / vn_exit / wrapup 后**（事件流天然钩子, 非每轮） |
| 检索 = 关键词（Lorebook）+ 语义（RAG）混合 | Phase 1 关键词/全量注入; Phase 2 接 RAG |
| 记忆管理两条路线（MemGPT 实时 vs Smallville 离线） | 本项目走**离线批处理**（digest 后台/会话结束触发）, 不侵入主 LLM 执行 |

## 1. 分层架构

```
events.jsonl ── episodic 层（唯一真源, 已有 ✅; render_timeline 派生叙事文本）
      │  session_end / vn_exit / wrapup 后触发
      ▼
digest（主 LLM 一次调用, 离线批处理; llm/prompts/digest.md）
      │  输入: render_timeline(events) + 上次角色级 wiki（增量/去重）
      ▼
wiki ── semantic 层（本次新增, 双层级, §4.6 细化）
      ├─ sessions/{id}/brain/wiki.json   会话级（本对话消化产物）
      └─ brain/wiki.json                 角色级（跨会话汇总, 常驻注入源）
      │
      ▼
检索注入（下轮对话/新会话）
      ├─ Phase 1: start_session 注入角色级 wiki（关键词命中可选）→ system prompt 段
      └─ Phase 2: RAG 语义检索 episodic + semantic（embedding, 后置）
```

## 2. 数据层：wiki 结构（§4.6 细化, schema_version 2）

**层级 1 — 会话级**（每对话一份, digest 产出）:
```jsonc
// data/{char_id}/sessions/{conversation_id}/brain/wiki.json
{
  "schema_version": 2,
  "conversation_id": "20260824_143022_ab12",
  "summary": "天台夜谈: 老师陪遥香看杂草, 遥香第一次觉得自己被需要",
  "facts": [                                     // 关键事件/事实（角色会记住的）
    {"content": "老师蹲下来陪遥香看杂草, 说以后常来陪她", "importance": 0.8, "tags": ["老师", "杂草", "约定"]}
  ],
  "beliefs": [                                   // 抽象信念（改变行为的关键层）
    {"content": "遥香第一次觉得'被需要', 开始相信能像杂草一样堂堂正正活着", "importance": 0.9}
  ],
  "relations": [                                 // 关系变化
    {"subject": "遥香", "object": "老师", "relation": "信任加深", "note": "约定常来陪她"}
  ],
  "updated_at": "2026-08-24T15:30:00.000000"
}
```

**层级 2 — 角色级**（跨会话归并, 常驻注入源）:
```jsonc
// data/{char_id}/brain/wiki.json
{
  "schema_version": 2,
  "character_id": "igusa_haruka",
  "summary": "遥香近期主线: 天台夜谈后开始相信被需要…",
  "facts":    [/* 归并各会话 facts, 同 content 去重, importance 取高 */],
  "beliefs":  [/* 归并; 矛盾保留（Smallville: 角色可以有复杂认知） */],
  "relations":[/* 归并; 时间演化后置（Phase 3 图结构） */],
  "digested_through_ts": "2026-08-24T15:30:00.000000",   // 增量: 只消化更晚结束的会话
  "updated_at": "2026-08-24T15:30:00.000000"
}
```

## 3. digest 流程

```
触发（调用方）: 会话结束钩子——vn_cli.finish 后 / main.py 会话退出 / wrapup_after_vn 后
                （不是每轮; 失败静默降级不阻断, 下次 digest 可用同区间重试）
输入:  render_timeline(events)（带板块标签【MMT对话】【羁绊剧情】【L2D生成】）
      + 角色级 wiki 现有内容（增量上下文: 告诉 LLM 已有什么, 只提炼新的/变化的）
处理:  主 LLM 按 digest.md 规则输出 JSON
      {summary, facts: [{content, importance, tags}], beliefs: [{content, importance}],
       relations: [{subject, object, relation, note}]}
      —— 规则核心: 只写"角色会记住/影响后续行为"的; importance 0~1; tags 供关键词检索
落盘:  ① 会话级 wiki.json（原子写）
       ② 归并进角色级 wiki.json（同 content 去重, importance 取高; digested_through_ts 前移）
失败:  logger.warning + 跳过（宁缺勿错; 事件流是唯一真源, wiki 只是派生, 可重算）
```

**digest prompt 要点**（llm/prompts/digest.md, 后续实现时写）:
- 输入: timeline 文本 + 现有角色级 wiki（增量锚点）
- 强调"反思而非流水账": 从事件**提炼信念**（"老师蹲下看杂草" → "遥香第一次被需要"）
- 输出严格 JSON（facts/beliefs/relations + importance/tags）; 无合适内容 → 空数组

## 4. 检索注入

**Phase 1（简化版）**: `start_session` 时把角色级 wiki 渲染成 prompt 段注入:
```
【角色记忆（brain）】
- summary: ...
- 关键事实: ...
- 信念: ...
```
- 注入位置: system prompt 追加（momotalk/bond_story 的 build_prompt 后）
- 量控: wiki 小（几十条目内）, 全量注入 token 可控; 超限 → 按 importance 截断 top N
- 可选关键词命中: 玩家输入含 tag → 高亮相关条目（Phase 1 先全量, 命中优化后置）

**Phase 2（RAG）**: embedding 语义检索 episodic + semantic（"上次天台" → 相关事件/事实）
- 依赖: 本地 embedding（.env 注释里有 text-embedding-nomic, LM Studio）
- 索引: 事件流段落 + wiki 条目 embedding; 检索 Top-K 注入
- 后置（Phase 1 验证 wiki 有效性后再上, 避免过早引入向量依赖）

## 5. 模块划分

```
core/brain/
  __init__.py      # 导出 digest / WikiStore / build_brain_injection
  wiki.py          # WikiStore: 会话级/角色级 wiki 读写 + 归并（atomic_write_json）
  digest.py        # digest(store, char_id, session_id, llm): render_timeline → LLM → 双层级落盘
  retrieve.py      # build_brain_injection(wiki) → prompt 段文本（Phase 1 全量/重要性截断）
llm/prompts/digest.md   # digest 规则 prompt（load_prompt 加载, 与代码分离）
```

**触发钩子**（Phase 1 接入点）:
- `core/ui/vn_cli.py`: run_bond_story_vn 结束（vn_exit + session_end 后）→ digest
- `main.py` / mmt_preset: 会话退出（/exit /back / Ctrl-D）→ digest
- digest 需要 llm（主 LLM）+ store——调用方已持有两者

## 6. 分阶段路线图

| 阶段 | 内容 | 依赖 |
|---|---|---|
| **Phase 1（本次）** | wiki 双层级（facts/beliefs/relations）+ digest（digest.md prompt）+ start_session 注入 + 触发钩子 | 事件流（已有）+ 主 LLM |
| Phase 2 | RAG 语义检索（embedding episodic + wiki）→ 检索式注入 | 本地 embedding |
| Phase 3 | self-model（人设 delta: 感情状态/角色变化写回动态层）+ 关系图结构（时间演化） | Phase 1 沉淀 |

## 7. 与现有系统衔接

- **episodic 不变**: events.jsonl 唯一真源; wiki 是**派生视图**（可删可重算, 同 renderer 哲学）
- **§4.6 骨架升级**: summary/growth/relationship 简单结构 → schema_version 2（facts/beliefs/relations + importance/tags）
- **注入与现有 prompt 的关系**: brain 段是 system prompt 的**记忆层**（追加在人设/世界观之后）——与人设卡（procedural 静态）互补, 不覆盖
- **成本**: digest 每会话一次主 LLM 调用（非每轮）; 注入零成本（本地拼文本）
