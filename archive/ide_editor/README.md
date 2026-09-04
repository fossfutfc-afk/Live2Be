# archive/ide_editor — IDE 角色撰写 Agent（已归档, 2026-09-05）

> **为什么归档**: 出厂记忆链路定稿为——wiki（图记忆）**全权交给运行时 digest（LLM）**,
> experience.yml 背景**原文直注**（LLM 扮演时自然内化）。角色创作不再需要
> "IDE agent 辅助撰写五件套"的独立编辑器: 作者直接写 config 卡, AI 创作辅助
> 若有需要走通用 LLM 对话（无需域化 agent 基础设施）。
> 2026-09-05 用户拍板: **IDE 编辑器 archive 掉**。
>
> 内容仅供历史参考, **不在主进程使用, 不保证可独立运行**（import 路径已随搬迁
> 失效）。git 历史保留全部演进。

## 内容

| 路径 | 是什么 |
|---|---|
| `ide/` | IDEAgent（角色资料撰写 agent）: agent 循环/动作集（character/interperson/search/net/view）/冲突检测/命令/事件/搜索索引 |
| `web/` | IDE 的 Web GUI 壳（fastapi + SSE + vanilla JS: hub/runner/app/mock——纯 I/O 层, 引擎零改动） |
| `entrance/` | IDE_CLI.bat / IDE_GUI.bat / IDE_GUI_mock.bat / USAGE.md / _env.bat |
| `tests/{ide,web}/` | 对应测试 |
| `experiments/` | e2e_agent / create_kayoko / run_4chars（依赖 IDEAgent 的实验） |

## 可复用资产（若未来重启）

1. **契约层动作注册表模式**（ActionSpec: schema 渲染 + parse 校验双源）——
   已泛化在 contract/（MMT/Story 域在用）, 不随 ide/ 归档
2. **IDEAgent emit/ask 回调驱动**（CLI/Web 双前端注入）——通用 agent 壳模式
3. character.yml 动作的 REQ~/SIG~ 约束体系——作者直接写卡的规范仍在
   （config/characters/.md + guidance/）

## 关联决策

- DESIGN_CONTEXT_WINDOW.md（2026-09-05: 上下文=事件流窗口/wiki=长期/卡=人设 分工——
  IDE 曾是"人机协作写卡"的载体, 该分工下无存在必要）
- 出厂记忆链路: wiki 全权 digest; experience.yml 原文直注（archive/factory_memory/）
