# Live2Be IDE — 角色资料撰写助手

用自然语言告诉 AI 要做什么，AI 自己查资料、生成 YAML、经你批准后写入 `config/characters/`。

## 快速开始

```bash
cd /d/MYCODE/Live2Be
conda activate live2be
python -m ide.ide_agent
```

## 用法示例

```
帮我创建《蔚蓝档案》里鬼方佳代子的完整角色档案，先查萌娘百科的资料
  → AI: fetch_url 查资料 → create_character 五件套 → 你批准 → 落盘

把遥香的关系表里加上佳代子
  → AI: update_interperson（全量快照替换, 新增关系需依据）

修改佳代子的 profile，把生日改成 3/17
  → AI: update_character（merge 字段级合并）

查一下伊草遥香的资料
  → AI: fetch_url → 抓取结果回灌给 AI → 继续
```

## 工作流程

```
用户输入 → AI 判断动作 → 写动作展示 diff → 你批准(y)/拒绝(n)/中止(q) → 落盘
```

## 动作清单

| 动作 | 说明 | 审批 |
|------|------|------|
| `create_character` | 新建角色（五件套子集, 至少 profile.yml） | 需批准 |
| `update_character` | 改角色（merge 字段合并 / overwrite 覆盖） | 需批准 |
| `update_interperson` | 改人际关系（全量快照替换） | 需批准 |
| `fetch_url` | 抓网页资料（结果回灌给 AI） | 直接执行 |
| `done` | 收尾 / 等待用户 | — |

每次动作 AI 都会用 `reply` 字段说明它基于什么资料、准备怎么写。

## 模型配置

- **主项目角色扮演**：`.env` 的 `LLM_MODEL`（默认 `deepseek-v4-flash`，推理模型）
- **IDE agent**：`IDE_LLM_MODEL` 环境变量（默认 `deepseek-v4-flash`）
- **推理模型必须配大 max_tokens**：agent 内置 16384——推理模型会把预算分给
  "思考"与"内容"，预算太小会导致 content 为空（实测坑，勿改小）

## 注意事项

- 萌娘百科默认域名 **`https://zh.moegirl.org.cn/`**（`zh.moegirl.cn` 等已失效，不要用）
- **OC 角色**无需网页资料，依据写进 `basis`（宁缺勿错，不编造）
- 官方角色按 `ide/prompts/character_writer.md` 指南产出五件套（含字段结构、质量要求、范例）
