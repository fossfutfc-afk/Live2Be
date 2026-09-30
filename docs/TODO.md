# TODO.md — 施工顺序表（**digest 三层重排**）

> 建立 2026-09-27。**给用户审的表** —— 一行一个节点、一个提交，判据写死。
> 规格在 `docs/DESIGN_DIGEST_LAYERS.md`；顶层裁决在 `PROCEED.md §5`。
> **当前状态：代码一行未动。**

---

## 0. 顺序原则（四句话）

1. **输入面先修**（L1 的切分形状）—— 不修的话，后面每一步的输入都是脏的（材料漏 40%、切分交错）
2. **免费的先做**（边属性 / 视野补齐 / **MMT 的发现**）—— 它们零或极低 LLM 成本，且是好几个节点的前置
3. **花钱的放最后**（`collision` / 取用重排）—— 前面没通，花了钱也白花
4. ⭐ **`L-M`（MMT 发现）要早做** —— 它把 link 的成本降到接近 0，**L2 因此不必自己找组**（`DESIGN_DIGEST_LAYERS §0.1(f)`）

---

## 1. 简表（15 步）

| # | 步 | 做什么（一句话） | 改动面 | 判据（可测） | 依赖 | 量级 |
|---|---|---|---|---|---|---|
| **N1a** | ✅ **已落地 2026-09-29** —— 加 `akin` + 对称 rel 规范化 | `REL_AKIN`（episode ↔ episode，对称）· `RELS` 7→8 · ⭐ `SYMMETRIC_RELS` + `canonical_for`（**对称性的唯一实现处**）· 顺手修 `clone_state` 位置参数 | `graph.py` · `store.py` | 对称正反只留一条 · 有向边不被交换 · `akin` **不进推断表**（旧档的 `links` 是"相关"不是"同类"，不猜）· `clone_state` 逐字段 + **结构性守门** | — | 已完成（全量 1095 passed · B 冒烟 PASS） |
| **N1b** | **群（`group` kind + `member_of`）** | `KINDS` + `"group"`（`title` 必填 · 前缀 `g`）· `REL_MEMBER_OF` 进 `RELS`（8→9） | `graph.py` · `nodes.py` | 群节点往返稳定 · 成员 = `edges_to(gid, "member_of")` · **多归属** · `audit` 不把 group 当 belief | N1a | ~40 行 |

> ⚠️ **原 N1「边加属性」已作废**（2026-09-29 用户裁决）：`Edge` 加 `aspect`/`conf` + `groups_of()` 那套
> 被 **`DESIGN_MMT_NEW_ACTION.md` §4.5** 取代 —— **群 = 节点 + `member_of` 边，边不带属性**。
> 理由：① 成员**会生长、各有自己的时刻**（"什么时候加入的"是信息，`aspect` 存不下）
> ② `akin`（她觉得像）与 `member_of`（L2 判定）**是输入与输出，不能合并**。
> ⇒ **N5 只依赖 N1a**（她发现 → 落 `akin` 边）；群是 **N7**（L2 分群）才建的，走 **N1b**。
| **N2** | **视野补齐（"深"）** | 接线 `render_organize_view` 的**边渲染**；`render_cognition_list` 给 belief **印被引数**；候选带 **why** | `render.py` · `digest.py` | 输入里**能看到边、被引数、why** | — | ~40 行 |
| **N3** | **L1 区间化** | `event_seq` → `span:[from,to]`；引擎 `_expand_spans` / `_resolve_overlaps` / `_backfill_unclaimed` | `contract/digest_registry.py` · `digest.py` · prompt | ⭐ **覆盖率 100%** · 密度 1.0 · 交错 0 · 旧档兼容 | — | ~50 行 **下游零改动** |
| **N4** | **L1 记账合并** | `promise` + `on_mind` 并进 L1 同一次调用；**`habits` 槽删掉** | `digest.py` · `notes.py` · 契约 | L1 产 promise ops + on_mind · `habits` 全仓只剩退役注释 | N3 | ~60 行（含删） |
| ⭐ **N5** | **L-M：MMT 的「想起 + 发现」** | ① 引擎召回 **1~2 条旧 episode**（接线 `recall_subgraph`，今天零调用者）② 注入一段"你想起的事" ③ prompt 给她一个动作 ④ 她引用 ⇒ **锚点校验** ⑤ 落**待挂记录** | `mmt/engine.py` · `promptkit` · `render.py` · `store.py`（待挂） | ① 召回有接线（非零调用者）② **编造的引用被丢**（锚点校验单测）③ 待挂记录可查 | N1 N3 | ~110 行 ⭐ **本主题的价值核心** |
| **N6** | **候选池 `gather_evidence`** | 抬 `panorama.py` 成通用件：参数化语料 + `why` + 两层深度 + **token 预算装填** | `panorama.py` → 新模块 · `recall.py` | 真机 5 个真组抬得出来 · 噪音组进 `rejected` · 按预算装 | N2 | ~120 行 |
| **N7** | **L2-a 分群** | ⭐ **主要吃 N5 连出来的边**（不再自己找组）+ `merge` + `contradicts` | `contract/digest_registry.py` · `digest.py` · 新 prompt | `add`/`update` **不在契约里** · 只有 `conf≥0.8` 的边推动 collision | N1 N5 | ~100 行 |
| **N8** | **L2-b `collision`** | 覆盖判据（`covered`/`gap`）+ **单独一次调用** + 派生出 C + 落节点 + N 条边 + 两条 `about` | `digest.py` · 新 prompt | 成员<3 或全在同段 ⇒ **不产节点** · 已有 belief **逐字节不变** · ⭐ **模式判断（频率词）在 n≥2 前不许出现** | N7 | ~90 行 |
| **N9** | **冲突候选通道** | 同一对象/主题下挑**相似度最低**的 belief；连同边与被引数摆出来 | `digest.py`（`_round_b_material` 旁） | 造一个"世界变了"的夹具 ⇒ **`contradicts` 能被写出来**（今天 0 次） | N2 | ~40 行 |
| **N10** | **轮级通道** | 玩家回合语义近邻（**确定性**）⇒ L2 第二条语料；证据指针支持 **seq 区间** | `recall.py` 或新模块 | `PROCEED §1.3` 那 5 条真机原话：**字面零重叠但聚成一组** | N6 | ~80 行 |
| **N11** | **L3 实体摘要** | `about` 边 → `soul/entity_summary.json`（**异步 · 可重建 · 不进事务**） | 新模块 · `render.py` | ⭐ **删缓存重跑，结果一致** | N2 | ~70 行 |
| **N12** | **refs 走法** | `index` 派生（topic+次数+时间范围+refs）；引擎按 refs **注入时预取** + **超时兜底** | `notes.py` · `render.py` · `digest.py` | 预取有**超时降级** · 无命中 ⇒ 退化成"最近 N 条"（**不是空**） | N1 N6 | ~90 行 |
| **N13** | **取用重排（步 1）** | ⭐ **只加不砍**：静态人设 + **L3 基线** + episode **骨架** + note | `render.py` · `promptkit` | 注入台账可查**每层 token** · 总量 ≤ 5000 字 | N11 N12 | ~60 行 |
| **N14** | **取用重排（步 2）** | ⭐ **砍正文**（等 N12 的命中率数据） | `render.py` | 预取命中率 ≥ 阈值 ⇒ 4293 → **~1500 字** | N13 + **真机数据** | ~30 行 |
| **N15** | **验收** | `PROCEED §1` 两个样本跑真机 | —— | ① 送花串 → 那句台词的材料**能凑齐**（能点名 N 个实例）② 玩家重复同一意思 ⇒ **她能觉察**；反例不再出现 | 全部 | —— |

---

## 2. 每步的细化（按需展开）

### ⭐ N5 L-M：MMT 的「想起 + 发现」（**本主题的价值核心**）

> 依据：`DESIGN_DIGEST_LAYERS §0.1(f)` —— **link 移交 MMT**（一石五鸟：绕开 O(wiki) 的 LLM 成本 ·
> 不预建类别 · 当下即触发 · 保留细节 · 可校验），且**打破"先分组才能派生"的循环**。

```
① 引擎召回 1~2 条旧 episode（按当前对话）
   ⚠️ 接线 recall_subgraph —— 它今天**零产品调用者**（只有 experiments）
   · 真机 18 条 episode ⇒ 召回预算按 token（不是条数）
② 注入一段"你想起的事"（render 加一段；与 note / brain 并列，不混）
③ prompt 给她一个动作（⚠️ 正面给例子 —— 陷阱 40：反例会把要的行为禁掉）
   "如果你发现现在这件事和你想起的某件事【是同一件】，就说出来 —— 引用那件事的细节"
④ 她说了 ⇒ 引擎**锚点校验**：她引用的实例必须真实存在（编造的引用直接丢）
⑤ 落一条【待挂记录】（不是边）—— 因为此刻"当下这件事"还没成为 episode
   · 待挂记录 = {旧 episode id, 本轮的 event_seq, 她的说法}
   · ⭐ **L1 建完 episode 后，引擎补边**（两端都是 episode，语义一致、幂等好做）
判据
  · 召回有接线（非零调用者）
  · **编造的引用被丢**（锚点校验单测）
  · 待挂记录可查、补边幂等（同一条发现补两次只出一条边）
  · ⚠️ **不许把它做成"每轮都调 LLM"** —— 召回是引擎的，发现是她说话时的自然产物
```

⚠️ **待裁（见 `DESIGN_DIGEST_LAYERS §0.1(i)`）**：她引用的"当下"还没有 episode id ⇒ 用**待挂记录 + L1 后补边**（倾向），还是边的一端直接用 seq 区间。

### N1a 加 `akin` + 对称 rel 规范化（✅ **2026-09-29 已落地**）

```
graph.py
  · ⭐ REL_AKIN = "akin"（episode ↔ episode, **对称**）= noticed 记录行的落点
    ⚠️ 定名理由: `kind` 在本项目已确切指"节点类型" ⇒ `same_kind` 会被读成"两条 kind 相同"（废话）
  · RELS: 7 → 8 条
  · ⭐ SYMMETRIC_RELS = frozenset({contradicts, akin}) —— **对称性的唯一清单**
  · ⭐ canonical_for(rel, src, dst) —— **对称性的唯一实现处**
    （原来对称性只活在自举的调用方: 按"来自 links 还是 contradictions"传 symmetric=,
     而 store.add_edge 完全不知道 ⇒ akin(B,A) 与 akin(A,B) 会各写一条）
  · ⚠️ **`episode ↔ episode` 不进 classify_pair**（有意, 别"修"）: 旧档的 links 只声称
    "挨着/相关", 而 akin 声称"同类" —— 那是**判断**。旧档继续落 unknown, 在 stats() 里如实可见。
store.py
  · add_edge: 对称 rel 先 canonical_for（⭐ **必须在幂等检查之前** —— 幂等键 (rel,src,dst) 是有向的）
  · remove_edge: 同一个规范化（⇒ 反着传也删得掉）
  · add_contradiction / remove_contradiction: 不再自己 canonical_pair（唯一一处）
  · ⚠️ **顺手修的雷**: clone_state 的 `Edge(e.rel, e.src, e.dst, e.ts)` **位置参数**
    → `Edge.from_dict(e.to_dict())`（与点侧同款）⇒ 加字段时"静默丢属性"在构造上不可能
判据（已过）
  · ⭐ add_edge("akin", B, A) 与 (A, B) **只留一条**；有向边**不被交换**（supports m0003→m0001 保持原样）
  · ⭐ clone_state → restore_state 后**逐字段不变**（含一条**结构性**断言: 源码里不许再出现 `Edge(`）
  · akin 不进推断表（classify_pair("episode","episode") == unknown）
  · 旧 edges.jsonl / 旧 links 自举照旧读得进
```

### N1b 群（`group` kind + `member_of`）—— 待做

```
nodes.py
  · KINDS + "group" · _REQUIRED["group"] = ("title",)（text 允许空, 同 entity）· _PREFIX + "g"
  · validate(): group 不走 belief/experience 的 epistemic 护栏
graph.py
  · REL_MEMBER_OF = "member_of"（episode → group）· RELS: 8 → 9 条 · **有向**（不进 SYMMETRIC_RELS）
  · _ABOUTABLE 加 "group"（群可归属 entity; 今天零写者 —— 先开接口, 别锁死）
渲染 / 契约 / bucket: ✅ **零改动**（群不进常驻注入，只是 index 的原料）
判据
  · group 节点 to_dict/from_dict 往返稳定；没 title 被拒
  · 成员 = edges_to(gid, "member_of")；⭐ **一个 episode 可同时在两个群里**（多归属）
  · audit() 不把 group 当 belief 报"无支撑"
```

### N2 视野补齐（这条最便宜、收益最直接）

```
render.py
  · render_cognition_list：belief 也印「被引 N 条」（今天只对 experience 印"次数"）
  · 接线 render_organize_view 的边渲染（`edges: supports→m0009 contradicts←m0001`）
    ⚠️ 它今天**零调用者**（只有测试）—— 边渲染已经写好了，接上就有"深"
digest.py
  · _round_b_material 的候选从「只给本地 id」改成「id + 正文 + 边 + 被引数 + why」
判据
  · 真机跑一次，L2 的输入里 **grep 得到 `edges:`** 与「被引」
```

### N3 L1 区间化（**下游零改动**是它的卖点）

```
contract/digest_registry.py
  · record_episode 的**示例**：`"event_seq":[12,14]` → `"span":[12,18]`   ⚠️ 示例才是形状的来源（陷阱 3/46）
  · _clean_episode_item：_clean_seq_list(event_seq) → _clean_span(span, seq_set)
  · parse_round_a：加"区间重叠/越界"校验（**告警不打回** —— 打回要重写整段，成本 > 收益）
digest.py（插在 _resolve_verbatim 旁边）
  · _expand_spans(entries, seq_set)      # span → 区间内全部内容 seq
  · _resolve_overlaps(entries)           # 先到先得 + 告警
  · _backfill_unclaimed(seq_set, entries) # 未认领 → 归闲聊，**不落节点**
判据
  · ∪episodes.event_seq ∪ unclaimed == seq_set   ← ⭐ **覆盖率 100%**
  · 旧档（只有 event_seq 无 span）读得进
  · 真机重跑：密度 1.0 / 交错 0 / 覆盖 100%
下游零改动的理由
  · 节点的 event_seq 字段**不变**，只是来源从"LLM 挑的点"变成"引擎算的区间"
  · _create_a_nodes / _node_ts / _collapse_bond_episodes / R3 / 注入 / 召回 **全部不动**
```

### N4 L1 记账合并

```
digest.py
  · R4 的收口（promise add/close）并进 R1 的那一次调用
  · on_mind 也由 L1 产出
notes.py
  · SLOT_HABITS 从读写路径上删掉（保留一条退役注释）
  · render_note_block 不再印"惯例"小节
契约 / prompt
  · L1 的输出加 promise / on_mind；删 habits
判据
  · 单测：L1 产出 promise ops + on_mind
  · grep habits 只剩注释
```

### N5 候选池 `gather_evidence`（⚠️ 最大一块，可能要拆成 N5a/N5b）

```
新模块（或抬升 panorama.py）
  · @dataclass Evidence: node / why / edges / n_evidence / when / quote
  · gather_evidence(store, *, corpora=("episode","turn"), matcher="semantic",
                    budget_tokens=2000, deep_k=5) -> list[Evidence]
      - corpora：三选（episode / turn / entity:<名字>）
      - matcher：semantic（无服务 ⇒ 降级 anchor 字面）
      - ⭐ **按 token 预算装填**，不按条数截断
      - 前 deep_k 条"深"，其余"浅"（id + 标题 + why）
  · render_evidence(evs, local_of, *, deep_k=5) -> str
判据
  · 真机 5 个真组（苔藓/夏莱/笔记/道歉/团子）抬得出来
  · 噪音组（同 tag 不同事）进 rejected
  · 预算装填：给 2000 token，装满即停
明确不做
  · ❌ 分数融合（含 RRF）· ❌ graph spreading 当通道（降级成语料参数）· ❌ temporal 当通道
```

### N6 L2-a 分群

```
契约：新 PHASE_GROUP
  · 输出 {"groups":[{aspect, members, merge_with, covered, gap, conf}], "links":[...], "rejected":[...]}
  · ⚠️ **没有 decisions**（`add`/`update` 两个词从契约里消失）
引擎
  · join 快路：同 about_hint + tags 交集 ≥1 + 群 ≥3 成员 ⇒ 直接落边 conf=0.5
  · merge：成员重叠 ≥ 阈值 ⇒ **引擎直接并**（Jaccard，纯计算）
  · 落 same_kind（链式 N−1 条）+ contradicts 边
  · 低 conf 的边写进边表，但 **ignite 的闸只数 conf≥0.8**
判据
  · 契约里 grep 不到 `add` / `update`
  · 引擎 join 的边 conf=0.5；换一个高 conf 的夹具 ⇒ 才推动 ignite
```

### N7 L2-b `ignite`

```
prompt + 契约
  · 一次调用只做一件事：给一个群（**整群原文**）+ 已有 belief ⇒ 判"覆盖得了吗 + 缺什么" ⇒ 写一条新 belief
  · 四条硬规矩：第一句是命题 · growth 起点在 text 里 · about_hint 两条边 · 缺省不许编
引擎
  · 闸：成员≥3（只数高 conf）· 跨≥2 段 · 该群无 belief 或证据落后 · **covered=false**
  · 落节点 + N 条 supports（一次挂全）+ about 边（≥1 且含 x0000/x0001）
  · 旧 belief **一个字不动**
判据
  · 成员<3 或全在同段 ⇒ 不产节点
  · 已有 belief 正文**逐字节不变**
  · 每条新 belief 的 about 边 ≥1 且含 x0000/x0001
```

### N8 冲突候选通道

```
digest.py（_round_b_material 旁边）
  · 取本段新 episode 的 about_hint / tags / aspect
  · 在同一 entity 或同一 subject 下的 belief 里挑**相似度最低**的
  · 连同「正文 + 边 + 被引数」摆出来
判据
  · ⭐ 造一个"世界变了"的夹具（新经历与某 belief 主题同、结论反）
  · 看 `contradicts` 能不能被写出来（真机今天 **0 次**）
```

### N9 轮级通道

```
· 读 events.jsonl 的 mmt_chat.payload.player（真机 7 天 37 个玩家回合）
· 确定性语义近邻聚类（Qwen3 已在跑）⇒ 作为 L2 的第二条语料
· 证据指针支持 **seq 区间**（不只 episode id）
判据
  · 用 PROCEED §1.3 那 5 条真机原话做夹具：**字面零重叠但应聚成一组**
  · 那 5 条：没关系呢那份报告… / 不要自卑呀… / 这是因为遥香对我而言很重要哦 /
    嗯...不被知道名字… / 没关系那我就来陪遥香吧…
```

### N10 L3 实体摘要

```
新模块
  · refresh_entity_summary(store) → 读 about 入边 → 每个 entity 一段摘要 → 写 soul/entity_summary.json
  · 异步调用（同 notes.json 的刷新时机）· 失败静默降级 · **不进事务**
render.py
  · 注入加一段"关于他们"（静态人设之外的动态基线）
判据
  · ⭐ 删掉缓存重跑 ⇒ **结果一致**（真源永远是 about 边）
```

### N11 refs 走法（`index` + 预取）

```
notes.py
  · 新增第三槽 index：{topic, n, span, refs, from:"group:<aspect>"}
  · ⭐ **纯派生缓存**（从边表重建，不落真源）· 只收过闸的群
render.py / digest.py
  · 引擎按 refs 在**注入时预取**（writer 一次调用中途不能去查）
  · ⭐ **超时兜底**（抄 TencentDB：`recall.timeoutMs=5000` —— "超时就跳过注入、不阻塞对话"）
  · 无命中 ⇒ 退化成"最近 N 条正文"（**不是空**）
  · 可选 **link 连环**（默认 1 跳 + 预算；只走 same_kind / supports / about）
判据
  · 预取有超时降级路径（单测：embed 服务关掉 ⇒ 不阻塞、有兜底）
  · `index` 删缓存重跑一致
```

### N12 / N13 取用重排（**两段，别合并**）

```
N12（步 1，只加不砍）
  注入 = 静态人设 + L3 基线 + episode 骨架（标题+时间）+ note
  总量 4293 → ~4650 字（+8%，可接受）
  判据：注入台账可查**每层 token**；总量 ≤ 5000 字

N13（步 2，砍正文）—— ⚠️ **必须等 N11 的真机命中率数据**
  预取命中率 ≥ 阈值 ⇒ 砍正文 ⇒ 4293 → ~1500 字
  判据：两个样本的台词材料仍然凑得齐（**砍了不能丢材料**）
```

---

## 3. 三条纪律（施工时别违反）

1. **示例才是形状的来源**（陷阱 3/46）—— 每次改契约**必须同批改示例**，否则白改（art 命中率 0/5 的教训）
2. **每步一提交 + 全量绿**（`pytest tests/core tests/webgui tests/llm tests/renderer -q --basetemp=.testtmp/pw` + `compileall` + `node --check bond.js`）
3. ⚠️ **改 `CLAUDE.md` 前先改名**（`git mv CLAUDE.md CLAUDE_EDIT.md` → 改 → 改回）

## 4. 明确不做（别顺手实现）

| 项 | 为什么 |
|---|---|
| ❌ 分数融合（含 RRF） | 我们排名不可靠（Qwen3 窗口 0.014 宽）；判定者是 LLM，它要理由 |
| ❌ graph spreading 当"通道" | 降级成语料参数 `entity:<名字>` |
| ❌ temporal 当"通道" | 时间是**判据**，不是检索 |
| ❌ 无监督聚类 | 只在"提候选"半步有用；分组定案必须 LLM |
| ❌ 给规律建节点 | 规律住在边属性里（已裁） |
| ❌ `habits` 槽 · `add` / `update` 两个动作 | 见 `DESIGN_DIGEST_LAYERS §3.6` |
| ❌ `update` 改"她变了" | 那是 `evolved_from`，**永不改写**（§3.7） |
