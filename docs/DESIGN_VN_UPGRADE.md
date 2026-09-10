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
| `character` | `sensei` | 老师台词：**每条 = 一个独立动作/一句话**；**最长连续 sensei 段 = 一个「群」，长度 1~3**；**群一律弹选项**（run=1 = 单选项、2~3 = 多选项，玩家挑一句说） | 任意（块内出现几次不限） |
| `character` | `narrator` | 叙述（旁白/舞台指示） | 任意 |
| `stage` | `switch` | **目标地点（自由文本，永不是资产键）** | 任意；**本章第一条必须是 switch**（交代开场景） |
| `stage` | `art` | **画面意向（1~2 句：谁/在哪/什么时刻/什么情绪；不写构图参数）** | **必须是本块第一条**；一章 ≤1；本块必须兑现 `memorial`（见 §7/§10.4） |
| `stage` | `memorial` | 触发句（可省） | **块内偏后**；**其后到块尾均为纪念区间**（§7） |
| `stage` | `end` | 收尾正文（可省） | **本块最后一条** |
| `stage` | `exit` | （可省） | **本块最后一条**，仅纪念域 |

### 2.2 规范十条（写进 schema 文档与 rules）

1. 一行一条记录（JSONL）；字段恒为两个（`character`/`stage` + `text`）。
2. `text` 内的半角 `"` 与 `\` 必须转义——rules 里配一条带 `\"` 的 few-shot（探针证明这是唯一真实错误源，且模型见过例子就会做对）。
3. **不写地点键、不写情绪键**（引擎侧标注层唯一真源）。
4. 不出现"选项/choice"字样——老师的话用"此刻会说的几句"表述。
5. 块 = 一次 LLM 调用；`end`/`memorial`/`exit` 必须块尾，`switch` 可在任意位置，**`art` 必须在块首**。
6. 本章第一条必须是 `switch`（若本块含纪念，则 `art` 紧随其后、成为该块的**首条**）。
7. 块/拍行数引导 **~40 行**（正常一拍含转场等约 40；**memorial 块同取 40**）。写进 prompt；引擎不截断
   ——上限只为"失败重试丢尾"规模与"程序 vs AI"判断留空间。
8. **sensei 群 = 最长连续 sensei 段，长度 1~3**（硬上限 3）。规范样例：
   `遥香 遥香 sensei 遥香 遥香 sensei sensei sensei 遥香` = **2 个群**
   （第一个 = 单选项；第二个 = 三选项）→ **4 次发言，玩家 2 次交互**。
   **不再用"整章 0~3 次"配额**（块内出现几次不是坏事）；引导模型"**把一句话拆两三半**"（官方 `s1/s2` 同款）。
   **群一律弹选项**：`run=1` 也弹（单选项，玩家点一下让老师说这句）——不做"自动播的剧本台词"。旧 webgui
   的"整章 ≥3 次后省略选项"机械兜底**保留为死代码**（不再触发）。
9. **`art` 是"预告制"**：它是本章纪念时刻的声明（意向级），引擎据此提前启动画师步+生图；
   未声明也能进纪念（降级为触发即发图，功能不丢——见 §7）。
10. **`max_tokens` 别卡太死**：命中上限（`finish=length`）要成为一个**明确的程序侧信号**，
    与"AI 自己写短了"清楚区分（诊断优先于省 token）。

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

**另一份样本 1600008（春香"错误的地点"，完整一章）**（详见 §14 附录）：
- 109 条记录里 **4 个表态点**（`SelectionGroup` 1/2、3/4、5/6、7/8），台词槽仍同向异辞，
  另有**动作型选项**（`[ns1] （环顾四周）` / `[ns2] （再等了一会儿）`）→ 印证"Sensei 的行动列表"；
- 转场 = `Transition（fade out 2000ms / fade in 2000ms）` + `BGName` + `#all;hide`；
- 中段切进 **`SpineBG_LobbyHaruka`（春香的记忆大厅 L2D，`MemoryLobbyDBSchema` 交叉验证）**，
  其"差分"是 L2D 动画态（`Idle_01` / `Talk_01_M`…`Talk_05_M`），且**进入前先淡到 `BG_Black`**。

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
- 词表 / 别名 / 资产 = **现成的背景资产库（2026-09-10 改版）**，不新造 `places.yml`：

> ⚠️ **状态（2026-09-10）**：该库是**目标形态**，但**人工审核远未完成**（`_place_review.json`
> 中大量 `active=false` / 条目待补）→ **实现先沿用旧系统**（`_director_whitelist.json` 的
> `common_scenes` + `assets/background/`）。接入（P1-1）等审核完善后再切换，届时按 `active`
> 导出词表即可。

```
D:\myStuff\tempo\                        ← 背景资产库根
  SDIR_*（10 大类）/DIR_*（210 地点组）/BG_*.jpg        合计 1115 张
  SDIR_Atmosphere\DIR_PureColor\    BG_Black.jpg / BG_Red.jpg / BG_White.jpg
  _place_review.json   人工审校: "SDIR|DIR|entity_key" → {name, region, keywords, active, note}
  _place_entities.json 机器可读导出: entity_key → {sdir, dir, name, region,
                        keywords[], files{day[], night[]}}
  place_studio.py      自包含工作台（942 行; 官方地名表 + 别名归一化 + 可选 LLM 建议）
```
  - **`_place_entities.json` 就是本节要的"翻译表"**：`entity_key`（英文 slug）+ `name`（中文主名）
    + `keywords`（别名，`|` 分隔，含官方译名变体）+ `files.day/night`（资产相对路径）；
  - **`_place_review.json` 的 `active` = 是否进词表**（人工裁决，如"夏莱会议室…暂时不进词表"）
    ——这正是"舞台清单"开关，取代散落的 `_director_whitelist.json`（对齐见 §13）；
  - 引擎侧读**导出视图**（可缓存为 `places_resolved`），`place` 锚点 + 时间（day/night）选图；
  - 纯色背景（`BG_Black` 等）是**本地资产、零生成**——memorial 黑场直接用它（§7），
    且**纳入导演可选项**（拍板 12：黑场/闪白/闪红等过渡）。
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
- 玩家侧节奏：**逐句点击推进**（每句话点一下；`sensei` 群弹选项）——取代原先"板间无缝连播"的设想，
  与官方 VN 观感一致；**每一次点击之间的停顿本身就是异步线程的天然缓冲**（§10.4）。
- 事件 payload = 该板的记录数组（append-only 不变，形状变了）。

---

## 7. memorial（章内状态区间）

- 触发：`{"stage": "memorial", ...}`（**块内偏后**；其后到块尾即纪念区间）；engine 校验**章级 ≤1 次**（计数落 marker，可恢复）。
- 区间 = 从触发记录到**本块结尾**（不需要 `exit`/`art` 记录——用户拍板简化）。
- 区间内允许：`character`（narrator/角色/**sensei**；老师的话"少而关键"，可构成候选槽）；
  禁止：`switch`（定格瞬间不换场）、`end`、第二个 `memorial`（违规 = 丢行 + 反馈 + 日志）。
- 退出三路（都不卡死）：① 块自然结束；② 玩家 UI 关闭 = 立即回 bond、0 LLM；③ 玩家离开 = abort 语义（不伪造收尾）。
- **降级 = 直接降级为普通 bond story（拍板 17）**：图 15s 未就绪（或生图失败）→ **不切 memorial 模式**，
  按普通 VN（背景＋差分＋文本）继续渲染——因为 memorial 与 bond story 的**记录文法互通**，
  区间内的 `character` 记录在两边都能渲染。图后到只入图鉴（不再回插）；`memorial_enter` marker
  按"未进入"处理（或落 enter+exit 成对，实施时定）。
- **结语另起一块**（不与该块同块）：块边界是纪念区间的唯一界线；结语在读完纪念后写，落点更好。
- **前置声明（块首 `stage: art`，预告制）**：若本块将包含纪念，模型在**第一条记录**发**画面意向**
  （1~2 句，意向级；不写构图参数）。引擎据此在**块解析通过后**启动画师步 + 生图 → 块内铺垫的阅读
  时间即缓冲桥（§10.4）。规则：一章 ≤1（与纪念同寿命）；本块必须兑现 `memorial`；`text` 空 = 无效声明；
  **未声明也能纪念**（降级为"触发即发图"）。
- 生图见 §11（`illustration.yml` 已提供角色级提示；触发点前置）。
- **过场机制（照官方 1600008 实证，见 §14）**：触发句在**旧背景 + 立绘**上正常显示 →
  背景连同立绘一起 **fade out 2s** → 停在 **`BG_Black`（纯色资产，零生成）** →
  **fade in 2s** 进入纪念画面（官方 `Transition = fade out 2000ms / fade in 2000ms`）。
  **这 ~4s 黑场是等待缓冲**：图就绪即续 fade in；未就绪则停在黑场（有加载态，超时上限
  后降级纯文本）——比"停在上一拍"更接近官方观感。
- **纪念段隐藏立绘与差分**（官方 `#all;hide`；用户拍板"memo 模式无差分变化"）——
  立绘层进入黑场后即撤，纪念画面由"背景层 + 文本"承担。

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
| 块行数引导 | **~40 行**（正常一拍含转场约 40；memorial 块同取 40。写进 prompt，不截断） | §2.2 规范 7 |
| `max_tokens` 放宽 | **别卡太死**：命中上限 = 程序侧信号；写短而未命中 = AI 侧 | §2.2 规范 10 |
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

### 10.2 异步设计（无蓝图 + 硬闸门 + 黑场缓冲）

**memorial 是硬闸门**（用户 09-10 更正）：`stage: memorial` 之后**不再渲染文本**，画面切到
生成图；纪念段**无立绘/差分变化**。所以"文本先行、图晚到淡入"是错的——等待只能发生在闸门处。

```
Writer 流：…铺垫板… │ {"stage":"memorial","text":"触发句"} │ 纪念文本（等图放行）
                     │              ▲
玩家侧：  读铺垫板（← 掩盖窗口 = 闸门前阅读 + 预生成链提前量）
                     │              └─ 闸门：图就绪 → fade in 2s 进纪念画面 → 放行文本
                     └─ 触发句显示完 → fade out 2s → BG_Black（纯色资产）→ 等图
```

- **提前量来源**（无蓝图，按贡献排序）：
  1. **预生成链（最大头）**：块在玩家读上一块时就已生成完 → 画师步 + 生图可在玩家进入该块前发出；
  2. **闸门前的正文阅读**（该块触发点之前的部分）；
  3. 画师步耗时（与正文生成并行，可忽略）。
- **黑场即缓冲**：fade out 2s → `BG_Black` → fade in 2s（官方数值）；图未就绪就**停在黑场**
  （带加载态），就绪立刻续 fade in；**超时上限**（建议 ~30s）后降级纯文本纪念，绝不卡死。
- **起跑点**：`stage: memorial` 闭合即启动画师步；纪念文本攒够（≥2 行 / ≥80 字）即定稿发图——
  此时玩家通常还在读铺垫板。
- **幂等 / 回放**：prompt 与图引用落事件流（`l2d`）；回放/resume **不重生成**；prompt hash 缓存复用；
  **回放时若 `l2d` 缺失**（玩家在生成中离开）→ 允许一次性补偿重发，再失败则纯文本。
- **取消钩子**：触发被引擎拒绝（本章已有纪念 / 格式违规）→ 丢弃在飞结果；其余情况让请求跑完
  （钱已花，纪念事实已落 marker）。
- **成本上界**：纪念一章 ≤1 次 + **只在真正触发时发图**（不投机预生成）→ 生图调用有硬上界。

#### 10.2.1 组件与职责

| 组件 | 何时动作 | 做什么 | 失败时 |
|---|---|---|---|
| **触发器**（解析器/引擎） | `stage: memorial` 记录闭合 | 校验（章级 ≤1）→ 落 `memorial_enter` marker → 置 `memorial_pending` → 唤醒 worker | 校验失败（二次纪念/违规）→ 丢行 + 反馈，**从不发图** |
| **画师步**（新增 LLM 任务档 `art`，thinking off / max_tokens ~512） | 纪念区间文本成形（**块尾**；若玩家已在闸门则攒够 ≥2 行即启动） | 从纪念正文提取画面指令（谁/在哪/表情/构图/光线）→ 中文 scene prompt | 失败 → 退化为"取纪念最后 2~3 行原文"当 prompt（零额外成本） |
| **生图 worker**（独立线程，主链外） | 画师步返回 | ref 压缩 + `illustration.yml` 提示注入 → APIYI 生图 → 归一化到屏幕尺寸 | 失败/超时 → 单行 WARNING；闸门走降级分支 |
| **画廊 / 事件** | 图落盘后 | `GalleryStore.write`（含 width/height）+ `l2d` 事件（引用式） | 落库失败 → 图仍在盘上，按文件名兜底 |
| **闸门**（前端/CLI） | 播放到触发记录 | 触发句在旧背景+立绘上显示 → **fade out 2s** → `BG_Black` → 等 `memorial_img_ready` → **fade in 2s** → 放行纪念文本 | 超时（~30s）→ **黑场纯文本**；图若稍后到达且玩家仍在纪念段 → 替换，否则入图鉴 |

#### 10.2.2 状态机

```
pending ──(worker 起)──► generating ──(图落盘 + l2d)──► ready ──► 播放纪念文本 ──► 块尾结束
   │                          │
   │                          └──(失败/超时)──► degraded（黑场纯文本，后台仍可补图）
   └──(触发被拒)──► cancelled（从未发起生图）
```
- **CLI 同步路径**：无 GUI 轮询 → worker 结果直接 join（等于阻塞在黑场），逻辑同构；
- **回放**：读记录 + `l2d` 引用 → 0 生图；`l2d` 缺失（玩家在生成中离开）→ **允许一次性补偿重发**，再失败则纯文本。

#### 10.2.3 延迟预算（决定"到闸门有没有图"）

| 阶段 | 典型量级 | 说明 |
|---|---|---|
| 预生成链给的头寸 | **30~90s** | 玩家读上一块的时间（块已生成完 → 画师步/生图提前跑） |
| 画师步 | 1~3s | 小调用，与正文生成并行 |
| 生图 | **13~26s**（方差大） | 实测（§10.1） |
| 黑场 fade | **4s**（2s+2s） | 官方数值，体感缓冲 |

判定式：**闸门前阅读时长 + 黑场 4s ≥ 画师步 + 生图** → 到闸门即有图；
否则玩家在黑场等（有加载态，超时降级）。

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

### 10.4 桥接时机：块首预告制（`stage: art`）

**形式化**（Storyloom `docs/theory/bridge-mechanism.md` + `asset-generation.md` 的落地）：

```
可行性:  T_consume(声明 → 展示之间的消费)  ≥  T_gen(素材)
代价:    Freeze(b) 随声明位置 b 前移单调增大
```

一维轴上的各方案坐标：

| 方案 | b | 固化代价 | 等待 |
|---|---|---|---|
| 开章定调（`trigger_bond_story` 一发就定 prompt） | ≈0 | **最重**（画面先于剧情） | 无 |
| 投机预生成 | ≈0 | 最重 + **白烧 $0.05** | 无 |
| **块首预告（本条）** | **块首** | **最轻（意向级）** | 基本无 |
| 触发即发（原设计） | ≈1 | 零 | 黑场 + 干等 |

两条关键修正：
1. **度量的是"玩家剩余阅读量"而非内容位置**——生成比阅读快（写 15 行 10~20s vs 读 15 行 40~60s）
   ＋预生成链 → "已生成未读"的内容天然是缓冲；
2. **固化代价取决于声明多具体**：意向级几乎不冻结剧情，画面级才冻结 →
   我们站 `(块首, 意向级)`，画面细节由**画师步**从（角色卡 + refs + `illustration.yml` +
   场景 + 意向 + 前文）补全。

另：memorial **不是分支点**，所以没有 Storyloom 那种"桥接 ⇒ 交互自由度上界"的额外代价
（那是他们选项模型的代价，不是桥接的普遍代价）。

**⚠️ 声明 ≠ 发图（本轮新增的关键结论）**：
- **声明**在块首（第一条记录）：占配额 + 定意向 + 给引擎预警；
- **发图**推迟到**块解析通过（无致命错误）**那一刻——块可能被重试/废弃（场级语义重试 ≤3），
  在块首就发图会为废弃块白烧 $0.05；
- 预生成链下"块解析通过"仍发生在**玩家读上一块期间**，提前量几乎不损失；
- 幂等：同一意向文本 → prompt hash 命中 → 不重复发图。

**时间账（预生成路径）**：上块剩余阅读 30~90s ＋ 本块生成 10~20s ＋ 本块铺垫阅读 20~60s
＋ 黑场 4s，对比 13~26s 生图 → **到闸门基本必有图**。
额外一层：**逐句点击推进**（每句话一次点击）会把铺垫阅读时间进一步拉长——玩家的点击节奏
本身就是异步线程的缓冲，不需要任何额外机制。

#### 10.4.1 边界情况清单

| # | 情况 | 处理 |
|---|---|---|
| 1 | 声明了但本块没进 `memorial`（含改走 `end`） | 记格式错误 + 下轮反馈；图**入图鉴**（不落 `l2d`，回放不误显示）；不重发 |
| 2 | 进了 `memorial` 但被引擎拒（本章已用过） | 声明即占章级配额 → 第二次声明**直接拒且不发图** |
| 3 | 忘了声明却直接 `memorial` | **允许**（关键降级）：回到"触发即发图"路径；记 INFO |
| 4 | `art` 不在块首（中段才出现） | 宽容接受并照常发图（提前量变少）；记 INFO，不进反馈 |
| 5 | 同块两条 `art` | 取第一条；第二条记错误、不发图 |
| 6 | `art` 的 `text` 空/无意义 | **视为无效声明**（不发图，避免无信息 prompt 烧钱）+ 反馈 |
| 7 | 块被重试/废弃 | 发图点已推迟到"块解析通过"→ 废弃块零成本；重试块同意向走 hash 幂等 |
| 8 | 预生成期间玩家 `vn_abandon` / 切角色 | 图落 gallery（资产），**不落 `l2d`**；不阻塞、不留假痕 |
| 9 | 块内既有 `switch`（换场）又有 `art` | 意向须覆盖换场后的场景；规则建议"声明置于换场之后" |
| 10 | `art` 出现在纪念区间内 | 违规（区间只允许 `character`/`sensei`）→ 丢行 + 反馈 |
| 11 | 触发闭合时图未就绪 | 正常路径；到闸门仍未就绪 → 黑场加载态 + **15s 后降级**（见下） |
| 12 | 降级后图才到 | **只入图鉴**（已按普通 bond story 渲染，不再回插替换） |
| 13 | 降级的具体行为 | **不切 memorial 模式**，按普通 VN（背景＋差分＋文本）继续——两套记录文法互通；`memorial_enter` 按"未进入"处理 |
| 14 | 图早就绪（命中） | **仍走固定 fade 两段**（官方节奏）——演出节奏优先于"省时间" |
| 15 | 纪念段极短（1~2 行） | 块边界（结语另起一块）天然是 pause 点，玩家可停留看图 |
| 16 | 本章有 NPC 同场 | 纪念图**以该角色为唯一主体**（官方 memorial = 单人 L2D 画面） |
| 17 | 换装/差分变体 | 纪念图取哪个 outfit 的 ref **未定**（现 ref 为角色级一套）→ §13 |
| 18 | BGM/音效 | 官方进记忆大厅会换 BGM（= 该角色 lobby BGM）；我们无该资产 → §13 |
| 19 | CLI 同步路径 | 声明与发图都在"块生成完"之后 → 提前量只剩铺垫阅读；可接受（开发路径），记档 |
| 20 | 观测口径 | 记 5 个时间戳：声明 / 发图 / 图就绪 / 到达闸门 / 闸门等待 ms |

**新增观测指标**：`gate_wait_ms` 分布（p50/p90）、`art→ready` 时长、`declared_but_unfulfilled` 计数、
`art_hash_reuse` 命中数。

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
| P1-1 | 读**背景资产库导出视图**（`D:\myStuff\tempo\_place_entities.json`：key/中文名/keywords 别名/files.day-night；`_place_review.json` 的 `active` 过滤出词表）+ 引擎侧缓存 **（⚠️ 库的人工审核未完成 → 本期先沿用旧 `_director_whitelist.json`，切换时机见 §5 状态注）** | 表可加载、别名可查、`active=false` 不进词表、缺文件不炸 |
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

**当前倾向：不立项**（2026-09-10 讨论，见 §12 抬头）。若确认，本阶段整体跳过；
替代物 = `mmt_trigger_bond_story` 可选 `bible` 字段 + 引擎侧起承转合计数（都不新增 LLM 调用）。

### 11.5 P4 — 生图异步完善

| 步 | 做什么 | 完成标志 |
|---|---|---|
| P4-1 | **画师步**（独立小调用：角色外观卡 + `illustration.yml` + **块首 `art` 意向** + 场景 + 前文 → image prompt；在**块解析通过**后启动） | 与 writer 解耦；产物可审计 |
| P4-2 | **闸门机制**：触发句 → fade out 2s → `BG_Black`（纯色资产）→ fade in 2s 进纪念画面；图未就绪停在黑场（加载态）+ 12~15s 降级纯文本；命中时仍走固定节奏 | 黑场即缓冲；绝不卡死 |
| P4-3 | 落库/幂等/回放：`l2d` 引用 + prompt hash 缓存 + 回放 0 生图 + `l2d` 缺失时一次性补偿 | 重复进纪念不重复烧钱 |
| P4-4 | 取消钩子（触发被拒才取消）+ 真机 p50/p90 采样（生图分布 / 闸门前阅读时长 → 就绪命中率） | 延迟与命中率入档 |

---

## 12. 蓝图（planner）待决问题

> **当前倾向（2026-09-10 讨论）：不立项。** 论证见下；本节其余问题**仅在重开时**才需要回答。
>
> 理由三条：① InfiPlot 式计划的字段里，`sceneSummary/sceneKey/entryActiveCharacters/
> speakingTone` 等四个直接服务于**图像/语音管线**（我们每章只生 1 张图，且由画师步从实际
> 正文产出，无需机位预告）；② `logline/genreTags/synopsis/openThreads` 是**无限长度故事**
> 的约束刚需——我们是有界一章（实测 ≈2.4k 字），`window_messages` 120 单元**装得下整章**；
> ③ 那些字段本质是"LLM 整理给 LLM 的 prompt"= **wiki**，我们已有 digest→wiki + 人设 + 好感 +
> MMT 历史这条链，只是节奏不同（他们在飞更新，我们事后消化）。
>
> **替代物（都不新增 LLM 调用）**：`mmt_trigger_bond_story` 未来可加可选 `bible` 字段
> （章首一句意图，等价于现有 `chapter_title` 的扩展）+ 引擎侧起承转合/多段计数（把纪念推向
> 靠后 → 为生图买阅读时间）。
>
> **重开条件**：VN 变长线（一章超出窗口 / 多章连演）｜多角色同场群像（需要 cast 调度）｜
> 改成每拍生图（需要镜头计划）｜官方长剧本需要多拍结构对齐（那用手写结构，不是 planner LLM）。

**（以下为若重开时的提问清单）**

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

## 13. 决策记录（2026-09-10 用户拍板）与残留未决

| # | 议题 | 决定 |
|---|---|---|
| 1 | registry 合并深度 | **单域**：一个 VN 记录域 + 状态约束（memorial 由状态机管，不另立动作集） |
| 2 | 槽上限 | **软引导**；语义钉死：每个 `sensei` text = **一个独立动作/一句话**，引导模型"**一句话拆两三半**" |
| 3 | 块上限 | **~40 行写进 prompt**（正常一拍含转场约 40；memorial 块同取 40）；`max_tokens` **别卡太死**（命中上限 = 程序侧信号，写短 = AI 侧） |
| 4 | 旧档兼容 | **直接冻结**（不做转换层；旧 `story_scene` 档只读不可续） |
| 5 | 蓝图 scene 字段 | **先不含 scene**，以后打补丁 |
| 6 | 光环位置约束 | **不加**（不写"正上方居中"之类） |
| 7 | `window_messages` 叙事单元 | **要改**：单元由"板"改为"**记录**"（影响 120 单元窗口语义，P0 一并处理） |
| 8 | 渲染层说话人 | **需要升级（大问题）**：必须能**按名字分辨**说话人（现网是单角色文本流）；**未来引入 NPC table** 供 LLM 调用第三方角色（有些场景不可避免要用到第三方） |
| 9 | 词表对齐（旧白名单 vs tempo 库） | **先用老方法**，不急 |
| 10 | `place_studio.py` 归属 | **不迁入**仓库，放在 `D:\myStuff\tempo` 原处 |
| 11 | 选项密度 | **撤销"整章 0~3 次"稀缺配额**。规则改为：**sensei 群 = 最长连续 sensei 段，长度 1~3**；群内 1 条 = 单选项、2~3 条 = 多选项；块内出现几个群不限。样例：`遥香 遥香 sensei 遥香 遥香 sensei sensei sensei 遥香` = 2 个群（单 + 三）→ 4 次发言、**玩家 2 次交互** |
| 12 | 纯色背景 | **是**：纯色纳入导演可选项（黑场/闪白等） |
| 13 | 纪念图 outfit ref | 先按现状；**未来加字段**（换装维度）作为扩展 |
| 14 | 记忆大厅 BGM | 我们有音乐资产；**未来做 audio_llm**，不急 |
| 15 | 立绘指令（跳动/移动等，差分 06/07 之外） | **未来扩展**（`#3;jump/hophop/shake` 那类演出的对应物） |
| 16 | 降级阈值 / `art`·`switch` 顺序 | 阈值 **15s**；`art` 置于 `switch` 之后 = **规则建议**（非引擎强制） |
| 17 | **降级行为（本轮关键）** | **直接降级为普通 bond story**：memorial 与 bond story 的**记录文法互通** → 不切 memorial 模式，按普通 VN（背景＋差分＋文本）继续渲染；图后到只入图鉴 |
| 18 | **run=1 的 UI / 推进节奏** | **统一弹选项**（run=1 = 单选项，不做"自动播的剧本台词"）；**逐句点击推进**（每句话点一下）——取代"板间无缝连播"；点击停顿即异步缓冲 |
| 19 | 旧的"≥3 次省略选项"机械兜底 | **保留为死代码**（不再触发），不必删除 |

**残留未决（真未定）**：
- `art` 意向文本的长度上限（现定"意向级 1~2 句"，是否设硬上限）；
- 说话人分辨的 **UI 形态**（名字/颜色/气泡——#8 的落地形态，属 P0 渲染层升级）；
- 生图 **p50/p90 采样**与闸门命中率实测（待"规模定了"再测）。

---

## 14. 附录：探针档案与官方实证（`.testtmp/`，不提交）

| 文件 | 用途 | 关键产出 |
|---|---|---|
| `jsonl_probe.py` / `probe2.py` | JSONL vs 单文档 JSON 出错率（温和/加硬） | 温和双 100%；加硬 JSONL 行好率 98.5% |
| `probe3.py` | 坏行抓现行 + 原始留存（`probe_raw/`） | 3/391 行坏：2 未转义引号 + 1 末行悬空 |
| `probe4.py` | 字段命名对照（speaker/who/actor/kind × narr/@前缀） | 命名不影响守约；`kind` 产出缩水；`@` 前缀最稳 |
| `probe5.py` / `probe6.py` | 单字段 vs 两分法（× end/memorial 变体） | 两分法 0 违规、产出最高；"尾条失败"实为空响应 |
| `probe7.py` | 空响应归因 | thinking 与正文共享 `max_tokens`（2048 → content 全空） |
| `probe_img_latency.py` | 生图真机计时（单张，授权后跑） | §10.1 四行数据 + `gen_out/last_request.txt` 审计留痕 |
| `check_img_request.py` | 离线 prompt 全文检查（零成本） | 逐图标签 / 比例 / payload 画像 |
| `ba_extract3.py` / `ba_dump4.py` | 官方剧本流式抽取（**保留 `#` 指令**，v2 会丢） | `ba_1600008_compact.txt`（109 条记录） |
| `ba_decode.py` / `ba_decode2.py` | 剧本哈希解码（BGName / Transition / Emotion / MemoryLobby） | 见下 |

**官方 1600008（春香羁绊剧情）实证**（`D:\myStuff\tools\Blue-Archive-Asset-Downloader\CN_Extracted\Table\ExcelDB\ScenarioScriptDBSchema.json`）：

- 结构：109 条记录 = 1 条 `#title` + 旁白 `#na` + 逐字文本 `#st` + 立绘指令 `#3;…`(含 `closeup`)
  + 4 个表态点（`SelectionGroup` 1/2、3/4、5/6、7/8；`[sN]` 台词槽 / `[nsN]` 动作槽）+ 6 处转场；
- **转场 = `Transition` + `BGName` + `#all;hide`**；`Transition 2482233134` = **fade out 2000ms
  / fade in 2000ms**；黑场 = **`BG_Black`（纯色图，非特效）**；
- **进入"记忆大厅"的确切序列**：记录 28 `Transition + BG_Black + #all;hide`（淡出到黑）→
  记录 29 `Transition + SpineBG_LobbyHaruka + BGMId=43 + #all;hide`（从黑淡入 L2D 记忆大厅）；
  交叉验证：`MemoryLobbyDBSchema` 中 `CharacterId 16000 → PrefabName LobbyHaruka`、`BGMId 43`；
- L2D 背景的几个哈希 = 同一 `SpineBG_LobbyHaruka` 的**不同动画态**（`Idle_01` / `Talk_01_M`…
  `Talk_05_M`）——即纪念段的"差分"是 **L2D 动画态**，而非立绘差分；
- 结尾：最后一句特写台词（`#3;closeup` + 害羞表情）→ 记录 109 `Transition + BG_Black + #all;hide`。

**背景资产库（2026-09-10 改版）**：`D:\myStuff\tempo\` —— `SDIR_*`(10) / `DIR_*`(210) /
`BG_*.jpg`(1115)；纯色在 `SDIR_Atmosphere\DIR_PureColor\`；实体表 `_place_entities.json`
（key→sdir/dir/name/region/keywords/files{day,night}，注意 **keywords 是 `|` 分隔的单个字符串**）
+ 审校表 `_place_review.json`（`active` = 是否进词表）；工具 `place_studio.py`。
（⚠️ 人工审核未完成 → 实现先沿用旧白名单，见 §5 状态注。）

**外部参照（机制来源）**：

| 来源 | 借用了什么 |
|---|---|
| Storyloom `docs/theory/bridge-mechanism.md`（本地 `D:\MYCODE\github\Storyloom`） | 桥接标记 + 缓冲区 + 不等式 `T_consume ≥ T_gen` + 三约束 + 交互边界 |
| Storyloom `docs/theory/asset-generation.md` | **素材"识别时刻 ≠ 展示时刻"**、需求位置权衡、**预声明**（本文 §10.4 的理论根） |
| [InfiPlot](https://github.com/zonghaoyuan/infiplot)（范式 D） | **块首 `<plan>` → `</plan>` 闭合即解锁图像管线**（与本文块首 `stage: art` 同构）；投机预生成（我们不用） |
| [Open Dungeon](https://github.com/newideas99/open-dungeon)（[image-generation.md](https://github.com/newideas99/open-dungeon/blob/main/docs/image-generation.md)） | "文本先流、图后插"（我们 memorial 结构性耦合，不可用；仅作对照） |
| 通用游戏工程 | placeholder → swap（对应"L2D 记忆大厅首屏"路线） |
