# PROCEED.md — 接续用（**整篇覆盖写**；上一版见 git 历史）

> ⚠️ **本文件不记 `ahead` 数**（写死过两次、两次都对不上）—— 真源 = `git status -sb` 与 `git log -1`。
> ⚠️ **`git status` 里常年挂着一份"作者手改未提交"的文件**（本章 = `config/settings/relation/interperson.yml`
> 的立场句重排）—— 那是**作者的改动, ⛔ 不是脏改动**, 别 `checkout` 掉。
> 现状：`tests/core` **1268 passed** · `tests/llm+renderer+webgui` **203 passed**（⚠️ **按域分开跑**, 见 §5 坑 4）·
> 三份 verifier 全 exit 0 · 真机数据未动。

---

## 0. 写法约定（2026-10-15 作者要求，代码注释一律照此）

- 只写**关键点**：顶部 docstring 不许比它底下的代码还长；函数内注释同理。
- 不用 `★ ⚠ ⛔ ✅` 这类装饰符号（满屏符号反而看不见重点）。
- 不写"用户拍板 / 用户裁 / 作者定的"这类表述 —— 重要的是规则本身，不是谁说的。
- 理由：长注释会随代码一起过时（本项目已经踩过多次）；解释放 PROCEED 与提交信息，代码里只留结论。
- 历史文件里那种写法很多，**读的时候别照抄**。

---

## 1. 现状：记忆层（线 A）走到哪了

**一句话**：写侧只写地址、引擎物化、内容归 LLM；**一段 6 轮**（`ROUNDS` 是唯一真源 ——
`group` 退役后从 7 掉到 6, 其中 5 轮发 LLM、`akin` 零 LLM）：
`split ⓪切 → record ①记 → akin 补边(0 LLM) → relate ③接 → cognize ⑥想 → settle ⑦沉淀`
（`understand`/`group`/`close` 已退役, 编号留空档）。

| 轮 | 今天的活 | 料（段名） | 产出 |
|---|---|---|---|
| `relate`（**判关系**） | 判这一段的新经历跟谁有关系, **一个字的正文都不写** | 本次新经历 · 现有经历（候选）· ⭐**她认过的同类印证过的看法** · 本段时间线 · 现有认知 · 人设 | 四种边：`akin` / `supports` / `contradicts` / `evolved_from` |
| `cognize`（**写正文**） | 造新看法 **或** 改已有的看法, 不判已有成分之间的关系 | ⭐**这次的事** · ⭐**这一类事** · 现有认知 · ⭐**跟这条撞上的现有看法** · 已有的对象 · 人设 | `belief` 节点 + 出生自带边 |

⭐ **今天刚落地的那一刀（`2597737`）：看法可改** ——
`{"belief": {"id": "u0003", "text": …}, "supports": […]}`
- **带 `id` = 改那条已有的**（只改写出来的格子; `text` 留空 = 正文不动, 只加边）
- **不带 `id` = 造一条新的**（`text` 必填, 至少一条立足点, 只数新建 ≤5）
- **边只增不减**（⛔ 没有"删证据"这个动作）· `evolved_from` **只在造新的那条上写**（改口 ≠ 取代）
- 三档分开：**锚点 `id` 没命中 ⇒ 丢这一行**（不连坐）· **证据 id 没命中 ⇒ 整包拒**
- **`text_seq` 水位**：同一段重跑不许把同一条正文再改写一遍（防措辞漂移）· ⛔ 改那一路**不并 `akin`**
- ⭐ 两个新料格都走同一条纪律：**看见就得能引用**（cap 之外的看法补发本地号并进引用面）

⭐ **`f6541b0`：L2 的料区域化** —— 【被连过的经历】拆成 **`【这次的事】`**（本段被 L1 连过的,
立足点）与 **`【这一类事】`**（它们一跳 `akin` 的邻居, 额外的证据）。**判据一个字没改**
（一跳 · 打架的不摆 · 边建立序 · 先到先得）, 换的只是摆放 —— 从前簇散在每条 anchor 底下,
她数不出"这一类一共几条 / 跨多长时间"。
- **正文互斥**（不是条目互斥）：本段的条目在第二区只出**信息头** + `（正文见上面【这次的事】）`,
  且**不占额度**（否则本段三条就把 5 格吃光, 老经历反而看不见）
- 额度：`DIGEST_L2_AKIN` **3/每条 anchor → 5/整区**（与 `AKIN_JOIN_MAX` / 撞上那格同量级）
- 空区 ⇒ 空串 ⇒ `_join_sections` **连段头一起不印** · `evidence_ids` 的集合与改前逐条相同
- "这些也算作证据"那句从**料的抬头**搬进契约【belief 释义】（抬头撤了, 留着就是假描述）

**其余已落的**（细节看提交信息, 不在这儿复述）：
`kind` 只剩四种（`episode/experience/belief/entity`; **`profile` 2026-10-14 删格式**）·
`topics` 退役（字段只停产, 判据随载体走）· `entity` 留空 ⇒ **默认归属**（读侧口径, ⛔ 不落边）·
`evolved_from` 图上方向 = **旧 → 新** · akin 共 belief（一跳邻域并进证据, 额度 5）。

**真机读数**（只读探针, haruka）：节点 30 · 边 58（`about 22 · supports 25 · member_of 6 · akin 5`）·
`entity` 字段 **0/30** · 全图 `contradicts`/`evolved_from` **= 0** · akin 5 条全在一个 6 条簇里 ·
⚠️ 认知列表里 `e0001` 是一条 **belief**（id 带老前缀, 历史遗留, 不影响功能）。

**线 B（包重组，另一个 agent 负责）**：`contract/` 与 `llm/` 那一层已经理到位 ——
1a / 1c / 1d / 1f / 1e / 1h 全部落地（见 §4 提交表），并**新建 `infra/` 层**
（`paths` 五个根 · `atomic` · `fuse`）、**解散 `core/common/`**（那个"抽屉"里 6 个模块 4 种性质各归各家）。

- `llm → core` 现在**零依赖**：`test_import_direction.py` 的 `LLM_CORE_ALLOWED` 是空表。
- `infra/paths.py` 的五个根：`RESOURCE`（只读，随包）· `CONFIG` / `ASSETS`（用户内容，
  以后可能由首次向导指定）· `APP`（settings.toml）· `DATA`（事件流真源）。源码树里
  `RESOURCE`/`APP` = 仓根、其余三个 = 仓根下同名目录，所以**老常量值一个字没变**。
- `infra/settings.py` 已是 settings.toml 的**唯一读入口**（9 个读者收成 1，按 mtime 失效）。
  `[paths]` 那一节也通了（首次向导写它，保存后要重启才能生效——`paths` 是 import 期常量）。
- 剩下：**批次 2 的目录改名**（`core→infra/engine`、`renderer+tui→tui`、`apps→cli`）
  要作者在场；另有两条可选 —— `webgui/store.DEFAULTS` 与各领域默认值**两处写**（设置项
  清单的归属问题）· 文档那一趟（`CLAUDE.md` 里还写着 `core/common/` 与 `contract/schema.py`）。

---

## 2. 下一步该干什么（按顺序）

### 2.1 ⭐ 真机端到端跑一次（唯一能看出"改完长什么样"的一步）
```powershell
# ① 先确认 embedder 在（不在 ⇒ L1 候选 + 撞上的语义那一路都只剩字面）
lms server start                      # 本机 LM Studio, base_url 指 1235
# ② 起服务 + 跑观察脚本
python -m uvicorn webgui.app:app --host 127.0.0.1 --port 8000
python experiments/recall_report.py
```
看三行：`digest_relate … cands= sim=`（`sim=0` = 语义没起来）· `digest_cognize … patched= empty= watermark=`
· `digest_embed fn=`（`none` = 降级）。⚠️ 真机数据只读之外, 这一次**会写**（真要跑 digest 才写）——
先想清是不是要在真档上跑。

### 2.2 ⏸ 已知缺口（记着, 不是现在做）
- **撞上的"语义那一路"暂缺**：那一刻她还没写出新看法, query 只能拿本段经历顶 ⇒ 等 `[embed]` 在位再补。
- **判错的 `akin` 无法撤回**（你裁"只为删边没必要"）。⚠️ 业界对**边**的撤回是**标记失效**
  （Graphiti `invalid_at`/`expired_at`, 从不 delete）—— 我们缺的正是这一层。
  将来要做, 形状是"**给边补一个结束时间**", ⛔ 不是 `remove_edge`。
- **召回折叠演化链**（"以后再说"）· **`aliases` 的写者**（"她主动补新别名"仍冻结: 并错不可逆）。
- `noticed` 那条路落的 `akin` 边**不写变更史**（只有一行日志）。

### 2.3 收口类（欠的活, 都不阻塞）
⭐ **代码里 19 处 `PROCEED §2 #10/#11/#16` 这类交叉引用指向的是"旧版 PROCEED 的结构"**
（第十二版重排后那些节号已经不存在 ⇒ 全是死链, 但**裁决本身都还在**）。两条出路, 二选一:
给 PROCEED 加一节「旧编号 → 今天在哪」, 或者把那些注释改成不依赖节号的写法（`akin.py` 那处
今天顺手改了, 其余 19 处没动）。
`form_key` 下移 `contract/`（统一 `parse_attribution` 两端）·
四份契约的**文风/结构统一**（向 `settle` 看齐 —— 值表 → 判据 → 【释义】→【范例】的固定顺序）。

---

## 3. 必读文件（只列真会打开的那些）

| 文件 | 为什么 |
|---|---|
| `core/digest/rounds/__init__.py` | ⭐ **轮次真源 `ROUNDS`**：key/步序/相位/prompt/**料**/**写什么**/预算一处说全；`material` 是硬契约（改了必须与 md 两边同改） |
| `core/digest/material.py` | 各轮的料（L2 那两个区在这儿：`_l2_material` / `_akin_region_rows`；两个新格：`akin_supported_beliefs_block` / `collided_beliefs_block`） |
| `contract/digest/prompts/cognize.md` | ⭐ **今天刚改的契约**（带 id = 改 / 不带 = 造；边只增；撞上四条出路）—— 改它先读 `docs/EXPERIMENT_CONTRACT_SHAPE.md` |
| `contract/digest/parse.py` | 两档校验（丢行 vs 整包拒）与 **id 容错**都在 `parse_cognitions` / `_clean_belief` |
| `core/brain/revise.py` | 三个执行器 + `_join_akin` + **`_apply_belief_patch`**（覆写/水位/留痕） |
| `core/brain/graph.py` | 边词汇表 + `DEFAULT_FACES` / `default_faces` / `lane`（**默认是读侧口径**） |
| `docs/EXPERIMENT_CONTRACT_SHAPE.md` | ⭐ 契约形状的 A/B 记录 + **别人的 digest 契约对照**（Mem0/AgentGal/Graphiti/LangMem/Letta） |
| `docs/DESIGN_MEMORY_MODES.md` | 四种模式的语义地基 —— ⚠️ **§0/§1 还在教已退役的"经验=门槛"模型**（读它要带这层判断） |
| `.testtmp/verify_1c.py` · `capture_prompts_1d.py` · `capture_1e.py` | ⭐ 动契约/文案的三份逐字节判据（各自 `check`；`EXPECTED_CHANGED`/`CHANGED` 要写"为什么"） |
| `CLAUDE.md` | ⚠️ 89 KB 且多处过时（`topics`/`profile` 那几行已作废）；当索引读, 冲突时**信代码** |

---

## 4. 这一段的提交（越往下越新）

| 提交 | 做了什么 |
|---|---|
| `080460b` | `topics` 退役：`on` 的判据随载体走 · 字段只停产 · `轴` 那格全撤 · L1 候选换源 `like(spec="digest")` |
| `7697b72` | `entity` 留空 ⇒ **默认归属**（R1: 你+老师）—— 读侧兜底, ⛔ 不落边 |
| `99b9271` | `evolved_from` 图上方向翻成 **旧 → 新**（名字不动） |
| `f7a280a` | PROCEED 修三处会误导的（`supports` 出边 · 去掉写死的 `ahead` · "树干净"那句） |
| `f738ea5` | **删掉 `profile` kind 与 `examples` 字段**（真机零依赖; `subject` 留着 —— belief 的活读者） |
| `2597737` | ⭐ **L2 碰撞那一刀**：看法可改（`id` 决定建/改）+ 两趟各补一格 + `DEFAULT_FACES["belief"]` |
| `f6541b0` | ⭐ **L2 料区域化**：【这次的事】/【这一类事】两区 + 正文互斥（信息头不占额度）+ 额度 3/条 → 5/区 |
| `3f34874` | `contract/schema.py` → **`contract/schema/` 包**，2.6 KB 文案搬进 `prompts/*.md`（5 个形态逐字节不变；顺带砍掉 3 个生产死件 67 行） |
| `3070a25` | `contract/schema/` 的**文案守门**：动作名必须在注册表里 · 取值表与 `records` 文法对账 · 规则 md 是干净列表 |
| `d83bb04` | **新建 `infra/` 层**：`paths.py`（五个根）· `atomic.py` · `fuse.py`；31 处 `core.paths` → `infra.paths`；顺手治 6 个"自己现拼根"的文件 |
| `21a4df0` | **解散 `core/common/`**：`errors` 壳删（20 处直连 `contract.errors`）· `mmt_registry`→`core/mmt/` · `tone`→`core/parsing/` |
| `4a8e39b` | **注释瘦身**：按作者要求改掉我自己写的那几个文件（去掉装饰符号、"只写关键点"；写法约定进了 §0） |
| `dd40344` | **`infra/settings.py`**：settings.toml 的**唯一读入口**（9 个读者收成 1，按 mtime 失效）· `[paths]` 覆盖通了 · 坏文件有声音 |

---

## 5. 隐形坑（一行一条；细节在代码注释与 git 历史里）

**环境 / 工具**
1. 跑测试必须带 `--basetemp=.testtmp/_pytemp -o cache_dir=.testtmp/_pcache`（`%TEMP%` 权限坏）。
2. 解释器 `C:\Users\johnf\miniconda3\envs\live2be\python.exe`；ruff 在 `…\envs\live2be\Scripts\ruff.exe`。
3. ⛔ **别用 `ruff --select … --fix`**（`--select` 覆盖 pyproject ⇒ 批量删掉有效的 `# noqa`）。
4. **四个域塞进一个 pytest 进程会互相干扰** ⇒ `tests/core` 一条命令、`tests/llm tests/renderer tests/webgui` 另一条。
5. ⚠️ **`git show HEAD:<file>` 是 LF、工作区是 CRLF**（autocrlf）—— 验行尾**只看工作区文件**;
   `write`/`Set-Content` 之后必须 `check_eol.py`（`edit` 工具不会改混）。
6. PowerShell 会吃掉 `-c` 里的嵌套引号 ⇒ 脚本一律写成 `.testtmp/*.py`；`git commit` 一律 `-F 消息文件`。

**契约 / 文案（改一个字节就要跑三份 verifier）**
7. ⭐ **改 `contract/digest/prompts/**` 或 `llm/prompts/**` ⇒ 立刻跑三份 verifier**，有意的改动写进
   `EXPECTED_CHANGED`/`CHANGED` **并写为什么**（长期红的判据 = 没人看的判据）。
8. ⭐ **`【】` 是段头不是强调号**：契约 md 里写 `【X】` = 对她宣布"下面这段叫 X"⇒ 必须有出处
   （料名 / 契约自己行首定义 / 渲染器标签），由 `test_digest_contract_refs.py` 钉住。
9. ⭐ **守门是一对**：`test_material_names_are_not_dead`（料名必须出现在某份 md）↔ `test_every_bracket_in_prompts_has_a_home`
   ⇒ **改段标题必须 `ROUNDS.material` 与 md 两边同改**。
10. ⭐ **模板槽只有一种写法** `{{名字}}` + `contract.slots.render_template`（**两个方向都对不上就当场炸**
    —— 我把 `{{max_cognitions}}` 写成字面量 5, 当场红）。
11. **契约里不许有"假威胁"**：写了"违反即丢弃", 引擎就必须真丢；**判据的载体死了, 那句判据也要跟着死**。
12. **空值语义有两种, 别混**：`settle`/`cognize` 的**空格子 = 不改** · `entity` 留空 = **取默认**。
13. **退役分两种**（先例）：**整行死了**（`profile`/`experience`）⇒ 认得出 + 丢行 + 记账；
    **只是行内一格死了**（`about_hint`/`items`/`topics`/`on`）⇒ 白名单外**静默不落库**。
14. 删停产件后**按名字 grep 全仓**（注释里还在讲"某个已删函数恒空"—— 编译器/测试都不会报）。

**方向 / 图**
15. ⭐⭐ **"方向只看一端"这类错犯了四次**：`related` / `conflicting` / `lane` 兜底 / **交接文档**。
    写法：**先把方向写成一句话**（`X → Y`）再写代码。`about` 是"节点 → entity"⇒ 判"这条属于谁"查
    **出**边（`targets`）; `supports` 是"经历 → 看法"⇒ 查经历的 `supports` 要 `targets`（写 `sources` **恒空且不报错**）。
16. **对称 rel 只查一个方向必然漏一半**（`akin`/`contradicts` 存进去被 `canonical_for` 归一）——
    唯一实现 = `graph.related` / `graph.conflicting`（`store` 上是薄封装）。
17. **加了"读侧默认面"这类口径之后, 老 fixture 会静默换一支**（不是红, 是**测的东西变了**）——
    给它们**明确写一个别的归属**, ⛔ 别改判据。
18. **`like()` 会把"本段自己那几条"排第一**（自匹配 1.00）⇒ 调它要 **`k + len(mine)`** 并过滤 `mine`。
19. **一份料里同一段正文只印一次**：`printed/shown` 只收**真印过正文**的; 主列表**永远印自己那一条**
    （我第一版把"只出信息头"也算进"已印"⇒ 那一条正文一个字都不剩）。
20. **`kind` 认不出会静默降级成 `episode`**（`from_dict` 的兜底）⇒ 删一个 kind 时,
    **"照条目建节点"的那一支必须删干净**, 不能只停产（否则埋一条"画像被写成经历"的路）。

**真机数据**
21. ⭐ **真机数据只读**：探针可以读、可以在内存里改, ⛔ **绝不 `save()`**
    （验证法: `git status -- data` 干净 + `wiki.jsonl` 的 mtime 不变）。
22. 加载真档要 `WikiStoreV2(path=…/soul/wiki.jsonl, …)` —— 第一个位置参数是 **data_root 不是 soul 目录**
    （传错会静默得到 0 个节点）。
23. ⚠️ **`[embed]` 服务不在 = 语义召回静默降级**（`digest_embed fn=none`）⇒ 排查"记忆只增不并"先 grep 这一行。
24. ⭐ **探针不许手搓判据**：我在对照探针里自己写了"本段的条目整个剔出第二区"⇒ 跑出"整区空",
    看着像数据的事, 其实是**我编的规则**（真实现是**正文互斥**）。改判据的活儿要**照抄现役
    实现**, 或者干脆**调真函数**（`.testtmp/probe_l2_region_final.py` 那一版）。

---

## 6. 等你拍 / 已裁"不做"（别自己捡回来）

- **拍**：要不要先跑真机端到端（§2.1）· 要不要现在推 push（§2.3）。
- **已裁不做**：`ambiguous` 不加机制 · bond 开场不补 entity 物化 · `examples` 字段已删（⛔ 别加回来）·
  `profile` 已删格式 · `topics` 只停产不删格式 · 撤回边不做（缺口见 §2.2）· 撤回/删证据不做 ·
  召回折叠演化链"以后再说" · ⛔ **belief 正文不原地改**这条**已被推翻**（今天起: 差不多就覆写,
  旧的那句不再成立才 `evolved_from`）。
