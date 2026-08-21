# experiments/ — 实验脚本与运行记录（非核心）

这里存放**开发期的手工实验脚本**和**运行记录**——不是核心引擎，也不是自动化测试
（自动化测试在 `tests/`）。它们被保留是为了调试历史和可复现性，**不保证可用**，
需要时从项目根目录手动运行（`python experiments/xxx.py`）。

## 脚本

| 文件 | 用途 | 需要 |
|------|------|------|
| `e2e_agent.py` | 真实 LLM 端到端：创建 OC + 查询资料 → 生成 `ide/E2E_TEST.md` | DeepSeek API key |
| `create_kayoko.py` | 推理模型 + 大 max_tokens 创建鬼方佳代子档案的实验 | DeepSeek API key |
| `llm_api_probe.py` | LLM API 连通性探测（文本 + JSON 模式） | DeepSeek API key |
| `run_4chars.py` | 批量跑 4 个角色的 CLI 冒烟 | DeepSeek API key |
| `demo_typing.py` | 打字流演示（streaming 渲染） | 无 |
| `mmt_real.py` | 真实 MomoTalk 对话实验 | DeepSeek API key |
| `mmt_two_chars.py` | 双角色 MMT 文本处理实验 | 无 |
| `engine_smoke.py` | 引擎冒烟（text_processors 核心函数） | 无 |
| `mmt_trigger_probe.py` | 羁绊触发探测实验 | DeepSeek API key |

## recordings/ — 运行记录（测试结果快照）

`cli_run_char1~4.txt` / `cli_run_transcript.txt` / `cli_run_log.jsonl` /
`cli_test_log.md` 是 IDE agent CLI 的历次运行输出转储，作为测试结果保留，
可随时重跑覆盖，不要当作权威结果。

> 说明：这些脚本原散落在 ide/、core/ui/、tests/ 下，本次布局重构统一收拢到
> 此目录。`tools/` 因 .gitignore 排除（个人工具 + 版权素材）不适合放被跟踪文件。
