# 打包（exe）

目标：双击能跑。**onedir**（不是单文件 exe）—— 启动快、杀软误报少，代价是一个目录。

## 一键

```powershell
C:\Users\johnf\miniconda3\envs\live2be\python.exe -m pip install pyinstaller   # 只需一次
pwsh -File packaging/build.ps1
```

**执行策略拦下 `.\build.ps1` 的话**（`is not digitally signed. You cannot run this script on
the current system`）：那是 PowerShell 的**执行策略**（`AllSigned`，或文件带"从网上下载"
的标记 + `RemoteSigned`），不是脚本坏了。两条出路：

```powershell
packaging\build.cmd            # ① 推荐：内部就是 pwsh -ExecutionPolicy Bypass -File build.ps1
pwsh -ExecutionPolicy Bypass -File packaging\build.ps1    # ② 等价的一条命令
```

`Bypass` 只对**那一次调用**生效，不改系统、不改用户策略。

产物在 `dist/Live2Be/`：

```
Live2Be.exe
Live2BeSetup.exe   资源配置助手（onefile，可以单独双击；见 setup_tool/.md）
_internal/         代码 + 前端静态页 + 三处 prompts（RESOURCE_ROOT，只读）
config/            角色卡 / 世界观（CONFIG_ROOT；程序不写，用户可改）
assets/            素材（ASSETS_ROOT；普通文件夹，可加可换可删，见下节两种口径）
data/              首次运行自动创建（DATA_ROOT）
.env/settings.toml 首次运行前填 LLM key（APP_ROOT）
```

### 配置助手（`Live2BeSetup.exe`）

和主程序放同一目录就共用同一份 `settings.toml` / `config` / `assets` / `data`。
六个按钮：重新体检 · 选素材目录 · 选角色卡目录 · 选数据目录 · 打开数据目录 · 清空 `[paths]`。
也可以纯控制台跑：`Live2BeSetup.exe --check`（有"问题"项时退出码 1，适合脚本）。

**轻量版（`-Slim`）的包会让它报"有角色卡但没有立绘"和"地点表声明的背景文件缺 N/435"，都是有意的**：
那个口径不带图（见下节）。这两个数字正是"用户拿到包会看到什么降级"的答案 ——
也可以拿它当"我还缺多少素材"的清单。

`infra/paths.py` 的五个根就是按这个形状写的：冻结后 `APP_ROOT = exe 同级`、
`RESOURCE_ROOT = sys._MEIPASS`；`CONFIG/ASSETS/DATA` 还能被 `settings.toml` 的 `[paths]` 覆盖。

## 素材：两种口径，同一份落盘形状

全量 `assets/` 是 **448 MB**（background 251 · illustration 177 · menu 18）。但**产品真正读的只有
159 MB** —— 差的 289 MB 是产品根本不看的东西：

| 不带 | 为什么 | 省 |
|---|---|---|
| 角色 `diff/` | 只有 `cli/` 的 `play_diff()` 读它；web 壳走 `spine/`（骨骼）+ `portrait/`（头像）。`catalog._scan_character` 在 diff 缺文件时 `static_path=None`、spine 照给（`tests/core/test_media.py` 有断言） | 119 MB |
| 背景里没被地点表引用的 663 张 | 表里 `files` 声明的 435 张才是引擎会引用的；其余是死料 | 151 MB |
| 角色 `ref/` | 只有纪念生图那一路用它，缺了降级纯文本 | 16 MB |

于是两种口径（`packaging/collect_assets.py --mode full|minimal`）：

| 口径 | 开关 | 带什么 | 体积 |
|---|---|---|---|
| **完整版**（默认） | `build.ps1` | 四角色 `spine/`+`portrait/`（含变装）、435 张背景、登录页三件 | **159.7 MB / 569 文件** |
| **轻量版** | `build.ps1 -Slim` | 只带"少了就报错或破相"的: 每个角色的 `emotions.yml`（词表进 prompt）、`menu/{logo,default}`、director 白名单 | 0.4 MB / 11 文件 |

完整版**断网可玩、零配置**；轻量版要靠「设置 → 素材状态 / 修复」按需下载（见下）。

### 素材是普通文件夹，不是只读资源

`assets/` 落在 **exe 同级**（`APP_ROOT/assets`），`_internal/` 里只有代码与前端。所以用户可以：

- 加自己的背景：丢进 `assets/background/`，在 `config/settings/world/place_entities.json` 加一条
- 换掉某张图：覆盖同名文件
- 写自己的角色卡：`config/characters/{id}/` 加六个文件
- 搬到别的盘：`settings.toml` 的 `[paths] assets = "D:/…"`
- 删掉不想要的：直接删，缺图只降级不报错

**升级时的纪律（安装器与手写覆盖安装都要守）**：`config/` 与 `assets/` 用**只补缺、不覆盖**，
`data/` 永不触碰。否则用户写好的角色卡会被一次升级扬了 —— 那比"不能改"更糟。

## 轻量版的素材包：切包 + 首次运行下载

`-Slim` 版把图改成按需下载。打包机上跑一次（约 30 秒）：

```powershell
C:\Users\johnf\miniconda3\envs\live2be\python.exe packaging/make_packs.py --dst dist/packs
```

| 包 | 内容 | 约 |
|---|---|---|
| `char.<id>` | `illustration/<id>/default/`（差分 + 头像 + spine + emotions.yml） | 18–47 MB |
| `char.<id>.ref` | `ref/`（纪念生图的参考图） | 16 MB |
| `char.<id>.outfits` | 其余外观目录（dress / newyear / suit / possession） | 14 MB |
| `bg.place_table` | 地点表 `files` 声明的**每一张**背景 | 100 MB |
| `menu.vol2` | 登录页轮播图 | 17 MB |

（切包这一路仍按旧口径切，包含 `diff/`；轻量版用户多半也不跑 CLI，若要压到最小，
把 `make_packs.py` 里角色包的目录范围改成和 `collect_assets` 的 `full` 一致即可。）

产物是 zip + `manifest.json`（含每包的 sha256、字节数、**每个文件的相对路径与大小**）。

**② 下载**：把 `dist/packs/` 传到任意静态托管（对象存储、GitHub Release、局域网
`python -m http.server`），把 `manifest.json` 的地址填进「设置 → 素材状态 / 修复」。

- 装没装**只看磁盘**：运行时逐个 stat 清单里的文件，不写状态文件 —— 手动删两张图，
  状态立刻变"部分"。
- 先校验后落地：下到 `.part` → 字节数与 sha256 都对上 → 才解压（逐条防 zip 穿越）。
- 单包失败不中断其余；取消停在当前包，已落地的文件保持完整。
- 清单地址存在 `settings.toml` 的 `[assets] manifest_url`；代理在 `[net] proxy`
  （空 = 交给 `HTTP(S)_PROXY` 环境变量）。

清单按**文件名排序**（可复现）。缺图不报错：渲染层退化到纯文字 / 默认底图。

## 打开方式：独立应用窗口（不碰你日常的浏览器）

双击后不是"用默认浏览器打开一个标签页"，而是**自己起一个无地址栏的应用窗口**：

```
msedge.exe --app=http://127.0.0.1:8000/ --user-data-dir=<exe 同级>\data\browser --no-first-run
```

为什么不用默认浏览器：**你日常那个 Edge 可能是以管理员权限起的**（从管理员终端启动过、
或 Explorer 本身提权）。Windows 有一条硬规矩（UIPI）——普通权限的进程不能把 URL 交给
管理员权限的进程。于是 Edge 会弹：

> Microsoft Edge 未响应，因为现有实例正在以提升的权限运行。是否要用普通权限重启现有实例？

选"是"它就重启自己，**刚打开的那个标签页连窗口一起没了**（实测踩过）。

自己起一个正常权限、独立配置（`data/browser/`，可丢）的实例，这条跨权限交接根本不存在。

- 想用**系统默认浏览器**：`Live2Be.exe --browser`
- 不想自动开：`Live2Be.exe --no-browser`（控制台会打地址）
- 找不到 Chromium 系浏览器时依次退回：提权则 `explorer.exe <url>` 代开 → `webbrowser.open`
- `data/browser/` 是那个窗口的配置目录（首启会创建）。删掉它 = 让那个窗口回到干净状态。

### 如果窗口是**空白**的

先看控制台那行警告：**你已经有 N 个 Edge 进程在跑**。Windows 有条硬规矩（UIPI）——
普通权限的进程不能把地址交给**管理员权限**的进程。

真机确认过的根因：**用「以管理员身份运行」启动本程序**。管理员进程开出来的 Edge 也带
管理员令牌，而且**关掉窗口不等于退出**（Edge 会驻留后台）；之后再用普通权限双击，新进程
没法把地址递给那个管理员实例 —— 表现就是灰色空窗口，关窗时还问"要不要用普通权限"。

处置顺序：

1. **直接双击**（不要「以管理员身份运行」）—— 这是正解；
2. 已经被污染过（后台有管理员 Edge）→ **完全退出 Edge 一次**（托盘图标右键退出，
   或任务管理器结束全部 msedge.exe），再双击；
3. 仍然空白 → `Live2Be.exe --no-browser`，把控制台里的地址自己贴进浏览器；
4. 想要"完全不碰 Edge"的窗口 → `Live2Be.exe --window`（pywebview）。
   ⚠️ **打包版这条路目前不通**：冻结后的 pythonnet 初始化失败
   （`Failed to resolve Python.Runtime.Loader.Initialize`）。程序会自动退回前面几条
   而**不会崩**（已加 try/except）。修它需要单独调 PyInstaller 的 pythonnet 钩子。

已经做了的两道保险：

- 程序**被以管理员身份运行时**，启动浏览器会自动降权（`runas /trustlevel:0x20000`
  基本用户令牌）⇒ 不会再制造"管理员 Edge"；
- 开窗前先确认**页面真的能出**（GET `/` 拿到 `id="app"`），避免"服务没就绪 → 灰窗口"。

- `Live2Be.exe` → 起服务 + 自动开浏览器（`--no-browser` 关掉）
- `Live2Be.exe --window` → 原生窗口（`pywebview`；没装就自动退回浏览器）
- 端口被占且那个端口上确实是 Live2Be → 直接打开已有实例，不报错
- **Ctrl+C 被忽略**；停服务走前端菜单「关闭服务」；关窗口 = 强杀，也是安全的
  （wiki 提交是两阶段的，digest 提交前看关停信号）

## 实测（2026-10-18 · PyInstaller 6.22.3 · 本机）

第一次 `build.ps1` 就过了，没补 hidden import。**完整版**（默认，`assets` 口径 = `full`）产物：

| 部分 | 体积 | 文件 |
|---|---|---|
| `Live2Be.exe` | 13.8 MB | 1 |
| `_internal/`（代码 + 前端 + prompts） | 74.2 MB | 440 |
| `assets/`（四角色 spine+头像 + 435 张背景 + 登录页） | 159.7 MB | 562 |
| `config/`（角色卡 / 世界观） | 0.2 MB | 61 |
| `Live2BeSetup.exe`（配置助手） | 18.7 MB | 1 |
| **合计** | **267 MB** | 1060 |

不算配置助手就是 **248 MB**（助手可以单独发）。助手从 42.1 MB 压到 18.7 MB 的做法是
在 `setup_tool.spec` 的 `excludes` 里加 `numpy` / `PIL` / `pydantic` —— 打包 TOC 里它们各有
几百处引用，而工具一个都不 import（它只用 `infra` + `core.parsing` + tkinter）。

`-Slim` 版是 **约 107 MB**（素材只占 0.4 MB）—— 两者差别只在 `assets/` 与是否需要去「素材状态 / 修复」联网补图。

验过的事（都是对 `dist/Live2Be/Live2Be.exe` 打 HTTP，不是读代码）：

| 探针 | 结果 |
|---|---|
| `--help` | 正常 |
| `/` · `/static/js/gui.js` · `/static/css/main.css` | 200（前端在包里） |
| `/api/menu` | 200，49 张背景 URL（`assets/` 在 exe 同级，找得到） |
| `/api/mmt/characters` | 200，**4 个角色**，头像 URL 全指 `portrait/collection.png` |
| 四个头像 `…/portrait/collection.png` | 全 200（177–219 KB） |
| `/api/spine/igusa_haruka` | 200，`pack=haruka_spr`、14 个情绪→动画映射 |
| 背景 `…/SDIR_Atmosphere/DIR_ViewSora/BG_View_Sky2.jpg` | 200，293 KB |
| 登录页轮播 `/assets/menu/vol2.0/BG_CS_PR2_1.jpg` | 200，485 KB |
| `data/diag/live2be.log` | 自动创建（`APP_ROOT` = exe 同级，可写） |
| `/api/runtime/paths` | 200，五个根都报对（`data` = `<exe 同级>\data`） |
| `/api/runtime/open` | 200，真打开了资源管理器；传 `C:/Windows` → 400（只认四个根） |
| 前端关停 → `/api/shutdown` | 200 → 进程退出码 0 |
| `Live2BeSetup.exe --check` | `有立绘的角色 4 个` · `168 个地点 / 435 张全部在位` |

启动横幅长这样（用户问"数据存哪儿"，答案就在这儿）：

```
02:53:17 web    WebGUI → http://127.0.0.1:8129/
02:53:17 web       角色卡  …\dist\Live2Be\config
02:53:17 web       素材    …\dist\Live2Be\assets
02:53:17 web       数据    …\dist\Live2Be\data   （事件流 / 记忆 / 诊断日志）
02:53:17 web       设置    …\dist\Live2Be\settings.toml
```

**最关键的一条**：塞假 key + `base_url=http://127.0.0.1:9/v1` 发一句话 —— 日志停在
`LLM 调用失败: [WinError 10061] 目标计算机积极拒绝`，**没有 FileNotFound / KeyError**。
说明打进去的 `.md` 提示词在冻结包里读得到（`_internal/` 里 datas 的落点与包内
`Path(__file__).parent` 对得上），整条装配链路是通的。

⚠️ 终端是**管理员权限**时 PyInstaller 6.x 会打一条 deprecation（7.0 会直接拒绝）——
打包不必用管理员。另一个副作用：管理员终端里起 `webgui.serve` 且**不加 `--no-browser`**，
开出来的浏览器会带管理员令牌 —— 冒烟一律加 `--no-browser`。

## 已知坑

1. 冻结后**没有控制台**时（spec 的 `console=True` 改 `False`），日志只落
   `data/diag/live2be.log`；`infra/logsetup.py` 的控制台 handler 会指向空设备。
2. `uvicorn.Config` **不能收字符串** `"webgui.app:app"` —— 冻结后 PyInstaller 看不到那个
   模块。`webgui/serve.py` 已是 `from webgui.app import app` 的真实 import，别改回去。
3. 装到 `C:\Program Files` 下会因权限写不了 `data/` —— 用用户目录或便携目录。
4. `Pillow` 属于可选依赖（`pip install -e ".[image]"`）；exe 里建议装，否则纪念立绘尺寸退化。
5. 单文件（`--onefile`）没做：每次启动解压 100+ MB，且误报率明显更高。
6. `build.ps1` 的 `Copy-Item -Recurse` 到已存在目录会套成 `config/config` —— 已改成先删再拷。

## 后续（这一轮没做）

- 素材包的**托管**还没定：现在只做"可配置素材源"，本地用 `python -m http.server` 验证过
  全链路（切包 → 填地址 → 下载 → 状态变 `installed`）
- 安装器（Inno Setup）：安装目录 + 快捷方式 + 卸载
