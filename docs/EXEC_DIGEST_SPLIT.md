# EXEC_DIGEST_SPLIT.md — digest **按轮拆包 + 命名对齐**（动工文档）

> **状态**：✅ **拆包两刀全部落地（乙-1 + 乙-2, 2026-09-29）** —— 四条待审已裁（§5）。
> `rounds/` 包拆完: `core/digest/pipeline.py` **672 → 479 行**（`digest_segment` **376 → 170**）;
> 轮次命名对齐: key ≡ 契约相位 ≡ 标签后缀, `label`/`prompt`/`phase` **由 key 派生**,
> prompt 文件改名 `digest_<key>.md`, 日志第一段恒为轮名（守门 `test_digest_naming_guard.py`）。
> **下一步 = §7 的逐层刀**：✅ L1 的 **D1 已落**（§10）· ⬜ 接着是 **L2（E1 认知列表按相关度 /
> D2 时间线去留）** 与 **L3（B1+A2 归属的进与出）**；L1 还留了一刀 **D2 补全**（用户裁决"另开"）。
> **上游**：`core/digest/rounds/__init__.py`（轮次表）· `docs/DESIGN_DIGEST_LAYERS.md`（三层视野）·
> /§9-12（每轮定义与待裁项）。
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
- ✅ 走**乙**（按轮拆包），**不用继承**（本仓无类型检查 + `` 已否决父子类 +
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

| 层 | 刀 | 落点 | 状态 |
|---|---|---|---|
| **L1** | **D1** 未认领/被丢弃的**台账出口** · D1b 一章一条是"丢"不是"合" · D1c `_find_duplicate` 判据脆弱 | `rounds/record.py` · `segment.py` · `contract/{model,digest_registry}.py` · `pipeline.py` · `core/creep/` | ✅ **已落 2026-09-29（见 §10）** |
| **L1** | **D2 补全**（本章那 3 条未认领的归口：把保留那条 episode 的 `event_seq` 并上整章）—— ⚠️ **改的是图上的数据**（连带 `emo_shape`/`place`/`place_raw`/`node.ts`），用户裁决"**另开一刀**" | `segment.py` · `episodes.py` | ⬜ 待做 |
| **L2** | **E1** R2 的认知列表按**相关度**召回（今天 `significance` 前 12 ⇒ `contradicts`/`evolved_from` 漏判的近因）· **D2** R2 还要不要吃"本段时间线"（`evidence` 删后已无消费者）· L2-b `ignite` 未开工（**群今天零读者**）· `add` 归 L2 未落 | `rounds/understand.py` · `rounds/group.py` | ⬜ |
| **L3** | **B1 + A2 一起做**（归属的**进**与**出**）：R3 池子补"本轮被 `update` 改写且没 `about` 边的旧节点"（**形式已报**：段头 `本轮新节点`→`本轮动过的节点`、被改写那行在 `〔〕` 里多一格 `改写`）+ `detach`/`merge_entity` | `rounds/attribute.py` · `core/brain/entities.py`/`revise.py` | ⬜ |
| 横切 | `_ABOUTABLE`/`_ATTACHABLE` 对齐（半天） · 三轮合并（① 记 ② 接 ③ 重看，最大） | — | ⬜ |

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
- **每轮预算** 120s + 整段硬顶 **840s**（2026-09-29 由 600 抬上来 —— 给 R0「切分」
  留第 6 个 LLM 轮的位子；600 当时已被 5 轮 × 120 顶满）；回灌走 `llm.client.feedback`（唯一实现）。
- `core/creep/`：账行**无 `seq`** ⇒ 结构性隐身（`Event.from_dict` 第一道就丢）；
  写入唯一入口 `SessionStore.append_raw_row`（与 `append_event` **共用同一把锁**）。

---

## 9. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-29 | 建文（拆包 S1/S2 已落，本文记"按轮拆 + 命名对齐"这一刀的全部前提与待审项） |
| 2026-09-29 | **乙-1 落地**：`rounds/` 包（表 · `base.py` · 六个轮文件）+ `pipeline.py` 编排循环化。四条待审已裁并入 §5 |
| 2026-09-29 | **乙-2 落地**：key→`record`/`understand`/`attribute` · 三个标识由 key 派生 · prompt 文件改名 `digest_<key>.md`（**内容一字未动**）· 常量 `DIGEST_*` · 日志一律带轮名 · 新守门 `test_digest_naming_guard.py`。⚠️ **LLM 看到的字节仍然零变化**（标签只进日志与桩分派） |
| 2026-09-29 | ⭐ **L1 的 D1 落地**：契约层 `vr.warnings` 接上出口（**从前一个字没落**）+ `ValidationResult.drops`（分类靠声明不靠文案）+ `kind=digest_gap` 一段一行 + 条目面（一章一条丢的 / 复用的）+ 审计探针。见 **§10** |

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

---

## 10. D1 落地记 —— **L1 的缺口账**（2026-09-29）

### 10.1 先纠一个数

**32% 不是"今天的病"，是逐点时代的旧账**。今天实测（`.testtmp/probe_l1_coverage.py`, 只读零 LLM）:

```
覆盖率 148/218 = 67.9%  未认领 70（67 mmt + 3 bond）
7 个段: 未认领率 0%~64%（MMT 碎聊按设计本来就 0~5 条 ⇒ 大头是**正常**）
6 章: **只有 1 章**有缺口（夏莱的大扫除前夕: 3 条 story_scene）
节点位置: 悬空 0 · 空 event_seq 2（x0000/x0001, 本来就先建）· 共享 3（R2/R3 的**段级指针**,
          本来就该落在 `interact_max` —— 不是丢区间）
```

⇒ 两个结论: ① **"未认领率"这个词有毛病**（把"闲聊"与"漏"混在一个数里）;
② 真正有信息的是**章内未认领**（章的边界是引擎已知的）。

### 10.2 真正的洞: **契约层的 warnings 一个字都没落**

`call._round_call` 只看 `vr.is_valid` / `vr.errors` ⇒ 契约层 25 种 warning **全被扔掉**,
里面有 **8 处是真的丢东西**（`_drop()` 标的那些），最狠的一条是:

> `{label} 的端点 {missing} 不在本段时间线里——丢弃` ⇒ **整条区间作废** ⇒
> 那条 episode 没有位置 ⇒ 它的内容**全变成未认领**。

⇒ 那 32% 里可能有一部分根本不是闲聊, 而是**区间被契约层丢了** —— 而原因今天看不见。
（这份档里**没有**实测到这种丢: 共享的 3 条是段级指针。但"没实测到" ≠ "没发生" —— 正因为
warning 被扔掉了, 谁都看不见。）

### 10.3 形状: 一段一行 `creep` 账（`kind=digest_gap`）

```
{"type":"creep","kind":"digest_gap","at_seq":<本段上界>,"ts":…,
 "skeptical":"…",                                  ← ⚠️ **只在真丢了内容时才有**
 "evidence":{
   "contract":{"lost":["record: episodes[0].span 的端点 [99] 不在本段时间线里——丢弃"],
               "by_round":{"record":1}},
   "items":{"in":2,"kept":2,"no_pos":1,
            "dropped":[{"chapter":"苔藓","keep":"写法乙","lost":["写法甲"]}],
            "reused":["m0001"]}}}
```

* **出口** = creep（`soul/events.jsonl` 一行**无 `seq`** ⇒ 结构性隐身, 她/窗口/digest/回放
  都读不到）—— 通道现成: `DigestResult.creep_rows` → `engine._run_digest` → `append_raw_row`。
* ⭐ **触发 = 真的丢了东西**（三选一: 契约层当场丢的 `drops` / 一章一条丢的条目 /
  判重复复用的）。⚠️ **2026-09-29 收窄过**: 从前"契约层说了任何话"就写（含"缺 tags"这种
  **建议**）⇒ 真机等于**每段一行**, 而 `grep digest_gap` 就再也挑不出真丢。
  建议类的话（健康度）走**一行日志**: `digest 契约层说了 N 句（其中丢了内容 M）: …`。
* ⭐ **只有"不可重算"的进账**（creep 自己的纪律 1）: 上面那三样**那一刻之后世上没有第二份**。
* ⛔ **可重算的进日志, 不进账**: 未认领的内容事件、章内未覆盖 —— 节点 `event_seq` +
  章 marker + `affection/digest` 的段界**都在盘上** ⇒ `probe_l1_coverage.py` 一条命令算出来。
  进账 = 存第二份真相。
* ⭐ **`skeptical` 只在真掉内容时填**（`contract.drops` 非空）: 形状建议、
  "一章一条丢掉一条冗余总结"、闲聊没成记忆 —— 都**不是**"她少了什么"。

### 10.3b ⚠️ **两种口径**（`items.no_pos`）—— 不是 bug, 但必须说清

`span` 被契约层丢掉（或她压根没给位置）的条目，会被引擎**兜底到段级指针**
（`_create_a_nodes` 的 `event_seq=[interact_max]`）。那个兜底是**文档化的有意设计**
（`test_emo_shape_absent_when_no_pointer`: 段级指针是**真的** —— 那条记忆确实产生于这一段;
而且它保住了 `_find_duplicate` 的幂等 ⇒ **不能**改成"不落位置"，那会拿幂等换好看）。

⇒ 后果: **按条目算的"未认领" ≠ 按节点算的**（兜底那条 seq 看起来已认领）。
这正是 `items.no_pos` 存在的理由 —— 把差异记成**一个数**, 而不是让它静默。

### 10.4 分类靠**声明**, 不靠文案（这一刀最容易做错的地方）

`ValidationResult` 加了一个字段 **`drops`**（`drops ⊆ warnings`）：哪些 warning 是"真丢"
由**写它的那行代码**说了算（`contract/digest_registry.py` 的 `_drop()` 那 8 处）。
⛔ 不走 `"丢弃" in msg` 那条路 —— 那是本项目 2026-09-21 栽过的坑
（`HARD_BLOCK_ISSUE_MARKS` 拿中文子串判软硬, 换个措辞就静默升级）。
同理, `evidence.contract.by_round` 按**轮次 key** 计数（结构化）, 不按文案分堆。

### 10.5 一个坑（写在这里免得下次重踩）

账**不能**在 `record` 轮里直接 append 进 `result.creep_rows` —— 那个字段在 **`COMMIT_ONLY`** 里,
**回滚不清** ⇒ 整段失败回滚了, 账还写着"这段有缺口"（描述了一件没发生的事）。
✅ 正确落法: 先落在**会被回滚清掉**的字段上（`record_gaps` / `contract_warnings` /
`contract_drops`, 全部声明在表里 ⇒ `reset_result` 由表推导）, 由**提交块**的 `_note_gap` 造行。

### 10.6 没做 / 下一刀

* **D2 补全**（章的覆盖缺口 ⇒ 把保留那条 episode 的 `event_seq` 并上整章）——
  用户裁决"**只记账, 补全另开一刀**"。⚠️ 它改的是图上的数据（`event_seq` 派生
  `emo_shape`/`place`/`place_raw`/`node.ts`）。
* **位置兜底不改**（2026-09-29 核 L1 时定的）: 见 §10.3b —— 它是文档化的有意设计,
  改它会拿 `_find_duplicate` 的幂等换好看 ⇒ 只把差异记成 `items.no_pos`。
* ⚠️ **一个边界**（不是 bug）: 没有位置的条目**逃过"一章一条"收口**（归属判据是
  "`event_seq` 与章块相交" ⇒ 无位置恒不相交）⇒ 一章可能落 2 条。不去猜它属于哪一章
  （猜错会把一条 MMT 记忆压掉）。
* **契约层别的轮的"重复丢"**（`links` 重复 / `close` 重复 / `aliases` 截断）**没进 `drops`**:
  要给它们分类就得逐站穿 `drops` 参数, 而它们不影响"内容是否进记忆"。
* **`DigestResult.created` 名不副实**（判重复时它装的是**复用**的 id）—— 只在账里
  `items.reused` 体现, **没改语义**（改它要动调用方与用例）。

### 10.7 验证

* 新用例 `tests/core/test_digest_gap.py` **10 条**（干净段不写账 · **建议类不写账** ·
  三面齐 · **无位置仍走段级指针 + `no_pos` 记账** · `skeptical` 只在真丢 · 一章一条进账 ·
  复用进账 · ⭐ **回滚不留账** · 端到端落真源且无 `seq`）。
* digest 板块 **241 passed** · `test_creep` 的"每 kind ≥3 句"守门自动覆盖新 kind。
* 契约层: `ValidationResult.drops` 落地后 `test_digest_registry.py` **36 passed**（判据没放宽）。

### 10.8 核 L1 时查清白的三件（免得下次重查）

* 节点位置体检: 空 `event_seq` 只有 `x0000/x0001`（本来就先建）· **悬空 0** ·
  18 条 episode **没有一条**是"单点兜底"的指纹。
* 那些**不连续**的 `event_seq`（如 `m0001 = [14,16,18,20,23]`）**不是异常**: 这份档全是
  **N3 之前**的逐点数据（节点 ts 都在 09-20~09-26, 而 N3 是 09-29 落的）—— 稀疏本来就该那样。
* `_find_duplicate`（判据 = kind 同 + `event_seq` 相交 + **正文全等**）在这份档里
  **从没命中过**（0 组完全相同的正文）⇒ 它是为"崩溃窗口重跑"设的安全网, 今天**未验证**。

---

## 11. D0 落地记 —— **段的推进规则**（2026-09-29）

> 用户裁决原话：*"固定每个角色说 40 轮（1/3 个 window）开始 digest 以及章闭环即可；
> 下一段的 slice start = 上一段中 slice 出的所有段中 span 右端点的最大值 + 1"*
> · 追问后补的一句：**只救尾巴**（中间空洞不重喂 —— 那些多是闲聊）。

### 11.1 它替换了什么

| | 改之前 | D0（改之后） |
|---|---|---|
| **触发** | MMT 每 **25** 轮 | MMT 每 **40** 轮（≈ 1/3 个 `window_messages(max_units=120)`） |
| **水位** | `max(窗口内全部事件.seq)` —— 触发点 | ⭐ `max(她这次**覆盖到**的 seq)` —— 她实际记到哪 |
| **没被覆盖的尾巴** | **永久丢**（水位一次推过它） | **欠着** —— 并进下一段窗口再喂一次 |
| **章的覆盖** | 她自己划 `span`（划窄了就漏） | ⭐ **引擎兜到整章**（并集） |

### 11.2 为什么"章覆盖"是**必要配套**，不是可选的另一刀

水位一旦按"她的覆盖"走，章的 episode 若没盖到章尾，那些章尾事件就留在水位之上 ⇒
下一段**重喂** ⇒ 而重喂的窗口里**没有 `vn_enter`** ⇒ `_segment_domain` 会把它们当
**孤儿章** ⇒ **可能重复记一条**。所以 `_collapse_bond_episodes` 顺手取了并集
（她声称的 ∪ 章块）—— 这也让"一章一条 = 这一章的总结"那句话从**假设**变成**事实**
（章内未认领从此不可能; §10 里说的"D2 补全"这一刀**就此消掉**）。

### 11.3 两条兜底（不配会卡死 / 发散）

| 兜底 | 不配会怎样 |
|---|---|
| **零覆盖 ⇒ 推到窗口上界**（含尾部 marker/账目） | MMT 碎聊本来就允许 0 条 ⇒ 水位不动 ⇒ 下一段窗口照旧 ⇒ **永远卡在同一段** |
| **窗口内容事件 > `DIGEST_WINDOW_EVENTS_CAP`(=120) ⇒ 丢最老的** | 万一"她每段只覆盖前几条" ⇒ 窗口单调变长 ⇒ prompt 无限贵。保险丝留一行 `digest 窗口超限` warning |

### 11.4 ⚠️ 两个 off-by-one（都是测试当场抓的，记下来免得重踩）

1. 用户说的"右端点 **+ 1**"是**下一段的 start**，而取窗判据是 `e.seq > digested_seq`
   （**排他**）⇒ 水位要存**右端点本身**。存 `top + 1` 会**悄悄吞掉**紧邻的那一条
   （`test_dedupe_on_rerun` 抓到：期望 3、实得 4）。
2. 覆盖点之后**紧邻的非内容事件**（marker / 账目）要**一起吞掉** —— 它们本来就属于这一段;
   停在最后一个内容事件上会让尾部账目永远留在窗口里
   （`test_affection_markers_excluded_from_digest_input` 抓到）。碰到**内容事件**立刻停
   —— 那是欠着的尾巴。

### 11.5 可观测

`digest_record span=… 认领=… 未认领=… 共享=… 章内未覆盖=… 无位置=… 未认领seq=…`
—— ⚠️ **未认领现在在"章收口之后"重算**（并集改变了覆盖）⇒ 这个数与**节点上的覆盖一致**，
§10.3b 说的"两种口径"在章这一侧消失（mmt 侧那份 `no_pos` 兜底仍在，照旧记着）。

### 11.6 验证

* 新用例 `tests/core/test_digest_window.py` **7 条**（覆盖决定水位 · 尾部非内容事件一起吞 ·
  零覆盖推进 · **中间空洞不重喂** · 章覆盖兜满 · 整章消化后无欠账 · 窗口超限丢最老的）。
* digest 板块 **250 passed**（上一刀 243 + 7）。

---

## 12. 约定改造成"她随身带着的事"（`pinned`）—— **第 1 步已落（2026-09-29）**

> 起因：用户提 *"promise 要不要换一个说法……note 只记 LLM 觉得重要的事情，LLM 可以实时
> markdown 重要的誓约话语，然后 close 后统一走 L1 变成固化 episode 节点"*，随后自己否掉了
> "固化节点"（*"真的需要新节点吗，因为我们是知道来源的……在 tag 里面增加一个 `#vow`
> 就可以轻松定位了"*），命名最后落在 **`pinned`**（*"假如重要的事情都可以进note，
> 那vow其实有点不够看"*）。

### 12.1 六条裁决

> ⚠️ **2026-09-29 收尾时两条被推翻**（用户看过 R0 的最终形态之后裁的）——
> ②③ 作废, ④⑤⑥ 保留。**R0 那条线**（`§13`）把"约定从哪来"整个换掉了。

| # | 裁决 | 状态 |
|---|---|---|
| ① | **判据**：**说定的将来 + 值得随身带着** —— 二者其一: *"忘了它就是说话不算数"* **或** *"哪怕你觉得自己不会忘，它也该在手边"*（誓约/重大的约定）· ⛔ 日常安排 / 事务待办 / 此刻的心情 / 已经发生的事 | ✅ **已落**（判据搬进 R0 的 `KEEP_SEMANTICS`，见 §13） |
| ② | ~~**实时 mark**：MMT 加第四类行 ⇒ 当场 append~~ | ⛔ **推翻** —— 地址只有 digest 那一刻才拿得到（真机那两条约定与来源经历**同分钟** ⇒ 延迟≈0）; 行类型 3→4 的成本/频率比差。**MMT 不加写路径** |
| ③ | ~~**结清并入 L1** ⇒ **R4 整轮删掉**~~ | ⛔ **推翻** —— R4 留着: 它是**唯一不对着切片干活**的那一轮（`RoundSpec.needs_segments=False`, 吃的是备忘录）, 而约定的翻篇可能正好落在"空骨架"那一段 |
| ④ | ⭐ **不建固化节点**：close 指到的那条 episode 打 **`#pinned`** tag | ⬜ 待做（要动已提交节点, 走 `revise` 通道） |
| ⑤ | 结清的条目**不退场**（"结清 ≠ 划掉"）⇒ 需要一条**淘汰规则** | ⚠️ **前提已变**（§13: 约定现在长在它自己那条 episode 上 ⇒ 退场不再等于消失）⇒ 与淘汰规则一并重裁 |
| ⑥ | **失约 / 无疾而终**（指不到 episode）⇒ **给它一条 episode**（位置从 `refs` 继承） | ⬜ 待做 |

⭐ **`keep=always` 的约定从哪来 —— 最终形态在 §13**（R0 出 `keep` · R1 填骨架 ·
它自己那条 episode 当 `refs` · `src` 做去重键）。

### 12.2 第 1 步落了什么（判据与命名）

* **判据与例子**（`digest_record.md` + `digest_close.md`）—— ⭐ **病根就在这两处**: 原来的例子
  （*"明天带猫粮去喂猫""下周去看烟火""周六去模型店"*）**本身就是"安排"**, 还标着"最高优先"
  ⇒ 模型照抄示例的形状（本项目自己的教训：*示例才是形状的来源*）。真机那两条与示例同形。
* **改名 `promise` → `pinned`**（槽 + `NotesState` 字段 + 结局词表 `PROMISE_OUTCOMES` →
  `PINNED_OUTCOMES` + digest 表里的 `note` 面）。
  ⚠️ **磁盘影响**: 事件流的 `add`/`close`/`retire` payload **不带槽名** ⇒ **真源零影响**;
  只有派生缓存 `notes.json` 有那个键 ⇒ `from_dict` **兼容读旧名一次**（真机那 2 条约定照旧读得出来,
  再存一次自动改写成 `pinned`）。
* **tag = `#pinned`**（英文 + `#` 前缀把"元标记"和内容词分开）。⚠️ 真机已有 **6 条 episode**
  打着旧的中文 tag「约定」—— 今天**没有任何代码按 tag 值筛**（筛选全是通用字面匹配）
  ⇒ "认两个"无处可落, **不建常量**, 只在文档记着（将来做筛选时要认两个）。
* ⭐ **`check()` 的两条判据换成一条"总量"**（用户裁决）: 从前的 `MAX_PROMISE=5`（每槽条数）与
  `MAX_CLOSED_PENDING=3`（结清积压）**生产里零读者**（只有测试调 `check`）⇒ 真机永远不响;
  而真机会发生的是"结清不退场 + 越记越多 ⇒ 注入块越来越长" ⇒ 改判 **`MAX_NOTE_CHARS=500`**（她真正
  在花的那个成本）。
* ⭐ **接上真读者**: `engine._write_note_ops` 写完缓存后调 `notes.check(...)` 打日志 ——
  **读者上岗当天就抓到一个真问题**: 真机那句 21 字的心境被 A 槽的"名词短语 ≤20 字"标尺误报
  ⇒ 加 `MAX_ON_MIND_TEXT=60`（与契约的 `ON_MIND_MAX` **同源**, 契约不依赖 core 所以那边有一份副本）。

### 12.3 ~~第 2~4 步的爆炸半径~~ ⛔ **②③ 已推翻, 这一节只作历史**

> **2026-09-29 收尾**: ②（实时 mark）与 ③（删 R4）都被推翻了 —— 见 §12.1 的说明。
> 下面这张表**不要再照着做**; 留下来只为"这些地方当时被摸过一遍"。

| 步 | 要碰的（~~作废~~） |
|---|---|
| ~~**2 实时 mark**~~ | `core/mmt/mmt_lines.py` · `momotalk_rules.md` · `build_line_schema`（三类行 → 四类）· `mmt_check.py` · `engine._finish_turn_lines` · ⚠️ 当场刷新注入段 |
| ~~**3 结清并入 L1**~~ | 删 `rounds/close.py` + 表里那行 + prompt + 契约相位 + 用例 —— ⛔ **R4 留着** |
| **4 打标**（⬜ 仍然待做） | close 指到的那条 episode 确保有 `#pinned` —— 要动**已提交的节点**（走 `revise` 通道）, 是这几步里唯一"改图"的 |

---

## 13. ⭐⭐ R0「切分员」—— 每段第一步（2026-09-29, **整条线已闭环**）

> ⚠️ **这一节是当前形态的唯一入口**。§12 的 ①②③ 已被它取代（那三条说的是
> "约定从哪来 / R4 去留", 答案现在在这里）。

### 13.1 一句话

digest 的**每段第一步**从"R1 自己划区间"改成 **R0**：

```
R0 切分(全覆盖 + keep) → R1 按骨架填(+drop) → close 收口 → understand → attribute → group
                              ↓ keep=always
                          note/add（refs = 它自己那条 episode）
```

**R0 只做三件事**：划区间（`span`）· 写一句 `abstract` · 标 `keep`。
⛔ 不写正文 / 不判情绪 / 不打分 / 不建节点。料 = **时间线 + 本章标题**（画面/人设/情绪标尺**不给它**
—— 切分是结构判断, 给了反而诱使它写文学化的 `abstract`）。

### 13.2 六条判据（都已落地）

| # | 判据 | 在哪 |
|---|---|---|
| ① | **`keep` 两档**: `temporary`（不记, **绝大多数**）/ `always`（誓约 · 被改了看法的时刻 · 她给自己定的规矩） | `KEEP_VALUES` + `KEEP_SEMANTICS`（判据**只在契约层**, prompt 一个字都不抄 —— 守门扫它） |
| ② | **判据一句话**: *"夸奖说的是当时, 誓约说的是往后"*；三类别记 = 日常安排 / 随口一说 / 夸奖与安慰 | 同上 |
| ③ | **全覆盖**: 时间线里的记录**一条都不许落在所有件外面**; ⚠️ **闲聊自成一件并明说是闲聊**（不许为了"连上"塞进旁边那件事 —— 那会稀释正文, 而 R1 看不见你塞进去的东西） | `_DOMAIN_CONTRACT["mmt"]` + `digest_split.md` |
| ④ | **R1 只填骨架**: `span` 退役（位置归 R0）· 新增 **`drop`**（唯一的不记方式）· ⚠️ **多写的挂在末条切片上**（一条切片能长不止一条记忆 ⇒ **不截断**）· 少写 ⇒ 没人填, ⛔ 引擎**不替她补** | `_RECORD_CONTRACT` + `_align_to_skeleton` |
| ⑤ | **`abstract` 一字段两用**: 不进 note = 给 R1 的参考书; 进 note = **就是她带走的那句话** | `KEEP_SEMANTICS` |
| ⑥ | **`keep=always` ⇒ note**: `refs` = **它自己那条 episode**（切分权在 R0 ⇒ 约定的来源是它自己那件事）· 幂等**两道**（节点面 `_find_duplicate` + 笔记面 `notes.ALREADY_PINNED` 的 `src`）· ⛔ 她 drop 掉 ⭐ ⇒ 收下裁决但**记账**（D1 的 `digest_gap`） | `rounds/record.py::_pinned_ops` + `notes.py` |

### 13.3 三条实现纪律（都不是风格问题）

* ⭐ **"区间 → 图"必须在 R0 的产出点做**: `_expand_spans`（写 `seqs`、**保留 `span`**）·
  章收口（判据换 `keep` 优先 / 跨度最长, **丢弃的区间并回**）· 覆盖率账（口径 = "切分员切到哪"）。
  谁决定形状, 谁承担后果。
* ⭐ **水位那两条铁律一行没动**（存 `top` 不存 `top+1` · 覆盖点后紧邻的非内容事件一起吞）:
  `_next_watermark` 只读 `node.event_seq` ⇒ **对展开发生在哪一轮完全透明**。
* ⭐ **空骨架 ⇒ 对着切片的那几轮都不发**（`RoundSpec.needs_segments`）——
  **只有 `close` 例外**（它吃备忘录不吃切片, 而那条约定的翻篇可能正好落在这一段）。
  水位照推（否则同一批会被反复喂给 R0, 顶到 `DIGEST_WINDOW_EVENTS_CAP=120` 就要丢最老的）。

### 13.4 还没做的（下一步的原料）

* ⬜ **真机实跑**（会调 LLM + 写盘需要用户点头）: 看 `digest_split segments=` 的分布
  （全覆盖做到没有）· `keep=always` 判得准不准 · `drop` 用得对不对 · **`MAX_SEGMENTS=20` 标定**。
* ⬜ **`retire` / 淘汰规则**（§12.1 ⑤）: 前提已变 —— 约定现在长在它自己那条 episode 上,
  "退场了就再也看不见"不再成立。
* ⬜ **§12.1 的 ④⑥**: 给 close 指到的那条 episode 补 `#pinned` tag · 失约⇒给它一条 episode。

