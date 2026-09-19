# 背景系统：组织形式与查询框架（DESIGN_PLACE, 2026-09-05 定稿）

> ## ⚠️ 状态（2026-09-15 校准——本稿此前**不在 CLAUDE.md 文档路由表里**，被漏读）
>
> | 节 | 状态 |
> |---|---|
> | **§1② 语义键层**（`_place_entities.json` 的 key/name/region/group/active/files） | ✅ **有效**，仍是目标形态 |
> | **§1③ 解析链**（语义名/描述 → **精确（id/name/别名）** → **embedding** → 阈值宁缺勿错） | ✅ **有效**——"两层解析"就是它 |
> | **§2 日夜组织**（`time_of_day` 独立字段, 不占键） | ✅ 有效; 未实现 |
> | **§1③ / §5 主 LLM 写 `place` 字段 + 注入活跃键表 ≤100 中文名** | ❌ **已被取代** |
>
> **取代链**：
> 1. **2026-09-10 记录流 v2**——换场改由 writer 发 `{"stage":"switch","text":"地点"}`，
>    **WHEN 归 writer、WHICH 归标注层**，主 LLM **不再写任何地点字段**
> 2. **2026-09-15 用户裁决"主 LLM 零内容词表"**——连"活跃键表"也不注入
>    （从列表里挑 = **收窄**创作空间）。改为**三档分流**：
>
>    | 档 | 给主 LLM | 现在能做？ |
>    |---|---|---|
>    | **粗粒度地理**（`region` 主名） | ✅ 文本说明（**世界设定, 非菜单**） | ✅ **T16 已落地** |
>    | **情景图**（`view_sky` 一类镜头） | ✅ 说明（**能力可见性**——不告诉它就永远不会用） | ⏸ 等 tempo 图片手写完成 |
>    | **具体地点**（`place` 键） | ❌ 不给 → 归异步 lane | ⏸ 等 tempo 表 |
>
> **实现进度**（2026-09-19 复核）：
>
> | 层 | 状态 |
> |---|---|
> | **粗粒度地理**（`region`） | ✅ **已接线**——盒B【世界区域】块 + 字符串归一（`core/parsing/place_regions.py`, T16） |
> | **语义键表**（`place` 查表键） | ⏸ **表已出、未接线**——`_place_entities.json` 在 tempo 工作区，**168 条 active**（2026-09-17）；Live2Be 侧零消费方 |
> | **情景图档** | ⏸ 挂起（等作者手写图片结束） |
> | **现役词表** | ⚠️ 仍是 `assets/_director_whitelist.json` 的 `common_scenes` — **31 条裸 slug**，与 tempo 表**无交集**（见 §6） |
>
> **表的实际形状**（与本节下方 §1② 的旧描述不同——以表为准）：
>
> ```json
> "big_bridge": { "sdir": "SDIR_Streets", "dir": "DIR_BigBridge",
>                 "place": "big_bridge",      // ← 查表键（唯一标识）
>                 "region": "",               // 剧情地理（regions.yml 主名）
>                 "keywords": ["桥","天桥"],   // 别名（检索用）
>                 "files": {"day": [...], "night": [...]} }
> ```
>
> **字段名统一（2026-09-19 用户裁决）**：`key`(导出外层键) / `name`(旧字段) /
> `place`(现字段) 三者曾**同指一个概念 = 查表键**。统一为 **`place`** —— 依据是
> 工具自己的迁移函数 `place_studio._migrate_export_entry()`（"把旧导出里的 name
> 字段迁移成 place" + `entry.pop("name")`）与 `default_place()` 的 docstring
> （"作为 place 默认查表键"）。
> **导出外层键也已收口到 `place`**（A1, 2026-09-19）—— 此前是自动派生的族键
> `root`，与手写 `place` 有 **103/168 条不等**（同一行两个标识符）。重导后
> 168/168 键 == 行内 `place`，行内容零差异。
>
> ⚠️ **表必须动态读入，不许在代码里写死任何地名**（用户 2026-09-19）：
> *"这个表因为官方地点的更新是会进行更新或者调整措辞的，所以最好是动态读入
> 而非写成死代码。"* 落地要求见 §7。
>
> ⚠️ **表自身的四处缺口**（2026-09-19 实测，接线前必修）：
> ① `keywords` **168/168 都是单元素数组**（工具按 `,` 拆，作者写的是 `/`）→ 别名表恒不命中；
> ② `region` **148/168 为空**；
> ③ `files.night` 里混着**状态变体 25 张**（ruin/erode/blur/off/dark/party/fake）+
>    **白天天气 7 张**（fog/rain/cloudy/dawn/sky）→ 只有 115/168 是真夜景；
> ④ review 里的 `note`（**245/246 条有值**，是作者写的用途说明，如 "这个更加偏向
>    天台，有护栏"）**不进导出** —— 而这正是标注 LLM 判"该用哪张"的依据。
>
> ⚠️ 另有**双表漂移**: `place_studio.py` 内嵌了一份自己的 `REGIONS`,
> 与 `config/settings/world/regions.yml` 各一份。
>
> **工具位置**（2026-09-19）：`place_studio.py` **只在工作区**
> `D:\myStuff\tempo\`（09-15 版，含 SDIR/DIR 组织 + 导出重写）; 仓库内那份
> `tools/place_studio.py`（09-07 旧版）**已删**——两份内容不同，留一份防漂移。

> 触发：资产 1094 张 / 620 scene_id——LLM 无法面对全量; 地点语义（杂草屋=破房子）
> 不在资产名里; 背景单调（LLM 无候选可选/不敢转场）。
> 定稿路线：**存储走现行自动扫描（扩展最优）, 键表 = 活跃语义视图, 日夜 = LLM
> 可选字段**——不是新存储, 是"存储上的语义层 + 契约字段"。

## 1. 三层框架

```
① 资产层（存储——现行不变）
   assets/background/{BG_*}/BG_{Scene}_{Variant}.jpg
   命名规范: camelCase scene + VARIANT_TOKENS 变体（night/sunset/...）;
   无变体后缀 = day（默认）
   自动扫描 → catalog（scene_id × variant, 加图自动可见——扩展零注册）
   整理时用不到的 → 移 _unused/（保留资产, 不进活跃键）

② 语义键层（活跃视图——整理产物, `_place_entities.json`，落在 tempo 工作区）
   每条 = 一个可被剧情提到的地点（日夜无关）; **外层键 = `place` 查表键**
   （2026-09-19 统一；旧稿写的 `scene_id`/`name`/`group` 已作废——见文首状态头）:
     place:    查表键（latin snake；作者手写优先, 缺省回落文件公共前缀）
     region:   剧情地理（可选; region 子集注入用）
     sdir/dir: 资产组织归属（SDIR_Streets/DIR_BigBridge）——**表自带三档分流的判据**
     keywords: 别名数组（剧情里的俗称/描述词; 层1 精确命中的语料）
     note:     用途说明（作者写"这个适合什么戏"——**标注 LLM 的判据, 现在不进导出**）
     files:    {day: [...], night: [...]}（按变体归位——日夜不占键）
   数量目标: 活跃 ~150-250（资产 ÷2 的现实值）; 键量由"语义归并 + 剔除"决定
   现状: 168 条 active / 246 条已审 / 468 组（覆盖 435 张图 = 全库 39%）

③ 契约/查询层
   story_scene payload 扩展:
     place:        语义名（候选注入 = 活跃集上下文子集 ≤100 或自由描述）
     time_of_day:  "day" | "night"（可选字段, 缺省 day——LLM 显式表达剧情氛围）
   程序解析链（core/rag, 语料 = 语义键表同源）:
     语义名/描述 → 精确（id/name/别名）→ embedding（跨语言中英日）→ 阈值宁缺勿错
     → scene_id × time_of_day variant → 资产 URL（无夜景 → 静默降级 day）
   切换保障: 候选含 60-100 语义名 + LLM 每场决策 → 剧情转场即换图（单调消除）
```

## 2. 日夜组织（独立字段, 不占键）

```
time_of_day: LLM 可选（"night" 或省略=day）——夜晚是剧情氛围决策, 表达权在 LLM
资产: scene × variant（_Night 文件已在位 337 张）
程序: night → 查 files.night → 缺 → 降级 day（宁缺勿错静默）
未来扩展: sunset/dawn 等 = 字段枚举 +2, 资产按 VARIANT_TOKENS 规范加图即可
```

## 3. 扩展性结论

| 动作 | 成本 |
|---|---|
| 加新地点图 | 资产落位 → 扫描自动可见 → 键表补 place 一次（工具辅助） |
| 加时刻变体 | 按命名规范加 _Night 文件 → files.night 自动归位 |
| 新区域/角色主场 | 键表 region 标注 → region 子集注入自动受益 |
| 玩家自由指定地点 | 自由描述 → 检索链（embedding 泛化）——CLAVIN 式后续 |
| 未来 embedding/记忆 RAG | 键表 = 语料/描述文档同源——一次构建双用 |

## 4. 整理操作规范（作者 tempo 工作流）

> **2026-09-19 更新**：资产组织已从"官方 `BG_*` 一目录一场景"换成
> **`SDIR_*/DIR_*` 两级**（工具 09-15 版起只认这个结构）。十个 SDIR 是
> **作者的语义大类**（不是官方命名）：`Atmosphere`（黑场/纯色/PV 全景/天空）·
> `Clubs`（社团据点）· `Infrastructure` · `Inner` · `Nature` · `Outer` ·
> `Public` · `Schools` · `Special` · `Streets`。
> ⚠️ **文件名不变** → `derive_background()` 派生的 scene_id 不变，
> `MediaCatalog._scan_backgrounds()` 用 `rglob` 递归，**换组织不影响查库**；
> 但 `background_dirs()` / `background_scenes_in_dir()` 会随目录名失效
> （两者目前零消费方）。

1. 目录结构 = `{bg-root}/{SDIR_*}/{DIR_*}/BG_{Scene}_{Variant}.jpg`; 逐 DIR 清理/补全
2. 命名规范不变: `BG_{Scene}_{Variant}.jpg`（Scene camelCase; Variant ∈ 白名单）
3. 同一地点的多镜头/版本图: 保留但语义键层自动同族（工具里可见/可调）
4. 确定用不到的（事件图/纯特效/重复）→ `DIR_Z` / `TRASH_*`（工具标 `suspect`,
   但**作者仍可把其中的组勾成 active** —— 现状 `DIR_Z` 里有 13 组是 active）
5. 产出物: 完整 `assets/background/`（= tempo 树）+ 工具审定的 `_place_entities.json`
   （工具: **`D:\myStuff\tempo\place_studio.py`**——看图/命名/region/剔除/进度/导出。
   仓库内不再放副本, 防双份漂移）

## 5. 契约接线（整理完成后实施）

- story_scene schema: place 语义名白名单（soft）+ time_of_day 枚举
- 注入: 活跃键表（region 子集 ≤100 中文名 + 分组标题 ~2k 字）
- bond_story_rules / 词表指引: "每个场景标 place; 夜晚剧情写 time_of_day=night"
- director: visual_for(place, time_of_day) → 变体选择
- core/rag place.py 语料升级 = 语义键表（别名同源）

## 6. 标注层：主 LLM 零内容词表 → 后台标注吃整表（2026-09-19 定稿）

> 核心逻辑（用户 2026-09-19 原话）：
> *"主 LLM 可以随便写或仅仅掌握部分词表，然后由后台 LLM 标注；后台 LLM 由于
> 任务极其单一，可以接受更复杂的巨大表单。"*

三段拆开：

**① 写（主 LLM）——自由优先，写表外地名是设计的一部分，不是缺陷**

> *"writer 当然可以说表外，为什么不能，writer 的自由不受限制，这个设计就是给
> writer 最大自由防止注意力矩阵稀疏。"*（用户 2026-09-19）

给 writer 的东西只有两类：
* **粗粒度地理**：`region`（21 条学院主名）——**世界设定**，不是可选空间。
* **一小撮"特效/情景词"**（`black`、`星空`…）——**这是主 LLM 唯一的内容词表**，
  判据是 *"这些词能让 LLM 更好的写作"*（用户 2026-09-19）——不是"可选空间菜单"，
  是**写作手段**。来源现成：表里 `sdir = SDIR_Atmosphere` 且 active 的条目
  （现 4 条：`view_sky`/`black`/`view_constellation`/`view_dawnsky`）——
  **判据是表自带的 `sdir`，不许另立名单**。
  旁证：`bond_story_rules.md:87` 的示例 `{"stage":"switch","text":"星空"}`
  正对应 `view_sky` 的 keyword `星空` —— 盒里那个示例**是故意的**。

其余地点一律**自由写**，包括表里没有的（`深夜的杂草屋`）。

**② 判（后台标注 LLM / 异步 lane）**——输入 = 原短语 + **整张表**
（168 条 × `place`/`keywords`/**`note`**/`region`），输出 = 一个 `place` 键。
**因为它的任务单一（只答"这句话说的是哪个地点"），表可以大到 168 条。**

| 层 | 做什么 | 成本 |
|---|---|---|
| **层1 精确命中** | `keywords` 别名 / `place` 整串或子串命中 | **0 调用**（纯字符串） |
| **层2 LLM 解析** | 吃整表（**含 `note`**）**就近推测**一个键 | 1 次廉价调用（off-thinking） |

> ⭐ **`note` 是"表外也能用"的全部依据**（用户 2026-09-19）：
> *"背后的 annotation-llm 只要看到 note 就能大致推测出地点，这就可以了，
> 而且关键地点还能给它当作注记注入 anno-llm，更加方便。"*
> 所以 **`note` 不进导出 = 这条路直接断掉** → A3 是关键路径，不是锦上添花。
>
> ⚠️ **与现役 prompt 冲突**：`place_resolve.md` 现在写着"词表里没有能对上 →
> `{"place": ""}`（宁可空着，不要硬凑一个近似的）"、`place_annotate.md` 写着
> "拿不准 → 不标"。**"大致推测"与"宁可空着"是两条相反的指令**——按上面的模型，
> 该改成"读 `note` 选语义最近的一个"。改动在**标注 prompt**（不进盒，无夹具影响）。
>
> 只有"与当前地点相同"仍走 `""`（画面不用动）。

**③ 用**——`place` 键 → `files.day` / `files.night` → 资产 URL。
**这是表的唯一消费目的**（不再走 `catalog.background(scene_id)` 的命名派生：
族键≠scene_id，且表自带文件清单）。

### 三档分流（给主 LLM 什么）

| 档 | 判据（表自带） | 给主 LLM | 谁解析 | 状态 |
|---|---|---|---|---|
| **写作用词**（特效/情景） | `sdir = SDIR_Atmosphere` 且 active（现 4 条: `view_sky`/`black`/`view_constellation`/`view_dawnsky`） | ✅ **小词表**（`black`/`星空`…——**唯一的内容词表**, 判据"能让 LLM 更好地写"） | 层1 → 层2 | ⏸ 词已在表里, 尚未作为块注入（只有 `星空` 一个示例在盒里） |
| **粗粒度地理** | `region` | ✅ 文本说明（世界设定, 非菜单） | 别名的纯字符串归一 | ✅ T16 已落地 |
| **自由地点** | 表外/表内均可 | ✅ **自由写, 不受限**（防注意力矩阵稀疏） | 层1 → **层2 读 `note` 就近推测** | ⏸ 等接线 |
| **具体地点键** | 其余 `place` 键 | ❌ 不给键（列表 = 收窄创作） | 异步 lane | ⏸ 等接线 |

> 后两行**不是对立的**：writer 的自由输出（无论表内表外）都归同一个 lane，
> 表内命中率高、表外靠 `note` 推测——**表外不是失败路径，是设计主路径**。

### ⚠️ 现役实现与这套逻辑的差距（2026-09-19 实测）

1. 词表是 **31 条裸 slug**（`assets/_director_whitelist.json` 的 `common_scenes`），
   不是 168 条带别名与说明的表 → **真机 3/3 换场 MISS**，board 级 `place` 0 条
2. 两个标注 prompt 只给 **id 列表**，**没给 `keywords` / `note`** ——
   而 `note` 才是"这个地点适合什么戏"的判据
3. **没有层1**：每次换场都是一次 LLM 调用（进程内缓存 `_RESOLVE_CACHE` 只省重复）
4. `keywords` 分隔符 / `note` 不进导出 / 103 条 `place` 漏下划线 —— 见文首状态头

> 未决项（用户 2026-09-19 表示"我自己也无法确认"）：**C 链路「同地」判据吃
> `place` 还是 `region`** —— 两处代码口径相反（`core/parsing/place_regions.py:18`
> 说"默认不吃 `place` 键，吃 `region`"；`core/brain/wiki_v2/channel_impl.py:277`
> 的 `needs` 写 `episode.place`）。见 `TODO.md` 地点节。

## 7. 动态读入（表随官方地点更新 —— 用户 2026-09-19）

> *"这个表因为官方地点的更新是会进行更新或者调整措辞的，所以最好是动态读入
> 而非写成死代码。"* … *"本来确实不需要动态注入，只是方便实时更新。"*

**性质**：这不是设计硬约束，是**实现选择——为了能实时更新**（改表即生效，
不用改代码、不用重启）。但既然要做，就做干净：

1. **表里已有的信息不写死在代码里**——包括"兜底用哪个背景""默认地点是什么"。
2. **路径可配**（构造参数覆盖默认值；默认值来自 `core/paths.py` 的宏
   `PLACE_TABLE_PATH`，换表/换世界线不用改代码）。
   📌 **固定路径一律写成 `core/paths.py` 的顶层宏**（用户 2026-09-19）：
   *"这种固定路径我推荐你写成 macro 的形式放在最上面……最后改成你用 grep 能
   直接全量定位的方法。"* —— 全量定位两条 grep：
   `grep -n "^[A-Z][A-Z_]* = " core/paths.py`（有哪些）/ `grep -rn "paths\.[A-Z]"`（谁在用）。
   由 `tests/core/test_paths.py` 守门（现拼项目根路径会直接红）。
3. **按 mtime 缓存**：`(path, mtime_ns, size)` 变了就重读 —— 作者改完表重导，
   下一次调用即生效，**不重启 webgui**。
4. 缺表/坏表 → **空表降级**（回落到"不标注地点"，画面保持），绝不抛（宁缺勿错）。

> **盒不需要动态**：盒里给 writer 的写作用词是**刻意选定的稳定少数**
> （`black`/`星空`——为了让 LLM 写得更好），它们不随表的增补而变；
> writer 的表外自由输出也不需要进盒（那是 anno-llm 的事）。
> 所以**"稳定前缀 ↔ 动态表"不构成矛盾**——动态读入只服务标注层。

### 现在写死的地名清单（接线时逐个拆）

| 位置 | 写死了什么 | 处置 |
|---|---|---|
| `webgui/routers/bond.py:55` | `_BG_FALLBACK_PRIORITY` — **7 个地点 id 在代码里** | 改由表/数据给（"哪张图能当通用底"） |
| `core/director/state.py:13` | `DEFAULT_BACKGROUND = "neutral"` —— **一个不存在的场景 id** | 改成表驱动的默认 |
| `assets/_director_whitelist.json` | `common_scenes`(31) + `common_dirs`(23) | 退役（`common_dirs` 换组织后必废） |
| `config/settings/world/places.yml` | 31 条 scene slug | 由表的 `keywords` 生成，别手维护第二份 |
| `llm/prompts/place_annotate.md` | 示例键 `rooftop` —— **表里没有**（是 `school_rooftop`） | 改（标注 prompt 可以动态，见下） |
| `place_studio.py`（tempo） | 内嵌第二份 `REGIONS`(21) | 收口到 `regions.yml` |
| `llm/prompts/bond_story_rules.md:52/87/95/106`, `contract/schema.py:192` | 示例地点「深夜的杂草屋」「放学后的天台」「星空」「傍晚的杂草坡道」 | **盒里保持静态**（前缀稳定）——**这不是问题**：写作用词（星空）与自由地点（杂草屋）都是设计要的，见上 §7 尾注 |
