# imgdesc — 让 Claude Code "看见"图片

一个本地 CLI 工具：用 **Qwen2.5-VL-7B**（跑在 Bionic/LM Studio 上，`http://localhost:1234/v1`）
把 PNG/JPG 图片描述成文字，供 Claude Code 或其他 AI 理解图片内容。
服务未运行时自动启动（无需手动 `lms server start`）。

## 用法

```bash
imgdesc photo.png                     # 详细描述
imgdesc scene.png "图里有猫吗?"       # 带问题
imgdesc a.png b.png --json            # 多图 + JSON 输出
imgdesc *.png --brief                 # 每张一行摘要
```

参数：
| 参数 | 说明 |
|---|---|
| `-q / --question` | 针对图片的具体问题 |
| `--brief` | 只输出每张图一句话摘要 |
| `--json` | 输出结构化 JSON（含路径/模型/描述） |
| `--model` | 视觉模型名（默认 `qwen2.5-vl-7b-instruct`） |
| `--no-autostart` | 不自动启动本地服务 |

## 让 Claude Code 使用

在 Claude Code 会话里直接说：

> 用 `imgdesc` 查看 `xxx.png` 的内容，然后……

或在项目 `CLAUDE.md` 里加一行，让 AI 记住这个能力：

```markdown
## Tools
- To understand an image file, run: `imgdesc <path.png> [question]`
  (local vision model, no network needed; returns a text description)
```

## 前置条件（都已配置好）

- live2be conda 环境（含 `openai` 客户端）
- Bionic 服务（模型 Qwen2.5-VL-7B-Instruct 已注册）
- 依赖：`imgdesc.cmd` 用绝对路径调用 live2be 的 python，任意目录可运行

## 可选：加入 PATH

想让 Claude Code 在任意项目目录直接调 `imgdesc`，把本目录加进 PATH：

```powershell
# 一次性（当前终端）
$env:PATH += ";D:\MYCODE\Live2Be"

# 永久（用户环境变量）
[Environment]::SetEnvironmentVariable("Path",
    [Environment]::GetEnvironmentVariable("Path","User") + ";D:\MYCODE\Live2Be",
    "User")
```

## 示例

```bash
imgdesc D:\by-user\fossf\AI\output\sd15_test.png --brief
# -> 一只红狐坐在黄昏雪松林中，暖光，数字绘画风格。
```
