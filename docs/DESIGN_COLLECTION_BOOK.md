# 回忆册（Collection Book）— 设计稿

> **状态: 设计稿, 未实现**（2026-09-12 与作者逐条敲定; 动代码前先读 §8）。
> 术语纪律: 本稿的**「回忆册」= 书页 UI**;**「回放」专指只读播 VN 正文**——
> 与现网那个"中断重进 → 回放前缀 → LLM 续写"的 resume 型 replay 是两件事（§5）。

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

- 章的图 = 落在该章区间 `[vn_enter.seq, vn_exit.seq]` 内的 `memorial_image` marker。
- **预热先出图**（#40）: marker 落在 `vn_enter` **之前** → 归"紧随其后的那个 `vn_enter` 所属章";
  但两者之间夹了 `vn_abandon` → 作废（那是废弃章的图）。
- **精确挂载**（推荐）: v2 板的 payload 带 `memorial: true` → 图挂到**那块板**上,
  回放播到那一刻淡入——与 live 同观感; 一章多图就按顺序配对。
- 数量对不上时静默降级: 有板无图 → 纯文字; 有图无板 → 章末定格一张。
- 角色页的章节条目可以带**缩略图**（有图才有; 没图就是纯标题行）。

## 4. 回放语义: **只读型**（与现网的 resume 型区分）

| | 现网 replay（#38） | 册子的回放 |
|---|---|---|
| 触发 | 中断后重进同一章 | 册子里点某个**已结束**的章 |
| 行为 | 回放已记录前缀 → **LLM 续写** | 播完即停, **0 LLM** |
| 碰 live 状态 | 是（`BondState`/`_draft_queue`/预生成） | **否**——不碰状态机、不写事件流、不改玩家当前进度 |
| 原料 | 同一份 | 同一份（`replay_attempts` 是纯读） |

前端可复用度很高: `renderScene` 消费的 scene dict 与 live 同构, 选项组的
`.resolved` / `.picked` 锁定态是决策 #37/#38 就做好的。**所以工作量主要在"给现有渲染器
加一个只读喂数据模式", 而不是后端。**

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

## 7. 实施切分

**P0（做完就能用）**

- 后端: `chapters(char)` 纯函数（`replay_attempts` + `completed` 过滤 + `exclude_abandoned`
  + 标题回落链 + 图归属）→ 一个 GET 路由, 返回册子数据:
  `[{char, cover_url, chapters: [{from_seq, title, boards, has_memorial, memorial_url}]}]`。
- 前端: 书页 overlay（两半页 / 24 格 / 翻页）+ 角色页 + 只读回放视图。
- 测试: A 层 HTTP 用例——**只有 completed 的章出现在列表里**, 废弃章不出现, 未完章不出现;
  B 层浏览器走一遍（点格子 → 条目 → 回放 → 播完停在末板）。

**P1（攒着）**: 图挂 memorial 板（§3 精确挂载）、条目缩略图、CSS 3D 翻页、书签。

**明确不做**: 索引表（§2）、未完章的渲染（§1）、任何续写。

## 8. 未决（先按暂定走, 作者一句话可改）

1. **章标题缺失**（v1 旧档 / 异常）的兜底文案 —— 暂定: 触发事件 title → `display_name`。
2. **一章多图**的呈现 —— 暂定: 每张挂对应 `memorial` 板, 多余的挂章末。
3. **0 章角色的格子**（如真机的 `onikata_kayoko`: 只有 session_start）——
   暂定: 格子照常可点, 角色页显示空态文案"还没有结束的故事"。
