# Live2Be 待办表（2026-09-03 快照；2026-09-15 校准）

> 此表是跨 session 的进度锚点——完成一项就勾掉。旧快照（08-23）已清理归档进 git 历史。
>
> **2026-09-15 校准说明**：本表停在 09-03，中间有两大段工作**没进过这张表**，
> 已在下面就地更新（时间架构、召回链路、地点系统、阈值退役）。跨 session 找进度时
> **别只信这张表**——`git log --oneline` 与各设计稿的状态头更准。
>
> **近期已落地（09-13 ~ 09-15，全部在 master）**：
> - **V3-0 召回台账** + 五链路接口（`core/brain/wiki_v2/channels.py`）
> - **时间骨干 T0–T13**：`core/worldtime/` 独立包（剧情时间游标 / 虚化短语 / 手机日期）
> - **召回链路 T14–T15**：时间线记录级索引 + 板指针接通 + `verbatim` 两条通道 +
>   B 链路（情绪序列 RAG）实现 + 召回侧字段隔离（`emo_shape` 等不进 LLM 上下文）
> - **地点 T16**：盒B 去内容词表（`place_palette` → `place_world`）+ `regions.yml`
>   归一（`core/parsing/place_regions.py`）
> - **T17**：删 `cand_high`/`cand_med`/`accept_hit_rate` + `must_touch` 结构强制
>   （Q11/Q31/Q32）——候选仅作提示
> - **T18**：`LocalEmbedder` 配置面（`settings.toml [embed]` + `LIVE2BE_EMBED_*`）+
>   `health()` 真探测 —— **等 embedding 服务起来，写路径自动活**（见下方中期项）
> 关联：CLAUDE_OPTIMIZE.md（优化方向状态清单）/ guidance/（角色卡写作指导）/
> AGENT_BRAIN.md（wiki 实施蓝图, 含开放问题 §9）/ DESIGN_BRAIN.md（记忆体系总纲）

## 进行中 / 即将

### ⏳ 时间轴换代：剧情日历 → 现实日期（2026-09-17 讨论定稿 + 用户五问五答）

> 讨论全过程（含两次翻盘与三次误判）：**docs/ESSAY_TIME_MODEL.md**（§10 = 结论）
> 一句话：**唯一日期轴 = 现实日期（`ts`）。剧情内部的流逝自由，但不累积、不进账。**
>
> **已落地**（`c4ff326` / `b569ff7`，745 passed）：映射层 + 段日期 + 删剧情时间注记。

**用户裁决（2026-09-17，五问五答）**

| # | 问题 | 裁决 |
|---|---|---|
| q1 | 她能不能注意到「手机上的日期不推进」？ | **不必注意**。承认 **double yesterday / double date 是结构性的、躲不掉** —— 不修，靠**提示词加固** |
| q2 | 手机的双重性写死到哪 | **允许 LLM 做简单日期推理**（*"从 9/13 当天以及昨天推到 9/12，一天都推不出来别当 AI 了"*） |
| q3 | 手机报「还有几天」还是「下次哪天」 | **挂起** —— 本质是 MMT 扩展 |
| q4 | 手机提醒的范围到哪停 | **挂起**；但立了一条设定：**她的时间感只在「一周以内」可靠**（*"我生日 5/10，你 4/26 问我还有几天我也答不上来，这是无止尽问题"*） |
| q5 | 生日/节日**补发**吗？ | **不补发** —— *"自己圣诞节不上线怪谁捏"* |
| — | 节日/生日**触发器本体** | **一并挂起**（§4.4 / §4.5 现在不做） |

**⭐ 两条边界（从 q2/q4 出来，要写进纪律）**

```
① 引擎给她的注记  →  仍受 I-c 约束（不给精确值 / 不给日期）
   她自己的推算    →  **允许**（她看得见"现在"，也记得"昨天"）
② 她的时间感**只在「一周以内」可靠** —— 更远的跨度，人本来也答不出来
```

**A. 可立即做（不依赖任何裁决）**

- [ ] **写入侧 `ts` 收敛到 `age.now_ts()`** ✅ **已完成**（`180e79a` / `f105afd`）
- [ ] **提示词加固**（q1 的直接产物，进 `rules_mmt` / `rules_bond`）—— 草案见 B
- [ ] **删**（时间换代剩下的整片）：
      `story.py`（`StoryTime` / `PHASES` / `DAY_PARTS` / `from_sim_day` / `advance` /
      `parse_story_time` —— **含 `:268` 那个自锚定 bug，删掉即消失**）·
      `clock.py` + `world_clock.json` · `span.py` + Round A 的 `time_span`
      （schema / prompt / 夹具同批）· `migrate_time.py` · `realtime.py` 空壳（**已重写为真实现, 见下节**）·
      `BrainNode.story_time` + `nodes.py:_parse_story_time`
      ✅ **已完成**（`dbb931b` / `09899f1` / `1f9cd67` / `84c809f` / `180e79a`）；
      ⚠️ **`span.py` 与 `time_span` 按用户裁决保留**（"输出但不消费", 等衰减新模型）
- [ ] `store.py`：`clock()` / `clock_path` / `save_clock` / `restore_clock_cursor` → 删 ✅ **已完成**（`1f9cd67`）
- [ ] `digest.py:206-213` 的时间推进整段删（`_clock.advance` + `new_cursor`
      + `story_time=` 实参）✅ **已完成**（`84c809f`）
- [ ] `recall_config` 的 `time_half_life_days`（及 `settings.toml [recall]` 同名项）
      —— **不是重标定，是等新模型**（见下）

**⏸ 记忆衰减：模型待重做（用户 2026-09-17 裁决）**

> *"这个东西要，但是之后它的计算方式会被改变。由于玩家游玩的时间通常是**密集成块的
> 离散**，不能用记忆曲线，需要新模型，但那是以后的事。"*

换轴（叙事日 → 现实日）之后，`freshness = 0.5 ** (age / half_life)` 的**两个方向都变了**：

| | 旧（叙事日） | 新（现实日） |
|---|---|---|
| 玩家**在玩**（密集成块） | `age` 随剧情 +N → 衰减快 | `age` 基本不动（同一现实日）→ 衰减慢 |
| 玩家**不在玩** | `age` 完全不动 → **不衰减** | `age` 随现实流逝 → **衰减快** |

而玩家的游玩时间**天然是密集成块的离散**，记忆曲线假设**连续均匀** —— **不匹配**。

⚠️ **2026-09-17 核实后修正两条口径**（以代码为准）:

1. **"在玩时衰减慢"不成立** —— `age` 是**现实日历日差**, 与玩没玩无关。
   你在 9/7 玩 3 小时、9/11 再玩, 9/7 的记忆 `age=4` → `freshness=0.574`。
   表里那格（"在玩 → age 基本不动 → 衰减慢"）是**换轴前的想象**, 不是行为
2. **`time_span` 不是新模型的输入** —— 见下

**真机数据长什么样**（`data/worlds/world1` 的三个角色）:

```
igusa_haruka    31 事件 → 只有 2 个活跃日:  9/7 有 8 条, 9/11 有 23 条
asagi_mutsuki   61 事件 → 只有 2 个活跃日:  9/9 有 1 条, 9/12 有 60 条
```

⇒ "离散"不是"隔几天玩一次", 是**"一天里塞进一整章, 然后消失几天"**。
⇒ 而且**不管玩 3 小时还是 10 分钟, `age_days` 只有 0 和 1 两个取值**。

**✅ 2026-09-17 已做的一步：`freshness` 加下界 `floor`**（其余仍待标定）

用户裁决: *"先把 floor 写了吧"* + *"现在其实根本没有数据，我们就……自行判断吧"*。

```
freshness(age, half_life_days, floor)
  = floor + (1 - floor) * 0.5 ** (age / half_life_days)
```

| | |
|---|---|
| 旋钮 | `settings.toml [recall] time_freshness_floor`（默认 **0.25**; `0.0` = 关掉） |
| `age=0` | 仍是 **1.0**（新记忆不受影响）—— 这条没变 |
| 半衰期处 | 从"正好 0.5"变成 `(1+floor)/2`（**行为变更**, 老测试的断言已改写） |
| 尾巴 | `age=365` 从 `1.06e-22` → **`0.25`** |

**为什么必须有它**（实测, `floor=0` 时, `half_life=5.0`）:

```
A = 一年的重大约定（SIG=0.90, 情绪平淡 ⇒ 矩阵第二项=0）
B = 今天的一句寒暄（SIG=0.50）
  交叉点 ≈ 4.2 天 —— 七天后 A=0.341 vs B=0.500, A 输; 一年后差 22 个数量级
```

⇒ 一个"**情绪平淡但重要**"的记忆（约定/事实/承诺）四天就被今天的寒暄盖过，
而它**没有别的机制撑**：情绪上的重要有矩阵第二行（不衰减），平淡的重要只剩
`SIG·fresh` 一项。

⚠️ **但 `floor` 不是万灵药**（这句要留着）：`floor=0.1` 时最坏 `0.9×0.1=0.09`，
**仍然输给** `0.5×1.0=0.5`。想让它长期占优需要 `floor≈0.56` = 几乎不衰减 = 背叛
这个函数的理由。⇒ 真正缺的是**第三条通道**：见下。

⚠️ **`0.25` 是判断不是标定**（用户原话: *"我们就……自行判断吧"*）。判据写进了
`age.py::freshness` 的 docstring：`SIG` 实际取值 `0.5~0.9`，取 0.25 时最旧的
`SIG=0.5` → 0.125、`SIG=0.9` → 0.225，而"今天"的 `SIG=0.5` → 0.500 ⇒
**仍然"新的赢"，但差距从无穷缩到 2~4 倍**。有真机数据后连同 `half_life` 一起重标定。

**⏸ 第三条通道：`SIG`（重要）× `emo_*`（情绪）之外，缺"重复提起"**

一个每周被想起来的约定，不该跟一次性的往事同命运。而这套机制的**位置已经留着、
实现没有**：

- `channel_impl.py:29` / `recall_ledger.py:26` 都注明"**不改任何节点、不写
  `last_recalled_at`**（那是 V3-3 的事，且要评估代价）"
- `DESIGN_WIKI_V3 §3.3` 把它归到**物化层**（"一次算、索引表里存"）
- 全库**无** `last_recalled_at` / `recall_count` / `times_recalled` 字段

⇒ 这是"情绪平淡但重要"的正解，`floor` 只是它落地前的**止损**。

**⏸ 换轴（单位）本身的形状（讨论过, 未实现 —— 等真实游玩数据）**

要求之间**互相打架**, 这是它难的原因:

| | |
|---|---|
| R1 | 一次 3 小时的连续游玩, 段内记忆**不该**因真实时间流逝而变旧 |
| R2 | 隔一周再玩, 旧记忆该变旧**一点** |
| R3 | 隔一年再玩, 旧记忆该**很旧** |

单条 `e^{-k·年龄}` 满足不了全部: 用"活跃日数"当年龄 → R1/R2 ✅ 但 R3 ❌
（玩 200 次后第 1 次的记忆只差 200 块）; 用"现实日数" → R3 ✅ 但 R1 ❌（现状）。

两个候选（探针 `.testtmp/probe_decay2.py`, 未落代码）:

- **A 加权块龄**: 年龄 = 带权活跃日（每"回来一次"记一块, 权重 = 距上次回来隔了多久）
  —— R1 天然满足（段内不新增块）, 缺勤自动进账; 但 R3 偏弱
- **B 两个坐标**: `现实日衰减 × 练习加成 × 缺勤惩罚` —— R3 直接满足, 三项可各自关掉;
  但要标定三个参数

**⇒ 卡在"没有数据"上**: ⚠️ **`events.jsonl` 里没有"会话"这个东西** ——
只有行级 `ts`。`session_start` 在真机只有 1 条而事件跨 5 天 ⇒ 它不在每次开游戏时写。
**标定常数之前必须先有会话数据**（用户 2026-09-17 裁决: 每次开游戏写一条会话标记）。

**⏸ 记忆衰减（旧结论）**：**调 `half_life` 数值解决不了**，需要新模型。
⇒ 在那之前，日常记忆的衰减行为**是已知不正确的**；唯一缓冲是矩阵第二行
   `emo_span·emo_int` **不衰减**（强情绪记忆不受影响）。

**另一条同源后果（设计内，但要记档）**

- [ ] **同一天玩的多章 → `age` 全 0 → TIME 格无区分度**：
      旧口径下一章 = 一段剧情时间（age 递增、TIME 递减）；新口径下 5 章都在
      同一个现实下午（age 全 0、TIME 全 1.0）⇒ 章与章之间**时间维度完全不起作用**，
      召回只靠 `SIG` 与 `emo_span·emo_int`。这是"段内无区分度"（约束 2）的放大版：
      从**段内**扩到**一整天**。
- [ ] （可选）章节序数，从 `segment_id` 推

### ✅ 孤儿字段审计（2026-09-17，与 `time_span` 同批）

> 判据 = `time_span` 的形状：**有定义、无消费**。逐项手工核实（脚本会把调用点的
> kwarg 当消费算, 有假阳性 —— 别只信脚本）。

**删了一个**:

| 字段 | 三重身份（生产者 / 消费者 / 真机数据） |
|---|---|
| **`time_span`**（A 轮契约） | ❌ 无消费（推进链已删）· ❌ **parse 层从来没取过它**（`parse_round_a` 只读 `episodes`）· ❌ 真机零记录 ⇒ 每轮 digest 白付 token |

**留了一个（用户裁决）**:

| 字段 | 处置 |
|---|---|
| **`BrainNode.observation`** | ⏸ **已声明、未投产** —— *"以后多人模式这个可能会很有用；现在我们的 digest 模式还没处理，只是在做前置"*。**不落库**（不在 `to_dict` 里，零生产者零消费者）; 旧档的键宽松忽略。⚠️ v3 落地时它**大概率不留在 belief 上**，应折进实体模型（`about` + `aspect` + `nature`），见 `nodes.py` 字段区说明 |

保留：`span.py` 的枚举定义（契约死了语法不必死）; 旧档里多余的键由 `from_dict` 宽松忽略。

**未来模型（用户 2026-09-17 口述，与 `DESIGN_WIKI_V3` 已写的设计吻合）**:

> *"它最终以 entity 对象节点为中心，belief 为第一层，episode 连接 belief 的水波形。"*

对应文档：`DESIGN_WIKI_V3.md §2.1`（实体中心的两层图）/ `§2.2`（entity 层）/
`§3.5`（BFS `entity → belief → episode`，深度上限 2 = "总-分-证"）。
⇒ `observation` 的挂点在**那个模型里**，不在现网的 v2 belief 上。


**查过是活的（留档, 免得下次重查）**: `source`（`render.py:187` 的出厂/运行期分流）·
`contradictions`（`recall.py:110` 一跳扩展）· `source_key`（出厂 seed 判重键）·
`history`（belief 改写溯源）· `growth` · `emo_shape`（B 链路）· `verbatim_seq` ·
`pkg`（`evolution.jsonl` 的操作批次）· `place_hint` / `art_hint` / `seed` / `visual` /
`input` / `round`（`vn_state` 恢复点）· `created_at`（`list_open` 排序 + 登录页显示）·
`digested_seq`（增量水位）· `rounds_since_bond`。

**查过是旧数据不是孤儿**: `progress.json` 里的 `rounds`（kayoko 那份）——
`read_bond_gap` docstring 明写"旧版文件（仅 rounds 键, 死数据）→ 视为 0"，
是 2026-09-02 的**有意裁决**, 不是漏删。

**防复发**: `tests/core/test_wiki_nodes.py` 两条 ——

- `test_every_serialized_field_is_parsed_back`：钉住 `to_dict` ⇄ `from_dict` 的字段一致
  （`observation` 就是"两边都写了、但没人生产也没人读"的三方缺两方）
- `test_observation_stays_dormant`：把"休眠"变成**可执行断言** —— 声明必须在、
  不许落库、**wiki_v2 里不许有任何真的读写它**（AST 扫描，不误伤 docstring）。
  已验证它会红（临时插一行赋值即失败）。谁要投产，就得先在这条用例里登记"谁生产、
  谁消费"，顺带被迫更新 `nodes.py` 的字段区说明

**未查（明确不在本轮范围，用户裁决"config 和 assets 不用管"）**: `config/` 的键 ·
`assets/` 的 yml 字段 · 前端 JS 读的响应字段。


**B. 提示词加固草案（q1 产物，待审）**

```
时间只有一条：老师那边的日历（你手机上看到的那个）。
· 你记得"今天""昨天"，也能从它们推出前天 —— 简单推算可以。
· 超过一周的跨度你答不出来（人本来也答不出来）。别硬编。
· 同一天里可以发生很多事 —— 那不是异常，不要因此觉得时间不对。
· 若你确实觉得对不上（做了好多事，日期却没怎么动）：
  只说"和老师在一起的时候，时间好像不一样" —— 不深究、不解释、不推算。
```

**C. 挂起（用户裁决 2026-09-17）**

- ~~节日 / 生日**触发器**（`real_clock.json` / 节日表 / `fired` 幂等）~~ →
  **2026-09-17 改判: 节日表已实现**（见下「现实日历」节）; **生日仍挂起**
  （用户: *"仍然读 yaml，角色生日的处理模式可能不太一样，正好先不啃这根骨头"*）
- 手机报「还有几天」/「下次哪天」、提醒范围 —— **本质 MMT 扩展**
- **补发** —— **不补发**（裁决）; 实现层再加一条"新角色**零**补发"（见下）
- `snap_to` / 目标日吸附（§4.6）—— **不需要**（只有一个时钟）
- `time_of_day` 独立字段 —— **作废**（戏内时刻归场景文本 → 标注层反推 `variant`）
- ~~`【现在是】` 剧情时间注记~~ ✅ **已删**（`b569ff7`）

**D. 要改的文档**

- [ ] `DESIGN_WIKI_V3.md §4`：整章标记作废 → 指向新稿；**§4.1 三条红线**一并处理
      （红线 1「影响召回排序必须用①」、红线 2「②绝不用来算记忆年龄」**前提已取消**）
- [ ] `CLAUDE.md §13` 时间架构那一行（gitignore，本地改）
- [ ] 本表开头「时间骨干 T0–T13」一行标注**部分作废**

### ✅ 现实日历（②）：特殊日期表 + 触发幂等（2026-09-17 落地）

> 一句话：**引擎只答"今天是不是某个日子"，不答"所以呢"。**
> 表 = `config/eggs/festivals.json`（作者手编）; 台账 = `data/worlds/{w}/real_clock.json`。

**已完成**（模块 `core/worldtime/realtime.py`, 44 个新用例）

| 件 | 说明 |
|---|---|
| 表 | 三栏（年/月/日）+ **留空 = 匹配任意**; `proactive` **逐行必填**（无默认值） |
| 判定 | `occasions_on`（纯投影）/ `due_occasions`（三闸）/ `mark_fired` / `due_notes` |
| 台账 | `last_seen_date` / `rewind_count` / **按角色分桶的 `fired`** |
| 入口 | `due_notes(char_id, world_dir)` —— 调一次 = 查表 + 记账 + 写盘 |

**⭐ 四条设计决定（都不要"顺手简化"掉, 踩过）**

1. **`year` 栏干两份活**：留空 = 每年一次（键 `christmas:2026`）; 写死 = 一辈子一次
   （键 `anniv:2027`）。一张表同时表达"每年"和"一次"
2. ~~**幂等键的年份必须是现实年**（因为她看到的是虚构年 2100）~~ ✅ **已消解**：
   虚构年 `FICTIONAL_YEAR = 2100` 于同日**删除**（用户裁决"既然时间同步了，
   FICTIONAL_YEAR 还有必要吗" → 直接删）。现在**键的年份 = 显示的年份 =
   `ts` 的年份**，三处同源；"两个不同年的圣诞在她眼里是同一个"这条后果消失
3. **台账按角色分桶**（世界级文件里存角色级的事）—— 否则遥香过完圣诞阿露收不到
4. **窗口 = "上次跟她说过话那天"**，`last_seen_date` 为空时窗口**为零**：
   - 用"一年以内"当窗口 → 12/25 那天四个节日**同时到期**（试出来的）
   - 空账本初始化成"今天" → **新档第一天收到元旦+情人节**（试出来的）

**⭐ 虚构年删除（2026-09-17，同批）**

| | 旧 | 新 |
|---|---|---|
| `phone_date_note` | `【手机上的日期】2100年9月13日（星期一）` | `【手机上的日期】2026年9月13日（星期日）` |
| 真实 `2/29` | 平移到 `3/1`（2100 非闰年） | **原样保留**（这是一次真实的行为变更） |

- 删除理由三条：① 它想防的（她嘴里的年份）是**破墙**问题，真防线是**归因**
  措辞不是那个数字；② 它**没有任何消费方**（不进 `det`/`age`/召回）；③ 换代后
  它成了**唯一不前进的年份**，而 `fired` 已按现实年记账 → 将来生日源（"我几岁"）
  必然对账
- ⚠️ **还纠正了一条我（助手）写错的说法**：我曾断言"2100 与真实年星期几差 1 天,
  所以 `nth_weekday` 必须按虚构年重算" —— **`phone_date` 本来就是按虚构年算
  星期几的**，她前后自洽。前提不成立，docstring 已改
- ⚠️ **归因那半句现在更承重**：原先还有"年份不重合"当第二道保险，现在她说的就是
  2026，全靠"这是手机上显示的"把它框在手机里

**✅ 已接进 MMT（2026-09-17）**

- **落点** = **每轮动态尾**（`round_messages` 的注记槽），**不是盒块** ——
  盒在 `start_session` **一次拼死、每轮逐字节复用**（前缀稳定），而节日注记只在
  那一天出现 ⇒ 进盒就会破缓存前缀。判据: **盒 = 会话级静态; 尾 = 每轮**
- `core/momotalk.py` 的 P17 块里、`time_notes` 之后调用
  `realtime_notes(char_id, store.world_dir())`，与 `time_notes` 同一个
  `try/except`（静默降级）; `char_id` 必须是 **slug**（台账按它分桶）
- ⚠️ **`agent_turn` 新增 `now` 形参**，三条注记**共用一个"现在"** —— 接线时探针
  抓到过"【手机上的日期】9月19日"与"（手机日历上标着：圣诞节）"同轮并存
  （`time_notes` 与 `realtime_notes` 各自读壁钟 ⇒ 一个 prompt 里两个时间事实，
  正是 `ESSAY §5.2` 那个坑的形状）。生产传 `None`（读壁钟），测试传钉死时刻
- ⚠️ **没变化就不写盘**：MMT 每轮调它，而节日只在少数日子点火 —— 每次
  `save_clock` 都是原子写（临时文件 + `replace`）。判据是"**值变了没有**"
  （`last_seen_date` 前进 / `rewind_count` / `fired` 多键），不是"今天是几号"
- 新增 9 例接线用例（`tests/core/test_momotalk_time_notes.py`）:
  进 messages / 与手机日期同源 / 说一次就不再说 / VN 不注 / 无 store 跳过

**待做**

- [ ] **birthday 源**（`OccasionSource` 扩展点已留）：现网 8 个 `profile.yml` 的
      `SIG~birthday` 有**三种写法**（`7/29` / `12月22日` / `5/13`）→ 要容错解析;
      幂等键用 `key`（8 人共用 `birthday` 这个 id）
- [x] ~~顺手清 `data/worlds/world1/world_clock.json`~~ ✅ 已删


### ⏳ 整章暂存：进真源的边界从 `vn_enter` 挪到 `vn_exit`（2026-09-17 用户立项 —— **必做，未动代码**）

> 一句话：**章内的一切先落暂存；看到 `vn_exit` 才整段 append 进 `events.jsonl`。**
> 动机（用户原话）：*"以后假如拒绝羁绊剧情，那么真源里就会出现不应该出现的东西。"*

**为什么该做**

- 现在进真源的边界是 **`vn_enter`**（`webgui/bond.py:1024-1033`）—— 玩家点进去之后的
  一切都落库，**包括中场退出、以及玩家没读完的部分**。
  `vn_abandon` 一族就是在给这个不该存在的边界打补丁。
- 挪到 `vn_exit` 之后，「段」从**约定**变成**结构事实** ——
  而这正是「段的日期 = 段尾」所需的前提（见上一条）。
- 它让「以后加"拒绝羁绊剧情"」变得安全。

**已经有一半在跑（有先例可循）**

| 旁路 | 文件 | 定位（代码里写着的） |
|---|---|---|
| staged 首场缓存 | `soul/prewarm.json` | "**非真源**——LLM 不读, 裁决才落库" |
| 草稿旁路（已生成未播放的板） | `soul/bond_draft.json` | 同上 |

⇒ 本项 = **把这两个特例推广到整章**。

**能做掉什么**

- [ ] `vn_abandon` marker + `abandon_open_attempts`（`webgui/bond.py:1041`）
- [ ] `exclude_abandoned`（恢复窗口过滤）
- [ ] `core/session/maintenance.py` 的 heal / supersede
- [ ] `replay_attempts` 按 `vn_enter` 分段回放
- [ ] 回忆册「只渲染 `vn_exit completed` 的章」从**查询条件**变成**结构事实**

**要实现的三件事**

- [ ] 暂存文件（建议 `data/worlds/{w}/characters/{c}/staging/chapter.jsonl`）——
      **每块 append 落盘**（不要在内存攒：崩了要能续上；可靠性必须与现在落真源**相同**）
- [ ] commit：见 `vn_exit` → 整段 append 进 `events.jsonl` → 删暂存
      ⚠️ **原子性**：搬迁中断 → 半截章回来。兜底 = 读时校验 `vn_enter…vn_exit` 闭合，
      不闭合的当不存在（或先写 `vn_pending` 再写内容）
- [ ] `session_status` 的 `in_vn` 改从**暂存**推（不再从真源 marker 栈推）

**必须同时改的一句话**

- [ ] `CLAUDE.md §0` / §5 的「**任何状态都能重建**」要改口径 →
      **真源记录「发生过的事」；暂存记录「正在发生的事」。
      重建的是已完成的状态 —— 因为没读完的章没有发生过。**

**⚠️ 顺带记一处现存的泄漏（与本项同源）**

- [ ] `webgui/bond.py:379`：视觉门**兜底的假 `nomal` / 假 `_place_done` 会随 `_log_scene`
      进 append-only 真源**，而"晚到的真标注再也回不去"。
      2026-09-13 审计 A6 修的是**触发频率**，不是泄漏本身。
      **整章暂存之后这个窗口自动闭合**（章没闭合就不落库）。

**架构论点（用户 2026-09-17，比动机更本质）**

> **缓存架构的真正优势是：「删除」变成了「丢弃」。**

| | 直接落真源 | 缓存/暂存 |
|---|---|---|
| 让一段内容"不进上下文" | **需要删除/遮断操作** —— `vn_abandon` 标记 + 每条读路径记得 `exclude_abandoned`。**漏一处就污染**，且遮断标记**自己也进真源** | **丢弃即可** —— 它从来没进过真源，**没有任何地方需要"记得过滤"** |

**三种结局，两种提交：**

```
章内（暂存 —— 什么都不进真源）
  ├─ 拒绝 / 从未进入   →  丢缓存                → 【从未发生】← 零删除操作
  ├─ 中途退出          →  vn_exit completed=False → 【发生过，但没读完】
  └─ 正常读完          →  vn_exit completed=True  → 【完整发生过】
```

**`vn_abandon` 一族之所以整个消失**：它存在的唯一理由是"真源里有**未闭合的段**"。
而缓存架构下，未闭合的段**只存在于暂存里** → 要么丢、要么以 `vn_exit` 提交
→ **真源里永远没有未闭合的段**。

**顺带一处语义修正**：现状把"中断"当 `vn_abandon`＝**宣告没发生过**；正确语义是
`vn_exit completed=False`＝**发生过但没读完** —— 她**确实经历了那半段**
（"玩家陪她到一半跑了"是有意义的叙事事件），而 abandon 把它删了。
`vn_exit` 的 payload **早就有 `completed` 字段**，数据结构不用改。
而且它与「记忆形成时刻 = 读完时刻」自洽：**进真源，但不进记忆**。

**"之前的缓存现在的职责不同了"**：`prewarm.json` / `bond_draft.json` 原本是
**性能优化**（跨重启首场缓存 / 待发板队列），新架构下它们**升格为暂存区的一部分**
—— 从"优化"变成"架构"。

**进度（2026-09-17）**

- [x] ✅ **地基**：`core/session/staging.py` —— `StagingStore` **继承** `SessionStore`；
      `commit_staging` / `discard_staging` / `close_open_attempts`；
      **overlay 语义**（2026-09-17 审计后升级）：`events()` = **真源 + 暂存**、
      `append_event()` 的 `seq` **接续真源**（`max(真源, 暂存)+1`）→ 合并天然有序、
      章外**逐字节等价于真源** ⇒ **读侧无需任何改动**（不会有"漏改一个读点"的幽灵）；
      `truth_store()` 保证 `commit_staging` 写真源（传 overlay 也安全）
      单测 13 例（含半截 commit 可重试 / 并发 seq 无重复）
- [x] ✅ **接线第一刀**：`bond_finish` 的 `vn_exit` 改走 `_stage_store(state)` +
      `commit_staging` —— **行为不变、数据路径变了**（752 个既有用例全绿即证明：
      若收尾条件写错，真源里会冒出两个 `vn_exit`，它们全会红）
- [x] ✅ **接线（章内读写口）**：`_flow_store(state)` → **overlay**（改这一行，
      5 处 `store = _flow_store(state)` 自动跟着变）；另补 3 处独立站点
      （`_pending_in_vn` / `_open_vn_seq` / `_last_bond_seq` 的缺省 fallback）；
      `_stage_store` 收敛为它的别名；`:1699` 的 `session_end` **故意仍写真源**
      （会话结束不属于章内容）
- [x] ✅ **测试迁移**：旧架构断言（"章内内容落在真源里"）**摘除 18 个**
      （`test_bond.py` 16 / `test_web_http.py` 2，AST 精确摘除）；
      新增 `tests/webgui/test_bond_staging.py` 3 例钉住新架构
      —— ⭐ **其中一例当场抓到 `_pending_in_vn` 漏改**（真 bug，已修）
- [ ] **CLI 路径同步**：`core/ui/vn_cli.py` ×7 写点仍走本地 `store`（真源）
- [ ] **`_log_scene` / `_log_scene_meta` 复核**：它们用 `store = _flow_store(state)`
      ⇒ 已自动走 overlay ✓（无需改动，但要确认行为）
- [ ] **语义修正**：中断 → `vn_exit completed=False` 替换
      `abandon_open_attempts` 的动作（`bond.py:1041`）
- [ ] **删死代码**：`maintenance.py` 整份 / `M_VN_ABANDON` / renderer + chapters 的
      abandon 分支 / 4 处 `exclude_abandoned`

**⚠️ 已写死的一条不变量（B-1 时踩到的坑）**

> `commit_staging` 的收尾**只在暂存自带 `vn_enter` 时才跑。**
>
> | 暂存内容 | 真源里那个未闭合段是谁 | 该不该收尾 |
> |---|---|---|
> | 自带 `vn_enter`（整章） | 必然是**旧的** | ✅ 收尾它 |
> | 不带（过渡期：只装本章尾巴） | **就是本章本身** | ❌ 收尾它 → 真源里两个 `vn_exit` + 本章被判成"没读完" |

### VN 契约形式换代（记录流 v2, 2026-09-10 设计整理——**P0–P2 已落地, 真机在跑**）

- 理论/分步规划/未决清单: **docs/DESIGN_VN_UPGRADE.md**
  （§11 分步规划 · §12 蓝图待决 14 问 · §13 决策记录 #1–#36 · **§14 渲染层设计稿=未实现**）
- 已归档旧 VN 文档: DESIGN_BOND_CONTRACT_V2 / DESIGN_CHOICE_PREGEN /
  DESIGN_SCENE_STREAM / DESIGN_BOND_STORY（→ docs/archive/）
- [x] **P0–P2 已落地**: 记录文法/行解析/板派生/待发板/草稿旁路、标注单元=记录、
      预热与预生成三层、渐进渲染流式、换场翻译、真机三轮体验修复（决策 #22–#35）
- [ ] **待用户**: 蓝图（planner）形态拍板（§12 A/B 组: 粒度·归属·时机·漂移）；
      **渲染层（多人同框站位/动作 #36, §14）暂缓实现——5 条待拍板见 §14.8**
- [ ] **未做**: P3 蓝图 planner · P4 生图异步完善（v2 memorial→生图重接线）

### 世界线语义定稿实施（core/DESIGN_WORLD.md §9, 2026-09-04 定稿——法则共享/历史固化/overlay 三层）

- [ ] **行为层现状核对**：config 单一真源实时读 = 定稿形态（无副本）——核对所有
      角色消费点是否"显式经过当前世界"（角色实例解析器: world_id+card_id → 基座+
      overlay+soul; 无 overlay 纯 config 查询零开销）; 消除隐式漂移（§9.2）
- [ ] **会话级内存快照**：会话开始时取一次基座进内存, 会话内固定——防中途改卡
      人格漂移（§9.3 哈希挂点 1）
- [ ] **世界注册表**：worlds/{w}/world.json（json）登记 roles 导入清单; 主世界默认 =
      mmt_registry 白名单; 运行时角色列表从注册表读（重开不重选, 新卡不进旧世界）;
      导入 = 显式实例化动作（§9.4）
- [ ] **哈希版本信号**：registry/overlay/出厂种子三个挂点记录基座哈希 → 变更冒泡
      （作者新版设定/记忆重整理/overlay 检查）（§9.3 哈希表）
- [ ] **overlay 承载形态**：per-world 差异文件（interperson/性格子集）——形态待用户
      （§9.6）; 出厂记忆"整理冒泡"随创建流程一起（§9.5）
- [ ] **待用户思考**: beliefs 出厂预置 vs 涌现 / 卡变体组织 / overlay 边界（§9.6）

### 出厂定稿管线 → **2026-09-05 转向: 运行时解耦**（出厂记忆不进 wiki）

> 调研定稿（Letta Memory Blocks / SillyTavern 卡 / 图记忆系）: 主流项目预置内容 =
> 直注上下文（persona 块/description）, LLM 扮演时自然内化; 图记忆只存运行时。
> experience.yml = 作者人设描述（与 personality 同性质）, 不是"待改编的记忆"。
> 改编链代码保留为可调用模块, **主进程不再使用**。

- [x] **运行时解耦已完成**（4290f3e + ece0747, 495 全过）: 主进程 seed_from_config
      调用全删（load_brain_segment/_inject_brain）——注入段 = 出厂背景
      （experience.yml 原文直注 cap 6: render_background_experience, 第三人称
      不转换——LLM 自然内化）+ 运行时 wiki（digest 产物）; world1 出厂残留已清
- [x] **预处理链归档**（5b44411, 471 全过）: seed 引擎/改编工具/prompt/brain_seed
      稿/beliefs 手册/对应测试 → archive/factory_memory/（git mv 保历史, README
      记录可复用资产: 记忆化重构规则/逐条调用模式/brain_seed 稿可作背景润色参考）
- [ ] **背景段实机效果验证**: 【背景经历】指引（"回忆过去以此为准/底色不必每轮提起"）
      在 bond/MMT 的表现——第三人称背景 LLM 自然内化是否成立（酒馆同款验证）;
      以及 cap 6 是否够（12 条只显前 6——作者可调 experience.yml 顺序）

**阶段 0 设计定稿** ✅
- [x] 0.1 出厂 = 一次定稿（brain_seed.yml）; seed = 确定性复制; digest 只处理玩家新记忆
- [x] 0.2 改编工具逐条调用 + 人设锚注入（profile/personality/称谓表）
- [x] 0.3 产物 = 初稿, 作者 review 后定稿; 工具防覆盖（--force 重跑）
- [x] 0.4 世界线创建时快照定稿输入进世界线（seed_snapshot/）——回退/重建与 config 解耦
- [x] 0.5 无 brain_seed 新角色 → 原文兜底（现逻辑）——可玩性永不阻塞

**阶段 1 prompt: llm/prompts/seed_digest.md** ✅（02460c8, 五连 commit）
- [x] 1.1 角色定位: 预设经历改编员（与 Round A 同协议: 第一人称/浓缩/不升华/verbatim 逐字）
- [x] 1.2 人设锚段: 角色档案/性格口吻/称谓表（{{占位符}} 文档化, 工具端渲染注入）
- [x] 1.3 单条输出规格: source_key/title/narration/verbatim/significance/author_notes
      （author_notes = 剥离的点评句, 空则省略）
- [x] 1.4 改编规则: 不增删原文事实/不发明细节/称谓按表/点评句不混入 narration/感受句可留
      + 示范对照（同一原文正例）
- [x] 1.5 输出纪律: 完整单条 JSON（工具端兼容 {"episodes": [...]} 数组态）, 不要代码块

**阶段 2 工具: tools/seed_digest.py** ✅（02d21e4, 七连 commit; git add -f 入库——tools/ 被 ignore）
- [x] 2.1 读卡: CharacterLoader 取 profile/personality; experience.yml 叶子（复用 _collect_leaves）
- [x] 2.2 称谓表渲染: knowledge.friends → 称谓行（供人设锚注入）
- [x] 2.3 逐条 LLM 改编: temp 低(0.3)/重试 ×2/单条失败记录不阻塞; task_levels 新增
      seed_digest 形态（medium/4096——有原文锚的转换任务, high 长考拖慢 12 条串行）
- [x] 2.4 解析校验: source_key 回填/必填非空/sig 0-1 硬错误; 第三人称残留/多余键软警告
- [x] 2.5 写 brain_seed.yml: episodes[] + review_notes[]; 已存在拒绝（--force 备份 .bak）
- [x] 2.6 CLI: --char/--dry/--only 单条重跑/--force; 进度/耗时/汇总提示

**阶段 3 引擎: seed.py** ✅（1052c56 + 1efdf05）
- [x] 3.1 brain_seed.yml 分支: episodes → make_node（narration/title/verbatim/sig
      逐条入档; source=experience 判重键与原文一致——中途补定稿不影响已有世界线）
- [x] 3.2 无 brain_seed → 原文兜底（现逻辑不动）——角色可玩性永不阻塞
- [x] 3.3 世界线创建快照: brain_seed/原文 yml + beliefs → worlds/{w}/characters/{c}/
      seed_snapshot/（首次 created 时写, 幂等不覆盖; 演练: config 模拟修改后快照保持原样）
- [x] 3.4 幂等/落盘沿用（source_key 判重 + save; created 时 save 根因修复保持）
- [x] 3.5 world1 遥香/佳代子重灌演练（原文兜底 12/4 条 + 快照写入验证）——
      **真实 brain_seed 重灌等 5.1 生成定稿后做（5.3）**
- [x] 3.6 momotalk.py 131/407 行 kind=="fact" 残留清理（恒 False 致每次 seed 空跑
      → is_seed() 判定; wiki 相关测试回归 21+26 过）

**阶段 4 测试** ✅（494 passed, +17 新增）
- [x] 4.1 brain_seed 分支: 全量映射（title/verbatim/sig/evolution 标记）/幂等/immutable/
      坏条目隔离/解析失败不回退原文（test_wiki_seed.py 追加 4 组）
- [x] 4.2 快照语义: 首建写入/原文兜底分支/不覆盖/config 改动世界线零变化/
      新世界线用新版（test_wiki_seed_snapshot.py 新文件 5 组）
- [x] 4.3 原文兜底回归: wiki 全组 108 过（haruka 真实目录 12 条原文映射不变）
- [x] 4.4 工具单测: tests/tools/test_seed_digest.py 8 组（fake LLM 注入/组装零占位符/
      校验硬软/重试跳过/写盘防覆盖 .bak——git add -f 入库, tests/tools 被 ignore）
- [x] 4.5 全量回归: 494 passed（477 + 17）

**阶段 5 真实执行（遥香）**（5.1 ✅ c10d5ae——5.2 起待用户）
- [x] 5.1 seed_digest.py --char igusa_haruka → brain_seed.yml 初稿（12/12 成功 ~4.5min;
      第一人称/title 全齐/2 verbatim/1 author_notes(regular.1 点评含"经典遥香思维"自注原样保留);
      忠实度抽查 main.1-3/valentine 与原文吻合; 原文 2281 字 → 改编 1857 字）
- [ ] 5.2 用户 review/手改（重点: 语气/自注/点评句去留; 已标 1 处措辞疑点:
      regular.1 "老师误解消息" vs "我误解"——原文主语含混, 作者定夺）→ 定稿
- [ ] 5.3 world1 重灌（删 wiki → brain_seed 重 seed）+ 渲染抽查（title 进组织视图/图谱）
- [ ] 5.4 review_notes → 用户写 beliefs.yml（素材已备: regular.1 点评句）
- [ ] 5.5 组织视图抽查（title/verbatim 展示）

**阶段 6 文档**
- [ ] 6.1 guidance/experience.md: 写作规范（档案语义/点评句留给 beliefs/改编工具说明）
- [ ] 6.2 AGENT_BRAIN.md 出厂管线段更新（定稿制 + 快照 + brain_seed 格式）
- [ ] 6.3 TODO.md 本表勾选

### 出厂 wiki 闭环（✅ 引擎全部落地, 9558287——剩内容创作）

- [x] **seed v3: beliefs.yml 解析**——出厂认知层（guidance/beliefs.md 已定稿）：
      subject/content/links（source_key 引用校验, 孤儿引用报错并列出可用键）/significance;
      belief 出厂**不 immutable**（运行时 digest 的 touch/update 要能挂新经历——认知基线演化）;
      遥香 beliefs.yml 内容待写（用户自己写或我起草——唯一剩余项）
- [x] **渲染段位修正**：出厂 episode（source=experience）→ "久远的记忆"段 cap 5;
      运行时 episode 独占珍贵/最近段（v3 落地, 真实渲染 1151 字 vs 旧 2576 字）
- [x] **fact 退役**（用户拍板, 9558287）：knowledge.yml 不再出厂化——"我知道的事" =
      世界观知识（overview.yml common 语义）→ 世界观知识库中期项（见下）; fact 语义
      已无消费方（knowledge 注入问题随之消解, 18 fact 不再注入）
- [x] **wiki 图谱可视化工具**：tools/wiki_viz.py（networkx PNG + mermaid 双输出;
      dev 依赖进 requirements-dev, 运行时仍 dict 邻接）
- [ ] **人称转换残余**（"她/自己"指代链混用——替换"遥香"→"我"后暴露）：
      渲染层保守启发式（先"自己→我"类无歧义项; "她"消解需谨慎——可能指 sensei）
- [ ] **出厂经历优先级表达**：12 条同 sig 0.9 → cap 5 恒显示 yml 前 5 条
      （现以作者书写顺序为准; 若需新_year/main 进窗口, 待定条目级 sig 标注）

### 上个 bug 修复的验证与遗留

- [ ] **bond 黑背景遗留确认**：标注/busy/竞态修复后重启重测——若仍黑, 查 director 背景
      映射或双前端错乱（见 29a4ea9 修复清单）
- [ ] **真机完整 bond 闭环验证 digest**：wiki 出厂落盘 + episode 化后, 跑完整剧情
      → digest 产 episode/belief + 注入刷新（此前 digest 从未成功闭环过）

### 中止语义修正（2026-09-09 用户拍板: 中断/异常 ≠ 失败/完成）✅ 引擎侧已落地

> 历史遗留: 生成失败超限曾 closing 伪收场（is_end+completed）→ 前端 1.6s 自动
> finish → vn_exit completed=True → digest + 完整收尾话/兜底落库——大量重复
> "好好记住"兜底话 + wiki 空的来源（从未自然完成）。

- [x] N_a 失败超限 = 中止态（completed 恒 False、不落结束事件、可重试/离开重进续写）; 篇幅超限强制 closing 删除, _system_note 每轮强制 story_end 注记
- [x] N_b 前端天然支持（showTurnError 重试按钮; 无 is_end 不触发自动 finish）; 中止文案简洁化（完整异常入 diag 日志 data/diag/live2be.log——诊断不进事件流）
- [x] N_c digest 触发面注释守卫（completed 只来自场景 is_end 自然收尾）
- [x] N_d CLI 失败收场对齐（72b2043）: 失败自动重试 ≤3 次, 超限/篇幅耗尽 = 中断退出（completed=False、不落 story_end、vn_exit False）——digest 只可能来自自然 story_end; 重进续写能力仍待 CLI resume 落地（见中期回放）
- [ ] 放弃本章/拒绝邀约（显式退出 UI + vn_abandon——未来扩展, 用户搁置）
- [ ] **见面式对话扩展（邀约, 预期未立项）**：docs/DESIGN_MEETUP.md——玩家显式
      发起（手机形态=发定位卡片）→ 纯对话不触发 memorial / 结束权在玩家 /
      意外中断≠BS（直接打终止符号, 不保留续写链）; 3s/回合前提已实测
      （v4-flash: off 0.66s / low 2.5s / high 2.2s, TTFT<200ms, 不需降档）
- [ ] replay 尾场 is_end → completed 置位口径核对（回放已完整结束剧情时的收尾/digest 语义）
- [x] 诊断日志落盘（5470f9f: data/diag/live2be.log, WARNING+ 旁路文件, 不进事件流）
- [x] **跨重启预热缓存**（soul/prewarm.json, 旁路非真源）: 首个落地场景即落盘,
      重启后 bond_start 命中（anchor=最新 mmt seq）→ 0 LLM 直出首场; adopt/finish/
      命中即删; 失配（触发后又聊/新触发轮）→ 现场生成并重新落盘; demo 不写;
      首场重试成功同样落盘（first_scene 判据）; 测试 4 组绿
- [ ] 预热缓存后续: adopt 已落 vn_enter 但首场未裁决就重启（回放空→现场生成,
      v1 接受）; 候选支/预生成持久化同机制评估; 多实例同 data 原子写实测

## 短期（体验闭环 / 明确小项）

- [ ] **mmt 圆括号剥离误伤（未来优化）**：`_strip_action_brackets` 剥全部 （）/() 内容——
      "哼，我才不理你呢(ps: 快安慰我)" 会被肘击; 需语义判断/白名单/人设开关
      （代码注释自认边界: "喜欢在聊天里发括号的人设…等我改逻辑"; 方括号 [] 安全不剥）

- [x] **MMT 协议终稿（消息流 messages）**：`{"messages": [{text|action}…]}` 任意交错——
      话→图→话 微信节奏; 动作外壳 {action,payload}（summary/reply/operation 全清）;
      旧协议保序归一 ✅ 469→471 passed
- [x] **MMT 触发节奏 v2**：引擎硬闸（不足 6 轮拒 trigger）删除——玩家遇险尬聊是硬拒的
      伪正确; 建议不拦截, SUGGEST_BOND_ROUNDS=6 注记分级提示, 触发权全交 LLM
- [x] **thinking level + max_tokens 集中管理**：llm/task_levels.py 唯一真源
      （main=default / emotion=off / digest=high; 六形态 max_tokens; settings [llm.tasks] 覆盖）
- [x] **wiki 重复 append 根因修复**：seed add 不 save → wiki.jsonl 恒空 → 每次触发重 seed;
      修复后真实数据清理 + 落盘验证 ✅
- [x] **出厂 digest v2**：experience.yml → episode（与 bond digest 产物同构, 用户拍板
      "预设记忆 = 角色记得的经历"）; knowledge → fact 不变; is_seed 扩展; v1 fact 自动迁移
- [x] **bond 表情卡 default + 无限 3 点加载修复**：标注调用关 reasoning（extra_body={}）+
      max_tokens 512; 分支路径同步等标注; _generate/_pregenerate 原子抢占; 前端重试上限
- [x] **问题 1 断句权移交**：切分器（jieba 碎句合并/块保护/句界）引擎化; 契约自然段语义;
      标注层唯一真源 + robust 二分降级 + character 注入; 推进门控（情绪未到位不可推进）
- [x] **问题 2 选项失灵**：send_vn_scene max_tokens 1536→8192（high reasoning 截断根因）;
      busy 标志 finally 恒复位; 门控兜底 fill 恒可达
- [x] **问题 3 轮数机制**：rounds_since_bond 持久（worlds progress.json 语义修正）;
      vn_exit completed 清零 / 中途退出保留（v2 后降级为建议线基准）
- [x] **guidance 目录建立**：README（五问心智模型）+ beliefs.md 完整写作指导
      （字段规格/source_key 规则/范例/反面例子/LLM 自查清单）
- [ ] **背景选择逻辑加速**：Director.visual_for 每场 `set(catalog.background_scenes())`
      全量重排（620 场景 O(n log n)）→ catalog 缓存 frozenset 一次构建; 顺带查
      background_scenes_in_dir 按需扫是否可预索引
- [ ] **bond_finish 收尾等标注的 8s 同步等待** → 后台化（当前阻塞 finish 请求线程;
      标注修复后 ~1-3s, 可接受但可优化）

### 选项等待减少 + 标注链路稳定（2026-09-08 立项候选, 未排期）

> 背景: SceneStream P1 真 API 实测（5 轮, experiments/p1_text_annotate_real.py）——
> 标注已收敛到「text + 编号映射 + 宽松解析 + 重试预算 3」(b12eb53); 今晚服务端
> 负载期空响应污染数据, 验收数字等空闲复测。选项等待现状: 分支直显零等待 +
> 分支播放期预生成, 剩余等待 ≈ max(0, 下一板生成 − 分支播放)。

- [x] **A. 预生成/纯推进板 low reasoning**——**用户否决（2026-09-08）**: 现网 API
       必须 high 才有正常文风（低思考 AI 味浓）, 创作档不可降; 选项等待改走
       D（P2 流式）为主 + 分支预生成已覆盖的窗口内就绪。放弃降档路线
- [ ] **B. 追赶降档**：预生成落后时先 low 出一版上屏, 后台 high 替换——双生成
       复杂度, 仅极端慢期值得, 暂缓
- [x] **C. 选项候选预生成（sibling 草稿支, 用户方案）**：已落地 master（N1 fork
       原语 + N2a spawn / N2b 消费切换 / N2c 清理观测 / N2d 开关, 489 绿）——
       板带 choices → fork 候选支（A1 按路径回录）各自预生成下一板; 裁决命中
       即端上（零等待, 未命中走老路）; 未选作废 GC（草稿纯内存零落库）。
       成本实测: 双路 prompt 近全量缓存（miss 262-1072 vs hit ~6.2k）, 增量
       ≈ 1 候选支输出; 设计/落地记录 docs/archive/DESIGN_CHOICE_PREGEN.md（已归档）; 开关
       settings.toml [bond] choice_pregen（缺省 sibling; tree 预留不做）;
       **待真机验证**: 选项命中 0 等待率 / 候选墙钟并发实测; ~~分歧感规则测试
       授权~~ 已撤销（2026-09-10 收敛终局定稿——VN 不做分歧感, 自由度移交
       邀约扩展 DESIGN_MEETUP.md）
- [ ] **D. P2 流式渐进（段闭合即发布）**：选项/继续等待的终态解——TTFT+首段即读;
       见 docs/archive/DESIGN_SCENE_STREAM §2/§10（已归档; 记录流 v2 见
       docs/DESIGN_VN_UPGRADE.md §11.3）
- [ ] **E. 空闲时段复测 P1 验收**：兜底句数≈0 / 重试率 / 单段耗时 p50
       （`P1_MAX_BOARDS=6` 全量; 今晚负载噪声不可信）
- [ ] **F. client json_object 空 raw 快速失败短路**：空响应根因已除（thinking
       disabled, 见 G）——此短路变为纯防御性加固, 优先级降; 若仍要: raw 空 →
       跳过两次 LLM 自纠错直接交上层重试
- [x] **G. 档位语义修正（2026-09-08, 已落地）**：emotion/place "off" = 显式传
       `{"thinking":{"type":"disabled"}}`（此前实现"不传参数"= DeepSeek 默认
       思考开、reasoning 计入 max_tokens → 空 content, DeepSeek-V3#1610 同型;
       disabled 后标注 4/4 一次通过、单段 0.5-2.4s）——task_levels.py 注释与
       实现已更新 + 单测对齐
- [ ] **H. MMT 空 reply/直触发复现追踪**：12 轮高/低探针 0 空 0 触发、completion
       tokens 27-1126 远低于 4096 → 判为服务端偶发窗口而非档位; 复现时抓
       `llm chat ms=…` + usage + raw（探针 .testtmp/probe_mmt_effort.py 可复用）
- [ ] **I. 每板档位表拍板**（候选: low = wrapup/纯叙事续写预生成/MMT 闲聊;
       high = 选项板/触发轮——~~自由输入板~~ 2026-09-10 锁死撤销, 自由度移交 DESIGN_MEETUP）——A 的决策前提, 待用户

### 标注层「两层解析」+ 主 LLM 去词表（2026-09-15 立项讨论——**未动代码**）

> 方向（用户裁决）: **主 LLM 零词表**（输出契约枚举除外）——
> `lexicon_emotion` 已因同样理由退出盒B（决策 #24: "词表注入对创作不再起作用,
> 且其提醒属白熊效应"）; **`place_palette` 是盒B 里最后一块词表**。
> 词表统一归标注层, 由标注层做「自由文本 → 键」。

- [x] **`place_palette` 退出盒B**（2026-09-15 T16 已落地 `20bf757`）——
      ⚠️ **原地换块, 不是删块**: `place_palette` → `place_world`, 盒B 仍是 **9 块**
      （原计划"9→8"是记错了）; 黄金夹具已刷。
      **它不是"防背景单调"的正解**: 想解决的是"writer 不敢换场", 而正确手段是
      **一条规则 + 一个动作**（`switch` 已经有了）——给菜单是**用错的手段做同一件事**,
      且菜单是**猜**需求、`[place][MISS]` 日志是**测**需求
- [ ] **switch 并入 place lane**: 现在 `resolve_place`（首记录是 `switch`）与
      `annotate_places`（句级锚点）**二选一 + 早返回**（`bond_story.py:1115-1136`）
      ——合成一条路; `current_place` 延续态跟着搬
- [ ] **接 tempo 导出表**: `_place_entities.json`（**168 条 active**, 2026-09-17）
      替换 31 条裸 slug —— **层1 `keywords` 别名精确命中（0 调用）+ 层2 LLM 解析**。
      `resolve_place` docstring 自称「P1-2 会用 tempo 导出视图替换词表」。
      ⚠️ 表当前**缺三样**才能当标注语料用（`DESIGN_PLACE.md §6` 差距表）:
      ① `note`（245/246 条有值, 作者写的用途说明）**不进导出** —— 而它才是
      "这个地点适合什么戏"的判据; ② 导出**外层键仍是自动族键 `root`**, 与
      `place` 不等者 **103/168**; ③ 键名统一为 `place`（2026-09-19 用户裁决,
      依据 `place_studio._migrate_export_entry`）
- [x] **导出外层键收口到 `place`**（A1, 2026-09-19 已在 tempo 侧落地）:
      `api_export` 改为按 `_place_of(item, rv)` 建键（作者手写 `place` →
      `place_default` → `root`），旧文件读取时就地重建键（键变了不能被 scope
      切碎）; 连带 `_do_export.py` / `_probe_tables4.py` 的对账口径。
      实测: 168→168 条、**103 条键被换写成 place 形式、行内容 0 差异**、
      外层键 == 行内 `place` 168/168、作者手写 place **168/168**（`place_default`
      回落从未生效）、`place` 无重名。
      ⚠️ 顺带堵了一个**旧的静默失败**: 两个组算出同一个键时此前是
      `merged[k] = …` **静默覆盖**（丢一整组图），现在撞车 → 不写盘 + 报出两个组
### 标注层模型定稿（2026-09-19 用户澄清 —— **表外不是缺陷路径**）

> *"writer 当然可以说表外，为什么不能，writer 的自由不受限制，这个设计就是给
> writer 最大自由防止注意力矩阵稀疏；背后的 annotation-llm 只要看到 `note` 就能
> 大致推测出地点，这就可以了，而且关键地点还能给它当作注记注入 anno-llm，更加
> 方便。"* … *"主 LLM 有部分词表，这个词表比较特殊，是某些特效比如说 `black`
> 或者`星空`这种词，这是因为这些词能让 LLM 更好的写作。"*

- [x] **写作用词表已在表里**（复核）: `sdir=SDIR_Atmosphere` 且 active 的 4 条
      = `view_sky`(星空/夜空/黄昏) · `black`(纯黑/黑屏) · `view_constellation`
      (流星雨/繁星) · `view_dawnsky`(黄昏云彩)。`red`/`white`/`black_effect` 已填
      但**未 active**（作者判定"engine 会处理"）→ 词表判据 = **表自带的 `sdir`**,
      不另立名单（符合"动态读入"）
- [ ] **⚠️ 现役 prompt 与模型相反, 必修**: `place_resolve.md` 写"词表里没有能对上
      → `{"place":""}`（**宁可空着，不要硬凑一个近似的**）"、`place_annotate.md`
      写"拿不准 → 不标" —— 而模型要的是**读 `note` 就近推测**。
      真机 `杂草屋 → school_rooftop` 就是这个矛盾的产物：**只给了 31 条裸 slug,
      没有 note**，模型只能瞎猜。改法 = 层2 prompt 换成整表（含 `note`）+
      指令改成"选语义最近的一个"；只有"与当前地点相同"仍走 `""`。
      改动在**标注 prompt**（不进盒 → 无 promptkit 夹具影响）
- [x] **A2 `keywords` 分隔符已修**（2026-09-19, tempo 侧）: 新增
      `_split_keywords()`（`, ， / | 、 ; ；` + 空白一起拆, 去重保序, 绝不抛）,
      `api_export` 与 UI placeholder 同修。实测 **单元素整串 71 → 0**,
      别名总数 168 → **260**（平均 1.55 / 最多 4 / 97 条仍只有单个别名）
- [x] **A3 `note` 进导出**（2026-09-19）: 实测 **167/168 有 note**
      （唯一空的是 `family_restaurant`）。重导幂等（再跑 0 变化）
- [x] **`杂草屋` 不是 `abandoned_warehouse`**（用户 2026-09-19 裁决）:
      那个是**房子外部**，不是正主 ⇒ 不勾它、不追这条。
      用户同时给了更新机制的定性: *"想要直接更改为 active: true 就好，这不就是
      我之前说的支持更新吗？"* ⇒ **表更新 = 翻 `active`**（工具 + 动态读入已就位），
      不需要为某一个地点单独立项
- [x] **`PlaceRetriever` 接线**: `core/rag/place.py` 已经就是「精确兜底 + 语义兜底」
      两层, 但**生产零调用**（只 `experiments/rag_test.py` 用）; 且它读 `places.yml`
      （中英日别名）与 `resolve_place` 的裸 slug **互不相识** → 词表统一时收口
      （C1 的 `keywords` 正是它缺的语料 —— 很可能直接由 `place_table` 取代）
      → **✅ 语料收口已做（PL4 2026-09-19）**: 语料 = 表（168 键/428 别名）,
      `places.yml` 删; 返回**表键**。**接线仍未做**（等召回策略, 与 PL5 同批看）
- [x] **固定路径收成宏 + 可 grep 全量定位**（2026-09-19 用户裁决）: 新增
      `core/paths.py`（**20 条路径的唯一清单**, 顶层平铺, 只依赖 pathlib 无环）;
      `core/ webgui/ llm/ contract/` 里 23 处现拼路径全部改为 `paths.XXX`;
      `tests/core/test_paths.py` 4 例守门（`__all__`↔常量一一对应 / 全绝对且在根下 /
      **零现拼项目根路径** / 依赖只有 pathlib）。哨兵已验证会红。
      全量定位: `grep -n "^[A-Z][A-Z_]* = " core/paths.py` +
      `grep -rn "paths\.[A-Z]"`。约定写进 `CLAUDE.md §12`。
- [x] **C1 `core/media/place_table.py` 已落地**（2026-09-19, **纯新增, 零行为变化**）:
      `PlaceEntry` + `PlaceTable`（`resolve_exact` 层1 / `lexicon_text` 层2 含 note /
      `writing_words` 按 `sdir` / `by_region`）+ `load_table`（**mtime 缓存**;
      缺/坏 → 空表绝不抛; 坏条目逐条丢弃）。表落位
      `config/settings/world/place_entities.json`（与 regions.yml/places.yml 同目录,
      入库可 diff）。12 例单测（含「外层键 == place」「mtime 缓存真重读」两条哨兵）。
      实测层1: `教室`→classroom ✔ · `街角的咖啡馆，靠窗的位子`→moderncafe ✔
      （两条在 31 条裸 slug 时代全 MISS）· `学校天台`→school_rooftop ✔ ·
      `天台`→歧义 3 条（交层2）· `杂草屋`类→未命中（交层2 读 note）。
      层2 词表体量 = 整表 7022 字符（≈3.5k tokens, **只在层2 调用时付**）
- [x] **C2/C3/C4 接线完成**（2026-09-19）: 引擎默认吃表（表坏才回落旧白名单）;
      `resolve_place` 接**层1（别名 0 调用）**，歧义不猜下沉层2; 层2 词表换成
      **整表含 `note`**（按 sdir 分组）; 两个标注 prompt 去掉"宁可空着/拿不准不标"
      这条**第一版遗老**，改成"编剧自由写 → 读 note 挑语义最近的一张"。
      ⚠️ 键集真源仍是 `place_keys`——层1 结果必须落在它里面（收窄时不越界）
- [x] **C5 图能落地**（2026-09-19, **不接这步表键一张图都查不到**）:
      表键（`classroom`）≠ 资产 scene_id（`class_room`）→ `PlaceEntry.scene_id()`
      从 `files` 文件名派生; 引擎 `_place_scene_id()` 喂导演（否则 `visual_for` 的
      `place in background_scenes` 闸门静默拦住一切 = 真机 20/20 板 `neutral`）;
      路由 `_place_bg_url()` 表键→scene_id→catalog→URL。
      实测全部出真 URL（含重命名条目 `68office→kohshinjo_room`）
- [x] **M3: 记忆里带上地点**（2026-09-19, 用户: *"先加上 M3 记忆里带地点"*）:

      | 项 | 落地 |
      |---|---|
      | `BrainNode.place: list[str]` | **地点键序列**（素材轴）; 进 `to_dict`/`from_dict`（往返由 `test_every_serialized_field_is_parsed_back` 钉住） |
      | `BrainNode.place_raw: list[str]` | **writer 原文序列**（叙事轴, 2026-09-19 用户指出"二者缺一不可"后补落）—— 键不是地名的双射, 判"同地"只能靠它做语义 |
      | ~~`BrainNode.region`~~ | **已撤**（用户 2026-09-19: *"只是用于判定在哪个学院的…基本没有太多作用，也不必落库"*）。它还是**派生视图**（`place_hint` → `regions.yml` 归一, 随时可从事件流重算）⇒ 落库 = 冗余的第二真源。真正用处仍在盒B【世界区域】块（T16）+ 未来地点体系 |
      | digest 物化 | `_place_shape()` / `_place_raw()` —— 照 `_emotion_shape` 那一手, 按 `event_seq` 取 `payload.place`（+`paragraphs[*].place`）与 `payload.place_hint`, **相邻去重保序**; **0 LLM** |
      | C 链路 | `PlaceGate.gather` **不再是 stub**: 准入 = 键相等（等值, 无阈值）; 语义轴**只给已准入的命中打分**（不参与准入） |

      **用户问"带的是 key 还是 writer 的本名" → 带 key。** 理由: C 链路比的是
      **相等**, 而「放学后的教室」/「教室里」/「回到教室」是同一张图、三个字符串,
      拿本名做等值分组是废的。**本名不落节点** —— 它在事件流里
      （`payload.place_hint` + 锚点句原文）, `event_seq` 指得到, 将来表改名要重解析
      时按指针回捞即可（同 `verbatim_seq` 的纪律: 地址永久有效）。
      不存本名的另一条理由: 那会是一个**没人消费的新字段** —— 正是前几天
      清掉三份孤儿产物的同一把尺子。

      ⭐ 真机闭环（`experiments/place_switch_real.py` 末段）: 真实 payload 物化得
      `node.place = ['classroom', 'school_rooftop']` ·
      `node.place_raw = ['格黑娜学院·放学后的教室', '傍晚的学校天台']`。
      ⚠️ **旧档没有地点**: M3 之前的事件 `payload.place` 全是空（正是本次修的 bug）,
      所以现网存量 episode 的 `place` 恒 `[]` —— 要等新章。
- [x] **素材缺失 → 黑屏 + 报出**（用户 2026-09-19 裁决: *"假如发现资源库里没有这张图，
      就用黑屏 black，且 alert/console.log 素材未找到即可"*；*"key 是不可改的"*）:
      此前是**静默换成别的图**（`_fallback_bg_url()` → `class_room`）—— 真机那
      20/20 板"每次 VN 都在显示教室"就是这么来的: **看起来正常, 其实错了**。
      现在 `webgui/routers/bond.py::_place_bg()` 返回 `(url, 状态)`,
      缺素材 → `missing_asset` 随场景下发 + `background_url` = **黑屏 `black`**;
      前端 `bond.js::reportMissingAsset` → `console.error` + 每 key 一次 `alert`。
      板级与锚点级都覆盖（板级独立于导演的"保持上一场", 所以不会被上一张图掩盖）。
      测试 799 通过（+1）; `node --check` 过。
      ⚠️ **待定: 「重复键名」怎么办**（用户: *"不过重复键名有点头疼"*）——
      key 不可改已定; 批量替换改名事件流是可行操作, 但**两个旧 key 撞成一个新名**
      是不可逆的信息合并, 未定策略
- [ ] **「AI 判过的地点映射」旁路 / 回灌 anno-llm —— 用户 2026-09-19: "先不干，
      把主要的弄完再说"**（评估已做完, 记在这里免得忘）:
      用户原话: *"有没有必要把 AI 已经拍板过的部分地点映射表直接做成一个旁路/
      回灌入 anno-llm??"*
      · 配对**已经在事件流里**（每板 `place_hint` 原文 + 解出的 `place`）→ 聚合即可,
        像 `emo_shape`/`place` 那样是**可重建的物化视图**, 不是第三份真源
      · 收益三条: ① 层1 命中率随使用自涨（省调用）② 同一句话永远同一个答案
        （治实测到的"层2 两跑两样"）③ 把攒下的配对当 few-shot 回灌 anno-llm
      · 风险一条: **把错判固化**（真机上真发生过 `杂草屋 → school_rooftop`）。
        ⇒ 必须有优先级: **作者手写 `keywords` > AI 累积旁路 > 层2 现判**;
        且旁路只对"当前表里还存在、且没被作者改过"的键生效（表更新即失效）
      · 这其实就是最初那句"**地点重复**"通道的落地形态
      - [ ] ⭐ **核心设计约束（用户 2026-09-19 澄清后补记）**: *"一名对两 key 只会出现
            在之后要做到已选择的地名回灌"* —— 即**"重复键名"这件事的真身不在表里,
            而在回灌表里**。因为**同一句 writer 原话在事件流里可能被解成过不同的 key**
            （实测: 「傍晚的杂草坡道」两跑分别落 `ruinschoolcorridor` / `forestroad`）。
            ⇒ 回灌表天生是 **`原话 → [key 分布]`**（many-to-many）, **不是一张能直读
            的表**; 用它时必须先定**消歧规则**（最高频？最近一次？与 `keywords` 谁优先？）。
            这也正是"先不干"的实质理由: **它不是缓存, 是个小决策系统**
- [x] **`docs/AI_BRIEF_PLACE.md`**（用户 2026-09-19 要求: *"把文档中误导你的重写成
      你理解的语言，不必过于专业，你看的懂就行，这个是给你看的"*）:
      给 AI 看的防坑速查 + **"会带偏你的旧话"逐条清单**（DESIGN_PLACE §1③/§5 作废、
      `time_of_day` 不存在、place_regions 旧"C 链路吃 region"、CLAUDE.md 旧词表来源…）。
      同时就地改正三处最误导的: `DESIGN_PLACE §1③/§5` 加删除线、`place_regions.py`
      docstring 重写（含旧说法纠正表）、`CLAUDE.md §3.3/§4/§10` 的词表来源。
- [ ] **★★ 地名 ≠ key（用户 2026-09-19 指出）—— 判"同地"的路只有两条, 待裁**:

      用户原话: *"key 名不一定能代表实际含义？杂草屋和破房子两个地方可以对应
      同一个 key；也就是真实地名和 key 大概率并不是一个双射。"*
      **实测证实, 两个方向都在表里活着**（`.testtmp/probe_place_bijection.py`）:

      | 方向 | 实例 | 后果 |
      |---|---|---|
      | **一键多义**（假阳性） | `ruinschoolcorridor` 的 note 自己写着 *"学校走廊废墟,青苔遍地,**也可以用做老屋子或者某种杂草秘密基地**"* | 真·走廊废墟与杂草屋两条记忆**同键** → C 判成"同图" |
      | **一地多键**（假阴性） | 别名 `天台` → 3 个键（`school_rooftop`/`rooftop`/`building_roof_top`） | 都在天台却**不同键** |
      | 无从消歧 | 9 条 note 自称"通用/也可以用作", 其中 **8 条 region 未知**; 全表 region 只有 **20/168** 非空 | 两个轴都救不了 |

      ⚠️ **已做的更正**（语义, 非结构）: `node.place` 的 docstring 与 C 链路的
      `by` 字段改成 **`same_image` / `same_area`** —— **不再写"同地"**。
      `place` 键相等只声称"**同一张图**"。

      **为什么推不出来**: 一地多键的知识（**两张不同的图代表同一个叙事地点**）
      不在资产结构里 —— key / `dir` / `region` 的任何组合都推不出来, 它只存在于
      语言侧。⇒ 判"同地"必须引入**叙事身份**, 两条路:

      - [ ] **路 A（短期, 不建表）**: 落 **`node.place_raw`（writer 原文序列）**
            + C 链路加**语义轴**: `place_raw` 做 embedding 相似（与 `D` 链路拿
            `narration` 做向量同一手）。优点: 「放学后的教室」≈「教室里」判同地、
            「走廊废墟」≉「杂草屋」判不同地 —— **两个失败方向一起治**。
            代价: 一个 embed 调用; 且相似度要阈值（宁缺勿错 → 高阈值）。
            ⚠️ 注意这**推翻我上一轮"本名不落节点"的结论** —— 那个结论只在
            "判据 = 等值" 时成立; 判据换成语义, 原文就是必要输入
      - [ ] **路 B（随 v3）**: **地点实体表**（真实地名 → entity）——即
            `DESIGN_WIKI_V3 §2` 的 entity 中心模型。`episode --at--> place_entity`,
            判据 = 实体相同。作者打表最准, 但要维护第三份表
      - [x] **路 A 的合规版本已落地**（2026-09-19）: `node.place_raw`（writer 原文
            序列, digest 按 `event_seq` 物化 `payload.place_hint`）+
            `ctx.place_raw_now` + C 链路**语义打分**。
            ⚠️ **语义轴只打分, 不参与准入** —— 准入靠语义就得有阈值, 而
            `test_no_threshold_knobs_left` 钉着 T17 裁决"配置面不许有阈值旋钮"。
            于是现在的形态: `same_image` 高 `sem` = 真同地; `same_image` 低 `sem`
            = **素材复用（假阳性可见, 不被隐藏）**; 语义高的排前面（排序全量参与）。
      - [x] ⭐ **核实并钉住: key / place_raw 都不进 LLM 上下文**（2026-09-19,
            用户反问 *"我为什么要把 key 字段给到 LLM 的记忆？喂给 llm 的时候我直接
            丢掉这个字段不就行了？"*）: 查证 `render.py` 的四个视图只读
            `narration/verbatim/content/pattern/examples/subject/growth/count/
            links/contradictions/significance/ts/observer` —— **从读 `place`**。
            已把 `test_recall_side_fields_never_reach_llm` 扩到 `place`/`place_raw`
            （**哨兵验过会红**: 临时注入 `str(node.place_raw)` → FAILED, 还原 → 绿）。
      - [ ] ⏸ **假阴性三条路（甲/乙/丙）—— 降级为备忘, 现在不做**
            （2026-09-19 用户反问后重估）:
            · 键分错组**只影响召回排序**, 不产生"错内容进上下文"（key 根本不进
              LLM, 已核实）; 被选中的记忆正文本身也不自相矛盾（"她在走廊废墟里找到
              我"放在杂草屋场景里读, 就是一段往事）
            · 而且 **C 链路压根没通电**（`get_channel(...).gather(...)` 全库只在
              测试里出现）⇒ 现在为它标定阈值 / 建实体表 = 给还没接上的零件做精密标定
            ⇒ 等 C 真通电、真出现召回质量问题时再拿出来。
            届时三条路仍是: (甲) 破例开阈值 / (乙) 用 `sim_k` 改"取前 N 条" /
            (丙) 地点实体表（= 路 B / v3）
- [ ] **C 链路仍未接线到运行时**: `Channel.gather` 至今**没有生产调用方**
      （V3-0 只落了台账）—— 链路本身通了、数据也有了, 但"谁在什么时候调它"
      还没做。这是 V3-3 的事
- [x] **C6 `switch` 并入 place lane**（2026-09-19）: `fill_scene_places` 不再
      "二选一 + 早返回" —— ① 板首 `switch` → 板级地点（权威）② 句级锚点覆盖
      **板内后续换场**（switch 板也跑）。`switch` 记录不在 `paragraphs` 里
      （`from_board` 跳过 STAGE_SWITCH）→ 两步不会撞车; `current_place` 顺序顺延。
      代价 = 每板恒定一次 `annotate_places`（层1 让 ① 免费; 真机 0.5s, 异步不挡玩家）
- [x] **⭐ 真机复测换场: 通了**（2026-09-19, `experiments/place_switch_real.py`,
      真 LLM + 真导演 + 真 catalog, 不写事件流）:

      ```
      种子「…她提议带老师去学校天台看看」
      板1 switch '放学后的教室'   → classroom      → class_room      图存在=True
      板4 switch '傍晚的学校天台' → school_rooftop → school_rooftop  图存在=True
      背景序列: [class_room ×3, school_rooftop ×3]   ← **背景真的切了**
      换场 2 次: 解出 2 / MISS 0; 地点调用 6 次 均 0.48s
      ```

      对照接线前的真机症状: **3/3 MISS、board 级 place 0 条、记录级锚点 0 条、
      每板 `background=neutral` → 展示兜底成 class_room（每次 VN 都在显示教室）**。
      另跑 8 板常规种子（全程在教室）: 换场 1/1 解出, 背景恒 `class_room` 真图,
      `neutral` **一次都没出现**。
- [ ] **句级锚点真机频率 ≈ 0（已观测, 不是缺陷）**: 两次真机跑（14 板）锚点 0 条
      —— writer 换场**都发了 `switch`**（这正是 rules 要的"换场即发"）。
      锚点是**兜底**（writer 漏发 switch 时救画面）; 其正确性已由合成板验证
      （`place_resolve_real.py` §③: 6 句板只锚「推开天台的门」那一句）。
      真要它常出场 = 让 writer 少发 switch, 但那会丢板边界, 不值得
- [x] **C2–C5 真机验收通过**（2026-09-19, 真 API 跑
      `experiments/place_resolve_real.py`）:

      | 段 | 结果 |
      |---|---|
      | 层1（0 调用） | 18 条里 4 条独占命中 —— 那个列表**故意装满难题**; 生产/示例那几条（`教室`/`街角的咖啡馆，靠窗的位子`/`星空`/`流星雨的夜空`）全中 |
      | 层2（真 API） | **✔10 / ✗0**（人判期望）+ 3 条非地点**全部正确给空**（第二天早上/她沉默/雨停了） |
      | 句级锚点 | 6 句板 + current=`classroom` → **只锚第 4 句**（「…推开天台的门。」）→ `school_rooftop`; 第 3 句"跑出去"没锚（到达地未命名）、第 1 句与当前同地没锚 —— **判得准** |
      | 性能 | 层2 单次 **0.4–0.7s**（均 0.5s）; 层2 prompt 7022 字符 / annotate 8046 字符 |

      ⭐ **`note` 确实被读进去了**（决定性证据）: 「天台的护栏边」→ `rooftop`
      —— 三条天台候选里只有它的 note 写着"**有护栏**"。
- [ ] **⭐ 表缺口会当场显形**: 「废弃的琴房」的正主 `ruinpianoroom`
      （review 里 kw=`废弃琴房`、note 都写好了）**没勾 active** → 模型只能落到
      `practiceroom`（乐队练习室）。与 `abandoned_warehouse` 同一类。修法 = 翻
      `active`（用户: "想要直接更改为 active: true 就好，这不就是支持更新吗"）
- [ ] **层2 是"判断"不是"查表"**（已观测）: 同一句话两跑可能落到不同但都说得通的
      条目 —— 「傍晚的杂草坡道」首跑 `ruinschoolcorridor`、二跑 `forestroad`
      （后者 note: *"森林中的小路,有人可能会在这里找花朵或者杂草"*）。
      温度 0.2 下的正常抖动, 符合用户"**大致**推测出地点就可以了"的标准;
      要更稳就得靠层1 补别名（作者侧），别指望 prompt
- [ ] **层2 词表体量优化**（7022 字符/次）: 层1 命中即 0 调用; 未命中才付。
      若要再压: 按 region 取子集 / 只对"有 note 才有区分度"的条目带 note。
      与 C6（`switch` 并入 place lane, 减少每板调用）同批看
- [ ] **`place` = 数组**: `BrainNode.place: list[str]`（digest 按 `event_seq` 物化,
      同 `emo_shape` 的做法）, **原文与键并存**——两根轴: 键 = 视觉/素材,
      原文 + `region` = 叙事
- [ ] **⚠️ 同键不同义（用户 2026-09-15 提醒）**: `place` 字段里混着两类键——
      `default_place()` 派生的**文件名 slug**（描述资产）与**作者手写语义键**
      （描述地点）, 且**无从判别是哪一种**。后果两个方向都有:
      ① 一键多义（`class_room` 同时服务阿拜多斯/格黑娜教室 → 求交**假阳性**）
      ② 一地多键（`DIR_ViewSora` 下 `view_sky`/`view_constellation`/`view_dawnsky`
      → 求交**假阴性**）。**结论: C 链路的"同地"判据默认不吃 `place` 键**,
      走 `region`（剧情地理, 独立轴）+ 原短语; `place` 键相等只声称"**同素材**"。
      `SDIR_Atmosphere`（黑场/纯色/全景）是**镜头不是地点**, 直接排除出同地判断
- [ ] **★ 三档分流: 情景图 / 粗粒度地理 / 具体地点**（用户 2026-09-15 澄清，
      **这是 emoment 的真实含义**）——**同一张 `_place_entities.json`, 按类别走三种
      注入策略**。表自身的结构（`sdir`/`dir` / `region` / `place`）**已经把三档分好了**:

      | 档 | 判据 | 给主 LLM | 谁解析 | 现在能做？ |
      |---|---|---|---|---|
      | **写作用词**（特效/情景） | `sdir=SDIR_Atmosphere` ∩ active | ✅ 给**小词表**（`black`/`星空`…）——判据是"能让 LLM 更好地写" | 层1 → 层2 | ⏸ 词已在表里, 尚未成块注入 |
      | **粗粒度地理** | `region`（`regions.yml` 21 条） | ✅ 给**文本**（学院名一级） | 别名的纯字符串归一 | ✅ **已落地**（T16） |
      | **自由地点** | 表内/表外**均可** | ✅ **自由写, 不受限**（防注意力矩阵稀疏） | 层1 → **层2 读 `note` 就近推测** | ⏸ **等接线** |
      | **具体地点键** | 其余 `place` 键 | ❌ **不给键**（会框死） | 异步 lane（anno） | ⏸ **等接线** |

      > 2026-09-19 更正: 原表把"情景图"写成"给说明、**不给键**"——用户澄清
      > 那是**给词**的（`black`/`星空` 这类词能提升写作）；且"表外地点"不是
      > 要堵的漏，是**设计主路径**（靠 `note` 推测兜住）。

      **判据 = 这张表是"多给 writer 一个手段"还是"少给 writer 一个自由"**:
      - 情景图**必须给**——**能力可见性**: writer 不知道资产存在就**永远不会调度**它
        （"可以在最后调天空的情景结束, 但不告诉 LLM 它就肯定不会用"）→ **扩大**空间
      - 具体地点**不能给**——从列表里挑 = **收窄**空间
      - ⚠️ **不是封闭枚举**: writer 不写资产名（既有纪律）, 它写自然语言、由别名表
        命中 → **两步走在两档上都成立**, 区别只是命中率（情景图高、具体地点低）
      - ⏸ **情景图档挂起**（用户 2026-09-15）: *"AI 在 bond story 更多是编剧,
        给它一些常见的组合拳它自然能理解的, **这是等我手写那些图片结束后的事情**"*
      - ⚠️ **`DIR_PureColor`（black/red/white）排除**——作者在 `note` 里已写死边界:
        "黑色特效, **转场不必使用, engine 会处理的**"。筛选依据现成
      - ⚠️ **粗粒度地理会不会与 `world` 块重复** → ✅ **已核: 不重复**。
        `overview.yml` 里只有"基沃托斯"和"夏莱", **没有任何学院名清单** →
        writer 现在其实**不知道这个世界有哪些学院**（可能凭空发明）。
        所以注入 `region` 不是"给菜单", 是**给世界设定**（与 persona/world 同性质）
      - ⚠️ **待定（挂起）: writer 用什么信号调度情景图**——复用 `switch` 的 text
        / 新开 stage 原语 / 同 `time_of_day` 那样加可选字段

- [ ] **★★ 现在就能做的 place 第一刀（不依赖 tempo 表）**:
      ① **`place_palette` 退出盒B**, 换成 **`region` 列表**（`regions.yml` 21 条
         中文主名）—— 这正是"粗粒度地理以文本形式说明"; 盒B 9→8 块, **夹具必刷**
      ② **`BrainNode.region: str` + `BrainNode.place: list[str]`**:
         region 由 switch 原文经 `regions.yml` **别名归一**（纯字符串, **0 LLM**）;
         place 先只落**原文**（键留空, 等 tempo 表 → 原文留着可重解析,
         同 `verbatim_seq` 的理由）
      ③ **switch 并入 place lane**: 消掉与 `annotate_places` 的"二选一早返回"
      ④ **C 链路先落 region 层**: `region` 相等（精确、0 依赖、不靠 embed 后端）

- [ ] **`regions.yml` vs `place_studio.REGIONS` 双表漂移**: `place_studio.py`
      **内嵌了第二份 `REGIONS`**（`place_studio.py:40`, 自称"不再依赖/import
      Live2Be"）与 `config/settings/world/regions.yml`（21 条）各一份
      → 两份表迟早漂移。接线时收口到一份。
      ~~Live2Be 侧零消费~~ **2026-09-19 更正: 此说法已过时** —— T16 之后
      `core/parsing/place_regions.py:57` 与 `core/promptkit/blocks.py:22` 都在读它,
      【世界区域】块已上屏

### 地点系统实测（2026-09-19 复核, 只读探针）

> 探针: `.testtmp/probe_place_ns.py`（命名空间对齐）/ `probe_place_table.py`
> （表结构缺口）/ `probe_place_real.py`（真机事件流地点痕迹）。

- [ ] **🔴 现役「地点→画面」链在真机上全灭**（haruka 6 板 + mutsuki 14 板）:

      | 观测 | 值 |
      |---|---|
      | `place_hint`（writer 的换场话） | **3 条**（校舍后面的杂草屋 ×2 / 街角的咖啡馆，靠窗的位子 ×1） |
      | board 级 `place`（翻译结果） | **0 条** —— 3/3 MISS |
      | 记录级 `place` 锚点 | **0 条** |
      | board 级 `background` | **`neutral` × 20/20** |

      `neutral` 不是场景（`cat.background("neutral") is None`）→ `_resolve_scene`
      落到 `_fallback_bg_url()` → `_BG_FALLBACK_PRIORITY[0]` → **`class_room`**。
      ⇒ **每次 VN 都在显示教室**，剧情开在杂草屋还是咖啡馆一样。
      （比对 `TODO` 里"bond 黑背景遗留确认"那条——这就是它的具体形态）
- [ ] **🔴 31 条裸 slug 两头都不对**（`data/diag/live2be.log` 的 `[place][SWITCH]`
      共 331 行）:
      - 写到的地儿**没有** → `'校舍后面的杂草屋'→MISS` / `'街角的咖啡馆…'→MISS`（生产）
      - 有的地儿模型**硬凑** → `'深夜的杂草屋' → school_rooftop` ×88（杂草屋译成校舍屋顶！）
        —— 正是 `place_resolve.md` "宁可空着，不要硬凑"要防的事, 没防住
      - `'学校天台' → rooftop` ×11：`rooftop` **不在**当前 31 条里（是 `school_rooftop`）;
        而 `llm/prompts/place_annotate.md` 的示例还写着 `[{"sentence": 3, "place": "rooftop"}]`
        → **示例教了一个会被闸门丢掉的 id**, 待改
- [x] **三份孤儿产物已删**（2026-09-19 用户裁决: background 目录整体换成工作区组织）:
      `assets/_background_lexicon.json`（616 条 VLM 打标, 曾经 `76e45d9` 入库 →
      `git rm`; 要回滚: `git show 76e45d9:assets/_background_lexicon.json > <path>`）·
      `assets/_place_draft.json`（94 KB,
      `place_organizer.py` 的 Stage 1 草案, 可重生成）·
      `assets/background/_place_entities.json`（2 条, 旧 `name` schema）。
      三者**全库零消费方**（grep 证实）
- [x] **旧版工作台已删**（2026-09-19 用户裁决: "只有 tempo 下是好的"）:
      `tools/place_studio.py`（09-07, 28 KB）已 `git rm`; 真源 =
      `D:\myStuff\tempo\place_studio.py`（09-15, 38 KB, SDIR/DIR + 导出重写）
- [ ] **⚠️ `assets/background/.thumbs/` 被当成资产扫进 catalog**：
      `MediaCatalog._scan_backgrounds` 用 `rglob("*")` 不跳隐藏目录 →
      **239 张 480px 缩略图进了 `background_scenes()`**。今天恰好不赢
      （同 scene 的首选图仍解析到真图, 0 个场景落在 `.thumbs`）——**顺序偶然, 不是设计**。
      换成 SDIR/DIR 组织时 `.thumbs` 会跟着搬 → 加一行"跳过点目录"再动

## 地点换代 PL0–PL8（**计划稿, 未开工** —— 用户 2026-09-19: *"允许你大刀阔斧做改动,
然后同样的先列 TODO，不要做"*）

> **读法**：这是把地点系统从"能跑"推到"干净且完整"的一条线。每条都写了
> **验收判据**与**阻塞点**；最后 §"开工前必须先跟你讨论的 6 件事"是**我不确定、
> 需要你先裁**的地方（用户要求：*"但凡你有任何的混淆都要先和我讨论"*）。
>
> **不碰的边界**（免得多线程互相踩）：MMT 主链 · v3 的 entity 层 · 日夜
> （`files.night`/`time_of_day`, 至今无消费方）· region（用户已说撤, 只留盒B 块）。

### PL0 资产换代：`assets/background/` → `SDIR_*/DIR_*`（**地基, 最大的一块**）

> **✅ 同步模型已定（用户 2026-09-19）**：*"tempo 是我的暂存工作区，你可以理解为一个
> 带实体的 development 分支，我会在 tempo 进行工作，然后将其中的 SDIR、DIR，此表
> 同步更新"* ⇒ **单向 tempo → repo**, 由用户执行同步; 我这边只负责"repo 侧能接住
> 新组织"。`.thumbs/` 不在同步清单里（同步的是 SDIR/DIR + 表）, 但 repo 里
> **现存的那份 `.thumbs`** 仍要处理（见下第 2 条）。

- [x] **repo 侧接住新组织（代码已做, 2026-09-19）**:
      · `MediaCatalog` 背景扫描改成显式 walk + **剪枝点/下划线开头的目录**
        （`.thumbs/` 缩略图 / `__pycache__` / 作者预留的 `_unused/`）
        —— 真机: 遍历到的图 **1333 → 1094**（239 张缩略图不再进索引）,
        `background_scenes()` 仍 620
      · **删** `background_dirs()` / `background_scenes_in_dir()`（零消费方 +
        换组织后会说谎）; `_director_whitelist.json` 的 `common_dirs` 同批删
      · 新增 3 例测试（两级组织可扫 / 缓存目录被剪 / 那两个 API 已删）,
        **哨兵验过会红**（关掉剪枝 → `['class_room','class_stairs','junk','old_thing']`）
- [ ] **用户侧同步**（他的活）: 把 tempo 的 `SDIR`/`DIR` + 表同步进 repo。
      ✅ **已完成**（asset 已换; 表本来就已在位, 逐字节相同）—— 见上面那条。
      **以后**若在 tempo 重新导出表: 拷 `_place_entities.json` →
      `config/settings/world/place_entities.json` 即可（`PlaceTable` 按 mtime 自动重读,
      不重启）; 拷完跑一次对账脚本。
- [x] **✅ PL0 完成（2026-09-19）—— 用户已把 `assets/background/` 换成工作区组织**:
      · 磁盘形态: **10 个 `SDIR_*` / 1094 张图 / 零 `BG_*` 残留 / 零缓存目录**
        （干净替换, 没留旧树）
      · 对账 `python experiments/place_asset_audit.py`:
        **A = 168/168 条目全对, 435/435 `files` 命中磁盘** ·
        **B = 168/168 `_place_bg(key)` 取到图** · C = `{'SDIR_*': 10}`
      · **表其实早就同步过了** —— repo 的
        `config/settings/world/place_entities.json` 与 tempo 的
        `_place_entities.json` **逐字节相同**（MD5 一致）: 我在 A1/A3 那步就拷进来并
        随 `abf5860` 入库了, 作者此后再没重新导出 ⇒ **无需再拷**
      · 全量 802 通过（换组织后无一测试因 `BG_*` 假设而红）
      · grep 复核: `core/ webgui/ llm/ contract/` 里**没有任何地方假定 `BG_*` 目录布局**
        （剩下的 `BG_` 命中都是命名前缀: `BG_DIR` / `_BG_CATALOG` / 文件名示例）
- **验收**: 跑 `python experiments/place_asset_audit.py` —— **A 全绿 ✔**
      （后续改表/换组织后复跑一次即可）

### PL1 表与资产的路径对齐 —— **✅ 完成（2026-09-19）**

- [x] `experiments/place_asset_audit.py` —— 答两个**不同**的问题:
      · **A. 表 `files` ↔ 磁盘**（PL0 的真验收）→ 资产换代后 **168/168 全对, 0 缺**
      · **B. 运行时 `_place_bg(key)`**（玩家会不会看黑屏）→ **168/168 取到图**
        （scene_id 由**文件名**派生, 所以组织换了也照样命中——这也是换代期间
        B 一直全绿、A 才飘红的原因）
      · C. 目录形态
- [ ] 以后改表 / 换组织后复跑一次（当常规自检）

### PL2 镜头与手法成块 —— **✅ 完成（2026-09-19）**

> **落地形态（与本节 ④ 记的原计划有两处不同, 见下"⚠️ 与原计划的偏差"）**:
> · 文件 `llm/prompts/bond_shots.md`（【镜头与手法】: 镜头词 / switch 组合拳 /
>   煽情场景怎么写 / 收尾收法 / 范本）
> · 加载 `blocks.py::_bond_shots(ctx)` → `load_prompt("bond_shots")`,
>   `{char_id}`/`{char_name}` 与 `_rules_bond` 同手替换
> · 盒B **9 → 10 块**: `rules_bond → **bond_shots** → schema → place_world → brain`
> · 规则书 §七 收窄为【七、收尾】（只留 end 硬规则 + 一句指针）; §八 范本整节迁走
> · 新测试 `tests/core/test_bond_shots.py`（5 例, 含**镜头词 ↔ 表**的镜像防漂移）;
>   promptkit 夹具已刷（`bond_box.txt` / `bond_scene.txt`）
> · 全量 **812 通过**

**⚠️ 与原计划的偏差（两处, 都是实测/推理后改的, 若要回退说一声就挪）**

1. **盒内位置 = 紧跟 `rules_bond`, 不是当初写的"紧跟 `place_world`"**。
   理由: 这一块**就是规则书 §七/§八 的搬迁续篇**（原话 *"我怀疑现在全堆在 bondrules"*）,
   而规则书里留的指针（*"常用收法与范本见【镜头与手法】"*）就在它上一行——隔开一个
   schema 去找它反而别扭; `place_world` 是另一族（世界设定, 且是条件块——它缺席时
   位置会飘）。schema 仍是"契约在后"。
2. **镜头词逐个核对过表, 改了三个字**（这是镜像测试当场抓到的）:
   · `繁星` → **`繁星夜空`**: 表的别名是"繁星夜空", 写"繁星"层1 **miss**
     （会白花一次 place 调用, 而且层2 可能挑到别的图）;
   · 删掉 `纯黑（黑场）` 里的"黑场": **"黑场"不是表的别名**（别名是 纯黑/黑屏/黑色/黑幕）
     ——摆在 writer 面前的词被照抄就 miss;
   · **补 `黄昏云彩`**: 不补的话 `view_dawnsky` 这张图**永远没有入口**
     （writer 不知道它存在, 层1 也没有针）⇒ 现在 8 个词覆盖全部 4 张 atmosphere 图。

**① writer 现在手里到底有什么**

只有 `bond_story_rules.md §五` 的**一个示例** `{"stage":"switch","text":"星空"}`。
**没有任何词表** —— 天空/黑场这类镜头, writer 只能从这一个例子自己推。

**② 表里那 4 条是什么（它们不是地点）**

| key | 别名 | 是什么 |
|---|---|---|
| `view_sky` | 蓝天白云 / 星空 / 夜空 / 黄昏 | 天空镜头 |
| `black` | 纯黑 / 黑屏 / 黑色 / 黑幕 | 黑场（作者 note: *"角色用于思考时可用的黑色特效, 转场不必使用, engine 会处理的"*） |
| `view_constellation` | 流星雨 / 繁星夜空 | 夜空镜头 |
| `view_dawnsky` | 黄昏云彩 | 黄昏镜头 |

**③ 为什么该给（而不违反"零内容词表"）**

- **能力可见性**: 不告诉 writer 有天空镜头, 它**永远不会调度**（这是项目自己的判据）
- 用户原话: *"这些词能让 LLM 更好的写作"*
- "零内容词表"那条裁决打的是**168 条资产菜单**（从列表里挑 = 收窄创作空间）。
  这里给的是 **4 个手段**（"你能切黑场 / 能给一个星空收尾"）, 不是"你只能去这 4 个地方"

**④ 机制: 用户 2026-09-19 定 —— "这个东西我打算单开一个小文件"**

⇒ 走 **`llm/prompts/` 手写家族**（项目既有形态: `bond_story_rules.md` /
`momotalk_environment.md`, **人可改, 代码只加载**）, 不做"从表动态生成"。

| | |
|---|---|
| 文件 | `llm/prompts/bond_shots.md`（跟现有 `<域>_<角色>.md` 命名一致; 名字可改） |
| 加载 | `core/promptkit/blocks.py` 加一个 `_bond_shots(ctx)` → `load_prompt("bond_shots")`, 与 `_rules_bond` 同一手 |
| 盒内位置 | ~~紧跟 `place_world`（同一家族: 地点/镜头）, 在 `brain` 前~~ → **实际紧跟 `rules_bond`**（见上面"偏差 1"）⇒ **盒B 10 块** |
| 代价 | 加块 → promptkit 夹具刷一次（既有纪律） |
| 好处 | 夹具稳定（不随表动）; 文案归作者手改（`black` 什么时候用这类话正好写在这儿） |

⚠️ **手写的代价（我已想好对策）**: 文件里那份词表与表里的 `SDIR_Atmosphere` 4 条
**是两份东西**, 会漂（文件写"流星雨"、表里把别名改了)。项目对这类问题有现成解法 ——
**镜像防漂移测试**（`test_judgement_mirror_between_rules_and_prompt` 就是干这个的）:
加一条"文件里出现的词都能在表里解析出 key", 漂了就红。**几行的事, 值得**。

**⑤ 文案草稿（我拟, 你改字）**——目标: 说清"这是镜头不是地点"

```
【镜头】（不是地点, 是"怎么拍"）
收尾、氛围、转场时可以用这些镜头, 写进 switch 的 text:
  星空 · 夜空 · 黄昏 · 蓝天白云 · 流星雨 · 繁星 · 纯黑（黑场）
例: {"stage": "switch", "text": "星空"} —— 一段戏的收束
（这些不是"你要去的地方", 是画面本身; 想不起用就不用）
```

**⑥ 与 `rules_bond §五【换场】` 的分工（不重复）**

rules 教**什么时候发 switch**（能力）; 新块给**能用什么镜头词**（手段）。

- [x] 拟文本 → 落块 + 刷夹具（**文案随时可改**: 文件在手写家族里, 代码只加载）
- [x] ⚠️ `black` 的用法归在那个文件里写 → 已写: *"纯黑用在角色走神、失神、
      一句话说不下去的地方，不用来当普通转场"*（作者 note 说"转场不必使用"）
- [x] ⚠️ **顺手修文档债**: `CLAUDE.md §8` 的"盒A **9** 块"→ **10**（`time_sense`）
      与盒B **9 → 10**（`bond_shots`）两处一起改正; 同节补"**唯一词表例外 = 镜头词**"
      （原句是"盒B 至此已无任何词表块"——现在有了, 得说清为什么它不违反"零内容词表"）

### PL3 每板一次的 `annotate_places`（**两次纠正后的版本**）

**① 用户纠正我（对）**：*"板的设定本身就是为了 switch，它不是剧情段，它就是一个
单纯的标注单元，所以为什么 writer 要在板内换场？奶奶的这 writer 都不知道有板的
存在啊"* —— **我那个"板内换场"的说法是错的**：板是**引擎的标注/推进单元**,
writer 根本不知道板存在, 它只是连着写记录、该换场就发 switch。

**② 我去量了真机（`.testtmp/probe_board_cause.py`）—— 结果比双方猜的都清楚**：

| 角色 | 板 | switch | **有选项的板** | 每板平均记录 |
|---|---|---|---|---|
| `igusa_haruka` | 6 | 2 | **5/6** | 8.7 |
| `asagi_mutsuki` | 14 | **1** | **13/14** | 5.1 |

⇒ **板主要是 `sensei` 群（= 选项点）切的, 不是 switch 切的**（`records.py`:
`sensei` 群结束就 `_close()`）。switch 只是另一种边界。

**③ 这不是 bug, 是 v2 的设计**（我顺手查了代码, 见 `webgui/bond.py:2611`）:
> *"记录流 v2（P0-7c）: 旧的'整段剧情 2~3 次选项配额'注记**退役**——v2 的交互密度
> **由 rules 引导（一段戏里老师开口 3~5 次）**, 引擎不再逐轮念配额"*

一段戏 ≈ 30~45 条记录, 老师开口 3~5 次 ⇒ **一段 = 3~5 个选项点 = 3~5 个板**。
真机 17 组选项 / 一章, 正在这个区间里。⇒ **板数 ≈ 交互密度, 是产品参数**。

**④ 所以"每板固定开销 × 板数"要分开看**：

- `emotion` 一次/板 + `place` 一次/板 —— **两次都是廉价调用, 且都在异步 lane**
  （不挡玩家: 玩家读一板 > 1s, 车道 0.5s）。⇒ **成本上不成问题**,
  "板数下界"作为**省钱手段没必要**。
- 真要立规矩, 理由该是**体验**（两句就抛一次选项太碎）而不是资源。
  真机中位数 ≈ 4~5 条记录/板, 最小 2 —— 这个我不觉得需要动。

**⑤ 真正该省的只有一份: `annotate_places`** —— 它是 **C6 引入的、与交互密度无关的**
额外成本（每板恒定一次 7022 字符调用）。而且它**只可能抓一种情形**:
**writer 描述了移动却没发 switch**（漏发）。实测 14 板 0 锚点。

**⑥ 决定（不变, 但理由更干净）**: 走 **(b) 板内有换场线索词才扫**
（线索词 = rules §五 那串, 与 `place_annotate.md` 镜像, 有测试钉着）。
"漏发 switch 却没写线索词"这个组合几乎不存在 ⇒ 预筛近乎无损。
顺手带**句级层1**（预筛过的板先逐句别名命中, 命中即 0 调用）。

**⑦ 顺手发现的文档债（已改）**: `CLAUDE.md §6` 写着
*"规则层整章 0~3 次、常单个直白（多数板无 choices）"* —— **v2 已废**, 真机 13/14 板
有 choices。那条是 v1 口径, 会误导人（我就是被这类句子带偏的）。

- [x] **✅ PL3 完成（2026-09-19）—— 两道 0 调用闸, 真机验收通过**

      **先量后做**: 真机 20 板 / 93 段正文 → 含换场线索词的板 **0/20**
      （正文几乎全是对话, 位移都写在 `switch` 里, 而 switch 不进 `paragraphs`）
      ⇒ 此前每板一次的 7022 字符调用 **20 次零收益**。

      | 件 | 落地 |
      |---|---|
      | `core/bond/place_cues.py` | 换场线索词表（**取宽**: 穿过边界的位移动词 38 个）。**故意排除** `转身/坐下/蹲下/走近`（`place_annotate.md` 明确判为"不换场"——收了它们等于把预筛关掉）。`CORE_CUES` = 必须与两份 prompt 逐字一致的核心子集 |
      | 闸1 线索预筛 | 板内无线索 → 整板跳过, 日志 `[place][SKIP] skip=no_cue` |
      | 闸2 句级层1 | 有线索但**每句都能被别名唯一命中且 ≠ 当前** → 直接落锚, `skip=layer1_hit` |
      | 兜底 | 两闸都过不了 → 照旧 `annotate_places`, 日志 `[place][SCAN] cue=…` |
      | 镜像测试 | `test_judgement_mirror_between_rules_and_prompt` 改成**遍历 `CORE_CUES`** ⇒ 引擎预筛词 ↔ rules ↔ annotate prompt **三处同源**, 改一处不改另两处就红 |

      ⚠️ **踩过的坑（已写成测试）**: 闸2 **不能用** `place_annotate._layer1` 的
      "歧义∩当前 → keep"捷径 —— 句子级最常见的换场恰恰是
      「她拉着我**走出教室**，来到**天台**」（当前与目的地同时出现）,
      走捷径会把整板判成"不用动" → **画面永远不切**。故本闸只认"唯一命中且≠当前",
      其余（歧义/表外/与当前相同）**一律交 LLM**。

      **真机验收**（`experiments/place_switch_real.py`, 已给脚本加 `basicConfig` 让
      `[place]` 可见）:
      ```
      [place][SWITCH] '放学后的教室'      → classroom          （层1, 0 调用）
      [place][SKIP] skip=no_cue recs=2 / recs=3 / recs=1 / recs=3   ← 4 板全跳过
      [place][SWITCH] '格黑娜学院·旧校舍天台' → school_rooftop    （层2, 1 调用: 天台歧义）
      地点相关调用 1 次（此前同样 4–6 板要 4–6 次）
      背景序列 ['class_room' ×3, 'school_rooftop'] —— 换场照常切
      ```
      测试 807 通过（+5）。

### PL4 旧物清账 —— **✅ 完成（2026-09-19）**

> 用户原话: *"总之我们需要一个地点语义检索来体现既视感以增强我们的召回策略"*
> ⇒ **能力保留, 只是换基座**: `PlaceRetriever` 的跨语言 embedding 检索是
> "玩家自由指定地点 / 地点既视感"的预留, **不能删**。

**落地（`core/rag/place.py` 重写 + 三处清账）**

| 件 | 结果 |
|---|---|
| **语料换基座** | `places.yml`（31 条手维护资产 slug）**删除** → 语料 = `place_entities.json` 本身（**168 键 / 428 别名**, 与标注层层1/层2 同源; `table.aliases()` = `place`+`keywords`, **`note` 刻意不进**——那是元话语, 嵌进向量只是噪声） |
| **返回单位** | 表键（不是资产 scene_id）; 翻译走新的 `asset_scene()` / `PlaceTable.scene_id()`。层1 命中（唯一别名）→ 1.0 且 **0 次 embedding**; **歧义不猜**（`天台` → 3 键）→ 下沉语义层, 服务不可用就 `[]` |
| **打分改法** | 旧实现每键只留"平方范数最大"的**一条**别名向量（L2 归一化下 ≈"只留第一条别名", 同键其它别名全白扔）→ 现在**保留全部别名向量**, 取键内最大余弦（428 条放得下） |
| **`build_place_injection`** | **删**（`emotion_lexicon` + `core/media/__init__` 导出 + 旧测试）——生产零调用, 且它宣传的"主 LLM 只从词表里选 place"早已被记录流 v2 + 零内容词表裁决废掉。新测试改成 **gone-API 哨兵** |
| **`paths.PLACES_PATH`** | 删（清单只剩 21 条）; `test_paths.MUST_EXIST` 同步 |
| **`_director_whitelist.json`** | **保留**（身份 = `bond_story._place_keys` 的降级兜底）; `paths.py` 那行过时注释已改（原写"现役 place 词表, 表接线后作废"——现在它已不是现役） |
| **`place_regions.py`** | **不动**（并进 `blocks.py` 是纯搬家, 无行为收益——PL4 原话"可不动"） |

测试: 新增 `tests/core/test_rag_place.py`（**9 例, 全用桩 embedder, 不碰本机服务**）:
语料=表且旧 slug 不在其中 · `places.yml`/`PLACES_PATH` 已消失 · **428 个别名全进 embedding**
（哨兵）· 唯一命中 0 调用 · 歧义下沉语义层（候选集 = 那 3 个键）· 歧义+无服务 → `[]`
（不猜）· **"该赢的是第二条别名"哨兵**（旧实现在这条上会返回 `[]`）· 空表降级 ·
`classroom → class_room` 翻译。全量 **822 通过**（+10）。

**⚠️ 一个必须报给作者的发现（换基座的代价）**

这版表里**一个假名别名都没有**（`grep` 实测: 428 个别名中 0 条含假名; 170 条拉丁
别名**全是 slug**（`view_sky`/`big_plaza`）, 不是自然英语）。而删掉的 `places.yml`
**有**（`屋上`/`廊下`/`ラーメン屋`/`コンビニ`…）——所以"跨语言"这条**从字面命中退化
成纯靠 embedding 模型**（bge-m3 这类能桥, 但那是模型能力, 不是语料）。
`experiments/rag_test.py` 已把这类 query 单列一节（**不计失败**, 只测模型能力,
并在输出里写明"想要字面命中: 在 tempo 表里给该键加这条别名"）。
另: 旧语料里的 `onsen`（温泉）**表里没有对应条目**、`gehenna_club_room` → 表里是
`68office`、`class_room`/`ramen_ya` → 表键是 `classroom`/`foodcart_ramen`
⇒ 这些都是"换基座"的必然结果（语料跟表走）。

### PL5 C 链路通电 —— **❌ 用户 2026-09-19 答"不"**

- **不做**（不补生产者、不接主链）。理由: 半通电比不通电更难查; 这是 v3-3 的活,
  等 v3 整体推进时一起做。
- 现状留档: `get_channel(...).gather(...)` 全库只在测试里出现;
  `ctx.place_now` / `place_raw_now` 无生产者。**`node.place`/`place_raw` 的数据照常
  物化**（digest 那一手不受影响, 将来通电时数据是齐的）。

### PL6 工具：改名批量替换 + 留痕 —— **✅ 用户: "允许留痕"；并澄清"表里不会有重名"**

> **⚠️ 我原先写错了一条, 删掉**：我编了个"两个旧 key 撞成一个新名 = 不可逆合并"的
> 场景。用户 2026-09-19 澄清: *"两个旧 key 对应同一个实际名，在 json 里不认为它会
> 发生，因为不然都过不了 json dump"* —— **对**:
> * 表是 **JSON 对象**（一个 key 一行）⇒ 同名只能是同一行; `json.dumps` 也构造不出
> * A1 之后 `api_export` 还加了**撞车保护**（两个组算出同一个键 → 不写盘 + 报出）
> ⇒ **"表里两条同名"不是要防的东西, 那条删掉。**

- [ ] 工具只需三件事: **① 改表里那一行的 key ② 扫引用面 ③ 留痕**
- [ ] 扫描面: 事件流 `payload.place` + `paragraphs[*].place` + 表 + `_place_review.json`；
      **`place_hint` 是原文, 不动**
- [ ] 留痕台账: `data/worlds/{world}/place_renames.jsonl`（append-only, 与事件流同卷可
      grep）记 `{ts, 旧key, 新key, 原因, 影响事件条数}`；**事件流本身不改**
      （append-only 铁律——改名只发生在表里, 台账解释"旧事件里的 key 为什么查不到"）
- [ ] **✅ 决定: 台账 + 给它一个消费方**（不然又是一件孤儿产物）——
      `_place_bg()` 查不到 key 时**先查台账**: 命中就报
      `"key 'X' 已改名为 'Y'"`, 而不是笼统的"素材未找到"。
      于是那条黑屏 `alert` 直接告诉人**该去改什么**。台账形态就此定为**独立 jsonl**
      （不塞进表: 表是"当下的视图", 不背历史）
- [ ] **小守卫**: **手编 JSON 里写重复键, `json.loads` 不报错、静默保留最后一个**
      （探针 `.testtmp/probe_json_dupkey.py` 实测）。生成侧安全（dict + A1 撞车保护）,
      但**读取侧**仍可能被手编文件骗 → `load_table` 用 `object_pairs_hook` 数重复键
      并 WARNING（一行的事）

### PL7 表自身收尾（**作者侧**, 我只出清单）

- [ ] `files.night` 归类：混进状态变体 25 张（ruin/erode/blur/off/dark/party/fake）
      + 白天天气 7 张（fog/rain/cloudy/dawn/sky）; 只有 115/168 是真夜景
- [ ] `tent_inside` 无 day 文件（唯一一条）
- [ ] 覆盖率：435/1094 = 39%; `SDIR_Special` 59 组 **0 active**; `SDIR_Schools` 9/126
- [ ] 写了 note 却没勾 active 的（`ruinpianoroom` 废弃琴房 / `abandoned_warehouse` …）
- [ ] `region` 补全（现 20/168）——用户说"作用不大", 可做可不做

### PL8 文档/夹具收尾

- [x] `CLAUDE.md §8` 的"**盒B 至此已无任何词表块**"要改成"唯一例外 = 写作用词"
      —— 已改（`bond_shots` 的例外 + "零内容词表"打的是 168 条资产菜单, 两处一起说清）
- [ ] `DESIGN_PLACE §2`（`time_of_day`）/`§3`（扩展性表）作废或改写
- [ ] `docs/AI_BRIEF_PLACE.md` 跟着每次改动更新（**它是给 AI 的, 落后就会再被带偏**）
- [x] promptkit 夹具（PL2 加块后必刷）—— 已刷 `bond_box.txt` / `bond_scene.txt`,
      并给基线加了 `【镜头与手法】` 的顺序标记

### 用户已裁（2026-09-19）

| # | 问题 | 裁决 |
|---|---|---|
| ① | PL0 同步方向 | **tempo = 带实体的 development 分支**; 用户在 tempo 工作 → 把 `SDIR`/`DIR` + 表同步进 repo。**单向 tempo → repo** |
| ③ | PL4 删还是留 | **留** —— *"我们需要一个地点语义检索来体现既视感以增强我们的召回策略"*（换语料基座即可） |
| ④ | PL5 要不要半通电 | **不**（并入 v3） |
| ⑤ | PL6 重复键名 | **表里不存在这问题**（JSON 对象 + A1 撞车保护）——我原先那条"合并"是编的, 已删。**"一名对两 key"的真身在回灌表**（见旁路项） |
| ⑤′ | PL6 留痕形态 | **独立 jsonl 台账 + 让它给"素材未找到"当解释**（见 PL6; 我已定, 不再问） |
| ⑥ | PL2 块名/文案 | **机制已定**: **单开一个手写小文件**（用户: *"这个东西我打算单开一个小文件"*）—— 不做"从表动态生成"; 已落（见 PL2 节） |
| ② | PL3 选项 | **已定 (b) 线索词预筛**。⚠️ 但**问题框架被用户纠正过, 且我实测后诊断又改了一次** —— 真机数据证明**板主要是选项点切的, 不是 switch**（详见 PL3 节）: "板内换场"不存在; 每板固定开销（emotion+place）都廉价且在异步 lane ⇒ **"板数下界"作为省钱手段没必要**, 真要立的理由是体验。**真正该省的只有 `annotate_places` 一份**（C6 引入, 与交互密度无关） |

### 仍需你过目的（不是选择题, 是"看一眼字/一件事"）

1. ~~**PL2 的文案草稿**~~ **已落**（`llm/prompts/bond_shots.md`, 见 PL2 节）——
   它是手写家族, **字随你改**; 唯一要守的是【一】那行镜头词得是表里的别名
   （改了会红, 见 `tests/core/test_bond_shots.py`）。
   附带那个小问已按"写进文件"处理: `black` 写成"纯黑用在角色走神、失神、
   一句话说不下去的地方, 不用来当普通转场"。
2. **PL6 台账文件名/位置**（`data/worlds/{world}/place_renames.jsonl`）—— 我已定,
   除非你想换个地方。

## 中期（蓝图 / 板块）

- [ ] **回放功能**（事件流 → 自动播放）：
      - vn_state marker 中断恢复：服务重启后重建 VN 引擎续播（webgui/bond.py 注释
        "M3 回放"——事件流在, 内存态丢, 需重建）
      - 回放模式：已存档剧情自动播放（选项锁定 picked）——DESIGN_RENDERER.md M3;
        CLI 恢复入口（list_open → resume, 旧 TODO"存档系统恢复入口"）
- [ ] **多角色扩展**（DESIGN_MULTI_CHAR.md 蓝图）：
      - 字段预留已就位：character_names 称呼注入（momotalk/bond_story 分饰多角）、
        interperson 权重表、hub channel 预留、observer 语义（reported_fact）
      - 群像本体：A 一次调用 / B 轮番调用（段落流抽象）——前置：单人模式稳定
- [ ] **RAG 召回记忆**：`recall.py` 三通道（读路径 v2）+ `channels.py` 五链路
      （读路径新接口 V3-3）**都已实现**; embed_fn 注入=RAG 升级接口已留。
      **2026-09-15 更新 —— 缺的不再是接口**:
      - ✅ **后端配置面已就位（T18）**: `settings.toml [embed]` + `LIVE2BE_EMBED_*`
        （真源 `core/rag/embedder.py`, 优先级 构造参数 > settings.toml > env > 默认）
      - ⏳ **服务没起**: 探过 1234/1235/8080 全部超时。**起来之后写路径自动活**——
        digest Round B 的候选提示走 `_get_embed_fn()`, 零代码改动; 观测口 =
        台账行 `recall_write … collide=% best=…`（可复测 Qwen3 的 (0.452, 0.682) 窗口）
      - ❌ **读路径缺组合层**: `RecallContext` 全仓只有测试构造 → 五链路谁都没在
        生产里被调用过（A/B/D 都能出分, 只是没人调）。**卡在"合成函数"这个裁决上**
        （链路 kind/scale 各不同, `channels.py` 写明"最终分由合成层算", 而合成层没写）
      - 原文回捞（滑动窗口外的按需调页）仍未做
- [ ] Virtual Brain 完整（Semantic Graph / Self-Model / Sleep 五阶段——当前 digest
      体系是其简化版; CLAUDE.md §3.2）
- [ ] 官方剧情（剧本解析器 + 播放器）
- [ ] 羁绊值系统（现用轮数制; 好感 delta 已流式累计——数值体系与行为挂钩未做）
- [ ] mmt_send_media 媒体管线（资源查库 → 生图; 当前占位回灌）
- [ ] 世界观输出侧校验（LLM 输出 vs overview.yml 规则检测矫正——config/settings/.md 未来项）
- [ ] SSE 流式推送替代轮询（chat_stream 客户端已有, 引擎/前端未接）
- [x] ~~时间系统（待拍板）~~ → **已落地（2026-09-13, T0–T13）**:
      `core/worldtime/` 独立包（游标 `world_clock.json` / 槽位算术 / 虚化短语 /
      手机日期 / 现实间隔）+ 写路径 stamp `story_time` + 读路径"（3 周前）"注记 +
      旧档迁移 + A 链路新鲜度。设计见 `docs/DESIGN_WIKI_V3.md` §4

## 已知技术债 / 文档债

- [ ] 事件流全量保留策略（YAGNI：等积累大再摘要化/归档）
- [ ] jsonl 单行 >4KB 的 append 原子性实测（长段落场景）
- [x] DESIGN_VISUAL_PROTOCOL.md 状态行过时（"设计定稿待实现"）——**2026-09-12 已校准**：
      顶部状态改写为"部分过时"（§2 主 LLM 出 emotion/place 已作废；§4/§8 词表形态仍生效）
- [ ] docs/archive 与 core/DESIGN_*.md 的部分过时描述（如 DESIGN_SAVE 已归档,
      新链路在代码 docstring——按需清理）。2026-09-12 已归档 maXEmo-miNDelay /
      reasoning_experiment / world_model_evolution 三份史料；仍在原位的 v1 架构档
      （DESIGN_VISUAL / DESIGN_GUI / DESIGN_MMT_CHAT / DESIGN_SEGMENT / DESIGN_WORLD /
      DESIGN_MULTI_CHAR）待逐个核对：仍是规范的修状态头, 只具史料的再归档
- [ ] llm/design.md 待定/未来扩展段核对（max_tokens/thinking 已集中到 task_levels.py）
