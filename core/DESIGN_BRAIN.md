# Live2Be Brain 算法设计（digest → session wiki → 注入）

> 2026-08-24 定稿 v3（v2 后大幅简化）。
> **brain 是算法, 不是跨 session 实体**——每个 session 是平行世界, 各自的
> events.jsonl（真源）→ brain 算法 → 各自唯一的 wiki。另一个世界线的成长与
> 本 session 无关: 无角色级 wiki、无归并、无迁移。

## 0. 核心定位

```
brain = 算法（与 renderer 同类: 输入事件流, 输出派生视图）

加载 session → 读该 session 的 events.jsonl → digest（调主 LLM 一次）
           → 生成该 session 自己的 wiki（sessions/{id}/brain/wiki.json）
           → 注入（角色记得"这个世界线"前面的事）
```

**为什么需要 digest（而非纯事件流回灌）**: 纯回灌 = LLM 每次从基座重新搭积木
（水平不行, 搭成什么样没保证）; wiki = "之前搭好的基础", 每次从基础上继续搭
一块——这才是成长过程（用户定调, 2026-08-24）。

## 1. 数据流

```
events.jsonl（本 session 真源, 已有 ✅）
      │  加载/恢复 session 时
      ▼
digest（主 LLM 一次调用, temperature 0.3, json_object; llm/prompts/digest.md）
      │  输入: render_timeline(events) + 本 session 视觉记忆（gallery prompts）
      ▼
sessions/{id}/brain/wiki.json（本 session 的 wiki, 派生视图）
      │
      ▼
注入（recall）: wiki → 【角色记忆】段（第一人称视角包装）→ system prompt
      └─ 恢复时角色记得本世界线前面的事; 新 session（新世界线）零注入
```

## 2. wiki 结构（schema_version 2）

```jsonc
// data/{char_id}/sessions/{conversation_id}/brain/wiki.json
{
  "schema_version": 2,
  "conversation_id": "20260824_143022_ab12",
  "summary": "天台夜谈: 老师陪遥香看杂草, 遥香开始相信自己被需要",
  "facts":    [{"content": "老师说以后常来陪她看杂草", "importance": 0.8, "tags": ["老师", "杂草"]}],
  "beliefs":  [{"content": "遥香第一次觉得自己被需要", "importance": 0.9}],
  "relations":[{"subject": "遥香", "object": "老师", "relation": "信任加深", "note": "约定常来陪她"}],
  "updated_at": "2026-08-24T15:30:00.000000"
}
```

- 条目 = 自然语言 content + 元数据（importance 排序 / tags 检索）——"内容天然是
  语言, JSON 只是给每条记忆挂元数据的外壳"（结构化 = 可检索）
- digest 输出规则（digest.md）: 提炼而非记录; 只写角色会记住/影响行为的;
  视觉记忆可提炼成画面事实; 预设经历（experience）已知晓不重复提炼; 矛盾保留

## 3. 视觉记忆（生图 prompt 即视觉记忆）

- **洞察**: memorial 生图时主 LLM 亲笔写的 prompt 就是画面文字化——视觉记忆
  无需视觉 LLM 转述（"看图说话"反而脱离剧情上下文）
- **存储**: gallery/{scene_id}.json 是视觉记忆底层（prompt + 时间 + 来源会话）
- **digest 收录**: 输入附本 session gallery prompts（l2d 事件 → 同名 json）,
  LLM 提炼值得记住的画面 → facts/beliefs

## 4. 注入（recall, 第一人称视角包装）

- 第三人称存储（digest 输出稳定）→ 注入时转第一人称: char_name 替换为"我"
  （"遥香第一次觉得被需要" → "我第一次觉得被需要"）, summary → "我记得那段日子…"
- 依据: Perspective-Bounded Memory（arXiv 2606.25632）+ 自我参照效应
- 量控: importance 降序截断（facts 10 / beliefs 5 / relations 5）; 空 wiki → ""

## 5. 模块（core/brain/ = 纯算法, 3 个文件）

```
core/brain/
  __init__.py           # 导出 WikiStore / digest_session / build_brain_injection
  hippocampus.py        # 海马体 — session wiki 读写（WikiStore: load/save）
  consolidation.py      # 巩固 — digest_session（events.jsonl → 本 session 的 wiki）
  recall.py             # 回忆 — build_brain_injection（wiki → 第一人称注入段）
llm/prompts/
  digest.md             # digest 规则（提炼 facts/beliefs/relations + importance/tags）
```

**experience 定位**: raw material 直接给 AI 读（五件套 build_prompt 静态注入,
不进 wiki）——author 静态设定 vs 运行时动态记忆, 混来源污染控制边界。

## 6. 边界

- **events.jsonl 唯一真源**: wiki 是派生视图（可删可重算, 原子写）
- **digest 不阻断主流程**: 失败静默降级（None）
- **平行世界**: 无跨 session 归并/迁移/角色级 wiki; 新 session 从五件套重新开始
- **频率**: 加载/恢复 session 时 digest（非每轮, 控成本）
- **远期（不做）**: 五件套动态增长（LLM 改 profile 等核心文件——废案, 无前车之鉴）;
  RAG 语义检索; 副本时间胶囊/配额（如需要再议）
