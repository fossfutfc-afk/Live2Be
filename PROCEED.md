# PROCEED.md — **接续用**

> ## ⏭️⏭️ **接续后第一件事（2026-09-29 中断点 · digest 拆包两刀 + L1/D1 已落）**
>
> **状态**：工作树干净 · HEAD = **D1 那一笔**（`git log -1`）· 本地领先 origin 待确认。
> **下一步 = 按 `docs/EXEC_DIGEST_SPLIT.md` §7 继续逐层**:
> · **L2 = E1**（R2 的认知列表按**相关度**召回 —— 今天按 `significance` 前 12, 是
>   `contradicts`/`evolved_from` 漏判的近因）+ **D2**（R2 还要不要吃"本段时间线"）
> · **L3 = B1 + A2 一起做**（归属的**进**与**出**）—— R3 池子补"被 `update` 改写且没 `about`
>   边的旧节点" + `detach`/`merge_entity`
> · L1 还留了一刀 **D2 补全**（章的覆盖缺口 ⇒ 把保留那条 episode 的 `event_seq` 并上整章）
>   —— 用户裁决"**只记账, 补全另开一刀**"
> ⚠️ 节奏照旧: **每层"讨论 → 实现 → 组织"**, 动代码前先报**关键信息的形式**给他审。
>
> **本阶段已落（11 个提交; 乙-1/乙-2 已 push, D1 未 push）**
> · 计划 B 两刀：`core/brain/wiki_v2`→`core/brain`（去 V2）· **`core/brain/read/`** 读路径分家
>   · **`core/digest/`** 管线抬出（`be7cb40` 及之前）
> · 节点 C：**`core/digest/rounds.py` 轮次表**（步序/身份/prompt/相位/parse/料/写什么/跳过/预算/快照
>   单源 + `Cursor` 越序即炸 + `_rollback` 由表推导）`b392f32`
> · 刀 1：**时间预算按轮**（120s/轮 + 600s 硬顶；失败文案带轮次）+ 回灌统一
>   `llm.client.feedback` `71f91aa`
> · **`core/creep/`**（世界线的账：无 seq ⇒ 结构性隐身）+ `append_raw_row`（共用写锁）`194b6ea`
> · 刀 2：**digest 失败 3 次 ⇒ 放弃**（先记 creep 账、再推水位）`3649277` · 账写入保证 `e02783c`
> · 拆包 S1/S2：`call.py`·`material.py`·`segment.py`·`episodes.py`·`akin.py`
>   （`pipeline.py` **1431 → 666 行**）`cc3ced7` `1706a0e`
> · ⭐ **乙-1：digest 按轮拆包** —— `core/digest/rounds/`（表 + `base.py` 的 `Ctx`/`RoundOut`
>   + 六个轮文件）+ **编排循环化**（`pipeline.py` **672 → 479 行**、`digest_segment` **376 → 170**）`baff075`
> · ⭐ **乙-2：命名对齐** —— 轮次 key = 契约相位 = 标签后缀 · `label`/`prompt`/`phase` **由 key 派生** ·
>   prompt 文件改名 · 常量 `DIGEST_*` · 日志第一段恒为轮名 + **命名守门**；**LLM 字节零变化** `9112faf`
> · ⭐ **L1/D1：缺口账** —— 契约层 `vr.warnings` **接上出口**（从前一个字没落）+
>   `ValidationResult.drops`（**分类靠声明不靠文案**）+ `kind=digest_gap` 一段一行 +
>   条目面（一章一条丢的 / 复用的）+ 审计探针（`.testtmp/probe_l1_coverage.py`）。
>   ⚠️ 一条纪律: **只有"不可重算"的进账** —— 未认领/章覆盖可重算, 进日志与探针。
>
> **拆完之后**：按**逐层**（L1 → L2 → L3）走"讨论 → 实现 → 组织"，
> 刀清单见 `EXEC_DIGEST_SPLIT.md` §7。
>
> ### ⚠️⚠️ 测试纪律（用户 2026-09-29 裁决，违反会被**当场断掉**）
> **禁止频繁跑全量。不到 5 轮会话 / 不是关键节点，不许跑全量。**
> **按文件夹 / 板块分着跑**：`pytest tests/core/test_wiki_notes.py`（秒级）· `pytest tests/webgui -q`（一块）·
> 中途只跑 `pytest --collect-only -q tests`（约 2s，查 import 断裂）。
> **全量四件套只在大节点收口时跑一次。** 没接线的改动更不该跑回归。
> ⭐ **删东西只许指定工作目录内的显式路径，不用通配符 `*`**（用户 2026-09-29）。
> ⭐ **动代码之前先报"关键信息的形式"给用户审**（LLM 会看到什么 · 信息头怎么渲染），
> 不说具体改法；**除用户明确说"继续"，不许自己往下做**（用户 2026-09-29 定的规矩）。

> ⭐ **这份文件的唯一用途**：compact / 换会话之后，**5 分钟拿回上下文**。
> **关键内容不在这里** —— 在 §5 文档地图那几份里。
> ⭐ **规则：不往这里堆内容。** 一次讨论结束后，**只更新三处**：**§0 下一步 · §2 已裁 · §3 待裁**。
> （2026-09-27 按用户要求瘦身：陷阱 → `docs/TRAPS.md` · 三份调研 → `docs/RESEARCH_MEMORY_SURVEY.md`）

---

## 0. 状态 + ⏭️ 下一步

| | |
|---|---|
| **主线** | **新 note 机制 + graph 升级**（digest 按视野三层重排） |
| **代码** | **N1a**（`akin` + 对称规范化）`6eb89e1` · **N1b**（`group` + `member_of`）`d08f2ae` · ⭐ **N3（位置字段 `span` 区间化）`327821c`** · ⭐ **修既有竞态**（章 `vn_enter` 漏落 / 假 `vn_exit`）⇒ 全量 **1110 passed** · B 冒烟 **PASS** |
| **N4** | ⭐ **N4a 已落地 2026-09-29**：`habits` 槽退役 · `on_mind` 归 **L1** · **全景轮退役** · refs 印名字。⬜ **N4b（R4 并入 R1）我建议缓** —— 收益只是省一次**离线低频**调用, 而风险是「让 R1 判结清」把注意力分散掉（本项目有前科: *让主 LLM 逐句内联情绪 → 注意力分散、重试爆炸*）。 |
| **N5 拆三** | ✅ **N5 已走完（2026-09-29）**：**N5a** `483e99b`（标题进注入 · `render_recall_block` · `recall_episodes` · **P19 槽位**）· **N5a-2** `28d8abf`（元信息定稿 `〔《事件名》｜相对｜绝对｜难忘〕` · `age.render_date` · `CONTEXT_MARKS`）· **N5b** `cf24562`（`{"noticed": …}` 第三类行 · ⭐ `address.py` · `noticed` 非内容事件 · 契约/rules 同批）· **N5c**（`digest._link_akin` 补 `akin` 边）· ⭐ **N5d**（**括号统一**）: 新 **`marks.py` = 括号与信息头的唯一实现**，五个写侧全部改调它，R4/R3 两处 `「」` 修掉，守门 `test_marks_guard.py` |
| **设计** | 已裁 **19 条**（§2）· 待裁 **7 条**（§3）· 动工文档 `docs/DESIGN_MMT_NEW_ACTION.md`（§5） |
| ⏭️ **下一步** | ⭐ **逐层推进（L1 → L2 → L3）**：L1=**D1** 未认领/被丢弃的台账出口（落 `rounds/record.py`）· L2=**E1** 认知列表按相关度 + **D2** 时间线去留 · L3=**B1+A2 一起**（归属的进与出）。全文见 **`docs/EXEC_DIGEST_SPLIT.md` §7**（拆包乙-1/乙-2 均已落地）。⚠️ 上面 N2/N6/N7 那三行是 **N5 时代的旧选项**，今天不对口 |
| **支线** | MMT 的 `when` 语法（`DESIGN_MMT_NEW_ACTION §7 a`）独立、可随时插空 · **本地领先 origin 7 个提交未 push** |

---

## 1. ⏭️ 接续点：为什么"注入形式"是下一个要讨论的

### 要讨论的问题

> **wiki（brain 注入）以什么形式进 prompt？**
> 而它**直接决定 MMT action 的设计** —— 因为 **"手边有什么"决定了"她还需要伸手要什么"**：
> **手边宽 ⇒ 不需要 action；手边窄 ⇒ action 变成必需品。**

### 今天的形态（真机实测，2026-09-27）

```
system 尾 = 【角色记忆（brain）】  … 4205 字符
              ├─ 我记得的事（从早到晚）：18 条 episode 【全文】（含「逐字原话」）
              └─ 我心里渐渐觉得：4 条 belief 全文（带 ——growth）
system 尾 += 【你自己记的备忘录】note（promise + on_mind）
history  = window_messages(max_units=120) → 真机 70 单元 … 5287 字符
────────────────────────────────────────────────────────
合计 ≈ 9500 字符（不含盒A 10 块 / 人设 / task 卡 / 玩家输入）
```

### 问题在哪

- **今天放得下**（18 条）—— 所以**五个玩家问题里四个她今天能答**（见下表）
- ⚠️ **wiki 变大就放不下**：100 天 ≈ 270 条 ⇒ **≈ 63000 字符**
- ⇒ **真正的问题是：变大之后，怎么保住"她能答那几个问题"？**
- **候选方向**：**骨架（title + 时间 + 难忘）常驻 + 按需正文**（refs 走法 / 引擎每轮摆 / `inspect`）
  · 今天 18 条全文 4205 字 vs 骨架 ~270 字（**≈ 1/15**）

### ⭐ 讨论时要带上的已知事实

| # | 事实 | 出处 |
|---|---|---|
| **1** | ⭐⭐ **`episode.title` 早就有了**（契约要求 8-16 字；真机 18 条**都唯一、都含具体名词**）—— ⚠️ **但从来没印出来** | `render._memory_line` **不印 title** |
| **2** | ⭐ 时间短语**故意虚化**（I-c 纪律："绝不出现小时/分钟/精确日期"）⇒ 真机全是 `（1 周前）`/`（7 天前）` ⇒ **"上周"筛不出**（**是纪律，不是 bug**） | `render._time_phrase` |
| **3** | ⭐⭐⭐ `_memory_line` 的设计理由里**已经写着**：*"LLM 需要先看到'这是多久以前的事'再读内容，才好判断'**这件事讲过了 / 该不该重提**'"* —— **判断的种子在提示词里，出口不存在** | 同上 |
| **4** | ⭐ **`inspect` 真机 0 次（157 轮）= 规模没到**，不是它没用（陷阱 **24** 的印证：*"没压过的地方就是 0"*） | 探针 |
| **5** | 五个玩家问题（上周干了什么 / 杂草屋发生过什么 / 你怎么看 X / 最珍贵 / 餐厅那次）⇒ ⭐ **四个她今天能答**（全文在手）；**只有"第三人"不能**（没预装、没注入） | 探针 dump |
| **6** | 两条链路**零调用者**：`render_organize_view`（边渲染）· `recall_subgraph`（整条召回链） | grep |

---

## 2. ✅ 已裁（17 条，一行一条）

> ⚠️ **这一节就是"我自己的 note"** —— 重复讨论的根因是 compact 之后我丢裁决。
> **动嘴之前先读这一节。**

| # | 裁决 | 详见 |
|---|---|---|
| **1** | **digest 按「视野」分三层**：`L-M` 对话轮 / `L1` 本段 / `L2` 跨段 / `L3` 实体；**不按轮**（`R5` 消掉、全景轮退役） | `DESIGN_DIGEST_LAYERS` §0 |
| **2** | ~~规律不落地成节点，落在边属性上（`same_kind{aspect, conf}`）；群的身份 = `aspect` 的值 ⇒ `group_by(aspect)`~~ ⚠️ **已推翻（2026-09-29）**：**群 = 节点**（`kind="group"`，`title` = 类名）+ ⭐ **`member_of` 边**（成员，自带各自 `ts`）；**`akin`** = **她的原始发现**（纯边，**无属性**；⚠️ 定名 `akin` 不叫 `same_kind` —— `kind` 在本项目已确切指"节点类型"，`same_kind` 会被读成"两条 kind 相同"）· **`Edge` 一个字段都不加**。理由：① 成员**会生长、各有自己的时刻**（"什么时候加入的"是信息，列表存不下）② `akin`（她觉得像）与 `member_of`（L2 判定）**是输入与输出，不能合并**。⭐ **"群上不放关键信息"** —— 判断归 belief，写两处必漂 | `DESIGN_MMT_NEW_ACTION` **§4.5** |
| **3** | **`add` 只归 L2**（`groups[].belief`）；`decisions` 只许 `touch`/`update` | 同上 §3.6 |
| **4** | **note = `promise` + `on_mind` + ⭐ `index`**（指向群的指针）；**`habits` 槽取消** | ✅ **2026-09-29（N4a）落地**: `habits` 退役 + `on_mind` 归 L1 + 全景轮退役。⬜ `index` 仍待做（它是 N12 的活, 要等 L2 建群才有原料） |
| **5** | **L3 = entity 摘要**（动态人设基线）—— 异步 · 派生缓存 · **不进事务** | `DESIGN_DIGEST_LAYERS` §4 |
| **6** | ⭐ **`refs` 要有走法（两条都要）**：引擎按 refs 展开（**注入时预取**）+ **给她一个动作**；**展开可选 link 连环**（默认 1 跳 + 预算） | `DESIGN_NOTE` §5.2 |
| **7** | **`index` = 纯派生缓存**（从边表重建，不落真源） | 同上 |
| **8** | **段边界** =「一个来访单位结束」= **空闲 ≥1h 或 章闭环（先到者）** | `DESIGN_DIGEST_LAYERS` §4.6(g) |
| **9** | ⭐⭐ **Link 移交 MMT**（本主题最重要的一次结构裁决）：**link 由 MMT 每轮发现 / collision 由 L2 离线派生**；一石五鸟 + 打破"先分组才能派生"的循环 | `DESIGN_DIGEST_LAYERS` **§0.1** · `MMT_DESIGN` §3 |
| **10** | ⭐⭐ **地址地基 = 一个地址空间**：**编号退回引擎内部，渲染时映射为标题**。唯一性**写入时强制**（冲突加数字，**只增不重排**）；**改名 ⇒ 旧名进 `aliases`** | ✅ **已落地 2026-09-29（N2b）**：`address.unique_title`（写入时加数字）+ `find_episode`（解析）**同住 `address.py`** —— 唯一性是**地址空间的不变量**，所以解析与写入在一处。⚠️ 跨 kind 那半还没消费者（等 `look` 要多 kind 解析）；`aliases` 未做 |
| **11** | ⭐ **需要标题的只有三类**：`episode`（骨架要指它）· `entity`（= `name`）· **群**（= `topic`/`aspect`）。**判据 = "注入给她的不是它的全部"** —— 全量常驻的**不需要** | 同上 |
| **12** | ⭐ **`inspect` 不退役**（用户裁决）：多人模式 / wiki 变大 / 玩家问起都要它 ⇒ 它是「**标题 → 论据**」的**唯一出口**。⚠️ 我已犯**两次**（拿 0/157 论证退役 = 陷阱 24） | `MMT_DESIGN` §2/§8 |
| **13** | **三种行的性质不许混**（`action` 抽象 = 错的分类）：她**说**的（`text`）· 她**发**的（图，**与 text 平级**）· 她**要**的（取论据）· **模式切换** · **顺手记账**（`noticed`） | 上文讨论 |
| **14** | ⭐⭐ **她只做「旧 ↔ 当下」**；**「旧 ↔ 旧」是 L2 的活**（要整组视野）。⭐ **实现已裁（2026-09-29）= 只记账 + L1 落地**：她那一轮**只记一笔**（⭐ **账就在事件流里**，零新存储），**L1 建完 episode 时直接落边** ⇒ 因为 `add_edge` **拒悬空**（端点必须是节点 id）、"seq 区间"不是节点，**原设计（seq 边 + 二分提升）在边表里没有合法表示** | `DESIGN_MMT_NEW_ACTION` **§4.4** |
| **15** | **`{"noticed": "标题"}`** —— 砍 `quote`/`what`：**定位 · 校验 · 归并维度全是引擎的**，她只做"指一下是哪条" | 上文讨论 |
| **16** | **日期 = 模糊 + 绝对两个都要**（模糊是她的口吻、绝对是引擎坐标）。⚠️ **history 只放常量**（绝对日期 + 周几）—— 模糊短语每天变，放进去每天炸一次前缀缓存 | 上文讨论 |
| **17** | ⭐⭐ **不许拿"防膨胀"当理由砍能力**（用户原话：*"不要为了解决这个问题把其他东西给丢掉了"*）。**膨胀的解法是"少花"，不是"少有能力"** | `MMT_DESIGN` §2 |
| **18** | ⭐⭐ **`when` 时间语法冻结**：**一个前缀 `back`**（`back A-B unit`，数字从 0 起、越大越早）。它是**过去检索语法**不是时间表达语法（`next`/`this`/`past`/`part`/时刻全砍）· 粒度 **day** · `back` 是**类型前缀**（省了就退回"时长"歧义）· 锚表 = `festivals.json` 那套（加一行 = 加一个节日） | `DESIGN_MMT_NEW_ACTION` §2 |
| **19** | ⭐ **`look` = 唯一"要东西进来"的动作**（与 `inspect` **合并**；权限按目标 kind 分派）· `{"look": […], "when": …}` 两字段都可选、至少一个 · 数组 **= AND**（要 OR 查两次）· 三级解析（标题→检索→明说）· 返回 **info-head + info** · ⭐ **空结果明说是"该问老师了"的触发器** | 同上 §3 |
| **20** | ⭐ **段的推进（D0，2026-09-29 已落地）**：**触发** = MMT 每 **40 轮**（1/3 window）**或** 章闭环 · ⭐ **水位 = 她这次实际覆盖到的最大 seq**（不是触发点）⇒ 没覆盖的**尾巴**并进下一段**重喂**；**只救尾巴、中间空洞不重喂** ⇒ 连带 **章块的覆盖由引擎兜到整章**（必要配套：否则章尾会被当孤儿章重记）· 两条兜底：**零覆盖推到窗口上界** · **窗口 > 120 条内容事件就丢最老的** | `EXEC_DIGEST_SPLIT` **§11** |
| **21** | ⭐ **约定（`promise`）改造成"她实时记的誓约"**（2026-09-29 讨论，**未开工**）：① 判据收到 **"说定的将来 + 值得随身带着"**（"忘了就是说话不算数" **或** "哪怕不会忘也该带着"；⛔ 日常安排/事务不记）② **实时 mark**（MMT 第四类行，与 `noticed` 并列 ⇒ **当场**进 note，不再等 40 轮）③ 结清（`close` + `afterwards`）**并入 L1**，**R4 整轮删掉** ④ ⭐ **不建固化节点** —— close 指到的那条 episode 打 **`#vow`** tag（机制已有 = 今天的「约定」tag；`digest_record.md` 那一行**举的例子本身就是"安排"**，是收得太松的病根）⑤ 结清的条目**不退场**（注入了才看得见）⇒ 需要一条**淘汰规则** ⑥ 失约/无疾而终（指不到 episode）**给它一条 episode** | `EXEC_DIGEST_SPLIT` §12 |

---

## 3. ⬜ 待裁（7 条）

| # | 项 | 我的倾向 |
|---|---|---|
| **1** | **L3 的注入位置**：**替代**一部分 episode 全量注入，还是并列？ | ⭐ **"换一种读法" + 分两步走**（步 1 只加 L3 + 骨架不砍正文；步 2 验证预取命中率后再砍）—— `DESIGN_DIGEST_LAYERS` §4.1 |
| **2** | **`refs` 预取的命中率阈值**（步 2 能不能开的门槛） | 需真机标定 |
| **3** | **`payload` 信封去掉吗** + 五个键的名字（`text` / `media` / `look` / `enter_story` / `noticed`） | 去掉信封（性质不同不许套同一形状） |
| **4** | **I-c 窄破**（"她嘴里不许精确日期；渲染栏可以"）· 改 `phone_date_note` 那句 *"不要把它写进你记得的事里"* · `history_rounds` 改名（它今天不表示轮数） | 三条都做 |
| **5** | `MMT_DESIGN §3.6` 的**读法**：标题是"让她多想起几条"，还是"她输出那个类"？ | 前者（后者已被 §3.2/§8 否掉） |
| **6** | **note 的 close 路径**：接上"主 LLM 顺手字段"，还是砍掉"印编号"那个例外？ | 砍例外（今天零消费者；要接也得用**文本**当句柄） |
| **7** | **`noticed` 那一笔没被任何 episode 认领** ⇒ 下次 L1 要不要**重扫**？ | 要（否则等于丢） |

✅ **已裁**：~~MMT 侧"她引用的当下"怎么落~~ ⇒ **§2 #14**（**只记账 + L1 落地**，2026-09-29）。

⚠️ §1 的"wiki 注入形式"讨论完，还会产生新裁决 —— **一律进 §2**。

---

## 4. 立刻要用的真机数字（`data/worlds/world1`）

```
haruka : 26 节点（18 episode + 4 belief + 4 entity）· 39 边（20 supports + 19 about）
         316 事件 · digested_seq=314 · note 6 条（note/close 0 次）
注入   : brain 4205 字 + history 5287 字（70 单元）≈ 9500 字符
5 个真组: 苔藓 · 夏莱 · 笔记 · 道歉 · 团子
致命三数: 4 条 belief 全部诞生自 1 条 episode · episode↔episode 边 0 条 · links 只写过 2 次
embed  : text-embedding-qwen3-embedding-0.6b（nomic 已换，见 TRAPS 38）
```

**四条实测结论**（讨论注入形式时都要用）：

| 结论 | 数值 |
|---|---|
| dense 相似度**判不了同类** | 组内最低 < 组外最高，最差 **0.425**（任何 k / 任何阈值下 4 个真组 **0/4 干净**） |
| 字面（`tags`）**精确度 1.00** | 归一化能把召回 0.67 → **1.00** |
| `inspect` 使用率 | **0 / 157 轮** |
| `contradicts` | **0 条**（机制齐全、零数据） |

### ⭐ N5a 探针（2026-09-29 重测，`.testtmp/probe_n5_recall.py`）

```
18 条 episode: **标题全唯一、全非空**（地址地基在真机上成立）
brain 段: 4309 → **4595** 字（元信息段 `〔《名》｜相对｜绝对｜难忘〕` 共 **+286 字**, ≈ +6.6%）
每轮召回段: 实测 **1~2 条 / 350~650 字**（真机一条 episode 正文 300~570 字）
embed_fn: **无（退词面）** ← 本机 LM Studio 没起（TRAPS 38 那条静默降级）
每轮召回命中（8 句真问题）: **4 / 8**
  ✓ "杂草屋那边发生过什么" → 中秋的杂草屋 · 杂草屋的环境调研
  ✓ "我今天又去看了看那片苔藓" → 瓦片缝里的苔藓 · 约老师来看苔藓
  ✗ "上周你都干了些什么"  → 0（**时间类问题不是 N5 的活**：那是 `look` + `when`）
  ✗ "上次在餐厅那回"      → 0（真身 = m0004「和老师的第一顿高级料理」——**语义通道关掉就抓不到**）
```

⭐ **用户裁决**：
1. 召回段**照旧全文注入** —— *"就是要全文注入，实在不行 digest 的时候让 LLM 精简即可；后续会考虑如何常驻信息，但这不是现在的问题。"*
2. 记忆行的形状**定稿**（2026-09-29，三轮讨论）：
   **`〔《事件名》｜多久以前｜日期｜难忘〕`** —— 事件名**放第一**（摘抄起点固定）·
   事件名用 `《》` 包（**加了对她无害**：锚点解析剥括号，带不带都命中）·
   字段边界用 **`｜`**（`·` 会出现在事件名里 ⇒ 抄多抄少 ⇒ 静默丢）·
   括号清单落成 **`docs/CONTEXT_MARKS.md`**（一形一义）。

---

## 5. 文档地图（**关键内容在哪**）

| 文档 | 管什么 |
|---|---|
| ⭐ **`docs/MMT_DESIGN.md`** | **主对话轮的设计（上游）**：三种行（消息/操作/记录）· `inspect` 慢路 · **link 记录行 + 锚 + 区间** · 手边六格 · 情形表 · **相对其他项目解了什么** |
| ⭐ **`docs/DESIGN_MMT_NEW_ACTION.md`** | **动作规格（上游的动作面）**：行的性质不许混 · ⭐ **`when` 语法（冻结）** · **`look`**（三级解析/权限分派/返回形状/延迟账）· **`noticed`**（只记账 + L1 落地 · ⭐ **§4.5 群 = 节点 + `member_of` 边**）· 同步/异步判据 · 落地七步 |
| ⭐ **`docs/DESIGN_DIGEST_LAYERS.md`** | **digest 三层重排（动工文档）**：§0.1 根因与最终分工 · L1/L2/L3 规格 · 边与图 · 候选池"窄而深" · L3 注入详解 · 节点拆分 |
| ⭐ **`docs/DESIGN_NOTE.md`** | **note 的真正定位**：人的三类 note · LLM 的三条差别 · 三条合一的存在判据 · **第三槽 `index`** |
| ⭐ **`docs/TODO.md`** | **施工顺序表（15 步）** + 每步细化 + 判据 + 三条纪律 |
| ⭐ **`docs/TRAPS.md`** | **陷阱 1–50**（编号全局，**不许改**） |
| ⭐ **`docs/CONTEXT_MARKS.md`** | **上下文里的括号约定**（一形一义）: `【】`段头 · `〔〕`元信息 · `《》`事件名=地址 · `（）「」`正文与原话 · `[]`历史动作前缀 · `{}`JSON · `<>`占位符 · `｜`字段边界（⚠️ **`·` 不是边界**） |
| ⭐ **`docs/RESEARCH_MEMORY_SURVEY.md`** | **三份调研结论**（本地深读 / 学术侧 9 条 / 生态侧 26 条，带出处与检索边界） |
| `core/brain/DESIGN_GRAPH_V4.md` | 图的设计稿：走法（**6 条**）· kind（**5 种**）· 每段四步 · 全景轮（⏸ promise 两段式 2026-09-29 退图） |
| `docs/DESIGN_WIKI_V3.md` | V3 设计稿：四轴 · `nature`（含 `pattern`+`occurrences`）· 四条召回道路 |
| `docs/DESIGN_RECALL.md` | **另一条链（读路径）**：`mmt_recall` 四支 scope / `when` / 结果生命周期 |
| `docs/EXPERIMENT_CAND_HIGH.md` | Q11 阈值实验（**nomic vs Qwen3 实测**——换模型的依据） |
| `CLAUDE.md`（仓根） | 项目主文档（⚠️ **改前先改名**）；§7 记忆 · §10 配置 · §12 测试/提交纪律 |

---

## 6. 施工顺序

⭐ **在 `docs/TODO.md`**（15 步，`N1` 边加属性 → … → `N15` 验收）。
**顺序原则**：输入面先修 → 免费的先做（含 **MMT 的发现**）→ 花钱的放最后。
**硬约束**：`N1` 起手；`N3`（L1 区间化）不做完，后面每步的输入都是脏的。

---

## 7. 纪律（**别违反**）

1. **动手前先说做什么；动手后报告"做了什么 / 遇到什么问题 / 下一步"**；⚠️ **歧义就停下讨论**
2. ⭐ **复杂节点先把逻辑整理给用户**（2026-09-25 那条救掉一个错判）
3. **一节点一提交**；`git commit -F <文件>`（**CJK 会炸 `-m`**）；只 stage 明确路径
4. ⭐ **改 `CLAUDE.md` 前先改名**（`git mv CLAUDE.md CLAUDE_EDIT.md` → 改 → 改回）；它的预算已满
5. 不跑 `ruff --fix`；不提交 `config/characters/*/illustration.yml`；`tools/` 是 gitignore
6. ⭐⭐ **别拿"真机数据频率"论证价值**（陷阱 **24**）—— **没压过的地方就是 0**（`inspect` 0 次 / `contradicts` 0 条都是这一类）
7. ⭐ **改契约必须同批改示例**（陷阱 **3/46**）—— **示例才是形状的来源**
8. ⭐ **调研结论要带出处 + 标检索边界**（*"在能读到的范围内没有"* **≠** "不存在"）
9. ⭐ **答复用户要具体**（他两次说"没咋听懂"）：**不堆比喻**，直接说问题在哪 / 能不能解决 / 代价是什么；**用真机数字说话**
10. ⭐⭐ **测试分两级**（2026-09-29 用户裁决）：**子节点只跑小回归，大节点收口才跑全量四件套**（§8）。全量 ≈ 5 分 20 秒，别在半成品上烧它

---

## 8. 验证配方（**分两级**）

> ⭐⭐ **2026-09-29 用户裁决：全量四件套只在「大节点收口」时跑。**
> **子节点**（`N5a/N5b/N5c` 这种拆出来的步）**只跑相关小回归**；一个**大节点**（N5 整体）
> 做完才跑一次全量。理由：全量 ≈ **5 分 20 秒**，拆一步跑一次 = 把时间花在还没做完的东西上。
> ⚠️ 跑全量时**别加 `| Select-Object -Last N`** —— 管道要等进程结束才吐字，
> 中途 `job_output` 永远是空的（看不到进度，像卡死）。

> ⚠️ **改到一半的树不跑回归**（2026-09-29 用户裁决）: 手术没做完树必然是红的, 跑了只是"还在改"。**中途只跑** `compileall` + **`pytest --collect-only -q tests`**（≈2 秒, 只查 import/语法断裂）; **一个节点改完只跑碰到的那几个文件**（秒级）; 全量四件套只在大节点收口。

**① 子节点：小回归**（只跑改动面那一片；下面是常用几组）

```powershell
New-Item -ItemType Directory -Force .testtmp/pw | Out-Null   # ⚠️ Windows 下要先建

# 改 wiki 层（render / recall / digest / store / graph）
python -m pytest tests/core/test_wiki_digest.py tests/core/test_digest_registry.py `
  tests/core/test_wiki_graph.py tests/core/test_wiki_store.py tests/core/test_wiki_render.py `
  tests/core/test_wiki_recall.py tests/core/test_round_close.py tests/core/test_round_attr.py `
  tests/core/test_wiki_revise.py -q --basetemp=.testtmp/pw_graph

# 改 MMT 轮/行协议/注记
python -m pytest tests/core/test_mmt_recall_note.py tests/core/test_momotalk_time_notes.py `
  tests/core/test_mmt_round_protocol.py tests/core/test_mmt_lines.py tests/core/test_mmt_check.py `
  tests/core/test_split_safety.py -q --basetemp=.testtmp/pw_graph

# 改 bond / webgui 章内
python -m pytest tests/webgui -q --basetemp=.testtmp/pw_bond
```

**② 大节点收口：全量四件套**

```powershell
python -m pytest tests/core tests/webgui tests/llm tests/renderer -q --basetemp=.testtmp/pw
python -m compileall -q core contract webgui apps llm tests main.py
node --check webgui/static/js/bond.js
python experiments/web_e2e/run.py
```

**最近一次已知绿**：全量 **1125 passed**（`N5a` 工作树，321s）· `compileall` 绿 · `node --check` 绿 ·
**B 层冒烟 PASS**（2026-10-01 00:21 产物目录 `.testtmp/webtest/20261001_002114`）。

**只读探针**（`.testtmp/` 是 gitignore，可能被清 ⇒ 结论已抄进各文档）：
`probe_mmt_view.py`（**真机注入 dump**）· `probe_bfs_purity.py`（dense 判不了同类的决定性证据）·
`probe_literal_dims.py`（tags 精确 1.00）· `probe_embed_ab.py`（nomic vs qwen3）·
`probe_belief_birth.py`（4 条 belief 全诞生自 1 条）· `probe_abstraction.py`（抽象句占比）·
另有 `probe_graph_shape` / `probe_time_axis` / `probe_turn_grain` / `probe_group_keys` /
`probe_chapter_scope` / `probe_mmt_grain` / `probe_pure_mmt` / `probe_mmt_entropy` / `probe_sessionize` /
`probe_belief_redundancy` / `probe_llm_load` / `probe_reabstract` / `probe_bfs_components` / `probe_ts_crash`

---

## 9. 提交记档（最近）
| 提交 | 内容 |
|---|---|
| `d0e4fe9` | embedding 换模型：**nomic → Qwen3-Embedding-0.6B**（并排实测 + 钉死配置） |
| `ca604d5` | PROCEED 第二次整篇重写（§4 推理链 + 三层） |
| `eaa1b63` | §4.4b belief 会不会膨胀（实测 + 三条准入） |
| `d055616` | **动工文档 `DESIGN_DIGEST_LAYERS` + `DESIGN_NOTE`** |
| `53f02db` | 落四条裁决（refs 走法 / index 派生 / 段边界 / L3 详解） |
| `41fa193` | §3.3 补"不做 tool call 怎么注入 graph"的七条路 |
| `02dab87` | L2 规格落五动作 + 新建 `TODO.md` |
| `ec5c0fc` · `c037e33` | **Link 移交 MMT**（§0.1 根因与最终分工） |
| `fbcf654` | **新建 `MMT_DESIGN.md`**（三种行 / inspect / link） |
| `d22a5f6` | ⭐ **PROCEED 瘦身成"接续用"**（1135 → 226 行）：陷阱 → `docs/TRAPS.md` · 调研 → `docs/RESEARCH_MEMORY_SURVEY.md` · **§1/§2/§4 → `docs/REASONING_LOG.md`** |
| `fd00aae` | ⭐ **新建 `DESIGN_MMT_NEW_ACTION.md`**（动作规格：`when` 语法冻结 / `look` / `noticed` / **群**）· 推翻 §2 #2（边属性 → 群是节点 + `member_of`） |
| `6eb89e1` | ⭐ **N1a**：`akin` 边（7→8）· `SYMMETRIC_RELS` + `canonical_for`（对称性唯一一份）· 顺手修 `clone_state` 位置参数 |
| `d08f2ae` | ⭐ **N1b**：`group` kind（前缀 `g`）· `member_of`（8→9）· `_ABOUTABLE` 加 group |
| `327821c` | ⭐ **N3**：位置字段 `event_seq`（逐点挑选）→ **`span`（区间）**；引擎 `_expand_spans` 展开 + 未认领/重叠台账。真机覆盖率 **67.9%** 是它的立项理由 |
| `5779c31` | ⭐ **修章内两个既有竞态**（陷阱 **48/49**）：`resumed` 支漏落 `vn_enter`（回忆册 0 章）· staged 预热支**无条件收尾**补假 `vn_exit`（完成淡行不出现）。两处修 + 2 用例；B 冒烟从红转 **PASS** |

---

## 10. ⚠️ 章节对照（**旧编号 → 新家**）

> 2026-09-27 瘦身时重排了编号。**别处写 `PROCEED §N` 的引用，按这张表找。**

| 旧编号（被别处引用过） | 现在在哪 |
|---|---|
| §1 验收样本（送花台词 + 反例 + 玩家觉察） | ⭐ `docs/REASONING_LOG.md` **§1** |
| §2 为什么现在的是坏的（真机证据 + 提示词 + 管线） | ⭐ `docs/REASONING_LOG.md` **§2** |
| §3 调研结论（三份，带出处） | ⭐ `docs/RESEARCH_MEMORY_SURVEY.md` |
| §4 本轮推理链（4.1–4.7b） | ⭐ `docs/REASONING_LOG.md` **§4**（**子编号原样**：`§4.4b` / `§4.6(g)` / `§4.7` 都在） |
| §5 拆分 + 待裁 | ✅ 仍在本文 **§2/§3**（裁决拆成"已裁 / 待裁"两张表） |
| §6 工作约定 | ✅ 仍在本文 **§7 纪律** |
| §7 已落地 / 已退役 | ✅ 并入本文 **§9 提交记档** |
| §8 陷阱清单 1–47 | ⭐ `docs/TRAPS.md`（**编号不变**） |
| §9 验证配方 + 真机基准 | ✅ 仍在本文 **§4 + §8** |
| §10 文档地图 | ✅ 仍在本文 **§5** |

⚠️ **新增/追加的规则**（搬家时验过：`TRAPS.md` 1–47 连续、`RESEARCH` 三节齐全、`REASONING_LOG` 各小节齐全）：
- **陷阱只许追加**，不许插入/重排（编号是全局引用键）
- **本文只更新三处**：§0 下一步 · §2 已裁 · §3 待裁；**新内容一律进设计文档**
