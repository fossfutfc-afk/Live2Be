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

## 已知未验证 / 坑

1. **本仓库的打包链路还没在真机上跑通过**（写这份文档时 `pyinstaller` 尚未安装）。
   第一次 `build.ps1` 大概率要补 hidden import 或 data 文件 —— 报错把最后 20 行贴回来。
2. 冻结后**没有控制台**时（把 spec 的 `console=True` 改成 `False`），日志只落
   `data/diag/live2be.log`；`infra/logsetup.py` 的控制台 handler 会指向空设备。
3. `uvicorn.Config` **不能收字符串** `"webgui.app:app"` —— 冻结后 PyInstaller 看不到那个
   模块。`webgui/serve.py` 已是 `from webgui.app import app` 的真实 import，别改回去。
4. 装到 `C:\Program Files` 下会因权限写不了 `data/` —— 用用户目录或便携目录。
5. `Pillow` 属于可选依赖（`pip install -e ".[image]"`）；exe 里建议装，否则纪念立绘尺寸退化。
6. 单文件（`--onefile`）没做：每次启动解压 100+ MB，且误报率明显更高。

## 后续（这一轮没做）

- **首次使用向导**（填 key / 选角色 / 试跑一句 / 选素材目录）：后端还缺
  `GET /api/firstrun` 与写 `[paths]` 的入口（`paths` 是 import 期常量，保存后要重启）
- 安装器（Inno Setup）：安装目录 + 快捷方式 + 卸载
