# PROCEED.md — **接续用**（整篇覆盖写；上一版见 git 历史）

> 位置（2026-10-08）：⭐ **"她怎么认识人"这条线全部落地** ——
> `interperson.yml` 换写法（值 = 一句她自己的看法）→ 物化成 `entity.text` →
> 注入 brain 段的「我眼里的他们」+「我是这样看自己的」；
> ⛔ `mmt_inspect_character`（读别人的客观档案）**退役**；规则书加【回忆】专段。
> 提交 `4013cd9` · 树干净 · **ahead 46（未推送）**。
> ⭐ **下一步没有必须做的了**（这条线收口）；要继续就是 §1 的"待裁三件"或"押后清单"。

---

## 1. 下一步该怎么做（每件一个提交 + 用户审一关）

### ⏸ 待裁三件（都只需要一句话）

1. **`一行前瞻` 撤不撤**（`engine._turn_lines`）：它当年的理由是"下一行可能是静默轮
   `inspect`，手里那行得能收回"——那个动作退役后**没有任何行会作废已交付的内容**
   ⇒ 今天它只让**最后一行晚一格上屏**。撤 = 首末字都快一格（行为/时机变更）。
2. **`self` 的出厂值写不写**（`interperson.yml` 的 `self` 键，现在 `text: ""` 占位）：
   ⚠️ 引擎是"**只填空 text**"⇒ 真档 `x0000` 已有 R3 长出来的那句，作者写了**不会立刻生效**。
   要立刻生效得同时改成"作者值优先"（那是 R3 的口径变更，要写进它的 prompt）。
3. **`hinomiya_chinatsu` 那一行**（表里唯一还是旧的数字形状）：她**有行、没卡、也没 friends**
   ⇒ 没有立场可搬，那一行**今天没有任何读者**。删掉 / 留着 / 让作者给她写立场 —— 用户定。

### 押后（不做, 除非用户点名）

`look` 的 cap + 标题清单 · `part_axis` · specificity 加权 · BFS 对照台 ·
`noticed` 带想法 · `emotion`/`place`/`mood` 进图 · `emo_span`/`emo_int` 退契约 ·
`entities.candidate_table` 死代码清理 · **interperson 渲染要不要印档案显示名**
（今天印 `entity.name` = 档案的 `most called name`，如「陆八魔 阿露」）·
**跨文件跑的两条红**（见 §3.1 末条）。

---

## 2. 已落地的链（这一段 11 笔，全部已验证）

| 提交 | 一句话 |
|---|---|
| `9f0a7af` | 作者改写立场（第一人称 + 转述）+ **折行语义定案**：换行 = 排版（无痕）、空格 = 内容（保留） |
| `ed4d48d` | **B 笔**：出厂物化 —— `ensure_entities(stances=…)` 把表里的立场装进 `entity.text`（幂等、只填空、保留号只填不建） |
| `e6e11c5` | **C 笔**：注入面搬家 —— brain 段新增「我眼里的他们」；盒A 撤 `interperson` 块（10 → 9）；物化**提前到开会话** |
| `a432ee8` | 「**我是这样看自己的**」—— `self` 那一格单开一行（用户裁：键名用 `self`，⛔ 不去搜 profile） |
| `cb6907d` | 修 `other_names` 写成 **YAML 列表**时别名变垃圾的 bug（静默；hina/iori/ako 三人中招） |
| `3330809` | **C2 笔**：6 个角色的 `SIG~friends` 逐字搬进表 + 删副本（对照脚本验"一字不少"） |
| `90af157` | **D 笔**：`mmt_inspect_character` 退役（注册/执行器/门控/自愈/`void` 分支/契约规则重编号） |
| `4013cd9` | 规则书 **【回忆】专段** + 删 `关键边界` 4 行 + 新守门"规则书与契约不许漂" |

⭐ **她今天的"认识人"链路**：`interperson.yml`（作者手写立场）
→ `ensure_entities(stances=…)` 物化（**开会话时跑**，幂等）
→ `entity.text` → `render_character_view` 的「我眼里的他们」
→ 之后 **R3 可以继续改写它**（她的看法随经历演化）。

---

## 3. ⚠️ 特别需要注意的

### 3.1 会**静默**出错的那几处

- **契约 / 规则书 / 示例三处必须同批改**：今天漂了两次 —— ① `mmt_look` 的 payload 说明
  写着"这是单独一轮"↔ 硬规则 5 说"话可前置"；② 规则书里留着指向已退役动作的悬空指令。
  **示例才是形状的来源**（真机 art 命中率 0/5 的根因）。
  守门 = `test_mmt_look_action.py::test_rulebook_section_and_the_contract_say_the_same_thing`。
- **`_pick`/`names` 的列表**：作者三种写法都在用（逗号串 / 行内 list / 块 list）——
  只认一种就会**静默**切出垃圾别名（名字车道与 `find_entity` 一起失灵）。
- **YAML 折行**：`text` 用 **`|`**（换行无痕）; `>` 会在解析时把换行变成空格（汉字之间
  由 `_fold_layout` 兜掉, 拉丁旁边兜不掉）。**行内空格是内容, 不许动**。
- **直接调 `_look_result` 的测试必须钉 `eng._turn_now`**（否则回落 `datetime.now()`，
  `上周` 这类相对时间随真实日期漂 —— 10-08 绿、10-12 红的**时间炸弹**）。
- **⚠️ 跨文件跑的两条红**（`tests/core` + `tests/webgui` 同跑时恒定出现，两种顺序都红；
  **各自单独跑全绿**）：`test_mmt_look_action.py::test_look_ledger_and_trace`
  （日志行选取 —— `find` 的 INFO 行被 `next()` 先抓到）与
  `test_bond_chain_readahead.py::test_chain_skips_when_enough_in_hand`（调用计数 6≠3）。
  **与 C/D 无关**，但会污染"组合跑"的结论 ⇒ 要么单独跑两套，要么先修那两条断言。

### 3.2 流程纪律

- 每件一个提交 + **用户审一关**；CJK commit 用 `git commit -F .testtmp/<file>.txt`；
  **stage 显式路径**；⛔ 不用 `ruff --fix`；⛔ 不 commit `illustration.yml`；真机数据**只读**。
- 测试：`python -m pytest … -q --basetemp=.testtmp/<名字>` —— ⚠️ **目录必须预建**
  （没预建 = 1403 个 `PermissionError`，看起来像代码炸了）。
- 改进 system 的内容 ⇒ **刷夹具 + 人审 diff**；改 `core/mmt/engine.py` 的 import ⇒
  `SPLIT_API_UPDATE=1 pytest tests/core/test_split_safety.py` + 人审。
- **变异验红的靶子要选对**：`check_turn` 那层用例管不到**流式暂存**（`WHOLE_TURN_ACTIONS`）——
  它有自己的流式用例。今天踩过：靶子选错 ⇒ 变异"绿"其实是没验到。

### 3.3 口径（用户裁过，不许悄悄推翻）

- `interperson` 的**键 = 她的叫法**；有档案给 `id`、没档案给 `name`（⭐ **没卡也能被认识**）；
  `self` / `sensei` 是**保留键**（按 id 认，⛔ 不搜 profile）。
- **不设硬上限**（entity 不裁剪）；计数只做"建议"（契约里那句 5 → 10）。
- **她只知道自己眼里的他们**（⛔ 不读别人的客观档案 —— D 笔退役 inspect 的理由）。
- 折行 = 排版 / 空格 = 内容；`|` 优先；`_me()` 只作用于**第三人称的记忆正文**，
  立场句与标题一律原样。
- ⛔ **不建 `about` 也要能召回**（名字车道）—— entity 必须**先建出来**（否则 `add_edge` 拒悬空）。

---

## 4. 必读文件（按要动的件挑）

| 要动什么 | 先读 |
|---|---|
| 她"认识人"的链路 | `config/settings/relation/interperson.yml`（**带注释的表**）· `core/brain/entities.py::_materialize_stances` · `core/mm/engine.py::_stances_of` · `render.py::_bucket_view` |
| 契约 / 规则书 | `contract/schema.py::build_line_schema` · `llm/prompts/momotalk_rules.md`（【回忆】专段）· `docs/PROMPT_INJECTION_MAP.md` |
| 记忆层设计 | `core/brain/DESIGN_GRAPH_V4.md`（§2 判据 / §3 未结）· `docs/DESIGN_DIGEST_LAYERS.md` §4 · `docs/DESIGN_MEMORY_MODES.md` |
| 主文档 | `CLAUDE.md` §3.1 / §7 / §8 / §10（这四处在 2026-10-08 都改过） |

## 5. 环境/本机

- 代理 `127.0.0.1:7897`；⚠️ **git 推送现在必须走代理**（2026-10-12 实测：直连
  `-c http.proxy= -c https.proxy=` 报 `Recv failure: Connection was reset`）：
  `git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin master`。
- LM Studio（`lms server start`，端口 1235）只在 **digest 语义召回**时要 —— 不在就静默降级
  （`digest_embed fn=none`，候选退化成字面命中；grep 这行能分辨）。
- 生图默认硬关（`tests/conftest.py` 设 `LIVE2BE_IMAGE=off`）；真机数据在 `data/`（**只读**）。
- 真档事实（2026-10-08）：haruka 的 entity = `x0000 伊草 遥香`（有 text，**有自己的那一行**）·
  `x0001 老师`（立场来自表）· `x0002 杂草屋` · `x0003 夏莱` + 表里那 4 个人（阿露/睦月/佳代子/纱织）。
