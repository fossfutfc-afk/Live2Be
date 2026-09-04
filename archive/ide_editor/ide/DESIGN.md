# IDE-Resources 设计文档 v0.1

> **⚠️ 已过时（superseded）**：本文是早期 `ide_resources` 设计稿 v0.1，包 `ide_resources`
> 已不存在。当前实现演进为 `ide/` 子项目（`IDEAgent` + 契约层动作 + CLI/Web GUI），
> **以 [ide/README.md](README.md) 为准**。本文保留作为设计决策的历史参考。

> 状态：等待 review。
> 范围：纯 CLI；只做单角色目录撰写；不抓图片/背景/L2D 资源。

## 1. 产品定位

IDE-Resources 是 Live2Be 的独立 CLI 辅助工具，本质是一个受限的角色资料写作对话器。

- 用户用自然语言指定角色，并区分“铁律”和“可修改”。
- LLM 综合用户输入、自身知识和网页资料，生成角色五件套 YAML。
- AI 的唯一动作是请求写入允许范围内的文件。

## 2. 运行环境
统一使用 `conda activate live2be`，Python 3.12。
建议 LLM 通过 Bridge 复用主项目 `llm/client.py`；YAML 用 PyYAML，网络用 httpx，HTML 提取用标准库 `html.parser`。
## 3. CLI 交互
启动：`python -m ide_resources`，可用 `--name`、`--target-id`、`--constraints`。
会话命令：`/help`、`/name`、`/target`、`/iron`、`/mutable`、`/source`、`/constraints`、`/proposal`、`/diff`、`/apply`、`/discard`、`/mode`、`/session`、`/exit`。
## 4. 约束体系
- 铁律：只有用户能改，最高优先级。
- 可修改：AI 可调整但必须说明。
- AI 推断：提出后等待用户批准。
约束来自 `constraints.yml` 或对话“铁律/可修改”；CLI 单独保存并在每轮注入。
冲突时铁律胜出；网页与 LLM 冲突必须列出，不能静默采用。
## 5. 会话记忆
单次 CLI 保留完整上下文；持久化 JSONL 到 `data/ide_sessions/`，不存 API Key。
对话过长时保留最近 30 条消息，旧信息压成“已确认事实卡”。
## 6. 网页资料
接口：`fetch_url(url, max_chars)` 与 `search(query)`。
v1 支持用户给 URL，httpx+`html.parser` 提取文本并截断，不执行 JS、不下载图片。
搜索先留接口；抓取失败必须报告，不能静默忽略。
## 7. 角色输出
输出 `config/characters/<id>/` 下五个固定文件。
遵循 `REQ~`/`SIG~`/无前缀/`null`；`profile.yml` 必须存在；字段 snake_case。
LLM 返回 `character_write_request`，包含完整五件 YAML、`interperson` 和 sources。
落盘前校验 ID、文件名、YAML/JSON、必填显示名。
## 8. interperson.json
写入前读取现有文件并注入 LLM；AI 提出完整新 JSON 或保持不变。
展示 diff，用户批准后写；缺少依据不能凭空添加关系。
优先级：用户明确关系 > 资料明显关系 > AI 猜测。
## 9. 已存在目录
目录存在时询问“新建/原目录”，不能静默覆盖。
新建要求新 ID；原目录读取现有文件给 AI，`mode` 必须是 merge 或 overwrite。
用户也可用 `/mode` 指定。
## 10. 安全边界
AI 只能请求写 `config/characters/<id>/*.yml` 和 `interperson.json`。
禁止 shell、图片下载、改 `.env`、stories、主项目源码、删除目录。
写前校验路径、白名单、YAML/JSON，并展示 diff 等待确认。
## 11. 测试
测试：约束解析、输出契约、YAML/JSON 校验、路径安全、新建/merge/overwrite、URL fetcher fixture、Mock LLM 端到端。
真实 API 和网络测试默认跳过。
## 12. 实现顺序
1 包结构/CLI；2 会话与约束；3 LLM Bridge 与输出契约；4 SourceFetcher；5 校验与写入；6 审批和目录分支；7 Mock 测试；8 文档示例。
## 13. 待确认
1 是否复用主项目 `llm/client.py`？yes
2 v1 是否必须实现网页搜索，还是只支持用户给 URL？默认萌娘百科，kivowiki,BAfandomwiki即可
3 `interperson.json` 是否由 AI 推断生成提案？可以，但必须谨慎，宁缺勿错
4 角色 ID 由用户指定还是 AI 生成？假如是OC用户指定，否则统一英文全名全小写如igusa_haruka

