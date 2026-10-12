# PROCEED.md — **接续用**（整篇覆盖写；上一版见 git 历史）

> 位置（2026-10-12 深夜 / **第四版**）：**树干净 · 最新 `3ad6e71` · 已推**。
> 第三版之后又落了四件（各一个提交）：① ⭐ **entity 常驻化** —— brain 段那块
> 改成「**我知道的名字**」（全体 entity, 键面 + 看法）; ② **台账收口**（`mmt_recall`
> 加 `per=` 每段字数 + `ms=` 召回耗时）; ③ **真机观察脚本**
> `experiments/recall_report.py`（只读）; ④ 两条新守门 + 变异靶验红。
> ⏭ **下一步 = `walk` 接线**（见 §2①）+ 真机跑一次（§2④）。

---

## 0. ⭐ 召回与 `look` 的 API（2026-10-12 定；用户: "字符串/参数格式随你定, 定完了告诉我"）

```python
from core.brain.read.modes import recall, recall_with_keys, render_section, mode_of, MODES

cands      = recall(store, ctx, *, mode="turn", k=None, weights=None)
cands, keys = recall_with_keys(store, ctx, *, mode="name")     # ⭐ 带"钥匙"
seg        = render_section(cands, *, mode="name", key="阿露", empty_ok=True, **渲染参数)
```

| 参数 | 规矩 |
|---|---|
| `mode` | **形式名**（`MODES` 的键）。今天三个：`name`（set,「你想着「X」」）· `when`（set, 时间窗）· `turn`（rank, 六路兜底） |
| `k` / `weights` | ⚠️ **只有 rank 型认识**；给 set 型传 ⇒ `ValueError` |
| `key` | ⭐ **这一段的"钥匙"** = 触发它的那个词（老师用的写法 / 扫到的时间词）—— 填进 `{key}` 槽; ⛔ 带槽没值 ⇒ **当场炸** |
| `empty_ok` | `False` = **这次的"空"是被别的段去重拿走了**（不是想不起来）⇒ ⛔ 一个字都不印（印了是假话） |
| `cap` / `budget` | 渲染层的"摆几条 / 多长"（互斥, `cap` 优先）—— ⛔ 不是召回层旋钮。P19 **每段**各自读 `[recall].turn_budget`（1000） |
| 未知名 | `KeyError` + 可用清单（⛔ 不静默回落缺省） |

⭐ **加一个形式 = `MODES` 表里加一行**（⛔ 别在执行器里写 `if mode == …`）：
```python
"when": Mode(shape=SHAPE_SET, anchors=("when",), payload_from=PAYLOAD_WHEN,
             header="【你想着「{key}」那阵子——浮上来的是这些（用不用由你判断）】",
             empty="【你想着「{key}」那阵子——那几天的事，一时没想起来】"),
```
`Mode` 字段: `shape / spec / anchors / payload_from / skip_ids / kinds / order / header / hint / empty`。
⛔ **没接线的形式不许先写进表**（空行 = 假承诺）—— 所以 `near`/`echo` **不在表里**（它们的走法
接口在 `walk.py`，见 §1）。

**`mmt_look` 的三格筛选轴（AND, 2026-10-12 加 `entity`）**：
`{"action": "mmt_look", "payload": {"entity": "阿露", "clue": "便利屋 && 苔藓", "when": "上个月"}}`
· `entity` → `entities.find_entity`（**只归一格式, 不做近似匹配**; miss/ambiguous 不猜 ⇒
`LOOK_EMPTY_ENTITY` 且**不计数**）⇒ `find` 的 entity 锚 = **他车道上全部**
· ⛔ **不印 `entity.text`**（「我知道的名字」已常驻 brain 段, 再印一遍是同一份内容两次进上下文）
· 三格**至少给一个**; 三格都空 ⇒ `ContractError`。

**台账那一行（2026-10-12 加 `per=`/`ms=`，真机就靠它）**：
```
mmt_recall igusa_haruka/s123 modes=name+when(empty)+turn eps=2 name=1 when=0 chars=1000 \
           per=name:400/when:0(empty)/turn:600 ms=4.2 titles=甲 / 乙
```
· `per=` 与 `modes=` **同一套标签**（含 `(empty)`）; `sum(per) == chars` 有守门
· `ms=` = **只这一段**（召回 + 渲染）的墙钟 —— 同步跑在 `round_messages` 之前 ⇒ 进 TTFT
· brain 段另有 `recall_read surface=chara … dropped=… buckets=…known:N`（`dropped` 现在应为 0）

**设计依据**（为什么分形式、不混分; 六类范式 + 出处）= `docs/DESIGN_RECALL_MODES.md`。

---

## 1. 召回与走法的地图（`core/brain/read/` · 12 文件 · ~3600 行）

```
写侧                                  读侧 core/brain/read/
digest/material.py ─┐
rag/brain.py ───────┴→ recall.py::recommend_candidates / recall_subgraph   现役（R2 的料 + rag）
                      → render.py::render_cognition_list                   现役（relate / cognize 的料）

MMT 引擎 ─┬→ modes.recall_with_keys(mode="name"/"when") → find.find(…)
          │                                            → render.render_section ⭐ P19 前两段
          ├→ modes.recall(mode="turn") → like.like(spec="turn") → render.render_section ⭐ 第三段
          ├→ render.render_character_view                                        ⭐ brain 段
          └→ recall_ledger.log_read · recall_config（台账 + 旋钮）

`mmt_look` ─→ find.find({entity|title|text|when} = AND) → render.render_candidates（她主动翻）
⛔ 未接线: walk.py（BFS 找同类 / DFS 深挖 —— 接口 + 守门 + 13 个变异靶都在, **没有调用方**）
⛔ 未接线: channels.py + channel_impl.py + compose.py（五链路 A–E + 合成层; 只有 experiments 在跑）
⛔ legacy: recall.py::recall_episodes（P19 已改用 like/modes; 只剩测试在调）
```

| 文件 | 行 | 干什么 | 现役 |
|---|---|---|---|
| `modes.py` | ~300 | ⭐ **形式表 + 唯一前门**（`recall` / `recall_with_keys` / `render_section` / `describe`） | ✅ engine（P19 三段） |
| `like.py` | ~720 | 相似召回：`PARTS`（六路）+ `SPECS`（档位）+ `like()` + `build_ctx` | ✅ engine |
| `find.py` | 425 | 定向寻找：五锚 `title/entity/group/when/text` **AND** ⇒ 全部（不漏即正确） | ✅ engine（`look`） |
| `walk.py` | ~300 | ⭐ **走法接口**：`bfs`（找同类: 纵向参数/广度闸 `width`）+ `chain`（深挖: 来路+方向, 防环） | ⛔ **未接线** |
| `pack.py` | 136 | 候选形状 `Candidate` + 共用命中面 `body_of` + 台账行 | ✅ 包内共用 |
| `render.py` | ~840 | 一切注入视图（brain 段 / 召回段 / `look` 结果 / 认知料 / 三档空手 + 名字空手） | ✅ engine + digest |
| `recall_config.py` | 142 | `[recall]` 旋钮（`like_k`/`sim_k`/`turn_budget`/`half_life`…） | ✅ |
| `recall_ledger.py` | 174 | 读路径台账（`log_read`）+ 合成台账（`log_compose`, 那层没接线） | 半 |
| `recall.py` | 396 | 旧三通道 + 一跳（`recommend_candidates` / `recall_subgraph` 仍现役） | 半 |
| `channels.py`+`channel_impl.py` | 747 | 五链路（A 强度先验 / B 情绪 RAG / C 地点 / D 既视感 / E 认知碎片） | ⛔ 未接线 |
| `compose.py` | 345 | 五链路合成（归一 + noisy-or + 名次门槛）· `recall_now()` | ⛔ 未接线 |

⚠️ 四条事实别踩：`turn` 档 `semantic` 权重 = **0**（**召回不靠语义**）· `find` 的 `entity` 锚是
**set 语义**而 `like` 的 `name` 路**只加成不作准入**（所以两段会撞同一条 ⇒ engine 跨段去重必需）·
「提到了谁」是**字面子串**命中（`form_key` 归一后 `cf in query`）⇒ 保留号会把整条河捞出来
（`RESERVED_TRIGGERS`）· `walk.bfs` 的**渲染预算不是广度闸**（见 §4）。

---

## 2. 下一步（每件一个提交 + 用户审一关；动代码前**先报形式**）

### ⏭ ① `walk` 接线（用户: *"这两个先都不接"* ⇒ **等她说**）
接线的三缺（`walk.py` 文件头也写着）：① `set` 形状的执行器（今天只有 `find`; 要么给它加
"按 id 集合"的锚, 要么 `Mode.executor` 表驱动）② `near`/`echo` 两行形式 + `Mode.order` 加取值
`"near"` ③ **`chain` 的用户还没定**（最自然是 `look` 的第三种形态"我为什么这么想"）。

### ⏭ ② 五链路 A–E：**改造**（各自成段）还是**归档** —— ⛔ 要用户拍。
### ⏭ ③ 扫尾（低价值）：`emo_span`/`emo_int` 退契约（⚠️ 唯一读者在**未接线**的 `channel_impl`）
· `entities.candidate_table` 死代码（生产侧零调用, 只有 `tests/core/test_wiki_entities.py` 在调）·
`graph.py:76` 那句"`contradicts`/`evolved_from` 零写者"**已过时**（P7-2 起有写者）。

### ⏭ ④ 真机跑一次（用户: *"等完全弄完我会从头跑真机"*）—— 工具已就绪
```powershell
python -m uvicorn webgui.app:app --host 127.0.0.1 --port 8000     # 日志落到 data/diag/live2be.log
python experiments/recall_report.py                               # 一条命令出清单
python experiments/recall_report.py --selftest                    # 解析器自检（不读真机日志）
```

| 看什么 | 判据（预设） |
|---|---|
| 三段实际长度（`per=`） | 撞满 1000 字符 ⇒ 该分预算; 平均 < 600 ⇒ 预算给多了 |
| 空手占比（`name(empty)`/`when(empty)`） | 每轮都空 ⇒ 触发面太宽 |
| 她会不会**过度汇报**"想不起来" | 多 ⇒ 措辞要收（那就不是信息, 是噪声） |
| `noticed` 写不写 / 抄得对不对 | `mmt_noticed hit=… title='…' said='…'` 两个串要一致 |
| `look` 用了几次 | 三段摆得多 ⇒ 她**该少翻**才对（P19 与 `look` 互补） |
| `ms=` | 召回耗时有没有随库长线性恶化（真档 21 条 episode 时 ≈ 0.5 ms 量级） |

### ⏭ ⑤ `form_key` **下移**（代码组织的活；统一 R3 重名挡板的两端）
`digest/rounds/attribute.py` 的 `known` 与 `contract/digest_registry.parse_attribution` 是
**一对** `casefold`（两端自洽, 但对空白敏感）⇒ 想让 R3 的重名挡板也空白不敏感, 必须**两端同时**
换成 `form_key`; 而**契约层不许 import core**（`tests/core/test_import_direction.py`）
⇒ 修法 = 把那个纯字符串件**下移到 `contract/`（或 `core.common`）**, `entities` 改成 import 它。
⚠️ 今天**不影响正确性**: 执行层 `revise.apply_entities` 用 `find_entity`（**已经是 form_key**）
再挡一道 ⇒ 差别只在台账那一笔（路标注释已写在 `attribute.py` 那一行上方）。

### 押后（不做, 除非用户点名）
P19 的 cap + 标题清单 · `specificity` 加权 · `part_axis` · BFS 对照台 · `noticed` 带想法 ·
`emotion`/`place`/`mood` 进图（= `mood` 形式的前置）· interperson 渲染要不要印档案显示名 ·
`look` 的"标题候选台" · 名表要不要给看法行加长度预算（**今天 1116 字**, 用户 2026-10-12 未裁）·
`hit_set`/`_body_hits` 要不要也走 `form_key`（**今天没铺**, 见 §4）。

---

## 3. 已裁（2026-10-12，用户）—— 别再翻案

- ⭐ **P19 三段的六条口径**：**每段各自** 1000 字符 · 段序 `name → when → turn` ·
  **保留号不触发**名字段 · 名字段**不挂** `noticed` 提示 · `when` **只查 exact 不放宽**
  （*"可以让 LLM 干脆自己多开区间搜"*）· 段头**印钥匙**、**空手也说话**（措辞限定在钥匙上、
  瞬时; ⛔ 不写"一片空白/良久"）。
- ⭐ **「我知道的名字」四条**（`4d978eb`）：**合并**（原「我眼里的他们」+「我是这样看自己的」
  成一块）· **保留号都收**（老师 + 她自己）· **只写主名**（别名不上屏）· **她自己在表尾**;
  抬头固定 `我知道的名字（想起谁、翻谁的事，都用这些叫法）：`
  （⛔ 改抬头要**同批**改规则书【回忆】那句, 有守门）。
- ⭐ **名字匹配忽略空白**（用户: *"注意处理空格"*）：`entities.form_key` = 去所有空白 + casefold,
  **唯一归一**, 铺 `find_entity` / `like.build_ctx` / `_materialize_stances` 幂等键。
- ⭐ **台账格式**（`mmt_recall`）: `per=` 与 `modes=` 同款标签（含 `(empty)`）, `ms=` 只量召回+渲染。
- ⭐ **`mmt_send_media` 封印**（`a0eb749`）：媒体管线未接、端到端 no-op ⇒ prompt 上收掉
  （`ActionSpec.in_prompt=False`）; **解析/执行照旧**。恢复 = 那一格改回 `True` + 同批改回
  规则书 3 处 / 环境 2 处 / 示例 + 刷夹具。
- ⭐ **不做 `inspect entity`**：`entity.text` 以后常驻 ⇒ "看档案"这个动作没有信息增量;
  `entity` 的正确定位是**筛选轴**（`look(entity=…)`）。
- **`echo` / `mood` 不做**：`echo` 的实时语义路与"P19 不吃后端"冲突（`akin` 边是它的离线版）;
  `mood` **无料**（情绪不在图里）。`precious`/`recent`/`notes`/`person_near` 也都**不做**。
- **`一行前瞻`：撤了**（`30fe6b6`）⇒ 内容行**到达即交付**。
- **`self` 出厂值：写了**（`9379a91`）。⚠️ 引擎仍是"只填空 text" ⇒ 真档 `x0000` 已有 R3 那份,
  **新世界线才生效**（用户: "先不管"）。
- **非便利屋68 的角色：不维护**（用户: *"以后除了便利屋68相关的都不打算维护, 那几位 sprite 都没"*）。
- **`entity.text` 的演化通道**（digest 侧没有写者）= **以后再说**。

---

## 4. ⚠️ 会**静默**出错的那几处（改召回/契约时必看）

- **契约 / 规则书 / 示例三处必须同批改**（漂过两次）。守门 = `test_mmt_look_action.py::
  test_rulebook_section_and_the_contract_say_the_same_thing` + ⭐ 新增
  `test_rulebook_points_at_the_name_list`（规则书那句要指向名表, 改名会当场红）。
- **改完任意进 system 的内容 ⇒ 刷 promptkit 夹具**
  （`PROMPTKIT_UPDATE_FIXTURES=1 pytest tests/core/test_promptkit_baseline.py`）+ 人审 diff。
- **封印位只收 prompt, 不收解析**：`in_prompt=False` 的动作**仍在注册表**（`action_names()`）——
  ⛔ 别把 `prompt_action_names()` 与 `action_names()` 合并。
- **位置实参串位**：`look_header(entity, clue, when, …)` / `look_fn(entity, clue, when)` 全是字符串,
  一律**关键字实参**。
- **`names._pick` 的列表**：作者三种写法都在用——只认一种会**静默**切出垃圾别名（**已修**）。
- **YAML 折行**：`text` 用 **`|`**; `>` 会把换行变空格（汉字之间由 `_fold_layout` 兜）。
- **直接调 `_look_result` / `_recall_notes` 的测试必须钉 `eng._turn_now`**（否则 `上周` 随真实日期漂）。
- **⛔ 假旋钮**: 加配置格之前先问"有没有第二个取值"。
- **⛔ 带槽不填 ⇒ 当场炸**（`render_section` 的 `{key}`; 用 `str.replace` 不用 `format`）。
- **⛔ 去重掏空 ≠ 空手**：跨段去重会把后一段掏空, 那时印"一时没想起来"是**假话** ⇒ `empty_ok=False`。
- **测试夹具别借保留号**（`x0000`/`x0001`）：借了会被 `skip_ids`/`RESERVED_TRIGGERS` 整条剔掉。
- **时间词扫句子要最长优先**（「上上周」不许被「上周」截走）, 且**未过完的窗口不算旧事**。
- **渲染预算不是广度闸**：一个类 30 个成员时, 1000 字符挡不住**两跳的扇出平方放大**与**台账那一行**
  ⇒ `walk.bfs(width=…)`（缺省不裁, 由形式给值）。
- **`walk.chain` 的已访问集是安全件**：`contradicts` 对称 ⇒ 环在真图里可能, 少了它**不是慢, 是停不下来**。
- **变异靶子要选对**：`check_turn` 那层用例**管不到**流式暂存; 靶子选错 ⇒ 变异"绿"其实是没验到。
- ⭐ **名字归一只有一处**（`entities.form_key`）：⛔ 别在调用方再 `casefold()` 一遍;
  已铺 **四处**（`find_entity` / `like.build_ctx` / `_materialize_stances` / `hit_set` 的正文扫描,
  2026-10-12 全齐 —— 真档实测三种口径命中集相同, 零误命中）。
  ⚠️ **唯一的例外是一对**（不是一处）: `attribute.py` 的 `known` + `parse_attribution` 两边
  都用 `casefold` —— 见 §2⑤（要下移纯字符串件才能统一）。
- ⭐ **编号永不进她的视图**：守门 = `test_no_internal_ids_in_what_she_sees`（扫**整段注入文本**）+
  `test_known_names_rows_are_names_not_ids`。⚠️ 新加注入行时**别印 `node.id`**。
- ⭐ **名表行形状**：`- 主名` / `- 主名：看法`, ⛔ 别名/编号/`【】`/空标题都不许。

## 5. 流程纪律与环境（踩过的都在这儿）

- 每件一个提交 + **用户审一关**; CJK commit 用 `git commit -F .testtmp/<file>.txt`;
  **stage 显式路径**; ⛔ 不用 `ruff --fix`（本机**没装 ruff**, `python -m ruff` 报 No module）;
  ⛔ 不 commit `illustration.yml`; 真机数据**只读**（探针也**不 save**）。
- **PROCEED.md 统一最后写**（用户 2026-10-12 裁）—— 不再夹在每件里单独开提交。
- 测试: `python -m pytest … -q --basetemp=.testtmp/<名字>` —— ⚠️ **目录必须预建**,
  否则上千个 `PermissionError`。分板块跑（`tests/core` / `tests/webgui` / `tests/llm`+`tests/renderer`）。
- **git 推送必须走代理**（直连被 reset）:
  `git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin master`。
- 改 `core/mmt/engine.py` 的 import ⇒ `SPLIT_API_UPDATE=1 pytest tests/core/test_split_safety.py` + 人审快照 diff。
- LM Studio（`lms server start`, 端口 1235）只在 **digest 语义召回**时要; 不在就静默降级。
- ⭐ **变异靶**（都住 `.testtmp/`, 用完不留文件）: `verify_c5_guards_red.py`（3 个, 本次新增）·
  `verify_name_wire_red.py`（14）· `verify_walk_red.py`（13）—— 改完相关面各跑一次。

## 6. 口径（用户裁过, 不许悄悄推翻）

- 召回**分形式、不混分**（要总序就混名次 RRF）; 形式名按**意图**, 不按编号。
- `interperson` 的**键 = 她的叫法**; `self` / `sensei` 是**保留键**（按 id 认, ⛔ 不搜 profile）。
- **不设硬上限**（entity 不裁; 计数只做建议）; `look` 展示 cap 5。
- **她只知道自己眼里的他们**（⛔ 不读别人的客观档案）。
- `find` = 不漏即正确; 线索 = **字面**布尔式（**零正则**）; 时间两族（`last`/`back`）;
  时间轴 = **现实日/现实年**。
- **独占口径**: `look` / `trigger` = **唯一操作行**（话可前置）。
- **别名（`aliases`）是"她可能怎么写他"的唯一真源**，三条路共用同一张面
  （`entities.surface_forms`）：`look(entity=)` **精确等价**（空白不敏感）· P19 的 `name` 段**子串** ·
  digest 认人（`#entity:`）**精确等价**。
  ⚠️ **卡上的别名 ≠ 她的叫法**（真机: 阿露的 `other_names` 里**没有「阿露大人」**）⇒
  她若照自己习惯写「阿露大人」, `look` 会 miss（P19 那条是子串, 仍会触发）。
  想让某条路认得出, 就把那个写法写进 `aliases`（数据侧: `config/characters/*/profile.yml`）。

---

## 7. 这一段提交链（`a7d79c8` 之后 · 全部已验证）

| 提交 | 一句话 |
|---|---|
| `7eed29e` | PROCEED 第三版 |
| `4d978eb` | ⭐ **entity 常驻化** —— brain 段「**我知道的名字**」（键面 + 看法; 保留号都收, 她在表尾）+ `entities.form_key` 空白归一 + 台账桶 `known` |
| `5a5973e` | **台账收口**：`mmt_recall` 加 `per=`（每段字数）与 `ms=`（召回+渲染耗时） |
| `593d1a1` | ⭐ **真机观察脚本** `experiments/recall_report.py`（只读, 两代格式都认, `--selftest`） |
| `3ad6e71` | 两条新守门（**编号不入视图** · **名表行形状**）+ 3 个变异靶 + 重跑旧靶 14/14、13/13 |
| `c350a3b` | PROCEED 第四版 |
| `d32c8f3` | config: **作者缩短出厂立场句**（名表 1116 → 938 字; 跟一条断言） |
| `c7a4ac7` | 名字归一推广到 **`hit_set` 的正文扫描**（第三处; 真档实测三口径命中集相同） |
