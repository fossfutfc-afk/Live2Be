# LLM API Client — 设计文档

> 与 `client.py` 配套，描述设计决策和所有边缘情况处理。

---

## 一、职责边界

`client.py` 只管 **HTTP 通信 + 响应解析**。不涉及角色人设、记忆检索、Prompt 拼装——那些是上层调用者的责任。

```
调用者 (momotalk.py 等)
    │
    ├── 构造 messages (含 system prompt + 历史 + 用户输入)
    ├── 决定 response_format (json_object 或 text)
    │
    ▼
client.py
    ├── HTTP POST → LLM API
    ├── 解析响应
    ├── 处理异常 / 重试
    └── 返回纯文本 or 解析后的 dict
```

---

## 二、核心设计决策

### 2.1 接口：OpenAI-compatible Chat Completions

```python
def chat(
    messages: list[dict],           # [{"role": "system", "content": "..."}, ...]
    model: str = "deepseek-chat",   # 可切换模型
    temperature: float = 0.8,
    response_format: str = "text",  # "text" | "json_object"
    max_tokens: int = 1024,
) -> str | dict:
```

**为什么用 OpenAI-compatible 而非原生 OpenAI SDK？**
- 同一个接口兼容 DeepSeek / OpenAI / vLLM / Ollama / 本地模型
- 调用方不需要关心底层是哪个提供商
- API Key 和 Base URL 从 `.env` 读取

### 2.2 JSON 响应的可靠性问题（核心难点）

#### 场景：我们需要角色返回结构化数据

例如羁绊触发判断，期望返回：
```json
{"should_trigger": true, "reason": "...", "suggested_story_id": "valentine_1"}
```

#### 问题：AI 不听话的 5 种表现

| # | 表现 | 示例 |
|---|------|------|
| 1 | **markdown 包裹** | ` ```json\n{...}\n``` ` |
| 2 | **前后废话** | `好的，这是你要的JSON：{...}希望能帮到你` |
| 3 | **嵌套字符串** | `{"text": "他说：\"你好\""}` → 内部引号未正确转义 |
| 4 | **多余字段** | 返回了 schema 之外的内容，但核心字段正确 |
| 5 | **完全拒绝** | `作为一个负责任的AI，我不能...` ——无法解析 |

#### 解决方案：分层清洗管道

```
原始响应文本
    │
    ▼
[Layer 1] 移除 markdown 代码块标记 (```json ... ```)
    │
    ▼
[Layer 2] 提取 JSON 子串 (找到第一个 { 到最后一个 } 的区间)
    │
    ▼
[Layer 3] 尝试 json.loads()
    ├── 成功 → 返回 dict
    └── 失败 →
        │
        ▼
[Layer 4] 修复常见错误后重试:
    ├── 尾部多余逗号 → 移除
    ├── 单引号 → 替换为双引号
    └── 未转义的控制字符 → 转义
        │
        ├── 成功 → 返回 dict（记录警告）
        └── 失败 → 重试整个请求（最多 N 次）
```

### 2.3 System Prompt 注入策略

调用者负责构造 system prompt。client 不参与内容，但提供 `format_messages()` 辅助：

```python
def format_messages(
    system_prompt: str,
    user_message: str,
    history: list[dict] | None = None
) -> list[dict]:
    """
    输出:
    [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "历史对话1"},    # 可选
        {"role": "assistant", "content": "历史回复1"}, # 可选
        {"role": "user", "content": user_message},
    ]
    """
```

### 2.4 重试策略

| 错误类型 | 策略 |
|----------|------|
| 网络超时 | 指数退避，最多 3 次 |
| HTTP 429 (限流) | 读 `Retry-After` 头，等待后重试 |
| HTTP 5xx | 指数退避，最多 3 次 |
| JSON 解析失败 | 先清洗再重试解析，仍失败则重试请求（附加强提示） |
| HTTP 4xx (非 429) | 不重试，直接抛异常 |

### 2.5 JSON 模式 vs 自然语言模式

LLM API 的 `response_format: "json_object"` 参数**不能保证返回合法 JSON**。它只是增强了概率。所以：

```
任何时候期望 JSON 响应：
  1. 在 prompt 中明确要求 {"key": "value"} 格式
  2. 设置 response_format="json_object"
  3. 仍然经过 Layer 1-4 的清洗管道
```

纯聊天（MomoTalk 日常对话）：`response_format="text"`，直接返回字符串。

### 2.6 本地模型兼容

本地 Ollama 的 `response_format` 支持不完整。因此 `response_format` 参数应为可选的——当目标为本地模型时，靠 prompt 描述来约束输出格式。

---

## 三、配置

`.env` 文件：

```env
# 主 LLM (支持 OpenAI-compatible 的任何服务)
LLM_API_KEY=sk-xxxxxxxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# 可选：本地模型
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=qwen2.5:7b
```

`client.py` 在 import 时自动加载 `.env`（通过 `python-dotenv`）。

---

## 四、文件结构

```
llm/
├── DESIGN.md       ← 本文件
├── client.py       ← 主 LLM 客户端
├── json_cleaner.py ← JSON 清洗管道（§2.2 的 Layer 1-4）
└── prompts/        ← Prompt 仓库（长篇 prompt 统一为 md，不内嵌在代码里）
    ├── __init__.py     ← load_prompt(name) 加载入口（缺失抛 FileNotFoundError 并列出可用清单）
    ├── momotalk_environment.md  ← 【MomoTalk 环境说明】（on_phone 文本）
    ├── momotalk_rules.md        ← 【MomoTalk 回复规则】
    ├── bond_story_rules.md      ← 【羁绊剧情 回复规则】
    └── behavior_rules.md        ← 【回复要求】（core/parsing/dynamic_character_parser 用）
```

> **Prompt 仓库**：长篇 prompt 从代码迁移为 md 文件（项目地基之一，见 CLAUDE.md 3.1.7）。
> 内容逐字节保留原内嵌文本；`load_prompt()` 统一加载，便于人工修改与 review。
> 错误消息走统一格式 `[xxx.py][errtype][errinfo]`（根级 errors.py）。

---

## 五、状态与待定

### 已实现

- [x] 流式响应：`stream=True`（MomoTalk "正在输入..."效果）
- [x] JSON 清洗管道（§2.2 Layer 1-4）
- [x] Prompt 仓库 `llm/prompts/`（load_prompt 加载 md）

### 待定 / 未来扩展

- [ ] Token 计数：在发送前估算 token 用量，超出时压缩历史
- [ ] 多 API Key 负载均衡：当单 Key 限流时自动切换
- [ ] Function Calling / Tool Use：**已由契约层部分覆盖**——`contract/` 提供
      动作注册 + 解析（LLM 输出单动作 JSON），替代原生 function calling
      （见 [../contract/DESIGN.md](../contract/DESIGN.md)）。MMT 动作化是其首次运行时落地。
