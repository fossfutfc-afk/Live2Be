# 回忆册（Collection Book）— 设计稿

> **状态: P0 已落地**（2026-09-12; 设计 2026-09-12 与作者逐条敲定, 同日实现）。
> 落地清单: `core/session/chapters.py`（派生）+ `webgui/routers/collection.py`（三个只读路由）
> + `webgui/static/js/collection.js` / `css/collection.css`（书页/角色页）
> + `BondVN.enterReadonly`（只读回放）+ 主界面"回 放"按钮接线。
> 测试: `tests/core/test_chapters.py`（10 例）+ `tests/webgui/test_web_http.py::test_collection_book_routes`
> + B 层冒烟"回忆册/只读回放"步骤。**P1（图挂 memorial 板/缩略图之外的呈现/3D 翻页/书签）未做。**
> 术语纪律: 本稿的**「回忆册」= 书页 UI**;**「回放」专指只读播 VN 正文**——
> 与现网那个"中断重进 → 回放前缀 → LLM 续写"的 resume 型 replay 是两件事（§4）。

---

## 1. 形态（作者口径 2026-09-12）

- 网页正中一个大白框 = **书页**, 分左右两个半页; 每半页 **3 行 × 4 列 = 12 格**,
  一个跨页 **24 格**。
- **一格 = 一个角色**（不是一章）。封面 = `{cid}/{outfit}/portrait/collection.png`。
- 排列顺序 = `config/settings/mmt_registry.toml` 白名单顺序（作者维护的真源）。
- 放不下 → **翻页按钮**（按跨页翻, 不是按半页）。
- **无素材角色 → 留白格**（没有 collection.png 也**占位**）: 顺序因此稳定,
  且玩家看得出"这里还有一个我拿不到的人", 比整格消失好。

**点格子 → 角色页**（第二层）:

- 列出该角色的 **bond story 标题**, 顺序 = `events.jsonl` 行序（= 事件 `seq` 升序）。
- 每条标题旁一个**按钮** → 进入回放。
- **只有"确认结束"的章才渲染**（`vn_exit.payload.completed == True`）;
  未完 / 中断 / 废弃的章**连条目都不出现**（不是灰掉, 是根本不画）。
  - 理由（值得记下来）: 未完章的正文还会继续长——渲染它 = 册子里放了一段**可变**
    的内容, 而回忆册承诺的是"已经结束、不会再变的记忆"。这也是 append-only 语义下
    唯一能保证"回放内容 = 当时看到的内容"的判据。
- 标题真源 = `vn_enter.payload.chapter_title`（`SessionStore.enter_vn` 的 docstring
  已声明"回放/章节列表消费"）; 缺失 → 回落该章前最近一条
  `mmt_trigger_bond_story.chapter_title` → 角色 `display_name`
  （复用 `webgui/chat.py` 那条既有优先级链, 别另写一套）。

## 2. 数据来源: **从事件流派生, 不建索引表**（决策）

"每完成一个 story 就往某张表里注册"这个想法我否掉了, 理由是它是**第二份真相**:

1. 章会被 `vn_abandon` 废弃（真源里"发生过又作废"）——表里写过的那行怎么办?
   append-only 不能改, 于是表和真源永久分叉。
2. 纪念图**异步后到**（决策 #40: 预热期先出图, `vn_enter` 都还没写）——表行写完时图还没到。
3. 表写入点与"章结束"不是原子的: 写完表崩 / 写完章崩, 两种崩溃都留下不一致。

而需要的信息**一次扫描就能算出来, 且 0 LLM**——现成零件已经齐了:

| 需要 | 现成零件 |
|---|---|
| 章分段 + 是否结束 + 正文场景 | `webgui/bond.py:replay_attempts()`（按 `vn_enter` 分段, `vn_exit.payload.completed` 定 completed, 未关段 = interrupted） |
| 章标题 | 同上（读 `vn_enter.payload.chapter_title`） |
| 废弃段过滤 | `core/session/maintenance.py:exclude_abandoned()` + `abandoned_ranges()` |
| 纪念图 | `core/media/gallery.py:GalleryStore.list(char)`（png+json 成对才算） + `memorial_image` marker |
| 每角色一条线 | `SessionStore.char_dir(cid)` + `meta.session_id`（v2 单事件流, 无子会话） |
| 全扫事件文件的先例 | MMT 列表路由每请求 `load_affection_from_events` 全扫 —— 这在本项目是既有惯例, 不是新负担 |

事件流路径 = `data/worlds/{world}/characters/{char}/**soul/**events.jsonl`
（`store.py:events_path`——soul/ 是记忆层, events 原材料与 wiki 成品同居）。

**真机现状（2026-09-12 读 `data/worlds/world1`, 验证本稿的标题假设）**:

```
asagi_mutsuki   vn_enter seq=27 title='咖啡厅的甜点陷阱' → vn_exit seq=56 completed=True  ✅可回放
igusa_haruka    vn_enter seq=13 title='杂草屋的品种调查' → vn_exit seq=26 completed=True  ✅可回放
onikata_kayoko  只有 session_start（无章）→ 角色页空态
rikuhachima_aru 无事件流文件
```

两个结论: ① `vn_enter.payload.chapter_title` 在真机流里**确实是有的**（§1 的标题口径成立）;
② 三份流里**都没有 `memorial_image` marker** → 眼下这两个条目都会走"降级为 VN"那条路,
纪念图分支要等真机跑出一次纪念才有数据（与"纪念链路尚未真机验收"一致）。

**两个必须踩上的坑**:

- `replay_attempts()` **不处理 `vn_abandon`**——废弃章会以 `interrupted=true` 混进结果。
  册子必须套 `exclude_abandoned` 的同一套判据, 否则废弃章会出现在册子里（真机已有废弃段,
  这不是理论问题）。
- 过滤掉 bond 事件后**只剩标题、没有正文**的章（极端: 全段被废弃）也不渲染——
  "渲染都不渲染"的同一条原则。

**升级路线**（真到了瓶颈才做, 按顺序）:

1. 开书慢 → **进程级缓存**（key = 事件文件 `mtime+size`）; 先例 `place_annotate._RESOLVE_CACHE`
   （新增模块级缓存要登记到 `tests/conftest.py:_clear_module_caches`）。
2. 还慢（几十个角色 / 单文件 10MB+）→ **落盘派生缓存**: 每章一行 JSONL, 由
   `vn_exit completed` 那一刻追加（与 digest 同一触发点）, **开书时校验、不一致以事件流为准并可一键重建**。
   真源永远只有 `events.jsonl` 一处。

世界线: 一本书 = **当前世界**（`data/worlds/{world}/characters/*`）——画廊本来就按世界线隔离,
册子跟着隔离, 不跨周目混。

## 3. 纪念图怎么出现（回放里的图）

**已实现的归属规则**（`core/session/chapters.py:_memorial_urls`, 实现时被测试逼着收敛成三条）:

1. **板锚点说了算**: 找该图 marker **最近的前置 `memorial_enter`**（那才是"哪块板触发的图"）——
   锚点落在某章内 → 图归该章; 锚点落在章前的空档（预热板）→ 归紧随其后的那一章（#40）。
2. **没有锚点时退回区间判据**（v1 档 / 图先于板落盘）: 图在章区间内 → 该章;
   在 `vn_enter` 之前 → 紧随其后的章; 中间夹 `vn_abandon` → 作废。
3. **孤儿**（锚点/图之后没有任何新章）→ 不显示（没有章可挂）。

> **为什么必须有第 1 条**: 生图 ~26s, 而纪念多在本章末尾——**图经常在本章 `vn_exit`
> 之后才落盘**; 只按区间判会把它错挂到下一章（玩家在下一章看到上一章的画）。
> 这是实现期写测试时才发现的口径漏洞, 已写成用例 `test_memorial_image_attribution`。

P0 只把图挂到**章**（角色页条目上的缩略图 + `memorial_url`）; **播到那一刻淡入**
（图挂到具体那块 `memorial` 板）留 P1——板 payload 带 `memorial: true`, 数据已具备。

## 4. 回放语义: **只读型**（与现网的 resume 型区分）

| | 现网 replay（#38） | 册子的回放 |
|---|---|---|
| 触发 | 中断后重进同一章 | 册子里点某个**已结束**的章 |
| 行为 | 回放已记录前缀 → **LLM 续写** | 播完即停, **0 LLM** |
| 碰 live 状态 | 是（`BondState`/`_draft_queue`/预生成） | **否**——不碰状态机、不写事件流、不改玩家当前进度 |
| 原料 | 同一份 | 同一份（`replay_attempts` 是纯读） |

前端可复用度很高: `renderScene` 消费的 scene dict 与 live 同构, 选项组的
`.resolved` / `.picked` 锁定态是决策 #37/#38 就做好的。**推进机制** = 点画面
（决策 #41 删掉了"▼ 继续"按钮）; 回放里**所有选项可点**——点了只是推进（本地下一板）,
高亮仍留在当时选的那句（"毕竟都是一句话": 收敛链下两句通往同一后续）。

## 5. UI 细节（先定死, 免得来回改）

- 格子里的图用 **`contain` 不用 `cover`**: `collection.png` 是 404×456 竖版半身像,
  MMT 头像那种圆形 `cover` 裁剪会切掉帽子和光环。图鉴要完整。
- **翻页动效先做便宜的**（淡入/滑动）, CSS 3D `rotateY` 翻页留作加分项——
  24 张图同时做 3D 变换在低端机会掉帧。
- **分页漂移**: 组内按时间**正序**（新章进组尾）+ **不做"上次读到第几页"**。
  若将来要书签, 再讨论"新章插入导致页码位移"。
- 留白格画成**浅色占位框**, 不是纯空白。

## 6. 术语（已同步进 CLAUDE.md §1）

| 词 | 含义 |
|---|---|
| 回忆册 | 书页 UI（大白框 / 两半页 / 一格一角色） |
| 角色页 | 点格子后的第二层: 该角色**已结束**章节的标题列表 |
| 章节条目 | 角色页里一行标题 + 进入回放的按钮 |
| 只读回放 | 册子里的回放: 播完即停、0 LLM、不碰 live 状态 |

## 7. 实施切分（P0 = 已落地）

**P0（做完就能用）—— 已实现 2026-09-12**

- 后端: `core/session/chapters.py:replayable_chapters/chapter_index`（纯派生）→
  `webgui/routers/collection.py` 三个只读路由:
  `GET /api/collection/book`（角色格 + 封面, **不扫章**——开书零成本）
  `GET /api/collection/{cid}/chapters`（已结束的章; 不背正文）
  `GET /api/collection/{cid}/{from_seq}`（逐板 scene + 当时的选择; 章不存在/未结束 → **404**）
- 前端: `collection.js`（书页 24 格 / 翻页 / 角色页 / 留白格）+ `collection.css`;
  `BondVN.enterReadonly(payload, onExit)` 复用 live 渲染器逐板播, 播完出"▸ 返回回忆册"
  （决策 #41 后是交互区里唯一的按钮; 推进 = 点画面, 选项可点=只推进）。
- 测试: `tests/core/test_chapters.py`（10 例: 只收 completed / 废弃 / 空壳 / 旧档 /
  图归属三条 / 流序 / 索引不带正文）; `test_web_http.py::test_collection_book_routes`
  （书页 4 格 3 留白 → 角色页 1 章 → 回放 3 板含 picked → 未完/废弃/不存在章 404）;
  B 层冒烟: 书页 → 角色页 → 只读回放 → 播完返回, 并断言**全程 0 个 bond 写请求**。

**只读保证（三层）**: ① 后端只有读路由, 没有写路径; ② 前端 `submit()/finish()` 在
`readonly` 下短路成本地推进（绝不 POST）; ③ 冒烟监听 `POST /api/bond/{start,turn,finish}`
计数为 0。

**P1（攒着）**: 图挂 memorial 板（播到那一刻淡入）、CSS 3D 翻页、书签/续读位置。

**明确不做**: 索引表（§2）、未完章的渲染（§1）、任何续写。

## 8. 未决 → 已按暂定实现（作者 2026-09-12 "都按暂定的来做"）

1. **章标题缺失**（v1 旧档 / 异常）→ 前端兜底 `第 N 章`（后端 title 原样给空串;
   角色页按序号补）。**注**: 触发事件 title → `display_name` 那条链在 P0 没接
   （需要跨到 mmt 触发事件去查）——真机两章都有标题, 等真出现空标题再补。
2. **一章多图** → P0 取**最后一张**作章代表（`memorial_url`）; 逐张挂板的呈现留 P1。
3. **0 章角色的格子** → 格子照常可点, 角色页显示"还没有结束的故事。"
