# TRAPS.md — 陷阱清单（踩过的 + 设计写死的）

> 从 `PROCEED.md` §8 搬出（2026-09-27，用户要求 PROCEED 只做"接续用"、不堆内容）。
> ⭐ **编号是全局的、不许改** —— 代码注释 / CLAUDE.md / 设计稿里都按号引用（可能写作"PROCEED 陷阱 N"，
> 那指的是本文件；搬家没改号，所以旧引用**零改动**有效）。
> **新陷阱一律追加在末尾**，不许插入、不许重排。

---

1. **新事件类型不登记进 `EVENT_TYPES` = 静默丢失**（`Event.from_dict` 对白名单外的 type 返回 `None`）。
2. **"非剧情事件"的判据只有一处** = `core/session/events.py::is_content_event`（静态守门在
   `test_note_events.py::test_content_filter_is_not_reimplemented_elsewhere`）。
3. **契约层改字段要三处同改**：取值清单 + 硬规则 + **示例**。⚠️ **示例才是形状的来源**。
4. **给 LLM 的示例全仓只能有一种形状**；JSON 换行只放成员之间（字符串里折行 = 示范本身非法）。
5. **note 的提交顺序 = 先真源（`note/*` 事件 append）后缓存（`notes.json`）**；反过来会出现
   "本子上有、事件流没有"（没人能重建它）。唯一实现 = `mmt.engine._write_note_ops`。
6. ⭐ **R4 的 note 操作不在 `digest_segment` 里 append** —— 它拿不到 `SessionStore`；挂在
   `DigestResult.notes_ops` 上，**调用方在整批 `ok` 之后**才写（`_rollback` 会清空它）。
7. ⭐ **全景轮的计数器不清零**（没跑成 / 没料 ⇒ 下一段再试）；**第一次直接到点**；**写卡后要重读事件流**。
8. **`experience` = 玩家画像专用**（写者只有 R1；R2 的 `add kind=experience` **被拒**）；
   读侧**按 kind 收、不看 `subject`**。
9. ⭐ **两个 id 空间不许混**：R2 的 `target_ids`（可 touch/update，**只有看法**）vs `link_ids`（含承诺）；
   R3 的 `c0001`（对象）vs `u0001`（节点）。混用会让"挂谁"与"挂在谁身上"写反，而那种错**看起来完全正常**。
10. **每段四步的批内顺序 `R1 → R4 → R2 → R3` 是正确性**。
11. **第 1 轮节点的 `ts` = 它自己 `event_seq` 里最后一条事件的时刻**；第 2/4 轮仍是段 ts。
12. **注入视图是"一条河"，从早到晚**（旧→新）；belief / 玩家画像 / reported **不进河**。
13. **`about_hint` 必须显式摘掉**再进 `make_node`（否则被 `from_dict` 静默忽略）。
14. **Round B 有"覆盖全部 episode"的结构检查** ⇒ 桩里 `decisions: []` 而 episode 非空 ⇒ 反馈重试。
15. **桩必须按 `task` 分派**（`llm/task_labels.py`）；**新任务要补四处**。
16. **`llm_call.llm_chat` 有 feedback 语义**：被拒 → 追加 assistant 位 + 引擎错误，同上下文重试 1 次。
17. **水位是单一整数 `digested_seq`**；任一轮失败 ⇒ **整体回滚**。
18. **`_find_duplicate`** = (同 kind, `event_seq` 有交集, 主文本相同) → 复用 id。
19. **改 digest prompt 必跑** `test_wiki_digest.py` + `test_digest_registry.py`；**digest 的 prompt 不在 promptkit 盒里 ⇒ 没有夹具**。
20. **`hit_set` 扫正文的称呼要求 ≥2 字**；候选表与载荷区**必须共用同一份 `local_of`**。
21. **`config/player/profile.yml` 坏了 → 本轮 digest 直接中止**（**不兜底**，用户裁决）。
22. ⭐ **空表时 `next_id("x")` 返回 `x0001`** = sensei 的保留号 ⇒ `ensure_entities` 必须在任何"自动建 entity"**之前**跑。
23. ⭐ **真机 entity 已存在**（haruka 4 个：`x0000`–`x0003`；`about` 边 19 条）。
24. ⭐ **别拿"真机数据频率"论证价值**（用户原话：*"真机数据我都是完全顺着 AI"*）—— 没压过的地方就是 0。
25. ⭐ **不要把图当列表用**：`about`/`supports` 有数据但消费者极少 ⇒ 没有 traverse 者时图 ≈ 带 id 的列表。
26. **`emo_shape` 是逐记录的情绪数组**（真机最长 129 键），空键跳过、不补位。
27. ⚠️ **编辑坑**：用 `.Replace()` 时若把行尾换行也吃掉，`def` 会与 docstring 挤成一行；**优先用 edit 工具**。
28. ⚠️ **测试里的 id 顺序别赌**：预置节点会占号 ⇒ 断言按**文本**查 id。
29. ⚠️ **搬家时"诊断文案"也是行为**：`ParseDiag.error` 的中文串被用例逐字钉住。
30. ⚠️ **`tests/fixtures/api_surface.txt` 第四列 = "真家"**：搬件后必须 `SPLIT_API_UPDATE=1` 刷新 + **人工审 diff**。
31. ⭐ **通用层不许认识域**：`contract/streams/` 只 import stdlib 与自身（守门已变异验证）。
32. ⚠️ **桩的 `chat_full` 必须喂"它返回的那段文本"**：`on_chunk(json.dumps(resp))` = **双重编码** ⇒ 一路跑到 `MAX_STEPS`。
33. ⭐ **流式下"校验面"与"执行面"不是一个东西**：`_run_lines(check_rows=…)`；`inspect` 静默轮要排除在 fatal 之外。
34. ⭐ **已交付 ⇒ 只记账，不抛 `MmtLoopError`**（玩家已经看见气泡）。
35. ⭐ **"点得早"会踩到预热构造中**（`bond_start` 的"并发 init skip"分支漏 `chapter_title` + `vn_enter`）。
36. ⭐ **冒烟断言要判"谎"，不要判"出现"**；断言超时时要**留证真身**。
37. ⭐ **时区混算 = 一类会"静默杀功能"的 bug，别再手写 `fromisoformat`**：统一 `age.parse_ts` + `datetime.now(REAL_TZ)`。
   ⚠️ 老用例全绿是因为 `_now_iso()` 造的是 **naive** ts ⇒ **测试数据形状与真机不一致，回归永远看不见**。
38. ⭐ **digest 的语义召回依赖本机 embedding 服务，服务不在就静默降级**：`[embed].base_url` 指 **1235**
   （LM Studio，`lms server start`）；服务 OFF 时 `digest_embed fn=none reason=model_missing`
   ⇒ 候选退化成字面命中（真机 haruka 候选覆盖 **39% → 100%**）。**用户裁决：保持服务开着。**
   ⭐⭐ **2026-09-27 换模型（nomic → Qwen3）**：
   · **`model` 必须钉死** = `text-embedding-qwen3-embedding-0.6b` —— 本机**同时装着两个 embedder**
     （nomic + qwen3），两个 id 都含 `"embed"`，而 `_EMBED_HINTS[0] == "embed"` ⇒ 自动发现取的是
     `/v1/models` 里**排前面的那个**（今天恰好是 qwen3，但**顺序由服务端定，不可靠**）。
   · ⚠️ **不要用注释里那个旧示例名 `Qwen3-Embedding-0.6B`** —— 服务上的真实 id 是
     `text-embedding-qwen3-embedding-0.6b`（`lms load` 输出的 identifier）。
   · **为什么换**（`docs/EXPERIMENT_CAND_HIGH.md` 的 C1/C4 + 2026-09-27 用**新真机数据复现**）：
     | 模型 | 真相关 top1 | 主题无关 top1 | 判决 |
     |---|---|---|---|
     | nomic | [0.848, 0.878] | [0.650, **0.865**] | ❌ **交叠**（无关最高 > 相关最低） |
     | qwen3 | [0.521, 0.706] | [0.339, **0.507**] | ✅ **干净分开** |
     独立旁证：nomic 下 **"天气" vs "量子色动力学" = 0.603**（`AUDIT §10`）。
   · ⭐ **副作用（对设计有用）**：belief × belief 的带宽从 nomic 的 **[0.818, 0.877]（0.06 宽）**
     变成 qwen3 的 **[0.418, 0.628]（0.21 宽）**，而且 **`e0001`（道歉的习惯）被正确分开**
     （0.418~0.462 vs 别人 0.596~0.628）—— 它是"独立轴"这件事，以前只能靠人眼看正文。
   · **不需要重建任何索引**：embedding **派生不落盘**（每次召回冷算）⇒ 换模型即刻生效。
   · **代价**：批量 40 条 143 ms → **1716 ms**（约 12×），digest 是后台路径 ⇒ 可接受。
   · **不需要重新标定阈值**（T17 已把 `cand_high` 整族删掉，只留排序）。
   · ⚠️ 本次实测窗口只有 **0.014 宽**（0.507~0.521）⇒ **单阈值脆弱**；但我们只用**排序**，不受影响。
39. ⭐ **"同一段里说定、又兑现"的约定，永远收不了口**：R4 的输入只有【还开着的约定】（**段前快照**）+
   【本段新增的经历】（截断 120 字），判据 2 又写"**这一段里**确实翻篇了的" ⇒ **永远不成立**；
   真机实证 `close` 全程 **0 次**。⇒ 判据要写"**只要它已经翻篇了**（兑现/失约/被盖过），不管翻篇发生在哪一段"。
40. ⭐ **提示词里的"反例"会变成一条禁令**：`panorama.md` 用 *✗「周六我们一起去了模型店」* 教它"别复述事件"
   ⇒ **把我们要的整类句子禁掉了**（那句台词恰恰是复述细节）。
41. ⭐ **规格与机制必须一起看**：`panorama.md` 说"她只会看到**这三两行**"，机制却**没有条数上限**
   （`MAX_HABITS=5` 只活在读侧告警）+ `drop` 措辞极保守 ⇒ **只增不减**。**文案与机制矛盾时，机制赢。**
42. ⭐⭐ **`node.ts` 是"记账时刻"，不是"事件时刻"**（2026-09-27 本轮查出）：真机 `m0014 ts=23:04:50`
   但 `m0015 ts=22:47:20` —— 同批写入、ts 相差 17 分钟、**与 `event_seq` 顺序相反**。
   而 `_bucket_view` 的排序与 `_time_phrase`（"（3 周前）"）**用的就是这个 ts**。
   ⇒ **要事件时刻必须走 `event_seq → events.jsonl.ts`**（真机 316 条 ts **单调，逆序对 0/315**，且带星期几）。
43. ⭐⭐ **`note.refs` 是一条"没有走法的边"**：它**印给 LLM 看了**（`render_note_block` 的
   `n7 他买东西时总先问我想要哪个 (m0005, m0010)`），但**引擎不会因为它去取物** ——
   细节仍然靠 `_bucket_view` 把 18 条 episode 全文（**4293 字**）全量灌。
   这正面撞上我们自己 §2.2 的判据：*"一条边值不值钱，看它有没有一条能走的路"*。
   ⇒ **要么给它走法（引擎按 refs 展开），要么承认它是装饰。**
44. ⭐⭐ **R1 的 `event_seq` 是"号码袋"，不是区间** ⇒ 三个后果（2026-09-27 本轮查出）：
   ① 密度可以低到 **0.17**、区间可以**互相跨骑**（`m0015` 跨 `m0016`）；
   ② **40% 的轮次无人认领**（157 → 94），其中包括玩家说的「不被知道名字、不引人注目也没关系吧」（seq 226）；
   ③ **引子必然掉缝里**。校验只有 `⊆ seq_set`，**没有连续性/重叠/覆盖率检查**。
45. ⭐ **`session_start` 只在世界线创建时写一次**（`store.py:205`）；**`session_end` 由 `bond_finish` 写**
   （`webgui/bond/api.py`）⇒ **纯聊天世界既无 session_start 也无 session_end**，
   `list_open`（"无 session_end = 未结束"）在纯聊天世界**恒成立**。
46. ⭐ **契约示例的字面形状会变成语义**：`add` 的示例只有**一个** `episode` 字段 ⇒
   真机 4 个认知**全部诞生自 1 条 episode**（`evolution.jsonl` 铁证）。
   ⇒ 改"N 条 → 1 条新 belief"**必须同批改示例**（陷阱 3 的又一实例）。
47. ⭐ **"真机一次也没发生"≠"不可能"**：`contradicts` / `evolved_from` 真机 **0 次**，但两个 kind 都在、
   将来会有走法；而 `source` 那条边**永远不会有走法**（起点 kind `fact` 已退役）⇒ 后者才是该删的。

---


---

## 48–49（2026-09-30, N1a/N1b/N3 开工途中）

48. ⭐⭐ **同一件事的"记账"散在多支分支里 ⇒ 少一支就是一条静默的丢数据路径。**
   `bond_start` 的四个分支（`adopt` / `concurrent` / `resumed` / 现场生成）里有三支要给
   **同一个状态**做记账（补落 `vn_enter`），而 `resumed` 那一支**漏了**
   ⇒ 整章没有 `vn_enter` ⇒ 剧情演得完、`vn_exit` 也照落，但 `replayable_chapters`
   认不出它 ⇒ **回忆册 0 章**（陷阱 35 记的就是这个症状，当年只补了 `concurrent` 那一支）。
   ⇒ 纪律: **同一份状态的写点超过一处时，先把它们收成一个函数**（这次收成了 `_close_stale_attempts`
   的同款做法），否则下次加分支还会漏。

49. ⭐⭐ **"收尾"这类维护动作必须带条件 —— 无条件调用会杀掉刚刚建立的东西。**
   `webgui/bond/entry.py` 在 `commit_staging` 之后**无条件**再调一次 `close_open_attempts`
   ⇒ 此刻真源里唯一的未闭合段**就是刚提交进去的本章** ⇒ 给**玩家正在玩的一章**补一条
   `vn_exit{completed:false, reason:"staging:superseded"}` ⇒ `_bond_done_map` 的
   **顺序配对**（trigger → 其后第一个 `vn_exit`）被提前关闭 ⇒
   **MMT"已完成羁绊剧情"淡行永不出现**（换一种交错就是回忆册 0 章）。
   ⚠️ `staging.py:258-261` 那张表**早就写了这个错误**（"不带 vn_enter ⇒ 真源里那个就是本章
   ⇒ 收尾它 = 把它误判成没读完，且真源里会冒出两个 vn_exit"）—— **保护写在了
   `commit_staging` 里，没覆盖到它外面的那次调用**。
   ⇒ 纪律: 维护型动作（收尾 / 清理 / 提升 / 补边）**必须问"我要动的那条，是不是我刚建的那条"**。

50. ⭐ **写时展开的字段，`pop` 要跟着走**（N3）: 契约从 `event_seq: ["28","30"]` 改成
   `span: [28, 30]` 之后，条目里那个 `span` **必须在引擎展开时 `pop` 掉** ——
   否则它会一路走到 `make_node("episode", **ent)` 并被 `from_dict` **静默忽略**
   （与当年 `about_hint` 同款坑：这个项目最恨的静默 no-op）。
   ⇒ 纪律: **"引擎字段"进出条目的每一处，都要有显式的摘掉动作 + 一条用例**。
