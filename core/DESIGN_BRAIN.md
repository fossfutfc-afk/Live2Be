# Live2Be Brain 算法设计（digest → session wiki → 注入）

> 2026-08-24 定稿 v3.1（v3 后加入"联想 digest"）。
> **brain 是算法, 不是跨 session 实体**——每个 session 是平行世界, 各自的
> events.jsonl（真源）→ brain 算法 → 各自唯一的 wiki。另一个世界线的成长与
> 本 session 无关: 无角色级 wiki、无归并、无迁移。

## 0. 关键思维记录（本设计是怎么长出来的）

| 思维 | 内容 |
|---|---|
| **搭积木论证**（为什么 digest 而非纯回灌） | 纯事件流回灌 = LLM 每次从基座重新搭积木（断连一次重搭一次, 搭成什么样没保证, 水平不行）; wiki = "之前搭好的基础", 每次从基础上继续搭一块——这才是人的成长过程 |
| **平行世界**（brain 是什么） | 每个 session 是独立世界线, 角色有自己的成长（本 session 的 wiki 控制）; 另一个世界线的成长与本 session 无关——brain 是**算法**（方法论共享, 记忆私有） |
| **联想记忆**（digest 的升级） | 人的成长 = 新旧经历的碰撞: "今天和女朋友约会" + "想起小时候的孤独" → 综合出"我从孤独走向被爱"——跨事件的联系才长出深层信念, 孤立摘要产不出。**越复杂越像人类** |
| **情感保底**（双通道回忆） | 回忆概率 = 时间衰减 × 情感/重要性。纯遗忘曲线丢情感维度——玩家对"初次相遇"极执着, 高 significance 记忆（初遇/告白/约定）必须**永存**: 珍贵通道保底 + 日常通道对数正态衰减 |
| **视觉记忆**（生图 prompt 即视觉记忆） | memorial 生图时主 LLM 亲笔写的 prompt 就是画面文字化——无需视觉 LLM 转述（"看图说话"反而脱离剧情上下文） |
| **第一人称注入**（视角） | 第三人称存储（digest 稳定）→ 注入时转第一人称（"我记得…"）——角色视角比旁观者视角更贴角色认同（Perspective-Bounded Memory, arXiv 2606.25632） |

## 1. 数据流（v3.1: 增量 + 联想 digest）

```
events.jsonl（本 session 真源, 已有 ✅）
      │  加载/恢复 session 时
      ▼
digest（主 LLM 一次调用; llm/prompts/digest.md）
      │  输入:
      │    ① render_timeline(新增事件, seq > digested_seq)   ← 增量, 不重读全量
      │    ② 本 session 视觉记忆（新增 l2d 的 gallery prompts）
      │    ③ 回想起来的旧记忆（见 §3 联想 digest）            ← 新旧碰撞
      ▼
sessions/{id}/brain/wiki.json（本 session 的 wiki; 含 digested_seq）
      │
      ▼
注入（recall）: wiki → 【角色记忆】段（第一人称）→ system prompt
      └─ 恢复时角色记得本世界线前面的事; 新 session（新世界线）零注入
```

## 2. 增量 digest（digested_seq）

- wiki 增加 `digested_seq: int`（上次消化到的最大事件 seq; 0 = 未消化）
- digest_session: 读 events（便宜, ms 级）→ `new_events = seq > digested_seq`
  - 无新增 → 直接返回旧 wiki（**0 次 LLM 调用**）
  - 有新增 → 只提炼新增部分; 输入附旧 wiki 概要作上下文（"已有记忆, 只提炼新增/变化"）
- LLM 输出**新增条目** → 引擎合并进旧 wiki（同 content 去重, significance 取高）→ 更新 digested_seq
- 收益: 省 token（只处理新增）、**旧记忆稳定**（不重写, 只在旧基础上追加——同一世界线的时间推进, "搭积木"）; 同 session 重复恢复不重复花钱
- 注: 这是**同一 session 内**的增量合并（同一世界线）, 不是跨 session 归并——平行世界语义不变

## 3. 联想 digest（v3.1 核心: 新旧碰撞出成长）

**机制**: digest 不只消化新增, 还"想起"相关旧记忆, 一起交给 LLM 综合——
新剧情 + 旧记忆的联系 = 深层信念/成长弧线（"约会" + "儿时孤独" → "从孤独走向被爱"）。

**两步联想（v3.1 落地 = 轻量召回; RAG 后置）**:

```
A. 轻量召回（零依赖, 先做）: 从【旧 wiki 条目】按关键词/tags 匹配召回复条
   （旧 wiki 条目短、有 tags、相关性天然强——recall.py 一物两用: 注入 + digest 联想）
B. 回忆摘段（v3.2 升级为双通道, "越复杂越像人类"）: 见下
C. RAG 回忆（Phase 2）: embedding 检索与新增语义相关的旧事件（更准的联想,
   本地 nomic embedding 已就绪）
```

### 3.1 双通道回忆（v3.2: 情感保底 + 遗忘曲线）

**核心公式**: 回忆概率 = 时间衰减 × 情感/重要性。纯遗忘曲线（对数正态）丢情感
维度——玩家对"初次相遇"极执着, 高情感记忆必须永存。所以回忆摘段分两通道:

```
每次 digest 的回忆摘段:
┌─ 珍贵通道（30% 概率, 可调）: 从 wiki 高 significance 条目选（significance ≥ 0.8
│   或 top-3）→ **永不衰减（保底）**
│   → 初遇/告白/约定都在这里——digest 时 LLM 已标 significance, 零新成本;
│     玩家执着的记忆 = 高 significance 记忆永存
│
└─ 日常通道（70%）: 对数正态加权摘历史事件原文（遗忘曲线）
    → 近期高峰 + 长尾（偶尔想起很久以前）——日常质感, 越复杂越像人类
```

**参数（per 角色可配, 呼应 CLAUDE.md §3.2.3 衰减系数设计）**:

| 参数 | 默认 | 含义 |
|---|---|---|
| `precious_ratio` | 0.3 | 珍贵通道概率（情感重的角色调高） |
| `significance_threshold` | 0.8 | 什么算"珍贵记忆"（significance 门槛） |
| `sigma` | 1.5 | 日常通道衰减快慢（天然呆角色 σ 大, 回忆更飘忽） |
| `mu` | 0 | 对数正态峰值位置（多久前的事最容易想起） |

digest.md 规则新增: "你突然想起了一些旧事——如果与当前经历有联系, 综合提炼出
更深层的认知/成长（如'从孤独到被爱'的弧线）; 若无关就忽略, 不要硬凑"。

## 4. wiki 结构（schema_version 2）

```jsonc
// data/{char_id}/sessions/{conversation_id}/brain/wiki.json
{
  "schema_version": 2,
  "conversation_id": "20260824_143022_ab12",
  "digested_seq": 87,                    // 增量: 上次消化到的事件 seq（v3.1）
  "summary": "天台夜谈: 老师陪遥香看杂草, 遥香开始相信自己被需要",
  "facts":    [{"content": "老师说以后常来陪她看杂草", "significance": 0.8, "tags": ["老师", "杂草"]}],
  "beliefs":  [{"content": "遥香第一次觉得自己被需要", "significance": 0.9}],
  "relations":[{"subject": "遥香", "object": "老师", "relation": "信任加深", "note": "约定常来陪她"}],
  "updated_at": "2026-08-24T15:30:00.000000"
}
```

- 条目 = 自然语言 content + 元数据（**significance 0~1 记忆显著性**排序 / tags 检索）
  = 结构化可检索; 旧字段 importance 读时兼容（significance 缺失取 importance）
- **significance 与 affection_exp_delta 正交**（DESIGN_SEGMENT.md §4）:
  affection = 好感（情感价）; significance = 记忆深刻度——悲伤剧情可高 significance
  低 affection, 分开判断不合并
- digest 输出规则: 提炼而非记录; 只写会记住/影响行为的; 视觉记忆可提炼成画面事实;
  预设经历（experience）已知晓不重复提炼; 矛盾保留

## 5. 注入（recall, 第一人称视角包装）

- 第三人称存储 → 注入时转第一人称: char_name 替换为"我", summary → "我记得那段日子…"
- 量控: significance 降序截断（facts 10 / beliefs 5 / relations 5）; 空 wiki → ""

## 6. 模块（core/brain/ = 纯算法, 3 个文件）

```
core/brain/
  __init__.py           # 导出 WikiStore / digest_session / build_brain_injection
  hippocampus.py        # 海马体 — session wiki 读写（WikiStore: load/save, digested_seq）
  consolidation.py      # 巩固 — digest_session（增量 + 联想: 新增事件+旧记忆召回 → wiki）
  recall.py             # 回忆 — build_brain_injection（注入, 第一人称）+ 联想召回辅助
llm/prompts/
  digest.md             # digest 规则（增量/联想/提炼 facts/beliefs/relations）
```

**experience 定位**: raw material 直接给 AI 读（五件套 build_prompt 静态注入,
不进 wiki）——author 静态设定 vs 运行时动态记忆, 混来源污染控制边界。

## 7. 路线图

| 阶段 | 内容 |
|---|---|
| **Phase 1（当前）** | 增量 digest（digested_seq）+ 轻量召回（旧 wiki 关键词匹配）+ 随机摘段（可选）+ 注入 + 接线 |
| Phase 2 | **RAG 回忆法**: embedding 检索相关旧事件（本地 nomic embedding）——联想升级 |
| 远期（不做） | 五件套动态增长（LLM 改 profile 等核心文件——废案, 无前车之鉴）; 副本时间胶囊/配额 |

## 8. embedding/RAG 实现说明（Phase 2 前置, 用户只需做一件事）

- **不需要写 C/Cpython RAG**——Python 生态现成:
  - embedding: 本地 `text-embedding-nomic-embed-text-v1.5`（LM Studio, OpenAI 兼容,
    `.env` 注释已有示例）——`client.embeddings.create(input=[...])`
  - 检索: 会话量小（每 session 几百事件）→ **numpy 余弦相似度**即可（毫秒级）,
    无需向量数据库（chromadb/faiss 是量级大了才需要）
- **用户 Phase 2 前唯一要做**: 启动本地 embedding 服务
  `lms server start && lms load text-embedding-nomic-embed-text-v1.5`
- 代码侧（届时我来写）: `core/brain/` 加 `recall_embed.py`（embedding client +
  余弦检索 → 相关旧事件 top-k）——纯 Python, 不碰 C

## 9. 边界

- **events.jsonl 唯一真源**: wiki 是派生视图（可删可重算, 原子写）
- **digest 不阻断主流程**: 失败静默降级（None）
- **平行世界**: 无跨 session 归并/迁移/角色级 wiki; 新 session 从五件套重新开始
- **频率**: 加载/恢复 session 时 digest（非每轮, 控成本）; 增量保证重复恢复零重复成本
