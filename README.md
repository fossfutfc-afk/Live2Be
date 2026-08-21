# Live2Be — LLM 驱动的角色互动故事生成器

> 灵感来源：《蔚蓝档案》(Blue Archive) · 目标用户：对 Python 不熟悉的 C++ 程序员
> 主设计文档：[CLAUDE.md](CLAUDE.md)（架构/算法/决策记录）

模拟"虚拟手机"的 LLM 叙事引擎：在类微信的 **MomoTalk** 里和角色聊天 → 羁绊加深后进入
**羁绊剧情**（视觉小说模式）→ 关键时刻生成/展示 **L2D 立绘**。角色由五件套 YAML
人设卡驱动，人际关系由权重表控制信息访问。

## 三个入口

| 入口 | 命令 | 说明 |
|------|------|------|
| MomoTalk 聊天 (CLI) | `python main.py` | 选角色 → 手机聊天 → 羁绊剧情 VN |
| IDE 角色撰写 (CLI) | `python -m ide.ide_agent` | 自然语言让 AI 查资料/写角色档/改关系 |
| IDE 角色撰写 (GUI) | `python -m web` | 浏览器界面（`IDE_MOCK=1` 走 mock 不烧 API） |

双击启动脚本在 `entrance/`（IDE_CLI.bat / IDE_GUI.bat / IDE_GUI_mock.bat），
使用手册见 [entrance/USAGE.md](entrance/USAGE.md)。

需要 API key：项目根 `.env` 里配 `LLM_API_KEY`（OpenAI 兼容接口，默认 DeepSeek）。

## 目录速查

```
main.py                 入口（MomoTalk CLI）
config/                 静态配置：characters/ 角色五件套 · settings/ 关系+世界观 · stories/ 剧本(空)
contract/               【地基】契约层：ActionSpec 单源真值驱动 schema/校验/渲染
core/                   核心引擎：momotalk(聊天) · bond_story(VN) · bond_progress(羁绊轮数)
                        common/ 全局错误格式(errors.py) · parsing/ 解析层 · mmt/ MMT 动作集 · ui/ 展示层
ide/                    IDE agent 引擎（原 fetch/，2026 重构改名）
llm/                    LLM 客户端 + json 清洗 + prompts 仓库
web/                    Web GUI 壳（FastAPI + SSE，当前服务 ide 域）
tests/                  自动化测试（pytest，按域分子目录）
experiments/            实验脚本 + 运行记录（非核心，手工运行）
entrance/               启动脚本 + 使用手册
tools/                  开发者工具（fetch_kivo 等，gitignore 不入库）
resources/              立绘素材（diff/ 静态差分 · spine/ 骨骼动画 · possession/ 物品）
data/                   运行时数据（sessions 对话 · basic 玩家名/羁绊轮数，gitignore）
```

## 测试

```bash
pip install -r requirements-dev.txt   # 含 pytest
python -m pytest                      # 全部离线测试（~150 个）
```

需要真实 API 的验证脚本（e2e / 建卡 / API 连通）在 `experiments/`，手工运行、烧 token。

## 文档索引

| 文档 | 内容 |
|------|------|
| [CLAUDE.md](CLAUDE.md) | 总架构：四大板块 / Virtual Brain / 契约层 / 开发阶段 |
| [entrance/USAGE.md](entrance/USAGE.md) | IDE 使用手册（五件套 / REQ~SIG~ 约定 / 常见问题） |
| [contract/DESIGN.md](contract/DESIGN.md) | 契约层设计（ActionSpec / 审批策略 / 数据流） |
| [ide/README.md](ide/README.md) | IDE agent 快速上手 |
| [web/DESIGN.md](web/DESIGN.md) | Web GUI 设计（SSE 并发 / 审批桥） |
| [core/DESIGN_AGENT.md](core/DESIGN_AGENT.md) | 角色表现层设计（情感→立绘，待实现） |
| 各目录 `.exp` | 目录级说明（人类 + LLM 共读） |
