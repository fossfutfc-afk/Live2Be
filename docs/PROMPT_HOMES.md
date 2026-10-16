# PROMPT_HOMES — 提示词住在哪里（**散落审计**，2026-10-05）

> **只读审计**（零代码改动）。回答两个问题：**"prompt 是不是散落一地?"** ·
> **"registry 是不是把动作的 prompt 搞散了?"**
>
> 一句话结论：**介质散是必须的（甚至是对的），出处散才是病** —— 后者我们这两天正在收
> （`keep` 判据 4 处 → 1 处 · 括号 5 份 → `marks.py` · note 长度 2 处 → 1 处）。
>
> 与 `docs/PROMPT_INJECTION_MAP.md` 的分工：那份是**逐调用点的注入地图**（但行号/路径停在
> 2026-09-07 —— `core/momotalk.py` 已搬到 `core/mmt/engine.py`，digest 六轮整段没进过那张表）；
> 本文回答"**谁住在哪、谁重复了、该不该收**"。

---

## 1. 四类家

| 家 | 装什么 | 量 | 谁在改 |
|---|---|---|---|
| **`llm/prompts/*.md`** | 主 prompt（规则书/手法/环境/任务卡/标注 prompt/digest 各轮） | **19 个文件** | 人（作者层） |
| **`contract/*.py`** | **输出契约**：`build_schema`（动作表）· `build_line_schema`（MMT 行流）· `build_record_schema`（Bond 记录流）· `digest_registry.build_schema(phase)` + **4 个 `DigestAction`**（role/semantics/field_schema/example） | 3 个渲染器 + 一整个 registry | 改**字段名/词表/校验**的人（与 `_clean_*`、`parse_*` 必须同批改） |
| **`core/` 内联** | 引擎拼出来的可读串：`material.SKELETON_HINT`（R1 骨架说明）· `notes.TITLE/GROUP_LEADS/render_item`（她的备忘录块）· `marks.*`（段头/记忆头/相对时间）· `entities.py` 四块（R3 的料）· `groups.py` 的块与类 · `rounds/*.py` 的 `_SECTIONS` 段标题 | 分散在 6~8 个模块 | 引擎侧 |
| **`promptkit/`** | **装配**：`DOMAIN_BOXES`（盒A/盒B 各 **10 块**）+ `round_messages`（动态尾唯一入口） | 2 个域 × 10 块 | 改"顺序/块清单"才动它 |

⚠️ **一个调用的全文仍然是完整的**：`round_messages` / `_sections_for` 是唯一入口，
且 `_sections_for` 会**逐字校对料段标题**（表里写什么、就必须拼出什么）。

## 2. 调用点总表（**12 个**）

`llm/task_labels.py::ALL` 里有 13 个标签，其中 `digest`（不带后缀）只是整轮缺省值，
真正的生产调用点是 **12 个**：

| # | 调用 | task | system（会话级/单次） | 动态部分 | 文案的家 |
|---|---|---|---|---|---|
| 1 | MMT 聊天 | `mmt` | **盒A 10 块** + brain 段尾拼 | history + ⛔P16（已封印，不再注入）+ P17 时间/系统注记 + P19「你想起的事」+ P18 `want_to_speak` + task 卡 + user | `momotalk_rules.md` · `momotalk_environment.md` · `behavior_rules.md` · `schema.py::build_line_schema` · `task_mmt.md` |
| 2 | MMT 收尾轮 | `mmt`（kind=wrapup） | 盒A | 同上（`system_note`） | + `task_mmt_wrapup.md` |
| 3 | Bond 一场 | `bond` | **盒B 10 块** | history + 约束注记 + **纠偏注记**（`_pending_feedback`）+ 场卡 + user | `bond_story_rules.md` · `bond_shots.md` · `schema.py::build_record_schema` · `task_bond.md` · `place_world` |
| 4 | 情绪标注 | `emotion` | `emotion_text_annotate.md` + 人设摘要 | 板内记录 | 词表（emotions.yml） |
| 5 | 地点锚点 | `place` | `place_annotate.md` | 变更句 | 168 条词表 |
| 6 | 板级换场 | `place_board` | `place_resolve.md` | 当前地点 + 候选项 | 同上 |
| 7 | 选图 | `place_variant` | `place_variant.md` | 候选文件名（标签机器派生） | 作者 `note` 原样进 |
| 8~13 | digest 六轮 | `digest.{split,record,close,understand,attribute,group}` | `llm/prompts/digest_<key>.md`（含 `{{digest_schema}}`） | **料由 `_sections_for` 拼**（`material.py`）+ 角色人设锚点 | `contract/digest_registry.py::build_schema(phase)` + `DigestAction` |

**动态那半的家**（散在 4 处，都有唯一入口）：

| 注入物 | 家 |
|---|---|
| ⛔ P16 羁绊进度（**已封印 2026-10-08**） | `core/mmt/engine.py::_bond_progress_note`（恒返回空串 —— 引擎不再按轮次对触发时机表态；守门 `tests/core/test_mmt_trigger_note_sealed.py`） |
| P17 时间注记 / 现实日历注记 | `core/worldtime/`（`time_notes` / `realtime_notes`） |
| P17 本轮系统注记 | 调用方传（`webgui/bond/pregen.py::_system_note` · `vn_cli` · wrapup） |
| P19「你想起的事」 | `core/brain/read/render.py::render_recall_block`（走 `marks`） |
| P18 随机想起 | `core/random_events/events.py` |
| 备忘录块 | `core/brain/notes.py::render_note_block` |
| 纠偏注记（Bond） | `core/bond/bond_story/engine.py::_pending_feedback` |

## 3. 真重复（6 条）

| # | 重复 | 几处 | 该不该收 |
|---|---|---|---|
| ① | ~~⭐ **"输出纪律"**：`必须输出完整 JSON…不要 ```json 代码块`~~ | 曾 **13 处** = 6 个 digest prompt + 6 个 phase 渲染（`digest_registry` 各 `build_schema` 开头）+ `digest/call.py` 的反馈话术 | ✅ **已收 1 处**（**G1**, 2026-10-05）：六个相位共用 `digest_registry.OUTPUT_DISCIPLINE`（由 `OUTPUT_RULES` 渲染，**唯一字面**），6 个 prompt 尾部那一段**整块删掉**；守门 = `test_the_output_discipline_lives_only_in_the_contract`（**两半都查**：prompt 里不许有 + 六个相位的 schema 里必须真有）。⚠️ **`call.py` 的 feedback 与 `llm/client.py` 的 JSON 修复循环故意各留一份** —— 那是**出错之后的修复轮**，不是同一次 system 里的重复 |
| ② | **note 正文 ≤20 字** | 2 处（`digest_close.md:29` + `digest_registry` close 相位的字段说明） | **已被 N1 判为孤立的旧规格**（note 正文现在 = 切片 `abstract` ≤60）⇒ 归 **L6/L8**（收口轮死掉时一起清） |
| ③ | **生日** | 2 个真源：`profile.yml` 的 `SIG~birthday`（给 AI）vs `mmt_registry.toml` 的 `birthday`（给显示） | 收不了（两个读者不同），但要写清**不一致时谁说了算** ⇒ `L3` 的料 |
| ④ | ~~`abstract` 的 60 字~~ | 曾 2 处（体检 + 契约） | ✅ **已收 1 处**（N1 删掉体检那条） |
| ⑤ | ~~`keep` 判据~~ | 曾 4 处（契约 / prompt / `notes` 注释 / docs） | ✅ **已收 1 处**（L1 + L2；prompt 里那句换成了指针） |
| ⑥ | ~~括号与信息头~~ | 曾 5 份 f-string（她视图 / L2 / R2 / R4 / R3） | ✅ **已收进 `marks.py`**（N5d + 守门 `test_marks_guard`） |

**判据（该住哪）**：
- 要跟**解析器严格同步**的文本 → **契约层**（`_clean_*` 与渲染器是同一个契约的两半；示例与逐字段说明还同源）。搬进 `.md` 反而会漂。
- 纯**语气/手法/边界声明** → `.md`。
- 引擎内联的可读串 → 收进 `marks.py` 那种"唯一实现"模块。

## 4. registry 那件事：它是"集中"，不是"散"

`DigestAction` 的 4 个动作（`record_episode` / `touch` / `update` / `add`）的 prompt 文案
**全在 `contract/digest_registry.py` 一个文件里**，MMT 的动作同理在 `contract/spec/` 的注册表。
它这么放的**硬理由**：字段名 / 词表 / 校验函数 / 文案必须一起改，而守门
（`test_schema_*` 的"示例与逐字段同源"）就钉在那一处。

⇒ **"读 prompt 得开 .py"是它的代价，不是它的病**。真正的病是"同一句话在 ≥2 个地方各写一份"（§3）。

## 5. 守门建议（按代价排序，都要能红）

现状：有**半张总账**（`PROMPT_INJECTION_MAP.md` + `promptkit/report.py::describe()`），
但**没有任何东西能自动回答"这段文本从哪来、有没有第二份"**。

| # | 做什么 | 代价 | 判据 |
|---|---|---|---|
| **G1** | ~~**"输出纪律"单源化** + 守门~~ | ✅ **已做（2026-10-05）** | 契约 `OUTPUT_RULES`/`OUTPUT_DISCIPLINE` + 6 个 prompt 删段 + 守门两半（prompt 里塞回任一条 ⇒ 红；相位 schema 里抽掉 ⇒ 红）—— **变异验过** |
| **G2** | **注入串白名单**：`core/` 里"会进 messages 的字符串字面量"只许来自 4 类入口（prompt 文件 / `build_*` / `marks.*` / `_SECTIONS`），其余进白名单 + 写理由 | ~半小时 | 新写一处内联串 ⇒ 红 |
| **G3** | `promptkit/report.py::describe()` 扩成**"某 task 的实拼全文 + 每段来源"**（今天只覆盖盒A/盒B），当夹具看 diff | ~1 小时 | 每段都能报出 file:函数 |

⚠️ **G2 的实现方式要先裁**（静态扫 import+调用点 / 还是运行期 hook）——它值得单独一次讨论，
不要顺手做。

## 6. 已知漂移（本次不修，记录在案）

| 漂的地方 | 现状 |
|---|---|
| `docs/PROMPT_INJECTION_MAP.md` | 行号/路径停在 2026-09-07（`core/momotalk.py` ⇒ `core/mmt/engine.py`）；digest 六轮从没进过那张表 |
| ~~`llm/task_labels.py:42` 的注释~~ | ✅ **已修（2026-10-05）**：`DIGEST_SPLIT` 从"划区间 + `keep` + `abstract`"改成"划区间 + `abstract` + 账目（`state`/`id`/`due`）" |
| ~~ 附近的 `text ≤20 字`~~ | ✅ **已修（2026-10-05）**：改成 **≤60**（真源 `ABSTRACT_MAX` = R0 切片的 `abstract`），并注明 `closed_at`/`afterwards`/`state` 三字段已删（L6） |
