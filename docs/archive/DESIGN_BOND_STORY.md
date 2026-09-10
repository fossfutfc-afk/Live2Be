# Bond Story JSON 契约化 + 双核升级 — 设计文档

> ⚠️ **已归档（2026-09-10）**：本文描述 **VN 引擎旧运行时路径**（`story_scene`/`story_end`
> 双动作 + 双 registry + JSON 单动作契约）。契约形式换代见 **`docs/DESIGN_VN_UPGRADE.md`**
> （记录流 v2；registry 的保留/改写/退役清单见该文 §8）。留作历史与设计意图参考，不再更新。

状态：已批准（2026-08-22 用户拍板，v1 已实现 + v2 双核升级）。
关联：contract/DESIGN.md（契约层根基）、llm/DESIGN.md（prompt 仓库）、docs/archive/DESIGN_AGENT.md（早期方案, 已归档）。

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

签名不变：`send_vn_scene(user_input, max_tokens=16384, system_note=None)`。
（2026-09-02: max_tokens 1536 → 8192——high reasoning 档思维链吃输出预算,
1536 在长场景（正文 + 全分支）中途截断, json_cleaner 修不动 → 连续失败。
2026-09-10: 8192 → 16384——新契约块级长输出 + 思考共享预算, wiki 记忆只增不减。）

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


---

## 10. 板块契约 v3（2026-08-30 用户拍板: 同响应分支 + 预生成零等待）

状态：已实现（commit 5e81728, 全量 277 passed）。

### 10.1 动机

真实运行暴露的四个问题（2026-08-30 用户反馈 + 分析）:
1. 表情变化极少——LLM 省略 emotion（契约可选 → 静默延续）
2. 句子太长——LLM 把多句压进大段落（prompt 曾允许"情绪一致多句合并"）
3. 选项过多——prompt 强制每场给选项（疲劳 + 凑数）
4. 选完等太久——每场一次 LLM 调用, 等待 = 完整生成时间

### 10.2 方案（借鉴 Storyloom: 短段 + bridge 预生成 + choice/branch 同响应）

- **整段剧情 = 3~5 个板块 + 收尾**（prompt 语义; 架构无板块数硬限,
  预生成/分支链路对任意板块数同构; 轮数兜底仍是上限）
- **一个板块 = 一次 LLM 调用**: 正文（2~5 句, 每句 15~40 字, 一句一段）+
  1 个选项（2~3 候选项）+ **branches**（每个选项的同响应分支内容 1~3 句）
- **emotion 契约必填**（正文 + 分支段落同一道 _parse_paragraphs 校验:
  缺 → ContractError → feedback 重试; 附加"全场同一 emotion"检测 → 下场
  system_note 提醒）
- **按句切分**（。！？；每句一段, emotion 继承; 省略号是语气停顿不切）
- **零等待链路**: 选选项 → 分支随 turn 响应直达（前端免轮询）→ 分支播放时
  后台预生成下一板块（输入固定"（继续）"）→ 点继续零等待衔接
- **选项配额**: 3~5 板块 × 每板块 1 选项 = 3~5 次选择（choices_used 注入
  system_note 提醒）; 纯叙事场由 LLM 少给（不再强制每场）
- **触发主动性**: mmt 规则加"角色主动提议见面/直接触发"（示范二为主动式）+
  频率约束（刚结束剧情至少再聊 10 轮）

### 10.3 对比实验（planned, 用户建议: 新旧方案 A/B 对照）

目标: 量化"每场自由生成 + 强制每场选项"（旧）vs "板块契约 + branches
同响应"（新）在质量/体验上的差异, 决定后续方向。

指标:
- **剧情长度**: 全文句数/字数分布（新方案是否过短——板块数 3 与 3~5 两档）
- **emotion 遵守率**: LLM 输出首次通过率（缺 emotion 的解析失败次数/总调用数）
  ——验证"一句一句输出遵守度更高"的假设
- **选项数分布**: 每段剧情选项总数（旧: 每场 1~3 → 6+; 新: 3~5）
- **体感等待**: TTFT / 分支命中率（选中分支 vs 生成成本）/ 预生成覆盖率
  （纯叙事场占比——预生成只覆盖无选项场）
- **token 成本**: 单段剧情总消耗（新方案分支全生成 ≈ 1.5~2×）

方法: 同一角色/种子场景, 各跑 N 段（N≥10）真实 LLM, 统计上述指标;
实验脚本放 experiments/（如 bond_contract_ab.py）。


---

## 11. 切分权移交定稿（2026-09-02 用户拍板: 断句/标注是程序的事, LLM 只写自然段）

状态: 已实现（commit 787d209 + 后续, 全量 461 passed）。

### 11.1 背景（用户实测反馈的三个结构性问题之一: 断句幻觉）

LLM 自切段落产生格式幻觉: （… 与 ）拆成两段、内嵌 inner 括号包裹、段内多句。
"该程序做的"（切分/配对/合并）不该让 LLM 背。

### 11.2 契约语义变更

- **story_scene/story_end/memorial_enter** 的 paragraphs 每项 = **自然段文本**
  （可长可短可含多句对白/动作; 每场 2~5 自然段 = 节拍）——LLM 不数句不拆段
- **骨架 emotion 一律丢弃**（标注层唯一真源——防双源/锚定; schema 明示"不要写,
  写了也忽略"）; inner 保留（创作内容, 挂切分后首句）
- branches 分支文本同走切分（契约 parse 统一切分, from_dict 回放/DEMO 不重切）

### 11.3 切分器 core/bond/sentence_splitter.py（规则全集）

```
孤符号清洗(全角不成对移除, 半角留 ASCII/表情/编号语境)
 → 块保护: 「」『』（） 成对区间 → 占位符（块内句末标点不切, 整块成句;
    :) :( =) 表情与 2) 编号排除; 嵌套/重叠联合; 块含句末标点/省略号 → 断点自成句,
    短语块(如 （声音很小）) 并入所在句）
 → 标点切句: 。！？； 全角 + 半角 !?; 半角 "." 两侧 ASCII 字母数字 → 不切
    (3.14 / v2.0); 半角点区(...) 跳过; 连续句末标点吞并; 省略号 … 不算句末
 → 碎句合并(jieba 正式依赖): 可见字(中英数字) ≤6 或后句 jieba 首词 ∈ 粘连虚词表
    → 并入; 合并结果 ≤30; 引号/括号块句 与 !？ 强情绪句 不并; 自然段 = 强边界
    (调用方逐段调, 绝不跨段合并)
```

### 11.4 emotion-LLM 工作方式（标注层唯一真源）

- **全量回填**: 骨架零 emotion → 每场景一次全量标注（正文 + 各分支组各一次）
- **上下文 = 角色人设 + 全场句段**: 标注 prompt 注入 {character}（身份 +
  personality 的 SIG~brief_traits 行为逻辑——"逞强笑着说没事"该标 embarrassed
  而非 smile 的人设化判断基准; 不注入情绪先验, 无锚定风险）
- **robust 化**: annotate_emotions_smart——全量校验失败 → 二分递归重标（局部错
  只牺牲局部, ≤ log n 额外调用）; 逐项容错（长度对齐但个别词表外 → 该项 None,
  其余保留）; 全败 → 延续兜底（首句 nomal）+ 标记就绪
- 输入含自然段空行分组（编号连续, 输出仍同序数组）

### 11.5 推进门控（用户拍板: 情绪没到位不让点下一轮）

- webgui turn 层 _scene_emotions_ready 门控: 当前场景（含分支）emotion 未就绪
  → 返回 busy 语义（accepted False busy True, 前端轮询自动放行; 标注 2~5s,
  玩家阅读期通常已覆盖, 实际几乎无感）
- 分支选择/继续/自由输入全部门控 → **append-only 事件流落库必含 emotion**
- bond_finish 补录最后场景前短等标注就绪（8s 超时宁缺勿错）
- closing 段落（程序文案）自带 emotion → 恒就绪
- prev_emotions（防单调 system_note）由标注 worker 回填后统一更新（骨架无值）

### 11.6 测试面

- 切分器 16 表驱动单测（块保护/数字点/表情/编号/碎句合并/合并上限/孤符号/
  真实形态回归）
- 契约: 自然段切句 + 骨架 emotion 丢弃断言; robust 标注二分/容错/人设注入
- 门控: 拦截(busy) → 释放 → 放行; 各文件 ScriptedLLM 加标注自动响应
- 全量 461 passed
