# REDUNDANCY.md — digest 字段与料的**冗余底稿**（2026-09-29）

> ⭐ **这份文件是工作底稿，不是设计稿**：把"审字段"时查出来的每一处冗余钉在这儿，**防止忘**。
> 每改完一条，就在「状态」列打 ✅。改任何字段之前，先按文末那 **5 条通用判据**过一遍。
>
> 审计判据（下面每条都注明"证据"）：**谁在读它** —— 代码行号 或 真机档数字（`data/worlds/world1`，
> 读于 2026-09-29：haruka 18 episode / mutsuki 2 episode，`data/diag/live2be.log`）。

---

## 一、字段级（R1 的 episode 行 + R2 的输出）

| # | 字段 | 发现 | 证据 | 状态 |
|---|---|---|---|---|
| 1 | `items` | **零活读者** | 全仓只有 `panorama.py:182` 读它当锚点，而那个模块**零调用者**；`notes.py:38` 注释许诺的 `inventory` 在代码里**根本不存在** | ✅ 已定**砍**（将来起 `inventory` 旁路） |
| 2 | `about_hint` | **同一件事判两次**（R1 猜"关于谁" → R3 再判"挂谁"）；判据（"三个月后再提到它需要一致吗"）与读者脱节 | 读者只有 `entities.hit_set(hints=…)`；真机 4 段**每条都填**（`digest_hint eps=5 hint=5` 等）；而 `hit_set` 本来就有 `texts=` 通道 | ✅ 已定**删字段**；改成 R3 从 `tags` + 正文 + 标题 + 原话认称呼；⭐ **别名机制保留**（`revise.py:346` 顺手把称呼记进 `aliases` ⇒ R3 输出里留一个可选称呼） |
| 3 | `epistemic` | ① 与 `observer` **互为函数**（`observer != ""` ⟺ `reported_fact`）② **跨 kind 两个意思** | 契约"reported_fact 时必填 observer"；`nodes.py:92`；`nodes.py:183`（belief 必须 `inferred_belief`）；`revise.py:181`（engine 归属） | ✅ 已定**整个退役**，只留 `observer`（空=亲历）；读侧 `render.py:206` / `recall.py:394` 改判据；真机 reported 1/20 且带 observer ⇒ 迁移无损 |
| 4 | `add.example`（R2） | 落成 belief 的 `examples`，而**belief 的 examples 零读者** | `recall.py:322` 只在 `kind=="experience"` 时用 examples（belief 用 `growth`，`recall.py:324`）；她视图 `_belief_line:476` 只渲染 text+growth；⭐ **真机佐证**：`haruka e0001`（从 experience 迁移成 belief 的那条）**真的带着 `examples`**，而它是 belief ⇒ 那条 examples 是死的 | ⭐ 建议**砍**（待拍） |
| 5 | `evidence`（R2） | **零产品消费者** | 产出曾在 `digest.py:477`；全仓只有一条测试与一个归档脚本（`archive/factory_memory/smoke_digest_v2.py:147`）读；`digest.py` 自注"罗盘应用后置, **无罗盘则丢弃**" | ✅ **已删（2026-09-29）**：`EVIDENCE_THRESHOLD` · `DigestResult.evidence` · `digest_segment(evidence_threshold=…)`（**零调用方传它**）· `_clean_evidence()` · 契约 schema 块 · prompt 判据 9；守门 = `test_digest_registry.py` 的 `"evidence" not in text`。⚠️ 测试桩里的 `"evidence": []` 回音**未清**（`parse` 不读它, 无害） |
| 6 | `verbatim` vs `verbatim_seq` | **两条通道说同一件事** | 契约"两条都给时**以②为准**"；真机 haruka **两条都填**（文本 + 序号） | ✅ 已定**二选一**：只留**序号**，文本由引擎填（`_resolve_verbatim` 已在） |
| 7 | `kind`（R1） | **轮次决定的常量**，不该由 LLM 声明 | R1 恒 `episode`；R2 恒 `belief`；promise 由 `apply_closures` 建（引擎） | ✅ 已定**删** ⚠️ 后果：`experience` 产线停（真机 mutsuki 有 1 条；player 桶靠它）⇒ "关于老师的事"归 entity 面（以后那一刀） |
| 8 | `title` / `span`（**bond 段**） | 章标题**在发起 VN 那一刻就定了**；整章的 span 引擎也知道 | 真机 haruka **6/6 与 `chapter_title` 逐字相同**；mutsuki 漂了 1 处（episode「咖啡厅的俄罗斯轮盘」vs 章「咖啡厅的甜点陷阱」） | ⭐ 建议：**bond 段这两个由引擎填**，mmt 段才由 LLM 给（待拍） |
| 9 | `observer` | 值**引擎推得出**（记录里谁在说话，引擎有 `records`） | `_node_texts` / 记录流的说话人 | 留（已定）；📌 待办：等真机 `reported` 数据再定要不要交引擎 |

---

## 二、料级（同一份料送多次）

| # | 料 | 送几遍 | 证据 / 备注 | 状态 |
|---|---|---|---|---|
| 10 | 人设 `character_prompt` | **3 遍**（R1 · R2 · R3） | `digest.py` 三处 `_join_sections` 都有「角色人设（锚点）」 | 合并轮次才省得掉 |
| 11 | **时间线** | **2 遍**（R1 · R2） | R2 那份**只为** `evidence` 的逐字引用 ⇒ ✅ **evidence 已于 2026-09-29 删**, 所以它现在**没有存在的理由**了；但"R2 要不要看原始时间线"是**改行为**（可能影响 decisions 质量, 该单独验甚至真机 A/B）⇒ 本次**只把标签改成"本段时间线"**，去留**待裁** | ⏳ 待裁（下一批候选） |
| 12 | 本段新增经历 | **2 遍**（R4 `_episode_lines` · R2 `_round_b_material`） | 同一批 episode，两种渲染 | 合并轮次才省得掉 |

---

## 三、机制级（两份实现 / 两个入口 / 零写者）

| # | 东西 | 发现 | 状态 |
|---|---|---|---|
| 13 | `supports` 边 | **两个入口**：`decisions.touch` 与 `links`（同一种边两种写法） | 待拍：要不要收成一个入口 |
| 14 | episode → 给 LLM 看的行 | **两份实现**：`digest._episode_lines`（R4）· `digest._round_b_material`（R2）—— 头已在 N5d 统一，**截断与行形状仍是两份** | 待收 |
| 15 | `hints` 中间产物 | 只为把 R1 的猜转给 R3（与 #2 同源）⇒ 随 #2 一起消失 | ✅ 随 #2 |
| 16 | `notes.retire_op` | 有定义 · 有读侧（`fold` 认它）· 有测试，**零产品写者**（R4 只发 `close`） | **留**（等读路径召回接通）；记一笔 |

---

## 四、归口不清（同一类内容有好几个家）

| # | 内容 | 三个家 | 状态 |
|---|---|---|---|
| 17 | "关于某人 / 某事" | `experience` 节点 · `belief.subject` · entity 载荷（`text` 立场 + `state` 现状） | ⭐ 无规则；且 entity 的 `state` **只能整段重写、没有删除机制**（`revise.py:258` 原话："今天没有'删掉一条 state'的机制（'谁判它过期' = §9-4 未定）⇒ 想删得整段重写"） |
| 18 | `belief.examples` | 与 #4 同源（写了没人读） | 随 #4 |

---

## 五、跨轮职责重叠

| # | 重叠 | 说明 |
|---|---|---|
| 19 | R1 的 `about_hint` ↔ R3 的归属 | = #2 |
| 20 | `verbatim`（R1 摘原话）↔ `evidence.quote`（R2 摘原话） | **同一件事做两遍**：一个进她的视图（有读者），一个进没人读的 `evidence` |
| 21 | `decisions.add`（R2，单条也能新建看法）↔ 将来的"群 → 看法"（证据 ≥2） | 两条"长出看法"的路；**分工要写清**：R2 允许单条（新经历带来的新看法 = 记忆的生长点）· 群那条 ≥2（归纳） |

---

## 六、**已确认不是冗余**（别误删）

| 字段 / 机制 | 活的读者 |
|---|---|
| `text` | 她的视图 · 召回 · 候选 · 证据 |
| `title`（mmt 段） | 注入（N5a）· `noticed` 指认 · 块/群的料 · 地址解析 |
| `span`（mmt 段） | 引擎据此物化 `ts` / `emo_shape` / `place` / `place_raw` / `aff_at_encoding` + 章收口 + 证据指针 |
| `tags` | `recall.recommend_candidates` 的锚点 · `_embed_text`（`narration + verbatim + tags`）；契约本含人名，**真机 tags 里已有** `老师` / `阿露` / `老师的话` ⚠️ 上限 4、真机基本用满 ⇒ **不设"必须带主体名"的义务** |
| `significance` | 「难忘」标记 · belief 排序 · 时间短语措辞 · 召回打分 `SIG·TIME` · 章收口挑最高 |
| `growth` | 她视图 `_belief_line:476`（`（——从「我不配」到…）`）· `recall.py:265`（候选召回的 2-gram 正文比对）· `recall.py:324`（`_embed_text`：belief 的检索文本 = text + growth）⇒ **三个活读者**；真机 7 条认知里 **5 条有值** |
| `verbatim`（文本字段本身） | 她视图 `render.py:455`（只是**改由引擎填**，见 #6） |
| `emo_int` / `emo_span` | 召回打分 `det = SIG·TIME + emo_span·emo_int`（`channel_impl.py:61`）⇒ **有读者**；但**搬不走**（见下） |
| 情绪两处加工 | 标注层给**逐记录**键 → `emo_shape`；R1 给**跨记录聚合**的峰值/摆幅 —— **有分工**，不是冗余 |

📌 **待办（记下不做）**：`emo_int`/`emo_span` 想交引擎，前提是**词表补一列 0~1 强度**
（今天 `emotion_lexicon` 每个键只有作者散文注释 `comment`/`eg`，`core/media/emotion_lexicon.py:155-163`，**没有数值** ⇒ 引擎算不出 max / max−min）。那是内容侧的活（14 个键各写一个数），做完这两个字段就能从 R1 消失，而召回打分从"LLM 估的"变成确定的。

### ⚠️ `growth` 附带查出的另一条：设计规矩④**从来没成立过**

设计稿 `DESIGN_DIGEST_LAYERS §3.2` 规矩④：*"`growth` 的起点必须出现在 `text` 里"*（怕两个字段各写各的、互相矛盾）。真机实测：

| growth 里的起点 | 在 `text` 里逐字出现吗 |
|---|---|
| `我不配`（haruka m0003） | ❌ |
| `只敢在外面看`（m0008） | ❌ |
| `有人会来看我`（m0018） | ❌ |

**3/3 不成立** ⇒ 那条规矩从未落地、也没有校验，而且**引擎没法校验**（真机连引号用法都不统一：`「」` 与 `『』` 混用）。
⇒ **建议**：换成一条给 LLM 的**轻纪律**写进契约 —— *"`growth` 只写**变化的方向**（从…到…），**不要在 growth 里引入 text 没提过的新事实**"*。理由：`growth` 的价值是"**她怎么变的**"这个视角（与 text 的"她现在怎么看"不同），逐字对齐是形式主义；真机那 3 条读起来也都是"同一件事的两个时间点"，不是新事实。

---

## 七、5 条通用判据（这次审出来的，长期用）

1. **每个字段必须点名它的读者**（谁读、读来干什么）—— **没读者 ⇒ 删**（`items` · `add.example`）
2. **判据写在"读者拿它做什么"上**，不写在感觉上（`about_hint` 那句"三个月后需不需要一致"）
3. **同一件事不许判两次**（`about_hint` ↔ R3 的归属）
4. **字段之间不许互为函数** —— 一个的值能推出另一个 ⇒ 删一个（`observer` ⟺ `epistemic`）
5. **一个字段不许在两种 kind 上是两个意思**（`epistemic`：episode 说"来源"、belief 说"别伪装"）

> 本次 R1 那 13 个字段里，**4 个**是这么查出来的（`items` · `example` · `about_hint` · `epistemic`）—— 不是巧合。

---

## 八、未决（等用户拍）

| 项 | 我的倾向 |
|---|---|
| **落地顺序** | **先小刀**（字段退役 + `evidence` 删 + 关系收敛到 `links`，**不动轮数**）→ 再大刀（合并轮次成 ① 记 / ② 接 / ③ 重看） |
| #4 `add.example` 删不删 | 删（belief 的 examples 零读者） |
| #8 bond 段的 `title`/`span` 交引擎 | 交（真机数据支持：让 LLM 抄章标题会漂） |
| #13 `supports` 收成一个入口 | 倾向收（今天两种写法） |
| #21 两条"长出看法"的路 | R2 允许单条 · 群那条要求证据 ≥2（分工写进契约） |
