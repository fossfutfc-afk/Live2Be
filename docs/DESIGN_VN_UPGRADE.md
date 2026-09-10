# DESIGN_VN_UPGRADE.md — VN 契约形式换代（记录流 v2）

> **状态（2026-09-10）: 理论整理稿，未实施。**
> 本文汇总近两日全部讨论（形式换代动因 → 记录文法 → 角色分工 → 与 registry 的关系 →
> 预算与失败口径 → 生图链路与异步规划 → 分步实现规划）。文中凡未拍板处均标「未决」，
> 凡实测数字均标出处（探针档案见 §14）。
>
> 关联: `docs/DESIGN_MEETUP.md`（自由度移交）、`docs/EXEC_BOND_LATENCY.md`（体感工程）、
> `llm/prompts/place_annotate.md`（换场判据本体）。
> 已归档（本文取代，仅作历史参考）: `docs/archive/DESIGN_BOND_CONTRACT_V2.md`、
> `docs/archive/DESIGN_CHOICE_PREGEN.md`、`docs/archive/DESIGN_SCENE_STREAM.md`、
> `docs/archive/DESIGN_BOND_STORY.md`。

---

## 0. 一句话

**VN 的 LLM 输出契约，从「每轮一个动作 JSON（story_scene + paragraphs + choices +
branches）」换成「逐行 JSONL 的说话人记录流」**：`character`（谁在说/叙述）与
`stage`（舞台机关）两类记录，交互槽由相邻性涌现，背景/情绪仍由引擎侧标注层回填。
被推翻的是**旧契约 schema 与其解析器**；已定语义（收敛链、两遍式视觉键、事件流真源、
A1 回录、官方文风、digest 仅 story_end、中断≠失败）全部保留。

---

## 1. 为什么换形式（问题清单）

| 旧形式的问题 | 说明 |
|---|---|
| 单动作 JSON = 一板 | 一轮只能写一板（~300 字），模型永远"接着演"，不知道本场演到第几拍、何时收 → 收尾/节奏只能靠 rules 打补丁（09-09「形式收敛」即补丁之一） |
| 整包 JSON 的失败是全局的 | 一个引号坏掉整轮报废；长输出下越贵（实测：JSONL 行级错误 0.77%/行，见 §10） |
| "choice" 概念本身生硬 | 官方剧本里根本不是"选项"，是 **Sensei 台词槽 s[n]**（同一句话的两半/同向异辞）。告诉 LLM"这是选项"→ 写出菜单腔决策项 |
| 老师被写成哑巴 | 旧锁「老师的话只经选项说出」对照官方是失真：官方单条 `[s]` 台词遍地、不交互（§2.5） |
| 板粒度靠模型自觉 | "换场即换段"、板尾给选项等纪律全压在写作者身上，一处不守就串味 |
| NPC 乱入无处安放 | 多角色同场需要"给谁选项"的特殊规则；记录流下只是多一个说话人 |

**目标校正过程**（保留在案，避免重走弯路）：`SAX + 长输出` → 发现"XML 外壳无用"
（Storyloom 的 XML 实为逐行正则状态机）→ 收敛为**行协议 + JSON 叶子** → 最终定为
**两分法记录流**（`character` / `stage`），连"候选数组"都被相邻性取代。

---

## 2. 契约文法（v2）

### 2.1 记录形状

```jsonl
{"character": "narrator", "text": "（深夜的杂草屋，只有一盏台灯亮着。）"}
{"character": "haruka",   "text": "……老师，你、你来了。"}
{"character": "sensei",   "text": "是我来晚了。"}
{"character": "sensei",   "text": "路上买了点东西。"}        ← 连续两条 = 交互槽
{"stage": "switch",       "text": "深夜的杂草屋"}
{"stage": "memorial",     "text": "（她忽然抬起头，朝我笑了一下。）"}
{"stage": "end",          "text": "（夜风停了。）"}
```

**每条记录恰好含 `character` 或 `stage` 之一**（两者都有 / 都无 = 格式错误，丢行 + 计数）。
`text` 除 `stage:exit` 外必填。**不存在 action 字段、不存在数组容器、不存在嵌套**。

| 字段 | 取值 | text 含义 | 位置约束 |
|---|---|---|---|
| `character` | 角色 id（如 `haruka`） | 台词 | 任意 |
| `character` | `sensei` | 老师台词；**连续 ≥2 条 = 候选槽**（玩家挑一句），单条 = 剧本台词 | 任意 |
| `character` | `narrator` | 叙述（旁白/舞台指示） | 任意 |
| `stage` | `switch` | **目标地点（自由文本，永不是资产键）** | 任意；**本章第一条必须是 switch**（交代开场景） |
| `stage` | `memorial` | 触发句（可省） | **本块最后一条** |
| `stage` | `end` | 收尾正文（可省） | **本块最后一条** |
| `stage` | `exit` | （可省） | **本块最后一条**，仅纪念域 |

### 2.2 规范八条（写进 schema 文档与 rules）

1. 一行一条记录（JSONL）；字段恒为两个（`character`/`stage` + `text`）。
2. `text` 内的半角 `"` 与 `\` 必须转义——rules 里配一条带 `\"` 的 few-shot（探针证明这是唯一真实错误源，且模型见过例子就会做对）。
3. **不写地点键、不写情绪键**（引擎侧标注层唯一真源）。
4. 不出现"选项/choice"字样——老师的话用"此刻会说的几句"表述。
5. 块 = 一次 LLM 调用；`end`/`memorial`/`exit` 必须块尾，`switch` 可在任意位置。
6. 本章第一条必须是 `switch`。
7. 块行数引导 12~20 行（下限 ~10，上限 ~35 仅作引导；引擎不截断——用户拍板"给大致数值，不设硬上限"）。
8. 连续 `sensei` ≥2 才构成交互槽；单条是剧本台词，不弹 UI。

### 2.3 为什么是 JSONL（而非整包 JSON / XML 行）

- **整包 JSON**：失败全局化 + 无法渐进 + 截断全损（DeepSeek `json_object` 是"整回复单对象"，
  与多记录流互斥，且官方文档明示可能返回空内容）。
- **XML 行协议**（Storyloom）：其内核实为逐行正则状态机，外壳 XML 只为承载"元素树 +
  条件属性"（branch/set/route）——我们已证明不需要这些，外壳只剩成本（开闭标签/属性引号/
  实体转义）。
- **JSONL**：转义免费、解析器标准、坏行只死自己、可渐进消费、截断只丢尾行。
  **"多重闭合"实测不构成风险**：391 行里结构性错误 0 次，错误全在内容转义与收笔（§10）。

### 2.4 命名与两分法的由来（实测）

命名探针（`jsonl_probe4.py`，6 配置 ×3 份）：**字段名不影响守约**（漂移 0 / 多余字段 0 /
围栏 0），但语义别扭的名字会让产出缩水（`kind` 记录数最少且丢边界记录）。
语法探针（`jsonl_probe5.py`）：单字段 vs **两分法**（`character`/`stage`）——
两分法形状违规 0、跨类误用 0、**产出量最高**（58 条/4 份 = 14.5 条/板）。
两分法顺带消掉了 `@` 前缀的需要（保留值天然住在 `stage` 里）。

### 2.5 官方剧本实证（BA 支线 1600002 抽取）

```
[  42] [指令] 3;하루카;04;呃，啊？！不用！我自己去就可以了！老，老师就不用和我一起……！
[  43] [指令] [s1]“我想和你一起去。”
              [s2]“你不想和我一起吗？”
[  45] [指令] 3;하루카;04;……！！
```
- `s1/s2` 是**同一 utterance 的两半**（陈述 + 反诘），不是互斥决策项；`s3/s4` 是同向异辞；
- 序号跨槽累进（s1→s2→s3→s4），是 **Sensei 台词流水号**，不是"第几组选项"；
- 槽之后**接续只写一份**（收敛链 + 候选同向），官方结构本身背书我们的收敛语义；
- 单条 `[s]` 遍地（"你好，春香。""做得不错。"）——**不交互**，就是剧本台词。

---

## 3. 与旧契约的对照

| 维度 | 旧（单动作 JSON） | 新（记录流） |
|---|---|---|
| 输出单位 | 一板一个 `story_scene` JSON | 一次调用 = 一串记录（多板） |
| 交互 | `choices: []` + `branches: {}`（键=选项原文） | 连续 `sensei` 记录（相邻性） |
| 老师台词 | 选项文本 | `character: sensei` 的 `text`；被选中者**物化**进历史，未选者从不进入 |
| 收尾 | `story_end` 动作 | `stage: end` 记录（块尾） |
| 纪念 | `memorial_enter` / `memorial_exit` 两个独占动作（另一 registry） | `stage: memorial` 触发 + **块边界即结束**（章内状态区间）→ 见 §7 |
| 分支 | `branches` 同响应预写、当屏直显 | 取消：`branches` 概念消失（收敛链下候选只需"说法不同"） |
| 背景 | 标注层 place 锚点（同一套） | 不变；新增 writer 的 `switch` 信号（§5） |
| 解析 | `registry.parse(dict)` 整包校验 | `parse_line(str)` 逐行 + 诊断聚合（§9） |
| 失败 | 整轮重试 | 行级丢弃 + 计数 + 下轮反馈 |

---

## 4. 角色分工（谁拿什么）

| 角色 | 输入 | 产出 | 拿词表 |
|---|---|---|---|
| **Writer**（主 LLM, bond） | rules + 记忆 + 拍卡 + 上下文 | 记录流（`character`/`switch`/`memorial`/`end`） | **不拿** |
| **Place 标注器**（bg-LLM） | `switch` 的 text + 当前场景 + 词表 + 前后 2 行 | `{line, place}` 稀疏锚点（或 quiet） | **拿**（唯一） |
| **Emotion 标注器** | 待判文本 + 词表 + 上一行情绪 | 逐行情绪键 | 拿 |
| **Planner**（蓝图） | 章目标 + 人设摘要 | 拍谱（`intent` / `slot` / `end`；**不含 scene**——方案 B 倾向） | 不拿 |
| **画师步**（生图 prompt） | 蓝图画面意图 + 角色外观 + 实际正文 | 成品 image prompt | 不拿资产细节 |

原则：**键与词表只活在"翻译层"，永不回灌 writer 上下文**（历史渲染里 `switch` 只回显
writer 自己写的那句 location 文本，绝不回显解析出的资产键）。

---

## 5. 背景 / 换场（switch + 翻译）

**WHEN 归 writer，WHICH 归标注器**：

- writer 发一条 `{"stage": "switch", "text": "深夜的杂草屋"}`（自然语言地点，可用自己话）；
  规则：换场（含时间/天气跃迁）必须发；`text` 要具体到名词短语（禁"外面/某处"）。
- engine 提取 `text` → 查**翻译表**（命中即 0 调用）→ 未命中则一次极小解析调用（带前后 2 行上下文）→ 资产键。
- 翻译表形态（世界目录）：

```yaml
# config/worlds/{world}/places.yml
- key: weed_hut_night
  owner: igusa_haruka            # 个人地点（可选）
  aliases: [深夜的杂草屋, 杂草屋, 废弃小屋, 那间小屋]   # 可混语言
  desc: 春香常待的废弃小屋（夜）
```
- 缓存：`data/worlds/{world}/places_resolved.jsonl`（原文→键，自动增长）；未命中且解析不了 → 三级兜底
  （角色默认景 → 全局默认 → keep）+ 日志 `[place][MISS] X`（**日志即美术需求单**）。
- 开场景：**本章第一条必须是 `switch`** → 引擎立刻解析（不必等整块生成完）→ 首屏背景零等待。
- 板边界由标注结果决定：锚点行前必切板（§6）。

---

## 6. beat / 板的新定义

**板从"LLM 的输出单位"降级为"引擎的派生单位"**——这是整份契约的地基改动。

```
边界来源（三类 + 兜底）：
① 换场点（标注层发现）        → 前必切板、背景在此切
② 交互槽（连续 character: sensei ≥2） → 槽前必切板
③ 端点（stage: end / memorial）       → 前必切板
④ 长度阈值（~8 行/板）        → 只为标注与提交节奏兜底，不为叙事
```

- 模型**不需要知道板的存在**（零格式负担），板在标注流水上长出来；
- 板保留的职责：**最小提交单元**——事件落库、回放、重试粒度、标注门控（用户 09-10 拍板）；
- 玩家侧节奏：行级打字机 + **板间无缝连播**（用户拍板）；只有槽/end 处才停；
- 事件 payload = 该板的记录数组（append-only 不变，形状变了）。

---

## 7. memorial（章内状态区间）

- 触发：`{"stage": "memorial", ...}`，必须是**本块最后一条**；engine 校验**章级 ≤1 次**（计数落 marker，可恢复）。
- 区间 = 从触发记录到**本块结尾**（不需要 `exit`/`art` 记录——用户拍板简化）。
- 区间内允许：`character`（narrator/角色/**sensei**；老师的话"少而关键"，可构成候选槽）；
  禁止：`switch`（定格瞬间不换场）、`end`、第二个 `memorial`（违规 = 丢行 + 反馈 + 日志）。
- 退出三路（都不卡死）：① 块自然结束；② 玩家 UI 关闭 = 立即回 bond、0 LLM；③ 玩家离开 = abort 语义（不伪造收尾）。
- **结语另起一块**（不与该块同块）：块边界是纪念区间的唯一界线；结语在读完纪念后写，落点更好。
- 生图见 §11（`illustration.yml` 已提供角色级提示；触发点前置）。

---

## 8. 与 registry / contract 层的关系（重点）

### 8.1 现有形态（事实）

```
contract/
  spec.py      ActionSpec(name, parse_payload, approval, validate, prompt_fields, payload_schema)
  registry.py  ActionRegistry.parse(raw: dict) → (AgentAction, ValidationResult)
               + StoryActionRegistry / MemorialActionRegistry / MMTActionRegistry / IDEActionRegistry
  schema.py    build_schema(registry, action_list=False) → LLM 可见 schema 文本
               export_definitions() → JS/WebLLM 数据面
  model.py     AgentAction / ContractError / ValidationResult
  constants.py 域常量 / 外壳字段 / 长度上限
```
`core/bond/bond_actions.py` 注册 `story_scene` / `story_end` / `memorial_enter`；
bond 引擎持双 registry（story + memorial 域）并按 registry.parse 校验。
**注意先例**：MMT 域在 2026-09-02 已经走完同样的一步——`build_schema(action_list=True)`
渲染的是 **messages 消息流协议**（chat = 消息序列，text 单元 + action 单元任意交错）。
VN 记录流 = 这同一思路在 story 域的对应演进。

### 8.2 保留

| 构件 | 保留理由 |
|---|---|
| `domain` 概念 | 域仍是 promptkit 盒 / 夹具 / 校验的边界（story 域 = VN 记录域） |
| `build_schema()` 作为唯一渲染入口 | 新增**第三种形态**：记录流 schema（与 MMT 的消息流并列），示例行 + 规范八条 |
| `ContractError` / `ValidationResult` 语义 | 逐行解析仍需要结构化诊断（行号 + 原因 + 是否致命） |
| promptkit 夹具基线机制 | 契约文本变了 → 夹具必须同批刷新（`PROMPTKIT_UPDATE_FIXTURES=1` + 人工审 diff） |
| 审批策略常量 | story 域仍全 `APPROVAL_AUTO`，不变 |
| `export_definitions()` 数据面 | 前端/回放仍需要契约的可序列化描述（形状随文法更新） |

### 8.3 改写

| 旧 | 新 |
|---|---|
| `ActionSpec.parse_payload(dict)` 白名单 | `RecordSpec`：kind（character/stage）+ 允许值 + 位置约束（块尾）+ 数量上限（槽 ≤3）+ 转义规范 |
| `ActionRegistry.parse(dict) → AgentAction` | `parse_line(text) → VnRecord \| ParseDiag`；另给 `parse_stream(lines)` 批量入口（回放/存档/测试） |
| `payload_schema`（JSON 字段描述） | **记录文法说明 + 示例行**（LLM 可见文本） |
| 双 registry（story/memorial 动作集） | 收敛为**单域 + 状态约束**：memorial 的合法性由状态机（§7）而非另一套动作集保证（未决：是否彻底合并 registry） |
| `memorial_enter/exit` 独占动作 | `stage: memorial` 触发 + 块边界结束 |

### 8.4 退役（仅 story 域）

- 外壳字段（`summary` / `sources` / `basis` / `reply`）与 `action` 字段：VN 记录流没有"动作"概念；
- 单动作 JSON 输出约定（`response_format="json_object"` 的 story 用途）；
- `paragraphs` / `choices` / `branches` 的白名单与容错（`_parse_paragraphs*`）；
- `is_end` 迁移容错等旧协议残留。

### 8.5 不动

- **MMT 域**（`mmt_*` 动作 + messages 消息流协议）——手机聊天与 VN 各自演进；
- **digest 域**（RoundA/B 长 JSON）——批处理任务不是流式正文，`json_object` 仍合适；
- emotion / place 标注域的输出形态（数组/锚点，任务级小输出）；
- 事件流 append-only、marker 栈、`window_messages`、预生成链等运行时骨架。

### 8.6 迁移影响面（清单）

| 面 | 具体改动 |
|---|---|
| `core/bond/bond_actions.py` | 动作集 → 记录文法 spec + 行解析器 |
| `contract/schema.py` | 新增记录流渲染形态 |
| `llm/prompts/bond_story_rules.md` / 盒 B schema 块 | 重写为记录流规则 + few-shot（含转义示例） |
| `core/bond/bond_story.py` | 组装/解析/重试/收尾判定改为流式消费；板由标注派生 |
| `core/ui/vn_cli.py`、`webgui/bond.py` | 流式消费 + 板派生 + 槽物化 + 事件 payload |
| A1 回录 | 选中候选**物化**为单条 `sensei` 记录（不再写"（选择了: X）"注解） |
| renderer | 记录 → 文本流（含说话人标识的最小呈现） |
| 测试桩 | 各 `ScriptedLLM` 应答改为记录流；夹具全量刷新 |
| 存档/回放 | 板 payload 形状变更（旧档只读兼容策略待定，未决） |

---

## 9. 预算与失败口径

| 项 | 值 / 规则 | 出处 |
|---|---|---|
| bond `max_tokens` | **16384**（2026-09-10 由 8192 翻倍；"wiki 记忆只增不减"） | 提交 `4908590` |
| thinking 与正文**共享**预算 | 实测思考可吃 3.3~3.7k token；2048 预算下出现 `content=0` + `finish=length` | `jsonl_probe7.py` |
| 块行数引导 | 12~20 行（下限 10 / 上限 35 仅引导，不截断） | 用户拍板 |
| 行级格式错误 | 0.77%/行（391 行 3 处：2 处未转义半角引号 + 1 处末行悬空） | `jsonl_probe3.py` |
| 尾行悬空 | 引擎补 `"}` 重试即可救回（EOF 处无歧义） | 同上 |
| 结构性错误 | 0（无括号/逗号/围栏/跨行记录问题） | 同上 |
| 失败分类 | ① 行级格式错 → 丢行 + 计数 + 下轮反馈；② `finish=length` / `content` 空 → **独立计数 + 可重试**（非格式问题） | 探针 6/7 |
| 两遍式标注档位 | emotion/place `thinking=off`（既定铁律，探针 7 从反面验证） | `llm/task_levels.py` |

---

## 10. 生图链路与异步规划

### 10.1 实测（同一角色，4 次真机调用，$0.05/张）

| # | 条件 | payload | 耗时 | 原始出图 |
|---|---|---|---|---|
| 1 | 原 ref（21.7MB）+ 旧 prompt | 21.7MB | 26.08s | 608×1737（竖长条：比例跟随首张 ref） |
| 2 | 原 ref + 精简 prompt + `aspectRatio` | 21.7MB | 26.15s | 1376×768（**16:9 生效**） |
| 3 | **ref 压缩**（1024/JPEG85）+ 同上 | **0.33MB** | 22.00s | 1376×768 |
| 4 | 同上 + 角色 `halo_hint` 注入 | 0.33MB | 13.70s | 1376×768 |

**结论**：payload 压缩 66× 只省约 4s → **延迟地板 ≈ 20s 是模型生成本身**；13.7~26s 方差大，
需真机多采样取 p50/p90（未决）。**想再快只能"更早发图"**。

### 10.2 异步设计（不阻塞玩家）

```
① 拍组开始（蓝图标记本拍组含纪念）
     └─ 画师步出草案 prompt（可选：先不发图，只备好）
② stage: memorial 记录闭合（文本流中）
     └─ 画师步定稿 prompt → 立即异步生图（独立线程，主链外）
③ 玩家侧：纪念文本即时可读 → 图到**淡入** → 未到不阻塞 → 退出后进图鉴
```
- **幂等/回放**：prompt 与图引用落事件流（`l2d`）；回放/resume **不重生成**；prompt hash 缓存复用；
- **取消钩子**：玩家离开 → 丢弃在飞结果（abort 语义，不落假收尾、不落假 l2d）；
- **失败降级**：生图失败/超时 → 保留占位 + 单行 WARNING，纪念照常进行；
- **成本上界**：纪念一章 ≤1 次 + 提示只会触发一次 → 生图调用有硬上界。

### 10.3 已落地的接口（生图侧）

| 能力 | 位置 | 状态 |
|---|---|---|
| 单后端（删本地 diffusers） | `llm/image_gen.py` | ✅ `3d77fe4` |
| 逐图标签（角色本体/画风基准/配饰：光环） | 同上 | ✅ `b0907d0` |
| 目标尺寸 = 屏幕尺寸（`screen_size` + `aspectRatio` + 归一化 contain/cover） | 同上 | ✅ `b0907d0` |
| 返回值 `GeneratedImage(path/width/height/elapsed/source_size)` | 同上 | ✅ `b0907d0` |
| ref 上传前压缩（1024/JPEG85 + 缓存） | 同上 | ✅ `1395eaa` |
| 角色级生图提示 `illustration.yml`（`halo_hint`/`character_hint`） | `config/characters/{id}/illustration.yml` + `CharacterLoader.load_illustration` | ✅ `ebc5c66` |
| 端到端确认提示真的进请求体 | `tests/llm/test_image_gen.py` + `tests/webgui/test_bond.py` | ✅ `3cd9891` |

> 与 `profile.yml` 的 `halo` 字段**刻意分开**：后者是给其他角色/扮演查阅的设定，
> `illustration.yml` 专供生图。

---

## 11. 分步实现规划（假如要实现）

> 纪律：**每步一提交、可回退**；收口节点跑全量；文案/契约/夹具同批。
> 顺序原则：契约层（纯函数）先于引擎接线；**P0 不顺手改预生成/双 lane**，保证回退面干净。

### 11.1 P0 — 记录流最小闭环（不动标注 / 预生成 / 前端结构）

| 步 | 做什么 | 触及文件 | 完成标志 |
|---|---|---|---|
| **P0-1** | **文法 spec**：`RecordSpec`（kind=character/stage、允许值、位置约束、槽上限、转义规范）+ 单域 registry 挂载 | `contract/`（新增 `records.py`，或扩展 `spec.py`）、`core/bond/bond_actions.py` | 单测：合法/非法记录行判定正确；保留值与角色 id 不冲突 |
| **P0-2** | **行解析器**：`parse_line(text) → VnRecord \| ParseDiag`；`parse_stream(lines)` 批量；坏行丢弃 + 诊断聚合（行号/原因/致命性） | 新模块（如 `core/bond/record_parse.py`） | 回归用例覆盖 §9 三类坏行：未转义引号、**末行悬空补 `"}`**、数组行拍平；391 行样本零致命误判 |
| **P0-3** | **schema 渲染第三形态**：`record_stream=True` 输出记录文法 + 规范八条 + 示例行；rules 重写（few-shot 含 `\"` 转义样例） | `contract/schema.py`、`llm/prompts/bond_story_rules.md`、盒 B schema 块 | 夹具刷新 + 人工审 diff；真机输出守形（照 probe5 口径统计） |
| **P0-4** | **引擎接线（单板）**：`send_vn_scene` 改为"收集文本 → 行解析 → 组装板"；板提交语义沿用现网（暂不做块式多板/板派生） | `core/bond/bond_story.py`、`core/ui/vn_cli.py`、`webgui/bond.py` | 真机跑通一场：开场 `switch` → 若干行 → 槽 → `end` |
| **P0-5** | **槽与回录**：连续 `sensei ≥2` 生成槽；选中者**物化**为单条记录进历史（替代"（选择了: X）"） | 引擎 + `core/session/renderer.py` + `record_picked` 路径 | live 历史与回放同形；未选台词不出现在任何视图/上下文 |
| **P0-6** | **落库 / 回放 / 存档**：板 payload 改记录数组；旧档只读策略落地（转换层 or 冻结） | `core/session/*`、`renderer/` | 回放逐字节稳定；旧档不炸（转换层测试 or 显式拒绝 + 提示） |
| **P0-7** | **夹具与测试桩迁移**：各 `ScriptedLLM` 应答改记录流；promptkit 基线刷新 | `tests/{core,webgui,llm}` | 全量绿 + 真机一场（含 switch/槽/end） |

**依赖关系**：P0-1/2/3 相互独立可并行 → P0-4 依赖三者 → P0-5 与 P0-6 可并行 → P0-7 收尾。

### 11.2 P1 — 标注单 lane + 换场翻译

| 步 | 做什么 | 完成标志 |
|---|---|---|
| P1-1 | 世界目录 `config/worlds/{world}/places.yml`（key/owner/aliases/desc）+ 引擎读取 | 表可加载、别名可查、缺文件不炸 |
| P1-2 | `switch` → 翻译（命中缓存 0 调用；未命中一次极小调用，**固定带前后 2 行上下文**） | 开场景解析在首条记录闭合时即发起 |
| P1-3 | 解析缓存 `places_resolved.jsonl`（原文→键）+ `[place][MISS]` 日志（= 美术需求单） | 命中率可观测；miss 可 grep |
| P1-4 | 标注合并为**单 lane**（emo 逐行 + place 翻译）；板边界由锚点决定（前必切） | 双 lane 机制退役；背景切换内容驱动 |

### 11.3 P2 — 块式长输出

| 步 | 做什么 | 完成标志 |
|---|---|---|
| P2-1 | 一次调用多板：流式消费 + 引擎按（换场/槽/端点/长度阈值）派生板 | 玩家无感；板=提交单元不变 |
| P2-2 | 行数引导（12~20 行；上限仅引导）+ 无缝连播 | 首板 TTFT 前移；早收率可观测 |
| P2-3 | 失败口径落地：行级丢弃计数、`finish=length`/空 content 独立计数与重试策略 | 指标进日志（可 grep） |
| P2-4 | 预算复核（bond 16384 是否够 35 行块；`window_messages` 单元定义） | 真机长块压测一次 |

### 11.4 P3 — 蓝图 planner

见 §12（待用户先想清蓝图形态再开工）。

### 11.5 P4 — 生图异步完善

| 步 | 做什么 | 完成标志 |
|---|---|---|
| P4-1 | **画师步**（独立小调用：蓝图画面意图 + 角色外观 + 实际正文 → image prompt） | 与 writer 解耦；产物可审计 |
| P4-2 | 两个触发点（拍组开始草案 / `memorial` 闭合定稿发图）+ 主链外线程 | 纪念文本零等待；图晚到为常态 |
| P4-3 | 图到淡入 + 图鉴兜底 + 回放不重生成 + prompt hash 幂等 | 回放 0 生图；重复进纪念不重复烧钱 |
| P4-4 | 取消钩子（玩家离开丢弃在飞结果）+ 真机 p50/p90 采样 | 中断不落假 l2d；延迟分布入档 |

---

## 12. 蓝图（planner）待决问题

> 本节是**给用户思考用的提问清单，不是方案**。P3 开工前建议至少回答 A/B 两组。

**A. 形态与粒度**
1. 蓝图的单位：章级拍谱（每拍一行）／幕（几拍一组）／更细（每拍带情绪走向）？
2. 每拍记什么：`intent` 之外，要不要 `emotion_arc`（情绪走向）、`slot`（表态点）、`end`（收尾点）、`scene`（换场计划）、`foreshadow`（伏笔）？
3. 拍的数量级：一章几拍？（现网真实数据：igusa 一章 6 板正文 + 1 收尾板）

**B. 归属与时机**
4. 谁定：作者手写 ／ 规划 LLM（独立档位 `blueprint`）／ 引擎确定性骨架 + LLM 只填 intent？
5. 何时定：章首一次 ／ 逐块滚动（每块结束规划下一步）／ 混合（章首粗排 + 块间微调）？
6. 漂移后如何重规划：判据（蓝图说换场但标注没发现／流里冒出蓝图外的槽／拍数超支／情绪走偏）？频率上限（现拟 ≤2 次/章）？已执行拍的冻结边界（板级？槽级？）

**C. 与"三权分立"如何相容**
7. `scene` 两方案未拍：A（规划者写 scene，拍卡暴露少量场景名）vs B（不含 scene，词表只归标注器）。若选 B，"防单调"由谁保障（rules 提示？蓝图 intent 自带场景变化？）
8. 蓝图是**引导**还是**约束**？writer 写偏时：引擎纠正、还是接受并记账？

**D. 与既有系统的接口**
9. 存放与注入：落事件流章节头 payload？每块一张拍卡的 token 预算多少？
10. 与 `chapter_title`（MMT 触发时 3-16 字）的关系：标题即蓝图标题锚，还是蓝图另起？
11. 与 digest／记忆：跨章连贯要不要让 wiki 产物参与下一次规划？关系阶段是否影响蓝图密度？
12. 与 memorial：蓝图标记"本拍组含纪念"就是**生图提前量的触发点**——纪念计划显式写进蓝图（含画面意图）吗？

**E. 长期复用（官方剧本）**
13. 官方固定剧情 = 手写蓝图 + 手写正文。现有 BA 抽取（`s[n]` 记号）能否直接转成"蓝图 + 记录流"？转换管线现在设计还是以后？
14. 蓝图 schema 要不要容纳作者演出提示（舞台指示／特效／好感节点），还是保持极简？

---

## 13. 未决清单

1. **registry 合并深度**：单域 + 状态约束（倾向）还是保留 story/memorial 两个 registry 只换语义？
2. **槽上限**：连续 `sensei` ≤3 是硬校验（丢行）还是软引导（保留 + 反馈）？
3. **块上限口径**：35 行引导是否最终改为"token 预算数字"？
4. **旧档兼容**：旧 `story_scene` payload 的只读回放策略（转换层 or 冻结旧档）。
5. **蓝图 scene 字段**：方案 A（规划者写）vs 方案 B（不含 scene，倾向 B）。
6. **生图数值**：`ref_max_edge` 定值（1024 vs 1536）、p50/p90 采样、光环位置是否加"正上方居中"约束。
7. **`window_messages` 单元**：记录流下"叙事单元"的定义是否从板改为记录（影响 120 单元窗口语义）。
8. **渲染层**：说话人是否需要最小标识（名字/颜色/气泡）；是否本轮一并升级 UI。

---

## 14. 附录：探针档案（`.testtmp/`，不提交）

| 文件 | 用途 | 关键产出 |
|---|---|---|
| `jsonl_probe.py` / `probe2.py` | JSONL vs 单文档 JSON 出错率（温和/加硬） | 温和双 100%；加硬 JSONL 行好率 98.5% |
| `probe3.py` | 坏行抓现行 + 原始留存（`probe_raw/`） | 3/391 行坏：2 未转义引号 + 1 末行悬空 |
| `probe4.py` | 字段命名对照（speaker/who/actor/kind × narr/@前缀） | 命名不影响守约；`kind` 产出缩水；`@` 前缀最稳 |
| `probe5.py` / `probe6.py` | 单字段 vs 两分法（× end/memorial 变体） | 两分法 0 违规、产出最高；"尾条失败"实为空响应 |
| `probe7.py` | 空响应归因 | thinking 与正文共享 `max_tokens`（2048 → content 全空） |
| `probe_img_latency.py` | 生图真机计时（单张，授权后跑） | §10.1 四行数据 + `gen_out/last_request.txt` 审计留痕 |
| `check_img_request.py` | 离线 prompt 全文检查（零成本） | 逐图标签 / 比例 / payload 画像 |
