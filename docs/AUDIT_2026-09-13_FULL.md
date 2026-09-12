# AUDIT_2026-09-13_FULL.md — 全项目代码审计（只读）

> **状态**: 一次性审计快照（非设计文档; 修完即勾, 全修完可归档 docs/archive/）。
> **方法**: 四个并行只读审计（bond 引擎 / webgui+promptkit / brain+MMT / 测试+回忆册）
> + 父代理对高危项**实机复核**（读真实 `data/`、跑探针脚本, 不只看代码）。
> **纪律**: 一切以代码为准。下列标 ✅ 的项由父代理**亲自验证**（含运行证据）;
> 标 ⚠️ 的项来自审计回执、未逐条复跑。修复前请以标注为准决定是否复核。
> **范围外**: 背景/地点链路（tempo 素材库尚未整理完, 用户 2026-09-13 明确暂不做）。
>
> **修复进度**: **拆分点 A（embedding 降级可观测）已落地**（2026-09-13）——
> `core/momotalk._get_embed_fn`（健康判定 + 跳变上报）+
> `core/brain/wiki_v2/recall.py`（两条降级路径带 reason 日志）。**580 测试绿**。
> 详见文末 §8。
>
> **2026-09-13 已修（与图/RAG 无关的批次, 用户指定）**:
> A1 设置页裁配置 · A2 留白格不可点 · A6 看门狗前置条件 · B1 退役场卡 ·
> B5 章末闭合纪念窗口 · B6 落库失败永久丢板 · B17 `reset_engines` 清锁 ·
> B18 `_wrapup_inner` 全局 store · **B21**（新增条目）退役 v1 表情单调注记 ·
> **E11** 轮数跨重连恢复。
> **已撤销 2 条误报**: B2（批式/流式切板**等价**）· B13（选项真源**一直是对的**,
> 缺的是断言）——两条均见该行说明与复核方法。
> **B19 订正**: 现象成立但**原修法无效**（清空语句在快路径 `return` 之后,
> 队列非空时不可达）——见该行; 仍未修, 已留注释防重踩。
> **编号说明**: 本条曾误写为"B8 退役 v1 表情注记"——**表里 B8 是另一件事**
> （`_trim_history` 从头截断破坏前缀缓存, **未修**）; 表情注记原表无条目, 现补为
> **B21**（见 §2 表末）。按 ID 追进度时以 §2 表为准。
> 回归 594 passed。

---

## 0. 复现基线

| 项 | 值 |
|---|---|
| 解释器 | `C:\Users\johnf\miniconda3\envs\live2be\python.exe`（miniconda **base 无 yaml**） |
| 测试 | **566 passed / 0 failed / 0 skipped, 31.02s**（按 §12 原命令会 566 ERROR——见 B7） |
| 现网数据 | `data/worlds/world1/characters/{5 角色}/soul/events.jsonl`（haruka 31 事件, mutsuki 61） |

---

## 1. A 级 — 已复核的数据/配置破坏（建议立刻修）

### A1 ✅ GUI 保存设置 = 静默删除用户配置（最高危）
`webgui/store.py:86-96 save_settings()` 只遍历 `DEFAULTS` 的**已知分组/字段**写回文件,
而 `DEFAULTS`（`store.py:41-63`）只有 `llm` 三键 + `image`。

**实机探针证据**（`load_settings()` 读真实 settings.toml → 模拟 GUI 提交 → 看写回键）:
```
真机键 : [llm] api_key, base_url, model, reasoning_effort, use_proxy
         [image] 9 键
         [bond] choice_pregen
写回键 : [llm] api_key, base_url, model          ← 丢 reasoning_effort, use_proxy
         [image] 9 键
         （bond 整组消失）                        ← 丢 choice_pregen
```
- **后果**: 玩家在设置页点一次保存 → `reasoning_effort="high"` 消失。而该键缺失的语义
  是"不注入 reasoning_effort"（`settings.toml:8-9` 自述）——**用户裁决项被无声改掉**,
  而 CLAUDE.md §9 把档位列为"用户裁决项"。
- **两条补充损失（2026-09-13 复核补，比键丢失更难恢复）**:
  ① **注释也一起没了**——`_to_toml`（`store.py:121`）是手写序列化、**整个文件重写**,
     所以 `settings.toml` 里那些说明性注释（含 `# [llm.tasks.emotion]` 那段覆盖语法
     模板）在第一次保存后**全部丢失**;
  ② **被裁掉的正是手工维护内容**——`use_proxy` 消费侧是
     `str(...).lower() == "true"`（`llm/client.py:127`）, 所以写成字符串 `"false"`
     没有真值 bug; 但这恰好说明该文件是**手工维护**的, 而保存动作裁掉的正是手工部分。
  两个键都是活配置: `reasoning_effort` → `llm/client.py:109-113` 注入
  `default_extra_body`; `choice_pregen` → `webgui/bond.py:2140-2152/2175`。
- **修法**: 写回前 `load_settings()` 取现文件做基底，再用提交值覆盖（保留未知分组/键
  **与注释**——若要保注释则不能整文件重写, 需行级替换）; 或把
  `reasoning_effort`/`use_proxy`/`[bond]` 补进 `DEFAULTS` 并让 GUI 暴露。
- **测试缺口**: `tests/` 全库无 `is_masked` / `masked` 断言 → "打码值不得覆盖真 key"
  （`store.py:108` + `routers/settings.py:53`）这条唯一防线零覆盖。
  且 `tests/webgui/test_settings_store.py` 的 docstring **自己就点名了这个失效模式**
  （"漏进 DEFAULTS 白名单 → save 时被裁掉就会静默失效"）, 但只给 `enabled` 加了护栏。

### A2 ✅ 回忆册"留白格"不可点 → 整本册子可能全不可点
`webgui/static/js/collection.js:87-107 slotFor()`: `has_cover=false` 分支
（`:91-97`）**提前 `return box`，没挂 `click`**; 只有有封面那条（`:105`）挂
`addEventListener("click", () => openChar(c))`。
而后端角色页**完全不看封面**（`webgui/routers/collection.py:90-102`）。

- **后果**: 没有 `portrait/collection.png` 的角色 → 其**已结束章节永远进不去**。
  且 `.gitignore:19-25` 忽略 `assets/illustration/*/*/*`（只放行 `emotions.yml`）
  → **fresh clone 后每一格都是留白格 = 整本回忆册不可点**。
  本机 `assets/illustration/shiraishi_kokoro/default/` 已缺 collection.png。
- **比 fresh clone 更常见的触发路径（2026-09-13 复核补）**: **作者加新角色**
  （人设 + spine + registry 齐了、封面还没做）——她有已结束的章, 但格子在 UI 上
  点不动, 角色页根本进不去。这不是"别人 clone 才会遇到"。
- **修法**: 留白格同样挂 `click`（后端本就不需要封面）; 顺带把 A/B 层断言从
  "留白格存在"（`tests/webgui/test_web_http.py:731-732`）改为"可点且能进角色页"。
- **报告自身的 bug（同一处, 已认领）**: B 层冒烟那行选择器
  `bookCells = .col-grid [data-char]` **把留白格也算进去了**（`data-char` 在早退
  之前就设了, `collection.js:90`）→ 打印的"N 格可点"其实只是"N 格"。
  fresh clone 上它会因为点留白格→等不到角色页而报红（这点是好的）,
  但本机"部分有封面"时那行标签会撒谎。
- 同区次要: `chapters.py:109` 标题恒空串 → 前端一律兜"第 N 章"
  （`collection.js:168`）——文档 §8.1 承诺的 `chapter_title` → `display_name`
  回落链**两条都没实现**。


### A3 ⚠️ 好感 delta 丢失窗口（wiki 已提交、事件未写）
`core/brain/wiki_v2/digest.py:207-209` 先提交 wiki + 推进水位 `digested_seq`;
调用方**之后**才写 `affection|digest` 事件（`core/momotalk.py:436-438`）。
两步之间崩溃/异常 → 下轮 `digest.py:132-133` 判"无新增"直接 ok → **delta 永久丢失**,
且真源无痕（events.jsonl 是唯一真源, 补写 = 补写历史）。
**修法**: delta 先落 wiki.meta 待结算位, 或把事件写入放进 digest 提交前同一临界区。

### A4 ⚠️ `save` / `save_meta` 非原子 → 重跑产生重复节点
`digest.py:207-209` 两次独立写（节点整写 + 水位）; meta 写失败 → 水位回退 → 整段重跑。
重跑时 `revise.py:458-468 _find_duplicate` **只认 `main_text` 全等**, 而调用温度 0.3
→ 文本不同即不判重 → 重复 episode。
**现网佐证**: haruka 31 事件已有 8 节点（水位已在流尾, 当前未爆）。
**修法**: 水位与节点同一次原子写; 或去重键降到 `(kind, segment_id)`。

### A5 ⚠️ 废弃段不回撤 → 半截剧情会进 wiki
`vn_abandon` 只过滤 digest 的**输入窗口**（`digest.py:128`;
`core/session/maintenance.py:102-114`）; 已消化的节点不回滚。且中断的 VN
（`vn_exit completed=False`）之后 `in_vn=False`, 而 MMT 25 轮 digest 守卫只查
`in_vn/in_memorial`（`momotalk.py:499-503`）→ **把中断的半截剧情写进 wiki**,
与"中断剧情不消化"的定稿语义矛盾。
**修法**: 尾部段未闭合时跳过 digest; abandon 时按 `event_seq ⊂ 区间` 删节点。

### A6 ⚠️ 门控可被看门狗绕过 → append-only 视觉键不变量破损（不可回补）
`webgui/bond.py:304-315 _force_scene_ready()`（被 `:347-353` 的 25s 看门狗调用）
直接回填 `nomal` 并置 `_place_done=True`; 此后玩家推进时 `_log_scene:2394-2415`
把**半成品板**写进事件流, 晚到的 lane 结果因对象身份检查（`:2315-2318`）被丢弃。
→ CLAUDE.md §4「门控保证落库前视觉键就绪」在 25s 后不成立, 且**重试无法补救**。

**前置条件本身没被建立（2026-09-13 复核修正——比"卡死才兜底"严重得多）**:
`_lanes_idle`（`:292-301`）**只看队列深度**。worker 一旦把场景从队列取走、
正在 await 标注 LLM, `qsize()==0` → `_lanes_idle` 返回 True。
即**一次健康的、只是慢（>25s）的标注调用期间, 看门狗就会开火**——不需要 worker 卡死。
所以原 docstring（和本报告初稿）说的"lane 空闲 = 没人正在做这件事"**不成立**。

**两条比"表情精度损失"更硬的后果**:
① 落库的是 `nomal` 填充版; 晚到的真标注只在 `state.scene_obj is scene` 时写回
   **内存展示视图**（`:2371-2381`）, 事件流永不更新（`_log_scene` 见
   `scene_logged=True` 直接早退）→ **不可回补**;
② `_place_done=True` 同时进了真源 → 那一板可能在**没有 place 锚点**的情况下
   永久落库, 回放时挂在上一张背景上。

**定性**: "宁缺勿错: 表情精度换能推进"是自觉的取舍——问题不在兜底存在, 而在
① 它能在**调用在途**时开火, ② 它的产物**进了 append-only 真源**, 而不是只降级
这一次显示。修法应据此写: 兜底只放行**推进**; 落库时若键缺失则记 `notes` 并落
"未标注"标记（供回放区分），别把假键当真源写进 append-only。


---

## 2. B 级 — 已复核/高置信的功能性缺陷

| # | 项 | 锚点 | 说明 |
|---|---|---|---|
| B1 | **v2 下仍注入已退役的 `memorial_exit` 任务卡** | `llm/prompts/task_bond_memorial_exit.md:1` + `core/bond/bond_story.py:1140-1143` | `_scene_task_kind()` 在 `_in_memorial=True` 时返回 `"memorial_exit"`, 而 v2 只吃记录流、动作 JSON 一律打回（`bond_story.py:743-745`）。`_system_note` 里同类注记**已为此删除**（`webgui/bond.py:2453-2455` 注释"会打回重发 → 反馈回环"）——卡这条路径漏改。**修法**: v2 下恒返回 `"scene"`。 |
| B2 | ~~**批式/流式切板语义不等价**（真分歧 bug）~~ → **【误报, 2026-09-13 复核撤销】** | `core/bond/bond_story.py:122` vs `contract/records.py:751-753` | 原判: 批式 `elif ... and i > start` → 板首 switch 不切板 → `place_hint=None`。**复核结论: 不成立**。槽后收板（`if i in group_ends`）已把 `start` 推到 switch 之后, 所以 `i > start` 在该场景**恒真**; 两个守卫语义等价（流式的 `if self._cur` 与批式的 `i > start` 都表达"当前板非空才切"）。用 7 种边界逐板比对（群后紧跟 switch / switch 在群前 / 超长群 / switch 落在群中间 / 群结尾即块尾 / 相邻双 switch / art+memorial）, **板切分与 `place_hint` 全部一致**。已补回归用例 `tests/core/test_records.py::test_board_split_batch_stream_equivalence` 钉住这条不变量（此前只有 `check_block` 的软断言）。 |
| B3 | **place 双通道并存** | `bond_story.py:1097-1120` | 板首是 switch → `resolve_place`; 其余板 → 回落 v1 的 `annotate_places`, 而 place lane **每块都调**（`webgui/bond.py:2259,2308`）。文档称句级标注器"已退役"——实际两套并存。 |
| B4 | **章内"至多 1 次 memorial"无强制** | `bond_story.py:454,661,693,908` | `_memorial_used` **只写不读**, 全仓无拒绝路径; 唯一约束是 `check_block:342-348` 的同块 ≤1。CLAUDE.md/规则书/成本模型（DESIGN_VN_UPGRADE §10.2"硬上界"）**三层都只是文档**。 |
| B5 | **纪念窗口 marker 章末不闭合** | `webgui/bond.py:1554-1623` | `bond_finish` 只写 `vn_exit`+`session_end`, **不写 `memorial_exit`**（补写只在"下一板落地" `:2432-2439`）。而 `_memorial_open_in_events:256-271` 只认 exit/session_end → 下一章同 `(char,session)` 首板被 `_memorial_no_visuals:1141-1145` 判为"纪念窗口内" → **整块跳过 emo/place 标注**（表情恒 nomal、背景不切、门控恒放行）。 |
| B6 | **`_log_scene` 写失败仍置 `scene_logged=True`** | `webgui/bond.py:2409-2415` | 该板永久丢失（回放/回忆册缺板, 草稿旁路也不再含它）。**修法**: 异常不置位 + 待重试。 |
| B7 | **测试命令第二次跑必全红（文档级坑）** | `CLAUDE.md §12` | 三条环境原因: ① `python`=base 无 yaml → 24 collection ERROR; ② `--basetemp=.testtmp/pw` 不可重入（pytest 9.1.1 `_pytest/tmpdir.py:157-158` 先 `rm_rf`, 该目录 `os.rmdir` 报 WinError 5）; ③ 根因: 本 sandbox 下 `os.mkdir(p, 0o700)` 造的目录**进程自身不可写**, 而 pytest 所有 tmpdir 都硬编码 `mode=0o700`（`tmpdir.py:139/158/168/172`）。**可用命令**: 预建 `.testtmp/tmprootN` + 设 `TMP`/`TEMP` 指向它 + `--basetemp` 每次新目录名 + `-p no:cacheprovider`。 |
| B8 | **`_trim_history` 从头截断破坏前缀缓存** | `core/momotalk.py:861,951-954`; `core/bond/bond_story.py:936,1256-1259` | 每轮丢最旧记录 → 窗口饱和后 `system+history` 公共前缀退化为仅 system, `cache_hit` 断崖。**未用真机 `cache_hit=` 序列验证**——动手前先核对 diag 日志。 |
| B9 | **`inspect` 结果被丢弃**（LLM 拿不到资料） | `core/momotalk.py:682-698` | executor 真读了目标资料（`core/mmt/mmt_executor.py:188-228`）, 但**只在失败时回灌**; 成功即 `return _finish_turn_list`, `exec_results` 的 message 被丢（`:832 _exec` 未用）。schema 仍在承诺"查完回灌给你后继续说话"（`:797-798`; `contract/schema.py:100`）。 |
| B10 | **`mmt_send_media` 端到端 no-op** | `mmt_executor.py:234-251` | 只返回"[图片占位]", 前端 JS 全量 grep 无 send_media 渲染分支 → 不出图、无气泡、只落一条空 reply 事件; 而 schema 承诺"先查资源库…就发"。 |
| B11 | **前端 finish 静默失败 → 章永不进回忆册** | `webgui/static/js/bond.js:1252-1261` | 不查 `res.ok`/body; 后端 busy 时返回 `completed:false`（`bond.py:1559-1560`）→ 无 `vn_exit`/wrapup/digest → `chapters.py:116-117` 不收（要求 completed）→ **回忆册看不到这一章**。 |
| B12 | **`is_end` 板落地但玩家不点 finish → completed 悬空** | `webgui/bond.py:1903` | `_scene_landed` 消费 `is_end` 板即 `completed=True`, 但事件流无 `vn_exit`; 重进时 `bond_start:842` 以"已完成"为由挡住玩家。**修法**: `is_end` 落地即后台 finish。 |
| B13 | ~~**选项组真源在落库前被抹掉**~~ → **【根因误报, 2026-09-13 复核撤销; 已补契约断言】** | `webgui/bond.py` 裁决分支 | 原判: `bond.py:1438` 在 `_log_scene` **之前**写 `scene["choices"]=[]` → 事件 payload `choices=[]` → 回放画不出选项组（"用户 09-12 的反馈其实没修好"）。**复核结论: 不成立**。落库取的是 `state.scene_obj.to_dict()` 快照, 清空动作只作用于**展示视图** `state.scene`——两者是**不同的 dict**。实测 pick 事件 payload = `choices=['选A','选B']` + `picked='选A'`, 一直是对的。另外 `_log_scene` 本就在清空语句**之前**执行。（变异验证: 即便把 `_log_scene` 挪到清空之后, payload 仍正确——因为清的不是同一个对象。）**真源没问题; 缺的是断言** → 已补 `test_bond.py::test_bond_full_flow` 对 payload choices/picked 的断言。顺带删掉裁决分支里对 `scene_obj.choices` 的那次冗余原地清空（少一个可变状态; 重复裁决由展示视图 `picked` 守卫拦截）。 |
| B14 | **每板一次无谓 place 调用 + 门控等待** | `bond_story.py:1108-1111`; `webgui/bond.py:2272-2289` | 换场必在板首 → 无 switch 的板不可能换场, 但仍走 `annotate_places` 并占 lane、卡推进门（约 1 次 LLM + ~1s/板）。**修法**: payload 标"本板有无 switch", 无则直接 `_place_done=True`。边界: sensei 槽正好压在 switch 记录上时（`_board_spans:119-124`）仍需兜底。 |
| B15 | **轮询 O(N) 全量重读** | `webgui/chat.py:322,326`; `webgui/routers/bond.py:224-230`; `webgui/bond.py` 多次全量读 | MMT 每秒全量读+解析 events.jsonl 并全量扫 `_bond_done_map` + 每次重解角色卡取 display_name（`routers/mmt.py:169-175,182`）; `store.append_event`（`core/session/store.py:226-245`）每次 append 都全量读+解析; `/api/bond/status` 无版本参数、同端点被三路并发轮询（`bond.js:1137,367,525`）。当前规模可接受, **随历史线性恶化**。 |
| B16 | **`_resolve_scene` 无缓存 + 就地改业务状态** | `webgui/routers/bond.py:112-162` | 每次 status 对每段重算 `fx`/`background_url`/名字表; 且**就地改 `state.scene` 内层段落 dict**（`:141-145`）→ 展示层写回业务状态。 |
| B17 | **`reset_engines` 清锁不清 BondState** | `webgui/chat.py:74-82` | 在跑的 turn 持旧 Lock、新调用者拿新锁 → 同角色并发 `agent_turn`; `_bonds` 不清则 `BondState.vn` 继续用旧 key。 |
| B18 | **`_wrapup_inner` 用全局 store** | `webgui/bond.py:2526` | 与自身 docstring（`:2522-2526`）矛盾, 也与决策 #31"流程绑定 store"的修法矛盾 → 迟到写入可能落错世界线（同类事故见 `:151-153`）。 |
| B19 | **`_draft_save` 在流式交付时读到"上一回合的待发板"**（**仍未修**——原修法经复核**无效**, 已订正根因） | `webgui/bond.py::_draft_save`/`_draft_boards`; `core/bond/bond_story.py:597-607` | 现象成立: 流式下首板在 `send_vn_scene` 的 LLM 调用中闭合即回调交付, 而 webgui 的 `_draft_save` 会在回调里读引擎 `_pending_boards` 写"未生成未播放"旁路 → 混入**上一回合的尾板**; 进程若在此刻死掉, 重进会把旧板当"已生成未播放"续播。<br>**但审计给的原修法（在 `send_vn_scene` 里清空队列）经实测无效**: 该清空语句位于 0-LLM 快路径 `if self._pending_boards: … return`（`:599-607`）**之后**, 故**队列非空时根本不可达**——而流式交付窗口恰恰是"队列非空"（本回合的板还没解析出来, 队列里挂的是上一回合的尾板）。行级 trace 实证: `line 599 executed / line 639 executed = 0`。<br>**正确修法（待做）**: webgui 侧标记"正在生成中", 让 `_draft_boards` 在生成期间**不取**引擎待发队列; 或引擎把"本回合待发板"与"上一回合残留"拆成两个字段。已在 `bond_story.py` 该处留注释说明（防下次重踩）。 |
| B20 | **前端错误吞噬** | `webgui/static/js/bond.js:434,546,1139` | `waitScene` 遇畸形 status 静默 return → 等待卡永驻; `emoWatch` 空 catch; `waitTurnIdle` 把网络错当空闲; 6 个 JS 无请求超时 → turn 悬挂时点击全静默。 |
| **B21** | **v1 遗留的"表情单调"注记每轮白喂**（原表遗漏, 2026-09-13 复核补录） | `webgui/bond.py::_system_note` + `BondState.prev_emotions` | "上一场所有单元都是同一 emotion → 请随情绪变化切换 emotion 并切新单元"——写给 **v1**（emotion 由主 LLM 内联）的; v2 的 emotion 由标注层按记录给（决策 #27）, **写作者既看不见也没有该字段可写**（schema 只有 `character`/`stage` + `text`; `bond_story_rules.md` 全文不提 emotion）。每轮白喂 token, 且会诱导模型为了"切换单元"碎化输出。`prev_emotions` 字段是它唯一的消费者 → 一并删除（否则后人会以为主 LLM 还参与表情决策）。**已修**。 |
| **B22** | **`_lane_inflight` 增减未持锁**（低危, 2026-09-13 用户复核指出） | `webgui/bond.py` 两处 worker 的 `+= 1` / `finally: -= 1` | 读它的看门狗在另一个线程。丢更新方向安全（只会偏小但仍 >0）; 危险的是"一个 worker 减到 0、另一个还没加 1"的**瞬时零穿越** → 配合 25s 计时器理论上仍可开火。窗口纳秒级。**未修**（低危, 留档）: 要彻底消掉需给计数加锁, 或改判"无进展 N 秒"。 |

---

## 3. C 级 — 文档漂移（照文档干活会被坑）

> 优先级最高的是"路径/文件名/id 本身错"这类, 其次是行号失效。

| # | 文档 | 实况 |
|---|---|---|
| C1 | `CLAUDE.md:178` 写 `characters/{char}/events.jsonl` | 实为 `characters/{char}/soul/events.jsonl`（`core/session/store.py:107-110`） |
| C2 | 三处写"盒B **10** 块（含 `lexicon_emotion`）"（`CLAUDE.md:241-245`、`DESIGN_PROMPTKIT.md:96`、`PROMPT_INJECTION_MAP.md:258`） | 代码 `core/promptkit/box.py:33-43` 只有 **9** 个 id、无 `lexicon_emotion`（该文件自己的 `:99-102` 又说降为 9 块——自相矛盾） |
| C3 | `CLAUDE.md:240` 块 id `environment` | 代码是 `environment_mmt`（`box.py:22`）; `render_block("environment")` **静默返回 None**（`blocks.py:222-224`） |
| C4 | `DESIGN_PROMPTKIT.md:62` / `CLAUDE.md:246` 称 `round_messages(box, history, notes, task, user)` 是含 task 槽的唯一入口 | 实际 keyword-only `system/user/history/notes/brain`（`core/promptkit/tail.py:17-24`）; 卡由**调用方**作 notes 末位追加（`momotalk.py:605-614`、`bond_story.py:614-622`） |
| C5 | `DESIGN_PROMPTKIT.md:105-108` kind 表 | 整表过期: `task_bond.md` 正文已是记录流（无 story_scene/branches/story_end）。按表改模板会写错文件 |
| C6 | `CLAUDE.md:151,243` "主 LLM 不写地点…place 判定已移交标注层" | **过期**: v2 writer 发 `stage:switch` → `place_hint`（`bond_story.py:240`）→ `resolve_place`（`:1099-1107`）; `place_palette` 明教发 switch（`blocks.py:165-173`） |
| C7 | `CLAUDE.md:45/§4` "重复 memorial 会被拒绝" | 无强制（见 B4） |
| C8 | `CLAUDE.md:104` "失败重试(feedback ≤3) → closing" | **过期**: 伪收场已废, 超限只置中止态 `completed=False`（`webgui/bond.py:2022-2039`, `MAX_GEN_FAILURES=3`） |
| C9 | `CLAUDE.md:104/105` "选项配额(≤3)" / "键一致的 branches" | v2 无配额代码; `from_board` 从不为 v2 板设 `branches`（`bond_story.py:235-244`） |
| C10 | `CLAUDE.md:46` A1 回录 = "写回『（选择了: X）』" | v2 实际物化为一条 `老师：X` 记录（`contract/records.py:603-635`） |
| C11 | `CLAUDE.md:160` 符号 `Q_emo/W_emo`、`Q_place/W_place` | **全仓只存在于归档文档**（`docs/archive/DESIGN_BOND_CONTRACT_V2.md:165-244`）; 代码是 `_anno_queue/_place_queue + _anno_thread/_place_thread`（`bond.py:203-209`） |
| C12 | `CLAUDE.md:319` "emo/place 补切经版本号" | 只有 emo 有版本号（`bond.js:62,426-429`）; place 无版本, 靠段级 `place/place_bg` 晚到即切（`bond.js:499-510`） |
| C13 | `CLAUDE.md:190-191` maintenance CLI 有 `audit` 模式 | 代码只有 `--mode {heal,supersede}`（`core/session/maintenance.py:266`） |
| C14 | `PROMPT_INJECTION_MAP.md` 行号整表失效 | 称 "bond.py 现 1256 行"（实 2590）; `_scene_task_kind` `bond_story.py:564-569`（实 1140-1143）; `send_vn_scene` 352-525（实 550-768）; `start_session` 290-335（实 492-544）; `_system_note` 1138-1179（实 `webgui/bond.py:2449-2488`） |
| C15 | `PROMPT_INJECTION_MAP.md:176-187` 的 P17 清单 | 列的"纪念 exit 注记 + 选项配额注记"**代码里都不存在**（`_system_note:2449-2488` 现役 4 条: 表情单一 + round 30/50/>50） |
| C16 | `CLAUDE.md:117,271,288` / `DESIGN_PROMPTKIT.md:165-172` 把 `reasoning_effort` / `[promptkit].task_card` 写成可用开关 | GUI **无字段**（`settings.js:8-18`）, 且保存即抹掉（见 A1） |
| C17 | `CLAUDE.md:247` task 卡 ≤100 token | 实测 `task_bond.md` = **311 字符**（`task_mmt.md` = 116）——A/B 基线要按 2~3 倍算 |
| C18 | `DESIGN_BRAIN.md` 多处 | §11:352"唯一触发点=bond 闭环" ×`momotalk.py:484-504`（MMT 25 轮）; §1.1:38 `wiki.json` ×`wiki.jsonl`; §8:310 注入 caps 10/5/5 ×实 5/5/5/6/3; §12:364-370 代码锚点整表指向 v1 且行号失效 |
| C19 | `place_annotate.md:2,12` "每行一句/已按句拆分" | v2 传入记录派生段, 索引是**记录号**（`bond_story.py:1108-1117`） |
| C20 | 断链引用 | `momotalk.py:161,273` → `docs/DESIGN_MEMORY.md`（不存在）; `settings.toml:36` → `DESIGN_CHOICE_PREGEN`（无此文档, 已归档） |
| C21 | `experiments/README.md:11-19` 脚本表 | 列了 `e2e_agent.py`/`create_kayoko.py`/`run_4chars.py` **三个不存在的文件**, 缺 17 个实际存在的（含 `web_e2e/`） |
| C22 | `tools/.md:10,28` | 缺 6 个现存工具（`sync_portrait.py` 等）; `:28` 仍写旧路径 `resources/illustration/`（现为 `assets/illustration/`） |
| C23 | `.gitignore:30 tools/` 与 `git ls-files tools`=7 矛盾 | `sync_portrait.py`/`fetch_kivo.py`/`reasoning.py`/`tools/.md` **只在本地未跟踪** → 新人 clone 后按 §10 跑 `python tools/sync_portrait.py` 会 FileNotFound |

---

## 4. D 级 — 死代码 / 遗留（清理前先确认, 有的不能删）

**可安全清（零引用）**
`bond_story.py:76-82 legacy_action_enabled`/`LEGACY_ACTION_ENV`（设计文档称该开关已删——僵尸）·
`records.materialize_pick:564` / `pick_insert_index:653`（docstring 声称 `from_dict` 在用——假）·
`BlockStreamParser.all_boards:761` · `VnBlock.is_valid:529` · `bond_story.has_records:205`/
`record_texts:208` / `MAX_HISTORY_ROUNDS:149` · `bond_actions.EMOTIVE_STEP:53` ·
整文件 `core/bond/stream_probe.py`。

**`scene.memorial_exit` / `scene.segments` / `scene.branches` 三个"恒假/恒空"字段的活分支**
（v2 恒 False/None/{}）: `bond_story.py:938,945,972,1095,978,987-989` +
`webgui/bond.py:1163,1187,1207,2252,2255,2281,2403,2429,1348-1419` —— 全是不可达分支,
但**回放 v1 旧档时 `branches` 可达**, 别一刀切。

**只被测试引用（主链不可达）**
`bond_actions.py`(335 行) · `bond_executor.py`(85) · `memorial_actions.py`(66) ·
`sentence_splitter.py`(317, 唯一活引用是 `MAX_SCENE_RETRIES`) · `emotion_annotate.py`
（除 `_extract_array:228` 外全体——`place_annotate.py:27` 借它） · `records.py` 约 200 行。

**别当死码清（v1 回放仍依赖）**
`choice_candidates` / `_spawn_candidates:2158` / `fork_for_pick:1178` —— v2 因
`if not scene.records:` 不触发（`bond.py:1919-1920`）, 但 v1 旧档回放仍走。

**被迫加载**
`core/brain/{hippocampus,consolidation,recall}.py` 主链 DEAD, 但
`core/brain/__init__.py:16-18` 仍 import 三者 → **任何 `core.brain.wiki_v2.*` 导入都先执行父包**,
每进程被迫加载 v1 digest 栈。

**其他 support 死码**
`core/affection` 的 `load_raiser_table`/`add_behavior`/`add_exp`（无 live 调用）;
`core/rag/place.py` 全体 + `brain.recall_with/recommend_with`（仅 `experiments/rag_test.py`）;
`core/random_events.memory_flash` 仅 CLI（`core/ui/vn_cli.py:243-249`）→ **web 产品 VN 永不触发"记忆浮现"**;
`core/ui` 的 `BondStoryOutput`/`LineBuffer`/`TypingDelay`/`simulate_typing`/`format_momotalk_reply`;
`core/media` 的 `build_place_injection`/`gallery.get`/`play_diff`/`play_spine`/`background_dirs`;
`image_gen.warmup()`（空体却被 `vn_cli.py:229` 起线程调用）;
`core/parsing` 的 `build_prompt("trigger")`、`include_hidden` 永假（`world_parser.py:70,82-83` → **hidden 档永不注入**）;
`core/common/tone.load_story_tone` 的 `character_id` 参数从不被读。

---

## 5. E 级 — 性能 / 体感（当前规模可接受, 但会线性恶化）

1. **digest 输入被砍到 120 字**（`core/session/renderer.py:261,308` 默认
   `max_paragraph_chars=120`, digest 未覆盖 `digest.py:138`）→ 一个 bond 板（3~12 条记录）
   拼成一行砍到 120 字, RoundA 的 verbatim"逐字原话"与 RoundB 的 evidence"逐字引用"
   **物理上不可能**。→ 传 800~1200 或按记录渲染。
2. **digest 双份输入 + 双 high**: 时间线与人设锚在 A/B 各送一次
   （`digest.py:152-156` vs `176-181`）, 两轮皆 `thinking=high` + 8192
   （`llm/task_levels.py:60`）→ 成本 ≈ 2× 最大块。B 轮只需 A 产物摘要 + id。
3. **evidence 白花钱**: schema 每轮要 ≤5 条（`contract/digest_registry.py:263-265`）,
   `_clean_evidence`（`digest.py:387-410`）**不校验 quote ∈ 时间线**, 且 `res.evidence`
   **无任何 live 消费者** → 建议从 B 轮 schema 删除。
4. **知识图谱只增不并**: `revise.apply_revision_package` 及 merge/contradict/accrue/create/
   link/unlink/resolve（`core/brain/wiki_v2/revise.py:152-382`）**仅被测试调用** →
   生产从不 merge/accrue。`PHASE_DEEP`（`digest_registry.py:30`）已声明但未注册动作,
   `build_schema("deep")` 直接抛错（`:281`）。
5. **认知窗口饱和**: `COGNITION_CAP=12` 按 significance 排序（`digest.py:69,171`;
   `render.py:285-317`）→ 超 12 条后低 sig 认知**永远不可见、无法被 touch/update**,
   而深层整理未接线 → 重复 add 滚雪球。
6. **注入体量与缓存**: memory 段拼进 **system 首串**（`core/promptkit/tail.py:36-38`）→
   digest 一落库整段前缀缓存失效（与 CLAUDE.md §9"稳定前缀"相冲）; 且
   `render.py:158-162` caps 5/6/5/5/3 条、narration ≤300 字但 **verbatim 无上限**。
   → 建议 brain 段移到 history 之后（notes 位）或压 verbatim 上限。
7. **空注入常驻**: 空库也总注入「【角色记忆（brain）】」标题（`render.py:194`）,
   调用方的 `or ""` 永不生效（`momotalk.py:143,443`）。
8. **CharacterLoader 无缓存**: 每次重读 6 个 yml（`core/parsing/dynamic_character_parser.py:479-508`）;
   `routers/mmt.py:128-138` 每次列表请求重读所有角色 events.jsonl。→ mtime 缓存即可。
9. **标注重试成本**: `emo_text._ANNO_TEXT_MAX_ATTEMPTS=3`（`:38`）每次重试重发**完整 system**
   （词表 + 人设 + 上一板原文）→ 长度不符时 3 倍 prompt 成本换 1 次机会。
   可参考退役的二分法只重问缺失行号。
10. **首板之后不再走流式交付**: 只有首板走 `_scene_landed`（`webgui/bond.py:1986`）→
    其后待发板要等 `_pregenerate` 逐板领出才标注（`pregenerate` 每板一次
    `send_vn_scene` + 至少一次标注调用）, 而同步批式一次调用标整块。
11. **计数器语义**: `_session_rounds` 在 `attach_session` 归零（`momotalk.py:367`）→
    resume 后 25 轮窗口重算; `want_to_speak` 冷却同键（`random_events/__init__.py:50-57`）
    → resume 后静默抑制约 30 轮。→ 改持久化计数。
12. **旧档 `wiki.jsonl` 并发写**: `WikiStoreV2.save` 整文件原子替换但**无跨进程锁**
    （`core/brain/wiki_v2/store.py:221-223`）, 而事件 append 有全局锁（`core/session/store.py:232`）
    → webgui + CLI 同时 digest 会互相覆盖丢节点。

---

## 6. F 级 — 测试 / 工作流

1. **42 个活跃 LLM 桩收敛为 1 个**: 4 份 `chat()` 派发近似重复
   （`tests/webgui/test_bond.py:80-98`/`test_web_http.py:64-81`/`test_vn_cli.py:49-71`/
   `test_vn_records_engine.py:40`）+ 3 份**逐字相同**的 `format_messages`。
   CLAUDE.md §11 自己写着"新增标注任务 → 同步给 4 个文件"——这句维护成本就是重复的税。
2. **桩加"未识别调用即失败"**: 8 个含桩文件**没有任何标注分支**,
   未知调用直接 `self._scripts.pop(0)` **静默吞脚本**, 只在脚本耗尽时才报
   （`test_bond.py:97`）→ `tests/core/test_session.py:476,543` 的 digest 桩匹配的
   **已退役关键字 `记忆巩固`** 就是这类债（活路径是 `记录员/整理者`）。
3. **`_setup/_cleanup` 提成 `chat_env` fixture**: 4 份 `_setup` + 3 份 `_cleanup`,
   store 还原有 3 种写法 → 兼具消除 2026-09-11"测试写脏真 data"事故的同型隐患。
4. **补测缺口（按价值）**:
   ① `webgui/store.py:108 is_masked` + `routers/settings.py:53` **零测试**（A1 的防线）;
   ② `webgui/static/js/**` 全部零自动化（A2、`bond.js:265-322 enterReadonly`、
   `:713` 选项锁定态、`:964/1163/1249` readonly 短路）;
   ③ `llm/client.py:189-195,257-264` 的 `cache_hit/out/in` 埋点零测试
   （§9 已落地机制**只有日志无断言**）;
   ④ 多世界管理零测试（`core/session/store.py:123,132,143,170`;
   `webgui/chat.py:118 new_world` **无调用者**）;
   ⑤ 回忆册三条降级分支零测试（`collection.py:66-69,43-46,111-114`）。
5. **慢例**: `test_mmt_digest.py::test_mmt_window_trigger_digests` 5.11s（真
   `time.sleep` 等 25 轮窗口）、`test_vn_cli.py::test_wrapup_after_vn` 3.53s;
   47 处 `time.sleep(0.05)` 忙等轮询可换 `threading.Event`（31s → ~20s）。
6. `tests/renderer/` 14 例**不在任何文档的运行命令里**（§12 只写 core/webgui/llm）。
7. `pytest.ini:11-12` 的 `api` marker 是死配置（tests/ 全库 0 处 `@pytest.mark.api`;
   真 API 全在 `experiments/`）。

---

## 7. 建议修复顺序（未拍板）

> 用户 2026-09-13 明确: **背景/地点链路暂不做**（tempo 素材库尚未整理完）——
> 故 §1/A 级里的背景相关项（`_resolve_place` 31 词表、20/20 板 background=neutral
> 等）**本文不列**, 待素材整理完成后单独立项。

```
批次 1（配置与数据不可逆 —— 立刻）
  A1 设置页保存抹配置      + 补 is_masked 测试
  A3 好感 delta 丢失窗口
  A4 save/save_meta 非原子
  A5 废弃段不回撤
  A6 看门狗绕门控（append-only 不可回补）
批次 2（一句话级 bug, 高性价比）
  B1 memorial_exit 卡（每轮白喂 + 可能打回）
  B6 _log_scene 写失败仍置位
  B11/B12 finish 静默失败 / completed 悬空
  B13 选项组真源在落库前被抹
  B5 纪念窗口 marker 章末不闭合
批次 3（前端体验）
  A2 留白格不可点 + 标题回落链
  B20 前端错误吞噬
批次 4（结构 / 成本）
  B2 切板语义统一（批式 vs 流式）
  B3 place 双通道并存
  B14 无 switch 板免 place 调用
  B15/B16 轮询与 _resolve_scene 缓存
  E1–E5 digest 输入/成本/图谱合并
批次 5（文档与工程债）
  C1–C23 文档校准（先修"路径/文件名/id 错", 再修行号）
  D/F 死码清理与桩收敛（先确认 v1 回放依赖）
```

---

## 8. 已落地: 拆分点 A（embedding 降级可观测, 2026-09-13）

> 动机: 记忆（wiki 图）质量的第一道闸是**引擎侧的语义候选碰撞**, 而它在
> **本机 embedding 模型未加载时全程静默降级为词面关键词匹配**——排查时无从下手。
> 先把"在跑语义召回"还是"在跑词面兜底"变成可观测事实, 再谈图谱质量。

### 改动

| 文件 | 改了什么 |
|---|---|
| `core/momotalk.py:88-141` | `_get_embed_fn()` 重写: **先健康判定**（`LocalEmbedder.health()` = 真的发现了 embedding 模型）, 未就绪 → **返回 None**（不再交出注定抛 `RagError` 的 embed_fn）; 状态**跳变时**打一条可 grep 的 `digest_embed fn=…` 日志（不逐次刷屏）; 未就绪**不永久缓存**（服务可能后起, 每次 digest 重探） |
| `core/brain/wiki_v2/recall.py:141-143` | `recommend_candidates` 的 `except Exception: pass` → 打 `recall_cand fallback=keyword reason=embed_error err=… nodes=N`（**这条是 wiki"只增不并"的直接告示**） |
| `core/brain/wiki_v2/recall.py:195-197` | `_similarity_hits` 的静默降级 → 打 `recall_sim fallback=tags reason=…` |

### 修复前 vs 修复后（实机, 本机 `localhost:1234` 返回 502）

```
修复前: embed_fn 照发 → 每轮 digest 每次 embed 都抛 RagError → 被 except 吞掉
        → 0 行日志。运维视角: "一切正常", 实际全程词面兜底。

修复后:
  core.momotalk INFO digest_embed fn=none reason=model_missing
      fallback=keyword_candidates（语义召回不可用: 本机未加载 embedding 模型
      → Round B 失去【疑似同主题】标注能力, 新经历只会 add）
```
且：① 连续调用**只上报一次**（跳变语义成立）; ② 服务后起 → 自动上报
`digest_embed fn=ok model=bge-m3 fallback=-` 并交出可用的 embed_fn;
③ 已构造后不再重探; ④ `embed_fn=None` 的纯关键词路径**保持静默**（不制造噪声）。

### 回归

`tests/core tests/webgui tests/llm tests/renderer` → **580 passed in 40s**
（本次含 `tests/renderer` 14 例; 原命令口径 566）。
`_get_embed_fn` 无直接单测——它生产上只在 `_inject_brain(digest=True)`
（`momotalk.py:468`）被调用, 测试桩路径不触发。实机探针（`.testtmp/`, 不提交）:
`_probe_embedfn.py`（探针 1–4: 未就绪 / 不刷屏 / 后起自愈 / 复用不重报）·
`_probe_recall_log.py`（探针 A–C: 抛错带 reason / None 路径静默 / 通道1 降级）·
`_probe_settings.py`（A1 的设置页裁配置复现）。

### 仍未做（拆分点 B/C, 待拍板）

- **B**: 候选碰撞窗口与 `COGNITION_CAP=12` 解耦（渲染 12 条 ≠ 碰撞全集,
  否则 belief 数过 12 后图结构性停止生长）。
- **C**: 给 merge/accrue 一个入口（`PHASE_DEEP` 是现成挂点, 现在
  `build_schema("deep")` 直接抛错 = 明确留白）——这是"episode → belief →
  多条 belief 升华"缺的那一环。

