# EXEC_DIGEST_SPLIT.md — digest **按轮拆包 + 命名对齐**（动工文档）

> **状态**：⬜ **未开工** —— 形式已报、用户 2026-09-29 裁决"**就走乙吧**"；
> 待审的是本文 §5 那几条（包内函数名要不要带前缀等），审完即动手。
> **上游**：`core/digest/rounds.py`（轮次表）· `docs/DESIGN_DIGEST_LAYERS.md`（三层视野）·
> `core/brain/DESIGN_GRAPH_V4.md` §8/§9-12（每轮定义与待裁项）。
> **当前 HEAD**：`1706a0e`（工作树干净）。

---

## 0. 一句话

把 digest 从**按层切**改成**按轮切**（一轮一个文件，装"它的料 + 它的调用体 + 它对执行器的调用"），
同时把**轮次命名**对齐契约相位名、并让所有轮次标识带 `digest` 前缀（**零 LLM 的 `akin` 也一样**）。

---

## 1. 为什么（三条判据）

1. **改动模式是按轮的** —— 这一阶段的刀全是"给 R2 加 links""R3 补视野""R4 只产 note""L2-a 分群"，
   **没有一次是"给所有轮改料"**。按层切（`material.py` 横着装所有轮的料）与实际改动模式相反。
2. **原计划就是这么写的** —— `pipeline.py` 旧 docstring：*"把它收成声明式 spec 是下一步……
   落点就是本文件 + **`rounds/`**"*。今天只有 `rounds.py`（表），执行体还在外面。
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

## 3. 命名（对齐契约相位名 + `digest` 前缀）

### 3.1 轮次 key ≡ 契约相位 ≡ 标签后缀

| 今天 | 建议 key | 中文 |
|---|---|---|
| `round_a` | **`record`** | ① 记 |
| （零 LLM）`akin` | **`akin`**（不变 —— 它是边名，本就是动作） | 补边 |
| `close` | **`close`**（不变） | ② 收口 |
| `round_b` | **`understand`** | ③ 接 |
| `attr` | **`attribute`**（全称） | ④ 挂 |
| `group` | **`group`**（不变） | ⑤ 分群 |

### 3.2 三种派生标识都从 `key` 派生（**不手写**）

| key | 标签 | prompt 文件 | **日志第一段** |
|---|---|---|---|
| `record` | `digest.record` | `digest_record.md` | `digest_record` |
| `akin` | —（零 LLM） | — | ⭐ **`digest_akin`**（也带前缀） |
| `close` | `digest.close` | `digest_close.md` | `digest_close` |
| `understand` | `digest.understand` | `digest_understand.md` | `digest_understand` |
| `attribute` | `digest.attribute` | `digest_attribute.md` | `digest_attribute` |
| `group` | `digest.group` | `digest_group.md` | `digest_group` |

⇒ **日志第一条恒为轮名** ⇒ `grep digest_attribute` 一次拿全这一轮的日志。要改的旧名：

| 今天 | 改后 |
|---|---|
| `digest_span eps=… 未认领=…` | `digest_record span=… 未认领=…` |
| `digest_hit eps=… hit=…` | `digest_attribute hit=…` |
| `digest_a contract=bond …` | `digest_record contract=bond …` |
| `recall_write char=… eps=…`（R2 的写路径台账，**今天**没前缀） | `digest_understand recall_write=…` |
| `digest_akin edges=…` | 不变 ✓ |

### 3.3 模块级常量带 `DIGEST_`

```
MAX_FEEDBACK_RETRIES      → DIGEST_MAX_FEEDBACK
COGNITION_CAP             → DIGEST_COGNITION_CAP
ROUND_BUDGET_SECONDS      → DIGEST_ROUND_BUDGET_SECONDS
SEGMENT_HARD_CAP_SECONDS  → DIGEST_SEGMENT_HARD_CAP
_AFF_MIN / _AFF_MAX       → DIGEST_AFF_MIN / DIGEST_AFF_MAX（顺手去掉那个 "_"）
```

### 3.4 守门

源码里**不许手写**这些前缀 —— 一律 `f"digest_{spec.key}"` 派生；
加一条用例扫 `core/digest/**/*.py`（照 `test_marks_guard.py` 的形状）。

### 3.5 ⭐ 磁盘零影响

轮次 key **不落盘**：标签只进日志不进事件流；`evolution.jsonl` / note payload 里的
`add`/`close`/`touch`/`attach`/`rewrite` 是**动作名**，与轮次 key 无关（只是巧合同名，别混）。
⇒ 真机档一个字都不用动。

---

## 4. 目标形态

```
core/digest/
  __init__.py      门面（不动）
  rounds/               ← 包（原 rounds.py 变成它的 __init__.py, import 路径不变）
    __init__.py    表 ROUNDS + Cursor + budget_of + reset_result
    base.py        Ctx（段级上下文）+ RoundOut（每轮产物）
    record.py  akin.py  close.py  understand.py  attribute.py  group.py
    （每个: def run(ctx) -> RoundOut | None）
  pipeline.py      编排与事务（376 行的 digest_segment → ~150 行）
  llm_call.py      LLM 鲁棒层（不动；文档补一句"第二个调用方出现就抬到 llm/"）
  call.py          一轮调用的四件套（Ctx 的方法就是它的薄转发）
  material.py      料的公共件（短名去 "_", 由各轮文件调用）
  segment.py       这一段是什么
  episodes.py      L1 落节点
```

### `Ctx`（dataclass；只读为主）

```
只读  store · llm · events · new_all · new_events
      domain · chapters · timeline · seq_set · by_seq
      visuals · emotion_scale · character_prompt
      interact_max · digest_from · now_ts · hard_deadline
      model · temperature · max_tokens · llm_timeout · extra_body · embed_fn · aff_at_encoding
      result（DigestResult）· cursor（Cursor）
可变  episode_ids · player_ids · r2_created · resp_b     ← 跨轮产物只有这四样
方法  enter(key) · system_for(spec) · parse_for(spec, **kw) · sections_for(spec, pairs)
      · log_skip(spec) · call(spec, system, user, parse_fn) -> (parsed, resp) | (None, None)
```

### `RoundOut`

```
rows        该轮解析出来的行（各轮形状不同）
resp        原始 resp —— ⭐ R2 的 affection 在成功路径要用
swallow     我挂了但别连累整段（今天只有 L2-a）
```

### 编排（`digest_segment` 变成循环）

```
ctx = Ctx(...)                       # 建上下文（≈现状 try 之前那 20 样）
for spec in ROUNDS:                  # ← 顺序由表说了算（Cursor 仍在每轮 enter 里把关）
    out = IMPL[spec.key](ctx)
    if out is None:
        if spec.own_snapshot:        # ⭐ 表的这一格从"人读的说明"升级成"编排真按它执行"
            回滚这一步 + 把这步的 errors 挪进它的 warnings 字段
        else:
            return _fail()           # 整段回滚 + 记账（计数/放弃）
提交（save + 水位 + 清计数）
```

### 某个轮的骨架（`understand.py`）

```
def run(ctx) -> RoundOut | None:
    spec = ctx.enter("understand")
    cog_text, local_of = render_cognition_list(ctx.store, cap=DIGEST_COGNITION_CAP,
                                               exclude=set(ctx.player_ids))
    ep_text = material.round_b_material(ctx.store, ctx.episode_ids, local_of, ctx.embed_fn, ...)
    parsed, resp = ctx.call(spec, ctx.system_for(spec),
                            ctx.sections_for(spec, [...]),
                            parse_fn=ctx.parse_for(spec, episode_ids=..., target_ids=..., link_ids=...))
    if parsed is None:
        return None                      # 整段失败（编排回滚）
    ctx.r2_created = apply_decisions(ctx.store, parsed, ...)
    ctx.resp_b = resp                    # 留给成功路径
    return RoundOut(rows=parsed, resp=resp)
```

---

## 5. 已定 / 待审

**已定（用户裁决）**
- ✅ 走**乙**（按轮拆包），**不用继承**（本仓无类型检查 + `DESIGN_GRAPH_V4 §10` 已否决父子类 +
  六轮形状不统一：`akin` 不调 LLM、`group` 双执行器 + 自吞、`attribute` 两套本地号）
- ✅ key 对齐契约相位名；**所有轮次标识带 `digest` 前缀**（含零 LLM 的 `akin`）
- ✅ 先拆包，再逐层（L1 → L2 → L3）

**待审（开工前要用户一句话）**
1. **包内函数名**要不要也带 `digest_`？（我建议**不带**：包路径已是前缀，traceback 自带路径）
2. **包内文件名**要不要带？（我建议**不带**，`rounds/record.py` 已经清楚）
3. 被吞掉那一步的 `errors` 挪进**哪个** `warnings` 字段 —— 三选项：
   ① `RoundOut(swallow=True, warnings_field="group_warnings")`（**我倾向**）
   ② 编排按 `spec.result_fields` 里的 `*_warnings` 猜 ③ 统一一个新字段
4. 表要不要**真省掉** `label` / `phase` 两格（由 `key` 派生；`akin` 空）

**切两刀（每刀一提交）**
- **乙-1**：`rounds.py` → `rounds/` 包 + `base.py`（Ctx/RoundOut）+ 六轮文件搬家（纯搬家，行为不变）
- **乙-2**：命名对齐（key / 标签 / prompt 文件 / 常量 / 日志）+ 守门用例 + 文档同步

---

## 6. 验证口径（**不跑全量**）

- 每刀：`pytest tests/core/test_digest_rounds.py tests/core/test_digest_skip.py
  tests/core/test_wiki_digest.py tests/core/test_round_*.py tests/core/test_digest_akin.py
  tests/core/test_mmt_digest.py tests/core/test_split_safety.py tests/core/test_creep.py -q
  --basetemp=.testtmp/pw` + `pytest --collect-only -q tests`
- 改名那刀额外：`tests/core/test_stub_dispatch_guard.py`（标签词表）+ 全量只在**关键节点**跑
- 全量历史：**1150 → 1184 → 1185 collected**（最近一次 `tests/core` 1024 + `webgui/llm/renderer` 161）

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
