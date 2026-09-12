# tests/archive —— 已退役机制的用例留档

> **状态**：2026-09-10 归入（记录流 v2 迁移期）。**不参与 pytest 收集**
> （`pytest.ini` 的 `norecursedirs = tests/archive`），跑全量时不会被加载。

## 为什么在这里

VN 契约从"单动作 JSON（story_scene/story_end + memorial 双动作）"换成
**记录流 v2**（逐行 JSONL；见 `docs/DESIGN_VN_UPGRADE.md`）后，一批机制整体退役。
它们对应的测试**测的是已经不存在的产品行为**——迁到新契约没有意义（翻译过来只是
在验证"该机制不存在"），故整文件留档，供将来需要时考古/复活参考。

| 文件 | 原测行为 | 退役原因（替代物） |
|---|---|---|
| `test_bond_candidates.py` | choices 板 fork 候选引擎、sibling 预生成、选中支直接端上、候选池 GC | v2 里**同一块的后继板已经在引擎待发队列**（0 LLM）→ 无需 fork 候选（§6/§10.4） |
| `test_engine_fork.py` | `fork_for_pick` 候选世界线草稿（共享只读面 / 独立可变面） | 同上——`fork_for_pick` 原语随之退役（代码暂留, 主链不调用） |
| `test_memorial_mode.py` | `memorial_enter/memorial_exit` 独占轮 + 纪念子模式状态机 + 立绘注入 | v2 里纪念 = 块内 `stage:memorial` 记录（区间到本块结束），**降级 = 普通 VN**（拍板 17）；生图钩子待 P2 重接到 `art`/`memorial` 记录 |
| `test_memorial_stream.py` | 流式嗅探 `memorial_enter` 的 prompt 字段以提前开画 | **已迁移（2026-09-12 决策 #39）**: 触发改为"一行 `stage:memorial` 解析即开画"（prompt = 块级 `art` 意向 → 缺省触发句）; v2 覆盖在 `test_vn_records_engine.py::test_memorial_fires_image_hook_with_art_intent` 与 B 层冒烟"纪念链路" |
| `test_stream_probe.py` | `MemorialProbe` 状态机（`memorial_enter.prompt` 引号闭合即回调） | 同上——模块 `core/bond/stream_probe.py` 留档、**主链不调用**（v1 专用） |
| `test_vn_cli_v1.py` | v1 时代 `test_vn_cli.py` 全量快照（单动作契约 + 双核 registry.parse/executor + `（选择了: X）` 历史） | 契约层换记录流; **活的部分**（CLI 流程/事件流/收尾）已就地迁移到新文件, 这里留 v1 契约与执行层的用例原样 |
| `test_promptkit_baseline_v1.py` | v1 时代 promptkit 基线（bond 场卡 = "推进当前板块" + 盒B story 域动作 schema） | 文案已换代（记录流契约 + 记录流场卡）; 活的部分在新文件按记录流刷新 |

## 复活时请注意

代码侧对应物**大部分还在**（`core/bond/memorial_actions.py`、`fork_for_pick`、
`MemorialProbe`、`bond_actions.py`/`bond_executor.py`），只是主链不再调用：
- 引擎**只吃记录流**——旧动作 JSON 会被打回重发（P0-7c 起连"兼容开关"也已删除,
  不再有 `LIVE2BE_VN_LEGACY_ACTION`）；
- 存量测试桩若仍写 v1 形状 dict, 用 `tests/vn_fixtures.from_v1_scene()` 在**测试侧**
  转成记录流（产品侧没有这条通道）；
- 旧档回放（历史事件流里的 v1 payload）**是活的**，由 `render_bond_scene_text` 的
  旧分支 + `BondScene.from_dict` 承担，冻结不改（§3/§11 P0-6）；
- 若要复活某个机制，先把它的用例按**记录流语义**重写再取消归档，不要直接改
  `norecursedirs` 放回来（它们会立刻红）。
