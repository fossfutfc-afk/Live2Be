# PROCEED.md — **接续用**（整篇覆盖写；上一版见 git 历史 `e9509ee`）

> 位置（2026-10-08）：**`mmt_look`（她主动翻自己的记忆）第 2 件已落 = 真执行器**，
> 她现在能真的翻到东西并接着说。提交 `ada7199` · 树干净 · **ahead 31（未推送）**。
> ⭐ **下一步 = 第 3 件：契约文案**（她每轮都看到的那一份）—— 然后 4/5/6 件见 §1。

---

## 1. 下一步该怎么做（每件一个提交 + 用户审一关）

### 第 3 件 · 契约文案 ← **现在做这个**
- `contract/schema.py::build_line_schema`：① 编号硬规则加一条"`mmt_look` 是**单独一轮**"
  （照 #5 `mmt_inspect_character` 那条的形状）；② ⭐ **示例块加一条"先翻再答"的**
  （**示例才是形状的来源**——真机 art 命中率 0/5 就是栽在示例上）。
- ⚠️ 它进 **system 盒A** ⇒ 改完必须 `PROMPTKIT_UPDATE_FIXTURES=1 pytest
  tests/core/test_promptkit_baseline.py` **+ 人审 git diff**（只允许有意的内容变更）。

### 第 4 件 · 规则书专段
- `llm/prompts/momotalk_rules.md`：「操作使用时机」加一行（照 `· sensei 深挖… → mmt_inspect_character`）
  + 一个**专段「回忆是动作，不是习惯」**：什么时候翻 / 什么时候**不**翻（别每轮翻、它比说话慢、
  不确定就问老师）/ 翻不到怎么办 + **示范**。⚠️ 也在盒A ⇒ **同样刷夹具**。

### 第 5 件 · 生命周期（`type="tool"` 落库）
- `core/session/events.py`：`TYPE_TOOL` + 进 `NON_CONTENT_TYPES`（digest 不吃）;
  `core/session/renderer.py`：`tool` 分支 —— ⚠️ **必须是 `user` 角色、逐字同形**
  （`llm.client.feedback()` 就是往 messages 追加 **user** 消息; 不同形 = resume 后她忘了自己翻过什么）;
  + 落库截断（`payload.result` 有长度上限）。
- 这一步修掉**已知的半截**：现在查到的内容**只活在这一轮**（不进 `_history`）。

### 第 6 件 · digest 一处接线
- `core/digest/material.py:800` 的候选碰撞：旧件 → `like(store, RecallCtx(now, query, embed_fn), spec="digest")`;
  `like.SPECS["digest"].kinds` 改成 **`("belief","profile")`**（用户已拍："稳定认知才参与组织, episode 是流水"）。
- 台账 `recall_write … mode=` → `spec=digest` + `skip=`。

### 收尾
- 本文件覆盖写 + 推送：`git -c http.proxy= -c https.proxy= push origin master`（ahead 31）。

### 押后（不做, 除非用户点名）
`cap + 标题清单`（常驻注入今天仍是全量 5204 字/30 行, 与 `look` 是三件套）· `part_axis`（topics 相交, 料只 3/21）·
**specificity 加权**（HippoRAG 的 `1/|Pᵢ|`, 治「老师」车道 48% 的天花板）· BFS 对照台 · `noticed` 带"当下的想法" ·
`emotion`/`place`/`mood` 路（缺 query 侧输入）· `emo_span`/`emo_int` 退不退契约。

---

## 2. 已落地的链（这一段 6 笔，全部已验证）

| 提交 | 一句话 |
|---|---|
| `d64c223` | 渲染收口：`render.render_candidates`（P19 与 `look` 共用一支）、P19 改候选直传、**选面归档位**（删掉渲染层的 kind 过滤） |
| `5c15554` | `read/find.py`：**锚 → 全部**（⛔ 不 top-k）。五条锚 `title`/`entity`/`group`/`when`/`text`; `Clue` = **字面**布尔式（⛔ 零 `re`）; `pack.body_of` 命中面单源 |
| `7cdcc3f` | `worldtime/when.py` + `cal.py`：**`last`（周期）/ `back`（点）两前缀** + Rust 区间 `..`/`..=` + 绝对形式 + 人话容错; 返回 `When(exact, wide, source, future)` |
| `df616a4` | `mmt_look` 第 1 件：注册 + parse + **独占** + `QUERY_ACTIONS` 接线 + 占位执行器 |
| `dd59c8a` | 线索的全角 `＆` 归一（中文输入法常见; 不归一 = 静默 0 命中） |
| `ada7199` | **第 2 件：真执行器**（三级解析 + 放宽 + 四句话 + cap 5 + `look_fn` 回调接缝） |

**验证口径**：`tests/core/test_mmt_look_action.py` 18 条 · 变异 `verify_look_red.py` **15/15 红** ·
`verify_find_red.py` 21/21 · `verify_when_red.py` 16/16 · 板块 85 passed。

---

## 3. ⚠️ 特别需要注意的（这一段踩过的坑 + 仍然有效的纪律）

### 3.1 会**静默**出错的那几处（改 `look` / 召回时必看）

1. ⛔ **两个截断机制不许叠加**：`render_candidates` 的 `cap`（条数）与 `budget`（字符）
   **互斥, cap 优先** —— 叠加就是"说好 5 条只给 2 条", 而调用方**数不出**"还有几条"。
   ⛔ **`budget=0` 的语义不许改**（既有测试把它当"极限小预算"钉住）。
2. ⛔ **`when.wide` 只能"再查一次", 绝不替代 `exact`** —— 顺序反了就是静默换掉她问的范围。
   ⭐ 而且**周期窗口不放宽**（用户裁：只有单点 ±2 天）。
3. ⛔ **①级标题命中也要过 `when`**（锚是 AND）—— 否则"上周的《某条》"会把两周前那条当命中。
4. ⛔ **时间认不出 ⇒ 不查**（不静默当成"没给时间"去查全库）；⛔ 也不报"格式错"。
5. ⛔ **回灌文案不破第四面墙**：她的视图里**不许出现**"引擎/格式/我不理解"——那是"她想不起来"。
6. ⛔ **未接线 / 无会话 ⇒ `MmtExecError`（硬）**；**"翻了没有" ⇒ `ok=True` + 人话**。两者别混。
   而**无 store 是正常降级**（连 warning 都不该有 —— 那是"降级"与"吞异常"的唯一区别）。
7. ⛔ **全角 `＆` 要归一**（中文输入法; 不归一 = 静默 0 命中）；⛔ **`｜` 与 `（）` 不许归一**
   （前者是**地址空间的字段分隔符**——她抄整段元信息进线索时归一会给出**错的**结果; 后者真档正文里有）。
8. ⛔ **变异验红的锚点会漂**：输出里出现"跳过（锚点 0 次）"= **没验到**, 不是通过。
   写完判据先问"哪支变异能让它红"; 抓不住就说明断言落在**中间量**上了（假绿）。

### 3.2 流程纪律

- 测试：`python -m pytest tests/core/... -q --basetemp=.testtmp/pw_like`（**Windows 必须预建目录**）;
  **不许频繁跑全量**（用户硬规矩）—— 按板块跑。
- ⛔ 改 `core/mmt/engine.py` 的 **import** ⇒ 刷 API 快照：`SPLIT_API_UPDATE=1 pytest
  tests/core/test_split_safety.py` + **人审 diff**（本段刷了两次, 每次 +1 / +13 行）。
- ⛔ 改**进 system 的内容**（盒A/盒B、规则书、契约）⇒ 刷 promptkit 夹具 + 人审 diff。
- ⛔ 代码字面量里**零手写** `《》〔〕｜`（`test_marks_guard`；`core/brain/` 内）—— 走 `marks.*`。
- 提交：CJK 信息走 `git commit -F .testtmp/*.txt`; **stage 显式路径**; 一笔一个可验证小板块。
- 删东西只用**显式路径**、只在工作目录内; `data/` 真档只读（写操作全在 `tmp_path`）。

### 3.3 口径（用户裁过, 不许悄悄推翻）

1. `look` 查 **`episode`** 一面（`LOOK_KINDS`, 留扩展位）· 展示 **cap 5**。
2. 时间语法：**`last` = 自然周期段 / `back` = 点**（一个前缀扛不了两族）; `..` 半开 / `..=` 闭;
   周首日 = 周一; `last 0` 是唯一被今天截断的周期; 无年份日期 = **最近一次已过**;
   落在将来 = **合法但空**（不是错）。
3. 线索 = **字面 + `&& & || |` + 半角括号**（四个运算符都认; ⛔ **不给她正则** ——
   `\d` 在 JSON 里是**非法转义**, 会打掉整行）。
4. `find` 的不变量 = **漏一条即错** ⇒ 锚里不许有打分、不许 top-k、不许截断;
   `like` 才是排序那一类。
5. embed **留在写路径/离线**, 实时注入不跑（P19 的 `turn` 档 `semantic=0`, **留行写 0**）。
6. 时间轴 = **现实日/现实年**（⚠️ 虚构年 2100 **2026-09-17 已删** —— `festivals.json`
   里那句注释当时是错的, 本段已改; 别再从它推出"她看不到年份"）。

---

## 4. 必读文件（按要动的件挑）

| 文件 | 为什么 |
|---|---|
| `core/mmt/engine.py::_look_result` | ⭐ 本段的主角：三级解析 / 宽窗 / 四句话 / 台账 / 绝不抛。下一件（契约文案）从它的**行为**倒推该教她什么 |
| `core/mmt/mmt_actions.py` · `mmt_check.py` · `mmt_executor.py` | `mmt_look` 的注册 / 独占 / `QUERY_ACTIONS` / `look_fn` 接缝 —— 加动作照这一套 |
| `core/brain/read/find.py` · `like.py` · `pack.py` · `render.py` | 两个召回类的全部形状（锚表 / 三张表 / 候选包 / 行与段头） |
| `core/worldtime/when.py` · `cal.py` | 时间语法的唯一实现（改口径只改这两处 + 它的测试） |
| `tests/core/test_mmt_look_action.py` | 一段一节长（第 1 件 / S1 各一节）—— 下一件接着加一节 |
| `.testtmp/verify_*_red.py` | 四个变异脚本（find 21 / when 16 / look 15 / like 22）—— **改代码前先看锚点** |
| `docs/DESIGN_MMT_NEW_ACTION.md` §2/§3 | `when` 与 `look` 的**设计原文**（⚠️ 部分口径已被本段推翻, 见 §3.3） |

## 5. 环境/本机

- LM Studio：`lms server start --port 1235`（只在跑 **digest**/语义探针时需要; 实时注入已不依赖它）;
  `[embed].model` 钉死 `text-embedding-qwen3-embedding-0.6b`。
- 真档：`data/worlds/world1/characters/{igusa_haruka,asagi_mutsuki}/soul/` —— **只读**。
- 提交链**未推送**（ahead **31**）; 推送：`git -c http.proxy= -c https.proxy= push origin master`。
