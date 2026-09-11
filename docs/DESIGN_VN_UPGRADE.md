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
`text` 除 `stage:end` / `stage:exit` 外必填。**不存在 action 字段、不存在数组容器、不存在嵌套**。

**收尾组合技巧**（用户样例，`end` 的 text 是独立收尾字段而非台词）：
```jsonl
{"character": "sensei", "text": "你看那边，多漂亮啊"}
{"stage": "switch",   "text": "星空"}
{"stage": "end",      "text": ""}          ← 老师一句 + 空镜 + 黑屏退场
```
其余组合：角色末句 + 余韵 `end` 文本 / 角色末句 + `end: ""` 黑屏 / 收在纪念正文的最后一句。

| 字段 | 取值 | text 含义 | 位置约束 |
|---|---|---|---|
| `character` | 角色 id（**记录里写真实 id**，如 `igusa_haruka`；显示名/别名由引擎归一——决策 #21） | 台词（**不包「」**——说话人由字段表达，决策 #21） | 任意 |
| `character` | `sensei` | 老师台词：**每条 = 一个独立动作/一句话**；**最长连续 sensei 段 = 一个「群」，长度 1~3**；**群一律弹选项**（run=1 = 单选项、2~3 = 多选项，玩家挑一句说） | 任意（块内出现几次不限） |
| `character` | `narrator` | 叙述（旁白/舞台指示） | 任意 |
| `stage` | `switch` | **目标地点（自由文本，永不是资产键）** | 任意；**本章第一条必须是 switch**（交代开场景） |
| `stage` | `art` | **画面意向（1~2 句：谁/在哪/什么时刻/什么情绪；不写构图参数）** | **必须是本块第一条**；一章 ≤1；本块必须兑现 `memorial`（见 §7/§10.4） |
| `stage` | `memorial` | 触发句（可省） | **块内偏后**；**其后到块尾均为纪念区间**（§7） |
| `stage` | `end` | 收尾字段（**不是老师的话**；可留空 `""` = 直接黑屏收尾） | **本块最后一条** |
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
- **载体落地（P0-4a）**：`contract.records.VnBlock` = 记录数组 + 群 + 位置元数据；
  两个出口 = `to_dict()`（落库/回放 payload）与 `render_text()`（历史回灌/回放文本，
  **最小说话人形态**：`显示名：正文`，旁白无前缀，`art`/`exit` 跳过）。
  校验（`check_block`）只出**问题清单**，不拦不修；`VnRecord.line_no` 不参与相等性
  （记录身份 = kind/value/text）→ payload 往返稳定。
- **板切分落地（P0-4b，`_board_spans`）**：边界 = **换场点前** + **交互槽后**——
  即"**槽挂在板尾、角色的反应在下一板**"（玩家读完本板正文才看到选项；选中后下一板
  才是反应）。`art` 是**块级声明**，不参与切分（否则会切出一个纯声明的空板）；
  只含舞台信号的板（如连发两条 `switch`）**并进下一板的记录真源**（地点顺延，真源不丢）。
  超长群（>3）按上限**切槽**（软违规，不整块重发）。一次调用可派生多板 → 首板本次发，
  其余进**待发板队列**（`_pending_boards`），后续调用 **0 LLM** 领取（§10.4 桥的朴素形态）。

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
| `build_schema()` 作为唯一渲染入口 | 新增**第三种形态**：记录流 schema（与 MMT 的消息流并列）——落点 = 独立函数 `build_record_schema()`（**不进 `build_schema(registry)`**：记录文法不依赖动作注册表，参数是角色 id 与状态约束；盒子仍由 `schema` 块承载，标题可换「本轮输出契约」） |
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
| **辅助转义**（一级修复） | `text` 含未转义半角引号（**唯一真实错误源**）→ 按文法形状确定性重建：判别符前缀 + `text` 定界 + 正文恒在行尾 → 数据层重建走正常校验 → NOTE 记账。**不是通用 JSON 修复**：正文里任意个数/位置的字面 `"`、同时缺收尾引号与 `}`、中间夹多余字段都能救；救回文本逐字节等于模型原意。**护栏**：正文里出现 `"}{"` / `":"` / `","` 之类结构残留（模型把两条记录粘在一行）→ 不救，退回丢行（护栏失效时最多退回旧行为） | P0-2 `_rescape_repair` |
| 尾行悬空（二级修复） | 引擎补 `"}` 救回（EOF 处无歧义） | 同上 |
| 结构性错误 | 0（无括号/逗号/围栏/跨行记录问题） | 同上 |
| **不救**（丢行 + 计数） | 形状类不可救：双判别符 / 都无判别符 / 未知 stage / 空 text / 缺逗号 / `text` 非字符串 / `text` 不是最后字段（text-first 形状）——**不越界修复**（宁可丢行也不猜语义） | P0-2 |
| 失败分类 | ① 行级格式错 → **能救则救 + NOTE 计数**，不可救才丢行；② `finish=length` / `content` 空 → **独立计数 + 可重试**（非格式问题） | 探针 6/7 |
| 两遍式标注档位 | emotion/place `thinking=off`（既定铁律，探针 7 从反面验证） | `llm/task_levels.py` |
| **记录流真机（首次）** | 47 条 → 16.0s；55 条 → 27.9s（high 档）; **DROP 0 / NOTE 0 / 硬违规 0 / 软违规 0**；55 条切出 **10 板**（含 1 板 memorial + `art` 声明）；首个待发板续发 **0.00s** | `probe_vn_records_engine.py` |
| **记录流真机（文案纪律 #24 后）** | 49 条 → **17.3s**；**DROP 0 / NOTE 0 / 违规 0**；7 板 / 6 群 → **交互密度 每 8.2 条一次**（改前 5.5）；说话人取值 `{igusa_haruka: 32, sensei: 11, narrator: 3}` = **模型 100% 输出真实 id**（别名归一零触发）；**输出文本零「」**（改前会包「」）；盒B 11059 → **9435 字** | 同上 |
| **标注单元（P0-7b 定稿）** | v2 里标注单元 = **记录**（一板一组一次调用）: 旧"自然段"随记录流消失; 板 1~4 条 → 输入规模与旧"自然段 2~5 句"同量级; 板间 carry 链照旧（`_para_seq`/`_carry_emo`）。emotion/place 仍 `thinking=off` | `test_emotion_text.py`（迁移后语义） |
| `response_format` | 记录流**必须走 `text`**（`json_object` = 整回复单对象; 且客户端会 `json.loads` 成 dict → 被误判成旧动作分支）; 纪念子模式（memorial_exit）仍 `json_object` | P0-4b 真机踩坑 |
| 待发板收益 | 一次调用 = 一拍（~10 板），板间**零 LLM**；否则按旧"一板一调用"需 ~10×20s | `probe_vn_records_engine.py` |
| **渐进渲染真机** | 1381 chunks; **首个 chunk 12.1s（思考段 75%）、整块 16.2s（内容段 4.1s）**；板1 交付 **12.9s** → 首板提前 **3.3s** 可读（= 内容段的 81%）；板 2~6 在 13.5→16.2s 陆续交付。另一跑: 27.0s 总时长 / 首板 25.1s（内容段只占 2s, 思考段 23s+）| `probe_stream_gain.py` |
| **首屏等待构成** | = 思考段（10~23s, 占 60~90%）+ 首板内容段（~1~4s, 渐进渲染已吃掉 80%）; 预热命中/缓存/草稿三条 0 LLM 路径绕开整段 | 同上 |
| **换场翻译真机** | 7 例: 「放学后的天台」→ `school_rooftop`、「教室里」→ `class_room`、「基沃托斯的商业街」→ `gehenna_street`；「深夜的杂草屋」「黄昏，杂草屋门前的小巷」（词表无此项）与「某个地方」→ **MISS(keep)** ✓；单次 0.2~0.8s；重复句 **0.0s**（进程内缓存） | `probe_place_resolve.py` |

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
| **P0-2** | **行解析器**：`parse_line(text) → VnRecord \| ParseDiag`；`parse_stream(lines)` 批量；坏行丢弃 + 诊断聚合（行号/原因/致命性）+ **辅助转义/末行悬空两级修复**（经用户裁决：值得做且简单，NOT 通用 JSON 修复） | `contract/records.py` | 回归用例覆盖 §9 各类行：未转义引号（含多引号/同时悬空/夹多余字段）、**末行悬空补 `"}`**、数组行拍平、不可救形状仍丢行；391 行样本零致命误判 |
| **P0-3a** | **schema 渲染第三形态**：`build_record_schema(with_examples, char_id, char_display)` = 七种取值 + 转义规范 + 硬规则七条 + few-shot（**随会话角色渲染真实 id/显示名**，不再漏占位 `haruka`） | `contract/schema.py` | 单测：全取值/转义示范/群上限/可关示例/随会话渲染 |
| **P0-3b** | **文案与盒装配换代**：rules 重写为记录流（switch/群/memorial/art 预告/end/节奏/三份范本，含 `\"` 转义示范）；盒 B `schema` 块改 `build_record_schema`（标题「本轮输出契约（VN 记录流）」）；`place_palette` 措辞反转（**换场由 writer 发 switch**）；词表块按 writer 受众措辞；`task_bond.md` 换代 | `llm/prompts/bond_story_rules.md`、`task_bond.md`、`core/promptkit/{blocks,bond_story}.py`、`core/media/emotion_lexicon.py` | 夹具刷新 + 人工审 diff（mmt 夹具不动）；真机输出守形（照 probe5 口径统计）——真机验证随 P0-4b |
| **P0-4a** | **块载体** `VnBlock`：记录数组 + sensei 群 + 位置元数据（`switch_at`/`art_at`/`memorial_at`/`end_at`/`exit_at`）+ 前后切片 + 两种出口（`to_dict` 落库 / `render_text` 历史渲染，最小说话人形态） | `contract/records.py` | 单测：群/位置/切片、payload 往返稳定、`line_no` 不参与相等、修复与丢行进 notes、**旧契约 payload 显式拒绝** |
| **P0-4b** | **引擎接线**：`send_vn_scene` 字符串输出走**记录流**（`VnBlock` → 板派生 → 群/槽 → 待发板队列）；`BondScene` 持 `records`（真源）+ 派生 `paragraphs/choices`（过渡期喂老 renderer）; 别名归一 + 两级修复上线; `response_format` 切 text | `core/bond/bond_story.py`、`contract/records.py` | 单测 9 例（板切分/待发板 0 LLM/历史隔离/别名/辅助转义/硬违规重试/软违规切槽/art 不切空板/空板并记录）;**真机一场跑通**（见 §9） |
| **P0-5** | **槽与回录**：群 → `choices`（run=1 也弹）; 选中候选**物化**为单条 `sensei` 记录（替掉"（选择了: X）"）; 渲染唯一源 = `render_records`（未选候选不出现 + 裁决物化在群首）; `BondScene.from_dict` 显示层同步物化 + 派生段落带 `speaker` | `contract/records.py`、`core/session/renderer.py`、`core/bond/bond_story.py` | 单测: live 尾部 == 事件流渲染**逐字节**、未选候选不进任何视图/上下文、显示层物化插回群首 |
| **P0-6** | **落库 / 回放 / 存档**：板 payload = `{records(真源), paragraphs(派生), choices(派生), is_end, place_hint?/art_hint?/memorial?}`（webgui `_log_scene` 早已写 `scene.to_dict()`，无需改）; **旧档冻结**（无 records → 旧渲染/旧结构原样）; webgui 回放视图 `_narrativize` 补记录流分支（裁决行插回群首） | `core/session/*`、`webgui/bond.py` | 单测 7 例：payload 经 SessionStore 往返逐字节、回放 == live、恢复窗口 == live、旧档冻结、混合存档、坏 payload 降级、旧契约被 VnBlock 显式拒绝 |
| **P0-7a** | **消费者切到记录流 + 换场翻译最小版**：① `switch` 地点话 → 背景键（新 prompt `place_resolve.md` + `resolve_place()`，复用 `place` 档位，**进程内缓存**，失败 `[place][SWITCH] MISS(keep)`）; ② webgui: 记录流板**不 fork 候选/不预生成**（下一板已在引擎待发队列）、点选项 = **就地物化展示** `老师：X`（不生成, 不重建 scene_obj——保住标注就绪态）、点继续 = 0 LLM 领下一板; ③ API 边界注入 `speaker_name`（角色 id → 显示名, `sensei` → 老师, 旁白空）; ④ CLI: `render_scene` 画名字行 + `simulate_vn_scene(speaker_names=)`; ⑤ 前端: `.bond-speaker` 名字行（样式最简, 细节留后） | `core/bond/place_annotate.py`、`llm/prompts/place_resolve.md`、`webgui/{bond.py,routers/bond.py}`、`core/ui/vn_cli.py`、`renderer/{scene,cli}.py`、`webgui/static/{js/bond.js,css/bond.css}` | 单测: 翻译/缓存/keep 全路径、引擎 `scene.place` 就位、webgui 端到端（选项物化 + 待发板 0 LLM + 事件流带 records/picked + `speaker_name`） |
| **P0-7b** | **删过渡缝（默认严格）**：引擎默认**只吃记录流**——收到动作 JSON → 打回重发; 旧动作路径退居**显式开关**（`allow_legacy_action` / 环境变量 `LIVE2BE_VN_LEGACY_ACTION`, **默认关**; 仅存量测试桩与开发通道用）。新增严格性测试（默认拒 / 开关放行）。迁移示范: `test_emotion_text.py` 全量改记录流（连带语义更新: **标注单元 = 记录/板**, 见 §9） | `core/bond/bond_story.py`、`tests/conftest.py`、`tests/vn_fixtures.py`、`tests/core/test_emotion_text.py` | 默认拒/开关放行两路都有测试; 全量绿 |
| **P0-7c** | **存量测试桩迁移 —— 已完成** | ① 退役用例归档（`tests/archive/` 8 文件 + README, `norecursedirs` 不收集）; ② 其余全部迁到记录流: `test_emotion_text` / `test_vn_cli`（含 6 例流程: 单板节奏 + 脚本计数重算）/ `test_promptkit_baseline` / `test_record_picked` / `test_place_annotate` / `test_director` / `test_emotion_annotate` / `test_bond_abort` / `test_prewarm_cache` / `test_bond`（18 例, 经 `tests.vn_fixtures.from_v1_scene` 测试侧适配）; ③ **删除兼容开关与旧动作输入路径**（`LIVE2BE_VN_LEGACY_ACTION` / `allow_legacy_action` / dict→registry.parse 段）——收到动作 JSON 一律打回重发 | `core/bond/bond_story.py`、`tests/**` | 全量绿（**无开关**）+ 真机一场 ✓（59 条 / 违规 0 / 6 板 / 5 群 / 密度 11.8 条一次） |

**依赖关系**：P0-1/2/3 相互独立可并行 → P0-4 依赖三者 → P0-5 与 P0-6 可并行 → P0-7 收尾。

### 11.2 P1 — 标注单 lane + 换场翻译

| 步 | 做什么 | 完成标志 |
|---|---|---|
| P1-1 | 读**背景资产库导出视图**（`D:\myStuff\tempo\_place_entities.json`：key/中文名/keywords 别名/files.day-night；`_place_review.json` 的 `active` 过滤出词表）+ 引擎侧缓存 **（⚠️ 库的人工审核未完成 → 本期先沿用旧 `_director_whitelist.json`，切换时机见 §5 状态注）** | 表可加载、别名可查、`active=false` 不进词表、缺文件不炸 |
| P1-2 | `switch` → 翻译（**最小版已随 P0-7a 落地**: `resolve_place` + 进程内缓存 + keep 兜底**；本步补: 命中文件缓存 0 调用、固定带前后 2 行上下文、tempo 导出视图词表） | 开场景解析在首条记录闭合时即发起 |
| P1-3 | 解析缓存 `places_resolved.jsonl`（原文→键）+ `[place][MISS]` 日志（= 美术需求单） | 命中率可观测；miss 可 grep |
| P1-4 | 标注合并为**单 lane**（emo 逐行 + place 翻译）；板边界由锚点决定（前必切） | 双 lane 机制退役；背景切换内容驱动 |

### 11.3 P2 — 块式长输出

| 步 | 做什么 | 完成标志 |
|---|---|---|
| **P2-1 前置（已落地）** | **渐进渲染**: `BlockStreamParser`（chunk → 完整行 → 板闭合即产出）+ `send_vn_scene(on_board=…)` 回调 → webgui 首板即时落地（`_streamed` 标记防重复落地）。真机: 首板提前 **3.3s**（= 内容段 81%）; 思考段（10~23s）仍是主项 | `contract/records.py`、`core/bond/bond_story.py`、`webgui/bond.py` | 单测: 增量解析边界（行半截/超长群/丢行）+ 流中途交付 + 块未完成时 status 已有场景 |
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
| 20 | **未转义半角引号要不要"辅助转义"** | **要**：唯一真实错误源（2/391 行），且我们文法形状固定（判别符 + `text` 恒在最后、正文恒在行尾）→ 可做**确定性**再转义（约 30 行、可解释、可计数），成本远低于行级重发。红线：只救这一类；形状类错误**不越界修复**（宁可丢行也不猜语义），每次救回打 NOTE 计入日志以便观测真实频率 |
| 21 | **记录的两处取值/写法**（P0-3b 用户裁决） | ① 台词**不包「」**（说话人由 `character` 字段表达；（）只留给 `narrator` 记录）——记录里"谁在说"不表达两次；② `character` 取值 = **真实角色 id**（`igusa_haruka`）而非显示名：模型偶尔写「伊草 遥香/遥香/春香」时由**引擎归一兜底**（P0-4b 实现，单人模式下非 narrator/sensei 的记录一律归主角） |
| 22 | **P0-4b 过渡缝（旧动作通道保留一个节点）** | 引擎按**输出类型**分流: 字符串 = 记录流（真机路径）; **dict = 旧动作 JSON**（测试桩/开发通道——各 `ScriptedLLM` 仍返回 story_scene dict, 故 535 例存量测试保持绿）。缝上带 WARNING 语义与 `trace.action` 区分; **P0-7 迁移测试桩时删除该通道**（届时旧 registry.parse 只剩 memorial exit）。配套: 记录流板仍**派生** `paragraphs/choices` 喂老 renderer（消费者迁移同属 P0-7） |
| 23 | **板切分语义（真机校准）** | **槽挂板尾、反应在下一板**（不是"槽起新板"——否则角色的反应会在玩家选择前就显示出来）；`art` 不切板（块级声明）; 空板并记录; 超长群切槽。真机实证: 55 条 → 10 板, 说明模型把"老师每次开口"都写成了群（≈每 5 条一次交互）——**与用户样例（9 条 2 群）同量级**，密度引导见 #24⑥ |
| 24 | **文案纪律（2026-09-10 用户六条裁决）** | ① **不写"不要写 X 字段"式负面提醒**（白熊效应: 不说模型不知道，一说反而幻觉 + 废 token）——schema/rules 里的"不写地点键/情绪键/action/choices/branches"全部删除; ② **范例里不出现「」**，直接告诉模型写纯文本（rules 内 meta 引用改用 “ ”）; ③ 范例说话人**统一真实 id**（`igusa_haruka`，rules 用 `{char_id}` 占位由引擎按会话替换）; ④ `end` 的 `text` = **收尾字段（不是老师的话）且可留空** = 直接黑屏收尾（`TEXT_OPTIONAL_STAGES` 纳入 `end`），并在文案里给**收尾组合技巧**（角色末句+余韵／末句+黑屏／老师一句+空镜+黑屏／收在纪念里）; ⑤ **`lexicon_emotion` 退出盒B**（v2 里 emotion 由标注层逐记录挑，词表对创作无用 → 盒B 10 块降为 9 块，省 ~1.6k 字）; ⑥ 删重复（rules 的"格式硬性要求"节由输出契约段承担）并**降低交互密度**（引导"一段里老师开口 3~5 次"） |
| 25 | **渲染唯一源与说话人形态（P0-5）** | 历史/回放的叙事文本**只有一个**渲染源 = `render_bond_scene_text(payload)`：记录流板走 `render_records`（**说话人取记录里的值**——角色 = 真实 id、老师 = `老师`、旁白无前缀），旧契约板走原 paragraphs 提取（旧档冻结）。因为只看 payload、不看外部名字表：① **live 尾部 == resume/回放逐字节同形**（构造性成立，不靠约定）; ② 显示名替换属于 **UI 层**（P0-7）。裁决物化 = 群里一条 `sensei` 记录（`老师：X`），**落在群首**（老师原本开口处），未选候选在渲染层消失但 `records` 真源不动 |
| 26 | **换场翻译与消费者切分（P0-7a）** | ① `switch` 地点话 → 背景键 = **独立小 prompt + `place` 档位**（不复用"变更句标注"prompt：那是变更检测，对名词短语不可靠），进程内缓存（同句同地点 0 调用），失败/词表外/与当前相同 → `[place][SWITCH] MISS(keep)`（日志即美术需求单）; ② webgui 记录流板**不 fork 候选、不预生成**（下一板已在引擎待发队列, 且避免 `_last_payload` 被预生成板顶掉的回录错位）; ③ 点选项 = **就地物化展示**（不生成, 且**不重建 scene_obj**——重建会丢掉标注就绪态, 推进门控永远等一个不回来的标注, 真机测试踩到）; ④ `speaker_name` 在 **API 边界**注入（payload 里只有 `speaker` 记录值） |
| 27 | **旧动作通道的处理（P0-7b 拍板 → P0-7c 收尾）** | 一次删缝 = 73 例语义重写（13 文件, 其中 45 例是分支/纪念/候选等**已退役机制**的用例）→ 风险与收益不成比例。分两步: ① P0-7b **默认严格**（返回动作 JSON 即打回重发）+ 旧路径退居**显式开关**（`LIVE2BE_VN_LEGACY_ACTION`）; ② P0-7c 存量桩迁完后**开关与旧动作输入路径已删除**——现在唯一形态 = 记录流, 收到 dict 一律 feedback 重发。**标注单元同时定为"记录"**（板内一组一次调用）——旧"自然段"概念随记录流消失。旧动作层模块（`bond_actions`/`bond_executor`/`memorial_actions`）留在库内但**主链不可达**（旧档回放由 `render_bond_scene_text` 旧分支承担, 冻结不改） |

| 28 | **预热三层在记录流下的语义（P0-7c 修正, 用户追问触发）** | ① **入口预热 / 跨重启缓存**（`soul/prewarm.json`）不变: 存 `scene.to_dict()`（含 records）, 新鲜判据 = mmt anchor seq, 命中后注入引擎历史与 `_last_payload`; ② **会话内预生成（桥）**: `_generate` 的 finally 对"无槽未收尾"板统一预生成（含记录流板——待发队列有货则 0 LLM 领出, 队列空则后台真生成 = **块边界桥**）; 预生成被消费后的**链式预生成**此前对记录流板被整体跳过（链在第二板断）→ 已修正为"无槽板照常接链"; **裁决后立即预生成**（必须在 `record_picked` 之后——请求历史要含物化裁决行）→ 反应板立刻领出或下一拍后台生成; 有槽板不预生成（裁决先落）; ③ **候选 fork 退役**: 记录流板不再 `_spawn_candidates`（后继板已在待发队列, fork 只是白复制）。**④ 草稿旁路（选项 b 落地, 2026-09-10）**: "已生成未播放"的内容（当前未落库板 + 引擎待发板 + 预生成板）落 `soul/bond_draft.json`（非真源, 裁决才落库）——新鲜判据 = **同一 vn_enter 段 + 其后无新 bond 事件**; 重进时①无已落库板 → 恢复待发队列（首板由 prewarm 首场缓存/正常生成给出）, ②有已落库板 → 回放交棒处 `_draft_adopt` 直接接上（当前板 + 队列）; 续播的板**正常进事件流**（它们此前从未落库）; finish/过期/换段即删 |

| 29 | **记录流的旁路一致性（用户四问核实后的补丁）** | ① **回放器**: 事件 payload 保留 `records`, `BondScene.from_dict` 读得到, `_resolve_scene` 在 API 边界注入 `speaker_name`（`/api/bond/status` 与 `/api/bond/replay` 早已过；**`/api/bond/turn` 的裁决直返此前漏了** → 已补）; 中断前缀回放走 `_narrativize`（裁决物化进段落）。② **滑动窗口**: 单元 = 渲染文本行数, v2 一条记录一行 → 口径不变, 无需改; 但 `render_timeline`（digest 输入）此前只读 paragraphs → 已补 `老师: {picked}` 行。③ **首场等待构成** 与 ④ **渲染策略（当时=非真流式）** 的核实结论 → 结论直接催生了决策 #30 |
| 30 | **渐进渲染（用户拍板先做流式; P2-1 前置落地）** | 记录流**行分隔** → chunk 里出现换行即可解析那一行: `BlockStreamParser` 逐行喂入、按与批式同源的规则增量切板（槽挂板尾需**一行前瞻**; 换场前切; 超长群切槽; `art` 块级声明不入板）, 板一闭合就 `on_board` 回调交付; 流式交付过的板不再重复解析/落地（`_streamed` 标记）; 流式下"硬违规"无法回滚（板已在屏上）→ 只 trace/日志, 不打回重发。**真机收益**: 首板提前 3.3s（= 内容段 81%）; 瓶颈转移到**思考段**（10~23s, 占 60~90%）——那属于 reasoning 档位与预热策略, 不是渲染问题。**不需要 SSE**（chunk 本就在客户端侧） |
| 31 | **流程落库绑定 store（2026-09-11 真机事故后的根治）** | **事故**: 渐进渲染测试的生成线程活过了 `_cleanup()` 的 store 恢复, 线程后续的 `_log_scene_meta` / `_prewarm_cache_save` / `_draft_save` 读的是**全局** `chat._store` → 把 `vn_state` marker 写进真实 `events.jsonl`（多出 seq 31~33 + 一份假首场 `prewarm.json`/`bond_draft.json`）。**根因**: 长流程（后台线程）的生命周期可能跨过调用方的 store 切换（测试注入 / 多开 / 重启）——"写入时再读全局"必然写错世界线。**修法**: store 在 `_state()` **创建流程状态时绑定**到 `BondState.store`, 流程内一切读写改走 `_flow_store(state)`（`_log_scene`/`_log_scene_meta`/`_prewarm_cache_*`/`_draft_*`/`_last_mmt_seq`/`_last_bond_seq`/`_open_vn_seq`/`enter_vn`/窗口灌入/废弃宣告）; 辅助函数新增可选 `store=` 参数（缺省回落全局, 单测可直接调）。附带: 测试收尾**先等生成线程落定再摘 store**（原 `finally` 顺序本身就是事故触发条件）+ 一条回归用例（生成在途切走全局 store → 断言落库进绑定 store、切换后的 store 零沾、真实 `events.jsonl` 逐字节未变） |
| 32 | **真机三处体验缺陷修复（2026-09-11 用户走查报障）** | ① **"第一段剧情出现两遍才进第二段"**: 裁决后 `bond_turn` 返回的是**完整物化板**（板正文 + 老师那句）, 而前端 `renderScene` 永远**从头逐段渲染**（点击推进制 + 逐段替换渲染）→ 已读过的板正文被重播一遍。修法: 裁决返回改**增量**（`_display_delta`: 只回新出现的"老师那句", 背景/records 等载体照旧带上, 前端渲染路径不变）; 完整物化板仍是 `state.scene`（status/回放视图不变, live 与回放同形不受影响）——**该半修在 #33② 被纠正: 展示视图也换成增量**。**这与缓存无关**——缓存（首场 prewarm/草稿旁路）给的是"还没播过的板"。② **标题屏只有四个大字"羁绊剧情"**: 标题屏文案取 `/api/bond/start` 的 `chapter_title`, 而 **adopt 就绪**（预热已完成 → 点击，真机最常见路径）与 busy_wait / 并发 skip 三个返回路径**漏带该字段** → 前端兜底 `title \|\| "羁绊剧情"`。修法: 新增 `_enter_title(state, char_id, session_id)` 统一兜底（state → 内存 trace → **事件流** `mmt_trigger_bond_story.chapter_title`, 进程重启也能补）, 所有进入返回路径一律带上; `bond_status` 也新增 `chapter_title`（重进/刷新/回放都能拿到）。③ **正文区重复的红字角色名**: 记录流 v2 的 `speaker_name` 名字行在"当前角色自己说话"时与左上**名字牌**（`#bond-name` + `#bond-club`，随当前角色变动的两个字段）重复。修法: 前端 `_isOnStageSpeaker()` 判定（空白归一化比对 `name` 与名字牌文本）——**同人则不画名字行**, 只有老师/其他角色才画（老师那句仍需名字行区分）。回归保护: 浏览器冒烟（B 层）新增三条断言——标题屏含章节名、名字牌两字段非空、裁决后不得重播板正文; 两处修复各做过**变异验证**（打回修复前 → 冒烟必红） |
| 33 | **真机第二轮报障四修（2026-09-11 傍晚）** | ① **"重进先黑屏 + 等一小段"**: 后端回放路径实测 **~0.1s**（纯读事件流）, 慢在前端——黑底标题屏（`showTitle(title, "")`）+ 先等一轮 status 轮询（700ms 起）+ `await initSpine()`（spine 包加载）全在首帧之前。修法: `bond_start` / 回放推进 / 预生成消费**把就绪场景一起回**（`_ready_scene_payload`: scene+round+emo_version+**name/club**）, 前端拿到即 `renderScene`（回放不播章节卡、其余在**场景自己的背景**上播）; `initSpine()` 改并行不阻塞首帧。② **"继续轮又看到老师 + 打搅了"**: 上一轮只改了返回值, `state.scene` 仍是完整物化板 → 前端任何一次 status 重渲染（round 在生成**开始**就 +1, 此时 scene 还是上一场）都会重播旧内容。修法: **展示视图也换增量** + 前端加**场景内容指纹去重**（`sceneKey`, 同内容绝不重渲染）。③ **"已等待 110s"**: 前端 `waitTurnIdle` 硬等 7min 且只显示一个数字; 后端在异常路径下（标注 lane 不再回来 / 生成线程丢失）`busy|gate` 可以永久为真。修法: **后端看门狗**（`BUSY_WATCHDOG_MS` 忙态+线程丢失→复位; `GATE_WATCHDOG_MS` 视觉门+lane 空闲→`_fallback_fill` 强制就绪; `PREGEN_GATE_WATCHDOG_MS` 预生成消费门同理）——"宁缺勿错: 表情精度换能推进"; **推进被拒留痕**（`bond_turn 被拒 reason=… 第 N 次` WARNING + 成功时汇总 INFO, 下次这类事故 diag 一眼可查）; 前端加**软上限 90s** 并显示卡在哪（生成中/标注中）。④ **测试污染真机数据（第二次）**: 冒烟走登录取名 → `mmt_preset.PLAYER_JSON`（真实 `data/basic/player.json`）被写成"老师"（用户报"填名字总在后面追加老师"的直接原因）; MMT 引擎的 `BondProgress()` 也没跟 store 走 → haruka 轮数被刷到 4550。修法: 引擎**跟随 store 的数据根**（`BondProgress(store.data_root)`）+ `BondProgress.__init__` 默认值改为**调用时解析**（默认参数原来在定义时就绑死了, 重定向无效）+ 冒烟桩世界重定向 `PLAYER_JSON` + `tests/conftest.py` 会话级兜底（连"显式传真实 data 根"的调用也重定向）+ 登录框改为**预填即全选**（打字 = 替换, 不再是追加）。真机文件已恢复（玩家名 `foss`; haruka 轮数 4550 → 12）; **⑤ 用户第二轮反馈补修（同日）**: "红字老师仍在, 且只在有继续按钮的节点出现"——那正是**玩家自己选的那句**（裁决物化 + 纯叙事场 → 显示"▼继续"）, 我上一轮只去掉了"当前角色"的重复名字行, 保留了老师那行。定稿规则改为: 正文区名字行**只在 speaker 是"别的角色"时画**（当前角色看名字牌; 老师=玩家自己选的话不画）——`.bond-speaker` 与数据仍在, 想改回一种样式只改这一处。同时把"卡在哪"彻底暴露出来（上一轮只加了兜底、没查清原因）: `bond_status` 新增 `gate_emo` / `gate_place` / `busy_ms` / `pregen_wait` 四字段, 前端等待文案直接写"生成中·12s / 表情标注中 / 换场判定中 / 下一板标注中"并 dbg 留现场——下次同类报障一次快照即可定位 |
| 34 | **收尾板只显示第一段就退出 VN + 收尾话要切页才出现（2026-09-11 真机第三轮）** | ① **"最后一段只看到第一句（outburst）就退出 VN 了"**: `onClick` / 继续三角写成 `if (sceneIsEnd) finish(); else advance();` —— **is_end 板点一下就结束整章**, 于是最后一板第 2 段之后的正文（真机那块有 7 段）永远读不到。is_end 的语义是"没有下一板", 不是"没有下一段"。修法: 统一 `advanceOrFinish()` —— 先 `_moreParas()` 逐段读完, 段尾才 finish（收尾仍由 `showInteraction` 的 is_end 分支 + 1.6s 自动 finish 承担）。**这条是最伤的一个**: 每章的情绪高潮段都被吞掉, 用户还以为"AI 写得不好"。② **"finish 后收尾话要切页/重进才看得到"**: wrapup 跑在 bond 自己的线程里（不走 chat 的 `_worker`）→ 前端 `pollLoop` 在 VN 退出后第一轮就看见 `running: false` → **停止轮询**（旧代码连 `bond_story` 标记也刚被 pop 掉）→ 收尾气泡要等切页时 `since=0` 全量才拉出来。修法: `chat.task_begin/task_end`（外部流程占/放 MMT 任务位, `_wrapup` 包一层 finally 必放）+ 前端 `resumePolling` 带 **25s 宽限窗口**（窗口内即使 running=false 也继续轮询并显示"对方正在输入…"）。回归: 冒烟桩块的收尾板改成**多段**并断言"收尾一/二/三都读到"（变异验证: 打回旧语义 → 冒烟立刻报"收尾板段落没读完"）; 新增断言"收尾话未切页即冒泡"; A 层 +1 用例（wrapup 期间 task busy 必须为真、结束必须释放） |

**残留未决（真未定）**：
- `art` 意向文本的长度上限（现定"意向级 1~2 句"，是否设硬上限）；
- 说话人分辨的 **UI 形态**（名字/颜色/气泡——#8 的落地形态，属 P0 渲染层升级）；
- 生图 **p50/p90 采样**与闸门命中率实测（待"规模定了"再测）。

> 待发板持久化（原 #28 开口）**已定并落地 = 选项 (b)**: `soul/bond_draft.json` 草稿旁路
> （见决策 #28④）；"限制预生成提前量"（选项 c）暂不做——先观测量级。

---

## 14. 附录：探针档案与官方实证（`.testtmp/`，不提交）

| 文件 | 用途 | 关键产出 |
|---|---|---|
| `jsonl_probe.py` / `probe2.py` | JSONL vs 单文档 JSON 出错率（温和/加硬） | 温和双 100%；加硬 JSONL 行好率 98.5% |
| `probe3.py` | 坏行抓现行 + 原始留存（`probe_raw/`） | 3/391 行坏：2 未转义引号 + 1 末行悬空 |
| `probe4.py` | 字段命名对照（speaker/who/actor/kind × narr/@前缀） | 命名不影响守约；`kind` 产出缩水；`@` 前缀最稳 |
| `probe5.py` / `probe6.py` | 单字段 vs 两分法（× end/memorial 变体） | 两分法 0 违规、产出最高；"尾条失败"实为空响应 |
| `probe7.py` | 空响应归因 | thinking 与正文共享 `max_tokens`（2048 → content 全空） |
| `probe_vn_records_engine.py` | **记录流引擎端到端**（P0-4b 真机验收） | 47 条/16.0s、55 条/27.9s，DROP 0、违规 0；55 条 → 10 板（1 板含 memorial + art 声明）；待发板续发 0.00s；**`json_object` 会把 JSONL 解析成 dict** → 记录流必须 `text` |
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
