# CLI 测试记录 — 风纪委员会四角色完整建档

运行日期: 2026-08-20 19:50 – 20:05
驱动方式: `fetch/_run_4chars.py`（真实 CLI 引擎 IDEAgent + 真实 LLM, auto-approve）
结果: **4 角色 × 五件套 + interperson 全部落盘，全套回归通过**

---

## 一、名字形式测试（要求 1）

按用户要求：测试时**偶尔给全名，偶尔给后半，偶尔给别称**。逐轮记录解析结果：

| 角色 | 全名 | 后半 | 别称/繁写 | 解析结果 |
|---|---|---|---|---|
| 空崎日奈 | profile / typical | personality「日奈」 | knowledge「大可爱」experience「空崎阳奈」 | 全部正确解析到 sorasaki_hina ✓ |
| 天雨亚子 | profile / knowledge / typical | personality / experience「亚子」 | — | 全部正确解析到 amau_ako ✓ |
| 银镜伊织 | profile / experience / typical | knowledge「伊织」 | personality「银镜佐仓」 | 全部正确解析到 ginkyou_iori ✓ |
| 火宫千夏 | profile / knowledge / typical | personality / experience「千夏」 | — | 全部正确解析到 hinomiya_chinatsu ✓ |

**关键验证点**：
- 「大可爱」→ 日奈：AI 凭知识直接映射并搜索**全名**（萌百 opensearch「大可爱」会命中无关页面，AI 没有踩坑）
- 「空崎阳奈」→ 日奈（繁写）
- 「银镜佐仓」→ 伊织：萌百**没有**「银镜佐仓」页面，AI 正确映射后改用全名「银镜伊织」搜索
- 别名索引（自动构建）：本轮写入的 4 个 profile 的 `other_names` **自动进入索引**，后续「大可爱」「委员长」「银镜佐仓」等均可经索引兜底解析（见第四节修复 2）

## 二、interperson（要求 2：消除 sensei 字段）

- 4 个新角色各写入 7 条学生关系：风纪委员会成员 = 2，便利屋68 = 1
- **全程无 sensei/玩家/老师 字段**（写入后守卫 strip_sensei 复查，未发现任何字段需要消除）
- 语义修正 1 处：我初版指令把伊草遥香误列为风纪委员会（遥香实际属便利屋68），AI 主动指出并纠正；已修正日奈关系表 `igusa_haruka: 2→1`，并对后续 3 个角色改用修正后的规格

## 三、测试发现的问题（要求 3）

### 问题 1：`view_interperson` 查看"暂无关系"的角色会报错（3/4 角色触发）
- 现象：写关系前 AI 先 `view_interperson(sorasaki_hina)` 查看现状，该角色尚无记录 → 抛 ExecError「角色无关系记录」。AI 能自行恢复（照常写入），但这是无效报错
- 影响：改/补关系的标准流程是"先看现状再写全量快照"，查看不存在的角色应得到空状态提示而非错误
- **已修复**：`_execute_view_interperson` 改为返回 ok=True 空状态提示（「暂无关系记录——可直接用 update_interperson 写入全量快照」）；`_view_test.py` 对应测试更新为 `test_exec_view_interperson_missing → 无记录→空状态`，全回归通过

### 问题 2：AI 写的 `other_names` 是 YAML 列表，自动别名索引漏收（静默）
- 现象：新 4 角色 profile 的 `other_names` 为列表形式 `['空崎阳奈','大可爱',...]`，而 `build_alias_index` 只处理**字符串**形式（老 profile 是逗号分隔字符串）→ `isinstance(field, str)` 直接跳过 → 「大可爱」「委员长」等别名**没进索引**
- 影响：已建档角色的别名兜底失效（静默，无报错），与问题 1 同属"测试才发现"的缺陷
- **已修复**：`search_index.py` 新增 `_field_pieces()` 兼容 字符串/字符串列表 两种形式；新增测试 `test_build_alias_index_list_other_names`；实测「大可爱」→['大可爱','空崎日奈'] ✓

### 问题 3：AI 偶发产出非法 YAML（多行长文本块），契约层拦截后 AI 重试成功（2 次）
- 现象：
  - amau_ako typical：`- "まあ、仕方ありません。"（啊，真是没办法呢。）` —— 中文注释跟在未闭合标量后，块集合解析失败
  - hinomiya_chinatsu profile：`其他外貌细节：光环...` 长行无缩进 → `could not find expected ':'`
- 影响：本轮均通过 INVALID_ACTION 反馈 → AI 修正重试恢复，无数据损坏。但说明长描述块（dress/halo/typical 示例）是 AI 易犯的 YAML 语法区
- **修复建议（未改代码）**：已在写手提示词中有 REQ~/SIG~ 约定，但可再强调「长文本用 `>-` 折叠块并保证统一缩进」。本轮靠契约层拦截 + 重试已足够稳健，暂不改

### 问题 4：AI 给银镜伊织的 `other_names` 漏了用户提到的译名「银镜佐仓」
- 现象：AI 只写了 `['佐仓','佐三枪']`
- 处理：手动补上 `银镜佐仓`（用户明确提到「银镜伊织(银镜佐仓)」），使索引可兜底该别称
- 提示：这是 AI 数据完整性问题，非代码缺陷；写入时可提醒 AI 把对话中出现的别名都收录进 `other_names`

## 四、本轮代码修复汇总

| 文件 | 修复 |
|---|---|
| `fetch/executor.py` | `_execute_view_interperson` 无记录角色 → 空状态提示（不再抛 ExecError） |
| `fetch/search_index.py` | 新增 `_field_pieces()`，别名索引兼容 YAML 列表形式的 `other_names` |
| `fetch/_view_test.py` | 更新无记录测试为新行为 |
| `fetch/_search_test.py` | 新增列表形式 other_names 测试 |

## 五、产物

```
config/characters/
├── sorasaki_hina/     空崎日奈  (5 个 yml, 3.1-3.4KB)
├── amau_ako/          天雨亚子  (5 个 yml)
├── ginkyou_iori/      银镜伊织  (5 个 yml)
└── hinomiya_chinatsu/ 火宫千夏  (5 个 yml)
config/settings/relation/interperson.json  4 新角色各 7 条关系, 无 sensei
```

原始逐轮事件: `fetch/_cli_run_log.jsonl` / `fetch/_cli_run_char{1-4}.txt`
