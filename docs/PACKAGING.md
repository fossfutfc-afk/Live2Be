# 打包（exe）

目标：双击能跑。**onedir**（不是单文件 exe）—— 启动快、杀软误报少，代价是一个目录。

## 一键

```powershell
C:\Users\johnf\miniconda3\envs\live2be\python.exe -m pip install pyinstaller   # 只需一次
pwsh -File packaging/build.ps1
```

产物在 `dist/Live2Be/`：

```
Live2Be.exe
_internal/         代码 + 前端静态页 + 三处 prompts（RESOURCE_ROOT，只读）
config/            角色卡 / 世界观（CONFIG_ROOT；程序不写，用户可改）
assets/            样张素材（ASSETS_ROOT；程序不写，可自己加）
data/              首次运行自动创建（DATA_ROOT）
.env/settings.toml 首次运行前填 LLM key（APP_ROOT）
```

`infra/paths.py` 的五个根就是按这个形状写的：冻结后 `APP_ROOT = exe 同级`、
`RESOURCE_ROOT = sys._MEIPASS`；`CONFIG/ASSETS/DATA` 还能被 `settings.toml` 的 `[paths]` 覆盖。

## 为什么素材只带一小份

全量 `assets/` 是 **448 MB**（background 251 · illustration 177 · menu 18），塞进包里不现实。
`packaging/collect_samples.py` 按一份**可审阅的清单**挑约 **106 MB**：

| 类 | 范围 |
|---|---|
| `menu/` | 全给（登录页轮播 + logo） |
| `illustration/` | **一个角色**全给（含 `ref/`：纪念生图的参考图） |
| `background/` | `SDIR_Atmosphere` + `SDIR_Clubs` 全给，`SDIR_Schools` 按文件名取前 40 张 |

抽样只用**文件名排序**（可复现）。缺图不报错：渲染层退化到纯文字 / 默认底图。
改清单 = 改 `packaging/collect_samples.py` 顶部那几个常量，然后重新打包。

## 启动与关停（exe 里也是同一套）

- `Live2Be.exe` → 起服务 + 自动开浏览器（`--no-browser` 关掉）
- `Live2Be.exe --window` → 原生窗口（`pywebview`；没装就自动退回浏览器）
- 端口被占且那个端口上确实是 Live2Be → 直接打开已有实例，不报错
- **Ctrl+C 被忽略**；停服务走前端菜单「关闭服务」；关窗口 = 强杀，也是安全的
  （wiki 提交是两阶段的，digest 提交前看关停信号）

## 实测（2026-10-18 · PyInstaller 6.22.3 · 本机）

第一次 `build.ps1` 就过了，没补 hidden import。产物：

| 部分 | 体积 |
|---|---|
| `Live2Be.exe` | 13.4 MB |
| `_internal/`（代码 + 前端 + prompts，345 文件） | 73.6 MB |
| `assets/`（样张，197 文件） | 105.8 MB |
| `config/` | 0.2 MB |
| **合计** | **193 MB** |

验过的事（都是对 `dist/Live2Be/Live2Be.exe` 打 HTTP，不是读代码）：

| 探针 | 结果 |
|---|---|
| `--help` | 正常 |
| `/` · `/static/js/gui.js` · `/static/css/main.css` | 200（前端在包里） |
| `/api/menu` | 200，47 张背景 URL（`assets/` 在 exe 同级，找得到） |
| `/api/mmt/characters` | 200，列出角色与头像 URL（`config/` 读得到） |
| 头像 `assets/illustration/…/collection.png` | 200，218 KB |
| `data/diag/live2be.log` | 自动创建（`APP_ROOT` = exe 同级，可写） |
| 前端关停 → `/api/shutdown` | 200 → 进程退出码 0 |

**最关键的一条**：塞假 key + `base_url=http://127.0.0.1:9/v1` 发一句话 —— 日志停在
`LLM 调用失败: [WinError 10061] 目标计算机积极拒绝`，**没有 FileNotFound / KeyError**。
说明打进去的 `.md` 提示词在冻结包里读得到（`_internal/` 里 datas 的落点与包内
`Path(__file__).parent` 对得上），整条装配链路是通的。

⚠️ 终端是**管理员权限**时 PyInstaller 6.x 会打一条 deprecation（7.0 会直接拒绝）——
打包不必用管理员。

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

- **首次使用向导**（填 key / 选角色 / 试跑一句 / 选素材目录）：后端还缺
  `GET /api/firstrun` 与写 `[paths]` 的入口（`paths` 是 import 期常量，保存后要重启）
- 安装器（Inno Setup）：安装目录 + 快捷方式 + 卸载
