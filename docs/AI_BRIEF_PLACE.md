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
| **表加载器** | `core/media/place_table.py` | `PlaceTable` / `load_table()` | 层1 别名命中 + 层2 整表文本。**按 mtime 缓存**（改表即生效，不重启） |
| **区域词表** | `config/settings/world/regions.yml` | 21 条学院主名 | **只给盒B 的【世界区域】块用**。跟"同地"判定**没关系**（已被用户撤出记忆） |
| **旧白名单** | `assets/_director_whitelist.json` | 31 条裸 slug | **只是降级兜底**（表读不出来时才用）。别再把它当词表 |
| **资产** | `assets/background/**` | 1094 张图 | 表的 `files` 里写的是**相对 `assets/background/` 的路径** |
| **回放/显示** | `webgui/routers/bond.py::_resolve_scene` | key → 图 URL | 缺素材 → **黑屏 black + 报出来**（不再静默换别的图） |

**路径一律走 `core/paths.py` 的宏**，别自己拼（`grep -n "^[A-Z][A-Z_]* = " core/paths.py`）。

---

## 2. 一条地点话的完整旅程（背下来，别猜）

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
| 「AI 判过的映射」旁路 / 回灌 anno-llm | **用户说"先不干，把主要的弄完再说"** |
| 情景图/写作用词**成块注入**盒B | 词在表里，还没做成块 |
| `files.night`（日夜） | 无消费方，`time_of_day` 不存在 |
| `ruinpianoroom`（废弃琴房）等**写了 note 却没勾 active** 的条目 | 作者侧一句话的事（翻 `active: true`） |
| 表维护纪律（key 不可改名 + 重复键名怎么办） | key 已定不可改；**重复键名**用户说"有点头疼"，未定 |
