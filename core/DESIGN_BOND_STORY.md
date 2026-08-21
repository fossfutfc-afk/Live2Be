# Bond Story JSON 契约化 — 设计文档

状态：已批准（2026-08-22 用户拍板），待实现。
关联：contract/DESIGN.md（契约层根基）、llm/DESIGN.md（prompt 仓库）、core/DESIGN_AGENT.md。

## 1. 为什么改（背景）

bond_story 当前是「自由文本 + 正则找标记」（`_parse_scene` 逐行找 `【选择】`/`【完】`/数字选项）。
这一 bug 类反复出现：模型分隔段落的换行不一致（`\n\n` / `\n` / `行尾两空格+单换行`）、
标记被埋进叙事段永远检测不到、模型忘输出 `【完】`。同时 VN 历史不持久化，只有轮数落盘
（`data/basic/bond_progress.json`）。

用户拍板两个决策：
1. **运行时用契约 JSON**——LLM 直接输出场景 JSON。`contract.py` 既规范 LLM 输出、也规范程序处理。
   **一个解析器一吃两用**：运行时解析 LLM 的 story 契约 + 读存档 `json[]`（天然实现保存与重播）。
2. **重播只读回放**——无 LLM，纯渲染已存场景。

## 2. 核心架构

### 2.1 场景 = 单个 `story_scene` 动作契约

`contract/registry.py` 的 `StoryActionRegistry`（story 域）已存在但从未被注册使用——正是归宿。
镜像 `core/mmt/mmt_actions.py` 的 `build_mmt_registry()` 工厂模式：

```
LLM 输出: {"action": "story_scene", "payload": {paragraphs: [str], choices: [str], is_end: bool}}
```

- `approval = APPROVAL_AUTO`，`prompt_fields = {action, payload}`（**无 summary**——场景自解释，省 token）
- `parse_story_scene(payload)`：白名单三字段 + 机器侧容错（单字符串→单元素列表、choices>3 截断、
  is_end 接受 int 0/1 强转）+ 类型硬校验抛 ContractError
- `validate_story_scene(payload)`：is_end=true 时 choices 必须为空（跨字段一致性）
- `payload_schema` 纯文本描述三字段（由 `build_schema` 渲染进系统 prompt）

### 2.2 一个解析器，两条用途

```
运行时: LLM dict → registry.parse → AgentAction.payload → BondScene.from_dict(payload) → 渲染
存档:   同上，把 payload + input + picked 逐场 append → 原子写 data/saves/
回放:   读存档 scenes[] → BondScene.from_dict(每条) → 渲染（复用 simulate_vn_scene，无 LLM）
```

`BondScene.to_dict()/from_dict()` 是序列化唯一路径；from_dict 逐字段 `.get` 容错 + 过滤非 str，
即回放解析器。运行时与回放同一条代码路径——这就是「解析器天然读取」。

### 2.3 删除文本解析

`_parse_scene`（逐行找标记）与 `send_vn_stream`（无调用方死代码）一并删除。
文本解析这一类 bug 从此不存在。历史 assistant 内容改为存紧凑 JSON：
`json.dumps(payload, ensure_ascii=False, separators=(",",":"))`。

## 3. 存档格式

路径：`data/saves/bond_story_{char_id}_{YYYY-MM-DD_HHMMSS}.json`（沿用 sessions 命名惯例）。
`.gitignore` 需追加 `data/saves/`（现状只 ignore 了 sessions/ 和 basic/）。

```json
{
  "character_id": "rikuhachima_aru",
  "character_name": "陆八魔 阿露",
  "started_at": "2026-08-22T...",
  "trigger_reason": "老师主动邀约外出用餐",
  "ended": true,
  "scenes": [
    {"seq": 1, "input": "（旁白）基于「...」……", "paragraphs": ["..."], "choices": ["A","B"], "picked": "A", "is_end": false},
    ...
  ]
}
```

- **逐场 append + 原子写**（`tempfile.mkstemp` 同目录 + `os.replace`），崩溃也保留下半段——宁缺勿错
- `finish(ended)`：b 提前退出 → ended=false；【完】/兜底 → ended=true
- 读档 `load_save` 包 try，坏文件/非 dict → `{}` 不 raise
- `picked` = 玩家对本场景的裁决（选项文本 / 自由输入文本 / None），直接取 `simulate_vn_scene` 返回值

## 4. 运行时路径（send_vn_scene）

签名不变：`send_vn_scene(user_input, max_tokens=1536, system_note=None)`。

- messages 组装不变（双层收尾兜底的 system_note 分支保留）
- `llm.chat(messages, response_format="json_object")` → dict（json_object 内部已有 3 次语法自纠错）
- **语义重试小循环** `MAX_SCENE_RETRIES=3`：`registry.parse` 无效 → `feedback("动作无效: ...")` 重试；
  耗尽抛 `SceneLoopError(Live2BeError)`；LLM 调用异常 → feedback 重试
- 失败轮只进本次 messages，不进 history；历史只记最终有效 payload
- `SceneLoopError` 由 `run_bond_story_vn` 捕获 → 合成收尾场景 → completed=True → 存档 finish（循环必终结）

## 5. 双层收尾兜底（不变）

`run_bond_story_vn` 的 `remind_rounds`/`end_rounds`/`force_after` 循环结构不动，
只把注记措辞的 `【完】` → `is_end=true`、`【选择】选项块` → `选项（choices 留空数组）`。

## 6. 回放

`replay_bond_story(save_path, char_ms)`：读存档 → 每场 `BondScene.from_dict` → 渲染段落 +
选项 `▶` 高亮当时选择 + 结束语。纯渲染不 input、不调 LLM。
入口 `experiments/replay_bond.py [save_path]`（无参取最近存档）。

## 7. 文件清单

- 新建 `core/story_actions.py`（story_scene 契约 + build_story_registry）
- 改 `core/bond_story.py`（BondScene to_dict/from_dict、registry、send_vn_scene JSON、删 _parse_scene/send_vn_stream）
- 新建 `core/bond_story_save.py`（BondStorySave 原子写 + load_save + list_saves）
- 改 `core/ui/vn_cli.py`（recorder 接入 + SceneLoopError 兜底 + replay_bond_story）
- 改 `llm/prompts/bond_story_rules.md`（格式段改 JSON 约束）
- 新建 `experiments/replay_bond.py`；改 `experiments/engine_smoke.py`（_t_bond_scene）
- 改 `.gitignore`（加 data/saves/）
- 改 `tests/core/test_vn_cli.py` + 新建 `tests/core/test_bond_story_save.py`

## 8. 边界（本轮不做）

- `/replay` 菜单命令不进 main.py（下轮迭代挂 `mmt_preset.handle_command`，`list_saves()` 已就绪）
- `web/`、`entrance/`、`mmt_preset.py` 不引用 VN API（已 grep 确认）
- 同名秒级存档覆盖风险沿用 sessions 惯例

## 9. 验证

1. `python -m pytest -q -p no:cacheprovider` 全绿（现有 156 + 新增）
2. `python experiments/engine_smoke.py`（含改后的 _t_bond_scene）
3. 实机顺序：跑 `--vn-only` 留现状基线 → 改代码 → 再跑 `--vn-only` 验证 DeepSeek 输出
   `paragraphs` 数组是否干净（**风险点**）→ 查 `data/saves/` 存档 → `replay_bond.py` 回放
4. 宁缺勿错：存档写失败降级不阻断 VN；坏存档回放返回 False 不崩
