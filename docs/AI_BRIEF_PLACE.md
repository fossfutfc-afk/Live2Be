# 地点系统速查（**给 AI 看的**，不是给人看的）

> **这份文件是什么**：用户 2026-09-19 说 *"鉴于你之前出现了很多理解偏差，再次
> 梳理一下信息，并且把文档中误导你的重写成你理解的语言，不必过于专业，你看的懂
> 就行，这个是给你看的。"*
>
> 所以：**格式随意、口语化、以"别再踩坑"为目的**。给人看的正稿仍是
> `docs/DESIGN_PLACE.md`；本文是它的"防坑版"。
>
> **怎么用**：动地点相关代码前先读这份。它只写了**今天为真的事**，
> 以及**哪些旧话是假的**。不确定时以代码为准，别信任何一句转述（包括本文）。

---

## 0. 一句话版本

**writer 自由写地点（自然语言），后台标注层把它翻成表里的一个键，键用来查图；
记忆里同时存"键"（管回放/同图）和"writer 原话"（管检索/同地）。**

---

## 1. 谁是谁（一张表记住）

| 东西 | 住哪 | 是什么 | 一句话 |
|---|---|---|---|
| **地点表** | `config/settings/world/place_entities.json` | 168 条, 作者用 tempo 工作台整理出来的 | **唯一的查表语料**。外层键 == 行内 `place` 字段 |
| **表加载器** | `core/media/place_table.py` | `PlaceTable` / `load_table()` | 层1 别名命中 + 层2 整表文本。**按 mtime 缓存**（改表即生效，不重启）。层2 文本的分组头是**中文**（`SDIR_LABELS`: `【社团】`/`【室外】`…, PL6 用户裁决——`sdir` 本身仍英文，别改它） |
| **写作用词** | 表里 `sdir == "SDIR_Atmosphere"` 的 4 条 | 镜头（天空/黑场/星空/黄昏） | **不是地点**。给 writer 的那份抄在 `llm/prompts/bond_shots.md` 里（手写） |
| **区域词表** | `config/settings/world/regions.yml` | 21 条学院主名 | **只给盒B 的【世界区域】块用**。跟"同地"判定**没关系**（已被用户撤出记忆） |
| **旧白名单** | `assets/_director_whitelist.json` | 31 条裸 slug | **只是降级兜底**（表读不出来时才用）。别再把它当词表 |
| **资产** | `assets/background/**` | 1094 张图 | 表的 `files` 里写的是**相对 `assets/background/` 的路径** |
| **回放/显示** | `webgui/routers/bond.py::_resolve_scene` | key → 图 URL | 缺素材 → **黑屏 black + 报出来**（不再静默换别的图） |
| **语义检索** | `core/rag/place.py` | `PlaceRetriever` | 自由话语 → **表键**（语料 = 同一张表, PL4 起）。**没接线**, 别以为它在跑 |
| **改名台账** | `data/worlds/{world}/place_renames.jsonl` | `core/media/place_renames.py` | **key 不可改**，改名只改表 + 在这里留痕；`_place_bg()` 查不到旧名时会说"已改名为 X"。工具 = `python -m core.media.place_rename`（默认干跑） |

**路径一律走 `core/paths.py` 的宏**，别自己拼（`grep -n "^[A-Z][A-Z_]* = " core/paths.py`）。

---

## 2. 一条地点话的完整旅程（背下来，别猜）

> ⚠️ **先搞清楚"板"是什么**（2026-09-19 我在这一点上栽过）：
> **板 = 引擎的标注/推进单元, 不是剧情段；writer 根本不知道板存在。**
> 板在两种边界切开: ① `switch` ② **`sensei` 群结束（= 选项点）**（`records.py`）。
> 真机实测: haruka 6 板 / 2 switch / **5 板有选项**; mutsuki 14 板 / **1** switch /
> **13 板有选项** ⇒ **板主要是选项点切的, 不是 switch**。
> 所以"板内换场"这种说法**不存在** —— switch 会开新板, 选项点也会收板。
> 详见 `CLAUDE.md §6`。

```
writer 发  {"stage":"switch","text":"傍晚的学校天台"}
   ↓ 这里 writer 写什么都可以（表里没有也行 —— 这是设计，不是 bug）
引擎        bond_story.fill_scene_places()
   ↓
① 板首 switch → resolve_place()
     层1: 表里的 place + keywords 做字面命中 → **0 次 LLM 调用**
     层2: 把**整张表（含 note）**丢给廉价 LLM → 让它挑语义最近的一条
     都失败 → ""（keep，画面不动）
   ↓ 得到键，例如 school_rooftop
② 句级锚点 → annotate_places()  （同一块板内后续又换了地方时补刀）
   ↓
scene.place = 键           ← 进事件流（回放/记忆用）
scene.place_hint = 原话     ← 进事件流（检索/追溯用）
   ↓
引擎 _place_scene_id()  键 → 资产 scene_id（school_rooftop → school_rooftop）
   ↓
导演 visual_for(scene_id) → scene.background = 真 scene_id（**不是 neutral**）
   ↓
路由 _resolve_scene() → /assets/background/... → 前端换图
```

**记住两个"翻译"**（这是最容易搞错的地方）：

- **表键 ≠ 资产 scene_id**。表键 `classroom` ↔ 资产键 `class_room`；
  表键 `68office` ↔ 资产键 `kohshinjo_room`。翻译靠**表里 `files` 的文件名**，
  不是靠猜名字（`PlaceEntry.scene_id()`）。
- **板级 `place` 是键，`place_hint` 是原话**，两个都在事件流里。
- **`switch` 的 text 不一定是个地名**——writer 也会写**镜头词**（星空/纯黑/黄昏…,
  抄自 `llm/prompts/bond_shots.md`【一】那行）。那几条也在同一张表里
  （`sdir == "SDIR_Atmosphere"`）, 层1 直接命中 → 0 调用换一张天空/黑场图。
  对代码来说**和普通地点没有任何区别**（同一个 `resolve_place`）——别为它们写特例。

---

## 3. 记忆里存什么（M3）

`BrainNode` 上两个字段，**两个维度，别混**：

| 字段 | 存什么 | 判据 | 回答 | 单位 |
|---|---|---|---|---|
| `place: list[str]` | **键**序列 | **字面相等** | **同一张图**（回放） | 素材轴 |
| `place_raw: list[str]` | **writer 原话**序列 | **语义相似** | **同一个地方**（检索） | 叙事轴 |

都在 `digest` 里按 `event_seq` 从事件流**物化**（跟 `emo_shape` 同一手，0 LLM）。

- `region` **曾经也在节点上，已撤**（用户：*"基本没有太多作用，也不必落库"*）。
  它随时能从 `place_hint` 原文 + `regions.yml` 重算 ⇒ 落库是冗余的第二真源。
- **key / place_raw 都不进 LLM 上下文**（已核实 + 有测试钉住：
  `test_recall_side_fields_never_reach_llm`）。`render.py` 的四个视图从不读它们。

---

## 4. 那条"键不是地名的双射"的事（用户点出来的，很关键）

**键 = "用哪张图"的编号；不是"这是哪儿"的名字。** 两个方向都会错，两个方向
**实测都在表里活着**：

| 方向 | 实例 | 后果 |
|---|---|---|
| **一键多义** | `ruinschoolcorridor` 的 note 自己写着*"也可以用做老屋子或者某种杂草秘密基地"* | "走廊废墟"和"杂草屋"**同键** |
| **一地多键** | 别名 `天台` → 3 个键 | 都在天台却**不同键** |

⇒ **`place` 键相等只声称"同一张图"，绝不声称"同一个地方"。**
C 链路的 `by` 字段因此叫 `same_image`（不是"same_place"）。

**但别把这事想得太严重**（我一度想重了）：键分错组只影响**召回排序**，
不会往 LLM 里塞错内容（key 根本不进上下文）。而且 **C 链路现在压根没通电**
——`get_channel(...).gather(...)` 全库**只在测试里出现**。
所以"要不要给语义轴设阈值/建地点实体表"**暂时不做**，等真通电再说。

---

## 5. ⚠️ 会带偏你的旧话（逐条列出，见到就当它不存在）

| 你会读到的 | 真相 |
|---|---|
| `DESIGN_PLACE.md §1③` / `§5`（"注入活跃键表 ≤100 中文名""主 LLM 写 place 字段""time_of_day"） | **整节作废**，已加删除线。一条都没按它做 |
| `DESIGN_PLACE.md §2` 的 `time_of_day` | **没有这个字段**。`files.night` 至今**无消费方**（`background(sid, variant)` 的 variant 生产里从没传过） |
| `place_regions.py` 旧 docstring："C 链路吃 `region`" | **假的**。C 用过 place 键；region 已撤出记忆 |
| `place_regions.py` 旧 docstring："地点解析第一层 = switch 话 → region 归一" | **假的**。第一层是表的 `keywords` 别名命中 |
| `place_annotate.py` 旧话："P1-2 会用 tempo 导出视图替换词表" | **已做完**（就是现在这张表） |
| `channel_impl.py` 旧话：`needs: "episode.place"` / "BrainNode 无 place 字段" | **过时**。字段有了，链路实现也有了（只是没通电） |
| `CLAUDE.md §3.3 / §4`："词表 = `_director_whitelist.json` common_scenes" | **过时**。词表现在是 `place_entities.json`；旧白名单只剩降级 |
| `CLAUDE.md §10` / `DESIGN_PLACE §4`：资产是 `BG_*` 一目录一场景 | **要换成 `SDIR_*/DIR_*` 两级**（作者的 tempo 组织）。文件名不变 ⇒ `derive_background()` 结果不变 ⇒ 查库不受影响 |
| 任何"place 键 = 地点"的说法 | 键是**素材**，不是地点。见 §4 |
| 任何"缺素材就兜底一张别的图"的写法 | **已被用户否掉**：缺素材 → **黑屏 `black` + alert/console.log 报"素材未找到"** |
| "想给 writer 加个镜头词？改表就行，盒B 会自动跟上" | **假的**。writer 手里那份是**手写**的 `llm/prompts/bond_shots.md`——表改了不会自动进盒, **两处都得动**。测试只守一个方向（文件里的词必须是表的别名）, 守不了"表里新加的图没人用"以外的另一半 |
| "`PlaceRetriever` 返回 scene_id" | **PL4 起返回的是表键**（语料 = 表）。要图就走 `asset_scene(key)` / `PlaceTable.scene_id(key)`——`classroom` ↔ `class_room` 这对翻译别自己拼 |
| "key 不可改" = "key 永远不会变" | 前半句是纪律（**回放按 key 查表**，事件流 append-only 不许改），**不是**"改名不会发生"。改名 = **只改表 + 写台账**（`core/media/place_rename.py`），事件流一个字不动；旧板于是按旧名回放 → 查不到图时**先看台账**再喊"素材未找到" |
| "地点检索的语料在 `config/settings/world/places.yml`" | **文件已删（PL4 2026-09-19）**。语料 = `place_entities.json` 本身, `paths.PLACES_PATH` 宏也一并删了 |
| `CLAUDE.md §6` 旧配额句"规则层整章 0~3 次、**多数板无 choices**" | **v1 口径, v2 已废**。真机 **13/14 板都有 choices**（板由选项点切）。已于 2026-09-19 改正 |

---

## 6. 用户对这个系统的原话（别自己演绎）

- **核心逻辑**：*"主 LLM 可以随便写或仅仅掌握部分词表，然后由后台 LLM 标注；
  后台 LLM 由于任务极其单一，可以接受更复杂的巨大表单。"*
- **writer 的自由**：*"writer 当然可以说表外，为什么不能，writer 的自由不受限制，
  这个设计就是给 writer 最大自由防止注意力矩阵稀疏。"*
- **note 的作用**：*"annotation-llm 只要看到 note 就能大致推测出地点，这就可以了，
  而且关键地点还能给它当作注记注入 anno-llm，更加方便。"*
- **主 LLM 手里那份词表**：*"比较特殊，是某些特效比如说 black 或者星空这种词，
  这是因为这些词能让 LLM 更好的写作。"*（= 表里 `sdir == "SDIR_Atmosphere"` 的
  4 条：`view_sky`/`black`/`view_constellation`/`view_dawnsky`）
- **动态读入**：*"这个表因为官方地点的更新是会进行更新或者调整措辞的，所以最好是
  动态读入而非写成死代码。"* → 已做（mtime 缓存）。*"本来确实不需要动态注入，
  只是方便实时更新。"*
- **key 不可改**：*"key 是不可改的"*。缺素材：*"就用黑屏 black，且 alert/console.log
  素材未找到即可，批量替换不是一个很难的操作（不过重复键名有点头疼）"*。
- **region**：*"它只是用于判定在那个学院的，作用并不大，是为以后可能的地点体系做
  铺垫的产物，现在其实基本没有太多作用，也不必落库。"*
- **两轴**：*"key 需要用于回放，而 writer 名则需要用于检索，二者缺一不可……会不会
  是用于检索的两个维度？"* → 是，已按两轴落。

---

## 7. 还没做的 / 别自己开工

| 事 | 状态 |
|---|---|
| 语义轴"同地"的门槛（甲阈值 / 乙取前 N / 丙实体表） | **暂停**——C 没通电，做了也白做 |
| ~~地点语义检索的语料~~ | **✅ 换基座了（PL4, 2026-09-19）**: `PlaceRetriever` 现在直接吃这张表（168 键 / 428 别名, 与层1 同源）, 手维护的 `places.yml` 删了。⚠️ 但**接线还是没做**（"现在接 = 空转", 与召回策略同批）——它返回**表键**, 且层1 唯一命中时 0 调用、歧义时**不猜**（有 embedding 就排序, 没有就 `[]`） |
| 「AI 判过的映射」旁路 / 回灌 anno-llm | **用户说"先不干，把主要的弄完再说"** |
| 情景图/写作用词**成块注入**盒B | **✅ 做了（PL2, 2026-09-19）**——但**不是**从表生成: 用户要的是一份**手写的小文件** `llm/prompts/bond_shots.md`（【镜头与手法】），盒B 第 7 块（紧挨规则书）。⚠️ **手写 = 会漂** ⇒ `tests/core/test_bond_shots.py` 钉住: 【一】那行的每个镜头词都必须在**层1 唯一命中**（0 调用；层1 是"最长别名子串"匹配, 不必逐字相等）且落在写作用词上, 4 张 atmosphere 图一个不落（写错字会红, 不会静默退化成"多花一次调用 + 可能挑错图"） |
| 谁把表里的写作用词**交给 writer** | `PlaceTable.writing_words()` **至今没有生产消费方**（只有测试/stats 在读）——真正到 writer 手里的是上面那份手写文件。别以为改了表就会自动进盒 |
| `files.night`（日夜） | **仍然无消费方**（`time_of_day` 不存在）。变体（夜/夕/侵蚀…）目前**谁都选不了**: anno-llm 只输出一个键, 取图走 `catalog.background(scene_id, variant=None)` = 永远第一条无变体图（153 张 `_Night` + 35 张 `_Sunset` + 45 个键的第 2 张 base 图都闲置）。**这只是待决, 不是已定**——设计方案见 TODO「变体/两遍式」 |
| `ruinpianoroom`（废弃琴房）等**写了 note 却没勾 active** 的条目 | 作者侧一句话的事（翻 `active: true`） |
| ~~表维护纪律（key 不可改名 + 重复键名怎么办）~~ | **✅ 都落了（PL6, 2026-09-19）**: ①改名 = `python -m core.media.place_rename`（扫引用面/改表/留台账, 默认干跑; 台账 = `data/worlds/{w}/place_renames.jsonl`, 消费方 = `_place_bg()` 的"已改名为 X"）②重复键名 = 生成侧不存在（JSON 对象 + A1 撞车保护）, 读取侧 `load_table` 用 `object_pairs_hook` 数出来并报 `重复键 [...]`（手编文件骗不了人） |
