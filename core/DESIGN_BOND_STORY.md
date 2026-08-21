# Bond Story JSON 契约化 + 双核升级 — 设计文档

状态：已批准（2026-08-22 用户拍板，v1 已实现 + v2 双核升级）。
关联：contract/DESIGN.md（契约层根基）、llm/DESIGN.md（prompt 仓库）、core/DESIGN_AGENT.md。

## 1. 为什么改（背景）

bond_story 当前是「自由文本 + 正则找标记」（`_parse_scene` 逐行找 `【选择】`/`【完】`/数字选项）。
这一 bug 类反复出现：模型分隔段落的换行不一致（`\n\n` / `\n` / `行尾两空格+单换行`）、
标记被埋进叙事段永远检测不到、模型忘输出 `【完】`。同时 VN 历史不持久化，只有轮数落盘
（`data/basic/bond_progress.json`）。

用户拍板两个决策（v1，JSON 契约化）：
1. **运行时用契约 JSON**——LLM 直接输出场景 JSON。`contract.py` 既规范 LLM 输出、也规范程序处理。
   **一个解析器一吃两用**：运行时解析 LLM 的 story 契约 + 读存档 `json[]`（天然实现保存与重播）。
2. **重播只读回放**——无 LLM，纯渲染已存场景。

用户拍板双核升级（v2，2026-08-22）：
3. **动作集拆分**——`story_scene{paragraphs, choices}`（中段，is_end 隐含 False）+
   `story_end{paragraphs}`（收尾，无选项，is_end 隐含 True）。收尾成为一等动作，
   **结构上保证「收尾必无选项」**，删 validate 软校验钩子。
4. **executor 执行层**——镜像 momotalk 双核（`build_mmt_registry()` 契约层 +
   `MmtExecutor` 执行层），story 域补上 `StoryExecutor` + 引擎 `trace`。
5. **存档留 vn_cli**——executor 只做校验 + trace；save 落盘仍由 vn_cli 的 recorder
   处理（picked=玩家选择在渲染后才得知）。

## 2. 核心架构

### 2.1 场景 = `story_scene` / `story_end` 双动作契约

`contract/registry.py` 的 `StoryActionRegistry`（story 域）承载双动作。
镜像 `core/mmt/mmt_actions.py` 的 `build_mmt_registry()` 工厂模式：

```
LLM 输出: {"action": "story_scene", "payload": {paragraphs: [str], choices: [str]}}   # 中段
          {"action": "story_end",   "payload": {paragraphs: [str]}}                    # 收尾
```

- 两个动作均 `approval = APPROVAL_AUTO`，`prompt_fields = {action, payload}`（**无 summary**——
  场景自解释，省 token；无 validate 钩子——跨字段一致性由动作类型结构性保证）
- `parse_story_scene(payload)` → `{paragraphs, choices}`：白名单 + 机器侧容错（单字符串→
  单元素列表、choices>3 截断）+ 类型硬校验抛 ContractError；**不看 is_end（残留字段静默丢弃）**
- `parse_story_end(payload)` → `{paragraphs}`：**非空 choices 硬拒绝**（含 nudge「请改用
  story_scene」）；空/缺省 choices 静默忽略
- `payload_schema` 纯文本描述各动作字段（由 `build_schema` 渲染进系统 prompt）

### 2.2 双核：契约层 + 执行层

```
契约层  core/story_actions.py   build_story_registry() → registry.parse → AgentAction
执行层  core/story_executor.py   StoryExecutor.execute(action) → ExecResult / 抛 StoryExecError
引擎    core/bond_story.py       send_vn_scene: parse → exec → trace → BondScene
```

- `StoryExecutor.execute` 逐行镜像 `MmtExecutor.execute`：域校验 `DOMAIN_STORY` +
  `getattr(self, f"_execute_{action.action}")` 反射分派 + 未知动作抛 StoryExecError。
- **ExecResult 复用 MMT 域**（`from core.mmt.mmt_executor import ExecResult`）——单一
  canonical 形状，无循环依赖。
- story 域动作是纯输出契约——`_execute_story_scene/_execute_story_end` 只确认「场景已就绪」，
  供 trace 留痕。媒体/立绘等副作用动作将来直接挂进 `_execute_*` dispatch 即可。

**守卫取舍（宁缺勿错、不过度拒绝）**：

| 校验 | 落点 | 理由 |
|---|---|---|
| 空 paragraphs | parse 层 ContractError（硬） | 结构错误，必须回灌修正 |
| story_end 带非空 choices | parse 层 ContractError（硬） | 结构性「收尾无选项」 |
| choices > 3 截断 | parse 层机器侧容错 | 宁缺勿错不过度拒绝 |
| 残留 is_end 于 story_scene | 白名单静默丢弃 | 迁移容错，双层兜底照常兜住 |
| 段落数上限 | 不做 | max_tokens 天然约束；拒绝只烧 token |

### 2.3 一个解析器，两条用途

```
运行时: LLM dict → registry.parse → AgentAction.payload → BondScene.from_action(动作) → 渲染
         （from_action 由动作类型推导 is_end: story_scene False / story_end True）
存档:   同上，把 payload + input + picked 逐场 append → 原子写 data/saves/
回放:   读存档 scenes[] → BondScene.from_dict(每条) → 渲染（存档显式 is_end，无 LLM）
```

`BondScene.to_dict()/from_dict()` 是序列化唯一路径；from_dict 逐字段 `.get` 容错 + 过滤非 str，
即回放解析器。运行时 from_action 与回放 from_dict 是「一解析器两用」的两个变体——动作类型
推导 vs 存档显式字段。

### 2.4 删除文本解析

`_parse_scene`（逐行找标记）与 `send_vn_stream`（无调用方死代码）一并删除。
文本解析这一类 bug 从此不存在。历史 assistant 内容改为存紧凑 JSON：
`json.dumps(payload, ensure_ascii=False, separators=(",",":"))`。

### 2.5 执行层 trace

`send_vn_scene` 每次 chat 后记一条 trace（镜像 momotalk 的 `_trace`，字段用 attempt 重试语义）：

```python
{attempt, action, summary, reply, payload,          # 解析层
 parse_valid, parse_errors,                          # 解析结果（无效 → 无 exec 字段）
 exec_ok, exec_message}                              # 执行层（仅 parse 通过后写入）
```

只读属性 `trace` 返回副本。trace 不落盘（调试/追溯用），存档 scenes[] 才是持久化真相。

## 3. 存档格式

路径：`data/saves/bond_story_{char_id}_{YYYY-MM-DD_HHMMSS}.json`（沿用 sessions 命名惯例）。
`.gitignore` 追加 `data/saves/`。

```json
{
  "character_id": "rikuhachima_aru",
  "character_name": "陆八魔 阿露",
  "started_at": "2026-08-22T...",
  "trigger_reason": "老师主动邀约外出用餐",
  "ended": true,
  "scenes": [
    {"seq": 1, "input": "（旁白）基于「...」……", "paragraphs": ["..."], "choices": ["A","B"], "picked": "A", "is_end": false},
    {"seq": 2, "input": "A", "paragraphs": ["..."], "picked": null, "is_end": true}
  ]
}
```

- **逐场 append + 原子写**（`tempfile.mkstemp` 同目录 + `os.replace`），崩溃也保留下半段——宁缺勿错
- `finish(ended)`：b 提前退出 → ended=false；story_end / 兜底 → ended=true
- 读档 `load_save` 包 try，坏文件/非 dict → `{}` 不 raise
- `picked` = 玩家对本场景的裁决（选项文本 / 自由输入文本 / None），直接取 `simulate_vn_scene` 返回值
- 存档 is_end 显式字段（兼容 v1 旧档）；story_end 场景的 payload 无 choices 键 → 存档无 choices 项

## 4. 运行时路径（send_vn_scene）

签名不变：`send_vn_scene(user_input, max_tokens=1536, system_note=None)`。

- messages 组装不变（双层收尾兜底的 system_note 分支保留）
- `llm.chat(messages, response_format="json_object")` → dict（json_object 内部已有 3 次语法自纠错）
- **重试小循环** `MAX_SCENE_RETRIES=3`（双核，语义扩展）：
  `registry.parse` 无效 → trace 记 parse 失败 → `feedback("动作无效: ...")` 重试；
  parse 通过 → `executor.execute` 抛 `StoryExecError` → trace 记 exec_message → `feedback(str(e))` 重试；
  解析或执行任一失败耗尽 → 抛 `SceneLoopError(Live2BeError)`
- 失败轮只进本次 messages，不进 history；历史只记最终有效 payload
- `SceneLoopError` 由 `run_bond_story_vn` 捕获 → 合成收尾场景 → completed=True → 存档 finish（循环必终结）

## 5. 双层收尾兜底（措辞已随双动作更新）

`run_bond_story_vn` 的 `remind_rounds`/`end_rounds`/`force_after` 循环结构不动，
注记措辞已从 `is_end=true` 改为 `改用 story_end 动作收尾`：
- 第 `remind_rounds` 场 →「请开始把剧情向结尾收束……就改用 story_end 动作收尾结束剧情」
- 第 `end_rounds` 场 →「本轮请务必改用 story_end 动作收尾结束剧情——收尾场景只有 paragraphs」

## 6. 回放

`replay_bond_story(save_path, char_ms)`：读存档 → 每场 `BondScene.from_dict`（显式 is_end）→
渲染段落 + 选项 `▶` 高亮当时选择 + 结束语。纯渲染不 input、不调 LLM。
入口 `experiments/replay_bond.py [save_path]`（无参取最近存档）。

## 7. 文件清单

- `core/story_actions.py`（story_scene/story_end 双动作契约 + build_story_registry）
- `core/story_executor.py`（StoryExecutor/StoryExecError，镜像 MmtExecutor）
- `core/bond_story.py`（BondScene to_dict/from_dict/from_action、registry、executor、trace、send_vn_scene 双核）
- `core/bond_story_save.py`（BondStorySave 原子写 + load_save + list_saves）
- `core/ui/vn_cli.py`（recorder 接入 + SceneLoopError 兜底 + 双动作兜底措辞 + replay_bond_story）
- `llm/prompts/bond_story_rules.md`（双动作 few-shot）
- `experiments/replay_bond.py`；`experiments/engine_smoke.py`（_t_bond_scene + _t_story_executor）
- `tests/core/test_vn_cli.py` + `tests/core/test_bond_story_save.py` + `tests/core/test_story_executor.py`
- `.gitignore`（data/saves/）

## 8. 边界（本轮不做）

- `/replay` 菜单命令不进 main.py（下轮迭代挂 `mmt_preset.handle_command`，`list_saves()` 已就绪）
- `web/`、`entrance/`、`mmt_preset.py` 不引用 VN API（已 grep 确认）
- 同名秒级存档覆盖风险沿用 sessions 惯例
- story_reflect 静默轮 / send_vn_scene 多步循环（镜像度最高但 VN 每场皆玩家可见，属过度设计）
- 段落数软上限、media/立绘副作用动作（将来挂进 `_execute_*` dispatch 即可）
- IDE/MMT/Story 三套 executor 收敛共享基类（当前鸭子类型）

## 9. 验证

1. `python -m pytest -q -p no:cacheprovider` 全绿
2. `python experiments/engine_smoke.py`（含 _t_bond_scene + _t_story_executor）
3. 实机顺序：跑 `--vn-only` 验证 DeepSeek 双动作下中段输出 story_scene（无 is_end）、
   收尾输出 story_end（**风险点**：若继续 story_scene+is_end:true 被静默当中段→看双层兜底
   是否仍收尾；若 story_end+choices 被硬拒→看重试收敛）、兜底注记是否引导 story_end
   → 查 `data/saves/` 存档（收尾场 is_end:true、无 choices 残留、与旧格式兼容）
   → `replay_bond.py` 回放
4. 宁缺勿错：exec 拒绝不崩、SceneLoopError 正常捕获、存档写失败降级不阻断
