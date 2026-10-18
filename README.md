# Live2Be

在一个类微信的界面里和《蔚蓝档案》的学生聊天。聊得够久、羁绊够深，她会主动把你拉进一段
视觉小说；最关键的那一刻会生成立绘，存进回忆册。

**非官方的粉丝作品。** 与 NEXON Korea、NEXON Games、Yostar 及其关联公司没有任何关系，
未获授权或背书；**非商业** —— 不收费、不接广告、不接受捐赠。角色立绘与场景背景的版权归
原权利人所有。完整声明（含下架渠道）见 [NOTICE.md](NOTICE.md)。

## 你需要什么

| | |
|---|---|
| 系统 | Windows 10 / 11（x64） |
| 磁盘 | 约 300 MB |
| 网络 | 只有对话要联网 —— 立绘与背景已在包里，不联网也能看到画面 |
| 必需 | 一个 OpenAI 兼容的 **LLM API Key**（DeepSeek 等，自备，按 token 计费） |
| 可选 | 生图 API Key（只用于「纪念立绘」那一刻；没有就降级成纯文字） |

除了 API Key，没有别的前置条件：不用装 Python，不用装浏览器插件。

## 跑起来

1. 解压到**你自己有写权限**的目录（不要 `C:\Program Files` —— 程序要往同目录写数据）
2. 双击 `Live2Be.exe`。它会起一个本地服务，并打开一个没有地址栏的应用窗口
3. 点「**设 置**」填 API Key → 保存 → 返回主界面，点「**手机 MMT**」开始

也可以提前放 key：在 `Live2Be.exe` 同目录建一个 `.env`，写 `LLM_API_KEY=...`。

## 能玩什么

| 主界面按钮 | 是什么 |
|---|---|
| **手机 MMT** | 平时的聊天。她在手机里回你，会发多条消息、换表情，语气随关系变 |
| **回 放** | 回忆册：翻已经发生过的章节，只读重看 |
| **设 置** | API Key / 生图开关 / 文件位置 |
| **素 材** | 素材状态。完整版已自带全部素材；轻量版在这里一键下载 |
| **关闭服务** | 正经营业方式，见下 |

**羁绊剧情不需要你点**：聊到引擎判定"够了"（看羁绊值），她会主动把你拉进一段全屏视觉小说，
用选项推进。做完会记进回忆册。

## 怎么关

用主界面左下角的「**关闭服务**」。控制台里的 Ctrl+C 是**故意忽略**的 —— 防止手滑打断后台
正在做的记忆整理（半途中断会白花已经花掉的 token）。

真急就直接关掉那个控制台窗口。强杀是安全的，数据不会写坏（落盘分两阶段）。

## 你的东西在哪

全部在 `Live2Be.exe` 同级的几个普通文件夹里，**都能改、能换、能搬**：

| 目录 | 放什么 | 能自己改吗 |
|---|---|---|
| `assets/` | 立绘、背景、登录页图 | 能。加图换图都行；删掉只会降级，不报错 |
| `config/characters/` | 每个角色一个目录（六个文件） | 能，见下 |
| `config/settings/` | 世界观、地点表、人际关系、MMT 名单 | 能 |
| `data/` | 聊天记录、记忆、日志 —— **唯一真源** | 能看能复制，**别改**（append-only） |
| `.env` / `settings.toml` | key 与各项配置 | 能（也可以在「设 置」页改） |

想把素材放到别的盘（比如机械硬盘）：在 `settings.toml` 里写 `[paths]` 的 `assets = "D:/…"`，
**改完要重启**（路径是启动时读的）。

**加自己的角色**要动五处，缺一样就会在某个环节悄悄降级：

1. `config/characters/{角色}/` 六个文件：`profile` / `personality` / `knowledge` /
   `experience` / `typical` / `script`
2. 立绘：`assets/illustration/{角色}/default/`，里面要有 `emotions.yml`（表情词表）与 `spine/`
3. `config/settings/relation/interperson.yml`：她认识谁、能知道谁的多少
4. `config/settings/mmt_registry.toml`：在 MMT 列表里出不出现
5. 世界观 / 地点表（只有你要写新场景时才需要动）

## 常见问题

**窗口是空白的 / 灰的**
九成是「以管理员身份运行」了。别那么启动 —— 管理员进程开出来的浏览器带管理员令牌，之后
普通权限再启动就会撞 Windows 的 UIPI 规则。已经污染过（后台有管理员权限的浏览器）→
把它完全退出一次再双击。仍不行就用 `Live2Be.exe --no-browser`，把控制台里的地址自己贴进浏览器。

**聊天一直报错**
- 提示 API Key → 「设 置」里没填，或填的 key 没余额
- 提示超时 → 网络或代理；程序不会无限重试，一次失败就停下来告诉你
- 能连上但话很短、不换表情 → 换个更强的对话模型，或看控制台里的警告

**看不到立绘**
轻量版没下素材。进「素 材」页看缺多少、点安装。完整版不会出现这个。

**纪念立绘没出来**
生图要单独配 key（`[image]` 段）。没配或失败会**静默降级**成纯文字 —— 有意的，不让生图
耽误剧情。想彻底关掉：设置页取消勾选。

**数据会丢吗 / 怎么备份**
`data/` 是唯一真源，按世界线 + 角色分目录，全是纯文本（JSONL / JSON）。备份就是复制整个
`data/`。程序只往里追加，不改不删已有内容。

## 版权与免责

- **非官方**粉丝作品：与 NEXON Korea / NEXON Games / Yostar **无任何关系**，未获授权、
  认可或背书
- **非商业**：不收费、不接广告、不接受捐赠，不以任何方式通过本项目获利
- 角色立绘、场景背景、界面字体的版权归 **NEXON Games / Yostar** 及原权利人所有；本项目
  不主张任何权利，也**不是**素材的再分发渠道 —— 请勿把 `assets/` 单独抽出使用
- 角色卡、地点表、提示词与引擎代码是原创内容
- 权利人如需停止使用：见 [NOTICE.md](NOTICE.md) 的下架一节

## 从源码跑（macOS / Linux / 开发者）

**打包好的 exe 只有 Windows。** macOS 与 Linux 只能从源码跑 —— 这也是开发者的路径。

### 1. 环境

| | |
|---|---|
| Python | **3.12 或更高**（见 `pyproject.toml` 的 `requires-python`） |
| 系统 | macOS 12+ / 任意现代 Linux（Windows 同样适用，把 `python3.12` 换成 `py -3.12`） |
| Git | 只需要 clone 这一次 |

```bash
git clone https://github.com/fossfutfc-afk/Live2Be.git Live2Be
cd Live2Be
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # 只跑不测可以用 `pip install -e .`
```

`.[dev]` 装的是 pytest / ruff / networkx；`.[image]` 是纪念生图要的 Pillow —— 不装也行，
生图会自动退化成纯文字。

### 2. 放 key

```bash
echo 'LLM_API_KEY=sk-...' > .env    # 也可以启动后在「设 置」页填
```

### 3. 起服务

```bash
python -m webgui.serve             # → http://127.0.0.1:8000/ ，会自己开浏览器
```

这是**推荐**的启动方式：它负责端口占用检查、自动开浏览器，以及"Ctrl+C 被忽略、退出走前端
「关闭服务」"那一套保护。

只想要最裸的 FastAPI 进程（开发调试常用）：

```bash
uvicorn webgui.app:app --host 127.0.0.1 --port 8000
# 装了 fastapi[standard] 之后也可以：
fastapi dev webgui/app.py
```

这两条**绕过** `webgui.serve` 的外壳：不自动开浏览器，Ctrl+C 正常工作（也就少了"防手滑
打断后台记忆整理"的保护）。改前端时它们更顺手。

其他入口：

```bash
python main.py                     # 终端调试入口（功能是 Web 版的子集）
pwsh -File start.ps1               # 只在 Windows：顺带起本地 embedding 服务
```

### 4. 没有素材是正常的

`assets/` 不进版本库（版权原因），所以**刚 clone 下来一张图都没有**：登录页没有 logo 与背景、
MMT 列表没有头像、羁绊剧情里不出现角色（退化成纯文字）。

**但角色卡与世界观在 `config/` 里，是完整的** —— 聊天、记忆、剧情判定全都跑得起来。

想让画面出来，把文件按目录放进去就行（细节见 [guidance/CHARACTER.md](guidance/CHARACTER.md)）：

```
assets/illustration/{角色}/default/portrait/collection.png   # MMT 头像（一张 png 就够）
assets/illustration/{角色}/default/emotions.yml              # 表情词表
assets/background/…                                          # 背景（要在 place_entities.json 登记）
```

也可以把 Windows release 里的 `assets/` 整个拷过来。

### 5. 自检与打包

```bash
python -m setup_tool --check       # 体检：路径 / 角色卡 / 素材 / 数据 / LLM
python -m pytest tests/core        # 与 tests/llm tests/tui tests/webgui 分域跑（别塞一个进程）
pwsh packaging/build.ps1           # 打 exe（Windows；默认完整版 ≈267 MB，-Slim 出 ≈107 MB）
```

产物在 `dist/Live2Be/`。一个能跑的闭环是 **`Live2Be.exe` + `_internal/` + `assets/` + `config/`**
（onedir 的 exe 离不开 `_internal/`；`data/` 首次运行自建，`.env` 与 `Live2BeSetup.exe` 可选）。

**改代码前先读 [AGENTS.md](AGENTS.md)** —— 它是唯一活入口：分层、开发纪律、测试跑法、
以及踩过的坑。设计稿与执行记录在 `docs/`，它们**带日期、可能已漂移**，与代码冲突时信代码。
