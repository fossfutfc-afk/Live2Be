# DIGEST 小手册（给压缩后的我 / 也给未来的接手人）

> 2026-09-23 建立。**读法**：先读这份（现状 + 下一步 + 陷阱），再读同目录
> `DESIGN_GRAPH_V4.md`（设计稿 = 目标形状 + 未定项 + 已否决项）。
> 这份只写"**怎么跑、动哪里、别踩什么**"，设计争论不在这里。

---

## 0. 一句话

`digest` = **记忆消化的唯一入口**：把 `events.jsonl` 里**水位之后**的新事件，经 LLM 浓缩成
`wiki.jsonl` 的节点（+ `edges.jsonl` 的边）。它是**异步旁路**（不在玩家等待主链上），
失败**静默降级**（水位不推进 ⇒ 下次可重算）。

---

## 1. 今天的形状（**两轮**，2026-09-23 现状）

```
① 触发 ──┬─ webgui: bond 完整闭环（`_wrapup_inner`, 只在 `completed=True` 时）→ engine.async_digest()
         └─ MMT: 每 25 轮（`_maybe_mmt_digest`; in_vn/in_memorial 中不触发）
② digest_segment(store, llm, events, *, character_prompt, visuals, model, temperature,
                 max_tokens, deadline_seconds, llm_timeout, extra_body,
                 aff_at_encoding, emotion_lexicon)          core/brain/wiki_v2/digest.py
③ 增量切片: new_all = seq > store.digested_seq; new_events = 排除 marker/affection
④ 段类型 + 章: _segment_domain(new_all) —— 从 marker 派生（不落库）, 给"一章一条"用
⑤ 时间线:   render_timeline(new_events, indexed=True) —— 记录级带行索引 `[28.3]`/`[28.p]`
⑥ Round A（记录员）: prompt digest_v2_round_a.md + digest_registry.build_schema(PHASE_RECORD)
      → parse_round_a(raw, seq_set=…)   ← 契约层清洗 + ⊆ 校验
      → _resolve_verbatim(索引→文本; **文本优先**) → _collapse_bond_episodes(逐章留 1 条)
      → _create_a_nodes: 建 episode/experience; 物化 emo_shape/place/place_raw;
        落 items; 摘掉 about_hint 收进 hints(内存, 不落库)
⑦ Round B（理解者）: render_cognition_list(store, cap=12) + _round_b_material(含引擎候选)
      → prompt digest_v2_round_b.md + build_schema(PHASE_UNDERSTAND)
      → parse_round_b(raw, episode_ids, target_ids)   ← 覆盖检查在这
      → apply_decisions(touch/update/add)   revise.py
⑧ 提交: store.save()（**点 + 边两个文件**）→ meta["digested_seq"] = max(seq) → save_meta()
⑨ 失败: clone_state 快照回滚（**现在带边**）; 水位不推进 ⇒ 零残留、可重算
```

**常量/口径**（`contract/digest_registry.py`）：`MAX_EPISODES=5` · `MAX_TEXT=300` ·
`MAX_TAGS=4` · `MAX_ITEMS=3` · `PLAYER_SUBJECT="player"`。
**轮次成本** = 2 次调用（`llm/task_labels.py`: `digest.round_a` / `digest.round_b`）。

---

## 2. 目标形状（`DESIGN_GRAPH_V4.md` §8 定案）

| 轮 | 读什么 | 写什么 | **禁止** |
|---|---|---|---|
| **1 产出** | 时间线（记录级带索引）· 人设锚点 · 视觉记忆 | `episode` / `belief`（+ 日后 `fact`）的**正文** + `aspect` + 情绪标量 + **`about_hint`**（自然名字） + episode 的 `items` | 引用任何现有 id · 判"这是不是新的" |
| **2 链接/裁剪** | 本轮新节点 · 现有认知（本地 id）· 引擎候选 | 边（`supports`/`contradicts`/`evolved_from`）· `update` · `merge` | **新建节点** |
| **3 归属 + entity 维护** | 全量候选表（**只有身份**）· 命中集的**当前载荷** · 本轮新节点 | `about`（映射 hint→id）· `new_entity`（**要理由**）· 重写 entity 载荷（`text`+`state`）· 别名顺手写 | 改正文 · 合并节点 |

三条纪律：**第 1 轮只 add** · **entity 载荷写者唯一 = 第 3 轮** · **候选表不进第 1 轮**
（第 1 轮的 prompt 是稳定前缀, 吃缓存）。

**已定的边界**（别顺手实现）：`about_state` 三态**退回未定**（归属 = 有边/没边）·
`fact` 先不产（§9-2 未定）· `experience` 先不动（§9-3）· `etype` 不做（只留 `x0000`=self）·
place 挂起（§9-5）。

---

## 3. 落地节点（**D0/D1 已落地**）

| # | 内容 | 状态 |
|---|---|---|
| **D0** | `entity` kind + 字段（`name`/`aliases`/`state` + episode 的 `items`）+ `_PREFIX` 的 `x` + `entities.ensure_entities`（保留号 `x0000`=self / `x0001`=sensei, 幂等, 不写盘） | ✅ `9a78337` |
| **D1** | 第 1 轮产出 `about_hint`（**不落库**）+ `items`（落库）; `DigestResult.hints` 作 D3 的接缝; 台账 `digest_hint eps= hint= items=` | ✅ `915c26e` |
| **D2** ← **下一步** | 第 3 轮执行器 + 候选表渲染: `entities.py` 加**候选表（只给身份）**与**命中集载荷**（确定性规则 = `about_hint` ∪ 别名命中正文）; `revise.apply_attribution()`: hint→id 映射、写 `about` 边、`new_entity`（要理由）、重写 entity `text`/`state`、别名顺手写。**先做成独立执行器 + 单测**（当年 `apply_decisions` 就是这么起的） | ⬜ |
| **D3** | 三轮**编排**接线: `digest_segment` 接第 3 轮（共享 deadline、共用同一份 `clone_state` 快照、`ensure_entities` 首次接线）; `llm/task_labels` 加 `digest.round_3`; `tests/stub_tasks` 加标准应答 | ⬜ |
| **D4** | **belief 的产出搬到第 1 轮**（§8.1 的真正落地）+ 第 2 轮摘掉 `add`（必须同一步, 否则功能断档） | ⬜ |
| **D5** | 端到端验收（桩 LLM 跑完整三轮: entity 出生 / `about` 边 / `items` / 载荷重写）+ 真机演练 + 更新 `AGENT_BRAIN.md` 与 `DESIGN_GRAPH_V4.md` §8 | ⬜ |

---

## 4. 陷阱清单（**踩过的 + 设计写死的**）

1. **`about_hint` 必须显式摘掉**再进 `make_node` —— 否则是"被 `from_dict` 静默忽略的未知键"，
   测试全绿、线索全丢（D1 已做，改这块时别退回去）。
2. **Round B 有"覆盖全部 episode"的结构检查**：测试里给 `decisions: []` 会**触发反馈重试**、
   把桩的 response 耗尽 → 测试红。给一条 `touch` 即可。
3. **契约层改字段要三处同改**：取值清单 + 硬规则 + **示例**。
   ⚠️ **示例才是形状的来源**（真机 `art` 命中率 0/5 = 只改清单没改示例）。
4. **给 LLM 的示例全仓只能有一种形状**，讲评/注释放形状**外面**（我踩过：写成 `key = value`
   清单, 而 schema 是 JSON ⇒ 两个形状）。改完用脚本 `json.loads` 验一遍示范块。
5. **JSON 换行只放成员之间**（字符串里折行 = 示范本身是非法 JSON, 模型照抄出坏的）。
6. **`_collapse_bond_episodes` 是逐章收口**（不是整段）：窗口常同时含 MMT 聊天（真机 13/26 条）
   与**多章**（水位清了必然）; 它留 `significance` 最高那条 + 打 `digest_a contract=bond` 告警。
7. **`experience` 有两种语义**：Round A 产的是**玩家画像**（`subject` 被契约固定为 `player`，
   进"老师的事"桶）; Round B `add` 产的是**重复模式**（`subject` 自由）。后者**不进注入**
   （`_bucket_view` 没有对应桶）—— §9-3 的合并要连这个一起修。
8. **`count` 已删**（G4）: experience 的次数 = `supports` **入边数**（`render._count_of`）。
9. **水位是单一整数** `digested_seq`；第 3 轮失败会**整体回滚**（含前两轮产出）。
   ⚠️ 而 `about_hint` **不落库** ⇒ 第 3 轮失败 = 归属信息需要靠**重跑整段**或**复查队列**找回。
10. **边的 `ts` = 本段日期**（`new_events[-1].ts`），不是"写库时刻"（`revise` 里显式传）。
11. **`_find_duplicate`** = (同 kind, `event_seq` 有交集, 主文本相同) → 命中即复用 id
    （崩溃窗口重跑的幂等靠它）。
12. **改 prompt 必跑**：`tests/core/test_wiki_digest.py`（真两轮管线 + 桩）+ `test_digest_registry.py`
    （契约清洗/schema 文档化）。**没有 promptkit 夹具**（digest 的 prompt 不在盒里）。
13. **`llm_call.llm_chat` 有 feedback 语义**：被拒 → 把 LLM 自己的输出追加成 assistant 位 +
    引擎错误, 同一上下文重试 1 次。

---

## 5. 验证配方

```powershell
# 单测（快）
python -m pytest tests/core/test_wiki_digest.py tests/core/test_digest_registry.py tests/core/test_wiki_revise.py -q --basetemp=.testtmp/pw_graph
# 全量 + 编译 + 冒烟（每节点必跑; .testtmp/pw 目录要预建）
python -m pytest tests/core tests/webgui tests/llm tests/renderer -q --basetemp=.testtmp/pw
python -m compileall -q core contract webgui apps llm tests main.py
python experiments/web_e2e/run.py
```
**真机数据现状**（验收基准, world1/haruka）: 9 节点 / 6 边 / `digested_seq=130` /
三张纪念图；`.testtmp/check_*.py` 里有几个只读探针脚本可复用（改路径即可）。

**提交纪律**：一节点一提交; 提交信息用 `git commit -F <文件>`（CJK 会炸 `-m`）。
