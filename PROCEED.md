# PROCEED.md —— 接续指南（给压缩后的我）

> 建立 2026-09-23，**取代 `core/brain/wiki_v2/DIGEST_HANDBOOK.md`（已删，别去找）**。
> **读法**：先读这份（拿回上下文 ≤5 分钟）→ 需要细节时按 §6 的文档地图跳进去。
> **设计争论不在这里** —— 全部在 `core/brain/wiki_v2/DESIGN_GRAPH_V4.md`。

---

## 0. 一句话现状

Live2Be = Blue Archive 式叙事引擎（MMT 聊天 + Bond 视觉小说 + digest 记忆）。

**当前主线 = 记忆图 v4 落地**（`core/brain/wiki_v2/`）：边层 G1/G3/G4 已落地；digest 三轮改造走到
**D2a / D2b / D3a**（第 3 轮的输入侧 + 执行器 + entity 初始化接线都已备好，**编排未接**）。

⭐ **2026-09-23 发生了一次结构性重议**：结论是"**图不是唯一形式**" ——
**图 / note（随身笔记）/ 台账（inventory）** 三种组织形式；而 MMT 的 `function_call`
（她主动 `recall`）让"**边的走法**"第一次有了消费者。

**最新提交**：`44dd378`(docs) · `a9a612c`(D2b 执行器) · `785acda`(玩家 config) ·
`73ddb9b`(D3a) · `f2ac5f3`(D2a)。**工作树干净，全量 922 passed。**

---

## 1. 工作约定（用户明确要求过的，别违反）

1. **动手前先说做什么；动手后报告"做了什么 / 遇到什么问题 / 下一步"**；⚠️ **一旦遇到歧义，停下讨论**。
2. **一节点一提交**；提交信息用 `git commit -F <文件>`（**CJK 会炸 `-m`**）；只 stage 明确路径。
3. ⭐ **改 `CLAUDE.md` 前先把它改成别的名字**（用户 2026-09-23 要求）—— 否则每次编辑都会触发整个文件
   重新注入上下文。改完再改回来。
4. **每个节点必跑验证**（§5 四件套）。
5. **设计稿纪律**：`DESIGN_GRAPH_V4.md` = "已达成一致的形状"。**动之前先与用户讨论**，动完在文末
   **变更记录**留一行；**未定的点写在 §9 —— 不要顺手实现**。
6. 测试**别贪多**（用户："我们测试超级多了诶"）；**遇到失败的旧用例可直接删**（若它测的是"已不可能存在的世界"）。
7. 不跑 `ruff --fix`；不提交 `config/characters/*/illustration.yml`；`tools/` 是 gitignore 的本机工具目录。
8. 用户会**自己改人设/提示词** —— 改了之后 promptkit 夹具要刷新
   （`PROMPTKIT_UPDATE_FIXTURES=1 pytest tests/core/test_promptkit_baseline.py` + **人工审 diff**）。
9. **本文件**是压缩后的第一读物；它取代的那份 handbook 已删。

---

## 2. 现在在哪 / 下一步

**用户定的链路**（2026-09-23）：

```
① note  →  ② 消解无用 kind  →  ③ 正常 digest  →  ④ 时序  →  ⑤ 注入提示词时间重排  →  ⑥ 优化 MMT
```

**当前位置 = ①（note）的设计已闭合，代码一个字没动。**

### ① note 的开工清单（设计见 `DESIGN_GRAPH_V4` §3.2 / §6 / §8.6）

- **事件**：`type:"note"`（append-only，**不进 `window_messages` 历史** —— 同 `affection` 的处理），
  subtype = `add` / `done` / `rewrite`。
- **折叠**：事件序列 → `soul/notes.json`（带 `up_to_seq` 缓存水位；**不存在就现折**；可随时重建）。
  ⇒ 并发安全（主 LLM 与 digest 同时写不丢更新）+ 可回放。
- **三个槽**：`promise`（**操作式**：add/done，done = 移除、无状态机）·
  `habits`（**快照式**，全景轮整段替换）· `on_mind`（一段散文，她的口吻）。
  ⚠️ **物品一个字都不进 note**（痕迹 → `episode.items`；当前持有 → inventory）。
- **渲染**（拼在 system 尾、固定标题、**不进按时间排序的记忆流**）：
  ```
  【你自己记的备忘录】（编号是索引, 细节去查那些编号）
    n3 周六模型店 (m0009)  ← 记于 3 天前
  ```
  ⚠️ **编号必须渲染**（否则她只能靠文本匹配去 tick）；⚠️ **频次不进注入**（数值不喂 LLM 的既有纪律）。
- **校验**：每项 ≥1 个 `refs` 且指向现存节点（悬空 → 记账告警，**不阻断**）；上限 `5 / 5 / 1`，**超限只告警**。
- **写者分工**：加 = 当场（MMT 主 LLM 的可选字段；bond 侧由 digest 兜底）· 收口 = digest ·
  归纳（B 类整体重写）= **全景轮**（低频）。

### ⏳ §9-9 还开着的四个小口子（我给了默认值，用户没反对就照此实现）

| 口子 | 默认 |
|---|---|
| B 类槽超限丢哪条 | **全景轮决定**（引擎只告警，不截断） |
| 全景轮频率 | **每 N=10 段**（或章闭环时） |
| note 事件进不进 `window_messages` 排除表 | **进**（不进上下文历史） |
| MMT 的"顺手记一笔"可选字段 | **排在链路 ⑥**，现在不做 |

---

## 3. 未决账（**动手前必须问用户**）

**A. `DESIGN_GRAPH_V4` §9-12 的 ①-⑧ —— 全部待裁**（问过两次都没答，别当成已定）：

| # | 项 | 我的提案 |
|---|---|---|
| ① | `evidence`（成长证据） | **删**（零消费者 + 逼 R2 重喂时间线） |
| ② | `affection_delta` | **留 R2**，输入换成"episode 摘要 + 情绪标量"，不喂时间线 |
| ③ | R2 加 **`detach`**（裁错边） | 加（§8 写了但执行器没有） |
| ④ | R3 加 **`merge_entity`**（窄口，只合并 entity） | 加（否则重复 entity 永远无法合并） |
| ⑤ | R3 也看"**本轮被改写的旧节点**" | 加（否则它们永远没归属） |
| ⑥ | 补归属（复查队列） | **不做**，但把"永久没归"的后果写进文档 |
| ⑦ | `aspect`（设计稿里出现两次、代码零定义） | 从设计稿**删** |
| ⑧ | **顺序 D4 → D3** | 认（否则 R2 产的节点没有 `about_hint`，归属漏一批且**永久补不回**） |

**B. §9 其余未定项（共 13 项，动手前读原文，别凭记忆答）**：
常驻层的界（1）· fact 的提升（2）· `state` 清理（4）· place 归位（5）· `about_state`（6）·
玩家改名回填（7）· 用户档案/用户提示词（8）· note 落地（9）· `recall` 返回形态（11）·
R2 视野（13，`cap=12` → 按相关度）· **`self` 无条件进命中集（14）**。

---

## 4. 陷阱清单（踩过的 + 设计写死的）

1. **`about_hint` 必须显式摘掉**再进 `make_node` —— 否则被 `from_dict` 静默忽略，测试全绿、线索全丢。
2. **Round B 有"覆盖全部 episode"的结构检查** ⇒ 测试里给 `decisions: []` 会触反馈重试、把桩耗尽 → 红。给一条 `touch`。
3. **契约层改字段要三处同改**：取值清单 + 硬规则 + **示例**。⚠️ **示例才是形状的来源**（真机 `art` 命中率 0/5 的教训）。
4. **给 LLM 的示例全仓只能有一种形状**，讲评/注释放形状**外面**；改完用 `json.loads` 验一遍。
5. **JSON 换行只放成员之间**（字符串里折行 = 示范本身非法）。
6. **`_collapse_bond_episodes` 是逐章收口**（不是整段）：窗口常同时含 MMT 聊天与**多章**。
7. **`experience` 有两种语义**（R1 的玩家画像 / R2 的重复模式）—— 本日已裁 **不做 kind**（§9-10），改法是链路 ②。
8. **`count` 已删**：次数 = `supports` **入边数**（真机 m0003 入边 6 / e0001 入边 3）。
9. **水位是单一整数 `digested_seq`**；第 3 轮失败会**整体回滚**（含前两轮产出）。
10. **边的 `ts` = 本段日期**（`new_events[-1].ts`），不是"写库时刻"。
11. **`_find_duplicate`** = (同 kind, `event_seq` 有交集, 主文本相同) → 复用 id（崩溃窗口重跑的幂等靠它）。
12. **改 digest prompt 必跑**：`tests/core/test_wiki_digest.py` + `test_digest_registry.py`；
    **digest 的 prompt 不在 promptkit 盒里 ⇒ 没有夹具**。
13. **`llm_call.llm_chat` 有 feedback 语义**：被拒 → 追加 assistant 位 + 引擎错误，同上下文重试 1 次。
14. **`hit_set` 扫正文的称呼要求 ≥2 字**（单字"他/她/它"会命中每一段正文）；hint 走精确相等不受此限。
15. **候选表与载荷区必须共用同一份 `local_of`**（两套本地 id 会让模型把一个人当成两个人）。
16. **`config/player/profile.yml` 坏了 → 本轮 digest 直接中止**（**不兜底**，用户裁决）；
    `sensei` 的名字来自它 + `data/basic/player.json`（只当别名）—— **不是硬编码**。
17. **玩家名两个来源别合并**（config = 作者层进 git；`player.json` = 玩家自取，gitignored）。
18. **第 3 轮执行器三道闸**：`entity` 必须是候选表里的本地 id · 可归属 kind 限 episode/belief/experience ·
    **保留号防撞**（self/sensei 不在 ⇒ **跳过全部 `new_entity`** + WARNING）。
19. ⭐ **空表时 `next_id("x")` 返回 `x0001`** = **sensei 的保留号**，谁先建谁占坑 ⇒
    `ensure_entities` 必须在任何"自动建 entity"**之前**（D3a 已接在 digest 入口最前面）。
20. ⭐ **`self` 几乎永远不会进命中集**（她的名字不出现在第一人称正文里）⇒
    `entity(self)` 的载荷/state/inventory **今天没人维护**（待裁 §9-14：`self` 无条件进）。
21. ⭐ **别拿"真机数据频率"论证价值** —— 用户原话：*"真机数据我都是完全顺着 AI，几乎不给它增加外部负担的"*。
    没压过的地方就是 0（例：`items` 只有 1 条，但那不代表机制没用）。
22. ⭐ **`emo_shape` 是逐记录的情绪数组**（真机最长 129 个键），**空键跳过、不补位** ⇒
    位置对齐丢失；`nodes.py` 的注释写"板级"是**错的**（实现是记录级）。
23. ⭐ **不要把图当列表用**：`about`/`supports` 有数据但**零消费者** ⇒ 没有 traverse 者时图 ≈ 带 id 的列表。

---

## 5. 验证配方 + 真机基准

```powershell
# 单测（快，改 wiki 层时先跑这个）
python -m pytest tests/core/test_wiki_entities.py tests/core/test_wiki_revise.py tests/core/test_wiki_graph.py tests/core/test_wiki_digest.py tests/core/test_digest_registry.py -q --basetemp=.testtmp/pw_graph

# 全量（每节点必跑；⚠️ .testtmp/pw 目录要先建）
python -m pytest tests/core tests/webgui tests/llm tests/renderer -q --basetemp=.testtmp/pw
python -m compileall -q core contract webgui apps llm tests main.py
node --check webgui/static/js/bond.js
python experiments/web_e2e/run.py          # B 层冒烟（Playwright，本机已装浏览器）
```

**真机基准**（`world1/igusa_haruka`，2026-09-23 量）：
**14 节点**（11 episode / 2 belief / 1 experience）+ **11 条边**（全是 `supports`）·
`digested_seq ≈ 206` · **0 条 entity**（D3a 之后下一次 digest 才会长出来）· 三张纪念图。
另一条线：`asagi_mutsuki` 5 节点（**没有 `edges.jsonl`**，探针要容错）；`onikata_kayoko` 0。

**只读探针**：`.testtmp/probe_nodes.py`（我写的，改路径即可复用）。

---

## 6. 文档地图（+ 外部材料）

| 文档 | 管什么 |
|---|---|
| **本文件 `PROCEED.md`** | 压缩后的第一读物：现状 / 约定 / 未决 / 陷阱 / 配方 |
| `core/brain/wiki_v2/DESIGN_GRAPH_V4.md`（80 KB） | **设计稿**：§1.1 三种组织形式 · §2 边与**走法** · §3 entity/**note**/inventory · §4 注入两档 · §5 fact · §6 **promise 两段式** · §7 时间 · §8 digest 三轮 · **§8.6 全景轮 + `habits` v3** · **§9 未定 13 项** · §10 已否决 · **§11 `function_call` 与动作面** · §12 外部参照（**§12.1 BaiShou 设计哲学**） |
| `CLAUDE.md`（仓根，⚠️ **改前先改名**） | 项目主文档；§12 是测试/路径/提交纪律 |
| `docs/PROMPT_INJECTION_MAP.md` | 现网注入事实（改盒/加注记前看） |
| `docs/AI_BRIEF_PLACE.md` | 改地点代码前先扫它 |
| `docs/DESIGN_MEMORIAL.md` | 纪念链路（A–D 已落地） |
| `.testtmp/research/` | 09-23 的外部调研材料（AgentGal / BaiShou 源码，含它们的 AGENTS.md）—— **gitignore，可能被清** |
