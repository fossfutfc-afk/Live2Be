# TODO.md — 施工顺序表（**digest 三层重排**）

> 建立 2026-09-27。**给用户审的表** —— 一行一个节点、一个提交，判据写死。
> 规格在 `docs/DESIGN_DIGEST_LAYERS.md`；顶层裁决在 `PROCEED.md §5`。
> **当前状态：N1a/N1b/N2/N2b/N3/N4a/N5(a,b,c,d)/N7/N7b/N7c 已落地（见下表 ✅）；下一个候选 = N8（`ignite` —— 群变记忆）/ N6 / N7d（多归属，待裁）/ N4b（建议缓）。**

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
| **N2** | ✅ **视野补齐（"深"）（已落地 2026-09-29）** | ⭐ `render_cognition_line`（两处共用）: 元信息进 `〔〕` + **边续行** + belief/promise 也印被引；`_round_b_material` 候选带**正文 + 被引 + 边 + why**；`recommend_candidates` 加 `why_out` | `render.py` · `digest.py` · `recall.py` | 真机输入里 **grep 得到 `edges:` 与「被引」**（零 LLM 渲染即可验） | — | 已完成 |
| **N2b** | ✅ **标题唯一性·写入时强制（已落地 2026-09-29）** | `address.unique_title`: 与既有名字冲突就加数字（`名字` → `名字 2`）· **只增不重排**（旧的改都不改）· 解析与写入**同住 `address.py`** | `address.py` · `digest.py` | 撞名后**两个名字各自唯一解析**（在此之前是 `ambiguous` ⇒ 她那笔直接丢） | N2 | 已完成 |
| **N3** | ✅ **L1 区间化（已落地 `327821c`）** | `event_seq` → `span:[from,to]`；引擎 `_expand_spans` + 未认领/重叠台账 | `contract/digest_registry.py` · `digest.py` · prompt | ⭐ **覆盖率** · 重叠如实报告不裁 · 旧档兼容 | — | 已完成 **下游零改动** |
| **N4a** | ✅ **note 的写者收成一个（已落地 2026-09-29）** | `habits` 槽**退役**（全链）· `on_mind` 改由 **L1（Round A）** 写（`on_mind_out` 传出 + 挂 `notes_ops`）· **全景轮整条退役**（它的两个槽都没了）· ⭐ 注入块的 refs **印名字不印编号** | `notes.py` · `digest.py` · `contract/digest_registry.py` · `revise.py` · `panorama.py` · `engine.py` · prompt | `habits` 全仓只剩退役注释 · L1 产 on_mind · 全景轮零调用者 | N3 | 已完成 |
| **N4b** | ⬜ **R4 并入 R1（缓 —— 见下方理由）** | 把 R4 的结清判断并进 Round A ⇒ 每段 4 次调用 → 3 次 | `digest.py` · 契约 | ⭐ **2026-09-29 更新**: 承诺退图后 R4 **只产 note 操作、不建节点** ⇒ 再也没有"节点必须先就位"这条验收线了, **并轮的阻力比原先小**（原来那句"promise 节点仍在 R2 之前就位"作废） | N4a | ~40 行 |
| ⭐ **N5** | ✅ **已落地 2026-09-29（拆三: N5a/N5b/N5c）** | ① 引擎召回 **1~2 条旧 episode** ② 注入"你想起的事" ③ 给她一个动作 ④ **锚点校验** ⑤ 落账 → **L1 补 `akin` 边** | `render.py` · `recall.py` · `mmt/*` · ⭐ `address.py`（新）· `digest.py` · `events.py` · `contract/schema.py` · rules | 召回有调用者 · **编造的引用被丢** · 账可查 · 补边幂等 · 未认领可 grep | N1 N3 | ⭐ **本主题的价值核心** |
| **N5a** | ✅ **想起（已落地 2026-09-29）** | ⭐ **标题进注入**（`episode.title` 从来没进过任何注入面 —— 它是**地址**）· 新 `render_recall_block` · 新 `recall_episodes`（只出 episode、**按相关度排**）· `agent_turn` 加 **P19** 槽位（动态尾） | `render.py` · `recall.py` · `recall_config.py` · `mmt/engine.py` | 召回有产品调用者 · 落点守卫（**不许进 system**）· 标题**不过 `_me`** · 无命中不注 | N1 N3 | 已完成（1125 passed · 真机探针见 §2） |
| **N5b** | ✅ **发现（已落地 2026-09-29）** | `{"noticed": "标题"}`（**顶层键, 不进 `action` 信封**）· 判别键恰好其一 · 不独占 · 锚点校验（命中 0 丢 / 歧义不猜）· 落 `noticed` 事件（**非内容事件**）· rules + 契约示例同批 · ⭐ **P19 段末加"候选旁的提示"**（真机实测: 只写在规则书里会漏报） | `mmt_lines.py` · `mmt_check.py` · `engine.py` · `events.py` · ⭐ `address.py`（新）· `schema.py` · `momotalk_rules.md` | 编造的引用被丢 · 账可查 · 旧形状不受影响 | N5a | 已完成 |
| **N5c** | ✅ **L1 落地（已落地 2026-09-29）** | 读窗口里的 `noticed` → 归属（"该账之前最近的有主内容"）→ `add_edge("akin", 新, 她指的)` · 幂等 · 未认领记台账 | `digest.py` | 同一条发现跑两次只出一条边 · 未认领可 grep | N5b | 已完成 |
| **N5d** | ✅ **括号统一（已落地 2026-09-29）** | 新 **`marks.py` = 括号与信息头的唯一实现**（`name`/`head`/`kind_tag`/`relative`/`abs_date`/`section`）· **五个写侧全部改调它**（她视图 · L2 · R2 · R4 · R3）· 类型标签与时间短语各收成一处 · `address` 的剥字符集从它取（**印剥同源**）· 顺手修掉 R4/R3 两处 `「标题」`（N2 漏改的） | ⭐ `marks.py`（新）· `render.py` · `digest.py` · `entities.py` · `notes.py` · `address.py` | ⭐ 守门用例 `test_marks_guard.py`: 代码字面量里零手写 `《》〔〕｜` · 她的视图不许印编号 · 格序钉死 · 印剥同源 · marks 零 import 期依赖 | N5a N5b | 已完成 |
| **N6** | **候选池 `gather_evidence`** | 抬 `panorama.py` 成通用件：参数化语料 + `why` + 两层深度 + **token 预算装填** | `panorama.py` → 新模块 · `recall.py` | 真机 5 个真组抬得出来 · 噪音组进 `rejected` · 按预算装 | N2 | ~120 行 |
| **N7** | ✅ **L2-a 分群（已落地 2026-09-29）** | 新 `groups.py`: **引擎切块**（`akin` 连通块 ≥2 条 —— ⚠️ **锚点兜底有意不做**, 见文件 docstring）→ 一轮 LLM **只起名**（`attach` / `new`）→ **群节点 + `member_of` 边**; ⭐ **同名即并**（纯计算闸）; ⭐ **这一步失败只回滚它自己**（分群是加法的 ⇒ 自愈） | ⭐ `groups.py`（新）· `contract/digest_registry.py`（`PHASE_GROUP` + `parse_group`）· `digest.py` · `address.py`（`find_group`）· `llm/prompts/digest_group.md`（新; 2026-09-29 乙-2 改名）· `llm/task_labels.py` | 块 ≥2 条才发 · **已归群的出局**（增量/幂等）· 没块 ⇒ **0 次调用** · 漏块 ⇒ 打回一次 · ⭐ **她的上下文零变化**（产出只在图上） | N1a N1b N5c | 已完成 |
| **N7b** | ✅ **`merge`（群撞群）（已落地 2026-09-29）** | ⭐ **候选判据只有一条: 跨群的 `akin` 边**（她连过 ⇒ "它们本来是一类"的直接证据; **名字相近那条有意不做** —— 中文短名会撞"的事 / 那些"这类虚词 ⇒ 全是假候选）· **并进 L2-a 那一轮**（同一个判断框架; 输出多一个 `merge` 键, 没候选时那一节不出现 ⇒ 常态零成本）· 执行 = **端点 remap（边的 `ts` 原样保留）** + 删输家 + **旧名写进赢家的 `aliases`** | `groups.py` · `contract/digest_registry.py` · `digest.py` · prompt | 只并**引擎提过的那些对**（闭集闸在执行器 —— 名字要归一, 而契约层不依赖 core）· `from==into` / 一轮里一个类并两次 ⇒ 整包拒 · 并完**候选自清** | N7 | 已完成 |
| **N7c** | ✅ **单条也能归已有的类（已落地 2026-09-29）** | 块多了一型: ⭐ **1 条**, 判据 = 它**连到了某个已有的类**（`Block.linked`）—— 以前这种单条被"≥2"直接扔掉 ⇒ **她那条边永远没人读**; 料里写成 `〔b1｜1 条〕 与 〔《那片苔藓》｜2 条〕 —— 她把它连到这一类` | `groups.py` · `contract/digest_registry.py`（schema 一行）· prompt | 单条照旧要归属, `attach` 是常态（**也允许 `new`** —— 禁掉它 L2 就没有"不是同一类"的出口, 那块会**每段重发**)· **完全孤立**的仍不进料 · 契约结构零改动 | N7 | 已完成 |
| **N7d** | ⬜ **多归属（发现第二个类）** | 设计稿允许"同一件事在两个类里", 但"已归群的出局"⇒ **第二个归属发现不了**（横切主题的类长不出来）; ⚠️ 它也是设计稿那条"成员重叠 ≥ 阈值 ⇒ 引擎直接并"永远不触发的原因 | `groups.py` · ⚠️ 语义要先定（**什么轴**允许第二归属） | 两条轴上的类都能长出来 | N7b | 待裁 |
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
✅ **已裁 2026-09-29**：**只记账 + L1 落地**（`DESIGN_MMT_NEW_ACTION §4.4` —— 原"seq 边"在边表里没有合法表示: `add_edge` 拒悬空）。

### N5a 想起（✅ **2026-09-29 已落地**）

```
render.py
  · ⭐ _memory_line / _meta_head: 记忆行的**元信息段定稿**（2026-09-29 用户裁决, 三轮讨论）:
        - 〔《事件名》｜多久以前｜日期｜难忘〕正文…（「原话」）
    事件名**放第一**（摘抄起点固定）· 用 `《》` 包（加了对她无害: 锚点解析剥括号）·
    字段边界用 **`｜`**（`·` 会出现在事件名里 ⇒ 抄多抄少 ⇒ 静默丢）·
    缺 title 就**不出名字字段**（`episode` 只必填 text）⇒ 规则 = **照抄它的 `《…》`**
    （按书名号找, 不按位置找）· ⚠️ 事件名**绝不过 `_me`**（它是**地址**, 要逐字可抄）
  · ⭐ 绝对日期（引擎坐标）与相对短语**两个都要**（`PROCEED §2 #16`）:
    `core/worldtime/age.render_date`（今年 `9/27`, 跨年 `2025/9/26`; 不给 now 或 ts 坏
    ⇒ 空 —— 不知道"今天"就不能猜年份）
  · ⭐ render_recall_block(): 新段【你想起的事（此刻浮上来的旧事——跟你现在要说的话
    有没有关系, 由你判断）】; 预算是**装填停止条件**（第一条永远留, 绝不截半条）
recall.py
  · recommend_candidates 加 `kinds=`（缺省不变 = Round B 的稳定认知）
  · ⭐ recall_episodes(): **只出 episode + 按相关度排**
    ⚠️ 与 recall_subgraph 的分工（别合并）: 那个要的是"取一块子图去归纳"（1-hop
       会把 belief/entity 一起带进来, 排序按 significance 是组织视图的口径）;
       这里要"此刻跟这句话有关的 1~2 条旧事" ⇒ 按 significance 排会变成
       **永远想起最重要的那条** ⇒ 同一条边反复 ⇒ 群永远长不出成员
  · 宁缺勿错: 空 query / 空库 / 一条都不像 ⇒ **返 []（这一轮就不注）**
recall_config.py
  · [recall].turn_k = 2 · turn_budget = 700（"取几条"类, **不是阈值**）
mmt/engine.py
  · agent_turn 加 **P19 槽位** —— ⭐ **进 notes（动态尾, history 之后）, 不进 system**:
    查询是玩家这一句 ⇒ 每轮都变 ⇒ 进 system 就逐轮破前缀缓存（tail.py 的不变式）
  · 位置: 时间注记之后、task 卡之前; wstore 提到 try 外**复用**（省一次读盘）
  · ⭐ 新构造参数 `embed_fn=`（接缝）—— 别 patch 模块属性（split-guard 会拦:
    core.mmt.engine 是拆分目标, patch 模块属性将来**静默失效**）
判据（已过）
  · 真机 18 条标题全唯一全非空; brain 段 4309 → **4595**（元信息段 +286 字）
  · 8 句真问题命中 **4/8**; 无 embed 服务 ⇒ 自动退词面（不是不召回）
  · 落点守门: 召回段**不许出现在 system 里** · 事件名不被转换 · 无命中不注
  · 形状守门: 元信息段里**不许出现 `·`**（那是事件名里会有的字符, 不能当边界）
  · ⚠️ **全文注入是用户裁决**（"实在不行 digest 的时候让 LLM 精简即可"）
  · 括号清单 = `docs/CONTEXT_MARKS.md`（一形一义）
```

### N5b 发现（行的第三类）—— ✅ **已落地 2026-09-29**

```
mmt_lines.py  · KIND_NOTICED = "noticed"（**顶层键, 不套 action 信封**）· KINDS 三值
              · 判别键扩成"**恰好其一**" · 值必须是非空字符串（只判形状）
mmt_check.py  · 想起行**不计入"整轮只有它一条行"**（它是账目不是内容 ⇒ 不产假硬问题）
engine.py     · `_accept_row` 收在手里（不进 held/deferred; reask 轮也收; void 则丢）
              · `_finish()`（**两个成功出口收成一个** —— 陷阱 48）→ `_log_notices`
              · 落账时机 = **本轮内容行交付之后**（seq 顺序 = N5c 归属正确的前提）
              · 台账 `mmt_noticed hit= / drop=miss|ambiguous|empty said=`
events.py     · TYPE_NOTICED 进 NON_CONTENT_TYPES ⇒ 三处自动生效（历史/digest/气泡）
address.py    · ⭐ 新件: `normalize_title` + `find_episode`（`look` 将来共用同一份）
              · 只剥格式（`《》〈〉<>【】〔〕` + 半全角引号 + `｜` 取第一段）· 不做近似匹配
              · 命中 0 / 歧义 ⇒ **不猜**
schema.py     · 两类行 → 三类行 + 硬规则 1/6 + **一个示例**（示例才是形状的来源）
momotalk_rules.md · 【想起的事（可选——想起来才写）】
render.py     · P19 段末加 `RECALL_ACTION_HINT`（⭐ **候选旁的提示**）
判据（已过）
  · 编造的引用被丢 · 同名歧义不猜 · 带书名号/引号/整段都命中
  · 账可查（事件流里那一条）· **不进对话历史**（非内容事件）
  · 只有账没说话 ⇒ 不静默成功（契约硬规则 6 的对应行为）
  · 旧形状零影响（没写 ⇒ 事件流与改动前同形）
⭐ **真机 A/B 实测（2026-09-29, deepseek-flash + main=high, haruka 真档, 4 轮/组）**:
  · 抄写形态: 三组共 6 笔**全部原样逐字命中**, 零变形 ⇒ 规范"不带书名号"成立
    （B 组"照抄整段"唯一那笔带上了书名号 ⇒ 多一层归一依赖）
  · ⚠️ **瓶颈是"写不写"**: 动作只写在规则书里 ⇒ 2/4 轮写了, 且**最该写的那轮**
    （召回段正摆着两条苔藓、「她话里也提到了」）没写;
    挪到**候选旁**（P19 段末一句）⇒ **3/4 轮写了、最该写那轮写了**; 无关轮两组都不写。
    ⇒ 结论: 缺的是**触发**不是**格式**; 动作必须贴着候选。
```

### N5c L1 落地（补 akin 边）—— ✅ **已落地 2026-09-29**

```
digest.py · 新 `_link_akin(store, episode_ids, noticed, ts=)`
  · 位置 = **建完 episode 之后的第一件事**（边两端都已是真节点 ⇒ 不违 `add_edge` 拒悬空）
  · ⭐ 归属判据 = "该账**之前**、最近的、**被某条 episode 认领**的内容事件"
    （`bisect` 在认领 seq 集合里取 ≤ noticed.seq 的最大者）
    ⚠️ **不是"区间包含"**: `noticed` 是非内容事件, 它自己的 seq 不在任何
      episode 的 `event_seq` 里（`new_events` 按 `is_content_event` 过滤）⇒ 永远落空
    ⚠️ **依赖 N5b 的落账时机**（账写在那一轮她的话**之后**）—— 否则归属落到上一轮
      （静默错归属: 边连到错误的记忆上）。专用反证用例钉住
    ⚠️ 区间会交叠（真机 m0015 ⊃ m0016）⇒ 同一 seq 可能两个主人, 取**靠后**那条
  · 一跳都不猜: 找不到归属 / 目标不在库里 ⇒ **不落边 + 台账**
  · 幂等: `add_edge` 同 (rel,src,dst) 跳过; ⚠️ `akin` 对称 ⇒ **方向不进边表**
    （只在台账里 —— 这是有意的: "她觉得这两条像"本来就不带方向）
  · 台账 `digest_akin edges= unclaimed= self=` + 每边一行 `new= old=`
判据（已过）
  · 命中落边 · 重跑只出一条边 · 对称边反着写不新增 · 账太早 ⇒ 未认领
  · 本段没产出 episode ⇒ 未认领 · 目标不存在 ⇒ 跳过（不抛）· 自环 ⇒ 跳过
  · 没有账 ⇒ 零影响
⚠️ **待裁 #7（未认领要不要下次 L1 重扫）**: 2026-09-29 用户裁决 = **先丢 + 看台账**,
   真机上 `unclaimed` 多起来再谈（重扫要新存"未认领水位", 而"零新存储"正是这条设计的好处）
```

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
  · validate(): group 不走 belief 的来源护栏（⏸ 原文写的是"epistemic 护栏"——那个字段
    2026-09-29 已退役, 今天的护栏是"belief 不许带 observer"）
graph.py
  · REL_MEMBER_OF = "member_of"（episode → group）· RELS: 8 → 9 条 · **有向**（不进 SYMMETRIC_RELS）
  · _ABOUTABLE 加 "group"（群可归属 entity; 今天零写者 —— 先开接口, 别锁死）
渲染 / 契约 / bucket: ✅ **零改动**（群不进常驻注入，只是 index 的原料）
判据
  · group 节点 to_dict/from_dict 往返稳定；没 title 被拒
  · 成员 = edges_to(gid, "member_of")；⭐ **一个 episode 可同时在两个群里**（多归属）
  · audit() 不把 group 当 belief 报"无支撑"
```

### N2 视野补齐（这条最便宜、收益最直接）—— ✅ **已落地 2026-09-29**

```
render.py
  · ⭐ render_cognition_line()（**新, 两个调用者共用**）:
      认知行 = `〔u0001｜belief｜被引 3｜sig 0.97〕subject：正文` + 缩进续行 `edges: …`
      · 「被引」对 belief/promise 也印（今天只对 experience 印"次数"）
      · 边只印**能指认的**两端: 认知→本地号 · episode→**真实 id** · 其余只计数
        （`（另有 N 条边指向列表外）` —— **绝不编一个看不到正文的号**）
      · 边封顶 6 条（`被引 N` 已经说明有几条 —— 少花 ≠ 少信息）
      · ⚠️ 顺手修: `subject` 不再前置"关于"（真机里它本来就写成「关于 我道歉的习惯」⇒ 老形态是「关于 关于 …」）
  · render_cognition_list 改用它; render_organize_view **本体不动**
digest.py
  · `_round_b_material`: 新经历行 `m0025 「标题」 正文` → `〔m0025｜《标题》〕正文`
    ⚠️ 原来 `「」` 与她视图里"逐字原话"**同形不同义**（`CONTEXT_MARKS` 的活）
  · 候选行从「只有编号」→ **每条一行**: `〔u0001｜belief｜被引 3〕正文` + 边续行 + `为什么: …`
recall.py
  · `recommend_candidates` 加 `why_out`（**可选传出, 不改返回签名**）:
    `语义 0.72` / `tags[…] 命中` / `subject 点名` / `2-gram 0.41`
    ⚠️ `_keyword_candidates` 里必须**逐次比较时记**（事后重算 = 第二个真源）
判据（已过）
  · 真机渲染一次（**零 LLM 调用**: 纯函数）: `edges:` **4 行** · `被引` **4 处** ✓
  · ⚠️ 真机候选为**空**（embed 服务没起 ⇒ 词面路径 0 命中）—— 陷阱 38 的又一次现身;
    why/候选正文这一半在真机上要等 `lms server start` 才看得见
```

> ⚠️ **原 N2 那条"接线 render_organize_view 的边渲染"的落实方式**（2026-09-29 判断）:
> **不去调用那个函数**（它是零产品调用者的**旧**组织视图: 印真实 id、无本地映射、
> 分不出"能 touch / 能 link"）, 而是把它的**边渲染语法**接进真正在跑的
> `render_cognition_list`。函数本体保留（N6 候选池 / 将来组织视图还要用）。

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
