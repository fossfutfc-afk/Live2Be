# EXEC_DIGEST_SPLIT.md — digest **按轮拆包 + 命名对齐**（动工文档）

> **状态**：✅ **拆包两刀全部落地（乙-1 + 乙-2, 2026-09-29）** —— 四条待审已裁（§5）。
> `rounds/` 包拆完: `core/digest/pipeline.py` **672 → 479 行**（`digest_segment` **376 → 170**）;
> 轮次命名对齐: key ≡ 契约相位 ≡ 标签后缀, `label`/`prompt`/`phase` **由 key 派生**,
> prompt 文件改名 `digest_<key>.md`, 日志第一段恒为轮名（守门 `test_digest_naming_guard.py`）。
> **下一步 = §7 的逐层刀**（L1 D1 → L2 E1/D2 → L3 B1+A2）。
> **上游**：`core/digest/rounds/__init__.py`（轮次表）· `docs/DESIGN_DIGEST_LAYERS.md`（三层视野）·
> `core/brain/DESIGN_GRAPH_V4.md` §8/§9-12（每轮定义与待裁项）。
> **当前 HEAD**：乙-2 那一笔（本文与它同批提交）。

---

## 0. 一句话

把 digest 从**按层切**改成**按轮切**（一轮一个文件，装"它的料 + 它的调用体 + 它对执行器的调用"），
同时把**轮次命名**对齐契约相位名、并让所有轮次标识带 `digest` 前缀（**零 LLM 的 `akin` 也一样**）。

---

## 1. 为什么（三条判据）

1. **改动模式是按轮的** —— 这一阶段的刀全是"给 R2 加 links""R3 补视野""R4 只产 note""L2-a 分群"，
   **没有一次是"给所有轮改料"**。按层切（`material.py` 横着装所有轮的料）与实际改动模式相反。
2. **原计划就是这么写的** —— `pipeline.py` 旧 docstring：*"把它收成声明式 spec 是下一步……
   落点就是本文件 + **`rounds/`**"*。节点 C 先立了表（`rounds.py`），执行体还在外面
   —— **乙-1 把这一步走完**。
3. **它让"逐层推进"有落点** —— L1 的刀落 `rounds/record.py`、L2 的落 `rounds/understand.py` /
   `close.py`、L3 的落 `rounds/attribute.py` ⇒ 不用再想"这刀该改哪个文件"。

**现状数字（2026-09-29 量）**：一轮的定义散在 **6 处**（表 · prompt · 契约 schema · 契约 parse ·
料 · 调用体 · 执行器）+ 测试 = 7 处。

| 轮 | prompt | 契约 schema | 契约 parse | 调用体(pipeline) | 执行器(brain) | 合计 |
|---|---|---|---|---|---|---|
| `round_a` | 82 | 26 | 42 | 56 | 78 | 284 行 |
| `close` | 30 | 34 | 46 | 35 | 52 | 197 行 |
| `round_b` | 62 | 45 | 101 | 36 | 119 | 363 行 |
| `attr` | 29 | 36 | 53 | 45 | 71 | 234 行 |
| `group` | 40 | 49 | 103 | **181** | 93 | 466 行 |
| `akin` | — | — | — | 9 | 64 | 73 行 |

**六处里三处必须留着**（有理由的分家）：`llm/prompts/*.md`（人可改的文案）·
`contract/digest_registry.py`（契约层不依赖 core）· `core/brain/revise.py`/`groups.py`（数据层零 LLM）。
**可以合而没合的是两处**：料的正文 + 调用体。

---

## 2. 现状审核（拆之前必须记住的）

### 2.1 段级共享上下文（进 `try` 之前建好）

| 组 | 内容 | 谁用 |
|---|---|---|
| 引擎 | `store` · `llm` · `result` · `snapshot` | 全体 |
| 模型参数 6 件 | `model` `temperature` `max_tokens` `llm_timeout` `extra_body` `hard_deadline` | 全体 |
| 段级料 | `timeline` | R1 · R2 |
| ⚠️ **只归 R1** | `seq_set` · `by_seq` · `domain` · `chapters` · `visuals` · `emotion_scale` · `aff_at_encoding` · `on_mind_box` | R1 |
| 跨轮常用 | `character_prompt`（R1/R2/R3）· `interact_max`（R1/R2/R3/L2-a/失败路径）· `now_ts`（**每个建节点的地方**） | — |
| 筛选源 | `events`（全量，含 marker/账目）→ R4 的 `notes_state` + 成功路径 `max(seq)`；`new_all` → `_segment_domain` + 筛 `noticed` | — |
| 失败路径 | `digest_from` · `write_ledger` | — |
| 只归 R2 | `embed_fn` · `store.char_id` · `COGNITION_CAP` | R2 |

### 2.2 跨轮依赖**只有三条** + 两样机制

1. `episode_ids` / `player_ids` —— R1 → R4 / R2 / R3
2. `r2_created` —— R2 → R3
3. ⭐⚠️ **`resp_b`** —— R2 → **成功路径**（`result.affection_delta = _clamp_aff(resp_b.get("affection_exp_delta"))`
   在 `try` **之外**）⇒ **每轮的返回值不能只有"解析出的行"，必须带上原始 `resp`**（最容易漏）
4. **游标 `cur`** —— 跨轮共享（每轮开头 `cur.enter(key)`）
5. **`_fail()` 闭包** —— 每轮失败都要能"申请整段回滚"

### 2.3 四个硬骨头 + 解

| # | 骨头 | 解 |
|---|---|---|
| 1 | `_fail()` 捕获 store/snapshot/result/… | **每轮返回 `None` = 我失败了**，由编排统一 `_fail()`（每轮不管回滚怎么滚） |
| 2 | `resp_b`（affection）跨轮 | 每轮返回小结构 `RoundOut(rows, resp, …)` |
| 3 | L2-a 的 181 行大半是"失败自吞"样板 | 变成**表驱动**：`spec.own_snapshot` 由**编排**执行（取快照 / 失败时按它决定滚不滚） |
| 4 | 游标跨轮 | 同一个 `Cursor` 实例放进 `Ctx` |

---

## 3. 命名（对齐契约相位名 + `digest` 前缀）—— ✅ 乙-2 已落

### 3.1 轮次 key ≡ 契约相位 ≡ 标签后缀

| 今天 | 建议 key | 中文 |
|---|---|---|
| `round_a` | **`record`** | ① 记 |
| （零 LLM）`akin` | **`akin`**（不变 —— 它是边名，本就是动作） | 补边 |
| `close` | **`close`**（不变） | ② 收口 |
| `round_b` | **`understand`** | ③ 接 |
| `attr` | **`attribute`**（全称） | ④ 挂 |
| `group` | **`group`**（不变） | ⑤ 分群 |

### 3.2 三种派生标识都从 `key` 派生（**不手写**）—— ✅ 已落

`RoundSpec` 上现在有 **4 个只读 property**（`name` / `label` / `prompt` / `phase`），
表里**不再有** `label` / `prompt` / `phase` 三格，只有一格 `llm: bool`（`akin` 填 `False`）:

| key | 标签 | prompt 文件 | **日志第一段** |
|---|---|---|---|
| `record` | `digest.record` | `digest_record.md` | `digest_record` |
| `akin` | —（零 LLM） | — | ⭐ **`digest_akin`**（也带前缀） |
| `close` | `digest.close` | `digest_close.md` | `digest_close` |
| `understand` | `digest.understand` | `digest_understand.md` | `digest_understand` |
| `attribute` | `digest.attribute` | `digest_attribute.md` | `digest_attribute` |
| `group` | `digest.group` | `digest_group.md` | `digest_group` |

⇒ **日志第一条恒为轮名** ⇒ `grep digest_attribute` 一次拿全这一轮的日志。改过的旧名:

| 今天 | 改后 |
|---|---|
| `digest_span eps=… 未认领=…` | `digest_record span=… 未认领=…` |
| `digest_hit eps=… hit=…` | `digest_attribute nodes=… hit=…`（`eps` 是误称, 它数的是**节点**） |
| `digest_attr table=… …` | `digest_attribute table=… …` |
| `digest_a contract=bond …` | `digest_record contract=bond …` |
| `digest_akin edges=…` | 不变 ✓ |
| `recall_write char=… eps=…` | ⏸ **不动**（见 §9 遗留三条: 那行由 `core/brain/read/recall_ledger.py` 打,
它本来就只有一处、名字唯一, 加轮名要往 brain 传一个只为日志的参数） |

### 3.3 模块级常量带 `DIGEST_` —— ✅ 已落

```
MAX_FEEDBACK_RETRIES      → DIGEST_MAX_FEEDBACK      （call.py; pipeline 里那份死的已删）
COGNITION_CAP             → DIGEST_COGNITION_CAP     （随 R2 搬进 rounds/understand.py）
ROUND_BUDGET_SECONDS      → DIGEST_ROUND_BUDGET_SECONDS
SEGMENT_HARD_CAP_SECONDS  → DIGEST_SEGMENT_HARD_CAP
_AFF_MIN / _AFF_MAX       → DIGEST_AFF_MIN / DIGEST_AFF_MAX（顺手去掉那个 "_"）
MAX_DIGEST_ATTEMPTS       → DIGEST_MAX_ATTEMPTS      （顺手对齐前缀形式）
```

### 3.4 守门 —— ✅ 已落（`tests/core/test_digest_naming_guard.py`）

两条判据（都只看**日志调用的第一个字面量** —— 扫宽了会把守门变成噪声:

`digest_segment` / `digest_retry` / `digest_schema` / `digest_registry` **不是轮名**）:

① 全包扫: 日志第一段只要是"轮名形状"，就得是**当前** key（旧名残留一律红 ——
   `segment.py` 那处 `digest_a` 就是被它抓出来的）;
② 轮文件扫: 每个轮文件里的日志第一段**等于它自己的轮名**（轮名从该文件的
   `ctx.enter("<key>")` 读出来）。

⚠️ **日志字面量本身没改成 `spec.name` 拼接**（初稿是那么写的）: 那要把前缀穿进
`_link_akin` / `_collapse_bond_episodes` 的签名，为一个日志字段付的接口噪声比收益大;
判据 ②/① 已经把"字面量与 key 对不上"这条堵死了。**实测能红**：往 `record.py` 塞一个
`digest_span`，两条判据当场都报。

### 3.5 ⭐ 磁盘零影响

轮次 key **不落盘**：标签只进日志不进事件流；`evolution.jsonl` / note payload 里的
`add`/`close`/`touch`/`attach`/`rewrite` 是**动作名**，与轮次 key 无关（只是巧合同名，别混）。
⇒ 真机档一个字都不用动。

---

## 4. 目标形态（⭐ 乙-1 已按此落地）

```
core/digest/
  __init__.py      门面（不动）
  rounds/               ← 包（原 rounds.py 变成它的 __init__.py, import 路径不变）
    __init__.py    表 ROUNDS + Cursor + budget_of + reset_result + 两个时间常量（319 行）
    base.py        Ctx（段级上下文）+ RoundOut（每轮跑完的交代）（170 行）
    record.py  akin.py  close.py  understand.py  attribute.py  group.py
    （每个: def run(ctx) -> RoundOut, 60~104 行）
  pipeline.py      编排与事务（672 → 479 行; digest_segment 376 → 170）
  llm_call.py      LLM 鲁棒层（不动；文档补一句"第二个调用方出现就抬到 llm/"）
  call.py          一轮调用的四件套（Ctx 的方法就是它的薄转发）
  material.py      料的公共件（短名去 "_", 由各轮文件调用）
  segment.py       这一段是什么
  episodes.py      L1 落节点
```

⭐ **key → 实现的那张表在 `pipeline.py` 的 `IMPL`**（不在 `rounds/__init__.py` ——
那会让"读一张表"变成"拉起整条管线"）; 守门用例钉住它与 `ROUNDS` **同序同集**。

### `Ctx`（dataclass；只读 23 + 可变 4 + 6 个方法）

```
只读  store · llm · result · cursor
      模型 6 件  model · temperature · max_tokens · llm_timeout · extra_body · hard_deadline
      本段料    events · new_all · domain · chapters · timeline · seq_set · by_seq
                visuals · emotion_scale · character_prompt · interact_max · now_ts
                embed_fn · aff_at_encoding
可变  episode_ids · player_ids · r2_created · resp_b      ← 跨轮产物只有这四样
方法  enter(key) · system_for(spec) · parse_for(spec, **kw) · sections_for(spec, pairs)
      · log_skip(spec) · call(spec, system, user, parse_fn=) -> (parsed, resp)
```

⚠️ **两处与本文初稿的差**（乙-1 动工时对着代码核出来的）:
`digest_from` / `new_events` **不进 `Ctx`** —— 零读者（前者只被 `_fail()` 用, 它仍是
`digest_segment` 的闭包变量）。Ctx 里不放没有读者的字段。

### `RoundOut`（⭐ 用户裁决: **最小形状**）

```
ok              跑成了（`skip=True` 也算跑成 —— 它是**按表跳过**, 不是失败）
skip            条件不满足, 这一轮没跑（日志文案来自表里的 `skip` 格）
swallow         我挂了, 但别连累整段（只有表里 own_snapshot 的那一步可以）
warnings_field  swallow 时: errors 挪进 DigestResult 的哪个字段（由**这一轮**说）
四个构造: done() · skipped() · failed() · swallowed(field)
```

⚠️ **为什么不带 `rows` / `resp`**（初稿里有）: 五轮解析出来的行都在**各自文件里当场消费掉**
（建节点 / `apply_decisions` / `apply_attribution` / `apply_groups`）, 外面**零读者**;
R2 那份原始 `resp` 有唯一读者（成功路径的 `affection_exp_delta`）而它走 `Ctx.resp_b`
—— 返回值里再带一份就是同一个事实的两条通道。

### 编排（`digest_segment` 里剩下的那十来行 —— 真代码）

```
for spec in ROUNDS:                       # 顺序只由表说了算, 循环里不写任何一步的名字
    snap = store.clone_state() if spec.own_snapshot else None   # 自吞那一步先取快照
    err0 = len(result.errors)
    out  = IMPL[spec.key](ctx)
    if out.ok: continue                   # 跑成 / 按表跳过
    if not out.swallow: return _fail()    # 整段回滚 + 记账
    _swallow(store, spec, result, out, snap, err0)   # 只回滚它 + errors 挪进 warnings
```

⭐ `spec.own_snapshot` 从"人读的说明"升级成**编排真按它执行**; `_swallow` 里两条
当场炸的判据（表说不能自吞 / warnings_field 不在表里）保证它不会静默漂移。

### 某个轮的骨架（`understand.py` —— 真代码的形状）

```
def run(ctx) -> RoundOut:
    spec = ctx.enter("round_b")            # 越序当场炸
    cog_text, local_of = render_cognition_list(ctx.store, cap=COGNITION_CAP, ...)
    ep_text = _round_b_material(ctx.store, ctx.episode_ids, local_of, ...)
    rows, resp = ctx.call(spec, ctx.system_for(spec),
                          ctx.sections_for(spec, [...]),   # ← 逐字校对料的段标题
                          parse_fn=ctx.parse_for(spec, ...))
    if rows is None:
        return RoundOut.failed()           # 整段失败（编排回滚）
    ctx.r2_created = apply_decisions(ctx.store, rows, ...)
    ctx.resp_b = resp                      # ⭐ 留给成功路径
    return RoundOut.done()
```

---

## 5. 已定 / 待审

**已裁（用户 2026-09-29 裁决）**
- ✅ 走**乙**（按轮拆包），**不用继承**（本仓无类型检查 + `DESIGN_GRAPH_V4 §10` 已否决父子类 +
  六轮形状不统一：`akin` 不调 LLM、`group` 双执行器 + 自吞、`attribute` 两套本地号）
- ✅ key 对齐契约相位名；**所有轮次标识带 `digest` 前缀**（含零 LLM 的 `akin`）
- ✅ 先拆包，再逐层（L1 → L2 → L3）
- ✅ **① 包内函数名不带 `digest_`** —— 六轮统一 `def run(ctx)`（包路径已是前缀）
- ✅ **② 包内文件名不带** —— `rounds/record.py` 已经清楚
- ✅ **③ 吞掉那一步的 errors 走 `RoundOut(swallow=True, warnings_field="group_warnings")`**
- ✅ **④ 表真省掉 `label` / `phase` 两格**（由 `key` 派生；`akin` 空）⇒ **乙-2 做**
- ✅ RoundOut 取**最小形状**（`ok`/`skip`/`swallow`/`warnings_field`，见 §4）

**切两刀（每刀一提交）**
- ✅ **乙-1（已落）**：`rounds.py` → `rounds/` 包 + `base.py`（Ctx/RoundOut）+ 六轮文件搬家
  + 编排循环化。**行为零变化**（差量见 §9）
- ✅ **乙-2（已落）**：命名对齐（key / 标签 / prompt 文件 / 常量 / 日志）+ 守门用例 + 文档同步。
  顺手发现并处理的两笔:
  · `pipeline.MAX_FEEDBACK_RETRIES` 与 `call.MAX_FEEDBACK_RETRIES` 曾是**同一个常量的两份**
    （前者零读者）—— 乙-1 删掉那份死的, 乙-2 给活的那个改名 `DIGEST_MAX_FEEDBACK`
  · `COGNITION_CAP` 随 R2 搬进 `rounds/understand.py`（它只有那一个读者）

---

## 6. 验证口径（**不跑全量**）

- 每刀：`pytest tests/core/test_digest_rounds.py tests/core/test_digest_skip.py
  tests/core/test_wiki_digest.py tests/core/test_round_*.py tests/core/test_digest_akin.py
  tests/core/test_mmt_digest.py tests/core/test_split_safety.py tests/core/test_creep.py -q
  --basetemp=.testtmp/pw` + `pytest --collect-only -q tests`
- 改名那刀额外：`tests/core/test_stub_dispatch_guard.py`（标签词表）+ 全量只在**关键节点**跑
- 全量历史：**1150 → 1184 → 1185 collected**（最近一次 `tests/core` 1024 + `webgui/llm/renderer` 161）
- ⭐ **乙-1 实测（2026-09-29）**：digest 板块 **153 passed**（含 `test_split_safety`）·
  邻接板块 `tests/webgui` + digest 相邻 core 用例 **158 passed** ·
  `compileall` 全绿 · `--collect-only` **1185 collected**（与拆前一致）· 全量仍未跑（不是关键节点）。
- ⭐ **乙-2 实测（2026-09-29）**：digest 板块 **197 passed**（加了命名守门与两条派生判据）·
  `tests/webgui` + `tests/llm` + digest 相邻 core **213 passed** · 守门**当场验过能红**
  （塞一个旧轮名 → 两条判据都报）· 全量仍未跑。

---

## 7. 拆完之后：逐层的刀（按用户定的"讨论→实现→组织"）

| 层 | 刀 | 落点 |
|---|---|---|
| **L1** | **D1** 未认领/被丢弃的**台账出口**（今天只有一行日志；旧真机账 32% 内容事件没进任何记忆）· D1b 一章一条是"丢"不是"合" · D1c `_find_duplicate` 判据脆弱（`text` 全等） | `rounds/record.py` · `segment.py` |
| **L2** | **E1** R2 的认知列表按**相关度**召回（今天 `significance` 前 12 ⇒ `contradicts`/`evolved_from` 漏判的近因）· **D2** R2 还要不要吃"本段时间线"（`evidence` 删后已无消费者）· L2-b `ignite` 未开工（**群今天零读者**）· `add` 归 L2 未落 | `rounds/understand.py` · `rounds/group.py` |
| **L3** | **B1 + A2 一起做**（归属的**进**与**出**）：R3 池子补"本轮被 `update` 改写且没 `about` 边的旧节点"（**形式已报**：段头 `本轮新节点`→`本轮动过的节点`、被改写那行在 `〔〕` 里多一格 `改写`）+ `detach`/`merge_entity` | `rounds/attribute.py` · `core/brain/entities.py`/`revise.py` |
| 横切 | `_ABOUTABLE`/`_ATTACHABLE` 对齐（半天） · 三轮合并（① 记 ② 接 ③ 重看，最大） | — |

---

## 8. 关键事实（容易忘，别再重新推导）

- **`about` 今天没有聚合读者**（"关于某人"那条走法不存在）⇒ 真机 **14/22 个节点没 `about` 边**
  （episode 11/18 · 认知 3/4，且那 3 条全被 update/touch 动过）—— 归属的漏**今天不疼**，
  疼在接通读路径之后。
- **群（`member_of`）零读者**（L2-b ignite 未开工）· **creep 账零读者**（注入口未接）·
  **`real_clock.rewind_count` 零读者**（已实现且在跑）· **`evolution.jsonl` 零读者**（有 before/after）。
- digest **触发点** = bond 闭环（`if completed`）/ MMT 每 25 轮；**段** = 水位之后全部事件。
- **失败语义**：整批原子回滚；L2-a 自带快照（表里 `own_snapshot`）；同一段 3 次 ⇒ 放弃
  （**先记 creep 账、再推水位**到第一次失败那一窗的上界）。
- **每轮预算** 120s + 整段硬顶 600s；回灌走 `llm.client.feedback`（唯一实现）。
- `core/creep/`：账行**无 `seq`** ⇒ 结构性隐身（`Event.from_dict` 第一道就丢）；
  写入唯一入口 `SessionStore.append_raw_row`（与 `append_event` **共用同一把锁**）。

---

## 9. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-29 | 建文（拆包 S1/S2 已落，本文记"按轮拆 + 命名对齐"这一刀的全部前提与待审项） |
| 2026-09-29 | **乙-1 落地**：`rounds/` 包（表 · `base.py` · 六个轮文件）+ `pipeline.py` 编排循环化。四条待审已裁并入 §5 |
| 2026-09-29 | **乙-2 落地**：key→`record`/`understand`/`attribute` · 三个标识由 key 派生 · prompt 文件改名 `digest_<key>.md`（**内容一字未动**）· 常量 `DIGEST_*` · 日志一律带轮名 · 新守门 `test_digest_naming_guard.py`。⚠️ **LLM 看到的字节仍然零变化**（标签只进日志与桩分派） |

### 乙-2 的三条**遗留**（没做 —— 要不要做由用户定）

| # | 遗留 | 为什么没做 | 代价 |
|---|---|---|---|
| 1 | 契约层的 `parse_round_a` / `parse_round_b` 仍是旧名 | 契约是**独立面**（`contract/` 不依赖 core），且改名要动 `tests/core/test_digest_registry.py` 里 **60 多处**引用 | 半小时机械活 |
| 2 | `material._round_b_material`（+ 测试文件 `test_round_b_view.py`）仍是旧名 | 不在 §3.2 列的那三条派生标识里; 改名要连带改 `core/brain/read/{render,recall_ledger}.py` 两处注释 | 十分钟 |
| 3 | `recall_write char=… eps=…` 那行日志没加轮名 | 它由 **`core/brain/read/recall_ledger.py`** 打（读路径台账自己的行）—— 要加前缀就得让 brain 收一个"只为日志"的参数; 而这个名字**全仓唯一**, `grep recall_write` 本来就能一次拿全 | 十分钟 |

### 乙-1 的**行为差量清单**（"纯搬家"到底动了什么 —— 只有这三条，都可核对）

| # | 差量 | 为什么 |
|---|---|---|
| 1 | ⭐ `akin` 没账时**多一行日志** `digest_akin 跳过（本段没有想起账）` | 表里那格 `skip` 从前**零读者**（静默跳过）; 现在五个轮一致走 `ctx.log_skip` |
| 2 | 删掉 `pipeline.MAX_FEEDBACK_RETRIES`（**死常量**） | 与 `call.py` 那份是同一个值的**两份**，而 pipeline 那份零读者 |
| 3 | `COGNITION_CAP` 从 `pipeline` 搬进 `rounds/understand.py` | 它只有 R2 一个读者; 留在 pipeline 会形成 `rounds → pipeline` 反向 import |

**除这三条之外**：每轮的料（段标题逐字校对）· 调用顺序 · 跳过判据 · 回滚语义 ·
日志文案 · 落库形状 · LLM 看到的每一个字节 —— 全部逐字不变。
守门用例按新结构改写（`IMPL` 同序同集 · 调用点扫 `rounds/` · `span` 展开顺序看 R1 的 `run`）,
**判据一条都没放宽**。
