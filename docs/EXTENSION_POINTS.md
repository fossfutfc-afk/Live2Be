# EXTENSION_POINTS — 「留着、但还没接线」的接口清单

> **状态**：机制稿 + 索引（2026-09-21 建立）。
> **来源**：`docs/ARCH_REVIEW_2026-09-20.md` P0-2——"退役只删调用点、不删能力"让地里埋着
> 看起来能用的死路。清理时按用户裁决分成两堆：**有具名未来节点的接口保留并打标**，
> 其余（投机性通用 / 兼容别名 / 纯退役残留）删除。
>
> **最大的成本不是占地方**，而是下一个人分不清「没接线」和「忘了删」——所以给前者一个
> 可 grep 的标记，让"这条接口是有主的"一眼可查。

---

## 1. 约定（就三条）

1. **定义处上一行**打标记：
   `# EXT: <slug> — <说明>; 勿删（docs/EXTENSION_POINTS.md）`
   —— 紧贴定义（不隔空行），不插到装饰器与 `def` 之间。
2. **`grep -rn "# EXT:"` 是权威清单**，本表只是给人看的视图（表会漂，以代码为准；
   §2 因此只写**文件 + 符号**，不写行号——行号必漂，`DESIGN_MEMORIAL.md` 已经吃过一次）。
3. **判据 = 有没有一个具名的未来节点指向它**（M2 / R6 / 阶段 8-10 / PL4 / V3 /
   affection-view / 周年 之类）。**没有具名节点的不是 EXT，是投机性通用 → 删**
   （2026-09-21 已按此清掉 C/D/E 三类）。
   ⚠️ EXT **不是免删金牌**：一旦判定"永不会接线"，就删掉标记连同代码。

**接线时**（出现第一个产品消费者）：删掉 `# EXT:` 行 → 从 §2 表里删掉这一条。
标记的生命周期 = "还没有消费者"。

**⚠️ 不许在 `llm/prompts/*.md` 里打标记**：那些文件的内容会被拼进 prompt 注入 LLM，
注释会变成提示词的一部分。只在那类 prompt 的**加载代码**处打标记，并在 §2 表里点名文件。

---

## 2. 现役扩展点

| slug | 位置（文件 · 符号） | 指向的节点 | 留的理由（证据原文） |
|---|---|---|---|
| `anniversary` | `core/worldtime/realtime.py` · `_minus_one_year` | "周年"窗口（未来需求） | docstring：*"当前没有调用点……留着是因为'周年'类需求迟早要用它，而闰年那一格是那种'不写就必然写错'的地方"* |
| `emotion-batch-v1` | `core/bond/emotion_annotate.py` · `annotate_emotions_smart` / `annotate_emotions` / `fill_missing_emotions`（+ prompt `llm/prompts/emotion_annotate.md`） | 协议单测 / 简单调用 | docstring：*"本函数保留给协议单测/简单调用"*。主链走 `emo_text.py`（按记录标注）；同模块的 `_extract_array` 是**活**的，被 `emo_text`/`place_annotate` 共用。⚠️ 2026-09-21 清 v1 时**没动它**（滑块名带 v1，但它是"留给测试"的声明式保留，不是 v1 契约的一部分）——要一起删说一声即可 |
| `digest-deep` | `contract/digest_registry.py` · `PHASE_DEEP` | digest 三相位之 `deep` | 相位常量 `record`/`understand`/`deep` 已声明，`deep` 无实现 |
| `brain-v1-legacy` | ~~`core/brain/{hippocampus,consolidation,recall}.py`~~ | — | **2026-09-21 已删除**（用户裁决"v1 整族删掉"）：三件套 + `llm/prompts/digest.md` + `contract/schema.build_digest_schema()` + `experiments/brain_real_run.py`。现役记忆 = `core/brain/wiki_v2/` |
| `world-switch-m2` | `core/session/store.py` · `create_world` / `active_world`；`webgui/chat.py` · `new_world` | **M2 世界切换器** | docstring：*"切换由 M2 世界切换器负责"* / *"显式开新世界线（平行世界语义）"* |
| `save-point-r6` | `core/session/store.py` · `snapshots_dir`；`core/brain/wiki_v2/store.py` · `snapshot_to` / `restore_from` / `audit` | **R6 存档点** / 阶段 8-10 | docstring：*"R6 存档点语义: 自包含"* / *"v2: 森林时点快照, 阶段 8/10"* / *"冒烟/R6 完整性检查用"* |
| `affection-view` | `core/affection/affection_calc.py` · `progress` / `exp_to_next` | 好感可视化（未立项） | docstring：*"当前等级内进度 0-1（**进度条用**）"*。数值层本身是活的（digest 结算走它） |
| `place-semantic-pl4` | `core/rag/place.py` · `PlaceRetriever`（含 `resolve_one` / `asset_scene`） | **PL4 语义检索** | 语料已备（`config/settings/world/place_entities.json`），但产品侧只接了 `core.rag.brain`（`core/momotalk.py`）；place 侧对应"层1 别名 0 调用" |
| `random-events-introspection` | `core/random_events/spec.py` · `all_events`；`core/random_events/__init__.py` · `set_enabled` | 事件作者侧内省 / 确定性测试 | `fire_event` 才是活入口（`MomoTalkEngine`、`vn_cli` 各一处）；注册表自省与全局开关暂无消费方 |
| `affection-behavior` | `core/affection/affection_calc.py` · `load_raiser_table` / `add_behavior` | **"未来行为加好感"**（行为名 → exp） | `core/session/events.py` 的 `TYPE_AFFECTION` 注释写明 *"未来行为加好感同板块, subtype=行为名"*；审计台账 `AUDIT_2026-09-13_FULL.md` 已记为"无 live 调用"。注意配置里**还没有** raiser 表——接线时要连表一起落 |

---

## 3. 待定与边界

- **2026-09-21 · v1 整族退役（用户裁决"删掉 v1 和相关测试"）**——产品侧删除：
  `core/bond/{bond_actions,bond_executor,memorial_actions,sentence_splitter,stream_probe}.py`、
  `BondScene.from_action`、`BondScene.memorial_prompt`/`memorial_exit` 字段与 webgui 里
  8 处 `memorial_exit` 恒假分支、`vn_cli` 的"纪念子模式 + exit schema 注入"、
  `contract/schema.build_digest_schema`、`contract/constants` 的 `DOMAIN_STORY`/`DOMAIN_MEMORIAL`、
  `contract/registry` 的 `StoryActionRegistry`/`MemorialActionRegistry`、
  旧版记忆三件套 + `llm/prompts/digest.md` + `experiments/brain_real_run.py`。
  **测试侧**：`tests/archive/` 整目录（9 文件）+ `test_story_executor.py` +
  `test_sentence_splitter.py` 删除; `pytest.ini` 的 `norecursedirs` 一并去掉。
  **效果**：`docs/ARCH_REVIEW_2026-09-20.md` 的 P0-2（恒假分支）就此消除。
  考古读 git 历史（`git log --diff-filter=D --name-only`）。
  这一节比 §2 的表重要：**§2 是"留着但没接线"的正面清单，本节是"曾经像死代码、
  已确认删除"的负面清单**——两者合起来才是"哪些接口有主"的完整答案。
- **不属于 EXT（判据见 §1 第 3 条）**：
  - **已删 2026-09-21（节点 2 清理）**：`memorial_img_ready`、`choices_used`、
    `legacy_action_enabled`（+ `LEGACY_ACTION_ENV`）、JS `splitReplyChunks`
    （+ `MMT_CHUNK_MAX`/`MMT_CHUNK_FRAGMENT`）、死 DOM id `logo-img`/`panel-name`、
    `contract/digest_registry.py` 的 `MAX_CONTENT`/`MAX_EXAMPLES`/`MAX_EVIDENCE`
    （自称"parse 级边界"但零校验器消费）。
  - **已删 2026-09-21（节点 3 清理 · C 类对称性访问器 + D 类兼容别名）**：
    `VnBlock` 的 `switch_at`/`art_at`/`end_at`/`exit_at`（位置访问器——只留**唯一有消费者的
    `memorial_at`**）、`group_texts`/`has_choices` 与**连带**的 `groups`（群视图；群判定改由
    模块函数 `sensei_groups` 与 `_board_spans` 直接做）、`before`/`after`（切片助手）、
    `render_text`（渲染包装——现役唯一渲染源是 `render_records`，测试断言已改打它）、
    `CHARACTER_SPECIALS`；`BondScene.has_records`/`record_texts`；`ActionSpec.requires_sources`；
    `ValidationResult.require_valid`；`catalog.has_sprite`/`has_background`/`background_variants`；
    `place_table.by_region`；`display.get_current_text`；`MAX_HISTORY_ROUNDS`（**两处**同名兼容别名）；
    `Store.sessions_dir`/`session_dir`（注释自称"v1 兼容路径"）。
  - **已删 2026-09-21（节点 4 清理 · 测试独占 API）**：`WikiStoreV2._world_has_history` /
    `by_kind` / `find_by_event_seq` / `reload`；`recall_config.py` **不算**（见下）；
    `bond_actions.EMOTIVE_STEP`；`maintenance.PROJECT_ROOT`；`SessionStore.update_session_progress`
    （自称"[废弃]…无人读"）；`GeneratedImage.as_dict`；`webgui/routers/bond._place_bg_url`
    （"只要 URL"的兼容包装——测试断言已改打现役 `_place_bg()`）；`LocalEmbedder.model_from_config`；
    `BondScene.para_emotions`（逐段 emotion 缺省延续——现役是标注层写 `paragraphs[].emotion`
    + 前端 `applyEmotions`）；`BondScene._draft`（只写不读）；`Session.from_json`；
    `MomoTalkEngine._characters_root`；测试侧 31 处未用导入。
  - **删错又恢复的一例（教训）**：`core/brain/wiki_v2/recall_config.py::reload` —— 按"零消费者"
    删掉后，全量测试立刻 13 errors: 它有 **11+ 处调用, 全在 `tests/core/test_wiki_recall_ledger.py`
    的 autouse fixture**（进程级懒加载缓存必须逐用例清）。⇒ **测试基础设施也是消费者**；
    且 `reload` 这种常见名**必须查调用点（`.reload(`）而不是只查定义处**——我第一遍就是
    只看了定义。已恢复并在 docstring 里写明。
  - **两处"看起来死、其实是假阳性"（已核实并保留，勿再删）**：
    1. `core/session/events.py::TYPE_AFFECTION` —— 作为**名字**零引用，但它的**值**
       `"affection"` 是 `EVENT_TYPES` 白名单成员，而白名单在 `Event.from_dict` 里做**入库校验**
       （`typ not in EVENT_TYPES → 丢弃`）。删掉它 = 好感事件被静默丢弃。**这是"枚举成员当校验白名单"的典型**。
    2. `core/media/place_table.py::stats` —— 起初按"只被测试引用"归入 C 类，复核发现
       `experiments/place_resolve_real.py` 真在用它打印表自查 ⇒ 有消费者即非死代码，保留。
  - **重新判定为保留**：`webgui/bond.py::_lane_writer_alive` —— 起初按"只被测试引用"归入
    退役残留，但它的 docstring 自己写着 *"保留本函数仅作观测/测试"*，且 `_gate_stalled`
    的 docstring 引用它来解释那条非显然的不变量（线程死活**不能**当门控判据——真实会话里
    恒为 True）。删掉会让那段结论失去唯一出处。**按 §1 第 3 条（有声明即留）保留；
    不打 `# EXT:`**（它指向"观测/测试"，不是未来节点）。
- **~~v1 动作通道~~**（`bond_actions`/`bond_executor`/`memorial_actions`/`sentence_splitter` +
  `BondScene.from_action` + `scene.memorial_exit` 的消费分支）：2026-09-21 **已随 v1 整族删除**
  （上一节）。原"保留为旧代通道"的裁决被用户后续裁决覆盖。
