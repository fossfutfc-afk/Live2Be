# contract — 契约层设计

**状态**：已实现（2026-08）· **定位**：项目根基之一（见 CLAUDE.md 3.1.5）
**目标**：所有域（IDE / MMT / Story）的 LLM 输入/输出/校验统一由一个契约层驱动，
各项目只注册自己的动作集，不再各自手写解析。

---

## 1. 为什么需要契约层

没有契约层时，每个域（IDE（ide 域）、未来的 momotalk、羁绊剧情）都要各自实现：
- 告诉 LLM 能输出什么（prompt / schema）
- 解析 LLM 原始输出为可执行对象
- 校验字段类型、长度、取值白名单
- 把错误回灌给 LLM 修正

三份实现必然漂移：IDE 定义变了，MMT 忘了同步；schema 说允许 `sources`，解析器却丢弃它。
契约层把这三件事收进一套机制，**同一份 ActionSpec 同时驱动三层行为**（见 §3）。

## 2. 目录与依赖

```
contract/
├── __init__.py     # 集中 re-export 公共 API（from contract import ...）
├── constants.py    # 审批策略 / 动作域 / 字段上限 / is_valid_identifier
├── model.py        # 纯数据对象：AgentAction / ValidationResult / ContractError
├── spec.py         # ActionSpec（单动作注册声明）
├── registry.py     # ActionRegistry + 三个具名域 + parse_action_text
└── schema.py       # build_schema（LLM 可见） / export_definitions（纯数据导出）
```

依赖方向：`schema → registry → spec → model/constants`。各子模块内部一律用
`contract.xxx` 完整路径互导，不依赖 `__init__` 的执行顺序。
唯一外部依赖：`core/common/errors.py`（`Live2BeError` / `err()`，统一错误格式）。

## 3. 核心机制：ActionSpec 单一真源

`ActionSpec.prompt_fields`（外壳字段子集，`⊆ ALL_SHELL_FIELDS`）同时驱动三层行为：

| 层 | 行为 |
|----|------|
| **输入层** | `build_schema()` 只输出集合内的字段 → LLM 只看到这些字段（裁剪） |
| **输出层** | `AgentAction` 按集合取字段，未声明的一律为空（不污染数据） |
| **校验层** | `parse()` 按集合处理——声明了 `sources` 强制非空（宁缺勿错）；未声明则丢弃违规返回 |

外壳字段全集（`ALL_SHELL_FIELDS`）：
`{action, summary, payload, sources, basis, reply}`。
运行时动作（Story / MMT）用 `RUNTIME_SHELL_FIELDS = {action, summary, payload}`，
schema 里就不会出现 `sources/basis` 证据字段。

```python
registry.register(ActionSpec(
    "search",                          # 只读动作: 直接执行, 无证据字段
    parse_search,
    APPROVAL_NEVER,
    prompt_fields=IDE_RUNTIME_FIELDS,  # {action, summary, payload, reply}
    payload_schema='query: str(非空), source?: str, max_results?: int(1-10)',
))
```

### 审批策略（APPROVAL_*）

| 常量 | 含义 | 典型 |
|------|------|------|
| `APPROVAL_REQUIRED = "required"` | 用户批准后才执行 | 写配置（IDE 写角色/关系） |
| `APPROVAL_AUTO     = "auto"`     | 规则校验通过即执行 | 主项目运行时（MMT 动作） |
| `APPROVAL_NEVER    = "never"`    | 只读/抓取直接执行   | fetch_url / search |

## 4. 数据流

```
LLM 原始响应文本
   │  parse_action_text(registry, text)     ← 内部走 llm.json_cleaner.extract_json
   ▼
{action, summary, payload, ...} (dict)
   │  registry.parse(raw)
   ▼
(AgentAction | None, ValidationResult)
   │
   ├── is_valid=False → 停止执行，把 result.errors 回灌给 LLM 修正
   └── is_valid=True  → AgentAction（烙上 domain 标签 + approval 策略）
                          │
                          ├── 审批：required → 用户批准；auto/never → 直接
                          ▼
                      调用方按 approval 执行（ide/ide_agent.py 的 execute 流程）
```

- `AgentAction.to_dict()/from_dict()` 是 Python ↔ JS 的对称 JSON wire format
  （字段：action/domain/approval/summary/reply/payload/sources/basis）。
- `ValidationResult.errors` = 硬性错误（调用方停止 + 回灌）；`warnings` = 软提示（可放行）。

### 解析失败的两条路径

| 路径 | 触发 | 处置 |
|------|------|------|
| `ContractError`（硬） | `parse_payload` 结构错误（字段类型/白名单外/跨字段条件） | 由 registry.parse 捕获并收入 errors |
| `ValidationResult`（软） | 结构无误但软校验不通过（validate 钩子） | errors → 拒绝执行 |

## 5. 三个动作域

| 注册表 | domain | 用途 | 状态 |
|--------|--------|------|------|
| `IDEActionRegistry` | `ide` | 辅助项目：写配置（写动作默认需证据 + 用户审批） | **已使用**（ide/actions/build_ide_registry） |
| `MMTActionRegistry` | `mmt` | MomoTalk 运行时：模拟手机操作 | **规划**（下一步动作化） |
| `StoryActionRegistry` | `story` | 羁绊剧情运行时：表情/背景切换 | 规划 |

各注册表实例只属于一个域，`parse()` 出的 AgentAction 烙上域标签——域之间隔离，
各自独立注册/扩展。

## 6. 数据面（A 方案）

`export_definitions(registry)` 把动作域导出为纯数据（JSON 兼容，含 approval /
prompt_fields / payload_schema）。Python 端是唯一执行引擎，但定义本身与语言无关——
未来 JS/WebLLM 端可消费同一份数据生成自己的渲染/校验。

## 7. 与其他模块的契约

- **errors**：`ContractError(Live2BeError, ValueError)` 多继承 ValueError，
  保留既有 `except ValueError` 捕获语义；`__str__` 输出 `[model.py][ContractError][info]`。
- **llm.json_cleaner**：`parse_action_text` 依赖其 `extract_json` 从原始文本提取 JSON。
- **ide/ide_agent.py**：`client.chat(response_format="json_object")` 返回 dict 时直接
  `registry.parse(response)`，不走 `parse_action_text`（那是对原始文本的入口）。

## 8. 下一步（MMT 动作化）

- `core/parsing/relation_parser.py`：interperson 扁平权重表 → 权重→访问层级映射
- `core/mmt/mmt_actions.py`：`build_mmt_registry()` 注册 4 个动作（动作名带 `mmt_` 前缀）
  `mmt_chat / mmt_inspect_character / mmt_send_media / mmt_trigger_bond_story`；
  MMT 禁发视频（media_type 白名单仅 `image`），图片先查库后生成
- `core/mmt/mmt_executor.py`：按 approval=auto 执行动作，reply 承载对白
- `core/momotalk.py` 改造为全 JSON agent loop，历史格式同步清理（每轮至少记动作名）
