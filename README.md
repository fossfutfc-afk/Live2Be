# *这个项目只有两个原则：宁缺勿错，不OOC*

# Live2Be — LLM 驱动的角色互动故事生成器

> 灵感来源：《蔚蓝档案》(Blue Archive) · 目标用户：对 Python 不熟悉的 C++ 程序员
> 主设计文档：[CLAUDE.md](CLAUDE.md)（架构/算法/决策记录）

模拟"虚拟手机"的 LLM 叙事引擎：在类微信的 **MomoTalk** 里和角色聊天 → 羁绊加深后进入
**羁绊剧情**（视觉小说模式）→ 关键时刻生成/展示 **L2D 立绘**。角色由五件套 YAML
人设卡 ＋ 扮演手册 script.yml 驱动，人际关系由权重表控制信息访问。

## 两个入口

| 入口 | 命令 | 说明 |
|------|------|------|
| **Web GUI（主入口）** | `python -m webgui.serve --host 127.0.0.1 --port 8000` | 浏览器里：登录 → MomoTalk 聊天 → 羁绊剧情 VN → 回忆册（`webgui/`）。**停服务用菜单里的「关闭服务」**——Ctrl+C 被忽略（防手滑打断记忆消化）；急停就关掉控制台窗口（强杀也安全） |
| MomoTalk CLI | `python main.py` | 终端版：选角色 → 手机聊天 → 羁绊剧情 VN（调试入口，真代码在 `cli/`） |

需要 API key：项目根 `.env` 里配 `LLM_API_KEY`（OpenAI 兼容接口，默认 DeepSeek）。
生图另需 `[image]` 段配置（`settings.toml` 或 GUI 设置页）；`LIVE2BE_IMAGE=off` 可整体关掉。

## 目录速查

```
main.py                 启动壳（转调 cli/main.py）——`python main.py` 就是 CLI 入口
cli/                    CLI（调试入口）：main.py（对话循环）· vn_cli.py（VN 终端驱动；唯一依赖 tui 的地方）
webgui/                 Web 壳 + 会话状态机：app.py · deps.py（显式接缝）· bond/（BondState 状态机 / lane / 回放 / 生图 / 收尾）·
                        chat.py（每角色输入队列 worker）· routers/（HTTP）· static/js/{bond,mmt,gui}.js
core/                   引擎层（无 web 依赖）：mmt/engine(聊天引擎) · bond/bond_story(VN 引擎) · bond/(标注层: 情绪/换场/选图) ·
                        session/(事件流 events.jsonl + 叙事化 + 认章 + 维护) · brain/(记忆数据层: 点/边/笔记 + read/ 只读视图与召回) · digest/(记忆消化管线) · promptkit/(提示词装配) ·
                        tui/(终端展示层) · media/ · director/(视觉导演) · parsing/ · worldtime/(三层时钟) · rag/ · common/
contract/               契约地基：records/(记录流文法 + 解析 + 块/板校验 + 载体) · schema/registry/spec/model(动作契约) · errors · json_cleaner
llm/                    LLM 客户端（超时/流式/usage）+ task_levels(档位) + task_labels(调用身份) + prompts/ 文案仓库
renderer/               终端渲染管线（CLI 用：背景/立绘/特效/打字/选项）
docs/                   设计文档（DESIGN_*.md）· 执行计划（EXEC_*.md）· 审计（AUDIT_*.md）· 归档（archive/）
config/                 静态配置：characters/（人设六文件 + illustration.yml）· settings/（世界 overview.yml + 关系权重表）
tests/                  自动化测试（pytest，按域分 core/ webgui/ llm/ renderer/）
experiments/            真 API 基准与探究脚本（手工运行，烧 token）· web_e2e/（浏览器冒烟）
archive/                历史代码（旧 IDE 编辑器）；tools/ = 本机工具（gitignore）
assets/  data/          资源与运行时数据（均 gitignore；data/ 下 worlds/*/characters/*/soul/ = 事件流与记忆）
```

## 测试

```bash
pip install -e ".[dev]"               # 依赖与测试/lint 配置都在 pyproject.toml
python -m pytest                      # 全部离线测试
python -m ruff check .                # lint
python experiments/web_e2e/run.py     # B 层浏览器冒烟（Playwright 驱动本机 Chrome/Edge）
```

需要真实 API 的验证脚本（e2e / 建卡 / API 连通）在 `experiments/`，手工运行、烧 token。

### 环境

解释器用 conda env `live2be`（`C:\Users\johnf\miniconda3\envs\live2be\python.exe`），
`start.ps1` 与 `.vscode/settings.json` 都指向它。conda `base` 里**没有 jieba**，
用 `base` 跑测试会挂。

## 代码约定

1. **文件头 docstring ≤ 5 行**：一句话说清"这个模块负责什么"，必要时补一句边界。
   不写变更史、日期、"用户裁决"、决策编号、执行计划代号（`C8` / `N5b` / `P0-7c` 这类）。
2. **不留底部注释块**。已删字段的悼词、跨文件考古（"与 `x.py` 的写法相同"——而 `x.py`
   可能早就不存在了）一律删。史料归 `docs/`，不归代码。
3. **行内注释只讲"为什么"**，且只在代码本身说不清时才写。讲"曾经是什么"的删。
4. **类型注解用 `X | None`**（目标 3.12），不用 `Optional`。字符串注解只用于跨模块
   前向引用，且被引用的名字必须在本模块可见（否则 `typing.get_type_hints` 会炸，
   IDE 也会报"`|` 不能作用于 `None`"）。
5. **一个文件只干一类事**；一类职责只有一个真源模块（路径、错误、JSON 容错、重试、原子写）。
6. **依赖方向单向**：`contract` → `llm` → `engine` → `tui` / `webgui` / `cli`。反向 import 视为 bug。

## 文档索引

| 文档 | 内容 |
|------|------|
| [CLAUDE.md](CLAUDE.md) | **主文档**：架构 / 契约 / 事件流 / 提示词装配 / 配置 / 测试纪律 —— 第一份该读的 |
| [docs/EXEC_SPLIT.md](docs/EXEC_SPLIT.md) | 文件拆分与位置规划（C0–C12b 执行记录 + 陷阱清单） |
| [docs/EXEC_PIPELINE_UNIFY.md](docs/EXEC_PIPELINE_UNIFY.md) | 单一记录流流水线（records → boards）执行记录 |
| [docs/DESIGN_STREAM_CONTRACT.md](docs/DESIGN_STREAM_CONTRACT.md) | **流式契约形式（MMT + VN 统一）**：JSONL 行流 / 判别键 / 兜底分级 / 重试三段式；**附录 A = VN 记录流 v2 全文** |
| [docs/DESIGN_MEMORIAL.md](docs/DESIGN_MEMORIAL.md) | 纪念链路（art / memorial / 黑屏缓冲 / 记录级进入 / 生图质量） |
| [docs/DESIGN_PLACE.md](docs/DESIGN_PLACE.md) · [docs/AI_BRIEF_PLACE.md](docs/AI_BRIEF_PLACE.md) | 地点系统（设计稿 · 给 AI 的速查一页纸） |
| [docs/DESIGN_COLLECTION_BOOK.md](docs/DESIGN_COLLECTION_BOOK.md) | 回忆册（书页 UI / 角色页 / 只读回放） |
| [docs/DESIGN_WIKI_V3.md](docs/DESIGN_WIKI_V3.md) | 记忆图 v3（实体中心 + 混合召回 + 时间架构 + 组合） |
| [docs/](docs/) | 其余设计稿：`DESIGN_{GUI,SEGMENT,WORLD,MULTI_CHAR,VISUAL,VISUAL_PROTOCOL,PROMPTKIT,RESEND,MEETUP,FOURTH_WALL,CONTEXT_WINDOW}.md` |
| [docs/archive/](docs/archive/) | 已归档设计稿（v1 动作契约 / 旧 VN 运行时 / 旧记忆栈 / 旧 IDE 方案 …） |
