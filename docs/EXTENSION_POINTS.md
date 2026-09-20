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
| `v1-memorial-probe` | `core/bond/stream_probe.py` · `MemorialProbe` | v1 复活 / 考古 | 模块 docstring：*"已退役（决策 #39）：主链不再调用，留档供考古/复活参考"* |
| `emotion-batch-v1` | `core/bond/emotion_annotate.py` · `annotate_emotions_smart` / `annotate_emotions` / `fill_missing_emotions`（+ prompt `llm/prompts/emotion_annotate.md`） | 协议单测 / 简单调用 | docstring：*"本函数保留给协议单测/简单调用"*。主链走 `emo_text.py`（按记录标注）；同模块的 `_extract_array` 是**活**的，被 `emo_text`/`place_annotate` 共用 |
| `digest-deep` | `contract/digest_registry.py` · `PHASE_DEEP` | digest 三相位之 `deep` | 相位常量 `record`/`understand`/`deep` 已声明，`deep` 无实现 |
| `brain-v1-legacy` | `core/brain/{hippocampus,consolidation,recall}.py` + `core/brain/__init__.py` 再导出 | 无（legacy 参考） | `core/brain/wiki_v2/AGENT_BRAIN.md`：*"legacy `core/brain/{consolidation,hippocampus,recall}` 保留但**无运行时消费方**"*。⚠️ **处置待定**：2026-09-21 曾判"不保留"，与上述文档声明冲突，见 §3 |
| `world-switch-m2` | `core/session/store.py` · `create_world` / `active_world`；`webgui/chat.py` · `new_world` | **M2 世界切换器** | docstring：*"切换由 M2 世界切换器负责"* / *"显式开新世界线（平行世界语义）"* |
| `save-point-r6` | `core/session/store.py` · `snapshots_dir`；`core/brain/wiki_v2/store.py` · `snapshot_to` / `restore_from` / `audit` | **R6 存档点** / 阶段 8-10 | docstring：*"R6 存档点语义: 自包含"* / *"v2: 森林时点快照, 阶段 8/10"* / *"冒烟/R6 完整性检查用"* |
| `affection-view` | `core/affection/affection_calc.py` · `progress` / `exp_to_next` | 好感可视化（未立项） | docstring：*"当前等级内进度 0-1（**进度条用**）"*。数值层本身是活的（digest 结算走它） |
| `place-semantic-pl4` | `core/rag/place.py` · `PlaceRetriever`（含 `resolve_one` / `asset_scene`） | **PL4 语义检索** | 语料已备（`config/settings/world/place_entities.json`），但产品侧只接了 `core.rag.brain`（`core/momotalk.py`）；place 侧对应"层1 别名 0 调用" |
| `random-events-introspection` | `core/random_events/spec.py` · `all_events`；`core/random_events/__init__.py` · `set_enabled` | 事件作者侧内省 / 确定性测试 | `fire_event` 才是活入口（`MomoTalkEngine`、`vn_cli` 各一处）；注册表自省与全局开关暂无消费方 |

---

## 3. 待定与边界

- **`brain-v1-legacy` 处置未定**：`AGENT_BRAIN.md` 声明"保留"，而 2026-09-21 的一次裁决
  （"五组里除了第 1 组都保留"，第 1 组 = 本组）指向"归档/删除"。**目前只打了标记，没有动代码**；
  定下来之后要么删本行、要么把三件套移到 `archive/brain_v1/`（连同 `experiments/brain_real_run.py`
  的 import 与根级 `DESIGN_BRAIN.md` 的引用一起改）。
- **不属于 EXT（本次已判定该删，从清单里排除）**：载体/契约的对称性访问器（`VnBlock` 的
  `switch_at`/`art_at`/`end_at`/`exit_at`/`group_texts`/`has_choices`/`render_text`、
  `BondScene.has_records`/`record_texts`、`requires_sources`/`require_valid`、
  `catalog.has_sprite`/`has_background`/`background_variants`、`place_table.by_region`/`stats`、
  `display.get_current_text`）；兼容别名（`MAX_HISTORY_ROUNDS`、`sessions_dir`/`session_dir`）；
  退役残留（`memorial_img_ready`、`choices_used`、`legacy_action_enabled`、`_lane_writer_alive`、
  JS `splitReplyChunks`、死 DOM `logo-img`/`panel-name`）。判据见 §1 第 3 条。
- **v1 动作通道**（`bond_actions`/`bond_executor`/`memorial_actions`/`sentence_splitter` +
  `BondScene.from_action` + `scene.memorial_exit` 的消费分支）：用户裁决**保留**。它们不是"未来节点"
  而是"旧代通道"，所以按 §1 第 3 条不打 `# EXT:`；如需复活的定位说明，读
  `core/bond/__init__.py` 的模块 docstring 与 `docs/ARCH_REVIEW_2026-09-20.md` P0-2。
