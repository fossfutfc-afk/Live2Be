# Live2Be IDE — 使用手册

Live2Be IDE 是角色资料撰写助手：用自然语言告诉 AI 要做什么，AI 自己查资料、生成 YAML、经你批准后写入 `config/characters/`。

---

## 一、快速开始（双击）

打开 `entrance/` 目录，双击：

| 双击 | 作用 |
|---|---|
| `IDE_GUI.bat` | 图形界面（真实 LLM，需 API key）→ 自动打开浏览器 |
| `IDE_GUI_mock.bat` | 图形界面（mock 模式，无需 API，演示/上手用） |
| `IDE_CLI.bat` | 命令行界面（真实 LLM） |

**建议首次**：先双击 `IDE_GUI_mock.bat` 跑通流程（不花 API）；配好 API key 后再用 `IDE_GUI.bat`。

窗口操作：**关闭服务窗口 = 停止服务**。端口被占用时改 `WEB_PORT`（见「常见问题」）。

> 本目录是统一入口。未来 MMT（MomoTalk）等界面上线后，同样在这里加 `MMT_*.bat` 即可。

---

## 二、五件套与 interperson 简述

每个角色一个目录 `config/characters/{角色id}/`，放五个 YAML 文件（**五件套**，IDE 产出）
＋ 一个可选的**扮演手册** `script.yml`（作者手写，IDE 不产出），按"信息深度"分层：

| 文件 | 层级 | 内容 |
|---|---|---|
| `profile.yml` | L1 最表层 | 外貌、年龄、学校、社团、公开形象（信息密度最高） |
| `personality.yml` | L2 行为逻辑 | 性格、说话风格、行为模式 |
| `knowledge.yml` | L3 独有知识 | 认识谁、技能、重要物品、敌对势力 |
| `experience.yml` | L4 预设经历 | 与玩家的过往经历（→ Virtual Brain 初始化） |
| `typical.yml` | L5 校准样本 | 口头禅、说话方式、Q&A 范例 |
| `script.yml` | 扮演手册（2026-09 新增） | `SIG~main_tone` 剧情基调 / `SIG~mmt_tone` MMT 风格 / `SIG~bond_tone` 羁绊剧情建议——运行时注入各域 system prompt（缺省不注入） |

另有一个**关系表**（不在角色目录里）：`config/settings/relation/interperson.json`，记录角色之间"认识多深"（权重 = 熟悉程度 = 访问层级）：

| 权重 | 含义 | 能读到对方 |
|---|---|---|
| **1** | 萍水相逢 | 只见 profile |
| **2** | 社团成员/队友 | profile + personality（**社团成员默认 2**） |
| **3** | 故知/青梅竹马/老对手 | 再加 experience（很难达到） |

---

## 三、必要字段（REQ~）与重要字段（SIG~）

`REQ~` / `SIG~` 是 **YAML 键的字面前缀**——直接写进 key，不是概念标记：

```yaml
REQ~most_called_name: 伊草 遥香
SIG~age: 15
school: 格黑娜学园
```

### REQ~ 必填（缺失 → 角色加载失败）

`profile.yml` 里必填：
- `REQ~most_called_name` — 界面显示名（**代码级必需**，必须非空）
- `REQ~is_official_character` — 是否官方角色
- `REQ~gender` — 性别
- `REQ~introduction` — 3-6 句简介

### SIG~ 重要（决定信息完整度）

SIG 字段构成角色核心形象。**SIG 太少 → 完整度低 → 运行期角色扮演 AI 会自动补资料，可能与你写的档案冲突**，所以尽量写满。各文件关键 SIG：

| 文件 | 关键 SIG |
|---|---|
| `profile.yml` | `age`、`birthday`、`height`、`interest`、`club`、`dress` |
| `personality.yml` | `brief_traits`、`detailed_personality` |
| `knowledge.yml` | `friends`、`technique`、`possession` |
| `experience.yml` | `self` |
| `typical.yml` | `frequent_phrases` |
| `script.yml` | `SIG~main_tone`、`SIG~mmt_tone`、`SIG~bond_tone`（作者手写） |

- **无前缀字段**：普通字段，可选但推荐填写（如 `en_name`、`school`、`halo`、`behavior`）
- **`null`**：合法占位（该板块暂缺）
- 写完后用 `/view <角色>/<文件>` 查看完整度，缺失字段会直接列出

---

## 四、使用方法

### 图形界面（GUI）

1. 双击 `IDE_GUI.bat` → 浏览器自动打开 `http://127.0.0.1:8000/`
2. 底部输入框用自然语言提需求，回车发送
3. 流程：AI 思考中 → AI 提议（含 diff）→ 你点「批准 / 拒绝 / 中止」→ 执行 → 完成
4. 顶部「自动批准」开关：开启后提议会在 N 秒后自动批准（纯演示/测试推荐）

### 命令行（CLI）

双击 `IDE_CLI.bat`，或手动：

```bash
cd /d/MYCODE/Live2Be
conda activate live2be
python -m ide.ide_agent
```

### 工作流

```
用户输入 → AI 判断动作
  写动作(创建/修改/关系) → 展示 diff → 批准(y)/拒绝(n)/中止(q) → 落盘
  查资料(search/fetch_url) → 结果回灌给 AI → 继续
  done → 收尾, 控制权交回你
```

要点：
- **创建/修改角色时**，AI 会**按文件**问「是否读取该文件的高质量范例板块（伊草遥香）」，读取后写作质量更高。三个选项：`读取`（本次注入该板块）/ `跳过`（下次写该文件还会再问）/ `不再询问`（本会话不再问该文件）
- **补全 / 完善已有角色**：对 AI 说「补全这个角色 / 把剩下的写完 / 看看还缺什么」，AI 会**先查看现状**（五件套哪些已存在、缺失，profile 完整度），然后只补**缺失**的文件（一次一个文件，不重复已有内容）
- **改 / 补关系**：对 AI 说「给 XX 补个和 YY 的关系」，AI 会先 `view_interperson` 看现状，再以**全量快照**提交（自动带上想保留的现有关系）；新增关系会要求你确认资料/需求依据
- **官方角色**：AI 先查萌娘百科再写，不凭记忆编造；**原创角色（OC）**：依据你的描述，内容合理构建
- **范围由你决定**：只说「把遥香的生日改成 5/13」就只改那一个字段；说「完整建档」才写全五件套+关系；范围含糊时 AI 会先问你

---

## 五、命令（本地命令，不走 AI）

在输入框（GUI）或命令行（CLI）直接输入：

| 命令 | 作用 |
|---|---|
| `/view <角色>` | 列出该角色的五件套清单 |
| `/view <角色>/<文件>` | 展示该文件全文 + SIG 完整度 + 缺失字段 |
| `/edit <角色>/<文件> 键: 值` | 直接改某个 YAML 字段（先展示 diff，批准后写入） |
| `/exit` | 退出 CLI |

示例：

```
/view igusa_haruka
/view igusa_haruka/profile.yml
/edit igusa_haruka/profile.yml SIG~age: 16
```

GUI 里 `/edit` 可以只写 `/edit <角色>/<文件>`，会弹出粘贴框让你输入多行 YAML 补丁。

---

## 六、mock 模式

`IDE_MOCK=1` 时用内置 StubLLM：不调 API、落盘到临时目录、不碰真实配置，可反复演示完整流程（思考 → 提议 → 审批 → 执行 → 完成）。

- 双击 `IDE_GUI_mock.bat` 即可
- 或命令行：`set IDE_MOCK=1` 后 `python -m web`

---

## 七、常用动作清单

| 动作 | 说明 | 审批 |
|---|---|---|
| `create_character` | 新建角色（至少 profile.yml） | 需批准 |
| `update_character` | 改角色（merge 字段级合并 / overwrite 覆盖） | 需批准 |
| `update_interperson` | 改人际关系（全量快照替换） | 需批准 |
| `search` | 搜资料页 URL（默认萌娘百科；别名/繁体字自动处理，自动用已建角色 profile 的别名重试；新角色可传 `aliases` 一次提交多个候选词） | 直接执行 |
| `fetch_url` | 抓网页资料（结果回灌给 AI） | 直接执行 |
| `view_character` | 查看角色现状（五件套清单 / 单文件全文 + 完整度），供「补全」决策 | 直接执行 |
| `view_interperson` | 查看关系现状（全部角色清单 / 单角色完整关系），供「改关系」决策 | 直接执行 |
| `done` | 收尾 / 等待用户 | — |

---

## 八、常见问题

- **浏览器打不开 / 连不上**：确认服务窗口还开着（关了 = 停了）；手动访问 `http://127.0.0.1:8000/`
- **端口 8000 被占用**：改环境变量 `WEB_PORT`（如 8123），并同步改 `IDE_GUI.bat` 里的网址
- **报「LLM 调用失败」**：检查项目根 `.env` 里的 `LLM_API_KEY` / `LLM_BASE_URL`；IDE agent 的模型可用 `IDE_LLM_MODEL` 覆盖（默认 `deepseek-v4-flash`，**推理模型必须配大 max_tokens**，内置 16384，勿改小）
- **AI 编造资料**：官方角色应查资料后写、OC 靠你的描述；发现编造可在审批时「拒绝」并要求重写
- **写了五个文件还是提示完整度低**：`/view <角色>/<文件>` 看缺失的 SIG 字段，逐个补上

---

## 目录速查

```
Live2Be/
├── entrance/                                ← 本手册 + 双击启动脚本
├── config/characters/{角色id}/               ← 五件套 YAML（AI 写到这里）
├── config/settings/relation/interperson.json ← 关系权重表
├── ide/                                     ← IDE agent 引擎（命令层/动作/提示词）
├── web/                                     ← GUI 服务（FastAPI + 单页前端）
├── core/                                    ← 核心引擎（含 parsing 解析层 / ui 展示层 / mmt 动作化工作区）
├── contract/                                ← 动作契约（字段白名单/校验）
└── data/                                    ← 运行时数据
```
